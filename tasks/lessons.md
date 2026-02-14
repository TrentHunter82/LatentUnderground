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
- Update (Claude-4): In practice, `onClose` is an inline arrow in App.jsx, recreated every render, so deps change every render and the callback is always current. Still bad practice but not an actual bug in this app.

### [Claude-4] Test fixtures must use tmp_path for folder_path, never hardcoded real paths
- What happened: test_launch_no_swarm_script and test_boundary_values_accepted use `sample_project_data` fixture with `"folder_path": "F:/TestProject"`. When a real `F:/TestProject/swarm.ps1` exists on the developer's machine, the test passes the swarm.ps1 check and launches a real subprocess instead of failing with 400.
- Root cause: Test fixture uses a hardcoded path that could accidentally exist on the host filesystem
- Rule: Always use `tmp_path` for project `folder_path` in tests. Never use hardcoded paths like `F:/TestProject` - they are not isolated and break when the host has matching files.

### [Claude-2] ResizeObserver not available in jsdom - polyfill in test setup
- What happened: Adding ResizeObserver to LogViewer for virtual scroll container sizing caused ALL LogViewer tests to crash with `ReferenceError: ResizeObserver is not defined`
- Root cause: jsdom doesn't implement ResizeObserver. Any component using it will crash during test rendering.
- Rule: When using browser APIs not in jsdom (ResizeObserver, IntersectionObserver, matchMedia), add a polyfill in the test setup file. Always check that new browser APIs work in tests before committing.
- Update (Claude-4): The mock must also (1) set on both `globalThis` AND `window`, (2) call the constructor callback on `observe()` with reasonable defaults, (3) be unconditional (no `if undefined` guards). Fixed in setup.js.

### [Claude-2] Debounce in components breaks synchronous test assertions
- What happened: Adding 300ms debounce to Sidebar search caused tests to fail because `fireEvent.change` + immediate `expect` doesn't wait for the debounced value
- Root cause: `useDebounce` uses setTimeout internally. The debounced value updates asynchronously.
- Rule: When adding debounce to search inputs, update all tests that assert on filtered results to use `await waitFor(() => expect(...))` instead of synchronous assertions.

### [Claude-4] Toast setTimeout creates memory leak without cleanup tracking
- What happened: ToastProvider used bare `setTimeout` for auto-dismiss without storing timeout IDs. If component unmounted or toast was manually dismissed, the timeout callback still fired against stale state.
- Root cause: setTimeout returns an ID that must be tracked for cleanup. Common in notification components.
- Rule: When using setTimeout for auto-dismiss behavior, store IDs in a `useRef(new Map())`. Clear specific timeouts on manual dismiss. Clear all on unmount.

### [Claude-4] Swarm agents may not activate - plan for partial phase completion
- What happened: Phase 10 backend and testing agents (Claude-1, Claude-3) never activated. Their heartbeats never updated from start time. All backend tasks had to be deferred.
- Root cause: Swarm launch may fail to start all agents due to context limits, rate limits, or process management issues.
- Rule: Claude-4 (reviewer) should always plan for partial phase completion. Generate next-swarm.ps1 that carries forward incomplete tasks rather than blocking on missing work.

### [Claude-3] Python str.encode() cannot handle raw surrogate pairs
- What happened: Test used `\ud83d\ude80` (surrogate pair for rocket emoji) in a payload string. `_sign_payload` called `.encode()` which raised `UnicodeEncodeError: surrogates not allowed`
- Root cause: Python string literals with `\uD800-\uDFFF` create strings with raw surrogates. These are valid in JSON wire format but not encodable by Python's UTF-8 codec.
- Rule: In Python tests, use actual Unicode characters (`\u2605`) or pre-encoded JSON strings, never raw surrogate pairs (`\ud83d\ude80`). JSON parsers handle surrogates internally but Python source code cannot.

### [Claude-1] `from .module import NAME` creates a frozen copy - use `module.NAME` for testability
- What happened: `from .database import DB_PATH` in main.py created a module-level copy of the Path object. When tests changed `database.DB_PATH = tmp_db`, `_reconcile_running_projects()` still used the original path because it referenced the module-local `DB_PATH` copy.
- Root cause: Python's `from X import Y` binds `Y` as a local name. Reassigning `X.Y` later doesn't update the local binding in other modules.
- Rule: For values that tests need to override (DB paths, config), use `from . import module` and reference `module.ATTR` at call time. This ensures runtime reads the current value, not the import-time snapshot.

