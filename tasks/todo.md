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

## Claude-1 - Phase 5 Plan

### Task 1: Environment Configuration (.env support)
- [ ] Create `app/config.py` with Settings class (env vars with defaults)
- [ ] Update `database.py` to use config DB_PATH
- [ ] Update `run.py` to use config HOST/PORT
- [ ] Update `main.py` CORS to use config CORS_ORIGINS
- [ ] Create `.env.example`

### Task 2: Docker Support
- [ ] Dockerfile: multi-stage (build frontend, serve from backend)
- [ ] docker-compose.yml with volume for DB
- [ ] .dockerignore

### Task 3: Database Backup Endpoint
- [ ] GET /api/backup → SQLite file download

### Task 4: Swarm Templates CRUD
- [ ] Add swarm_templates table
- [ ] Pydantic models + CRUD routes
- [ ] Register router

### Task 5: Process Reconnection
- [ ] Startup check for stale running projects
- [ ] Auto-correct dead PIDs, log results
