# DIA Harness Skills

This repository is the reviewed source for DIA skills used in TritonAI Harness on managed Windows computers.

## Skill catalog

| Skill | Use it for | Invocation |
| --- | --- | --- |
| [`analyze-csv-with-duckdb`](skills/analyze-csv-with-duckdb/SKILL.md) | Creating a local DuckDB workspace for ad hoc analysis of one CSV | `$analyze-csv-with-duckdb` |
| [`connect-clickup`](skills/connect-clickup/SKILL.md) | Connecting TritonAI Harness to ClickUp through the official OAuth MCP server | `$connect-clickup` |
| [`start-my-day`](skills/start-my-day/SKILL.md) | Choosing today's focus from ClickUp, Outlook calendar, and Outlook mail | `$start-my-day` |

## Install a skill

Clone the repository, open PowerShell in its root, and run:

```powershell
pwsh -File .\scripts\install-skill.ps1 -Skill analyze-csv-with-duckdb
```

Replace the skill name with another catalog entry when installing a different skill.

The installer copies the source skill into `%USERPROFILE%\.tritonai-harness\codex\skills`. It asks before replacing an installed copy and keeps the previous copy in a timestamped backup directory.

After installation, restart TritonAI Harness so it reloads the skill catalog. Invoke the skill explicitly:

```text
$analyze-csv-with-duckdb
```

## Repository layout

```text
DIA-Harness-Skills/
|-- .github/workflows/     Validation in GitHub Actions
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

The validator checks skill packages, local Markdown links, invocation policy, and likely secrets. The installer test uses a temporary directory and never touches the active TritonAI Harness installation. The GitHub workflow also runs the DuckDB helper against temporary CSV files.

## Security

Do not commit source CSVs, DuckDB databases, analysis outputs, ClickUp tokens, OAuth credentials, copied user configuration, task exports, or personal task IDs. Shared workspace and space IDs are allowed when they identify an approved team destination.
