"""Tests for output guardrail validation system.

Tests cover:
- GuardrailRule model validation
- _run_guardrails() function with all rule types
- Guardrail endpoint GET /api/projects/{id}/guardrails
- Halt vs warn action semantics
- Guardrail results storage in swarm_runs
- Edge cases: invalid regex, empty output, missing config
"""

import json
import os
from collections import deque
from unittest.mock import patch

os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import aiosqlite
import pytest
from pydantic import ValidationError

from app.models.project import GuardrailRule, ProjectConfig
from app.routes.swarm import (
    _project_output_buffers,
    _run_guardrails,
    _buffers_lock,
)
from app import database


# ---------------------------------------------------------------------------
# GuardrailRule Model Validation
# ---------------------------------------------------------------------------
class TestGuardrailRuleModel:
    """Test GuardrailRule Pydantic model validation."""

    def test_regex_match_rule(self):
        rule = GuardrailRule(type="regex_match", pattern="SUCCESS", action="halt")
        assert rule.type == "regex_match"
        assert rule.pattern == "SUCCESS"
        assert rule.action == "halt"

    def test_regex_reject_rule(self):
        rule = GuardrailRule(type="regex_reject", pattern="FATAL", action="warn")
        assert rule.type == "regex_reject"
        assert rule.pattern == "FATAL"
        assert rule.action == "warn"

    def test_min_lines_rule(self):
        rule = GuardrailRule(type="min_lines", threshold=10, action="halt")
        assert rule.type == "min_lines"
        assert rule.threshold == 10

    def test_max_errors_rule(self):
        rule = GuardrailRule(type="max_errors", threshold=5, action="warn")
        assert rule.type == "max_errors"
        assert rule.threshold == 5

    def test_default_action_is_warn(self):
        rule = GuardrailRule(type="regex_match", pattern="test")
        assert rule.action == "warn"

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            GuardrailRule(type="invalid_type", pattern="test")

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            GuardrailRule(type="regex_match", pattern="test", action="invalid")

    def test_pattern_max_length(self):
        with pytest.raises(ValidationError):
            GuardrailRule(type="regex_match", pattern="x" * 501)

    def test_threshold_ge_zero(self):
        with pytest.raises(ValidationError):
            GuardrailRule(type="min_lines", threshold=-1)

    def test_project_config_guardrails_field(self):
        cfg = ProjectConfig(guardrails=[
            GuardrailRule(type="regex_match", pattern="OK", action="halt"),
            GuardrailRule(type="max_errors", threshold=3, action="warn"),
        ])
        assert len(cfg.guardrails) == 2
        assert cfg.guardrails[0].type == "regex_match"
        assert cfg.guardrails[1].type == "max_errors"

    def test_project_config_guardrails_max_20_rules(self):
        with pytest.raises(ValidationError):
            ProjectConfig(guardrails=[
                GuardrailRule(type="regex_match", pattern=f"pat{i}")
                for i in range(21)
            ])

    def test_project_config_guardrails_none_default(self):
        cfg = ProjectConfig()
        assert cfg.guardrails is None


