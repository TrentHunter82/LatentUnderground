# Agent Plans

## Claude-1 - Phase 11 Backend Hardening

### Plan
Phase 10 already implemented: webhooks CRUD, project archival, request logging middleware.
Phase 11 new work:

#### Task 1: Security headers middleware
- [x] Add SecurityHeadersMiddleware to main.py
- Headers: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Cache-Control: no-store on API, Referrer-Policy: strict-origin-when-cross-origin, X-XSS-Protection: 0 (modern approach - rely on CSP)
- Only apply to /api/ routes (not frontend static files)

#### Task 2: Global exception handlers
- [x] Add RequestValidationError handler -> 422 with structured {detail, errors}
- [x] Add sqlite3.OperationalError handler -> 503 with structured {detail}
- [x] Add generic Exception handler -> 500 with structured {detail}
- Log all exceptions at appropriate levels

#### Task 3: Dependency audit
- [x] Installed pip-audit, ran audit: 0 known vulnerabilities found

#### Task 4: Verify existing Phase 10 features
- [x] 507 backend tests pass, zero failures
- [x] All tasks marked [x] in TASKS.md

#### Task 5: Signal
- [x] Created .claude/signals/backend-ready.signal

## Claude-2 - Phase 11 Frontend Plan

### Tasks
1. [x] API functions: webhook CRUD + archive/unarchive + getProjectsWithArchived in api.js
2. [x] Code splitting: lazy-load LogViewer (7.37KB), SwarmHistory (2.50KB) in ProjectView.jsx
3. [x] Lazy-load highlight.js: dynamic import rehype-highlight in FileEditor.jsx (177KB on demand)
4. [x] Version badge: __APP_VERSION__ via vite define, replaced "v0.1" in SettingsPanel + Sidebar
5. [x] WebhookManager component: CRUD with form, LED indicators, event toggles, ConfirmDialog
6. [x] Archive toggle: Sidebar checkbox + hover button + Dashboard action button, App-level state
7. [x] Unsaved changes confirmation: beforeunload + dirty indicator in ProjectSettings
8. [x] Signal: .claude/signals/frontend-ready.signal

### Build Results
- Main: 246KB (under 300KB target), 15 lazy chunks
- LogViewer (7.37KB) + SwarmHistory (2.50KB) now split from main
- highlight.js (177KB) lazy via dynamic import in FileEditor
- Tests: 383 passed, 5 skipped, zero failures, zero regressions

### New/Modified Files
- NEW: WebhookManager.jsx (webhook CRUD component)
- MODIFIED: api.js (+14 API functions), ProjectView.jsx (lazy imports + WebhookManager),
  Sidebar.jsx (archive toggle), Dashboard.jsx (archive button), App.jsx (showArchived state),
  ProjectSettings.jsx (unsaved changes), SettingsPanel.jsx (version badge),
  FileEditor.jsx (lazy rehype-highlight), vite.config.js (__APP_VERSION__), package.json (v0.11.0)

## Claude-3 - Phase 11 Testing & Quality Gate

### Plan
Phase 11 focus: test new middleware (security headers, request logging), webhook edge cases,
archival lifecycle, load testing, bundle size regression.

#### Task 1: Security Header Tests - DONE
- [x] test_security_headers.py: 13 tests, all passing
  - 5 header types: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, X-XSS-Protection, Cache-Control
  - Tested on GET/POST/PATCH/DELETE/404/422 responses

#### Task 2: Request Logging Middleware Tests - DONE
- [x] test_request_logging.py: 10 tests, all passing
  - Isolated app fixture with middleware explicitly enabled
  - Captures method, path, status in log messages
  - Duration tracking with ms format regex verification
  - Structured extras (method, path, status, duration_ms) on log records
  - Slow endpoint verified at >= 40ms duration

#### Task 3: Archival Lifecycle Tests - DONE
- [x] test_archival_lifecycle.py: 13 tests, all passing
  - Full archive/unarchive cycle (archive→excluded→unarchive→restored)
  - Edge cases: double archive returns 400, nonexistent 404, still readable/updatable/deletable
  - History preservation: swarm history, stats, status all accessible when archived

#### Task 4: Webhook HMAC Edge Cases - DONE
- [x] 5 new tests added to test_webhook_integration.py, all passing
  - Tampered payload fails verification
  - Empty payload produces valid 64-char signature
  - Unicode payload (accented chars) signed correctly
  - Re-serialization changes signature (raw body signing proof)
  - Large payload (100KB) signed without issues

#### Task 5: Load Testing Enhancement - DONE
- [x] 3 new tests added to test_load.py, all passing
  - 10 concurrent status polls on same project (no cross-contamination)
  - 10 concurrent status polls on 10 different projects
  - 10 concurrent health checks

#### Task 6: Bundle Size Test - ALREADY ADEQUATE
- [x] bundle-size.test.js already has 6 tests: main<300KB, total<500KB, CSS<50KB, chunks<50KB, 8+ chunks

#### Task 7: Verification & Signal - DONE
- [x] Backend: 551 passed, zero failures (was 507)
- [x] Frontend: 383 passed, 5 skipped, zero failures
- [x] Total: 934 tests, zero failures
- [x] .claude/signals/tests-passing.signal created

