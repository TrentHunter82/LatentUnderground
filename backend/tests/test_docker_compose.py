"""Docker Compose integration tests.

Validates Docker configuration files and provides a smoke test
that can run when Docker is available. When Docker is not available,
tests validate the configuration files themselves.
"""

import os
import subprocess

os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

from pathlib import Path

import pytest

# Project root (parent of backend/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _docker_available() -> bool:
    """Check if Docker CLI is available."""
    try:
        result = subprocess.run(
            ["docker", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


DOCKER_AVAILABLE = _docker_available()


# ---------------------------------------------------------------------------
# Configuration Validation Tests (always run)
# ---------------------------------------------------------------------------


class TestDockerfileValidation:
    """Validate Dockerfile structure and best practices."""

    def test_dockerfile_exists(self):
        dockerfile = PROJECT_ROOT / "Dockerfile"
        assert dockerfile.is_file(), "Dockerfile not found at project root"

    def test_dockerfile_multi_stage_build(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "AS frontend-build" in content, "Missing frontend build stage"
        assert "AS runtime" in content, "Missing runtime stage"

    def test_dockerfile_uses_slim_base(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "python:3.12-slim" in content, "Should use slim Python base image"
        assert "node:20-slim" in content, "Should use slim Node base image"

    def test_dockerfile_copies_uv(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "ghcr.io/astral-sh/uv" in content, "Should install uv for dependency management"

    def test_dockerfile_no_dev_deps(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "--no-dev" in content, "Production build should exclude dev dependencies"

    def test_dockerfile_sets_volume(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "VOLUME /app/data" in content, "Should declare data volume"

    def test_dockerfile_exposes_port(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "EXPOSE 8000" in content, "Should expose port 8000"

    def test_dockerfile_env_defaults(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "LU_HOST=0.0.0.0" in content, "Docker should bind to all interfaces"
        assert "LU_DB_PATH=/app/data/latent.db" in content, "DB should be in data volume"

    def test_dockerfile_creates_directories(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert ".claude/heartbeats" in content, "Should create heartbeats directory"
        assert ".claude/signals" in content, "Should create signals directory"

    def test_dockerfile_copies_frontend_dist(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "frontend/dist" in content, "Should copy built frontend from build stage"

    def test_dockerfile_cmd_uses_uvicorn(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "uvicorn" in content, "Should start with uvicorn"
        assert "app.main:app" in content, "Should reference correct ASGI app"


class TestDockerComposeValidation:
    """Validate docker-compose.yml configuration."""

    def test_compose_file_exists(self):
        compose = PROJECT_ROOT / "docker-compose.yml"
        assert compose.is_file(), "docker-compose.yml not found"

    def test_compose_defines_service(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "latent-underground:" in content, "Should define main service"

    def test_compose_maps_port(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert ":8000" in content, "Should map port 8000"

    def test_compose_mounts_data_volume(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "lu-data:/app/data" in content, "Should mount data volume"

    def test_compose_restart_policy(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "unless-stopped" in content, "Should restart unless stopped"

    def test_compose_defines_volumes(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "volumes:" in content, "Should define volumes section"
        assert "lu-data:" in content, "Should define lu-data volume"


class TestDockerComposeProdValidation:
    """Validate docker-compose.prod.yml production configuration."""

    def test_prod_compose_exists(self):
        prod = PROJECT_ROOT / "docker-compose.prod.yml"
        assert prod.is_file(), "docker-compose.prod.yml not found"

    def test_prod_has_healthcheck(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "healthcheck:" in content, "Production should have health check"
        assert "/api/health" in content, "Health check should hit /api/health"

    def test_prod_has_backup_config(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "LU_BACKUP_INTERVAL_HOURS" in content, "Should configure backups"
        assert "lu-backups" in content, "Should have backup volume"

    def test_prod_has_json_logging(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "LU_LOG_FORMAT=json" in content, "Production should use JSON logging"

    def test_prod_has_rate_limiting(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "LU_RATE_LIMIT_RPM" in content, "Should configure rate limiting"

    def test_prod_has_log_retention(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "LU_LOG_RETENTION_DAYS" in content, "Should configure log retention"

    def test_prod_has_nginx(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "nginx:" in content, "Production should have nginx reverse proxy"

    def test_prod_nginx_depends_on_healthy(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "service_healthy" in content, "Nginx should wait for healthy app"

    def test_prod_has_network(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "lu-net:" in content, "Should define internal network"

    def test_prod_supports_api_key(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "LU_API_KEY" in content, "Should support API key configuration"

    def test_prod_healthcheck_params(self):
        content = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
        assert "interval:" in content, "Health check should have interval"
        assert "timeout:" in content, "Health check should have timeout"
        assert "retries:" in content, "Health check should have retries"
        assert "start_period:" in content, "Health check should have start period"


class TestDockerBuildContext:
    """Validate that all files needed for Docker build exist."""

    def test_backend_pyproject_exists(self):
        assert (PROJECT_ROOT / "backend" / "pyproject.toml").is_file()

    def test_backend_run_py_exists(self):
        assert (PROJECT_ROOT / "backend" / "run.py").is_file()

    def test_backend_app_package_exists(self):
        assert (PROJECT_ROOT / "backend" / "app" / "__init__.py").is_file()

    def test_frontend_package_json_exists(self):
        assert (PROJECT_ROOT / "frontend" / "package.json").is_file()

    def test_frontend_build_exists(self):
        dist = PROJECT_ROOT / "frontend" / "dist"
        assert dist.is_dir(), "Frontend must be built before Docker build"
        assert (dist / "index.html").is_file(), "index.html missing from dist"
        assert (dist / "assets").is_dir(), "assets directory missing from dist"

    def test_frontend_dist_has_js(self):
        assets = PROJECT_ROOT / "frontend" / "dist" / "assets"
        js_files = list(assets.glob("*.js"))
        assert len(js_files) > 0, "No JS bundles in frontend dist"

    def test_frontend_dist_has_css(self):
        assets = PROJECT_ROOT / "frontend" / "dist" / "assets"
        css_files = list(assets.glob("*.css"))
        assert len(css_files) > 0, "No CSS bundles in frontend dist"


# ---------------------------------------------------------------------------
# Docker Integration Tests (only run when Docker is available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker not available")
class TestDockerBuild:
    """Integration tests that require Docker."""

    def test_docker_build_succeeds(self):
        """Verify the Docker image builds successfully."""
        result = subprocess.run(
            ["docker", "build", "-t", "latent-underground-test", "."],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Docker build failed: {result.stderr[-500:]}"

    def test_docker_compose_config_valid(self):
        """Verify docker-compose.yml is valid YAML/config."""
        result = subprocess.run(
            ["docker", "compose", "config"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Compose config invalid: {result.stderr}"

    def test_docker_compose_prod_config_valid(self):
        """Verify docker-compose.prod.yml is valid."""
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.prod.yml", "config"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Prod compose config invalid: {result.stderr}"
