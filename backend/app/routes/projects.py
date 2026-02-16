import itertools
import json
import logging
import re
import shutil
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import aiosqlite

from ..database import get_db
from ..models.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectConfig
from ..models.responses import (
    ProjectStatsOut, ProjectAnalyticsOut, ProjectConfigUpdateOut, ErrorDetail,
    ProjectDashboardOut, BulkArchiveOut, BulkUnarchiveOut, BulkArchiveRequest,
    ProjectHealthOut, QuotaOut, GuardrailValidationOut,
)
from ..sanitize import sanitize_string

logger = logging.getLogger("latent.projects")

# Root of the Latent Underground installation (where swarm.ps1 lives)
_LU_ROOT = Path(__file__).parent.parent.parent.parent

# Scripts to copy into new project folders
_SCAFFOLD_SCRIPTS = ["swarm.ps1", "stop-swarm.ps1", "swarm.bat"]

# Directories to create in new project folders
_SCAFFOLD_DIRS = [
    ".claude/heartbeats",
    ".claude/signals",
    ".claude/handoffs",
    ".claude/prompts",
    ".claude/attention",
    ".swarm/bus",
    "tasks",
    "logs",
]

# MCP server configuration for agents
_MCP_CONFIG = {
    "mcpServers": {
        "windows-control": {
            "type": "http",
            "url": "http://localhost:3001/mcp"
        },
        "windows-control-2": {
            "type": "http",
            "url": "http://localhost:3002/mcp"
        }
    }
}

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Whitelist of columns allowed in dynamic UPDATE statements
ALLOWED_UPDATE_FIELDS = {
    "name", "goal", "project_type", "tech_stack",
    "complexity", "requirements", "folder_path", "status",
}


_404 = {404: {"model": ErrorDetail, "description": "Project not found"}}
_400 = {400: {"model": ErrorDetail, "description": "Invalid request"}}


@router.post("", response_model=ProjectOut, status_code=201,
             summary="Create project",
             responses={400: {"model": ErrorDetail, "description": "Invalid folder path"}})
async def create_project(project: ProjectCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new project and scaffold its directory structure."""
    # Validate folder_path is an absolute path
    folder = Path(project.folder_path)
    if not folder.is_absolute():
        raise HTTPException(status_code=400, detail="folder_path must be an absolute path")

    # Scaffold the project directory
    folder.mkdir(parents=True, exist_ok=True)
    for subdir in _SCAFFOLD_DIRS:
        (folder / subdir).mkdir(parents=True, exist_ok=True)
    for script in _SCAFFOLD_SCRIPTS:
        src = _LU_ROOT / script
        dest = folder / script
        if src.exists() and not dest.exists():
            shutil.copy2(src, dest)
            logger.info("Scaffolded %s into %s", script, folder)

    # Copy message bus client
    bus_src = _LU_ROOT / "backend" / "bus-client" / "swarm-msg.ps1"
    bus_dest = folder / ".swarm" / "bus" / "swarm-msg.ps1"
    if bus_src.exists() and not bus_dest.exists():
        shutil.copy2(bus_src, bus_dest)
        logger.info("Scaffolded swarm-msg.ps1 into %s", folder)

    # Create .claude/settings.json with MCP config
    settings_file = folder / ".claude" / "settings.json"
    if not settings_file.exists():
        settings_file.write_text(json.dumps(_MCP_CONFIG, indent=2), encoding="utf-8")
        logger.info("Created .claude/settings.json with MCP config in %s", folder)

    # Sanitize user-provided string fields to prevent stored XSS
    name = sanitize_string(project.name)
    goal = sanitize_string(project.goal)
    requirements = sanitize_string(project.requirements)

    cursor = await db.execute(
        """INSERT INTO projects (name, goal, project_type, tech_stack, complexity, requirements, folder_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, goal, project.project_type, project.tech_stack,
         project.complexity, requirements, project.folder_path),
    )
    await db.commit()
    project_id = cursor.lastrowid

    # Create bus.json with project_id (after insert so we have the ID)
    bus_config_file = folder / ".swarm" / "bus.json"
    if not bus_config_file.exists():
        bus_config = {"port": 8000, "project_id": project_id}
        bus_config_file.write_text(json.dumps(bus_config, indent=2), encoding="utf-8")
        logger.info("Created .swarm/bus.json for project %d", project_id)

    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    return dict(row)


