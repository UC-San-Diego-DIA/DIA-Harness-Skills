# DIA Harness Skills

This repository is the reviewed source for DIA skills used in TritonAI Harness on managed Windows computers.

## Skill catalog

| Skill | Use it for | Invocation |
| --- | --- | --- |
| [`dia-analyze-local-data`](skills/dia-analyze-local-data/SKILL.md) *(testing)* | Creating a local DuckDB workspace for ad hoc analysis of one CSV | `$dia-analyze-local-data` |
| [`dia-clickup-mcp-setup`](skills/dia-clickup-mcp-setup/SKILL.md) *(production)* | Connecting TritonAI Harness to ClickUp through the official OAuth MCP server | `$dia-clickup-mcp-setup` |
| [`dia-data-model-docs`](skills/dia-data-model-docs/SKILL.md) *(development)* | Drafting four analyst-facing documents from one extracted model-facts file | `$dia-data-model-docs` |
| [`dia-data-model-intake`](skills/dia-data-model-intake/SKILL.md) *(development)* | Extracting deterministic facts from one Oracle BI Publisher data model | `$dia-data-model-intake` |
| [`dia-new-data-analysis-workspace`](skills/dia-new-data-analysis-workspace/SKILL.md) *(testing)* | Creating a fresh local data-analysis workspace with raw inputs, numbered pipeline scripts, and dashboard-ready output | `$dia-new-data-analysis-workspace` |
| [`dia-transcript-to-meeting-notes`](skills/dia-transcript-to-meeting-notes/SKILL.md) *(testing)* | Converting a Zoom transcript into a detailed local project meeting-note Markdown file | `$dia-transcript-to-meeting-notes` |
| [`dia-transcript-to-process-map`](skills/dia-transcript-to-process-map/SKILL.md) *(testing)* | Saving a Zoom transcript locally, writing a confirmable process outline with current-state timing, and rendering the confirmed process map | `$dia-transcript-to-process-map` |
| [`dia-transcript-to-requirements`](skills/dia-transcript-to-requirements/SKILL.md) *(testing)* | Converting a business-owner requirements Zoom transcript into a structured requirements document | `$dia-transcript-to-requirements` |
| [`dia-process-meeting-transcript`](skills/dia-process-meeting-transcript/SKILL.md) *(development)* | Turning a project transcript into meeting notes and DIA-owned ClickUp tasks | `$dia-process-meeting-transcript` |
| [`dia-setup-project-folder`](skills/dia-setup-project-folder/SKILL.md) *(development)* | Creating or validating a business-insights project folder connected to ClickUp | `$dia-setup-project-folder` |
| [`dia-start-my-day`](skills/dia-start-my-day/SKILL.md) *(testing)* | Choosing today's focus from ClickUp, Outlook calendar, and Outlook mail | `$dia-start-my-day` |

Each skill's `SKILL.md` frontmatter declares its lifecycle with `metadata.status: development`, `testing`, or `production`. Skills start in development, get promoted to testing, and finally to production. The landing page in `docs/index.html` catalogs production and testing skills, marks each entry with a small lifecycle indicator, and the repository validator enforces that rule.

## Playbooks

Playbooks in [playbooks/](playbooks/) chain reviewed skills into end-to-end DIA workflows:

- [Meeting notes to ClickUp tasks](playbooks/meeting-notes-to-tasks.md) - set up the project, convert the transcript, publish notes, and create approved tasks.
- [Start of day](playbooks/start-of-day.md) - verify ClickUp access, then run the daily brief from ClickUp and Outlook.
- [Requirements to process map](playbooks/requirements-to-process-map.md) - turn a requirements conversation into a structured requirements document and a rendered process map.

## Install skills

Clone the repository, open PowerShell in its root, and run the installer with one or more skill names:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day, dia-setup-project-folder
```

To install every skill in the repository at once, including development skills that are not listed on the landing page, run:

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

The validator checks skill packages, local Markdown links, invocation policy, and likely secrets. The installer test uses a temporary directory and never touches the active TritonAI Harness installation. The GitHub workflow also tests the DuckDB, project-folder, and workspace helpers in temporary directories.

## Security

Do not commit source CSVs, DuckDB databases, analysis outputs, ClickUp tokens, OAuth credentials, copied user configuration, task exports, or personal task IDs. Shared workspace and space IDs are allowed when they identify an approved team destination.
