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

### [Claude-4] When refactoring constructor parameters, update ALL callers including tests
- What happened: RateLimitMiddleware was changed from `rpm=` to `write_rpm=`/`read_rpm=` but 3 existing tests still used `rpm=2`, causing TypeError.
- Root cause: Constructor signature change without searching for all call sites.
- Rule: After changing any function/class signature, grep for ALL callers across source AND test files. Use `Grep pattern="ClassName(" path="."` to find all instantiations.
