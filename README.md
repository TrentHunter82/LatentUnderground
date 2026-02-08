# Latent Underground

A local web application for managing Claude Swarm sessions. Provides a GUI that wraps the existing PowerShell-based swarm orchestration scripts.

## What It Does

- **Create swarm projects** by filling in 5 setup fields (goal, type, stack, complexity, requirements) and clicking Launch
- **Live dashboard** showing task progress, agent heartbeats, signal states, and recent activity (web version of `watch.ps1`)
- **View and edit** `tasks/TASKS.md` and `tasks/lessons.md` in-browser with markdown rendering and syntax highlighting
- **Stop/resume swarms** with buttons and confirmation dialogs
- **Manage multiple projects** from one interface with a collapsible sidebar listing past and active swarms
- **View agent logs** with auto-scroll, per-agent filtering, and color coding
- **Real-time updates** via WebSocket with toast notifications for actions
- **Process tracking** - persisted swarm PIDs with automatic stale-status detection

## Architecture

```
LatentUnderground/
├── backend/                 # Python FastAPI API server
│   ├── app/
│   │   ├── main.py          # FastAPI app, lifespan, CORS, static file serving
│   │   ├── database.py      # SQLite via aiosqlite (with migrations)
│   │   ├── models/
│   │   │   └── project.py   # Pydantic models (ProjectCreate/Update/Out)
│   │   ├── routes/
│   │   │   ├── projects.py  # CRUD for projects (with path validation)
│   │   │   ├── swarm.py     # Launch/stop/status/output via PowerShell
│   │   │   ├── files.py     # Read/write allowlisted files
│   │   │   ├── logs.py      # Agent log retrieval
│   │   │   ├── websocket.py # Real-time WebSocket events
│   │   │   └── watcher.py   # Filesystem watch/unwatch endpoints
│   │   └── services/
│   │       └── watcher.py   # Filesystem watcher (heartbeats, signals, tasks, logs)
│   ├── tests/               # pytest test suite (148 tests)
│   ├── run.py               # Entry point (starts uvicorn, opens browser)
│   └── pyproject.toml       # Dependencies and config
├── frontend/                # React 19 + Vite + Tailwind 4
│   ├── src/
│   │   ├── App.jsx          # Root layout with sidebar toggle + routing
│   │   ├── main.jsx         # Entry point with providers
│   │   ├── lib/api.js       # API client (fetch wrapper)
│   │   ├── hooks/useWebSocket.js  # WebSocket hook with auto-reconnect
│   │   └── components/      # 19 React components
│   │       ├── Dashboard.jsx      # Live swarm status with debounced WS updates
│   │       ├── NewProject.jsx     # Project creation form
│   │       ├── FileEditor.jsx     # Markdown editor with Ctrl+S, syntax highlight
│   │       ├── LogViewer.jsx      # Filtered agent log viewer
│   │       ├── SwarmControls.jsx  # Launch/Stop/Resume with confirmations
│   │       ├── Toast.jsx          # Toast notification system
│   │       ├── ConfirmDialog.jsx  # Confirmation modal dialog
│   │       ├── Skeleton.jsx       # Loading skeleton components
│   │       └── ...                # AgentGrid, SignalPanel, TaskProgress, etc.
│   └── dist/                # Production build (served by FastAPI)
├── swarm.ps1                # Main swarm launcher (4 Claude agents)
├── stop-swarm.ps1           # Stop all Claude processes
├── AGENTS.md                # Agent workflow guidelines
└── tasks/
    ├── TASKS.md             # Task board with per-agent assignments
    └── lessons.md           # Self-improvement loop
```

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+ (for frontend build)
- PowerShell (for swarm scripts)

### Production (Single Server)

```bash
# Build frontend
cd frontend
npm install
npm run build
cd ..

# Start server (serves both API and frontend on port 8000)
cd backend
uv sync
uv run python run.py
```

The server auto-opens `http://localhost:8000` in the browser.

### Development (Hot Reload)

```bash
# Terminal 1: Backend
cd backend
uv sync
uv run python run.py

# Terminal 2: Frontend dev server (proxies API to backend)
cd frontend
npm install
npm run dev
```

Frontend dev server runs at `http://localhost:5173` with hot module replacement.

### Run Tests

