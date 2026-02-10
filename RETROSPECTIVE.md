# Latent Underground - v1.0 Retrospective

## Project Summary

**Latent Underground** is a swarm orchestration dashboard for managing multi-agent AI development workflows. It provides a retro-futuristic web interface for launching, monitoring, and reviewing Claude Code swarm sessions.

Built across 12 development phases by a 4-agent swarm (Backend, Frontend, Testing, Review), the project demonstrates autonomous multi-agent software development at scale.

## Architecture

- **Backend**: Python FastAPI + SQLite (async via aiosqlite), managed with `uv`
- **Frontend**: React 19 + Vite 7 + Tailwind CSS, retro-futuristic analog design
- **Real-time**: WebSocket for live events, SSE for output streaming
- **Security**: API key auth, CORS, security headers, SSRF protection, rate limiting

## The Journey: Phase by Phase

### Phase 1 - Foundation
FastAPI backend with SQLite, project CRUD, swarm launch/stop, WebSocket events, filesystem watcher. The core loop: create project -> launch swarm -> monitor via WS -> stop.

### Phase 2 - Frontend
16 React components, dark theme, WebSocket hook with exponential backoff, ErrorBoundary, ConfirmDialog with focus trap, static file serving from FastAPI. **195 tests.**

### Phase 3 - History & Monitoring
Swarm run history table, SSE output streaming, project stats, agent config, 6-tab ProjectView (Overview, Terminal, History, Settings, Files, Logs). **266 tests.**

### Phase 4 - Design
Complete retro-futurism UI redesign: analog control panel aesthetic, mint/teal/crimson/orange palette, 3D jewel-cap LEDs, chrome bezels, Space Mono + JetBrains Mono typography.

### Phase 5 - Deployment
Docker multi-stage build, .env configuration, database backup endpoint, CI test script. **373 tests.**

### Phase 6 - Discovery
Project search/filter, analytics with SVG charts, log search, health check, OpenAPI docs, browser notifications. **387 tests.**

### Phase 7 - Interaction
Stdin input for running swarms, API key authentication, database indexes, date range filtering, keyboard shortcuts (Ctrl+K, Ctrl+N, Escape). **503 tests.**

### Phase 8 - Templates & Performance
Template CRUD, filesystem browser, process reconnection on restart, output pagination, rate limiting, debounced search, sparklines, virtual scroll. **542 tests.**

### Phase 9 - Production Hardening
Structured logging (JSON/text), auto backups, graceful shutdown, log retention, per-API-key rate limiting, DB retry with exponential backoff, SQLite WAL mode. **731 tests.**

### Phase 10 - Extensibility
Plugin system with JSON discovery, webhook notifications (HMAC-SHA256), project archival, API versioning (/api/v1/), request logging middleware. Code splitting reduced bundle 49% (481KB -> 245KB). **890 tests.**

### Phase 11 - Security
Security headers middleware, global exception handlers (422/503/500), webhook SSRF protection, WebhookManager UI, archive toggle, version badge, unsaved changes confirmation. **934 tests.**

### Phase 12 - v1.0 Release
GZip compression, connection pooling, per-endpoint rate limiting (read vs write), retry with jitter, WebSocket reconnection banner, error recovery UI, print stylesheet, React.memo() optimization, comprehensive E2E and integration testing. **1165 tests.**

## Final Metrics

| Metric | Value |
|--------|-------|
| Total Tests | 1165 (685 backend + 480 frontend) |
| Test Failures | 0 |
| Main Bundle Size | 246 KB |
| Lazy Chunks | 15 |
| CSS Size | 40 KB |
| Source Maps | None (production) |
| Security Issues | 0 CRITICAL, 0 HIGH |
| API Endpoints | 30+ |
| React Components | 25+ |
| Development Phases | 12 |
| Agent Roles | 4 (Backend, Frontend, Testing, Review) |

## Key Technical Decisions

1. **SQLite over PostgreSQL**: Perfect for a localhost tool. WAL mode handles concurrent reads/writes well. Connection pooling added in Phase 12 for performance.

2. **FastAPI over Flask/Django**: Async-first, automatic OpenAPI docs, Pydantic validation, excellent for real-time features (WebSocket, SSE).

3. **React + Vite over Next.js**: SPA served from FastAPI eliminates CORS complexity. Vite provides fast builds and code splitting. No SSR needed for a localhost tool.

4. **Retro-futuristic design**: Distinctive visual identity that makes the tool memorable. Analog control panel metaphor maps well to monitoring/operations UI.

5. **Progressive enhancement**: Started with basic CRUD (Phase 1), added real-time (Phase 3), search/analytics (Phase 6), and polish (Phases 10-12) incrementally.

## Lessons Learned

### Process
- **4-agent swarm works**: Backend, Frontend, Testing, and Review agents can build a production-quality app autonomously across 12 phases
- **Plan for partial completion**: Not all agents activate every phase. The review agent must carry forward incomplete work.
- **Test count compounds**: Each phase adds 100-200 tests. Starting with good test infrastructure pays dividends.

### Technical
- **SQLite in async**: Requires careful handling (WAL mode, busy_timeout, connection pooling, retry with backoff)
- **React.memo() matters**: Dashboard components re-rendering on every WebSocket event caused visible lag until memo() was applied
- **Test flakiness**: Performance benchmark tests need generous thresholds (500ms+ in test env vs 200ms production target)
- **FastAPI DI**: Always use `dependency_overrides` for test mocking, never `unittest.mock.patch` on DI functions

### Security
- **Localhost doesn't mean insecure**: Even for local tools, security headers, input validation, CORS, and rate limiting are worth implementing
- **SSRF protection**: Webhook URLs validated at creation time against localhost/private IPs
- **No source maps in production**: Vite build correctly excludes them by default

## What's Next (Phase 13+)

- Multi-project dashboard with aggregated monitoring
- Swarm output intelligence (AI-powered summaries)
- Resource usage tracking (CPU/memory during runs)
- Project cloning and batch operations
- PWA support for installable web app