### New Test Files Created (Phase 11)
1. backend/tests/test_security_headers.py (13 tests)
2. backend/tests/test_request_logging.py (10 tests)
3. backend/tests/test_archival_lifecycle.py (13 tests)
4. backend/tests/test_webhook_integration.py (+5 tests, expanded)
5. backend/tests/test_load.py (+3 tests, expanded)

## Claude-3 - Phase 10 QA & Release Testing

### Current State
- Backend: 466 tests (421 existing + 45 new in test_phase10_features.py)
- Frontend: 347 tests passing
- Total: 813 tests, zero failures
- Phase 10 features ALL implemented: plugins, webhooks, archival, versioning, request logging, settings, shortcuts, onboarding

### Test Plan

#### Task 1: Deep Plugin Integration Tests (backend) - DONE
- [x] 15 tests in test_plugin_integration.py: discovery, schema validation, config, hooks, lifecycle
- File: backend/tests/test_plugin_integration.py

#### Task 2: Webhook Delivery Integration Tests (backend) - DONE
- [x] 16 tests in test_webhook_integration.py: HMAC, delivery mock, event filtering, emit, edge cases
- File: backend/tests/test_webhook_integration.py

#### Task 3: Bundle Size Regression Test (frontend) - DONE
- [x] 6 tests in bundle-size.test.js: main<300KB, total<500KB, CSS<50KB, chunks, splitting
- File: frontend/src/test/bundle-size.test.js

#### Task 4: Load Testing (backend) - DONE
- [x] 10 tests in test_load.py: concurrent CRUD, status polling, archive, webhook, mixed ops
- File: backend/tests/test_load.py

#### Task 5: Accessibility Audit - Phase 10 Components (frontend) - DONE
- [x] 15 tests in phase10-accessibility.test.jsx: axe-core, ARIA, focus trap, keyboard nav
- [x] OnboardingModal fix: step dots changed div→span[role="img"] for axe compliance
- File: frontend/src/test/phase10-accessibility.test.jsx

#### Task 6: Upgrade Guide - DONE
- [x] UPGRADE.md: schema changes, env vars, API versioning, migration steps, breaking changes
- File: UPGRADE.md

#### Task 7: Final Verification & Signal - DONE
- [x] Backend: 507 passed, 0 failures (was 466, +41 new)
- [x] Frontend: 383 passed, 5 skipped, 0 failures (was 347, +36 new)
- [x] Total: 890 tests, zero failures (target was 840+)
- [x] .claude/signals/tests-passing.signal created

### New Test Files Created
1. backend/tests/test_plugin_integration.py (15 tests)
2. backend/tests/test_webhook_integration.py (16 tests)
3. backend/tests/test_load.py (10 tests)
4. frontend/src/test/bundle-size.test.js (6 tests)
5. frontend/src/test/phase10-accessibility.test.jsx (15 tests)
6. UPGRADE.md (documentation)

## Claude-4 - Phase 10 Final Review (COMPLETE)

### Test Verification
- Backend: 421 passed, 0 failures
- Frontend: 347 passed, 0 failures, 5 skipped
- **Total: 768 tests, all green (was 706 in Phase 9)**

### Code Reviews (3 subagent reviews: frontend, security, backend)
- Frontend: 5 issues found (1 critical Toast leak, 4 high a11y/pattern) - ALL FIXED
- Security: 0 CRITICAL, 0 HIGH, 4 MEDIUM (workspace root, PID race, info disclosure, config limits)
- Backend: No Phase 10 changes to review (Claude-1 inactive, only webhooks table schema added)

### Fixes Applied:
- [x] Toast.jsx: Track timeouts in ref Map, clear on dismiss/unmount (memory leak fix)
- [x] OnboardingModal.jsx: useCallback for handleClose, onKeyDown prop pattern (stale closure + a11y fix)
- [x] SettingsPanel.jsx: Replace inline confirm dialog with ConfirmDialog component (focus trap + a11y)
- [x] SettingsPanel.jsx: onKeyDown + useCallback pattern for focus trap (consistency)
- [x] test_database_indexes.py: Update expected index count 5→6 for new webhooks index

### Created:
- [x] CHANGELOG.md: Full Phase 1-10 history in Keep a Changelog format
- [x] next-swarm.ps1: Phase 11 transition (webhooks, archival, security hardening)

### Phase 10 Gap Analysis:
- Claude-1 backend tasks NOT completed: plugin system, webhook routes, archival, API versioning, request logging
- Claude-3 testing tasks NOT completed: no new features to test
- Root cause: Claude-1 and Claude-3 did not activate (heartbeats never updated from start time)
- Resolution: Backend tasks carried forward to Phase 11 with updated scope

### Research Findings
- FastAPI security: Input validation covered, need security headers middleware + global exception handlers
- React/Vite: Code splitting done by Claude-2 (49% reduction), source maps should be off in prod
- SQLite: WAL mode set, busy_timeout set, parameterized queries verified, backup via SQL dump avoids WAL sidecar issue
- Key gap: No security response headers (X-Content-Type-Options, X-Frame-Options) - added to Phase 11

## Claude-2 - Phase 10 Plan (COMPLETE)

