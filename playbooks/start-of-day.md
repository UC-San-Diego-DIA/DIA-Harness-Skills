---
name: start-of-day
description: Verify ClickUp access and run the daily brief from ClickUp, Outlook calendar, and Outlook mail using reviewed DIA skills.
---

# Playbook: Start of day

Give a staff member a defensible daily focus in one morning ritual. This playbook changes nothing in ClickUp or Outlook until the user approves specific proposed actions.

## Sequence

1. `$dia-clickup-mcp-setup` - one-time setup. Connects TritonAI Harness to ClickUp through official OAuth and verifies access. Skip when the connection is already verified.
2. `$dia-start-my-day` - one run each morning. Reads assigned and blocked ClickUp work plus Outlook calendar and mail, ranks one to three priorities, writes a local HTML brief, and proposes only user-approved follow-up actions.

## Handoffs

- Step 1 must report a connected Workspace before step 2 can read ClickUp evidence; if ClickUp tools are missing, step 2 continues with Outlook-only evidence and names the gap.
- The Microsoft 365 plugin must be enabled for Outlook calendar and mail; step 2 reports any missing source under `Source gaps` rather than guessing.
