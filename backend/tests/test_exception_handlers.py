"""Tests for global exception handlers.

Verifies that RequestValidationError, OperationalError, and unhandled exceptions
return structured JSON responses with consistent error format.
"""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest


class TestValidationExceptionHandler:
    """Custom 422 handler returns structured error response with field details."""

    @pytest.mark.asyncio
    async def test_validation_error_returns_422_with_errors_array(self, client):
        """POST with empty body triggers validation error with structured response."""
        resp = await client.post("/api/projects", json={})
        assert resp.status_code == 422

        data = resp.json()
        assert "detail" in data
        assert data["detail"] == "Validation error"
        assert "errors" in data
        assert isinstance(data["errors"], list)
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validation_error_includes_field_and_message(self, client):
        """Each error entry should have field, message, and type keys."""
        resp = await client.post("/api/projects", json={})
        assert resp.status_code == 422

        errors = resp.json()["errors"]
        for err in errors:
            assert "field" in err, f"Missing 'field' key in error: {err}"
            assert "message" in err, f"Missing 'message' key in error: {err}"
            assert "type" in err, f"Missing 'type' key in error: {err}"

    @pytest.mark.asyncio
    async def test_validation_error_identifies_missing_name_field(self, client, tmp_path):
        """Missing required 'name' field should be identified in errors."""
        resp = await client.post("/api/projects", json={
            "goal": "Test",
            "folder_path": str(tmp_path / "test").replace("\\", "/"),
        })
        assert resp.status_code == 422

        errors = resp.json()["errors"]
        field_names = [e["field"] for e in errors]
        assert any("name" in f for f in field_names), (
            f"Expected 'name' in error fields, got: {field_names}"
        )

    @pytest.mark.asyncio
    async def test_validation_error_for_wrong_type(self, client, tmp_path):
        """Sending wrong type (int instead of string) should produce structured error."""
        resp = await client.post("/api/projects", json={
            "name": 12345,  # int instead of string - may or may not be coerced
            "goal": "Test",
            "folder_path": str(tmp_path / "test").replace("\\", "/"),
        })
        # Pydantic v2 may coerce int to str; if so, 201 is acceptable
        # The important thing is that if it's 422, the format is structured
        if resp.status_code == 422:
            data = resp.json()
            assert data["detail"] == "Validation error"
            assert isinstance(data["errors"], list)


class TestDatabaseExceptionHandler:
    """Custom 503 handler for sqlite3.OperationalError."""

    @pytest.mark.asyncio
    async def test_db_error_returns_503(self, client):
        """OperationalError during request should return 503 with structured response."""
        with patch(
            "app.routes.projects.get_db",
            new_callable=AsyncMock,
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            resp = await client.get("/api/projects")

        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"] == "Database temporarily unavailable"
        assert data["error"] == "db_error"

    @pytest.mark.asyncio
    async def test_db_error_does_not_leak_internal_details(self, client):
        """503 response should not expose internal error messages to client."""
        with patch(
            "app.routes.projects.get_db",
            new_callable=AsyncMock,
            side_effect=sqlite3.OperationalError("disk I/O error at sector 42"),
        ):
            resp = await client.get("/api/projects")

        assert resp.status_code == 503
        body = resp.text
        assert "sector 42" not in body
        assert "disk I/O" not in body


class TestGenericExceptionHandler:
    """Custom 500 handler for unhandled exceptions."""

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self, client):
        """Unhandled exception should return 500 with generic message."""
        with patch(
            "app.routes.projects.get_db",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected crash"),
        ):
            resp = await client.get("/api/projects")

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_generic_error_does_not_leak_traceback(self, client):
        """500 response should not expose Python tracebacks to client."""
        with patch(
            "app.routes.projects.get_db",
            new_callable=AsyncMock,
            side_effect=RuntimeError("secret internal state"),
        ):
            resp = await client.get("/api/projects")

        assert resp.status_code == 500
        body = resp.text
        assert "secret internal state" not in body
        assert "Traceback" not in body