@router.get("", response_model=list[ProjectOut], summary="List projects")
async def list_projects(
    search: str = "",
    status: str | None = None,
    sort: str = "created_at",
    include_archived: bool = False,
    db: aiosqlite.Connection = Depends(get_db),
):
    """List projects with optional search, status filter, and sort."""
    conditions = []
    params = []

    if not include_archived:
        conditions.append("archived_at IS NULL")

    if search:
        conditions.append("(name LIKE ? OR goal LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # Whitelist sort columns to prevent SQL injection
    allowed_sorts = {"name": "name ASC", "updated_at": "updated_at DESC", "created_at": "created_at DESC"}
    order = allowed_sorts.get(sort, "created_at DESC")

    query = f"SELECT * FROM projects{where} ORDER BY {order}, id DESC"
    rows = await (await db.execute(query, params)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Bulk operations — must come BEFORE /{project_id} to avoid route conflicts
# ---------------------------------------------------------------------------

@router.post("/bulk/archive", response_model=BulkArchiveOut,
             summary="Bulk archive projects")
async def bulk_archive(req: BulkArchiveRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Archive multiple projects at once in a single transaction."""
    archived = []
    already_archived = []
    not_found = []

    for pid in req.project_ids:
        row = await (await db.execute("SELECT id, archived_at FROM projects WHERE id = ?", (pid,))).fetchone()
        if not row:
            not_found.append(pid)
        elif row["archived_at"]:
            already_archived.append(pid)
        else:
            await db.execute(
                "UPDATE projects SET archived_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
                (pid,),
            )
            archived.append(pid)

    if archived:
        await db.commit()
    return {"archived": archived, "already_archived": already_archived, "not_found": not_found}


@router.post("/bulk/unarchive", response_model=BulkUnarchiveOut,
             summary="Bulk unarchive projects")
async def bulk_unarchive(req: BulkArchiveRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Unarchive multiple projects at once in a single transaction."""
    unarchived = []
    not_archived = []
    not_found = []

    for pid in req.project_ids:
        row = await (await db.execute("SELECT id, archived_at FROM projects WHERE id = ?", (pid,))).fetchone()
        if not row:
            not_found.append(pid)
        elif not row["archived_at"]:
            not_archived.append(pid)
        else:
            await db.execute(
                "UPDATE projects SET archived_at = NULL, updated_at = datetime('now') WHERE id = ?",
                (pid,),
            )
            unarchived.append(pid)

    if unarchived:
        await db.commit()
    return {"unarchived": unarchived, "not_archived": not_archived, "not_found": not_found}


@router.get("/{project_id}", response_model=ProjectOut, summary="Get project",
            responses=_404)
async def get_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single project by ID."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Update project",
              responses=_404)
async def update_project(project_id: int, update: ProjectUpdate, db: aiosqlite.Connection = Depends(get_db)):
    """Update project fields. Only provided fields are changed."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    fields = {k: v for k, v in update.model_dump().items() if v is not None and k in ALLOWED_UPDATE_FIELDS}
    if not fields:
        return dict(row)

    # Sanitize user-provided string fields
    for key in ("name", "goal", "requirements"):
        if key in fields and isinstance(fields[key], str):
            fields[key] = sanitize_string(fields[key])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [project_id]
    await db.execute(
        f"UPDATE projects SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
        values,
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    return dict(row)


@router.get("/{project_id}/stats", response_model=ProjectStatsOut,
            summary="Get project stats", responses=_404)
async def project_stats(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get aggregated stats for a project."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Total runs
    total_runs = (await (await db.execute(
        "SELECT COUNT(*) as cnt FROM swarm_runs WHERE project_id = ?", (project_id,)
    )).fetchone())["cnt"]

    # Average duration (only completed runs with both timestamps)
    avg_row = await (await db.execute(
        """SELECT AVG(
            CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS INTEGER)
        ) as avg_duration
        FROM swarm_runs
        WHERE project_id = ? AND ended_at IS NOT NULL""",
        (project_id,),
    )).fetchone()
    avg_duration = round(avg_row["avg_duration"]) if avg_row["avg_duration"] is not None else None

    # Total tasks completed
    total_tasks = (await (await db.execute(
        "SELECT COALESCE(SUM(tasks_completed), 0) as total FROM swarm_runs WHERE project_id = ?",
        (project_id,),
    )).fetchone())["total"]

    return {
        "project_id": project_id,
        "total_runs": total_runs,
        "avg_duration_seconds": avg_duration,
        "total_tasks_completed": total_tasks,
    }


@router.get("/{project_id}/analytics", response_model=ProjectAnalyticsOut,
            summary="Get project analytics", responses=_404)
async def project_analytics(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get detailed analytics for a project: run trends, efficiency, phase durations."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Single aggregate query for all stats (5 queries -> 1)
    stats_row = await (await db.execute(
        """SELECT
            COUNT(*) as total_runs,
            AVG(CASE WHEN ended_at IS NOT NULL
                THEN CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS INTEGER)
                END) as avg_duration,
            COALESCE(SUM(tasks_completed), 0) as total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END), 0) * 100 as success_rate
        FROM swarm_runs WHERE project_id = ?""",
        (project_id,),
    )).fetchone()

    total_runs = stats_row["total_runs"]
    avg_duration = round(stats_row["avg_duration"]) if stats_row["avg_duration"] is not None else None
    total_tasks = stats_row["total_tasks"]
    success_rate = round(stats_row["success_rate"], 1) if stats_row["success_rate"] is not None else None

    # Run history for trends (last 20 runs)
    trend_rows = await (await db.execute(
        """SELECT started_at, ended_at, status, tasks_completed
           FROM swarm_runs WHERE project_id = ?
           ORDER BY started_at DESC, id DESC LIMIT 20""",
        (project_id,),
    )).fetchall()
    run_trends = [dict(r) for r in trend_rows]

    return {
        "project_id": project_id,
        "total_runs": total_runs,
        "avg_duration": avg_duration,
        "total_tasks": total_tasks,
        "success_rate": success_rate,
        "run_trends": run_trends,
    }


@router.get("/{project_id}/quota", response_model=QuotaOut,
            summary="Get project quota and usage", responses=_404)
async def project_quota(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Return resource quota configuration and current live usage for a project."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Import swarm internals for live data
    from .swarm import _get_project_quota, _project_resource_usage

    import time as _time
    from datetime import datetime as _dt

    quota = await _get_project_quota(project_id)
    usage = _project_resource_usage.get(project_id, {})

    elapsed_hours = None
    started_at_str = None
    if usage.get("started_at"):
        elapsed_hours = round((_time.time() - usage["started_at"]) / 3600, 2)
        started_at_str = _dt.fromtimestamp(usage["started_at"]).isoformat()

    return {
        "project_id": project_id,
        "quota": {
            "max_agents_concurrent": quota.get("max_agents_concurrent"),
            "max_duration_hours": quota.get("max_duration_hours"),
            "max_restarts_per_agent": quota.get("max_restarts_per_agent"),
        },
        "usage": {
            "agent_count": usage.get("agent_count", 0),
            "restart_counts": usage.get("restart_counts", {}),
            "started_at": started_at_str,
            "elapsed_hours": elapsed_hours,
        },
    }


@router.get("/{project_id}/health", response_model=ProjectHealthOut,
            summary="Get project health", responses=_404)
async def project_health(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Project-specific health metrics with trend direction."""
    row = await (await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    from datetime import datetime as _dt

    runs = await (await db.execute(
        "SELECT id, status, summary, started_at, ended_at FROM swarm_runs "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 10",
        (project_id,),
    )).fetchall()

    if not runs:
        return {
            "project_id": project_id,
            "crash_rate": 0.0,
            "error_density": 0.0,
            "avg_duration_seconds": None,
            "status": "healthy",
            "trend": "stable",
            "run_count": 0,
        }

    crash_row = await (await db.execute(
        "SELECT COUNT(*) FROM agent_events WHERE project_id = ? AND event_type = 'agent_crashed'",
        (project_id,),
    )).fetchone()
    crash_count = crash_row[0] if crash_row else 0

    total_agents = 0
    total_output_lines = 0
    total_error_count = 0
    durations = []
    per_run_crash_rates = []

    for run in runs:
        summary = None
        if run["summary"]:
            try:
                summary = json.loads(run["summary"])
            except (json.JSONDecodeError, TypeError):
                pass

        if summary:
            ac = summary.get("agent_count", 0)
            total_agents += ac
            total_output_lines += summary.get("total_output_lines", 0)
            total_error_count += summary.get("error_count", 0)
            if ac > 0:
                per_run_crash_rates.append(summary.get("error_count", 0) / ac)
            else:
                per_run_crash_rates.append(0.0)

        if run["started_at"] and run["ended_at"]:
            try:
                started = _dt.fromisoformat(run["started_at"])
                ended = _dt.fromisoformat(run["ended_at"])
                durations.append(int((ended - started).total_seconds()))
            except (ValueError, TypeError):
                pass

    crash_rate = crash_count / max(total_agents, 1)
    error_density = total_error_count / max(total_output_lines, 1)
    avg_dur = int(sum(durations) / len(durations)) if durations else None

    # Compute trend
    trend = "stable"
    if len(per_run_crash_rates) >= 2:
        half = len(per_run_crash_rates) // 2
        first = sum(per_run_crash_rates[:half]) / max(half, 1)
        second = sum(per_run_crash_rates[half:]) / max(len(per_run_crash_rates) - half, 1)
        diff = second - first
        if diff < -0.05:
            trend = "improving"
        elif diff > 0.05:
            trend = "degrading"

    # Classify health
    status = "healthy"
    if crash_rate >= 0.3:
        status = "critical"
    elif crash_rate >= 0.1:
        status = "warning"

    return {
        "project_id": project_id,
        "crash_rate": round(crash_rate, 3),
        "error_density": round(error_density, 5),
        "avg_duration_seconds": avg_dur,
        "status": status,
        "trend": trend,
        "run_count": len(runs),
    }


@router.get("/{project_id}/guardrails", response_model=GuardrailValidationOut,
            summary="Get guardrail config and last results", responses=_404)
async def project_guardrails(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Return guardrail configuration and last validation results for a project."""
    row = await (await db.execute("SELECT config FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    cfg = json.loads(row["config"]) if row["config"] else {}
    guardrails = cfg.get("guardrails", [])

    # Find last run with guardrail_results
    last_results = None
    last_run_id = None
    run_row = await (await db.execute(
        "SELECT id, guardrail_results FROM swarm_runs "
        "WHERE project_id = ? AND guardrail_results IS NOT NULL "
        "ORDER BY id DESC LIMIT 1",
        (project_id,),
    )).fetchone()
    if run_row:
        last_run_id = run_row["id"]
        try:
            last_results = json.loads(run_row["guardrail_results"])
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "project_id": project_id,
        "guardrails": guardrails,
        "last_results": last_results,
        "last_run_id": last_run_id,
    }


@router.get("/{project_id}/dashboard", response_model=ProjectDashboardOut,
            summary="Get project dashboard", responses=_404)
async def project_dashboard(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get combined dashboard data in a single call: project info, agents, tasks, runs, output."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])

    # --- Agent info (import swarm internals for live process data) ---
    from .swarm import (
        _project_agent_keys, _agent_processes, _agent_output_buffers,
        _agent_started_at, _project_output_buffers, _buffers_lock,
        _any_agent_alive,
    )

    keys = sorted(_project_agent_keys(project_id))
    agents = []
    for key in keys:
        agent_name = key.split(":")[1]
        proc = _agent_processes.get(key)
        is_alive = proc is not None and proc.poll() is None
        exit_code = None
        if proc and not is_alive:
            exit_code = proc.returncode
        with _buffers_lock:
            line_count = len(_agent_output_buffers.get(key, deque()))
        agents.append({
            "name": agent_name,
            "pid": proc.pid if proc else None,
            "alive": is_alive,
            "exit_code": exit_code,
            "output_lines": line_count,
            "started_at": _agent_started_at.get(key),
            "supports_stdin": bool(proc and proc.stdin),
        })

    any_alive = _any_agent_alive(project_id)

    # --- Task progress from TASKS.md ---
    tasks_file = folder / "tasks" / "TASKS.md"
    task_progress = {"total": 0, "done": 0, "percent": 0}
    if tasks_file.exists():
        try:
            content = tasks_file.read_text()
            total = len(re.findall(r"- \[[ x]\]", content))
            done = len(re.findall(r"- \[x\]", content))
            task_progress = {
                "total": total,
                "done": done,
                "percent": round((done / total) * 100, 1) if total > 0 else 0,
            }
        except Exception:
            pass

    # --- Run stats (single optimized query) ---
    stats_row = await (await db.execute(
        """SELECT
            COUNT(*) as total_runs,
            AVG(CASE WHEN ended_at IS NOT NULL
                THEN CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS INTEGER)
                END) as avg_duration,
            SUM(CASE WHEN status = 'completed' THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END), 0) * 100 as success_rate
        FROM swarm_runs WHERE project_id = ?""",
        (project_id,),
    )).fetchone()

    total_runs = stats_row["total_runs"]
    avg_duration = round(stats_row["avg_duration"]) if stats_row["avg_duration"] is not None else None
    success_rate = round(stats_row["success_rate"], 1) if stats_row["success_rate"] is not None else None

    # --- Recent runs (last 5) ---
    from datetime import datetime
    recent_rows = await (await db.execute(
        """SELECT id, status, started_at, ended_at
           FROM swarm_runs WHERE project_id = ?
           ORDER BY started_at DESC, id DESC LIMIT 5""",
        (project_id,),
    )).fetchall()

    recent_runs = []
    for r in recent_rows:
        run = dict(r)
        dur = None
        if run["started_at"] and run["ended_at"]:
            try:
                s = datetime.fromisoformat(run["started_at"])
                e = datetime.fromisoformat(run["ended_at"])
                dur = int((e - s).total_seconds())
            except (ValueError, TypeError):
                pass
        recent_runs.append({
            "id": run["id"],
            "status": run["status"],
            "started_at": run["started_at"],
            "ended_at": run["ended_at"],
            "duration_seconds": dur,
        })

    # --- Output summary ---
    with _buffers_lock:
        proj_buf = _project_output_buffers.get(project_id, deque())
        output_line_count = len(proj_buf)
        # Use islice to get last 10 lines without full list copy
        last_lines = list(itertools.islice(proj_buf, max(0, len(proj_buf) - 10), None)) if proj_buf else []

    return {
        "project_id": project_id,
        "name": project["name"],
        "status": project["status"],
        "folder_path": project["folder_path"],
        "agents": agents,
        "any_alive": any_alive,
        "tasks": task_progress,
        "total_runs": total_runs,
        "avg_duration_seconds": avg_duration,
        "success_rate": success_rate,
        "recent_runs": recent_runs,
        "output_line_count": output_line_count,
        "last_output_lines": last_lines,
    }


@router.patch("/{project_id}/config", response_model=ProjectConfigUpdateOut,
              summary="Update project config", responses=_404)
async def update_project_config(
    project_id: int, config: ProjectConfig, db: aiosqlite.Connection = Depends(get_db)
):
    """Save project agent configuration (agent count, max phases, custom prompts)."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    config_json = json.dumps(config.model_dump(exclude_none=True))
    await db.execute(
        "UPDATE projects SET config = ?, updated_at = datetime('now') WHERE id = ?",
        (config_json, project_id),
    )
    await db.commit()

    return {"project_id": project_id, "config": config.model_dump(exclude_none=True)}


