# Changelog

All notable changes to the Latent Underground project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] - Phase 11

### Added
- Security headers middleware: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, X-XSS-Protection, Cache-Control on all responses
- Global exception handlers: structured JSON error responses for RequestValidationError (422), OperationalError (503), and generic Exception (500)
- Webhook SSRF protection: URL scheme validation (http/https only), localhost and private IP blocking
- Webhook management UI (WebhookManager component) integrated into project settings tab
- Project archive/unarchive toggle in Sidebar and Dashboard
- Version badge in SettingsPanel and Sidebar showing dynamic app version
- Security header test suite (15 tests)
- 890+ total tests (507 backend + 383 frontend), zero failures

### Changed
- Webhook create/update endpoints validate URL against SSRF attack vectors
- ProjectView getProject useEffect now uses mounted flag for cleanup (prevents state update on unmount)
- Version test uses regex matcher for forward compatibility with version bumps

### Fixed
- ProjectView.jsx missing `toast` in useEffect dependency array (stale closure risk)
- Unused `timedelta` import removed from main.py

## [0.10.0] - Phase 10

### Added
- Plugin system with JSON-based discovery and CRUD API at /api/plugins
- Webhook notification system with HMAC-SHA256 signing, async delivery, and retry with exponential backoff
- Project archival with archived_at column, archive/unarchive endpoints, filtered from default listing
- API versioning: /api/v1/ routes with deprecation headers on unversioned /api/ routes
- Request/response logging middleware (method, path, status, duration) with LU_REQUEST_LOG toggle
- SQLite optimization: mmap_size=256MB, ANALYZE on init, 3 new composite indexes
- Settings panel with theme toggle, API key management, notification preferences, and system info
- Keyboard shortcut cheatsheet modal (Ctrl+? to open)
- First-run onboarding modal with 3-step setup carousel for new users
- Default template presets: Quick Research, Code Review, Feature Build, Debugging
- Retry action buttons on error toast notifications
- Route-level code splitting: React.lazy() for 8 components (49% main bundle reduction: 481KB to 245KB)
- Plugin integration tests (15), webhook integration tests (16), load tests (10)
- Bundle size regression tests (6), Phase 10 accessibility tests (15)
- UPGRADE.md migration guide

### Changed
- Toast notifications now support action buttons with configurable duration (10s for error+action)
- SettingsPanel clear confirmation uses ConfirmDialog component for consistent accessibility

### Fixed
- Toast timeout memory leak on unmount (timeouts now tracked and cleaned up)
- OnboardingModal stale closure on Escape key (uses useCallback with proper dependencies)
- OnboardingModal focus trap uses onKeyDown pattern matching ConfirmDialog
- SettingsPanel focus trap uses onKeyDown + useCallback pattern (consistent with other modals)
- SettingsPanel clear API key dialog now has full keyboard navigation and focus trap

## [0.9.0] - Phase 9

### Added
- Structured logging with JSON format support (LU_LOG_FORMAT=json|text)
- Automatic database backups on configurable interval (LU_BACKUP_INTERVAL_HOURS)
- Log retention policy with automatic cleanup (LU_LOG_RETENTION_DAYS)
- Database connection retry with exponential backoff (3 retries on transient failures)
- Per-API-key rate limiting (falls back to IP-based when no key present)
- Graceful shutdown: cancels backup tasks, stops PID monitors, drains buffers
- Production deployment guide with docker-compose, nginx, and systemd configs
- E2E test suite (20 tests covering full lifecycle flows)
- API contract test suite (48 tests validating endpoint schemas)
- axe-core accessibility auditing across 23 components

### Changed
- Rate limiter now uses API key prefix as identity when authentication is enabled
- Enhanced lifespan management with ordered shutdown sequence

### Fixed
- Unused import removed from database.py
- Log retention glob wrapped in OSError protection (prevents crash on deleted project folders)

