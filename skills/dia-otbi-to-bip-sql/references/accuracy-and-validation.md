# Native SQL review

Use an evidence ledger that distinguishes direct catalog facts, candidate mappings, documented database relationships, and unresolved semantic choices.

For a filtered cost report, verify these dependencies before claiming equivalence:

| Dependency | Evidence needed |
| --- | --- |
| Amount | Exact logical-measure expression, selected currency, and selected item/distribution logical table source |
| Distribution population | PVO or generated physical SQL predicates, including line types and adjustment treatment |
| Time | Date role, calendar identity, fiscal-period name, and adjustment-period treatment |
| Dimension | Foreign key, language, effective date, and cross-subject conformance |
| Access | Secured object or actual row-level predicates for the reporting identity |
| Presentation | Criteria columns versus stale layout references, totals, and formatting |

Ask for the analysis Advanced-tab logical SQL, BI Server physical query/log if available, OTBI currency preference, relevant secured-view definitions, or a baseline export only for unresolved dependencies that matter. Describe exactly which uncertainty each item resolves. Do not request passwords, tokens, or unrestricted database access.

Compare the native dataset against the original report using the same reporting identity, currency preference, period, and filters. Reconcile every organization and both individual measures before checking grand totals. Totals alone can hide offsetting errors.

Include cases with costs on camp and non-camp projects, the specified task and other tasks, projects in and outside subtraction lists, null costs, negative adjustments, and organizations with no contributing measure rows. Compare distinct fact keys before and after joins. Inspect all actual line types and multiple calendars before choosing predicates. If totals differ, compare transaction keys and amounts rather than adding filters until totals happen to match.
