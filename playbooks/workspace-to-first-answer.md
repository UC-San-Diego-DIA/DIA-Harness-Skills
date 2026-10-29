---
name: workspace-to-first-answer
pattern: pipeline
description: Create a fresh data-analysis workspace, link one source file into it, and answer ad hoc questions from that file with read-only SQL.
---

# Playbook: Workspace to first answer

Set up a local data-analysis workspace and reach the first defensible answer from one source file. Run this when analysis starts on a new project or a new file arrives; each later question runs against the same linked view.

## Sequence

1. `$dia-new-data-analysis-workspace` - one run per project. Creates the schema-1 workspace with immutable raw inputs, numbered pipeline scripts, dashboard-ready output, and `docs/transcripts/` for meeting records.
2. Place the dataset in `data/raw/`. The workspace skill never copies or creates data files, so the user performs this step between the two skill runs.
3. `$dia-analyze-local-data` - one run per file. Links the file into a read-only DuckDB view under `scratch/analysis/` and answers ad hoc questions from that view, recording every question and its SQL.

Variant: for a confirmed KPI artifact rather than ad hoc questions, run the business-questions-to-dashboard-mockup playbook instead; it creates the workspace as its own first step and stops at the mapping report when no mockup is needed. `$dia-kpi-data-mapping` inspects the dataset schema without linking it.

## Handoffs

- Step 3 refuses to run outside a schema-1 workspace, so create the workspace first and place exactly one `.csv` or `.xlsx` file under `data/raw/` before invoking it.
- The link records the file's hash. If the source file changes later, queries fail with a staleness error and the user confirms an explicit re-link; earlier answers stay associated with the link that produced them.
- Every question and its SQL are recorded in the analysis folder's `ANALYSIS.md`, so answers stay reviewable after the run ends.
