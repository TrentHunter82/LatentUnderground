# Latent Underground - Task Board (Phase 7)

## Claude-1 [Backend/Core] - Stdin input, real-time streaming, auth, DB optimization

- [x] Add swarm stdin input: pipe stdin in Popen, store process objects in _swarm_processes dict, POST /api/swarm/input endpoint (write to stdin, echo as [stdin] in output buffer, cleanup on stop/shutdown)
- [x] Add WebSocket-based log streaming: push new log lines to connected clients in real-time (replace polling)
- [x] Add basic authentication: API key middleware with configurable LU_API_KEY env var (skip for /api/health)
- [x] Add database indexes: CREATE INDEX on projects(status), swarm_runs(project_id, started_at), swarm_runs(status)
- [x] Add log search date range filter: from/to params on GET /api/logs/search (missing from Phase 6)
- [x] Signal: Create .claude/signals/backend-ready.signal

## Claude-2 [Frontend/Interface] - Terminal input, real-time UI, auth refinements

- [x] Add terminal input bar: text field + Enter-to-send in TerminalOutput component (> prompt, disabled when not running, sends via POST /api/swarm/input, wire sendSwarmInput from api.js through ProjectView)
- [x] Add real-time log viewer: WebSocket subscription for live log lines (LIVE indicator, server-side search with dates)
- [x] Add login/API key prompt: AuthModal on 401, persist key in localStorage, attach Bearer header to all requests
- [x] Add date range picker for log search (from/to date inputs, switches to searchLogs API)
- [x] Add keyboard shortcuts: Ctrl+K for search, Ctrl+N for new project, Escape to close modals
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - Test coverage for Phase 7 features

- [x] Add tests for stdin input endpoint (8 tests: not found, not running, no process, process exited, success, echo buffer, broken pipe, text too long)
- [x] Add tests for auth middleware (8 tests: disabled, valid Bearer, valid X-API-Key, invalid key, missing key, health bypass, docs bypass, non-API bypass)
- [x] Add tests for database indexes (3 tests: created, correct columns, idempotent)
- [x] Add tests for log search date range filter (7 tests: from, to, both, invalid from, invalid to, date-only format, no-timestamp lines)
- [x] Add frontend tests for terminal input (8 tests), auth modal (8 tests), date range (3 tests), live logs (2 tests), keyboard shortcuts (2 tests), API functions (8 tests)
- [x] Signal: Create .claude/signals/tests-passing.signal (503 total: 276 backend + 227 frontend, 0 failures)

## Claude-4 [Polish/Review] - Final quality gate

- [x] Review all Phase 7 code changes for quality and consistency
- [x] Verify no regressions: 503 total tests (276 backend + 227 frontend), 2 pre-existing flaky tests
- [x] Security review: auth uses hmac.compare_digest, proper bypass rules, Bearer+X-API-Key support
- [x] Performance review: indexes correct (IF NOT EXISTS), log streaming uses incremental file positions
- [x] Fix: Add Field(ge=1) to SwarmStopRequest/SwarmInputRequest for validation consistency
- [x] Fix: Add _swarm_processes.clear() to conftest teardown for test isolation
- [x] Fix: Add client-side max length (1000) validation to terminal input
- [x] FINAL: Generate next-swarm.ps1 for Phase 8

## Completion Criteria
- [x] Users can type input to running swarm processes from the web terminal
- [x] Log viewer updates in real-time via WebSocket (incremental file position tracking)
- [x] API protected by optional API key (configurable via LU_API_KEY env var)
- [x] Database queries use indexes for search and analytics
- [x] All tests pass (276 backend + 227 frontend = 503 total, 2 pre-existing flaky tests on host paths)