### [Claude-4] FastAPI `dependency_overrides` is the ONLY way to mock Depends() in tests
- What happened: Exception handler tests mocked `app.routes.projects.get_db` with `patch()` but the route still used the real function, returning 200 instead of the expected error.
- Root cause: `Depends(get_db)` stores the original function reference when the route is defined. Patching the module attribute doesn't affect the stored reference.
- Rule: Always use `app.dependency_overrides[get_db] = mock_fn` to override FastAPI dependencies in tests. Clean up with `app.dependency_overrides.pop(get_db, None)` in `finally` block.

### [Claude-4] Starlette's BaseHTTPMiddleware wraps exceptions in ExceptionGroup
- What happened: Generic `@app.exception_handler(Exception)` didn't catch RuntimeError when the app has multiple BaseHTTPMiddleware layers. Tests got unhandled ExceptionGroup instead of 500.
- Root cause: BaseHTTPMiddleware uses anyio task groups internally. Exceptions from downstream routes get wrapped in ExceptionGroup, which doesn't match the `Exception` handler before ServerErrorMiddleware intercepts.
- Rule: Test generic exception handlers by calling the handler function directly (unit test), not through the full ASGI stack. Specific exception handlers (e.g., sqlite3.OperationalError) work fine through the stack.

### [Claude-4] Keep backend and frontend version numbers in sync
- What happened: Frontend was at v0.11.0 (bumped each phase) but backend was still at v0.1.0 (never bumped). Health endpoint version mismatch caused test failures when synced.
- Root cause: No process to bump backend version alongside frontend.
- Rule: When bumping frontend package.json version, also bump FastAPI app version in main.py and update any hardcoded version assertions in tests.

### [Claude-3/Claude-4] (Consolidated) See above: dependency_overrides and ExceptionGroup lessons
- Duplicate entries from Claude-3 and Claude-4 merged. See lines 171-179 above.

### [Claude-3] Frontend integration tests need ALL api.js exports mocked
- What happened: vi.mock('../lib/api') requires every function that any child component imports, not just the ones the test directly uses. Missing mocks cause silent errors or "not a function" crashes.
- Root cause: React component tree imports deeply; Dashboard imports getSwarmStatus, AgentGrid, etc.
- Rule: When writing full-page integration tests, mock the ENTIRE api.js module with all ~30+ exports. Copy the comprehensive mock from phase12-integration.test.jsx as a template.

### [Claude-3] Use getAllByText/getAllByRole when text appears in multiple components
- What happened: "Latent Underground" appears in both Sidebar header and Home page; getByText throws on multiple matches.
- Root cause: Full-page integration renders all visible components simultaneously.
- Rule: In integration tests that render full App, always use getAllByText/getAllByRole and check .length >= 1, or target specific containers.

### [Claude-3] Flaky timeout tests need explicit timeout parameter
- What happened: Two pre-existing tests (End key navigation, react-markdown import) intermittently timed out at 5000ms default.
- Root cause: After 400+ tests, resource pressure slows later tests. Dynamic imports especially affected.
- Rule: Add explicit timeout (15000) to tests with heavy setup (renderProjectView) or dynamic imports. Syntax: `it('name', async () => { ... }, 15000)`

### [Claude-4] Vitest doesn't always collect new untracked test files with `npx vitest run`
- What happened: Running `npx vitest run` found 17 test files (383 tests), but running `npx vitest run src/test/` found 21 files (480 tests). 4 new test files were missed.
- Root cause: Vitest's default file discovery may be affected by untracked git status or file system caching on Windows. Explicit path argument forces collection.
- Rule: After adding new test files, always verify collection by running `npx vitest run src/test/` with explicit path. Or run individual new files to confirm they work.

### [Claude-3] Don't hardcode version strings - reference the single source of truth
- What happened: Health endpoint at main.py:534 had `"version": "0.11.0"` hardcoded, while `app = FastAPI(version="1.0.0")` was the actual version. Tests expected "1.0.0" and failed.
- Root cause: Version was bumped in the FastAPI app constructor but never in the health endpoint's response dict.
- Rule: Never hardcode version strings in response bodies. Always reference `app.version` or a shared constant. Grep for old version strings when bumping versions.

