import json
import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectConfig
from ..models.responses import ProjectStatsOut, ProjectAnalyticsOut, ProjectConfigUpdateOut, ErrorDetail

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
    "tasks",
    "logs",
]

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

    cursor = await db.execute(
        """INSERT INTO projects (name, goal, project_type, tech_stack, complexity, requirements, folder_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project.name, project.goal, project.project_type, project.tech_stack,
         project.complexity, project.requirements, project.folder_path),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))).fetchone()
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

    # Total runs
    total_runs = (await (await db.execute(
        "SELECT COUNT(*) as cnt FROM swarm_runs WHERE project_id = ?", (project_id,)
    )).fetchone())["cnt"]

    # Average duration (completed runs with both timestamps)
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

    # Success rate (completed vs total finished runs)
    finished = (await (await db.execute(
        "SELECT COUNT(*) as cnt FROM swarm_runs WHERE project_id = ? AND ended_at IS NOT NULL",
        (project_id,),
    )).fetchone())["cnt"]
    completed = (await (await db.execute(
        "SELECT COUNT(*) as cnt FROM swarm_runs WHERE project_id = ? AND status = 'completed'",
        (project_id,),
    )).fetchone())["cnt"]
    success_rate = round((completed / finished) * 100, 1) if finished > 0 else None

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
