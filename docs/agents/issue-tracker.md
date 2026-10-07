# Issue tracker

Issues and specs live in GitHub Issues for
`moedesux/tic-tac-toe-jev`. Use the `gh` CLI from this clone.

## Operations

- Create: `gh issue create --title "..." --body-file <file>`.
- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open --json number,title,body,labels`.
- Comment: `gh issue comment <number> --body-file <file>`.
- Apply labels: `gh issue edit <number> --add-label "<label>"`.
- Remove labels: `gh issue edit <number> --remove-label "<label>"`.
- Close: `gh issue close <number> --comment "..."`.

Use temporary files for multiline issue bodies and comments.

When a skill says "publish to the issue tracker", create a GitHub issue.
When it says "fetch the relevant ticket", read the GitHub issue.

## Related issues

Use native GitHub sub-issues and dependencies when available.
Otherwise record `Part of #<parent>` and `Blocked by: #<number>`
in the issue body. A ticket is unblocked when every blocker is closed.

## Pull requests

PRs as a request surface: no.
