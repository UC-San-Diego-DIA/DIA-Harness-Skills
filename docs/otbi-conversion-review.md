# OTBI conversion review

Reviewed November 12, 2026. Scope: the source skill, its conversion helper and bundled 26B FIN/PPM workbooks, a user-supplied real catalog inspected locally, synthetic conversion cases, and current official Oracle documentation. Real catalog content, business literals, and local user paths are excluded from this repository report and the regression fixtures.

## Verdict

The original workflow did not establish that generated physical SQL would execute in Oracle or match OTBI. It could silently alter filters and values, select an ambiguous mapping, and emit an executable Cartesian query while treating file generation as success. The supplied real analysis also requires semantic reconstruction beyond text substitution.

The revised skill is suitable for continued testing with explicit evidence and validation stages. It is not certified as a universal OTBI compiler. No Oracle query was executed, no BI Publisher model was changed, and no OTBI result export was available for reconciliation during this review. It remains in testing.

## Demonstrated defects and corrections

| Finding | Consequence | Correction |
| --- | --- | --- |
| Binary metadata and report XML shared one compressed stream | Decoding a container could replace bytes or reject valid report XML | Extract UTF-8 report fragments from the binary envelope and reject invalid bytes inside XML |
| Multiple tables without applied joins | A local two-by-two fixture returned four rows from the original scaffold | Physical scaffolds now return no rows until required mapping, semantic, join, and scope review; required unresolved edges block runnable delivery |
| First mapped row selected among different database columns | Wrong currency, grain, code, or meaning could be chosen | Differing mappings block automatic construction; choices require recorded evidence |
| Coverage checked only for a selected expression's last field | Unmapped formula operands, filters, or sorts could survive into physical SQL | Every substituted reference must map; filter-only and sort-only fields participate |
| Two-part regex applied to three-part references | Subject area could be mistaken for a presentation folder | Qualified references use their explicitly named subject area |
| Pattern filters lost from parameterized SQL | Literal and parameterized variants could return different populations | Preserve nonparameterized filter nodes; reject unknown operators rather than flattening text |
| Saved filters omitted and variables left unresolved | Source criteria could be missing or non-Oracle syntax could remain | Stop construction and preserve complete source evidence through inspection |
| Separate bounds reused one parameter name | One bound could remain a literal | Distinct predicates receive distinct parameters |
| Strings typed by appearance, numeric literals quoted, whitespace collapsed | IDs, literal matching, and datatypes could change | Use source literal types, preserve string contents, and validate typed literals |
| Reference substitution inside quoted strings | A business literal could be rewritten | Keep SQL strings opaque during substitution |
| ASCENDING/DESCENDING and modified headings emitted | Invalid sort syntax and changed output labels | Emit ASC/DESC and preserve quoted headings |
| OTBI functions and aggregates passed through | Oracle rejection or incorrect aggregation | Helper rejects unsupported semantic compilation; skill reconstructs it from inspection and evidence |
| Ordinary multi-select menus emitted as lexicals | Instructions omitted the required lexical package setup | Use bind parameters for menus and document their BI Publisher settings |
| Every documented FK treated as a join to apply | Wrong role, inner/outer behavior, or grain could change results | Select the intended graph; verify role, direction, composite keys, cardinality, scope, and join type |
| File generation described as success | A novice could mistake a draft for a validated report | Separate BLOCKED, CANDIDATE_NOT_EXECUTED, EXECUTED_NOT_RECONCILED, and RECONCILED |

## Real catalog stress test

The supplied analysis contains 26 selected columns in Project Costing - Actual Costs Real Time, including a qualified reference to Projects - Cross Subject Area Analysis - Real Time. Its formulas use IFNULL, FILTER with USING, and DESCRIPTOR_IDOF. A fiscal-period predicate uses a presentation variable, so the saved catalog does not establish the intended runtime period selection.

The bundled PPM workbook supplies six distinct database mappings for the logical Cost measure. These combine expenditure-item and cost-distribution sources with entered, project, and project-functional burdened-cost columns. The Fiscal Period field has four distinct mapped sources. Project Number and Task Number also have table/view alternatives. The mapping inventory therefore does not establish which physical cost branch and calendar branch OTBI used.

The revised inspection route preserves the complete formulas and filter XML, recognizes qualified references, and reports the unresolved runtime variable. Automatic SQL construction stops. It does not replace the unknown period, select the first Cost mapping, convert a descriptor ID to a displayed task number, or claim to have produced working database SQL.

