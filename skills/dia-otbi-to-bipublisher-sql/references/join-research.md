# Oracle table and join research

## Release and source selection

Discover current product-family documentation through [Oracle Cloud Applications](https://docs.oracle.com/en/cloud/saas/). Search official Oracle documentation if navigation is unavailable. Open the release's book and confirm its label; snippets alone do not establish current evidence. Record release, URL, title, access date, workbook release, and known target Fusion tenant release. Use the newest published documentation for research, and check differences against a known tenant release. Record an unknown tenant release and ask only when a release difference affects construction. Do not assume the tenant runs the newest release or that the 26B bundle is current.

Use Tables and Views for database definitions and the OTBI Subject Areas reference for grain, time dimension, restrictions, and security. Official view SQL or explicit joins can support views with no Foreign Keys section. A missing FK section is a gap, not proof of no relationship. Only official Oracle evidence or supplied tenant-specific metadata can support a relationship; record which was used.

## Research every used object

Verify mapped objects and columns, datatypes, primary/unique keys, nullable keys, and relevant FKs. An FK can appear as incoming on the parent's page or outgoing on the child's. Read the row's Table and Foreign Table labels rather than assuming the page's object is the child.

Record source URLs and concise evidence summaries. For composite keys, identify every child-to-parent pair in order. An FK listing can show only child columns; verify the referenced unique key and correspondence on the parent's page. Do not assume identical names or blindly equate child columns to the parent's primary key. An FK can reference another unique key.

For multiple relationships between two objects, select the business role required by the analysis. An invoice line's invoice, corrected invoice, prepayment invoice, and retained invoice are different roles. Applying every FK would constrain unrelated roles simultaneously. Use aliases when one object plays several roles.

## Build the intended join graph

The agent selects and records the intended relationships from the analysis and documentation; supported technical decisions need no separate analyst approval. List necessary edges; do not force joins for every pair. Each used object must connect through an evidenced path. Add documented intermediate tables and keys when required even if OTBI does not project those keys. Record each addition's purpose and source without changing workbook field lineage.

For each applied edge record:

- Aliases and exact key pairs, including all composite-key columns.
- Business relationship and why this FK role is correct.
- Cardinality, expected grain, and risk of multiplying measures.
- INNER or LEFT join and evidence for preserving or excluding unmatched rows.
- Required tenant, business-unit, ledger, language, lookup-type, set, status, or effective-date restrictions, with sources.
- Documentation release, URL, title, access date, and concise evidence summary.

Use explicit ANSI JOIN syntax in reviewed SQL. Put optional-side restrictions in ON when source semantics preserve unmatched facts. Define the underlying unique fact key, using all components rather than a displayed number alone. Check each join's effect on that key and on the declared result grain. Dimension joins should not multiply fact rows. Distinguish legitimate separate fact records with identical projected values from unwanted copies of one fact record. Pre-aggregate or separate fact sets at their documented grain when needed. DISTINCT cannot repair incorrect joins or duplicated measures, including when the final projection contains attributes only.

## Status and blocking

- RELATIONSHIP_VERIFIED: exact key relationship is documented; this alone does not approve its use.
- APPLIED_REVIEWED: relationship, role, cardinality, join type, scope, and grain are resolved and recorded.
- NOT_USED: a documented alternative is irrelevant; record why.
- UNRESOLVED: missing or contradictory evidence blocks a runnable candidate when the edge is required.
- NOT_REQUIRED: no additional relationship is needed. Semantic review and comparison still apply.

Do not remove a general join warning after verifying one edge. If research fails, save attempted lookups and continue independent work. Required unresolved edges keep the physical scaffold blocked. No Cartesian query should be offered for the analyst to test.
