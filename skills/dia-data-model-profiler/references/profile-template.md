# Profile template

Use this structure for the single `data-model-profile.md` output. Replace bracketed placeholders with facts or with `Needs analyst confirmation.` Never leave a template placeholder in the written document. Cite a fact path once per section when every claim in that section shares the same path, and per item when they differ. Keep tables narrow: if a cell would hold more than about one line of text, shorten it and move the detail to a bullet.

```markdown
# Data model profile: [model.name]

Derived only from [extraction.source_file]. Extracted [extraction.extracted_at]. Container: [extraction.container].

## Quick take

- **Grain:** [one-line meaning of one output row, or Needs analyst confirmation.]
- **Biggest row-count risk:** [the join or dedup pattern most likely to surprise someone summing the output.]
- **Time window:** [one line, or None declared.]
- **Logic to watch:** [the one or two hard-coded rules most likely to change answers silently.]

## 1. Grain and row-level meaning

[Proposed grain statement in one sentence. Cite the join conditions, grouping, and output columns that support it. If the facts do not establish the grain, use Needs analyst confirmation.]

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

One block per rule. Order the rules by how much each can change an answer.

### [Output column] (from [CTE or main query])

- **Sets:** [THEN value] when [conditions]; otherwise [ELSE value or none].
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
| [left side] to [target] | [INNER/LEFT/CROSS] | [ON condition] | [drops rows / duplicates rows] |

**One-row lookups** (LEFT joins that add at most one row per output row)

- [Left side] to [target] on [condition].

## 5. Source-table lineage

| CTE or query | Source tables | Feeds into | Notes |
| --- | --- | --- | --- |
| [CTE name] | [source tables it reads] | [downstream CTE or main query] | [brief structural note from comments or logic] |

**Lineage paths** (one bullet per output column group)

- [Source tables] -> [CTE] -> [main query] -> [output column group]
```

## Writing rules

- Preserve source capitalization for tables, aliases, columns, CTE names, and query names.
- Quote SQL fragments exactly when they appear in the profile. Do not reformat SQL in a way that changes meaning.
- Every claim in the profile must be traceable to a cited fact path, at section level when rows share a path. Every interpretation that the facts do not establish must say `Needs analyst confirmation.`
- Prefer bullets over wide tables when a cell would hold a full sentence or more.
- Do not include institutional email addresses or catalog paths in the profile unless the user confirms they are appropriate.
