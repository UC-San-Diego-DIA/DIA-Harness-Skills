# KPI mapping contract

This contract describes `kpi-mapping.yaml` schema version 1, the optional machine-readable companion to `KPI-Data-Mapping-YYYY-MM-DD-<topic>.md`. Write it only when it genuinely adds value for the user's follow-up work, and keep it consistent with the Markdown report.

## Top-level object

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Contract version. This skill writes only `1`. |
| `generated_at` | string | ISO-8601 date the mapping was confirmed. |
| `kpi_artifact` | string | File name of the source `Business-Questions-and-KPIs-*.md`. |
| `dataset` | object | Dataset identity and schema. |
| `kpis` | array of objects | One entry per mapped KPI, in report order. |

## Dataset object

| Field | Type | Meaning |
| --- | --- | --- |
| `file` | string | Dataset path relative to the report location. |
| `columns` | array of objects | One entry per column, in file order, each with `name` (exact header text) and `apparent_type` (`text`, `number`, `date`, or `unknown`). |
| `row_count_estimate` | integer | Approximate row count. |

## KPI object

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | KPI identifier, matching the report section and the artifact when it records one. |
| `name` | string | KPI name copied from the artifact. |
| `status` | string | `mapped`, `partial`, or `blocked`. |
| `required_fields` | array of objects | Each has `component` (from the KPI definition) and `field` (exact dataset field name, or null for a data gap). |
| `calculation` | string | The formula to build against the exact field names. |
| `grouping` | array of strings or null | Grouping fields, or null when not established. |
| `time_period` | string or null | Stated period, or null when not established. |
| `filters` | array of strings | Each filter; empty when none are recorded. |
| `assumptions` | array of strings | Stated as assumptions, not facts. |
| `data_gaps` | array of objects | Each has `missing` (the component) and `request` (what to ask stakeholders or source systems for). |
| `open_questions` | array of strings | Unresolved questions carried from the artifact. |

## Writing rules

- Keep the YAML consistent with the Markdown report. If the report changes, update the YAML in the same step.
- Copy field names exactly as they appear in the dataset schema.
- Use null, not a guess, for grouping or time period the artifact does not establish.
- Never write computed values into the file. This contract documents what to build, not results.
- Do not include absolute paths, credentials, or sample data values.