### Task Assessment
- Settings panel, keyboard shortcuts, project export, template presets, error display, onboarding: ALL already implemented in Phase 9
- Only new task: **Optimize bundle size** (analyze with rollup-plugin-visualizer, lazy-load heavy components)

### Execution: ALL COMPLETE
- [x] 1. Installed rollup-plugin-visualizer, added to vite.config.js
- [x] 2. Manual chunk split: react-markdown + remark-gfm into 'markdown' chunk (vite.config.js manualChunks)
- [x] 3. React.lazy() for route components: NewProject (17KB), ProjectView (35KB)
- [x] 4. React.lazy() for modals: AuthModal (2.3KB), SettingsPanel (6.5KB), ShortcutCheatsheet (2.3KB), OnboardingModal (4.7KB)
- [x] 5. React.lazy() for tab components: FileEditor (3.2KB, pulls markdown chunk), Analytics (4.7KB, was already lazy)
- [x] 6. Suspense boundaries: route fallback ("Loading..."), modal fallback (null), tab fallback (animate-pulse)
- [x] 7. Tests: 347 passing, 5 skipped, zero failures, zero regressions
- [x] 8. Signal: .claude/signals/frontend-ready.signal created
- [x] 9. TASKS.md updated with all items checked

### Bundle Size Results
- **Before**: 481KB main JS (single chunk) + 179KB highlight.js
- **After**: 245KB main JS + 165KB markdown + 177KB highlight + ~77KB lazy chunks
- **Main chunk reduction: 49%** (481KB → 245KB)
- **Well under 500KB target**

### Lazy-loaded Chunks (12 total)
| Chunk | Size | Load Trigger |
|-------|------|-------------|
| index.js | 245KB | Initial page load |
| highlight.js | 177KB | FileEditor tab (code blocks) |
| markdown.js | 165KB | FileEditor tab (markdown preview) |
| ProjectView.js | 35KB | /projects/:id route |
| NewProject.js | 17KB | /projects/new route |
| SettingsPanel.js | 6.5KB | Gear icon click |
| OnboardingModal.js | 4.7KB | First-run only |
| Analytics.js | 4.7KB | Analytics tab |
| FileEditor.js | 3.2KB | Files tab |
| AuthModal.js | 2.3KB | Auth required |
| ShortcutCheatsheet.js | 2.3KB | Ctrl+? |
| constants.js | 1.8KB | Shared (auto-split) |

## Claude-1 - Phase 10 Plan (Backend/Core)

### Research Findings
- Plugin systems: Use auto-registration pattern with directory scanning, config.json per plugin
- Webhooks: Use BackgroundTasks for async delivery, HMAC-SHA256 signing, retry with exponential backoff
- API versioning: URL-based /api/v1/ with deprecation headers (X-API-Deprecation, Sunset)
- SQLite: Add PRAGMA mmap_size for read performance, use EXPLAIN QUERY PLAN on hot queries

### Execution: ALL COMPLETE
- [x] Task 3: Project archival (archived_at column, archive/unarchive endpoints, exclude from list)
- [x] Task 5: SQLite optimization (mmap_size=256MB, ANALYZE, 3 new composite indexes)
- [x] Task 6: Request/response logging middleware (method, path, status, duration_ms, LU_REQUEST_LOG)
- [x] Task 1: Plugin system (PluginManager, JSON discovery, CRUD at /api/plugins)
- [x] Task 2: Webhooks (DB table, CRUD at /api/webhooks, HMAC-SHA256, async delivery, swarm event emission)
- [x] Task 4: API versioning (APIVersionMiddleware rewrites /api/v1/ to /api/, deprecation headers)
- [x] Task 7: 466 backend tests passing (421 + 45 new), backend-ready.signal created

### New Files
- backend/app/plugins.py, routes/plugins.py, routes/webhooks.py, tests/test_phase10_features.py

### Modified Files
- database.py, main.py, config.py, routes/projects.py, routes/swarm.py, models/project.py, conftest.py, .env.example

## Claude-3 - Phase 9 Quality Gate (COMPLETE)

### Assessment
Phase 9 tests already exist (706 total passing). My job: verify, fill gaps, sign off.

Existing coverage:
- E2E: 20 tests (test_e2e_phase9.py) - full lifecycle ✓
- API contracts: 36 tests (test_api_contracts.py) - endpoint existence + response shapes ✓
- Performance: 7 tests (phase9-quality.test.jsx) - Sparkline, TemplateManager, FolderBrowser ✓
- Accessibility: 10 axe + 41 ARIA tests - subset of components ✓
- Error boundary: 10 tests (phase9-quality.test.jsx) ✓
- Template lifecycle: 3 tests (test_e2e_phase9.py) ✓

### Gaps Filled
1. [x] Frontend a11y: 13 new axe-core tests for TaskProgress(3), AgentGrid(2), SignalPanel(2), SwarmHistory(2), SwarmControls(2), Sidebar(2)
2. [x] Backend: 8 new field type validation tests (project, template, health, output, browse, history, stats)
3. [x] Backend: 4 new pagination edge case tests (negative offset, oversized limit, zero limit, large offset)
4. [x] Full suite: 421 backend + 310 frontend = 731 total, zero failures
5. [x] Signal: .claude/signals/tests-passing.signal created
6. [x] TASKS.md marked complete with updated counts

