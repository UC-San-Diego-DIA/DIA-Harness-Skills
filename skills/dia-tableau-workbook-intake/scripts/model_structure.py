"""Extract recorded Tableau model structure without queries or data access.

Object-graph tables are logical tables. Connection and object-property relation
trees are retained separately, including extract-context duplicates. Configured
endpoint settings and cached null flags are evidence, never database tests.
"""
from __future__ import annotations

def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def children(node, name):
    return [item for item in node if local_name(item.tag) == name]


def first(node, name):
    return next(iter(children(node, name)), None)


def text(node, name):
    found = first(node, name)
    return "".join(found.itertext()) if found is not None else None


def xml_record(node):
    """Namespace-neutral expression tree, with text preserved exactly."""
    if node is None:
        return None
    return {"tag": local_name(node.tag), "attributes": dict(sorted(node.attrib.items())),
            "text": node.text if node.text and node.text.strip() else None,
            "children": [xml_record(item) for item in node]}


def extract_model_structure(root, datasources):
    """Attach a version-1 structural inventory after existing IDs are assigned."""
    container = first(root, "datasources")
    declarations = children(container, "datasource") if container is not None else []
    for source in datasources:
        source_xml = next((item for item in declarations if item.get("name") == source["name"]), None)
        model = {"scope": "workbook_metadata_only", "logical_tables": [], "relations": [],
                 "relationships": [], "column_metadata": [], "gaps": []}
        source["model_structure"] = model
        prefix = source["id"] + "__model__"

        def identifier(kind, number):
            return prefix + kind + "-" + str(number + 1)

        def gap(code, message, evidence):
            model["gaps"].append({"id": identifier("gap", len(model["gaps"])),
                                  "code": code, "message": message, "evidence": [evidence]})

        if source_xml is None:
            gap("NO_DATASOURCE_DECLARATION", "Only worksheet dependency metadata is available.", "datasources")
            continue
        source_index = declarations.index(source_xml)
        source_path = f"datasources/datasource[{source_index}]"
        paths = {}

        def index_paths(node, path):
            paths[id(node)] = path
            counts = {}
            for item in node:
                tag = local_name(item.tag)
                number = counts.get(tag, 0)
                counts[tag] = number + 1
                index_paths(item, f"{path}/{tag}[{number}]")

        index_paths(source_xml, source_path)
        object_nodes = [node for node in source_xml.iter() if local_name(node.tag) == "object"]
        object_ids = {}
        for number, node in enumerate(object_nodes):
            logical_id = identifier("logical", number)
            recorded_id = node.get("id")
            if recorded_id in object_ids:
                gap("DUPLICATE_OBJECT_ID", "Multiple logical objects record the same object ID.", paths[id(node)])
            object_ids[recorded_id] = logical_id
            model["logical_tables"].append({"id": logical_id, "object_id": recorded_id,
                "caption": node.get("caption"), "relation_ids": [], "evidence": [paths[id(node)]]})

        parents = {id(item): node for node in source_xml.iter() for item in node}
        relation_ids = {}
        for node in source_xml.iter():
            if local_name(node.tag) == "relation":
                relation_ids[id(node)] = identifier("relation", len(relation_ids))
        for node in source_xml.iter():
            if local_name(node.tag) != "relation":
                continue
            ancestor = parents.get(id(node))
            logical_id = None
            context = "connection"
            parent_relation = None
            while ancestor is not None:
                tag = local_name(ancestor.tag)
                if tag == "relation" and parent_relation is None:
                    parent_relation = relation_ids[id(ancestor)]
                if tag == "properties":
                    context = ancestor.get("context", "")
                if tag == "extract" and context == "connection":
                    context = "extract"
                if tag == "object":
                    logical_id = object_ids.get(ancestor.get("id"))
                    break
                ancestor = parents.get(id(ancestor))
            relation_type = node.get("type")
            record = {"id": relation_ids[id(node)], "logical_table_id": logical_id,
                "parent_relation_id": parent_relation, "context": context,
                "type": relation_type, "name": node.get("name"), "table": node.get("table"),
                "connection": node.get("connection"), "join_type": node.get("join"),
                "attributes": dict(sorted(node.attrib.items())),
                "clauses": [xml_record(item) for item in node if local_name(item.tag) in ("clause", "expression", "columns", "union")],
                "text": node.text if node.text and node.text.strip() else None,
                "evidence": [paths[id(node)]]}
            model["relations"].append(record)
            if logical_id:
                next(item for item in model["logical_tables"] if item["id"] == logical_id)["relation_ids"].append(record["id"])
            if relation_type not in ("table", "join", "union", "collection", "text"):
                gap("UNSUPPORTED_RELATION_TYPE", f"Relation type {relation_type!r} is retained without interpretation.", paths[id(node)])
        for number, node in enumerate(item for item in source_xml.iter() if local_name(item.tag) == "relationship"):
            endpoints = []
            for endpoint in node:
                if local_name(endpoint.tag) not in ("first-end-point", "second-end-point"):
                    continue
                recorded_id = endpoint.get("object-id")
                resolved = object_ids.get(recorded_id)
                endpoints.append({"side": local_name(endpoint.tag), "object_id": recorded_id,
                    "logical_table_id": resolved, "configured_settings": dict(sorted(endpoint.attrib.items())),
                    "evidence": [paths[id(endpoint)]]})
                if resolved is None:
                    gap("UNRESOLVED_RELATIONSHIP_ENDPOINT", "Relationship endpoint has no matching logical object.", paths[id(endpoint)])
            model["relationships"].append({"id": identifier("relationship", number),
                "attributes": dict(sorted(node.attrib.items())), "endpoints": endpoints,
                "expressions": [xml_record(item) for item in node if local_name(item.tag) in ("expression", "clause")],
                "evidence": [paths[id(node)]]})
            if len(endpoints) != 2:
                gap("UNSUPPORTED_RELATIONSHIP_ENDPOINTS", "Relationship does not record exactly two recognized endpoints.", paths[id(node)])
        fields = {field["name"]: field["id"] for field in source.get("fields", [])}
        for node in source_xml.iter():
            if local_name(node.tag) != "metadata-record" or node.get("class") not in ("column", "measure"):
                continue
            name = text(node, "local-name")
            object_id = text(node, "object-id")
            raw_object_id = object_id.strip("[]") if object_id else None
            nullable = text(node, "nullable")
            if nullable is None:
                nullable = node.get("nullable")
            model["column_metadata"].append({"id": identifier("column", len(model["column_metadata"])),
                "field_id": fields.get(name), "name": name, "remote_name": text(node, "remote-name"),
                "parent_name": text(node, "parent-name"), "family": text(node, "family"),
                "object_id": object_id, "logical_table_id": object_ids.get(raw_object_id),
                "source_declared_nullable": nullable,
                "cached_contains_null": text(node, "contains-null"),
                "evidence": [paths[id(node)]]})
        if not model["logical_tables"]:
            gap("NO_LOGICAL_OBJECT_GRAPH", "No logical-table object graph is recorded; physical relations do not establish a universal dataset grain.", source_path)
        if not model["relations"]:
            gap("NO_RELATIONS_RECORDED", "No physical relation tree is recorded; published-source internals may be unavailable.", source_path)


