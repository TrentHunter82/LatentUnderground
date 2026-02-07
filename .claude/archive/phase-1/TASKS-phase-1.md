# Latent Underground - Task Board

## Claude-1 [Backend/Core] - Python FastAPI backend, SQLite, WebSocket, file watchers

- [x] Initialize Python project with uv (pyproject.toml, dependencies: fastapi, uvicorn, websockets, watchfiles, aiosqlite)
- [x] Create project structure: backend/app/ with models, routes, services, database modules
- [x] Set up SQLite database with aiosqlite - project table (id, name, goal, type, stack, complexity, requirements, folder_path, status, created_at, updated_at)
- [x] Build CRUD API for projects (POST/GET/PATCH/DELETE /api/projects)
- [x] Build swarm launch endpoint (POST /api/swarm/launch) - calls swarm.ps1 via subprocess
- [x] Build swarm stop endpoint (POST /api/swarm/stop) - calls stop-swarm.ps1 via subprocess
- [x] Build swarm status endpoint (GET /api/swarm/status/{project_id}) - reads .claude/ directory for heartbeats, signals, task progress
- [x] Build file API (GET/PUT /api/files/{path}) - read/write tasks/TASKS.md and tasks/lessons.md with path allowlisting
- [x] Build WebSocket endpoint (/ws) for real-time events
- [x] Build filesystem watcher service - watch .claude/heartbeats/, .claude/signals/, tasks/ for changes, push events via WebSocket
- [x] Build log streaming service - tail logs/*.log files and broadcast new lines via WebSocket
- [x] Create run.py entry point that starts uvicorn and auto-opens browser
- [x] Signal: Create .claude/signals/backend-ready.signal after all APIs verified working

## Claude-2 [Frontend/Interface] - React + Vite + Tailwind dark UI

- [x] Initialize React project with Vite + Tailwind in frontend/
- [x] Create app layout: dark theme sidebar (project list) + main content area
- [x] Build project creation form (5 fields: goal, type, stack, complexity, requirements) + Launch button
- [x] Build live dashboard view - task progress bar, agent heartbeats, signal states, recent activity (WebSocket-powered)
- [x] Build markdown editor/viewer for tasks/TASKS.md and tasks/lessons.md (in-browser editing with preview)
- [x] Build swarm controls - Launch/Stop/Resume buttons with status indicators
- [x] Build agent log viewer with auto-scroll and color coding per agent
- [x] Build project sidebar - list past/active swarms, click to switch context
- [x] Apply "Latent Underground" aesthetic - refined dark mode, subtle generative/neural accent colors, sleek not gaudy
- [x] Signal: Create .claude/signals/frontend-ready.signal after UI connects to backend

## Claude-3 [Integration/Testing] - Connect pieces and verify

- [x] Write backend API tests (pytest) - CRUD, swarm launch/stop, file API, status endpoint
- [x] Write WebSocket integration tests - connection, event reception, heartbeat/signal updates
- [x] Test swarm.ps1 integration - verify backend correctly calls and monitors PowerShell scripts
- [x] Test filesystem watcher - verify file changes propagate to WebSocket clients
- [x] End-to-end test: create project via API, launch swarm, verify dashboard updates
- [x] Signal: Create .claude/signals/tests-passing.signal after all tests pass

## Claude-4 [Polish/Review] - Quality and refinement

- [x] Review all agent code for quality, consistency, and security (especially file API path validation)
- [x] Review frontend for accessibility and responsive design
- [x] Verify error handling across all API endpoints and WebSocket connections
- [x] Review and consolidate tasks/lessons.md - deduplicate, sharpen rules
- [x] Write README.md with setup instructions and architecture overview
- [x] FINAL: Generate next-swarm.ps1 script for the next development phase

## Completion Criteria
- [x] Backend serves API on port 8000
- [x] Frontend builds and connects to backend
- [x] WebSocket delivers real-time updates
- [x] Can create project, launch swarm, see live dashboard, stop swarm - all from browser
- [x] All tests pass
