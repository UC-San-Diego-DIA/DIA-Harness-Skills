# Dataset Profile Report Template

Use this structure for `Dataset-Profile-YYYY-MM-DD-<Topic>.md`. Keep every
claim traceable to the profile JSON or the source schema. Where the data does
not establish something, write `Needs confirmation.` instead of guessing.

## Sections

```markdown
# Dataset Profile: <Topic>

- Source: `<path or file name>`
- Profiled: YYYY-MM-DD
- Rows: <count>
- Fields: <count>
- Grain: <plain-language reading of what one row represents, Needs confirmation if inferred>

## Summary

<Three to five sentences: what the dataset appears to hold, its apparent grain,
and the most important caveats from the profile.>

## Fields

| Field | Apparent type | Distinct | Null rate | Reading |
| --- | --- | ---: | ---: | --- |
| <name> | <duckdb type> | <count> | <percent> | <plain-language meaning, or Needs confirmation> |

## Distributions

<Numeric fields: min, max, mean, standard deviation, and quartiles in plain
language. Categorical fields: the most common values and their share. Date
fields: the covered range.>

## Missingness

<List fields with material null rates, in descending order, with the count of
affected rows and what a missing value may mean. Say plainly when the reason
cannot be known from the data.>

## Keys and Duplicates

- Candidate keys: <fields that are fully populated and unique>
- Duplicate rows: <count, and what that suggests about the grain>
- Notes: <near-key fields, composite-key possibilities, Needs confirmation flags>

## Anomalies and Outliers

<Report interquartile-range outliers and other data-evident irregularities.
Describe what the data shows, not what it should show. Include example values
when they help.>

## Suggested Metrics and KPIs

| Candidate metric | Fields involved | Formula sketch | Status |
| --- | --- | --- | --- |
| <metric> | <fields> | <plain-language formula> | Candidate; needs confirmation |

<Candidates come from field names and data shapes only. Mark each one as
needing confirmation and note what business definition is missing.>

## Open Questions

<Numbered list of questions for the data owner or the user, including
unresolved grain, units, filters, and business definitions.>
```

## Rules

- Never state a currency, unit, or business definition the data does not
  establish.
- Keep the report descriptive: this is a profile, not a recommendation to
  change the dataset or a confirmed KPI mapping.
- Reference the helper's numbers exactly; do not round beyond readability.
- If a section has nothing to report, say so plainly instead of dropping it.
