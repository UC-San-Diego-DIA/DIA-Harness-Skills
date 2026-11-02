"""Declarative, metadata-grounded metric and analytical-question proposals.

These helpers never evaluate a formula or infer business approval from schema support.
The caller performs JSON schema validation before these cross-document checks.
"""

from __future__ import annotations

from datetime import datetime
import html
import re


def _seed(dictionary, dataset_id, document_type, collection):
    return {
        "schema_version": 1, "document_type": document_type,
        "dataset_id": dataset_id,
        "source_workbook_sha256": dictionary["source"]["workbook_sha256"],
        "status": "draft", "reviewed": False, collection: [],
    }


def seed_metrics(dictionary, model, glossary, dataset_id):
    """Create empty review slots. Candidate selection belongs to contextual review."""
    return _seed(dictionary, dataset_id, "metric_proposals", "metrics")


def seed_questions(dictionary, model, glossary, metrics, dataset_id):
    return _seed(dictionary, dataset_id, "analytical_questions", "questions")


def _fields(dictionary):
    return {f["id"]: f for ds in dictionary.get("datasources", [])
            for f in ds.get("fields", []) if f.get("category") not in ("tableau_internal", "internal")
            and not f.get("name", "").startswith("[__tableau_internal_object_id__]")}


def _term_ids(glossary):
    return {term["term_id"] for term in glossary.get("terms", [])}


def _base(data, dictionary, model, glossary):
    issues = []
    expected_hash = dictionary.get("source", {}).get("workbook_sha256")
    if not expected_hash or data.get("source_workbook_sha256") != expected_hash:
        issues.append({"path": "source_workbook_sha256", "message": "Workbook snapshot differs from the dictionary."})
    for name, other in (("model", model), ("glossary", glossary)):
        if other.get("source_workbook_sha256") != expected_hash:
            issues.append({"path": name + ".source_workbook_sha256", "message": "Workbook snapshot differs from the dictionary."})
        if other.get("dataset_id") != data.get("dataset_id"):
            issues.append({"path": name + ".dataset_id", "message": "Dataset identity differs from this document."})
    dictionary_id = dictionary.get("dataset_id")
    if dictionary_id is not None and dictionary_id != data.get("dataset_id"):
        issues.append({"path": "dataset_id", "message": "Dataset identity differs from the dictionary."})
    return issues


def _problem(issues, path, message):
    issues.append({"path": path, "message": message})


def _refs(values, known, path, issues):
    if len(values) != len(set(values)):
        _problem(issues, path, "Duplicate references are not allowed.")
    for index, value in enumerate(values):
        if value not in known:
            _problem(issues, f"{path}[{index}]", "Unknown reference: " + str(value))


def _review(item, path, issues):
    gates = item.get("approval_gates", [])
    ids = [gate.get("id") for gate in gates]
    if len(ids) != len(set(ids)):
        _problem(issues, path + ".approval_gates", "Gate IDs must be unique within the proposal.")
    for index, gate in enumerate(gates):
        if gate.get("resolved") and not gate.get("evidence"):
            _problem(issues, f"{path}.approval_gates[{index}]", "Resolved gates require explicit evidence.")
    unresolved = [gate for gate in gates if not gate.get("resolved")]
    if item.get("support") == "supported" and unresolved:
        _problem(issues, path + ".support", "Unresolved approval gates require conditional or unsupported support.")
    approval = item.get("approval")
    if item.get("status") == "approved":
        if unresolved:
            _problem(issues, path + ".status", "Unresolved gates prevent approval.")
        if not isinstance(approval, dict) or not all(approval.get(k) for k in ("by", "at", "evidence")):
            _problem(issues, path + ".approval", "Approval requires explicit attribution, timestamp, and evidence.")
        else:
            try:
                if datetime.fromisoformat(approval["at"]).utcoffset() is None:
                    raise ValueError("timezone missing")
            except (ValueError, TypeError):
                _problem(issues, path + ".approval.at", "Approval timestamp must include a timezone.")
    elif approval is not None:
        _problem(issues, path + ".approval", "A proposed item cannot carry an approval record.")
    if item.get("support") in ("conditional", "unsupported") and not unresolved:
        _problem(issues, path + ".approval_gates", "Conditional or unsupported proposals need explicit unresolved requirements.")
    if item.get("data_verification") != "not_tested":
        _problem(issues, path + ".data_verification", "Metadata review cannot certify data verification.")


