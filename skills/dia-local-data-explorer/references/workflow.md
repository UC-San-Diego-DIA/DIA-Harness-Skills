# Runtime and project contract

Run `python <skill>/scripts/local_data_explorer.py --help`. The installer bundles the maintained `duckdb_analysis.py` engine; no separate analysis skill installation is needed. Source-tree execution finds that same maintained helper in the repository. Python dependencies are `duckdb>=1.4,<2` and `pytz>=2024.1`. The engine controls Excel extension installation and CSV parsing. This skill uses its helper API, not the other skill's workflow.

## User flow

```text
$dia-local-data-explorer Use C:\Exports\activity.xlsx
  -> choose a sheet and new project folder if missing
  -> create guidance and a checked copy of the file
"How many requests were completed each month?"
  -> clarify completed/date definitions if needed, run SQL, explain answer
"Show that as a line chart. Save it."
  -> preview and save that exact visual
"Which teams have the largest backlog?"
  -> calculate, explain, preview a bar chart
"Save that too. Build my dashboard."
  -> include the two saved visuals in a local offline HTML dashboard
```

## Layout

```text
<new-project>/
  AGENTS.md                 guidance for future chats
  README.md                 purpose, locations, resume prompt
  explorer.json             schema-1 identity, field inventory, selections
  data/raw/dataset.csv      immutable copy, or dataset.xlsx
  data/output/              reserved; no pipeline in v1
  scripts/README.md         records that execution uses installed helpers
  scratch/analysis/dataset/ engine link, ANALYSIS.md, successful SQL
  questions/q-<id>.json     question, exact SQL result, note, provenance
  visuals/v-<id>.json       chart definition, question ID, selection state
  visuals/v-<id>.html       offline preview
  reports/dashboard-<id>.html
```

This is an explorer project with engine-compatible markers. It is distinct from the numbered-pipeline schema-1 data analysis workspace. Reports embed stored exploration results. Do not claim that `data/output/` feeds these reports or call the new-workspace skill.

## Commands

Use absolute Windows paths and literal arguments. For multiline SQL, write a UTF-8 file in a known temporary location, pass that exact path, and delete only that temporary file afterward. Never interpolate cell content into a command. Commands return JSON and failures exit nonzero.

```powershell
python <helper> inspect --source <absolute-file>
python <helper> init --project <absolute-new-folder> --source <absolute-file> --title "Service activity" --sheet "Activity"
python <helper> status --project <absolute-project>
python <helper> ask --project <absolute-project> --question "Completed by month?" --sql-file <absolute-query.sql> --note "Count rows with status = Complete; group by completion month; exclude missing dates."
python <helper> visual --project <absolute-project> --question-id q-<id> --kind line --x month --y completed --title "Completed requests by month"
python <helper> save --project <absolute-project> --visual-id v-<id>
python <helper> unsave --project <absolute-project> --visual-id v-<id>
python <helper> build --project <absolute-project>
```

`init` also accepts `--install-excel-extension` after approval and CSV overrides `--delimiter`, `--encoding`, `--quote`, `--escape`, `--skip-rows`, `--date-format`, `--timestamp-format`, `--all-varchar`, `--null-padding`, and `--force-header`. Run `--help` for syntax. Use overrides only when the user/file format supports them. A failed setup can leave a partial project, which must be reported and preserved.

`ask` returns at most 1,000 rows, 200 by default via `--max-rows`. Every question result is saved automatically to support resumed conversations and visual provenance. This differs from the narrower analysis skill. `visual` refuses truncated results, duplicate column names, missing/nonfinite numeric values, duplicate x values, more than 100 bar/line points, or an empty result. A KPI needs exactly one numeric value. Table previews support up to the question limit. Zero and negative numbers are valid. Use SQL for missing-value treatment, category aggregation, chronological ordering, and deliberate top-N selection. Put those decisions in the note. V1 supports one numeric series per chart and no row-level dashboard filters.

`status` returns question summaries and visual titles/selection states without dumping all result rows. Read a specific question JSON when resuming a calculation. The project manifest preserves the original path/hash and snapshot path/hash, sheet, row count, normalized field names, engine link ID, interpreter, and setup options. Questions retain exact successful SQL and computed rows; visual records point to immutable question records. Save order determines dashboard order. `unsave` then `save` places a visual last. Dashboard builds record their visual IDs in the manifest and never overwrite earlier builds.

Run one writer per project. Helpers use a lock and atomic JSON replacement for normal operation; a crash can leave a lock. Investigate the recorded PID and partial state before manually removing only that project's `.explorer.lock`. Helpers fail when tracked paths leave the project or a snapshot hash changes. They are local workflow guards, not a sandbox for executing arbitrary untrusted code.