### Research Findings
- vitest-axe best in JSDOM env (project already uses JSDOM) ✓
- API contract tests should validate types, not just field presence
- Performance tests in JSDOM don't reflect real browser; acceptable for regression detection
- axe-core catches ~30-50% of real a11y issues; manual testing still needed

## Claude-4 - Phase 9 Final Review (COMPLETE)

### Test Verification
- Backend: 409 passed, 0 failures
- Frontend: 297 passed, 0 failures, 5 skipped
- **Total: 706 tests, all green**

### Code Review (3 subagent reviews: backend, frontend, security)
- Backend: 3 reviewer-flagged "critical" issues analyzed - 2 false positives, 1 real (log retention glob)
- Frontend: 0 critical/important issues - rated EXCELLENT
- Security audit: 9 findings analyzed, 2 actionable fixes applied, remainder documented as by-design

### Fixes Applied:
- [x] database.py: Remove unused `from pathlib import Path` import
- [x] main.py: Wrap log retention glob in OSError protection (prevents crash on deleted project folders)

### Review Findings (documented, no action needed for localhost tool):
- WebSocket intentionally unauthenticated (broadcast-only, localhost)
- Browse API allows full filesystem browsing (intended behavior for file picker)
- Rate limiter dict growth bounded by (unique clients * endpoints) - negligible for localhost
- Log search collects all matches before pagination - acceptable for local project log sizes
- Auto-backup BytesIO buffer already seek(0) in _create_backup() - reviewer false positive
- DB retry for-else raises before yield db reached - reviewer false positive on UnboundLocalError

### Deployment Guide Created:
- [x] docker-compose.prod.yml (nginx + app + health checks + named volumes)
- [x] deploy/nginx.conf (SSL, WebSocket upgrade, SSE proxy_buffering off)
- [x] deploy/latent-underground.service (systemd with security hardening)
- [x] deploy/DEPLOY.md (full guide: Docker, bare metal, SSL, monitoring, troubleshooting)

## Claude-3 - Phase 9 Test Plan (COMPLETE)

### Phase 8 Gap Fill (done first)
- [x] test_browse.py: 26 tests for browse endpoint (was 0% coverage)
- [x] test_templates.py: +6 edge cases (update nonexistent, no-op, description only, empty/nested config, ordering)
- [x] test_reconciliation.py: +3 edge cases (NULL PID, multiple orphaned runs, _pid_alive exception)
- [x] phase8-components.test.jsx: +23 tests (FolderBrowser 13, TemplateManager edit/delete 5, useDebounce 5)

### Phase 9 E2E & Quality
- [x] test_e2e_phase9.py: 20 E2E tests (template lifecycle, browse→create, pagination flow, search+filter, analytics, full lifecycle, health)
- [x] test_api_contracts.py: 36 tests (29 endpoint existence via OpenAPI schema, 7 response format contracts)
- [x] phase9-quality.test.jsx: 27 tests (ErrorBoundary 10, axe-core accessibility 10, performance benchmarks 7)

### Final Verification
- [x] Backend: 409 passed, 0 failures (was 295)
- [x] Frontend: 297 passed, 5 skipped, 0 failures (was 247)
- [x] Total: 706 tests, zero failures
- [x] tests-passing.signal created
- [x] TASKS.md updated

### New Test Files Created
1. backend/tests/test_browse.py (26 tests)
2. backend/tests/test_e2e_phase9.py (20 tests)
3. backend/tests/test_api_contracts.py (36 tests)
4. frontend/src/test/phase9-quality.test.jsx (27 tests)
5. Updated: test_templates.py (+6), test_reconciliation.py (+3), phase8-components.test.jsx (+23)

## Claude-1 - Phase 9 Plan

### Task 1: Structured Logging (LU_LOG_FORMAT=json|text)
- Add LU_LOG_FORMAT to config.py (default "text")
- Create JsonFormatter class in main.py (JSON lines: timestamp, level, logger, message)
- Apply formatter in lifespan based on config

### Task 2: Graceful Shutdown
- Lifespan shutdown already stops PID monitors, cancels drain tasks, cleans watchers
- Add: flush output buffers, structured shutdown logging, timeout on thread joins
- This is enhancement of existing lifespan, not new SIGTERM handler (uvicorn handles SIGTERM)

### Task 3: Log Retention Policy (LU_LOG_RETENTION_DAYS)
- Add LU_LOG_RETENTION_DAYS to config.py (default 0 = disabled)
- On startup: scan all project log directories, delete files older than N days
- Run after init_db in lifespan

### Task 4: Per-API-Key Rate Limiting
- Modify RateLimitMiddleware to use API key (from Authorization/X-API-Key header) as rate limit key when present
- Fall back to IP-based limiting for unauthenticated requests

### Task 5: Automatic Database Backups
- Add LU_BACKUP_INTERVAL_HOURS and LU_BACKUP_KEEP to config.py (default 0=disabled, keep=5)
- Background asyncio task in lifespan that runs every N hours
- Uses existing _create_backup() from backup.py, saves to backend/backups/
- Deletes oldest when count > keep limit

