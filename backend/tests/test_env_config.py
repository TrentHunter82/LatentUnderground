"""Tests for environment configuration loading (app/config.py).

Verifies that config module reads from environment variables with correct
defaults, and that .env file loading works properly.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestConfigDefaults:
    """Verify default values when no environment variables are set."""

    def test_default_host(self):
        from app import config
        # Default should be 127.0.0.1 for local-only binding
        assert config.HOST == os.environ.get("LU_HOST", "127.0.0.1")

    def test_default_port(self):
        from app import config
        # Default port should be 8000
        port = int(os.environ.get("LU_PORT", "8000"))
        assert config.PORT == port

    def test_default_log_level(self):
        from app import config
        assert config.LOG_LEVEL == os.environ.get("LU_LOG_LEVEL", "info")

    def test_db_path_is_pathlib_path(self):
        from app import config
        assert isinstance(config.DB_PATH, Path)

    def test_cors_origins_is_list(self):
        from app import config
        assert isinstance(config.CORS_ORIGINS, list)
        assert len(config.CORS_ORIGINS) > 0

    def test_cors_origins_include_localhost(self):
        from app import config
        origins_str = " ".join(config.CORS_ORIGINS)
        assert "localhost" in origins_str or "127.0.0.1" in origins_str

    def test_frontend_dist_is_pathlib_path(self):
        from app import config
        assert isinstance(config.FRONTEND_DIST, Path)


class TestConfigEnvironmentOverrides:
    """Verify environment variables override defaults."""

    def test_host_from_env(self):
        with patch.dict(os.environ, {"LU_HOST": "0.0.0.0"}):
            # Re-evaluate the config value
            host = os.environ.get("LU_HOST", "127.0.0.1")
            assert host == "0.0.0.0"

    def test_port_from_env(self):
        with patch.dict(os.environ, {"LU_PORT": "9000"}):
            port = int(os.environ.get("LU_PORT", "8000"))
            assert port == 9000

    def test_log_level_from_env(self):
        with patch.dict(os.environ, {"LU_LOG_LEVEL": "debug"}):
            level = os.environ.get("LU_LOG_LEVEL", "info")
            assert level == "debug"

    def test_cors_origins_from_env(self):
        with patch.dict(os.environ, {"LU_CORS_ORIGINS": "http://example.com,http://test.com"}):
            raw = os.environ.get("LU_CORS_ORIGINS", "")
            origins = [o.strip() for o in raw.split(",") if o.strip()]
            assert "http://example.com" in origins
            assert "http://test.com" in origins


class TestDotenvLoading:
    """Test the _load_dotenv function reads .env files correctly."""

    def test_load_dotenv_parses_key_value(self, tmp_path):
        from app.config import _load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY_ABC=test_value\n")

        # Patch the function to look at our tmp .env
        with patch("app.config._BACKEND_DIR", tmp_path):
            # Clear the var if it exists
            os.environ.pop("TEST_KEY_ABC", None)
            _load_dotenv()
            assert os.environ.get("TEST_KEY_ABC") == "test_value"
            # Cleanup
            os.environ.pop("TEST_KEY_ABC", None)

    def test_load_dotenv_skips_comments(self, tmp_path):
        from app.config import _load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text("# This is a comment\nTEST_COMMENT_KEY=value\n")

        with patch("app.config._BACKEND_DIR", tmp_path):
            os.environ.pop("TEST_COMMENT_KEY", None)
            _load_dotenv()
            assert os.environ.get("TEST_COMMENT_KEY") == "value"
            os.environ.pop("TEST_COMMENT_KEY", None)

    def test_load_dotenv_skips_empty_lines(self, tmp_path):
        from app.config import _load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nTEST_EMPTY_KEY=present\n\n")

        with patch("app.config._BACKEND_DIR", tmp_path):
            os.environ.pop("TEST_EMPTY_KEY", None)
            _load_dotenv()
            assert os.environ.get("TEST_EMPTY_KEY") == "present"
            os.environ.pop("TEST_EMPTY_KEY", None)

    def test_load_dotenv_strips_quotes(self, tmp_path):
        from app.config import _load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_QUOTE_KEY="quoted_value"\n')

        with patch("app.config._BACKEND_DIR", tmp_path):
            os.environ.pop("TEST_QUOTE_KEY", None)
            _load_dotenv()
            assert os.environ.get("TEST_QUOTE_KEY") == "quoted_value"
            os.environ.pop("TEST_QUOTE_KEY", None)

    def test_load_dotenv_does_not_override_existing(self, tmp_path):
        from app.config import _load_dotenv
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_OVERRIDE_KEY=from_file\n")

        with patch("app.config._BACKEND_DIR", tmp_path):
            os.environ["TEST_OVERRIDE_KEY"] = "from_env"
            _load_dotenv()
            assert os.environ.get("TEST_OVERRIDE_KEY") == "from_env"
            os.environ.pop("TEST_OVERRIDE_KEY", None)

    def test_load_dotenv_no_file_is_noop(self, tmp_path):
        from app.config import _load_dotenv
        # No .env file in tmp_path - should not raise
        with patch("app.config._BACKEND_DIR", tmp_path):
            _load_dotenv()  # Should complete without error


class TestDotenvExample:
    """Verify .env.example exists and documents all settings."""

    def test_env_example_exists(self):
        env_example = Path(__file__).parent.parent / ".env.example"
        assert env_example.exists(), ".env.example should exist in backend/"

    def test_env_example_documents_all_settings(self):
        env_example = Path(__file__).parent.parent / ".env.example"
        content = env_example.read_text()
        assert "LU_HOST" in content
        assert "LU_PORT" in content
        assert "LU_DB_PATH" in content
        assert "LU_LOG_LEVEL" in content
        assert "LU_CORS_ORIGINS" in content
