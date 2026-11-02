"""Seed, validate, and render the model component of a dataset intelligence pack.

Extraction snapshots are immutable. Interpretations use explicit proposal and
review labels and never turn workbook settings into successful data tests.
"""
from __future__ import annotations

import copy
import html
import json


def snapshot(facts):
    return [{"datasource_id": source["id"], "model_structure": copy.deepcopy(source.get("model_structure"))}
            for source in facts.get("datasources", [])]


def table_records(facts):
    records = []
    for source in facts.get("datasources", []):
        model = source.get("model_structure") or {}
        tables = model.get("logical_tables", [])
        if not tables:
            tables = [item for item in model.get("relations", []) if item.get("type") in ("table", "text")]
        records.extend((source, table) for table in tables)
    return records


def seed(facts, dataset_id):
    if facts.get("model_metadata_version") != 1:
        raise ValueError("Fresh model_metadata_version: 1 workbook facts are required.")
    data = {"schema_version": 1, "document_type": "dataset_model", "dataset_id": dataset_id,
            "source_workbook_sha256": facts.get("provenance", {}).get("input_sha256"),
            "status": "draft", "reviewed": False,
            "structural_snapshot": snapshot(facts), "table_meanings": [], "grains": [],
            "candidate_keys": [], "risks": [], "open_questions": []}
    for number, (source, table) in enumerate(table_records(facts), 1):
        base = {"table_id": table["id"], "field_ids": [], "statement": "Needs analyst interpretation.",
                "status": "proposed", "verification": "not_tested", "evidence": [table["id"]]}
        data["table_meanings"].append({"id": f"{dataset_id}.table-meaning.{number}", **copy.deepcopy(base)})
        data["grains"].append({"id": f"{dataset_id}.grain.{number}", **copy.deepcopy(base)})
    return data


def validate(data, facts):
    """Semantic checks. The pack entry point also validates the JSON Schema."""
    violations = []

    def fail(path, code, message):
        violations.append({"path": path, "code": code, "message": message})

    if not isinstance(data, dict):
        return [{"path": "$", "code": "MODEL_TYPE", "message": "Model must be an object."}]
    if facts.get("model_metadata_version") != 1:
        fail("$", "MODEL_FACTS_REQUIRED", "Fresh model metadata extension is required.")
    expected_hash = facts.get("provenance", {}).get("input_sha256")
    if not expected_hash or data.get("source_workbook_sha256") != expected_hash:
        fail("$.source_workbook_sha256", "SOURCE_HASH_MISMATCH", "Model must bind to the exact source workbook hash.")
    if data.get("structural_snapshot") != snapshot(facts):
        fail("$.structural_snapshot", "MODEL_SNAPSHOT_MISMATCH", "Structural snapshot must exactly equal the extracted model facts.")
    known_tables = {table["id"] for _, table in table_records(facts)}
    field_sources = {field["id"]: source["id"] for source in facts.get("datasources", []) for field in source.get("fields", [])}
    table_sources = {table["id"]: source["id"] for source, table in table_records(facts)}
    field_tables = {}
    for source in facts.get("datasources", []):
        for column in (source.get("model_structure") or {}).get("column_metadata", []):
            if column.get("field_id") and column.get("logical_table_id"):
                field_tables.setdefault(column["field_id"], set()).add(column["logical_table_id"])
    known_evidence = set(field_sources) | known_tables
    for source in facts.get("datasources", []):
        known_evidence.add(source["id"])
        for records in (source.get("model_structure") or {}).values():
            if isinstance(records, list):
                for record in records:
                    if isinstance(record, dict):
                        known_evidence.add(record.get("id"))
    seen = set()
    for section in ("table_meanings", "grains", "candidate_keys", "risks", "open_questions"):
        records = data.get(section, [])
        if not isinstance(records, list):
            fail(f"$.{section}", "MODEL_RECORD_TYPE", "Expected an array.")
            continue
        for index, record in enumerate(records):
            path = f"$.{section}[{index}]"
            if not isinstance(record, dict):
                fail(path, "MODEL_RECORD_TYPE", "Expected an object.")
                continue
            identifier = record.get("id")
            if not identifier or identifier in seen:
                fail(path + ".id", "DUPLICATE_OR_MISSING_ID", "Each annotation must have a unique explicit ID.")
            seen.add(identifier)
            if section in ("table_meanings", "grains", "candidate_keys"):
                table_id = record.get("table_id")
                if table_id not in known_tables:
                    fail(path + ".table_id", "UNKNOWN_TABLE", "Table must reference an extracted logical table or physical table when no logical graph exists.")
                for field_id in record.get("field_ids", []):
                    if field_id not in field_sources:
                        fail(path + ".field_ids", "UNKNOWN_FIELD", "Field ID does not exist in facts.")
                    elif table_sources.get(table_id) != field_sources[field_id]:
                        fail(path + ".field_ids", "CROSS_SOURCE_FIELD", "Table annotation cannot use a field from another datasource.")
                    elif field_id in field_tables and table_id not in field_tables[field_id]:
                        fail(path + ".field_ids", "FIELD_TABLE_MISMATCH", "The workbook explicitly binds this field to another logical table; retain that recorded ownership.")
            if section != "open_questions":
                if record.get("status") not in ("proposed", "confirmed"):
                    fail(path + ".status", "INTERPRETATION_STATUS", "Interpretations must be proposed or confirmed.")
                if record.get("verification") != "not_tested":
                    fail(path + ".verification", "UNSUPPORTED_VERIFICATION", "Workbook metadata never verifies grain, keys, nullability, or relationship safety.")
                if record.get("status") == "confirmed" and not all(record.get(key) for key in ("confirmed_by", "confirmed_at")):
                    fail(path, "CONFIRMATION_ATTRIBUTION", "Confirmed interpretations require explicit analyst attribution and timestamp.")
            for evidence in record.get("evidence", []):
                if evidence not in known_evidence:
                    fail(path + ".evidence", "UNKNOWN_EVIDENCE", "Evidence must reference a recorded fact ID.")
    for section in ("table_meanings", "grains"):
        recorded = [record.get("table_id") for record in data.get(section, []) if isinstance(record, dict)]
        if set(recorded) != known_tables or len(recorded) != len(set(recorded)):
            fail("$." + section, "TABLE_COVERAGE", "Every extracted logical table, or physical table when no logical graph exists, requires exactly one annotation.")
    if data.get("reviewed") is True:
        for section in ("table_meanings", "grains", "candidate_keys", "risks"):
            if any(record.get("statement") == "Needs analyst interpretation." for record in data.get(section, [])):
                fail("$.reviewed", "MODEL_REVIEW_INCOMPLETE", "Review cannot retain seed placeholders.")
    return violations