### Task 6: DB Retry Logic
- Create get_db_with_retry async generator in database.py
- On aiosqlite.OperationalError, retry up to 3 times with exponential backoff (0.1s, 0.5s, 1s)
- Replace get_db with the retry-aware version

### Execution: ALL COMPLETE
- [x] 1. Structured logging - JsonFormatter + LU_LOG_FORMAT + LU_LOG_LEVEL in lifespan
- [x] 2. Graceful shutdown - Enhanced lifespan: cancel backup task, stop monitors, drain buffers
- [x] 3. Log retention - _cleanup_old_logs on startup, LU_LOG_RETENTION_DAYS config
- [x] 4. Per-API-key rate limiting - RateLimitMiddleware uses key prefix when present
- [x] 5. Auto backups - _auto_backup_loop asyncio task, backend/backups/, prune old
- [x] 6. DB retry - get_db retries 3x with exponential backoff (0.1s, 0.3s, 0.9s)
- [x] 7. Tests: 15 new in test_phase9_features.py, 409 total passing
- [x] 8. Signal: backend-ready.signal created

## Claude-1 - Production Hardening (Post-Phase 8)

### Research Findings
- SQLite WAL mode enables concurrent reads/writes (critical for WebSocket + API + watcher threads)
- `PRAGMA synchronous = NORMAL` is safe with WAL, avoids fsync overhead
- `PRAGMA foreign_keys = ON` must be set per-connection (not persisted)
- `PRAGMA busy_timeout = 5000` prevents SQLITE_BUSY errors under concurrent access
- Blocking SQLite operations in async routes should use `asyncio.to_thread()`
- Log search pagination needs server-side limit caps to prevent OOM

### Fixes Applied
- [x] SQLite WAL mode + production pragmas in database.py init_db()
- [x] Per-connection foreign_keys + busy_timeout in database.py get_db()
- [x] backup.py: Fixed resource leak (try/finally on connections) + moved blocking I/O to asyncio.to_thread
- [x] logs.py: Capped search_logs limit at 1000, clamp negative offset to 0
- [x] 8 new tests in test_hardening_p9.py (backup safety, WAL mode, FK enabled, log caps, index verification)
- [x] Verification: 338 backend tests passing, 0 failures

## Claude-4 - Phase 8 Final Review (Session 2)

### Test Verification
- Backend: 295 passed, 0 failures, 0 skipped
- Frontend: 247 passed, 0 failures, 5 skipped (pre-existing)
- **Total: 542 tests, all green**

### Review Session 2 Fixes:
- [x] FolderBrowser.jsx: Fix setTimeout memory leak (clearTimeout on cleanup)
- [x] TemplateManager.jsx: Disable save button when name is empty
- [x] Sidebar.jsx: Add aria-label to search input for screen readers

### Review Session 2 Findings (no action needed):
- browseDirectory in api.js already uses request() helper (auth headers included) - reviewer false positive
- RateLimitMiddleware _requests dict keys accumulate but bounded by (IPs * endpoints) - negligible for localhost
- LogViewer virtual scroll scrollTop could be out of bounds after filter change - self-corrects on next scroll event
- Analytics race on projectId change already mitigated by cancelled flag pattern

## Claude-4 - Phase 8 Review Findings & Fixes (Session 1)

### Review Summary (4 subagent code reviews)
Issues found across browse.py, templates.py, FolderBrowser.jsx, main.py:

### Fixes Applied:
- [x] browse.py: Add MAX_DIRS=500 limit to prevent resource exhaustion on large directories
- [x] swarm.py: Guard `_pid_alive()` against pid<=0 edge case (PID 0 = process group on Unix)
- [x] templates.py: Add logging to silent JSON parse catch in `_row_to_dict()`
- [x] main.py: Wrap `_pid_alive()` in try/except in `_reconcile_running_projects()` for robustness
- [x] FolderBrowser.jsx: Add proper focus trap (Tab cycling, matching ConfirmDialog/AuthModal pattern)
- [x] FolderBrowser.jsx: Add `aria-modal="true"` and `aria-labelledby` for WCAG compliance
- [x] FolderBrowser.jsx: Consolidate Escape handler into `onKeyDown` (eliminates stale closure risk)
- [x] FolderBrowser.jsx: Add `aria-label` on directory buttons for screen readers
- [x] FolderBrowser.jsx: Clarify "new folder name" label to "Subfolder name (optional, will be appended to path)"
- [x] FolderBrowser.jsx: Add backdrop click-to-close (matching other modal patterns)
- [x] NewProject.jsx: Replace silent `.catch(() => {})` with `console.warn` for template load errors

### Documented but not fixed (acceptable for localhost tool):
- Symlink following in browse.py: `.resolve()` follows symlinks - intentional for a file browser
- Config field on templates accepts any dict: flexible by design (templates may store non-ProjectConfig keys)
- Response models on templates: nice-to-have, not critical for internal API

## Claude-2 - Frontend Build Plan

### Step 1: Project Initialization
- [ ] Create frontend/ with Vite + React + Tailwind CSS
- [ ] Configure vite proxy to localhost:8000 for API calls
- [ ] Set up project structure: components/, hooks/, lib/

### Step 2: Core Layout & Routing
- [ ] Build AppShell: dark sidebar + main content area
- [ ] Set up React Router: / (dashboard), /projects/new, /projects/:id
- [ ] Build ProjectSidebar component (list past/active swarms)

