# Contributing

Keep changes small enough to review as one coherent decision.

## Before editing

1. Read `AGENTS.md` and the relevant `SKILL.md`.
2. Check `CONTEXT.md` for the repository's terms.
3. Confirm the change belongs to an existing skill before widening its scope.

## Skill changes

- New skills start in `development` and are promoted to `testing`, then `production`, by updating `metadata.status` in `SKILL.md`.
- Put routing, the main workflow, and safety boundaries in `SKILL.md`.
- Put team IDs or conditional detail in a linked reference.
- Add a script only when deterministic behavior reduces a real failure risk.
- Never add credentials, copied user configuration, personal task IDs, source CSVs, DuckDB databases, analysis outputs, or live ClickUp content.
- Keep `agents/openai.yaml` consistent with the skill name and invocation policy.
- Follow the naming convention: the slug is `dia-` plus the lowercase hyphenated display name, and the invocation is `$dia-<name>`. A rename must update the folder, `SKILL.md`, `agents/openai.yaml`, both catalogs, and every script or workflow reference together.

Archived skills retain their packages with `metadata.status: archived`. Exclude them from active catalogs and bulk installation; explicit named installation is available for deliberate recovery.

## Playbook changes

- Playbook frontmatter declares `name`, `description`, `pattern`, and `metadata.status`. Use `pipeline` for linear handoffs and `fan-out` for one shared input with independent branches.
- A playbook's status follows its connected skills: `production` when every connected skill is production, `testing` when every connected skill is in testing or production and at least one is testing, and `development` when any connected skill is in development. Only create a testing or production playbook whose connected skills are all in testing or production; a playbook that needs a development skill waits until that skill promotes and stays marked `development` until then.
- Show the status visibly: a `Status:` line under the playbook title, a status marker in the README playbook list, and a status dot beside the playbook title plus per-skill dots on the landing-page card, with the section color legend covering both. Update the README playbook list and the landing-page cards together.
- The repository validator derives each playbook's status from the `$dia-` skills it references and fails when the declared status, the visible `Status:` line, the README marker, or the landing-page title dot and skill dots disagree.

## Validation

Run:

```powershell
pwsh -File .\scripts\validate-repository.ps1
pwsh -File .\scripts\test-install-skill.ps1
```

Both commands must pass before review. A reviewer should also check that the skill stays within its stated boundary and does not grant itself permission for external writes.
