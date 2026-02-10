# Latent Underground - Task Board (Phase 10)

## Claude-1 [Backend/Core] - Plugin system and API refinements

- [x] Add plugin system: load custom swarm configs from plugins/ directory
- [x] Add webhook notifications: configurable POST webhooks on swarm events (start, stop, error)
- [x] Add project archival: archive completed projects to reduce dashboard clutter
- [x] Add API versioning: /api/v1/ prefix, deprecation headers on current /api/ routes
- [x] Optimize SQLite queries: EXPLAIN ANALYZE on hot paths, add missing indexes
- [x] Add request/response logging middleware: log method, path, status, duration (JSON format)
- [x] Signal: Create .claude/signals/backend-ready.signal

### Claude-1 Implementation Summary
- **Plugin system**: PluginManager with JSON-based plugin discovery, CRUD API at /api/plugins, enable/disable, create/delete
- **Webhooks**: webhooks DB table, CRUD at /api/webhooks, HMAC-SHA256 signing, async delivery with retry, events emitted on swarm launch/stop/crash
- **Project archival**: archived_at column, POST /archive and /unarchive endpoints, list_projects excludes archived by default
- **API versioning**: /api/v1/ prefix rewrites to /api/ (full backward compat), deprecation headers on unversioned /api/ routes
- **SQLite optimization**: mmap_size=256MB, ANALYZE on init, 3 new composite indexes (swarm_runs project+ended, templates created, webhooks enabled)
- **Request logging**: RequestLoggingMiddleware logs method, path, status, duration_ms (disabled by default, LU_REQUEST_LOG=true to enable)
- **Tests**: 466 backend tests passing (421 existing + 45 new), zero failures

## Claude-2 [Frontend/Interface] - Settings, onboarding, and final polish

- [x] Add Settings panel: theme toggle, rate limit display, API key rotation, log retention config
- [x] Add keyboard shortcut reference: Ctrl+? opens cheatsheet modal with all shortcuts
- [x] Add project export: download project config + run history as JSON from ProjectView
- [x] Add default template presets: Quick Research, Code Review, Feature Build, Debugging
- [x] Improve error display: toast notifications for all API errors with retry action button
- [x] Add first-run onboarding: welcome modal on empty project list with setup guide
- [x] Optimize bundle size: analyze with rollup-plugin-visualizer, lazy-load heavy components
- [x] Signal: Create .claude/signals/frontend-ready.signal

## Claude-3 [Integration/Testing] - Final QA and release testing

- [x] Add integration tests for plugin system: load, validate, apply custom configs
- [x] Add webhook notification tests: mock HTTP endpoints, verify payloads
- [x] Add bundle size regression tests: fail CI if JS bundle exceeds 500KB
- [x] Add load testing: simulate 10 concurrent projects with status polling
- [x] Run full accessibility audit: manual checklist + automated axe-core on all views
- [x] Write upgrade guide: migration from Phase 9 to Phase 10 (if schema changes)
- [x] Signal: Create .claude/signals/tests-passing.signal

### Claude-3 Implementation Summary
- **Plugin integration tests**: 15 tests (filesystem discovery, schema validation, config application, hooks aggregation, full lifecycle)
- **Webhook integration tests**: 16 tests (HMAC verification, delivery mock with retry, event filtering, emit integration, API edge cases)
- **Bundle size regression**: 6 tests (main JS < 300KB, total JS < 500KB, CSS < 50KB, no oversized lazy chunks, code splitting verification)
- **Load testing**: 10 tests (concurrent project CRUD, status polling, archive ops, webhook ops, mixed operations)
- **Accessibility audit**: 15 tests (axe-core + ARIA + focus trap + keyboard nav for SettingsPanel, ShortcutCheatsheet, OnboardingModal)
- **Upgrade guide**: UPGRADE.md documenting schema changes, new env vars, API versioning, migration steps
- **OnboardingModal fix**: Step indicator dots changed from div to span[role="img"] for axe-core compliance
- **Tests**: 890 total (507 backend + 383 frontend), zero failures, +77 new tests

## Claude-4 [Polish/Review] - v1.0 release gate

- [x] Review all Phase 10 code changes for quality and consistency
- [x] Verify no regressions: all Phase 9 tests still pass (768 total: 421 backend + 347 frontend)
- [x] Final security review: comprehensive audit - 0 CRITICAL, 0 HIGH, 4 MEDIUM (all acceptable for localhost tool)
- [x] Create CHANGELOG.md: document all features from Phase 1-10
- [x] FINAL: Generate next-swarm.ps1 for Phase 11 (backend tasks deferred)

### Claude-4 Review Summary
- **Frontend review**: 5 issues found (1 critical Toast timeout leak, 4 high a11y/pattern issues) - ALL FIXED
- **Security audit**: 0 blocking issues. 4 MEDIUM defense-in-depth items for future phases
- **Backend review**: No Phase 10 changes to review (Claude-1 inactive)
- **Test verification**: 768 total (421 backend + 347 frontend), zero failures, zero regressions
- **Fixes applied**: Toast timeout cleanup, OnboardingModal useCallback pattern, SettingsPanel ConfirmDialog
- **CHANGELOG.md**: Created with full Phase 1-10 history in Keep a Changelog format

## Completion Criteria
- [x] Settings panel accessible from UI header
- [x] Keyboard shortcut reference modal
- [x] Plugin system loads custom swarm configs
- [x] First-run onboarding guides new users
- [x] All tests pass (890 total: 507 backend + 383 frontend), zero regressions
- [x] Bundle size under 500KB JS
- [x] CHANGELOG.md documents all features
