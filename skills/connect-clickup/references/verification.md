# Connection verification

Use this reference only after ClickUp tools load. These checks are read-only. Shared company destination IDs are allowed in the source skill; never add personal task, List, or user IDs.

## Default destination

- Workspace ID: `1275695`
- Default view: the authenticated staff member's Assigned to me tasks

`My Tasks` and `Assigned to me` are personalized ClickUp views, not Spaces or Lists. They have no destination ID. Verify the default connection by:

1. Confirming that Workspace `1275695` is accessible.
2. Running a read-only task query scoped to the authenticated user in that Workspace.

Use a current-user or `me` capability exposed by the server. If the available tools cannot identify the authenticated user without guessing, fail this check. Do not ask for the user's name or email, enumerate members to infer identity, or substitute another assignee.

The assigned-work check passes when the query succeeds, including when it returns no tasks. Report a count only when the tool explicitly provides a total. Do not infer a total from one page of results. Do not report task titles, descriptions, comments, task IDs, assignee details, or personal List IDs.

## Optional Space URLs

Accept one or more URLs shaped like:

```text
https://app.clickup.com/1275695/v/s/<space-id>
```

A URL may have additional path segments after the Space ID. Validate all of the following before calling ClickUp:

1. The scheme is `https`.
2. The host is exactly `app.clickup.com`.
3. The path identifies Workspace `1275695` and contains `/v/s/` followed by a numeric Space ID.

Reject malformed URLs and URLs for another Workspace without opening them. Record each rejection as an optional warning, explain that this company skill supports Workspace `1275695` only, and continue the base connection. Do not change a working MCP connection because of an optional URL.

For every valid URL, use a read-only Workspace hierarchy capability and match the numeric Space ID. Follow pagination until the Space is found or the hierarchy is exhausted. Report the resolved Space name and ID when accessible. A missing or inaccessible optional Space is a warning, not a failure of the base connection.

Supplying a Space URL does not grant access or save a preference. OAuth already exposes the ClickUp locations the staff member can access. The URL only selects a Space for this verification run.

## Pass conditions

The base connection passes only when:

1. Workspace `1275695` is accessible.
2. A read-only Assigned to me query succeeds for the authenticated staff member.
3. Verification performs no ClickUp write.

Evaluate optional Space URLs separately and report a result for each one.
