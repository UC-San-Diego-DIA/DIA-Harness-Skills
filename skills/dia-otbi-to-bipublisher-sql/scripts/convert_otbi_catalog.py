#!/usr/bin/env python3
"""Inspect an OTBI catalog and build blocked SQL scaffolds for scalar analyses."""

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
PRESENTATION_REF = re.compile(r'(?:(?P<subject>"(?:[^"]|"")+")\s*\.\s*)?"(?P<table>(?:[^"]|"")+)"\s*\.\s*"(?P<column>(?:[^"]|"")+)"')


def sql_parts(expression: str) -> list[str]:
    """Keep SQL string literals opaque during reference replacement."""
    return re.split(r"('(?:[^']|'')*')", expression)


def references(expression: str) -> list[re.Match[str]]:
    return [m for part in sql_parts(expression)[::2] for m in PRESENTATION_REF.finditer(part)]


def sql_heading(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sort_direction(value: str) -> str:
    try:
        return {'ascending': 'ASC', 'descending': 'DESC', 'asc': 'ASC', 'desc': 'DESC'}[value.lower()]
    except KeyError:
        raise ConversionError(f'Unsupported sort direction: {value}')


def validate_physical_expression(expression: str) -> None:
    """The helper is a scalar scaffold builder, not an OTBI semantic compiler."""
    code = ''.join(sql_parts(expression)[::2])
    if re.search(r'@\{|\b(?:FILTER|IFNULL|DESCRIPTOR_IDOF|VALUEOF|AGO|TODATE|PERIODROLLING|EVALUATE\w*|SUM|AVG|COUNT|MIN|MAX|REPORT_SUM|RANK|RSUM|TOPN)\s*\(', code, re.I):
        raise ConversionError('Expression requires evidence-backed semantic translation; use --inspect and the semantic-equivalence reference. No physical SQL generated.')
    code = PRESENTATION_REF.sub('MAPPED_COLUMN', code)
    allowed = {'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'LIKE', 'BETWEEN', 'DATE', 'TIMESTAMP', 'AS', 'NUMBER', 'VARCHAR2', 'CHAR', 'NVL', 'COALESCE', 'NULLIF', 'CAST', 'ROUND', 'TRUNC', 'ABS', 'UPPER', 'LOWER', 'LENGTH', 'SUBSTR', 'REPLACE', 'TO_CHAR', 'TO_DATE', 'TO_NUMBER', 'MAPPED_COLUMN'}
    unknown = set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*', code.upper())) - allowed
    if unknown or any(token in code for token in (';', '--', '/*', '&')):
        raise ConversionError('Expression outside the supported scalar subset; use --inspect for semantic translation: ' + ', '.join(sorted(unknown)))


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
            inflater = zlib.decompressobj()
            inflated = inflater.decompress(data[offset:])
        except zlib.error:
            offset += 1
            continue
        if inflater.eof and b"<saw:report" in inflated:
            # A catalog stream can contain binary metadata around UTF-8 report XML.
            # Decode only XML, never replace undecodable bytes inside an expression.
            for match in re.finditer(rb'<saw:report[ >]', inflated):
                end = inflated.find(b'</saw:report>', match.start())
                if end < 0:
                    raise ConversionError('Incomplete saw:report XML document in catalog')
                fragment = inflated[match.start():end + len(b'</saw:report>')]
                try:
                    parts.append(fragment.decode('utf-8'))
                except UnicodeDecodeError as error:
                    raise ConversionError('Report XML is not valid UTF-8; source encoding needs inspection') from error
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
            raise ConversionError('Incomplete saw:report XML document in catalog')
        end += len("</saw:report>")
        fragment = text[start:end]
        blocks.append(fragment)
    if not blocks:
        raise ConversionError("No complete saw:report XML document was found in the catalog")
    return blocks


def expression_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    text = "".join(element.itertext())
    return text if is_literal(element) else text.strip()


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
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ConversionError('Date literal requires YYYY-MM-DD without a timezone')
            try:
                datetime.strptime(value, '%Y-%m-%d')
            except ValueError as error:
                raise ConversionError('Invalid date literal') from error
            return f"DATE '{value}'"
        if raw_type in {"xsd:dateTime", "xsd:time"}:
            if raw_type == 'xsd:time' or not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?', value):
                raise ConversionError('Timestamp or time with timezone requires explicit translation')
            return f"TIMESTAMP '{value.replace('T', ' ')}'"
        if raw_type.split(':')[-1] in {'integer', 'int', 'long', 'decimal', 'double', 'float', 'short'}:
            if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?', value):
                raise ConversionError('Invalid numeric literal')
            return value
        if raw_type not in {'xsd:string', 'xsd:date', 'xsd:dateTime'}:
            raise ConversionError(f'Unsupported literal type {raw_type}')
        return sql_literal(value)
    return render_expression(element, parameterized=parameterized) or expression_text(element)


def render_expression(element: ET.Element | None, parameterized: bool = False) -> str | None:
    if element is None:
        return None
    name = expression_type(element)
    children = list(element)
    if name == "savedFilter":
        raise ConversionError('Saved filter must be supplied and expanded before conversion; use --inspect')
    if name == "eval":
        variable = expression_text(element)
        raise ConversionError(f'Unresolved presentation variable {variable}; supply runtime values before conversion, use --inspect')
    if name in {"sqlExpression", "columnExpression"}:
        if name == "columnExpression":
            nested = element.find(".//sawx:expr", NS)
            if nested is not None:
                return render_expression(nested, parameterized=parameterized)
        return expression_text(element)
    if name == "logical":
        operator = (element.get("op") or "and").upper()
        if operator not in {'AND', 'OR', 'NOT'} or not children or (operator == 'NOT' and len(children) != 1):
            raise ConversionError('Unsupported logical filter')
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
        if len(children) != 2 or element.get('op') not in {'equal', 'notEqual', 'greater', 'greaterOrEqual', 'less', 'lessOrEqual', 'like'}:
            raise ConversionError('Unsupported comparison filter')
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
            if not values:
                raise ConversionError('Empty list filter')
            keyword = "IN" if operator == "in" else "NOT IN"
            return f"{left} {keyword} ({', '.join(values)})"
        if operator in {"contains", "notContains", "startsWith"}:
            conditions = []
            for value in children[1:]:
                if not is_literal(value):
                    raise ConversionError('Pattern filter needs literal values')
                text_value = expression_text(value)
                if operator == "contains":
                    conditions.append(f"{left} LIKE {sql_literal('%' + text_value + '%')}")
                elif operator == "notContains":
                    conditions.append(f"{left} NOT LIKE {sql_literal('%' + text_value + '%')}")
                else:
                    conditions.append(f"{left} LIKE {sql_literal(text_value + '%')}")
            connector = ' AND ' if operator == 'notContains' else ' OR '
            return "(" + connector.join(conditions) + ")"
    if name in {'unary', 'isNull'} and element.get('op') in {'isNull', 'isNotNull'} and len(children) == 1:
        return render_value(children[0]) + (' IS NULL' if element.get('op') == 'isNull' else ' IS NOT NULL')
    if name == 'between' and element.get('op') in {'between', 'notBetween'} and len(children) == 3:
        return f"{render_value(children[0])} {'NOT BETWEEN' if element.get('op') == 'notBetween' else 'BETWEEN'} {render_value(children[1])} AND {render_value(children[2])}"
    raise ConversionError(f'Unsupported filter expression {name}; use --inspect; no filter may be dropped')


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
    matches = references(expression)
    if matches:
        return matches[-1].group('column')
    matches = re.findall(r'"([^"]+)"', expression)
    return matches[-1] if matches else expression[:80]


def extract_report(block: str, index: int, inspect_only: bool = False) -> dict[str, object]:
    root = ET.fromstring(block)
    criteria = root.find("saw:criteria", NS)
    if criteria is None:
        raise ConversionError("The catalog XML has no saw:criteria element")
    subject_area = clean_text(criteria.get("subjectArea", "")).strip('"')
    columns_node = criteria.find("saw:columns", NS)
    if columns_node is None:
        if inspect_only:
            return {
                'analysis': analysis_name(root, subject_area, index),
                'analysis_index': index + 1, 'subject_area': subject_area,
                'columns': [], 'sorts': [],
                'filter': {'explicit_sql': '', 'raw_xml': '', 'saved_filters': []},
                'raw_report_xml': block,
                'inspection_blockers': ['No simple columns; inspect full criteria and resolve combined or unsupported query semantics'],
            }
        raise ConversionError("The catalog XML has no saw:columns element")

    columns: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for position, column in enumerate(columns_node.findall("saw:column", NS)):
        column_id = clean_text(column.get("columnID", f"column_{position}"))
        if column_id in seen_ids:
            raise ConversionError('Duplicate column ID')
        seen_ids.add(column_id)
        expression_node = column.find("./saw:columnFormula/sawx:expr", NS)
        expression = expression_text(expression_node)
        if not expression:
            raise ConversionError('Empty column formula')
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
                "presentation_table": matches[0].group('table') if (matches := references(expression)) else "",
                "presentation_column": matches[0].group('column') if (matches := references(expression)) else "",
            }
        )

    filter_node = criteria.find("./saw:filter/sawx:expr", NS)
    if not columns:
        raise ConversionError('No selected columns')
    blockers = []
    try:
        explicit_filter = render_expression(filter_node) or ""
    except ConversionError as error:
        if not inspect_only:
            raise
        explicit_filter = ''
        blockers.append(str(error))
    saved_filters = saved_filter_details(filter_node)
    sorts: list[dict[str, str]] = []
    for order_ref in criteria.findall(".//saw:columnOrderRef", NS):
        column_id = clean_text(order_ref.get("columnID", ""))
        direction = clean_text(order_ref.get("direction", "ascending")).lower()
        column = next((item for item in columns if item["column_id"] == column_id), None)
        if not column:
            raise ConversionError('Sort references an unknown column')
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
        "raw_report_xml": block,
        "inspection_blockers": blockers,
    }


