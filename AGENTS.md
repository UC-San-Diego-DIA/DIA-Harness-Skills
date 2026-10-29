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

`dia-dashboard-mockup` owns rendering one confirmed KPI data mapping report into a single self-contained UCSD-branded HTML dashboard mockup with mock data and explicit data-gap panels. It does not produce mapping reports, KPI artifacts, or requirements documents, read datasets, execute calculations, publish or send anything, or replace real dashboards.

dia-dataset-profile owns a one-time profile of one CSV or Excel file: field inventory, distributions, missingness, candidate keys, anomalies, and suggested metrics or KPIs, plus one-off answers to business questions the profile surfaces. It does not create workspaces, keep a question history, map confirmed KPIs, execute calculations, or produce other deliverables.

`dia-data-model-intake` owns local, deterministic extraction of facts from one Oracle BI Publisher data model into `model-facts.yaml`. It does not execute the model's SQL, connect to data sources, interpret business meaning, author documentation, or change source files.

`dia-data-model-docs` owns drafting the overview card, data dictionary, business-questions catalog, and when-to-use guidance from one schema-version-1 `model-facts.yaml` file after analyst confirmation. It does not extract facts, connect to databases, execute SQL, publish documentation, or modify the facts file.

`dia-kpi-data-mapping` owns validating a confirmed KPI artifact against one user-named dataset and drafting a declarative mapping report that identifies the fields supplying each metric, the calculations to build, and explicit data gaps. It does not execute calculations, build pipeline scripts, modify the dataset, resolve open questions in the KPI artifact, or invoke other skills.

`dia-transcript-to-meeting-notes` owns converting a Zoom transcript into a detailed project meeting-note Markdown file saved in the user's working directory. It does not publish to Project Hub, create ClickUp tasks, capture transcripts, or set up project folders.

`dia-transcript-to-process-map` owns saving one supplied Zoom transcript locally, writing a process-outline Markdown file, obtaining the user's explicit confirmation of that outline, and rendering the confirmed process as a process-map diagram through the installed diagram-design skill, using the process source from a requirements document for the same transcript when one exists. It does not own meeting notes, diagram design rules, transcript capture, requirements-gathering extraction, ClickUp content, or Project Hub publication.

`dia-transcript-to-requirements` owns converting a supplied Zoom transcript of a business-owner requirements conversation into a local structured requirements document. It does not produce meeting notes, render diagrams, create ClickUp tasks, capture transcripts, or publish to Project Hub.

`dia-transcript-to-kpis` owns converting a supplied Zoom transcript of a business-owner requirements or discovery conversation into a confirmed local business-questions-and-KPIs Markdown file with a schema-version-1 `kpi-facts.yaml` beside it. It does not produce meeting notes, requirements documents, process diagrams, ClickUp content, or Project Hub publication, and it does not map KPIs to datasets.

`dia-process-meeting-transcript` owns one transcript's meeting-note synthesis, Project Hub publication, DIA-owned action-item extraction, and approved task creation. It does not own transcript capture, project-folder setup, connection setup, general ClickUp task management, or follow-through in other systems.

`dia-start-my-day` owns read-only daily prioritization from ClickUp, Outlook calendar, and Outlook mail, plus user-approved follow-through in those systems. It does not own connection setup, other evidence sources, or unapproved external changes.

`dia-setup-project-folder` owns local creation and validation of the schema-1 business-insights project folder for existing ClickUp resources. It does not create or change ClickUp content, migrate conflicting folders, process project files, analyze data, or create deliverables.

## Working rules

- Read `README.md`, `CONTEXT.md`, and the relevant skill before changing behavior.
- Keep each skill focused on one outcome.
- Use lowercase hyphenated skill names prefixed with `dia-` for skill folders.
- Keep the display name and slug consistent: a skill's folder, `SKILL.md` `name`, and `agents/openai.yaml` slug are `dia-` plus the lowercase hyphenated display name, and users invoke it as `$dia-<name>` (for example, "Analyze Local Data" is `dia-analyze-local-data`, invoked as `$dia-analyze-local-data`). When naming or renaming a skill, update the folder, `SKILL.md`, `agents/openai.yaml`, the `README.md` and `docs/index.html` catalogs, and any scripts, tests, or workflows that reference the slug.
- Declare each skill's lifecycle in its `SKILL.md` frontmatter as `metadata.status: development`, `testing`, or `production`. Skills start in development, get promoted to testing, and finally to production. The `docs/index.html` catalog shows production and testing skills, each with a small lifecycle indicator; development skills stay out of the catalog; the repository validator enforces this.
- Keep user-specific data and secrets out of the repository.
- Preserve explicit invocation policies.
- Update the catalog and workspace map when paths or skill boundaries change.
- Run both validation commands from `README.md` before finishing.
- Do not install a changed skill into a live TritonAI Harness unless the user asks for that separate action.
