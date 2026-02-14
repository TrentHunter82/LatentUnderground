"""API contract tests: verify all frontend API calls match backend endpoints.

These tests fetch the OpenAPI schema and validate that every endpoint
the frontend expects is registered in the backend.
"""

import pytest


class TestAPIContractEndpointExistence:
    """Every frontend API call should have a matching backend route."""

    def test_openapi_schema_loads(self, app):
        """OpenAPI schema generates without errors."""
        schema = app.openapi()
        assert "openapi" in schema
        assert "paths" in schema
        assert len(schema["paths"]) > 0

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/projects"),
        ("post", "/api/projects"),
        ("get", "/api/projects/{id}"),
        ("patch", "/api/projects/{id}"),
        ("delete", "/api/projects/{id}"),
        ("get", "/api/projects/{id}/stats"),
        ("get", "/api/projects/{id}/analytics"),
        ("patch", "/api/projects/{id}/config"),
        ("post", "/api/swarm/launch"),
        ("post", "/api/swarm/stop"),
        ("post", "/api/swarm/input"),
        ("get", "/api/swarm/status/{project_id}"),
        ("get", "/api/swarm/history/{project_id}"),
        ("get", "/api/swarm/output/{project_id}"),
        ("get", "/api/files/{path:path}"),
        ("put", "/api/files/{path:path}"),
        ("get", "/api/logs"),
        ("get", "/api/logs/search"),
        ("get", "/api/browse"),
        ("get", "/api/templates"),
        ("post", "/api/templates"),
        ("get", "/api/templates/{template_id}"),
        ("patch", "/api/templates/{template_id}"),
        ("delete", "/api/templates/{template_id}"),
        ("post", "/api/watch/{project_id}"),
        ("post", "/api/unwatch/{project_id}"),
        ("get", "/api/health"),
        ("get", "/api/backup"),
    ])
    def test_frontend_endpoint_exists(self, app, method, path):
        """Each endpoint the frontend calls must exist in the backend OpenAPI schema."""
        schema = app.openapi()
        paths = schema["paths"]

        # Try to find the path - FastAPI may use slightly different path parameter syntax
        matched = False
        for schema_path in paths:
            # Normalize for comparison: replace {param_name} variations
            if self._paths_match(path, schema_path):
                assert method in paths[schema_path], (
                    f"{method.upper()} {path} exists as path but {method} method is not registered. "
                    f"Available methods: {list(paths[schema_path].keys())}"
                )
                matched = True
                break

        assert matched, (
            f"{method.upper()} {path} not found in backend. "
            f"Available paths: {sorted(paths.keys())}"
        )

    @staticmethod
    def _paths_match(frontend_path, schema_path):
        """Check if a frontend path matches an OpenAPI schema path.

        Handles parameter name differences:
        /api/projects/{id} should match /api/projects/{project_id}
        /api/files/{path:path} should match /api/files/{path}
        """
        # Strip Starlette path converters like :path
        fp = frontend_path.replace(":path", "")
        sp = schema_path.replace(":path", "")

        fp_parts = fp.strip("/").split("/")
        sp_parts = sp.strip("/").split("/")

        if len(fp_parts) != len(sp_parts):
            return False

        for f, s in zip(fp_parts, sp_parts):
            if f.startswith("{") and s.startswith("{"):
                continue  # Both are path params - match
            if f != s:
                return False
        return True


