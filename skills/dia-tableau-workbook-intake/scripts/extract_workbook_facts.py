#!/usr/bin/env python3
"""Extract deterministic facts from a Tableau workbook package or workbook XML."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


from facts_common import (
    SCHEMA_VERSION,
    SCHEMA_URL,
    TOOL_VERSION,
    IdAssigner,
    build_provenance,
    slugify,
)


class ExtractionError(Exception):
    """Raised when the input cannot be parsed deterministically."""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element, name):
    return [child for child in element if local_name(child.tag) == name]


def child(element, name):
    found = children(element, name)
    return found[0] if found else None


def descendants(element, name):
    return [node for node in element.iter() if local_name(node.tag) == name]


def dedupe_in_order(values):
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalize_title(element) -> str:
    """Join formatted-text runs into one line, using ' | ' between lines.

    Tableau stores line breaks as the character U+00C6 followed by a newline.
    """
    if element is None:
        return ""
    runs = ["".join(run.itertext()) for run in descendants(element, "run")]
    if not runs:
        runs = ["".join(element.itertext())]
    joined = "\n".join(runs).replace("\u00c6", "\n")
    lines = [line.strip() for line in joined.split("\n")]
    return " | ".join(line for line in lines if line)


def find_formatted_title(parent):
    layout_options = child(parent, "layout-options")
    if layout_options is None:
        return None
    title = child(layout_options, "title")
    if title is None:
        return None
    return child(title, "formatted-text")


def load_workbook_document(raw: bytes, warnings: list[str], notes: list[dict]):
    """Return (xml_text, container, entry_name) from .twbx bytes or .twb bytes."""
    if raw[:2] == b"PK":
        try:
            package = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise ExtractionError(
                "input is a zip archive but cannot be opened as a .twbx package"
            ) from exc
        entries = [
            info for info in package.infolist()
            if info.filename.lower().endswith(".twb")
        ]
        if not entries:
            raise ExtractionError(
                "no .twb workbook XML entry found in the .twbx package"
            )
        if len(entries) > 1:
            warnings.append(
                f"package contains {len(entries)} .twb entries; "
                f"extracted {entries[0].filename}"
            )
            notes.append({"code": "MULTIPLE_TWB_ENTRIES", "count": 1})
        entry = entries[0]
        try:
            xml_text = package.read(entry).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractionError(
                f"workbook XML entry is not UTF-8 text: {entry.filename}"
            ) from exc
        return xml_text, "twbx", entry.filename
    try:
        xml_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExtractionError(
            "input is not UTF-8 text and is not a .twbx package"
        ) from exc
    if "<workbook" not in xml_text:
        raise ExtractionError(
            "input is neither a .twbx package nor a .twb workbook XML document"
        )
    return xml_text, "twb", ""


def parse_size(dashboard) -> dict:
    size_element = child(dashboard, "size")
    if size_element is None:
        return {}
    size = {}
    for attribute in ("sizing-mode", "minwidth", "minheight", "maxwidth", "maxheight"):
        value = size_element.get(attribute)
        if value is None:
            continue
        try:
            value = int(value)
        except ValueError:
            pass
        size[attribute.replace("-", "_")] = value
    return size


def zone_entry(zone, worksheet_names, captions):
    """Classify one dashboard zone into a layout entry.

    Returns a dict, the string "empty", or None for layout containers.
    """
    zone_type = zone.get("type-v2", "")
    name = zone.get("name", "")
    if zone_type.startswith("layout-"):
        return None
    if not zone_type and not name:
        return None
    if zone_type == "filter":
        entry = {
            "kind": "filter",
            "source_sheet": name,
            "field": zone.get("param", ""),
            "mode": zone.get("mode", ""),
            "show_apply": zone.get("show-apply", "") in ("true", "1"),
            "values": zone.get("values", ""),
        }
        field_caption = resolve_field_caption(zone.get("param", ""), captions)
        if field_caption:
            entry["field_caption"] = field_caption
        return entry
    if zone_type in ("color", "size", "shape"):
        entry = {
            "kind": "legend",
            "legend_kind": zone_type,
            "source_sheet": name,
            "field": zone.get("param", ""),
        }
        field_caption = resolve_field_caption(zone.get("param", ""), captions)
        if field_caption:
            entry["field_caption"] = field_caption
        return entry
    if zone_type == "paramctrl":
        entry = {
            "kind": "parameter",
            "parameter": zone.get("param", ""),
            "caption": zone.get("caption", ""),
        }
        if not entry["caption"]:
            parameter_caption = resolve_field_caption(zone.get("param", ""), captions)
            if parameter_caption:
                entry["caption"] = parameter_caption
        return entry
    if zone_type == "title":
        return {"kind": "title"}
    if zone_type == "text":
        return {
            "kind": "text",
            "text": normalize_title(child(zone, "formatted-text")),
        }
    if zone_type in ("image", "web"):
        return {"kind": zone_type, "name": zone.get("caption", "") or name}
    if zone_type == "empty":
        return "empty"
    if name and name in worksheet_names:
        return {"kind": "sheet", "name": name}
    return {"kind": "other", "zone_type": zone_type or "untyped", "name": name}


def resolve_field_caption(field, captions):
    """Resolve a qualified zone field to its human-readable column caption."""
    if not field:
        return None
    match = re.search(r"\]\.\[(.*)\]$", field)
    content = match.group(1) if match else field.strip("[]")
    candidates = [f"[{content}]"]
    if ":" in content:
        candidates.extend(f"[{part}]" for part in content.split(":"))
    for candidate in candidates:
        caption = captions.get(candidate)
        if caption:
            return caption
    if ":" not in content:
        return content.strip()
    return None


def collect_captions(root, worksheets_element) -> dict:
    """Map bracketed column names to their captions across the workbook."""
    captions = {}
    sources = []
    datasources_element = child(root, "datasources")
    if datasources_element is not None:
        sources.extend(children(datasources_element, "datasource"))
    if worksheets_element is not None:
        for worksheet in children(worksheets_element, "worksheet"):
            view = child(child(worksheet, "table"), "view")
            if view is not None:
                for dependency in children(view, "datasource-dependencies"):
                    sources.append(dependency)
    for source in sources:
        for column in children(source, "column"):
            column_name = column.get("name", "")
            caption = column.get("caption", "")
            if column_name and caption and column_name not in captions:
                captions[column_name] = caption
    return captions


def parse_dashboard(dashboard, worksheet_names, captions, warnings, notes) -> dict:
    name = dashboard.get("name", "")
    datasources = []
    for datasource in descendants(dashboard, "datasource"):
        datasource_name = datasource.get("name", "")
        if datasource_name:
            datasources.append(datasource.get("caption") or datasource_name)

    layout = []
    empty_zones = 0
    zones_element = child(dashboard, "zones")
    if zones_element is not None:
        def walk(zone):
            nonlocal empty_zones
            entry = zone_entry(zone, worksheet_names, captions)
            if entry == "empty":
                empty_zones += 1
            elif entry is not None:
                layout.append(entry)
            for zone_child in children(zone, "zone"):
                walk(zone_child)

        walk(zones_element)

    unknown = sorted(
        entry["zone_type"] for entry in layout if entry["kind"] == "other"
    )
    if unknown:
        warnings.append(
            f"dashboard '{name}' has {len(unknown)} unrecognized zones; "
            f"zone types: {', '.join(dedupe_in_order(unknown))}"
        )
        notes.append(
            {
                "code": "UNRECOGNIZED_ZONE",
                "dashboard": name,
                "count": len(unknown),
            }
        )
    if empty_zones:
        warnings.append(f"dashboard '{name}' has {empty_zones} empty zones")
        notes.append(
            {
                "code": "EMPTY_ZONE",
                "dashboard": name,
                "count": empty_zones,
            }
        )

    actions = []
    actions_element = child(dashboard, "actions")
    if actions_element is not None:
        for action in children(actions_element, "action"):
            title_element = child(action, "title")
            title_text = (
                "".join(title_element.itertext()).strip()
                if title_element is not None
                else action.get("name", "")
            )
            actions.append(
                {"title": title_text, "source_sheet": action.get("source", "")}
            )

    sheets = dedupe_in_order(
        entry["name"] for entry in layout if entry["kind"] == "sheet"
    )
    return {
        "name": name,
        "datasources": dedupe_in_order(datasources),
        "size": parse_size(dashboard),
        "title_text": normalize_title(find_formatted_title(dashboard)),
        "sheets": sheets,
        "layout": layout,
        "filters": [entry for entry in layout if entry["kind"] == "filter"],
        "legends": [entry for entry in layout if entry["kind"] == "legend"],
        "parameter_controls": [
            entry for entry in layout if entry["kind"] == "parameter"
        ],
        "actions": actions,
    }


def parse_worksheet(worksheet, captions) -> dict:
    name = worksheet.get("name", "")
    view = child(child(worksheet, "table"), "view")
    datasources = []
    rows = []
    cols = []
    filters = []
    if view is not None:
        datasources_element = child(view, "datasources")
        if datasources_element is not None:
            for datasource in children(datasources_element, "datasource"):
                datasource_name = datasource.get("name", "")
                if datasource_name:
                    datasources.append(datasource_name)
        for shelf, target in (("rows", rows), ("cols", cols)):
            shelf_element = child(view, shelf)
            if shelf_element is not None:
                target.extend("".join(shelf_element.itertext()).split())
        filters_element = child(view, "filters")
        if filters_element is not None:
            for sheet_filter in children(filters_element, "filter"):
                sheet_filter_entry = {
                    "column": sheet_filter.get("column", ""),
                    "class": sheet_filter.get("class", ""),
                }
                column_caption = resolve_field_caption(
                    sheet_filter.get("column", ""), captions
                )
                if column_caption:
                    sheet_filter_entry["column_caption"] = column_caption
                filters.append(sheet_filter_entry)

    calculations = []
    seen_calculations = set()
    for column in descendants(worksheet, "column"):
        calculation = child(column, "calculation")
        if calculation is None or column.get("param-domain-type"):
            continue
        caption = column.get("caption") or column.get("name", "")
        identity = (caption, column.get("name", ""))
        if identity in seen_calculations:
            continue
        seen_calculations.add(identity)
        calculations.append(
            {
                "caption": caption,
                "kind": calculation.get("class", ""),
                "formula": calculation.get("formula", ""),
            }
        )

    mark_types = dedupe_in_order(
        mark.get("class", "")
        for mark in descendants(worksheet, "mark")
        if mark.get("class")
    )
    encodings = []
    seen_encodings = set()
    for encoding in descendants(worksheet, "encoding"):
        attribute = encoding.get("attr", "")
        field = encoding.get("field", "")
        identity = (attribute, field)
        if identity in seen_encodings:
            continue
        seen_encodings.add(identity)
        encoding_entry = {"attr": attribute, "field": field}
        field_caption = resolve_field_caption(field, captions)
        if field_caption:
            encoding_entry["field_caption"] = field_caption
        encodings.append(encoding_entry)

    return {
        "name": name,
        "title_text": normalize_title(find_formatted_title(worksheet)),
        "datasources": dedupe_in_order(datasources),
        "rows": rows,
        "cols": cols,
        "calculations": calculations,
        "filters": filters,
        "mark_types": mark_types,
        "encodings": encodings,
    }


def parse_workbook(root, warnings: list[str], notes: list[dict], expected: dict) -> dict:
    datasources = []
    parameters = []
    worksheets_element = child(root, "worksheets")
    captions = collect_captions(root, worksheets_element)
    datasources_element = child(root, "datasources")
    if datasources_element is not None:
        for datasource in children(datasources_element, "datasource"):
            datasource_name = datasource.get("name", "")
            datasources.append(
                {
                    "name": datasource_name,
                    "caption": datasource.get("caption"),
                }
            )
            for column in children(datasource, "column"):
                if not column.get("param-domain-type"):
                    continue
                members_element = child(column, "members")
                members = []
                if members_element is not None:
                    members = [
                        member.get("value", "").strip('"')
                        for member in children(members_element, "member")
                    ]
                parameters.append(
                    {
                        "datasource": datasource_name,
                        "name": column.get("name", ""),
                        "caption": column.get("caption", ""),
                        "members": members,
                    }
                )

    worksheets = []
    worksheet_names = []
    if worksheets_element is not None:
        for worksheet in children(worksheets_element, "worksheet"):
            worksheets.append(parse_worksheet(worksheet, captions))
            worksheet_names.append(worksheet.get("name", ""))

    dashboards = []
    dashboards_element = child(root, "dashboards")
    if dashboards_element is not None:
        for dashboard in children(dashboards_element, "dashboard"):
            dashboards.append(
                parse_dashboard(dashboard, worksheet_names, captions, warnings, notes)
            )

    stories_element = child(root, "stories")
    if stories_element is not None:
        warnings.append("workbook contains stories; story sheets are not inventoried")
        notes.append({"code": "STORY_NOT_INVENTORIED", "count": 1})

    sheets_on_dashboards = dedupe_in_order(
        sheet for dashboard in dashboards for sheet in dashboard["sheets"]
    )
    orphan_sheets = [
        name for name in worksheet_names if name not in sheets_on_dashboards
    ]
    base_names = {}
    for sheet_name in worksheet_names:
        base = re.sub(r" \(\d+\)$", "", sheet_name)
        base_names.setdefault(base, []).append(sheet_name)
    duplicate_name_groups = [
        {"base": base, "sheets": names}
        for base, names in base_names.items()
        if len(names) > 1
    ]

    location = child(root, "repository-location")
    expected["dashboards"] = len(children(dashboards_element, "dashboard")) if dashboards_element is not None else 0
    expected["worksheets"] = len(children(worksheets_element, "worksheet")) if worksheets_element is not None else 0
    expected["datasources"] = len(children(datasources_element, "datasource")) if datasources_element is not None else 0
    expected["parameters"] = 0
    if datasources_element is not None:
        for datasource in children(datasources_element, "datasource"):
            expected["parameters"] += sum(
                1
                for column in children(datasource, "column")
                if column.get("param-domain-type")
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "workbook": {
            "name": "",
            "tableau_version": root.get("version", ""),
            "source_build": root.get("source-build", ""),
            "source_platform": root.get("source-platform", ""),
            "repository_location": (
                location.get("derived-from", "") if location is not None else ""
            ),
        },
        "extraction": {
            "container": "",
            "entry": "",
            "timestamp": "",
            "warnings": warnings,
        },
        "datasources": datasources,
        "parameters": parameters,
        "dashboards": dashboards,
        "worksheets": worksheets,
        "derived": {
            "sheets_on_dashboards": sheets_on_dashboards,
            "orphan_sheets": orphan_sheets,
            "duplicate_name_groups": duplicate_name_groups,
        },
    }


def assign_ids(facts: dict, assigner: IdAssigner):
    """Attach stable IDs to every entity, in facts order."""
    workbook_id = assigner.assign(
        slugify(facts["workbook"]["name"]), "workbook"
    )
    facts["workbook"]["id"] = workbook_id
    for index, datasource in enumerate(facts["datasources"]):
        datasource["id"] = assigner.assign(
            f"{workbook_id}__ds__{slugify(datasource['name'])}",
            f"datasources[{index}]",
        )
    for index, parameter in enumerate(facts["parameters"]):
        parameter["id"] = assigner.assign(
            f"{workbook_id}__param__{slugify(parameter['caption'])}",
            f"parameters[{index}]",
        )
    for index, dashboard in enumerate(facts["dashboards"]):
        dashboard["id"] = assigner.assign(
            f"{workbook_id}__dash__{slugify(dashboard['name'])}",
            f"dashboards[{index}]",
        )
    sheet_ids = {}
    for index, worksheet in enumerate(facts["worksheets"]):
        sheet_id = assigner.assign(
            f"{workbook_id}__sheet__{slugify(worksheet['name'])}",
            f"worksheets[{index}]",
        )
        worksheet["id"] = sheet_id
        sheet_ids[worksheet["name"]] = sheet_id
        for calc_index, calculation in enumerate(worksheet["calculations"]):
            calculation["id"] = assigner.assign(
                f"{sheet_id}__calc__{slugify(calculation['caption'])}",
                f"worksheets[{index}].calculations[{calc_index}]",
            )
    dashboard_ids = {
        dashboard["name"]: dashboard["id"] for dashboard in facts["dashboards"]
    }
    return workbook_id, sheet_ids, dashboard_ids


def build_anomalies(facts: dict, notes: list[dict], sheet_ids: dict, dashboard_ids: dict, assigner: IdAssigner) -> list[dict]:
    """Convert extraction observations and v1-style warnings into typed records."""
    observed: list[dict] = []

    def record(code, affected_ids, evidence, count, status="observed"):
        observed.append(
            {
                "code": code,
                "rule_version": TOOL_VERSION,
                "affected_ids": affected_ids,
                "evidence": evidence,
                "count": count,
                "status": status,
            }
        )

    for note in notes:
        if note["code"] == "EMPTY_ZONE":
            dashboard_index = next(
                index
                for index, dashboard in enumerate(facts["dashboards"])
                if dashboard["id"] == dashboard_ids[note["dashboard"]]
            )
            record(
                "EMPTY_ZONE",
                [dashboard_ids[note["dashboard"]]],
                [f"dashboards[{dashboard_index}].layout"],
                note["count"],
            )
        elif note["code"] == "UNRECOGNIZED_ZONE":
            dashboard_index = next(
                index
                for index, dashboard in enumerate(facts["dashboards"])
                if dashboard["id"] == dashboard_ids[note["dashboard"]]
            )
            record(
                "UNRECOGNIZED_ZONE",
                [dashboard_ids[note["dashboard"]]],
                [f"dashboards[{dashboard_index}].layout"],
                note["count"],
            )

    duplicate_records = []
    for group in facts["derived"]["duplicate_name_groups"]:
        affected = [sheet_ids[name] for name in group["sheets"]]
        duplicate_records.append(
            {
                "code": "DUPLICATE_SHEET_NAME",
                "rule_version": TOOL_VERSION,
                "affected_ids": affected,
                "evidence": ["derived.duplicate_name_groups"],
                "count": len(group["sheets"]),
                "status": "observed",
            }
        )
    observed.extend(duplicate_records)

    orphan_ids = [sheet_ids[name] for name in facts["derived"]["orphan_sheets"]]
    if orphan_ids:
        record(
            "ORPHAN_SHEET",
            orphan_ids,
            ["derived.orphan_sheets"],
            len(orphan_ids),
        )

    for collision in assigner.collisions:
        record(
            "ID_COLLISION",
            [collision["final"]],
            [collision["evidence"]],
            1,
        )

    for note in notes:
        if note["code"] == "MULTIPLE_TWB_ENTRIES":
            record("MULTIPLE_TWB_ENTRIES", [], ["extraction.warnings"], note["count"])
        elif note["code"] == "STORY_NOT_INVENTORIED":
            record(
                "STORY_NOT_INVENTORIED",
                [],
                ["extraction.warnings"],
                note["count"],
                status="out_of_scope",
            )

    for code in ("EMPTY_ZONE", "UNRECOGNIZED_ZONE", "DUPLICATE_SHEET_NAME", "ORPHAN_SHEET"):
        if not any(entry["code"] == code for entry in observed):
            record(code, [], [], 0, status="not_found")

    return observed


def build_completeness(facts: dict, expected: dict) -> list[dict]:
    records = []
    for section in ("dashboards", "worksheets", "parameters", "datasources"):
        found = len(facts[section])
        skipped = max(0, expected[section] - found)
        entry = {
            "section": section,
            "expected": expected[section],
            "found": found,
            "skipped": skipped,
            "out_of_scope": 0,
            "status": "complete" if skipped == 0 else "partial",
        }
        if entry["status"] == "partial":
            entry["reason_code"] = "section_parse_skipped"
        records.append(entry)
    return records


# ---------------------------------------------------------------------------
# YAML emission (standard library only)
# ---------------------------------------------------------------------------


SAFE_SCALAR_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ ./()+,@\-:|\[\]]*")
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
    if ": " in value or value.endswith(":") or " #" in value:
        return False
    return True


def quote_scalar(value: str) -> str:
    out = value.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    out = re.sub(r"[\x00-\x1f]", lambda match: "\\u%04x" % ord(match.group()), out)
    return '"' + out + '"'


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
    workbook_name = value.get("workbook", {}).get("name", "unknown workbook")
    header = [
        f"# workbook-facts for {workbook_name}",
        "# Generated by dia-tableau-workbook-intake. Deterministic extraction; do not hand-edit.",
    ]
    return "\n".join(header + render_dict(value, 0)) + "\n"


# ---------------------------------------------------------------------------
# Command line entry point
# ---------------------------------------------------------------------------


def build_summary(facts: dict, output_path: Path):
    return {
        "schema_version": facts["schema_version"],
        "workbook": facts["workbook"]["name"],
        "workbook_id": facts["workbook"]["id"],
        "container": facts["extraction"]["container"],
        "dashboards": len(facts["dashboards"]),
        "worksheets": len(facts["worksheets"]),
        "sheets_on_dashboards": len(facts["derived"]["sheets_on_dashboards"]),
        "orphan_sheets": len(facts["derived"]["orphan_sheets"]),
        "parameters": len(facts["parameters"]),
        "calculations": sum(
            len(worksheet.get("calculations", []))
            for worksheet in facts["worksheets"]
        ),
        "output": str(output_path),
        "warnings": facts["extraction"]["warnings"],
        "anomalies_by_code": {
            code: sum(1 for record in facts["anomalies"] if record["code"] == code)
            for code in sorted({record["code"] for record in facts["anomalies"]})
        },
        "completeness": {
            record["section"]: record["status"] for record in facts["completeness"]
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Extract deterministic facts from a Tableau workbook package "
            "or workbook XML."
        ),
    )
    parser.add_argument(
        "--input", required=True,
        help="absolute path to the .twbx or .twb file",
    )
    parser.add_argument(
        "--output", required=True,
        help="absolute path for workbook-facts.yaml",
    )
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

    warnings: list[str] = []
    notes: list[dict] = []
    expected: dict = {}
    try:
        raw = source.read_bytes()
        xml_text, container, entry = load_workbook_document(raw, warnings, notes)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ExtractionError(f"workbook XML is malformed: {exc}") from exc
        if local_name(root.tag) != "workbook":
            raise ExtractionError("input XML root element is not <workbook>")
        facts = parse_workbook(root, warnings, notes, expected)
        facts["workbook"]["name"] = source.stem
        facts["extraction"]["container"] = container
        facts["extraction"]["entry"] = entry
        extracted_at = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        facts["extraction"]["timestamp"] = extracted_at
        input_sha256 = hashlib.sha256(raw).hexdigest()
        facts["provenance"] = build_provenance(
            input_sha256, extracted_at, container, entry, str(source)
        )
        assigner = IdAssigner()
        _, sheet_ids, dashboard_ids = assign_ids(facts, assigner)
        facts["anomalies"] = build_anomalies(
            facts, notes, sheet_ids, dashboard_ids, assigner
        )
        facts["completeness"] = build_completeness(facts, expected)
        facts["interpretation_inputs"] = {"dashboard_purposes": [], "sheet_roles": []}
        facts = {
            key: facts[key]
            for key in (
                "schema_version",
                "provenance",
                "workbook",
                "extraction",
                "datasources",
                "parameters",
                "dashboards",
                "worksheets",
                "derived",
                "completeness",
                "anomalies",
                "interpretation_inputs",
            )
        }
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
