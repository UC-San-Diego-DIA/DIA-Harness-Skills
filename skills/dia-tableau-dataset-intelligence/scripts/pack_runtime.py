"""Locate the maintained dictionary/intake runtime, in source or bundled installs."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SKILL = HERE.parent


def dictionary_runtime():
    candidates = (
        HERE / "dependencies" / "dia-tableau-data-dictionary" / "scripts",
        SKILL.parent / "dia-tableau-data-dictionary" / "scripts",
    )
    for candidate in candidates:
        if (candidate / "data_dictionary.py").is_file():
            sys.path.insert(0, str(candidate))
            return importlib.import_module("data_dictionary")
    raise RuntimeError("Dictionary runtime is missing. Use the repository installer for this skill.")


dictionary = dictionary_runtime()


def load(path):
    return dictionary.load(Path(path))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def yaml_text(data):
    return dictionary.yaml_text(data).replace(
        "# Structured source for the generated data dictionary.",
        "# Structured Dataset Intelligence Pack asset. Edit metadata before rendering.", 1,
    )


def write_new(path, content):
    dictionary.write_new(Path(path), content)


def write_yaml(path, data):
    write_new(path, yaml_text(data))


def schema_issues(data, filename):
    schema = json.loads((SKILL / "references" / filename).read_text(encoding="utf-8-sig"))
    return dictionary.schema_check.validate(data, schema)


def md(value):
    return dictionary.md(value)
