#!/usr/bin/env python3
"""Extract deterministic facts from a Tableau workbook package or workbook XML."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1


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


def load_workbook_document(raw: bytes, warnings: list[str]):
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


def zone_entry(zone, worksheet_names):
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
        return {
            "kind": "filter",
            "source_sheet": name,
            "field": zone.get("param", ""),
            "mode": zone.get("mode", ""),
            "show_apply": zone.get("show-apply", "") in ("true", "1"),
            "values": zone.get("values", ""),
        }
    if zone_type in ("color", "size", "shape"):
        return {
            "kind": "legend",
            "legend_kind": zone_type,
            "source_sheet": name,
            "field": zone.get("param", ""),
        }
    if zone_type == "paramctrl":
        return {
            "kind": "parameter",
            "parameter": zone.get("param", ""),
            "caption": zone.get("caption", ""),
        }
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


def parse_dashboard(dashboard, worksheet_names, warnings) -> dict:
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
            entry = zone_entry(zone, worksheet_names)
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
    if empty_zones:
        warnings.append(f"dashboard '{name}' has {empty_zones} empty zones")

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


def parse_worksheet(worksheet) -> dict:
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
                filters.append(
                    {
                        "column": sheet_filter.get("column", ""),
                        "class": sheet_filter.get("class", ""),
                    }
                )

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
        encodings.append({"attr": attribute, "field": field})

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


def parse_workbook(root, warnings: list[str]) -> dict:
    datasources = []
    parameters = []
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
    worksheets_element = child(root, "worksheets")
    if worksheets_element is not None:
        for worksheet in children(worksheets_element, "worksheet"):
            worksheets.append(parse_worksheet(worksheet))
            worksheet_names.append(worksheet.get("name", ""))

    dashboards = []
    dashboards_element = child(root, "dashboards")
    if dashboards_element is not None:
        for dashboard in children(dashboards_element, "dashboard"):
            dashboards.append(parse_dashboard(dashboard, worksheet_names, warnings))

    if child(root, "stories") is not None:
        warnings.append("workbook contains stories; story sheets are not inventoried")

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
        "workbook": facts["workbook"]["name"],
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
    try:
        raw = source.read_bytes()
        xml_text, container, entry = load_workbook_document(raw, warnings)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ExtractionError(f"workbook XML is malformed: {exc}") from exc
        if local_name(root.tag) != "workbook":
            raise ExtractionError("input XML root element is not <workbook>")
        facts = parse_workbook(root, warnings)
        facts["workbook"]["name"] = source.stem
        facts["extraction"]["container"] = container
        facts["extraction"]["entry"] = entry
        facts["extraction"]["timestamp"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
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
