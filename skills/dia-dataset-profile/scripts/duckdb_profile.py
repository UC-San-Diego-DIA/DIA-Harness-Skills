#!/usr/bin/env python3
"""Profile one CSV or Excel file through a read-only in-memory DuckDB connection."""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Sequence

try:
    import duckdb
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The Python package 'duckdb' is required. Install it only after the user "
        "confirms the proposed environment and command."
    ) from exc

try:
    import pytz
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The Python package 'pytz' is required for DuckDB timezone results. Install it "
        "only after the user confirms the proposed environment and command."
    ) from exc


TABLE_NAME = "dataset"
SOURCE_FORMATS = {".csv": "csv", ".xlsx": "xlsx"}
ENCODING_ALIASES = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "utf-8-sig": "utf-8",
    "utf-16": "utf-16",
    "utf16": "utf-16",
    "latin-1": "latin-1",
    "latin1": "latin-1",
    "iso-8859-1": "latin-1",
    "iso8859-1": "latin-1",
}
NUMERIC_TYPE_MARKERS = ("decimal", "double", "real", "float", "int")
TEMPORAL_TYPE_MARKERS = ("date", "timestamp")
DEFAULT_TOP_VALUES = 10
MAX_TOP_VALUES = 50
DEFAULT_MAX_ROWS = 200
MAX_ROWS_LIMIT = 1000
XLSX_SHEET_TAG = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"


class ProfileError(RuntimeError):
    """A user-correctable input or configuration error."""


def require_absolute_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise ProfileError(f"{label} must be an absolute path: {raw_path}")
    return path.resolve(strict=False)


def validate_source(source: Path) -> str:
    if not source.is_file():
        raise ProfileError(f"Source does not exist or is not a regular file: {source}")
    suffix = source.suffix.casefold()
    if suffix not in SOURCE_FORMATS:
        raise ProfileError(
            "Source must be a .csv or .xlsx file. Convert .xls workbooks to .xlsx first: "
            f"{source}"
        )
    return SOURCE_FORMATS[suffix]


def sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_encoding(encoding: str | None) -> str | None:
    if encoding is None:
        return None
    normalized = encoding.strip().casefold().replace("_", "-")
    canonical = ENCODING_ALIASES.get(normalized)
    if canonical is None:
        raise ProfileError(
            f"Unsupported encoding {encoding!r}. This helper supports UTF-8, UTF-16 with "
            "a byte-order mark, and Latin-1. Convert the CSV to UTF-8 otherwise."
        )
    return canonical


def configure_base_extensions(connection: Any) -> None:
    connection.execute("SET autoinstall_known_extensions = false")
    connection.execute("SET autoload_known_extensions = false")
    connection.execute("SET allow_community_extensions = false")


def load_source_extension(connection: Any, source_format: str, allow_install: bool) -> None:
    configure_base_extensions(connection)
    if source_format != "xlsx":
        return
    try:
        connection.execute("LOAD excel")
        return
    except duckdb.Error:
        pass
    if not allow_install:
        raise ProfileError(
            "The official DuckDB 'excel' extension is required to read .xlsx files and is "
            "not installed. After the user confirms, rerun this command with "
            "--install-excel-extension, or export the sheet to CSV."
        )
    try:
        connection.execute("INSTALL excel")
        connection.execute("LOAD excel")
    except duckdb.Error as exc:
        raise ProfileError(
            "Could not install the official DuckDB 'excel' extension. Export the sheet to "
            "CSV instead."
        ) from exc


def xlsx_sheet_names(source: Path) -> list[str]:
    try:
        with zipfile.ZipFile(source) as archive:
            content = archive.read("xl/workbook.xml")
        tree = ET.fromstring(content)
        names = [
            element.attrib["name"]
            for element in tree.iter(XLSX_SHEET_TAG)
            if element.attrib.get("name")
        ]
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ProfileError(f"Could not read the .xlsx workbook: {source}: {exc}") from exc
    if not names:
        raise ProfileError(f"The .xlsx workbook has no named sheets: {source}")
    return names


