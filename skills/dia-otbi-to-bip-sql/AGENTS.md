# AGENTS.md

Guidance for agents and contributors working in this repository.

## What this is

`dia-otbi-to-bip-sql` is a TritonAI skill: [SKILL.md](SKILL.md) is the entry point
the agent loads, `scripts/extract_catalog.py` is its only executable helper,
and `references/` holds durable background material. The skill translates an
Oracle Fusion OTBI analysis (`.catalog`) into reviewable BI Publisher SQL.

## Navigating the mappings

- The mapping library lives in
  [references/mappings/](references/mappings/README.md): one XLSX workbook per
  subject area, indexed in its README with row counts and verification dates.
- The extractor discovers mapping sheets by the `SUBJECT_AREA` header row and
  matches report fields on subject area + presentation table + presentation
  column. Pass the workbook whose subject area matches the analysis; if no
  bundled workbook matches, ask the user for their own standard XLSX mapping
  instead of guessing or borrowing another subject area's file.
- Workbooks are candidate evidence only. They never define joins, source
  selection, measure aggregation, currency rules, or security predicates.
- Treat an existing indexed workbook as frozen evidence. To change it, verify
  the new rows, update the index row (Last Verified date and reason), and
  preserve prior candidate rows unless a row is demonstrably wrong.
- To add a subject area, follow the "Producing a new mapping" section of the
  mappings README and add the index row in the same change.

## House rules

- Keep tenant literals, report-specific business rules, and UCSD-specific
  values out of this skill; they belong in review output files.
- Keep the extractor stdlib-only; do not add dependencies for parsing XLSX or
  catalog files.
- Review packages produced with the skill freeze their own copies of inputs
  and record hashes; never edit those frozen copies to "fix" history.
