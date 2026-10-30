#!/usr/bin/env python3
"""Migrate a schema-version-1 model-facts.yaml to schema version 2.

Reads the v1 artifact, re-derives the parse facts deterministically from the
recorded SQL text, and writes a new v2 artifact. The input file is never
modified, and no SQL is executed and no data source is contacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import extract_model_facts as emf
import yaml_min


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Migrate a schema-version-1 model-facts.yaml to schema version 2.",
    )
    parser.add_argument("--input", required=True, help="absolute path to the v1 model-facts.yaml")
    parser.add_argument("--output", required=True, help="absolute path for the v2 model-facts.yaml")
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

    try:
        raw_input = source.read_bytes()
        text = raw_input.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: could not read the input file: {exc}", file=sys.stderr)
        return 1
    try:
        facts = yaml_min.load(text)
    except yaml_min.YamlError as exc:
        print(f"Error: the input is not in the supported model-facts YAML subset: {exc}", file=sys.stderr)
        return 1
    if not isinstance(facts, dict) or "schema_version" not in facts:
        print("Error: the input does not look like a model-facts.yaml file.", file=sys.stderr)
        return 1
    if facts["schema_version"] != 1:
        print(
            f"Error: input has schema_version {facts['schema_version']!r}; "
            "this tool migrates version 1 only.",
            file=sys.stderr,
        )
        return 2

    extraction = facts.get("extraction") or {}
    container = extraction.get("container")
    source_file = extraction.get("source_file")
    if container not in ("xml-document", "zlib-archive") or not source_file:
        print(
            "Error: the input is missing a usable extraction block with a source_file "
            "and a supported container kind.",
            file=sys.stderr,
        )
        return 1

    warnings = []
    v1_model = facts.get("model") or {}
    model_name = v1_model.get("name") or "unknown model"
    catalog_items = facts.get("catalog_items") or []
    parameters = facts.get("parameters") or []
    output_columns = [dict(column) for column in facts.get("output_columns") or []]
    datasets = []
    for dataset in facts.get("datasets") or []:
        datasets.append({
            "name": dataset.get("name") or "unnamed",
            "type": dataset.get("type"),
            "data_source": dataset.get("data_source"),
            "sql": dataset.get("sql") or "",
        })
    emf.analyze_datasets(datasets, output_columns, parameters, warnings)

    source_sha256 = None
    recorded_source = Path(source_file)
    if recorded_source.is_file():
        try:
            source_sha256 = hashlib.sha256(recorded_source.read_bytes()).hexdigest()
        except OSError:
            source_sha256 = None
    if source_sha256 is None:
        emf.add_warning(
            warnings, "SOURCE_FILE_UNAVAILABLE", "info",
            f"the source model file could not be read to compute its SHA-256 hash: {source_file}",
        )
    provenance = {
        "source_file": str(source_file),
        "source_sha256": source_sha256,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extractor_version": emf.EXTRACTOR_VERSION,
        "container": container,
    }
    migration = {
        "source_facts_file": str(source),
        "source_facts_sha256": hashlib.sha256(raw_input).hexdigest(),
    }

    artifact = emf.build_v2_artifact(
        model_name=model_name,
        description=v1_model.get("description") or "",
        xdm_version=v1_model.get("xdm_version"),
        default_data_source=v1_model.get("default_data_source"),
        bi_publisher_build=v1_model.get("bi_publisher_build"),
        author=v1_model.get("author"),
        modified_at=v1_model.get("modified_at"),
        catalog_items=catalog_items,
        data_properties=facts.get("data_properties") or {},
        data_sources=facts.get("data_sources") or [],
        parameters=parameters,
        value_sets=facts.get("value_sets") or [],
        datasets=datasets,
        output_columns=output_columns,
        bursting=facts.get("bursting") or [],
        warnings=warnings,
        provenance=provenance,
        migration=migration,
    )
    try:
        emf.validate_artifact(artifact)
    except emf.ExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(emf.render_yaml(artifact), encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write the output file: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(emf.build_summary(artifact, output), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
