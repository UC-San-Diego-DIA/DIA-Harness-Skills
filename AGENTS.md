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

## Current skill boundary

`connect-clickup` owns configuration, OAuth login, restart guidance, and read-only connection verification. It does not own ClickUp task management, workflow rules, legacy server migration, or fallback authentication.

## Working rules

- Read `README.md`, `CONTEXT.md`, and the relevant skill before changing behavior.
- Keep each skill focused on one outcome.
- Use lowercase hyphenated names for skill folders.
- Keep user-specific data and secrets out of the repository.
- Preserve explicit invocation policies.
- Update the catalog and workspace map when paths or skill boundaries change.
- Run both validation commands from `README.md` before finishing.
- Do not install a changed skill into a live TritonAI Harness unless the user asks for that separate action.