```bash
# Backend (148 tests)
cd backend
uv run python -m pytest tests/ -v

# Frontend (118 tests)
cd frontend
npm test

# All tests (266 total)
bash test-all.sh
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/projects/{id}` | Get project details |
| `PATCH` | `/api/projects/{id}` | Update project fields |
| `DELETE` | `/api/projects/{id}` | Delete a project |
| `POST` | `/api/swarm/launch` | Launch swarm (calls `swarm.ps1`) |
| `POST` | `/api/swarm/stop` | Stop swarm (calls `stop-swarm.ps1`) |
| `GET` | `/api/swarm/status/{id}` | Swarm status (agents, signals, tasks, phase, PID health) |
| `GET` | `/api/swarm/output/{id}` | Get captured subprocess stdout/stderr |
| `GET` | `/api/swarm/output/{id}/stream` | SSE real-time output stream |
| `GET` | `/api/swarm/history/{id}` | Swarm run history with duration |
| `GET` | `/api/projects/{id}/stats` | Project run statistics |
| `PATCH` | `/api/projects/{id}/config` | Save project agent config |
| `GET` | `/api/files/{path}` | Read an allowlisted file |
| `PUT` | `/api/files/{path}` | Write an allowlisted file |
| `GET` | `/api/logs` | Get recent agent log lines |
| `POST` | `/api/watch/{id}` | Start filesystem watcher for a project |
| `POST` | `/api/unwatch/{id}` | Stop filesystem watcher |
| `GET` | `/api/health` | Health check |
| `WS` | `/ws` | WebSocket for real-time events |

### WebSocket Events

The `/ws` endpoint broadcasts these event types:

- `heartbeat` - Agent heartbeat update (`agent`, `timestamp`)
- `signal` - Signal created/deleted (`name`, `active`)
- `tasks` - Task progress change (`total`, `done`, `percent`)
- `log` - New log lines (`agent`, `lines`)
- `file_changed` - Non-task markdown file changed (`file`)
- `pong` - Response to client `ping`

### File API Security

The file API only allows access to these paths (relative to project folder):
- `tasks/TASKS.md`
- `tasks/lessons.md`
- `tasks/todo.md`
- `AGENTS.md`
- `progress.txt`

All other paths return 403 Forbidden.

### Security Notes

- **No authentication** - designed for local/single-user use only
- CORS restricted to localhost origins (5173, 8000)
- File API uses strict allowlist (no path traversal)
- SPA catch-all validates paths stay within `dist/`
- Folder paths must be absolute (validated on project creation)
- SQL queries use parameterized bindings throughout
- Subprocess execution uses `exec` (not shell) to prevent injection

## How Swarm Orchestration Works

1. `swarm.ps1` launches 4 Claude agents in separate PowerShell windows
2. Each agent works on assigned tasks from `tasks/TASKS.md`
3. Agents write heartbeats to `.claude/heartbeats/` so the supervisor knows they're alive
4. Agents create signal files in `.claude/signals/` when milestones are reached
5. The supervisor auto-chains to the next phase when `phase-complete.signal` appears (up to 24 phases by default; override with `-MaxPhases N`)
6. This web app provides a GUI for the entire lifecycle instead of terminal scripts

## Development Status

**Phase 1**: Backend API + test suite - complete
**Phase 2**: React frontend, real-time updates, production serving, polish - complete
**Phase 3**: History, analytics, and advanced APIs - complete

### Phase 3 Deliverables
- Swarm run history tracking (start/stop timestamps, duration, task counts)
- SSE real-time output streaming endpoint
- Project statistics API (total runs, average duration, tasks completed)
- Project agent configuration (agent count, max phases up to 24, custom prompts)
- SwarmHistory component with run table (started, duration, status, tasks)
- TerminalOutput component with ANSI color parsing, auto-scroll, and line cap
- ProjectSettings component with save/load configuration form
- Stats summary displayed in Dashboard header
- 6 new tabs in ProjectView (dashboard, history, output, files, logs, settings)
- 266 total tests (148 backend + 118 frontend) with CI script

### Phase 2 Deliverables
- 15 React components with dark theme (zinc/violet palette)
- Real-time WebSocket updates with auto-reconnect
- Markdown editor with syntax highlighting (highlight.js)
- Toast notifications, confirmation dialogs, loading skeletons
- Keyboard shortcuts (Ctrl+S save, Escape cancel)
- Responsive sidebar with mobile overlay
- Log viewer with per-agent filtering and auto-scroll
- FastAPI serves built frontend (SPA fallback with path traversal protection)
- File write rate limiting (2s cooldown)
- Process PID tracking with automatic stale-status correction
