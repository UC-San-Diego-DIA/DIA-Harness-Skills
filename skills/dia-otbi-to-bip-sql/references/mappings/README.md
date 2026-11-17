# OTBI-to-OFC Mapping Library

One XLSX workbook per Oracle Fusion subject area, bundled with the skill so the
mapping evidence is available on any machine that installs it.

## Format contract

Each workbook is a standard XLSX with one or more data sheets. Every mapping
sheet has a header row containing at least:

`SUBJECT_AREA`, `PRESENTATION_TABLE`, `PRESENTATION_COLUMN`,
`PHYSICAL_TABLE`, `PHYSICAL_COLUMN`, `VO_DEFINITION`, `DATABASE_OBJECT`,
`DATABASE_COLUMN`, `INDEXED`

`scripts/extract_catalog.py` discovers mapping sheets by this header, reads all
matching sheets in the workbook, and matches report fields on the
`SUBJECT_AREA` + `PRESENTATION_TABLE` + `PRESENTATION_COLUMN` triple. Keep
every candidate row for a column, including rows with different physical
sources; the extractor reports all of them and the agent must not pick one
automatically.

## Index

| Subject Area | File | Rows | Last Verified | Notes |
| --- | --- | ---: | --- | --- |
| Project Costing - Actual Costs Real Time | [project-costing-actual-costs.xlsx](project-costing-actual-costs.xlsx) | 3,404 | 2026-11-16 | Initial bundled mapping |
| Payables Invoices - Transactions Real Time | [payables-invoices-transactions.xlsx](payables-invoices-transactions.xlsx) | 3,977 | 2026-11-17 | Added 2026-11-17 |
| Payables Payments - Disbursements Real Time | [payables-payments-disbursements.xlsx](payables-payments-disbursements.xlsx) | 1,686 | 2026-11-17 | Added 2026-11-17 |
| Procurement - Procure To Pay Real Time | [procurement-procure-to-pay.xlsx](procurement-procure-to-pay.xlsx) | 2,981 | 2026-11-17 | Added 2026-11-17 |
| Procurement - Purchasing Real Time | [procurement-purchasing.xlsx](procurement-purchasing.xlsx) | 4,686 | 2026-11-17 | Added 2026-11-17 |
| Procurement - Requisitions Real Time | [procurement-requisitions.xlsx](procurement-requisitions.xlsx) | 3,375 | 2026-11-17 | Added 2026-11-17 |
| Supplier - Supplier Real Time | [supplier-supplier.xlsx](supplier-supplier.xlsx) | 538 | 2026-11-17 | Added 2026-11-17 |

When adding a subject area: name the file in kebab-case after the subject
area, fill every column above for each row, record the tenant (or release)
against which the mapping was verified, and add the workbook to this index
with its row count and verification date. Do not replace an existing workbook
without updating its Last Verified date and noting the reason.

## Producing a new mapping

1. Identify candidate sources from generated OTBI physical SQL, Oracle Fusion
   documentation, and the subject area's view-object definitions.
2. Confirm each presentation column maps to its stated subject area only; a
   field absent from the workbook's subject area stays unresolved even if
   another subject area has the same name.
3. Validate representative columns against tenant data where a connection is
   available, and record what was and was not verified.
4. Freeze the workbook, add the index row, and keep tenant literals out of the
   workbook; mappings are candidate evidence, never join definitions, measure
   semantics, currency rules, or security predicates.