## [0.8.0] - Phase 8

### Added
- Swarm config templates CRUD API (POST/GET/PATCH/DELETE /api/templates)
- Filesystem browser API (GET /api/browse) for project folder selection
- FolderBrowser component with focus trap, aria-modal, and keyboard navigation
- TemplateManager component for creating, editing, and deleting templates
- Process reconnection on server restart (PID monitor background threads)
- Paginated swarm output (limit param capped at 500, total/has_more metadata)
- Rate limiting middleware (configurable via LU_RATE_LIMIT_RPM, default 30 RPM)
- Debounced search hook (useDebounce) applied to Sidebar and LogViewer
- Run duration trend sparkline on Dashboard alongside task completion sparkline
- Virtualized log rendering for 200+ lines with 22px fixed row height
- Loading skeleton states for LogViewer, SwarmHistory, and Analytics
- Fade-in animations on tab panel transitions
- SQLite WAL mode with optimized pragmas (synchronous=NORMAL, busy_timeout=5000, cache_size=16MB)

### Changed
- DB_PATH uses dynamic lookup from database module for testability
- Backup route uses asyncio.to_thread to avoid blocking the event loop
- Log search limit capped at 1000, offset clamped to 0+
- Test fixtures use tmp_path instead of hardcoded paths (eliminates flaky tests)

### Fixed
- browse.py MAX_DIRS=500 cap to prevent resource exhaustion
- _pid_alive guard against pid<=0 edge case
- FolderBrowser setTimeout memory leak (clearTimeout on cleanup)
- TemplateManager save button disabled when name is empty
- Sidebar search input aria-label for screen readers
- Backup resource leak with try/finally on database connections

## [0.7.0] - Phase 7

### Added
- Swarm stdin input endpoint (POST /api/swarm/input) for sending text to running processes
- API key authentication middleware (LU_API_KEY env var, Bearer/X-API-Key headers)
- Database indexes on projects(status), swarm_runs(project_id, started_at), swarm_runs(status)
- Log search date range filtering (from_date, to_date parameters)
- Incremental WebSocket log streaming with file position tracking
- Terminal input bar in frontend (> prompt, Enter-to-send, local echo, 1000 char limit)
- AuthModal component (401 handling, Bearer header injection, localStorage persistence)
- Date range picker in LogViewer
- LIVE indicator in LogViewer (green dot when WebSocket events are flowing)
- Keyboard shortcuts: Ctrl+K (search), Ctrl+N (new project), Escape (close modals)
- Shared constants module (lib/constants.js)

### Changed
- Max phases default changed from 3 to 24 across all layers (backend, frontend, scripts)

### Fixed
- Field(ge=1) validation on SwarmStopRequest and SwarmInputRequest
- _swarm_processes cleanup in test fixtures

## [0.6.0] - Phase 6

### Added
- Project search and filtering (GET /api/projects?search=&status=&sort=)
- Project analytics endpoint (GET /api/projects/{id}/analytics) with trends and efficiency metrics
- Log search endpoint (GET /api/logs/search?q=&level=&agent=) with text and metadata filtering
- Enhanced health check (GET /api/health) with database probe, uptime, and active process count
- OpenAPI/Swagger auto-documentation at /docs and /redoc
- useHealthCheck hook with latency measurement and 30s polling
- Search bar and status filter in Sidebar with client-side filtering
- Browser notifications for swarm events (useNotifications hook)
- Log tools: search, level filter, copy, and download in LogViewer
- Analytics tab (7th tab) with summary chips and SVG charts

### Changed
- Thread-safe output buffers with _buffers_lock
- Input validation with Field constraints (ge/le/min_length/max_length) on all request models
- Silent exception handlers now log at debug level

### Fixed
- File read/write error handling in file API
- Drain thread join on swarm stop (prevents data loss)

## [0.5.0] - Phase 5