def validate_model_structure(facts):
    """Check optional extension integrity in addition to its JSON Schema."""
    violations = []
    present = ["model_structure" in source for source in facts.get("datasources", [])]
    if facts.get("model_metadata_version") != 1:
        if any(present):
            violations.append({"path": "$.model_metadata_version", "code": "MODEL_VERSION_REQUIRED",
                               "message": "Model structure requires model_metadata_version: 1."})
        return violations
    seen = set()
    for index, source in enumerate(facts.get("datasources", [])):
        model = source.get("model_structure")
        path = f"$.datasources[{index}].model_structure"
        if not isinstance(model, dict):
            violations.append({"path": path, "code": "MODEL_STRUCTURE_REQUIRED", "message": "Every data source requires model_structure."})
            continue
        tables = {item.get("id") for item in model.get("logical_tables", [])}
        relations = {item.get("id") for item in model.get("relations", [])}
        fields = {item.get("id") for item in source.get("fields", [])}

        def reference(value, choices, location):
            if value is not None and value not in choices:
                violations.append({"path": location, "code": "MODEL_UNKNOWN_REFERENCE", "message": "Reference does not exist in this data source."})

        for section in ("logical_tables", "relations", "relationships", "column_metadata", "gaps"):
            for number, record in enumerate(model.get(section, [])):
                location = f"{path}.{section}[{number}]"
                identifier = record.get("id")
                if not identifier or identifier in seen or not identifier.startswith(source["id"] + "__model__"):
                    violations.append({"path": location + ".id", "code": "MODEL_ID_INVALID", "message": "Model IDs must be unique and scoped to their datasource."})
                seen.add(identifier)
                reference(record.get("logical_table_id"), tables, location + ".logical_table_id")
                reference(record.get("parent_relation_id"), relations, location + ".parent_relation_id")
                reference(record.get("field_id"), fields, location + ".field_id")
                for relation_id in record.get("relation_ids", []):
                    reference(relation_id, relations, location + ".relation_ids")
                for endpoint in record.get("endpoints", []):
                    reference(endpoint.get("logical_table_id"), tables, location + ".endpoints")
    return violations

