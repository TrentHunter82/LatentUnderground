"""System metrics endpoint - CPU, memory, disk, Python version, app info."""

import json
import logging
import platform
import time
from datetime import datetime
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import config
from .. import database
from ..database import get_db
from ..models.responses import SystemInfoOut, HealthTrendsOut, ProjectHealthOut

logger = logging.getLogger("latent.system")

router = APIRouter(prefix="/api/system", tags=["system"])

_start_time = time.time()


@router.get("", response_model=SystemInfoOut, summary="System metrics")
async def system_info():
    """Return system resource usage and application metadata."""
    cpu_percent = 0.0
    mem = None
    disk = None
    cpu_count = 1

    try:
        import psutil  # Lazy import: avoid ~50ms startup cost when not needed

        try:
            cpu_percent = psutil.cpu_percent(interval=0)
        except (psutil.Error, OSError):
            pass
        try:
            mem = psutil.virtual_memory()
        except (psutil.Error, OSError):
            pass
        try:
            disk = psutil.disk_usage(str(database.DB_PATH.parent))
        except (psutil.Error, OSError):
            pass
        cpu_count = psutil.cpu_count() or 1
    except ImportError:
        logger.debug("psutil not available, returning zeros for system metrics")

    # DB file size
    db_size_bytes = 0
    try:
        db_size_bytes = database.DB_PATH.stat().st_size
        wal = database.DB_PATH.with_suffix(".db-wal")
        shm = database.DB_PATH.with_suffix(".db-shm")
        if wal.exists():
            db_size_bytes += wal.stat().st_size
        if shm.exists():
            db_size_bytes += shm.stat().st_size
    except OSError:
        pass

    return {
        "cpu_percent": cpu_percent,
        "memory_percent": mem.percent if mem else 0.0,
        "memory_used_mb": round(mem.used / (1024 * 1024)) if mem else 0,
        "memory_total_mb": round(mem.total / (1024 * 1024)) if mem else 0,
        "disk_percent": disk.percent if disk else 0.0,
        "disk_free_gb": round(disk.free / (1024 ** 3), 1) if disk else 0.0,
        "disk_total_gb": round(disk.total / (1024 ** 3), 1) if disk else 0.0,
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "app_version": config.APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "db_size_bytes": db_size_bytes,
        "cpu_count": cpu_count,
    }


# ---------------------------------------------------------------------------
# Database diagnostics
# ---------------------------------------------------------------------------

# Pre-defined queries that represent the most common API access patterns
_DIAGNOSTIC_QUERIES = {
    "list_projects": (
        "SELECT * FROM projects WHERE archived_at IS NULL ORDER BY created_at DESC, id DESC"
    ),
    "list_projects_filtered": (
        "SELECT * FROM projects WHERE archived_at IS NULL AND status = 'running' "
        "ORDER BY created_at DESC, id DESC"
    ),
    "project_runs_stats": (
        "SELECT COUNT(*), AVG(CASE WHEN ended_at IS NOT NULL "
        "THEN CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS INTEGER) END), "
        "COALESCE(SUM(tasks_completed), 0), "
        "SUM(CASE WHEN status = 'completed' THEN 1.0 ELSE 0 END) "
        "/ NULLIF(SUM(CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END), 0) * 100 "
        "FROM swarm_runs WHERE project_id = 1"
    ),
    "run_trends": (
        "SELECT started_at, ended_at, status, tasks_completed "
        "FROM swarm_runs WHERE project_id = 1 "
        "ORDER BY started_at DESC, id DESC LIMIT 20"
    ),
    "running_runs_update": (
        "SELECT id FROM swarm_runs WHERE project_id = 1 AND status = 'running'"
    ),
    "project_webhooks": (
        "SELECT * FROM webhooks WHERE project_id = 1 AND enabled = 1"
    ),
}


@router.get("/db/indexes", summary="List database indexes")
async def db_indexes(db: aiosqlite.Connection = Depends(get_db)):
    """List all indexes in the database with their definitions."""
    rows = await (await db.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL "
        "ORDER BY tbl_name, name"
    )).fetchall()
    return {
        "indexes": [{"name": r["name"], "table": r["tbl_name"], "sql": r["sql"]} for r in rows],
        "schema_version": database.SCHEMA_VERSION,
    }


