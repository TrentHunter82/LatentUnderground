"""Tests for file API endpoints (read/write with allowlisting)."""

import pytest


class TestReadFile:
    """Tests for GET /api/files/{path}."""

    async def test_read_allowed_file(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "tasks/TASKS.md"
        assert "Task 1" in data["content"]

    async def test_read_lessons_file(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/tasks/lessons.md?project_id={pid}")
        assert resp.status_code == 200
        assert resp.json()["path"] == "tasks/lessons.md"

    async def test_read_agents_md(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/AGENTS.md?project_id={pid}")
        assert resp.status_code == 200
        assert resp.json()["path"] == "AGENTS.md"

    async def test_read_disallowed_path(self, client, project_with_folder):
        """Should reject paths not in the allowlist."""
        pid = project_with_folder["id"]
        # Note: HTTP clients normalize .. segments, so use a realistic non-allowlisted path
        resp = await client.get(f"/api/files/.claude/swarm-config.json?project_id={pid}")
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    async def test_read_disallowed_arbitrary_file(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/swarm.ps1?project_id={pid}")
        assert resp.status_code == 403

    async def test_read_nonexistent_project(self, client):
        resp = await client.get("/api/files/tasks/TASKS.md?project_id=9999")
        assert resp.status_code == 404

    async def test_read_file_not_found(self, client, tmp_path):
        """Project exists but file doesn't on disk."""
        folder = tmp_path / "no_files"
        folder.mkdir()
        (folder / "tasks").mkdir()
        # Don't create TASKS.md

        resp = await client.post("/api/projects", json={
            "name": "No Files",
            "goal": "Test missing",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 404


class TestWriteFile:
    """Tests for PUT /api/files/{path}."""

    async def test_write_allowed_file(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# Updated Tasks\n- [x] Done\n", "project_id": pid},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "written"

        # Verify content was written
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert "Updated Tasks" in resp.json()["content"]

    async def test_write_disallowed_path(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.put(
            "/api/files/swarm.ps1",
            json={"content": "malicious content", "project_id": pid},
        )
        assert resp.status_code == 403

    async def test_write_non_allowlisted_path(self, client, project_with_folder):
        """Writing to non-allowlisted paths should be blocked."""
        pid = project_with_folder["id"]
        resp = await client.put(
            "/api/files/.claude/swarm-config.json",
            json={"content": "bad", "project_id": pid},
        )
        assert resp.status_code == 403

    async def test_write_nonexistent_project(self, client):
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "test", "project_id": 9999},
        )
        assert resp.status_code == 404

    async def test_write_creates_parent_dirs(self, client, tmp_path):
        """Writing to a file should create parent directories if needed."""
        folder = tmp_path / "write_test"
        folder.mkdir()
        # Don't create tasks/ subdirectory

        resp = await client.post("/api/projects", json={
            "name": "Write Test",
            "goal": "Test write",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# New\n", "project_id": pid},
        )
        assert resp.status_code == 200

        # Verify file exists
        assert (folder / "tasks" / "TASKS.md").exists()


class TestConcurrentModification:
    """Tests for file editor save/reload with concurrent modifications."""

    async def test_external_modification_visible_on_reload(self, client, project_with_folder, mock_project_folder):
        """After an external tool modifies a file, the API should return the new content."""
        pid = project_with_folder["id"]

        # Read the original content via API
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 200
        original = resp.json()["content"]
        assert "Task 1" in original

        # Simulate an external tool (e.g., another agent) modifying the file directly
        tasks_file = mock_project_folder / "tasks" / "TASKS.md"
        tasks_file.write_text("# Modified by external agent\n- [x] External Task\n")

        # Read again via API - should see the external changes
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 200
        assert "Modified by external agent" in resp.json()["content"]
        assert "External Task" in resp.json()["content"]

    async def test_api_write_then_external_modify_then_read(self, client, tmp_path):
        """Full cycle: API write -> external modify -> API read shows external version."""
        folder = tmp_path / "concurrent_test"
        folder.mkdir()
        (folder / "tasks").mkdir()
        (folder / "tasks" / "TASKS.md").write_text("# Initial\n")

        resp = await client.post("/api/projects", json={
            "name": "Concurrent Test",
            "goal": "Test concurrent mods",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Write via API
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# API Write\n- [ ] From API\n", "project_id": pid},
        )
        assert resp.status_code == 200

        # Verify API write
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert "API Write" in resp.json()["content"]

        # External modification overwrites
        (folder / "tasks" / "TASKS.md").write_text("# External Override\n- [x] Done\n")

        # API read returns the external version (last-write-wins)
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert "External Override" in resp.json()["content"]
