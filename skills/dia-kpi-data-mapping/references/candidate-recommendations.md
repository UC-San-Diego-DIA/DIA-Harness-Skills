# Optional dataset-derived recommendations

Read this reference only when the user asks for additional measures supported
by the named dataset. Otherwise map the requested KPIs without recommendations.

## Choose useful candidates

- Honor a user-supplied limit. Otherwise suggest at most three candidates and
  prefer fewer when the schema offers little beyond the requested metrics.
- Use schema and a small sample only. Each proposal needs exact existing
  fields, a plausible declarative definition, and a reason it could help the
  stated audience. Do not claim the measure is validated or calculate it.
- Do not duplicate a requested KPI or propose a proxy for a missing component.
- Respect explicitly parked, rejected, or deferred ideas in the source artifact.
  If the user asks to reconsider one, record that user decision and keep its
  origin dataset-derived; it does not become transcript-confirmed. If deferred
  context is missing and materially affects a candidate, ask rather than assume.
- Do not infer stakeholder demand from a column's existence. A category column
  can support a proposed category-volume view; it does not establish root cause.
- Unstated grain, eligible rows, units, time basis, null handling, or business
  definitions remain assumptions or open questions. Data support is conditional
  on those decisions, not proof of data quality or business value.

## Report each candidate separately

Append a `## Dataset-derived recommendations` section after requested mappings.
Use stable `CAND-01`, `CAND-02` identifiers, separate from source KPI IDs.
For each candidate record:

- Origin: `Dataset-derived recommendation`.
- Proposed name and business question, explicitly a proposal.
- Why this might help the stated audience.
- Exact supplying fields and schema evidence.
- Proposed calculation to build, grouping, period, and filters.
- Assumptions, data gaps, and open questions.
- Selection: `Selected for mockup` or `Not selected`, as confirmed by the user.

Use the mapping report's requested-KPI fields for calculation detail, but do
not require a nonexistent transcript question or attribution for a candidate.
The report must say these are schema-supported proposals, with no calculated
results or full-dataset validation. Never modify the source KPI artifacts.

## Confirm the handoff

Show candidate choices together with requested mappings in one final review.
Ask which candidates to include, allowing none. Keep unselected candidates in
the report as not selected. Do not infer selection from interest or silence.

Write this inclusion table after the final review, covering every mapped
requested KPI and every proposed candidate:

| ID | Name | Origin | Include in mockup |
| --- | --- | --- | --- |
| KPI-01 | Source KPI name | Stakeholder-requested | Yes |
| CAND-01 | Proposed measure name | Dataset-derived recommendation | Yes or No, exactly as confirmed |

Requested KPIs in the confirmed mapping scope default to Yes, including their
gap panels, unless the user explicitly excludes them. Each candidate requires
an individual Yes or No. Keep candidate selection text consistent with this
table. If nothing is selected, record that and report no dashboard input rather
than inventing panels. A later selection change requires a revised confirmed
report at a nonconflicting filename, not a silent edit to source facts.

The Markdown report is the handoff for this mode. Do not write optional
version-1 kpi-mapping.yaml for a candidate-mode run; its contract cannot record
origin, selection, or recommendations that were not in the source KPI artifact.
