# Validate the conversion with the analyst

File generation, Oracle execution, and result equivalence are different milestones. Deliver a complete candidate before requesting execution or comparison results. Update its existing manifest/evidence record with returned results and keep any existing status summaries consistent. A separate validation document is optional. This skill does not connect to Oracle; the analyst runs BI Publisher and supplies evidence.

## Before execution

Record source catalog, workbook and SQL hashes, selected analysis/view, workbook and documentation releases/URLs, construction decisions, effective runtime values, and the candidate's scope. Record known tenant release and access context without credentials. Ask for missing context before construction only when it materially affects SQL; otherwise carry it as an unverified comparison condition. Complete the comparison context when exports are available, including applicable language, timezone, currency, business-unit/ledger scope, access context, data window and run times. Use a stable closed period or bounded slice when data can change between runs.

Review physical field identity, join keys/types, input and result grain, filters, calculations, row policy, and scope. Check Oracle datatype/date handling and valid output names. Exact column order, alias spelling, and ordinary sorting are secondary unless a requested layout/interface depends on them. Ordering that controls top-N, limits, windows, or calculations remains essential. No OTBI-only functions, unresolved variables, missing keys, Cartesian joins, no-row guards, semantic placeholders, or silently omitted criteria may remain in a candidate. A source logical measure needs review even in a single-table conversion.

Set CANDIDATE_NOT_EXECUTED only when that review is complete. Keep Oracle execution and reconciliation as not_run. Record concrete unresolved issues under BLOCKED rather than inviting the user to test an incomplete query.

## First BI Publisher run

Give a new user these steps:

1. In BI Publisher, create or open a data model in their normal test location. Add a SQL Query data set and choose Standard SQL and the tenant's Fusion database source. Ask their reporting administrator if the appropriate source is unavailable. Do not choose Oracle BI Server for the physical SQL file.
2. Paste the reviewed physical literal SQL without a trailing semicolon. Use the editor's SQL validation and a small data preview first. Preview acceptance establishes neither full execution nor parity.
3. After SQL executes, request complete exports for the declared comparison goal and same bounded scope. For physical-row construction, a supplied BIP reference can verify row multiplicities; OTBI supports field/value comparison but may collapse separate fact records. For exact OTBI output, use matching complete OTBI/BIP exports. Reuse exports already supplied when their scope and runtime values match. A preview row cap cannot support a complete count comparison. Record truncation. For a large report, agree on a complete slice and apply it to both sources.
4. If an Oracle error occurs, provide its exact code/message, the tested SQL file/hash, and parameter values without credentials. Repair the candidate from that evidence, then rerun the same comparison scope. Do not remove a required filter or join just to make the error disappear.
5. When parameters and LOVs are requested, configure them from the manifest and parameter reference after literal results match. Initialize them to the original effective values and rerun the comparison. Test multiple selections, null/All where enabled, boundary dates, and empty results.

Record successful database execution as EXECUTED_NOT_RECONCILED until the comparison below passes.

## Compare the exported data

State the goal and row policy before interpreting counts. Compare the full agreed scope, not just aggregate totals or the first 200 rows:

- Align corresponding physical fields by the recorded mapping, allowing different positions and aliases. Compare compatible raw values separately from display formatting. Exact names/order are required only for a requested dependent interface/layout.
- For `physical_rows`, compare row counts and duplicate multiplicities against a physical reference or independent fact-key evidence. Different fact keys with identical projected values are legitimate repeated rows. Investigate unwanted multiplication of the same fact key. Do not deduplicate either side merely to obtain equal counts.
- For an OTBI comparison in `physical_rows` mode, align distinct displayed tuples for field/value comparison and separately explain physical multiplicities with underlying keys. Matching sets alone cannot establish correct physical row counts. Do not fail physical construction just because OTBI removes legitimate repeated projections, or claim full OTBI output parity.
- For `otbi_distinct` or aggregate-result comparison, require matching result-row counts and multiplicities for the declared output grain. Compare as multisets when order is irrelevant; set subtraction alone loses duplicate counts.
- Compare underlying keys and duplicate-key counts when available. Use a separate diagnostic when required keys are not projected; do not silently change requested output columns. Investigate missing and extra keys in both directions.
- Every measure by result key and agreed business grouping, plus totals, null counts, and min/max dates. Equal grand totals can conceal offsetting row errors.
- Exact text/code matches, including leading zeros, spaces, and lookup language. Record Oracle empty-string/null handling and distinguish missing data from zero.
- Numeric agreement at the required scale. Default to exact decimal comparison. Any tolerance must be explicitly agreed and recorded before treating differences as acceptable. Check currency and rounding stage before choosing a tolerance.
- Sort parity when requested, with explicit null ordering and ties considered. Do not invent a stable order for ties absent from the source.

Use local comparison scripts when exports are provided; do not execute SQL against Oracle. Do not store real exports or business literals in the skill repository. Report mismatch counts and a bounded set of examples, then isolate mappings, aggregation, join multiplication, filters, access, and source-time drift in that order as the evidence warrants.

Set RECONCILED only after all agreed checks pass on complete evidence for the declared goal and scope. Record goal, row policy, input and SQL hashes, export row counts, mismatch counts, explained multiplicity differences, approved tolerances, runtime context, and analyst confirmation. Physical-row reconciliation does not establish identical OTBI duplicate counts. If only one slice was tested, say so. Future prompt combinations and changing source data remain outside that observed result.

## Handoff

Lead with the exact physical SQL path to paste, status, material scope limits, and the next test. Link the existing evidence record for provenance; include parameter and LOV setup only when requested. State whether Oracle execution was analyst-reported or whether supplied exports were locally compared. Never describe unexecuted SQL as working, or syntax acceptance as matching output. Repair the same candidate from the exact error or mismatched results; reopen only decisions the new evidence challenges. The analyst owns deployment and production access configuration.
