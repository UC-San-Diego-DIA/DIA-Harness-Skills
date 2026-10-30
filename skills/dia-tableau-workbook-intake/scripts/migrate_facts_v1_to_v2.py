#!/usr/bin/env python3
"""Migrate a schema-version-1 workbook-facts.yaml file to schema version 2.

The input file is never modified. IDs are derived from names with the contract
slug rule, warnings are converted to anomaly records, and provenance marks the
input_sha256 as null with reason migrated_from_v1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml_min
from facts_common import SCHEMA_VERSION, IdAssigner, build_provenance, slugify


EMPTY_ZONE_RE = re.compile(r"^dashboard '(.+)' has (\d+) empty zones$")
UNRECOGNIZED_ZONE_RE = re.compile(
    r"^dashboard '(.+)' has (\d+) unrecognized zones(?:; zone types: (.*))?$"
)
MULTIPLE_TWB_RE = re.compile(r"^package contains (\d+) \.twb entries; extracted (.+)$")
STORY_WARNING = "workbook contains stories; story sheets are not inventoried"


def print_error(message):
    print(f"Error: {message}", file=sys.stderr)


def derive_ids(facts, assigner):
    workbook_id = assigner.assign(
        slugify(facts["workbook"]["name"]), "workbook"
    )
    facts["workbook"]["id"] = workbook_id
    for index, datasource in enumerate(facts["datasources"]):
        datasource["id"] = assigner.assign(
            f"{workbook_id}__ds__{slugify(datasource['name'])}",
            f"datasources[{index}]",
        )
    for index, parameter in enumerate(facts["parameters"]):
        parameter["id"] = assigner.assign(
            f"{workbook_id}__param__{slugify(parameter['caption'])}",
            f"parameters[{index}]",
        )
    for index, dashboard in enumerate(facts["dashboards"]):
        dashboard["id"] = assigner.assign(
            f"{workbook_id}__dash__{slugify(dashboard['name'])}",
            f"dashboards[{index}]",
        )
    sheet_ids = {}
    for index, worksheet in enumerate(facts["worksheets"]):
        sheet_id = assigner.assign(
            f"{workbook_id}__sheet__{slugify(worksheet['name'])}",
            f"worksheets[{index}]",
        )
        worksheet["id"] = sheet_id
        sheet_ids[worksheet["name"]] = sheet_id
        for calc_index, calculation in enumerate(worksheet["calculations"]):
            calculation["id"] = assigner.assign(
                f"{sheet_id}__calc__{slugify(calculation['caption'])}",
                f"worksheets[{index}].calculations[{calc_index}]",
            )
    return workbook_id, sheet_ids


def warning_anomalies(facts, sheet_ids):
    """Convert v1 free-text warnings into typed anomaly records."""
    records = []
    dashboard_ids = {
        dashboard["name"]: dashboard["id"] for dashboard in facts["dashboards"]
    }
    for warning in facts["extraction"]["warnings"]:
        empty_match = EMPTY_ZONE_RE.match(warning)
        unrecognized_match = UNRECOGNIZED_ZONE_RE.match(warning)
        multiple_match = MULTIPLE_TWB_RE.match(warning)
        if empty_match:
            records.append(
                {
                    "code": "EMPTY_ZONE",
                    "rule_version": "2.0.0",
                    "affected_ids": [dashboard_ids.get(empty_match.group(1), "")],
                    "evidence": ["extraction.warnings"],
                    "count": int(empty_match.group(2)),
                    "status": "observed",
                }
            )
        elif unrecognized_match:
            records.append(
                {
                    "code": "UNRECOGNIZED_ZONE",
                    "rule_version": "2.0.0",
                    "affected_ids": [dashboard_ids.get(unrecognized_match.group(1), "")],
                    "evidence": ["extraction.warnings"],
                    "count": int(unrecognized_match.group(2)),
                    "status": "observed",
                }
            )
        elif multiple_match:
            records.append(
                {
                    "code": "MULTIPLE_TWB_ENTRIES",
                    "rule_version": "2.0.0",
                    "affected_ids": [],
                    "evidence": ["extraction.warnings"],
                    "count": 1,
                    "status": "observed",
                }
            )
        elif warning == STORY_WARNING:
            records.append(
                {
                    "code": "STORY_NOT_INVENTORIED",
                    "rule_version": "2.0.0",
                    "affected_ids": [],
                    "evidence": ["extraction.warnings"],
                    "count": 1,
                    "status": "out_of_scope",
                }
            )
        else:
            records.append(
                {
                    "code": "UNCLASSIFIED_WARNING",
                    "rule_version": "2.0.0",
                    "affected_ids": [],
                    "evidence": ["extraction.warnings"],
                    "count": 1,
                    "status": "observed",
                }
            )
    return records


def build_anomalies(facts, sheet_ids, assigner):
    records = []
    for group in facts["derived"]["duplicate_name_groups"]:
        records.append(
            {
                "code": "DUPLICATE_SHEET_NAME",
                "rule_version": "2.0.0",
                "affected_ids": [sheet_ids[name] for name in group["sheets"]],
                "evidence": ["derived.duplicate_name_groups"],
                "count": len(group["sheets"]),
                "status": "observed",
            }
        )
    orphan_ids = [sheet_ids[name] for name in facts["derived"]["orphan_sheets"]]
    if orphan_ids:
        records.append(
            {
                "code": "ORPHAN_SHEET",
                "rule_version": "2.0.0",
                "affected_ids": orphan_ids,
                "evidence": ["derived.orphan_sheets"],
                "count": len(orphan_ids),
                "status": "observed",
            }
        )
    for collision in assigner.collisions:
        records.append(
            {
                "code": "ID_COLLISION",
                "rule_version": "2.0.0",
                "affected_ids": [collision["final"]],
                "evidence": [collision["evidence"]],
                "count": 1,
                "status": "observed",
            }
        )
    records.extend(warning_anomalies(facts, sheet_ids))
    for code in ("EMPTY_ZONE", "UNRECOGNIZED_ZONE", "DUPLICATE_SHEET_NAME", "ORPHAN_SHEET"):
        if not any(record["code"] == code for record in records):
            records.append(
                {
                    "code": code,
                    "rule_version": "2.0.0",
                    "affected_ids": [],
                    "evidence": [],
                    "count": 0,
                    "status": "not_found",
                }
            )
    return records


def build_completeness(facts):
    records = []
    for section in ("dashboards", "worksheets", "parameters", "datasources"):
        found = len(facts[section])
        records.append(
            {
                "section": section,
                "expected": found,
                "found": found,
                "skipped": 0,
                "out_of_scope": 0,
                "status": "complete",
            }
        )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Migrate a schema-version-1 workbook-facts.yaml file to schema "
            "version 2 without modifying the input."
        ),
    )
    parser.add_argument("--input", required=True, help="absolute path to the v1 facts file")
    parser.add_argument("--output", required=True, help="absolute path for the v2 facts file")
    args = parser.parse_args(argv)

    source = Path(args.input)
    output = Path(args.output)
    if not source.is_absolute() or not output.is_absolute():
        print_error("--input and --output must be absolute paths.")
        return 2
    if not source.is_file():
        print_error(f"input is not a regular file: {source}")
        return 1
    if output.exists():
        print_error(f"output already exists: {output}")
        return 1

    try:
        raw_text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print_error(f"could not read the input file: {exc}")
        return 1
    try:
        facts = yaml_min.load(raw_text)
    except yaml_min.YamlError as exc:
        print_error(f"input is not readable YAML: {exc}")
        return 1
    if not isinstance(facts, dict) or "schema_version" not in facts:
        print_error("input is not a workbook-facts file.")
        return 1
    if facts["schema_version"] != 1:
        print_error(
            f"input has schema_version {facts['schema_version']!r}; this tool migrates version 1 only."
        )
        return 2

    assigner = IdAssigner()
    workbook_id, sheet_ids = derive_ids(facts, assigner)
    extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    container = facts["extraction"].get("container", "")
    entry = facts["extraction"].get("entry", "")
    facts["provenance"] = build_provenance(
        None,
        extracted_at,
        container,
        entry,
        str(source),
        reason="migrated_from_v1",
    )
    facts["anomalies"] = build_anomalies(facts, sheet_ids, assigner)
    facts["completeness"] = build_completeness(facts)
    facts["interpretation_inputs"] = {"dashboard_purposes": [], "sheet_roles": []}
    facts["schema_version"] = SCHEMA_VERSION
    facts = {
        key: facts[key]
        for key in (
            "schema_version",
            "provenance",
            "workbook",
            "extraction",
            "datasources",
            "parameters",
            "dashboards",
            "worksheets",
            "derived",
            "completeness",
            "anomalies",
            "interpretation_inputs",
        )
    }

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_facts(facts), encoding="utf-8")
    except OSError as exc:
        print_error(f"could not write the output file: {exc}")
        return 1

    summary = {
        "input": str(source),
        "output": str(output),
        "schema_version": SCHEMA_VERSION,
        "dashboards": len(facts["dashboards"]),
        "worksheets": len(facts["worksheets"]),
        "orphan_sheets": len(facts["derived"]["orphan_sheets"]),
        "parameters": len(facts["parameters"]),
        "anomalies_by_code": {
            code: sum(1 for record in facts["anomalies"] if record["code"] == code)
            for code in sorted({record["code"] for record in facts["anomalies"]})
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


def render_facts(facts):
    import extract_workbook_facts as extractor

    workbook_name = facts["workbook"]["name"]
    header = [
        f"# workbook-facts for {workbook_name}",
        "# Migrated to schema version 2 by dia-tableau-workbook-intake migrate_facts_v1_to_v2.py.",
        "# Do not hand-edit.",
    ]
    return "\n".join(header + extractor.render_dict(facts, 0)) + "\n"


if __name__ == "__main__":
    sys.exit(main())
