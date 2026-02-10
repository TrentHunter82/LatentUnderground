"""Tests for swarm template CRUD endpoints."""

import pytest


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


class TestTemplateEdgeCases:
    """Edge cases for template operations."""

    async def test_update_nonexistent_template(self, client):
        """PATCH on non-existent template returns 404."""
        resp = await client.patch("/api/templates/99999", json={"name": "Ghost"})
        assert resp.status_code == 404

    async def test_update_with_no_fields(self, client):
        """PATCH with all None fields is a no-op but returns current template."""
        # Create template first
        create_resp = await client.post("/api/templates", json={
            "name": "NoOp Test",
            "config": {"agent_count": 4},
        })
        tid = create_resp.json()["id"]

        resp = await client.patch(f"/api/templates/{tid}", json={})
        assert resp.status_code == 200
        assert resp.json()["name"] == "NoOp Test"

    async def test_update_description_only(self, client):
        """PATCH with only description updates just that field."""
        create_resp = await client.post("/api/templates", json={
            "name": "Desc Update",
            "description": "Original desc",
            "config": {"agent_count": 2},
        })
        tid = create_resp.json()["id"]

        resp = await client.patch(f"/api/templates/{tid}", json={
            "description": "New description",
        })
        assert resp.status_code == 200
        assert resp.json()["description"] == "New description"
        assert resp.json()["name"] == "Desc Update"  # unchanged

    async def test_create_with_empty_config(self, client):
        """Create template with empty config dict."""
        resp = await client.post("/api/templates", json={
            "name": "Empty Config",
            "config": {},
        })
        assert resp.status_code == 201
        assert resp.json()["config"] == {}

    async def test_create_with_nested_config(self, client):
        """Create template with deeply nested config."""
        resp = await client.post("/api/templates", json={
            "name": "Nested Config",
            "config": {"agent_count": 4, "extra": {"key": "value", "list": [1, 2, 3]}},
        })
        assert resp.status_code == 201
        assert resp.json()["config"]["extra"]["list"] == [1, 2, 3]

    async def test_list_ordering(self, client):
        """Templates listed in reverse chronological order."""
        await client.post("/api/templates", json={"name": "First", "config": {}})
        await client.post("/api/templates", json={"name": "Second", "config": {}})

        resp = await client.get("/api/templates")
        names = [t["name"] for t in resp.json()]
        assert names[0] == "Second"  # most recent first
        assert names[1] == "First"
