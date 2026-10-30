# Profile template

Use this structure for the single `data-model-profile.md` output. Replace bracketed placeholders with facts or with a link to an open-questions register entry. Never leave a template placeholder in the written document. Cite a fact path once per section when every claim in that section shares the same path, and per item when they differ. Keep tables narrow: if a cell would hold more than about one line of text, shorten it and move the detail to a bullet.

Unresolved interpretations never appear as inline `Needs analyst confirmation` text. They live only in the open-questions register, and the body links to them by ID, like `(see OQ-01)`.

```markdown
# Data model profile: [model.name]

Derived only from [extraction.source_file]. Extracted [extraction.extracted_at]. Container: [extraction.container].

Extraction warnings (reported verbatim, unedited): [each warning string, or "None declared."] Evidence: `warnings`.

## Quick take

- **Grain:** [one-line meaning of one output row from the grain contract, or "Open question OQ-xx."]
- **Biggest row-count risk:** [the join or dedup pattern most likely to surprise someone summing the output, stated with its risk-table row, e.g. "Row-count risk R-02."]
- **Time window:** [one line, or None declared.]
- **Logic to watch:** [the one or two hard-coded rules most likely to change answers silently.]

## 1. Grain contract

[One sentence stating what one output row represents. Cite the join conditions, grouping, and output columns that support it.]

**Unique at grain:** [each column that should be unique at this grain, each with its fact path; or "Open question OQ-xx."]

In practice:

- [Concrete multiplication example: an invoice with X distributions and Y payments produces Z rows.]
- [What summing the main amount column totals, and when it double-counts. Evidence: `fact path`.]

## 2. Filters, exclusions, and windows

Fact paths: `datasets[*].main_query.clauses.where`, `datasets[*].ctes[*].clauses.where`.

| Filter | Excludes | Effect on interpretation |
| --- | --- | --- |
| [condition] | [what rows are removed] | [what questions it prevents or narrows] |

**Time window**: [date range or relative window from the filters, or None declared.]

**Window functions**

- [Function] in [CTE or query] — [its role]. Evidence: `fact path`.

## 3. Hard-coded business logic

One value table per CASE rule, ordered by how much each can change an answer.

### [Output column] (from [CTE or main query])

| Source value | Target value | Affected output column | Unmapped |
| --- | --- | --- | --- |
| [WHEN condition or value] | [THEN value] | [output column] | no |
| [any other value / ELSE] | [ELSE value or null] | [output column] | yes |

- **Why it matters:** [why an analyst should know before using the output].
- **Evidence:** `fact path`.

## 4. Deduplication and join patterns

### Deduplication

- [Pattern] in [CTE or query] — [what it deduplicates or collapses]. Evidence: `fact path`.

### Joins

Fact paths: `datasets[*].main_query.joins`.

**Joins that change row counts**

| Join | Type | Condition | Row-count risk |
| --- | --- | --- | --- |
| [left side] to [target] | [INNER/LEFT/CROSS] | [ON condition] | [drops rows / duplicates rows; reference the risk-table row, e.g. R-01] |

**One-row lookups** (LEFT joins that add at most one row per output row)

- [Left side] to [target] on [condition].

## 5. Row-count risk

Fact paths: `datasets[*].main_query.joins`, `datasets[*].ctes[*]`.

| ID | Expected count (derived from structure) | Observed count | Delta | Cause |
| --- | --- | --- | --- | --- |
| R-01 | [structural formula, e.g. one row per [entity] after [join] drops] | not measurable offline | not measurable offline | [join type, filter, or dedup pattern that produces the count, with evidence path] |

Without a database connection, observed and delta are `not measurable offline`. Every risk claim about row counts must be a row in this table; the rest of the profile may describe patterns but may not assert risk in prose only.

## 6. Candidate checks

| ID | Finding | Assertion (tool-neutral) | Type | Offline | Evidence |
| --- | --- | --- | --- | --- | --- |
| C-01 | [structural finding] | [assertion, e.g. `unique(<column>)` or `row_count() = <structural expectation>`] | [uniqueness / row-count / join fan-out / null expectations] | yes or no | `fact path` |

`Offline: yes` means the assertion can be verified from the facts file alone (for example, a single-column GROUP BY that structurally guarantees uniqueness). `Offline: no` means it needs the model's data; name what it needs, such as row counts or key samples.

## 7. Source-table lineage

| CTE or query | Source tables | Feeds into | Notes |
| --- | --- | --- | --- |
| [CTE name] | [source tables it reads] | [downstream CTE or main query] | [brief structural note from comments or logic] |

**Lineage paths** (one bullet per output column group)

- [Source tables] -> [CTE] -> [main query] -> [output column group]

## 8. Open-questions register

| ID | Question | Evidence path | Owner | Status |
| --- | --- | --- | --- | --- |
| OQ-01 | [question the facts cannot settle] | `fact path` | [owner or unassigned] | [open] |

The body links to register entries by ID instead of restating them. Every interpretation the facts do not establish must have a register entry; no `Needs analyst confirmation` text appears anywhere else in the profile.
```

## Writing rules

- Preserve source capitalization for tables, aliases, columns, CTE names, and query names.
- Quote SQL fragments exactly when they appear in the profile. Do not reformat SQL in a way that changes meaning.
- Every claim in the profile must be traceable to a cited fact path, at section level when rows share a path.
- Every row-count risk must be quantified as a row in the row-count risk table. Never leave a risk claim in prose only.
- Every CASE mapping must be a value table with source value, target value, affected output column, and an unmapped marker that includes the ELSE branch or the absent-ELSE null.
- Every unresolved interpretation lives in the open-questions register with an evidence path, owner, and status; the body links to it by ID and does not restate the question.
- Prefer bullets over wide tables when a cell would hold a full sentence or more.
- Do not include institutional email addresses or catalog paths in the profile unless the user confirms they are appropriate.
