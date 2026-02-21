# Push to Main

Push changes directly to main branch without PR.

## Instructions

1. Run `git status` to see current changes
2. Run `git diff --staged` and `git diff` to understand what will be committed
3. Stage appropriate files (prefer specific files over `git add -A`)
4. Create a commit with a clear message following repo conventions
5. Push directly to main: `git push origin main`

## Commit Message Format

```
<type>: <short description>

<optional body>

Co-Authored-By: Claude <noreply@anthropic.com>
```

Types: fix, feat, refactor, docs, test, chore

## Safety Checks

Before pushing:
- Verify you're on main branch (`git branch --show-current`)
- Check for uncommitted changes that shouldn't be included
- Don't commit sensitive files (.env, credentials, etc.)

## Arguments

If the user provides a message after `/push-main`, use it as the commit message.
Otherwise, analyze the changes and generate an appropriate message.