### Step 3: Project Creation Form
- [ ] Build NewProject page with 5 fields (goal, type, stack, complexity, requirements)
- [ ] Wire to POST /api/projects + POST /api/swarm/launch

### Step 4: Live Dashboard
- [ ] Build useWebSocket hook for ws://localhost:8000/ws
- [ ] Build DashboardView: task progress bar, agent heartbeats grid, signal states, activity feed
- [ ] Wire to GET /api/swarm/status/{id} for initial load, WebSocket for live updates

### Step 5: File Editor
- [ ] Build MarkdownEditor component (edit + preview) for TASKS.md and lessons.md
- [ ] Wire to GET/PUT /api/files/{path}

### Step 6: Swarm Controls
- [ ] Build SwarmControls: Launch/Stop buttons with status indicators
- [ ] Wire to POST /api/swarm/launch and /api/swarm/stop

### Step 7: Log Viewer
- [ ] Build LogViewer with auto-scroll and per-agent color coding
- [ ] Wire to GET /api/logs + WebSocket log events

### Step 8: Styling & Polish
- [ ] Apply "Latent Underground" aesthetic - dark mode, neural accent colors
- [ ] Responsive layout, loading states, error handling

### Step 9: Signal
- [ ] Verify frontend connects to backend end-to-end
- [ ] Create .claude/signals/frontend-ready.signal

## Claude-3 - Phase 5 Test Plan

### Task 1: E2E Full Project Lifecycle Test (backend) - DONE
- [x] Write test_lifecycle.py: 7 tests (complete lifecycle, multi-run, config round-trip, stop safety, empty history, agent status, file ops)

### Task 2: Accessibility Tests (frontend) - DONE
- [x] Write accessibility.test.jsx: 41 tests across 8 describe blocks
- [x] ConfirmDialog (7), TaskProgress (6), ThemeToggle (3), ProjectView tabs (8), Sidebar (6), NewProject (6), SwarmControls (4), TerminalOutput (1)

### Task 3: Environment Config Tests (backend) - DONE
- [x] Write test_env_config.py: 19 tests (defaults, env overrides, dotenv loading, .env.example validation)

### Task 4: Docker Tests (backend) - DONE
- [x] Write test_docker.py: 17 tests (Dockerfile structure, compose structure, .dockerignore)

### Task 5: Swarm Template CRUD Tests (backend) - SCAFFOLD DONE
- [x] Write test_templates.py: 11 tests (skip until Claude-1 implements templates table)

### Task 6: Final Verification - DONE
- [x] Backend: 203 passed, 11 skipped (templates scaffold)
- [x] Frontend: 170 passed
- [x] Total: 373 tests, zero failures
- [x] tests-passing.signal created

## Claude-3 - Phase 6 Test Plan

### Step 1: Health endpoint tests (test_health.py) - DONE
- [x] test_health_ok - 200 with status=ok, db=ok
- [x] test_health_has_all_fields - response has {status, db, app, version}
- [x] test_health_degraded_on_db_failure - patch aiosqlite.connect, expect 503

### Step 2: Phase 6 hardening tests (test_phase6_hardening.py) - DONE
- [x] SwarmLaunchValidation: agent_count/max_phases boundary + rejection (5 tests)
- [x] ProjectCreateValidation: empty name, long name, long goal, empty folder_path (4 tests)
- [x] BufferLockExists: _buffers_lock type, _MAX_OUTPUT_LINES, MAX_CONTENT_SIZE (3 tests)

### Step 3: Skipped backend tests - DONE
- [x] test_project_search.py: 10 tests (search, filter, sort, combined) - all skipped
- [x] test_analytics.py: 4 tests (empty, not found, aggregation, fields) - all skipped
- [x] test_log_search.py: 7 tests (text, agent, level, combined, pagination) - all skipped

### Step 4: Frontend tests - DONE
- [x] phase6-components.test.jsx: 23 real tests (useHealthCheck 3, Sidebar Search 5, Sidebar Status Filter 3, useNotifications 4, LogViewer Search 3, Analytics Tab 3, Analytics Component 3)
- [x] phase6-api.test.js: 5 tests (searchProjects, getProjectAnalytics, searchLogs) - skipped
- [x] Fixed truncated file from Claude-2, completed useNotifications tests
- [x] Fixed requestPermission test (permission='default' to trigger actual call)
- [x] Fixed notify test (mock document.hasFocus=true)
- [x] Fixed Analytics "Total Runs" duplicate text (getAllByText)

### Step 5: Pre-existing test fixes - DONE
- [x] phase3-components: max_phases default 3→24 (2 assertions)
- [x] ProjectSettings.jsx: input max=20→24 (HTML5 validation blocked form submit)
- [x] components.test.jsx: getByText('All')→getAllByText('All') (duplicate button)
- [x] performance.test.jsx: same "All" button fix

### Step 6: Verification - DONE
- [x] Backend: 229 passed, 21 skipped = 250 total
- [x] Frontend: 196 passed, 5 skipped = 201 total
- [x] Grand total: 425 passing + 26 skipped = 451 tests, zero failures
- [x] tests-passing.signal created

