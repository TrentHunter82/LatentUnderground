"""Plugin management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..plugins import plugin_manager

logger = logging.getLogger("latent.plugins")

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    config: dict = Field(default_factory=dict)
    hooks: Optional[dict] = Field(default_factory=dict)


@router.get("")
async def list_plugins():
    """List all discovered plugins."""
    return [p.to_dict() for p in plugin_manager.list_plugins()]


@router.get("/{name}")
async def get_plugin(name: str):
    """Get a plugin by name."""
    plugin = plugin_manager.get(name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin.to_dict()


@router.post("", status_code=201)
async def create_plugin(body: PluginCreateRequest):
    """Create a new plugin configuration file."""
    if plugin_manager.get(body.name):
        raise HTTPException(status_code=409, detail="Plugin with this name already exists")
    plugin = plugin_manager.create_plugin(
        name=body.name,
        description=body.description,
        config=body.config,
        hooks=body.hooks or {},
    )
    return plugin.to_dict()


@router.post("/{name}/enable")
async def enable_plugin(name: str):
    """Enable a plugin."""
    if not plugin_manager.enable(name):
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"name": name, "enabled": True}


@router.post("/{name}/disable")
async def disable_plugin(name: str):
    """Disable a plugin."""
    if not plugin_manager.disable(name):
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"name": name, "enabled": False}


@router.delete("/{name}", status_code=204)
async def delete_plugin(name: str):
    """Delete a plugin."""
    if not plugin_manager.delete_plugin(name):
        raise HTTPException(status_code=404, detail="Plugin not found")
