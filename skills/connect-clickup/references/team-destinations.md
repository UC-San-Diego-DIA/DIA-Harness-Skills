# Team destinations

Use this reference only for post-login verification. These IDs identify shared team locations and contain no credentials.

## Workspace

- ID: `1275695`

The authenticated staff member must have access to this Workspace.

## DIA Space

- Name: `Data, Insights, Analytics (DIA)`
- ID: `90146841564`
- Link: `https://app.clickup.com/1275695/v/s/90146841564/90146841564`

Confirm the Space through a read-only workspace hierarchy call. Match the ID first because names can change.

## My Tasks

`My Tasks` is the authenticated staff member's view of assigned work across the Workspace. It is not a ClickUp List and does not have a shared destination ID.

Run a read-only assigned-work query for the authenticated staff member. The query passes when the tool completes successfully, including when it returns no assigned work. Do not save or commit task titles, task IDs, personal List IDs, or user IDs.

## Verification result

Connection verification passes only when:

1. Workspace `1275695` is accessible.
2. Space `90146841564` is present in its hierarchy.
3. A read-only assigned-work query succeeds for the authenticated staff member.
4. Verification performs no ClickUp write.
