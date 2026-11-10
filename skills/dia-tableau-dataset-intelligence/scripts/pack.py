#!/usr/bin/env python3
"""Build, validate, and render one local Tableau Dataset Intelligence Pack."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import pack_runtime as runtime
import glossary
import model_spec
import proposals

ASSETS = {
    "dictionary": ("data-dictionary.yaml", None),
    "model": ("data-model.yaml", "data-model.schema.json"),
    "glossary": ("business-glossary.yaml", "business-glossary.schema.json"),
    "metrics": ("metrics.yaml", "metrics.schema.json"),
    "questions": ("questions.yaml", "questions.schema.json"),
}
VIEWS = ("README.md", "data-dictionary.md", "data-dictionary.csv", "data-model.md",
         "business-glossary.md", "metrics.md", "questions.md")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"Path must be absolute: {value}")
    return path.resolve()


def protect_library(output):
    source_root = runtime.SKILL.parent.parent
    protected = source_root if (source_root / "scripts" / "install-skill.ps1").is_file() else runtime.SKILL.parent
    if output.is_relative_to(protected):
        raise ValueError("Dataset artifacts must be outside the source/installed skill library.")


def within(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Pack references must stay inside the pack directory: " + relative)
    return path


def assets(root):
    return {key: runtime.load(root / filename) for key, (filename, _) in ASSETS.items()}


def manifest(root, dataset_id, name, domain, description=None, model_facts=None):
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", dataset_id):
        raise ValueError("Dataset ID must use lowercase words separated by dots or hyphens.")
    root = root.resolve()
    dictionary = runtime.load(root / "data-dictionary.yaml")
    field_facts = runtime.dictionary.facts_path(dictionary, root / "data-dictionary.yaml")
    if not field_facts.is_relative_to(root):
        raise ValueError("Keep source facts inside the pack so it can be moved as a unit.")
    structural = Path(model_facts or (root / "evidence" / "workbook-model-facts.yaml")).resolve()
    if not structural.is_file():
        structural = field_facts
    if not structural.is_relative_to(root):
        raise ValueError("Model facts must stay inside the pack directory.")
    facts = runtime.dictionary.verify_facts(field_facts)
    structure_facts = runtime.dictionary.verify_facts(structural)
    source_hash = facts["provenance"]["input_sha256"]
    if structure_facts["provenance"]["input_sha256"] != source_hash:
        raise ValueError("Field and model facts belong to different workbook snapshots.")
    result = {
        "schema_version": 1, "document_type": "dataset_intelligence_pack",
        "dataset_id": dataset_id, "name": name, "domain": domain,
        "description": description, "business_owner": None, "technical_owner": None,
        "status": "draft", "data_verification": "not_tested", "reviewed": False,
        "build_state": "scaffold", "created_at": now(), "updated_at": now(),
        "source": {
            "input_name": Path(facts["provenance"]["input_file"]).name,
            "format": facts["provenance"]["container"], "workbook_sha256": source_hash,
            "facts": {"path": field_facts.relative_to(root).as_posix(), "sha256": runtime.digest(field_facts)},
            "model_facts": {"path": structural.relative_to(root).as_posix(), "sha256": runtime.digest(structural)},
        },
        "assets": [{"kind": key, "path": filename, "schema_version": dictionary["schema_version"] if key == "dictionary" else 1,
                    "sha256": None} for key, (filename, _) in ASSETS.items()],
        "generated_views": [],
    }
    profile_path = root / "evidence" / "value-profile.yaml"
    if profile_path.exists():
        import value_profiler
        profile = runtime.load(profile_path)
        if value_profiler.validate(profile, source_hash):
            raise ValueError("Invalid value-profile evidence for this workbook snapshot.")
        result["source"]["value_profile"] = {
            "path": value_profiler.PROFILE_PATH, "sha256": runtime.digest(profile_path),
            "extract_sha256": profile["provenance"]["extract_sha256"],
        }
        result["data_verification"] = "profiled"
    return result


def initialize(source, root, dataset_id, name, domain, profile_values=False):
    protect_library(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Use a new or empty output directory; existing packs are never replaced.")
    root.mkdir(parents=True, exist_ok=True)
    facts_path = root / "evidence" / "workbook-facts.yaml"
    with redirect_stdout(io.StringIO()):
        result = runtime.dictionary.intake.main(["--input", str(source), "--output", str(facts_path)])
    if result:
        raise ValueError("Workbook extraction failed; no enrichment or alternate extraction was attempted.")
    facts = runtime.dictionary.verify_facts(facts_path)
    if facts.get("model_metadata_version") != 1:
        raise ValueError("Fresh intake model_metadata_version 1 is required. Reinstall the pack skill.")
    if profile_values:
        import value_profiler
        value_profiler.profile(source, root, facts["provenance"]["input_sha256"])
    dictionary = runtime.dictionary.seed(facts, facts_path, root / "data-dictionary.yaml")
    model = model_spec.seed(facts, dataset_id)
    terms = glossary.seed(dictionary, dataset_id)
    metrics = proposals.seed_metrics(dictionary, model, terms, dataset_id)
    questions = proposals.seed_questions(dictionary, model, terms, metrics, dataset_id)
    for key, value in (("dictionary", dictionary), ("model", model), ("glossary", terms), ("metrics", metrics), ("questions", questions)):
        runtime.write_yaml(root / ASSETS[key][0], value)
    runtime.write_yaml(root / "dataset.yaml", manifest(root, dataset_id, name or source.stem, domain, model_facts=facts_path))


def validate(root, require_sealed=None):
    issues = []

    def fail(path, message):
        issues.append({"path": path, "message": message})

    data = runtime.load(root / "dataset.yaml")
    issues += runtime.schema_issues(data, "dataset.schema.json")
    if issues:
        return issues
    if not data["reviewed"] or not data["description"] or not data["description"].strip():
        fail("dataset.yaml", "Complete the pack identity/context review and description before finalizing.")
    for key in ("created_at", "updated_at"):
        try:
            if datetime.fromisoformat(data[key]).utcoffset() is None:
                raise ValueError("timezone missing")
        except ValueError:
            fail("dataset.yaml." + key, "Use an ISO 8601 timestamp with a timezone.")
    profile_ref = data["source"].get("value_profile")
    expected_verification = "profiled" if profile_ref else "not_tested"
    if data["data_verification"] != expected_verification:
        fail("dataset.yaml.data_verification", "Data verification must match the presence of value-profile evidence.")
    if (root / "evidence/value-profile.yaml").exists() != bool(profile_ref):
        fail("source.value_profile", "Value-profile evidence and its manifest reference must both be present.")
    if profile_ref:
        import value_profiler
        if profile_ref["path"] != value_profiler.PROFILE_PATH:
            fail("source.value_profile", "Use the fixed evidence/value-profile.yaml path.")
        profile_path = within(root, profile_ref["path"])
        if runtime.digest(profile_path) != profile_ref["sha256"]:
            fail("source.value_profile", "Immutable value-profile evidence has changed; rebuild from the workbook.")
        else:
            profile = runtime.load(profile_path)
            issues += value_profiler.validate(profile, data["source"]["workbook_sha256"])
            if not issues and profile["provenance"]["extract_sha256"] != profile_ref["extract_sha256"]:
                fail("source.value_profile", "Extract hash differs from the value-profile provenance.")
    if require_sealed is True and data["build_state"] != "complete":
        fail("dataset.yaml.build_state", "Finalize the reviewed pack before distributing it.")
    facts = {}
    for name in ("facts", "model_facts"):
        reference = data["source"][name]
        path = within(root, reference["path"])
        if runtime.digest(path) != reference["sha256"]:
            fail("source." + name, "Extracted evidence has changed; rebuild from the source workbook.")
            continue
        facts[name] = runtime.dictionary.verify_facts(path)
        if facts[name]["provenance"]["input_sha256"] != data["source"]["workbook_sha256"]:
            fail("source." + name, "Evidence belongs to another workbook snapshot.")
    if issues:
        return issues
    records = data["assets"]
    if len(records) != len(ASSETS) or {item["kind"] for item in records} != set(ASSETS):
        fail("assets", "Exactly one dictionary, model, glossary, metric catalog, and question catalog are required.")
        return issues
    for record in records:
        filename = ASSETS[record["kind"]][0]
        if record["path"] != filename:
            fail("assets", "Asset paths must use their fixed pack filenames.")
        if data["build_state"] == "complete" and record["sha256"] != runtime.digest(root / filename):
            fail(filename, "Asset changed after finalization; preserve this pack and create a new reviewed revision.")
    if issues:
        return issues
    content = assets(root)
    dictionary = content["dictionary"]
    if not isinstance(dictionary, dict) or dictionary.get("schema_version") != 2:
        fail("data-dictionary.yaml", "Use the context-enriched schema-version-2 dictionary.")
        return issues
    dictionary_issues = runtime.dictionary.validate(dictionary, root / "data-dictionary.yaml", require_ready=True)
    issues.extend({**item, "asset": "data-dictionary.yaml"} for item in dictionary_issues)
    if dictionary_issues:
        return issues
    if runtime.dictionary.facts_path(dictionary, root / "data-dictionary.yaml") != within(root, data["source"]["facts"]["path"]):
        fail("data-dictionary.yaml.source.facts_path", "Dictionary evidence must match the manifest's portable field-facts reference.")
        return issues
    for record in records:
        if record["schema_version"] != content[record["kind"]].get("schema_version"):
            fail(record["path"], "Asset schema version differs from the manifest.")
    if dictionary["source"]["workbook_sha256"] != data["source"]["workbook_sha256"]:
        fail("data-dictionary.yaml", "Dictionary belongs to another workbook snapshot.")
    for key in ("model", "glossary", "metrics", "questions"):
        value = content[key]
        current = runtime.schema_issues(value, ASSETS[key][1])
        issues.extend({**item, "asset": ASSETS[key][0]} for item in current)
        if current:
            continue
        if value["dataset_id"] != data["dataset_id"] or value["source_workbook_sha256"] != data["source"]["workbook_sha256"]:
            fail(ASSETS[key][0], "Asset identity or source snapshot differs from the manifest.")
        if not value["reviewed"]:
            fail(ASSETS[key][0], "Complete the LLM interpretation review before finalizing.")
    if issues:
        return issues
    checks = (
        ("model", model_spec.validate(content["model"], facts["model_facts"])),
        ("glossary", glossary.validate(content["glossary"], dictionary)),
        ("metrics", proposals.validate_metrics(content["metrics"], dictionary, content["model"], content["glossary"])),
        ("questions", proposals.validate_questions(content["questions"], dictionary, content["model"], content["glossary"], content["metrics"])),
    )
    for key, current in checks:
        issues.extend({**item, "asset": ASSETS[key][0]} for item in current)
    if data["build_state"] == "complete":
        if len(data["generated_views"]) != len(VIEWS) or {item["path"] for item in data["generated_views"]} != set(VIEWS):
            fail("generated_views", "Every generated reader view must be recorded exactly once.")
        for record in data["generated_views"]:
            if runtime.digest(within(root, record["path"])) != record["sha256"]:
                fail(record["path"], "Generated view changed; edits belong in structured metadata.")
        if not issues:
            for filename, text in reader_views(data, content, root).items():
                if (root / filename).read_text(encoding="utf-8-sig") != text:
                    fail(filename, "Generated view no longer matches structured metadata and the current renderer.")
    return issues


def reader_views(manifest, content, root):
    dictionary = content["dictionary"]
    business = [field for source in dictionary["datasources"] for field in source["fields"] if field["category"] == "business"]
    unresolved = sum(field["definition"]["text"] is None for field in business)
    metrics = content["metrics"]["metrics"]
    questions = content["questions"]["questions"]
    out = ["# " + runtime.md(manifest["name"]) + " Dataset Intelligence Pack", "",
           runtime.md(manifest["description"]), "",
           ("Status: draft. Business approval and data verification remain separate. Local extract values were profiled. "
            "Row/null counts are observations, not business-correctness tests. Metric proposals were not executed."
            if manifest["data_verification"] == "profiled" else
            "Status: draft. Business approval and data verification remain separate. No dataset values were read or calculations executed."), "",
           f"Dataset ID: {runtime.md(manifest['dataset_id'])}; domain: {runtime.md(manifest['domain'])}.", "",
           f"Business fields: {len(business)}; unresolved meanings: {unresolved}; glossary concepts: {len(content['glossary']['terms'])}; metric proposals: {len(metrics)}; analytical questions: {len(questions)}.", "",
           "| Analyst asset | Structured source | Readable view |", "| --- | --- | --- |",
           "| Identity and ownership | [dataset.yaml](dataset.yaml) | This page |",
           "| Field meanings | [data-dictionary.yaml](data-dictionary.yaml) | [Dictionary](data-dictionary.md), [CSV](data-dictionary.csv) |",
           "| Relationships, keys and grain | [data-model.yaml](data-model.yaml) | [Model and grain](data-model.md) |",
           "| Business terminology | [business-glossary.yaml](business-glossary.yaml) | [Glossary](business-glossary.md) |",
           "| Metric proposals | [metrics.yaml](metrics.yaml) | [Metrics](metrics.md) |",
           "| Analytical questions | [questions.yaml](questions.yaml) | [Questions](questions.md) |", "",
           "## Before using the pack", "",
           "- Read the model and grain proposals before selecting aggregations.",
           "- Review definition proposals and clarify unresolved identifiers, dates, units, codes, and business rules.",
           "- Conditional questions retain the unresolved requirements of their metric proposals.",
           "- The workbook's configured keys/cardinality/null flags do not constitute successful data tests.",
           "- Owners are unknown until supplied. Approving a business definition does not certify dataset correctness.",
           "- Update YAML first. Preserve this completed pack and create a new reviewed pack for subsequent revisions.",
           "- Keep evidence and original revision files with the pack. Sharing only Markdown loses provenance and validation inputs.", "",
           "## Reproducibility", "",
           "Source: " + runtime.md(manifest["source"]["input_name"]) + ". Workbook SHA-256: " + manifest["source"]["workbook_sha256"],
           "Created: " + runtime.md(manifest["created_at"]) + ". Updated: " + runtime.md(manifest["updated_at"]), "",
           "Reader files are generated from the six versioned YAML assets. CSV text cells beginning with formula characters are prefixed with an apostrophe for spreadsheet viewing; canonical YAML values are unchanged.", ""]
    return {
        "README.md": "\n".join(out),
        "data-dictionary.md": runtime.dictionary.render(dictionary, root / "data-dictionary.yaml"),
        "data-dictionary.csv": glossary.export_dictionary_csv(dictionary, content["model"]),
        "data-model.md": model_spec.render(content["model"]),
        "business-glossary.md": glossary.render(content["glossary"]),
        "metrics.md": proposals.render_metrics(content["metrics"]),
        "questions.md": proposals.render_questions(content["questions"]),
    }


def finalize(root):
    data = runtime.load(root / "dataset.yaml")
    if data.get("build_state") != "scaffold":
        raise ValueError("A completed pack is immutable; create a new reviewed pack revision.")
    current = validate(root)
    if current:
        raise ValueError("Pack validation failed: " + json.dumps(current))
    existing = [name for name in VIEWS if (root / name).exists()]
    if existing:
        raise ValueError("Reader files already exist; use a fresh output directory: " + ", ".join(existing))
    data["updated_at"] = now()
    views = reader_views(data, assets(root), root)
    for filename, text in views.items():
        runtime.write_new(root / filename, text)
    for record in data["assets"]:
        record["sha256"] = runtime.digest(root / record["path"])
    data["generated_views"] = [{"path": name, "sha256": runtime.digest(root / name)} for name in VIEWS]
    data["build_state"] = "complete"
    temporary = root / "dataset.finalizing.yaml"
    runtime.write_yaml(temporary, data)
    temporary.replace(root / "dataset.yaml")
    current = validate(root, require_sealed=True)
    if current:
        raise ValueError("Final output verification failed: " + json.dumps(current))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--input", required=True)
    init.add_argument("--output", required=True)
    init.add_argument("--profile-values", action="store_true",
                      help="Opt in to local read-only profiling of one packaged Hyper extract; requires tableauhyperapi.")
    for action in (init, sub.add_parser("assemble")):
        if action is not init:
            action.add_argument("--pack", required=True)
        action.add_argument("--dataset-id", required=True)
        action.add_argument("--name")
        action.add_argument("--domain", required=True)
    for command in ("validate", "finalize"):
        action = sub.add_parser(command)
        action.add_argument("--pack", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            root = absolute(args.output)
            initialize(absolute(args.input), root, args.dataset_id, args.name, args.domain, args.profile_values)
        else:
            root = absolute(args.pack)
            protect_library(root)
            if args.command == "assemble":
                dictionary = runtime.load(root / "data-dictionary.yaml")
                runtime.write_yaml(root / "dataset.yaml", manifest(root, args.dataset_id, args.name or dictionary["workbook"]["name"], args.domain))
            elif args.command == "finalize":
                finalize(root)
            else:
                current = validate(root, require_sealed=True)
                print(json.dumps({"valid": not current, "violations": current}, indent=2))
                return 2 if current else 0
        print(json.dumps({"command": args.command, "pack": str(root), "state": runtime.load(root / "dataset.yaml")["build_state"]}, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, runtime.dictionary.yaml_min.YamlError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