### [Claude-4] Windows `find -delete` unreliable for .pyc cleanup; use `rm -rf __pycache__` instead
- What happened: After bumping app version to 1.0.0, tests still saw 0.11.0. Cleared pycache with `find . -name "__pycache__" -exec rm -rf {} +` but stale .pyc persisted.
- Root cause: Windows MINGW `find` command behaves differently from Linux. The -exec rm variant may fail silently, and .pyc files get regenerated by uv/pytest collection before the test actually runs.
- Rule: On Windows, use `rm -rf app/__pycache__` directly on the specific directories. Always verify with `ls` that caches are actually gone. When version bumps cause mysterious test failures, suspect stale .pyc first.

### [Claude-4] aria-label on span/div requires role="img" per axe 4.11
- What happened: axe-core 4.11 enforces aria-prohibited-attr: `aria-label` cannot be used on `<span>` or `<div>` without a valid ARIA role.
- Root cause: Earlier axe versions allowed aria-label on any element. 4.11 is stricter.
- Rule: When using `aria-label` on decorative/indicator elements (`<span>`, `<div>`), always add `role="img"` to make it valid ARIA. This applies to LED indicators, status dots, badges.

### [Claude-1] Claude Code --print mode blocks on open stdin pipe
- What happened: Agents launched via `subprocess.Popen(stdin=subprocess.PIPE)` with `claude --print` produced zero output for 60+ seconds. The process was alive but nothing came through stdout/stderr pipes.
- Root cause: Claude Code's `--print` mode waits for stdin EOF before processing. When `stdin=subprocess.PIPE` keeps the pipe open, Claude blocks indefinitely waiting for input that never comes. The `communicate()` method works because it closes stdin first.
- Rule: Always use `stdin=subprocess.DEVNULL` when launching Claude Code in `--print` mode. This provides immediate EOF. Also add `creationflags=subprocess.CREATE_NO_WINDOW` on Windows to prevent console windows. If stdin interaction is needed, don't use `--print` mode.

### [Claude-4] When refactoring constructor parameters, update ALL callers including tests
- What happened: RateLimitMiddleware was changed from `rpm=` to `write_rpm=`/`read_rpm=` but 3 existing tests still used `rpm=2`, causing TypeError.
- Root cause: Constructor signature change without searching for all call sites.
- Rule: After changing any function/class signature, grep for ALL callers across source AND test files. Use `Grep pattern="ClassName(" path="."` to find all instantiations.

### Project creation scaffolds files automatically
**Context**: `POST /api/projects` copies swarm.ps1, stop-swarm.ps1, swarm.bat from LU root into the project folder, plus creates .claude/, tasks/, logs/ directories.
**Mistake**: Test assumed creating a project with an empty folder would leave it empty. In reality, the API scaffolds it immediately.
**Fix**: Create the project via API, then delete the scaffolded file before testing the missing-file path.
**Rule**: Always check what the API endpoint does beyond just the DB insert — FastAPI endpoints in this project often have side effects (file creation, directory scaffolding).

### [Claude-1] replace_all on version assertions can over-replace manual-insert tests
- What happened: Used `replace_all` for `assert version == 3` → `assert version == 4` when updating migration tests. This correctly updated migration-driven assertions but ALSO changed `test_get_schema_version_multiple_records` which manually inserts versions 1,2,3 and asserts max==3 (not migration-driven).
- Root cause: `replace_all` is a blunt instrument — it doesn't understand semantic context. Some tests insert specific version numbers without running migrations.
- Rule: When updating schema version assertions, use targeted edits (not replace_all). Review each assertion individually to determine if it's testing the migration system or testing the version-reading logic with manually inserted data.

### [Claude-1] Pydantic min_length/max_length validation returns 422, not 400
- What happened: Tests expected `status_code == 400` for empty string and too-long string inputs, but Pydantic's `Field(min_length=1, max_length=100000)` validation rejects them with 422 (Unprocessable Entity) before the endpoint handler runs.
- Root cause: Pydantic validation errors are caught by FastAPI's RequestValidationError handler which returns 422. Only errors raised explicitly by endpoint code return 400.
- Rule: Use `assert status_code == 422` for inputs rejected by Pydantic model validation (type errors, min/max length, regex patterns). Use `assert status_code == 400` for business logic errors raised explicitly in the endpoint handler (e.g., invalid agent name checked by custom validation functions).

