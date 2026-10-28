---
name: business-questions-to-data-mapping
pattern: pipeline
description: Create a data-analysis workspace, extract confirmed business questions and KPIs from a requirements transcript, and map them to the workspace dataset.
---

# Playbook: Business questions to data mapping

Move one requirements conversation from raw transcript to confirmed business questions and KPIs, then to a declarative mapping of those KPIs against the project dataset. Run this at the start of an analysis project, before any pipeline work is scoped.

## Sequence

1. `$dia-new-data-analysis-workspace` - one run per project. Creates the schema-1 data-analysis workspace; the user places the dataset in `data/raw/` afterwards.
2. `$dia-transcript-to-kpis` - one run per conversation, inside the workspace. Saves the transcript in `docs/transcripts/` and, after the user confirms the draft, writes `docs/Business-Questions-and-KPIs-YYYY-MM-DD-<topic>.md` and `docs/kpi-facts.yaml`.
3. `$dia-kpi-data-mapping` - one run per dataset, inside the workspace. The user names the dataset; the skill re-validates the KPI artifact and the dataset, then writes `docs/KPI-Data-Mapping-YYYY-MM-DD-<topic>.md` naming the fields that supply each KPI, the calculations to build, and the data gaps.

Variant: when no workspace exists yet, step 2 can run outside a workspace and saves its artifacts in the working directory. The mapping in step 3 is designed for a workspace dataset, so create the workspace first when mapping is expected.

## Handoffs

- `kpi-facts.yaml` is the machine-readable contract between steps 2 and 3; step 3 re-validates its `schema_version: 1` before mapping anything.
- The mapping report's data gaps are the follow-up list for stakeholders and source systems. Resolve them before building pipeline scripts, because a gap in the report means no dataset field supports that KPI component today.
- The mapping report is declarative documentation: it names fields and calculations but does not execute them. Building the metrics happens later through the workspace pipeline or ad hoc analysis, outside this playbook.
