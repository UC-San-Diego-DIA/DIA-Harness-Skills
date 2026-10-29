# Brand tokens live inside skill packages

DIA work repeatedly needs the official UC San Diego brand tokens, and the team wants visual outputs to stay consistent across skills. The question was whether skills should carry their own copy of the brand reference or consult a top-level shared reference in the repository.

The installer copies only the chosen skill folder into TritonAI Harness, so an installed skill cannot rely on any repository-level sibling existing on a staff member's computer. The repository validator also treats every folder under `skills/` as a complete skill package that must contain its own `SKILL.md`, so a shared token folder cannot live there without installer and validator changes.

Decision: each skill that needs brand tokens carries them inside its own package. `dia-dashboard-mockup` is the first skill to do this; its `assets/dashboard-mockup-template.html` embeds the core palette (Navy #182B49, Blue #00629B, Yellow #FFCD00, Gold #C69214) with the accent and neutral colors from the brand page. The brand page at https://brand.ucsd.edu/visual-brand/color/index.html (checked 2026-10-29) is the source of truth for the values.

Consequences: duplicated token values must be updated manually when the campus brand changes, which is acceptable while only one skill carries them. When a second skill needs the same tokens, revisit this decision with an installer change that delivers a shared reference alongside skills and a validator rule that keeps that reference intact, and record the outcome in a new ADR.
