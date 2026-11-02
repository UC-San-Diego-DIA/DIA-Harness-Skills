"""Contextual annotations and the compact schema-v2 analyst reference."""

from __future__ import annotations

import copy
from datetime import datetime


def category(field):
    # A reserved technical identifier and datatype, never a caption-based guess.
    if field["datatype"] == "table" and field["name"].startswith("[__tableau_internal_object_id__]."):
        return "tableau_internal"
    return "business"


def initialize(data, migrated=False):
    """Add enrichment slots without inventing business meaning or approvals."""
    result = copy.deepcopy(data)
    result["schema_version"] = 2
    result["migrated_from_schema_version"] = 1 if migrated else None
    result["context_sources"] = []
    result["dataset_context"] = {
        "reviewed": False, "summary": None, "row_description": None,
        "usage_notes": [], "open_questions": [],
    }
    for source in result["datasources"]:
        for field in source["fields"]:
            field["category"] = category(field)
            field["definition"]["evidence_refs"] = [field["id"]] if field["definition"]["text"] else []
            field["enrichment"] = {
                "reviewed": field["category"] == "tableau_internal",
                "label": None, "units": None, "format": None, "code_meanings": [],
                "derivation": None, "usage_notes": [],
            }
    return result


def validate_annotations(data, facts, issues, require_ready=False):
    def problem(path, message):
        issues.append({"path": path, "message": message})

    def identifiers(value):
        found = set()
        if isinstance(value, dict):
            if isinstance(value.get("id"), str):
                found.add(value["id"])
            for item in value.values():
                found.update(identifiers(item))
        elif isinstance(value, list):
            for item in value:
                found.update(identifiers(item))
        return found

    known = identifiers(facts)
    for index, source in enumerate(data["context_sources"]):
        if source["id"] in known:
            problem(f"context_sources[{index}].id", "Context reference IDs must be unique and not shadow workbook IDs.")
        known.add(source["id"])
        if source["kind"] == "supplied_document" and source["sha256"] is None:
            problem(f"context_sources[{index}].sha256", "Supplied documents require a source hash.")

    def annotation(value, path, allow_undocumented=False):
        if value is None:
            return
        refs = value["evidence_refs"]
        if any(ref not in known for ref in refs):
            problem(path + ".evidence_refs", "An evidence reference does not identify a fact or supplied context source.")
        if value["basis"] == "undocumented":
            if value["text"] is not None:
                problem(path, "Undocumented meaning must have null text.")
            elif not allow_undocumented:
                problem(path, "Omit unavailable optional annotations instead of filling an empty annotation record.")
        elif not value["text"] or not value["text"].strip() or not refs:
            problem(path, "A populated annotation requires nonempty text and evidence references.")
        if value["basis"] == "supplied_context" and not any(
            ref in {item["id"] for item in data["context_sources"]} for ref in refs
        ):
            problem(path, "Supplied-context annotations must cite a supplied context record.")
        confirmed = value["confirmation_status"] == "confirmed"
        if confirmed != (value["basis"] == "analyst_confirmed"):
            problem(path, "Only analyst-confirmed annotations can have confirmed status.")
        if confirmed:
            if not value["text"] or not value["confirmed_by"] or not value["confirmed_by"].strip() or not value["confirmed_at"]:
                problem(path, "Confirmation requires text, attribution, and time.")
            else:
                try:
                    if datetime.fromisoformat(value["confirmed_at"]).utcoffset() is None:
                        raise ValueError("timezone missing")
                except ValueError:
                    problem(path, "Confirmation time must be ISO 8601 with a timezone.")
        elif value["confirmed_by"] is not None or value["confirmed_at"] is not None:
            problem(path, "Draft annotations cannot carry confirmation attributes.")

    context = data["dataset_context"]
    annotation(context["summary"], "dataset_context.summary")
    annotation(context["row_description"], "dataset_context.row_description")
    for index, note in enumerate(context["usage_notes"]):
        annotation(note, f"dataset_context.usage_notes[{index}]")
    if require_ready and (not context["reviewed"] or not context["summary"] or not context["summary"]["text"]):
        problem("dataset_context", "Complete the LLM context review and dataset summary before rendering.")
    for source_index, source in enumerate(data["datasources"]):
        for field_index, field in enumerate(source["fields"]):
            path = f"datasources[{source_index}].fields[{field_index}]"
            if field["category"] != category(field):
                problem(path + ".category", "Field category must follow the reserved-identifier rule.")
            annotation(field["definition"], path + ".definition", allow_undocumented=True)
            details = field["enrichment"]
            for key in ("label", "units", "format", "derivation"):
                annotation(details[key], path + ".enrichment." + key)
            for index, note in enumerate(details["usage_notes"]):
                annotation(note, f"{path}.enrichment.usage_notes[{index}]")
            codes = set()
            for index, item in enumerate(details["code_meanings"]):
                annotation(item["meaning"], f"{path}.enrichment.code_meanings[{index}].meaning")
                if item["code"] in codes:
                    problem(path + ".enrichment.code_meanings", "Code meanings must have unique codes per field.")
                codes.add(item["code"])
            if require_ready and field["category"] == "business":
                if not details["reviewed"]:
                    problem(path, "Review this business field in dataset context before rendering.")
                if field["definition"]["text"] is None and not field["open_questions"]:
                    problem(path, "An unresolved business field requires a focused clarification question.")


