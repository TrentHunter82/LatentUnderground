"""Tests for RequestLoggingMiddleware.

Verifies that HTTP requests are logged with method, path, status code, and duration.
Uses an isolated FastAPI app with the middleware explicitly enabled (since the default
conftest app has request logging disabled).
"""

import logging
import re
import time

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import RequestLoggingMiddleware


def _make_test_app():
    """Create a minimal FastAPI app with RequestLoggingMiddleware enabled."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/api/test")
    async def test_endpoint():
        return {"ok": True}

    @app.post("/api/test")
    async def test_post():
        return {"created": True}

    @app.get("/api/slow")
    async def slow_endpoint():
        import asyncio
        await asyncio.sleep(0.05)  # 50ms delay
        return {"slow": True}

    @app.get("/api/error")
    async def error_endpoint():
        raise HTTPException(status_code=500, detail="Test error")

    @app.get("/api/not-found")
    async def not_found_endpoint():
        raise HTTPException(status_code=404, detail="Not found")

    return app


@pytest.fixture()
async def logging_client():
    """Create a test client with request logging enabled."""
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRequestLoggingCapture:
    """Verify that RequestLoggingMiddleware captures request metadata."""

    @pytest.mark.asyncio
    async def test_logs_get_request(self, logging_client, caplog):
        """GET request should be logged with method, path, and 200 status."""
        with caplog.at_level(logging.INFO, logger="latent"):
            resp = await logging_client.get("/api/test")

        assert resp.status_code == 200
        log_messages = [r.message for r in caplog.records if "latent" in r.name]
        assert any("GET" in msg and "/api/test" in msg and "200" in msg for msg in log_messages), (
            f"Expected log with 'GET /api/test 200', got: {log_messages}"
        )

    @pytest.mark.asyncio
    async def test_logs_post_request(self, logging_client, caplog):
        """POST request should be logged with correct method."""
        with caplog.at_level(logging.INFO, logger="latent"):
            resp = await logging_client.post("/api/test")

        assert resp.status_code == 200
        log_messages = [r.message for r in caplog.records if "latent" in r.name]
        assert any("POST" in msg and "/api/test" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_error_status(self, logging_client, caplog):
        """500 error responses should be logged with the error status code."""
        with caplog.at_level(logging.INFO, logger="latent"):
            resp = await logging_client.get("/api/error")

        assert resp.status_code == 500
        log_messages = [r.message for r in caplog.records if "latent" in r.name]
        assert any("500" in msg and "/api/error" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_404_status(self, logging_client, caplog):
        """404 responses should be logged."""
        with caplog.at_level(logging.INFO, logger="latent"):
            resp = await logging_client.get("/api/not-found")

        assert resp.status_code == 404
        log_messages = [r.message for r in caplog.records if "latent" in r.name]
        assert any("404" in msg for msg in log_messages)


class TestRequestLoggingDuration:
    """Verify duration tracking in request logs."""

    @pytest.mark.asyncio
    async def test_duration_is_logged(self, logging_client, caplog):
        """Log entry should include duration in milliseconds."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/test")

        log_messages = [r.message for r in caplog.records if "latent" in r.name]
        # Duration format: "X.Yms"
        assert any(re.search(r"\d+\.\d+ms", msg) for msg in log_messages), (
            f"Expected duration in ms format, got: {log_messages}"
        )

    @pytest.mark.asyncio
    async def test_slow_request_has_higher_duration(self, logging_client, caplog):
        """A deliberately slow endpoint should log a duration >= 40ms."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/slow")

        log_messages = [r.message for r in caplog.records
                        if "latent" in r.name and "/api/slow" in r.message]
        assert len(log_messages) >= 1

        # Extract duration from log message
        match = re.search(r"(\d+\.\d+)ms", log_messages[0])
        assert match, f"No duration found in: {log_messages[0]}"
        duration = float(match.group(1))
        assert duration >= 40.0, f"Expected >= 40ms for slow endpoint, got {duration}ms"


class TestRequestLoggingExtras:
    """Verify structured log extras are attached to log records."""

    @pytest.mark.asyncio
    async def test_log_record_has_method_extra(self, logging_client, caplog):
        """Log record should have 'method' in extras."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/test")

        latent_records = [r for r in caplog.records if "latent" in r.name]
        request_log = [r for r in latent_records if hasattr(r, "method")]
        assert len(request_log) >= 1, "No log record with 'method' extra found"
        assert request_log[0].method == "GET"

    @pytest.mark.asyncio
    async def test_log_record_has_path_extra(self, logging_client, caplog):
        """Log record should have 'path' in extras."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/test")

        latent_records = [r for r in caplog.records if "latent" in r.name]
        request_log = [r for r in latent_records if hasattr(r, "path")]
        assert len(request_log) >= 1
        assert request_log[0].path == "/api/test"

    @pytest.mark.asyncio
    async def test_log_record_has_status_extra(self, logging_client, caplog):
        """Log record should have 'status' in extras."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/test")

        latent_records = [r for r in caplog.records if "latent" in r.name]
        request_log = [r for r in latent_records if hasattr(r, "status")]
        assert len(request_log) >= 1
        assert request_log[0].status == 200

    @pytest.mark.asyncio
    async def test_log_record_has_duration_ms_extra(self, logging_client, caplog):
        """Log record should have 'duration_ms' numeric extra."""
        with caplog.at_level(logging.INFO, logger="latent"):
            await logging_client.get("/api/test")

        latent_records = [r for r in caplog.records if "latent" in r.name]
        request_log = [r for r in latent_records if hasattr(r, "duration_ms")]
        assert len(request_log) >= 1
        assert isinstance(request_log[0].duration_ms, float)
        assert request_log[0].duration_ms >= 0
