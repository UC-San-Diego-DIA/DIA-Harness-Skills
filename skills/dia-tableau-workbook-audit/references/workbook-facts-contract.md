# workbook-facts.yaml contract (schema version 1)

This file describes the facts that `$dia-tableau-workbook-intake` extracts from one Tableau workbook package or workbook XML document. Audit skills must treat these fields as the only factual source about the workbook.

## Top-level fields

- `schema_version`: fixed `1`. Stop on any other value.
- `workbook`: `name` (input file name without extension), `tableau_version`, `source_build`, `source_platform`, and `repository_location` (the Tableau Server location the workbook was published from, when present).
- `extraction`: `container` (`twbx` or `twb`), `entry` (the workbook XML entry inside a package), `timestamp` (extraction time in UTC), and `warnings` (extraction warnings that must be reported in the audit).
- `datasources`: one entry per workbook-level data source with `name` and `caption` (null when the data source has no caption, such as the `Parameters` data source).
- `parameters`: one entry per workbook parameter with `datasource`, `name`, `caption`, and `members` (allowed values).
- `dashboards`: one entry per dashboard, in workbook order.
- `worksheets`: one entry per worksheet, in workbook order, including sheets never shown on a dashboard.
- `derived`: `sheets_on_dashboards`, `orphan_sheets`, and `duplicate_name_groups`. The audit must report orphan sheets, not hide them.

## Dashboard fields

- `name`: dashboard name.
- `datasources`: captions of the data sources the dashboard references.
- `size`: fixed or automatic size attributes such as `sizing_mode`, `minwidth`, and `minheight`.
- `title_text`: the dashboard title and subtitle text, normalized.
- `sheets`: worksheet names placed on the dashboard, in layout order.
- `layout`: every non-container zone in layout order. Each entry has a `kind` of `sheet`, `filter`, `legend`, `parameter`, `title`, `text`, `image`, `web`, or `other`, plus kind-specific fields.
- `filters`: quick filters with `source_sheet`, `field`, `field_caption` (workbook caption when available, otherwise the readable column name), `mode`, `show_apply`, and `values`.
- `legends`: legends with `legend_kind` (color, size, or shape), `source_sheet`, `field`, and `field_caption` (same resolution rule).
- `parameter_controls`: parameter controls with `parameter` and `caption`.
- `actions`: dashboard actions with `title` and `source_sheet`, when present.

## Worksheet fields

- `name`: worksheet name.
- `title_text`: the sheet title and caption text, normalized; empty when the sheet has no title.
- `datasources`: data source names the sheet references.
- `rows` and `cols`: field tokens on the rows and columns shelves, in shelf order.
- `calculations`: one entry per calculation field with `caption`, `kind` (Tableau calculation class), and `formula` (verbatim Tableau formula text).
- `filters`: sheet-level filters with `column`, `column_caption` (same resolution rule), and `class`.
- `mark_types`: mark types such as `Automatic` or `bar`.
- `encodings`: mark encodings with `attr` (color, size, label, and similar), `field`, and `field_caption` (same resolution rule).

## Normalization rules

- Title text joins formatted-text runs with a space-pipe-space separator between lines; the Tableau line-separator glyph U+00C6 is removed.
- Formulas are kept verbatim, including line breaks.
- Parameter member values keep their contents without the surrounding double quotes Tableau stores.

## Interpretation rules

- The audit reports facts only. It must not recommend renames, deletions, redesigns, or business interpretations.
- Any statement not supported by a fact field must read `Not recorded in the workbook facts.`