def resolve_sheet(source: Path, requested: str | None) -> str:
    sheets = xlsx_sheet_names(source)
    if requested is None:
        return sheets[0]
    for name in sheets:
        if name.casefold() == requested.casefold():
            return name
    raise ProfileError(
        f"Sheet {requested!r} not found in the workbook. Available sheets: "
        + ", ".join(repr(name) for name in sheets)
    )


def csv_relation(source: Path, args: argparse.Namespace) -> str:
    encoding = normalize_encoding(args.encoding)
    clauses = [
        "header = true",
        "sample_size = -1",
        "ignore_errors = false",
        "normalize_names = false",
    ]
    option_map = (
        ("delim", args.delimiter),
        ("encoding", encoding),
        ("quote", args.quote),
        ("escape", args.escape),
        ("skip", args.skip_rows),
    )
    for name, value in option_map:
        if value is not None:
            clauses.append(f"{name} = {sql_string_literal(str(value))}")
    if args.all_varchar:
        clauses.append("all_varchar = true")
    if args.null_padding:
        clauses.append("null_padding = true")
    return f"read_csv({sql_string_literal(str(source))}, {', '.join(clauses)})"


def xlsx_relation(source: Path, sheet: str) -> str:
    return (
        f"read_xlsx({sql_string_literal(str(source))}, header = true, "
        f"sheet = {sql_string_literal(sheet)})"
    )


def source_relation(source: Path, source_format: str, sheet: str | None, args: argparse.Namespace) -> str:
    if source_format == "csv":
        return csv_relation(source, args)
    return xlsx_relation(source, sheet or resolve_sheet(source, None))


