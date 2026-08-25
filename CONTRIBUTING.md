# Contributing

Keep changes small enough to review as one coherent decision.

## Before editing

1. Read `AGENTS.md` and the relevant `SKILL.md`.
2. Check `CONTEXT.md` for the repository's terms.
3. Confirm the change belongs to an existing skill before widening its scope.

## Skill changes

- Put routing, the main workflow, and safety boundaries in `SKILL.md`.
- Put team IDs or conditional detail in a linked reference.
- Add a script only when deterministic behavior reduces a real failure risk.
- Never add credentials, copied user configuration, personal task IDs, source CSVs, DuckDB databases, analysis outputs, or live ClickUp content.
- Keep `agents/openai.yaml` consistent with the skill name and invocation policy.

## Validation

Run:

```powershell
pwsh -File .\scripts\validate-repository.ps1
pwsh -File .\scripts\test-install-skill.ps1
```

Both commands must pass before review. A reviewer should also check that the skill stays within its stated boundary and does not grant itself permission for external writes.
