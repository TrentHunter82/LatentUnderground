"""Tests for log API endpoint."""

import pytest


class TestGetLogs:
    """Tests for GET /api/logs."""

    async def test_get_logs_with_files(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/logs?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()

        assert "logs" in data
        agents = {log["agent"]: log for log in data["logs"]}
        assert "Claude-1" in agents
        assert "Claude-2" in agents
        assert agents["Claude-1"]["lines"] == ["Line 1", "Line 2", "Line 3"]
        assert agents["Claude-2"]["lines"] == ["Starting work"]

    async def test_get_logs_empty_folder(self, client, tmp_path):
        folder = tmp_path / "no_logs"
        folder.mkdir()

        resp = await client.post("/api/projects", json={
            "name": "No Logs",
            "goal": "Test empty logs",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.get(f"/api/logs?project_id={pid}")
        assert resp.status_code == 200
        assert resp.json()["logs"] == []

    async def test_get_logs_project_not_found(self, client):
        resp = await client.get("/api/logs?project_id=9999")
        assert resp.status_code == 404

    async def test_get_logs_with_line_limit(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/logs?project_id={pid}&lines=2")
        assert resp.status_code == 200
        data = resp.json()

        # Claude-1 has 3 lines, should be limited to last 2
        for log in data["logs"]:
            if log["agent"] == "Claude-1":
                assert len(log["lines"]) == 2
                assert log["lines"] == ["Line 2", "Line 3"]