def configure_connection(connection: Any, source: Path, source_format: str, allow_install: bool) -> None:
    load_source_extension(connection, source_format, allow_install)
    connection.execute(f"SET allowed_paths = [{sql_string_literal(str(source))}]")
    connection.execute("SET enable_external_access = false")
    connection.execute("SET lock_configuration = true")


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (dt.date, dt.time, dt.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def is_numeric_type(duckdb_type: str) -> bool:
    lowered = duckdb_type.casefold()
    if lowered.startswith("interval"):
        return False
    return any(lowered.startswith(marker) for marker in NUMERIC_TYPE_MARKERS)


def is_temporal_type(duckdb_type: str) -> bool:
    lowered = duckdb_type.casefold()
    return any(marker in lowered for marker in TEMPORAL_TYPE_MARKERS)


def top_values(connection: Any, column: str, limit: int) -> list[dict[str, Any]]:
    quoted = quote_identifier(column)
    rows = connection.execute(
        f"""
        SELECT CAST({quoted} AS VARCHAR) AS value, count(*) AS n
        FROM {TABLE_NAME}
        WHERE {quoted} IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC, 1
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return [{"value": value, "count": int(count)} for value, count in rows]


def numeric_stats(connection: Any, column: str, row_count: int) -> dict[str, Any]:
    quoted = quote_identifier(column)
    row = connection.execute(
        f"""
        SELECT
            min({quoted}),
            max({quoted}),
            avg({quoted}),
            stddev_samp({quoted}),
            quantile_cont({quoted}, 0.25),
            quantile_cont({quoted}, 0.5),
            quantile_cont({quoted}, 0.75)
        FROM {TABLE_NAME}
        WHERE {quoted} IS NOT NULL
        """
    ).fetchone()
    if row is None:
        raise ProfileError(f"No non-null values found for {column!r}.")
    minimum, maximum, mean, stddev, q1, median, q3 = row
    if q1 is None or q3 is None:
        raise ProfileError(f"Not enough non-null values to compute quartiles for {column!r}.")
    q1 = float(q1)
    q3 = float(q3)
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    outlier_count = connection.execute(
        f"""
        SELECT count(*)
        FROM {TABLE_NAME}
        WHERE {quoted} IS NOT NULL AND ({quoted} < ? OR {quoted} > ?)
        """,
        [low, high],
    ).fetchone()[0]
    stats = {
        "min": json_value(minimum),
        "max": json_value(maximum),
        "mean": json_value(mean),
        "stddev": json_value(stddev),
        "q1": json_value(q1),
        "median": json_value(median),
        "q3": json_value(q3),
        "iqr_low": json_value(low),
        "iqr_high": json_value(high),
        "outlier_count": int(outlier_count),
    }
    if row_count == 0:
        raise ProfileError(f"The dataset has no rows; quartiles are undefined for {column!r}.")
    return stats


def temporal_stats(connection: Any, column: str) -> dict[str, Any]:
    quoted = quote_identifier(column)
    row = connection.execute(
        f"SELECT min({quoted}), max({quoted}) FROM {TABLE_NAME} WHERE {quoted} IS NOT NULL"
    ).fetchone()
    if row is None:
        raise ProfileError(f"No non-null values found for {column!r}.")
    return {"min": json_value(row[0]), "max": json_value(row[1])}


def validate_column_names(names: Sequence[str]) -> None:
    blank = [name for name in names if not name.strip()]
    if blank:
        raise ProfileError(
            "The source has blank parsed column names. Fix the header row or pass the "
            "appropriate CSV overrides."
        )
    duplicates: dict[str, list[str]] = {}
    for name in names:
        duplicates.setdefault(name.casefold(), []).append(name)
    collision_groups = [values for values in duplicates.values() if len(values) > 1]
    if collision_groups:
        rendered = "; ".join(", ".join(repr(value) for value in group) for group in collision_groups)
        raise ProfileError(f"The source has duplicate column names: {rendered}")


def profile_command(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.top_values <= MAX_TOP_VALUES:
        raise ProfileError(f"top-values must be between 1 and {MAX_TOP_VALUES}.")
    source = require_absolute_path(args.source, "Source")
    source_format = validate_source(source)
    sheet = resolve_sheet(source, args.sheet) if source_format == "xlsx" else None

    connection = duckdb.connect(":memory:")
    try:
        configure_connection(connection, source, source_format, args.install_excel_extension)
        relation = source_relation(source, source_format, sheet, args)
        connection.execute(
            f"CREATE VIEW {quote_identifier(TABLE_NAME)} AS SELECT * FROM {relation}"
        )
        described = connection.execute(f"DESCRIBE {TABLE_NAME}").fetchall()
        names = [str(row[0]) for row in described]
        types = [str(row[1]) for row in described]
        validate_column_names(names)

        row_count = int(connection.execute(f"SELECT count(*) FROM {TABLE_NAME}").fetchone()[0])
        null_projection = ", ".join(
            f"count(*) FILTER (WHERE {quote_identifier(name)} IS NULL)" for name in names
        )
        null_counts = list(connection.execute(f"SELECT {null_projection} FROM {TABLE_NAME}").fetchone())

        columns: list[dict[str, Any]] = []
        for index, name in enumerate(names):
            quoted = quote_identifier(name)
            null_count = int(null_counts[index])
            column: dict[str, Any] = {
                "name": name,
                "duckdb_type": types[index],
                "null_count": null_count,
                "null_rate": (null_count / row_count) if row_count else None,
            }
            column["distinct_count"] = int(
                connection.execute(f"SELECT count(DISTINCT {quoted}) FROM {TABLE_NAME}").fetchone()[0]
            )
            column["top_values"] = top_values(connection, name, args.top_values)
            try:
                if is_numeric_type(types[index]):
                    column.update(numeric_stats(connection, name, row_count))
                elif is_temporal_type(types[index]):
                    column.update(temporal_stats(connection, name))
            except (duckdb.Error, ProfileError) as exc:
                column["stats_error"] = str(exc)
            columns.append(column)

        candidate_keys = [
            column["name"]
            for column in columns
            if column["null_count"] == 0
            and column["distinct_count"] == row_count
            and row_count > 0
        ]
        duplicate_row_count = int(
            connection.execute(
                "SELECT count(*) FROM (SELECT 1 AS one FROM dataset GROUP BY ALL HAVING count(*) > 1)"
            ).fetchone()[0]
        )
    finally:
        connection.close()

    return {
        "action": "profile",
        "source": str(source),
        "source_file": source.name,
        "source_format": source_format,
        "sheet": sheet,
        "generated_at": utc_now(),
        "python_executable": sys.executable,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "candidate_keys": candidate_keys,
        "duplicate_row_count": duplicate_row_count,
    }


def query_command(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.max_rows <= MAX_ROWS_LIMIT:
        raise ProfileError(f"max-rows must be between 1 and {MAX_ROWS_LIMIT}.")
    source = require_absolute_path(args.source, "Source")
    source_format = validate_source(source)
    sheet = resolve_sheet(source, args.sheet) if source_format == "xlsx" else None
    sql_file = require_absolute_path(args.sql_file, "SQL file")
    if not sql_file.is_file():
        raise ProfileError(f"SQL file does not exist: {sql_file}")
    sql = sql_file.read_text(encoding="utf-8").strip()
    if not sql:
        raise ProfileError("SQL file is empty.")

    connection = duckdb.connect(":memory:")
    try:
        configure_connection(connection, source, source_format, args.install_excel_extension)
        relation = source_relation(source, source_format, sheet, args)
        connection.execute(
            f"CREATE VIEW {quote_identifier(TABLE_NAME)} AS SELECT * FROM {relation}"
        )
        statements = connection.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            statement_types = [statement.type.name for statement in statements]
            raise ProfileError(
                "Analysis SQL must contain exactly one SELECT statement. "
                f"Parsed statement types: {statement_types}"
            )
        try:
            cursor = connection.execute(sql)
        except duckdb.Error as exc:
            raise ProfileError(f"DuckDB query failed: {exc}") from exc
        column_names = [description[0] for description in cursor.description]
        fetched = cursor.fetchmany(args.max_rows + 1)
        truncated = len(fetched) > args.max_rows
        rows = fetched[: args.max_rows]
    finally:
        connection.close()

    return {
        "action": "query",
        "source": str(source),
        "source_file": source.name,
        "source_format": source_format,
        "sheet": sheet,
        "columns": column_names,
        "rows": [[json_value(value) for value in row] for row in rows],
        "returned_rows": len(rows),
        "truncated": truncated,
        "max_rows": args.max_rows,
    }


def inspect_command(args: argparse.Namespace) -> dict[str, Any]:
    source = require_absolute_path(args.source, "Source")
    source_format = validate_source(source)
    result: dict[str, Any] = {"source": str(source), "format": source_format}
    if source_format == "xlsx":
        result["sheets"] = xlsx_sheet_names(source)
    return result


def add_csv_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--delimiter")
    parser.add_argument("--encoding")
    parser.add_argument("--quote")
    parser.add_argument("--escape")
    parser.add_argument("--skip-rows", type=int)
    parser.add_argument("--all-varchar", action="store_true")
    parser.add_argument("--null-padding", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="Profile one source file")
    profile_parser.add_argument("--source", required=True)
    profile_parser.add_argument("--sheet")
    profile_parser.add_argument("--top-values", type=int, default=DEFAULT_TOP_VALUES)
    profile_parser.add_argument("--install-excel-extension", action="store_true")
    add_csv_override_arguments(profile_parser)

    query_parser = subparsers.add_parser("query", help="Run one read-only SELECT against the source")
    query_parser.add_argument("--source", required=True)
    query_parser.add_argument("--sql-file", required=True)
    query_parser.add_argument("--sheet")
    query_parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    query_parser.add_argument("--install-excel-extension", action="store_true")
    add_csv_override_arguments(query_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Report source format and sheets")
    inspect_parser.add_argument("--source", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "profile":
            result = profile_command(args)
        elif args.command == "query":
            result = query_command(args)
        else:
            result = inspect_command(args)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    except ProfileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
