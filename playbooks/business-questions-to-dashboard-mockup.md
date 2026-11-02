---
name: business-questions-to-dashboard-mockup
pattern: pipeline
description: Create a data-analysis workspace, capture requested KPIs, map them to a dataset, optionally select separate recommendations, and render a labeled HTML dashboard mockup.
---

# Playbook: Business questions to dashboard mockup

Use one requirements conversation to identify requested business questions and
KPIs, map them to a dataset, and optionally review a dashboard prototype.
No KPI calculations or pipeline scripts are produced by this playbook.

## Sequence

1. `$dia-new-workspace` with the data-analysis layout. Open the resulting folder as the Harness project. Starting files move only when explicitly confirmed during setup. Otherwise place or copy the CSV into `data/raw/` and transcript into `docs/transcripts/` separately, before invoking the next skill. A shell directory change does not switch the Harness project.
2. `$dia-transcript-to-kpis` inside the workspace. A supplied transcript stays at its existing path. Review one complete draft, then save `docs/Business-Questions-and-KPIs-YYYY-MM-DD-<topic>.md` and `docs/kpi-facts.yaml`. Deferred ideas remain separate from the confirmed KPI facts.
3. `$dia-kpi-data-mapping` inside the workspace. Supply the CSV path and confirmed artifact pair. Review exact fields, calculations to build, assumptions, and missing components. If requested, also review separate schema-supported recommendations and select none or specific additions. Save `docs/KPI-Data-Mapping-YYYY-MM-DD-<topic>.md` with the dashboard inclusion list after confirmation.
4. `$dia-dashboard-mockup` from that confirmed mapping report. Review the panel outline, then render `docs/Dashboard-Mockup-YYYY-MM-DD-<topic>.html`. Include selected measures only, visible requested/recommended origin labels, mock values, and explicit gap panels. The template is a local prototype with a chart CDN dependency, not an offline working dashboard.

Stop after step 3 when mapping is enough. Continue to step 4 for a stakeholder
prototype. Steps 2-4 can also write in the working directory outside an analysis
workspace; choose a workspace first when its folder organization is wanted.

## Handoffs

- The paired KPI Markdown and schema-version-1 facts preserve transcript-confirmed requests. Dataset-derived recommendations never modify them.
- Read the Markdown deferred-ideas context when proposing candidates. A dataset column does not reopen a deferred or rejected business decision.
- Candidate recommendations carry proposed definitions, exact fields, assumptions, evidence limits, and individual selection. They remain dataset-derived even after selection.
- The Markdown mapping report is the dashboard contract. Its inclusion list records every requested measure and candidate with an explicit selection. Candidate-mode runs skip optional version-1 mapping YAML because that schema cannot represent provenance and selection.
- Requested-only legacy reports remain supported. Recommendations without explicit selection cannot become panels automatically.
- Mapping is a specification, not a calculation. Missing data stays missing, with a source-system request rather than a proxy.
- Mockup numbers are fabricated placeholders. Included gaps stay visible; no data is read or computed at the rendering step.

## Release dependency

The transcript and mapping skills remain in development until their acceptance
runs support promotion. The standard production/testing installer skips them.
Publishing a session-ready catalog requires that separate release step.
