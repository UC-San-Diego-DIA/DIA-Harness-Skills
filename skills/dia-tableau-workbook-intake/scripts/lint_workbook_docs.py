#!/usr/bin/env python3
"""Lint generated workbook documents against their facts file.

Checks: facts-schema validity, referenced IDs exist in the facts, no orphan
sheet names in the reference or specs documents, no stale template placeholders
or unconfirmed-confirmation markers, and doc-ownership violations. Exits 0 when
clean and 2 with a machine-readable violation list when not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import schema_check
import yaml_min
from facts_common import ROLE_VOCABULARY


PLACEHOLDER_RE = re.compile(r"<[a-z][^<>\n]{2,79}>")
ID_TOKEN_RE = re.compile(r"[A-Za-z0-9_&.\[\]:%-]+__[A-Za-z0-9_&.\[\]:%-]+")
UNCONFIRMED_MARKER = "Needs analyst confirmation."
ROLE_TERMS = [
    term for term in ROLE_VOCABULARY
    if term not in ("table", "map", "other")
] + [term.replace("_", " ") for term in ROLE_VOCABULARY if term not in ("table", "map", "other")]
ROLE_TERMS = sorted(set(ROLE_TERMS))


def resolve_schema_path(explicit):
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    script_dir = Path(__file__).resolve().parent
    sibling = script_dir / "workbook-facts.schema.json"
    if sibling.is_file():
        return sibling
    for parent in [script_dir, *script_dir.parents]:
        candidate = parent / "docs" / "shared" / "workbook-facts.schema.json"
        if candidate.is_file():
            return candidate
    return None


def load_confirmations(path):
    """Load confirmed purposes and roles from the dashboard-docs sidecar."""
    purposes = []
    roles = []
    if not path.is_file():
        return purposes, roles
    data = yaml_min.load(path.read_text(encoding="utf-8-sig"))
    interpretation = data.get("interpretation_inputs", data)
    purposes = list(interpretation.get("dashboard_purposes", []))
    roles = list(interpretation.get("sheet_roles", []))
    return purposes, roles


def orphan_name_occurs(name, text, all_names):
    """True when the orphan name appears in text as itself, not as the prefix
    of a longer known sheet name."""
    start = 0
    while True:
        position = text.find(name, start)
        if position < 0:
            return False
        shadowed = False
        for other in all_names:
            if other != name and other.startswith(name):
                if text[position:position + len(other)] == other:
                    shadowed = True
                    break
        if not shadowed:
            return True
        start = position + 1


def lint(facts, documents, confirmations):
    violations = []
    purposes, roles = confirmations
    confirmed_dashboard_ids = {record.get("dashboard_id") for record in purposes}
    confirmed_sheet_ids = {record.get("sheet_id") for record in roles}
    dashboards = facts.get("dashboards", [])
    used_sheets = facts.get("derived", {}).get("sheets_on_dashboards", [])
    all_purposes_confirmed = bool(dashboards) and all(
        dashboard.get("id") in confirmed_dashboard_ids for dashboard in dashboards
    )
    sheet_ids = {
        worksheet["id"] for worksheet in facts.get("worksheets", [])
    }
    used_sheet_ids = {
        worksheet["id"]
        for worksheet in facts.get("worksheets", [])
        if worksheet.get("name") in used_sheets
    }
    all_roles_confirmed = bool(used_sheet_ids) and all(
        sheet_id in confirmed_sheet_ids for sheet_id in used_sheet_ids
    )

    known_ids = set()
    if "workbook" in facts and "id" in facts["workbook"]:
        known_ids.add(facts["workbook"]["id"])
    for entry in facts.get("datasources", []):
        known_ids.add(entry.get("id", ""))
    for entry in facts.get("parameters", []):
        known_ids.add(entry.get("id", ""))
    for entry in dashboards:
        known_ids.add(entry.get("id", ""))
    for entry in facts.get("worksheets", []):
        known_ids.add(entry.get("id", ""))
        for calculation in entry.get("calculations", []):
            known_ids.add(calculation.get("id", ""))

    orphan_names = facts.get("derived", {}).get("orphan_sheets", [])
    all_sheet_names = [worksheet.get("name", "") for worksheet in facts.get("worksheets", [])]

    for document in documents:
        if document["text"] is None:
            continue
        text = document["text"]
        name = document["name"]

        for match in ID_TOKEN_RE.finditer(text):
            token = match.group(0)
            if token not in known_ids:
                violations.append(
                    {
                        "path": name,
                        "code": "UNKNOWN_ID",
                        "message": f"referenced ID '{token}' does not exist in the facts file",
                    }
                )

        for match in PLACEHOLDER_RE.finditer(text):
            violations.append(
                {
                    "path": name,
                    "code": "TEMPLATE_PLACEHOLDER",
                    "message": f"template placeholder survives: {match.group(0)!r}",
                }
            )

        if orphan_names and name in ("dashboard-reference.md", "sheet-specs.md"):
            for orphan_name in orphan_names:
                if orphan_name and orphan_name_occurs(orphan_name, text, all_sheet_names):
                    violations.append(
                        {
                            "path": name,
                            "code": "ORPHAN_SHEET_IN_DOCUMENT",
                            "message": f"orphan sheet '{orphan_name}' appears in a document that must exclude it",
                        }
                    )

        if UNCONFIRMED_MARKER in text:
            if name == "dashboard-reference.md" and all_purposes_confirmed:
                violations.append(
                    {
                        "path": name,
                        "code": "UNCONFIRMED_MARKER_STALE",
                        "message": "all dashboards have logged purpose confirmations, but the marker survives",
                    }
                )
            if name == "sheet-specs.md" and all_roles_confirmed:
                violations.append(
                    {
                        "path": name,
                        "code": "UNCONFIRMED_MARKER_STALE",
                        "message": "all dashboard-used sheets have logged role confirmations, but the marker survives",
                    }
                )

        if name == "workbook-audit.md":
            lowered = text.lower()
            for term in ROLE_TERMS:
                if term in lowered:
                    violations.append(
                        {
                            "path": name,
                            "code": "OWNERSHIP_VIOLATION",
                            "message": f"audit contains sheet-role content ('{term}'); roles belong to sheet-specs.md",
                        }
                    )
            if re.search(r"(?i)\bpurpose\b", text):
                violations.append(
                    {
                        "path": name,
                        "code": "OWNERSHIP_VIOLATION",
                        "message": "audit contains purpose content; purposes belong to dashboard-reference.md",
                    }
                )

        if name == "dashboard-reference.md":
            for phrase in ("Rows shelf", "Columns shelf", "```tableau", "Formula:"):
                if phrase in text:
                    violations.append(
                        {
                            "path": name,
                            "code": "OWNERSHIP_VIOLATION",
                            "message": f"reference contains shelf-level mechanics ('{phrase}'); mechanics belong to sheet-specs.md",
                        }
                    )

        if name == "sheet-specs.md":
            for pattern in (r"(?i)\borphan\b", r"(?i)total worksheets", r"(?i)dashboard count", r"(?i)duplicate sheet name"):
                if re.search(pattern, text):
                    violations.append(
                        {
                            "path": name,
                            "code": "OWNERSHIP_VIOLATION",
                            "message": f"specs contain audit-owned inventory content matching {pattern!r}",
                        }
                    )

    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint generated workbook documents against their facts file.",
    )
    parser.add_argument("--facts", required=True, help="absolute path to the v2 facts file")
    parser.add_argument("--schema", help="absolute path to workbook-facts.schema.json")
    parser.add_argument("--audit", help="absolute path to workbook-audit.md")
    parser.add_argument("--reference", help="absolute path to dashboard-reference.md")
    parser.add_argument("--specs", help="absolute path to sheet-specs.md")
    parser.add_argument("--confirmations", help="absolute path to confirmations.yaml")
    args = parser.parse_args(argv)

    violations = []
    facts_path = Path(args.facts)
    if not facts_path.is_absolute():
        violations.append({"path": "$", "code": "ARGUMENT_ERROR", "message": "--facts must be an absolute path"})
        facts_path = None
    facts = None
    if facts_path is not None and facts_path.is_file():
        try:
            facts = yaml_min.load(facts_path.read_text(encoding="utf-8-sig"))
        except yaml_min.YamlError as exc:
            violations.append({"path": "$", "code": "PARSE_ERROR", "message": str(exc)})
    elif facts_path is not None:
        violations.append({"path": "$", "code": "ARGUMENT_ERROR", "message": f"facts file not found: {facts_path}"})

    schema_path = resolve_schema_path(args.schema)
    if facts is not None and schema_path is not None:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            violations.extend(schema_check.validate(facts, schema))
        except (OSError, json.JSONDecodeError) as exc:
            violations.append({"path": "$", "code": "SCHEMA_ERROR", "message": str(exc)})
        except schema_check.SchemaError as exc:
            violations.append({"path": "$", "code": "SCHEMA_ERROR", "message": str(exc)})
    elif facts is not None:
        violations.append(
            {
                "path": "$",
                "code": "SCHEMA_NOT_FOUND",
                "message": "workbook-facts.schema.json not found; pass --schema",
            }
        )

    documents = []
    sidecar_default = facts_path.parent / "confirmations.yaml" if facts_path else None
    confirmations_path = Path(args.confirmations) if args.confirmations else sidecar_default
    purposes, roles = [], []
    if confirmations_path is not None:
        purposes, roles = load_confirmations(confirmations_path)

    if facts is not None:
        for option, default_name in (
            ("audit", "workbook-audit.md"),
            ("reference", "dashboard-reference.md"),
            ("specs", "sheet-specs.md"),
        ):
            explicit = getattr(args, option)
            path = Path(explicit) if explicit else (
                facts_path.parent / default_name if facts_path else None
            )
            if path is not None and path.is_file():
                documents.append({"name": path.name, "text": path.read_text(encoding="utf-8-sig")})
            elif path is not None:
                documents.append({"name": path.name, "text": None})

        if facts is not None and isinstance(facts, dict):
            interpretations = facts.get("interpretation_inputs", {})
            purposes = purposes or list(interpretations.get("dashboard_purposes", []))
            roles = roles or list(interpretations.get("sheet_roles", []))
            violations.extend(lint(facts, documents, (purposes, roles)))

    result = {
        "valid": not violations,
        "facts": str(facts_path) if facts_path else None,
        "documents": [document["name"] for document in documents],
        "violations": violations,
    }
    print(json.dumps(result, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main())
