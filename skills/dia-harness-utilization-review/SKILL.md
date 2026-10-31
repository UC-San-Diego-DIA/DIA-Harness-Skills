---
name: dia-harness-utilization-review
description: Review the previous day's TritonAI Harness threads and conversations and produce 2 to 4 ways to improve the user's existing interactions plus 1 to 3 new ways to use the Harness, recording confirmed recommendations in a local review log. Designed for a scheduled morning run and explicit invocation as $dia-harness-utilization-review. Do not use for task work, skill installation, or changes to other systems.
metadata:
  status: development
---

# Harness utilization review

Review the threads and conversations from the previous day the way a thoughtful colleague would: identify what went well, what created friction, and what the user has not tried yet. Deliver a small set of concrete recommendations, get the user's verdict on each, and record the outcome in a review log so future reviews measure progression instead of repeating the same advice.

This skill is designed to run from a scheduled Harness task at about 09:00 `America/Los_Angeles` with one new thread per run. It also works when invoked explicitly during a session.

## Boundaries

- Evidence comes from the previous day's Harness activity only: TritonAI thread tools and the local Harness session files named below. Do not query ClickUp, Outlook, GitHub, or any other external system.
- Read-only everywhere except the review log. Never modify, send to, rename, or interrupt any thread. Never modify session files.
- The only file this skill writes is the review log defined below. Never modify skills, project documents, datasets, or other outputs while running this review.
- Session content and thread content are private. Record behavioral summaries, not quotes. Never record credentials, personal identifiers, task IDs, file contents, or anything sensitive in the log.
- Do not install, update, or recommend installing a specific skill unless the user asks for that as follow-up work after the review.
- In interactive mode, every recommendation needs an explicit verdict before it is recorded. In scheduled mode, record recommendations as `Pending` and follow the validation section.

## Required capabilities

Resolve what is available before gathering evidence, and never install anything to fill a gap:

1. **TritonAI thread tools** (`t3_thread_list`, `t3_thread_read`). These are the preferred source when loaded.
2. **Local session files.** Harness runs are stored as `rollout-YYYY-MM-DDThh-mm-ss-<uuid>.jsonl` under a `sessions\YYYY\MM\DD` tree. Each file opens with a `session_meta` record holding the start timestamp, working directory, and originator, followed by `event_msg` and `response_item` records.
3. **Shell access** for listing and parsing session files when the thread tools are not available or do not cover the window.

Resolve the session root without hard-coding a username:

1. Use `CODEX_HOME\sessions` when `CODEX_HOME` is defined.
2. Otherwise check `%USERPROFILE%\.tritonai-harness\codex\sessions`.
3. Otherwise check `%USERPROFILE%\.tritonai-harness-nightly\codex\sessions`.

If both the stable and nightly roots exist, use the one matching the running install first, and include the other only if its files fall inside the review window. If no session root exists and thread tools are unavailable, report that no review is possible and stop without writing the log.

## Determine the review window

Use `America/Los_Angeles` for every date and time calculation, file filter, displayed timestamp, and log timestamp. This timezone observes Pacific Standard Time and Pacific Daylight Time as applicable.

The default window is the previous calendar day, 00:00 through 23:59. When invoked interactively, confirm the window with the user before gathering evidence; the user may ask for today so far or another day. A scheduled run uses the default window without asking.

## Gather prior-day evidence

Gather in this priority order and deduplicate by time and subject, since one thread may appear in both sources.

### From thread tools

Use `t3_thread_list` without a project filter when the user has not named projects, otherwise once per named project. Page newest-first until returned threads predate the window or the cursor is exhausted; cap the enumeration at 100 threads. For each thread with activity in the window, use `t3_thread_read` with the messages view, capped at 100 items, to capture what the user asked for and how the interaction went. Cap detailed reads at 25 threads; for the rest, record only the title, status, and rough activity time.

If the thread tools are not loaded, continue with the session files and note the gap.

### From session files

For the window's `YYYY\MM\DD` folder under the resolved session root, select files whose name starts with `rollout-` and whose date matches the window. Also include files from earlier days whose last-write time falls inside the window, since a session can continue past midnight. Cap selection at 40 files per day; if more exist, prioritize the largest by last-write time and note the shortfall.

