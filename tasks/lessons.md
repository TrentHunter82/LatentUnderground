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

### [Claude-3] vi.useFakeTimers() blocks waitFor() in tests with async state updates
- What happened: TerminalOutput tests using `vi.useFakeTimers()` hung forever on `await waitFor(...)` because fake timers prevent the microtask queue from flushing naturally
- Root cause: `waitFor` polls every 50ms using real timers. When fake timers are active, these polling intervals never fire, creating a deadlock
- Rule: When testing components that use intervals/timers AND also need async state updates, use `await act(async () => { await vi.advanceTimersByTimeAsync(100) })` instead of `waitFor` to flush pending state updates

### [Claude-3] SSE streaming endpoints can't be tested with httpx ASGI transport
- What happened: httpx AsyncClient with ASGITransport hangs forever on SSE endpoints because the ASGI transport waits for the response body to complete, but SSE endpoints stream indefinitely
- Root cause: ASGI transport doesn't support true streaming disconnect - it buffers the full response
- Rule: Test SSE endpoints by: (1) testing the 404 case normally, (2) testing the generator logic directly as a unit test, (3) using `asyncio.wait_for` with a short timeout to verify the endpoint exists and starts streaming

### [Claude-4] Swarm relaunches with stale task lists cause agent loops
- What happened: Swarm agents launched but stuck in "Starting iteration 1" loops because signals directory was empty and TASKS.md was already complete from prior session
- Root cause: Swarm relaunch cleared signals but didn't reset TASKS.md or check if work was already done
- Rule: Swarm launcher should check if tasks are already marked complete before starting agents. Include a staleness check or task reset mechanism.

### [Claude-4] Always validate Pydantic model fields that become subprocess arguments
- What happened: ProjectConfig had no bounds on agent_count/max_phases. A user could set agent_count=999999, which gets passed directly to PowerShell as `-AgentCount 999999`
- Root cause: Pydantic `Optional[int]` accepts any integer without constraints
- Rule: Any model field that becomes a subprocess argument or resource allocation must have `Field(ge=..., le=...)` bounds. Add `max_length` to string fields that get stored in DB.

### [Claude-4] Pass initialConfig to settings components when loading from database
- What happened: ProjectSettings always showed defaults (4 agents, 3 phases) because ProjectView didn't fetch the project's stored config and pass it as initialConfig
- Root cause: Component was coded with an `initialConfig` prop but the parent never provided it
- Rule: When integrating a component that supports pre-population props, trace the data path end-to-end: DB -> API -> parent component -> child prop. Verify with: does the saved value round-trip?

### [Claude-1] asyncio.create_subprocess_exec fails on Windows under uvicorn's reloader
- What happened: POST /api/swarm/launch returned 500 Internal Server Error with `NotImplementedError` from `_make_subprocess_transport`
- Root cause: uvicorn's WatchFiles reloader on Windows runs the child server process with `SelectorEventLoop`, which does NOT support `asyncio.create_subprocess_exec`. Only `ProactorEventLoop` supports async subprocesses on Windows.
- Rule: On Windows, use `subprocess.Popen` + daemon threads for output draining instead of `asyncio.create_subprocess_exec`. This works regardless of the event loop type. Reserve async subprocess calls for Linux/macOS only.

### [Claude-3] When changing production code's mock target, update ALL test files that mock it
- What happened: Claude-1 migrated swarm.py from asyncio.create_subprocess_exec to subprocess.Popen, but only updated 4 of 8 test files. The remaining 4 files (test_e2e, test_workflow_integration, test_swarm_history, test_project_stats) had 10 stale mocks patching the wrong target - meaning real PowerShell subprocesses ran during tests.
- Root cause: grep for the old pattern was only done in the files that were explicitly changed, not across the entire test suite
- Rule: After changing a mock target in production code, ALWAYS grep for the old pattern across ALL test files: `grep -r "old_pattern" tests/`. Fix every occurrence. Add buffer cleanup to conftest if the mock involves module-level state.

### [Claude-3] MagicMock streams need readline.return_value = b"" for drain thread termination
- What happened: Tests using MagicMock for subprocess stdout/stderr caused drain threads to run infinitely because MagicMock().readline() returns a truthy MagicMock instead of b"" (EOF). This leaked garbage into _output_buffers, causing test_output_empty_buffer to fail.
- Root cause: iter(stream.readline, b"") sentinel comparison fails because MagicMock != b"". The drain thread never exits.
- Rule: When mocking subprocess streams used by drain threads, either (1) add conftest cleanup for _output_buffers with cancel_drain_tasks() in teardown, or (2) set mock_process.stdout.readline.return_value = b"" to make drain threads terminate immediately.

### [Claude-3] HTML5 input max constraint blocks form submission silently
- What happened: ProjectSettings form submit tests failed (onSave never called, "Saving..." never shown) after max_phases default changed from 3 to 24
- Root cause: The `<input type="number" max={20}>` with `value={24}` fails HTML5 constraint validation. Form onSubmit is never called because the browser blocks it silently.
- Rule: When changing a numeric default, also update the corresponding HTML input min/max constraints. Verify: is the default value within [min, max]? This is invisible in manual testing (browsers show a tooltip) but breaks automated tests completely.

### [Claude-3] LogViewer gained a second toolbar with "All" button, breaking getByText('All')
- What happened: Tests using `getByText('All')` failed with "found multiple elements" after LogViewer added a log-level filter bar with its own "All" button
- Root cause: Agent filter bar has "All" button and the new level filter bar also has "All" button. `getByText` expects exactly one match.
- Rule: Use `getAllByText('All')[0]` or `getAllByText('All').length >= 1` when the same text can appear in multiple UI sections. Prefer `getByRole` with `name` option for more resilient selectors.

### [Claude-3] vi.mock must include ALL exports used by child components, not just the tested component
- What happened: ProjectView tab accessibility tests failed with "No startWatch export" because the vi.mock for ../lib/api didn't include startWatch, which Dashboard (a child of ProjectView) imports
- Root cause: vi.mock replaces the entire module. Any export used by any child component in the render tree must be mocked, not just what the direct component uses
- Rule: When mocking a shared module like api.js, grep all components in the render tree for their imports and include every export in the mock. Use `vi.mock(import("..."), async (importOriginal) => ...)` pattern when uncertain.

### [Claude-3] Async loadLogs() races with synchronous WebSocket state updates
- What happened: LogViewer test passed wsEvents at initial render, but the ws-appended lines were overwritten when the async loadLogs() resolved and called setLogs([])
- Root cause: useEffect for initial load runs an async fetch. useEffect for wsEvents fires synchronously. The fetch resolves later and replaces state.
- Rule: When testing components with both async data loading and synchronous prop-driven state updates, render first with null props, await the async effect, then re-render with the prop data.

### [Claude-3] useCallback stale closure when deps don't include referenced state
- What happened: AuthModal handleKeyDown (useCallback with [onClose]) calls handleSave which captures `key` state. But since `key` isn't in deps, Enter key always saves the initial empty key.
- Root cause: handleKeyDown memoized with incomplete dependency array - references handleSave which closes over stale `key`
- Rule: This is a real production bug (not a test issue). When useCallback calls another function that reads state, either include that state in deps or use a ref. Flag it for the frontend agent.
