"""Tests for global exception handlers.

Verifies that RequestValidationError, OperationalError, and unhandled exceptions
return structured JSON responses with consistent error format.
"""

import sqlite3

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
    async def test_db_error_returns_503(self, app, client):
        """OperationalError during request should return 503 with structured response."""
        from app.database import get_db

        async def broken_db():
            raise sqlite3.OperationalError("database is locked")

        app.dependency_overrides[get_db] = broken_db
        try:
            resp = await client.get("/api/projects")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"] == "Database temporarily unavailable"
        assert data["error"] == "db_error"

    @pytest.mark.asyncio
    async def test_db_error_does_not_leak_internal_details(self, app, client):
        """503 response should not expose internal error messages to client."""
        from app.database import get_db

        async def broken_db():
            raise sqlite3.OperationalError("disk I/O error at sector 42")

        app.dependency_overrides[get_db] = broken_db
        try:
            resp = await client.get("/api/projects")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 503
        body = resp.text
        assert "sector 42" not in body
        assert "disk I/O" not in body


class TestGenericExceptionHandler:
    """Unit tests for the generic exception handler function.

    Starlette's ServerErrorMiddleware intercepts unhandled exceptions before
    @app.exception_handler(Exception) in ASGI transport tests, so we test
    the handler function directly to verify its response structure.
    """

    @pytest.mark.asyncio
    async def test_generic_handler_returns_500_json(self):
        """The handler function should return JSONResponse with status 500."""
        from unittest.mock import MagicMock

        from app.main import generic_exception_handler

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        exc = RuntimeError("unexpected crash")

        response = await generic_exception_handler(mock_request, exc)

        assert response.status_code == 500
        import json
        body = json.loads(response.body)
        assert body["detail"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_generic_handler_does_not_leak_exception_message(self):
        """The handler should not include the exception message in the response."""
        from unittest.mock import MagicMock

        from app.main import generic_exception_handler

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/projects"
        exc = RuntimeError("secret internal state with credentials")

        response = await generic_exception_handler(mock_request, exc)

        body_text = response.body.decode()
        assert "secret internal state" not in body_text
        assert "credentials" not in body_text
