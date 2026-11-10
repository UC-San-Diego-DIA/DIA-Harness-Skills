#!/usr/bin/env python3
"""Create, validate, revise, and render a versioned Tableau field dictionary."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import re
import sys

sys.dont_write_bytecode = True
from prepare_dictionary import helper_directory
import dictionary_enrichment as enrichment

sys.path.insert(0, str(helper_directory()))
import extract_workbook_facts as intake
import schema_check
import validate_facts
import yaml_min


SCHEMA = Path(__file__).resolve().parent.parent / "references" / "data-dictionary.schema.json"
SCHEMA_V1 = SCHEMA.with_name("data-dictionary-v1.schema.json")
TOOL_VERSION = "2.0.0"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path):
    return yaml_min.load(path.read_text(encoding="utf-8-sig"))


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"Path must be absolute: {value}")
    return path


def facts_path(data, dictionary_path):
    return (dictionary_path.parent / data["source"]["facts_path"]).resolve()


def relative(path, parent):
    # Different Windows drives cannot have relative paths.
    try:
        return Path(os.path.relpath(path, parent)).as_posix()
    except ValueError:
        return str(path)


def verify_facts(path):
    facts = load(path)
    schema_path = validate_facts.resolve_schema_path(None)
    if schema_path is None:
        raise ValueError("Workbook facts schema is missing.")
    issues = schema_check.validate(facts, json.loads(schema_path.read_text(encoding="utf-8")))
    if not issues:
        issues += validate_facts.check_ids(facts)
        issues += validate_facts.check_completeness(facts)
        issues += validate_facts.check_field_metadata(facts)
    if issues:
        raise ValueError("Invalid workbook facts: " + json.dumps(issues))
    if facts.get("field_metadata_version") != 1:
        raise ValueError("Fresh extraction with field_metadata_version 1 is required.")
    if not facts["provenance"]["input_sha256"]:
        raise ValueError("Workbook hash is required; migrated facts cannot seed a dictionary.")
    if any(item["code"] == "MULTIPLE_TWB_ENTRIES" for item in facts["anomalies"]):
        raise ValueError("Package contains multiple workbooks; supply the intended standalone TWB.")
    return facts


def field_snapshots(facts):
    """Field dictionary ownership excludes additive source-model structures."""
    return [
        {key: copy.deepcopy(source[key]) for key in ("name", "caption", "id", "fields", "field_inventory")}
        for source in facts["datasources"]
    ]


def seed(facts, source, output):
    timestamp = now()
    data = {
        "schema_version": 1,
        "document_type": "tableau_data_dictionary",
        "dictionary_id": "dictionary-" + facts["provenance"]["input_sha256"],
        "revision": 1,
        "previous_revision_sha256": None,
        "previous_revision_path": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "tool_version": TOOL_VERSION,
        "source": {
            "facts_path": relative(source, output.parent),
            "facts_sha256": sha256(source),
            "workbook_sha256": facts["provenance"]["input_sha256"],
            "field_metadata_version": 1,
        },
        "workbook": copy.deepcopy(facts["workbook"]),
        "extraction_warnings": list(facts["extraction"]["warnings"]),
        "datasources": field_snapshots(facts),
        "parameters": copy.deepcopy(facts["parameters"]),
    }
    for source_record in data["datasources"]:
        for field in source_record["fields"]:
            description = field["description"]
            field["definition"] = {
                "text": description or None,
                "basis": "workbook_description" if description else "undocumented",
                "confirmation_status": "unconfirmed",
                "confirmed_at": None,
                "confirmed_by": None,
            }
            field["open_questions"] = []
    return enrichment.initialize(data)


def validate(data, path, require_ready=False):
    schema_path = SCHEMA_V1 if isinstance(data, dict) and data.get("schema_version") == 1 else SCHEMA
    issues = schema_check.validate(data, json.loads(schema_path.read_text(encoding="utf-8")))
    if issues:
        return issues

    def problem(location, message):
        issues.append({"path": location, "message": message})

    source = facts_path(data, path)
    if sha256(source) != data["source"]["facts_sha256"]:
        problem("source.facts_sha256", "The source facts file has changed.")
        return issues
    facts = verify_facts(source)
    if data["source"]["workbook_sha256"] != facts["provenance"]["input_sha256"]:
        problem("source.workbook_sha256", "Workbook hash differs from the extracted provenance.")
    if data["dictionary_id"] != "dictionary-" + facts["provenance"]["input_sha256"]:
        problem("dictionary_id", "Dictionary identity differs from the source workbook hash.")
    if data["revision"] < 1:
        problem("revision", "Revision must be positive.")
    if (data["revision"] == 1) != (data["previous_revision_sha256"] is None):
        problem("previous_revision_sha256", "Only revision 1 has no parent hash.")
    if (data["revision"] == 1) != (data["previous_revision_path"] is None):
        problem("previous_revision_path", "Only revision 1 has no parent path.")
    if data["revision"] > 1 and data["previous_revision_path"]:
        previous_path = (path.parent / data["previous_revision_path"]).resolve()
        if previous_path == path.resolve():
            problem("previous_revision_path", "A revision cannot reference itself as its parent.")
        elif sha256(previous_path) != data["previous_revision_sha256"]:
            problem("previous_revision_sha256", "The previous revision file has changed.")
        else:
            previous = load(previous_path)
            migration_parent = (data["schema_version"] == 2
                                and data.get("migrated_from_schema_version") == 1
                                and previous.get("schema_version") == 1)
            if (previous.get("dictionary_id") != data["dictionary_id"]
                    or (previous.get("schema_version") != data["schema_version"] and not migration_parent)
                    or previous.get("created_at") != data["created_at"]
                    or previous.get("revision") != data["revision"] - 1):
                problem("previous_revision_path", "Parent identity, schema, creation time, or revision is inconsistent.")
    for key in ("created_at", "updated_at"):
        try:
            parsed = datetime.fromisoformat(data[key])
            if parsed.utcoffset() is None:
                raise ValueError("timezone missing")
        except ValueError:
            problem(key, "Timestamp must be ISO 8601 with a timezone.")
    for key in ("workbook", "parameters", "extraction_warnings"):
        original = facts["extraction"]["warnings"] if key == "extraction_warnings" else facts[key]
        if data[key] != original:
            problem(key, "Recorded workbook metadata must match the source facts.")
    stripped = copy.deepcopy(data["datasources"])
    if data["schema_version"] == 2:
        validate_value_domains(data, path, issues)
        enrichment.validate_annotations(data, facts, issues, require_ready)
    for source_index, source_record in enumerate(stripped):
        for field_index, field in enumerate(source_record["fields"]):
            definition = field.pop("definition")
            field.pop("open_questions")
            if data["schema_version"] == 2:
                field.pop("category")
                field.pop("enrichment")
                field.pop("value_domain", None)
            location = f"datasources[{source_index}].fields[{field_index}].definition"
            confirmed = definition["confirmation_status"] == "confirmed"
            if confirmed != (definition["basis"] == "analyst_confirmed"):
                problem(location, "Only analyst_confirmed definitions can have confirmed status.")
            if confirmed:
                if not definition["confirmed_at"] or not definition["confirmed_by"] or not definition["text"]:
                    problem(location, "Confirmed definitions require text, attribution, and time.")
                else:
                    try:
                        if datetime.fromisoformat(definition["confirmed_at"]).utcoffset() is None:
                            raise ValueError("timezone missing")
                    except ValueError:
                        problem(location, "Confirmation time must be ISO 8601 with a timezone.")
            elif definition["confirmed_at"] is not None or definition["confirmed_by"] is not None:
                problem(location, "Unconfirmed definitions cannot carry confirmation attributes.")
            if definition["basis"] == "undocumented":
                if definition["text"] is not None:
                    problem(location, "Undocumented meaning must have null text.")
            elif not definition["text"] or not definition["text"].strip():
                problem(location, "A documented or proposed meaning requires nonempty text.")
            if definition["basis"] == "workbook_description" and not field["description"]:
                problem(location, "No workbook description supports this evidence label.")
            if definition["basis"] == "formula_derived" and not (
                field["calculation"] and field["calculation"]["formula"]
            ):
                problem(location, "No recorded formula supports this evidence label.")
    if stripped != field_snapshots(facts):
        problem("datasources", "Field coverage, IDs, order, or recorded metadata differ from source facts.")
    return issues


def validate_value_domains(data, path, issues):
    """Check optional observations against portable, hashed profiling evidence."""
    for source in data["datasources"]:
        for field in source["fields"]:
            domain = field.get("value_domain")
            if domain is None:
                continue
            location = field["id"] + ".value_domain"

            def fail(message):
                issues.append({"path": location, "message": message})

            provenance = domain["provenance"]
            root = path.parent.resolve()
            profile_path = (root / provenance["profile_path"]).resolve()
            if provenance["profile_path"] != "evidence/value-profile.yaml" or not profile_path.is_relative_to(root):
                fail("Value domains must reference evidence/value-profile.yaml inside the output directory.")
                continue
            if not profile_path.is_file() or sha256(profile_path) != provenance["profile_sha256"]:
                fail("Immutable value-profile evidence is missing or has changed.")
                continue
            profile = load(profile_path)
            if (profile.get("document_type") != "tableau_value_profile" or profile.get("schema_version") != 1
                    or profile.get("provenance", {}).get("workbook_sha256") != data["source"]["workbook_sha256"]
                    or profile.get("provenance", {}).get("extract_sha256") != provenance["extract_sha256"]):
                fail("Value-domain provenance differs from the workbook/extract snapshot.")
                continue
            matches = [(table, column) for table in profile.get("tables", [])
                       if table.get("schema") == provenance["schema"] and table.get("name") == provenance["table"]
                       for column in table.get("fields", []) if column.get("name") == provenance["column"]]
            if len(matches) != 1:
                fail("Value-domain provenance must identify exactly one physical extract column.")
                continue
            table, column = matches[0]
            if (domain["row_count"] != table.get("row_count") or any(
                domain[key] != column.get(key) for key in ("null_count", "distinct_count", "values", "values_truncated")
            )):
                fail("Value-domain observations must exactly match their immutable profile evidence.")


def yaml_text(data):
    # Quote all nonempty strings to preserve whitespace in definitions as well as formulas.
    def lines(value, indent=0):
        pad = " " * indent
        if isinstance(value, dict):
            result = []
            for key, item in value.items():
                key = intake.render_key(key)
                if isinstance(item, (dict, list)) and item:
                    result.append(f"{pad}{key}:")
                    result.extend(lines(item, indent + 2))
                else:
                    result.append(f"{pad}{key}: {scalar(item)}")
            return result
        result = []
        for item in value:
            if isinstance(item, (dict, list)) and item:
                nested = lines(item, indent + 2)
                result.append(pad + "- " + nested[0][indent + 2:])
                result.extend(nested[1:])
            else:
                result.append(pad + "- " + scalar(item))
        return result

    def scalar(value):
        if isinstance(value, str):
            return intake.quote_scalar(value)
        if isinstance(value, (dict, list)):
            return "{}" if isinstance(value, dict) else "[]"
        return intake.render_scalar(value)

    return "# Structured source for the generated data dictionary.\n" + "\n".join(lines(data)) + "\n"


def md(value):
    if value is None or value == "":
        return "Not recorded in workbook metadata."
    return re.sub(r"([\\`*_{}\[\]<>()#+!|~])", r"\\\1", str(value)).replace("\r", "").replace("\n", "<br>")


def fenced(value):
    length = max([len(run) for run in re.findall(r"`+", value)] + [2]) + 1
    fence = "`" * length
    return fence + "text\n" + value + ("" if value.endswith("\n") else "\n") + fence


LABELS = {
    "workbook_description": "Workbook description",
    "formula_derived": "Formula-derived explanation, unconfirmed",
    "name_based": "Name-based interpretation, unconfirmed",
    "analyst_confirmed": "Analyst-confirmed definition",
    "undocumented": "Meaning not documented",
}


def render(data, path):
    if data["schema_version"] == 2:
        return enrichment.render(data, path, md, sha256)
    out = [
        "# Tableau data dictionary", "",
        "Generated from structured, versioned metadata. Update the YAML and regenerate this document.", "",
        f"Workbook: {md(data['workbook']['name'])}", "",
        f"Structured dictionary: {md(path.name)}",
        f"Schema version: {data['schema_version']}; revision: {data['revision']}",
        f"Dictionary SHA-256: {sha256(path)}",
        f"Updated: {md(data['updated_at'])}",
        f"Workbook SHA-256: {data['source']['workbook_sha256']}",
        f"Source facts: {md(data['source']['facts_path'])}", "",
        "This dictionary describes fields represented in the workbook's metadata. "
        "Data values and the underlying database schema were not inspected.", "",
    ]
    if data["extraction_warnings"]:
        out += ["## Extraction warnings", ""]
        out += ["- " + md(item) for item in data["extraction_warnings"]] + [""]
    questions = []
    for source in data["datasources"]:
        out += ["## " + md(source["caption"] or source["name"]), "",
                f"Source: {md(source['name'])}; ID: {md(source['id'])}", "",
                f"Recorded fields: {len(source['fields'])}", ""]
        out += ["- " + md(item) for item in source["field_inventory"]["warnings"]]
        if source["field_inventory"]["warnings"]:
            out.append("")
        if not source["fields"]:
            out += ["No field definitions recorded. Workbook controls are listed under Parameters.", ""]
        for field in source["fields"]:
            definition = field["definition"]
            out += ["### " + md(field["caption"] or field["name"]), "",
                    "| Attribute | Recorded value |", "| --- | --- |"]
            for label, key in (("Field ID", "id"), ("Technical name", "name"), ("Tableau data type", "datatype"),
                               ("Role", "role"), ("Type", "type"), ("Field kind", "field_kind"),
                               ("Default aggregation", "default_aggregation")):
                out.append(f"| {label} | {md(field[key])} |")
            hidden = "Unknown" if field["hidden"] is None else ("Hidden" if field["hidden"] else "Explicitly visible")
            out += [f"| Hidden status | {hidden} |", "",
                    f"Meaning: {md(definition['text']) if definition['text'] is not None else 'Meaning not documented in workbook metadata.'}", "",
                    f"Evidence: {LABELS[definition['basis']]}", "",
                    f"Confirmation status: {definition['confirmation_status']}", "",
                    "Original workbook description: " + md(field["description"]), ""]
            if definition["confirmation_status"] == "confirmed":
                out += [f"Confirmed by {md(definition['confirmed_by'])} at {md(definition['confirmed_at'])}.", ""]
            if field["aliases"]:
                out += ["Configured aliases, not observed values:", ""]
                out += [f"- {md(item['key'])} = {md(item['value'])}" for item in field["aliases"]] + [""]
            else:
                out += ["No aliases recorded.", ""]
            if field["source_columns"]:
                out += ["Cached source mappings, not verified database lineage:", ""]
                out += [f"- Table: {md(item['table'])}; column: {md(item['name'])}; physical type: {md(item['datatype'])}"
                        for item in field["source_columns"]] + [""]
            else:
                out += ["No physical-column mappings recorded.", ""]
            if field["conflicts"]:
                out += ["Metadata conflicts. Source declarations take precedence over worksheet caches, then connection metadata.", ""]
                out += [f"- {md(item['attribute'])}: {md(item['evidence'])}" for item in field["conflicts"]] + [""]
            if field["calculation"] is not None:
                calculation = field["calculation"]
                out += ["Calculation class: " + md(calculation["class"]), ""]
                out += [fenced(calculation["formula"]) if calculation["formula"] is not None
                        else "Formula text not recorded in workbook metadata.", ""]
            out += ["Metadata evidence:", ""]
            out += ["- " + md(item) for item in field["evidence"]] + [""]
            questions.extend((field["id"], item) for item in field["open_questions"])
    out += ["## Parameters", "", "Parameters are workbook controls. Allowed values are metadata settings.", ""]
    for parameter in data["parameters"]:
        out += [f"### {md(parameter['caption'] or parameter['name'])}", "",
                f"ID: {md(parameter['id'])}; technical name: {md(parameter['name'])}; source: {md(parameter['datasource'])}", ""]
        out += ["- " + md(member) for member in parameter["members"]] or ["No allowed values recorded."]
        out.append("")
    if not data["parameters"]:
        out += ["No parameters recorded.", ""]
    out += ["## Open definitions", ""]
    out += [f"- {md(identifier)}: {md(question)}" for identifier, question in questions] or ["No additional questions recorded."]
    return "\n".join(out) + "\n"


def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--facts", required=True)
    create.add_argument("--output", required=True)
    for command in ("validate", "render", "revise", "migrate"):
        action = sub.add_parser(command)
        action.add_argument("--dictionary", required=True)
        if command in ("render", "revise", "migrate"):
            action.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            source, output = absolute(args.facts), absolute(args.output)
            data = seed(verify_facts(source), source, output)
            issues = validate(data, output)
            content = yaml_text(data)
        else:
            source = absolute(args.dictionary)
            data = load(source)
            issues = validate(data, source, require_ready=args.command in ("validate", "render"))
            if args.command == "validate":
                print(json.dumps({"valid": not issues, "violations": issues}, indent=2))
                return 2 if issues else 0
            if issues:
                raise ValueError("Dictionary validation failed: " + json.dumps(issues))
            output = absolute(args.output)
            if args.command in ("revise", "migrate"):
                if args.command == "migrate":
                    if data["schema_version"] != 1:
                        raise ValueError("Only schema-version-1 dictionaries need migration.")
                    data = enrichment.initialize(data, migrated=True)
                data["revision"] += 1
                data["previous_revision_sha256"] = sha256(source)
                data["previous_revision_path"] = relative(source, output.parent)
                data["updated_at"] = now()
                data["tool_version"] = TOOL_VERSION
                data["source"]["facts_path"] = relative(facts_path(load(source), source), output.parent)
                issues = validate(data, output)
                content = yaml_text(data)
            else:
                content = render(data, source)
        if issues:
            raise ValueError("Dictionary validation failed: " + json.dumps(issues))
        write_new(output, content)
        print(json.dumps({"output": str(output), "schema_version": data["schema_version"], "revision": data["revision"]}))
        return 0
    except (OSError, ValueError, yaml_min.YamlError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
