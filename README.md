# DIA Harness Skills

This repository is the reviewed source for DIA skills used in TritonAI Harness on managed Windows computers.

## Skill catalog

| Skill | Use it for | Invocation |
| --- | --- | --- |
| [`dia-local-data-explorer`](skills/dia-local-data-explorer/SKILL.md) *(development)* | Creating a local project for one CSV or XLSX sheet, asking questions, saving real-data visuals, and building an offline HTML dashboard | `$dia-local-data-explorer` |
| [`dia-analyze-local-data`](skills/dia-analyze-local-data/SKILL.md) *(testing)* | Answering ad hoc questions about one CSV or Excel file inside a data-analysis workspace, via a linked DuckDB view under `scratch/analysis/` | `$dia-analyze-local-data` |
| [`dia-dataset-profile`](skills/dia-dataset-profile/SKILL.md) *(production)* | Understanding one new CSV file or selected XLSX sheet: how to read it, possible uses, data issues, and questions for its owner | `$dia-dataset-profile` |
| [`dia-clickup-mcp-setup`](skills/dia-clickup-mcp-setup/SKILL.md) *(production)* | Connecting TritonAI Harness to ClickUp through the official OAuth MCP server | `$dia-clickup-mcp-setup` |
| [`dia-dashboard-mockup`](skills/dia-dashboard-mockup/SKILL.md) *(testing)* | Rendering selected requested KPIs and dataset-derived recommendations from a confirmed mapping report, with visible origins, mock data, and gap panels | `$dia-dashboard-mockup` |
| [`dia-data-model-docs`](skills/dia-data-model-docs/SKILL.md) *(development)* | Drafting four analyst-facing documents, including a KPI and business-questions catalog, from one extracted model-facts file and its structural profile | `$dia-data-model-docs` |
| [`dia-data-model-intake`](skills/dia-data-model-intake/SKILL.md) *(development)* | Extracting deterministic facts from one Oracle BI Publisher data model | `$dia-data-model-intake` |
| [`dia-data-model-profiler`](skills/dia-data-model-profiler/SKILL.md) *(testing)* | Profiling one model-facts file: grain, filters, hard-coded logic, dedup and join patterns, and source lineage | `$dia-data-model-profiler` |
| [`dia-kpi-data-mapping`](skills/dia-kpi-data-mapping/SKILL.md) *(production)* | Mapping requested KPIs to one dataset and optionally proposing separately labeled, user-selected schema-supported measures | `$dia-kpi-data-mapping` |
| [`dia-transcript-to-meeting-notes`](skills/dia-transcript-to-meeting-notes/SKILL.md) *(production)* | Converting a Zoom transcript into a detailed local project meeting-note Markdown file | `$dia-transcript-to-meeting-notes` |
| [`dia-transcript-to-process-map`](skills/dia-transcript-to-process-map/SKILL.md) *(testing)* | Saving a Zoom transcript locally, inventorying possible processes, building confirmable ROI-based outlines for the confirmed ones, and rendering the confirmed process maps | `$dia-transcript-to-process-map` |
| [`dia-transcript-to-project-request-draft`](skills/dia-transcript-to-project-request-draft/SKILL.md) *(production)* | Drafting a first-pass, field-by-field fill-in for the VCFA DIA Project Request Form from a project-request transcript, with data gaps named for review | `$dia-transcript-to-project-request-draft` |
| [`dia-transcript-to-requirements`](skills/dia-transcript-to-requirements/SKILL.md) *(production)* | Converting a business-owner requirements Zoom transcript into a decision-driven requirements document | `$dia-transcript-to-requirements` |
| [`dia-transcript-to-kpis`](skills/dia-transcript-to-kpis/SKILL.md) *(production)* | Extracting confirmed business questions and KPIs into paired Markdown and `kpi-facts.yaml`, keeping deferred ideas separate | `$dia-transcript-to-kpis` |
| [`dia-new-workspace`](skills/dia-new-workspace/SKILL.md) *(production)* | Choosing and creating a simple or data-analysis workspace, moving confirmed starting files, and handing off to planning | `$dia-new-workspace` |
| [`dia-plan-my-project`](skills/dia-plan-my-project/SKILL.md) *(production)* | Refining a task or project goal and creating or revising a confirmed `plan.md` with the minimum steps needed to achieve it | `$dia-plan-my-project` |
| [`dia-bi-publisher-sql-optimizer`](skills/dia-bi-publisher-sql-optimizer/SKILL.md) *(development)* | Reviewing one BI Publisher SQL dataset with a required SQL Monitor export and confirmed 200-row editor smoke test, proposing behavior-preserving changes, and comparing before/after estimated plans | `$dia-bi-publisher-sql-optimizer` |
| [`dia-tableau-dashboard-docs`](skills/dia-tableau-dashboard-docs/SKILL.md) *(development)* | Drafting internal dashboard-reference and sheet-specs documentation from one workbook-facts file | `$dia-tableau-dashboard-docs` |
| [`dia-tableau-workbook-audit`](skills/dia-tableau-workbook-audit/SKILL.md) *(development)* | Auditing one Tableau workbook's facts: sheet usage, orphan sheets, duplicate names, calculation reuse, and parameters | `$dia-tableau-workbook-audit` |
| [`dia-tableau-dataset-intelligence`](skills/dia-tableau-dataset-intelligence/SKILL.md) *(development)* | Building one complete metadata-only Dataset Intelligence Pack from a TWB or TWBX: identity, dictionary, model/grain, glossary, metric proposals, and questions | `$dia-tableau-dataset-intelligence` |
| [`dia-tableau-data-dictionary`](skills/dia-tableau-data-dictionary/SKILL.md) *(testing)* | Enriching Tableau field meanings from workbook and supplied context, then generating a concise analyst reference from versioned YAML | `$dia-tableau-data-dictionary` |
| [`dia-tableau-workbook-intake`](skills/dia-tableau-workbook-intake/SKILL.md) *(testing)* | Extracting deterministic workbook facts, fields, and model structure into workbook-facts.yaml | `$dia-tableau-workbook-intake` |
| [`dia-start-my-day`](skills/dia-start-my-day/SKILL.md) *(production)* | Choosing today's focus in chat from open assigned ClickUp tasks, today's and the next two days' Outlook calendar, and the last 72 hours of mail; HTML on request | `$dia-start-my-day` |
| [`dia-harness-utilization-review`](skills/dia-harness-utilization-review/SKILL.md) *(development)* | Reviewing the previous day's Harness threads and conversations for interaction improvements and new usage ideas, then recording confirmed recommendations in a local review log; designed for a scheduled ~9 AM run | `$dia-harness-utilization-review` |

