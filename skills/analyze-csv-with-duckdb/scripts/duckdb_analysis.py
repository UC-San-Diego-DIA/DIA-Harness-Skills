#!/usr/bin/env python3
"""Create, refresh, and query a one-CSV DuckDB analysis workspace."""

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
WORKSPACE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
QUERY_FILE_PATTERN = re.compile(r"^(\d+)-.*\.sql$", re.IGNORECASE)
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


def validate_setup_paths(root_raw: str, source_raw: str, workspace_raw: str) -> tuple[Path, Path, Path]:
    root = require_absolute_path(root_raw, "Root")
    source = require_absolute_path(source_raw, "Source")
    workspace = require_absolute_path(workspace_raw, "Workspace")

    if not root.is_dir():
        raise WorkspaceError(f"Root folder does not exist: {root}")
    if not source.is_file():
        raise WorkspaceError(f"Source CSV does not exist or is not a regular file: {source}")
    if source.suffix.casefold() != ".csv":
        raise WorkspaceError(f"Source must have a .csv extension: {source}")
    if not WORKSPACE_NAME_PATTERN.fullmatch(workspace.name):
        raise WorkspaceError(
            "Workspace folder name must use lowercase letters, digits, and single hyphens: "
            f"{workspace.name}"
        )

    analysis_root = (root / "analysis").resolve(strict=False)
    if workspace.parent != analysis_root:
        raise WorkspaceError(f"Workspace must be directly under {analysis_root}: {workspace}")
    if analysis_root.exists() and not is_within(analysis_root.resolve(), root):
        raise WorkspaceError(f"Analysis folder resolves outside the current folder: {analysis_root}")
    if is_within(source, workspace):
        raise WorkspaceError("Source CSV cannot be inside the analysis workspace.")

    return root, source, workspace


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


def normalized_headers(raw_headers: Sequence[str]) -> list[str]:
    if not raw_headers:
        raise WorkspaceError("CSV header row is empty.")

    blank_headers = [index + 1 for index, value in enumerate(raw_headers) if not value.strip()]
    if blank_headers:
        joined = ", ".join(str(index) for index in blank_headers)
        raise WorkspaceError(f"CSV has blank headers in column positions: {joined}")

    duplicates: dict[str, list[str]] = {}
    for value in raw_headers:
        duplicates.setdefault(value.strip().casefold(), []).append(value)
    duplicate_groups = [values for values in duplicates.values() if len(values) > 1]
    if duplicate_groups:
        rendered = "; ".join(", ".join(repr(value) for value in group) for group in duplicate_groups)
        raise WorkspaceError(f"CSV has duplicate headers: {rendered}")

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


def snapshot_id(imported_at: str, source_hash: str) -> str:
    compact_time = re.sub(r"[-:.+]", "", imported_at)
    return f"{compact_time}-{source_hash[:12]}"


def configure_no_extension_install(connection: Any) -> None:
    connection.execute("SET autoinstall_known_extensions = false")
    connection.execute("SET autoload_known_extensions = false")
    connection.execute("SET allow_community_extensions = false")


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


def csv_options(args: argparse.Namespace) -> dict[str, Any]:
    encoding = normalize_encoding(args.encoding)
    options: dict[str, Any] = {
        "header": True,
        "sample_size": -1,
        "ignore_errors": False,
        "normalize_names": False,
    }
    optional_values = {
        "delimiter": args.delimiter,
        "encoding": encoding,
        "quotechar": args.quote,
        "escapechar": args.escape,
        "skiprows": args.skip_rows,
        "date_format": args.date_format,
        "timestamp_format": args.timestamp_format,
    }
    options.update({key: value for key, value in optional_values.items() if value is not None})
    if args.all_varchar:
        options["all_varchar"] = True
    if args.null_padding:
        options["null_padding"] = True
    return options


def read_csv_table_function(
    source: Path, args: argparse.Namespace
) -> tuple[str, list[Any]]:
    encoding = normalize_encoding(args.encoding)
    clauses = [
        "header = true",
        "sample_size = -1",
        "ignore_errors = false",
        "normalize_names = false",
    ]
    parameters: list[Any] = [str(source)]
    option_map = (
        ("delim", args.delimiter),
        ("encoding", encoding),
        ("quote", args.quote),
        ("escape", args.escape),
        ("skip", args.skip_rows),
        ("dateformat", args.date_format),
        ("timestampformat", args.timestamp_format),
    )
    for sql_name, value in option_map:
        if value is not None:
            clauses.append(f"{sql_name} = ?")
            parameters.append(value)
    if args.all_varchar:
        clauses.append("all_varchar = true")
    if args.null_padding:
        clauses.append("null_padding = true")
    return f"read_csv(?, {', '.join(clauses)})", parameters


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