def render(data, path, md, sha256):
    def status(value):
        if value is None or value["text"] is None:
            return "Needs clarification"
        return "Confirmed" if value["confirmation_status"] == "confirmed" else "Draft"

    def annotated(value):
        if value is None or value["text"] is None:
            return "Not established."
        return md(value["text"]) + (" [draft]" if status(value) == "Draft" else " [confirmed]")

    fields = [field for source in data["datasources"] for field in source["fields"]]
    context = data["dataset_context"]
    business = [field for field in fields if field["category"] == "business"]
    out = ["# Data dictionary: " + md(data["workbook"]["name"]), "",
           "Generated from versioned YAML. Draft meanings require analyst review.", "",
           annotated(context["summary"]), ""]
    if context["row_description"] is not None:
        out += ["Record context: " + annotated(context["row_description"]), ""]
    out += [f"Business fields: {len(business)}; Tableau internal records: {len(fields) - len(business)}.", ""]
    for note in context["usage_notes"]:
        out += ["- " + annotated(note)]
    if context["usage_notes"]:
        out.append("")
    questions = [("Dataset", question) for question in context["open_questions"]]
    internals = []
    for source in data["datasources"]:
        out += ["## " + md(source["caption"] or source["name"]), "",
                "| Field | Meaning | Type | Important notes | Review |", "| --- | --- | --- | --- | --- |"]
        for field in source["fields"]:
            if field["category"] == "tableau_internal":
                internals.append((source, field))
                continue
            details = field["enrichment"]
            proposed_label = details["label"]
            label = annotated(proposed_label) if proposed_label is not None else md(field["caption"] or field["name"])
            technical = md(field["name"])
            if proposed_label is not None or (field["caption"] and field["caption"] != field["name"].strip("[]")):
                label += "<br>" + technical
            notes = []
            for key, title in (("units", "Units"), ("format", "Format"), ("derivation", "Derivation")):
                if details[key] is not None:
                    notes.append(title + ": " + annotated(details[key]))
            notes.extend(annotated(note) for note in details["usage_notes"])
            notes.extend("Code " + md(item["code"]) + ": " + annotated(item["meaning"]) for item in details["code_meanings"])
            if field["aliases"]:
                notes.append("Configured labels: " + "; ".join(md(item["key"]) + " = " + md(item["value"]) for item in field["aliases"]))
            if any(item["attribute"] in ("datatype", "calculation") for item in field["conflicts"]):
                notes.append("Recorded type or calculation metadata differs; review the structured evidence.")
            meaning = md(field["definition"]["text"]) if field["definition"]["text"] else "Meaning needs clarification."
            out.append(f"| {label} | {meaning} | {md(field['datatype'])} | {'<br>'.join(notes)} | {status(field['definition'])} |")
            questions.extend((field["caption"] or field["name"], question) for question in field["open_questions"])
        if not source["fields"]:
            out.append("| No recorded fields | No field definitions are available in this workbook. | | | Needs clarification |")
        out += [""]
        if source["field_inventory"]["warnings"]:
            out += ["Coverage: " + " ".join(md(item) for item in source["field_inventory"]["warnings"]), ""]
    if questions:
        out += ["## Questions for review", ""]
        out += ["- " + md(label) + ": " + md(question) for label, question in questions] + [""]
    if data["parameters"]:
        out += ["## Workbook controls", "", "Parameters are controls, not dataset columns.", ""]
        out += ["- " + md(item["caption"] or item["name"]) + ": " + ", ".join(md(member) for member in item["members"])
                for item in data["parameters"]] + [""]
    if internals:
        out += ["## Tableau internal metadata", "", "These reserved table records are retained separately from business fields.", ""]
        out += ["- " + md(source["caption"] or source["name"]) + ": " + md(field["caption"] or field["name"])
                for source, field in internals] + [""]
    if data["extraction_warnings"]:
        out += ["## Extraction limitations", ""] + ["- " + md(item) for item in data["extraction_warnings"]] + [""]
    out += ["## Structured source", "",
            "This dictionary covers workbook metadata. Dataset values, keys, joins, and grain were not verified.", "",
            "Technical IDs, original descriptions/formulas, workbook aggregation settings, native type codes, evidence, and confirmation attribution remain in the YAML.", "",
            f"YAML: {md(path.name)}; schema: {data['schema_version']}; revision: {data['revision']}.",
            f"Dictionary SHA-256: {sha256(path)}",
            f"Workbook SHA-256: {data['source']['workbook_sha256']}",
            "Source facts: " + md(data["source"]["facts_path"]),
            "Updated: " + md(data["updated_at"]), ""]
    return "\n".join(out)
