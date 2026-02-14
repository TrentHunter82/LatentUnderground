"""Tests for Prometheus-compatible metrics endpoint and collection."""

import os
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import _fastapi_app as app
from app.metrics import Metrics, metrics


# --- Unit tests for Metrics class ---

class TestMetricsClass:
    def setup_method(self):
        self.m = Metrics()

    def test_record_request_increments_counter(self):
        self.m.record_request("GET", "/api/projects", 200, 0.05)
        self.m.record_request("GET", "/api/projects", 200, 0.1)
        export = self.m.export()
        assert 'lu_http_requests_total{method="GET",path="/api/projects",status="200"} 2' in export

    def test_record_request_different_statuses(self):
        self.m.record_request("GET", "/api/projects", 200, 0.05)
        self.m.record_request("GET", "/api/projects", 404, 0.01)
        export = self.m.export()
        assert 'status="200"} 1' in export
        assert 'status="404"} 1' in export

    def test_duration_histogram_buckets(self):
        self.m.record_request("GET", "/api/test", 200, 0.003)  # fits in 0.005 bucket
        export = self.m.export()
        assert 'le="0.005"} 1' in export
        assert 'le="0.01"} 1' in export  # cumulative
        assert 'le="+Inf"} 1' in export

    def test_duration_sum_and_count(self):
        self.m.record_request("POST", "/api/test", 201, 0.1)
        self.m.record_request("POST", "/api/test", 201, 0.2)
        export = self.m.export()
        assert 'lu_http_request_duration_seconds_sum{method="POST",path="/api/test"} 0.3' in export
        assert 'lu_http_request_duration_seconds_count{method="POST",path="/api/test"} 2' in export

    def test_normalize_path_collapses_ids(self):
        assert Metrics._normalize_path("/api/projects/42") == "/api/projects/{id}"
        assert Metrics._normalize_path("/api/swarm/agents/7/Claude-1") == "/api/swarm/agents/{id}/Claude-1"
        assert Metrics._normalize_path("/api/projects") == "/api/projects"

    def test_set_gauge(self):
        self.m.set_gauge("lu_active_agents", 3.0, "Number of active agents")
        export = self.m.export()
        assert "# HELP lu_active_agents Number of active agents" in export
        assert "# TYPE lu_active_agents gauge" in export
        assert "lu_active_agents 3.0" in export

    def test_set_gauge_updates_value(self):
        self.m.set_gauge("lu_test", 1.0)
        self.m.set_gauge("lu_test", 5.0)
        export = self.m.export()
        assert "lu_test 5.0" in export
        assert "lu_test 1.0" not in export

    def test_reset_clears_all(self):
        self.m.record_request("GET", "/api/test", 200, 0.01)
        self.m.set_gauge("lu_test", 42.0)
        self.m.reset()
        export = self.m.export()
        assert "lu_http_requests_total" not in export
        assert "lu_test" not in export

    def test_export_format_has_type_and_help(self):
        self.m.record_request("GET", "/api/test", 200, 0.01)
        export = self.m.export()
        assert "# HELP lu_http_requests_total Total HTTP requests" in export
        assert "# TYPE lu_http_requests_total counter" in export
        assert "# HELP lu_http_request_duration_seconds Request duration in seconds" in export
        assert "# TYPE lu_http_request_duration_seconds histogram" in export


# --- Integration tests for /api/metrics endpoint ---

@pytest.fixture
def reset_metrics():
    """Reset global metrics before and after each test."""
    metrics.reset()
    yield
    metrics.reset()


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(reset_metrics):
    """Test that /api/metrics returns text/plain in Prometheus format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Make a few requests first to generate metrics
        await client.get("/api/health")

        # Then check metrics
        resp = await client.get("/api/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        body = resp.text
        assert "lu_http_requests_total" in body
        assert "lu_active_agents" in body
        assert "lu_uptime_seconds" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_includes_gauges(reset_metrics):
    """Test that /api/metrics includes application-level gauges."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "lu_active_projects" in body
        assert "lu_uptime_seconds" in body
        assert "lu_active_agents" in body


@pytest.mark.asyncio
async def test_metrics_not_self_referencing(reset_metrics):
    """Test that the metrics endpoint doesn't count its own requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Call metrics 3 times
        await client.get("/api/metrics")
        await client.get("/api/metrics")
        resp = await client.get("/api/metrics")
        body = resp.text
        # The metrics endpoint itself should NOT appear in the request counts
        assert "/api/metrics" not in body.split("lu_active")[0]  # only check request section


@pytest.mark.asyncio
async def test_metrics_requires_auth(reset_metrics):
    """Test that /api/metrics requires API key (contains sensitive operational data)."""
    import app.config as cfg
    original = cfg.API_KEY
    cfg.API_KEY = "test-secret-key-12345"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Without key: should be rejected
            resp = await client.get("/api/metrics")
            assert resp.status_code == 401
            # With key: should work
            resp = await client.get(
                "/api/metrics",
                headers={"Authorization": "Bearer test-secret-key-12345"},
            )
            assert resp.status_code == 200
    finally:
        cfg.API_KEY = original