def _ids(data, collection, suffix, issues):
    ids = set()
    prefix = data.get("dataset_id", "") + "." + suffix + "."
    for index, item in enumerate(data.get(collection, [])):
        value = item.get("id", "")
        if not value.startswith(prefix) or len(value) == len(prefix):
            _problem(issues, f"{collection}[{index}].id", "Use a stable dataset-scoped ID beginning " + prefix)
        if value in ids:
            _problem(issues, f"{collection}[{index}].id", "Duplicate item ID.")
        ids.add(value)


def validate_metrics(data, dictionary, model, glossary):
    issues = _base(data, dictionary, model, glossary)
    fields, terms = _fields(dictionary), _term_ids(glossary)
    grains = {grain["id"]: grain for grain in model.get("grains", [])}
    _ids(data, "metrics", "metric", issues)
    for index, item in enumerate(data.get("metrics", [])):
        path = f"metrics[{index}]"
        _review(item, path, issues)
        _refs(item.get("field_refs", []), fields, path + ".field_refs", issues)
        _refs(item.get("glossary_refs", []), terms, path + ".glossary_refs", issues)
        formula = item.get("formula", {})
        bindings = formula.get("bindings", [])
        symbols = [binding.get("symbol") for binding in bindings]
        if len(symbols) != len(set(symbols)):
            _problem(issues, path + ".formula.bindings", "Formula symbols must be unique.")
        expression = formula.get("expression", "")
        used = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", expression))
        if used != set(symbols):
            _problem(issues, path + ".formula.expression", "Every formula placeholder must match one explicit field binding and every binding must be used.")
        remainder = re.sub(r"\{[a-z][a-z0-9_]*\}", "", expression)
        allowed = {"SUM", "COUNT", "COUNTD", "AVG", "MIN", "MAX", "ABS", "NULLIF", "IFNULL", "DISTINCT"}
        if any(token.upper() not in allowed for token in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", remainder)) or re.search(r"[^\w\s\d.,()+*/%<>=!\-]", remainder):
            _problem(issues, path + ".formula.expression", "Use declarative arithmetic/aggregation with {symbol} field bindings; raw field names, SQL, and executable code are not allowed.")
        refs = [binding.get("field_id") for binding in bindings]
        date = item.get("date", {})
        if date.get("field_ref"):
            refs.append(date["field_ref"])
            if date["field_ref"] in fields and fields[date["field_ref"]].get("datatype") not in ("date", "datetime"):
                _problem(issues, path + ".date.field_ref", "Date basis requires a recorded date or datetime field.")
        refs += item.get("dimension_refs", [])
        refs += [entry.get("field_ref") for entry in item.get("filters", [])]
        _refs(list(dict.fromkeys(refs)), fields, path + ".formula/date/dimensions/filters", issues)
        if set(refs) != set(item.get("field_refs", [])):
            _problem(issues, path + ".field_refs", "Field references must exactly cover formula, date, dimension, and filter bindings.")
        if formula.get("grain_ref") is not None and formula.get("grain_ref") not in grains:
            _problem(issues, path + ".formula.grain_ref", "Unknown model grain reference.")
        if item.get("support") == "supported" and formula.get("grain_ref") is None:
            _problem(issues, path + ".formula.grain_ref", "Supported proposals require a recorded model grain reference.")
        elif item.get("support") == "supported" and formula.get("grain_ref") in grains and grains[formula["grain_ref"]].get("status") != "confirmed":
            _problem(issues, path + ".support", "An unconfirmed model grain requires conditional or unsupported support.")
    return issues


def validate_questions(data, dictionary, model, glossary, metrics):
    issues = _base(data, dictionary, model, glossary)
    for key in ("dataset_id", "source_workbook_sha256"):
        if metrics.get(key) != data.get(key):
            _problem(issues, "metrics." + key, "Metric proposals belong to a different dataset snapshot.")
    fields, terms = _fields(dictionary), _term_ids(glossary)
    known = {metric["id"]: metric for metric in metrics.get("metrics", [])}
    _ids(data, "questions", "question", issues)
    for index, item in enumerate(data.get("questions", [])):
        path = f"questions[{index}]"
        _review(item, path, issues)
        metric_refs = item.get("metric_refs", [])
        if not metric_refs:
            _problem(issues, path + ".metric_refs", "An analytical question must reference at least one metric proposal.")
        _refs(metric_refs, known, path + ".metric_refs", issues)
        _refs(item.get("field_refs", []), fields, path + ".field_refs", issues)
        _refs(item.get("dimension_refs", []), fields, path + ".dimension_refs", issues)
        _refs(item.get("glossary_refs", []), terms, path + ".glossary_refs", issues)
        required = set(item.get("dimension_refs", []))
        if item.get("date_field_ref"):
            required.add(item["date_field_ref"])
        for ref in metric_refs:
            if ref in known:
                required.update(known[ref].get("field_refs", []))
                if item.get("support") == "supported" and known[ref].get("support") != "supported":
                    _problem(issues, path + ".support", "Question cannot be supported while a referenced metric is conditional or unsupported.")
        if not required.issubset(set(item.get("field_refs", []))):
            _problem(issues, path + ".field_refs", "Include every referenced metric field, dimension, and date field.")
    return issues


def _text(value):
    text = html.escape(str(value).replace("\n", " ").replace("\r", " "), quote=True)
    return re.sub(r"([\\`*_{}\[\]#|!:])", r"\\\1", text)


def _list(lines, label, values):
    if values:
        lines.extend(["", label + ":", ""])
        lines.extend("- " + _text(value) for value in values)


def _intro(data, title):
    return ["# " + title, "", "Dataset: " + _text(data["dataset_id"]), "",
            "Draft metadata proposals. No values were calculated; data verification is not tested.",
            "Schema support and business approval are separate. Approval does not certify data correctness."]


def _finish_item(lines, item):
    _list(lines, "Assumptions", item.get("assumptions", []))
    _list(lines, "Approval gates", [gate["requirement"] + (" [resolved: " + gate["evidence"] + "]" if gate["resolved"] else " [unresolved]") for gate in item.get("approval_gates", [])])
    if item.get("approval"):
        record = item["approval"]
        lines.extend(["", "Approved by " + _text(record["by"]) + " at " + _text(record["at"]) + ". Evidence: " + _text(record["evidence"])])


def render_metrics(data):
    lines = _intro(data, "Metric proposals")
    if not data["metrics"]:
        lines.extend(["", "No metric candidates have been authored. Contextual review is required."])
    for item in data["metrics"]:
        lines.extend(["", "## " + _text(item["name"]), "", _text(item["description"]), "",
                      "ID: " + _text(item["id"]), "", "Approval: " + item["status"] + ". Schema support: " + item["support"] + ". Data verification: not tested.",
                      "", _text(item["support_rationale"]), "", "Formula to build: " + _text(item["formula"]["expression"]),
                      "", "Aggregation: " + _text(item["formula"]["aggregation"]), "", "Grain: " + _text(item["formula"]["grain_statement"]),
                      "", "Unit: " + _text(item["unit"]["label"]) + ". " + _text(item["unit"]["basis"]),
                      "", "Date: " + _text(item["date"]["basis"]) + "; period: " + _text(item["date"]["period"]) + "; timezone: " + _text(item["date"]["timezone"])])
        _list(lines, "Field bindings", [b["symbol"] + " = " + b["field_id"] for b in item["formula"]["bindings"]])
        _list(lines, "Dimension field IDs", item["dimension_refs"])
        _list(lines, "Filters to build", [f["field_ref"] + " " + f["operator"] + " " + f["value"] + ". " + f["rationale"] for f in item["filters"]])
        _finish_item(lines, item)
    return "\n".join(lines).rstrip() + "\n"


def render_questions(data):
    lines = _intro(data, "Analytical questions")
    if not data["questions"]:
        lines.extend(["", "No analytical questions have been authored. Contextual review is required."])
    for item in data["questions"]:
        lines.extend(["", "## " + _text(item["question"]), "", _text(item["rationale"]), "", "ID: " + _text(item["id"]), "",
                      "Approval: " + item["status"] + ". Schema support: " + item["support"] + ". Data verification: not tested.", "", _text(item["support_rationale"])])
        _list(lines, "Metric proposal IDs", item["metric_refs"])
        _list(lines, "Dimension field IDs", item["dimension_refs"])
        _list(lines, "Field IDs", item["field_refs"])
        if item.get("date_field_ref"):
            lines.extend(["", "Date field ID: " + _text(item["date_field_ref"])])
        _finish_item(lines, item)
    return "\n".join(lines).rstrip() + "\n"
