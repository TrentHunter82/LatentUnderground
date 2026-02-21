# Agent Protocol

Inter-agent coordination rules. Read once at session start.

## Status Updates

Write to `AGENT_STATUS.md`:
```
[Claude-N] STATUS: working|blocked|deferred|done
WORKING_ON: <task>
BLOCKED_BY: Claude-X/<task>
```

Update when: session starts, blocked, deferring, or done.

## File Locking

Before editing shared/high-conflict files:
1. Check AGENT_STATUS.md for `LOCKING: <file>` markers
2. If locked, log your intended change under `## Pending Edits` and wait
3. When taking a lock: `[Claude-N] LOCKING: <file>`
4. When done: `[Claude-N] UNLOCKED: <file> — changes: <summary>`

## Inter-Agent Communication

**Format:** `[Claude-X → Claude-Y] TYPE: message`

Types:
- `READY` — feature complete, here's the signature
- `NEEDS` — I need this action/API from you
- `BLOCKED` — waiting on your output
- `DEFERRED` — postponed, here's why

**When to communicate:**
- API signature changes → notify test agent
- Need action that doesn't exist → notify backend agent
- Bug in another agent's code → notify them before fixing
- Feature deferred → notify dependent agents to stub tests

## Message Bus

```powershell
.swarm/bus/swarm-msg.ps1 inbox              # Check messages
.swarm/bus/swarm-msg.ps1 send --to Claude-2 --body "API ready"
.swarm/bus/swarm-msg.ps1 send --to all --priority high --body "STOP"
```

## Defer Triggers

MUST defer and communicate when:
- Test needs feature not yet implemented → stub with `it.todo()`
- UI needs non-existent store action → add `// TODO` comment
- Fix requires editing locked file → log fix, don't edit
- Changing shared type → notify all agents first
