# workbook-facts.yaml contract (schema version 2)

This file is the shared source of truth for `workbook-facts.yaml`. It describes the facts that `$dia-tableau-workbook-intake` extracts from one Tableau workbook package or workbook XML document. Audit and documentation skills must treat this file as the only factual source about the workbook; they must not keep their own copy of the contract.

## Top-level fields

- `schema_version`: fixed `2`. Consumers stop on any other value and report the version they found.
- `provenance`: `run_id`, `tool_version`, `input_file`, `input_sha256`, `container` (`twbx` or `twb`), `entry` (the workbook XML entry inside a package; empty for a bare `.twb`), `extracted_at` (UTC), and `schema_url`. `run_id` is the first 12 hexadecimal characters of SHA-256 over the UTF-8 string `"<input_sha256 or null>:<extracted_at>"`, so the same input bytes and timestamp always produce the same `run_id`. When a v1 file is migrated, `input_sha256` is `null` and `input_sha256_reason` is `migrated_from_v1`; `input_file` is the path of the migrated facts file.
- `workbook`: `name` (input file name without extension), `tableau_version`, `source_build`, `source_platform`, `repository_location` (the Tableau Server location the workbook was published from, when present), and `id` (the workbook_id).
- `extraction`: `container`, `entry`, `timestamp` (extraction time in UTC), and `warnings`. The free-text `warnings` list is kept for human readability; every warning entry must also exist as an `anomalies` record.
- `datasources`: one entry per workbook-level data source with `name`, `caption` (null when the data source has no caption, such as the `Parameters` data source), and `id` (the datasource_id).
- `parameters`: one entry per workbook parameter with `datasource`, `name`, `caption`, `members` (allowed values), and `id` (the param_id).
- `dashboards`: one entry per dashboard, in workbook order.
- `worksheets`: one entry per worksheet, in workbook order, including sheets never shown on a dashboard.
- `derived`: `sheets_on_dashboards`, `orphan_sheets`, and `duplicate_name_groups`, still by sheet name. The audit must report orphan sheets, not hide them; documentation must use only the sheets in `sheets_on_dashboards`.
- `completeness`: one record per top-level section (`dashboards`, `worksheets`, `parameters`, `datasources`); see below.
- `anomalies`: typed anomaly records; see below.
- `interpretation_inputs`: where analyst confirmations are stored; see below.

## Stable IDs

Every entity carries a stable, deterministic ID:

- `workbook_id`: lowercase slug of the workbook name, hyphens for spaces.
- `dashboard_id`: `<workbook_id>__dash__<slug of dashboard name>`.
- `sheet_id`: `<workbook_id>__sheet__<slug of worksheet name>`.
- `calc_id`: `<sheet_id>__calc__<slug of caption>`.
- `param_id`: `<workbook_id>__param__<slug of caption>`.
- `datasource_id`: `<workbook_id>__ds__<slug of datasource name>`.

Slug rule: lowercase the text, replace spaces, `/`, `(`, and `)` with `-`, collapse repeated hyphens into one, and strip trailing hyphens. IDs must be unique within the file; if a collision occurs, append `_2`, then `_3`, and record an `ID_COLLISION` anomaly naming the affected IDs. Because IDs are deterministic, the same workbook always produces the same IDs.

## completeness

One record per top-level section, in the order `dashboards`, `worksheets`, `parameters`, `datasources`:

- `section`: the section name.
- `expected`: the number of entities the workbook XML declares for that section.
- `found`: the number of entities recorded in the facts file.
- `skipped`: entities the extractor saw but did not record.
- `out_of_scope`: entities deliberately excluded, such as story sheets.
- `status`: `complete`, `partial`, or `out_of_scope`.
- `reason_code`: required when `status` is `partial`; a stable short code explaining the gap.

## anomalies

Typed records replace narrative warnings. Each record has:

- `code`: a stable string, for example `EMPTY_ZONE`, `DUPLICATE_SHEET_NAME`, `ORPHAN_SHEET`, `ID_COLLISION`, `UNRECOGNIZED_ZONE`, `MULTIPLE_TWB_ENTRIES`, `STORY_NOT_INVENTORIED`, `UNCLASSIFIED_WARNING`.
- `rule_version`: the contract or tool version whose rule produced the record.
- `affected_ids`: the stable IDs of the affected entities (empty when the anomaly has no entity, such as a story warning).
- `evidence`: fact paths that support the record.
- `count`: how many occurrences the record covers.
- `status`: `observed`, `not_found`, or `out_of_scope`.

Records appear in facts order and in the order the underlying facts were parsed. Every `extraction.warnings` entry must correspond to at least one anomaly record.

## interpretation_inputs

- `dashboard_purposes`: an array of confirmed dashboard purpose records: `dashboard_id`, `purpose`, `confirmed_at` (UTC), and `supporting_fact_id`.
- `sheet_roles`: an array of confirmed sheet-role records: `sheet_id`, `role`, `confirmed_at` (UTC), and `supporting_fact_id`. The role must come from the shared role vocabulary.

Both arrays are empty at extraction. They are written back only by the `$dia-tableau-dashboard-docs` confirmation flow into its `confirmations.yaml` sidecar, never hand-edited and never written into the extraction facts file itself.

## Dashboard fields

- `id`: the dashboard_id.
- `name`: dashboard name.
- `datasources`: captions of the data sources the dashboard references.
- `size`: fixed or automatic size attributes such as `sizing_mode`, `minwidth`, and `minheight`.
- `title_text`: the dashboard title and subtitle text, normalized.
- `sheets`: worksheet names placed on the dashboard, in layout order.
- `layout`: every non-container zone in layout order. Each entry has a `kind` of `sheet`, `filter`, `legend`, `parameter`, `title`, `text`, `image`, `web`, or `other`, plus kind-specific fields such as `name` for sheets or `field` for filters. Filter, legend, and parameter entries also carry `field_caption` (the workbook caption when available, otherwise the readable column name).
- `filters`: quick filters with `source_sheet`, `field`, `field_caption` (same resolution rule), `mode`, `show_apply`, and `values`.
- `legends`: legends with `legend_kind` (color, size, or shape), `source_sheet`, `field`, and `field_caption` (same resolution rule).
- `parameter_controls`: parameter controls with `parameter` and `caption`.
- `actions`: dashboard actions with `title` and `source_sheet`, when present.

## Worksheet fields

- `id`: the sheet_id.
- `name`: worksheet name.
- `title_text`: the sheet title and caption text, normalized; empty when the sheet has no title.
- `datasources`: data source names the sheet references.
- `rows` and `cols`: field tokens on the rows and columns shelves, in shelf order. Empty for single-value sheets such as KPI cards.
- `calculations`: one entry per calculation field with `id` (the calc_id), `caption`, `kind` (Tableau calculation class), and `formula` (verbatim Tableau formula text).
- `filters`: sheet-level filters with `column`, `column_caption` (same resolution rule), and `class`.
- `mark_types`: mark types such as `Automatic` or `bar`.
- `encodings`: mark encodings with `attr` (color, size, label, and similar), `field`, and `field_caption` (same resolution rule).

## Normalization rules

- Title text joins formatted-text runs with a space-pipe-space separator between lines; the Tableau line-separator glyph U+00C6 is removed.
- Formulas are kept verbatim, including line breaks.
- Parameter member values keep their contents without the surrounding double quotes Tableau stores.

## Interpretation rules

- The audit reports facts only. It must not recommend renames, deletions, redesigns, or business interpretations, and it must not restate content owned by another document.
- Title text is on-sheet wording, not confirmed business meaning. Formula text is Tableau syntax; translating it into business terms is an interpretation that needs analyst confirmation.
- Any statement not supported by a fact field must read `Not recorded in the workbook facts.` in audit output, or `Needs analyst confirmation.` in documentation output, and be traced to the containing fact path.
