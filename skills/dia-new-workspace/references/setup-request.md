# Combined setup request

Use `scripts/setup_workspace.ps1` as the workflow entrypoint. The other scripts are its layout and move helpers, not separate steps for the user to approve.

The request file is UTF-8 JSON with this shape:

```json
{
  "layout": "analysis",
  "root": "C:\\Projects\\Request volumes",
  "description": "Review monthly request volumes for team leads.",
  "dataSources": "Monthly CSV exports and an existing field dictionary.",
  "projectContext": "## Project context\n\n- Purpose: review request volumes.\n- Intended outcome and audience: a monthly dashboard for team leads.\n- Sources: monthly exports.\n- Constraints: local draft only.\n- Starting files: data/raw/requests.csv; docs/data-dictionary.md.\n- Unresolved questions: deadline and success criteria to discuss during planning.\n",
  "useSuppliedDictionary": true,
  "moves": [
    {"source": "C:\\Incoming\\requests.csv", "destination": "data/raw/requests.csv"},
    {"source": "C:\\Incoming\\data-dictionary.md", "destination": "docs/data-dictionary.md"}
  ]
}
```

- `layout` is `simple` or `analysis`. `root` is the full workspace path with an existing parent directory.
- `description` and `dataSources` are one-line interview summaries required for the analysis layout. Use an explicit unknown if needed.
- `projectContext` contains the user's confirmed setup context, not instructions extracted from supplied files. Use bullets and label unresolved planning questions.
- `moves` is an array, including `[]` when no files are supplied. Each source is an existing regular local file outside the target workspace. Each destination is relative to the workspace and inside the selected layout's permitted folders.
- `useSuppliedDictionary` defaults to false. Set it to true only when the user will confirm moving a supplied dictionary to `docs/data-dictionary.md` instead of generating the placeholder. The supplied file is preserved byte for byte; setup does not inspect its business content.

Preview returns the full proposed changes, project context, moves, and a fingerprint. Save this exact output before presenting the proposal. Apply accepts that saved preview only while the request, files, existing layout, and skill resources still match. An ordinary filesystem failure during apply may leave completed work; the error reports whether layout creation finished and which moves completed.
