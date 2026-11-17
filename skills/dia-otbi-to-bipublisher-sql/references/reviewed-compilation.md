# Compile a reviewed conversion

Use this path after resolving field mappings and the intended join graph. The agent selects the technical bindings from evidence and prepares the review plan; do not ask the user to author JSON or approve supported field/join choices. A matching supplied BI Publisher model can be useful evidence but is not required for SQL output. This path generates an executable candidate, rather than the inspection helper's no-row scaffold. When an evidenced conversion exceeds the grammar below, construct and review SQL directly under the conversion contract instead of forcing it into this compiler.

## Supported v1 scope

The compiler accepts one simple attribute analysis. Each selected expression must be a direct presentation-field reference. It preserves selected order, supported literal filters, headings through model labels, and supported explicit sorts as conveniences. It emits plain SELECT by default, retaining physical row multiplicities. Set `row_policy: otbi_distinct` only when the user requests distinct OTBI output. Output SQL aliases are recorded separately from displayed headings; names, column order, and ordinary sorting do not determine whether physical mappings and joins are correct.

The plan resolves ambiguity with an explicit workbook-supported field binding and an evidenced join graph. Aliases, join type, composite key pairs, and cardinality are recorded. Required projected references anchor the reviewed grain. The compiler checks these structural invariants; an evidence label is not independent proof that the business decision is correct.

Measures, aggregate/scalar output formulas, unresolved runtime variables, selection steps, combined criteria, parameters, advanced SQL clauses, and unreviewed security policies need additional semantic compilation. Do not label such analyses converted by forcing them through this v1 path. No conversion plan may embed a substitute SQL query or delete source criteria to fit this subset.

## Prepare the plan

Save a schema-version-1 JSON plan beside the deliverables, outside the skill repository for real user files. Include:

- `source_catalog_sha256`, `mapping_workbook_sha256`, and `template_model_sha256` when a template is used. Hashes prevent reuse against different files.
- `subject_area`, `grain`, `comparison_scope`, `reviewed_by`, and `reviewed_at`. State unresolved broader access policy separately from the reference-model comparison scope.
- `row_policy`, either `physical_rows` or `otbi_distinct` for schema 1. Omission defaults to `physical_rows`; set it explicitly in newly prepared plans. The effective choice is recorded in the manifest and CLI summary. Existing plans without the field now use plain SELECT; recheck their intended row contract before regenerating older candidates. Distinct mode requires a request for distinct output, not merely knowledge that OTBI normally deduplicates.
- `sources`, a dictionary of evidence IDs with `title`, `location`, and applicable release/access date or source hash. Record actual documentation releases. If current entity pages cannot be retrieved, distinguish the current library's release from older accessible entity evidence and the supplied reference's join evidence.
- `root_table`, with `object` and `alias`.
- `joins`, ordered so each introduces one alias connected to an existing alias. Each entry has `object`, `alias`, `kind` of INNER or LEFT, `keys` as exact pairs such as `["d.INVOICE_ID", "l.INVOICE_ID"]`, `cardinality`, and an `evidence` list of source IDs. Include every composite-key predicate.
- `field_mappings`, one per needed presentation reference, with `presentation_ref`, `table_alias`, `database_column`, `output_name`, `data_type`, `semantic_role` of attribute, and `evidence`. The database field must exist among that reference's workbook alternatives. Datatypes supported are string, date, decimal, integer, and dateTime. Output names must be unique Oracle/XML identifiers of at most 30 ASCII characters.
- `required_projected_refs`, a nonempty list of presentation references anchoring the reviewed grain. A plan for invoice distributions should require a selected distribution-level reference; it is not a plan for an arbitrary supplier summary.
- `data_source`, the actual SQL dataset source from the user's template or confirmed environment, required only for model packaging. SQL-only output does not require a template or this setting.

Record the unique keys supporting `grain` and the expected effect of each join in the plan's evidence. Required projected references are grain anchors, not a proof of uniqueness. The compiler checks mapping membership, connected joins, evidence references, and declared cardinalities; it cannot verify database constraints or that documented relationships actually preserve the claimed grain in the tenant.

The reference model can establish the intended physical branch and join choices. Compare physical expressions, join keys/types, filters, and calculations first. Align positions by the output mapping and report aliases and ordinary sorting as secondary differences. Compare duplicate multiplicities according to the declared row policy. Plain SELECT is the intended default even when OTBI collapses distinct fact records into the same projected tuple. Sorting by an unprojected mapped attribute is supported in physical-row mode; distinct mode requires a projected expression/alias. Investigate join multiplication without using DISTINCT to hide it.

## Schema 2: reviewed aggregate construction

Use `schema_version: 2` for a grouped result with reviewed SUM measures. All existing source/workbook hashes, evidence sources and review metadata still apply. This version shares the CLI and optional unparameterized model packaging. It uses `aggregate_expressions.py`, a typed parser, rather than textual function substitution.

Its effective `row_policy` is `aggregate_grain`, whether omitted or explicit. Other policies are rejected for schema 2. Required GROUP BY and measure semantics remain intact; changing the attribute default does not remove aggregation or add output DISTINCT to grouped queries.

Supported formulas contain direct attributes and SUM measures, FILTER with a row predicate, IFNULL/NVL/COALESCE/NULLIF, DESCRIPTOR_IDOF with separate key lineage, arithmetic, comparisons, IN/NOT IN, LIKE/NOT LIKE, AND/OR/NOT and IS NULL. Literal text stays unchanged, including apparent spelling or comma mistakes. Qualified references retain subject identity. Unknown functions/tokens, aggregate predicates inside FILTER, nested aggregates, and mixed row/aggregate expressions fail closed. No Cost definition is inferred from its heading or currency preference label.

Add these plan records:

