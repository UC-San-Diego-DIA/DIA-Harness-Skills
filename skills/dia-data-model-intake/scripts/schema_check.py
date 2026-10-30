"""Hand-written validator for the JSON Schema subset used by
references/model-facts.schema.json. Standard library only; no pip installs.

Supported keywords: $ref (internal), type, const, enum, required, properties,
additionalProperties, items, minItems, maxItems, minLength, maxLength, pattern,
anyOf, allOf. Unknown keywords are ignored.
"""

from __future__ import annotations

import re


class SchemaError(Exception):
    """Raised when the schema itself cannot be read."""


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported $ref: {ref}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node[part]
        else:
            raise SchemaError(f"cannot resolve $ref: {ref}")
    return node


def _type_matches(instance, expected):
    if expected == "null":
        return instance is None
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "object":
        return isinstance(instance, dict)
    raise SchemaError(f"unsupported type keyword: {expected}")


def _validate(instance, schema, root, path, violations):
    if schema is True:
        return
    if schema is False:
        violations.append({
            "path": path, "keyword": "false schema", "message": "value is not allowed",
        })
        return
    if not isinstance(schema, dict):
        raise SchemaError(f"schema must be an object at {path}")

    if "$ref" in schema:
        _validate(instance, _resolve_ref(root, schema["$ref"]), root, path, violations)
        return

    if "type" in schema:
        expected = schema["type"]
        expected_list = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(instance, item) for item in expected_list):
            violations.append({
                "path": path,
                "keyword": "type",
                "message": f"expected {' or '.join(expected_list)}, found {type(instance).__name__}",
            })
            return

    if "const" in schema and instance != schema["const"]:
        violations.append({
            "path": path,
            "keyword": "const",
            "message": f"expected {schema['const']!r}, found {instance!r}",
        })

    if "enum" in schema and instance not in schema["enum"]:
        violations.append({
            "path": path,
            "keyword": "enum",
            "message": f"value {instance!r} is not one of {schema['enum']}",
        })

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            violations.append({
                "path": path,
                "keyword": "minLength",
                "message": f"length {len(instance)} is below {schema['minLength']}",
            })
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            violations.append({
                "path": path,
                "keyword": "maxLength",
                "message": f"length {len(instance)} is above {schema['maxLength']}",
            })
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            violations.append({
                "path": path,
                "keyword": "pattern",
                "message": f"value {instance!r} does not match {schema['pattern']!r}",
            })

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            violations.append({
                "path": path,
                "keyword": "minItems",
                "message": f"expected at least {schema['minItems']} items, found {len(instance)}",
            })
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            violations.append({
                "path": path,
                "keyword": "maxItems",
                "message": f"expected at most {schema['maxItems']} items, found {len(instance)}",
            })
        items_schema = schema.get("items")
        if items_schema is not None:
            for position, item in enumerate(instance):
                _validate(item, items_schema, root, f"{path}[{position}]", violations)

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                violations.append({
                    "path": path,
                    "keyword": "required",
                    "message": f"missing required property '{name}'",
                })
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for name in instance:
                if name not in properties:
                    violations.append({
                        "path": path,
                        "keyword": "additionalProperties",
                        "message": f"unexpected property '{name}'",
                    })
        elif isinstance(additional, dict):
            for name, value in instance.items():
                if name not in properties:
                    _validate(value, additional, root, f"{path}.{name}", violations)
        for name, value in instance.items():
            if name in properties:
                _validate(value, properties[name], root, f"{path}.{name}", violations)

    if "anyOf" in schema:
        branch_violations = []
        for branch in schema["anyOf"]:
            branch_violations = []
            _validate(instance, branch, root, path, branch_violations)
            if not branch_violations:
                break
        if branch_violations:
            violations.append({
                "path": path,
                "keyword": "anyOf",
                "message": "value does not match any allowed variant",
            })

    if "allOf" in schema:
        for branch in schema["allOf"]:
            _validate(instance, branch, root, path, violations)


def validate(instance, schema):
    """Return a list of violation dicts for the instance against the schema."""
    if not isinstance(schema, dict):
        raise SchemaError("top-level schema must be an object")
    violations = []
    _validate(instance, schema, schema, "$", violations)
    return violations
