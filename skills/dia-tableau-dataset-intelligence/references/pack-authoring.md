# Pack authoring and ownership

The six YAML assets are the authoritative knowledge. Reader files are deterministic generated views. The unchanged extraction facts support both factual snapshots and LLM interpretation.

| Asset | Schema | Owns | Reader view |
| --- | --- | --- | --- |
| `dataset.yaml` | [dataset.schema.json](dataset.schema.json) | Stable identity, source snapshot, ownership, asset/view inventory and hashes | Pack README |
| `data-dictionary.yaml` | Bundled maintained dictionary schema version 2 | Dataset/field explanations and relevant semantic annotations | Markdown and CSV |
| `data-model.yaml` | [data-model.schema.json](data-model.schema.json) | Recorded model, table meanings, grain proposals, candidate keys, risks | Markdown with model diagram |
| `business-glossary.yaml` | [business-glossary.schema.json](business-glossary.schema.json) | Selected reusable concepts and proposed synonyms | Markdown |
| `metrics.yaml` | [metrics.schema.json](metrics.schema.json) | Declarative calculations, bindings, dates, dimensions, filters, units, gates | Markdown |
| `questions.yaml` | [questions.schema.json](questions.schema.json) | Possible analyses and their metric/field dependencies and support conditions | Markdown |

No source-specific user data belongs in the skill package. Deterministic helpers are shared through the installer, not copied as a new extraction implementation. The dictionary runtime's own schema and guide are located under the installed skill's `scripts/dependencies/dia-tableau-data-dictionary/`; the source checkout uses its existing sibling skill. Generated pack README and CSV are deliverables, not skill-package README files.

## Field dictionary authoring

The dictionary seed includes all extracted fields and evidence, plus empty context and enrichment slots. Read the entire facts set before explaining columns. Populate `dataset_context.summary`, relevant cautions, and `reviewed`. Each field's `definition` has `text`, `basis`, `confirmation_status`, `confirmed_at`, `confirmed_by`, and `evidence_refs`. Valid bases are workbook_description, recorded_metadata, formula_derived, context_inferred, supplied_context, name_based, analyst_confirmed, and undocumented.

A contextual explanation can combine source-table mappings, captions, related fields, actual formula text, workbook wording, and registered supplied context. Use actual IDs as references. Preserve original descriptions, formulas, aliases, attributes, and field ordering. Add optional `enrichment.label`, units, format, code_meanings, derivation, and usage_notes only when useful and supported. Every annotation carries its own evidence and confirmation; a definition's approval does not approve its units or currency.

Set each business field's `enrichment.reviewed` only after examining its meaning in context. Null meaning requires a focused question. Mark internal table records separately using the existing reserved-name/type rule. No observed-value claims, uniqueness claims, or invented code lists are allowed. Source-declared nullability belongs to recorded metadata when present; cached contains-null is not a constraint or null-count test. Unknown nullability stays unknown.

A proposed definition does not need an approval round before saving a draft. Only explicit user approval permits analyst_confirmed with attribution and timezone-aware time. Do not derive approvals from the previous Markdown. Existing snapshot IDs are not permanent enterprise concept IDs.

## Model interpretation

Every logical table has a proposed business role and grain; a physical table fallback is explicit when no logical graph exists. Interpretations reference actual table and field IDs. Keep configured relationship endpoints and performance/uniqueness settings unchanged. Candidate keys and all grain/relationship safety checks remain not_tested. Where information is missing, record a gap and a question rather than filling in plausible constraints.

Explain actual relationships precisely. Do not confuse similarly named payment identifiers, transaction-header identifiers, or tender lookup identifiers. An aggregation must identify its intended record level and how related tables could expand those rows. Alternate extract-context relation trees are representations, not additional business entities.

## Glossary and catalogs

Glossary concepts use dataset-scoped term IDs and reference their business fields. Definitions and synonyms have separately attributed proposal/confirmation states. Terms explain concepts such as Payment or Reporting Date; they do not repeat every column.

Metrics use dataset-scoped IDs and explicit formula placeholders/bindings. Every bound/date/filter/dimension field must exist. Metrics reference the intended model grain and any glossary concepts. Approval gates record unresolved grain, units, exclusions, event time, reversals, and duplication behavior as needed. A SUM over a numeric field is only a proposal, not a certified measure. Do not claim payment volume when counting only non-null occurrences of an unverified identifier.

Questions use existing metric, field, glossary, date, and dimension references. Support status means what the metadata supports; it is distinct from proposed/approved business status and not_tested data verification. Conditions propagate from their metric dependencies. Limit the MVP to a useful, coherent catalog; unrelated or unsupported ideas belong in explicit gaps, not manufactured formulas.

## Reproducibility and portability

All six assets identify the same dataset and workbook snapshot. Dictionary/model evidence files may be distinct extraction runs only when the input hash matches. Keep both inside the pack's evidence directory. The manifest records exact paths and hashes. Finalization checks the dictionary's facts reference matches the manifest and that every asset passes both schema and semantic validation.

Seven reader files are produced: README, dictionary Markdown/CSV, model Markdown, glossary Markdown, metrics Markdown, and questions Markdown. Schema/metadata remains machine-readable in the six YAML assets. These extra views preserve the requested six knowledge assets while making them readable. CSV cells beginning with spreadsheet formula characters receive an export-only apostrophe; canonical YAML is unchanged.

Completed packs are checked for tampering/staleness and exact regenerated view content. Preserve completed folders; use a fresh reviewed build for revisions. The helper does not silently recompute hashes over edited artifacts or regenerate directly edited reader views. No live systems, data-value scans, external publishing, automatic metric promotion, or semantic-layer execution occur in this MVP.
