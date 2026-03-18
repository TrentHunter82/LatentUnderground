"""Tests for Phase 28 project changes: agent_count/max_phases in ProjectCreate,
config JSON generation, and field sanitization."""

import json

import pytest


class TestProjectCreateWithConfig:
    """Tests for agent_count and max_phases in project creation."""

    async def test_create_with_agent_count(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Config Test",
            "goal": "Test agent_count in create",
            "folder_path": str(tmp_path / "p1").replace("\\", "/"),
            "agent_count": 6,
        })
        assert resp.status_code == 201
        data = resp.json()
        config = json.loads(data["config"])
        assert config["agent_count"] == 6

    async def test_create_with_max_phases(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Phase Test",
            "goal": "Test max_phases in create",
            "folder_path": str(tmp_path / "p2").replace("\\", "/"),
            "max_phases": 12,
        })
        assert resp.status_code == 201
        config = json.loads(resp.json()["config"])
        assert config["max_phases"] == 12

    async def test_create_with_both_config_fields(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Both Fields",
            "goal": "Test both config fields",
            "folder_path": str(tmp_path / "p3").replace("\\", "/"),
            "agent_count": 8,
            "max_phases": 24,
        })
        assert resp.status_code == 201
        config = json.loads(resp.json()["config"])
        assert config["agent_count"] == 8
        assert config["max_phases"] == 24

    async def test_create_without_config_fields_empty_json(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "No Config",
            "goal": "Test empty config",
            "folder_path": str(tmp_path / "p4").replace("\\", "/"),
        })
        assert resp.status_code == 201
        config = json.loads(resp.json()["config"])
        assert config == {}

    async def test_agent_count_bounds_low(self, client, tmp_path):
        """agent_count below 1 should return 422."""
        resp = await client.post("/api/projects", json={
            "name": "Bad Count",
            "goal": "Test",
            "folder_path": str(tmp_path / "p5").replace("\\", "/"),
            "agent_count": 0,
        })
        assert resp.status_code == 422

    async def test_agent_count_bounds_high(self, client, tmp_path):
        """agent_count above 16 should return 422."""
        resp = await client.post("/api/projects", json={
            "name": "Bad Count",
            "goal": "Test",
            "folder_path": str(tmp_path / "p6").replace("\\", "/"),
            "agent_count": 17,
        })
        assert resp.status_code == 422

    async def test_max_phases_bounds_low(self, client, tmp_path):
        """max_phases below 1 should return 422."""
        resp = await client.post("/api/projects", json={
            "name": "Bad Phases",
            "goal": "Test",
            "folder_path": str(tmp_path / "p7").replace("\\", "/"),
            "max_phases": 0,
        })
        assert resp.status_code == 422

    async def test_max_phases_bounds_high(self, client, tmp_path):
        """max_phases above 999 should return 422."""
        resp = await client.post("/api/projects", json={
            "name": "Bad Phases",
            "goal": "Test",
            "folder_path": str(tmp_path / "p8").replace("\\", "/"),
            "max_phases": 1000,
        })
        assert resp.status_code == 422

    async def test_agent_count_min_boundary(self, client, tmp_path):
        """agent_count=1 should be valid."""
        resp = await client.post("/api/projects", json={
            "name": "Min Count",
            "goal": "Test",
            "folder_path": str(tmp_path / "p9").replace("\\", "/"),
            "agent_count": 1,
        })
        assert resp.status_code == 201
        config = json.loads(resp.json()["config"])
        assert config["agent_count"] == 1

    async def test_agent_count_max_boundary(self, client, tmp_path):
        """agent_count=16 should be valid."""
        resp = await client.post("/api/projects", json={
            "name": "Max Count",
            "goal": "Test",
            "folder_path": str(tmp_path / "p10").replace("\\", "/"),
            "agent_count": 16,
        })
        assert resp.status_code == 201
        config = json.loads(resp.json()["config"])
        assert config["agent_count"] == 16


class TestFieldSanitization:
    """Tests that all string fields are sanitized on project creation."""

    async def test_xss_in_name_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": '<script>alert("xss")</script>',
            "goal": "Test XSS",
            "folder_path": str(tmp_path / "xss1").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<script>" not in data["name"]

    async def test_xss_in_goal_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Safe Name",
            "goal": '<img onerror="alert(1)" src="">',
            "folder_path": str(tmp_path / "xss2").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        # html.escape() converts < to &lt; — the raw HTML tag is neutralized
        assert "<img" not in data["goal"]
        assert "&lt;" in data["goal"]

    async def test_xss_in_project_type_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Safe",
            "goal": "Safe",
            "project_type": '<div onmouseover="hack()">',
            "folder_path": str(tmp_path / "xss3").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<div" not in data["project_type"]
        assert "&lt;" in data["project_type"]

    async def test_xss_in_tech_stack_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Safe",
            "goal": "Safe",
            "tech_stack": '<a href="javascript:alert(1)">click</a>',
            "folder_path": str(tmp_path / "xss4").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<a " not in data["tech_stack"]
        assert "&lt;" in data["tech_stack"]

    async def test_xss_in_complexity_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Safe",
            "goal": "Safe",
            "complexity": '<b onload="x()">High</b>',
            "folder_path": str(tmp_path / "xss5").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<b " not in data["complexity"]
        assert "&lt;" in data["complexity"]

    async def test_xss_in_requirements_is_sanitized(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Safe",
            "goal": "Safe",
            "requirements": '<iframe src="evil.com"></iframe>',
            "folder_path": str(tmp_path / "xss6").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<iframe" not in data["requirements"]
        assert "&lt;" in data["requirements"]


class TestProjectHealthTrend:
    """Tests for the corrected health trend calculation."""

    async def test_health_no_runs_is_healthy(self, client, created_project):
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["trend"] == "stable"
        assert data["run_count"] == 0

    async def test_health_404_nonexistent(self, client):
        resp = await client.get("/api/projects/99999/health")
        assert resp.status_code == 404