Each skill's `SKILL.md` frontmatter declares its lifecycle with `metadata.status: development`, `testing`, `production`, or `archived`. Skills start in development, get promoted to testing, and finally to production. The landing page in `docs/index.html` catalogs every active skill behind a lifecycle filter with production selected by default, marks each entry with a small lifecycle indicator, sorts entries production, testing, then development, and the repository validator enforces that every active skill appears. Archived skills are retained outside the active catalog and excluded from bulk installation.

`dia-new-workspace` replaces the separate simple and data-analysis workspace creators while preserving both layouts. It is in production after a live Harness pilot of the combined interview, file moves, and planning handoff. Existing installations are not changed by this repository update.

Workspace setup uses one preview for generated files and incoming file moves. A supplied data dictionary can replace the planned placeholder after confirmation. The project context carries known goals and explicit unknowns into the shorter planning interview.

## Local data explorer v1

Invoke `$dia-local-data-explorer` with a CSV or XLSX path to start a new local explorer project. It creates project guidance and folders, copies the file without moving the original, and records the selected sheet and snapshot hash. Ask questions in Harness, request visuals, say which ones to save, then ask to build the dashboard. Resume later from the project folder using its recorded questions and visual selections.

V1 supports one file and one selected Excel sheet, read-only SQL, bar and line charts, KPI values, and tables. Dashboards contain real calculated results and query evidence, open offline, and include only saved visuals. They are point-in-time exports with panel search and CSV downloads. They do not provide browser chat, automatic refresh, multi-file joins, or cross-filtering. Python with DuckDB and pytz is required; Excel also needs DuckDB's Excel extension. The skill asks before installing missing dependencies. The installer bundles the maintained analysis engine so no second skill installation is needed.

