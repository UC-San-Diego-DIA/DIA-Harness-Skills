# DIA business-insights project folder, schema 1

Use this reference when planning, creating, or validating a local project folder.

## Terms

- A **local project folder** is the top-level directory for one DIA project. Its name exactly matches the connected ClickUp Folder name.
- A **project manifest** is the root `project.yaml` file containing stable ClickUp IDs and the supported project type.
- A **deliverable** is a stakeholder-facing project outcome.
- A **data product** is a reusable analytical deliverable, such as a Tableau dashboard.

## Required structure

```text
<ClickUp Folder name>/
|-- AGENTS.md
|-- README.md
|-- project.yaml
|-- transcripts/
|   |-- inbox/
|   `-- processed/
|-- source-data/
|-- analysis/
|-- deliverables/
|   |-- data-products/
|   `-- presentations/
`-- working/
```

Folder responsibilities are fixed in schema 1:

- `transcripts/inbox` receives unprocessed meeting transcripts.
- `transcripts/processed` holds transcripts after their workflow finishes.
- `source-data` holds project data as received. Do not assume it is safe to commit or share.
- `analysis` holds analytical workspaces. The `$analyze-csv-with-duckdb` skill may create `analysis/<workspace-name>` beneath it.
- `deliverables/data-products` holds durable local files for analytical products such as Tableau dashboards.
- `deliverables/presentations` holds stakeholder presentation files.
- `working` holds drafts and temporary project work.

Add another deliverable subtype only when the project produces one. Do not create empty categories for hypothetical outputs.

## Project manifest

The helper writes this exact shape. IDs are quoted because they are identifiers, not quantities.

```yaml
# DIA project manifest schema 1
schema_version: 1

project:
  name: "<ClickUp Folder name>"
  type: "business-insights"

clickup:
  workspace_id: "<Workspace ID>"
  space_id: "<Space ID>"
  folder_id: "<project Folder ID>"
  task_list_id: "<task List ID>"
  project_hub:
    doc_id: "<Project Hub document ID>"
    page_id: "<Project Hub page ID>"
```

The manifest does not repeat local paths. Skills use the fixed schema-1 paths. It also does not contain credentials, tokens, task content, personal IDs, or copied ClickUp documents.

## Invariants

- The local folder name equals `project.name` and the current ClickUp Folder name.
- The ClickUp IDs resolve to one hierarchy and remain the machine connection even if display names change.
- The task List belongs to the project Folder.
- The Project Hub document and page are the approved location for project documents.
- A setup run never overwrites, moves, renames, or deletes existing local content.
