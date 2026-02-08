# Agent Plans

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

## Claude-1 - Production Hardening Plan
- [x] 1. Thread safety on output buffers (swarm.py) - added _buffers_lock
- [x] 2. Input validation on SwarmLaunchRequest (swarm.py) - Field(ge=1, le=16/20)
- [x] 3. Input validation on ProjectCreate/ProjectUpdate (project.py) - min/max_length
- [x] 4. Health check with database probe (main.py) - SELECT 1, 503 on failure
- [x] 5. Fix data loss on swarm stop (swarm.py) - join threads before pop
- [x] 6. Add logging to silent exception handlers (websocket.py, swarm.py) - logger.debug
- [x] 7. Run full test suite - 214 backend + 173 frontend = 387 passing, zero failures