See the [workflow and command contract](skills/dia-local-data-explorer/references/workflow.md). This is a new end-to-end workflow; the existing analysis, workspace, and mockup skills keep their narrower responsibilities.

## Archived skills

- [`dia-setup-business-insights-folder`](skills/dia-setup-business-insights-folder/SKILL.md) is retained for future use. It is excluded from active catalogs and `-All`; explicit `-Skill` installation remains available for deliberate recovery. Archiving does not remove already installed copies.

## Playbooks

Playbooks in [playbooks/](playbooks/) chain reviewed skills into end-to-end DIA workflows:

- [Requirements to process map](playbooks/requirements-to-process-map.md) - turn a requirements conversation into a structured requirements document and a rendered process map.
- [Business questions to dashboard mockup](playbooks/business-questions-to-dashboard-mockup.md) - create the analysis workspace, extract confirmed business questions and KPIs from the transcript, map them to the workspace dataset, optionally select separate dataset-derived recommendations, and stop there or continue to an HTML mockup with mock data and origin labels.
- [One transcript, many artifacts](playbooks/one-transcript-many-artifacts.md) - save one transcript, then derive meeting notes, requirements, a process map, or confirmed KPIs as the meeting needs.
- [Workspace to first answer](playbooks/workspace-to-first-answer.md) - create the analysis workspace, link one source file, and answer ad hoc questions from it with read-only SQL.
- [Data model to documentation](playbooks/data-model-to-documentation.md) - extract facts from one Oracle BI Publisher data model, profile its structure, then draft analyst-facing documentation in sequence.

## Install skills

Clone the repository, open PowerShell in its root, and run the installer with one or more skill names:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day, dia-new-workspace
```

To install every active skill in the repository at once, including development skills, run:

```powershell
pwsh -File .\scripts\install-skill.ps1 -All
```

To install only the skills that have reached a given lifecycle, filter by status:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Status production,testing
```

Use `-All` when you help test skills that are still in development. Add `-Force` to replace installed copies without the per-skill confirmation prompt. The landing page in `docs/index.html` also carries a copyable prompt that asks TritonAI Harness to install every production and testing skill, so it stays current as skills are added.

`dia-tableau-dataset-intelligence` accepts TWB or TWBX and produces six structured YAML assets plus generated Markdown/CSV views. Its installer bundles the maintained dictionary and intake runtimes, including model extraction, so it can be installed alone. It does not read data values, execute calculations, or publish.

For `dia-tableau-data-dictionary`, the installer bundles the maintained workbook-intake helpers and shared schema so the skill works on its own. It also includes the schema with workbook intake. No separate intake installation is required for the dictionary.

The installer copies the source skill into `%USERPROFILE%\.tritonai-harness\codex\skills`. It asks before replacing an installed copy and keeps the previous copy in a timestamped backup directory.

`dia-transcript-to-process-map` additionally requires the MIT-licensed `diagram-design` skill from https://github.com/cathrynlavery/diagram-design; its skill package lives at `skills/diagram-design` in that repository. When the skill starts and `diagram-design` is not installed, it offers to install it on the user's behalf through the Harness skill installer and proceeds only after explicit approval. You can also install it yourself in advance with the Harness skill installer.

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

The validator checks skill packages, local Markdown links, invocation policy, and likely secrets. The installer test uses a temporary directory and never touches the active TritonAI Harness installation. The GitHub workflow also tests the local data explorer lifecycle and the DuckDB, project-folder, workspace, data-model intake, dataset-profile, and workbook-intake helpers in temporary directories.

## Security

Do not commit source CSVs, DuckDB databases, analysis outputs, ClickUp tokens, OAuth credentials, copied user configuration, task exports, or personal task IDs. Shared workspace and space IDs are allowed when they identify an approved team destination.
