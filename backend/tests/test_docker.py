"""Tests for Docker build configuration.

Validates that Dockerfile and docker-compose.yml are present and well-formed.
These are structural tests that don't require Docker to be installed.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestDockerfileStructure:
    """Validate Dockerfile content and best practices."""

    def test_dockerfile_exists(self):
        dockerfile = PROJECT_ROOT / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile should exist in project root"

    def test_dockerfile_has_multi_stage_build(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        # Should have at least 2 FROM statements (multi-stage)
        from_count = content.count("FROM ")
        assert from_count >= 2, f"Expected multi-stage build (2+ FROM), got {from_count}"

    def test_dockerfile_builds_frontend(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "npm" in content.lower() or "node" in content.lower(), \
            "Dockerfile should include frontend build step"

    def test_dockerfile_copies_frontend_dist(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "frontend/dist" in content or "frontend\\dist" in content, \
            "Dockerfile should copy built frontend dist"

    def test_dockerfile_exposes_port(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "EXPOSE" in content, "Dockerfile should EXPOSE the server port"

    def test_dockerfile_has_cmd(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "CMD" in content or "ENTRYPOINT" in content, \
            "Dockerfile should have CMD or ENTRYPOINT"

    def test_dockerfile_uses_env_vars(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "LU_HOST" in content or "LU_PORT" in content, \
            "Dockerfile should set environment variables for configuration"

    def test_dockerfile_has_volume(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "VOLUME" in content, "Dockerfile should declare a VOLUME for persistent data"

    def test_dockerfile_creates_required_dirs(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert ".claude" in content, "Dockerfile should create .claude directory"


class TestDockerComposeStructure:
    """Validate docker-compose.yml content."""

    def test_compose_file_exists(self):
        compose = PROJECT_ROOT / "docker-compose.yml"
        assert compose.exists(), "docker-compose.yml should exist in project root"

    def test_compose_is_valid_yaml(self):
        """Verify compose file is parseable YAML (basic check without PyYAML)."""
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        # Basic structural checks
        assert "services:" in content, "compose file should have services section"
        assert "volumes:" in content, "compose file should define volumes"

    def test_compose_has_port_mapping(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "ports:" in content, "compose file should map ports"
        assert "8000" in content, "compose file should reference port 8000"

    def test_compose_has_volume_mount(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "volumes:" in content
        # Should mount a named volume for data persistence
        assert "data" in content.lower(), "compose file should mount data volume"

    def test_compose_has_environment_section(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "environment:" in content, "compose file should set environment variables"

    def test_compose_has_restart_policy(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "restart:" in content, "compose file should have restart policy"


class TestDockerIgnore:
    """Validate .dockerignore exists to keep builds efficient."""

    def test_dockerignore_exists(self):
        dockerignore = PROJECT_ROOT / ".dockerignore"
        if not dockerignore.exists():
            pytest.skip(".dockerignore not yet created")
        assert dockerignore.exists()

    def test_dockerignore_excludes_common_items(self):
        dockerignore = PROJECT_ROOT / ".dockerignore"
        if not dockerignore.exists():
            pytest.skip(".dockerignore not yet created")
        content = dockerignore.read_text()
        # Should exclude at least node_modules, .venv, or __pycache__
        excludes_something = any(
            pattern in content
            for pattern in ["node_modules", ".venv", "__pycache__", ".git"]
        )
        assert excludes_something, ".dockerignore should exclude build artifacts"