## Claude-2 - Phase 6 Frontend Features (COMPLETE)

### Task 5: Health Status Indicator - DONE
- [x] Created useHealthCheck.js hook (polls /api/health every 30s, measures latency)
- [x] Updated App.jsx header with combined health+WS indicator + hover tooltip

### Task 1: Project Search + Status Filter - DONE
- [x] Added search input + status filter buttons to Sidebar.jsx
- [x] Client-side filtering by name/goal + status, "No matching projects" empty state

### Task 4: Browser Notifications - DONE
- [x] Created useNotifications.js hook, integrated in App.jsx + SwarmControls.jsx

### Task 3: Log Search Improvements - DONE
- [x] Added search, level filter, copy, download to LogViewer.jsx

### Task 2: Analytics Tab - DONE
- [x] Created Analytics.jsx (summary chips + 3 SVG charts), added as 7th tab
- [x] Updated tab count in phase5/accessibility tests (6->7)

### Verification - DONE
- [x] 23 new tests, 196 total passing, zero failures
- [x] Production build: 441KB JS + 34KB CSS + 179KB highlight.js

## Claude-1 - Phase 5 Plan (COMPLETE)
All Phase 5 tasks done. See TASKS.md.

## Claude-1 - Production Hardening Plan (COMPLETE)
- [x] 1. Thread safety on output buffers (swarm.py) - added _buffers_lock
- [x] 2. Input validation on SwarmLaunchRequest (swarm.py) - Field(ge=1, le=16/20)
- [x] 3. Input validation on ProjectCreate/ProjectUpdate (project.py) - min/max_length
- [x] 4. Health check with database probe (main.py) - SELECT 1, 503 on failure
- [x] 5. Fix data loss on swarm stop (swarm.py) - join threads before pop
- [x] 6. Add logging to silent exception handlers (websocket.py, swarm.py) - logger.debug
- [x] 7. Run full test suite - 214 backend + 173 frontend = 387 passing, zero failures

## Claude-1 - Phase 7 Plan (COMPLETE)
- [x] 1. Database indexes: projects(status), swarm_runs(project_id, started_at), swarm_runs(status)
- [x] 2. Fix swarm-phase.json MaxPhases=3 → 24
- [x] 3. Log search date range filter: from_date/to_date params with timestamp parsing
- [x] 4. Swarm stdin input: POST /api/swarm/input, _swarm_processes dict, stdin=PIPE, echo to buffer
- [x] 5. WebSocket log streaming: incremental file position tracking in watcher.py
- [x] 6. API key auth middleware: LU_API_KEY, Bearer/X-API-Key headers, skip health/docs/ws
- [x] 7. Verification: 250 backend tests passing, 0 failures, backend-ready.signal created

## Claude-1 - Phase 8 Plan

### Assessment
1. Templates CRUD - ALREADY DONE (templates.py exists with full CRUD, table in DB, routes in main.py)
2. Process reconnection - Enhance startup to monitor alive PIDs via background thread
3. Swarm output pagination - Add `limit` param with capping
4. Fix flaky tests - Change sample_project_data/minimal fixtures to use tmp_path
5. Rate limiting - Add configurable rate limiting middleware for POST endpoints
6. Signal - Create backend-ready.signal after verification

### Execution - ALL COMPLETE
- [x] 1. Verify templates CRUD works - already implemented, unskipped 11 tests
- [x] 2. Process reconnection - _monitor_pid thread, sync sqlite3, DB_PATH dynamic lookup
- [x] 3. Output pagination - limit param, total/has_more fields, capped at _MAX_OUTPUT_LINES
- [x] 4. Fix flaky tests - conftest fixtures use tmp_path, test_projects.py assertion updated
- [x] 5. Rate limiting - RateLimitMiddleware, configurable RPM via LU_RATE_LIMIT_RPM, rpm=0 disables
- [x] 6. Verification - 295 backend tests passing, 0 failures, backend-ready.signal created
- [x] 7. DB_PATH scoping fix - database.DB_PATH dynamic lookup in main.py (reconciliation+health)
- [x] 8. Reconciliation test fix - removed stale patch("app.main.DB_PATH") after refactor

## Claude-2 - Phase 9 Plan (COMPLETE)

### Task Assessment
- Project export: ALREADY DONE (Dashboard.jsx handleExport, line 97-117)
- Remaining: 6 tasks + signal

### Execution: ALL COMPLETE
- [x] 1. Toast enhancement - addToast accepts optional `action` {label, onClick} param; error toasts with action get 10s duration
- [x] 2. Keyboard shortcut registry - KEYBOARD_SHORTCUTS constant in constants.js + ShortcutCheatsheet.jsx modal (grouped, kbd elements)
- [x] 3. Settings panel - SettingsPanel.jsx (slide-in right panel, 4 sections: Appearance, Auth, Notifications, System Info)
- [x] 4. Default template presets - DEFAULT_TEMPLATE_PRESETS in constants.js (Quick Research, Code Review, Feature Build, Debugging)
- [x] 5. First-run onboarding - OnboardingModal.jsx (3-step carousel, localStorage lu_onboarding_complete)
- [x] 6. Retry toasts - Dashboard, SwarmControls, NewProject all show retry action on API errors
- [x] 7. Signal - .claude/signals/frontend-ready.signal created
- [x] 8. App.jsx integration - Ctrl+?, gear icon, keyboard icon in top bar, onboarding auto-show on empty
- [x] 9. Tests - 37 new tests in phase9-components.test.jsx, 347 total frontend passing (was 310)
- [x] 10. Build - 481KB JS + 39KB CSS + 179KB highlight.js, zero warnings