@router.delete("/{project_id}", status_code=204, summary="Delete project",
               responses=_404)
async def delete_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Permanently delete a project and its database records."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Clean up swarm tracking state for this project
    from .swarm import (
        cancel_drain_tasks, _project_locks, _project_resource_usage,
        _known_directives, _last_output_at,
    )
    await cancel_drain_tasks(project_id)
    _project_locks.pop(project_id, None)
    _project_resource_usage.pop(project_id, None)
    _known_directives.pop(project_id, None)
    _last_output_at.pop(project_id, None)

    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()


@router.post("/{project_id}/archive", response_model=ProjectOut,
             summary="Archive project", responses={**_404, **_400})
async def archive_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Archive a project to hide it from the default project list."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if dict(row).get("archived_at"):
        raise HTTPException(status_code=400, detail="Project is already archived")
    await db.execute(
        "UPDATE projects SET archived_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
        (project_id,),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    return dict(row)


@router.post("/{project_id}/unarchive", response_model=ProjectOut,
             summary="Unarchive project", responses={**_404, **_400})
async def unarchive_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Unarchive a project to show it in the default project list."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if not dict(row).get("archived_at"):
        raise HTTPException(status_code=400, detail="Project is not archived")
    await db.execute(
        "UPDATE projects SET archived_at = NULL, updated_at = datetime('now') WHERE id = ?",
        (project_id,),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    return dict(row)