class TestAPIContractResponseFormats:
    """Verify response shapes match what the frontend expects."""

    async def test_projects_list_returns_array(self, client):
        """GET /api/projects must return a JSON array."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_project_create_returns_object_with_id(self, client, sample_project_data):
        """POST /api/projects must return object with id field."""
        resp = await client.post("/api/projects", json=sample_project_data)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "status" in data

    async def test_templates_list_returns_array(self, client):
        """GET /api/templates must return a JSON array."""
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_health_returns_expected_shape(self, client):
        """GET /api/health must return status and db fields."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "db" in data

    async def test_browse_returns_expected_shape(self, client, tmp_path):
        """GET /api/browse must return path, parent, dirs."""
        resp = await client.get(f"/api/browse?path={str(tmp_path)}")
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert "parent" in data
        assert "dirs" in data
        assert isinstance(data["dirs"], list)

    async def test_swarm_output_returns_pagination_fields(self, client, created_project):
        """GET /api/swarm/output must return pagination fields."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        for field in ["project_id", "offset", "limit", "total", "has_more", "next_offset", "lines"]:
            assert field in data, f"Missing field: {field}"

    async def test_delete_returns_204_no_body(self, client, created_project):
        """DELETE endpoints must return 204 with no body."""
        pid = created_project["id"]
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204


class TestAPIContractFieldTypes:
    """Verify response field types match what frontend expects."""

    async def test_project_fields_have_correct_types(self, client, sample_project_data):
        """Project response has correct field types."""
        resp = await client.post("/api/projects", json=sample_project_data)
        data = resp.json()
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)
        assert data["status"] in ("created", "running", "stopped", "completed")

    async def test_project_list_items_have_correct_types(self, client, sample_project_data):
        """Project list items have same shape as individual project."""
        await client.post("/api/projects", json=sample_project_data)
        resp = await client.get("/api/projects")
        data = resp.json()
        assert len(data) > 0
        project = data[0]
        assert isinstance(project["id"], int)
        assert isinstance(project["name"], str)
        assert isinstance(project["status"], str)

    async def test_template_fields_have_correct_types(self, client):
        """Template response has correct field types."""
        resp = await client.post("/api/templates", json={
            "name": "Type Test Template",
            "config": {"agent_count": 4, "max_phases": 6},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["config"], dict)
        assert isinstance(data["config"]["agent_count"], int)

    async def test_health_fields_have_correct_types(self, client):
        """Health response has correct field types."""
        resp = await client.get("/api/health")
        data = resp.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["db"], str)
        assert isinstance(data["uptime_seconds"], int)
        assert isinstance(data["version"], str)
        assert data["status"] in ("ok", "degraded")
        assert data["db"] in ("ok", "error")

    async def test_swarm_output_fields_have_correct_types(self, client, created_project):
        """Swarm output response has correct field types."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}")
        data = resp.json()
        assert isinstance(data["project_id"], int)
        assert isinstance(data["offset"], int)
        assert isinstance(data["limit"], int)
        assert isinstance(data["total"], int)
        assert isinstance(data["has_more"], bool)
        assert isinstance(data["next_offset"], int)
        assert isinstance(data["lines"], list)

    async def test_browse_fields_have_correct_types(self, client, tmp_path):
        """Browse response has correct field types."""
        subdir = tmp_path / "test-dir"
        subdir.mkdir()
        resp = await client.get(f"/api/browse?path={str(tmp_path)}")
        data = resp.json()
        assert isinstance(data["path"], str)
        assert isinstance(data["dirs"], list)
        if data["dirs"]:
            dir_entry = data["dirs"][0]
            assert isinstance(dir_entry["name"], str)
            assert isinstance(dir_entry["path"], str)

    async def test_swarm_history_fields_have_correct_types(self, client, created_project):
        """Swarm history response has correct field types."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["runs"], list)

    async def test_project_stats_fields_have_correct_types(self, client, created_project):
        """Project stats response has correct field types."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["total_runs"], int)
        assert isinstance(data["total_tasks_completed"], int)


class TestPaginationEdgeCases:
    """Test pagination with invalid/edge case parameters."""

    async def test_negative_offset_handled(self, client, created_project):
        """Negative offset should not crash the server."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?offset=-1")
        # Server should respond (200 or 422), not crash (500)
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            # Empty lines expected since offset is before start
            assert isinstance(resp.json()["lines"], list)

    async def test_limit_capped_at_max(self, client, created_project):
        """Limit above max should be capped, not cause error."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?limit=9999")
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            assert resp.json()["limit"] <= 5000  # default LU_OUTPUT_BUFFER_LINES

    async def test_zero_limit_returns_no_lines(self, client, created_project):
        """Limit=0 should return empty lines or validation error."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?limit=0")
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            assert len(resp.json()["lines"]) == 0

    async def test_very_large_offset_returns_empty(self, client, created_project):
        """Offset beyond total lines returns empty."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?offset=999999")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 0
        assert data["has_more"] is False