# ---------------------------------------------------------------------------
# _run_guardrails() Unit Tests
# ---------------------------------------------------------------------------
class TestRunGuardrails:
    """Test the _run_guardrails() function directly against output buffers."""

    @pytest.fixture(autouse=True)
    def cleanup_buffers(self):
        """Clean up output buffers between tests."""
        yield
        _project_output_buffers.clear()

    @pytest.mark.asyncio
    async def test_regex_match_passes_when_pattern_found(self, tmp_db):
        """regex_match rule passes when the pattern exists in combined output."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # Create project with guardrail config
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "BUILD SUCCESS", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            # Populate output buffer with matching content
            _project_output_buffers[1] = deque([
                "[Claude-1] Starting build...",
                "[Claude-1] Compiling sources...",
                "[Claude-1] BUILD SUCCESS",
                "[Claude-1] Done",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is True
            assert results[0]["rule_type"] == "regex_match"
            assert results[0]["detail"] == "Pattern found"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_match_fails_when_pattern_missing(self, tmp_db):
        """regex_match rule fails when the pattern is not in output."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "ALL TESTS PASSED", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Running tests...",
                "[Claude-1] Some tests failed",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is False
            assert "not found" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_reject_halts_when_pattern_found(self, tmp_db):
        """regex_reject rule fails (triggers action) when forbidden pattern is found."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_reject", "pattern": "SEGFAULT|segmentation fault", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Running process...",
                "[Claude-1] SEGFAULT detected at 0x00000",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is False
            assert results[0]["action"] == "halt"
            assert "Rejected pattern found" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_reject_passes_when_pattern_not_found(self, tmp_db):
        """regex_reject rule passes when forbidden pattern is absent."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_reject", "pattern": "SEGFAULT", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Clean exit",
                "[Claude-1] Done",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is True
            assert "not found" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_min_lines_fails_when_output_too_short(self, tmp_db):
        """min_lines rule fails when output has fewer lines than threshold."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "min_lines", "threshold": 10, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Line 1",
                "[Claude-1] Line 2",
                "[Claude-1] Line 3",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is False
            assert results[0]["rule_type"] == "min_lines"
            assert "Only 3 lines, need at least 10" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_min_lines_passes_when_enough_output(self, tmp_db):
        """min_lines rule passes when output meets threshold."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "min_lines", "threshold": 3, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                f"[Claude-1] Line {i}" for i in range(5)
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is True
            assert "5 lines (min 3)" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_max_errors_warns_when_count_exceeds_threshold(self, tmp_db):
        """max_errors rule fails when error count exceeds threshold."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 2, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Starting...",
                "[Claude-1] ERROR: file not found",
                "[Claude-1] Working...",
                "[Claude-1] Error: compilation failed",
                "[Claude-1] FATAL: out of memory",
                "[Claude-1] Done",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is False
            assert results[0]["rule_type"] == "max_errors"
            assert results[0]["action"] == "warn"
            assert "3 errors exceed max of 2" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_max_errors_passes_when_within_threshold(self, tmp_db):
        """max_errors rule passes when error count is within threshold."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 5, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Starting...",
                "[Claude-1] ERROR: minor issue",
                "[Claude-1] All good otherwise",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is True
            assert "1 errors (max 5)" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_invalid_regex_fails_gracefully(self, tmp_db):
        """Invalid regex patterns in rules fail the rule but don't crash."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "[invalid(regex", "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque(["some output"])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 1
            assert results[0]["passed"] is False
            assert "Invalid regex" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_invalid_regex_reject_fails_gracefully(self, tmp_db):
        """Invalid regex in regex_reject also fails gracefully."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_reject", "pattern": "(unclosed", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque(["output"])

            results = await _run_guardrails(1)
            assert results is not None
            assert results[0]["passed"] is False
            assert "Invalid regex" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_no_guardrails_returns_none(self, tmp_db):
        """Returns None when project has no guardrails configured."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", "{}"),
                )
                await db.commit()

            results = await _run_guardrails(1)
            assert results is None
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_empty_output_buffer(self, tmp_db):
        """Guardrails work with empty output buffer."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "min_lines", "threshold": 1, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            # No output buffer populated for project 1
            results = await _run_guardrails(1)
            assert results is not None
            assert results[0]["passed"] is False
            assert "Only 0 lines" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_multiple_rules_all_evaluated(self, tmp_db):
        """Multiple guardrail rules are all evaluated and results returned."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "DONE", "action": "halt"},
                    {"type": "regex_reject", "pattern": "CRASH", "action": "halt"},
                    {"type": "min_lines", "threshold": 2, "action": "warn"},
                    {"type": "max_errors", "threshold": 0, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Starting work",
                "[Claude-1] DONE",
                "[Claude-1] Finished",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 4

            # regex_match: "DONE" found -> passed
            assert results[0]["passed"] is True
            # regex_reject: "CRASH" not found -> passed
            assert results[1]["passed"] is True
            # min_lines: 3 >= 2 -> passed
            assert results[2]["passed"] is True
            # max_errors: 0 errors <= 0 threshold -> passed
            assert results[3]["passed"] is True
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_match_no_pattern_fails(self, tmp_db):
        """regex_match without a pattern fails with descriptive message."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque(["output"])

            results = await _run_guardrails(1)
            assert results is not None
            assert results[0]["passed"] is False
            assert "No pattern specified" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_reject_no_pattern_passes(self, tmp_db):
        """regex_reject without a pattern passes (nothing to reject)."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_reject", "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque(["output"])

            results = await _run_guardrails(1)
            assert results is not None
            assert results[0]["passed"] is True
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_nonexistent_project_returns_none(self, tmp_db):
        """Returns None for a project ID that doesn't exist."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            results = await _run_guardrails(999)
            assert results is None
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_error_patterns_detected(self, tmp_db):
        """max_errors detects all error pattern variants."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 0, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "error: something wrong",
                "ERROR: critical failure",
                "Error: validation failed",
                "FATAL: out of memory",
                "fatal: unrecoverable",
                "panic: unexpected state",
                "PANIC: system crash",
                "this line is fine",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert results[0]["passed"] is False
            # Should detect 7 error lines (all except "this line is fine")
            assert "7 errors exceed max of 0" in results[0]["detail"]
        finally:
            database.DB_PATH = original


# ---------------------------------------------------------------------------
# Guardrail Endpoint Tests (GET /api/projects/{id}/guardrails)
# ---------------------------------------------------------------------------
class TestGuardrailEndpoint:
    """Test the GET /api/projects/{id}/guardrails endpoint."""

    @pytest.mark.asyncio
    async def test_guardrail_endpoint_returns_config(self, client, created_project, tmp_db):
        """Endpoint returns guardrail configuration."""
        pid = created_project["id"]

        # Save guardrail config
        guardrail_config = {
            "guardrails": [
                {"type": "regex_match", "pattern": "SUCCESS", "action": "halt"},
                {"type": "max_errors", "threshold": 5, "action": "warn"},
            ]
        }
        resp = await client.patch(
            f"/api/projects/{pid}/config",
            json=guardrail_config,
        )
        assert resp.status_code == 200

        # Fetch guardrails
        resp = await client.get(f"/api/projects/{pid}/guardrails")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert len(data["guardrails"]) == 2
        assert data["guardrails"][0]["type"] == "regex_match"
        assert data["guardrails"][1]["type"] == "max_errors"

    @pytest.mark.asyncio
    async def test_guardrail_endpoint_returns_last_results(self, client, created_project, tmp_db):
        """Endpoint returns last guardrail results from swarm_runs."""
        pid = created_project["id"]

        # Insert a run with guardrail results
        results_json = json.dumps([
            {"rule_type": "regex_match", "pattern": "OK", "threshold": None,
             "action": "halt", "passed": True, "detail": "Pattern found"},
        ])
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, guardrail_results) VALUES (?, ?, ?)",
                (pid, "completed", results_json),
            )
            await db.commit()

        resp = await client.get(f"/api/projects/{pid}/guardrails")
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_results"] is not None
        assert len(data["last_results"]) == 1
        assert data["last_results"][0]["passed"] is True
        assert data["last_run_id"] is not None

    @pytest.mark.asyncio
    async def test_guardrail_endpoint_no_config(self, client, created_project):
        """Endpoint returns empty guardrails when none configured."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/guardrails")
        assert resp.status_code == 200
        data = resp.json()
        assert data["guardrails"] == []
        assert data["last_results"] is None
        assert data["last_run_id"] is None

    @pytest.mark.asyncio
    async def test_guardrail_endpoint_404_for_missing_project(self, client):
        """Endpoint returns 404 for non-existent project."""
        resp = await client.get("/api/projects/99999/guardrails")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_guardrail_endpoint_returns_latest_run(self, client, created_project, tmp_db):
        """Endpoint returns results from the most recent run only."""
        pid = created_project["id"]

        # Insert two runs with different results
        old_results = json.dumps([
            {"rule_type": "regex_match", "pattern": "OLD", "threshold": None,
             "action": "halt", "passed": False, "detail": "Old run"},
        ])
        new_results = json.dumps([
            {"rule_type": "regex_match", "pattern": "NEW", "threshold": None,
             "action": "halt", "passed": True, "detail": "New run"},
        ])
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, guardrail_results) VALUES (?, ?, ?)",
                (pid, "completed", old_results),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, guardrail_results) VALUES (?, ?, ?)",
                (pid, "completed", new_results),
            )
            await db.commit()

        resp = await client.get(f"/api/projects/{pid}/guardrails")
        data = resp.json()
        assert data["last_results"][0]["detail"] == "New run"
        assert data["last_results"][0]["passed"] is True


