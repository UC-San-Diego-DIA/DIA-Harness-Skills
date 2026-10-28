---
name: one-transcript-many-artifacts
pattern: fan-out
description: Save one Zoom transcript once, then pull the meeting documents the project needs from it through reviewed DIA skills.
---

# Playbook: One transcript, many artifacts

Work from one saved transcript and produce only the derived documents the meeting actually needs. Every branch runs independently, asks for its own confirmation, and writes its own files, so run the branches the meeting type calls for and skip the rest.

## Shared input

Save the transcript once as `Meeting-Transcript-YYYY-MM-DD-<topic>.txt` in the working directory. Every branch accepts a supplied transcript path, so save it with the first branch you run and pass the same path, or run later branches from the same directory. Do not re-paste or duplicate the transcript.

Choose branches by meeting type, not by completeness:

- Status updates and project reviews: meeting notes only.
- Business-owner requirements conversations: requirements, process map, or both.
- Discovery conversations about what an analysis must answer: KPIs.

## Branches

Each branch is one invocation of one reviewed skill:

- `$dia-transcript-to-meeting-notes` - detailed local meeting notes with decisions, action items, and open questions. No ClickUp writes.
- `$dia-transcript-to-requirements` - a structured requirements document: actors and roles, current-state process, problems, requested capabilities, inputs and outputs, success criteria, constraints, out-of-scope items, and open questions.
- `$dia-transcript-to-process-map` - a process outline the user confirms, then a rendered process-map diagram with current-state timing. Uses the requirements document as its process source when one exists.
- `$dia-transcript-to-kpis` - confirmed business questions and KPIs as a readable Markdown file plus a schema-version-1 `kpi-facts.yaml`.

## Handoffs

- The requirements and process-map branches chain: the process map follows the actors, steps, and handoffs the requirements document records, so run requirements first when both are needed.
- The notes, requirements, and KPI branches do not feed each other; each reads the transcript directly.
- Every branch keeps the same date and topic labels as the transcript, so derived files stay grouped in one working directory.
- Open questions from any branch are the follow-up list for the business owner. Resolve them before scoping work in ClickUp.
