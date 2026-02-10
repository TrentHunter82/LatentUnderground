# Latent Underground - Task Board (Phase 8)

## Claude-1 [Backend/Core] - Templates CRUD, process reconnection, performance

- [x] Add swarm templates CRUD: POST/GET/PATCH/DELETE /api/templates with name, description, config JSON
- [x] Add process reconnection on restart: store PID+folder in DB, attempt to reattach stdout/stderr pipes on startup (if process still alive)
- [x] Add swarm output pagination: GET /api/swarm/output/{id}?offset=&limit= with proper capping
- [x] Fix flaky tests: Replace hardcoded "F:/TestProject" in sample_project_data with tmp_path
- [x] Add rate limiting: configurable requests-per-minute on POST endpoints (prevent accidental rapid launches)
- [x] Signal: Create .claude/signals/backend-ready.signal

## Claude-2 [Frontend/Interface] - Templates UI, sparklines, performance polish

- [x] Add template selector: dropdown in NewProject to apply saved configs, template management page
- [x] Add sparkline graphs in Dashboard: task completion trend, run duration trend (lightweight SVG)
- [x] Add virtualized log rendering: react-window or virtual scroll for 1000+ lines in LogViewer
- [x] Add debounced search: 300ms debounce on search text input in LogViewer and Sidebar
- [x] Improve loading states: skeleton placeholders while data loads, smooth transitions
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - Test coverage for Phase 8 features

- [x] Add tests for templates CRUD API (create, list, get, update, delete, not found) — 11 tests in test_templates.py (by Claude-1)
- [x] Add tests for process reconnection (alive PID reattach, dead PID cleanup) — 6 tests in test_reconciliation.py
- [x] Add tests for swarm output pagination (offset, limit, empty buffer) — 13 tests in test_output_pagination.py
- [x] Fix flaky tests: Migrate all test fixtures from hardcoded paths to tmp_path — 10 paths fixed across 5 files
- [x] Add frontend tests for template selector, sparklines, virtualized log — 20 tests in phase8-components.test.jsx
- [x] Signal: Create .claude/signals/tests-passing.signal — 542 total (295 backend + 247 frontend)

## Claude-4 [Polish/Review] - Final quality gate

- [x] Review all Phase 8 code changes for quality and consistency — 4 subagent reviews, 11 fixes applied
- [x] Verify no regressions: all Phase 7 tests still pass (503+) — 542 total, 0 failures
- [x] Accessibility review: keyboard nav, screen reader support, ARIA on new components — FolderBrowser hardened
- [x] Performance profiling: virtualized LogViewer handles 1000+ lines, browse API capped at 500 dirs
- [x] FINAL: Generate next-swarm.ps1 for Phase 9

## Completion Criteria
- [x] Swarm templates can be created, saved, and applied to new projects
- [x] Server restart reconnects to running swarm processes (no orphaned processes)
- [x] Dashboard shows sparkline trend graphs for key metrics
- [x] Log viewer handles 1000+ lines without UI lag (virtual scroll + ResizeObserver)
- [x] All tests pass (backend + frontend), zero flaky tests — 542 total, 0 failures
