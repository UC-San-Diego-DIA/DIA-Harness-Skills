---
name: business-questions-to-dashboard-mockup
pattern: pipeline
description: Create a data-analysis workspace, extract confirmed business questions and KPIs from a requirements transcript, map them to the workspace dataset, and optionally render a UCSD-branded HTML dashboard mockup with mock data.
---

# Playbook: Business questions to dashboard mockup

Move one requirements conversation from raw transcript to confirmed business questions and KPIs, then to a declarative mapping of those KPIs against the project dataset. Run this at the start of an analysis project, before any pipeline work is scoped.

Stop after step 3 when the mapping report is the deliverable. Continue to step 4 when stakeholders should see what the mapped KPIs would look like on a dashboard before any pipeline work is built.

## Sequence

1. `$dia-new-data-analysis-workspace` - one run per project. Creates the schema-1 data-analysis workspace; the user places the dataset in `data/raw/` afterwards.
2. `$dia-transcript-to-kpis` - one run per conversation, inside the workspace. Saves the transcript in `docs/transcripts/` and, after the user confirms the draft, writes `docs/Business-Questions-and-KPIs-YYYY-MM-DD-<topic>.md` and `docs/kpi-facts.yaml`.
3. `$dia-kpi-data-mapping` - one run per dataset, inside the workspace. The user names the dataset; the skill re-validates the KPI artifact and the dataset, then writes `docs/KPI-Data-Mapping-YYYY-MM-DD-<topic>.md` naming the fields that supply each KPI, the calculations to build, and the data gaps.
4. `$dia-dashboard-mockup` - one run per mapping report, inside the workspace. The user confirms the panel outline; the skill renders `docs/Dashboard-Mockup-YYYY-MM-DD-<topic>.html` from the UCSD-branded template with mock data and explicit data-gap panels.

Variant: when no workspace exists yet, step 2 can run outside a workspace and saves its artifacts in the working directory. The mapping in step 3 is designed for a workspace dataset, so create the workspace first when mapping is expected. The mockup in step 4 follows its mapping report's location.

## Handoffs

- `kpi-facts.yaml` is the machine-readable contract between steps 2 and 3; step 3 re-validates its `schema_version: 1` before mapping anything.
- The mapping report is the contract between steps 3 and 4: every mock panel traces to one mapped KPI, and every data gap in the report renders as its own no-data panel rather than a missing chart.
- The mapping report is declarative documentation: it names fields and calculations but does not execute them. Building the metrics happens later through the workspace pipeline or ad hoc analysis, outside this playbook.
- The mockup never reads the dataset or executes the mapped calculations. Its numbers are mock placeholders, and the file says so on every panel and in the footer, so stakeholder review never mistakes a placeholder for a result.
- Data gaps from step 3 remain the follow-up list for stakeholders and source systems. Resolve them before building pipeline scripts, because a gap in the report means no dataset field supports that KPI component today.
