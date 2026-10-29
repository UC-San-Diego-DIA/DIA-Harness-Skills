# Documentation templates

Use these structures for the four final documents. Replace bracketed placeholders with facts or with `Needs analyst confirmation.` Never leave a template placeholder in a written document.

## Overview card

```markdown
# [model.name]

[model.description, copied as source description]

## Model card

| Attribute | Value | Evidence |
| --- | --- | --- |
| Model name | [model.name] | `model.name` |
| BI Publisher build | [value or Needs analyst confirmation.] | `model.bi_publisher_build` |
| Modified | [value or Needs analyst confirmation.] | `model.modified_at` |
| Data sources | [comma-separated data_sources values] | `data_sources` |
| Dataset | [dataset name and type] | `datasets[0].name`, `datasets[0].type` |
| Source tables | [count and names] | `datasets[0].sql_summary.source_table_count`, `datasets[0].source_tables` |
| Output columns | [count] | `output_columns` |
| Parameters | [count and names, or none] | `parameters` |
| Bursting | [confirmed summary, or none] | `bursting` |

## What it contains

- [One confirmed sentence describing the SQL scope, traced to a query fact.]
- [One confirmed sentence describing the output structure, traced to output_columns.]

## Grain

[One confirmed sentence describing one output row. Cite the main query and grouping evidence. If grain is not established, use Needs analyst confirmation.]

## Confidence and open questions

- [Each missing business definition, scope boundary, or ownership fact, marked Needs analyst confirmation.]
```

## Data dictionary

```markdown
# Data dictionary: [model.name]

This dictionary describes the BI Publisher output fields. It is derived only from [extraction.source_file].

## Output columns

| # | Output name | Label | Data type | Group | Source expression | Business definition |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [name] | [label] | [data_type] | [group] | [matching select alias expression] | [plain, non-technical definition or Needs analyst confirmation.] |

Match an output column to a selected expression by comparing names case-insensitively. When no match exists, use the output column's `value` and mark the business definition for analyst confirmation.

Every row traces to `output_columns` and the matched select alias in `datasets[*].main_query.select_aliases`; that shared fact path in the section introduction replaces a per-row evidence column.

Write the business definition in plain, non-technical language a business reader can use without knowing Oracle schema names or SQL. State the best definition the facts support; use `Needs analyst confirmation.` only when the facts leave the meaning genuinely open.

## Source tables

| Source table | Aliases | Referenced by | Evidence |
| --- | --- | --- | --- |
| [table] | [aliases or none] | [referenced_in] | `datasets[0].source_tables[index]` |

## Parameters

[If no parameters exist, write: This model has no parameters. Otherwise use one row per parameter with its name, type, default, and evidence. Mark unknown business meaning as Needs analyst confirmation.]

## Interpretation limits

- [Each warning or extraction limitation.]
- [Each field whose business definition is not established in the facts.]
```

## Business questions catalog

```markdown
# Business questions: [model.name]

These questions were confirmed by [analyst or role supplied by user] on [date]. Each question is answerable from the documented model.

## BQ-01: [confirmed question]

**What it answers**

[One to three plain sentences. Lead with what the model returns, stated only from facts.]

**Fields that matter**

- [Output column] — [one short phrase: its role in the answer.]

**Logic that shapes the answer**

- [Filter, join, grouping, or CASE mapping] — [plain-English effect on the answer.]

**Read it with care**

- [Confirmed condition that changes interpretation] — [plain-English interpretation effect.]

**Status:** Confirmed

## Out of scope

- [Confirmed question the model cannot answer] — [the missing filter, field, grain, or source, in plain English.]
```

Number questions sequentially as `BQ-01`, `BQ-02`, and so on. Add one section per confirmed question. Do not add an unconfirmed question.

## When-to-use guidance

```markdown
# When to use: [model.name]

## Use this model when

- [Each confirmed use case, with evidence from fields, filters, or output columns.]

## Do not use this model when

- [Each confirmed exclusion, with evidence from the model's filters or scope.]
- [Each question requiring data the model does not include.]

## Gotchas

| Gotcha | Why it matters | Evidence |
| --- | --- | --- |
| [Confirmed gotcha] | [Confirmed interpretation effect] | [fact path] |

## Unknowns

- [Each unresolved business rule, ownership question, refresh cadence, or definition, marked Needs analyst confirmation.]

## Related facts

- Facts file: [absolute model-facts.yaml path]
- Extraction container: [extraction.container]
- Extraction time: [extraction.extracted_at]
```

## Writing rules

- Keep the four documents mutually consistent. If a fact changes, update every affected document.
- Prefer exact source terms over synonyms for tables, aliases, columns, and parameters.
- Write definitions and explanations as prose. Never copy raw fact values such as Python tuple strings, YAML anchors, or literal quote-wrapped source comments into a definition cell.
- Keep tables narrow. If a cell would hold more than about one line of text, shorten it and move the detail to a bullet under the table, or split the row.
- Keep SQL fragments short and quote them exactly when needed. Do not reformat SQL in a way that changes meaning.
- Do not expose credentials. If a fact appears to contain a secret, omit the value and tell the user.
- Do not claim data quality, refresh schedule, ownership, or business purpose unless the user confirmed it during this run.
- Do not include institutional email addresses or catalog paths in final documentation unless the user confirms they are appropriate.
