"""Tests for swarm template CRUD endpoints.

Templates allow saving/loading project configs as reusable presets.
These tests will activate once Claude-1 implements the templates table and routes.
"""

import pytest

# Check if templates route exists
try:
    from app.routes import templates  # noqa: F401
    TEMPLATES_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    TEMPLATES_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not TEMPLATES_AVAILABLE,
    reason="Swarm templates not yet implemented (waiting for Claude-1)"
)


class TestTemplateCreate:
    """Test creating swarm templates."""

    async def test_create_template(self, client):
        resp = await client.post("/api/templates", json={
            "name": "Default 4-Agent",
            "description": "Standard 4-agent configuration",
            "config": {
                "agent_count": 4,
                "max_phases": 3,
            }
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Default 4-Agent"
        assert data["config"]["agent_count"] == 4

    async def test_create_template_minimal(self, client):
        resp = await client.post("/api/templates", json={
            "name": "Minimal",
            "config": {"agent_count": 2},
        })
        assert resp.status_code == 201

    async def test_create_template_requires_name(self, client):
        resp = await client.post("/api/templates", json={
            "config": {"agent_count": 2},
        })
        assert resp.status_code == 422


class TestTemplateRead:
    """Test listing and fetching templates."""

    async def test_list_templates_empty(self, client):
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_templates_returns_created(self, client):
        # Create a template first
        await client.post("/api/templates", json={
            "name": "Test Template",
            "config": {"agent_count": 4},
        })
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_get_template_by_id(self, client):
        create_resp = await client.post("/api/templates", json={
            "name": "Fetch Me",
            "config": {"agent_count": 6},
        })
        tid = create_resp.json()["id"]

        resp = await client.get(f"/api/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    async def test_get_nonexistent_template(self, client):
        resp = await client.get("/api/templates/99999")
        assert resp.status_code == 404


class TestTemplateUpdate:
    """Test updating templates."""

    async def test_update_template_name(self, client):
        create_resp = await client.post("/api/templates", json={
            "name": "Original",
            "config": {"agent_count": 4},
        })
        tid = create_resp.json()["id"]

        resp = await client.patch(f"/api/templates/{tid}", json={
            "name": "Updated Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_template_config(self, client):
        create_resp = await client.post("/api/templates", json={
            "name": "Config Update",
            "config": {"agent_count": 4},
        })
        tid = create_resp.json()["id"]

        resp = await client.patch(f"/api/templates/{tid}", json={
            "config": {"agent_count": 8, "max_phases": 5},
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["agent_count"] == 8


class TestTemplateDelete:
    """Test deleting templates."""

    async def test_delete_template(self, client):
        create_resp = await client.post("/api/templates", json={
            "name": "Delete Me",
            "config": {"agent_count": 2},
        })
        tid = create_resp.json()["id"]

        resp = await client.delete(f"/api/templates/{tid}")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get(f"/api/templates/{tid}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_template(self, client):
        resp = await client.delete("/api/templates/99999")
        assert resp.status_code == 404
