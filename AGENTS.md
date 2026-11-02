# Agent instructions

## Purpose

This repository stores reusable skills for DIA staff who use TritonAI Harness on managed Windows computers. Treat the repository copy of each skill as the source skill. Treat copies under a user's TritonAI Harness directory as installed skills.

## Workspace map

| Path | Purpose |
| --- | --- |
| `README.md` | Human-facing catalog, installation steps, and validation commands |
| `CONTEXT.md` | Project-specific language only |
| `CONTRIBUTING.md` | Contribution and review process |
| `docs/adr/` | Decisions whose tradeoffs would be hard to reconstruct |
| `playbooks/` | Ordered skill sequences for end-to-end workflows |
| `docs/index.html` | Repository landing page mirroring the skill and playbook catalog |
| `scripts/` | Installer, installer tests, and repository validation |
| `skills/` | Source skill packages |
| `.github/workflows/` | Automated repository checks |

## Skill package shape

```text
skills/
`-- skill-name/
    |-- SKILL.md
    |-- agents/
    |   `-- openai.yaml
    |-- references/
    |-- scripts/
    `-- assets/
```

Only add optional directories when the skill uses them. Do not add a README or changelog inside a skill package.

## Current skill boundaries

`dia-clickup-mcp-setup` owns configuration, OAuth login, restart guidance, and read-only connection verification. It does not own ClickUp task management, workflow rules, legacy server migration, or fallback authentication.

`dia-dashboard-mockup` owns rendering selected measures from one confirmed KPI data mapping report into a single UCSD-branded HTML dashboard mockup, preserving stakeholder-requested versus dataset-derived origins, mock-data labels, and explicit gap panels. It follows the report inclusion list and never selects recommendations itself. It does not produce mapping reports, KPI artifacts, or requirements documents, read datasets, execute calculations, publish or send anything, or replace real dashboards.

`dia-dataset-profile` owns one confirmed orientation report for one CSV file or selected XLSX sheet: contents, field inventory, distributions, missingness, candidate identifiers, duplicate and unusual values, possible uses, and questions for the data owner. It explains existing profile findings but does not answer new business calculations, define KPIs, map confirmed KPIs, create workspaces, update data dictionaries, or produce other deliverables.

`dia-data-model-intake` owns local, deterministic extraction of facts from one Oracle BI Publisher data model into `model-facts.yaml`. It does not execute the model's SQL, connect to data sources, interpret business meaning, author documentation, or change source files.

`dia-data-model-docs` owns drafting the overview card, data dictionary, KPI and business-questions catalog, and when-to-use guidance from one schema-version-1 or -2 `model-facts.yaml` file and its `data-model-profile.md` when present, after analyst confirmation or in user-requested draft mode. It enforces the ownership map across the four documents: grain, filters, join risk, and CASE mappings stay owned by the profile, column facts stay in the dictionary, KPI formulas stay in the catalog, and open questions stay in one overview register. It does not extract facts, connect to databases, execute SQL, publish documentation, or modify the facts file or the profile.

`dia-kpi-data-mapping` owns validating a confirmed KPI artifact against one user-named dataset and drafting a declarative mapping report with fields, calculations to build, and data gaps. When requested, it also proposes separate schema-supported candidates and records explicit user selections in a dashboard inclusion list without changing transcript facts. It does not execute calculations, build pipeline scripts, modify the dataset, resolve open questions in the KPI artifact, or invoke other skills.

`dia-transcript-to-meeting-notes` owns converting a Zoom transcript into a detailed project meeting-note Markdown file saved in the user's working directory. It does not publish to Project Hub, create ClickUp tasks, capture transcripts, or set up project folders.

`dia-transcript-to-process-map` owns saving one supplied Zoom transcript locally, writing a process-outline Markdown file, obtaining the user's explicit confirmation of that outline, and rendering the confirmed process as a process-map diagram through the installed diagram-design skill, using the process source from a requirements document for the same transcript when one exists. When the diagram-design skill is missing, it offers to install it through the Harness skill installer and installs only after explicit user approval. It does not own meeting notes, diagram design rules, transcript capture, requirements-gathering extraction, ClickUp content, or Project Hub publication.

`dia-transcript-to-requirements` owns converting a supplied Zoom transcript of a business-owner requirements conversation into a local structured requirements document. It does not produce meeting notes, render diagrams, create ClickUp tasks, capture transcripts, or publish to Project Hub.

`dia-transcript-to-kpis` owns converting a supplied Zoom transcript into paired confirmed business-questions-and-KPIs Markdown and schema-version-1 `kpi-facts.yaml`, keeping deferred ideas separate in the Markdown. Supplied paths skip redundant intake; one content review remains. It does not produce meeting notes, requirements documents, process diagrams, ClickUp content, or Project Hub publication, and it does not map KPIs to datasets.

`dia-bi-publisher-sql-optimizer` owns reviewing one selected SQL dataset in one BI Publisher data model with a required SQL Monitor export and confirmed editor smoke test with 200 selected, producing an optimization report and a behavior-preserving candidate, and comparing before/after estimated plans in delta mode. It requires the same preview and export for the candidate, keeps correctness and estimated performance findings separate, and does not request full runs, repeated benchmarks, or engine logs. It does not execute SQL, connect to a database, apply rewrites in BI Publisher, extract data-model facts, or map KPIs to datasets.

`dia-start-my-day` owns a daily chat brief from open assigned ClickUp tasks, today's and the following two days' Outlook calendar, and the last 72 hours of Outlook mail, with matching HTML on request and user-approved follow-through in those systems. It hands disconnected ClickUp access to the installed setup skill only after user approval. It does not own connection setup, other evidence sources, or unapproved external changes.

`dia-setup-business-insights-folder` is archived and retained outside active catalogs and bulk installation. It owns local creation and validation of the schema-1 business-insights project folder for existing ClickUp resources. It does not create or change ClickUp content, migrate conflicting folders, process project files, analyze data, or create deliverables.

`dia-new-workspace` owns interviewing the user, choosing a simple or data-analysis layout, creating its local folders and project-context README and AGENTS files, moving explicitly confirmed starting files, and giving the open-folder handoff to planning. It does not analyze content, create a plan, connect external systems, or switch the Harness project.

`dia-plan-my-project` owns helping the user refine one task or project goal and creating or revising a confirmed, human-readable `plan.md` at an existing workspace's root with the minimum sequence of work needed to achieve it. It reads relevant local documents for planning context but does not create workspaces, redefine stakeholder requirements, analyze datasets, extract source-model facts, connect external systems, or execute the plan.

`dia-tableau-dataset-intelligence` owns one complete local Dataset Intelligence Pack from one TWB or TWBX: a versioned dataset manifest, contextual field dictionary, model/grain specification, business glossary, metric proposals, and analytical questions, with deterministic generated reader views. It reuses maintained dictionary/intake helpers, keeps extraction snapshots immutable, and validates identity, provenance, reviews, references, and proposal gates. It does not read dataset values, execute SQL or metrics, verify data constraints, connect external systems, publish, or promote proposals to an enterprise registry.

`dia-tableau-data-dictionary` owns structured, versioned `data-dictionary.yaml` metadata from one local Tableau workbook and its deterministically generated `data-dictionary.md` view. Internal intake helpers extract immutable evidence; the LLM builds dataset context and enriches every business field's meaning, relevant units/codes/derivations, cautions, and questions from workbook and supplied documentation. Structured annotations retain evidence and review status before a concise analyst reference is rendered; review changes revise YAML first. It includes hidden and dashboard-unused fields, keeps parameters separate, preserves recorded descriptions and formulas, and labels interpretations and unresolved meanings. It does not read data values or extracts, connect to Tableau or databases, profile datasets, author dashboard documentation or audits, publish, or modify the source workbook.

`dia-tableau-workbook-intake` owns local, deterministic extraction of workbook facts, data-source fields, and recorded logical/physical model structure from one Tableau workbook package or workbook XML document into `workbook-facts.yaml`. It does not open Tableau, connect to Tableau Server, read the package's data extract, interpret business meaning, author documentation, or change source files.

`dia-tableau-dashboard-docs` owns drafting internal dashboard-reference and sheet-specs documentation from one schema-version-1 `workbook-facts.yaml` file after analyst confirmation, covering only sheets that appear on a dashboard. It does not extract facts, open Tableau, publish documentation, or modify the facts file.

`dia-tableau-workbook-audit` owns a factual workbook-wide inventory and health report from one schema-version-1 `workbook-facts.yaml` file, including sheet usage, orphan sheets, duplicate names, calculation reuse, and parameters. It does not extract facts, interpret business meaning, recommend changes, or produce dashboard documentation.

## Working rules

- Read `README.md`, `CONTEXT.md`, and the relevant skill before changing behavior.
- Keep each skill focused on one outcome.
- Use lowercase hyphenated skill names prefixed with `dia-` for skill folders.
- Keep the display name and slug consistent: a skill's folder, `SKILL.md` `name`, and `agents/openai.yaml` slug are `dia-` plus the lowercase hyphenated display name, and users invoke it as `$dia-<name>` (for example, "Analyze Local Data" is `dia-analyze-local-data`, invoked as `$dia-analyze-local-data`). When naming or renaming a skill, update the folder, `SKILL.md`, `agents/openai.yaml`, the `README.md` and `docs/index.html` catalogs, and any scripts, tests, or workflows that reference the slug.
- Declare each skill's lifecycle in its `SKILL.md` frontmatter as `metadata.status: development`, `testing`, `production`, or `archived`. Skills start in development, get promoted to testing, and finally to production. Archived skills stay in the repository but are excluded from active catalogs and bulk installation. The landing page catalogs active skills with production selected by default.
- Keep user-specific data and secrets out of the repository.
- Preserve explicit invocation policies.
- Update the catalog and workspace map when paths or skill boundaries change.
- Run both validation commands from `README.md` before finishing.
- Do not install a changed skill into a live TritonAI Harness unless the user asks for that separate action.
