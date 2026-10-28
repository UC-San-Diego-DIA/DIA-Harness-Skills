# Mapping report template

Use this structure for `KPI-Data-Mapping-YYYY-MM-DD-<topic>.md`. Replace bracketed placeholders with artifact facts, dataset-schema facts, or `Needs confirmation.` Never leave a template placeholder in a written document.

## Report skeleton

```markdown
# KPI Data Mapping: [topic]

**Mapped:** [YYYY-MM-DD]
**KPI artifact:** [Business-Questions-and-KPIs file name]
**Dataset:** [dataset path relative to the report location]
**Scope:** [All KPIs or the confirmed subset, listed by KPI identifier and name]

## Dataset schema

| Column | Apparent type |
| --- | --- |
| [exact column name] | [text, number, date, or Needs confirmation] |

Rows: [row-count estimate and how it was estimated, stated as approximate]

## KPI-01: [KPI name]

**Question:** [the business question from the KPI artifact, verbatim]
**Status:** Mapped | Partial | Blocked

### Required fields

| Metric component | Dataset field | Evidence |
| --- | --- | --- |
| [component from the KPI definition] | [exact dataset field name, or Data gap] | [artifact section or dataset column] |

### Calculation

[The formula to build, expressed against the exact dataset field names. For example: sum of Orders_Amount minus sum of Returns_Amount, grouped by Customer_Region.]

- Grouping: [fields or Needs confirmation]
- Time period: [period from the artifact or Needs confirmation]
- Filters: [each filter, or none recorded]

### Assumptions

- [Each grouping, time-period, or filter assumption, labeled as an assumption rather than a fact.]

### Data gaps

- [Missing component]: [What to request from stakeholders or source systems, concretely enough to act on.]

### Open questions

- [Open question carried from the KPI artifact, unresolved.]

## How to use this report

This report documents what to build. It contains no calculated results; build the confirmed calculations in the workspace pipeline or analysis workflow once the data gaps are resolved.
```

## Per-KPI rules

- Number sections sequentially as `KPI-01`, `KPI-02`, and so on, using the artifact's own KPI identifiers when it records them.
- Status values: `Mapped` when every component resolves to a dataset field; `Partial` when some components are data gaps; `Blocked` when no mapping is possible.
- Quote field names exactly as they appear in the dataset schema. Never paraphrase or normalize them.
- Copy the business question from the artifact verbatim; do not rewrite it.
- Under Data gaps, state the request concretely: which field, which system or stakeholder, and why it is needed. Never propose a substitute field or proxy metric.
- Carry each unresolved open question from the artifact into the report unchanged. Record both positions when the artifact records a disagreement.
- Keep the Assumptions, Data gaps, and Open questions headings in every KPI section; write `None recorded.` under a heading with nothing to report.

## Writing rules

- Cite evidence for every required-field row: the artifact section for the component and the dataset column for the field.
- Keep calculations declarative. Describe what to build; never present computed values or claim to have verified them.
- Do not name a currency or unit unless the artifact or user defines it.
- Use file names for sources, not absolute paths.
- Do not quote sample data values in the report. The schema description is enough; the report is documentation, not a data extract.
- Mark anything not established by the artifact or the dataset schema as `Needs confirmation.`
