# Document ownership map

Each Tableau workbook document owns exactly one kind of content. `workbook-facts.yaml` owns extracted facts. The dictionary's versioned YAML adds attributed definitions and questions; its human-readable document is generated from that structured source.

| Content | Owning document |
| --- | --- |
| Inventory, IDs, counts, duplicates, orphans, calculation reuse, anomalies, provenance, completeness | `workbook-audit.md` (plus `audit-facts.yaml`) only |
| Purpose, audience, owner, refresh cadence, layout as rendered, dashboard-level filter/legend/parameter/action behavior, caveats | `dashboard-reference.md` only |
| Worksheet shelf fields, mark types, encodings, sorts, sheet-local formulas and source bindings, confirmed role | `sheet-specs.md` only |
| Dataset context, contextual field meanings, relevant semantic annotations, technical metadata, source-level formulas, unresolved meanings | `data-dictionary.yaml`, rendered into `data-dictionary.md`, only |
| Dataset identity, source snapshot, asset inventory and hashes, unknown ownership | Pack `dataset.yaml`, rendered into its README |
| Table roles, recorded structure, per-table grain proposals, candidate keys, structural risks | Pack `data-model.yaml`, rendered into `data-model.md` |
| Reusable business concepts and separately proposed synonyms | Pack `business-glossary.yaml` |
| Candidate metric formulas, bindings, dates, dimensions, filters, units and approval gates | Pack `metrics.yaml` |
| Possible analytical questions, metric/field references and support conditions | Pack `questions.yaml` |

Documents reference each other by stable ID only. Restating another document's owned content is a defect.

The dictionary workflow extracts immutable workbook facts, creates versioned `data-dictionary.yaml`, records contextual dataset/field explanations, supported semantic annotations, and confirmations there, validates, and deterministically renders `data-dictionary.md`. Human document changes must enter the structured source first. It owns fields by `field_id`, while sheet specifications own worksheet-local calculations by `calc_id`. A dictionary may contain source-level formula text for understanding a field; it does not reproduce sheet usage, dashboard documentation, or workbook audit findings. Its provenance and local field-coverage caveats are necessary to identify the dictionary's evidence and do not constitute a workbook audit.
