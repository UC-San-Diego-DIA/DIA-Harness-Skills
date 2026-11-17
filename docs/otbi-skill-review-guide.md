# Review the OTBI conversion skill

Think of the skill as instructions for a translator, with a few small tools. You give it an OTBI report description. The agent finds the real database columns and the right ways to connect their tables. It then writes a SQL query for you to test in BI Publisher.

The agent makes the technical decisions. The Python tools read files, check supported decisions, and assemble SQL. The tools do not search Oracle documentation, discover the intended joins by themselves, or prove that a query works in your Oracle environment.

## What matters most

Check these first:

1. Did it choose the right physical database columns for every requested field?
2. Did it connect the tables using the right keys and INNER/LEFT behavior?
3. Can it explain what one input row and one output row represent, and the keys that identify them?
4. Did it preserve the filters and calculations that affect the data?
5. Did it retain legitimate physical records without hiding a bad join?

For attribute queries, the default is plain SELECT. Two different physical records can look identical after choosing only a few columns. Both records stay. DISTINCT is available when you ask for OTBI's distinct output. Queries containing sums still need their proper grouping; retaining physical attribute rows does not remove required calculations.

Column order, readable names, and ordinary sorting are secondary. They matter when an existing layout expects particular field names, or when ordering determines top-N records, row limits, or a calculation.

## Every maintained file in the package

All paths below refer to the repository's source skill. Installed Harness copies are separate.

| File | Plain-language job | What to check |
| --- | --- | --- |
| [SKILL.md](../skills/dia-otbi-to-bipublisher-sql/SKILL.md) | The main instructions the agent follows. | Priorities, default physical rows, when it asks questions, and when it delivers SQL. |
| [agents/openai.yaml](../skills/dia-otbi-to-bipublisher-sql/agents/openai.yaml) | The skill's name card and starting prompt. | Display name, prompt, and explicit invocation policy. This file does not generate SQL. |
| [references/conversion-contract.md](../skills/dia-otbi-to-bipublisher-sql/references/conversion-contract.md) | The rules for what comes in and what must come out. | Source preservation, mapping coverage, usable SQL, and evidence records. |
| [references/semantic-equivalence.md](../skills/dia-otbi-to-bipublisher-sql/references/semantic-equivalence.md) | Explains how to keep the report's meaning. | Filters, formulas, currencies, nulls, row grain, duplicates, and diagnostic options. |
| [references/join-research.md](../skills/dia-otbi-to-bipublisher-sql/references/join-research.md) | The instructions for connecting tables. | Official documentation, every part of composite keys, relationship roles, optional joins, and row multiplication. |
| [references/reviewed-compilation.md](../skills/dia-otbi-to-bipublisher-sql/references/reviewed-compilation.md) | Explains the instructions the SQL-building tool accepts. | Review-plan fields, row policies, supported formulas, and compiler limits. |
| [references/parameter-and-lov-contract.md](../skills/dia-otbi-to-bipublisher-sql/references/parameter-and-lov-contract.md) | Adds requested filters the user can fill in, including dropdown choices. | Parameter types, multiple selections, and All/null behavior. Optional after the literal query. |
| [references/validation-and-handoff.md](../skills/dia-otbi-to-bipublisher-sql/references/validation-and-handoff.md) | Explains how to test and compare the query. | Compare the declared row policy; align columns by meaning; distinguish physical duplicates from join errors. |
| [scripts/convert_otbi_catalog.py](../skills/dia-otbi-to-bipublisher-sql/scripts/convert_otbi_catalog.py) | Opens the OTBI package and lists its report fields, filters, and formulas. It also supplies shared mapping readers. | Start with its inspection mode. Its optional unfinished SQL scaffolds deliberately return no rows and are not deliverables. |
| [scripts/compile_reviewed_conversion.py](../skills/dia-otbi-to-bipublisher-sql/scripts/compile_reviewed_conversion.py) | Builds SQL from the OTBI report and the agent's reviewed choices. Can also fill a requested BIP model template. | `row_policy`, `reviewed_bindings`, `compile_analysis`, and `run`. They select row behavior, check bindings/joins, build attribute SQL, and save the SQL/evidence. |
| [scripts/aggregate_expressions.py](../skills/dia-otbi-to-bipublisher-sql/scripts/aggregate_expressions.py) | Translates supported calculations, such as conditional sums. | It parses formulas and checks what each part means. It does not choose physical columns or joins. |
| [assets/mapping-workbooks/workbook-index.yaml](../skills/dia-otbi-to-bipublisher-sql/assets/mapping-workbooks/workbook-index.yaml) | The contents list for the bundled Oracle mapping books. | Product family, release, filename, coverage, and file hash. A hash is a fingerprint used to detect changed input. |
| [Financials mapping workbook](<../skills/dia-otbi-to-bipublisher-sql/assets/mapping-workbooks/fin/26b/R13_26B_FIN_OTBI_database_mapping_with ViewObjects.xlsx>) | Oracle's Financials field lookup book. | The OTBI subject-area rows linking presentation fields to physical objects/columns. It is release 26B, not automatically updated. |
| [Project Portfolio Management mapping workbook](<../skills/dia-otbi-to-bipublisher-sql/assets/mapping-workbooks/ppm/26b/R13_26B_PPM_OTBI_database_mapping_with ViewObjects.xlsx>) | Oracle's Projects field lookup book. | Same purpose for Projects subject areas. It is also release 26B. |

