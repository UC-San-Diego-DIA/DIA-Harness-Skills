"""Read field declarations and cached schema metadata, never dataset values."""

from __future__ import annotations


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def children(node, tag):
    return [item for item in node if local_name(item.tag) == tag]


def first(node, tag):
    return next(iter(children(node, tag)), None)


def text(node, tag):
    item = first(node, tag)
    return "".join(item.itertext()) if item is not None else None


def column_attributes(column):
    description = first(column, "desc")
    if description is None:
        description = first(column, "description")
    calculation = first(column, "calculation")
    hidden = column.get("hidden")
    return {
        "caption": column.get("caption"),
        "datatype": column.get("datatype"),
        "role": column.get("role"),
        "type": column.get("type"),
        "hidden": {"true": True, "1": True, "false": False, "0": False}.get(hidden),
        "default_aggregation": column.get("aggregation"),
        "description": "".join(description.itertext()).strip() if description is not None else None,
        "calculation": {
            "class": calculation.get("class"), "formula": calculation.get("formula")
        } if calculation is not None else None,
    }


def extract_field_metadata(root, datasources):
    """Union fields by datasource and exact local name.

    Source declarations take precedence over worksheet caches, then connection
    metadata. Conflicting nonempty observations remain visible in the inventory.
    Parameter columns are deliberately excluded from dataset fields.
    """
    states = {}

    def source_state(name, scope="workbook_datasource"):
        if name not in states:
            states[name] = {"fields": {}, "parameters": set(), "skipped": 0, "scope": scope}
        return states[name]

    def observe(state, name, attributes, evidence, column=None, physical=None):
        if not name:
            state["skipped"] += 1
            return
        if name in state["parameters"]:
            return
        fields = state["fields"]
        if name not in fields:
            fields[name] = {
                "name": name,
                **{key: None for key in (
                    "caption", "datatype", "role", "type", "hidden",
                    "default_aggregation", "description", "calculation",
                )},
                "field_kind": "source", "aliases": [], "source_columns": [],
                "evidence": [], "conflicts": [],
            }
        field = fields[name]
        field["evidence"].append(evidence)
        for key, value in attributes.items():
            if value is None or value == "":
                continue
            if field[key] is None or field[key] == "":
                field[key] = value
            elif field[key] != value:
                field["conflicts"].append({"attribute": key, "evidence": evidence})
        if column is not None:
            aliases = first(column, "aliases")
            if aliases is not None:
                for alias in children(aliases, "alias"):
                    item = {"key": alias.get("key"), "value": alias.get("value")}
                    prior = next((entry for entry in field["aliases"] if entry["key"] == item["key"]), None)
                    if prior is None:
                        field["aliases"].append(item)
                    elif prior != item:
                        field["conflicts"].append({"attribute": "aliases", "evidence": evidence})
        if physical and any(value is not None for value in physical.values()):
            if physical not in field["source_columns"]:
                field["source_columns"].append(physical)
        if field["calculation"] is not None:
            field["field_kind"] = "calculated"

    root_sources = first(root, "datasources")
    declarations = children(root_sources, "datasource") if root_sources is not None else []
    for index, source in enumerate(declarations):
        state = source_state(source.get("name", ""))
        state["parameters"] = {
            col.get("name") for col in children(source, "column") if col.get("param-domain-type")
        }
        for col_index, column in enumerate(children(source, "column")):
            if column.get("param-domain-type"):
                continue
            observe(state, column.get("name"), column_attributes(column),
                    f"datasources/datasource[{index}]/column[{col_index}]", column)

    worksheets = first(root, "worksheets")
    sheets = children(worksheets, "worksheet") if worksheets is not None else []
    known_names = {source["name"] for source in datasources}
    for sheet_index, sheet in enumerate(sheets):
        dependencies = [node for node in sheet.iter() if local_name(node.tag) == "datasource-dependencies"]
        for dep_index, dependency in enumerate(dependencies):
            name = dependency.get("datasource", "")
            if not name:
                continue
            state = source_state(name, "worksheet_dependencies_only")
            if name not in known_names:
                datasources.append({"name": name, "caption": None})
                known_names.add(name)
            for col_index, column in enumerate(children(dependency, "column")):
                if column.get("param-domain-type"):
                    state["parameters"].add(column.get("name"))
                    continue
                observe(state, column.get("name"), column_attributes(column),
                        f"worksheets/worksheet[{sheet_index}]/datasource-dependencies[{dep_index}]/column[{col_index}]",
                        column)

    for index, source in enumerate(declarations):
        state = source_state(source.get("name", ""))
        records = [node for node in source.iter()
                   if local_name(node.tag) == "metadata-record" and node.get("class") == "column"]
        for record_index, record in enumerate(records):
            observe(state, text(record, "local-name"), {
                "datatype": text(record, "local-type"),
                "default_aggregation": text(record, "aggregation"),
            }, f"datasources/datasource[{index}]/metadata-record[{record_index}]", physical={
                "table": text(record, "parent-name"),
                "name": text(record, "remote-name"),
                "datatype": text(record, "remote-type"),
            })

    for source in datasources:
        state = source_state(source["name"])
        source["fields"] = [field for name, field in state["fields"].items()
                            if name not in state["parameters"]]
        conflicts = sum(bool(field["conflicts"]) for field in source["fields"])
        warnings = []
        if state["scope"] == "worksheet_dependencies_only":
            warnings.append("Only worksheet dependency metadata is available for this data source.")
        if not source["fields"] and source["name"] != "Parameters":
            warnings.append("No field definitions are recorded for this data source.")
        if state["skipped"]:
            warnings.append("Some field records have no local name and could not be inventoried.")
        if conflicts:
            warnings.append("Conflicting cached metadata exists; source declarations take precedence.")
        source["field_inventory"] = {
            "scope": state["scope"], "field_count": len(source["fields"]),
            "skipped_records": state["skipped"], "conflicting_fields": conflicts,
            "warnings": warnings,
        }
