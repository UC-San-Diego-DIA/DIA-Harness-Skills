# BI Publisher parameters and lists of values

Prove the literal baseline before broadening behavior with parameters. Parameterization is optional convenience, not evidence of equivalence.

Use `column = :P_VALUE` for one value and `column IN (:P_VALUES)` for a BI Publisher multiple-selection menu. Preserve NOT IN. Enable Multiple Selection in the parameter configuration. A comma-separated string is not a list of bind values. Do not generate ampersand lexicals for ordinary multi-select menus; lexicals require a different PL/SQL package and trigger setup.

Record name, source predicate, original typed value or list, required/optional status, and menu settings. Preserve strings such as 0012 as text. Derive types from source types and confirmed database metadata, not a string's appearance. Separate lower and upper bounds need distinct names. Preserve date/time boundaries and timezones. Do not replace an exclusive next-day bound with an inclusive end-day bound.

For runtime presentation variables, ask for effective value, datatype, multiplicity, and behavior when unset. Defaults such as noData do not establish a report's intended run. Do not leave presentation variables in Oracle SQL. Distinguish fixed classification lists inside formulas from user prompts; do not turn each classification list into a dashboard parameter.

Create SQL Query LOVs in the data model editor's List of Values section and associate them with parameters. A one-column LOV can return PARAMETER_VALUE; use separate display and return values when users see a label but the filter expects an ID. Return the predicate's datatype. Apply reviewed report access scope, language, and lookup restrictions to LOV queries too. A raw table-wide DISTINCT query is only a blocked scaffold.

For the first test, require parameters, initialize them to original values, and disable Select All unless the source used it. If Select All or null selection is requested, record whether it passes NULL or all values and implement that behavior. Validate single value, multiple values, no selection, and Select All where enabled. Do not infer null-safe behavior for NOT IN.

Paste physical Oracle SQL into a SQL Query data set of type Standard SQL on the analyst's Fusion database source, often ApplicationDB_FSCM. Logical SQL belongs on an Oracle BI Server source. Check the source name in the tenant; the example is not a guaranteed connection name.

Oracle references to recheck for the target environment:

- [Create Datasets Using SQL Queries](https://docs.oracle.com/en/middleware/bi/analytics-server/design-publish/create-datasets-using-sql-queries.html), bind variables, lexicals, and Oracle BI Server queries.
- [Performance Best Practices](https://docs.oracle.com/middleware/bi12214/bip/BIPDM/GUID-478A2B1D-BC89-421E-9702-5749BA49EFD2.htm), multi-value parameters and LOV limits.