### [Claude-4] useEffect polling closure captures stale derived state
- What happened: TerminalOutput's agent polling used `anyAgentAlive` (derived from `availableAgents` state) inside `setTimeout` callback, but `anyAgentAlive` was stale since `availableAgents` wasn't in the effect's dependency array.
- Root cause: Derived values computed outside `useEffect` are captured at closure creation time. Since the effect only depends on `[projectId]`, the closure never updates.
- Rule: When polling functions need to branch on fetched data (e.g., adaptive interval), compute the decision inside the polling function from the fresh response data, not from state variables.

### [Claude-4] Supervisor asyncio.Task must clean up tracking dict in finally block
- What happened: `_supervisor_tasks` dict accumulated stale entries when supervisors exited via exception or cancellation, because only the normal exit path removed the entry.
- Root cause: `_supervisor_tasks.pop()` was only called in `_cleanup_project_agents()`, not in the supervisor's own exit paths.
- Rule: Any long-running task that registers itself in a tracking dict must have a `finally` block that removes itself. This prevents memory leaks from accumulating done-but-never-cleaned tasks.

### [Claude-4] Pydantic models must be ordered by dependency (no forward references)
- What happened: `ProjectDashboardOut` (line 58) referenced `AgentStatusOut` (line 148) and `TaskProgress` (line 120) before they were defined. This caused `NameError` at import time, breaking 4 test files.
- Root cause: New model added without checking if referenced types were already defined above it in the file.
- Rule: In Pydantic response model files, always define models in dependency order (leaf models first, composite models last). When adding a model that references others, search for the referenced class definitions and ensure they appear above.

### [Claude-4] Toast retry callbacks must not capture DOM events
- What happened: `handleSubmit` passed `e` (React event) to toast retry: `onClick: () => handleSubmit(e)`. The event is recycled by React, so when the user clicks "Retry", `e` is null/stale.
- Root cause: React synthetic events are pooled and recycled. Closures over event objects become invalid after the event handler returns.
- Rule: Extract the core logic into a separate function that doesn't need the event. The form handler calls `e.preventDefault()` then delegates to the event-free function. Retry callbacks call the event-free function directly.

### [Claude-1] Never call blocking subprocess/thread operations from async coroutines
- What happened: `_cleanup_project_agents()` does `proc.wait(timeout=5)` and `t.join(timeout=3)` synchronously. Called from async `stop_swarm`, `cancel_drain_tasks`, and `_supervisor_loop`, it blocked the event loop for up to 11 seconds per agent.
- Root cause: Functions that manage subprocesses naturally use blocking calls. When invoked from async code without wrapping, they freeze all other request handling.
- Rule: Any function that calls `proc.wait()`, `proc.communicate()`, `thread.join()`, or similar blocking I/O must be wrapped in `asyncio.to_thread()` when called from async code. Audit all call sites when refactoring sync→async boundaries.

### [Claude-4] ARIA tablist must contain only role="tab" or role="presentation" children
- What happened: FileEditor had a `role="tablist"` div that contained tab buttons, spacer divs, timestamp spans, and action buttons (Cancel/Save/Edit). axe-core 4.11 flagged `aria-required-children` violation.
- Root cause: All children of `tablist` must have `role="tab"`, `role="presentation"`, or `role="none"`. Non-tab UI elements inside a tablist are invalid.
- Rule: When using `role="tablist"`, wrap only the tab buttons inside it. Move toolbar elements (spacers, action buttons, metadata) outside the tablist into a sibling container. Use `role="presentation"` for any structural wrappers inside the tablist that aren't tabs.

### [Claude-4] Test mocks must match actual export shape (named vs default)
- What happened: `vi.mock('../hooks/useWebSocket', () => ({ default: () => ... }))` broke because the hook file exports `export function useWebSocket` (named), not `export default`.
- Root cause: Test writer assumed default export without checking the source file.
- Rule: Before writing a vi.mock for any module, check whether it uses named exports or default export. `Grep pattern="export" path="source/file"` takes 2 seconds and prevents hours of debugging.

### [Claude-4] Component tests must pass ALL required props to render meaningful output
- What happened: AgentGrid PID responsive test passed `agents` but not `processAgents`. The PID is only rendered via `proc?.pid` from processAgents lookup, so no PID elements were rendered and the test found 0 matches.
- Root cause: Test assumed `agents` prop contained PID data, but the component derives it from a separate `processAgents` prop.
- Rule: Before writing assertions about rendered output, trace the data flow: which prop controls which DOM element? Pass all props needed to render the element under test.

