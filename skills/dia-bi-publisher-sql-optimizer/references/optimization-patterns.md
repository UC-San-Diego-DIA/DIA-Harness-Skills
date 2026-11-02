# SQL rewrites with preservation conditions

These are investigation patterns, not blanket permissions. Apply a change only when its preservation conditions are established from SQL semantics and supplied evidence. Diagnostics estimate work; they do not prove uniqueness, foreign keys, values, or business meaning. If a condition is unknown, document the idea and leave it out of the candidate.

## Ordering and row selection

An internal `ORDER BY` can determine rows selected by `ROWNUM`, `FETCH FIRST`, `OFFSET`, or another order-dependent consumer. Trace all consumers before considering removal. Preserve final ordering, including direction, null placement and expressions. Do not add a tie-breaker or replace `ROW_NUMBER` with `MIN`/`MAX` to "fix" nondeterminism. Existing ties are a correctness uncertainty to disclose; an aggregate can choose values from different source rows.

## Join removal and duplicate guards

For an unused inner join, prove both that every retained left row has a match under the full join/filter/security conditions and that it has exactly one match. For an unused left join, prove at most one match and that no downstream expression/filter depends on it. No orphan rows alone does not prove unchanged multiplicity. Never infer constraints from names, indexes listed in a plan, or a sample.

Removing columns before `DISTINCT` can collapse rows that later produce duplicate outputs. Prove the remaining columns determine the removed values, preserve all consumers and duplicate multiplicities, and account for nulls. An outer projection selecting fewer columns is insufficient evidence.

## Restricting intermediate work

Filter pushdown or restricting an intermediate source to relevant driving keys can reduce work. Prove no needed match, unmatched outer-join row, aggregate input, analytic partition, or top-N candidate is lost. Prefer an existence restriction over a multiplying join when appropriate, but still prove equivalence. Moving a predicate between `WHERE` and `ON` across an outer join can change results.

Drop unused intermediate columns only when no consumer, deduplication, grouping, ordering, set operator or wildcard relies on them. Keep final outputs intact. Do not narrow types, truncate text, shorten output aliases, or remove output columns to make a sort smaller.

## Aggregates and repeated work

Pre-aggregation requires preserving all grouping/join keys, fan-out, aggregate inputs, null handling and each aggregate's meaning. Keeping the same grouping keys alone does not establish equivalence. `AVG`, distinct aggregates and outer joins require particular care.

Repeated scalar subqueries or PL/SQL calls may explain repeated work, but replacing them with joins requires evidence about cardinality, no-match behavior, errors on multiple rows, and session-dependent function semantics. Do not replace security functions or secured views with base tables. Factor expressions only if evaluation timing, errors and nondeterministic values remain equivalent.

## Parameters and dates

Inspect function-wrapped predicates and implicit conversions when supported by plan evidence. Date-range rewrites must preserve inclusive/exclusive bounds, time components, nulls, time zones and actual bind types. Preserve single-value, multivalue and all/null parameter semantics and lexical substitutions. Do not replace binds with literals or remove effective-date, language, enterprise or security filters. Missing parameter metadata is an open question, not permission to guess.

## Hints and environment limits

Do not add parallelism or undocumented materialization hints to the candidate or make Fusion SaaS recommendations depend on a database team changing indexes, statistics or configuration. CTE reuse count alone does not justify materialization. Preserve existing hints unless a separately justified change establishes their purpose and supported use. User-side testing in Publisher remains necessary.

## Reading plans

- `EXPLAIN PLAN ... FOR` and `PLAN_TABLE_OUTPUT` with `Rows`, `Bytes`, `TempSpc`, `Cost`, and `Time` describe estimates. A file named `sql_monitor.txt` can contain only this evidence. Estimated bytes/rows indicate estimated row width, not measured XML size; estimated TempSpc indicates possible work-area demand, not a measured spill.
- Consider access paths, predicates, cardinalities and repeated operations together. A full scan or `TEMP TABLE TRANSFORMATION` is not automatically a problem. Never sum hierarchical costs or elapsed values; parent and child work can overlap or include the same work. Parallel activity is not directly additive wall-clock time.
- When actuals exist, record units, starts, rows, waits, execution identity and fetch/completion status as provided. Account for repeated starts when comparing estimated and actual rows. Unavailable metrics stay unavailable. A failed, partial or first-N-row execution may still have actuals.
- Plan predicates can include injected security conditions. Use them as evidence; do not copy them into submitted SQL or remove source security logic. Adaptive-plan notes require care about which operations actually ran.

## Primary references

- [Publisher SQL tuning](https://docs.oracle.com/en/cloud/saas/otbi/otbi-pub-design/tune-sql-query.html) distinguishes explain plans from execution diagnostics. Its general tuning suggestions still require the preservation and SaaS boundaries above.
- [Oracle ROWNUM semantics](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html) explains how inner ordering affects top-N selection.
- [SQL Monitor identity and status](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_MONITOR.html) distinguishes complete fetching, partial fetching, errors and running executions.
