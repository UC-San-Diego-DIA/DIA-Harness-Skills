# DIA Harness Skills

This repository is the reviewed source for DIA skills used in TritonAI Harness on managed Windows computers.

## Skill catalog

| Skill | Use it for | Invocation |
| --- | --- | --- |
| [`dia-analyze-local-data`](skills/dia-analyze-local-data/SKILL.md) | Creating a local DuckDB workspace for ad hoc analysis of one CSV | `$dia-analyze-local-data` |
| [`dia-clickup-mcp-setup`](skills/dia-clickup-mcp-setup/SKILL.md) | Connecting TritonAI Harness to ClickUp through the official OAuth MCP server | `$dia-clickup-mcp-setup` |
| [`dia-new-data-analysis-workspace`](skills/dia-new-data-analysis-workspace/SKILL.md) | Creating a fresh local data-analysis workspace with raw inputs, numbered pipeline scripts, and dashboard-ready output | `$dia-new-data-analysis-workspace` |
| [`dia-transcript-to-meeting-notes`](skills/dia-transcript-to-meeting-notes/SKILL.md) | Converting a Zoom transcript into a detailed local project meeting-note Markdown file | `$dia-transcript-to-meeting-notes` |
| [`dia-transcript-to-process-map`](skills/dia-transcript-to-process-map/SKILL.md) | Saving a Zoom transcript locally, creating meeting notes, and rendering its process map | `$dia-transcript-to-process-map` |
| [`dia-transcript-to-requirements`](skills/dia-transcript-to-requirements/SKILL.md) | Converting a business-owner requirements Zoom transcript into a structured requirements document | `$dia-transcript-to-requirements` |
| [`dia-process-meeting-transcript`](skills/dia-process-meeting-transcript/SKILL.md) | Turning a project transcript into meeting notes and DIA-owned ClickUp tasks | `$dia-process-meeting-transcript` |
| [`dia-setup-project-folder`](skills/dia-setup-project-folder/SKILL.md) | Creating or validating a business-insights project folder connected to ClickUp | `$dia-setup-project-folder` |
| [`dia-start-my-day`](skills/dia-start-my-day/SKILL.md) | Choosing today's focus from ClickUp, Outlook calendar, and Outlook mail | `$dia-start-my-day` |

## Playbooks

Playbooks in [playbooks/](playbooks/) chain reviewed skills into end-to-end DIA workflows:

- [Meeting notes to ClickUp tasks](playbooks/meeting-notes-to-tasks.md) - set up the project, convert the transcript, publish notes, and create approved tasks.
- [Start of day](playbooks/start-of-day.md) - verify ClickUp access, then run the daily brief from ClickUp and Outlook.
- [Requirements to process map](playbooks/requirements-to-process-map.md) - turn a requirements conversation into a structured requirements document and a rendered process map.

## Install a skill

Clone the repository, open PowerShell in its root, and run:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Skill dia-start-my-day
```

Replace the skill name with another catalog entry when installing a different skill.

The installer copies the source skill into `%USERPROFILE%\.tritonai-harness\codex\skills`. It asks before replacing an installed copy and keeps the previous copy in a timestamped backup directory.

`dia-transcript-to-process-map` additionally requires the `dia-transcript-to-meeting-notes` skill and the MIT-licensed `diagram-design` skill from https://github.com/cathrynlavery/diagram-design. Install `diagram-design` into TritonAI Harness separately, for example with the Harness skill installer, before using that skill.

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