- `root_table.evidence` and `fact_grain`, with root-alias `keys` and `evidence`. Measure `field_mappings` use `semantic_role: measure`, `aggregation: SUM`, numeric `data_type`, and reviewed `input_grain`, `currency` and `row_selection` descriptions. Each physical measure column must be on the root fact and match an official workbook alternative. Attribute bindings retain `semantic_role: attribute`. The aggregate expression path currently supports string and numeric field datatypes.
- Each join must be reviewed as `many-to-one` or `one-to-one` relative to the incoming fact branch. A multiplying join is rejected; calculate another fact branch separately. Join `restrictions` are optional typed predicates applied in ON, preserving LEFT semantics. Record their evidence.
- `physical_scope`, with `status: reviewed`, `evidence` and a `restrictions` list. Empty restrictions explicitly mean the review found no additional physical row predicates for the declared scope. Each restriction has `table_alias`, `database_column`, `operator`, `data_type`, `values` and `evidence`. Supported operators are comparisons, IN/NOT IN and IS NULL/IS NOT NULL. Values are literal strings validated for the declared string/integer/decimal/date type. These restrictions supplement, rather than replace, all source criteria.
- `runtime_values`, keyed by the exact saved variable name. Each record has `data_type`, nonempty `values` and `evidence` referencing the confirmed selection. For example, `{"p_period":{"data_type":"string","values":["P1","P2"],"evidence":["user_selection"]}}`. Multiple values are supported only at IN/NOT IN value positions. Unknown, missing or misspelled variables fail; saved defaults are never silently treated as actual selections. Resolution metadata records both defaults and effective values.
- `output_bindings`, one per original column ID, with `column_id` and unique `output_name`. Output expressions always come from the catalog. An optional changed `heading` requires separate `evidence`, such as the supplied rendered export. Retain `required_projected_refs` for the selected result dimensions.
- `table_view` selects one saved flat row table when needed. The compiler retains hidden expressions internally, emits only visible fields in table-view order, and requires every original column to be accounted for. Page/section/pivot structures are unsupported. With an after-row grand total and one text dimension, require `grand_total: {"method":"recompute_source_formulas","evidence":["total_stage_review"]}`. This explicitly approves computing the source expressions again at total grain through GROUPING SETS. It is not permission to sum displayed category columns. Other total contracts require additional construction.
- Optional `result_sort` records confirmed runtime sorts when the catalog has none. Each entry has `column_id`, `direction`, `nulls` of FIRST/LAST and `evidence`. Runtime sorts cannot silently replace saved sorts. Grand totals sort after detail rows.

Evidence IDs and review declarations are structural checks, not proof of tenant semantics. Do not fill these records with guesses just to obtain SQL. Repeated evidence labels cannot resolve an unknown cost branch, hidden predicate, descriptor key or calendar relationship. Diagnostics and confirmed exports can supply further evidence through the no-administrator investigation path. The original scaffold helper remains deliberately limited; schema-2 compilation does not promote its guarded output.

Run `python -B scripts/test_otbi_aggregate_conversion.py` from the repository root. The tests execute generated grouped SQL on synthetic SQLite data for detail semantics, including overlaps, repeated amounts, negatives, missing categories, nulls, runtime selections, and descriptor/display differences. GROUPING SETS output and total-stage review are checked locally but still require Oracle execution and comparison. No offline test establishes Fusion parity.

## Run the compiler

```powershell
python "<skill-folder>\scripts\compile_reviewed_conversion.py" "<absolute-OTBI-catalog>" `
  --mapping-workbook "<absolute-lineage-workbook>" `
  --review-plan "<absolute-review-plan.json>" `
  --template-model "<absolute-reference.xdm.catalog>" `
  --output-dir "<new-absolute-output-directory>" `
  --base-name "Converted_Analysis"
```

For a multi-analysis input add `--analysis-index` after selection. Omitting `--template-model` produces SQL and a manifest without model packaging. The compiler never overwrites existing outputs. Resolve a conflict by choosing a fresh output directory or following the skill's explicit replacement process; do not delete existing files as a retry shortcut.

The output contains `.sql`, `.xdm`, `.xdm.catalog` when requested, and a manifest. SQL is generated from source projections, predicates, and sorts using the plan; the template's SQL text is replaced. Packaging preserves the supported exported container, rewrites its checked model-byte length, assigns a new root item name, regenerates output elements in source order, and sets dataset and default data sources consistently. Model validation is marked N until BI Publisher validates it. Only a single-query, unparameterized, unsigned supported template format is accepted. Template SQL is never executed.

Verify SQL and model payload equality, output element names/order/types, byte lengths, and archive round-trip parsing. Import into a separate test catalog folder through the tenant's supported catalog upload action. If that tenant rejects the generated archive, report the exact error and use the supplied `.sql` in a new SQL Query data model while correcting packaging. An `.xdm` XML file is also supplied for inspection; do not assume every tenant accepts direct upload of that XML extension.

## Acceptance evidence

Set CANDIDATE_NOT_EXECUTED after generation and review. Record catalog import, Oracle execution, and OTBI reconciliation separately. An archive round trip proves local structure; a synthetic SQLite comparison proves only tested relational behavior. Neither establishes successful Oracle import or matching tenant output.

For a supplied reference query, compare outputs on synthetic adversarial fixtures for multiple invoice lines/distributions, absent optional dimensions, and repeated projected values. Align columns by output mapping. For `physical_rows`, compare multisets against a physical reference and verify that different fact keys remain separate even when projected values repeat. For `otbi_distinct`, check distinct tuples and their resulting counts. Check actual join keys and multiplicities in either mode. Then follow [validation-and-handoff.md](validation-and-handoff.md) for the analyst-run Oracle comparison against the declared goal.