### New Components (4)
- SettingsPanel.jsx: Slide-in right panel, theme/auth/notifications/system info sections
- ShortcutCheatsheet.jsx: Modal with grouped keyboard shortcuts, kbd elements
- OnboardingModal.jsx: 3-step carousel welcome modal with localStorage persistence
- (Toast.jsx enhanced, not new)

### New Constants
- KEYBOARD_SHORTCUTS: 7 shortcuts in 3 groups (Navigation, Actions, Views)
- DEFAULT_TEMPLATE_PRESETS: 4 presets (Quick Research, Code Review, Feature Build, Debugging)

### Files Modified (11)
- Toast.jsx: action button support
- App.jsx: Settings, Shortcuts, Onboarding integration + Ctrl+? + gear/keyboard icons
- NewProject.jsx: "Load defaults" for template presets + retry toasts
- Dashboard.jsx: retry toasts on refresh/export failure
- SwarmControls.jsx: retry toasts on launch/stop failure
- constants.js: KEYBOARD_SHORTCUTS + DEFAULT_TEMPLATE_PRESETS
- components.test.jsx: ToastProvider wrapper for NewProject, createTemplate mock
- accessibility.test.jsx: ToastProvider wrapper for NewProject, createTemplate mock
- phase8-components.test.jsx: getAllByText for duplicate error text

## Claude-2 - Phase 8 Plan (COMPLETE)

### Task 1: Debounced Search (300ms) - DONE
- [x] Created `useDebounce` hook in `frontend/src/hooks/useDebounce.js`
- [x] Applied to LogViewer search input (debouncedSearch for client-side + server-side filtering)
- [x] Applied to Sidebar search input (debouncedSearch for project filtering)

### Task 2: Sparkline Graphs Enhancement - DONE
- [x] Added run duration trend sparkline to Dashboard (amber color, alongside task completion sparkline)

### Task 3: Virtualized Log Rendering - DONE
- [x] Implemented custom virtual scroll in LogViewer for 200+ lines
- [x] Fixed row height (22px), only render visible rows + 15-row overscan buffer
- [x] Below threshold: normal rendering for small lists (backward compatible with tests)

### Task 4: Loading States - DONE
- [x] Added LogViewerSkeleton, HistorySkeleton, AnalyticsSkeleton to Skeleton.jsx
- [x] Applied to SwarmHistory and Analytics loading states
- [x] Added fade-in animation + applied to tab panel transitions in ProjectView

### Task 5: Template Management - DONE
- [x] Added template CRUD API calls (create, update, delete) to api.js
- [x] Created TemplateManager component (list/create/edit/delete)
- [x] Integrated into NewProject with "Manage Templates" toggle

### Task 6: Signal - DONE
- [x] Created .claude/signals/frontend-ready.signal

### Verification
- [x] 247 frontend tests passing + 5 skipped, zero failures
- [x] Production build: 462KB JS + 37KB CSS + 179KB highlight.js
- [x] All pre-existing tests pass (fixed ResizeObserver polyfill, debounce waitFor, searchLogs mock)

## Claude-3 - Phase 7 Test Plan

### Task 1: Stdin input endpoint tests (test_swarm_input.py) - DONE
- [x] 8 tests: not found, not running, no process, process exited, success, echo buffer, broken pipe, text too long

### Task 2: Auth middleware tests (test_auth_middleware.py) - DONE
- [x] 8 tests: disabled, valid Bearer, valid X-API-Key, invalid key, missing key, health bypass, docs bypass, non-API bypass

### Task 3: Database index tests (test_database_indexes.py) - DONE
- [x] 3 tests: indexes created, columns correct, idempotent

### Task 4: Log search date range tests (test_log_date_range.py) - DONE
- [x] 7 tests: from_date, to_date, both, invalid from, invalid to, date-only format, no-timestamp included

### Task 5: Frontend tests (phase7-components.test.jsx + phase7-api.test.js) - DONE
- [x] TerminalInput: 8 tests (render, disabled, enabled, send button, Enter key, echo, error, clear)
- [x] AuthModal: 8 tests (hidden, visible, save, clear, cancel, Esc, Enter, stored key)
- [x] LogViewer date range: 3 tests (inputs, clear button, searchLogs call)
- [x] Live log indicator: 2 tests (LIVE shown, ws lines appended)
- [x] Keyboard shortcuts: 2 tests (Ctrl+N, Escape)
- [x] API functions: 8 tests (sendSwarmInput, Bearer header, 401, searchLogs params, auth helpers)

### Task 6: Verification - DONE
- [x] Backend: 276 passed (250 existing + 26 new), zero failures
- [x] Frontend: 227 passed + 5 skipped (196 existing + 31 new), zero failures
- [x] Grand total: 503 passing, 0 failures
- [x] tests-passing.signal updated
- [x] TASKS.md marked complete