def extract_catalog(path: Path, inspect_only: bool = False) -> list[dict[str, object]]:
    text = inflate_catalog(path.read_bytes())
    return [extract_report(block, index, inspect_only) for index, block in enumerate(report_blocks(text))]


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
    return "P_" + (normalized or 'PARAMETER')


def presentation_expression_column(expression: str) -> tuple[str, str]:
    matches = references(expression)
    if matches:
        return normalize_presentation_table(matches[-1].group('table')), matches[-1].group('column')
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
    refs = references(expression)
    if refs and refs[-1].group('subject'):
        subject_area = refs[-1].group('subject')[1:-1].replace('""', '"')
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
        table, column = match.group('table'), match.group('column')
        effective_subject = match.group('subject') or subject_area
        key = f"{effective_subject}|{table}|{column}"
        if key in selected_mappings:
            mapping = selected_mappings[key]
            return f"{mapping['DATABASE_OBJECT']}.{mapping['DATABASE_COLUMN']}"
        mapping, alternatives = mapping_for_expression(match.group(0), subject_area, mappings)
        if len(unique_database_alternatives(alternatives)) > 1:
            raise ConversionError(f'Ambiguous database mapping for {match.group(0)}; confirm a mapping with evidence before translation')
        if mapping:
            if not all(re.fullmatch(r'[A-Za-z][A-Za-z0-9_$#]*', mapping[k]) for k in ('DATABASE_OBJECT', 'DATABASE_COLUMN')):
                raise ConversionError('Workbook mapping needs expression or identifier review')
            selected_mappings[key] = mapping
            return f"{mapping['DATABASE_OBJECT']}.{mapping['DATABASE_COLUMN']}"
        raise ConversionError(f'No database mapping for {match.group(0)} in subject area {subject_area}')

    parts = sql_parts(expression)
    for i in range(0, len(parts), 2):
        parts[i] = PRESENTATION_REF.sub(replace, parts[i])
    return ''.join(parts), selected_mappings


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
        for node in filter_node.iter():
            if expression_type(node) == 'sqlExpression':
                validate_physical_expression(expression_text(node))
    heading_by_expression = {str(column["expression"]): str(column["heading"]) for column in analysis["columns"]}

    def add_parameter(left_expression: str, operator: str, value: str, multi_select: bool, literal_nodes: list[ET.Element]) -> str | None:
        literal_types = [node.get(f'{{{XSI_NS}}}type', '') for node in literal_nodes]
        if len(set(literal_types)) != 1 or literal_types[0] == 'xsd:dateTime':
            raise ConversionError('Mixed list types or timestamp parameters require explicit datatype review')
        for parameter in parameters:
            if parameter['logical_expression'] == left_expression and parameter['operator'] == operator and parameter['original_values'] == [expression_text(node) for node in literal_nodes]:
                return str(parameter['name'])
        source_heading = heading_by_expression.get(left_expression, "")
        _, presentation_column = presentation_expression_column(left_expression)
        source = source_heading or presentation_column or left_expression
        variable_matches = re.findall(r"@{([^}]+)}", left_expression)
        if variable_matches:
            source = variable_matches[-1]
        base = normalize_parameter_name(source)
        name = base
        suffix = 2
        while name in parameter_names:
            name = f'{base}_{suffix}'
            suffix += 1
        parameter_names.add(name)
        mapping, alternatives = mapping_for_expression(left_expression, subject_area, mappings)
        parameter: dict[str, object] = {
            "name": name,
            "source": source,
            "logical_expression": left_expression,
            "operator": operator,
            "original_value": value,
            "type": ('number' if literal_nodes[0].get(f'{{{XSI_NS}}}type', '').split(':')[-1] in {'integer', 'int', 'long', 'decimal', 'double', 'float', 'short'} else 'date' if literal_nodes[0].get(f'{{{XSI_NS}}}type', '') == 'xsd:date' else 'text'),
            "original_values": [expression_text(node) for node in literal_nodes],
            "literal_types": [node.get(f'{{{XSI_NS}}}type', '') for node in literal_nodes],
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
                    [children[1]],
                )
            return
        if name == "list" and element.get("op") in {"in", "notIn"} and children:
            if len(children) < 2 or not all(is_literal(child) for child in children[1:]):
                raise ConversionError('Resolve runtime list values before parameterization')
            add_parameter(
                expression_text(children[0]),
                element.get("op", ""),
                ", ".join(expression_text(child) for child in children[1:]),
                True,
                children[1:],
            )
            return
        for child in children:
            walk(child)

    walk(filter_node)
    return parameters


