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
- [x] Add project archival tests: 13 tests in test_archival_lifecycle.py (full lifecycle, edge cases, history)
- [x] Add request logging middleware tests: 10 tests in test_request_logging.py (log format, duration, extras)
- [x] Add security header tests: 13 tests in test_security_headers.py (5 headers on GET/POST/PATCH/DELETE/404/422)
- [x] Add bundle size regression test: 6 tests in bundle-size.test.js (main<300KB, total<500KB)
- [x] Add load testing: 13 tests in test_load.py (10 existing + 3 new concurrent status/health polls)
- [x] Signal: .claude/signals/tests-passing.signal created (934 total tests, zero failures)

## Claude-4 [Polish/Review] - v1.0 release preparation

- [ ] Review all Phase 11 code changes for quality and consistency
- [ ] Verify no regressions: all Phase 10 tests still pass (768+)
- [ ] Security review of webhook implementation (HMAC signing, URL validation, timeout on outbound requests)
- [ ] Update CHANGELOG.md with Phase 11 features
- [ ] Verify code splitting reduces initial bundle size below 300KB
- [ ] FINAL: If all features complete, tag v1.0.0 release; otherwise generate next-swarm.ps1 for Phase 12

## Completion Criteria
- [ ] Webhook CRUD API + event dispatching works end-to-end
- [ ] Project archival reduces dashboard clutter
- [ ] Security headers present on all API responses
- [ ] Request logging captures method/path/status/duration
- [ ] Route-level code splitting implemented
- [ ] All tests pass (target: 800+), zero regressions
- [ ] CHANGELOG.md updated with Phase 11 features
