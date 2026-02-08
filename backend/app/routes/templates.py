"""Swarm template CRUD endpoints - save/load project configs as presets."""

import json
import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..database import get_db

logger = logging.getLogger("latent.templates")

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field("", max_length=2000)
    config: dict = Field(default_factory=dict)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    config: Optional[dict] = None


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert a template row to a response dict with parsed config."""
    d = dict(row)
    try:
        d["config"] = json.loads(d["config"])
    except (json.JSONDecodeError, TypeError):
        d["config"] = {}
    return d


@router.post("", status_code=201)
async def create_template(body: TemplateCreate, db: aiosqlite.Connection = Depends(get_db)):
    config_json = json.dumps(body.config)
    cursor = await db.execute(
        "INSERT INTO swarm_templates (name, description, config) VALUES (?, ?, ?)",
        (body.name, body.description or "", config_json),
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (cursor.lastrowid,)
    )).fetchone()
    return _row_to_dict(row)


@router.get("")
async def list_templates(db: aiosqlite.Connection = Depends(get_db)):
    rows = await (await db.execute(
        "SELECT * FROM swarm_templates ORDER BY created_at DESC, id DESC"
    )).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/{template_id}")
async def get_template(template_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _row_to_dict(row)


@router.patch("/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
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


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute(
        "SELECT * FROM swarm_templates WHERE id = ?", (template_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.execute("DELETE FROM swarm_templates WHERE id = ?", (template_id,))
    await db.commit()
    return Response(status_code=204)
