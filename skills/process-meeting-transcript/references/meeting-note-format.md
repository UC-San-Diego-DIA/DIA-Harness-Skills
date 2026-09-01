# Meeting-note format and extraction rules

Read this reference whenever drafting notes or tasks from a transcript.

## Evidence rules

Write a faithful synthesis, not a cleaned-up version of what participants might have meant.

- Record a fact only when the transcript presents it as a fact. Label estimates, assumptions, and uncertainty.
- Treat an explicitly hypothetical or made-up example as an example, never as a factual claim, decision, or task.
- Record a decision only when participants clearly settle a question or choose a direction. A suggestion, preference, brief acknowledgment, or lack of objection is not enough.
- Record an action item when a named person accepts concrete future work or the group explicitly assigns it and the person accepts. Do not turn vague offers, brainstorming, "we should" statements, or unaccepted requests into commitments.
- Do not label completed work as an action item. Treat work scheduled before the meeting as context unless the meeting adds a new commitment or follow-through.
- When ownership, timing, or the intended outcome remains unsettled, put the issue under `Open items` instead of guessing.
- Keep materially different viewpoints and stated concerns. Do not manufacture consensus.
- Paraphrase. Use a short quotation only when the exact wording changes the meaning.

For long transcripts, build the evidence ledger in chronological sections. Reconcile the ledger before drafting so later discussion does not displace earlier topics or commitments.

## Meeting note

Use this structure. Omit the `Decisions` column when the meeting contains no decisions. Omit the entire `Action items` or `Open items` section when it would be empty. Do not add filler rows.

```markdown
# <YYYY-MM-DD> - <Meeting title>

**Participants:** <unique speaker labels in order of first appearance>

**Source:** <transcript filename>

## Summary

<A short account of the meeting's purpose, main conclusions, and material uncertainty.>

## Discussion

| Topic | Discussion details | Decisions |
| --- | --- | --- |
| <topic> | <main points, rationale, differing views, and caveats> | <decision or "No decision recorded"> |

## Action items

### <Owner name>

| Action item | Due date |
| --- | --- |
| <specific future outcome or next step> | <date or "Not stated"> |

## Open items

| Open item | Owner or decision-maker | What remains unresolved |
| --- | --- | --- |
| <question, decision, or ownership gap> | <name or "Unassigned"> | <missing information or next decision> |
```

Keep the summary short enough to scan. The discussion table should retain enough detail for someone who missed the meeting to understand the rationale, differing views, assumptions, and decisions. Remove small talk, verbal repetition, and transcript noise. Use as many discussion rows and owner sections as the meeting needs. Sort action-item sections by first appearance in the transcript, not alphabetically.

Preserve complete transcript speaker labels in `Participants`. Remove parenthetical pronoun labels from action-item headings so the owner name can match ClickUp.

Escape Markdown table separators and line breaks in cell text so the ClickUp table remains intact. Do not include the absolute local transcript path, raw transcript text, internal extraction labels, or ClickUp eligibility notes in the published meeting note.

## Task candidates

Use meeting-note action items as the only source for task candidates. Do not create a task from a discussion row or open item unless the user first confirms the missing commitment and owner.

For each candidate, retain a compact evidence note for the preview. Identify the speaker and the relevant timestamp or passage without copying a long excerpt. Never place this audit note in the ClickUp task.

Use a separate task for each distinct outcome. Use the target List's default status. Do not infer priority or other task metadata. A task description contains the outcome, relevant context, meeting title and date, meeting-note link, and an explicitly supported due date when one exists.

People without a unique active ClickUp member match still receive their own action-item section in the meeting note. Mark them as notes-only in the preview, not in the published note.
