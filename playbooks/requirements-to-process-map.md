---
name: requirements-to-process-map
pattern: pipeline
description: Turn one business-owner requirements Zoom transcript into a structured requirements document and a rendered process map using reviewed DIA skills.
---

# Playbook: Requirements to process map

Move one business-owner requirements conversation from raw transcript to a structured requirements document and a process-map diagram. Run this at the start of a project, before any work is scoped in ClickUp.

## Sequence

1. `$dia-transcript-to-requirements` - one run per conversation. Saves the transcript locally and produces the requirements document: the decision it supports, audience and decision context, key questions, data requirements, functional requirements, acceptance criteria, constraints, out-of-scope items, and open questions, with meeting capture in an appendix.
2. `$dia-transcript-to-process-map` - one run per conversation. Inventories possible processes from the same transcript, asks the user which ones to analyze, then writes a process outline with a current-state ROI baseline for each confirmed process and waits for confirmation before rendering its process map. When the requirements document from step 1 exists, the outline uses it as its process source instead of re-reading the transcript.

Variant: when the requirements document is enough and no diagram is needed, run only step 1.

## Handoffs

- Step 1 writes `Requirements-YYYY-MM-DD-<topic>.md`; step 2's map follows the actors, steps, and handoffs that document records, so the diagram stays consistent with the reviewed requirements.
- Both steps work on the same saved transcript, so both artifacts share the date and topic labels.
- The requirements document's open questions are the follow-up list for the business owner; resolve them before scoping work in ClickUp.
