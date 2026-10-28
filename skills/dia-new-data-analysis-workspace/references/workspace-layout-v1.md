# Data analysis workspace, schema 1

Use this reference when planning, creating, or validating a local data-analysis workspace.

## Terms

- A **data analysis workspace** is a fresh local working area for one analysis project. It is not connected to ClickUp, GitHub, or any external system.
- **Raw inputs** are the untouched source files, usually Excel exports, placed in `data/raw/`.
- **Pipeline scripts** are the numbered scripts in `scripts/` that transform raw inputs into analysis-ready output.
- **Output tables** are the transformed, analysis-ready tables in `data/output/` that dashboards connect to.
- **Analysis workspaces** are per-file DuckDB analysis folders under `scratch/analysis/`, created by the `$dia-analyze-local-data` skill. They keep ad hoc analysis separate from the pipeline.

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
|   |-- presentations/
|   `-- transcripts/
`-- scratch/
    `-- analysis/
```

Folder responsibilities are fixed in schema 1:

- `data/raw/` holds immutable source files. Load scripts read from here; nothing edits these files.
- `data/output/` holds transformed tables written by pipeline scripts and read by dashboards. Never edited by hand.
- `scripts/` holds the numbered pipeline, run in dependency-level order. Its `README.md` is the pipeline manifest.
- `reports/` holds dashboards and exports, connected to `data/output/` only.
- `docs/` holds project documentation, the data dictionary, `docs/presentations/` for project presentations, and `docs/transcripts/` for saved meeting transcripts.
- `scratch/` holds exploration, throwaway work, and analysis workspaces under `scratch/analysis/`. Throwaway work there is safe to delete, but analysis workspaces keep question history; do not delete them casually.

The skill intentionally omits `sql/`, `src/`, `notebooks/`, and version-control files. Add `sql/` only if a project later needs standalone reusable queries. Promotion of shared logic happens inside pipeline scripts, not in a separate module folder.

## Transcripts and meeting outputs

- `docs/transcripts/` holds saved meeting transcripts, such as a Zoom export pasted into a transcript skill. A transcript the user supplies at an existing path stays where it is; skills do not copy or move it.
- Transcript-derived artifacts keep their standard filenames and are saved in `docs/`: meeting notes, requirements documents, process outlines, process-map diagrams, and business-questions-and-KPIs files with `kpi-facts.yaml`.
- Transcripts are meeting evidence, not pipeline inputs. Pipeline scripts never read from `docs/transcripts/`, and reading a transcript never earns a script a place in `scripts/`.

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