### Added
- Docker support: multi-stage Dockerfile (Node + Python), docker-compose.yml, .dockerignore
- Environment configuration via .env file (LU_HOST, LU_PORT, LU_DB_PATH, LU_LOG_LEVEL, LU_CORS_ORIGINS)
- Database backup endpoint (GET /api/backup) returning SQLite dump as downloadable .sql file
- CI test script (test-all.sh) for running full backend + frontend suite

### Fixed
- Migration exception specificity (catch sqlite3.OperationalError instead of broad Exception)
- Output buffer leak on swarm stop (_output_buffers.pop cleanup)
- Column update whitelist (ALLOWED_UPDATE_FIELDS) to prevent arbitrary field injection

## [0.4.0] - Phase 4

### Changed
- Complete retro-futurism UI redesign inspired by vintage analog control panels
- Color palette: mint/seafoam (#80C8B0), teal (#5AACA0), crimson (#C41E3A), orange (#E87838)
- Typography: Space Mono (body) + JetBrains Mono (code/terminal) via Google Fonts CDN
- 3D jewel-cap LED indicators, chrome bezel panels, tactile button styling
- Agent-specific colors: Claude-1=teal, Claude-2=crimson, Claude-3=mint, Claude-4=orange
- Light theme with mint/cream palette (#D8EEE2 backgrounds, #C8E0D4 surfaces)
- CSS utilities: .neon-*, .glow-*, .led-*, .btn-neon, .retro-panel, .retro-input
- prefers-reduced-motion support disables all custom animations and scanlines

## [0.3.0] - Phase 3

### Added
- Swarm run history table (swarm_runs) with duration tracking
- Swarm history API (GET /api/swarm/history/{id})
- SSE real-time output streaming (GET /api/swarm/output/{id}/stream)
- Project run statistics endpoint (GET /api/projects/{id}/stats)
- Project agent config endpoint (PATCH /api/projects/{id}/config)
- SwarmHistory component with run list and duration display
- TerminalOutput component for live swarm output
- ProjectSettings component for agent configuration
- 6-tab ProjectView layout (Overview, Terminal, History, Settings, Files, Logs)
- Dashboard project stats summary (total runs, avg duration, tasks completed)

### Fixed
- ThemeToggle.jsx explicit .jsx extension on useTheme import for Rollup compatibility
- ProjectConfig Field validation (ge/le/max_length constraints)
- DateTime parsing wrapped in try/except for malformed timestamps
- Tab ARIA roles for accessibility compliance

## [0.2.0] - Phase 2

### Added
- 16 React components: Dashboard, Sidebar, ProjectView, NewProject, SwarmControls, LogViewer, and more
- Dark theme with Tailwind CSS
- WebSocket hook (useWebSocket) with exponential backoff reconnection
- ErrorBoundary component for graceful error handling
- ConfirmDialog with focus trap for accessible modal interactions
- Dashboard visibility polling (pauses updates when tab is hidden)
- Static file serving from FastAPI with SPA catch-all routing
- Path traversal protection on static file serving
- CORS restricted to localhost origins (5173, 8000)
- Allowlisted file API for secure file read/write
- Parameterized SQL queries throughout
- Subprocess execution via exec (not shell) for security

## [0.1.0] - Phase 1

### Added
- FastAPI backend with SQLite database
- Project CRUD API (POST/GET/PATCH/DELETE /api/projects)
- Swarm launch and stop endpoints (POST /api/swarm/launch, POST /api/swarm/stop)
- Swarm status endpoint (GET /api/swarm/status/{id}) with agent, signal, and task data
- Real-time WebSocket endpoint (/ws) for live event broadcasting
- Filesystem watcher pushing heartbeat, signal, and task events
- File read/write API (GET/PUT /api/files/{path})
- Log viewer API (GET /api/logs)
- React + Vite + Tailwind frontend scaffold
- Project creation form with goal, type, stack, complexity, and requirements fields
