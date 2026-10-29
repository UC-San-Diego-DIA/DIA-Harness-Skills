---
name: data-model-to-documentation
pattern: fan-out
description: Extract facts from one Oracle BI Publisher data model, then profile its structure and draft analyst-facing documentation from the same facts file.
---

# Playbook: Data model to documentation

Move one Oracle BI Publisher data model from raw export to a structural profile and analyst-facing documentation. Run this when your team takes ownership of an existing data model or needs to document one for reference.

## Shared input

`$dia-data-model-intake` - one run per data model file. Accepts an `.xdm.catalog` archive, an `.xdm` file, or a data-model XML document. Produces a deterministic `model-facts.yaml` beside the model file. No SQL is executed and no data source is contacted.

## Fan-out branches

After the facts file exists, run either or both branches. Each consumes the same `model-facts.yaml`.

- `$dia-data-model-profiler` - produces `data-model-profile.md`: grain, filters and exclusions, hard-coded business logic, deduplication and join patterns, and source-table lineage. Recommended first because it surfaces structural findings that inform your review of the docs branch.
- `$dia-data-model-docs` - produces `overview.md`, `data-dictionary.md`, `business-questions.md`, and `when-to-use.md`. Requires analyst confirmation of grain, business questions, and gotchas before writing.

## Handoffs

- The profiler's grain and filter findings are evidence you can use when confirming the docs branch's grain and gotchas, but the two branches are independent: docs does not read the profiler output.
- Both branches consume the same facts file, so re-running intake with a new model version invalidates both outputs.
- The facts file is the single source of truth. If a fact appears wrong, rerun intake rather than hand-editing the facts or the outputs.
