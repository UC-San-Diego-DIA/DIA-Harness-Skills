# Documentation templates

Use these structures for the four final documents. Replace bracketed placeholders with facts or with `Needs analyst confirmation.` Never leave a template placeholder in a written document.

## Ownership map

Each content item lives in exactly one document. Every other document links to the owner instead of restating it.

| Content item | Owner | Everyone else |
| --- | --- | --- |
| Extraction provenance, schema version, content hash, model and dataset IDs | `model-facts.yaml` | Overview cites it once |
| Grain contract (one sentence) | `data-model-profile.md`, its grain section | Overview links to it; the docs never derive their own grain sentence |
| Filters, exclusions, time windows, join fan-out, row-count risk | `data-model-profile.md` | Referenced by section name, never restated |
| CASE and hard-coded logic mappings | `data-model-profile.md` | Dictionary and KPI catalog cite the section or column; never re-derive |
| Column-level facts: name, type, example, missing-value behavior, constraint, source expression | `data-dictionary.md` | No column table anywhere else |
| Canonical KPI formulas and business-question definitions | `kpis-and-questions.md` | `when-to-use.md` links by KPI ID, never restates a formula |
| Use cases, exclusions, adoption guidance | `when-to-use.md` | Overview links; the catalog does not restate use cases |
| Open questions and unknowns | One register in `overview.md` | Other documents link to register entries by ID |

When no profile exists, the grain, filters, join risk, and CASE items become open-questions register entries; do not draft interpretations for them.

## Overview card

```markdown
# [model.name]

[model.description, copied as source description]

Status: [Confirmed | Candidate]

**Who this serves:** [one line naming the audience, for example analysts and report developers who use this model].
**What this answers:** [one line naming the question this document answers, for example what this data model contains and how reliable its structure is.]

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

[When `schema_version: 2` supplies them, add one row citing the provenance or ID fields the intake contract defines, such as model ID, content hash, and extraction timestamp. Do not invent field names the intake contract does not define.]

## What it contains

- [One confirmed sentence describing the SQL scope, traced to a query fact.]
- [One confirmed sentence describing the output structure, traced to output_columns.]

## Structure

This is an analyst-facing documentation set. Structural interpretation lives elsewhere, owned where the facts were analyzed:

- **Grain:** the one-sentence contract for what one output row represents is owned by the profile document `data-model-profile.md` in its grain section. Read it before summing or averaging any column.
- **Filters, exclusions, and time windows:** owned by the profile's filters section.
- **Join fan-out and row-count risk:** owned by the profile's joins section.
- **Hard-coded logic:** owned by the profile's hard-coded-logic section.

[When no profile exists, replace each bullet with a link to the matching open-questions register entry below and do not state the interpretation.]

## Open questions

The register below is the single place where unresolved questions live. Other documents link here by entry ID.

| ID | Question | Affected document | Severity | Status |
| --- | --- | --- | --- | --- |
| OQ-01 | [question] | [data-dictionary.md \| kpis-and-questions.md \| when-to-use.md] | [high \| medium \| low] | [Open \| Resolved] |

[In confirmed mode, include only questions the user confirmed belong there, with status Open or Resolved as confirmed. In draft mode, include every unconfirmed item: every `Needs analyst confirmation.` point in any of the four documents must appear here exactly once.]
```

## Data dictionary

```markdown
# Data dictionary: [model.name]

This dictionary describes the BI Publisher output fields. It is derived only from [extraction.source_file].

Status: [Confirmed | Candidate]

## Output columns

[One row per output column. Fill Example, Missing value behavior, and Constraint only where the facts support them; otherwise leave the cell as `Not stated in facts.`]

| # | Output name | Label | Data type | Group | Example | Missing value behavior | Constraint | Business definition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [name] | [label] | [data_type] | [group] | [example or Not stated in facts.] | [missing-value behavior or Not stated in facts.] | [constraint or Not stated in facts.] | [plain, non-technical definition or Needs analyst confirmation. OQ-xx] |

Match an output column to a selected expression by comparing names case-insensitively. When no match exists, use the output column's `value` and mark the business definition for analyst confirmation, with a register link such as `OQ-01` in the overview document's open-questions section.

Every row traces to `output_columns` and the matched select alias in `datasets[*].main_query.select_aliases`; that shared fact path in the section introduction replaces a per-row evidence column.

Write the business definition in plain, non-technical language a business reader can use without knowing Oracle schema names or SQL. State the best definition the facts support; use `Needs analyst confirmation.` only when the facts leave the meaning genuinely open, and link the register entry.

Keep source expressions, which are physical SQL, visually separate from business definitions. List them in the next table, never in the definition column above.

## Source expressions

| Output name | Source expression | Evidence |
| --- | --- | --- |
| [name] | [matching select alias expression, quoted exactly] | `datasets[0].main_query.select_aliases[name=...]` |

For columns whose logic is hard-coded, do not restate the CASE or rule here. Cite the profile section that owns the mapping, for example: `Hard-coded logic: see data-model-profile.md, hard-coded-logic section.`

## Grain note

What one output row represents is owned by the profile document `data-model-profile.md` in its grain section. This dictionary does not restate it.

[When no profile exists, replace this note with a link to the open-questions register entry for grain.]

## Source tables

| Source table | Aliases | Referenced by | Evidence |
| --- | --- | --- | --- |
| [table] | [aliases or none] | [referenced_in] | `datasets[0].source_tables[index]` |

## Parameters

[If no parameters exist, write: This model has no parameters. Otherwise use one row per parameter with its name, type, default, and evidence. Mark unknown business meaning as Needs analyst confirmation.]

## Interpretation limits

[Extraction warnings are reported once per run in chat and are not restated in the documents. List only reading limits specific to the dictionary, plus a link to the open-questions register entry that owns any unresolved interpretation. Do not copy the register table here.]
```