@router.get("/db/explain", summary="EXPLAIN QUERY PLAN for common queries")
async def db_explain(
    query: Optional[str] = Query(
        default=None,
        description="Named query to explain (omit for all common queries)",
    ),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Run EXPLAIN QUERY PLAN on common API queries to diagnose index usage.

    Returns the SQLite query plan showing whether indexes are used or full scans occur.
    """
    targets = {}
    if query and query in _DIAGNOSTIC_QUERIES:
        targets[query] = _DIAGNOSTIC_QUERIES[query]
    elif query:
        return {"error": f"Unknown query name. Available: {list(_DIAGNOSTIC_QUERIES.keys())}"}
    else:
        targets = _DIAGNOSTIC_QUERIES

    results = {}
    for name, sql in targets.items():
        try:
            rows = await (await db.execute(f"EXPLAIN QUERY PLAN {sql}")).fetchall()
            plan_lines = [dict(r) for r in rows]
            # Check if any step uses SCAN (full table scan) vs SEARCH (index)
            uses_index = all("SCAN" not in str(r.get("detail", "")) for r in plan_lines)
            results[name] = {
                "sql": sql,
                "plan": plan_lines,
                "uses_index": uses_index,
            }
        except Exception as e:
            results[name] = {"sql": sql, "error": str(e)}

    return {"queries": results}


# ---------------------------------------------------------------------------
# Health Trend Detection
# ---------------------------------------------------------------------------

def _classify_health(crash_rate: float) -> str:
    """Classify health status based on crash rate."""
    if crash_rate < 0.1:
        return "healthy"
    elif crash_rate < 0.3:
        return "warning"
    return "critical"


def _compute_trend(recent_rates: list[float]) -> str:
    """Compute trend direction from a series of crash rates."""
    if len(recent_rates) < 2:
        return "stable"
    first_half = sum(recent_rates[:len(recent_rates) // 2]) / max(len(recent_rates) // 2, 1)
    second_half = sum(recent_rates[len(recent_rates) // 2:]) / max(len(recent_rates) - len(recent_rates) // 2, 1)
    diff = second_half - first_half
    if diff < -0.05:
        return "improving"
    elif diff > 0.05:
        return "degrading"
    return "stable"


@router.get("/health/trends", response_model=HealthTrendsOut,
            summary="Health trend metrics for all projects")
async def health_trends(db: aiosqlite.Connection = Depends(get_db)):
    """Per-project health score based on last 10 runs.

    Computes crash rate, error density, and trend direction for each project.
    """
    # Get all non-archived projects
    projects = await (await db.execute(
        "SELECT id, name FROM projects WHERE archived_at IS NULL ORDER BY id"
    )).fetchall()

    results = []
    for proj in projects:
        pid = proj["id"]
        pname = proj["name"]

        # Get last 10 completed/stopped runs
        runs = await (await db.execute(
            "SELECT id, status, summary, started_at, ended_at FROM swarm_runs "
            "WHERE project_id = ? ORDER BY id DESC LIMIT 10",
            (pid,),
        )).fetchall()

        if not runs:
            results.append({
                "project_id": pid,
                "project_name": pname,
                "crash_rate": 0.0,
                "error_density": 0.0,
                "avg_duration_seconds": None,
                "status": "healthy",
                "trend": "stable",
                "total_runs_analyzed": 0,
            })
            continue

        # Compute crash rate from agent_events
        crash_count = await (await db.execute(
            "SELECT COUNT(*) FROM agent_events WHERE project_id = ? AND event_type = 'agent_crashed'",
            (pid,),
        )).fetchone()
        crash_count = crash_count[0] if crash_count else 0

        # Get total agent count from run summaries
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
                # Per-run crash rate for trend detection
                if ac > 0:
                    per_run_crash_rates.append(summary.get("error_count", 0) / ac)
                else:
                    per_run_crash_rates.append(0.0)

            if run["started_at"] and run["ended_at"]:
                try:
                    started = datetime.fromisoformat(run["started_at"])
                    ended = datetime.fromisoformat(run["ended_at"])
                    durations.append(int((ended - started).total_seconds()))
                except (ValueError, TypeError):
                    pass

        crash_rate = crash_count / max(total_agents, 1)
        error_density = total_error_count / max(total_output_lines, 1)
        avg_dur = int(sum(durations) / len(durations)) if durations else None

        results.append({
            "project_id": pid,
            "project_name": pname,
            "crash_rate": round(crash_rate, 3),
            "error_density": round(error_density, 5),
            "avg_duration_seconds": avg_dur,
            "status": _classify_health(crash_rate),
            "trend": _compute_trend(per_run_crash_rates),
            "total_runs_analyzed": len(runs),
        })

    return {
        "projects": results,
        "computed_at": datetime.now().isoformat(),
    }


@router.get("/health/project/{project_id}", response_model=ProjectHealthOut,
            summary="Health metrics for a single project")
async def project_health(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Project-specific health metrics with trend direction."""
    row = await (await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

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

    crash_count = await (await db.execute(
        "SELECT COUNT(*) FROM agent_events WHERE project_id = ? AND event_type = 'agent_crashed'",
        (project_id,),
    )).fetchone()
    crash_count = crash_count[0] if crash_count else 0

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
                started = datetime.fromisoformat(run["started_at"])
                ended = datetime.fromisoformat(run["ended_at"])
                durations.append(int((ended - started).total_seconds()))
            except (ValueError, TypeError):
                pass

    crash_rate = crash_count / max(total_agents, 1)
    error_density = total_error_count / max(total_output_lines, 1)
    avg_dur = int(sum(durations) / len(durations)) if durations else None

    return {
        "project_id": project_id,
        "crash_rate": round(crash_rate, 3),
        "error_density": round(error_density, 5),
        "avg_duration_seconds": avg_dur,
        "status": _classify_health(crash_rate),
        "trend": _compute_trend(per_run_crash_rates),
        "run_count": len(runs),
    }
