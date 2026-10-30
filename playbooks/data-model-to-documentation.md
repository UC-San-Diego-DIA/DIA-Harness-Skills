---
name: data-model-to-documentation
pattern: pipeline
description: Extract facts from one Oracle BI Publisher data model, profile its structure, then draft analyst-facing documentation in sequence.
---

# Playbook: Data model to documentation

Move one Oracle BI Publisher data model from raw export to a structural profile and analyst-facing documentation. Run this when your team takes ownership of an existing data model or needs to document one for reference.

## Sequence

1. `$dia-data-model-intake` - one run per data model file. Accepts an `.xdm.catalog` archive, an `.xdm` file, or a data-model XML document. Produces a deterministic `model-facts.yaml` beside the model file. No SQL is executed and no data source is contacted.
2. `$dia-data-model-profiler` - one run per facts file. Produces `data-model-profile.md`: grain, filters and exclusions, hard-coded business logic, deduplication and join patterns, and source-table lineage. Read this before running docs because the structural findings inform the grain and gotcha confirmations.
3. `$dia-data-model-docs` - one run per facts file. Produces `overview.md`, `data-dictionary.md`, `kpis-and-questions.md`, and `when-to-use.md`. Reads the profiler output directly and cites its sections for grain, filters, join risk, and hard-coded logic instead of restating them. Requires analyst confirmation of candidate KPIs, business questions, and open questions before writing; when the user explicitly asks for draft mode, it writes all four files as candidates and records every open item in the overview register.

Variant: when only a quick structural understanding is needed, run steps 1 and 2. When only the documentation is needed, run steps 1 and 3.

## Handoffs

- The docs step reads the profiler output directly and links to its sections rather than restating grain, filters, join risk, or hard-coded logic, so each finding lives in exactly one document.
- All three steps consume the same model file lineage: intake produces the facts file that both downstream steps read. Re-running intake with a new model version invalidates both outputs.
- The facts file is the single source of truth. If a fact appears wrong, rerun intake rather than hand-editing the facts or the outputs.
