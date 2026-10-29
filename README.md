# DIA Harness Skills

This repository is the reviewed source for DIA skills used in TritonAI Harness on managed Windows computers.

## Skill catalog

| Skill | Use it for | Invocation |
| --- | --- | --- |
| [`dia-analyze-local-data`](skills/dia-analyze-local-data/SKILL.md) *(testing)* | Answering ad hoc questions about one CSV or Excel file inside a data-analysis workspace, via a linked DuckDB view under `scratch/analysis/` | `$dia-analyze-local-data` |
| [`dia-dataset-profile`](skills/dia-dataset-profile/SKILL.md) *(testing)* | Profiling one CSV or Excel file: fields, distributions, missingness, candidate keys, anomalies, and suggested metrics or KPIs | `$dia-dataset-profile` |
| [`dia-clickup-mcp-setup`](skills/dia-clickup-mcp-setup/SKILL.md) *(production)* | Connecting TritonAI Harness to ClickUp through the official OAuth MCP server | `$dia-clickup-mcp-setup` |
| [`dia-dashboard-mockup`](skills/dia-dashboard-mockup/SKILL.md) *(testing)* | Rendering a UCSD-branded HTML dashboard mockup with mock data and explicit data-gap panels from one KPI data mapping report | `$dia-dashboard-mockup` |
| [`dia-data-model-docs`](skills/dia-data-model-docs/SKILL.md) *(testing)* | Drafting four analyst-facing documents, including a KPI and business-questions catalog, from one extracted model-facts file | `$dia-data-model-docs` |
| [`dia-data-model-intake`](skills/dia-data-model-intake/SKILL.md) *(testing)* | Extracting deterministic facts from one Oracle BI Publisher data model | `$dia-data-model-intake` |
| [`dia-data-model-profiler`](skills/dia-data-model-profiler/SKILL.md) *(testing)* | Profiling one model-facts file: grain, filters, hard-coded logic, dedup and join patterns, and source lineage | `$dia-data-model-profiler` |
| [`dia-kpi-data-mapping`](skills/dia-kpi-data-mapping/SKILL.md) *(testing)* | Mapping confirmed KPIs to one named dataset: required fields, calculations to build, and data gaps | `$dia-kpi-data-mapping` |
| [`dia-new-data-analysis-workspace`](skills/dia-new-data-analysis-workspace/SKILL.md) *(production)* | Creating a fresh local data-analysis workspace with raw inputs, numbered pipeline scripts, dashboard-ready output, and a home for meeting transcripts | `$dia-new-data-analysis-workspace` |
| [`dia-transcript-to-meeting-notes`](skills/dia-transcript-to-meeting-notes/SKILL.md) *(testing)* | Converting a Zoom transcript into a detailed local project meeting-note Markdown file | `$dia-transcript-to-meeting-notes` |
| [`dia-transcript-to-process-map`](skills/dia-transcript-to-process-map/SKILL.md) *(testing)* | Saving a Zoom transcript locally, inventorying possible processes, building confirmable ROI-based outlines for the confirmed ones, and rendering the confirmed process maps | `$dia-transcript-to-process-map` |
| [`dia-transcript-to-project-request-draft`](skills/dia-transcript-to-project-request-draft/SKILL.md) *(testing)* | Drafting a first-pass, field-by-field fill-in for the VCFA DIA Project Request Form from a project-request transcript, with data gaps named for review | `$dia-transcript-to-project-request-draft` |
| [`dia-transcript-to-requirements`](skills/dia-transcript-to-requirements/SKILL.md) *(testing)* | Converting a business-owner requirements Zoom transcript into a decision-driven requirements document | `$dia-transcript-to-requirements` |
| [`dia-transcript-to-kpis`](skills/dia-transcript-to-kpis/SKILL.md) *(testing)* | Extracting confirmed business questions and KPIs from a requirements transcript into Markdown and `kpi-facts.yaml` | `$dia-transcript-to-kpis` |
| [`dia-process-meeting-transcript`](skills/dia-process-meeting-transcript/SKILL.md) *(development)* | Turning a project transcript into meeting notes and DIA-owned ClickUp tasks | `$dia-process-meeting-transcript` |
| [`dia-setup-project-folder`](skills/dia-setup-project-folder/SKILL.md) *(development)* | Creating or validating a business-insights project folder connected to ClickUp | `$dia-setup-project-folder` |
| [`dia-tableau-dashboard-docs`](skills/dia-tableau-dashboard-docs/SKILL.md) *(development)* | Drafting internal dashboard-reference and sheet-specs documentation from one workbook-facts file | `$dia-tableau-dashboard-docs` |
| [`dia-tableau-workbook-audit`](skills/dia-tableau-workbook-audit/SKILL.md) *(development)* | Auditing one Tableau workbook's facts: sheet usage, orphan sheets, duplicate names, calculation reuse, and parameters | `$dia-tableau-workbook-audit` |
| [`dia-tableau-workbook-intake`](skills/dia-tableau-workbook-intake/SKILL.md) *(development)* | Extracting deterministic facts from one Tableau workbook package into workbook-facts.yaml | `$dia-tableau-workbook-intake` |
| [`dia-start-my-day`](skills/dia-start-my-day/SKILL.md) *(testing)* | Choosing today's focus from ClickUp, Outlook calendar, and Outlook mail | `$dia-start-my-day` |

