# Conversion contract

## Inputs

One run accepts exactly one OTBI `.catalog` export and one selected analysis. If the catalog contains more than one `saw:report`, the helper reports the available analyses and requires `--analysis-index` or `--analysis-name`.

One run also accepts exactly one official Oracle subject-area-to-database mapping workbook. The workbook must contain an `OTBI Subject Areas` sheet with these columns:

- `SUBJECT_AREA`
- `PRESENTATION_TABLE`
- `PRESENTATION_COLUMN`
- `PHYSICAL_TABLE`
- `PHYSICAL_COLUMN`
- `VO_DEFINITION`
- `DATABASE_OBJECT`
- `DATABASE_COLUMN`

The helper requires every selected presentation column to have a nonempty `DATABASE_OBJECT` and `DATABASE_COLUMN`. Subject-area coverage alone is not enough. If the workbook omits the subject area or any selected column, the conversion stops.

## Output paths

Use a new output directory for each conversion. With the base name `Agent_Invoice_Report`, the helper writes:

```text
Agent_Invoice_Report-manifest.json
Agent_Invoice_Report-logical-literal.sql
Agent_Invoice_Report-logical-parameters.sql
Agent_Invoice_Report-physical-literal.sql
Agent_Invoice_Report-physical-parameters.sql
Agent_Invoice_Report-README.md
Agent_Invoice_Report-join-research.md
Agent_Invoice_Report-parameters/
```

The parameter directory contains one standalone list-of-values SQL file for each detected parameter. The helper does not overwrite existing files unless `--overwrite` is supplied after the user explicitly confirms that exact write.

## SQL construction

The logical SQL is a faithful projection of the OTBI analysis against the named subject area. It preserves selected presentation expressions, output headings, explicit filters, saved-filter references, and recorded sort order.

The physical SQL substitutes each mapped presentation reference with the workbook's `DATABASE_OBJECT` and `DATABASE_COLUMN`, preserves the original column aliases and ordering, and places the substituted filter in the physical statement. The `FROM` table list is derived after column, filter, and sort substitutions, so every referenced object appears in `FROM`. If the mapped columns span more than one database object, the SQL lists the objects in `FROM` and marks join conditions as `VERIFY` work. The mapping workbook does not provide joins.

The helper also writes a join-research worksheet that lists every physical table, its mapped columns and workbook rows, and every join candidate, and it records the workbook release token in the manifest. Real-time research against official Oracle documentation resolves the current release, verifies the tables and columns, and validates each join. Only `VERIFIED` joins, supported by explicit official-source evidence recorded in the worksheet, may replace a `VERIFY` marker in both physical SQL files. `CANDIDATE` and `UNRESOLVED` joins keep the `VERIFY` marker. See [join-research.md](join-research.md).

Literal SQL preserves the values found in the OTBI analysis. Parameterized SQL is a separate file so the exact literal behavior is not silently replaced.

## Parameters and list of values

For a single-value parameter, the helper uses a bind variable such as `:P_PARAMETER_NAME`. For a multi-select parameter, it uses the documented BI Publisher lexical-reference pattern `IN (&PARAMETER_NAME)`.

The helper records the source expression, operator, original value, inferred type, multi-select status, database mapping, and mapping alternatives in the manifest. It creates a list-of-values query from the selected mapping as:

```sql
SELECT DISTINCT
    DATABASE_OBJECT.DATABASE_COLUMN AS PARAMETER_VALUE
FROM DATABASE_OBJECT
ORDER BY PARAMETER_VALUE;
```

If a column has more than one mapping candidate, the helper records all candidates and marks the semantic choice as `VERIFY`. Do not resolve a code-versus-meaning ambiguity by silently choosing one candidate.

## Review

Before reporting success:

1. Re-read the manifest and all generated SQL.
2. Confirm that every physical object and column came from the supplied mapping workbook.
3. Confirm that output headings, column order, filters, sort order, and parameter placement match the manifest.
4. Confirm that every unresolved mapping or join is visible as a `VERIFY` item.
5. Confirm the join-research worksheet records the current Oracle documentation release, the sources used, and a verification status for every join candidate.
6. Tell the user that the skill did not execute SQL, connect to Oracle, or modify BI Publisher.
