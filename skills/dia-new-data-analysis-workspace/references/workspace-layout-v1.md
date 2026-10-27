# Data analysis workspace, schema 1

Use this reference when planning, creating, or validating a local data-analysis workspace.

## Terms

- A **data analysis workspace** is a fresh local working area for one analysis project. It is not connected to ClickUp, GitHub, or any external system.
- **Raw inputs** are the untouched source files, usually Excel exports, placed in `data/raw/`.
- **Pipeline scripts** are the numbered scripts in `scripts/` that transform raw inputs into analysis-ready output.
- **Output tables** are the transformed, analysis-ready tables in `data/output/` that dashboards connect to.

## Required structure

```text
<workspace name>/
|-- README.md
|-- AGENTS.md
|-- data/
|   |-- raw/
|   `-- output/
|-- scripts/
|   `-- README.md
|-- reports/
|-- docs/
|   |-- data-dictionary.md
|   `-- presentations/
`-- scratch/
```

Folder responsibilities are fixed in schema 1:

- `data/raw/` holds immutable source files. Load scripts read from here; nothing edits these files.
- `data/output/` holds transformed tables written by pipeline scripts and read by dashboards. Never edited by hand.
- `scripts/` holds the numbered pipeline, run in dependency-level order. Its `README.md` is the pipeline manifest.
- `reports/` holds dashboards and exports, connected to `data/output/` only.
- `docs/` holds project documentation, the data dictionary, and `docs/presentations/` for project presentations.
- `scratch/` holds exploration and throwaway work. It is safe to delete.

The skill intentionally omits `sql/`, `src/`, `notebooks/`, and version-control files. Add `sql/` only if a project later needs standalone reusable queries. Promotion of shared logic happens inside pipeline scripts, not in a separate module folder.

## Pipeline conventions

- A script earns a place in `scripts/` only if it is part of the pipeline: it reads from `data/raw/` or an earlier script's output, and it writes to `data/output/` or feeds the reports. Everything else lives in `scratch/`.
- A script's number is one more than the highest number of anything it reads. Independent scripts may share a number. Example: `01_load_tables.py`, `02_combine_orders_customers.py`, `02_clean_sales.py`, `03_build_summary.py`.
- A script may read only from `data/raw/` or from the output of a lower-numbered script. This keeps the dependency graph acyclic.
- Keep the `scripts/README.md` manifest current with one line per script describing what it reads and what it writes.
- Delete obsolete scripts instead of archiving them; the workspace shows the current pipeline. Move anything worth remembering into `scratch/` first.

## Invariants

- A setup run never overwrites, moves, renames, or deletes existing local content. It only adds missing files and folders.
- The workspace is created locally only, with no repository, remote, or external service connection.
- The generated `README.md`, `AGENTS.md`, and manifest are starting points the user may edit; the helper preserves existing versions.
