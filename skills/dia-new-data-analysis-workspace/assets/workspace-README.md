# {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

## Data sources

{{DATA_SOURCES}}

## How this workspace works

Data flows in one direction:

- `data/raw/` holds the untouched source files. Load scripts read from here; nothing edits these files.
- `scripts/` holds the numbered pipeline. Run scripts in dependency-level order; independent scripts that share a number can run in any order.
- `data/output/` holds the transformed, analysis-ready tables the scripts produce.
- `reports/` holds dashboards and exports, connected to `data/output/`.

`scripts/README.md` is the pipeline manifest: one line per script describing what it reads and what it writes. Start there to understand the project.

## Newcomer notes

- `scratch/` is for exploration and throwaway work. It is safe to delete.
- A script earns a place in `scripts/` only when it is part of the pipeline: it reads from `data/raw/` or an earlier script's output and writes to `data/output/` or feeds the reports. Everything else belongs in `scratch/`.
- Document fields in `docs/data-dictionary.md` as they are used: what each field means, where it comes from, and who owns it.
