# Documentation templates

Use these templates for the two documents. Replace every placeholder; a template placeholder must never survive into a written file. Both documents start with the fixed front-matter block, cite stable fact IDs, and reference each other by ID only.

## dashboard-reference.md

```markdown
<!-- Front matter: copy verbatim with the bracketed values filled in. -->
Source facts: <absolute path to workbook-facts.yaml> (sha256: <64-hex digest>)
Schema version: 2
Generated: <UTC timestamp>
Confirmations: <absolute path to confirmations.yaml>

# Dashboard reference - <workbook name>

Source: <repository_location or workbook file name>

## <dashboard name>

Dashboard ID: <dashboard_id>

- Size: <sizing_mode, width x height from size facts>
- Data sources: <datasource captions>
- Purpose: <confirmed purpose statement from confirmations.yaml, or "Needs analyst confirmation.">

### What is on the dashboard

| Order | Zone | Sheet ID | Detail |
| --- | --- | --- | --- |
| <n> | <kind> | <sheet_id for sheet zones, empty otherwise> | <sheet name plus sheet title, filter field, legend field, or text> |

### Filters

| Filter field | Source sheet | Sheet ID | Mode | Apply button shown |
| --- | --- | --- | --- | --- |

### Parameters

| Parameter | Caption | Members |
| --- | --- | --- |

### Legends

| Legend | Source sheet | Field |
| --- | --- | --- |

### Analyst-provided context

- Owner: <confirmed owner, or "Not recorded in the workbook facts.">
- Audience: <confirmed audience, or "Not recorded in the workbook facts.">
- Refresh cadence: <confirmed refresh cadence, or "Not recorded in the workbook facts.">
- Access notes: <confirmed access notes, or "Not recorded in the workbook facts.">

### Notes and caveats

- <verbatim lines from the dashboard title_text that state data caveats, or "None recorded in the workbook facts.">

### Change log

- Generated from: <absolute path to workbook-facts.yaml>
- Supersedes: <previous document path, or "none">
- Date: <generation date YYYY-MM-DD>

Inventory, counts, duplicates, orphan sheets, anomalies, and completeness live in `workbook-audit.md` beside this document; this document does not restate them.
```

## sheet-specs.md

```markdown
<!-- Front matter: copy verbatim with the bracketed values filled in. -->
Source facts: <absolute path to workbook-facts.yaml> (sha256: <64-hex digest>)
Schema version: 2
Generated: <UTC timestamp>
Confirmations: <absolute path to confirmations.yaml>

# Sheet specifications - sheets used on dashboards

Scope: only the sheets listed on a dashboard in the workbook facts.

## <sheet name>

Sheet ID: <sheet_id>

- Appears on: <dashboard names, each with its dashboard_id>
- Role: <confirmed role label from the shared role vocabulary, or "Needs analyst confirmation.">
- Title text: <title_text>
- Data sources: <datasource names>
- Rows shelf: <rows or "none">
- Columns shelf: <cols or "none">
- Mark types: <mark_types>
- Sheet filters: <sheet filter captions or "none recorded">
- Encodings: <encoding summary or "none recorded">

### Calculations

**<calculation caption>** (calc_id: <calc_id>)

```tableau
<verbatim formula>
```

### Sheet filters

Use the sheet filters bullet in the sheet header; add the table below only when the sheet has filters.

| Column | Filter class |
| --- | --- |

### Encodings

Use the encodings bullet in the sheet header; add the table below only when the sheet has encodings.

| Attribute | Field |
| --- | --- |

Field definitions: use the shared field registry (`docs/shared/role-vocabulary.md` in the DIA-Harness-Skills repository) for field semantic types; this document does not define fields.
```

## Section rules

- Omit a subsection table entirely when its facts list is empty; do not print an empty table.
- When the dashboard title text contains a literal author placeholder segment such as `<Sheet Name>`, do not use it as the purpose statement; use the descriptive title segment instead and record the placeholder in the notes section.
- When a dashboard purpose statement is proposed from the title text rather than confirmed by the user, append "(proposed from the dashboard title text; needs analyst confirmation)" to the purpose line.
- Keep every formula verbatim inside a fenced `tableau` code block under its caption; use one caption heading plus one code block per calculation rather than a table when formulas span multiple lines.
- In tables and zone details that name a field, use `field_caption` (or `column_caption` for sheet filters) when present so the document shows the human-readable name such as "Location Name"; fall back to the raw `field` or `column` path only when no caption is available.
- Keep every formula verbatim inside a fenced code block row or inline code; never paraphrase a formula.
- Every purpose statement and role label that was not confirmed by the user must read `Needs analyst confirmation.`
- The analyst-provided context fields are never invented from workbook content; write `Not recorded in the workbook facts.` unless the analyst supplied and confirmed the value.
- Documents reference each other by stable ID only. Restating another document's owned content is a defect.
