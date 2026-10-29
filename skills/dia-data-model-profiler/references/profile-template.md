# Profile template

Use this structure for the single `data-model-profile.md` output. Replace bracketed placeholders with facts or with `Needs analyst confirmation.` Never leave a template placeholder in the written document.

```markdown
# Data model profile: [model.name]

Derived only from [extraction.source_file]. Extracted [extraction.extracted_at]. Container: [extraction.container].

## 1. Grain and row-level meaning

[Proposed grain statement. Cite the join conditions, grouping, and output columns that support it. If the facts do not establish the grain, use Needs analyst confirmation.]

## 2. Filters, exclusions, and windows

| Filter | Excludes | Effect on interpretation | Evidence |
| --- | --- | --- | --- |
| [condition] | [what rows are removed] | [what questions it prevents or narrows] | [fact path] |

**Time window**: [date range or relative window from the filters, or None declared.]

**Window functions**: [each detected window function and its role, or None detected.]

## 3. Hard-coded business logic

| Location | Output column | WHEN conditions | THEN values | ELSE | Why it matters | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| [CTE or main query name] | [output column it feeds] | [conditions] | [values returned] | [else value or none] | [why an analyst should know] | [fact path] |

## 4. Deduplication and join patterns

### Deduplication

| Pattern | Where | Effect | Evidence |
| --- | --- | --- | --- |
| [DISTINCT / GROUP BY / ROW_NUMBER] | [CTE or main query name] | [what it deduplicates or collapses] | [fact path] |

### Joins

| Join | Type | Target table | Condition | Row-count risk | Evidence |
| --- | --- | --- | --- | --- | --- |
| [order] | [INNER/LEFT/CROSS] | [table] | [ON condition] | [drops rows / duplicates rows / one-to-one] | [fact path] |

## 5. Source-table lineage

| CTE or query | Source tables | Feeds into | Notes |
| --- | --- | --- | --- |
| [CTE name] | [source tables it reads] | [downstream CTE or main query] | [brief structural note from comments or logic] |

**Full lineage path**: [source table] -> [CTE] -> [CTE] -> [main query] -> [output column group]
```

## Writing rules

- Preserve source capitalization for tables, aliases, columns, CTE names, and query names.
- Quote SQL fragments exactly when they appear in the profile. Do not reformat SQL in a way that changes meaning.
- Every claim in the profile must cite a fact path. Every interpretation that the facts do not establish must say `Needs analyst confirmation.`
- Do not include institutional email addresses or catalog paths in the profile unless the user confirms they are appropriate.
