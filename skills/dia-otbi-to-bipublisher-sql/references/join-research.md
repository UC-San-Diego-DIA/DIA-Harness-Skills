# Real-time join research protocol

## Purpose

The mapping workbook is the only authority for field mappings, and it does not
supply join conditions. After the helper writes a
`<base-name>-join-research.md` worksheet, complete it with real-time research
against official Oracle sources during the same run. The worksheet is the
durable record; chat reports the same findings for the user.

Real-time research is allowed only for:

1. Resolving the current Oracle documentation release.
2. Verifying that mapped tables and columns still exist in that release.
3. Validating join conditions between the tables the physical SQL references.

Never use research results to add, replace, or re-map a field mapping.

## Release resolution

1. Open `https://docs.oracle.com/en/cloud/saas/` and select the product family
   library that matches the subject area's module, such as Financials, Supply
   Chain Management, or Project Portfolio Management.
2. Record the release the library shows, in its URL, page title, or What's New
   page, for example `26B` or `26C`.
3. Record the library URL, the release token, and the access date in the
   worksheet header.
4. Resolve the release fresh in every run. Never reuse a release recorded in an
   earlier run and never hardcode a release value.
5. If the live release is newer than the workbook release token, keep the
   workbook as the mapping authority but source join evidence from the live
   release, and note any mapped table or column that changed or disappeared.

## Table and column verification

For every table in the worksheet, use current-release official Oracle
documentation to confirm the table exists and that the mapped columns are still
documented. OTBI subject-area documentation for the same release is the best
cross-check because it names the entities behind each attribute.

- Record the documentation URL, page title, release, and access date.
- If a table or column cannot be found in the live release, record that in the
  worksheet notes, keep the workbook mapping in the SQL, and surface the
  discrepancy to the user before reporting the SQL as ready. Do not substitute a
  different column from research.

## Join evidence hierarchy

Research every join candidate block in the worksheet. Accept evidence only from
official Oracle sources, strongest first:

1. A join condition stated explicitly in current-release official Oracle
   documentation, such as subject-area or entity documentation.
2. A relationship shown by the workbook's own `VO_DEFINITION` value, recorded
   with its workbook row number as the source.
3. A documented primary-key or foreign-key relationship for the exact pair of
   tables in current-release official documentation.

Never accept a join inferred only from similar column names, third-party blogs,
AI-generated summaries, forum posts without an Oracle source, or by executing
SQL against any database. This skill never connects to a database.

## Recording requirements

For every researched table and join, complete the worksheet fields:

- Source URL
- Page title
- Documentation release
- Access date
- Evidence quote or a precise description of the evidence
- Verification status

Report every join status and its source URL to the user in chat as well as in
the worksheet. An unverified claim must never be reported as verified.

## Verification statuses

- `VERIFIED`: explicit official-source evidence supports the exact join
  condition. Replace the `VERIFY` join comment in both physical SQL files with
  the verified condition. Keep the two files otherwise identical, and keep the
  source recorded in the worksheet.
- `CANDIDATE`: strong indirect evidence, such as a workbook view-object
  association. Keep the `VERIFY` marker, show the candidate condition to the
  analyst, and apply it only after the analyst confirms it.
- `UNRESOLVED`: no official evidence was found. Keep the `VERIFY` marker and
  report the gap together with the sources attempted.
- `NOT_REQUIRED`: the query references a single database table.

When research is unavailable or inconclusive, leave every affected join as
`VERIFY`, record what was attempted in the worksheet, and report the remaining
lookups to the user. This is not a conversion failure; the conversion outputs
remain valid with the worksheet incomplete.
