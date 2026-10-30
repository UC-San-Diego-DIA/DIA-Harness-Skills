# Document ownership map

Each Tableau workbook document owns exactly one kind of content. `workbook-facts.yaml` is the only factual source; human documents are rendered views of it.

| Content | Owning document |
| --- | --- |
| Inventory, IDs, counts, duplicates, orphans, calculation reuse, anomalies, provenance, completeness | `workbook-audit.md` (plus `audit-facts.yaml`) only |
| Purpose, audience, owner, refresh cadence, layout as rendered, dashboard-level filter/legend/parameter/action behavior, caveats | `dashboard-reference.md` only |
| Shelf fields, mark types, encodings, sorts, verbatim formulas, source binding, confirmed role | `sheet-specs.md` only |

Documents reference each other by stable ID only. Restating another document's owned content is a defect.