def parameter_token(parameter: dict[str, object]) -> str:
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
                    and parameter['operator'] == element.get('op')
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
                and parameter['operator'] == element.get('op')
            ),
            None,
        )
        if match:
            left = render_value(children[0])
            keyword = "IN" if element.get("op") == "in" else "NOT IN"
            return f"{left} {keyword} ({parameter_token(match)})"
    if name != 'logical':
        return render_expression(element)
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
        alias = sql_heading(str(column['heading']))
        lines.append(f"    {column['expression']} AS {alias},")
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
        order_items = [f"{item['expression']} {sort_direction(item['direction'])}" for item in analysis["sorts"]]
        lines.append("ORDER BY")
        lines.append("    " + ", ".join(order_items))
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
        validate_physical_expression(str(column['expression']))
        substituted, selected_mappings = substitute_physical_references(
            str(column["expression"]),
            subject_area,
            mappings,
            selected_mappings,
        )
        if substituted == column["expression"] and references(str(column['expression'])):
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
        "-- BLOCKED SCAFFOLD: no rows until mapping, joins and OTBI semantics are reviewed.",
        f'-- Analysis: {analysis["analysis"]}',
        f'-- Subject area: "{analysis["subject_area"]}"',
        "SELECT",
    ]
    for column in substituted_columns:
        alias = sql_heading(column['heading'])
        lines.append(f"    {column['physical_expression']} AS {alias},")
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
        for node in filter_node.iter():
            if expression_type(node) == 'sqlExpression':
                validate_physical_expression(expression_text(node))
        physical_filter, selected_mappings = substitute_physical_references(
            physical_filter,
            subject_area,
            mappings,
            selected_mappings,
        )
        if physical_filter:
            where_block.extend(["WHERE", f"    1 = 0 AND ({physical_filter}) -- BLOCKED: semantic review required"])
    if not where_block:
        where_block = ['WHERE', '    1 = 0 -- BLOCKED: semantic review required']

    order_block: list[str] = []
    if analysis["sorts"]:
        order_items = []
        for sort in analysis["sorts"]:
            validate_physical_expression(str(sort['expression']))
            substituted, selected_mappings = substitute_physical_references(
                str(sort["expression"]),
                subject_area,
                mappings,
                selected_mappings,
            )
            order_items.append(f"{substituted} {sort_direction(sort['direction'])}")
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
        for (left_table, right_table), shared_columns in join_column_candidates(selected_mappings).items():
            for column in shared_columns:
                lines.append(
                    "-- PROPOSED JOIN (name candidate; never evidence, confirm in official Oracle FK docs): "
                    f"{left_table}.{column} = {right_table}.{column}"
                )
    lines.extend(where_block)
    lines.extend(order_block)
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
        "-- BLOCKED SCAFFOLD: apply the reviewed report access scope before use as a list of values.",
        "SELECT DISTINCT",
        f"    {database_object}.{database_column} AS PARAMETER_VALUE",
        f"FROM {database_object}",
        "WHERE 1 = 0 -- BLOCKED: scope and mapping review required",
        "ORDER BY PARAMETER_VALUE",
    ]
    return "\n".join(lines) + "\n"