The agent reads supporting references when their subject is needed. They are not separate programs that all run on every conversion. Current Oracle table/join documentation is researched during the task; the mapping workbooks do not contain the complete OTBI model or every required join decision.

A `__pycache__` folder or `.pyc` file is a Python-generated cache. It is not a maintained instruction or source file to review, and it is not needed to understand the skill.

## How the pieces work together

1. The user supplies an OTBI catalog and invokes the skill.
2. SKILL.md tells the agent to inspect it with convert_otbi_catalog.py.
3. The agent uses the mapping workbook to select columns and Oracle documentation to establish the joins and grain.
4. The agent writes a review plan. This is a per-conversion JSON file containing decisions and evidence, not another file built into the skill.
5. The compiler checks those supplied choices and builds SQL for supported attributes or calculations. An evidenced query beyond its supported grammar can be written directly by the agent under the same rules.
6. The agent delivers the SQL. The user runs it in BI Publisher and returns results or an exact error for repair.

The review plan is the most useful place to check a particular conversion. It says which columns and joins the agent chose and why. The compiler manifest saves those choices, input fingerprints, output field mappings, effective row policy, and test status. A manifest is a receipt, not proof that the choices are correct.

## What a conversion creates

| Per-conversion file | What it is |
| --- | --- |
| `*.sql` | The query to paste into BI Publisher. |
| `*-review-plan.json` | The agent's selected mappings, joins, grain, row policy, and evidence. |
| `*-manifest.json` | The compiler's record of inputs, choices, output fields, and checks. |
| `*-evidence.md` | A concise record used when the agent writes SQL directly rather than using the compiler. |
| `*.xdm` and `*.xdm.catalog` | Optional model files, created only when requested with a supported template. |

These are user-project outputs. They do not belong inside the skill package or this repository when they contain real user material.

## Where to start checking the implementation

Read SKILL.md first, then join-research.md and the row-handling section of reviewed-compilation.md. If those rules match your intent, inspect `row_policy` and `compile_analysis` in the compiler. Attribute plans default to `physical_rows`; `otbi_distinct` is explicit. Aggregate plans use `aggregate_grain` and preserve their required grouping.

Then look at the tests outside the package:

| Test file | What it checks |
| --- | --- |
| [test_otbi_conversion.py](../scripts/test_otbi_conversion.py) | Reading catalogs, preserving filters/literals, mapping coverage, and keeping incomplete scaffolds blocked. |
| [test_otbi_reviewed_conversion.py](../scripts/test_otbi_reviewed_conversion.py) | Executable attribute SQL, physical duplicate counts by default, optional distinct output, composite keys, optional dimensions, and model packaging. |
| [test_otbi_aggregate_conversion.py](../scripts/test_otbi_aggregate_conversion.py) | Conditional sums, prompts, descriptor keys, nulls, grain restrictions, and the supported total stage. |

These tests use synthetic data. They can catch parser and SQL-building errors; they cannot prove correct Oracle execution, tenant security, or business meaning. The [conversion review](otbi-conversion-review.md) records earlier findings and follow-ups. Earlier references to automatic DISTINCT describe the previous policy; its final physical-row section records the current default.
