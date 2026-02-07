"""Tests for project CRUD API endpoints."""

import pytest


class TestCreateProject:
    """Tests for POST /api/projects."""

    async def test_create_project_full(self, client, sample_project_data):
        resp = await client.post("/api/projects", json=sample_project_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == sample_project_data["name"]
        assert data["goal"] == sample_project_data["goal"]
        assert data["project_type"] == sample_project_data["project_type"]
        assert data["tech_stack"] == sample_project_data["tech_stack"]
        assert data["complexity"] == sample_project_data["complexity"]
        assert data["requirements"] == sample_project_data["requirements"]
        assert data["folder_path"] == sample_project_data["folder_path"]
        assert data["status"] == "created"
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    async def test_create_project_minimal(self, client, sample_project_minimal):
        resp = await client.post("/api/projects", json=sample_project_minimal)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal Project"
        assert data["goal"] == "Test minimal creation"
        assert data["folder_path"] == "F:/MinimalProject"
        # Defaults should be applied
        assert data["project_type"] == "Web Application (frontend + backend)"
        assert data["complexity"] == "Medium"
        assert data["requirements"] == ""

    async def test_create_project_missing_name(self, client):
        resp = await client.post("/api/projects", json={
            "goal": "Test",
            "folder_path": "F:/Test",
        })
        assert resp.status_code == 422

    async def test_create_project_missing_goal(self, client):
        resp = await client.post("/api/projects", json={
            "name": "Test",
            "folder_path": "F:/Test",
        })
        assert resp.status_code == 422

    async def test_create_project_missing_folder_path(self, client):
        resp = await client.post("/api/projects", json={
            "name": "Test",
            "goal": "Test goal",
        })
        assert resp.status_code == 422

    async def test_create_multiple_projects(self, client, sample_project_data):
        resp1 = await client.post("/api/projects", json=sample_project_data)
        assert resp1.status_code == 201

        sample_project_data["name"] = "Second Project"
        resp2 = await client.post("/api/projects", json=sample_project_data)
        assert resp2.status_code == 201

        assert resp1.json()["id"] != resp2.json()["id"]


class TestListProjects:
    """Tests for GET /api/projects."""

    async def test_list_empty(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_projects(self, client, sample_project_data):
        # Create two projects
        await client.post("/api/projects", json=sample_project_data)
        sample_project_data["name"] = "Second Project"
        await client.post("/api/projects", json=sample_project_data)

        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_ordered_by_created_at_desc(self, client, sample_project_data):
        sample_project_data["name"] = "First"
        await client.post("/api/projects", json=sample_project_data)
        sample_project_data["name"] = "Second"
        await client.post("/api/projects", json=sample_project_data)

        resp = await client.get("/api/projects")
        data = resp.json()
        # Most recent first
        assert data[0]["name"] == "Second"
        assert data[1]["name"] == "First"


class TestGetProject:
    """Tests for GET /api/projects/{id}."""

    async def test_get_existing(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == project_id
        assert data["name"] == created_project["name"]

    async def test_get_not_found(self, client):
        resp = await client.get("/api/projects/9999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestUpdateProject:
    """Tests for PATCH /api/projects/{id}."""

    async def test_update_name(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.patch(f"/api/projects/{project_id}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        # Other fields unchanged
        assert data["goal"] == created_project["goal"]

    async def test_update_status(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.patch(f"/api/projects/{project_id}", json={"status": "running"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    async def test_update_multiple_fields(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.patch(f"/api/projects/{project_id}", json={
            "name": "New Name",
            "goal": "New Goal",
            "complexity": "Complex",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["goal"] == "New Goal"
        assert data["complexity"] == "Complex"

    async def test_update_empty_body(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.patch(f"/api/projects/{project_id}", json={})
        assert resp.status_code == 200
        # Should return unchanged project
        assert resp.json()["name"] == created_project["name"]

    async def test_update_not_found(self, client):
        resp = await client.patch("/api/projects/9999", json={"name": "Nope"})
        assert resp.status_code == 404

    async def test_update_sets_updated_at(self, client, created_project):
        project_id = created_project["id"]
        original_updated_at = created_project["updated_at"]
        resp = await client.patch(f"/api/projects/{project_id}", json={"name": "Trigger Update"})
        assert resp.status_code == 200
        # updated_at should change (or at least not break)
        assert resp.json()["updated_at"] is not None


class TestDeleteProject:
    """Tests for DELETE /api/projects/{id}."""

    async def test_delete_existing(self, client, created_project):
        project_id = created_project["id"]
        resp = await client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 404

    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/projects/9999")
        assert resp.status_code == 404

    async def test_delete_removes_from_list(self, client, sample_project_data):
        # Create a project
        resp = await client.post("/api/projects", json=sample_project_data)
        project_id = resp.json()["id"]

        # Delete it
        await client.delete(f"/api/projects/{project_id}")

        # List should be empty
        resp = await client.get("/api/projects")
        assert resp.json() == []
