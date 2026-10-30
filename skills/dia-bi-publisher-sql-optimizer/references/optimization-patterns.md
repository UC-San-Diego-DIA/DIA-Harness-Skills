# SQL optimization patterns for export-driven rewrites

These patterns apply only when the plan and SQL text both support them, and only when they cannot change the output contract. Each pattern lists its evidence signature in an execution plan and its contract risk.

## Zero-risk cleanups

**Inert CTE ordering.** Evidence: an `ORDER BY` inside a CTE that is consumed only through a join or aggregate. The optimizer discards it, but removing it removes ambiguity and any temptation for a sort. Apply freely.

**Dead existence joins.** Evidence: a table joined on keys with no filter, no selected column, and no effect on row multiplication beyond an inner-join existence check. Removing it preserves results under referential integrity; keep it applied only with a verification step confirming no orphan rows exist, and drop the rewrite if the user cannot confirm integrity.

**Redundant DISTINCT columns.** Evidence: a `DISTINCT` view selecting columns already functionally determined by its join keys or aggregation keys. Narrowing the DISTINCT to needed columns reduces hash-unique temp usage without changing values. Verify the removed columns truly were redundant in every row.

## Low-risk rewrites

**Filter pushdown through aggregates.** Evidence: an outer-joined aggregate view whose inner `WHERE` already matches the driving filter, but whose join key could also carry the driving table's date window. Moving window filters into the CTE reduces build size. Apply only when the driving filter provably subsumes the CTE filter.

**Aggregate-before-join reordering.** Evidence: a large join fanning out before a `GROUP BY` that aggregates on the smaller dimension's key. Pre-aggregating the many side reduces hash-join build size. Verify the aggregation key set is unchanged.

**Analytic-free deduplication.** Evidence: `ROW_NUMBER() ... = 1` used purely to pick one row per key where the ordering column is stable and unique per key after other filters. A pre-filtered or aggregate-based equivalent may avoid a full window sort. Verify the tie-breaking behavior is semantically identical; if any tie could resolve differently, do not apply.

## High-risk ideas (document, do not apply)

**Join restructuring of fan-out guards.** Rewriting `DISTINCT` guard CTEs, merging requisition-lookup chains, or replacing `LEFT JOIN` plus `WHERE row_num = 1` patterns can silently change which rows survive. These often hold the biggest wins on Fusion Procurement queries but require result-set diffing the user must perform; record them with explicit evidence and expected effect only.

**Parallelism hints.** `/*+ PARALLEL(n) */` can cut wall-clock time on wide scans but is environment-dependent on Fusion SaaS and may be disallowed. Never place it in the candidate file; document it as a question for the database team.

**Materialization hints.** `/*+ MATERIALIZE */` on reused CTEs trades temp space for repeated-scan cost. Only document when a CTE is consumed three or more times.

## Environment levers that do not exist in Fusion SaaS

Oracle Fusion Cloud environments do not allow index creation, schema changes, statistics tuning, or database-side configuration, and parallel execution hints are generally not permitted on Fusion SaaS either. When the user's environment is Fusion SaaS, these are not options to document; the SQL rewrite is the only lever. Designs that depend on a database team making a change are dead ends and must not appear in reports.

## Reading plan exports

- A SQL Monitor report carries actuals: real elapsed time, actual rows, and actual temp usage per plan line. When actuals are present, rank hotspots by actuals first and treat plan estimates as secondary. When actuals and estimates disagree materially, trust the actuals and say so in the report.
- Rank hotspots by `TempSpc` first, then cost, then estimated time. Wide final sorts and spilled hash joins dominate real-world Fusion reporting timeouts even when estimated times look safe.
- Estimated bytes per row (bytes / rows) reveals row width. A final sort of a very wide rowset is usually the single largest cost driver, and in Fusion SaaS it cannot be fixed by indexing or any database-side change; the levers are reducing row width and reducing rows reaching the sort.
- Predicate information shows where filters landed. A filter on the driving table's date window must appear on the driving table's scan, not only in a joined view.
- `TEMP TABLE TRANSFORMATION` indicates Oracle materialized a CTE; it is not itself a problem, but check whether the materialized table is scanned once or many times.
- A SQL Monitor report captured without actuals shows estimates only. Never present estimated times as measured; if the report lacks actuals because the query timed out before returning rows, the missing actuals are themselves the diagnostic, and the re-run after optimization must produce them.