### [Claude-4] axe-core heading-order fails for components rendered in isolation
- What happened: Dashboard and ProjectView components use `h3` section headings. When rendered in test isolation (without parent page's h1/h2), axe-core flags heading-order violation.
- Root cause: Components are designed to be embedded in pages that have h1/h2 headings. Standalone rendering skips the heading hierarchy.
- Rule: In component-level axe tests, disable heading-order rule: `axe(container, { rules: { 'heading-order': { enabled: false } } })`. Only test heading hierarchy in full-page integration tests.

### [Claude-1] Supervisor tasks must not clean up themselves via shared cleanup function
- What happened: `_supervisor_loop` called `_cleanup_project_agents()` which also cancels the supervisor task (itself). This worked by accident but was fragile.
- Root cause: A long-running task calling a shared cleanup function that terminates the caller creates confusing control flow.
- Rule: Split cleanup into layers: `_terminate_project_agents()` for agent-only cleanup (safe to call from supervisor), `_cleanup_project_agents()` for full cleanup including supervisor cancel (for external callers). The supervisor should only clean up what it owns, then exit normally.

### [Claude-1] Cache shared references before TOCTOU checks
- What happened: `get_db()` checked `if _pool and not _pool._closed` without caching `_pool`. Between these checks, `close_pool()` could set `_pool = None`.
- Root cause: Module-level mutable references can change between sequential attribute accesses in async code.
- Rule: When checking a global/shared reference and then using it, cache the reference first: `pool = _pool; if pool and not pool._closed: ...`. This prevents the reference from changing between the check and the use.

### [Claude-3] vi.clearAllMocks() clears state but not implementations
- What happened: Dashboard tests failed because `getProject` was returning undefined after `beforeEach(() => vi.clearAllMocks())`. A prior test had called `getProject.mockRejectedValue(...)` and clearAllMocks removed the mock calls/return values but the top-level `vi.mock` factory wasn't re-invoked.
- Root cause: `vi.clearAllMocks()` only resets mock state (calls, return values). It does NOT restore the original implementation from the `vi.mock()` factory. After clearing, mocks become `vi.fn()` returning undefined.
- Rule: When tests modify mock implementations (`.mockRejectedValue`, `.mockResolvedValue`), re-set the needed mock implementations at the start of each dependent test. Don't rely on `clearAllMocks` to restore factory defaults.

### [Claude-3] Match component prop interfaces exactly in tests
- What happened: Tests for SwarmControls used `onStatusChange` prop but the component accepts `onAction`. Tests for TerminalOutput used `status="running"` but the component accepts `fetchOutput` and `isRunning`. Dashboard tests passed a `project` prop but it accepts `wsEvents` and `onProjectChange` (fetches via useParams/getProject internally).
- Root cause: Test writer assumed prop names without reading the component's export signature.
- Rule: Always check `export default function ComponentName({ ...props })` destructuring before writing tests. Props not in the destructuring are silently ignored, leading to tests that don't exercise the intended behavior.

### [Claude-3] SwarmControls Stop button opens ConfirmDialog first
- What happened: Tests clicked the Stop button and immediately expected `stopSwarm` to be called. The button actually opens a `ConfirmDialog` - the user must click the confirm button within the dialog before `handleStop` executes.
- Root cause: Safety pattern - destructive actions require confirmation. Test didn't account for the two-step interaction.
- Rule: For buttons that trigger destructive actions, check if they open a confirmation dialog. After clicking the trigger button, wait for `screen.getByRole('alertdialog')` to appear, then click the confirm button within it.

### [Claude-3] get_db() is an async generator — cannot use `await get_db()`
- What happened: Benchmark tests used `db = await get_db()` which raised `TypeError: object async_generator can't be used in 'await' expression`.
- Root cause: `get_db()` in database.py is an async generator (uses `yield`) meant for FastAPI's `Depends()`. It cannot be awaited directly.
- Rule: In tests that need direct DB access, use `async with aiosqlite.connect(database.DB_PATH) as db:` instead. Or use `async for db in get_db():`. Never `await get_db()`.

### [Claude-4] Adding new exports to shared modules (api.js) requires updating ALL test mocks
- What happened: `createAbortable()` was added to api.js and used by Dashboard.jsx. Only 1 of 25 test files that mock `../lib/api` included `createAbortable` in the mock. This caused 62 frontend test failures because components importing the function got `undefined`.
- Root cause: vi.mock replaces the entire module. Any new export added to a shared module must be added to every test file that mocks that module.
- Rule: When adding a new export to a widely-mocked module like api.js: (1) grep for `vi.mock.*lib/api` to find all test files, (2) add the mock to every file, (3) run the full test suite, not just individual files. Consider adding shared mock factories in setup.js to reduce duplication.

### [Claude-4] Frontend test pollution: tests pass alone but fail in full suite
- What happened: 6 tests in phase17-error-recovery and phase15-features fail in full suite but pass individually. Empty `<div/>` body indicates component didn't render at all.
- Root cause: Dynamic imports (`await import('../components/Dashboard')`) cache modules between test files. If an earlier test file's vi.mock leaks into the module cache, later files get the wrong mock.
- Rule: This is a known Vitest limitation with dynamic imports + vi.mock. Solutions: (1) avoid dynamic imports in tests when possible, (2) use `vi.resetModules()` before dynamic imports, (3) accept as pre-existing flakes and document them.

### [Claude-3] Vite chunk name extraction must handle multi-hyphen hashes
- What happened: Bundle analysis test extracted chunk names with regex that assumed single hyphen+hash. File `markdown-Cn0I5-83.js` has hash `Cn0I5-83` containing a hyphen, so regex produced `markdown-Cn0I5` instead of `markdown`.
- Root cause: Vite's content hashes can contain hyphens, making `name.replace(/-[hash]\.ext$/, '')` unreliable.
- Rule: Use `name.split('.').slice(0, -1).join('.').split('-')[0]` to reliably extract the chunk name (everything before the first hyphen in the extensionless filename).

### [Claude-3] Schema version assertions must use dynamic constants, not hardcoded integers
- What happened: test_phase20_features.py had `assert version == 3` which broke when Phase 21 added migration_004 (SCHEMA_VERSION=4). test_swarm_history.py was missing 'summary' from expected_fields after swarm_runs gained a summary column.
- Root cause: Hardcoded version numbers become stale when migrations are added. Field sets don't track schema changes.
- Rule: Use `database.SCHEMA_VERSION` instead of hardcoded integers in tests. When adding columns to tables, grep all test files for expected field sets and add the new column name.

### [Claude-1] Don't clean up shared locks in a function that callers hold the lock through
- What happened: Added `_project_locks.pop(project_id, None)` to `_cleanup_project_agents()` to prevent memory leak. But `_launch_swarm_locked()` calls `cancel_drain_tasks(project_id)` → `_cleanup_project_agents()` WHILE HOLDING the lock from `_get_project_lock()`. The lock got deleted from the dict while still held, breaking assertions.
- Root cause: `_launch_swarm_locked()` is called inside `async with lock:`, but it calls cleanup which deleted the lock it was holding.
- Rule: Never clean up a shared resource (lock, semaphore) inside a function called while that resource is held. Clean up locks on project deletion or process exit, not on swarm stop/restart. The memory cost of retaining asyncio.Lock objects is negligible (~100 bytes each).

### [Claude-3] _compute_trend splits DESC-ordered list — first_half = newer, second_half = older
- What happened: Test expected "improving" when older runs had high errors and newer runs had none. But the function returned "degrading".
- Root cause: `per_run_crash_rates` is built from DB query `ORDER BY id DESC`, so index 0 is newest. `_compute_trend` splits into first_half (newer) and second_half (older). `diff = second_half - first_half`. If second_half (older) > first_half (newer), diff > 0 → "degrading". This means "things are getting worse over time" (older data being higher confusingly maps to "degrading").
- Rule: When testing `_compute_trend`, remember: improving = newer half has HIGHER rates (diff < -0.05), degrading = older half has HIGHER rates (diff > 0.05). The naming is inverted from intuition because the function compares older vs newer, not newer vs older.

### [Claude-3] aiosqlite.Row factory required for string-indexed column access
- What happened: Migration tests calling `_get_schema_version(db)` after `_run_migrations(db)` failed with `TypeError: tuple indices must be integers or slices, not str` because `row["version"]` needs Row factory.
- Root cause: `_get_schema_version` uses `row["version"]` which requires `db.row_factory = aiosqlite.Row`. Without it, rows are plain tuples.
- Rule: When calling database helper functions that use string column access (`row["column"]`), always set `db.row_factory = aiosqlite.Row` on the connection first.

### [Claude-4] When changing _AUTH_SKIP_PATHS, grep for tests that depend on the old auth behavior
- What happened: Removed `/api/metrics` from `_AUTH_SKIP_PATHS` to require auth. `test_metrics_skips_auth` failed because it asserted the old behavior (200 without auth).
- Root cause: Security behavior change without updating the test that explicitly verified the old behavior.
- Rule: After changing auth skip paths, grep all tests for the endpoint path AND for "skip_auth" / "skips_auth" patterns. Update every test to match the new expected behavior.

### [Claude-4] ConnectionPool._create_connection() must set all per-connection PRAGMAs from init_db()
- What happened: Pool connections only set `foreign_keys=ON` and `busy_timeout=5000`, missing `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-16000`. These are per-connection PRAGMAs (not database-level like WAL mode). Pool connections ran 2-3x slower for writes.
- Root cause: `init_db()` and `_create_connection()` were written independently. PRAGMAs were added to init_db but never propagated to the pool.
- Rule: When adding PRAGMAs to `init_db()`, always check if they're per-connection (most are) and add them to `_create_connection()` too. Only WAL mode is database-level.

### [Claude-1] Prometheus histogram must handle durations exceeding all buckets
- What happened: Custom histogram had a `for/break` loop that never incremented any bucket when `duration > max(DURATION_BUCKETS)`. Slow requests (>10s) were lost from bucket distribution, breaking p50/p95/p99 percentile calculations.
- Root cause: Standard histogram semantics require every observation to land in some bucket. The loop silently dropped values above the largest bucket.
- Rule: Always add `for/else` to histogram bucket insertion: `else: buckets[-1] += 1`. This ensures durations exceeding all bounds land in the largest bucket, matching Prometheus convention.

### [Claude-2] vi.resetModules() breaks React context providers in tests with dynamic imports
- What happened: Added `vi.resetModules()` to phase17-error-recovery.test.jsx beforeEach to fix module cache pollution. This caused ALL tests that dynamically import components (Dashboard, FileEditor, SwarmControls) to fail with "useToast must be used within ToastProvider".
- Root cause: `vi.resetModules()` forces re-evaluation of all modules. The `ToastProvider` imported statically at the top of the test file becomes a DIFFERENT module instance than the one dynamically imported components use. React contexts only match within the same module instance.
- Rule: Do NOT use `vi.resetModules()` when (1) the test uses static imports for providers (ToastProvider, MemoryRouter) AND (2) the test dynamically imports components that use those providers. These are irreconcilable — the static provider and the dynamic consumer become different module instances. Accept these as known flakes and verify they pass individually.

### [Claude-2] Shape-based accessibility indicators need matching processAgents prop in tests
- What happened: Updated AgentGrid LEDs from color-only dots to SVG shape icons with sr-only text. Test searched for "Claude-1: running" text but the agent status showed "Stale" because only `agents` prop was passed, not `processAgents`.
- Root cause: `agentStatus()` checks `processInfo` (from `processAgents` prop) first for alive/crashed/stopped status. Without `processAgents`, it falls back to heartbeat-based detection which returns "Stale" for agents with no heartbeat.
- Rule: When testing AgentGrid with expected alive/running agents, always pass both `agents` and `processAgents` props. The `alive` field in the agents array is NOT checked by `agentStatus()` — only `processInfo.alive` from processAgents matters.

### [Claude-4] TanStack Query hooks mock must return stable references to prevent infinite re-renders
- What happened: After adding TanStack Query hook mocks (`useProjects`, `useSwarmQuery`) to integration tests, App.jsx entered infinite re-render loops because `useEffect([projects])` detected new references every render.
- Root cause: Mock functions like `useProjects: () => ({ data: [...] })` create new array/object references on each call. React's `useEffect` dependency comparison sees a new reference and re-runs, triggering another render.
- Rule: When mocking hooks that return data used in React dependency arrays, extract data as module-level constants outside the mock function: `const _data = [...]; vi.mock(() => ({ useProjects: () => ({ data: _data }) }))`. This ensures the same reference is returned on every render.

### [Claude-3] mockRejectedValue pollutes subsequent tests - vi.clearAllMocks doesn't reset implementations
- What happened: Test set `getProject.mockRejectedValue(new Error('Network error'))` to test error states. Subsequent tests in same suite failed because getProject still rejected - vi.clearAllMocks() only clears call history, not mock implementations.
- Root cause: vi.clearAllMocks() resets mock.calls and mock.results but does NOT reset mockReturnValue/mockResolvedValue/mockRejectedValue. The mock implementation persists.
- Rule: When a test changes a mock implementation (mockRejectedValue, mockResolvedValue, etc.), wrap the test body in try/finally and restore the original mock implementation in the finally block. Example: `try { getProject.mockRejectedValue(...); /* test */ } finally { getProject.mockResolvedValue(originalData) }`. Alternative: use mockRejectedValueOnce() which auto-resets after one call.

### [Claude-3] TanStack Query mock pattern for Dashboard tests: use vi.fn() for configurable hooks
- What happened: Dashboard tests needed different hook return values per test (error state, loading state, success state). Static hook mocks couldn't be changed per-test.
- Root cause: vi.mock() runs once and returns the same value. Tests that need different hook behaviors per test case need a controllable mock.
- Rule: Make hooks configurable by wrapping in vi.fn(): `const mockUseProject = vi.fn(() => defaultResult); vi.mock('../hooks/useProjectQuery', () => ({ useProject: (...args) => mockUseProject(...args) }))`. Then in each test: `mockUseProject.mockReturnValue({ data: null, isLoading: false, error: new Error('fail'), refetch: vi.fn() })`.

### [Claude-4] TanStack Query v5 useMutation passes extra context arg to mutationFn
- What happened: Tests using `toHaveBeenCalledWith(expectedArg)` for mutation functions failed because TanStack Query v5 passes a second argument (mutation context object with `client`, `meta`, `mutationKey`) to the `mutationFn`.
- Root cause: TanStack Query v5 changed the `mutationFn` signature to include context metadata as a second parameter.
- Rule: When testing TanStack Query mutations, check only the first argument: `expect(fn.mock.calls[0][0]).toEqual(expected)` instead of `expect(fn).toHaveBeenCalledWith(expected)`.

### [Claude-4] Guardrail regex must have same ReDoS protections as output search
- What happened: Phase 25 added output guardrails with user-supplied regex patterns but initially lacked the timeout protection that output search already had. A malicious regex could freeze the entire backend supervisor.
- Root cause: Feature was added without inheriting existing security patterns from the same codebase.
- Rule: When adding any new feature that accepts user-supplied regex, always copy the protection pattern: `re.compile()` + `asyncio.wait_for(asyncio.to_thread(search), timeout=5.0)` + pattern length cap (200 chars) + input size cap (1MB). Grep for existing `wait_for.*to_thread.*search` patterns to find the reference implementation.

### [Claude-3] App-level rendering in vitest/jsdom always times out
- What happened: Tests that `await import('../App')` and render the full App component timeout at 15s. Tried multiple mock patterns (vi.hoisted, async vi.mock factory, inline constants) — none help.
- Root cause: App component loads all routes, lazy-loaded chunks, providers, etc. in jsdom which is too slow. The timeout is inherent to full-App rendering, not the mock pattern.
- Rule: Never test global keyboard shortcuts by rendering the full App. Instead, test at the component level (e.g., test ProjectView tabs, Sidebar shortcuts separately). Use `describe.skip` for App-level render tests and cover them via e2e/Playwright instead.

### [Claude-3] vi.hoisted() pattern for shared mock factories
- What happened: Creating shared TanStack Query mock factories in test-utils.jsx and importing via `await vi.hoisted(() => import('./test-utils'))` works for most component tests but NOT for tests that render the full App.
- Root cause: `vi.hoisted` with dynamic import works when the mock factory returns synchronously before the module is first imported. But full App rendering triggers deep import chains that can race with mock setup.
- Rule: Use `await vi.hoisted(() => import('./test-utils'))` + `vi.mock('./hooks/useX', () => createXMock())` for component-level tests. For files using `vi.fn()` wrappers that need per-test overrides, use static `import { createXMock } from './test-utils'` instead (works because vi.mock factory captures the import at module scope).