def existing_snapshots(database_path: Path) -> list[dict[str, Any]]:
    if not database_path.is_file():
        raise WorkspaceError(f"Workspace database is missing: {database_path}")
    connection = None
    try:
        connection = duckdb.connect(str(database_path), read_only=True)
        configure_read_only_query(connection)
        rows = connection.execute(
            """
            SELECT snapshot_id, imported_at, source_path, source_file, source_hash,
                   row_count, read_options, python_executable, is_current
            FROM _analysis_snapshots
            ORDER BY imported_at
            """
        ).fetchall()
    except Exception as exc:
        raise WorkspaceError(f"Workspace metadata is invalid: {database_path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    keys = (
        "snapshot_id",
        "imported_at",
        "source_path",
        "source_file",
        "source_hash",
        "row_count",
        "read_options",
        "python_executable",
        "is_current",
    )
    return [dict(zip(keys, row)) for row in rows]


def current_snapshot(snapshots: Sequence[dict[str, Any]]) -> dict[str, Any]:
    current = [snapshot for snapshot in snapshots if snapshot["is_current"]]
    if len(current) != 1:
        raise WorkspaceError("Workspace must contain exactly one current snapshot.")
    return current[0]


def build_database(
    database_path: Path,
    snapshot_csv: Path,
    source: Path,
    args: argparse.Namespace,
    prior_snapshots: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    imported_at = utc_now()
    source_hash = file_sha256(snapshot_csv)
    new_snapshot_id = snapshot_id(imported_at, source_hash)
    options = csv_options(args)

    connection = duckdb.connect(str(database_path))
    try:
        configure_no_extension_install(connection)
        delimiter, quote, escape, skip_rows, has_header = sniff_dialect(
            connection, snapshot_csv, args
        )
        if not has_header and not args.force_header:
            raise WorkspaceError(
                "DuckDB did not detect a header row. Retry with --force-header only if the first data row is the header."
            )
        raw_headers = read_raw_headers(
            snapshot_csv, delimiter, quote, escape, skip_rows, args.encoding
        )
        sql_headers = normalized_headers(raw_headers)

        table_function, table_parameters = read_csv_table_function(snapshot_csv, args)
        header_cursor = connection.execute(
            f"SELECT * FROM {table_function} LIMIT 0", table_parameters
        )
        duckdb_headers = [str(column[0]) for column in header_cursor.description]
        if len(duckdb_headers) != len(raw_headers):
            raise WorkspaceError(
                "DuckDB parsed a different number of columns than the header row: "
                f"header={len(raw_headers)}, parsed={len(duckdb_headers)}"
            )

        projection = ", ".join(
            f"{quote_identifier(actual)} AS {quote_identifier(normalized)}"
            for actual, normalized in zip(duckdb_headers, sql_headers)
        )
        connection.execute(
            f"CREATE TABLE {quote_identifier(TABLE_NAME)} AS "
            f"SELECT {projection} FROM {table_function}",
            table_parameters,
        )

        row_count = int(connection.execute(f"SELECT count(*) FROM {TABLE_NAME}").fetchone()[0])
        type_rows = connection.execute(f"PRAGMA table_info('{TABLE_NAME}')").fetchall()
        type_by_name = {str(row[1]): str(row[2]) for row in type_rows}
        null_projection = ", ".join(
            f"count(*) FILTER (WHERE {quote_identifier(name)} IS NULL)"
            for name in sql_headers
        )
        null_counts = list(
            connection.execute(f"SELECT {null_projection} FROM {TABLE_NAME}").fetchone()
        )

        connection.execute(
            """
            CREATE TABLE _analysis_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                imported_at VARCHAR NOT NULL,
                source_path VARCHAR NOT NULL,
                source_file VARCHAR NOT NULL,
                source_hash VARCHAR NOT NULL,
                row_count BIGINT NOT NULL,
                read_options VARCHAR NOT NULL,
                python_executable VARCHAR NOT NULL,
                is_current BOOLEAN NOT NULL
            )
            """
        )
        for snapshot in prior_snapshots:
            connection.execute(
                """
                INSERT INTO _analysis_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, false)
                """,
                [
                    snapshot["snapshot_id"],
                    snapshot["imported_at"],
                    snapshot["source_path"],
                    snapshot["source_file"],
                    snapshot["source_hash"],
                    snapshot["row_count"],
                    snapshot["read_options"],
                    snapshot["python_executable"],
                ],
            )
        serialized_options = json.dumps(options, sort_keys=True)
        connection.execute(
            """
            INSERT INTO _analysis_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, true)
            """,
            [
                new_snapshot_id,
                imported_at,
                str(source),
                source.name,
                source_hash,
                row_count,
                serialized_options,
                sys.executable,
            ],
        )

        connection.execute(
            """
            CREATE TABLE _analysis_columns (
                snapshot_id VARCHAR NOT NULL,
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
                    new_snapshot_id,
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

    snapshots = [dict(snapshot, is_current=False) for snapshot in prior_snapshots]
    snapshots.append(
        {
            "snapshot_id": new_snapshot_id,
            "imported_at": imported_at,
            "source_path": str(source),
            "source_file": source.name,
            "source_hash": source_hash,
            "row_count": row_count,
            "read_options": json.dumps(options, sort_keys=True),
            "python_executable": sys.executable,
            "is_current": True,
        }
    )
    return {
        "snapshot_id": new_snapshot_id,
        "imported_at": imported_at,
        "source_path": str(source),
        "source_file": source.name,
        "snapshot_file": f"data/{source.name}",
        "source_hash": source_hash,
        "row_count": row_count,
        "read_options": options,
        "python_executable": sys.executable,
        "columns": columns,
        "snapshots": snapshots,
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
        "This workspace contains a local snapshot of one source CSV for ad hoc analysis.",
        "The original CSV is never watched. Refresh happens only when requested and confirmed.",
        "",
        "## Current snapshot",
        "",
        f"- Snapshot ID: `{summary['snapshot_id']}`",
        f"- Imported at: `{summary['imported_at']}`",
        f"- Original source: `{summary['source_path']}`",
        f"- Snapshot file: `{summary['snapshot_file']}`",
        f"- SHA-256: `{summary['source_hash']}`",
        f"- DuckDB table: `{TABLE_NAME}`",
        f"- Python executable: `{summary['python_executable']}`",
        f"- Rows: {summary['row_count']}",
        f"- Read options: `{json.dumps(summary['read_options'], sort_keys=True)}`",
        "",
        "Later changes to the original CSV do not affect this snapshot. Run a confirmed workspace refresh to replace it.",
        "",
        "## Columns",
        "",
        "| # | Original header | SQL name | DuckDB type | Nulls |",
        "| ---: | --- | --- | --- | ---: |",
    ]
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

    lines.extend(["", "## Snapshot history", ""])
    for snapshot in summary["snapshots"]:
        status = "current" if snapshot["is_current"] else "superseded"
        lines.append(
            f"- `{snapshot['snapshot_id']}`: {snapshot['imported_at']}, "
            f"{snapshot['row_count']} rows, {status}"
        )

    lines.extend(["", questions_section(existing_analysis).rstrip(), ""])
    return "\n".join(lines)


def write_gitignore(path: Path) -> None:
    path.write_text("*\n!.gitignore\n", encoding="utf-8", newline="\n")


def setup_stage(
    stage: Path,
    source: Path,
    args: argparse.Namespace,
    prior_snapshots: Sequence[dict[str, Any]],
    existing_analysis: str | None,
) -> dict[str, Any]:
    data_dir = stage / "data"
    queries_dir = stage / "queries"
    data_dir.mkdir(parents=True)
    queries_dir.mkdir()
    snapshot_csv = data_dir / source.name
    shutil.copy2(source, snapshot_csv)

    summary = build_database(
        stage / DATABASE_NAME, snapshot_csv, source, args, prior_snapshots
    )
    (stage / ANALYSIS_NAME).write_text(
        render_analysis_markdown(summary, existing_analysis), encoding="utf-8", newline="\n"
    )
    write_gitignore(stage / ".gitignore")
    return summary


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
    names = ("data", DATABASE_NAME, ANALYSIS_NAME, ".gitignore")
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
                f"Refresh failed and rollback was incomplete. Recovery files remain at {backup}. "
                f"Rollback errors: {details}"
            ) from refresh_error
        raise
    finally:
        if completed or not any(backup.iterdir()):
            remove_checked_tree(backup, workspace.parent)


def validate_existing_workspace(workspace: Path, source: Path) -> tuple[list[dict[str, Any]], str]:
    required = (
        workspace / DATABASE_NAME,
        workspace / ANALYSIS_NAME,
        workspace / ".gitignore",
        workspace / "data",
        workspace / "queries",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise WorkspaceError("Existing target is not a valid workspace. Missing: " + ", ".join(missing))
    snapshots = existing_snapshots(workspace / DATABASE_NAME)
    current = current_snapshot(snapshots)
    current_source = os.path.normcase(os.path.normpath(str(current["source_path"])))
    requested_source = os.path.normcase(os.path.normpath(str(source)))
    if current_source != requested_source:
        raise WorkspaceError(
            "Existing workspace belongs to a different source CSV: "
            f"{current['source_path']}"
        )
    existing_analysis = (workspace / ANALYSIS_NAME).read_text(encoding="utf-8")
    return snapshots, existing_analysis


def setup_command(args: argparse.Namespace) -> dict[str, Any]:
    _, source, workspace = validate_setup_paths(args.root, args.source, args.workspace)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    prior_snapshots: list[dict[str, Any]] = []
    existing_analysis: str | None = None
    if args.refresh:
        if not workspace.is_dir():
            raise WorkspaceError(f"Refresh requires an existing workspace: {workspace}")
        prior_snapshots, existing_analysis = validate_existing_workspace(workspace, source)
    elif workspace.exists():
        raise WorkspaceError(f"Workspace already exists. Use a different name or confirm refresh: {workspace}")

    stage = Path(
        tempfile.mkdtemp(prefix=f".{workspace.name}.staging-", dir=str(workspace.parent))
    )
    try:
        try:
            summary = setup_stage(stage, source, args, prior_snapshots, existing_analysis)
        except duckdb.Error as exc:
            raise WorkspaceError(f"DuckDB could not import the CSV: {exc}") from exc
        if args.refresh:
            replace_refreshed_files(stage, workspace)
        else:
            install_created_workspace(stage, workspace)
        summary.update(
            {
                "action": "refreshed" if args.refresh else "created",
                "workspace": str(workspace),
                "database": str(workspace / DATABASE_NAME),
                "table": TABLE_NAME,
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


def configure_read_only_query(connection: Any) -> None:
    configure_no_extension_install(connection)
    connection.execute("SET enable_external_access = false")
    connection.execute("SET lock_configuration = true")


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
        workspace / ".gitignore",
        workspace / "data",
        queries_dir,
    )
    if any(not path.exists() for path in required):
        raise WorkspaceError(f"Target is not a valid analysis workspace: {workspace}")
    sql = sql_file.read_text(encoding="utf-8").strip()
    if not sql:
        raise WorkspaceError("SQL file is empty.")

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        configure_read_only_query(connection)
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
        snapshot_row = connection.execute(
            "SELECT snapshot_id FROM _analysis_snapshots WHERE is_current = true"
        ).fetchone()
        if snapshot_row is None:
            raise WorkspaceError("Workspace has no current snapshot metadata.")
        active_snapshot_id = str(snapshot_row[0])
    finally:
        connection.close()

    saved_sql = next_query_path(queries_dir, args.question)
    saved_sql.write_text(sql + "\n", encoding="utf-8", newline="\n")
    return {
        "workspace": str(workspace),
        "snapshot_id": active_snapshot_id,
        "question": args.question,
        "sql_file": str(saved_sql),
        "columns": column_names,
        "rows": [[json_value(value) for value in row] for row in rows],
        "returned_rows": len(rows),
        "truncated": truncated,
        "max_rows": args.max_rows,
    }


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

    setup_parser = subparsers.add_parser("setup", help="Create or refresh a workspace")
    setup_parser.add_argument("--root", required=True)
    setup_parser.add_argument("--source", required=True)
    setup_parser.add_argument("--workspace", required=True)
    setup_parser.add_argument("--refresh", action="store_true")
    add_csv_override_arguments(setup_parser)

    query_parser = subparsers.add_parser("query", help="Run and save one read-only SELECT")
    query_parser.add_argument("--workspace", required=True)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--sql-file", required=True)
    query_parser.add_argument("--max-rows", type=int, default=200)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            result = setup_command(args)
        else:
            result = query_command(args)
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
