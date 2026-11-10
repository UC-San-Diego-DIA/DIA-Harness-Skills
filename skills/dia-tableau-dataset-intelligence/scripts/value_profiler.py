"""Opt-in, local-only observations of the single Hyper extract in a TWBX."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import pack_runtime as runtime

PROFILE_PATH = "evidence/value-profile.yaml"


@contextmanager
def local_temporary_environment(directory):
    # Hyper inherits these settings. Its spill files must stay with the pack.
    previous = {key: os.environ.get(key) for key in ("TEMP", "TMP", "TMPDIR")}
    try:
        for key in previous:
            os.environ[key] = str(directory)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def profile(source, root, workbook_sha256):
    """Write new evidence only after a complete successful read-only scan."""
    source, root = Path(source), Path(root)
    output = root / PROFILE_PATH
    if output.exists():
        raise ValueError("Value-profile evidence is immutable; use a new pack directory.")
    if source.suffix.lower() != ".twbx":
        raise ValueError("--profile-values requires a TWBX containing exactly one .hyper extract.")
    if runtime.digest(source) != workbook_sha256:
        raise ValueError("Workbook changed after metadata extraction; use a fresh pack.")
    try:
        import tableauhyperapi as hyper
    except ImportError as exc:
        raise RuntimeError("--profile-values requires tableauhyperapi in this Python environment. "
                           "Install it separately, then initialize a new pack.") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source) as archive:
            entries = [item for item in archive.infolist()
                       if not item.is_dir() and item.filename.lower().endswith(".hyper")]
            if len(entries) != 1:
                raise ValueError("--profile-values requires exactly one .hyper extract in the TWBX; "
                                 f"found {len(entries)}. No extract was selected automatically.")
            with tempfile.TemporaryDirectory(prefix="value-profile-", dir=output.parent) as temporary:
                directory = Path(temporary)
                extract = directory / "extract.hyper"
                # Never use an archive entry as a filesystem path.
                with archive.open(entries[0]) as incoming, extract.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                extract_hash = runtime.digest(extract)
                data = {"schema_version": 1, "document_type": "tableau_value_profile",
                        "provenance": {"workbook_sha256": workbook_sha256,
                                       "extract_entry": entries[0].filename,
                                       "extract_sha256": extract_hash}, "tables": []}
                with local_temporary_environment(directory), hyper.HyperProcess(
                    hyper.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                    parameters={"log_config": "", "log_dir": str(directory), "use_tcp_port": "off",
                                "hyper_temp_directory_override": str(directory)},
                ) as process:
                    with hyper.Connection(process.endpoint, database=extract,
                                          create_mode=hyper.CreateMode.NONE,
                                          parameters={"access_mode": "readonly"}) as connection:
                        connection.execute_command("BEGIN READ ONLY")
                        for schema in sorted(connection.catalog.get_schema_names(), key=str):
                            for table in sorted(connection.catalog.get_table_names(schema), key=str):
                                definition = connection.catalog.get_table_definition(table)
                                row_count = connection.execute_scalar_query(f"SELECT COUNT(*) FROM {table}")
                                record = {"schema": schema.name.unescaped, "name": table.name.unescaped,
                                          "row_count": row_count, "fields": []}
                                for column in definition.columns:
                                    name = str(column.name)  # Hyper quotes identifiers, including embedded quotes.
                                    nonnull, cardinality = connection.execute_list_query(
                                        f"SELECT COUNT({name}), COUNT(DISTINCT {name}) FROM {table}")[0]
                                    values = []
                                    if cardinality <= 100:
                                        values = [{"value": value, "count": count} for value, count in
                                                  connection.execute_list_query(
                                                      f"SELECT CAST({name} AS TEXT) AS value, COUNT(*) AS n "
                                                      f"FROM {table} WHERE {name} IS NOT NULL GROUP BY {name} "
                                                      "ORDER BY n DESC, value ASC LIMIT 50")]
                                    record["fields"].append({"name": column.name.unescaped,
                                                             "datatype": str(column.type),
                                                             "null_count": row_count - nonnull,
                                                             "distinct_count": cardinality,
                                                             "values": values,
                                                             "values_truncated": cardinality > len(values)})
                                data["tables"].append(record)
                        connection.execute_command("ROLLBACK")
                if runtime.digest(extract) != extract_hash:
                    raise ValueError("Hyper extract changed during read-only profiling.")
        if runtime.digest(source) != workbook_sha256:
            raise ValueError("Workbook changed during value profiling; use a fresh pack.")
    except (hyper.HyperException, zipfile.BadZipFile) as exc:
        # Native errors can contain observed literals; do not print them into chat/logs.
        raise RuntimeError("Local Hyper profiling failed. No value-profile evidence was written; "
                           "check the extract and local Hyper installation, then use a fresh pack.") from exc
    issues = validate(data, workbook_sha256)
    if issues:
        raise ValueError("Invalid generated value profile: " + str(issues))
    runtime.write_yaml(output, data)
    return {"path": PROFILE_PATH, "sha256": runtime.digest(output), "extract_sha256": extract_hash}


def validate(data, workbook_sha256):
    issues = runtime.schema_issues(data, "value-profile.schema.json")
    if issues:
        return issues

    def fail(message):
        issues.append({"path": PROFILE_PATH, "message": message})

    if data["provenance"]["workbook_sha256"] != workbook_sha256:
        fail("Value profile belongs to another workbook snapshot.")
    tables = set()
    for table in data["tables"]:
        identity = (table["schema"], table["name"])
        if identity in tables:
            fail("Duplicate physical table in value profile.")
        tables.add(identity)
        fields = set()
        if table["row_count"] < 0:
            fail("Row counts must be nonnegative.")
        for field in table["fields"]:
            if field["name"] in fields:
                fail("Duplicate physical column in value profile.")
            fields.add(field["name"])
            nulls, cardinality = field["null_count"], field["distinct_count"]
            nonnull = table["row_count"] - nulls
            if not 0 <= nulls <= table["row_count"] or not 0 <= cardinality <= nonnull:
                fail("Null counts and non-null cardinalities must fit the table row count.")
            expected = min(cardinality, 50) if cardinality <= 100 else 0
            values = field["values"]
            if len(values) != expected or len({item["value"] for item in values}) != len(values):
                fail("Distinct summaries must contain unique values within the 50/100 limits.")
            if field["values_truncated"] != (cardinality > len(values)):
                fail("Value-summary truncation flag differs from cardinality.")
            counts = [item["count"] for item in values]
            if any(count <= 0 for count in counts) or sum(counts) > nonnull:
                fail("Observed value counts must be positive and fit the non-null row count.")
            if cardinality <= 50 and sum(counts) != nonnull:
                fail("Complete value summaries must account for all non-null rows.")
    return issues
