# Latent Underground - Task Board (Phase 11)

## Claude-1 [Backend/Core] - Webhooks, archival, and middleware

- [x] Implement webhook notification routes: CRUD at /api/webhooks + event dispatching on swarm start/stop/error (HMAC-SHA256 signing, SSRF protection, async retry delivery)
- [x] Add project archival: POST /api/projects/{id}/archive + /unarchive, filtered from default listing, include_archived param
- [x] Add request/response logging middleware: RequestLoggingMiddleware logs method, path, status, duration_ms (LU_REQUEST_LOG=true, JSON format when LU_LOG_FORMAT=json)
- [x] Add security headers middleware: SecurityHeadersMiddleware adds X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Referrer-Policy, X-XSS-Protection: 0, Cache-Control: no-store on API
- [x] Add global exception handlers: RequestValidationError→422 (structured errors), OperationalError→503, generic Exception→500 (with full traceback logging)
- [x] Run dependency audit: pip-audit found 0 known vulnerabilities (551 tests passing)
- [x] Signal: .claude/signals/backend-ready.signal created

## Claude-2 [Frontend/Interface] - Webhook UI, archival, and code splitting

- [x] Add webhook management UI: list/create/edit/delete webhooks per project in ProjectSettings (WebhookManager.jsx with full CRUD, LED indicators, event toggles, ConfirmDialog)
- [x] Add project archive/unarchive toggle in project list and ProjectView (Sidebar hover buttons + Dashboard header button with archive icon)
- [x] Implement route-level code splitting: React.lazy() + Suspense for Analytics, LogViewer, SwarmHistory, TemplateManager (App.jsx + ProjectView.jsx lazy-load 12 chunks)
- [x] Lazy-load highlight.js (179KB) on demand instead of at bundle time (FileEditor dynamically imports rehype-highlight; manualChunks splits to 177KB lazy chunk)
- [x] Add dependency badge showing version in Settings panel (replace hardcoded "v0.1") (__APP_VERSION__ via vite define from package.json v0.11.0, shown in SettingsPanel + Sidebar)
- [x] Add confirmation before navigating away from unsaved settings changes (beforeunload + isDirty detection in ProjectSettings with visual "Unsaved changes" indicator)
- [x] Signal: .claude/signals/frontend-ready.signal created (383 tests passing, 246KB main bundle, 12 lazy chunks)

## Claude-3 [Integration/Testing] - Webhook tests, archival tests, security tests

- [x] Add webhook notification tests: 21 tests in test_webhook_integration.py (16 existing + 5 new HMAC edge cases)
- [x] Add project archival tests: 15 tests in test_archival_lifecycle.py (lifecycle, edge cases, history with swarm_runs, include_archived param)
- [x] Add request logging middleware tests: 10 tests in test_request_logging.py (log format, duration, extras)
- [x] Add security header tests: 13 tests in test_security_headers.py (5 headers on GET/POST/PATCH/DELETE/404/422)
- [x] Add bundle size regression test: 6 tests in bundle-size.test.js (main<300KB, total<500KB)
- [x] Add load testing: 13 tests in test_load.py (10 existing + 3 new concurrent status/health polls)
- [x] Add exception handler tests: 8 tests in test_exception_handlers.py (422 structured, 503 db error, 500 generic, no info leaks)
- [x] Signal: .claude/signals/tests-passing.signal created (944 total tests, zero failures)

## Claude-4 [Polish/Review] - v1.0 release preparation

- [x] Review all Phase 11 code changes for quality and consistency
- [x] Verify no regressions: 944 tests pass (561 backend + 383 frontend), zero failures
- [x] Security review of webhook implementation (HMAC signing, URL validation, timeout on outbound requests)
- [x] Update CHANGELOG.md with Phase 11 features (version 0.11.0)
- [x] Verify code splitting reduces initial bundle size below 300KB (246KB main chunk)
- [x] FINAL: Generate next-swarm.ps1 for Phase 12 (needs E2E, performance, CI/CD before v1.0)

### Claude-4 Review Fixes:
- Backend version synced 0.1.0 -> 0.11.0 (main.py + test_health.py)
- WebhookManager.jsx: mountedRef prevents state updates after unmount
- CHANGELOG.md: Accurate test count (944), all Phase 11 features documented

### Security Review Summary:
- HMAC-SHA256: Correct (_sign_payload + sha256= prefix header)
- SSRF: Blocks localhost, private IPs, non-http schemes, reserved ranges
- Timeouts: 10s per delivery, 3 retries with 1s/2s backoff
- Secrets: Not exposed in API responses (has_secret boolean only)
- Exception handlers: No info leakage (generic 500 message, traces logged server-side only)

## Completion Criteria
- [x] Webhook CRUD API + event dispatching works end-to-end
- [x] Project archival reduces dashboard clutter
- [x] Security headers present on all API responses
- [x] Request logging captures method/path/status/duration
- [x] Route-level code splitting implemented
- [x] All tests pass (target: 800+), zero regressions - ACTUAL: 944
- [x] CHANGELOG.md updated with Phase 11 features
