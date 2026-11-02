# Context-enriched dictionary contract

The versioned YAML owns both extracted evidence and LLM-authored explanations. The Markdown is a deterministic analyst view. [data-dictionary.schema.json](data-dictionary.schema.json) defines schema version 2; [data-dictionary-v1.schema.json](data-dictionary-v1.schema.json) preserves version-1 compatibility. The helper validates structure, snapshot identity, annotations, and rendering readiness.

## Minimum useful dictionary

The analyst needs a dataset explanation and each business field's name, meaningful definition, and data type. Units/format, code meanings, calculation logic, and usage cautions are conditional additions. Do not fill optional properties merely to fill a template. Important unknowns become focused questions. Every proposed meaning carries a review status; confirmed meaning requires explicit approval.

Keep descriptions compact enough to scan. Explain the field's business concept and important distinction from neighboring fields. Do not repeat its label or prepend "based on the field name" to every description; the structured evidence basis already records that limitation.

## Dataset context

`dataset_context` contains `reviewed`, `summary`, optional `row_description`, `usage_notes`, and `open_questions`. Summary describes the dataset's subject and represented records using available context. Record context may be a labeled inference; it is never evidence of verified row grain or uniqueness. Put shared uncertainties here once, such as payment versus transaction record levels. A complete review requires a populated summary.

Use workbook/source titles, source-table mappings, related field groups, captions, documented descriptions, actual formulas, available sheet/dashboard wording, and supplied documentation as a connected body of evidence. Do not use external systems or sample data values. Contextual enrichment should use the strongest available evidence rather than treating every column in isolation.

## Annotation records

`definition` and each populated semantic annotation use the same record shape:

```yaml
text: "The amount recorded against a transaction's payment entry."
basis: "context_inferred"
confirmation_status: "unconfirmed"
confirmed_at: null
confirmed_by: null
evidence_refs:
  - "<actual-field-id>"
  - "<actual-related-field-or-datasource-id>"
```

This is an example proposal, appropriate only if the actual workbook supports it. It does not establish payment-row grain, currency, or summation safety. References must be actual IDs from the extracted facts or registered context records; placeholders fail validation.

| Basis | Meaning |
| --- | --- |
| `workbook_description` | Existing description or faithful paraphrase |
| `recorded_metadata` | Directly recorded attributes, such as configured labels |
| `formula_derived` | Explanation supported by an actual recorded calculation |
| `context_inferred` | LLM explanation combining dataset, table, field, and document context |
| `supplied_context` | Meaning supported by a registered supplied-document or user-statement excerpt |
| `name_based` | Tentative interpretation when only the name provides useful evidence |
| `analyst_confirmed` | User explicitly supplied or approved this annotation |
| `undocumented` | Meaning unresolved; null text |

All populated meanings require evidence references. Only `analyst_confirmed` has confirmed status and non-null attribution/time; all other annotations remain unconfirmed. Confirmation applies to the individual annotation. An approved definition does not automatically approve its currency, code meanings, or usage notes. The skill establishes actual user approval; code checks record consistency.

`context_sources` registers additional evidence with unique `id`, `kind` (`supplied_document` or `user_statement`), `locator`, `sha256`, and a relevant `excerpt`. Documents require a hash; user statements can have null hash. Workbook/source/field/sheet IDs already exist in facts and need no duplicate catalog record. Keep enough evidence for an AI to distinguish extracted fact, documented meaning, and interpretation. Do not fabricate excerpts or approval.

## Field enrichment

Every original field remains in its source with exact extracted metadata and stable ID. It adds:

- `category`: `business` or `tableau_internal`, assigned deterministically. The latter requires both datatype `table` and a reserved `[__tableau_internal_object_id__].` name. Do not reclassify ambiguous fields to avoid reviewing them.
- `definition`: primary contextual meaning. Partial supported explanations are useful; do not force unsupported detail. Null text is permitted when genuinely unresolved.
- `open_questions`: field-specific questions about unresolved distinctions or meaning. Unresolved business definitions need a question.
- `enrichment.reviewed`: set true only after contextual review.
- `enrichment.label`: optional readable business label when the workbook caption is absent or confusing. Preserve original names/captions. Draft labels are visibly marked.
- `enrichment.units`, `format`, `derivation`: optional annotation records, otherwise null.
- `enrichment.code_meanings`: an array of unique `code` plus annotated `meaning` records. Only actual supported code mappings are allowed.
- `enrichment.usage_notes`: annotations for material interpretation guidance.

For calculations, explain actual operators, branches, aggregation, null handling, LODs, and table calculations as supported. Raw formulas remain unchanged in YAML. Optional derivation text is the concise analyst explanation. For money or date fields, document supported units or formats; unknown currency and timezone remain questions instead of assumptions. Do not treat cached default aggregation as a business metric recommendation.

For similar IDs or dates, use mappings, captions, and surrounding context to explain supported distinctions. A name alone does not prove a primary key, a foreign key, equivalence, or an event-time definition. Keep those interpretations conditional or unresolved.

## Validation and rendering

`create` and `migrate` produce structurally valid, unreviewed scaffolding. `validate` and `render` require the completed dataset review and every business-field review. These commands reject broken evidence references, missing provenance, changed metadata, incomplete confirmation, and unresolved meanings without questions. They cannot prove that prose is true or helpful; the skill must review semantic usefulness.

The Markdown contains a short dataset overview and one field table per source, followed by questions, controls, and internal records. It shows drafted or confirmed annotations explicitly. Native type codes, technical evidence, hashes beyond compact provenance, original descriptions/formulas, and confirmation attribution remain in the YAML. No copied technical inventory per field is needed in the analyst document.

Version 1 remains readable with its original renderer. `migrate` creates version 2 in a new file, preserving prior definitions and approvals while adding empty enrichment and evidence slots. Complete a new contextual review before rendering. Ordinary `revise` preserves the current schema, increments content revision, and records parent path/hash. Do not silently relabel migrated name-based meanings as context-inferred.

Source workbook hashes, extracted fact hashes, original snapshots, and revision links retain their existing roles. Keep referenced facts and prior YAML revisions for validation. Changed workbook snapshots require fresh extraction; stable IDs here do not establish permanent enterprise business-concept identities.
