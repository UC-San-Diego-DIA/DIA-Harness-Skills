# Required 200-row smoke test and estimated-plan delta

Use this reference for intake, the candidate handoff and delta mode. Staff perform one editor preview for the original and one for the candidate, both with **200** selected. The SQL Monitor export is the only required file for each version. Do not request scheduled reports, full runs, repeated benchmarks, full-result comparisons, stopwatch measurements or engine logs.

## Required evidence

For the original at intake and the candidate at delta review, require:

1. The SQL Monitor export from **Generate SQL Monitor Report**, such as `sql_monitor.txt`, containing the complete selected SQL and an interpretable plan. The file can have another name and can contain an estimated explain plan with imperfect XML/CDATA wrappers. Require the content, not an exact filename or well-formed XML.
2. Confirmation that the analyst selected **Data > Rows: 200**, clicked **View**, and the preview completed. Record its status, known returned row count, parameters and any visible errors or anomalies. A query returning fewer than 200 rows still qualifies when the selector was 200. Do not demand artificial rows or change the query to make it return exactly 200.

Reuse evidence already provided. The plan's estimated `Rows` value does not establish the editor setting or the returned sample size. If the setting is absent, ask only for confirmation. If a smaller setting was used, ask for a preview with 200 selected. If the export is missing, request it. Pause candidate generation or completion of a successful delta review until the required evidence is present. A failed or timed-out preview must be recorded as failed, never passed; explain the blocker without repeatedly requesting the same failed run or escalating to a full run.

User confirmation is sufficient when the export does not record the preview setting and status. Label it user-reported evidence. Do not require a screenshot, sample-data export, timing record or second diagnostic file. If the user voluntarily supplies local preview data, it can support the smoke check, but it is not a new prerequisite.

## Staff workflow

### Original SQL

1. Keep the original SQL and its current data-model settings.
2. In the data model editor's **Data** tab, select **200**, use the intended parameter values and click **View** once.
3. Check for successful completion, expected column names and order, and obvious missing values, unexpected duplicates, missing records or other visible anomalies. Report what was actually checked rather than asserting full-result equality.
4. Export **Generate SQL Monitor Report** and supply that file with confirmation of the 200 setting and preview outcome. Retain the parameters locally for the candidate test. Sensitive values do not need to be pasted into chat.

### Candidate SQL

1. Test the complete candidate in the analyst's permitted test copy/version. Preserve the data structure, parameter definitions and security context.
2. Use the same parameters, user/role and settings as the recorded baseline, select **200** and click **View** once. Do not rerun the original merely to start delta mode; use its recorded evidence.
3. Check successful completion, column names/order and visible anomalies. Compare available preview values and duplicate behavior where the samples overlap. Do not require identical first-200 row sets when final sort keys tie. If values differ for matching records, investigate without silently changing business logic.
4. Export the candidate's SQL Monitor report and return it with the preview outcome for delta mode.

Use the editor selector, not SQL changes, to limit the sample. Do not add `ROWNUM`, `FETCH FIRST`, a `COUNT(*)` wrapper or test-only business filters. Do not shrink the date range or change other parameters just to speed up this workflow. A failed preview is a reported failure, not permission to bypass the required setting.

## Correctness findings

Keep the static equivalence review in the skill and optimization-patterns reference as the first safeguard. A successful preview does not make an assumption-dependent rewrite safe. Preserve values, nulls, types where known, duplicate multiplicity, row grain, parameters, security logic and ordering when preparing the candidate.

Report static review and smoke testing separately. Use smoke-test findings such as `passed, user-reported`, `passed, supplied preview checked`, `failed`, or `pending required evidence`. State what the analyst checked. A reported value or schema mismatch is a correctness concern regardless of the estimated plan direction; flag it and withhold a positive candidate recommendation.

Reaching the 200-row cap leaves the rest of the result unexamined. Different tied rows or changing source data can affect previews. Do not dismiss a mismatch as data drift without evidence, and do not claim full-result equality from sample checks. State the limit briefly without turning full-result verification into a staff task or an unfinished requirement for this skill.

## Estimated-plan comparison

The delta report's required performance comparison is the before/after estimated plan. It must not depend on measured timings or complete result sets.

- Confirm that both exports belong to the selected model/dataset, baseline and candidate. Compare the SQL against the recorded candidate. Match parameters and environment where known; keep unknowns explicit without demanding a benchmarking record.
- Compare plan hash, root estimated cost, estimated output rows and bytes, estimated `Time`, estimated TempSpc for corresponding work areas, access paths, predicates, joins, sorts and repeated work. Match operations by meaning, not line number. If an operation disappears, record that rather than inventing a zero-valued measurement.
- Label every numeric plan field as estimated. Root cost and parent/child costs describe overlapping work; do not sum them. Do not sum per-operation times or temp demands into supposed runtime or peak usage. A lower cost or changed plan hash is not a measured speedup. A large estimated row-count change may warrant a semantic recheck rather than praise for reduced work.
- Show baseline and candidate values, their estimated differences and the proposed reason for each material change. If a percentage is useful, label it by its metric, such as "estimated root cost decreased by 12%." Use `100 * (baseline - candidate) / baseline` only for comparable positive baseline values; omit percentages for zero, missing or incomparable values. Never describe these as runtime savings or infer actual timeout headroom from estimated `Time`.
- If the exports contain actual execution statistics, identify them separately with their recorded scope. They do not replace the required estimated-plan comparison or prove full-run performance. No additional actuals are requested.
- If SQL identity, parameters, database version or other material conditions differ, explain the affected comparison as `not comparable`. Retain both observations without attributing the difference to the rewrite. Do not ask staff to run a full report to resolve the limitation.

## Delta conclusion and completion

Write three distinct conclusions in each delta report:

1. Static correctness review, including unresolved assumptions and any mismatch.
2. The original and candidate 200-row smoke-test outcomes and their evidence sources.
3. Estimated plan direction: `lower estimated work`, `higher estimated work`, `mixed`, `unchanged`, or `not comparable`, with the specific supporting estimates.

With explain-plan-only inputs, state **Runtime improvement not measured**. Full-result equality remains unverified. These are limits of this lightweight review, not reasons to require full runs or repeated tests. Once the required exports and completed 200-row smoke tests are present and the report records its findings, delta mode is complete. Recommend analyst review of the candidate when supported, or retaining the original when correctness concerns remain; never certify production readiness from the plan or preview.

## Primary references

- [Publisher sample-data testing](https://docs.oracle.com/en/cloud/saas/otbi/otbi-pub-design/test-data-models-generate-sample-data.html) documents the editor's row selector, preview and sample export.
- [Publisher SQL tuning](https://docs.oracle.com/en/cloud/saas/otbi/otbi-pub-design/tune-sql-query.html) distinguishes explain-plan estimates from execution diagnostics.