To complete this particular conversion, obtain the issued logical SQL for the intended run, effective period prompt values, evidence for the physical cost/currency/calendar and descriptor-key choices, the target release and access context, and an OTBI export. Construct the literal candidate with those choices, have the analyst run it in BI Publisher, and compare the complete agreed scope. Do not infer its displayed Total by adding the classification columns.

## Oracle documentation checks

The newest product-family libraries verified in this review were 26D; the bundled lineage workbooks remain 26B. The revised workflow resolves releases anew and also records the tenant release rather than assuming it matches the documentation.

- Oracle's [OTBI architecture description](https://docs.oracle.com/en/cloud/saas/financials/26d/occar/overview-of-transactional-business-intelligence.html) explains that the BI Server uses repository mappings and ADF view objects. This supports treating raw column lineage as incomplete semantic evidence.
- The [Project Management 26D schema library](https://docs.oracle.com/en/cloud/saas/project-management/26d/api.html) links the current Tables and Views book. The [PJC_EXP_ITEMS_ALL entity](https://docs.oracle.com/en/cloud/saas/project-management/26d/oedpp/pjcexpitemsall-25003.html) documents its item key, currency-specific costs, outgoing relationships, and incoming cost-distribution relationship. A documented relationship does not decide the report's intended grain.
- The [Financials 26D Tables and Views book](https://docs.oracle.com/en/cloud/saas/financials/26d/oedmf/index.html) was opened to verify its release label.
- Oracle's [Logical SQL reference](https://docs.oracle.com/middleware/bi12214/biee/BIESQ/toc.htm) defines FILTER as conditional aggregation. Translation must preserve each measure's own predicate and actual aggregation rule.
- Oracle's [double-column guidance](https://docs.oracle.com/en/middleware/bi/analytics-server/user-oas/create-parameter-that-uses-logical-sql-query-double-column.html) identifies DESCRIPTOR_IDOF as access to a descriptor key.
- Oracle's [SQL data set guidance](https://docs.oracle.com/en/middleware/bi/analytics-server/design-publish/create-datasets-using-sql-queries.html) distinguishes database SQL from BI Server logical SQL and documents binds and lexical setup.

## Verification and limits

The offline regression suite contains 33 tests covering source extraction and selection, binary catalog envelopes, filter and literal preservation, mapping coverage and ambiguity, qualified references, parameters, sorting/headings, guarded SQL behavior, inspection of complex criteria, output conflicts, provenance, malformed inputs, and a conditional-aggregation example. Fixtures are synthetic and use the Python standard library. One test executes portable scaffold SQL in SQLite to demonstrate the Cartesian-output defect and verify the no-row guard. This does not test Oracle syntax or Fusion semantics. A final read of the real catalog confirmed one analysis, 26 selected columns, preserved source evidence, and an actionable unresolved-prompt error. The source file's hash was unchanged.

Run the suite with `python -B scripts/test_otbi_conversion.py`. It is also included in repository CI. The skill-package validator, repository validator, and installer tests passed during the review. Installer checks used a temporary destination, not the live Harness installation.

The next acceptance milestone is an analyst-executed Oracle candidate reconciled against OTBI for a recorded scope. A real catalog is sufficient to expose conversion risks, but it cannot prove output equality without the runtime context and result evidence. Follow the [validation protocol](../skills/dia-otbi-to-bipublisher-sql/references/validation-and-handoff.md).

## Follow-up with a paired OTBI and BIP example

A supplied matching invoice-distribution analysis and data model enabled implementation of the [reviewed compiler](../skills/dia-otbi-to-bipublisher-sql/references/reviewed-compilation.md). This produces literal Oracle attribute SQL from source projections and predicates using workbook-checked field choices and a documented join graph. It can package that SQL and matching output metadata into a new local catalog using the supplied model container. It does not copy the template query as its generated SQL.

The reference model resolved the Supplier Name lineage branch and supplied required header/line/distribution joins and optional supplier relationships. Comparison also exposed different column order, an additional reference sort, and plain SELECT in the physical reference versus logical distinct-row semantics. The generated candidate follows OTBI projection order and distinct behavior.

Seventeen additional synthetic tests exercise executable relational behavior, composite keys, missing optional dimensions, repeated projected values, source filters and ordering, workbook choice validation, source-hash binding, model output metadata, UTF-8 payload lengths, full CLI generation, and overwrite protection. The actual generated SQL and supplied reference SQL were also executed locally on synthetic fixtures after aligning column positions. Their distinct row sets and join graph matched; the physical reference retained one extra duplicate tuple in the adversarial fixture. This is a local behavioral check, not an Oracle or live OTBI reconciliation.

The generated catalog round-tripped through its packaging parser and the maintained data-model intake helper. Oracle catalog import and database execution remain separate unperformed checks. User files and generated conversion deliverables remain outside this repository. The skill remains in testing, with a working local candidate-generation path for the supported simple-attribute scope.

## Follow-up for external prompts and aggregate formulas

The aggregate compiler now accepts schema-version-2 review plans for a bounded typed grammar: reviewed SUM measures, conditional FILTER, null functions, descriptor keys, arithmetic and row predicates. External prompt values are separately evidenced inputs, including multiple selections, rather than an expectation that the standalone analysis's Advanced SQL reflects a dashboard asset's active prompt. Original defaults and XML remain available in the manifest.

The compiler shares workbook-checked field bindings and documented join plans with the attribute path. Aggregate plans require explicit fact keys, input grain, currency, physical row scope, descriptor lineage when used, and review of any grand-total stage. Multiplying joins are rejected. A selected flat table view determines visible output order; hidden calculations remain internal. The supported one-text-dimension total is computed from the source formulas at total grain. Automatic BIP parameter metadata and unsupported result structures remain outside this implementation.

The no-administrator investigation route uses documented bounded diagnostic queries and supplied BIP exports to examine source alternatives. It does not treat lack of session-log privileges as a dead end or ask users to guess physical mappings. Diagnostics remain separate from report candidates, and equal amounts among alternatives do not prove their lineage.

Twenty-five additional synthetic tests exercise aggregate results, overlapping category predicates, repeated and negative costs, nulls, descriptor/display differences, subject identity, literal preservation, runtime substitution, evidence failures, source/view completeness, physical scope restrictions, and full CLI/model packaging. A grammar-only pass over all 26 expressions in a supplied complex catalog succeeded with deliberately unresolved symbolic bindings. That check established expression coverage without approving any physical mapping or generating an Oracle candidate. Live Oracle execution and complete OTBI reconciliation remain required.

## Captured physical execution evidence

Access to OTBI Performance Real Time provided tenant-specific physical SQL without the Administration session-log UI. A clipped capture nevertheless contained two complete source/aggregation CTEs. Those blocks established the distribution-line project-functional cost branch, ledger-specific fiscal-day relationship, task descriptor key, project owning-organization role, effective-date restrictions and session-sensitive security predicates for the captured request. Derived aliases needed tracing back to their base columns; alias spelling alone was not a new workbook mapping.

The accompanying performance XML contained both native SQL and ADF SQLBypass request rows, including different effective prompt selections on the same day. Native SQL was clipped before its calculation/output tail. The workflow now records execution identity and completeness, distinguishes ADF metadata from database SQL, and supports character-length/chunk export investigation using actual presentation references. The original catalog remains available for a separately labeled reconstruction. Neither a partial source block nor a rebuilt tail establishes reconciliation with an earlier OTBI export.

The returned chunk export contained only the two previously available ADF requests. It did not recover native SQL. A separate literal candidate now combines the complete captured source CTEs with all 26 original catalog expressions, preserving the selected table's 25 visible columns and recalculating the source formulas at grand-total grain. Oracle-dialect parsing and comparisons of factored versus unfactored expressions on synthetic rows passed. Oracle execution and OTBI reconciliation remain unperformed.

A category-identity cross-check also corrected an earlier diagnostic label. The two projects tested as Sports Camp actually belong to NCAA Post-Season Expenses in the source catalog. Their results cannot be compared with the Sports Camp total. Bind each diagnostic to the source column ID, heading and complete formula before choosing project lists or a reference total. Preserve earlier evidence, but explicitly supersede conclusions based on the wrong category.

## Physical-row construction is now the default

Following the attribute-query comparison, the skill now prioritizes physical field identity, joins, row grain, filters, and calculations. Column order, readable aliases, and ordinary sorting are secondary unless they affect record selection, calculations, or a requested dependent interface. Earlier sections describing automatic logical DISTINCT record the previous policy.

The attribute compiler now retains physical rows by default with plain SELECT. A review plan can request `row_policy: otbi_distinct` for distinct OTBI output. The effective policy is saved in the manifest and CLI summary. Unknown policies fail rather than silently selecting one. Aggregate compilation retains its required GROUP BY and uses `aggregate_grain`; changing the attribute default does not change measure semantics.

Regression checks now compare duplicate multiplicities against a physical reference, verify the explicit distinct option, and allow mapped unprojected sort attributes in physical-row mode while retaining the distinct-mode constraint. Grain review distinguishes different fact keys with identical displayed values from multiplication of the same key. No live Oracle execution or tenant reconciliation is established by this policy change. The [plain-language review guide](otbi-skill-review-guide.md) maps package files, decision ownership, and test coverage.
