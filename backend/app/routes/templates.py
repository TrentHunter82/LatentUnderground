"""Swarm template CRUD endpoints - save/load project configs as presets."""

import json
import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..database import get_db
from ..models.responses import TemplateOut, ErrorDetail
from ..sanitize import sanitize_string

logger = logging.getLogger("latent.templates")

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    """Create a reusable swarm configuration template."""
    name: str = Field(..., min_length=1, max_length=200, examples=["Fast Build"])
    description: Optional[str] = Field("", max_length=2000, examples=["Optimized for quick iteration cycles"])
    config: dict = Field(default_factory=dict, examples=[{"agent_count": 4, "max_phases": 6}])


class TemplateUpdate(BaseModel):
    """Update template fields. Only provided fields are changed."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, examples=["Updated Name"])
    description: Optional[str] = Field(None, max_length=2000)
    config: Optional[dict] = None


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert a template row to a response dict with parsed config."""
    d = dict(row)
    try:
        d["config"] = json.loads(d["config"])
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse config for template %s: %s", d.get("id"), e)
        d["config"] = {}
    return d


_404 = {404: {"model": ErrorDetail, "description": "Template not found"}}


@router.post("", status_code=201, response_model=TemplateOut,
             summary="Create template")
async def create_template(body: TemplateCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Create a new swarm configuration template."""
    config_json = json.dumps(body.config)
    name = sanitize_string(body.name)
    description = sanitize_string(body.description or "")
    cursor = await db.execute(
        "INSERT INTO swarm_templates (name, description, config) VALUES (?, ?, ?)",
        (name, description, config_json),
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (cursor.lastrowid,)
    )).fetchone()
    return _row_to_dict(row)


@router.get("", response_model=list[TemplateOut], summary="List templates")
async def list_templates(db: aiosqlite.Connection = Depends(get_db)):
    """List all saved swarm configuration templates."""
    rows = await (await db.execute(
        "SELECT * FROM swarm_templates ORDER BY created_at DESC, id DESC"
    )).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/{template_id}", response_model=TemplateOut,
            summary="Get template", responses=_404)
async def get_template(template_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a single template by ID."""
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_dict(row)


@router.patch("/{template_id}", response_model=TemplateOut,
              summary="Update template", responses=_404)
async def update_template(template_id: int, body: TemplateUpdate, db: aiosqlite.Connection = Depends(get_db)):
    """Update template fields. Only provided fields are changed."""
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(sanitize_string(body.name))
    if body.description is not None:
        updates.append("description = ?")
        params.append(sanitize_string(body.description))
    if body.config is not None:
        updates.append("config = ?")
        params.append(json.dumps(body.config))

    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(template_id)
        await db.execute(
            f"UPDATE swarm_templates SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()

    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    return _row_to_dict(row)


@router.delete("/{template_id}", status_code=204,
               summary="Delete template", responses=_404)
async def delete_template(template_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Permanently delete a template."""
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.execute("DELETE FROM swarm_templates WHERE id = ?", (template_id,))
    await db.commit()
    return Response(status_code=204)
