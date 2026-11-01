# Dataset profile report template

Use this structure for `Dataset-Profile-YYYY-MM-DD-<Topic>.md`. Trace numbers
to the helper JSON and distinguish inferred meanings from source facts or
attributed user definitions. Replace placeholders before saving.

```markdown
# Dataset Profile: <Topic>

## What the dataset contains

<Two or three sentences describing what the file appears to contain, what
one row appears to represent, and its most important limitation. Mark
inferred grain as Needs confirmation.>

- Source: <filename>
- Sheet: <selected sheet; omit for CSV>
- Profiled: <generated_at>
- Source SHA-256: <source_sha256>
- Rows: <count>
- Fields: <count>
- Date coverage: <range for each relevant temporal field, or Not established>
- Parsing: <settings from the helper, including overrides and auto-detection>
- Runtime: <Python and DuckDB versions>

## How to read the fields

| Field | Inferred type | Distinct, excluding nulls | Null count | Null rate | Reading |
| --- | --- | ---: | ---: | ---: | --- |
| <exact name> | <type> | <count> | <count> | <percent, or undefined for no rows> | <supported meaning with attribution, or tentative reading marked Needs confirmation> |

## How records are organized

- Candidate single-column identifiers: <populated and unique fields, or None found>
- Extra identical rows beyond the first: <duplicate_row_count>

<Explain material implications without asserting a business key or grain.
Uniqueness applies only to this file. Duplicates are based on parsed values
across all columns and are not necessarily errors.>

## Distributions and things to watch

<Compact numeric table with min, Q1, median, Q3, max, mean and standard
deviation. Explain quartiles briefly if needed. Omit date ranges already
shown above. For selected categorical fields, show common values and counts;
if using shares, state whether the denominator is all or non-null rows.
Avoid listing identifying values or free text when they add no useful context.>

<Call out important missingness, statistically unusual values with IQR counts,
parsing limitations and unavailable statistics. Reference the field inventory
instead of repeating every null count. Never treat outliers as proven errors.
Say plainly if there are no additional findings.>

## Possible uses

<Optional: a few exploration possibilities tied to exact fields. Reference
the prerequisite questions below. No KPI formulas, targets, recommendations
or calculated business answers. Omit this section when no useful possibility
is supported.>

## Questions for the data owner

<One numbered list of unresolved grain, definitions, units, codes, population
coverage and prerequisites. Keep each question here once. If none remain,
say None recorded.>
```

Keep the summary short, the field inventory complete and the other tables
compact. Do not repeat tables in prose. Round only for readability, retaining
the helper's meaning. Do not infer currency, units or reasons for missingness.
This report is a first look at one file, not a confirmed business dictionary
or evidence that the file is fit for a particular decision.
