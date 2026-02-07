import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models.project import ProjectCreate, ProjectUpdate, ProjectOut, ProjectConfig

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Whitelist of columns allowed in dynamic UPDATE statements
ALLOWED_UPDATE_FIELDS = {
    "name", "goal", "project_type", "tech_stack",
    "complexity", "requirements", "folder_path", "status",
}


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(project: ProjectCreate, db: aiosqlite.Connection = Depends(get_db)):
    # Validate folder_path is an absolute path
    folder = Path(project.folder_path)
    if not folder.is_absolute():
        raise HTTPException(status_code=400, detail="folder_path must be an absolute path")

    cursor = await db.execute(
        """INSERT INTO projects (name, goal, project_type, tech_stack, complexity, requirements, folder_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project.name, project.goal, project.project_type, project.tech_stack,
         project.complexity, project.requirements, project.folder_path),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return dict(row)


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: aiosqlite.Connection = Depends(get_db)):
    rows = await (await db.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC")).fetchall()
    return [dict(r) for r in rows]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, update: ProjectUpdate, db: aiosqlite.Connection = Depends(get_db)):
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


@router.get("/{project_id}/stats")
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


@router.patch("/{project_id}/config")
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


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()
