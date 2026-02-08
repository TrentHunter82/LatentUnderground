# Latent Underground - User Guide

A step-by-step guide to installing, running, and using Latent Underground to manage Claude AI swarm sessions.

---

## Table of Contents

1. [What Is Latent Underground?](#what-is-latent-underground)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Starting the Application](#starting-the-application)
5. [Creating a Project](#creating-a-project)
6. [Launching a Swarm](#launching-a-swarm)
7. [Monitoring Your Swarm](#monitoring-your-swarm)
8. [Editing Task Files](#editing-task-files)
9. [Viewing Agent Logs](#viewing-agent-logs)
10. [Stopping a Swarm](#stopping-a-swarm)
11. [Swarm History and Statistics](#swarm-history-and-statistics)
12. [Project Settings](#project-settings)
13. [Templates](#templates)
14. [Managing Multiple Projects](#managing-multiple-projects)
15. [Docker Deployment](#docker-deployment)
16. [Keyboard Shortcuts](#keyboard-shortcuts)
17. [Troubleshooting](#troubleshooting)

---

## What Is Latent Underground?

Latent Underground is a local web application that gives you a graphical interface for running **Claude AI swarm sessions**. A swarm is a coordinated group of 4 Claude agents that work in parallel on tasks you define. Instead of managing swarms through PowerShell scripts and terminal windows, Latent Underground lets you create projects, launch swarms, and monitor everything from a single browser dashboard.

**Key capabilities:**
- Create and configure swarm projects through a web form
- Launch, stop, and resume swarms with one click
- Watch a live dashboard showing agent heartbeats, task progress, and phase signals
- Edit task files directly in the browser with markdown rendering
- Filter and read per-agent logs in real time
- Track run history with timing and task statistics
- Save and reuse swarm configurations as templates

---

## Prerequisites

Before installing, make sure you have:

1. **Python 3.11 or newer** - The backend is built with FastAPI and Python.
2. **[uv](https://docs.astral.sh/uv/)** - A fast Python package manager used to install backend dependencies.
   ```bash
   # Install uv (if you don't have it)
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. **Node.js 18 or newer** - Required to build the React frontend.
4. **PowerShell** - The swarm orchestration scripts (`swarm.ps1`, `stop-swarm.ps1`) run in PowerShell. On Windows this is built in. On Linux/macOS, install [PowerShell Core](https://github.com/PowerShell/PowerShell).

---

## Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd LatentUnderground

# Install frontend dependencies and build the production bundle
cd frontend
npm install
npm run build
cd ..

# Install backend dependencies
cd backend
uv sync
cd ..
```

Optionally, copy the environment config template and adjust settings:

```bash
cp backend/.env.example backend/.env
```

The default settings work out of the box for local use. Available options in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LU_HOST` | `127.0.0.1` | Address the server binds to |
| `LU_PORT` | `8000` | Port the server listens on |
| `LU_DB_PATH` | `latent.db` | Path to the SQLite database file |
| `LU_LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |
| `LU_CORS_ORIGINS` | localhost origins | Comma-separated allowed CORS origins |
| `LU_FRONTEND_DIST` | `../frontend/dist` | Path to the built frontend files |

---

## Starting the Application

### Production Mode (Recommended)

Run the backend, which serves both the API and the built frontend on a single port:

```bash
cd backend
uv run python run.py
```

Your browser will automatically open to `http://localhost:8000`. If it doesn't, open that URL manually.

### Development Mode (Hot Reload)

For working on the code with live-reloading:

```bash
# Terminal 1 - Start the backend API server
cd backend
uv run python run.py

# Terminal 2 - Start the frontend dev server with hot module replacement
cd frontend
npm run dev
```

In dev mode, use `http://localhost:5173` instead. The Vite dev server automatically proxies API and WebSocket requests to the backend.

---

## Creating a Project

1. Click **"New Project"** in the sidebar (or navigate to the home page and click the create button).
2. Fill in the 5 project fields:

| Field | What to Enter | Example |
|-------|--------------|---------|
| **Goal** | What you want the swarm to accomplish | "Build a REST API for user authentication" |
| **Project Type** | The category of work | "Web Application", "CLI Tool", "Library" |
| **Tech Stack** | Languages, frameworks, and tools to use | "Python, FastAPI, PostgreSQL" |
| **Complexity** | How complex the project is | "Medium", "High" |
| **Requirements** | Specific requirements or constraints | "Must include JWT auth, rate limiting, and tests" |

3. Provide the **folder path** where the swarm should work. This must be an absolute path to an existing directory on your machine (e.g., `/home/user/my-project` or `C:\Users\me\my-project`).
4. Click **Create** to save the project.

---

## Launching a Swarm

1. Select your project from the **sidebar** to open its detail view.
2. Go to the **Dashboard** tab (selected by default).
3. Click the **Launch** button in the swarm controls area.
4. A confirmation dialog will appear. Confirm to start the swarm.

Behind the scenes, this calls `swarm.ps1`, which opens 4 Claude agent sessions that begin working on the tasks defined in your project's `tasks/TASKS.md` file.

---

## Monitoring Your Swarm

Once a swarm is running, the **Dashboard** tab updates in real time via WebSocket:

### Agent Grid
Shows each of the 4 agents (Claude-1 through Claude-4) with a heartbeat indicator. A green indicator means the agent has sent a heartbeat recently and is actively working. A stale heartbeat means the agent may have stopped.

### Task Progress
Displays a progress bar showing how many tasks from `tasks/TASKS.md` are completed. Tasks are parsed from markdown checklist items (`- [x]` for done, `- [ ]` for pending).

### Signal Panel
Shows phase milestone signals. As agents complete major milestones, they create signal files (e.g., `backend-ready`, `frontend-ready`, `tests-passing`, `phase-complete`). Each signal lights up on the panel when reached.

### Activity Feed
A live stream of recent events: agent heartbeats, signal changes, task progress updates, and file modifications.

### Sparkline
A small chart in the dashboard header showing the task completion rate trend over time.

---

## Editing Task Files

1. Go to the **Files** tab in your project view.
2. You can view and edit these files directly in the browser:
   - `tasks/TASKS.md` - The main task board with per-agent assignments
   - `tasks/lessons.md` - Patterns and lessons learned from past runs
   - `tasks/todo.md` - Current work tracking
   - `AGENTS.md` - Agent workflow guidelines
   - `progress.txt` - Human-readable status notes

3. The editor renders markdown with syntax highlighting. Click into the editor to make changes.
4. Press **Ctrl+S** (or Cmd+S on Mac) to save your changes.

File writes are rate-limited to prevent rapid overwrites (2-second cooldown between saves).

---

## Viewing Agent Logs

1. Go to the **Logs** tab in your project view.
2. Logs from all 4 agents are displayed with color coding per agent.
3. Use the **agent filter** buttons to show logs from a specific agent or all agents at once.
4. The log viewer auto-scrolls to the bottom as new lines arrive. You can scroll up to read earlier output, and auto-scroll will pause until you scroll back to the bottom.

---

## Stopping a Swarm

1. On the **Dashboard** tab, click the **Stop** button.
2. A confirmation dialog will appear asking you to confirm.
3. Confirm to stop the swarm. This calls `stop-swarm.ps1`, which terminates all running Claude agent processes.

The run is recorded in history with its duration and final task count.

---

## Swarm History and Statistics

### History Tab
Go to the **History** tab to see a table of all past swarm runs for the current project. Each row shows:
- When the run started
- Duration
- Final status (running, completed, stopped)
- Number of tasks completed

### Statistics
The Dashboard header displays aggregate stats for the project:
- Total number of runs
- Average run duration
- Total tasks completed across all runs

---

## Project Settings

Go to the **Settings** tab to configure how the swarm runs for this project:

| Setting | Description |
|---------|-------------|
| **Agent Count** | Number of Claude agents to launch (default: 4) |
| **Max Phases** | Maximum number of phases before the swarm stops |
| **Custom Prompts** | Custom instructions passed to the agents |

Click **Save** to persist the configuration. These settings are used the next time you launch a swarm for this project.

---

## Templates

Templates let you save and reuse swarm configurations across projects.

### Saving a Template
1. Configure your project settings the way you want.
2. Use the template save feature to store the configuration with a name and optional description.

### Loading a Template
1. When creating or configuring a project, browse available templates.
2. Select a template to apply its saved configuration to your current project.

Templates are managed through the API at `/api/templates` and are stored in the database.

---

## Managing Multiple Projects

The **sidebar** on the left lists all your projects. Each project shows a status badge indicating whether its swarm is idle, running, or stopped.

- Click any project to switch to its detail view.
- The sidebar is collapsible - click the toggle to expand or collapse it.
- On mobile, the sidebar appears as an overlay.
- Use the **Delete** option in a project's settings to remove it. This deletes the project record from the database but does not delete any files on disk.

---

## Docker Deployment

To run Latent Underground in a Docker container:

```bash
docker-compose up --build
```

This builds a multi-stage image (Node for the frontend build, Python for the runtime) and starts the server on port 8000. Data is persisted in a Docker volume (`lu-data`).

To stop:

```bash
docker-compose down
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+S** / **Cmd+S** | Save the current file in the editor |
| **Escape** | Cancel the current operation / close dialogs |

---

## Troubleshooting

### The browser didn't open automatically
Navigate to `http://localhost:8000` manually. If the page doesn't load, check that the backend is running and no other process is using port 8000.

### "PowerShell not found" when launching a swarm
The swarm scripts require PowerShell. On Linux/macOS, install PowerShell Core:
```bash
# Ubuntu/Debian
sudo apt-get install -y powershell

# macOS
brew install powershell/tap/powershell
```

### Agent heartbeats show as stale
This means an agent hasn't written a heartbeat file recently. The agent may have crashed or finished its work. Check the **Logs** tab for error messages from that agent.

### File save returns an error
- Make sure the file is in the allowlist (`tasks/TASKS.md`, `tasks/lessons.md`, `tasks/todo.md`, `AGENTS.md`, `progress.txt`). Other files cannot be edited through the web interface.
- If you see a rate-limit error, wait 2 seconds and try saving again.

### WebSocket disconnects frequently
The frontend automatically reconnects with exponential backoff (1 second up to 30 seconds). If the connection is unstable, check that the backend server is still running. In development mode, make sure both the backend and frontend dev servers are active.

### Database errors on startup
The backend creates and migrates the SQLite database automatically. If you encounter schema errors, you can delete the `latent.db` file in the backend directory to start fresh (this will erase all project data).

### Port 8000 is already in use
Either stop the other process using port 8000, or change the port in your `.env` file:
```
LU_PORT=9000
```
Then access the app at `http://localhost:9000`.

### Swarm stops immediately after launching
Check that:
1. The project folder path exists and is an absolute path.
2. The `tasks/TASKS.md` file exists in the project folder with task definitions.
3. PowerShell can execute `swarm.ps1` without errors (try running it manually).
