---
name: meeting-notes-to-tasks
description: Turn one meeting transcript into published Project Hub notes and approved DIA ClickUp tasks using reviewed DIA skills.
---

# Playbook: Meeting notes to ClickUp tasks

Move one readable transcript from raw capture through published meeting notes and approved ClickUp tasks. Run this for a project that already exists in ClickUp; the playbook never creates ClickUp resources itself.

## Sequence

1. `$dia-clickup-mcp-setup` - one-time setup. Connects TritonAI Harness to ClickUp through official OAuth and verifies access. Skip when the connection is already verified.
2. `$dia-setup-project-folder` - one-time setup per project. Creates or validates the local schema-1 project folder connected to the existing ClickUp Folder, task List, and Project Hub. Skip when the folder already validates.
3. `$dia-process-meeting-transcript` - one run per meeting. Drafts the Project Hub meeting note, extracts DIA-owned action items, and creates only the tasks the user approves.

Variant: when the meeting needs notes but no tasks, run `$dia-transcript-to-meeting-notes` in place of step 3. It writes a detailed meeting-note Markdown file locally and touches no ClickUp content.

## Handoffs

- Step 2 stores the stable ClickUp IDs that step 3 reads from `project.yaml`.
- Step 3 writes the published note into the Project Hub and links it from every task description, so tasks always point back to the meeting record.
- Step 3 moves the transcript from `transcripts\inbox` to `transcripts\processed` only after every note and task item is resolved.
