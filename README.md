# Latent Underground

A web-based orchestration dashboard for managing multi-agent Claude Code swarms. Launch, monitor, and control AI agent teams from your browser — no terminal management needed.

## Features

- **Per-Agent Orchestration** — Launch up to 24 Claude Code agents as managed subprocesses with individual output streams, stop controls, and crash detection
- **Real-Time Monitoring** — Live terminal output via SSE, WebSocket events for signals/heartbeats/tasks, agent process timeline
- **Project Management** — Create, configure, archive, and search projects with persistent SQLite storage
- **Swarm Controls** — Launch/stop/resume swarms, send stdin to individual agents, view per-agent output with agent-colored tabs
- **Dashboard** — Combined view of agent status, task progress, signal panel, activity feed, and run history with analytics
- **Configuration Templates** — Save and reuse swarm configurations (agent count, max phases, prompt files)
- **File Editor** — In-browser markdown editor with syntax highlighting for TASKS.md, lessons.md, and other project files
- **Log Viewer** — Searchable, filterable log viewer with syntax highlighting and date range picker
- **Security** — Optional API key auth, rate limiting, CORS restriction, input sanitization, XSS prevention
- **Production Ready** — Docker Compose with nginx reverse proxy, HTTPS/SSL, health checks, auto-backups, graceful shutdown
- **Accessibility** — ARIA-compliant components, keyboard navigation, screen reader support
- **Three-Mode Theme** — Dark, light, and system-following theme with smooth transitions

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js](https://nodejs.org/) 18+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed globally

### Development

```bash
# Backend
cd backend
uv sync
uv run python run.py
# Starts at http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# Starts at http://localhost:5173
```

Or use the one-click launcher (Windows): `start.bat`

### Production (Docker)

```bash
export LU_API_KEY="your-secret-key"

# Generate SSL certs (or use Let's Encrypt)
mkdir -p deploy/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/ssl/key.pem -out deploy/ssl/cert.pem \
  -subj "/CN=localhost"

# Launch with nginx reverse proxy
docker compose -f docker-compose.prod.yml up -d
# Access at https://localhost
```

See [deploy/DEPLOY.md](deploy/DEPLOY.md) for full production guide including systemd, Let's Encrypt, monitoring, and troubleshooting.

## Architecture

```
latent-underground/
├── backend/                  # Python FastAPI server
│   ├── app/
│   │   ├── main.py           # App setup, middleware, lifespan
│   │   ├── config.py         # Environment-based configuration
│   │   ├── database.py       # SQLite with WAL, connection pool, migrations
│   │   ├── models/           # Pydantic request/response models
│   │   └── routes/           # API route handlers
│   │       ├── projects.py   # Project CRUD, stats, analytics, archival
│   │       ├── swarm.py      # Agent launch/stop/input/output/status
│   │       ├── templates.py  # Config template CRUD
│   │       ├── files.py      # Allowlisted file read/write
│   │       ├── logs.py       # Log streaming and search
│   │       ├── system.py     # System metrics (CPU, memory, disk)
│   │       ├── backup.py     # Database backup download
│   │       ├── plugins.py    # Plugin management
│   │       ├── webhooks.py   # Webhook notification CRUD
│   │       └── websocket.py  # Real-time WebSocket events
│   ├── tests/                # 876 pytest tests
│   └── run.py                # Entry point with auto-reload
├── frontend/                 # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/       # 20+ React components
│   │   ├── hooks/            # useTheme, useWebSocket
│   │   ├── lib/              # API client, constants
│   │   └── test/             # 610 Vitest tests
├── deploy/                   # Production configs
│   ├── nginx.conf            # Reverse proxy with SSL/WebSocket
│   ├── latent-underground.service
│   └── DEPLOY.md
├── Dockerfile                # Multi-stage build
├── docker-compose.yml        # Dev Docker setup
├── docker-compose.prod.yml   # Production with nginx
├── swarm.ps1                 # PowerShell swarm launcher
└── CHANGELOG.md              # Version history
```

### How It Works

1. **Create a project** — Point it at a directory containing `.claude/` prompts and a `swarm.ps1` launcher
2. **Configure** — Set agent count, max phases, and prompt assignments via the web UI
3. **Launch** — Backend runs `swarm.ps1 -SetupOnly` for workspace setup, then spawns each agent as a `claude --print` subprocess
4. **Monitor** — Real-time output via SSE, agent status via polling, signals/heartbeats via WebSocket
5. **Control** — Stop individual agents, view per-agent output, export terminal logs

### Key Technical Decisions

| Decision | Rationale |
|---|---|
| SQLite + WAL mode | Single-file DB, concurrent reads, no external dependency |
| subprocess.Popen + drain threads | Each agent is a subprocess; daemon threads drain stdout/stderr into deque buffers |
| stdin=DEVNULL | Claude `--print` mode blocks on open stdin; DEVNULL provides immediate EOF |
| SSE for output | Server-Sent Events for incremental output; more reliable than WebSocket for one-way data |
| WebSocket for events | Bidirectional channel for heartbeats, signals, task updates from filesystem watchers |
| Connection pool (asyncio.Queue) | Size-4 pool with overflow fallback for SQLite connections |

## Configuration

All settings use environment variables with `LU_` prefix. Set in `backend/.env` or pass to Docker.

| Variable | Default | Description |
|---|---|---|
| `LU_HOST` | `127.0.0.1` | Server bind address |
| `LU_PORT` | `8000` | Server port |
| `LU_DB_PATH` | `backend/latent.db` | SQLite database path |
| `LU_API_KEY` | _(empty)_ | API key for auth (empty = disabled) |
| `LU_LOG_LEVEL` | `info` | Logging level |
| `LU_LOG_FORMAT` | `text` | `text` or `json` for structured logging |
| `LU_RATE_LIMIT_RPM` | `30` | Write endpoint rate limit (req/min/client, 0 = off) |
| `LU_RATE_LIMIT_READ_RPM` | `120` | Read endpoint rate limit |
| `LU_CORS_ORIGINS` | `localhost:5173,8000` | Allowed CORS origins (comma-separated) |
| `LU_BACKUP_INTERVAL_HOURS` | `0` | Auto-backup interval in hours (0 = disabled) |
| `LU_BACKUP_KEEP` | `5` | Max auto-backups to retain |
| `LU_LOG_RETENTION_DAYS` | `0` | Auto-delete old project logs in days (0 = disabled) |
| `LU_AUTO_STOP_MINUTES` | `0` | Auto-stop idle swarms in minutes (0 = disabled) |
| `LU_VACUUM_INTERVAL_HOURS` | `0` | Database VACUUM schedule in hours (0 = disabled) |
| `LU_OUTPUT_BUFFER_LINES` | `5000` | Max output lines kept in memory per agent |
| `LU_REQUEST_LOG` | `false` | Log all HTTP requests with timing |

## API Reference

REST API at `/api/` (also at `/api/v1/`). Interactive docs at `/docs` (Swagger) and `/redoc`.

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/projects` | Create project |
| `GET` | `/api/projects` | List projects (`?search=&status=&sort=&include_archived=`) |
| `GET` | `/api/projects/{id}` | Get project details |
| `PATCH` | `/api/projects/{id}` | Update project |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `GET` | `/api/projects/{id}/stats` | Run statistics |
| `GET` | `/api/projects/{id}/analytics` | Detailed analytics (trends, efficiency) |
| `GET` | `/api/projects/{id}/dashboard` | Combined dashboard data |
| `PATCH` | `/api/projects/{id}/config` | Save agent configuration |
| `POST` | `/api/projects/{id}/archive` | Archive project |
| `POST` | `/api/projects/{id}/unarchive` | Unarchive project |
| `POST` | `/api/projects/bulk/archive` | Bulk archive (1-50 IDs) |
| `POST` | `/api/projects/bulk/unarchive` | Bulk unarchive |

### Swarm Control

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/swarm/launch` | Launch swarm agents |
| `POST` | `/api/swarm/stop` | Stop all agents for a project |
| `POST` | `/api/swarm/input` | Send stdin to agent(s) |
| `GET` | `/api/swarm/status/{id}` | Status with agents/signals/tasks |
| `GET` | `/api/swarm/history/{id}` | Run history with duration |
| `GET` | `/api/swarm/output/{id}` | Paginated output (`?offset=&limit=&agent=`) |
| `GET` | `/api/swarm/output/{id}/stream` | SSE real-time output stream |
| `GET` | `/api/swarm/agents/{id}` | Agent list with status/PID/exit code |
| `GET` | `/api/swarm/agents/{id}/metrics` | CPU/memory per agent (psutil) |
| `POST` | `/api/swarm/agents/{id}/{name}/stop` | Stop individual agent |
| `PATCH` | `/api/swarm/runs/{run_id}` | Annotate run (label, notes) |

### Templates, Plugins, Webhooks

| Method | Endpoint | Description |
|---|---|---|
| `POST/GET/PATCH/DELETE` | `/api/templates[/{id}]` | Config template CRUD |
| `POST/GET/DELETE` | `/api/plugins[/{name}]` | Plugin CRUD |
| `POST` | `/api/plugins/{name}/enable\|disable` | Toggle plugin |
| `POST/GET/PATCH/DELETE` | `/api/webhooks[/{id}]` | Webhook CRUD |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check (DB, uptime, version) |
| `GET` | `/api/system` | System metrics (CPU, memory, disk) |
| `GET` | `/api/backup` | Download database backup as SQL |
| `GET` | `/api/logs` | Recent log lines |
| `GET` | `/api/logs/search` | Search logs (`?q=&agent=&level=&from_date=&to_date=`) |
| `GET/PUT` | `/api/files/{path}` | Read/write allowlisted files |
| `GET` | `/api/browse` | Browse directories |
| `WS` | `/ws` | Real-time WebSocket events |

### Authentication

When `LU_API_KEY` is set, all endpoints except `/api/health`, `/docs`, `/redoc`, and `/ws` require `Authorization: Bearer <key>`. The frontend stores the key in localStorage and sends it automatically.

## Testing

```bash
# Backend (876 tests)
cd backend && uv run pytest -x -q

# Frontend (610 tests)
cd frontend && npx vitest run src/test/

# Total: 1486 tests
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+L` | Clear terminal output |
| `Ctrl+Enter` | Send terminal input |
| `Escape` | Clear input / close modal |
| `Ctrl+?` | Show shortcut cheatsheet |
| `Arrow Left/Right` | Navigate agent tabs |
| `Home/End` | Jump to first/last agent tab |

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes.

## License

MIT