# ---------------------------------------------------------------------------
# Halt Action Tests
# ---------------------------------------------------------------------------
class TestGuardrailHaltAction:
    """Test that halt action marks run as failed_guardrail."""

    @pytest.mark.asyncio
    async def test_halt_action_marks_run_failed_guardrail(self, tmp_db):
        """When halt guardrail fails, run status becomes failed_guardrail."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # Create project with halt guardrail
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "ALL TESTS PASS", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            # Populate output without the required pattern
            _project_output_buffers[1] = deque([
                "[Claude-1] Tests partially done",
            ])

            results = await _run_guardrails(1)
            assert results is not None

            # Simulate supervisor logic for determining run status
            has_halt = any(
                not r["passed"] and r["action"] == "halt"
                for r in results
            )
            assert has_halt is True, "Should detect halt violation"

            # In the real supervisor, this sets run_status = "failed_guardrail"
            run_status = "failed_guardrail" if has_halt else "completed"
            assert run_status == "failed_guardrail"
        finally:
            _project_output_buffers.clear()
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_warn_action_continues_with_completed_status(self, tmp_db):
        """When only warn guardrails fail, run status stays completed."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 0, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] ERROR: something broke",
            ])

            results = await _run_guardrails(1)
            assert results is not None

            has_halt = any(
                not r["passed"] and r["action"] == "halt"
                for r in results
            )
            has_violations = any(not r["passed"] for r in results)

            assert has_halt is False
            assert has_violations is True

            run_status = "failed_guardrail" if has_halt else "completed"
            assert run_status == "completed"
        finally:
            _project_output_buffers.clear()
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_mixed_halt_and_warn_results_in_halt(self, tmp_db):
        """Mix of halt and warn violations: halt takes precedence."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "REQUIRED", "action": "halt"},
                    {"type": "max_errors", "threshold": 0, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] ERROR: some issue",
                "[Claude-1] Done",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert len(results) == 2

            # regex_match failed (REQUIRED not found) + halt action
            assert results[0]["passed"] is False
            assert results[0]["action"] == "halt"

            # max_errors failed (1 error > 0 threshold) + warn action
            assert results[1]["passed"] is False
            assert results[1]["action"] == "warn"

            has_halt = any(
                not r["passed"] and r["action"] == "halt"
                for r in results
            )
            assert has_halt is True
        finally:
            _project_output_buffers.clear()
            database.DB_PATH = original


# ---------------------------------------------------------------------------
# Guardrail Results Storage Tests
# ---------------------------------------------------------------------------
class TestGuardrailResultsStorage:
    """Test that guardrail results are properly stored in swarm_runs."""

    @pytest.mark.asyncio
    async def test_guardrail_results_stored_in_swarm_runs(self, tmp_db):
        """Guardrail results are stored as JSON in swarm_runs.guardrail_results."""
        results = [
            {"rule_type": "regex_match", "pattern": "OK", "threshold": None,
             "action": "halt", "passed": True, "detail": "Pattern found"},
            {"rule_type": "max_errors", "pattern": None, "threshold": 5,
             "action": "warn", "passed": False, "detail": "8 errors exceed max of 5"},
        ]
        results_json = json.dumps(results)

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            # Create project
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Test", "/tmp/test"),
            )
            # Create run with guardrail results
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, guardrail_results) VALUES (?, ?, ?)",
                (1, "failed_guardrail", results_json),
            )
            await db.commit()

            # Verify stored correctly
            row = await (await db.execute(
                "SELECT guardrail_results FROM swarm_runs WHERE project_id = 1"
            )).fetchone()
            assert row is not None
            stored = json.loads(row["guardrail_results"])
            assert len(stored) == 2
            assert stored[0]["passed"] is True
            assert stored[1]["passed"] is False
            assert stored[1]["detail"] == "8 errors exceed max of 5"

    @pytest.mark.asyncio
    async def test_null_guardrail_results_when_not_configured(self, tmp_db):
        """guardrail_results is NULL when no guardrails are configured."""
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Test", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                (1, "completed"),
            )
            await db.commit()

            row = await (await db.execute(
                "SELECT guardrail_results FROM swarm_runs WHERE project_id = 1"
            )).fetchone()
            assert row["guardrail_results"] is None

    @pytest.mark.asyncio
    async def test_failed_guardrail_status_stored(self, tmp_db):
        """failed_guardrail status is stored correctly in swarm_runs."""
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Test", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                (1, "failed_guardrail"),
            )
            await db.commit()

            row = await (await db.execute(
                "SELECT status FROM swarm_runs WHERE project_id = 1"
            )).fetchone()
            assert row["status"] == "failed_guardrail"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------
class TestGuardrailEdgeCases:
    """Test edge cases in guardrail validation."""

    @pytest.fixture(autouse=True)
    def cleanup_buffers(self):
        yield
        _project_output_buffers.clear()

    @pytest.mark.asyncio
    async def test_max_errors_with_zero_threshold(self, tmp_db):
        """max_errors with threshold=0 fails on any error line."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 0, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] error: just one error",
            ])

            results = await _run_guardrails(1)
            assert results[0]["passed"] is False
            assert "1 errors exceed max of 0" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_max_errors_no_errors_passes(self, tmp_db):
        """max_errors passes when no error patterns are present."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "max_errors", "threshold": 0, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] All good",
                "[Claude-1] Clean output",
            ])

            results = await _run_guardrails(1)
            assert results[0]["passed"] is True
            assert "0 errors (max 0)" in results[0]["detail"]
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_min_lines_zero_threshold_always_passes(self, tmp_db):
        """min_lines with threshold=0 always passes (even empty output)."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "min_lines", "threshold": 0, "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            # Empty buffer
            results = await _run_guardrails(1)
            assert results[0]["passed"] is True
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_case_sensitivity(self, tmp_db):
        """regex_match is case-sensitive by default."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "SUCCESS", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] success",  # lowercase, should NOT match
            ])

            results = await _run_guardrails(1)
            assert results[0]["passed"] is False  # Case-sensitive
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_regex_with_flags(self, tmp_db):
        """User can use inline regex flags like (?i) for case-insensitive."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "(?i)success", "action": "halt"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] SUCCESS achieved",
            ])

            results = await _run_guardrails(1)
            assert results[0]["passed"] is True  # (?i) makes it case-insensitive
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_all_rules_pass_no_violations(self, tmp_db):
        """When all rules pass, no violations are detected."""
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                config = json.dumps({"guardrails": [
                    {"type": "regex_match", "pattern": "DONE", "action": "halt"},
                    {"type": "regex_reject", "pattern": "CRASH", "action": "halt"},
                    {"type": "min_lines", "threshold": 1, "action": "warn"},
                    {"type": "max_errors", "threshold": 10, "action": "warn"},
                ]})
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                    ("Test", "Test", "/tmp/test", config),
                )
                await db.commit()

            _project_output_buffers[1] = deque([
                "[Claude-1] Starting...",
                "[Claude-1] DONE",
            ])

            results = await _run_guardrails(1)
            assert results is not None
            assert all(r["passed"] for r in results)

            has_violations = any(not r["passed"] for r in results)
            assert has_violations is False
        finally:
            database.DB_PATH = original