def join_column_candidates(selected_mappings: dict[str, dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    table_columns: dict[str, dict[str, str]] = {}
    for mapping in selected_mappings.values():
        table = clean_text(mapping.get("DATABASE_OBJECT", ""))
        column = clean_text(mapping.get("DATABASE_COLUMN", ""))
        if table and column:
            table_columns.setdefault(table, {})[column.upper()] = column
    table_names = sorted(table_columns)
    candidates: dict[tuple[str, str], list[str]] = {}
    for position, left in enumerate(table_names):
        for right in table_names[position + 1 :]:
            shared_keys = sorted(set(table_columns[left]) & set(table_columns[right]))
            if shared_keys:
                candidates[(left, right)] = [table_columns[left][key] for key in shared_keys]
    return candidates


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
    tables: dict[str, list[str]] = {}
    for mapping in selected_mappings.values():
        tables.setdefault(mapping["DATABASE_OBJECT"], []).append(
            f"{mapping['DATABASE_COLUMN']} | workbook row {mapping.get('workbook_row', '')}"
        )
    lines = [
        f"# Oracle mapping and join review - {analysis_name}", "",
        "Status: BLOCKED. Field lineage is not a complete semantic model.", "",
        f"- Subject area: {subject_area}",
        f"- Workbook: {workbook_path}",
        f"- Workbook release: {workbook_release_token(cover_text, workbook_path.name)}",
        "- Target tenant release: UNKNOWN",
        "- Current documentation release, library URL, access date: UNRESOLVED",
        "- Output grain, measure aggregation, access scope: UNRESOLVED", "",
        "## Object and field verification", "",
    ]
    for table, fields in sorted(tables.items()):
        lines += [
            f"### {table}", "",
            *[f"- {field}" for field in sorted(set(fields))],
            "- Oracle source URL, title, release, access date: UNRESOLVED",
            "- Primary/unique keys, nullable keys, relevant FK rows: UNRESOLVED",
            "- Datatypes, language/effective-date/scope restrictions: UNRESOLVED", "",
        ]
    lines += [
        "## Required join graph", "",
        "Build only the edges the analysis requires. Do not apply all available foreign keys.",
        "Bridge objects and unprojected keys require separate documented evidence.",
        "No-row guards remain until mapping, semantics, joins, and scope are reviewed.", "",
        "| Edge / aliases | Exact key pairs | Business role | Cardinality / grain | INNER or LEFT | Restrictions | Source / release / date | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        "| Complete during research | | | | | | | UNRESOLVED |", "",
        "An FK can appear as incoming on a parent page. Verify child/parent direction,",
        "all composite key pairs, referenced unique key, and the intended business role.",
        "A documented relationship alone does not establish the correct join type or grain.", "",
        "## Semantic transformation and remaining issues", "",
        "| Source expression | Oracle expression | Workbook rows / additional evidence | Aggregate stage | Review status |",
        "| --- | --- | --- | --- | --- |",
        "| Complete during semantic review | | | | UNRESOLVED |", "",
        "Record unresolved choices for filter-only and sort-only fields as well as selected fields.",
        "Update the manifest, README, and validation record after review. File generation is not",
        "Oracle execution or OTBI reconciliation.", "",
    ]
    return "\n".join(lines) + "\n"


def build_validation_markdown() -> str:
    return """# Conversion validation

Status: BLOCKED

- Oracle execution: not_run
- OTBI reconciliation: not_run
- Source and workbook hashes: see manifest
- Reviewed SQL hash / reviewer / date: not recorded
- Tenant, release, effective access scope: unresolved
- Prompt values, currency, language, timezone: unresolved
- Source data window and both run times: not recorded
- Required mapping, semantic, join, scope review: incomplete
- OTBI and BI Publisher complete export paths/hashes: not supplied
- Compared columns, rows, duplicate multiplicities, business keys: not_run
- Per-key measure differences, totals, nulls, dates: not_run
- Agreed numeric tolerances and mismatch counts: not recorded
- Literal and parameterized test cases: not_run
- Analyst confirmation and tested-scope limitations: not recorded

Do not remove no-row guards or call SQL runnable until required review is complete.
After that review use CANDIDATE_NOT_EXECUTED; after Oracle execution use
EXECUTED_NOT_RECONCILED; after the agreed export comparison passes use RECONCILED.
Keep the manifest and README consistent with the evidence recorded here.
"""


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
    root = ET.fromstring(analysis['raw_report_xml'])
    criteria = root.find('saw:criteria', NS)
    allowed = {'columns', 'filter', 'columnOrder'}
    if any(local_name(child.tag) not in allowed for child in criteria) or expression_type(criteria) not in {'', 'simpleCriteria'}:
        raise ConversionError('Criteria contains unsupported semantics; use --inspect for evidence-backed translation')

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
        "validation": output_dir / f"{base_name}-validation.md",
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
                "conversion_status": "blocked_scaffold",
                "validation": {"oracle_execution": "not_run", "otbi_reconciliation": "not_run", "semantic_review": "required"},
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
    paths['validation'].write_text(build_validation_markdown(), encoding='utf-8')

    readme_lines = [
        f"# {analysis['analysis']} - OTBI to BI Publisher SQL",
        "",
        f"Subject area: `{subject_area}`",
        "",
        "Status: BLOCKED SCAFFOLD. File generation does not establish Oracle syntax or OTBI equivalence.",
        "The physical and LOV files contain a no-row guard. Remove it only after the evidence review in the skill.",
        "",
        "## Artifacts",
        "",
        f"- Logical SQL (literal): `{paths['logical_literal'].name}`",
        f"- Logical SQL (parameters): `{paths['logical_parameters'].name}`",
        f"- Physical SQL (literal): `{paths['physical_literal'].name}`",
        f"- Physical SQL (parameters): `{paths['physical_parameters'].name}`",
        f"- Manifest: `{paths['manifest'].name}`",
        f"- Join research worksheet: `{paths['join_research'].name}`",
        f"- Validation record: `{paths['validation'].name}`",
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
        "For multi-select menu parameters, use bind form `IN (:PARAMETER_NAME)` and enable Multiple Selection.",
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
        "conversion_status": "blocked_scaffold",
        "oracle_execution": "not_run",
        "otbi_reconciliation": "not_run",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--mapping-workbook", type=Path)
    parser.add_argument("--inspect", action='store_true', help='Print source evidence as JSON without writing SQL or requiring a workbook')
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--base-name")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--analysis-name")
    selection.add_argument("--analysis-index", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_path = args.catalog.resolve()
    if not catalog_path.is_file():
        print(f"ERROR: catalog file not found: {catalog_path}", file=sys.stderr)
        return 1
    if not args.inspect and not args.mapping_workbook:
        print('ERROR: --mapping-workbook is required unless --inspect is used', file=sys.stderr)
        return 1
    workbook_path = args.mapping_workbook.resolve() if args.mapping_workbook else None
    if workbook_path is not None and not workbook_path.is_file():
        print(f"ERROR: mapping workbook not found: {workbook_path}", file=sys.stderr)
        return 1
    try:
        analyses = extract_catalog(catalog_path, inspect_only=True)
        if args.inspect:
            print(json.dumps({'source_catalog': {'path': str(catalog_path), 'sha256': sha256_file(catalog_path)}, 'analyses': analyses}, indent=2, ensure_ascii=False))
            return 0
        if len(analyses) > 1 and args.analysis_index is None and not args.analysis_name:
            names = [str(analysis["analysis"]) for analysis in analyses]
            raise ConversionError(
                "The catalog contains multiple analyses. Select one with --analysis-index or --analysis-name. "
                "Available analyses: " + "; ".join(names)
            )
        if args.analysis_name:
            matches = [analysis for analysis in analyses if str(analysis['analysis']).lower() == args.analysis_name.lower()]
            if not matches:
                raise ConversionError(f"No analysis named \"{args.analysis_name}\" was found in the catalog")
            if len(matches) != 1:
                raise ConversionError('Multiple analyses share this name; use --analysis-index')
            selected = matches[0]
        elif args.analysis_index is not None:
            if args.analysis_index < 1 or args.analysis_index > len(analyses):
                raise ConversionError(f"Analysis index {args.analysis_index} is outside 1-{len(analyses)}")
            selected = analyses[args.analysis_index - 1]
        else:
            selected = analyses[0]
        selected = extract_report(str(selected['raw_report_xml']), int(selected['analysis_index']) - 1)
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
