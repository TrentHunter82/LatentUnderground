# Latent Underground - Task Board (Phase 9)

## Claude-1 [Backend/Core] - Error handling, resilience, and operations

- [x] Add structured logging: JSON log format to stdout, configurable via LU_LOG_FORMAT (json|text)
- [x] Add automatic database backups: configurable interval (LU_BACKUP_INTERVAL_HOURS), keep last N backups
- [x] Add graceful shutdown: SIGTERM handler that stops PID monitors, drains output buffers, closes DB cleanly
- [x] Add log retention policy: configurable max age (LU_LOG_RETENTION_DAYS), auto-cleanup on startup
- [x] Add per-API-key rate limiting: track rate limits per API key instead of per IP only
- [x] Add retry logic for transient DB failures: aiosqlite connection retry with exponential backoff
- [x] Signal: Create .claude/signals/backend-ready.signal

## Claude-2 [Frontend/Interface] - Settings, onboarding, and UX polish

- [x] Add Settings panel: theme toggle, rate limit display, API key rotation, log retention config — SettingsPanel.jsx (slide-in panel, 4 sections, focus trap)
- [x] Add keyboard shortcut reference: Ctrl+? opens cheatsheet modal with all shortcuts — ShortcutCheatsheet.jsx + KEYBOARD_SHORTCUTS constant
- [x] Add project export: download project config + run history as JSON from ProjectView — (already existed in Dashboard.jsx handleExport)
- [x] Add default template presets: Quick Research, Code Review, Feature Build, Debugging — DEFAULT_TEMPLATE_PRESETS in constants.js, "Load defaults" button in NewProject
- [x] Improve error display: toast notifications for all API errors with retry action button — Toast.jsx enhanced with action param, retry buttons on Dashboard/SwarmControls/NewProject
- [x] Add first-run onboarding: welcome modal on empty project list with setup guide — OnboardingModal.jsx (3-step carousel, localStorage persistence)
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - E2E tests and quality assurance

- [x] Add E2E test suite: complete project lifecycle (create, launch, stop, view logs, delete) — 20 tests in test_e2e_phase9.py
- [x] Add API contract tests: verify all frontend API calls match backend OpenAPI schema — 48 tests in test_api_contracts.py (28 endpoint existence + 8 response shapes + 8 field types + 4 pagination edge cases)
- [x] Add performance benchmarks: log render time for 1000+ lines, API response time under load — 7 perf tests in phase9-quality.test.jsx
- [x] Add accessibility audit: axe-core automated checks on all page views — 23 axe-core tests via vitest-axe (NewProject, TemplateManager, FolderBrowser, ConfirmDialog, Sparkline, ErrorBoundary, TaskProgress, AgentGrid, SignalPanel, SwarmHistory, SwarmControls, Sidebar)
- [x] Add error boundary tests: verify ErrorBoundary catches and displays errors in all routes — 10 tests (catch, recover, retry, nested)
- [x] Add template lifecycle tests: create template, apply to project, verify config applied — 3 tests in test_e2e_phase9.py
- [x] Add browse endpoint tests (Phase 8 gap) — 26 tests in test_browse.py
- [x] Add Phase 8 edge case tests: templates, reconciliation, FolderBrowser, useDebounce — 32+ tests
- [x] Signal: Create .claude/signals/tests-passing.signal — 731 total (421 backend + 310 frontend), zero failures

## Claude-4 [Polish/Review] - Final quality gate

- [x] Review all Phase 9 code changes for quality and consistency
- [x] Verify no regressions: all Phase 8 tests still pass (542+) — 731 total (421 backend + 310 frontend), zero failures
- [x] Security audit: check all new endpoints for input validation, auth bypass, injection
- [x] Write production deployment guide: docker-compose.prod.yml, SSL, reverse proxy, systemd
- [x] FINAL: Generate next-swarm.ps1 for Phase 10 or mark project v1.0 production-ready

### Review Fixes Applied:
- [x] database.py: Remove unused `from pathlib import Path` import
- [x] main.py: Wrap log retention glob in OSError protection (prevents crash on deleted project folders)

### Review Findings (documented, no action needed for localhost tool):
- WebSocket intentionally unauthenticated (broadcast-only, localhost)
- Browse API allows full filesystem browsing (intended behavior for file picker)
- Rate limiter dict growth bounded by (unique clients * endpoints) - negligible for localhost
- Log search collects all matches before pagination - acceptable for local project log sizes
- JsonFormatter lacks timezone - acceptable for single-server localhost tool

## Completion Criteria
- [x] Structured JSON logging configurable via environment
- [x] Automatic database backups with retention policy
- [x] Settings panel accessible from UI header — gear icon in top bar opens SettingsPanel
- [x] Keyboard shortcut reference modal — Ctrl+? or keyboard icon in top bar
- [x] E2E tests cover critical user flows
- [x] All tests pass (backend + frontend), zero regressions
