#!/usr/bin/env python3
"""Validate a workbook-facts.yaml file against the shared schema version 2.

Checks the JSON Schema, ID uniqueness, slug-rule compliance, and completeness
reason codes. Exits 0 when valid and 2 with a machine-readable violation list
when not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import schema_check
import yaml_min
from facts_common import SCHEMA_VERSION, slugify


def resolve_schema_path(explicit):
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate
        return None
    script_dir = Path(__file__).resolve().parent
    sibling = script_dir / "workbook-facts.schema.json"
    if sibling.is_file():
        return sibling
    for parent in [script_dir, *script_dir.parents]:
        candidate = parent / "docs" / "shared" / "workbook-facts.schema.json"
        if candidate.is_file():
            return candidate
    return None


def collect_ids(facts):
    pairs = []
    workbook_id = facts.get("workbook", {}).get("id")
    if workbook_id is not None:
        pairs.append((workbook_id, "workbook.id"))
    for index, datasource in enumerate(facts.get("datasources", [])):
        if "id" in datasource:
            pairs.append((datasource["id"], f"datasources[{index}].id"))
    for index, parameter in enumerate(facts.get("parameters", [])):
        if "id" in parameter:
            pairs.append((parameter["id"], f"parameters[{index}].id"))
    for index, dashboard in enumerate(facts.get("dashboards", [])):
        if "id" in dashboard:
            pairs.append((dashboard["id"], f"dashboards[{index}].id"))
    for index, worksheet in enumerate(facts.get("worksheets", [])):
        if "id" in worksheet:
            pairs.append((worksheet["id"], f"worksheets[{index}].id"))
        for calc_index, calculation in enumerate(worksheet.get("calculations", [])):
            if "id" in calculation:
                pairs.append(
                    (calculation["id"], f"worksheets[{index}].calculations[{calc_index}].id")
                )
    return pairs


def check_ids(facts):
    violations = []
    pairs = collect_ids(facts)
    seen = {}
    for identifier, path in pairs:
        if identifier in seen:
            violations.append(
                {
                    "path": path,
                    "code": "ID_NOT_UNIQUE",
                    "message": f"ID '{identifier}' already used at {seen[identifier]}",
                }
            )
        else:
            seen[identifier] = path

    workbook_id = facts.get("workbook", {}).get("id", "")
    checks = []
    if "workbook" in facts:
        checks.append(
            (
                facts["workbook"].get("id"),
                slugify(facts["workbook"].get("name", "")),
                "workbook.id",
            )
        )
    for index, datasource in enumerate(facts.get("datasources", [])):
        checks.append(
            (
                datasource.get("id"),
                f"{workbook_id}__ds__{slugify(datasource.get('name', ''))}",
                f"datasources[{index}].id",
            )
        )
    for index, parameter in enumerate(facts.get("parameters", [])):
        checks.append(
            (
                parameter.get("id"),
                f"{workbook_id}__param__{slugify(parameter.get('caption', ''))}",
                f"parameters[{index}].id",
            )
        )
    for index, dashboard in enumerate(facts.get("dashboards", [])):
        checks.append(
            (
                dashboard.get("id"),
                f"{workbook_id}__dash__{slugify(dashboard.get('name', ''))}",
                f"dashboards[{index}].id",
            )
        )
    for index, worksheet in enumerate(facts.get("worksheets", [])):
        sheet_id = worksheet.get("id")
        checks.append(
            (
                sheet_id,
                f"{workbook_id}__sheet__{slugify(worksheet.get('name', ''))}",
                f"worksheets[{index}].id",
            )
        )
        for calc_index, calculation in enumerate(worksheet.get("calculations", [])):
            checks.append(
                (
                    calculation.get("id"),
                    f"{sheet_id}__calc__{slugify(calculation.get('caption', ''))}",
                    f"worksheets[{index}].calculations[{calc_index}].id",
                )
            )
    for identifier, expected, path in checks:
        if identifier is None:
            continue
        if identifier != expected and re.fullmatch(re.escape(expected) + r"_\d+", identifier) is None:
            violations.append(
                {
                    "path": path,
                    "code": "ID_SLUG_MISMATCH",
                    "message": f"ID '{identifier}' does not follow the slug rule (expected '{expected}' or '{expected}_N')",
                }
            )
    return violations


def check_completeness(facts):
    violations = []
    for index, record in enumerate(facts.get("completeness", [])):
        if record.get("status") == "partial" and not record.get("reason_code"):
            violations.append(
                {
                    "path": f"completeness[{index}]",
                    "code": "COMPLETENESS_REASON_MISSING",
                    "message": "a partial completeness record requires a reason_code",
                }
            )
    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a workbook-facts.yaml file against schema version 2.",
    )
    parser.add_argument("--facts", required=True, help="absolute path to the facts file")
    parser.add_argument("--schema", help="absolute path to workbook-facts.schema.json")
    args = parser.parse_args(argv)

    facts_path = Path(args.facts)
    violations = []
    facts = None
    if not facts_path.is_absolute():
        violations.append(
            {"path": "$", "code": "ARGUMENT_ERROR", "message": "--facts must be an absolute path"}
        )
    elif not facts_path.is_file():
        violations.append(
            {"path": "$", "code": "ARGUMENT_ERROR", "message": f"facts file not found: {facts_path}"}
        )
    else:
        try:
            facts = yaml_min.load(facts_path.read_text(encoding="utf-8-sig"))
        except yaml_min.YamlError as exc:
            violations.append(
                {"path": "$", "code": "PARSE_ERROR", "message": str(exc)}
            )

    schema_path = resolve_schema_path(args.schema)
    schema = None
    if schema_path is None:
        violations.append(
            {
                "path": "$",
                "code": "SCHEMA_NOT_FOUND",
                "message": "workbook-facts.schema.json not found; pass --schema",
            }
        )
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            violations.append(
                {"path": "$", "code": "SCHEMA_ERROR", "message": str(exc)}
            )

    if facts is not None and schema is not None:
        try:
            violations.extend(schema_check.validate(facts, schema))
        except schema_check.SchemaError as exc:
            violations.append(
                {"path": "$", "code": "SCHEMA_ERROR", "message": str(exc)}
            )
        if facts is not None and isinstance(facts, dict):
            violations.extend(check_ids(facts))
            violations.extend(check_completeness(facts))

    result = {
        "valid": not violations,
        "facts": str(facts_path),
        "schema": str(schema_path) if schema_path else None,
        "violations": violations,
    }
    print(json.dumps(result, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main())