def escape(value):
    return html.escape(str(value if value is not None else "Not recorded"), quote=False).replace("|", "\\|").replace("\n", "<br>").replace("`", "&#96;").replace("[", "&#91;").replace("]", "&#93;")


def expression_text(node):
    if node is None:
        return "Not recorded"
    op = node.get("attributes", {}).get("op", node.get("tag", ""))
    children = node.get("children", [])
    if not children:
        return op + (" " + node["text"] if node.get("text") else "")
    return "(" + (" " + op + " ").join(expression_text(item) for item in children) + ")"


def render(data):
    out = ["# Dataset data model", "", f"Dataset: `{escape(data['dataset_id'])}`", "",
           f"Status: {escape(data['status'])}. Review completed: {str(data.get('reviewed', False)).lower()}.", "",
           "This model describes workbook metadata. Grain and keys are interpretations; no data tests were run. Each logical table has its own grain proposal.", "",
           "## Table meaning and grain", "", "| Logical table | Business meaning | Proposed grain | Candidate key, untested |", "| --- | --- | --- | --- |"]
    all_labels = {}
    for source in data.get("structural_snapshot", []):
        structure = source.get("model_structure") or {}
        for table in structure.get("logical_tables", []):
            all_labels[table["id"]] = table.get("caption") or table.get("object_id") or table["id"]
        if not structure.get("logical_tables"):
            for relation in structure.get("relations", []):
                all_labels[relation["id"]] = relation.get("name") or relation.get("table") or relation["id"]
    grains = {item["table_id"]: item for item in data.get("grains", [])}
    for meaning in data.get("table_meanings", []):
        table_id = meaning["table_id"]
        keys = [item["statement"] for item in data.get("candidate_keys", []) if item["table_id"] == table_id]
        out.append("| " + " | ".join(escape(value) for value in (all_labels.get(table_id, table_id), meaning["statement"], grains.get(table_id, {}).get("statement", "Needs analyst interpretation."), "; ".join(keys) or "Not proposed")) + " |")
    out += ["", "Each interpretation's status and fact references are listed below.", "", "## Logical relationships", ""]
    logical_tables = [(item["id"], item.get("caption") or item.get("object_id") or item["id"])
                      for source in data.get("structural_snapshot", [])
                      for item in (source.get("model_structure") or {}).get("logical_tables", [])]
    nodes = {identifier: "t" + str(index) for index, (identifier, _) in enumerate(logical_tables, 1)}
    if nodes:
        out += ["```mermaid", "flowchart LR"]
        for identifier, label in logical_tables:
            # Encode all user-controlled punctuation inside quoted Mermaid labels.
            safe_label = "".join(character if character.isalnum() or character in " _.-" else "#" + str(ord(character)) + ";" for character in label)
            out.append(f'  {nodes[identifier]}["{safe_label}"]')
        for source in data.get("structural_snapshot", []):
            for relationship in (source.get("model_structure") or {}).get("relationships", []):
                ends = [nodes.get(endpoint.get("logical_table_id")) for endpoint in relationship.get("endpoints", [])]
                if len(ends) == 2 and all(ends):
                    out.append(f"  {ends[0]} --- {ends[1]}")
        out += ["```", "", "Lines represent recorded logical relationships; line direction does not claim tested cardinality.", ""]
    out += ["| Tables | Recorded relationship expression | Configured unique-key sides |", "| --- | --- | --- |"]
    for source in data.get("structural_snapshot", []):
        for relationship in (source.get("model_structure") or {}).get("relationships", []):
            names = [str(all_labels.get(endpoint.get("logical_table_id"), endpoint.get("object_id"))) for endpoint in relationship.get("endpoints", [])]
            unique = [str(all_labels.get(endpoint.get("logical_table_id"), endpoint.get("object_id"))) for endpoint in relationship.get("endpoints", []) if endpoint.get("configured_settings", {}).get("unique-key") == "true"]
            out.append("| " + " | ".join(escape(value) for value in (" / ".join(names), "; ".join(expression_text(item) for item in relationship.get("expressions", [])), ", ".join(unique) or "Not recorded")) + " |")
    out += ["", "Configured uniqueness is not a completed key test. Recorded physical relations, exact endpoint settings, IDs, and evidence follow.", "", "## Recorded structure details", ""]
    for source in data.get("structural_snapshot", []):
        model = source.get("model_structure") or {}
        out += [f"### {escape(source['datasource_id'])}", "", "| Logical table ID | Recorded caption |", "| --- | --- |"]
        labels = {}
        for table in model.get("logical_tables", []):
            labels[table["id"]] = table.get("caption") or table.get("object_id")
            out.append(f"| `{escape(table['id'])}` | {escape(labels[table['id']])} |")
        out += ["", "| Relationship ID | Endpoints | Expression | Recorded settings |", "| --- | --- | --- | --- |"]
        for rel in model.get("relationships", []):
            endpoint_labels = [labels.get(ep.get("logical_table_id"), ep.get("object_id")) for ep in rel["endpoints"]]
            settings = [ep.get("side", "") + ": " + json.dumps(ep.get("configured_settings", {}), sort_keys=True) for ep in rel["endpoints"]]
            expr = "; ".join(expression_text(item) for item in rel["expressions"])
            out.append(f"| `{escape(rel['id'])}` | {escape(' / '.join(str(item) for item in endpoint_labels))} | {escape(expr)} | {escape('; '.join(settings))} |")
        out += ["", "Endpoint unique-key, cardinality, and integrity values are recorded settings, not completed tests.", "",
                "| Physical relation ID | Logical owner | Context | Type | Table or name | Parent / join |", "| --- | --- | --- | --- | --- | --- |"]
        for relation in model.get("relations", []):
            out.append("| " + " | ".join(escape(value) for value in (relation["id"], labels.get(relation.get("logical_table_id"), relation.get("logical_table_id")), relation["context"], relation["type"], relation.get("table") or relation.get("name"), str(relation.get("parent_relation_id") or "") + " / " + str(relation.get("join_type") or ""))) + " |")
            if relation.get("clauses"):
                out += ["", "Recorded clauses for `" + escape(relation["id"]) + "`: " + escape("; ".join(expression_text(item) for item in relation["clauses"])), ""]
        columns = model.get("column_metadata", [])
        declared = [item for item in columns if item.get("source_declared_nullable") is not None]
        out += ["", f"Source-declared nullability is recorded on {len(declared)} of {len(columns)} metadata records. Cached contains-null flags remain separate in YAML and establish no constraint or null count.", ""]
        if model.get("gaps"):
            out += ["Recorded structure gaps:", ""] + [f"- `{escape(item['id'])}` {escape(item['message'])}" for item in model["gaps"]] + [""]
    for section, title in (("table_meanings", "Table meanings"), ("grains", "Grain by table"), ("candidate_keys", "Candidate keys"), ("risks", "Risks")):
        out += ["## " + title, ""]
        for item in data.get(section, []):
            out += [f"### {escape(item['id'])}", "", f"{escape(item.get('statement'))}", "",
                    f"Status: {escape(item.get('status'))}. Verification: {escape(item.get('verification'))}.", ""]
            if item.get("table_id"):
                out += [f"Table: `{escape(item['table_id'])}`. Fields: " + ", ".join("`" + escape(value) + "`" for value in item.get("field_ids", [])) + ".", ""]
            out += ["Evidence: " + ", ".join("`" + escape(value) + "`" for value in item.get("evidence", [])) + ".", ""]
        if not data.get(section):
            out += ["None recorded.", ""]
    out += ["## Open questions", ""]
    out += [f"- `{escape(item['id'])}` {escape(item['question'])}" for item in data.get("open_questions", [])] or ["None recorded."]
    return "\n".join(out).rstrip() + "\n"
