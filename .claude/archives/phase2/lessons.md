# Lessons Learned

ALL AGENTS: Read this file at session start before writing any code.
After ANY correction, failed attempt, or discovery, add a lesson here.

## Format
### [Agent] Short description
- What happened: What went wrong or was discovered
- Root cause: Why it happened
- Rule: The rule to follow going forward

## Lessons

### [Claude-3] SQLite ORDER BY with datetime('now') needs tiebreaker
- What happened: Two projects created in same second had identical created_at, making ORDER BY created_at DESC non-deterministic
- Root cause: SQLite datetime('now') has 1-second resolution. Fast sequential inserts get same timestamp.
- Rule: Always add `id DESC` as tiebreaker when ordering by timestamps: `ORDER BY created_at DESC, id DESC`

### [Claude-3] HTTP clients normalize path traversal out of URLs
- What happened: Test for `../../etc/passwd` path traversal got 404 instead of 403 because httpx normalized `..` segments before sending the request
- Root cause: httpx/HTTP clients resolve relative path components (`..`) during URL construction. `GET /api/files/../../etc/passwd` becomes `GET /etc/passwd` which doesn't match any route.
- Rule: Don't test path traversal with `..` via HTTP client tests. The allowlist approach (checking path against a set of known-good paths) is the correct security mechanism. Test it with realistic non-allowlisted paths instead.

### [Claude-4] Always bind local-only servers to 127.0.0.1, not 0.0.0.0
- What happened: run.py bound to `0.0.0.0` which exposes the API to the entire local network
- Root cause: Default uvicorn examples often use `0.0.0.0` for convenience
- Rule: For local-only tools, always use `host="127.0.0.1"`. Only use `0.0.0.0` when network access is intentional.

### [Claude-4] Use HTTPException consistently - never return error dicts with 200 status
- What happened: `/api/watch/{project_id}` and `/api/unwatch/{project_id}` returned `{"error": "Project not found"}` with HTTP 200 instead of raising HTTPException(404)
- Root cause: Inconsistent error handling patterns across inline endpoints vs router endpoints
- Rule: Always use `raise HTTPException(status_code=..., detail=...)` for errors. Never return plain dicts with error messages - clients can't distinguish success from failure by status code.

### [Claude-4] Build command-line args conditionally, don't use insert(index)
- What happened: `args.insert(4, "-Resume")` in swarm launch used a hardcoded index that would silently break if the args list structure changed
- Root cause: Fragile code that depends on positional assumptions about list contents
- Rule: Build command args by conditional appending, not index insertion. Use `if condition: args.append(flag)` then add remaining args after.

### [Claude-4] pytest-asyncio >= 0.21 deprecates session-scoped event_loop fixture
- What happened: conftest.py had a custom `event_loop` fixture with `scope="session"` that's deprecated in modern pytest-asyncio
- Root cause: Copy-pasted pattern from older tutorials
- Rule: Let pytest-asyncio manage the event loop. Remove custom `event_loop` fixtures unless you need cross-test state sharing (and even then use `loop_scope` config instead).

### [Claude-4] Match frontend property names to actual API response schema
- What happened: SignalPanel.jsx used `phase.current` and `phase.max` but the backend returns `Phase` and `MaxPhases` (from swarm-phase.json). Phase indicator rendered empty.
- Root cause: Frontend was coded against an assumed schema rather than the actual API response
- Rule: Always verify the actual API response shape before coding the frontend component. When wrapping external files (like swarm-phase.json), document the exact schema in a shared location.

### [Claude-4] Add ARIA attributes to visual-only indicators
- What happened: Progress bar, status dots, and signal indicators relied on color alone with no ARIA roles
- Root cause: Accessibility isn't visible in development; easy to skip
- Rule: For any visual indicator (progress bars, status dots, badges), add `role`, `aria-valuenow`, and `aria-label`. Screen readers need text equivalents of visual states.

### [Claude-3] PowerShell writes UTF-8 BOM to heartbeat files, breaking JS Date parsing
- What happened: Heartbeat timestamps contained BOM marker (`\ufeff`) which made `new Date()` return Invalid Date on the frontend, showing all agents as "Stale"
- Root cause: PowerShell's default file encoding adds a UTF-8 BOM. Python's `read_text()` preserves it, and `strip()` doesn't remove BOM.
- Rule: Always use `encoding="utf-8-sig"` when reading files that may have been written by PowerShell or other Windows tools. The `utf-8-sig` codec automatically strips the BOM.

### [Claude-3] Module-level rate limiter state leaks across test runs
- What happened: File write tests got 429 errors because the rate limiter dict persisted from earlier tests
- Root cause: The `_last_write` dict lives at module scope and isn't reset between test classes
- Rule: When adding module-level state (caches, rate limiters), always add a `clear()` call in the test fixtures/conftest to reset it between tests.

### [Claude-4] Clear WebSocket reconnection timers before setting new ones
- What happened: useWebSocket.js `onclose` handler set a new `setTimeout` without clearing the previous one, causing timer accumulation on rapid disconnect/reconnect
- Root cause: Only `onopen` and the cleanup function cleared `reconnectTimer.current`, not `onclose`
- Rule: Any time you set a timer on a ref, clear the existing one first: `if (ref.current) clearTimeout(ref.current)` before `ref.current = setTimeout(...)`

### [Claude-4] Swarm relaunches with stale task lists cause agent loops
- What happened: Swarm agents launched but stuck in "Starting iteration 1" loops because signals directory was empty and TASKS.md was already complete from prior session
- Root cause: Swarm relaunch cleared signals but didn't reset TASKS.md or check if work was already done
- Rule: Swarm launcher should check if tasks are already marked complete before starting agents. Include a staleness check or task reset mechanism.
