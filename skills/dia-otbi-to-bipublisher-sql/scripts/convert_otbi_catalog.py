#!/usr/bin/env python3
"""Convert one OTBI .catalog analysis into BI Publisher logical and physical SQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


SAW_NS = "com.siebel.analytics.web/report/v1.1"
SAWX_NS = "com.siebel.analytics.web/expression/v1.1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NS = {"saw": SAW_NS, "sawx": SAWX_NS, "xsi": XSI_NS}
PRESENTATION_REF = re.compile(r'"([^"]+)"\s*\.\s*"([^"]+)"')


class ConversionError(Exception):
    pass


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def safe_base_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "otbi_analysis"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def inflate_catalog(data: bytes) -> str:
    parts: list[str] = []
    offset = 0
    size = len(data)
    while offset + 2 < size:
        if data[offset] != 0x78:
            offset += 1
            continue
        try:
            inflater = zlib.decompressobj(-15)
            inflated = inflater.decompress(data[offset + 2 :])
        except zlib.error:
            offset += 1
            continue
        if b"<saw:report" in inflated:
            parts.append(inflated.decode("utf-8", errors="replace"))
            trailing = len(inflater.unused_data)
            offset = size - trailing
        else:
            offset += 1
    if not parts:
        raise ConversionError("No zlib stream containing an OTBI report XML document was found")
    return "\n".join(parts)


def report_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(r"<saw:report[ >]", text):
        start = match.start()
        end = text.find("</saw:report>", start)
        if end < 0:
            continue
        end += len("</saw:report>")
        fragment = text[start:end]
        blocks.append(re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", fragment))
    if not blocks:
        raise ConversionError("No complete saw:report XML document was found in the catalog")
    return blocks


def expression_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean_text("".join(element.itertext()))


def expression_type(element: ET.Element) -> str:
    return element.get(f"{{{XSI_NS}}}type", "").split(":", 1)[-1]


def is_literal(element: ET.Element) -> bool:
    return element.get(f"{{{XSI_NS}}}type", "").startswith("xsd:")


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_operator(element: ET.Element) -> str:
    return {
        "equal": "=",
        "notEqual": "<>",
        "greater": ">",
        "greaterOrEqual": ">=",
        "less": "<",
        "lessOrEqual": "<=",
        "like": "LIKE",
    }.get(element.get("op", ""), element.get("op", ""))


def normalize_presentation_table(value: object) -> str:
    normalized = clean_text(value).strip('"').strip()
    return re.sub(r"^\s*-\s*", "", normalized)


def render_value(element: ET.Element, parameterized: bool = False) -> str:
    if is_literal(element):
        raw_type = element.get(f"{{{XSI_NS}}}type", "")
        value = expression_text(element)
        if raw_type == "xsd:date":
            return f"DATE '{value}'"
        if raw_type in {"xsd:dateTime", "xsd:time"}:
            return f"TIMESTAMP '{value}'"
        if parameterized:
            return sql_literal(value)
        return sql_literal(value)
    return render_expression(element, parameterized=parameterized) or expression_text(element)


def render_expression(element: ET.Element | None, parameterized: bool = False) -> str | None:
    if element is None:
        return None
    name = expression_type(element)
    children = list(element)
    if name == "savedFilter":
        return None
    if name == "eval":
        variable = expression_text(element)
        default = element.get("default", "%")
        return f"@{{{variable}}}{{'{default}'}}"
    if name in {"sqlExpression", "columnExpression"}:
        if name == "columnExpression":
            nested = element.find(".//sawx:expr", NS)
            if nested is not None:
                return render_expression(nested, parameterized=parameterized)
        return expression_text(element)
    if name == "logical":
        operator = (element.get("op") or "and").upper()
        rendered = [render_expression(child, parameterized=parameterized) for child in children]
        rendered = [item for item in rendered if item]
        if not rendered:
            return None
        if operator == "NOT":
            return f"NOT ({rendered[0]})"
        if operator in {"AND", "OR"}:
            return "(" + f"\n  {operator} ".join(rendered) + ")"
        return "(" + f" {operator} ".join(rendered) + ")"
    if name == "comparison":
        if len(children) < 2:
            return expression_text(element) or None
        operator = sql_operator(element)
        left = render_value(children[0], parameterized=False)
        right = render_value(children[1], parameterized=parameterized)
        return f"{left} {operator} {right}"
    if name == "list":
        if not children:
            return None
        operator = element.get("op", "")
        left = render_value(children[0], parameterized=False)
        values = [render_value(value, parameterized=parameterized) for value in children[1:]]
        if operator in {"in", "notIn"}:
            keyword = "IN" if operator == "in" else "NOT IN"
            return f"{left} {keyword} ({', '.join(values)})"
        if operator in {"contains", "notContains", "startsWith"}:
            conditions = []
            for value in values:
                text_value = value.strip("'")
                if operator == "contains":
                    conditions.append(f"{left} LIKE {sql_literal('%' + text_value + '%')}")
                elif operator == "notContains":
                    conditions.append(f"{left} NOT LIKE {sql_literal('%' + text_value + '%')}")
                else:
                    conditions.append(f"{left} LIKE {sql_literal(text_value + '%')}")
            return "(" + " AND ".join(conditions) + ")"
    return expression_text(element) or None


def saved_filter_details(element: ET.Element | None) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    if element is None:
        return details
    for node in element.iter():
        if expression_type(node) == "savedFilter":
            details.append(
                {
                    "name": clean_text(node.get("name", "")),
                    "path": clean_text(node.get("path", "")),
                }
            )
    return details


def analysis_name(root: ET.Element, subject_area: str, index: int) -> str:
    for attribute in ("name", "id", "displayName"):
        value = clean_text(root.get(attribute) or "")
        if value:
            return value
    return f"{subject_area or 'OTBI Analysis'}_{index + 1:02d}"


def default_heading(expression: str) -> str:
    matches = PRESENTATION_REF.findall(expression)
    if matches:
        return matches[-1][1]
    matches = re.findall(r'"([^"]+)"', expression)
    return matches[-1] if matches else expression[:80]


def extract_report(block: str, index: int) -> dict[str, object]:
    root = ET.fromstring(block)
    criteria = root.find("saw:criteria", NS)
    if criteria is None:
        raise ConversionError("The catalog XML has no saw:criteria element")
    subject_area = clean_text(criteria.get("subjectArea", "")).strip('"')
    columns_node = criteria.find("saw:columns", NS)
    if columns_node is None:
        raise ConversionError("The catalog XML has no saw:columns element")

    columns: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for position, column in enumerate(columns_node.findall("saw:column", NS)):
        column_id = clean_text(column.get("columnID", f"column_{position}"))
        if column_id in seen_ids:
            continue
        seen_ids.add(column_id)
        expression_node = column.find("./saw:columnFormula/sawx:expr", NS)
        expression = expression_text(expression_node)
        if not expression:
            continue
        heading_node = column.find("./saw:columnHeading/saw:caption/saw:text", NS)
        table_heading_node = column.find("./saw:tableHeading/saw:caption/saw:text", NS)
        heading = clean_text(heading_node.text if heading_node is not None else "")
        table_heading = clean_text(table_heading_node.text if table_heading_node is not None else "")
        columns.append(
            {
                "column_id": column_id,
                "position": len(columns) + 1,
                "heading": heading or default_heading(expression),
                "table_heading": table_heading,
                "expression": expression,
                "presentation_table": matches[0][0] if (matches := PRESENTATION_REF.findall(expression)) else "",
                "presentation_column": matches[0][1] if (matches := PRESENTATION_REF.findall(expression)) else "",
            }
        )

    filter_node = criteria.find("./saw:filter/sawx:expr", NS)
    explicit_filter = render_expression(filter_node) or ""
    saved_filters = saved_filter_details(filter_node)
    sorts: list[dict[str, str]] = []
    for order_ref in criteria.findall(".//saw:columnOrderRef", NS):
        column_id = clean_text(order_ref.get("columnID", ""))
        direction = clean_text(order_ref.get("direction", "ascending")).lower()
        column = next((item for item in columns if item["column_id"] == column_id), None)
        if column:
            sorts.append(
                {
                    "column_id": column_id,
                    "heading": str(column["heading"]),
                    "expression": str(column["expression"]),
                    "direction": direction,
                }
            )

    return {
        "analysis": analysis_name(root, subject_area, index),
        "analysis_index": index + 1,
        "subject_area": subject_area,
        "columns": columns,
        "filter": {
            "explicit_sql": explicit_filter,
            "saved_filters": saved_filters,
            "raw_xml": ET.tostring(filter_node, encoding="unicode") if filter_node is not None else "",
        },
        "sorts": sorts,
        "prompts_present": root.find("saw:prompts", NS) is not None,
    }


def extract_catalog(path: Path) -> list[dict[str, object]]:
    text = inflate_catalog(path.read_bytes())
    return [extract_report(block, index) for index, block in enumerate(report_blocks(text))]


def column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref.upper())
    if not letters:
        return 0
    result = 0
    for letter in letters.group(0):
        result = result * 26 + ord(letter) - 64
    return result - 1


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value_node = cell.find(".//{*}v")
    inline_node = cell.find(".//{*}t")
    if (cell.get("t") or "") == "inlineStr" and inline_node is not None:
        return clean_text(inline_node.text)
    if value_node is None:
        return ""
    value = clean_text(value_node.text)
    if (cell.get("t") or "") == "s":
        try:
            return clean_text(shared_strings[int(value)])
        except (IndexError, ValueError):
            return value
    if (cell.get("t") or "") == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def read_sheet_rows(workbook_zip: zipfile.ZipFile, sheet_path: str) -> list[list[str]]:
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in workbook_zip.namelist():
        shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
        for item in shared_root:
            text = "".join(node.text or "" for node in item.iter() if local_name(node.tag) == "t")
            shared_strings.append(clean_text(text))
    sheet_root = ET.fromstring(workbook_zip.read(sheet_path))
    rows: dict[int, list[str]] = {}
    max_column = 0
    for row in sheet_root.iter():
        if local_name(row.tag) != "row":
            continue
        row_number = int(row.get("r", str(len(rows) + 1)))
        row_values: list[str] = []
        for cell in row:
            if local_name(cell.tag) != "c":
                continue
            ref = cell.get("r") or ""
            index = column_index(ref) if ref else len(row_values)
            while len(row_values) <= index:
                row_values.append("")
            row_values[index] = cell_value(cell, shared_strings)
            max_column = max(max_column, index + 1)
        rows[row_number] = row_values
    return [rows.get(number, [""] * max_column) for number in range(1, max(rows) + 1)]


def workbook_sheet_paths(workbook_zip: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
    relationships = {
        rel.get("Id", ""): rel.get("Target", "")
        for rel in rels_root
        if local_name(rel.tag) == "Relationship"
    }
    sheets: dict[str, str] = {}
    for sheet in workbook_root.iter():
        if local_name(sheet.tag) != "sheet":
            continue
        name = clean_text(sheet.get("name", ""))
        relationship_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = relationships.get(relationship_id, "")
        if not target:
            continue
        if target.startswith("/"):
            path = target[1:]
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        sheets[name] = path
    return sheets


def read_mapping_workbook(path: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(path) as archive:
            sheets = workbook_sheet_paths(archive)
            sheet_name = next(
                (name for name in sheets if name.lower() == "otbi subject areas"),
                next((name for name, _ in sheets.items() if "subject" in name.lower()), ""),
            )
            if not sheet_name:
                raise ConversionError("The mapping workbook has no OTBI Subject Areas sheet")
            rows = read_sheet_rows(archive, sheets[sheet_name])
            cover_rows: list[str] = []
            if "Cover Page" in sheets:
                for row in read_sheet_rows(archive, sheets["Cover Page"])[:20]:
                    cover_rows.extend(value for value in row if value)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as error:
        raise ConversionError(f"Could not read the mapping workbook: {error}") from error

    header_row_number = 0
    expected = {
        "SUBJECT_AREA",
        "PRESENTATION_TABLE",
        "PRESENTATION_COLUMN",
        "DATABASE_OBJECT",
        "DATABASE_COLUMN",
    }
    for row_number, row in enumerate(rows, start=1):
        if expected.issubset({clean_text(value).upper() for value in row}):
            header_row_number = row_number
            break
    if not header_row_number:
        raise ConversionError("The OTBI Subject Areas sheet does not contain the expected mapping headers")
    headers = [clean_text(value).upper() for value in rows[header_row_number - 1]]
    header_positions = {header: position for position, header in enumerate(headers) if header}
    mappings: list[dict[str, str]] = []
    for row_number, row in enumerate(rows[header_row_number:], start=header_row_number + 1):
        if not clean_text(row[header_positions["SUBJECT_AREA"]] if len(row) > header_positions["SUBJECT_AREA"] else ""):
            continue

        def value_for(header: str) -> str:
            position = header_positions[header]
            return clean_text(row[position]) if len(row) > position else ""

        mapping = {header: value_for(header) for header in header_positions}
        mapping["workbook_row"] = str(row_number)
        mappings.append(mapping)

    return {"mappings": mappings, "cover_text": cover_rows}


def normalize_parameter_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    if not normalized or normalized[0].isdigit():
        normalized = "P_" + (normalized or "PARAMETER")
    return "P_" + normalized


def infer_parameter_type(value: str, expression: str = "") -> str:
    if "AS DATE" in expression.upper():
        return "date"
    if re.fullmatch(r"-?\d{4}-\d{2}-\d{2}(?:[T ].*)?", value):
        return "date"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return "number"
    return "text"


def presentation_expression_column(expression: str) -> tuple[str, str]:
    matches = PRESENTATION_REF.findall(expression)
    if matches:
        return normalize_presentation_table(matches[-1][0]), matches[-1][1]
    matches = re.findall(r'"([^"]+)"', expression)
    if matches:
        return "", matches[-1]
    return "", ""


def mapping_for_expression(
    expression: str,
    subject_area: str,
    mappings: list[dict[str, str]],
) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    presentation_table, presentation_column = presentation_expression_column(expression)
    normalized_table = normalize_presentation_table(presentation_table)
    exact = [
        row
        for row in mappings
        if clean_text(row.get("SUBJECT_AREA", "")) == subject_area
        and clean_text(row.get("PRESENTATION_COLUMN", "")) == presentation_column
        and (not normalized_table or normalize_presentation_table(row.get("PRESENTATION_TABLE", "")) == normalized_table)
    ]
    if exact:
        with_database = [row for row in exact if row.get("DATABASE_OBJECT") and row.get("DATABASE_COLUMN")]
        if with_database:
            return with_database[0], exact
    return None, exact


def substitute_physical_references(
    expression: str,
    subject_area: str,
    mappings: list[dict[str, str]],
    selected_mappings: dict[str, dict[str, str]],
) -> tuple[str, dict[str, dict[str, str]]]:
    def replace(match: re.Match[str]) -> str:
        table, column = match.group(1), match.group(2)
        key = f"{table}|{column}"
        if key in selected_mappings:
            mapping = selected_mappings[key]
            return f"{mapping['DATABASE_OBJECT']}.{mapping['DATABASE_COLUMN']}"
        mapping, _ = mapping_for_expression(f'"{table}"."{column}"', subject_area, mappings)
        if mapping:
            selected_mappings[key] = mapping
            return f"{mapping['DATABASE_OBJECT']}.{mapping['DATABASE_COLUMN']}"
        return match.group(0)

    return PRESENTATION_REF.sub(replace, expression), selected_mappings


def collect_parameters(
    analysis: dict[str, object],
    subject_area: str,
    mappings: list[dict[str, str]],
) -> list[dict[str, object]]:
    parameters: list[dict[str, object]] = []
    parameter_names: set[str] = set()
    filter_node = None
    filter_xml = str(analysis["filter"]["raw_xml"])
    if filter_xml:
        filter_node = ET.fromstring(filter_xml)
    column_by_id = {str(column["column_id"]): column for column in analysis["columns"]}
    heading_by_expression = {str(column["expression"]): str(column["heading"]) for column in analysis["columns"]}

    def add_parameter(left_expression: str, operator: str, value: str, multi_select: bool) -> str | None:
        source_heading = heading_by_expression.get(left_expression, "")
        _, presentation_column = presentation_expression_column(left_expression)
        source = source_heading or presentation_column or left_expression
        variable_matches = re.findall(r"@{([^}]+)}", left_expression)
        if variable_matches:
            source = variable_matches[-1]
        name = normalize_parameter_name(source)
        if name in parameter_names:
            return name
        parameter_names.add(name)
        mapping, alternatives = mapping_for_expression(left_expression, subject_area, mappings)
        parameter: dict[str, object] = {
            "name": name,
            "source": source,
            "logical_expression": left_expression,
            "operator": operator,
            "original_value": value,
            "type": infer_parameter_type(value, left_expression),
            "required": True,
            "multi_select": multi_select,
            "database_mapping": mapping or {},
            "mapping_alternatives": alternatives,
        }
        parameters.append(parameter)
        return name

    def walk(element: ET.Element | None) -> None:
        if element is None:
            return
        name = expression_type(element)
        children = list(element)
        if name == "comparison" and len(children) >= 2:
            operator = element.get("op", "")
            if is_literal(children[1]):
                add_parameter(
                    expression_text(children[0]),
                    operator,
                    expression_text(children[1]),
                    False,
                )
            return
        if name == "list" and element.get("op") in {"in", "notIn"} and children:
            add_parameter(
                expression_text(children[0]),
                element.get("op", ""),
                ", ".join(expression_text(child) for child in children[1:]),
                True,
            )
            return
        for child in children:
            walk(child)

    walk(filter_node)
    return parameters


def parameter_token(parameter: dict[str, object]) -> str:
    if bool(parameter.get("multi_select")):
        return f"&{parameter['name']}"
    return f":{parameter['name']}"


def parameterize_expression(
    element: ET.Element | None,
    parameters: list[dict[str, object]],
) -> str | None:
    if element is None:
        return None
    name = expression_type(element)
    children = list(element)
    if name == "comparison" and len(children) >= 2:
        operator = sql_operator(element)
        if is_literal(children[1]):
            source_expression = expression_text(children[0])
            value = expression_text(children[1])
            match = next(
                (
                    parameter
                    for parameter in parameters
                    if parameter["logical_expression"] == source_expression
                    and parameter["original_value"] == value
                ),
                None,
            )
            if match:
                left = render_value(children[0])
                return f"{left} {operator} {parameter_token(match)}"
        left = render_value(children[0])
        right = render_value(children[1], parameterized=True)
        return f"{left} {operator} {right}"
    if name == "list" and element.get("op") in {"in", "notIn"} and children:
        source_expression = expression_text(children[0])
        value = ", ".join(expression_text(child) for child in children[1:])
        match = next(
            (
                parameter
                for parameter in parameters
                if parameter["logical_expression"] == source_expression
                and parameter["original_value"] == value
            ),
            None,
        )
        if match:
            left = render_value(children[0])
            keyword = "IN" if element.get("op") == "in" else "NOT IN"
            return f"{left} {keyword} ({parameter_token(match)})"
    rendered = [parameterize_expression(child, parameters) for child in children]
    rendered = [item for item in rendered if item]
    if not rendered:
        return None
    if name == "logical":
        operator = (element.get("op") or "and").upper()
        if operator == "NOT":
            return f"NOT ({rendered[0]})"
        if operator in {"AND", "OR"}:
            return "(" + f"\n  {operator} ".join(rendered) + ")"
        return "(" + f" {operator} ".join(rendered) + ")"
    return " ".join(rendered)


def logical_sql(
    analysis: dict[str, object],
    parameterized: bool,
    parameters: list[dict[str, object]],
) -> str:
    columns = analysis["columns"]
    lines = [
        "-- Logical SQL for the OTBI / Oracle BI Server.",
        f'-- Analysis: {analysis["analysis"]}',
        f'-- Subject area: "{analysis["subject_area"]}"',
        "SELECT",
    ]
    for column in columns:
        alias = safe_base_name(str(column["heading"])).replace("_", " ")
        lines.append(f"    {column['expression']} AS \"{alias}\",")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append(f'FROM "{analysis["subject_area"]}"')
    filter_xml = str(analysis["filter"]["raw_xml"])
    if filter_xml:
        filter_node = ET.fromstring(filter_xml)
        where = parameterize_expression(filter_node, parameters) if parameterized else str(analysis["filter"]["explicit_sql"])
        if where:
            lines.append("WHERE")
            lines.append(f"    {where}")
    for saved_filter in analysis["filter"]["saved_filters"]:
        lines.append(f"-- Saved filter: {saved_filter['name']} ({saved_filter['path']})")
    if analysis["sorts"]:
        order_items = [f"{item['expression']} {item['direction'].upper()}" for item in analysis["sorts"]]
        lines.append("ORDER BY")
        lines.append("    " + ", ".join(order_items))
    lines.append(";")
    return "\n".join(lines) + "\n"


def physical_sql(
    analysis: dict[str, object],
    subject_area: str,
    mappings: list[dict[str, str]],
    parameters: list[dict[str, object]],
    parameterized: bool,
) -> tuple[str, dict[str, dict[str, str]]]:
    selected_mappings: dict[str, dict[str, str]] = {}
    substituted_columns: list[dict[str, str]] = []
    for column in analysis["columns"]:
        substituted, selected_mappings = substitute_physical_references(
            str(column["expression"]),
            subject_area,
            mappings,
            selected_mappings,
        )
        if substituted == column["expression"]:
            raise ConversionError(
                f"No database mapping for presentation column \"{column['presentation_column']}\" "
                f"in subject area \"{subject_area}\""
            )
        substituted_columns.append(
            {
                "heading": str(column["heading"]),
                "logical_expression": str(column["expression"]),
                "physical_expression": substituted,
                "database_mapping": selected_mappings.get(
                    f"{column['presentation_table']}|{column['presentation_column']}", {}
                ),
            }
        )

    lines = [
        "-- Physical SQL for a BI Publisher SQL Query data set on the Fusion applications database.",
        f'-- Analysis: {analysis["analysis"]}',
        f'-- Subject area: "{analysis["subject_area"]}"',
        "SELECT",
    ]
    for column in substituted_columns:
        alias = safe_base_name(column["heading"]).replace("_", " ")
        lines.append(f"    {column['physical_expression']} AS \"{alias}\",")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    where_block: list[str] = []
    filter_xml = str(analysis["filter"]["raw_xml"])
    if filter_xml:
        filter_node = ET.fromstring(filter_xml)
        if parameterized:
            physical_filter = parameterize_expression(filter_node, parameters) or ""
        else:
            physical_filter = str(analysis["filter"]["explicit_sql"])
        physical_filter, selected_mappings = substitute_physical_references(
            physical_filter,
            subject_area,
            mappings,
            selected_mappings,
        )
        if physical_filter:
            where_block.extend(["WHERE", f"    {physical_filter}"])

    order_block: list[str] = []
    if analysis["sorts"]:
        order_items = []
        for sort in analysis["sorts"]:
            substituted, selected_mappings = substitute_physical_references(
                str(sort["expression"]),
                subject_area,
                mappings,
                selected_mappings,
            )
            order_items.append(f"{substituted} {sort['direction'].upper()}")
        order_block.extend(["ORDER BY", "    " + ", ".join(order_items)])

    tables = sorted(
        {
            mapping["DATABASE_OBJECT"]
            for mapping in selected_mappings.values()
            if mapping.get("DATABASE_OBJECT")
        }
    )
    if not tables:
        raise ConversionError("No physical database objects were mapped")
    lines.append("FROM " + ", ".join(tables))
    if len(tables) > 1:
        lines.append("-- VERIFY join conditions: the lineage workbook does not supply them.")
    lines.extend(where_block)
    lines.extend(order_block)
    lines.append(";")
    return "\n".join(lines) + "\n", selected_mappings


def lov_sql(parameter: dict[str, object]) -> str | None:
    mapping = parameter.get("database_mapping") or {}
    database_object = str(mapping.get("DATABASE_OBJECT", ""))
    database_column = str(mapping.get("DATABASE_COLUMN", ""))
    if not database_object or not database_column:
        return None
    parameter_name = str(parameter["name"])
    lines = [
        f"-- List of values for {parameter_name}.",
        "-- Configure this as a SQL Query list of values in BI Publisher.",
        "SELECT DISTINCT",
        f"    {database_object}.{database_column} AS PARAMETER_VALUE",
        f"FROM {database_object}",
        "ORDER BY PARAMETER_VALUE",
        ";",
    ]
    return "\n".join(lines) + "\n"


def unique_database_alternatives(alternatives: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for alternative in alternatives:
        key = (
            clean_text(alternative.get("DATABASE_OBJECT", "")).upper(),
            clean_text(alternative.get("DATABASE_COLUMN", "")).upper(),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(alternative)
    return unique


def workbook_release_token(cover_text: list[str], workbook_name: str) -> str:
    token_pattern = re.compile(r"(?:^|[^A-Za-z0-9])(2[0-9][A-D])(?:[^A-Za-z0-9]|$)")
    for value in cover_text:
        match = token_pattern.search(str(value))
        if match:
            return match.group(1)
    match = token_pattern.search(workbook_name)
    if match:
        return match.group(1)
    return "UNKNOWN"


def build_join_research_markdown(
    analysis_name: str,
    subject_area: str,
    selected_mappings: dict[str, dict[str, str]],
    parameters: list[dict[str, object]],
    workbook_path: Path,
    cover_text: list[str],
) -> str:
    tables: dict[str, dict[str, list[str]]] = {}
    for key, mapping in selected_mappings.items():
        table = clean_text(mapping.get("DATABASE_OBJECT", ""))
        column = clean_text(mapping.get("DATABASE_COLUMN", ""))
        if not table or not column:
            continue
        entry = tables.setdefault(table, {"columns": [], "vos": [], "rows": []})
        presentation_column = key.split("|", 1)[-1]
        entry["columns"].append(f"{column} <- {presentation_column}")
        vo_definition = clean_text(mapping.get("VO_DEFINITION", ""))
        if vo_definition and vo_definition not in entry["vos"]:
            entry["vos"].append(vo_definition)
        workbook_row = clean_text(mapping.get("workbook_row", ""))
        if workbook_row and workbook_row not in entry["rows"]:
            entry["rows"].append(workbook_row)

    table_names = sorted(tables)
    join_pairs = [
        (left, right)
        for position, left in enumerate(table_names)
        for right in table_names[position + 1 :]
    ]
    lov_tables: dict[str, list[str]] = {}
    for parameter in parameters:
        mapping = parameter.get("database_mapping") or {}
        table = clean_text(str(mapping.get("DATABASE_OBJECT", "")))
        if table and table not in tables:
            lov_tables.setdefault(table, []).append(str(parameter["name"]))

    lines = [
        f"# Join research worksheet - {analysis_name}",
        "",
        "The mapping workbook supplies field mappings but not join conditions.",
        "Complete this worksheet with official Oracle sources during the same run and",
        "report every source to the user. Keep `VERIFY` markers in the physical SQL",
        "until a join reaches `VERIFIED` status.",
        "",
        f"- Subject area: {subject_area}",
        f"- Mapping workbook: {workbook_path}",
        f"- Workbook release token: {workbook_release_token(cover_text, workbook_path.name)}",
        "- Live documentation release: (complete during this run)",
        "- Documentation library URL: (complete during this run)",
        "- Access date: (complete during this run)",
        f"- Physical tables: {len(table_names)}",
        f"- Join candidates: {len(join_pairs)}",
        "",
        "## Release check",
        "",
        "1. Open https://docs.oracle.com/en/cloud/saas/ and select the product family",
        "   for this subject area, such as Financials, Supply Chain Management, or",
        "   Project Portfolio Management.",
        "2. Record the current release shown by the documentation library, its URL, or",
        "   its page title. Resolve it fresh in every run; never reuse an earlier run.",
        "3. The mapping workbook remains the authority for field mappings. If the live",
        "   release is newer than the workbook release token, source join evidence from",
        "   the live release and note any table or column that changed.",
        "",
        "## Tables used by the physical SQL",
        "",
    ]
    if table_names:
        lines.append("Verify each table and its mapped columns against current-release documentation.")
        for table in table_names:
            entry = tables[table]
            lines.extend(
                [
                    "",
                    f"### {table}",
                    "",
                    f"- Mapped columns: {', '.join(entry['columns'])}",
                    f"- Workbook rows: {', '.join(entry['rows']) or 'not recorded'}",
                    f"- Workbook VO definitions: {'; '.join(entry['vos']) or 'none recorded'}",
                    "- Documentation URL: (complete)",
                    "- Documentation release: (complete)",
                    "- Access date: (complete)",
                    "- Verified in live release: (YES / NO / UNKNOWN)",
                    "- Notes: (complete)",
                ]
            )
    else:
        lines.append("No physical tables were mapped.")

    lines.extend(["", "## List-of-values tables", ""])
    if lov_tables:
        lines.append(
            "Parameter list-of-values queries are single-table. Verify them like the tables above; they add no joins."
        )
        for table in sorted(lov_tables):
            lines.extend(
                [
                    "",
                    f"### {table}",
                    "",
                    f"- Used by parameters: {', '.join(lov_tables[table])}",
                    "- Documentation URL: (complete)",
                    "- Documentation release: (complete)",
                    "- Access date: (complete)",
                    "- Verified in live release: (YES / NO / UNKNOWN)",
                ]
            )
    else:
        lines.append("No list-of-values tables exist outside the main query.")

    lines.extend(["", "## Join candidates", ""])
    if join_pairs:
        lines.extend(
            [
                "Research one block per candidate against official Oracle sources only.",
                "",
                "Evidence hierarchy, strongest first:",
                "",
                "1. A join condition stated in current-release official Oracle documentation.",
                "2. A relationship shown by the workbook's view-object definition; record the",
                "   workbook row as the source.",
                "3. A documented primary-key or foreign-key relationship in current-release",
                "   documentation.",
                "",
                "Column-name similarity alone is never evidence. Non-Oracle pages, AI",
                "summaries, and SQL execution are never evidence.",
                "",
            ]
        )
        for left, right in join_pairs:
            lines.extend(
                [
                    f"### {left} <-> {right}",
                    "",
                    f"- {left} columns: {', '.join(tables[left]['columns'])}",
                    f"- {right} columns: {', '.join(tables[right]['columns'])}",
                    "- Proposed condition: (complete only with recorded evidence)",
                    "- Verification status: UNRESOLVED",
                    "- Source URL: (complete)",
                    "- Page title: (complete)",
                    "- Documentation release: (complete)",
                    "- Access date: (complete)",
                    "- Evidence quote: (complete)",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "No joins are required: every selected column resolves to one database table.",
                "",
                "Verification status: NOT_REQUIRED",
                "",
            ]
        )

    lines.extend(
        [
            "## Status rules",
            "",
            "- VERIFIED: explicit official-source evidence for the exact join condition.",
            "  Replace the `VERIFY` comment in both physical SQL files with this join and",
            "  keep the source recorded in this worksheet.",
            "- CANDIDATE: strong indirect evidence, such as a workbook view-object",
            "  association. Keep the `VERIFY` marker and present the candidate to the",
            "  analyst for confirmation.",
            "- UNRESOLVED: no official evidence found. Keep the `VERIFY` marker and report",
            "  the gap together with the research that was attempted.",
            "- NOT_REQUIRED: the query references a single database table.",
            "",
            "Report every join status and its source URL to the user in chat as well as in",
            "this worksheet.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def parameter_readme_table(parameters: list[dict[str, object]]) -> str:
    if not parameters:
        return "No parameters were detected in the OTBI analysis."
    lines = [
        "| Parameter | Type | Operator | Multi-select | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for parameter in parameters:
        lines.append(
            f"| `{parameter['name']}` | {parameter['type']} | {parameter['operator']} | "
            f"{'yes' if parameter['multi_select'] else 'no'} | {parameter['source']} |"
        )
    return "\n".join(lines)


def write_outputs(
    analysis: dict[str, object],
    catalog_path: Path,
    workbook_path: Path,
    workbook_facts: dict[str, object],
    output_dir: Path,
    base_name: str,
    overwrite: bool,
) -> dict[str, object]:
    subject_area = str(analysis["subject_area"])
    mappings = list(workbook_facts["mappings"])
    subject_mappings = [
        mapping for mapping in mappings if clean_text(mapping.get("SUBJECT_AREA", "")) == subject_area
    ]
    if not subject_mappings:
        raise ConversionError(
            f"The supplied mapping workbook does not cover subject area \"{subject_area}\". "
            "Provide the official Oracle lineage workbook for that product family and release."
        )
    missing_columns = []
    for column in analysis["columns"]:
        mapping, _ = mapping_for_expression(str(column["expression"]), subject_area, mappings)
        if not mapping:
            missing_columns.append(str(column["presentation_column"] or column["heading"]))
    if missing_columns:
        raise ConversionError(
            "The mapping workbook covers the subject area but does not map these selected columns: "
            + ", ".join(missing_columns)
        )

    parameters = collect_parameters(analysis, subject_area, mappings)
    logical_literal = logical_sql(analysis, False, parameters)
    logical_parameterized = logical_sql(analysis, True, parameters)
    physical_literal, selected_mappings = physical_sql(
        analysis,
        subject_area,
        mappings,
        parameters,
        False,
    )
    physical_parameterized, selected_mappings = physical_sql(
        analysis,
        subject_area,
        mappings,
        parameters,
        True,
    )

    cover_text = list(workbook_facts.get("cover_text", []))
    workbook_release = workbook_release_token(cover_text, workbook_path.name)
    join_research_markdown = build_join_research_markdown(
        str(analysis["analysis"]),
        subject_area,
        selected_mappings,
        parameters,
        workbook_path,
        cover_text,
    )
    physical_tables = sorted(
        {
            clean_text(mapping.get("DATABASE_OBJECT", ""))
            for mapping in selected_mappings.values()
            if mapping.get("DATABASE_OBJECT")
        }
    )
    join_status = "not_required" if len(physical_tables) <= 1 else "research_required"

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": output_dir / f"{base_name}-manifest.json",
        "logical_literal": output_dir / f"{base_name}-logical-literal.sql",
        "logical_parameters": output_dir / f"{base_name}-logical-parameters.sql",
        "physical_literal": output_dir / f"{base_name}-physical-literal.sql",
        "physical_parameters": output_dir / f"{base_name}-physical-parameters.sql",
        "readme": output_dir / f"{base_name}-README.md",
        "join_research": output_dir / f"{base_name}-join-research.md",
    }
    parameter_dir = output_dir / f"{base_name}-parameters"
    parameter_paths: dict[str, Path] = {}
    for parameter in parameters:
        parameter_file = parameter_dir / f"{safe_base_name(str(parameter['name']))}.sql"
        paths[f"parameter_{parameter['name']}"] = parameter_file
        parameter_paths[str(parameter["name"])] = parameter_file

    existing = [path for path in paths.values() if path.exists()]
    if parameter_dir.exists():
        existing.extend(parameter_dir.glob("*.sql"))
    if existing and not overwrite:
        formatted = "\n".join(str(path) for path in existing)
        raise ConversionError(f"These output paths already exist; rerun with --overwrite only after explicit confirmation:\n{formatted}")

    for parameter in parameters:
        lov = lov_sql(parameter)
        if lov and parameter_paths.get(str(parameter["name"])):
            parameter_dir.mkdir(parents=True, exist_ok=True)
            parameter_paths[str(parameter["name"])].write_text(lov, encoding="utf-8")

    paths["manifest"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": utc_now(),
                "source_catalog": {
                    "path": str(catalog_path),
                    "sha256": sha256_file(catalog_path),
                },
                "mapping_workbook": {
                    "path": str(workbook_path),
                    "sha256": sha256_file(workbook_path),
                    "cover_text": workbook_facts["cover_text"],
                },
                "analysis": analysis,
                "parameters": parameters,
                "selected_physical_mappings": list(selected_mappings.values()),
                "join_research": {
                    "file": paths["join_research"].name,
                    "workbook_release": workbook_release,
                    "physical_tables": physical_tables,
                    "status": join_status,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["logical_literal"].write_text(logical_literal, encoding="utf-8")
    paths["logical_parameters"].write_text(logical_parameterized, encoding="utf-8")
    paths["physical_literal"].write_text(physical_literal, encoding="utf-8")
    paths["physical_parameters"].write_text(physical_parameterized, encoding="utf-8")
    paths["join_research"].write_text(join_research_markdown, encoding="utf-8")

    readme_lines = [
        f"# {analysis['analysis']} - OTBI to BI Publisher SQL",
        "",
        f"Subject area: `{subject_area}`",
        "",
        "## Artifacts",
        "",
        f"- Logical SQL (literal): `{paths['logical_literal'].name}`",
        f"- Logical SQL (parameters): `{paths['logical_parameters'].name}`",
        f"- Physical SQL (literal): `{paths['physical_literal'].name}`",
        f"- Physical SQL (parameters): `{paths['physical_parameters'].name}`",
        f"- Manifest: `{paths['manifest'].name}`",
        f"- Join research worksheet: `{paths['join_research'].name}`",
        "",
        "## BI Publisher setup",
        "",
        "- Create the physical SQL as a SQL Query data set on the Fusion applications database.",
        "- Create the logical SQL only when using an OTBI / Oracle BI Server data source.",
        "- The analyst owns data-source configuration, credentials, deployment, and report testing.",
        "",
        "## Parameters",
        "",
        parameter_readme_table(parameters),
        "",
        "For single-value parameters, use the documented bind-variable form `:PARAMETER_NAME`.",
        "For multi-select parameters, use the documented lexical-reference form `IN (&PARAMETER_NAME)`.",
        "Create one SQL Query list of values for each parameter file in the parameters directory.",
        "",
        "## Mapping evidence",
        "",
        f"- Catalog: `{catalog_path}` (`{sha256_file(catalog_path)}`)",
        f"- Mapping workbook: `{workbook_path}` (`{sha256_file(workbook_path)}`)",
        "",
        "| OTBI column | Database object | Database column | Workbook row |",
        "| --- | --- | --- | --- |",
    ]
    verify_items: list[list[str]] = []
    for column in analysis["columns"]:
        mapping, alternatives = mapping_for_expression(str(column["expression"]), subject_area, mappings)
        if mapping:
            readme_lines.append(
                f"| {column['heading']} | {mapping['DATABASE_OBJECT']} | {mapping['DATABASE_COLUMN']} | {mapping.get('workbook_row', '')} |"
            )
        database_alternatives = unique_database_alternatives(alternatives)
        if len(database_alternatives) > 1:
            verify_items.append(
                [f"`{column['heading']}` has multiple mapped database candidates:"]
                + [
                    f"- `{alternative['DATABASE_OBJECT']}.{alternative['DATABASE_COLUMN']}` "
                    f"(row {alternative.get('workbook_row', '')})"
                    for alternative in database_alternatives
                ]
            )
    if verify_items:
        readme_lines.extend(["", "## VERIFY items", ""])
        for verify_item in verify_items:
            readme_lines.extend(verify_item)
    readme_lines.extend(
        [
            "",
            "## Limits",
            "",
            f"The mapping workbook does not supply join conditions. Complete `{paths['join_research'].name}` with official Oracle sources before executing physical SQL.",
            "Semantic choices that have multiple mapping candidates remain `VERIFY` items.",
            "No SQL was executed and no database connection was made by this skill.",
        ]
    )
    paths["readme"].write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    return {
        "analysis": analysis["analysis"],
        "subject_area": subject_area,
        "outputs": [str(path) for path in paths.values()],
        "parameter_count": len(parameters),
        "selected_mapping_count": len(selected_mappings),
        "join_status": join_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--mapping-workbook", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--base-name")
    parser.add_argument("--analysis-name")
    parser.add_argument("--analysis-index", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_path = args.catalog.resolve()
    workbook_path = args.mapping_workbook.resolve()
    if not catalog_path.is_file():
        print(f"ERROR: catalog file not found: {catalog_path}", file=sys.stderr)
        return 1
    if not workbook_path.is_file():
        print(f"ERROR: mapping workbook not found: {workbook_path}", file=sys.stderr)
        return 1
    try:
        analyses = extract_catalog(catalog_path)
        if len(analyses) > 1 and not (args.analysis_index or args.analysis_name):
            names = [str(analysis["analysis"]) for analysis in analyses]
            raise ConversionError(
                "The catalog contains multiple analyses. Select one with --analysis-index or --analysis-name. "
                "Available analyses: " + "; ".join(names)
            )
        if args.analysis_name:
            selected = next(
                (analysis for analysis in analyses if str(analysis["analysis"]).lower() == args.analysis_name.lower()),
                None,
            )
            if selected is None:
                raise ConversionError(f"No analysis named \"{args.analysis_name}\" was found in the catalog")
        elif args.analysis_index:
            if args.analysis_index < 1 or args.analysis_index > len(analyses):
                raise ConversionError(f"Analysis index {args.analysis_index} is outside 1-{len(analyses)}")
            selected = analyses[args.analysis_index - 1]
        else:
            selected = analyses[0]
        workbook_facts = read_mapping_workbook(workbook_path)
        base_name = safe_base_name(args.base_name or str(selected["analysis"]))
        output_dir = args.output_dir.resolve() if args.output_dir else catalog_path.parent / "otbi-bip-sql"
        summary = write_outputs(
            selected,
            catalog_path,
            workbook_path,
            workbook_facts,
            output_dir,
            base_name,
            args.overwrite,
        )
    except (ConversionError, ET.ParseError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
