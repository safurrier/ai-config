---
description: Create a well-formatted git commit with conventional commit style
argument-hint: [type] [scope]
---

Create a git commit for the current staged changes.

If $ARGUMENTS includes a type, use that type. Otherwise, infer the type from the changes:
- feat: New feature
- fix: Bug fix
- docs: Documentation only
- style: Code style (formatting, etc.)
- refactor: Code change that neither fixes nor adds
- test: Adding or updating tests
- chore: Maintenance tasks

If a scope is provided as $2, include it in the commit message.

Write a clear, concise commit message following conventional commits format:
`<type>(<scope>): <description>`

The description should:
- Be imperative mood ("add" not "added")
- Not end with a period
- Be under 72 characters