For each selected file, read the `session_meta` record and the user messages only. Skip assistant output, tool output, and file contents. Extract for the log analysis: start time, end time from the last record, working directory, number of user turns, and behavioral signals such as repeated clarifications, retyped instructions, corrections, or manual work the Harness could have absorbed.

If a file cannot be parsed or is locked, skip it, note it, and continue.

## Analyze the day

Summarize across the window:

- What the user accomplished and where the day's effort went.
- Friction: repeated clarifications, rework, corrections, and manual steps the Harness could have absorbed.
- Underused capabilities that fit the user's actual work, such as scheduled tasks, worktrees, delegated reviews, memory, integrations that are loaded but never invoked, or an installed DIA skill that matched a need solved by hand.
- Patterns that went well, so they can be reinforced.

Do not invent friction to fill space. A quiet day may yield only two improvements and one idea, or none for a category.

## Draft recommendations

Produce exactly two sections, each recommendation numbered within its section:

1. **Ways to improve existing interactions.** Two to four recommendations about how the user already works with the Harness, each tied to concrete prior-day activity.
2. **New ideas for using the Harness.** One to three ideas for capabilities or workflows the user has not used, each connected to a need observed in the window.

For each recommendation give one to two sentences: what to do differently and the expected benefit. Name specific capabilities or skills when relevant.

## Read the prior log

The review log path is resolved in the next section. If it does not exist, this is the first review and skip this section.

Read the most recent entries and extract which recommendations were accepted, declined, or left pending; which accepted ones were acted on; and which recommendation kinds repeat. Use this to avoid repeating declined advice, to skip already-acted recommendations, and to shift the mix when one kind has been offered repeatedly. Name progression in one sentence when prior entries show movement. Never edit, reorder, or delete earlier entries.

## Write the review log

Resolve the log path in this order:

1. `harness-utilization-reviews.md` at the root of the active workspace, when the run has a bound workspace.
2. Otherwise `%USERPROFILE%\harness-utilization-review\harness-utilization-reviews.md`, creating the folder when needed.

Each person's log stays on their own computer. If the log does not exist, create it with this header, then append the entry:

```markdown
# Harness utilization reviews

Append-only log produced by $dia-harness-utilization-review. One entry per review. Never edit or delete earlier entries.
```

Append one entry per review in this structure:

```markdown
## Review YYYY-MM-DD HH:MM

### Coverage

One to three sentences naming the window, the threads and sessions reviewed, and any gaps such as unavailable thread tools or skipped files.

### Session summary

Two to four sentences on what the window accomplished and how the interaction went.

### Evidence themes

Three to six short bullets naming the observed friction, strengths, and underused capabilities.

### Recommendations

| # | Kind | Recommendation | Verdict |
| --- | --- | --- | --- |
| I1 | improvement | One-line summary of the recommendation. | Accepted |
| N1 | new idea | One-line summary of the recommendation. | Pending |

### Progression notes

One to three sentences comparing this review with the prior entry, or stating that this is the first review. Name what improved, what repeated, and what kind of recommendation should come next.
```

Use the current date and time in `America/Los_Angeles`. Number improvements `I1`, `I2`, and new ideas `N1`, `N2`, and keep every cell to one line. If the write fails, report the attempted path and error, deliver the recommendations in conversation, and do not claim the log was updated.

## Validate with the user

In interactive mode, present both sections and ask for a verdict on each numbered recommendation:

- **Accepted** - the user wants to try it.
- **Declined** - the user is not interested; record a one-line reason when given.
- **Edited** - record the user's revised wording as the recommendation.

Apply requested edits, confirm the final list once, then write the entry with final verdicts. If the user declines everything, record the review with declined verdicts so future reviews know the kinds were considered.

In scheduled mode, the run is unattended. Write the entry immediately with every verdict set to `Pending`, then end the thread response with the two recommendation sections and one instruction: reply to this thread with accept, decline, or an edit for each numbered recommendation. When the user replies with verdicts, append a short `## Verdict update YYYY-MM-DD HH:MM` section to the same log that names the review it finalizes and records the final verdict table. Never rewrite the original entry.

## Close the review

End the response with three parts, kept to 150 words or fewer:

1. One sentence on the strongest pattern observed in the window.
2. The log path after a successful write, or the reason no entry was recorded.
3. In interactive mode, the open verdicts awaiting the user. In scheduled mode, the reminder to reply to this thread with verdicts.
