# Conversion contract

## Source evidence

One run converts one selected analysis from one supplied catalog. The helper reads compressed report XML locally without opening Oracle. Use `--inspect` first to list analyses and expose full report XML, formulas, filter XML, sorts, and inspection blockers. It writes JSON to stdout without requiring a workbook. It does not resolve runtime dashboard context or execute logical SQL.

The workbook's OTBI Subject Areas sheet must include SUBJECT_AREA, PRESENTATION_TABLE, PRESENTATION_COLUMN, DATABASE_OBJECT, and DATABASE_COLUMN. Preserve PHYSICAL_TABLE, PHYSICAL_COLUMN, VO_DEFINITION, and workbook row numbers when available. The indexed 26B FIN and PPM bundles are lineage evidence, not the OTBI repository's full semantic model. Check actual coverage and record hashes. BICC mappings are not OTBI lineage mappings.

Match a two-part reference within the analysis's subject area. Match a three-part reference within its explicitly named subject area. Never strip its qualifier and map it to a similarly named field elsewhere. All operands, including filter-only and sort-only fields, need coverage. Constants do not need mappings. The agent resolves workbook alternatives using source semantics and official evidence, recording the selected field and rationale. Only missing lineage or a material ambiguity that remains unresolved blocks construction.

## Helper output

After mapping and join review, the [reviewed compiler](reviewed-compilation.md) produces literal SQL for its supported attribute and aggregate expressions, plus a local BIP data-model catalog only when requested with a supplied template. Its manifest identifies CANDIDATE_NOT_EXECUTED and separate import, execution, and reconciliation states. Its `.sql` and any generated model payload must agree. The scaffold behavior below applies to the optional investigation mode of `convert_otbi_catalog.py`, not the default delivery path.

For a restricted scalar analysis the helper writes:

```text
<base>-manifest.json
<base>-logical-literal.sql
<base>-logical-parameters.sql
<base>-physical-literal.sql
<base>-physical-parameters.sql
<base>-README.md
<base>-join-research.md
<base>-validation.md
<base>-parameters/<parameter>.sql
```

Physical and LOV scaffolds have a `WHERE 1 = 0` guard. The manifest and summary record blocked_scaffold, Oracle execution not_run, and reconciliation not_run. Exit 0 establishes file generation only. Logical SQL files are source references, not database SQL. The join worksheet is a research starting point.

The helper preserves supported comparison, literal list, logical, pattern, null, and between filters. It keeps literal types and whitespace, uses distinct parameter names for separate predicates, and preserves headings. Between and pattern predicates remain literal unless explicitly parameterized during review. Unsupported filter nodes, unresolved variables, and saved-filter references stop generation. Full inspection evidence remains available.

The helper does not compile OTBI aggregates, conditional measures, level-based/time-series functions, descriptor keys, repository security, combined criteria, selection steps, or view-specific semantics. It rejects these when detected. Read full report XML to catch semantics outside its recognized subset. Manual translation follows [semantic-equivalence.md](semantic-equivalence.md); never bypass an error by deleting source logic or relaxing coverage.

## Reviewed deliverables

Correct physical columns, join relationships/types, row grain, filters, and calculations define construction success. Attribute candidates default to `physical_rows` with plain SELECT. Set `otbi_distinct` only for an explicit distinct-output requirement; grouped measures retain `aggregate_grain`. Record the effective policy and underlying row keys in the evidence. Ordinary output order, names, and sorting are secondary; preserve dependencies that affect calculations, record selection, or a requested consuming interface. The compiler's convenient presentation preservation is not an extra equivalence gate.

Deliver the complete literal SQL candidate with its status and next BI Publisher test. Keep source hashes, helper provenance, workbook rows, documentation releases/URLs, selected mappings, joins, transformations, and material scope limits in the compiler manifest/plan or one concise evidence record. For manual SQL use `<base>-evidence.md`; update it with execution and reconciliation evidence as supplied. Do not duplicate the record across a README, join worksheet, report, and validation file. Existing helper outputs may be retained without creating manual counterparts. Additional evidenced keys and bridge tables are allowed for joins, security, and semantic reconstruction; projected presentation fields still need workbook lineage.

The reviewed physical query must be one read-only Oracle statement, optionally using WITH, nested SELECTs, explicit joins, GROUP BY, and HAVING. Do not include a trailing semicolon, OTBI-only functions, subject-area FROM clauses, presentation variables, unresolved comments, or parameter binds in the literal baseline. Align literal and parameterized variants except for intended parameter substitutions. Document BI Publisher element-name constraints separately from displayed OTBI headings.

Never overwrite outputs without confirmation of the exact paths. On failure, report the actionable error and preserve inputs and existing outputs. Missing evidence produces a blocked report, not a purported working query.
