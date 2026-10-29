# Documentation templates

Use these templates for the two documents. Replace every placeholder; a template placeholder must never survive into a written file.

## dashboard-reference.md

```markdown
# Dashboard reference - <workbook name>

Source: <repository_location or workbook file name>

## <dashboard name>

- Size: <sizing_mode, width x height from size facts>
- Data sources: <datasource captions>
- Purpose: <confirmed purpose statement, or "Needs analyst confirmation.">

### What is on the dashboard

| Order | Zone | Detail |
| --- | --- | --- |
| <n> | <kind> | <sheet name, filter field, legend field, or text> |

### Filters

| Filter field | Source sheet | Mode | Applies on change |
| --- | --- | --- | --- |

### Parameters

| Parameter | Caption | Members |
| --- | --- | --- |

### Legends

| Legend | Source sheet | Field |
| --- | --- | --- |

### Notes and caveats

- <verbatim lines from the dashboard title_text that state data caveats, or "None recorded in the workbook facts.">
```

## sheet-specs.md

```markdown
# Sheet specifications - sheets used on dashboards

Scope: only the sheets listed on a dashboard in the workbook facts.

## <sheet name>

- Appears on: <dashboard names>
- Role: <confirmed role label, or "Needs analyst confirmation.">
- Title text: <title_text>
- Data sources: <datasource names>
- Rows shelf: <rows or "none">
- Columns shelf: <cols or "none">
- Mark types: <mark_types>

### Calculations

| Caption | Formula |
| --- | --- |

### Sheet filters

| Column | Filter class |
| --- | --- |

### Encodings

| Attribute | Field |
| --- | --- |
```

## Section rules

- Omit a subsection table entirely when its facts list is empty; do not print an empty table.
- Keep every formula verbatim inside a fenced code block row or inline code; never paraphrase a formula.
- Every purpose statement and role label that was not confirmed by the user must read `Needs analyst confirmation.`
