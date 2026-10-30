#!/usr/bin/env python3
"""Extract deterministic facts from an Oracle BI Publisher data model export.

Emits schema-version-2 model-facts.yaml with a provenance block, a static
``model`` facet, and an extraction ``run`` facet. The output is validated
against references/model-facts.schema.json before it is written.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET


SCHEMA_VERSION = 2
MODEL_FACET_VERSION = 1
RUN_FACET_VERSION = 1
EXTRACTOR_VERSION = "dia-data-model-intake 2.0.0"

WARNING_SEVERITIES = ("info", "warning", "error")

WARNING_CODES = (
    "AMBIGUOUS_ALIAS_NO_AS",
    "CTE_PARSE_FALLBACK",
    "DATASET_NO_SQL",
    "NO_DATA_SETS",
    "NO_TOP_LEVEL_SELECT",
    "SELECT_ITEM_NO_ALIAS",
    "SOURCE_FILE_UNAVAILABLE",
)


def add_warning(warnings, code, severity, message, dataset=None, query=None,
                item_index=None):
    """Append one coded warning object with a stable field order."""
    warnings.append({
        "code": code,
        "dataset": dataset,
        "query": query,
        "item_index": item_index,
        "severity": severity,
        "message": message,
    })


class ExtractionError(Exception):
    """Raised when the input cannot be parsed deterministically."""


def is_word_char(char: str) -> bool:
    return char.isalnum() or char in "_$#"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_children(element, name):
    return [child for child in element if local_name(child.tag) == name]


def find_first(element, name):
    children = find_children(element, name)
    return children[0] if children else None


# ---------------------------------------------------------------------------
# SQL scanning primitives. Every transform below preserves string length so
# positions computed on one view stay valid on every other view.
# ---------------------------------------------------------------------------


def split_comments(sql: str):
    """Strip comments while preserving offsets.

    Returns (code, comments) where code has each comment replaced by spaces and
    comments is a list of (position, kind, text) in source order.
    """
    code_chars: list[str] = []
    comments: list[tuple[int, str, str]] = []
    i = 0
    length = len(sql)
    while i < length:
        char = sql[i]
        if char == "'":
            j = i + 1
            while j < length:
                if sql[j] == "'" and j + 1 < length and sql[j + 1] == "'":
                    j += 2
                elif sql[j] == "'":
                    break
                else:
                    j += 1
            end = min(j, length - 1)
            code_chars.append(sql[i : end + 1])
            i = end + 1
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            end = length if end == -1 else end + 2
            comments.append((i, "block", sql[i + 2 : end - 2].strip()))
            code_chars.append(" " * (end - i))
            i = end
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            end = length if end == -1 else end
            comments.append((i, "line", sql[i + 2 : end].strip()))
            code_chars.append(" " * (end - i))
            i = end
        else:
            code_chars.append(char)
            i += 1
    return "".join(code_chars), comments


def mask_strings(code: str) -> str:
    """Replace string literal contents with spaces, preserving length."""
    out: list[str] = []
    i = 0
    length = len(code)
    while i < length:
        char = code[i]
        if char == "'":
            j = i + 1
            while j < length:
                if code[j] == "'" and j + 1 < length and code[j + 1] == "'":
                    j += 2
                elif code[j] == "'":
                    break
                else:
                    j += 1
            end = min(j, length - 1)
            out.append("'" + " " * (end - i - 1) + "'")
            i = end + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def find_balanced(text: str, open_index: int) -> int:
    """Return the index of the close paren matching text[open_index], or -1."""
    depth = 0
    for i in range(open_index, len(text)):
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def find_top_level(text: str, pattern) -> int:
    """Find the first pattern match outside parentheses, or -1."""
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "(":
            close = find_balanced(text, i)
            if close == -1:
                return -1
            i = close + 1
            continue
        if char == ")":
            return -1
        if i == 0 or not is_word_char(text[i - 1]):
            match = pattern.match(text, i)
            if match:
                return match.start()
        i += 1
    return -1


CLAUSE_STOP_WORDS = {
    "CROSS", "FULL", "GROUP", "HAVING", "INNER", "INTERSECT", "JOIN", "LEFT",
    "MINUS", "MODEL", "ORDER", "OUTER", "RIGHT", "UNION", "WHERE", "WITH",
}


def find_clause_end(text: str, start: int) -> int:
    """Return the index where the current SQL clause ends."""
    i = start
    length = len(text)
    while i < length:
        char = text[i]
        if char == "(":
            close = find_balanced(text, i)
            if close == -1:
                return length
            i = close + 1
            continue
        if char == ")":
            return i
        if (char.isalpha() or char == "_") and (i == 0 or not is_word_char(text[i - 1])):
            j = i
            while j < length and is_word_char(text[j]):
                j += 1
            word = text[i:j].upper()
            if word in CLAUSE_STOP_WORDS:
                return i
            i = j
            continue
        i += 1
    return length


RESERVED_ALIAS_WORDS = {
    "AND", "AS", "CROSS", "ELSE", "END", "FOR", "FROM", "FULL", "GROUP",
    "HAVING", "INNER", "INTERSECT", "INTO", "JOIN", "LEFT", "MINUS", "NOT",
    "ON", "OR", "ORDER", "OUTER", "PARTITION", "RIGHT", "SELECT", "THEN",
    "UNION", "USING", "WHEN", "WHERE", "WITH",
}


TABLE_REF = r"[A-Za-z_][\w$#]*(?:\s*\.\s*[A-Za-z_][\w$#]*)?"


def _safe_alias(candidate):
    if candidate is None:
        return None
    if candidate.upper() in RESERVED_ALIAS_WORDS:
        return None
    return candidate


def _neutralize_extract_from(scan: str) -> str:
    """Hide FROM inside EXTRACT(...) and IS DISTINCT FROM so table scans skip them."""
    scan = re.sub(r"(EXTRACT\s*\(\s*[A-Za-z_]\w*\s+)FROM\b", r"\1FROM_", scan, flags=re.I)
    scan = re.sub(r"\bIS\s+DISTINCT\s+FROM\b", "IS DISTINCT FROM_", scan, flags=re.I)
    return scan


def extract_source_tables(scan: str):
    """Collect FROM and JOIN table references, including comma-join sources."""
    tables = []
    from_re = re.compile(r"\bFROM\s+(" + TABLE_REF + r")\s*([A-Za-z_][\w$#]*)?", re.I)
    for match in from_re.finditer(scan):
        alias = _safe_alias(match.group(2))
        tables.append({
            "table": re.sub(r"\s+", "", match.group(1)),
            "alias": alias,
        })
        if alias is None and match.group(2) is not None:
            cursor = match.start(2)
        elif alias is None:
            cursor = match.end(1)
        else:
            cursor = match.end()
        while cursor < len(scan):
            stop = find_clause_end(scan, cursor)
            segment = scan[cursor:stop]
            comma = segment.find(",")
            if comma == -1:
                break
            rest = segment[comma + 1 :].lstrip()
            name_match = re.match(r"(" + TABLE_REF + r")\s*([A-Za-z_][\w$#]*)?", rest)
            if not name_match:
                break
            tables.append({
                "table": re.sub(r"\s+", "", name_match.group(1)),
                "alias": _safe_alias(name_match.group(2)),
            })
            cursor = cursor + comma + 1 + name_match.end()
    join_re = re.compile(r"\bJOIN\s+(" + TABLE_REF + r")\s*([A-Za-z_][\w$#]*)?", re.I)
    for match in join_re.finditer(scan):
        tables.append({
            "table": re.sub(r"\s+", "", match.group(1)),
            "alias": _safe_alias(match.group(2)),
        })
    return tables


JOIN_HEADER_RE = re.compile(
    r"\b((?:LEFT|RIGHT|FULL)\s+(?:OUTER\s+)?JOIN|INNER\s+JOIN|CROSS\s+JOIN|"
    r"NATURAL\s+(?:LEFT\s+|RIGHT\s+|INNER\s+)?JOIN|JOIN)\s+(" + TABLE_REF
    + r")\s*([A-Za-z_][\w$#]*)?",
    re.I,
)


def extract_joins(scan: str):
    """Collect join type, target table, alias, and ON/USING condition."""
    joins = []
    for match in JOIN_HEADER_RE.finditer(scan):
        condition = None
        cursor = match.end()
        while cursor < len(scan) and scan[cursor].isspace():
            cursor += 1
        on_match = re.match(r"ON\b", scan[cursor:], re.I)
        using_match = re.match(r"USING\b", scan[cursor:], re.I)
        if on_match:
            start = cursor + on_match.end()
            end = find_clause_end(scan, start)
            condition = scan[start:end].strip()
        elif using_match:
            start = cursor + using_match.end()
            end = find_clause_end(scan, start)
            condition = "USING" + scan[start:end].strip()
        joins.append({
            "type": re.sub(r"\s+", " ", match.group(1)).upper(),
            "table": re.sub(r"\s+", "", match.group(2)),
            "alias": _safe_alias(match.group(3)),
            "condition": re.sub(r"\s+", " ", condition) if condition else None,
        })
    return joins


def split_top_level(text: str, separator: str = ","):
    """Split text on a separator that sits outside parentheses."""
    parts = []
    depth = 0
    start = 0
    for i, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append((start, i))
            start = i + 1
    parts.append((start, len(text)))
    return parts


AS_ALIAS_RE = re.compile(r"\s*\bAS\s+([A-Za-z_][\w$#]*)\s*$", re.I)
IMPLICIT_ALIAS_RE = re.compile(r"^(?:[A-Za-z_][\w$#]*\s*\.\s*)?([A-Za-z_][\w$#]*)$")
END_TRAILING_ALIAS_RE = re.compile(r"^(.*\bEND)\s+([A-Za-z_][\w$#]*)$", re.I | re.S)


def extract_select_aliases(
    masked_body: str, code_body: str, warnings, dataset_name: str, body_name: str,
    confirmed_columns=None,
):
    """List the outer SELECT items with their output names and expressions."""
    select_pos = find_top_level(masked_body, re.compile(r"SELECT\b", re.I))
    if select_pos == -1:
        add_warning(
            warnings, "NO_TOP_LEVEL_SELECT", "warning",
            "no top-level SELECT clause found", dataset=dataset_name, query=body_name,
        )
        return []
    keyword_match = re.compile(
        r"SELECT\s+(DISTINCT\s+|ALL\s+)?", re.I
    ).match(masked_body, select_pos)
    select_start = keyword_match.end() if keyword_match else select_pos + 6
    from_pos = find_top_level(masked_body[select_pos:], re.compile(r"FROM\b", re.I))
    select_end = len(masked_body) if from_pos == -1 else select_pos + from_pos
    select_masked = masked_body[select_start:select_end]
    select_code = code_body[select_start:select_end]
    aliases = []
    for item_index, (start, end) in enumerate(split_top_level(select_masked)):
        item_masked = select_masked[start:end].strip()
        item_code = select_code[start:end].strip()
        if not item_masked:
            continue
        as_match = AS_ALIAS_RE.search(item_masked)
        if as_match:
            aliases.append({
                "name": as_match.group(1).lower(),
                "expression": item_code[: as_match.start()].strip(),
            })
            continue
        if item_masked == "*":
            aliases.append({"name": "*", "expression": "*"})
            continue
        implicit_match = IMPLICIT_ALIAS_RE.match(item_masked)
        if implicit_match:
            aliases.append({"name": implicit_match.group(1).lower(), "expression": item_code})
            continue
        end_match = END_TRAILING_ALIAS_RE.search(item_masked)
        if end_match:
            candidate = end_match.group(2)
            if candidate.upper() not in RESERVED_ALIAS_WORDS:
                confirmed = bool(confirmed_columns) and candidate.lower() in confirmed_columns
                if confirmed:
                    aliases.append({
                        "name": candidate.lower(),
                        "expression": item_code[: end_match.end(1)].strip(),
                    })
                    add_warning(
                        warnings, "AMBIGUOUS_ALIAS_NO_AS", "info",
                        f"select item alias '{candidate}' appears after END without AS; "
                        "bound from the output structure",
                        dataset=dataset_name, query=body_name, item_index=item_index,
                    )
                    continue
        aliases.append({"name": None, "expression": item_code})
        add_warning(
            warnings, "SELECT_ITEM_NO_ALIAS", "warning",
            "select item has no derivable column name",
            dataset=dataset_name, query=body_name, item_index=item_index,
        )
    return aliases


def find_case_spans(masked: str):
    """Return (start, end) spans for every CASE expression, nested or not."""
    tokens = [(m.start(), "CASE") for m in re.finditer(r"\bCASE\b", masked, re.I)]
    tokens += [(m.start(), "END") for m in re.finditer(r"\bEND\b", masked, re.I)]
    tokens.sort()
    stack = []
    spans = []
    for position, kind in tokens:
        if kind == "CASE":
            stack.append(position)
        elif stack:
            spans.append((stack.pop(), position))
    return spans


def extract_case_mappings(masked_body: str, code_body: str):
    """Capture WHEN/THEN/ELSE branches of each CASE with real string values."""
    spans = find_case_spans(masked_body)
    mappings = []
    for start, end in spans:
        nested = [s for s in spans if s[0] > start and s[1] < end]

        def immediate(word):
            found = []
            for m in re.finditer(rf"\b{word}\b", masked_body[start:end], re.I):
                position = start + m.start()
                if any(ns <= position <= ne for ns, ne in nested):
                    continue
                found.append((position, start + m.end()))
            return found

        whens = immediate("WHEN")
        thens = immediate("THEN")
        elses = immediate("ELSE")
        if not whens or not thens:
            continue
        operand = code_body[start + 4 : whens[0][0]].strip()
        pairs = []
        for _index, (when_start, when_end) in enumerate(whens):
            matching_then = min((t for t in thens if t[0] > when_end), default=None)
            if matching_then is None:
                continue
            then_start, then_end = matching_then
            next_starts = [w[0] for w in whens if w[0] > then_end]
            next_starts += [e[0] for e in elses if e[0] > then_end]
            value_end = min(next_starts, default=end)
            pairs.append({
                "when": re.sub(r"\s+", " ", code_body[when_end:then_start].strip()),
                "then": re.sub(r"\s+", " ", code_body[then_end:value_end].strip()),
            })
        else_value = None
        if elses:
            else_start, else_end = elses[0]
            else_value = re.sub(r"\s+", " ", code_body[else_end:end].strip())
        mappings.append({"operand": operand or None, "whens": pairs, "else": else_value})
    return mappings


WINDOW_FUNCTION_NAMES = [
    "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "LAG", "LEAD", "FIRST_VALUE",
    "LAST_VALUE", "LISTAGG", "SUM", "COUNT", "AVG", "MIN", "MAX", "STDDEV",
    "VARIANCE", "MEDIAN",
]


def detect_features(masked_body: str):
    """Record query shapes that matter for documentation."""
    features = []
    select_match = re.compile(r"\bSELECT\s+(DISTINCT\s+)?", re.I).search(masked_body)
    if select_match and select_match.group(1):
        features.append("distinct")
    if re.search(r"\bGROUP\s+BY\b", masked_body, re.I):
        features.append("group_by")
    if re.search(r"\bROWNUM\b", masked_body, re.I):
        features.append("rownum")
    windows = []
    for name in WINDOW_FUNCTION_NAMES:
        pattern = re.compile(rf"\b{name}\s*\(", re.I)
        for match in pattern.finditer(masked_body):
            close = find_balanced(masked_body, match.end() - 1)
            if close == -1:
                continue
            rest = masked_body[close + 1 : close + 12].lstrip().upper()
            if rest.startswith("OVER"):
                windows.append(name)
                break
    if windows:
        features.append("window_functions:" + ",".join(sorted(set(windows))))
    set_ops = []
    for operator in ("UNION ALL", "UNION", "INTERSECT", "MINUS"):
        if re.search(rf"\b{operator}\b", masked_body, re.I):
            set_ops.append(operator)
    if set_ops:
        features.append("set_operators:" + ",".join(set_ops))
    return features


def extract_clauses(masked_body: str, code_body: str):
    """Capture the outer WHERE, GROUP BY, HAVING, and ORDER BY clause text."""
    clauses = {}
    for key, pattern, keyword_length in (
        ("where", re.compile(r"WHERE\b", re.I), 5),
        ("group_by", re.compile(r"GROUP\s+BY\b", re.I), 8),
        ("having", re.compile(r"HAVING\b", re.I), 6),
        ("order_by", re.compile(r"ORDER\s+BY\b", re.I), 8),
    ):
        pos = find_top_level(masked_body, pattern)
        if pos == -1:
            clauses[key] = None
            continue
        end = find_clause_end(masked_body, pos + keyword_length)
        clauses[key] = code_body[pos + keyword_length : end].strip()
    return clauses


WITH_RE = re.compile(r"\bWITH\b", re.I)
CTE_NAME_RE = re.compile(r"\s*([A-Za-z_][\w$#]*)")
AS_RE = re.compile(r"\s+AS\s*", re.I)


def parse_ctes(masked: str):
    """Split a WITH query into body spans and the main query.

    Returns (bodies, with_position) where each body records its definition and
    body spans. Spans use indices that are valid on every length-preserving
    view of the SQL, including the original text.
    """
    match = WITH_RE.search(masked)
    if not match or masked[: match.start()].strip():
        return [], -1
    with_pos = match.start()
    pos = match.end()
    bodies = []
    while True:
        name_match = CTE_NAME_RE.match(masked, pos)
        if not name_match:
            raise ExtractionError("could not parse a CTE name after WITH")
        name = name_match.group(1)
        def_start = name_match.start(1)
        pos = name_match.end()
        if pos < len(masked) and masked[pos] == "(":
            close = find_balanced(masked, pos)
            if close == -1:
                raise ExtractionError(f"CTE {name} has an unbalanced column list")
            pos = close + 1
        as_match = AS_RE.match(masked, pos)
        if not as_match:
            raise ExtractionError(f"could not find AS for CTE {name}")
        pos = as_match.end()
        while pos < len(masked) and masked[pos].isspace():
            pos += 1
        if pos >= len(masked) or masked[pos] != "(":
            raise ExtractionError(f"CTE {name} does not open a parenthesized query")
        close = find_balanced(masked, pos)
        if close == -1:
            raise ExtractionError(f"CTE {name} has unbalanced parentheses")
        bodies.append({
            "name": name,
            "kind": "cte",
            "def_start": def_start,
            "body_start": pos + 1,
            "body_end": close,
        })
        pos = close + 1
        while pos < len(masked) and masked[pos].isspace():
            pos += 1
        if pos < len(masked) and masked[pos] == ",":
            pos += 1
            continue
        break
    if masked[pos:].strip():
        bodies.append({
            "name": "main",
            "kind": "main",
            "def_start": pos,
            "body_start": pos,
            "body_end": len(masked),
        })
    return bodies, with_pos


def analyze_body(masked_body, code_body, dataset_name, body_name, warnings,
                 confirmed_columns=None):
    scan = _neutralize_extract_from(masked_body)
    return {
        "source_tables": extract_source_tables(scan),
        "joins": extract_joins(scan),
        "select_aliases": extract_select_aliases(
            masked_body, code_body, warnings, dataset_name, body_name, confirmed_columns,
        ),
        "case_mappings": extract_case_mappings(masked_body, code_body),
        "features": detect_features(masked_body),
        "clauses": extract_clauses(masked_body, code_body),
    }


def analyze_dataset_sql(sql: str, dataset_name: str, warnings,
                        declared_parameters=None, confirmed_columns=None):
    """Extract the full fact structure for one dataset SQL statement."""
    code, comments = split_comments(sql)
    masked = mask_strings(code)
    sql_parameters = []
    if declared_parameters:
        for match in re.finditer(r":([A-Za-z_][\w$#]*)", masked):
            token = match.group(1).lower()
            original = declared_parameters.get(token)
            if original and original not in sql_parameters:
                sql_parameters.append(original)
    try:
        bodies, with_pos = parse_ctes(masked)
    except ExtractionError as exc:
        add_warning(
            warnings, "CTE_PARSE_FALLBACK", "warning",
            f"{exc}; treating the SQL as one query", dataset=dataset_name,
        )
        bodies = [{
            "name": "main", "kind": "main", "def_start": 0,
            "body_start": 0, "body_end": len(masked),
        }]
        with_pos = -1

    assigned = {body["name"]: [] for body in bodies}
    header_comments = []
    for position, _kind, text in comments:
        placed = False
        for body in bodies:
            if body["body_start"] <= position <= body["body_end"]:
                assigned[body["name"]].append(text)
                placed = True
                break
        if placed:
            continue
        if with_pos != -1 and position < with_pos:
            header_comments.append(text)
            continue
        next_body = next((b for b in bodies if b["def_start"] > position), None)
        if next_body is not None:
            assigned[next_body["name"]].append(text)
        elif bodies:
            assigned[bodies[-1]["name"]].append(text)

    cte_names = {body["name"].lower() for body in bodies if body["kind"] == "cte"}
    analyzed = []
    for body in bodies:
        start, end = body["body_start"], body["body_end"]
        analysis = analyze_body(
            masked[start:end], code[start:end], dataset_name, body["name"], warnings,
            confirmed_columns,
        )
        analysis["name"] = body["name"]
        analysis["sql"] = sql[start:end].strip()
        analysis["comments"] = assigned[body["name"]]
        analysis["cte_table_refs"] = [
            table for table in analysis["source_tables"]
            if table["table"].lower() in cte_names
        ]
        analysis["cte_references"] = sorted({
            table["table"] for table in analysis["source_tables"]
            if table["table"].lower() in cte_names
        })
        analysis["source_tables"] = [
            table for table in analysis["source_tables"]
            if table["table"].lower() not in cte_names
        ]
        analysis["joins"] = [
            join for join in analysis["joins"]
            if join["table"].lower() not in cte_names
        ]
        analyzed.append(analysis)

    table_index = {}
    for body_analysis in analyzed:
        for table in body_analysis["source_tables"]:
            key = table["table"].lower()
            entry = table_index.setdefault(key, {
                "table": table["table"], "aliases": [], "referenced_in": [],
            })
            if table.get("alias") and table["alias"] not in entry["aliases"]:
                entry["aliases"].append(table["alias"])
            if body_analysis["name"] not in entry["referenced_in"]:
                entry["referenced_in"].append(body_analysis["name"])

    ctes = [a for a in analyzed if a["name"] != "main"]
    main = next((a for a in analyzed if a["name"] == "main"), None)
    return {
        "author_comments": header_comments,
        "ctes": ctes,
        "main_query": main,
        "source_tables": list(table_index.values()),
        "sql_parameters": sql_parameters,
        "sql_summary": {
            "cte_count": len(ctes),
            "source_table_count": len(table_index),
            "join_count": sum(len(a["joins"]) for a in analyzed),
            "case_mapping_count": sum(len(a["case_mappings"]) for a in analyzed),
        },
    }


# ---------------------------------------------------------------------------
# Stable identity, lineage, and artifact assembly
# ---------------------------------------------------------------------------


def stable_hash(*parts):
    return hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()


def catalog_model_path(catalog_items):
    for item in catalog_items:
        item_name = str(item.get("ItemName", ""))
        if str(item.get("ItemType")) == "1" and item_name.lower().endswith(".xdm"):
            return item.get("OriginalPath")
    return None


def derive_model_id(catalog_path, model_name):
    identity = catalog_path if catalog_path else model_name
    normalized = " ".join(str(identity).split()).strip().lower()
    return "mdl_" + stable_hash(normalized)[:16]


def derive_dataset_id(model_id, dataset_name):
    return "ds_" + stable_hash(model_id, str(dataset_name).strip().lower())[:16]


def assign_column_ids(model_id, columns):
    used = {}
    identifiers = []
    for column in columns:
        proposed = "col_" + stable_hash(
            model_id,
            column.get("group") or "",
            column.get("name") or "",
            column.get("field_order"),
        )[:16]
        count = used.get(proposed, 0) + 1
        used[proposed] = count
        identifiers.append(proposed if count == 1 else f"{proposed}_{count}")
    return identifiers


def _top_level_case_span(masked_expression):
    """Return the (start, end) span of the single outermost CASE, or None."""
    spans = find_case_spans(masked_expression)
    if not spans:
        return None
    top = [
        (start, end)
        for start, end in spans
        if not any(other[0] < start and other[1] > end for other in spans)
    ]
    if len(top) != 1:
        return None
    return top[0]


def _case_else_branch(masked_expression):
    """Return the top-level ELSE branch text of the outermost CASE.

    Returns None when there is no single outermost CASE, and the empty string
    when the CASE has no ELSE branch.
    """
    span = _top_level_case_span(masked_expression)
    if span is None:
        return None
    start, end = span
    nested = [s for s in find_case_spans(masked_expression) if s[0] > start and s[1] < end]
    elses = []
    for match in re.finditer(r"\bELSE\b", masked_expression[start:end], re.I):
        position = start + match.start()
        if any(ns <= position <= ne for ns, ne in nested):
            continue
        elses.append((position, start + match.end()))
    if not elses:
        return ""
    return masked_expression[elses[0][1] : end].strip()


def derive_nullability(expression):
    """Return 'not_null' or 'nullable' when derivable from a CASE expression.

    A CASE with an ELSE branch that never yields NULL is not null; a CASE
    without ELSE yields NULL when no WHEN matches. Anything else stays unknown.
    """
    if not expression:
        return None
    masked_expression = mask_strings(expression)
    branch = _case_else_branch(masked_expression)
    if branch is None:
        return None
    if not branch:
        return "nullable"
    if re.search(r"\bNULL\b", branch, re.I) or find_case_spans(branch):
        return None
    return "not_null"


JOIN_PAIR_RE = re.compile(
    r"\b([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\s*=\s*"
    r"([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)"
)


def collect_join_keys(body, qualifier):
    keys = []
    for join in body.get("joins") or []:
        condition = join.get("condition")
        if not condition:
            continue
        target = (join.get("alias") or join.get("table") or "").lower()
        if condition.upper().startswith("USING"):
            if target == qualifier:
                for match in re.finditer(r"\(([A-Za-z_][\w$#]*)\)", condition):
                    key = f"{qualifier}.{match.group(1)}"
                    if key not in keys:
                        keys.append(key)
            continue
        for match in JOIN_PAIR_RE.finditer(condition):
            if match.group(1).lower() == qualifier:
                key = f"{match.group(1)}.{match.group(2)}"
            elif match.group(3).lower() == qualifier:
                key = f"{match.group(3)}.{match.group(4)}"
            else:
                continue
            if key not in keys:
                keys.append(key)
    return keys


def build_body_edges(dataset_name, dataset_id, body):
    alias_map = {}
    for entry in (body.get("source_tables") or []) + (body.get("cte_table_refs") or []):
        table = entry["table"]
        alias_map.setdefault(table.lower(), table)
        if entry.get("alias"):
            alias_map.setdefault(entry["alias"].lower(), table)
    edges = []
    for alias_entry in body.get("select_aliases") or []:
        name = alias_entry.get("name")
        expression = alias_entry.get("expression") or ""
        if not name or name == "*" or not expression or expression.strip() == "*":
            continue
        masked_expression = mask_strings(expression)
        referenced = []
        for match in re.finditer(
            r"\b([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)", masked_expression
        ):
            qualifier = match.group(1).lower()
            table = alias_map.get(qualifier)
            if table and all(qualifier != seen[0] for seen in referenced):
                referenced.append((qualifier, table))
        if not referenced:
            distinct_tables = sorted(set(alias_map.values()))
            if len(distinct_tables) == 1:
                qualifier = next(
                    key for key, value in alias_map.items() if value == distinct_tables[0]
                )
                referenced.append((qualifier, distinct_tables[0]))
        for qualifier, table in referenced:
            edges.append({
                "dataset": dataset_name,
                "dataset_id": dataset_id,
                "input_table": table,
                "query": body.get("name"),
                "output_column": name,
                "join_keys": collect_join_keys(body, qualifier),
            })
    return edges


def analyze_datasets(datasets, output_columns, parameters, warnings):
    """Attach SQL analysis to every dataset, using shared coded warnings."""
    declared = {}
    for parameter in parameters:
        name = parameter.get("name")
        if name:
            declared.setdefault(str(name).lower(), str(name))
    for dataset in datasets:
        name = dataset.get("name") or "unnamed"
        sql = dataset.get("sql") or ""
        if not sql:
            add_warning(warnings, "DATASET_NO_SQL", "warning", "dataset has no SQL", dataset=name)
            dataset.update({
                "author_comments": [], "ctes": [], "main_query": None,
                "source_tables": [], "sql_parameters": [], "sql_summary": {},
            })
            continue
        confirmed_columns = {
            str(column["name"]).lower()
            for column in output_columns
            if column.get("group_source") == name and column.get("name")
        }
        dataset.update(analyze_dataset_sql(
            sql, name, warnings, declared_parameters=declared,
            confirmed_columns=confirmed_columns,
        ))
    return datasets


def enrich_output_columns(output_columns, parameters, datasets, model_id):
    """Add IDs, derivable nullability, and parameter bindings in field order."""
    parameter_names = {
        str(parameter.get("name")).lower(): str(parameter.get("name"))
        for parameter in parameters
        if parameter.get("name")
    }
    dataset_bindings = {}
    alias_expressions = {}
    for dataset in datasets:
        name = dataset.get("name")
        bindings = [
            {"parameter": parameter, "via": "sql"}
            for parameter in dataset.get("sql_parameters") or []
        ]
        if bindings:
            dataset_bindings[name] = bindings
        main_query = dataset.get("main_query")
        if main_query:
            for alias_entry in main_query.get("select_aliases") or []:
                alias_name = alias_entry.get("name")
                if alias_name and alias_name != "*":
                    alias_expressions.setdefault(
                        (name, alias_name.lower()), alias_entry.get("expression")
                    )
    identifiers = assign_column_ids(model_id, output_columns)
    enriched = []
    for column, column_id in zip(output_columns, identifiers):
        group_source = column.get("group_source")
        nullability = None
        declared_attribute = column.pop("nullable_attribute", None)
        if declared_attribute is not None:
            text = str(declared_attribute).strip().lower()
            if text in ("true", "1", "yes"):
                nullability = "nullable"
            elif text in ("false", "0", "no"):
                nullability = "not_null"
        if nullability is None:
            expression = alias_expressions.get(
                (group_source, str(column.get("name") or "").lower())
            )
            if expression:
                nullability = derive_nullability(expression)
        bindings = []
        value = column.get("value")
        if value and str(value).lower() in parameter_names:
            bindings.append({
                "parameter": parameter_names[str(value).lower()],
                "via": "element_value",
            })
        for binding in dataset_bindings.get(group_source) or []:
            entry = {"parameter": binding["parameter"], "via": "group_sql"}
            if entry not in bindings:
                bindings.append(entry)
        rebuilt = {"name": column.get("name"), "id": column_id}
        for key, item in column.items():
            if key not in ("name", "nullable_attribute"):
                rebuilt[key] = item
        if nullability:
            rebuilt["nullability"] = nullability
        if bindings:
            rebuilt["parameter_bindings"] = bindings
        enriched.append(rebuilt)
    return enriched


def build_v2_artifact(*, model_name, description, xdm_version, default_data_source,
                      bi_publisher_build, author, modified_at, catalog_items,
                      data_properties, data_sources, parameters, value_sets,
                      datasets, output_columns, bursting, warnings, provenance,
                      migration=None):
    model_id = derive_model_id(catalog_model_path(catalog_items), model_name)
    datasets_out = []
    parse_status = []
    lineage = []
    for dataset in datasets:
        name = dataset.get("name") or "unnamed"
        dataset_id = derive_dataset_id(model_id, name)
        entry = {
            "id": dataset_id,
            "name": name,
            "type": dataset.get("type"),
            "data_source": dataset.get("data_source"),
        }
        if dataset.get("sql"):
            entry["content_hash"] = hashlib.sha256(
                dataset["sql"].encode("utf-8")
            ).hexdigest()
        entry["sql"] = dataset.get("sql") or ""
        for key in ("author_comments", "ctes", "main_query", "source_tables", "sql_summary"):
            if key in ("ctes", "main_query"):
                entry[key] = copy.deepcopy(dataset.get(key))
                bodies = entry[key] if isinstance(entry[key], list) else (
                    [entry[key]] if entry[key] else []
                )
                for body in bodies:
                    body.pop("cte_table_refs", None)
            else:
                entry[key] = dataset.get(key)
        sql_parameters = dataset.get("sql_parameters") or []
        if sql_parameters:
            entry["parameter_bindings"] = [
                {"parameter": parameter, "via": "sql"} for parameter in sql_parameters
            ]
        datasets_out.append(entry)
        warning_count = sum(
            1 for warning in warnings
            if warning.get("dataset") == name
            and warning.get("severity") in ("warning", "error")
        )
        note_count = sum(
            1 for warning in warnings
            if warning.get("dataset") == name and warning.get("severity") == "info"
        )
        if not dataset.get("sql"):
            status = "no_sql"
        elif warning_count:
            status = "parsed_with_warnings"
        else:
            status = "parsed"
        parse_status.append({
            "dataset": name,
            "dataset_id": dataset_id,
            "status": status,
            "warning_count": warning_count,
            "note_count": note_count,
        })
        bodies = list(dataset.get("ctes") or [])
        if dataset.get("main_query"):
            bodies.append(dataset["main_query"])
        for body in bodies:
            lineage.extend(build_body_edges(name, dataset_id, body))
    columns_out = enrich_output_columns(
        [dict(column) for column in output_columns], parameters, datasets, model_id,
    )
    model = {
        "facet_version": MODEL_FACET_VERSION,
        "model_id": model_id,
        "name": model_name,
        "description": description,
        "xdm_version": xdm_version,
        "default_data_source": default_data_source,
        "bi_publisher_build": bi_publisher_build,
        "author": author,
        "modified_at": modified_at,
        "catalog_items": catalog_items,
        "data_properties": data_properties,
        "data_sources": data_sources,
        "parameters": parameters,
        "value_sets": value_sets,
        "datasets": datasets_out,
        "output_columns": columns_out,
        "lineage": lineage,
        "bursting": bursting,
    }
    run = {
        "facet_version": RUN_FACET_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "warnings": warnings,
        "parse_status": parse_status,
    }
    if migration is not None:
        run["migration"] = migration
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance,
        "model": model,
        "run": run,
    }


def load_schema():
    schema_path = (
        Path(__file__).resolve().parent.parent / "references" / "model-facts.schema.json"
    )
    if not schema_path.is_file():
        raise ExtractionError(f"the model-facts JSON Schema is missing: {schema_path}")
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExtractionError(f"the model-facts JSON Schema could not be read: {exc}")


def validate_artifact(facts):
    try:
        import schema_check
    except ImportError as exc:
        raise ExtractionError(f"the schema_check helper module is missing: {exc}")
    violations = schema_check.validate(facts, load_schema())
    if violations:
        details = "; ".join(
            f"{violation['path']}: {violation['message']}" for violation in violations
        )
        raise ExtractionError(f"the generated artifact failed schema validation: {details}")


# ---------------------------------------------------------------------------
# Container and XML parsing
# ---------------------------------------------------------------------------


ZLIB_SECOND_BYTES = (0x01, 0x5E, 0x9C, 0xDA)


def load_model_document(raw: bytes):
    """Return (xml_text, container_kind, container_bytes) for the input bytes."""
    if len(raw) >= 2 and raw[0] == 0x78 and raw[1] in ZLIB_SECOND_BYTES:
        try:
            decompressor = zlib.decompressobj()
            data = decompressor.decompress(raw) + decompressor.flush()
        except zlib.error as exc:
            raise ExtractionError(
                f"the file has a zlib header but could not be decompressed: {exc}"
            )
        marker = data.find(b"<dataModel")
        if marker == -1:
            raise ExtractionError(
                "the decompressed archive does not contain a dataModel XML document"
            )
        declaration = data.rfind(b"<?xml", 0, marker)
        start = declaration if declaration != -1 and marker - declaration < 200 else marker
        end = data.find(b"</dataModel>", marker)
        if end == -1:
            raise ExtractionError(
                "the decompressed archive has a dataModel element without an end tag"
            )
        xml_text = data[start : end + len(b"</dataModel>")].decode("utf-8", errors="replace")
        return xml_text, "zlib-archive", data
    text = raw.decode("utf-8", errors="replace")
    if "<dataModel" in text:
        return text, "xml-document", None
    raise ExtractionError(
        "the file is neither a zlib archive nor a dataModel XML document"
    )


def find_json_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_json_objects(text: str):
    objects = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            end = find_json_end(text, i)
            if end != -1:
                try:
                    value = json.loads(text[i : end + 1])
                    if isinstance(value, dict):
                        objects.append(value)
                except json.JSONDecodeError:
                    pass
                i = end + 1
                continue
        i += 1
    return objects


def parse_catalog_metadata(container_data):
    """Pull catalog item metadata out of a decompressed .xdm.catalog archive."""
    if container_data is None:
        return {"catalog_items": [], "model_name": None}
    text = container_data.decode("utf-8", errors="replace")
    objects = extract_json_objects(text)
    items = [obj for obj in objects if "ItemName" in obj]
    model_name = None
    for item in items:
        item_name = str(item.get("ItemName", ""))
        if str(item.get("ItemType")) == "1" and item_name.lower().endswith(".xdm"):
            model_name = item_name[:-4]
            break
    return {"catalog_items": items, "model_name": model_name}


def parse_parameter(parameter):
    entry = dict(parameter.attrib)
    for child in parameter:
        entry[local_name(child.tag)] = (child.text or "").strip()
    return entry


def parse_output_columns(root):
    columns = []
    for structure in root.iter():
        if local_name(structure.tag) != "dataStructure":
            continue
        for group in structure:
            if local_name(group.tag) != "group":
                continue
            for element in group:
                if local_name(element.tag) != "element":
                    continue
                attributes = dict(element.attrib)
                try:
                    field_order = int(attributes.get("fieldOrder"))
                except (TypeError, ValueError):
                    field_order = attributes.get("fieldOrder")
                columns.append({
                    "name": attributes.get("name"),
                    "value": attributes.get("value"),
                    "label": attributes.get("label"),
                    "data_type": attributes.get("dataType"),
                    "group": group.get("name"),
                    "group_source": group.get("source"),
                    "break_order": attributes.get("breakOrder"),
                    "format_mask": attributes.get("formatMask"),
                    "field_order": field_order,
                    "nullable_attribute": attributes.get("nullable")
                    or attributes.get("nullAllowed"),
                })
    return columns


def parse_data_model(xml_text, source_path, container, container_data, warnings,
                     source_sha256, extracted_at):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ExtractionError(f"the dataModel XML could not be parsed: {exc}")

    catalog = parse_catalog_metadata(container_data)
    model_name = catalog["model_name"] or source_path.stem

    description = ""
    description_element = find_first(root, "description")
    if description_element is not None and description_element.text:
        description = unquote(description_element.text.strip())

    properties = {}
    properties_element = find_first(root, "dataProperties")
    if properties_element is not None:
        for prop in find_children(properties_element, "property"):
            properties[prop.get("name")] = prop.get("value")

    parameters = []
    parameters_element = find_first(root, "parameters")
    if parameters_element is not None:
        for parameter in find_children(parameters_element, "parameter"):
            parameters.append(parse_parameter(parameter))

    value_sets = []
    value_sets_element = find_first(root, "valueSets")
    if value_sets_element is not None:
        for value_set in value_sets_element:
            entry = dict(value_set.attrib)
            for child in value_set:
                entry[local_name(child.tag)] = (child.text or "").strip()
            value_sets.append(entry)

    data_sources = []
    default_data_source = root.get("defaultDataSourceRef")
    if default_data_source:
        data_sources.append(default_data_source)

    output_columns = parse_output_columns(root)
    datasets = []
    data_sets_element = find_first(root, "dataSets")
    if data_sets_element is None:
        add_warning(
            warnings, "NO_DATA_SETS", "warning", "the data model has no dataSets element",
        )
    else:
        for data_set in find_children(data_sets_element, "dataSet"):
            name = data_set.get("name") or "unnamed"
            sql_element = find_first(data_set, "sql")
            sql = (sql_element.text or "").strip() if sql_element is not None else ""
            data_source = None
            if sql_element is not None:
                data_source = sql_element.get("dataSourceRef") or default_data_source
            if data_source and data_source not in data_sources:
                data_sources.append(data_source)
            dataset = {
                "name": name,
                "type": data_set.get("type"),
                "data_source": data_source,
                "sql": sql,
            }
            datasets.append(dataset)
    analyze_datasets(datasets, output_columns, parameters, warnings)

    bursts = []
    bursting_element = find_first(root, "bursting")
    if bursting_element is not None:
        for burst in find_children(bursting_element, "burst"):
            entry = dict(burst.attrib)
            entry["properties"] = {
                prop.get("name"): prop.get("value")
                for prop in burst.iter()
                if local_name(prop.tag) == "property"
            }
            sql_elements = [e for e in burst.iter() if local_name(e.tag) == "sql"]
            entry["sql"] = (sql_elements[0].text or "").strip() if sql_elements else None
            entry["data_source"] = (
                sql_elements[0].get("dataSourceRef") if sql_elements else None
            )
            bursts.append(entry)

    build = None
    author = None
    modified_at = None
    for item in catalog["catalog_items"]:
        props = item.get("WCProperties")
        if not isinstance(props, dict):
            continue
        build = build or props.get("Build")
        author = author or props.get("bip:AUTHOR")
        raw_modified = props.get("bip:MODIFIED")
        if raw_modified and modified_at is None:
            try:
                moment = datetime.fromtimestamp(int(raw_modified) / 1000, tz=timezone.utc)
                modified_at = moment.isoformat(timespec="seconds")
            except (ValueError, OverflowError, OSError):
                pass

    provenance = {
        "source_file": str(source_path),
        "source_sha256": source_sha256,
        "extracted_at": extracted_at,
        "extractor_version": EXTRACTOR_VERSION,
        "container": container,
    }
    return build_v2_artifact(
        model_name=model_name,
        description=description,
        xdm_version=root.get("version"),
        default_data_source=default_data_source,
        bi_publisher_build=build,
        author=author,
        modified_at=modified_at,
        catalog_items=catalog["catalog_items"],
        data_properties=properties,
        data_sources=data_sources,
        parameters=parameters,
        value_sets=value_sets,
        datasets=datasets,
        output_columns=output_columns,
        bursting=bursts,
        warnings=warnings,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# YAML emission (standard library only)
# ---------------------------------------------------------------------------


SAFE_SCALAR_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ ./()+,@\-]*")
BOOL_LIKE = {"true", "false", "null", "yes", "no", "on", "off", "~"}
INT_RE = re.compile(r"[-+]?\d+")
FLOAT_RE = re.compile(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?")


def is_safe_scalar(value: str) -> bool:
    if not value or value != value.strip():
        return False
    if SAFE_SCALAR_RE.fullmatch(value) is None:
        return False
    lowered = value.lower()
    if lowered in BOOL_LIKE:
        return False
    if INT_RE.fullmatch(value) or FLOAT_RE.fullmatch(value):
        return False
    return True


def quote_scalar(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    out = re.sub(r"[\x00-\x1f]", lambda m: "\\u%04x" % ord(m.group()), out)
    return "\"" + out + "\""


def render_scalar(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value if is_safe_scalar(value) else quote_scalar(value)
    raise TypeError(f"unsupported scalar type: {type(value)!r}")


def is_multiline(value) -> bool:
    return isinstance(value, str) and "\n" in value


def block_lines(value: str, indent: int):
    """Render a literal block scalar; tabs expand to spaces for YAML validity."""
    pad = " " * indent
    text = value.replace("\t", "    ")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    out = ["|-"]
    for line in lines:
        out.append(pad + line if line else "")
    return out


def render_dict(value: dict, indent: int):
    pad = " " * indent
    out = []
    for key, item in value.items():
        if isinstance(item, dict):
            if item:
                out.append(f"{pad}{key}:")
                out.extend(render_dict(item, indent + 2))
            else:
                out.append(f"{pad}{key}: {{}}")
        elif isinstance(item, list):
            if item:
                out.append(f"{pad}{key}:")
                out.extend(render_list(item, indent + 2))
            else:
                out.append(f"{pad}{key}: []")
        elif is_multiline(item):
            block = block_lines(item, indent + 2)
            out.append(f"{pad}{key}: {block[0]}")
            out.extend(block[1:])
        else:
            out.append(f"{pad}{key}: {render_scalar(item)}")
    return out


def render_list(value: list, indent: int):
    pad = " " * indent
    out = []
    for item in value:
        if isinstance(item, dict):
            if not item:
                out.append(f"{pad}- {{}}")
                continue
            item_lines = render_dict(item, indent + 2)
            out.append(f"{pad}- {item_lines[0][indent + 2:]}")
            out.extend(item_lines[1:])
        elif isinstance(item, list):
            out.append(f"{pad}-")
            out.extend(render_list(item, indent + 2))
        elif is_multiline(item):
            block = block_lines(item, indent + 2)
            out.append(f"{pad}- {block[0]}")
            out.extend(block[1:])
        else:
            out.append(f"{pad}- {render_scalar(item)}")
    return out


def render_yaml(value: dict) -> str:
    model_name = value.get("model", {}).get("name", "unknown model")
    header = [
        f"# model-facts for {model_name}",
        f"# Generated by {EXTRACTOR_VERSION}. Deterministic extraction; do not hand-edit.",
    ]
    return "\n".join(header + render_dict(value, 0)) + "\n"


# ---------------------------------------------------------------------------
# Command line entry point
# ---------------------------------------------------------------------------


def build_summary(facts: dict, output_path: Path):
    datasets = facts["model"]["datasets"]
    return {
        "schema_version": facts["schema_version"],
        "model": facts["model"]["name"],
        "model_id": facts["model"]["model_id"],
        "container": facts["provenance"]["container"],
        "output": str(output_path),
        "datasets": len(datasets),
        "ctes": sum(len(d.get("ctes", [])) for d in datasets),
        "source_tables": sum(len(d.get("source_tables", [])) for d in datasets),
        "output_columns": len(facts["model"]["output_columns"]),
        "parameters": len(facts["model"]["parameters"]),
        "lineage_edges": len(facts["model"]["lineage"]),
        "warnings": facts["run"]["warnings"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract deterministic facts from an Oracle BI Publisher data model.",
    )
    parser.add_argument("--input", required=True, help="absolute path to the data model file")
    parser.add_argument("--output", required=True, help="absolute path for model-facts.yaml")
    parser.add_argument(
        "--replace", action="store_true",
        help="replace the output file when it already exists",
    )
    args = parser.parse_args(argv)

    source = Path(args.input)
    output = Path(args.output)
    if not source.is_absolute() or not output.is_absolute():
        print("Error: --input and --output must be absolute paths.", file=sys.stderr)
        return 2
    if not source.is_file():
        print(f"Error: input is not a regular file: {source}", file=sys.stderr)
        return 1
    if output.exists() and not args.replace:
        print(
            f"Error: output already exists: {output}. Pass --replace to overwrite it.",
            file=sys.stderr,
        )
        return 1

    warnings = []
    try:
        raw = source.read_bytes()
        source_sha256 = hashlib.sha256(raw).hexdigest()
        xml_text, container, container_data = load_model_document(raw)
        extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        facts = parse_data_model(
            xml_text, source, container, container_data, warnings,
            source_sha256, extracted_at,
        )
        validate_artifact(facts)
    except ExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: could not read the input file: {exc}", file=sys.stderr)
        return 1

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_yaml(facts), encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write the output file: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(build_summary(facts, output), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
