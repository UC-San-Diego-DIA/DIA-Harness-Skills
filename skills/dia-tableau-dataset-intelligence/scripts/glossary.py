"""Business-concept glossary and safe, deterministic dictionary CSV view.

No workbook, database, formula, or data-value access occurs here. A seed is
deliberately empty: selecting reusable concepts requires contextual review.
"""

from __future__ import annotations

import csv
from datetime import datetime
import io
import json
import re


def seed(dictionary, dataset_id):
    return {"schema_version": 1, "document_type": "business_glossary",
            "dataset_id": dataset_id,
            "source_workbook_sha256": dictionary["source"]["workbook_sha256"],
            "status": "draft", "reviewed": False, "terms": [],
            "open_questions": []}


def _ids(value):
    result = set()
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            result.add(value["id"])
        for child in value.values():
            result.update(_ids(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_ids(child))
    return result


def validate(data, dictionary):
    """Return semantic violations; caller also applies the packaged schema."""
    issues = []

    def problem(path, message):
        issues.append({"path": path, "message": message})

    if not isinstance(data, dict):
        return [{"path": "$", "message": "Glossary must be an object."}]
    if data.get("source_workbook_sha256") != dictionary.get("source", {}).get("workbook_sha256"):
        problem("source_workbook_sha256", "Glossary and dictionary workbook hashes differ.")
    dataset_id = data.get("dataset_id", "")
    known = _ids(dictionary)
    fields = {f["id"] for s in dictionary.get("datasources", []) for f in s.get("fields", [])
              if f.get("category", "business") == "business"}
    seen = set()
    names = set()
    terms = data.get("terms", [])
    if not isinstance(terms, list):
        return issues + [{"path": "terms", "message": "Terms must be an array."}]
    if data.get("reviewed") and not terms:
        problem("terms", "A reviewed glossary needs at least one selected business concept.")
    for i, term in enumerate(terms):
        path = f"terms[{i}]"
        if not isinstance(term, dict):
            problem(path, "Term must be an object.")
            continue
        ident = term.get("term_id")
        if not isinstance(ident, str) or not re.fullmatch(re.escape(dataset_id) + r"\.term\.[a-z0-9]+(?:-[a-z0-9]+)*", ident):
            problem(path + ".term_id", "Use a stable dataset-scoped ID: <dataset_id>.term.<concept-slug>.")
        if ident in seen:
            problem(path + ".term_id", "Duplicate term ID.")
        seen.add(ident)
        name = str(term.get("name", "")).strip().casefold()
        if not name:
            problem(path + ".name", "Provide a nonempty business-concept name.")
        if name in names:
            problem(path + ".name", "Duplicate business-concept name.")
        names.add(name)
        refs = term.get("field_refs", [])
        if not refs or any(ref not in fields for ref in refs):
            problem(path + ".field_refs", "Concepts must reference existing business fields.")
        if len(refs) != len(set(refs)):
            problem(path + ".field_refs", "Duplicate field reference.")
        definition = term.get("definition", {})
        if (definition.get("status") == "confirmed") != (definition.get("basis") == "analyst_confirmed"):
            problem(path + ".definition", "Only analyst-confirmed definitions can have confirmed status.")
        for key, annotation in [("definition", definition)] + [
            (f"synonyms[{j}]", item) for j, item in enumerate(term.get("synonyms", []))
        ]:
            ap = path + "." + key
            evidence = annotation.get("evidence_refs", [])
            if not evidence or any(ref not in known for ref in evidence):
                problem(ap + ".evidence_refs", "Reference existing dictionary evidence IDs.")
            if not str(annotation.get("text") or "").strip():
                problem(ap + ".text", "Provide a supported definition or proposed synonym.")
            confirmed = annotation.get("status") == "confirmed"
            if confirmed:
                try:
                    if not annotation.get("confirmed_by", "").strip():
                        raise ValueError("missing attribution")
                    stamp = datetime.fromisoformat(annotation.get("confirmed_at") or "")
                    if stamp.utcoffset() is None:
                        raise ValueError("missing timezone")
                except (ValueError, TypeError, AttributeError):
                    problem(ap, "Confirmed annotations require attribution and timezone-aware approval time.")
            elif annotation.get("confirmed_at") is not None or annotation.get("confirmed_by") is not None:
                problem(ap, "Proposed annotations cannot carry approval attribution.")
        if term.get("approval_status") != definition.get("status"):
            problem(path + ".approval_status", "Concept approval must match definition approval; synonyms are approved separately.")
        if term.get("verification") != "not_tested":
            problem(path + ".verification", "Metadata review does not test the underlying data.")
    return issues


def _md(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def render(data):
    out = ["# Business glossary", "", "Definitions and synonyms are proposals unless explicitly confirmed. Data verification: not tested.", "",
           "| Business concept | Meaning | Proposed or confirmed synonyms | Approval |", "| --- | --- | --- | --- |"]
    for term in data["terms"]:
        synonyms = "; ".join(f"{s['text']} [{s['status']}]" for s in term["synonyms"]) or "None recorded"
        out.append("| " + " | ".join(_md(v) for v in [term["name"], term["definition"]["text"], synonyms, term["approval_status"]]) + " |")
    questions = [(term["name"], q) for term in data["terms"] for q in term["open_questions"]]
    questions += [("Dataset", q) for q in data["open_questions"]]
    if questions:
        out += ["", "## Questions for review", ""]
        out.extend("- " + _md(name) + ": " + _md(question) for name, question in questions)
    return "\n".join(out) + "\n"


def export_dictionary_csv(dictionary, model=None):
    """Export every field, including separately classified Tableau internals.

    Prefix text whose first non-whitespace character is =, +, -, or @ with an
    apostrophe. CSV quoting alone does not stop Excel formula interpretation.
    The apostrophe is an export-only safety marker; YAML stays unchanged.
    Source mappings/evidence are JSON strings. Nullability is source-declared
    only, never observed missingness; absent metadata exports as 'unknown'.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["field_id", "source_id", "source_name", "technical_name", "display_name", "datatype", "category", "technical_role", "field_kind", "meaning", "evidence_basis", "approval_status", "verification", "source_declared_nullability", "source_mappings", "calculation_logic", "aliases", "original_description", "evidence_refs"])
    declared = {}
    for source in (model or {}).get("structural_snapshot", []):
        for record in (source.get("model_structure") or {}).get("column_metadata", []):
            if record.get("field_id") and record.get("source_declared_nullable") is not None:
                declared.setdefault(record["field_id"], set()).add(str(record["source_declared_nullable"]))

    def safe(value):
        value = str(value) if value is not None else ""
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

    for source in dictionary["datasources"]:
        for field in source["fields"]:
            definition = field["definition"]
            label = field.get("enrichment", {}).get("label") or {}
            nullability = field.get("nullable", "unknown")
            if nullability is None:
                nullability = "unknown"
            if field["id"] in declared:
                values = sorted(declared[field["id"]])
                nullability = values[0] if len(values) == 1 else "conflicting: " + ", ".join(values)
            row = [field["id"], source["id"], source.get("caption") or source["name"], field["name"], label.get("text") or field.get("caption") or field["name"], field["datatype"], field.get("category", "business"), field.get("role"), field.get("field_kind"), definition.get("text"), definition["basis"], definition["confirmation_status"], "not_tested", nullability, json.dumps(field.get("source_columns", []), ensure_ascii=False, sort_keys=True), (field.get("calculation") or {}).get("formula"), json.dumps(field.get("aliases", []), ensure_ascii=False, sort_keys=True), field.get("description"), json.dumps(definition.get("evidence_refs", []), ensure_ascii=False)]
            writer.writerow([safe(value) for value in row])
    return stream.getvalue()
