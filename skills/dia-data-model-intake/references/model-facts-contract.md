# Model-facts emission contract

This contract describes what `$dia-data-model-intake` emits. It is the intake-side complement to the consuming contract in `$dia-data-model-docs`, which reads the artifact. The JSON Schema at `model-facts.schema.json` in this directory is the authoritative structural contract; this file explains intent and derivation.

## Top-level structure

```yaml
schema_version: 2
provenance:
  source_file: <absolute path to the input file>
  source_sha256: <hex SHA-256 of the source file bytes>
  extracted_at: <ISO-8601 UTC timestamp>
  extractor_version: dia-data-model-intake 2.0.0
  container: zlib-archive | xdm | xml
model:
  facet_version: 1
  # ... static facts below
run:
  facet_version: 1
  # ... extraction-run facts below
```

The `model` facet holds static facts about the data model. The `run` facet holds facts about this particular extraction. Each facet has its own `facet_version` so either can evolve independently.

## Stable IDs

- `model_id` is `mdl_` plus 16 hex characters derived from the SHA-256 of the catalog `OriginalPath` (or the lowercased whitespace-collapsed model name as fallback). It is deterministic for the same source path.
- Each dataset has a `ds_` ID derived from `model_id` + dataset name. Each output column has a `col_` ID derived from `model_id` + column name; duplicates get `_2` suffixes.
- Each dataset's `content_hash` is the SHA-256 of its stored `sql` string encoded as UTF-8.

## Coded warnings

Every warning is an object with `code`, `dataset`, `query`, `item_index`, `severity`, and `message`. Severity is `info`, `warning`, or `error`.

| Code | Severity | Meaning |
| --- | --- | --- |
| `AMBIGUOUS_ALIAS_NO_AS` | info | A select item's alias appears after END without AS; the output structure confirms the column name, so the alias is bound. This is a binding confirmation, not a defect. |
| `CTE_PARSE_FALLBACK` | warning | CTE extraction failed; the SQL was treated as one flat query. |
| `DATASET_NO_SQL` | warning | A dataset has no SQL text to analyze. |
| `NO_DATA_SETS` | warning | The model contains no datasets. |
| `NO_TOP_LEVEL_SELECT` | warning | A dataset's SQL has no recognized top-level SELECT. |
| `SELECT_ITEM_NO_ALIAS` | warning | A select item has no derivable alias and no output-structure confirmation. |
| `SOURCE_FILE_UNAVAILABLE` | warning | The migration helper could not read the original source file; the SHA-256 is set to null. |

Only `warning`- and `error`-severity records count toward a dataset's `parsed_with_warnings` status. Info-severity records do not indicate a parse problem.

## Lineage

The `lineage` array contains one edge per output column traced to a source table. Each edge is:

```yaml
- dataset: <dataset name>
  dataset_id: <ds_ ID>
  input_table: <table name>
  query: <CTE name or "main">
  output_column: <column name>
  join_keys: [<list of join condition expressions touching this column>]
```

Edges are derived from select alias expressions and join conditions. They are structural provenance, not business interpretation.

## Output-column enrichment

Each output-column descriptor preserves its declared field order and may carry:

- `nullability`: `not_null` when a CASE expression's ELSE branch contains no NULL token and no nested CASE, or when an XML `nullable`/`nullAllowed` attribute declares it. Omitted when not derivable.
- `parameter_bindings`: an array of `{parameter, via}` objects. `via` is `sql` when a `:NAME` token appears in the dataset SQL, `group_sql` when the column inherits its group-source dataset's bindings, or `element_value` when the column value equals the parameter name.

## Compatibility policy

`schema_version` changes only when the contract breaks:

- Additive optional fields do not bump `schema_version`. Consumers must tolerate unknown or extra fields and must not stop on them.
- Renames, removals, or semantic changes to existing fields require a `schema_version` bump.
- `facet_version` allows per-facet evolution: the `model` and `run` facets can evolve independently through their own `facet_version` values without a top-level `schema_version` bump.

The extractor emits only schema version 2. An existing schema-version-1 file is migrated exclusively by `scripts\migrate_model_facts_v1_to_v2.py`, which reads the v1 YAML, re-runs the SQL analysis against the recorded SQL text, and writes a new v2 file with the original source file's provenance when the file is readable and a `SOURCE_FILE_UNAVAILABLE` warning when it is not.