## KPI and business-questions catalog

```markdown
# KPIs and business questions: [model.name]

Candidate KPIs and confirmed business questions for this model, derived only from [extraction.source_file] and confirmed by [analyst or role supplied by user] on [date].

Status: [Confirmed | Candidate]

## How KPIs and business questions differ

- A **business question** is a question the model can answer on demand. You run the model, read the result, and act; the definition lives in the question itself.
- A **KPI** is a standing measure tracked repeatedly over time. It has a fixed name, one canonical formula over the model's output rows, and a decision it informs. A KPI answers the same question every period without re-deciding what to compute.

## Before you compute anything

The grain contract and the structural caveats that affect every calculation live in the profile document `data-model-profile.md`. Read its grain section and its filters and joins sections before computing anything. This catalog does not restate them.

[When no profile exists, link the open-questions register entries that own grain and join risk instead.]

## KPI-01: [name]

**Tags:** [controlled vocabulary terms, comma-separated. Omit this line when no vocabulary file was provided or no term is mapped.]

**What it measures:** [One sentence in business terms, stated only from output columns and confirmed facts.]

**Why it matters:** [One or two sentences on the decision, risk, or recurring question this measure informs. If the facts do not establish the business value, write Needs analyst confirmation.] and link its register entry from the overview document's open-questions section.

**Canonical formula:** [Exactly one formula over the model's output rows, such as `sum(PO_DISTRIBUTION_AMOUNT)` or `count(distinct PO_HEADER_ID)`, keyed to the columns it uses. This is the only place the formula appears.]

**Evidence:** [The fact paths for each column in the formula, such as `output_columns[name=PO_DISTRIBUTION_AMOUNT]`.]

**Status:** [Confirmed | Candidate]

## Business questions

## BQ-01: [question]

**Tags:** [controlled vocabulary terms mapped from this question's key fields. Omit when no vocabulary applies.]

**What it answers**

[One to three plain sentences. Lead with what the model returns, stated only from facts.]

**Fields that matter**

- [Output column] — [one short phrase: its role in the answer.]

**Logic that shapes the answer**

[Cite profile sections by name for filters, time windows, and join effects. Do not restate their content. Example: `Filters and the rolling creation-date window: see data-model-profile.md, filters section.` When no profile exists, link the open-questions register entry instead.]

**Read it with care**

[One line per confirmed interpretation condition, with its open-questions register ID if it is unresolved. Do not duplicate register content.]

**Status:** [Confirmed | Candidate]

## Out of scope

- [Confirmed KPI or question the model cannot support] — [the missing filter, field, grain, or source, in plain English.]

## Suggested starting set

- [When more than three KPIs are confirmed, name the two or three to start with and the recurring leadership question each answers. Omit this section with three or fewer.]
```

Number KPIs sequentially as `KPI-01`, `KPI-02`, and so on, and questions as `BQ-01`, `BQ-02`, and so on. Add one section per KPI and per question. Give each KPI exactly one canonical formula; no other document may repeat it. Propose only KPIs buildable from the model's output columns; anything needing data the model does not select belongs under Out of scope, not as an invented KPI.

## When-to-use guidance

```markdown
# When to use: [model.name]

Status: [Confirmed | Candidate]

## Use this model when

- [Each confirmed use case, written from this document's ownership: the business situation, the KPI IDs that serve it as relative links into `kpis-and-questions.md`, and evidence from fields or filters. Never restate a KPI formula here.]

## Do not use this model when

- [Each confirmed exclusion, with evidence from the model's filters or scope.]
- [Each question requiring data the model does not include.]

## Structural caveats

The caveats that change every answer live where they were analyzed:

- Grain and row-count effects: the profile document's grain section and joins section.
- Filters, exclusions, and time windows: its filters section.
- Hard-coded logic: its hard-coded-logic section.

This document does not restate them.

[When no profile exists, replace each bullet with a link to its open-questions register entry in the overview document's open-questions section.]

## Open questions

All unresolved questions live in the register in the overview document's open-questions section. Relevant entries for this document: [comma-separated register IDs, or none].

## Related facts

- Facts file: [absolute model-facts.yaml path]
- Extraction container: [extraction.container]
- Extraction time: [extraction.extracted_at]
```

## Writing rules

- Enforce the ownership map: the grain sentence, filter and join content, CASE mappings, and each KPI formula appear in exactly one owner. Every restatement elsewhere is a defect.
- Keep the four documents mutually consistent. If a fact changes, update the owning document and any links.
- Prefer exact source terms over synonyms for tables, aliases, columns, and parameters.
- Write definitions and explanations as prose. Never copy raw fact values such as Python tuple strings, YAML anchors, or literal quote-wrapped source comments into a definition cell.
- Keep tables narrow. If a cell would hold more than about one line of text, shorten it and move the detail to a bullet under the table, or split the row.
- Keep SQL fragments short and quote them exactly when needed. Do not reformat SQL in a way that changes meaning.
- Do not expose credentials. If a fact appears to contain a secret, omit the value and tell the user.
- Do not claim data quality, refresh schedule, ownership, or business purpose unless the user confirmed it during this run.
- Do not include institutional email addresses or catalog paths in final documentation unless the user confirms they are appropriate.
