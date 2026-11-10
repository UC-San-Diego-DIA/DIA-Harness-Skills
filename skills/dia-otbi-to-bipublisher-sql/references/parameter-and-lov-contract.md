# BI Publisher parameters and list of values

## Parameter forms

Use a bind variable for one selected value:

```sql
WHERE table.column = :P_PARAMETER_NAME
```

Use the documented BI Publisher lexical-reference pattern for a multi-select parameter:

```sql
WHERE table.column IN (&P_PARAMETER_NAME)
```

Keep `IN` and `NOT IN` exactly as the OTBI filter requires. Do not change an inclusive filter to an exclusive filter when parameterizing it.

## BI Publisher setup

For each parameter:

1. Create the parameter with the exact name recorded in the manifest.
2. Set the data type to the recorded type: date, number, or text.
3. Select the corresponding SQL Query list-of-values data set when one was generated.
4. Enable multi-select only when the manifest records `multi_select: true`.
5. Use the parameterized SQL file for the main data set and the standalone parameter SQL file for its list of values.

The generated list-of-values SQL has a `PARAMETER_VALUE` column. It intentionally contains no hard-coded business filter because the mapping workbook is the authority for the mapped database field. Add report-scoped security or row filtering only with an explicit analyst decision.

## Ambiguity

A presentation column can map to more than one database field. Common causes are lookup meanings, source codes, translated labels, and denormalized fields. When the manifest records multiple candidates:

- Keep the selected mapping visible in the generated SQL.
- Keep the alternatives visible in the README.
- Mark the choice as `VERIFY`.
- Ask the analyst to confirm the intended value rather than choosing by name similarity.