Each skill's `SKILL.md` frontmatter declares its lifecycle with `metadata.status: development`, `testing`, or `production`. Skills start in development, get promoted to testing, and finally to production. The landing page in `docs/index.html` catalogs every skill behind a lifecycle filter with production selected by default, marks each entry with a small lifecycle indicator, sorts entries production, testing, then development, and the repository validator enforces that every skill appears.

## Playbooks

Playbooks in [playbooks/](playbooks/) chain reviewed skills into end-to-end DIA workflows:

- [Requirements to process map](playbooks/requirements-to-process-map.md) - turn a requirements conversation into a structured requirements document and a rendered process map.
- [Business questions to dashboard mockup](playbooks/business-questions-to-dashboard-mockup.md) - create the analysis workspace, extract confirmed business questions and KPIs from the transcript, map them to the workspace dataset, and stop there or continue to a UCSD-branded HTML dashboard mockup with mock data.
- [One transcript, many artifacts](playbooks/one-transcript-many-artifacts.md) - save one transcript, then derive meeting notes, requirements, a process map, or confirmed KPIs as the meeting needs.
- [Workspace to first answer](playbooks/workspace-to-first-answer.md) - create the analysis workspace, link one source file, and answer ad hoc questions from it with read-only SQL.
- [Data model to documentation](playbooks/data-model-to-documentation.md) - extract facts from one Oracle BI Publisher data model, profile its structure, then draft analyst-facing documentation in sequence.

## Install skills

Clone the repository, open PowerShell in its root, and run the installer with one or more skill names:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day, dia-setup-project-folder
```

To install every skill in the repository at once, including development skills, run:

```powershell
pwsh -File .\scripts\install-skill.ps1 -All
```

To install only the skills that have reached a given lifecycle, filter by status:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Status production,testing
```

Use `-All` when you help test skills that are still in development. Add `-Force` to replace installed copies without the per-skill confirmation prompt. The landing page in `docs/index.html` also carries a copyable prompt that asks TritonAI Harness to install every production and testing skill, so it stays current as skills are added.

The installer copies the source skill into `%USERPROFILE%\.tritonai-harness\codex\skills`. It asks before replacing an installed copy and keeps the previous copy in a timestamped backup directory.

`dia-transcript-to-process-map` additionally requires the MIT-licensed `diagram-design` skill from https://github.com/cathrynlavery/diagram-design. Install it into TritonAI Harness separately, for example with the Harness skill installer, before using that skill.

After installation, restart TritonAI Harness so it reloads the skill catalog. Invoke the skill explicitly:

```text
$dia-start-my-day
```

## Repository layout

```text
DIA-Harness-Skills/
|-- .github/workflows/     Validation in GitHub Actions
|-- docs/                  Repository landing page
|-- playbooks/             Ordered skill sequences for end-to-end workflows
|-- docs/adr/              Decisions that need their reasoning preserved
|-- scripts/               Installation and repository checks
|-- skills/                Source skills
|-- AGENTS.md              Instructions for agents working in this repo
|-- CONTEXT.md             Project glossary
|-- CONTRIBUTING.md        Team contribution process
`-- README.md              Catalog and installation instructions
```

## Validate a change

Run both checks before opening a pull request:

```powershell
pwsh -File .\scripts\validate-repository.ps1
pwsh -File .\scripts\test-install-skill.ps1
```

The validator checks skill packages, local Markdown links, invocation policy, and likely secrets. The installer test uses a temporary directory and never touches the active TritonAI Harness installation. The GitHub workflow also tests the DuckDB, project-folder, workspace, data-model intake, dataset-profile, and workbook-intake helpers in temporary directories.

## Security

Do not commit source CSVs, DuckDB databases, analysis outputs, ClickUp tokens, OAuth credentials, copied user configuration, task exports, or personal task IDs. Shared workspace and space IDs are allowed when they identify an approved team destination.


