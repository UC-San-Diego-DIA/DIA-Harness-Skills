#!/usr/bin/env python3
"""Create, re-link, and query a DuckDB analysis workspace over one source file."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
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
DATABASE_NAME = "analysis.duckdb"
ANALYSIS_NAME = "ANALYSIS.md"
QUESTIONS_HEADING = "## Questions"
SOURCE_FORMATS = {".csv": "csv", ".xlsx": "xlsx"}
WORKSPACE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
QUERY_FILE_PATTERN = re.compile(r"^(\d+)-.*\.sql$", re.IGNORECASE)
DATA_ANALYSIS_MARKERS = (
    ("AGENTS.md", True),
    ("data/raw", False),
    ("data/output", False),
    ("scripts", False),
    ("scripts/README.md", True),
)
XLSX_SHEET_TAG = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
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


class WorkspaceError(RuntimeError):
    """A user-correctable workspace or input error."""


def require_absolute_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise WorkspaceError(f"{label} must be an absolute path: {raw_path}")
    return path.resolve(strict=False)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def validate_data_analysis_root(root: Path) -> None:
    missing = []
    for relative, is_file in DATA_ANALYSIS_MARKERS:
        path = root / relative
        if is_file and not path.is_file():
            missing.append(str(path))
        if not is_file and not path.is_dir():
            missing.append(str(path))
    if missing:
        raise WorkspaceError(
            "Target is not a data-analysis workspace. Missing: " + ", ".join(missing)
        )


def validate_setup_paths(workspace_raw: str, source_raw: str) -> tuple[Path, Path, Path]:
    workspace = require_absolute_path(workspace_raw, "Workspace")
    source = require_absolute_path(source_raw, "Source")

    if not WORKSPACE_NAME_PATTERN.fullmatch(workspace.name):
        raise WorkspaceError(
            "Analysis workspace folder name must use lowercase letters, digits, and "
            f"single hyphens: {workspace.name}"
        )
    if workspace.parent.name.casefold() != "analysis":
        raise WorkspaceError(
            "Analysis workspace must be directly under a scratch\\analysis folder: "
            f"{workspace.parent}"
        )
    scratch = workspace.parent.parent
    if scratch.name.casefold() != "scratch":
        raise WorkspaceError(
            f"Analysis workspace must live under a scratch folder: {scratch}"
        )
    root = scratch.parent
    if not root.is_dir():
        raise WorkspaceError(f"Data-analysis workspace root does not exist: {root}")
    validate_data_analysis_root(root)

    if not source.is_file():
        raise WorkspaceError(f"Source does not exist or is not a regular file: {source}")
    if source.suffix.casefold() not in SOURCE_FORMATS:
        raise WorkspaceError(
            "Source must be a .csv or .xlsx file. Convert .xls workbooks to .xlsx first: "
            f"{source}"
        )

    source_resolved = source.resolve(strict=False)
    allowed_areas = [
        (root / "data" / "raw").resolve(strict=False),
        (root / "data" / "output").resolve(strict=False),
    ]
    if not any(is_within(source_resolved, area) for area in allowed_areas):
        raise WorkspaceError(
            "Source must live under data\\raw or data\\output of the data-analysis "
            f"workspace: {root}"
        )
    if is_within(source_resolved, workspace.resolve(strict=False)):
        raise WorkspaceError("Source cannot be inside the analysis workspace.")

    return workspace, source, root


def normalize_header(header: str) -> str:
    ascii_header = (
        unicodedata.normalize("NFKD", header.strip()).encode("ascii", "ignore").decode("ascii")
    )
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_header).strip("_").lower()
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        raise WorkspaceError(f"Header cannot be normalized to snake_case: {header!r}")
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized


def validate_header_names(raw_headers: Sequence[str]) -> None:
    blank_headers = [index + 1 for index, value in enumerate(raw_headers) if not value.strip()]
    if blank_headers:
        joined = ", ".join(str(index) for index in blank_headers)
        raise WorkspaceError(f"Source has blank headers in column positions: {joined}")

    duplicates: dict[str, list[str]] = {}
    for value in raw_headers:
        duplicates.setdefault(value.strip().casefold(), []).append(value)
    duplicate_groups = [values for values in duplicates.values() if len(values) > 1]
    if duplicate_groups:
        rendered = "; ".join(", ".join(repr(value) for value in group) for group in duplicate_groups)
        raise WorkspaceError(f"Source has duplicate headers: {rendered}")


def normalized_headers(raw_headers: Sequence[str]) -> list[str]:
    validate_header_names(raw_headers)
    normalized = [normalize_header(value) for value in raw_headers]
    collisions: dict[str, list[str]] = {}
    for original, sql_name in zip(raw_headers, normalized):
        collisions.setdefault(sql_name.casefold(), []).append(original)
    collision_groups = [values for values in collisions.values() if len(values) > 1]
    if collision_groups:
        rendered = "; ".join(", ".join(repr(value) for value in group) for group in collision_groups)
        raise WorkspaceError(f"Headers collide after snake_case normalization: {rendered}")
    return normalized


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def link_id(linked_at: str, source_hash: str) -> str:
    compact_time = re.sub(r"[-:.+]", "", linked_at)
    return f"{compact_time}-{source_hash[:12]}"


def normalize_encoding(encoding: str | None) -> str | None:
    if encoding is None:
        return None
    normalized = encoding.strip().casefold().replace("_", "-")
    canonical = ENCODING_ALIASES.get(normalized)
    if canonical is None:
        raise WorkspaceError(
            f"Unsupported encoding {encoding!r}. Without a DuckDB extension, this helper "
            "supports UTF-8, UTF-16 with a byte-order mark, and Latin-1. Convert the CSV "
            "to UTF-8 before setup. The helper never installs or loads encoding extensions."
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
        raise WorkspaceError(
            "The official DuckDB 'excel' extension is required to read .xlsx files and is "
            "not installed. After the user confirms, rerun this command with "
            "--install-excel-extension, or export the sheet to CSV."
        )
    try:
        connection.execute("INSTALL excel")
        connection.execute("LOAD excel")
    except duckdb.Error as exc:
        raise WorkspaceError(
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
        raise WorkspaceError(f"Could not read the .xlsx workbook: {source}: {exc}") from exc
    if not names:
        raise WorkspaceError(f"The .xlsx workbook has no named sheets: {source}")
    return names


def resolve_sheet(source: Path, requested: str | None) -> str:
    sheets = xlsx_sheet_names(source)
    if requested is None:
        return sheets[0]
    for name in sheets:
        if name.casefold() == requested.casefold():
            return name
    raise WorkspaceError(
        f"Sheet {requested!r} not found in the workbook. Available sheets: "
        + ", ".join(repr(name) for name in sheets)
    )


def xlsx_relation(source: Path, sheet: str) -> str:
    return (
        f"read_xlsx({sql_string_literal(str(source))}, header = true, "
        f"sheet = {sql_string_literal(sheet)})"
    )


def xlsx_header_row_relation(source: Path, sheet: str) -> str:
    # header = false keeps the first row as data, so it can be read back as
    # the header row even though the view relation uses header = true.
    return (
        f"read_xlsx({sql_string_literal(str(source))}, header = false, "
        f"sheet = {sql_string_literal(sheet)})"
    )


def read_xlsx_headers(connection: Any, source: Path, sheet: str) -> tuple[list[str], list[str]]:
    cursor = connection.execute(
        f"SELECT * FROM {xlsx_header_row_relation(source, sheet)} LIMIT 1"
    )
    relation_names = [str(column[0]) for column in cursor.description]
    row = cursor.fetchone()
    if row is None:
        raise WorkspaceError(f"Sheet {sheet!r} contains no rows to use as a header.")
    headers = ["" if value is None else str(value) for value in row]
    return relation_names, headers


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
        ("dateformat", args.date_format),
        ("timestampformat", args.timestamp_format),
    )
    for name, value in option_map:
        if value is not None:
            clauses.append(f"{name} = {sql_string_literal(str(value))}")
    if args.all_varchar:
        clauses.append("all_varchar = true")
    if args.null_padding:
        clauses.append("null_padding = true")
    return f"read_csv({sql_string_literal(str(source))}, {', '.join(clauses)})"


def sniff_dialect(connection: Any, source: Path, args: argparse.Namespace) -> tuple[str, str, str, int, bool]:
    encoding = normalize_encoding(args.encoding)
    clauses = ["sample_size = -1"]
    parameters: list[Any] = [str(source)]
    option_map = (
        ("delim", args.delimiter),
        ("quote", args.quote),
        ("escape", args.escape),
        ("skip", args.skip_rows),
        ("encoding", encoding),
        ("dateformat", args.date_format),
        ("timestampformat", args.timestamp_format),
    )
    for sql_name, value in option_map:
        if value is not None:
            clauses.append(f"{sql_name} = ?")
            parameters.append(value)
    if args.null_padding:
        clauses.append("null_padding = true")
    if args.force_header:
        clauses.append("header = true")

    query = (
        'SELECT "Delimiter", "Quote", "Escape", "SkipRows", "HasHeader" '
        f"FROM sniff_csv(?, {', '.join(clauses)})"
    )
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise WorkspaceError("DuckDB could not detect the CSV format.")
    delimiter, quote, escape, skip_rows, has_header = row
    quote = "" if quote in (None, "(empty)") else str(quote)
    escape = "" if escape in (None, "(empty)") else str(escape)
    return str(delimiter), quote, escape, int(skip_rows), bool(has_header)


def read_raw_headers(
    source: Path,
    delimiter: str,
    quote: str,
    escape: str,
    skip_rows: int,
    encoding: str | None,
) -> list[str]:
    python_encoding = normalize_encoding(encoding) or "utf-8-sig"
    if python_encoding.casefold().replace("_", "-") == "utf-8":
        python_encoding = "utf-8-sig"

    reader_options: dict[str, Any] = {"delimiter": delimiter}
    if quote:
        reader_options["quotechar"] = quote
    else:
        reader_options["quoting"] = csv.QUOTE_NONE
    if escape and escape != quote:
        reader_options["escapechar"] = escape

    try:
        with source.open("r", encoding=python_encoding, newline="") as handle:
            reader = csv.reader(handle, **reader_options)
            for _ in range(skip_rows):
                next(reader, None)
            header = next(reader, None)
    except (LookupError, UnicodeDecodeError, csv.Error) as exc:
        raise WorkspaceError(
            f"Could not read the CSV header with encoding {python_encoding!r}: {exc}"
        ) from exc

    if header is None:
        raise WorkspaceError("CSV does not contain a header row.")
    return [str(value) for value in header]


def existing_links(database_path: Path) -> list[dict[str, Any]]:
    if not database_path.is_file():
        raise WorkspaceError(f"Workspace database is missing: {database_path}")
    connection = None
    try:
        connection = duckdb.connect(str(database_path), read_only=True)
        configure_base_extensions(connection)
        rows = connection.execute(
            """
            SELECT link_id, linked_at, source_path, source_file, source_hash,
                   source_format, sheet, row_count, read_options, python_executable,
                   is_current
            FROM _analysis_links
            ORDER BY linked_at
            """
        ).fetchall()
    except Exception as exc:
        raise WorkspaceError(f"Workspace metadata is invalid: {database_path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    keys = (
        "link_id",
        "linked_at",
        "source_path",
        "source_file",
        "source_hash",
        "source_format",
        "sheet",
        "row_count",
        "read_options",
        "python_executable",
        "is_current",
    )
    return [dict(zip(keys, row)) for row in rows]


def current_link(links: Sequence[dict[str, Any]]) -> dict[str, Any]:
    current = [link for link in links if link["is_current"]]
    if len(current) != 1:
        raise WorkspaceError("Workspace must contain exactly one current source link.")
    return current[0]


def build_workspace(
    database_path: Path,
    source: Path,
    args: argparse.Namespace,
    prior_links: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    source_format = SOURCE_FORMATS[source.suffix.casefold()]
    sheet = resolve_sheet(source, args.sheet) if source_format == "xlsx" else None
    linked_at = utc_now()
    source_hash = file_sha256(source)
    new_link_id = link_id(linked_at, source_hash)

    connection = duckdb.connect(str(database_path))
    try:
        load_source_extension(connection, source_format, args.install_excel_extension)
        if source_format == "csv":
            delimiter, quote, escape, skip_rows, has_header = sniff_dialect(connection, source, args)
            if not has_header and not args.force_header:
                raise WorkspaceError(
                    "DuckDB did not detect a header row. Retry with --force-header only "
                    "if the first data row is the header."
                )
            raw_headers = read_raw_headers(source, delimiter, quote, escape, skip_rows, args.encoding)
            sql_headers = normalized_headers(raw_headers)
            relation = csv_relation(source, args)
            header_cursor = connection.execute(f"SELECT * FROM {relation} LIMIT 0")
            relation_names = [str(column[0]) for column in header_cursor.description]
        else:
            relation_names, raw_headers = read_xlsx_headers(connection, source, sheet)
            sql_headers = normalized_headers(raw_headers)
            relation = xlsx_relation(source, sheet)
            header_cursor = connection.execute(f"SELECT * FROM {relation} LIMIT 0")
            relation_names = [str(column[0]) for column in header_cursor.description]

        if len(relation_names) != len(raw_headers):
            raise WorkspaceError(
                "DuckDB parsed a different number of columns than the header row: "
                f"header={len(raw_headers)}, parsed={len(relation_names)}"
            )

        projection = ", ".join(
            f"{quote_identifier(actual)} AS {quote_identifier(normalized)}"
            for actual, normalized in zip(relation_names, sql_headers)
        )
        connection.execute(
            f"CREATE VIEW {quote_identifier(TABLE_NAME)} AS SELECT {projection} FROM {relation}"
        )

        row_count = int(connection.execute(f"SELECT count(*) FROM {TABLE_NAME}").fetchone()[0])
        described = connection.execute(f"DESCRIBE {TABLE_NAME}").fetchall()
        type_by_name = {str(row[0]): str(row[1]) for row in described}
        null_projection = ", ".join(
            f"count(*) FILTER (WHERE {quote_identifier(name)} IS NULL)"
            for name in sql_headers
        )
        null_counts = list(
            connection.execute(f"SELECT {null_projection} FROM {TABLE_NAME}").fetchone()
        )

        connection.execute(
            """
            CREATE TABLE _analysis_links (
                link_id VARCHAR PRIMARY KEY,
                linked_at VARCHAR NOT NULL,
                source_path VARCHAR NOT NULL,
                source_file VARCHAR NOT NULL,
                source_hash VARCHAR NOT NULL,
                source_format VARCHAR NOT NULL,
                sheet VARCHAR,
                row_count BIGINT NOT NULL,
                read_options VARCHAR NOT NULL,
                python_executable VARCHAR NOT NULL,
                is_current BOOLEAN NOT NULL
            )
            """
        )
        for link in prior_links:
            connection.execute(
                """
                INSERT INTO _analysis_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, false)
                """,
                [
                    link["link_id"],
                    link["linked_at"],
                    link["source_path"],
                    link["source_file"],
                    link["source_hash"],
                    link["source_format"],
                    link["sheet"],
                    link["row_count"],
                    link["read_options"],
                    link["python_executable"],
                ],
            )
        if source_format == "xlsx":
            read_options: dict[str, Any] = {"sheet": sheet}
        else:
            read_options = {
                "header": True,
                "sample_size": -1,
                "ignore_errors": False,
                "normalize_names": False,
            }
            optional_values = {
                "delimiter": args.delimiter,
                "encoding": normalize_encoding(args.encoding),
                "quotechar": args.quote,
                "escapechar": args.escape,
                "skiprows": args.skip_rows,
                "date_format": args.date_format,
                "timestamp_format": args.timestamp_format,
            }
            read_options.update(
                {key: value for key, value in optional_values.items() if value is not None}
            )
            if args.all_varchar:
                read_options["all_varchar"] = True
            if args.null_padding:
                read_options["null_padding"] = True
        serialized_options = json.dumps(read_options, sort_keys=True)
        connection.execute(
            """
            INSERT INTO _analysis_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true)
            """,
            [
                new_link_id,
                linked_at,
                str(source),
                source.name,
                source_hash,
                source_format,
                sheet,
                row_count,
                serialized_options,
                sys.executable,
            ],
        )

        connection.execute(
            """
            CREATE TABLE _analysis_columns (
                link_id VARCHAR NOT NULL,
                ordinal INTEGER NOT NULL,
                original_name VARCHAR NOT NULL,
                sql_name VARCHAR NOT NULL,
                duckdb_type VARCHAR NOT NULL,
                null_count BIGINT NOT NULL
            )
            """
        )
        columns: list[dict[str, Any]] = []
        for ordinal, (original, sql_name, null_count) in enumerate(
            zip(raw_headers, sql_headers, null_counts), start=1
        ):
            column = {
                "ordinal": ordinal,
                "original_name": original,
                "sql_name": sql_name,
                "duckdb_type": type_by_name[sql_name],
                "null_count": int(null_count),
            }
            columns.append(column)
            connection.execute(
                "INSERT INTO _analysis_columns VALUES (?, ?, ?, ?, ?, ?)",
                [
                    new_link_id,
                    ordinal,
                    original,
                    sql_name,
                    type_by_name[sql_name],
                    int(null_count),
                ],
            )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    links = [dict(link, is_current=False) for link in prior_links]
    links.append(
        {
            "link_id": new_link_id,
            "linked_at": linked_at,
            "source_path": str(source),
            "source_file": source.name,
            "source_hash": source_hash,
            "source_format": source_format,
            "sheet": sheet,
            "row_count": row_count,
            "read_options": serialized_options,
            "python_executable": sys.executable,
            "is_current": True,
        }
    )
    return {
        "link_id": new_link_id,
        "linked_at": linked_at,
        "source_path": str(source),
        "source_file": source.name,
        "source_format": source_format,
        "sheet": sheet,
        "source_hash": source_hash,
        "row_count": row_count,
        "read_options": read_options,
        "python_executable": sys.executable,
        "columns": columns,
        "links": links,
    }


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def questions_section(existing_analysis: str | None) -> str:
    if not existing_analysis or QUESTIONS_HEADING not in existing_analysis:
        return f"{QUESTIONS_HEADING}\n\nNo questions recorded yet.\n"
    return QUESTIONS_HEADING + existing_analysis.split(QUESTIONS_HEADING, 1)[1]


def render_analysis_markdown(summary: dict[str, Any], existing_analysis: str | None) -> str:
    lines = [
        f"# Analysis: {Path(summary['source_file']).stem}",
        "",
        "This workspace answers questions directly against one source file. No data is copied.",
        "The `dataset` view references:",
        "",
        f"`{summary['source_path']}`",
        "",
        "If that file changes, questions stop until a confirmed re-link updates this workspace.",
        "",
        "## Current source",
        "",
        f"- Link ID: `{summary['link_id']}`",
        f"- Linked at: `{summary['linked_at']}`",
        f"- Source path: `{summary['source_path']}`",
        f"- Format: {summary['source_format']}",
    ]
    if summary["source_format"] == "xlsx":
        lines.append(f"- Sheet: `{summary['sheet']}`")
    lines.extend(
        [
            f"- SHA-256: `{summary['source_hash']}`",
            f"- DuckDB view: `{TABLE_NAME}`",
            f"- Python executable: `{summary['python_executable']}`",
            f"- Rows: {summary['row_count']}",
            f"- Read options: `{json.dumps(summary['read_options'], sort_keys=True)}`",
            "",
            "## Columns",
            "",
            "| # | Original header | SQL name | DuckDB type | Nulls |",
            "| ---: | --- | --- | --- | ---: |",
        ]
    )
    for column in summary["columns"]:
        lines.append(
            "| {ordinal} | {original} | `{sql_name}` | `{duckdb_type}` | {null_count} |".format(
                ordinal=column["ordinal"],
                original=markdown_escape(column["original_name"]),
                sql_name=markdown_escape(column["sql_name"]),
                duckdb_type=markdown_escape(column["duckdb_type"]),
                null_count=column["null_count"],
            )
        )

    lines.extend(["", "## Source history", ""])
    for link in summary["links"]:
        status = "current" if link["is_current"] else "superseded"
        lines.append(
            f"- `{link['link_id']}`: {link['linked_at']}, "
            f"{link['row_count']} rows, {status}"
        )

    lines.extend(["", questions_section(existing_analysis).rstrip(), ""])
    return "\n".join(lines)


def remove_checked_tree(path: Path, expected_parent: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_parent = expected_parent.resolve(strict=True)
    if resolved_path.parent != resolved_parent or not resolved_path.name.startswith("."):
        raise WorkspaceError(f"Refusing to remove unchecked temporary directory: {resolved_path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)


def install_created_workspace(stage: Path, workspace: Path) -> None:
    if workspace.exists():
        raise WorkspaceError(f"Workspace already exists: {workspace}")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, workspace)


def replace_refreshed_files(stage: Path, workspace: Path) -> None:
    backup = Path(
        tempfile.mkdtemp(prefix=f".{workspace.name}.backup-", dir=str(workspace.parent))
    )
    names = (DATABASE_NAME, ANALYSIS_NAME)
    moved_old: list[str] = []
    moved_new: list[str] = []
    completed = False
    try:
        for name in names:
            old_path = workspace / name
            if not old_path.exists():
                raise WorkspaceError(f"Workspace is missing required item: {old_path}")
            os.replace(old_path, backup / name)
            moved_old.append(name)
        for name in names:
            os.replace(stage / name, workspace / name)
            moved_new.append(name)
        completed = True
    except Exception as refresh_error:
        rollback_errors: list[str] = []
        for name in reversed(moved_new):
            try:
                current_path = workspace / name
                if current_path.exists():
                    os.replace(current_path, stage / name)
            except Exception as exc:
                rollback_errors.append(f"new {name}: {exc}")
        for name in reversed(moved_old):
            try:
                backup_path = backup / name
                if backup_path.exists():
                    os.replace(backup_path, workspace / name)
            except Exception as exc:
                rollback_errors.append(f"original {name}: {exc}")
        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise WorkspaceError(
                f"Re-link failed and rollback was incomplete. Recovery files remain at {backup}. "
                f"Rollback errors: {details}"
            ) from refresh_error
        raise
    finally:
        if completed or not any(backup.iterdir()):
            remove_checked_tree(backup, workspace.parent)


def validate_existing_workspace(workspace: Path, source: Path, requested_sheet: str | None) -> tuple[list[dict[str, Any]], str]:
    required = (
        workspace / DATABASE_NAME,
        workspace / ANALYSIS_NAME,
        workspace / "queries",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise WorkspaceError("Existing target is not a valid workspace. Missing: " + ", ".join(missing))
    links = existing_links(workspace / DATABASE_NAME)
    current = current_link(links)
    current_source = os.path.normcase(os.path.normpath(str(current["source_path"])))
    requested_source = os.path.normcase(os.path.normpath(str(source)))
    if current_source != requested_source:
        raise WorkspaceError(
            "Existing workspace belongs to a different source file: "
            f"{current['source_path']}"
        )
    current_format = str(current["source_format"])
    if current_format != SOURCE_FORMATS[source.suffix.casefold()]:
        raise WorkspaceError(
            f"Existing workspace expects a {current_format} source: {current['source_path']}"
        )
    if current_format == "xlsx":
        current_sheet = current["sheet"]
        resolved_sheet = resolve_sheet(source, requested_sheet)
        if str(current_sheet) != resolved_sheet:
            raise WorkspaceError(
                f"Existing workspace belongs to sheet {current_sheet!r}, not {resolved_sheet!r}."
            )
    existing_analysis = (workspace / ANALYSIS_NAME).read_text(encoding="utf-8")
    return links, existing_analysis


def setup_command(args: argparse.Namespace) -> dict[str, Any]:
    workspace, source, root = validate_setup_paths(args.workspace, args.source)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    prior_links: list[dict[str, Any]] = []
    existing_analysis: str | None = None
    if args.refresh:
        if not workspace.is_dir():
            raise WorkspaceError(f"Refresh requires an existing workspace: {workspace}")
        prior_links, existing_analysis = validate_existing_workspace(workspace, source, args.sheet)
    elif workspace.exists():
        raise WorkspaceError(f"Workspace already exists. Use a different name or confirm re-link: {workspace}")

    stage = Path(
        tempfile.mkdtemp(prefix=f".{workspace.name}.staging-", dir=str(workspace.parent))
    )
    try:
        try:
            summary = build_workspace(stage / DATABASE_NAME, source, args, prior_links)
            (stage / ANALYSIS_NAME).write_text(
                render_analysis_markdown(summary, existing_analysis), encoding="utf-8", newline="\n"
            )
            (stage / "queries").mkdir()
        except duckdb.Error as exc:
            raise WorkspaceError(f"DuckDB could not prepare the source: {exc}") from exc
        if args.refresh:
            replace_refreshed_files(stage, workspace)
        else:
            install_created_workspace(stage, workspace)
        summary.update(
            {
                "action": "relinked" if args.refresh else "created",
                "workspace": str(workspace),
                "database": str(workspace / DATABASE_NAME),
                "view": TABLE_NAME,
                "data_analysis_root": str(root),
            }
        )
        return summary
    finally:
        if stage.exists():
            remove_checked_tree(stage, workspace.parent)


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


def query_slug(question: str) -> str:
    ascii_question = (
        unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_question).strip("-").lower()
    return (slug[:60].rstrip("-") or "analysis-question")


def next_query_path(queries_dir: Path, question: str) -> Path:
    numbers = []
    for path in queries_dir.iterdir():
        match = QUERY_FILE_PATTERN.fullmatch(path.name)
        if match:
            numbers.append(int(match.group(1)))
    next_number = max(numbers, default=0) + 1
    return queries_dir / f"{next_number:03d}-{query_slug(question)}.sql"


def configure_query_connection(connection: Any, source: Path, source_format: str, allow_install: bool) -> None:
    load_source_extension(connection, source_format, allow_install)
    connection.execute(f"SET allowed_paths = [{sql_string_literal(str(source))}]")
    connection.execute("SET enable_external_access = false")
    connection.execute("SET lock_configuration = true")


def verify_source_matches(current: dict[str, Any], source: Path) -> None:
    if not source.is_file():
        raise WorkspaceError(
            "Source file is missing: "
            f"{source}. Restore it, or confirm a re-link with the user and rerun setup "
            "with --refresh."
        )
    actual_hash = file_sha256(source)
    if actual_hash != str(current["source_hash"]):
        raise WorkspaceError(
            "The source file changed since this workspace was linked. Recorded SHA-256: "
            f"{current['source_hash']}. Current SHA-256: {actual_hash}. Earlier answers "
            "describe the earlier version. After confirming with the user, rerun setup "
            "with --refresh to re-link this workspace."
        )


def query_command(args: argparse.Namespace) -> dict[str, Any]:
    workspace = require_absolute_path(args.workspace, "Workspace")
    sql_file = require_absolute_path(args.sql_file, "SQL file")
    if not workspace.is_dir():
        raise WorkspaceError(f"Workspace does not exist: {workspace}")
    if not sql_file.is_file():
        raise WorkspaceError(f"SQL file does not exist: {sql_file}")
    if not args.question.strip():
        raise WorkspaceError("Question cannot be empty.")
    if args.max_rows < 1 or args.max_rows > 1000:
        raise WorkspaceError("max-rows must be between 1 and 1000.")

    database_path = workspace / DATABASE_NAME
    queries_dir = workspace / "queries"
    required = (
        database_path,
        workspace / ANALYSIS_NAME,
        queries_dir,
    )
    if any(not path.exists() for path in required):
        raise WorkspaceError(f"Target is not a valid analysis workspace: {workspace}")
    links = existing_links(database_path)
    current = current_link(links)
    source = Path(str(current["source_path"]))
    verify_source_matches(current, source)

    sql = sql_file.read_text(encoding="utf-8").strip()
    if not sql:
        raise WorkspaceError("SQL file is empty.")

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        configure_query_connection(connection, source, str(current["source_format"]), args.install_excel_extension)
        statements = connection.extract_statements(sql)
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            statement_types = [statement.type.name for statement in statements]
            raise WorkspaceError(
                "Analysis SQL must contain exactly one SELECT statement. "
                f"Parsed statement types: {statement_types}"
            )
        try:
            cursor = connection.execute(sql)
        except duckdb.Error as exc:
            raise WorkspaceError(f"DuckDB query failed: {exc}") from exc
        column_names = [description[0] for description in cursor.description]
        fetched = cursor.fetchmany(args.max_rows + 1)
        truncated = len(fetched) > args.max_rows
        rows = fetched[: args.max_rows]
        active_link_id = str(current["link_id"])
    finally:
        connection.close()

    saved_sql = next_query_path(queries_dir, args.question)
    saved_sql.write_text(sql + "\n", encoding="utf-8", newline="\n")
    return {
        "workspace": str(workspace),
        "link_id": active_link_id,
        "question": args.question,
        "sql_file": str(saved_sql),
        "columns": column_names,
        "rows": [[json_value(value) for value in row] for row in rows],
        "returned_rows": len(rows),
        "truncated": truncated,
        "max_rows": args.max_rows,
    }


def inspect_command(args: argparse.Namespace) -> dict[str, Any]:
    source = require_absolute_path(args.source, "Source")
    if not source.is_file():
        raise WorkspaceError(f"Source does not exist or is not a regular file: {source}")
    suffix = source.suffix.casefold()
    if suffix not in SOURCE_FORMATS:
        raise WorkspaceError(
            "Source must be a .csv or .xlsx file. Convert .xls workbooks to .xlsx first: "
            f"{source}"
        )
    result: dict[str, Any] = {"source": str(source), "format": SOURCE_FORMATS[suffix]}
    if suffix == ".xlsx":
        result["sheets"] = xlsx_sheet_names(source)
    return result


def add_csv_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--delimiter")
    parser.add_argument("--encoding")
    parser.add_argument("--quote")
    parser.add_argument("--escape")
    parser.add_argument("--skip-rows", type=int)
    parser.add_argument("--date-format")
    parser.add_argument("--timestamp-format")
    parser.add_argument("--all-varchar", action="store_true")
    parser.add_argument("--null-padding", action="store_true")
    parser.add_argument("--force-header", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Create or re-link a workspace")
    setup_parser.add_argument("--workspace", required=True)
    setup_parser.add_argument("--source", required=True)
    setup_parser.add_argument("--sheet")
    setup_parser.add_argument("--refresh", action="store_true")
    setup_parser.add_argument("--install-excel-extension", action="store_true")
    add_csv_override_arguments(setup_parser)

    query_parser = subparsers.add_parser("query", help="Run and save one read-only SELECT")
    query_parser.add_argument("--workspace", required=True)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--sql-file", required=True)
    query_parser.add_argument("--max-rows", type=int, default=200)
    query_parser.add_argument("--install-excel-extension", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="Report source format and sheets")
    inspect_parser.add_argument("--source", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            result = setup_command(args)
        elif args.command == "query":
            result = query_command(args)
        else:
            result = inspect_command(args)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    except WorkspaceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
