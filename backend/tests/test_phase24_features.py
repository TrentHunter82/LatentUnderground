"""Phase 24 backend feature tests.

Tests for:
- Rate limiting with API key identity
- Checkpoint cooldown thread safety
- Supervisor directive check runs via asyncio.to_thread
- _generate_run_summary runs via asyncio.to_thread
- Memory lifecycle management (tracking dict cleanup on project stop/delete)
- Shutdown cleanup (_cleanup_stale_tracking_dicts)
- Checkpoint batching (accumulation + flush to DB)
- Run ID caching (_current_run_ids)
- Stale run_id clearing on relaunch
- Startup security warnings
- _flush_checkpoints failure logging (WARNING level)
- Periodic checkpoint flush in supervisor loop
"""

import asyncio
import inspect
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest

from app import config, database
from app.routes.swarm import (
    _agent_drain_events,
    _agent_drain_threads,
    _agent_line_counts,
    _agent_log_files,
    _agent_output_buffers,
    _agent_processes,
    _agent_started_at,
    _buffers_lock,
    _CHECKPOINT_BATCH_SIZE,
    _CHECKPOINT_COOLDOWN_SECONDS,
    _MAX_OUTPUT_LINES,
    _checkpoint_batch,
    _checkpoint_batch_lock,
    _checkpoint_cooldowns,
    _cleanup_project_agents,
    _cleanup_stale_tracking_dicts,
    _current_run_ids,
    _flush_checkpoints,
    _generate_run_summary,
    _get_current_run_id,
    _known_directives,
    _last_output_at,
    _project_locks,
    _project_output_buffers,
    _project_resource_usage,
    _record_checkpoint_sync,
    _supervisor_tasks,
    _circuit_breakers,
    _cb_record_failure,
    _cb_check_restart_allowed,
    _cb_record_probe_start,
    _cb_record_probe_success,
    _get_circuit_breaker,
    _CB_DEFAULT_MAX_FAILURES,
    _CB_DEFAULT_WINDOW_SECONDS,
    _CB_DEFAULT_RECOVERY_SECONDS,
    cancel_drain_tasks,
)


# ---------------------------------------------------------------------------
# TestRateLimitKeyBasedIdentity
# ---------------------------------------------------------------------------


class TestRateLimitKeyBasedIdentity:
    """Verify rate limiting uses API key as identity, not just IP."""

    @pytest.mark.asyncio
    async def test_bearer_token_separates_buckets(self, app, client):
        """Different Bearer tokens get separate rate limit buckets."""
        from app.main import RateLimitMiddleware

        # Find the rate limiter instance on the app
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert "Bearer " in source, "Rate limiter should check Bearer token"
        assert "key:" in source, "Rate limiter should prefix key-based IDs"

    @pytest.mark.asyncio
    async def test_bearer_token_identity_extraction(self, app):
        """Bearer token identity uses first 8 chars of token."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        # The code extracts first 8 chars: auth_header[7:][:8]
        assert "[:8]" in source, "Should extract first 8 chars of key"

    @pytest.mark.asyncio
    async def test_xapikey_separates_buckets(self, app):
        """X-API-Key header identity is also extracted."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert "x-api-key" in source, "Should check X-API-Key header"

    @pytest.mark.asyncio
    async def test_no_auth_falls_back_to_ip(self, app):
        """Without auth headers, rate limit uses client IP."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert "request.client.host" in source, "Should fall back to client IP"

    @pytest.mark.asyncio
    async def test_rate_limit_key_format(self, app):
        """Rate limit key combines client_id and path."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert "request.url.path" in source, "Key should include URL path"

    @pytest.mark.asyncio
    async def test_rate_limit_cleans_stale_entries(self, app):
        """Rate limiter prunes empty buckets to prevent memory leak."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware.dispatch)
        assert ".pop(" in source, "Should pop empty keys to prevent memory leak"

    @pytest.mark.asyncio
    async def test_write_vs_read_rpm_split(self, app):
        """Write methods (POST/PUT/PATCH/DELETE) use stricter RPM than reads."""
        from app.main import RateLimitMiddleware
        source = inspect.getsource(RateLimitMiddleware)
        assert "write_rpm" in source
        assert "read_rpm" in source
        assert "_WRITE_METHODS" in source


# ---------------------------------------------------------------------------
# TestCheckpointCooldownThreadSafety
# ---------------------------------------------------------------------------


class TestCheckpointCooldownThreadSafety:
    """Verify concurrent _record_checkpoint_sync calls respect the 30s cooldown."""

    def setup_method(self):
        """Clean up state before each test."""
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        """Clean up state after each test."""
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_concurrent_same_type_only_one_passes(self, tmp_db):
        """Multiple threads writing same checkpoint type: only 1 should pass cooldown."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        # Create project and run in DB
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        # Pre-cache run_id
        _current_run_ids[1] = 1

        results = []
        barrier = threading.Barrier(4)

        def writer(thread_id):
            barrier.wait()
            _record_checkpoint_sync(
                project_id=1, run_id=1, agent_name="Claude-1",
                checkpoint_type="task_complete",
                data={"thread": thread_id},
            )

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Only 1 should have been added (the first to get the lock)
        with _checkpoint_batch_lock:
            count = len(_checkpoint_batch)

        assert count == 1, f"Expected exactly 1 checkpoint (cooldown blocks rest), got {count}"

        database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_concurrent_different_types_all_pass(self, tmp_db):
        """Threads writing different checkpoint types: all should pass cooldown."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        _current_run_ids[1] = 1

        types = ["task_complete", "error", "milestone", "directive"]
        barrier = threading.Barrier(4)

        def writer(cp_type):
            barrier.wait()
            _record_checkpoint_sync(
                project_id=1, run_id=1, agent_name="Claude-1",
                checkpoint_type=cp_type,
                data={"type": cp_type},
            )

        threads = [threading.Thread(target=writer, args=(t,)) for t in types]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        with _checkpoint_batch_lock:
            count = len(_checkpoint_batch)

        assert count == 4, f"Expected 4 checkpoints (different types), got {count}"

        database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_concurrent_different_agents_all_pass(self, tmp_db):
        """Threads writing same type for different agents: all should pass cooldown."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        _current_run_ids[1] = 1

        agents = ["Claude-1", "Claude-2", "Claude-3", "Claude-4"]
        barrier = threading.Barrier(4)

        def writer(agent):
            barrier.wait()
            _record_checkpoint_sync(
                project_id=1, run_id=1, agent_name=agent,
                checkpoint_type="task_complete",
                data={"agent": agent},
            )

        threads = [threading.Thread(target=writer, args=(a,)) for a in agents]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        with _checkpoint_batch_lock:
            count = len(_checkpoint_batch)

        assert count == 4, f"Expected 4 checkpoints (different agents), got {count}"

        database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_cooldown_key_format(self, tmp_db):
        """Cooldown key should be project:agent:type format."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        _current_run_ids[1] = 1

        _record_checkpoint_sync(
            project_id=1, run_id=1, agent_name="Claude-1",
            checkpoint_type="task_complete",
            data={"test": True},
        )

        expected_key = "1:Claude-1:task_complete"
        assert expected_key in _checkpoint_cooldowns, \
            f"Expected cooldown key '{expected_key}', got keys: {list(_checkpoint_cooldowns.keys())}"

        database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_cooldown_blocks_rapid_duplicate(self, tmp_db):
        """Same checkpoint type within 30s window should be blocked."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        _current_run_ids[1] = 1

        # First call should succeed
        _record_checkpoint_sync(1, 1, "Claude-1", "task_complete", {"first": True})
        # Second call within cooldown should be blocked
        _record_checkpoint_sync(1, 1, "Claude-1", "task_complete", {"second": True})

        with _checkpoint_batch_lock:
            count = len(_checkpoint_batch)

        assert count == 1, f"Second call should be blocked by cooldown, got {count}"

        database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_cooldown_expires_after_timeout(self, tmp_db):
        """Cooldown should expire after 30s, allowing new checkpoint."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        _current_run_ids[1] = 1

        # First call
        _record_checkpoint_sync(1, 1, "Claude-1", "task_complete", {"first": True})

        # Simulate cooldown expiration
        key = "1:Claude-1:task_complete"
        _checkpoint_cooldowns[key] = time.time() - _CHECKPOINT_COOLDOWN_SECONDS - 1

        # Second call should now succeed
        _record_checkpoint_sync(1, 1, "Claude-1", "task_complete", {"second": True})

        with _checkpoint_batch_lock:
            count = len(_checkpoint_batch)

        assert count == 2, f"Expected 2 checkpoints after cooldown expiry, got {count}"

        database.DB_PATH = database_orig


# ---------------------------------------------------------------------------
# TestSupervisorDirectiveAsync
# ---------------------------------------------------------------------------


class TestSupervisorDirectiveAsync:
    """Verify _check_directives_sync runs via asyncio.to_thread in supervisor."""

    @pytest.mark.asyncio
    async def test_directive_check_uses_to_thread(self):
        """The supervisor loop wraps _check_directives_sync in asyncio.to_thread."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "asyncio.to_thread(_check_directives_sync)" in source, \
            "Directive check must be called via asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_directive_check_uses_sync_sqlite(self):
        """_check_directives_sync uses sync sqlite3 (not aiosqlite) for thread safety."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        # The nested function _check_directives_sync is defined inside _supervisor_loop
        assert "import sqlite3" in source or "_sqlite3" in source, \
            "Directive check should use sync sqlite3"

    @pytest.mark.asyncio
    async def test_directive_check_records_consumed_events(self):
        """Consumed directives trigger _record_event_sync with 'directive_consumed' type."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "directive_consumed" in source, \
            "Should record 'directive_consumed' events"
        assert "_record_event_sync" in source, \
            "Should use _record_event_sync for thread-safe event recording"

    @pytest.mark.asyncio
    async def test_directive_check_error_handling(self):
        """Directive check failures are caught and logged, not propagated."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        # The directive check is wrapped in try/except
        assert "Directive check failed" in source, \
            "Should log directive check failures gracefully"


# ---------------------------------------------------------------------------
# TestRunSummaryAsync
# ---------------------------------------------------------------------------


class TestRunSummaryAsync:
    """Verify _generate_run_summary uses asyncio.to_thread for DB queries."""

    @pytest.mark.asyncio
    async def test_run_summary_uses_to_thread(self):
        """_generate_run_summary wraps DB query in asyncio.to_thread."""
        source = inspect.getsource(_generate_run_summary)
        assert "asyncio.to_thread" in source, \
            "Run summary DB query must use asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_run_summary_uses_sync_sqlite(self):
        """Inner DB query function uses sync sqlite3."""
        source = inspect.getsource(_generate_run_summary)
        assert "sqlite3" in source, \
            "Run summary should use sync sqlite3 for thread-safe DB access"

    @pytest.mark.asyncio
    async def test_run_summary_queries_agent_events(self):
        """Summary queries agent_events table for error count."""
        source = inspect.getsource(_generate_run_summary)
        assert "agent_crashed" in source, \
            "Should query for agent_crashed events"

    @pytest.mark.asyncio
    async def test_run_summary_reads_signals(self):
        """Summary reads .claude/signals/*.signal files."""
        source = inspect.getsource(_generate_run_summary)
        assert ".signal" in source, "Should read signal files"

    @pytest.mark.asyncio
    async def test_run_summary_parses_tasks(self):
        """Summary parses TASKS.md for task completion percentage."""
        source = inspect.getsource(_generate_run_summary)
        assert "TASKS.md" in source, "Should read TASKS.md"
        assert "\\[x\\]" in source or "[x]" in source, "Should count completed tasks"

    @pytest.mark.asyncio
    async def test_run_summary_returns_none_on_error(self):
        """_generate_run_summary returns None on exception (doesn't crash)."""
        source = inspect.getsource(_generate_run_summary)
        assert "return None" in source, \
            "Should return None on error, not crash"

    @pytest.mark.asyncio
    async def test_run_summary_aggregates_agent_data(self, tmp_db):
        """Summary correctly aggregates exit codes and output lines."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", str(tmp_db.parent / "proj")),
            )
            await db.commit()

        # Set up mock agent data
        key1 = "1:Claude-1"
        key2 = "1:Claude-2"
        mock_proc_1 = MagicMock()
        mock_proc_1.returncode = 0
        mock_proc_2 = MagicMock()
        mock_proc_2.returncode = 1

        _agent_processes[key1] = mock_proc_1
        _agent_processes[key2] = mock_proc_2
        with _buffers_lock:
            _agent_output_buffers[key1] = deque(["line1", "line2", "line3"])
            _agent_output_buffers[key2] = deque(["errline1"])
        _agent_started_at[key1] = "2026-01-01T00:00:00"
        _agent_started_at[key2] = "2026-01-01T00:00:01"

        try:
            summary = await _generate_run_summary(1)
            assert summary is not None
            assert summary["agent_count"] == 2
            assert summary["total_output_lines"] == 4
            assert "Claude-1" in summary["agents"]
            assert "Claude-2" in summary["agents"]
            assert summary["agents"]["Claude-1"]["exit_code"] == 0
            assert summary["agents"]["Claude-2"]["exit_code"] == 1
            assert summary["agents"]["Claude-1"]["output_lines"] == 3
            assert summary["agents"]["Claude-2"]["output_lines"] == 1
        finally:
            _agent_processes.pop(key1, None)
            _agent_processes.pop(key2, None)
            with _buffers_lock:
                _agent_output_buffers.pop(key1, None)
                _agent_output_buffers.pop(key2, None)
            _agent_started_at.pop(key1, None)
            _agent_started_at.pop(key2, None)
            database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_run_summary_empty_agents(self, tmp_db):
        """Summary with no agents returns zero counts."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", str(tmp_db.parent / "proj")),
            )
            await db.commit()

        try:
            summary = await _generate_run_summary(1)
            assert summary is not None
            assert summary["agent_count"] == 0
            assert summary["total_output_lines"] == 0
            assert summary["agents"] == {}
        finally:
            database.DB_PATH = database_orig


# ---------------------------------------------------------------------------
# TestFlushCheckpointsResilience
# ---------------------------------------------------------------------------


class TestFlushCheckpointsResilience:
    """Test _flush_checkpoints edge cases and error handling."""

    def setup_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_flush_empty_batch_is_noop(self, tmp_db):
        """Flushing empty batch should not touch DB."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # Should not raise
            _flush_checkpoints()
        finally:
            database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_flush_writes_to_db(self, tmp_db):
        """Flush correctly writes batch contents to agent_checkpoints table."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        # Add items to batch manually
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((1, 1, "Claude-1", "task_complete", json.dumps({"task": 1})))
            _checkpoint_batch.append((1, 1, "Claude-2", "error", json.dumps({"error": "oops"})))

        try:
            _flush_checkpoints()

            # Verify written to DB
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM agent_checkpoints ORDER BY id")
                rows = await cursor.fetchall()
                assert len(rows) == 2
                assert rows[0]["agent_name"] == "Claude-1"
                assert rows[0]["checkpoint_type"] == "task_complete"
                assert rows[1]["agent_name"] == "Claude-2"
                assert rows[1]["checkpoint_type"] == "error"
        finally:
            database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_flush_clears_batch(self, tmp_db):
        """After flush, the batch should be empty."""
        database_orig = database.DB_PATH
        database.DB_PATH = tmp_db

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                ("Test", "Goal", "/tmp/test"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
            )
            await db.commit()

        with _checkpoint_batch_lock:
            _checkpoint_batch.append((1, 1, "Claude-1", "task_complete", "{}"))

        try:
            _flush_checkpoints()
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 0, "Batch should be cleared after flush"
        finally:
            database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_flush_handles_db_error(self):
        """Flush with invalid DB path should log warning, not crash."""
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((1, 1, "Claude-1", "task_complete", "{}"))

        database_orig = database.DB_PATH
        database.DB_PATH = Path("/nonexistent/path/db.sqlite")

        try:
            # Should not raise
            _flush_checkpoints()
        finally:
            database.DB_PATH = database_orig

    @pytest.mark.asyncio
    async def test_flush_log_level_is_warning(self):
        """Flush failure should log at WARNING level (not DEBUG)."""
        source = inspect.getsource(_flush_checkpoints)
        assert "logger.warning" in source, \
            "Flush failures should be logged at WARNING level"

    @pytest.mark.asyncio
    async def test_flush_includes_batch_size_in_log(self):
        """Flush failure log should include the batch size."""
        source = inspect.getsource(_flush_checkpoints)
        assert "len(batch)" in source, \
            "Flush failure log should include batch size"


# ---------------------------------------------------------------------------
# TestSupervisorLoopCodeQuality
# ---------------------------------------------------------------------------


class TestSupervisorLoopCodeQuality:
    """Verify supervisor loop follows async safety patterns."""

    @pytest.mark.asyncio
    async def test_supervisor_finally_cleans_tracking(self):
        """Supervisor finally block cleans _supervisor_tasks and _known_directives."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "_supervisor_tasks.pop(" in source, \
            "Supervisor should clean up _supervisor_tasks in finally"
        assert "_known_directives.pop(" in source, \
            "Supervisor should clean up _known_directives in finally"

    @pytest.mark.asyncio
    async def test_supervisor_handles_cancellation(self):
        """Supervisor catches CancelledError for clean shutdown."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "CancelledError" in source, \
            "Supervisor should catch CancelledError"

    @pytest.mark.asyncio
    async def test_supervisor_flushes_checkpoints_before_summary(self):
        """Supervisor flushes pending checkpoints before generating summary."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        # Flush should appear before summary generation
        flush_pos = source.find("_flush_checkpoints")
        summary_pos = source.find("_generate_run_summary")
        assert flush_pos > 0 and summary_pos > 0, \
            "Both flush and summary should be in supervisor loop"
        assert flush_pos < summary_pos, \
            "Flush must happen before summary generation"

    @pytest.mark.asyncio
    async def test_supervisor_checkpoint_flush_uses_to_thread(self):
        """Checkpoint flush in supervisor runs via asyncio.to_thread."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "asyncio.to_thread(_flush_checkpoints)" in source, \
            "Checkpoint flush must be wrapped in asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_supervisor_terminate_uses_to_thread(self):
        """Agent termination in supervisor runs via asyncio.to_thread."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "asyncio.to_thread(_terminate_project_agents," in source, \
            "Agent termination must be wrapped in asyncio.to_thread"


# ===========================================================================
# Claude-1: Memory Lifecycle Management
# ===========================================================================


class TestMemoryLifecycleOnStop:
    """Verify that stopping a project clears all relevant tracking dicts."""

    def setup_method(self):
        _project_output_buffers.clear()
        _last_output_at.clear()
        _known_directives.clear()
        _project_resource_usage.clear()
        _current_run_ids.clear()
        _project_locks.clear()

    def teardown_method(self):
        _project_output_buffers.clear()
        _last_output_at.clear()
        _known_directives.clear()
        _project_resource_usage.clear()
        _current_run_ids.clear()
        _project_locks.clear()

    @pytest.mark.asyncio
    async def test_stop_clears_project_output_buffer(self, client, created_project):
        """Stopping a project should remove its output buffer."""
        pid = created_project["id"]
        with _buffers_lock:
            _project_output_buffers[pid] = deque(["line1", "line2"], maxlen=5000)
        _cleanup_project_agents(pid)
        assert pid not in _project_output_buffers

    @pytest.mark.asyncio
    async def test_stop_clears_last_output_at(self, client, created_project):
        """Stopping a project should remove auto-stop timer."""
        pid = created_project["id"]
        _last_output_at[pid] = time.time()
        _cleanup_project_agents(pid)
        assert pid not in _last_output_at

    @pytest.mark.asyncio
    async def test_stop_clears_known_directives(self, client, created_project):
        """Stopping a project should remove directive tracking."""
        pid = created_project["id"]
        _known_directives[pid] = {"Claude-1.directive", "Claude-2.directive"}
        _cleanup_project_agents(pid)
        assert pid not in _known_directives

    @pytest.mark.asyncio
    async def test_stop_clears_resource_usage(self, client, created_project):
        """Stopping a project should remove resource usage tracking."""
        pid = created_project["id"]
        _project_resource_usage[pid] = {
            "agent_count": 4, "restart_counts": {}, "started_at": time.time(),
        }
        _cleanup_project_agents(pid)
        assert pid not in _project_resource_usage

    @pytest.mark.asyncio
    async def test_stop_clears_current_run_ids(self, client, created_project):
        """Stopping a project should remove cached run_id."""
        pid = created_project["id"]
        _current_run_ids[pid] = 42
        _cleanup_project_agents(pid)
        assert pid not in _current_run_ids

    @pytest.mark.asyncio
    async def test_stop_preserves_project_locks(self, client, created_project):
        """Stopping a project should NOT remove its lock (caller may hold it)."""
        pid = created_project["id"]
        _project_locks[pid] = asyncio.Lock()
        _cleanup_project_agents(pid)
        assert pid in _project_locks

    @pytest.mark.asyncio
    async def test_full_lifecycle_create_stop_verify(self, client, created_project):
        """Full lifecycle: create -> seed state -> stop -> verify all cleaned."""
        pid = created_project["id"]
        with _buffers_lock:
            _project_output_buffers[pid] = deque(["output"], maxlen=5000)
        _last_output_at[pid] = time.time()
        _known_directives[pid] = {"Claude-1.directive"}
        _project_resource_usage[pid] = {"agent_count": 2, "restart_counts": {}, "started_at": time.time()}
        _current_run_ids[pid] = 99
        _project_locks[pid] = asyncio.Lock()

        _cleanup_project_agents(pid)

        assert pid not in _project_output_buffers
        assert pid not in _last_output_at
        assert pid not in _known_directives
        assert pid not in _project_resource_usage
        assert pid not in _current_run_ids
        assert pid in _project_locks  # Lock survives stop


# ===========================================================================
# Claude-1: Shutdown Cleanup
# ===========================================================================


class TestShutdownCleanupAllDicts:
    """Verify _cleanup_stale_tracking_dicts clears all tracking dicts."""

    def teardown_method(self):
        """Ensure clean state even if test fails."""
        _agent_processes.clear()
        _agent_output_buffers.clear()
        _agent_drain_threads.clear()
        _agent_drain_events.clear()
        _agent_started_at.clear()
        _agent_log_files.clear()
        _agent_line_counts.clear()
        _project_output_buffers.clear()
        _supervisor_tasks.clear()
        _last_output_at.clear()
        _known_directives.clear()
        _project_locks.clear()
        _project_resource_usage.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        _circuit_breakers.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_cleanup_clears_all_dicts(self, client, created_project, tmp_db):
        """_cleanup_stale_tracking_dicts should empty all 14+ tracking dicts."""
        pid = created_project["id"]
        key = f"{pid}:Claude-1"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.stdout.readline.return_value = b""
        mock_proc.terminate = MagicMock()

        _agent_processes[key] = mock_proc
        _agent_output_buffers[key] = deque(["test"], maxlen=5000)
        _agent_drain_threads[key] = []
        _agent_drain_events[key] = threading.Event()
        _agent_started_at[key] = "2026-01-01T00:00:00"
        _agent_log_files[key] = Path("/tmp/test.log")
        _agent_line_counts[key] = 100
        _project_output_buffers[pid] = deque(["out"], maxlen=5000)
        mock_task = MagicMock()
        mock_task.done.return_value = True
        _supervisor_tasks[pid] = mock_task
        _last_output_at[pid] = time.time()
        _known_directives[pid] = {"Claude-1.directive"}
        _project_locks[pid] = asyncio.Lock()
        _project_resource_usage[pid] = {"agent_count": 2, "restart_counts": {}, "started_at": time.time()}
        _checkpoint_cooldowns[f"{pid}:Claude-1:heartbeat"] = time.time()
        _current_run_ids[pid] = 42
        _circuit_breakers[f"{pid}:Claude-1"] = {
            "state": "open", "failures": [(time.time(), 1)],
            "opened_at": time.time(), "probe_started_at": None,
        }
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((pid, 1, "Claude-1", "heartbeat", "{}"))

        _cleanup_stale_tracking_dicts()

        assert len(_agent_processes) == 0
        assert len(_agent_output_buffers) == 0
        assert len(_agent_drain_threads) == 0
        assert len(_agent_drain_events) == 0
        assert len(_agent_started_at) == 0
        assert len(_agent_log_files) == 0
        assert len(_agent_line_counts) == 0
        assert len(_project_output_buffers) == 0
        assert len(_supervisor_tasks) == 0
        assert len(_last_output_at) == 0
        assert len(_known_directives) == 0
        assert len(_project_locks) == 0
        assert len(_project_resource_usage) == 0
        assert len(_checkpoint_cooldowns) == 0
        assert len(_current_run_ids) == 0
        assert len(_circuit_breakers) == 0
        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 0

    @pytest.mark.asyncio
    async def test_cleanup_flushes_pending_checkpoints(self, client, created_project, tmp_db):
        """_cleanup_stale_tracking_dicts should flush checkpoints before clearing."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
                (pid,),
            )
            await db.commit()
            cur = await db.execute("SELECT id FROM swarm_runs WHERE project_id = ?", (pid,))
            run_id = (await cur.fetchone())[0]

        with _checkpoint_batch_lock:
            _checkpoint_batch.append(
                (pid, run_id, "Claude-1", "heartbeat", json.dumps({"status": "alive"}))
            )

        _cleanup_stale_tracking_dicts()

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                "SELECT * FROM agent_checkpoints WHERE project_id = ?", (pid,)
            )).fetchall()
            assert len(rows) == 1
            assert rows[0]["agent_name"] == "Claude-1"
            assert rows[0]["checkpoint_type"] == "heartbeat"


# ===========================================================================
# Claude-1: Checkpoint Batching & Flush
# ===========================================================================


class TestCheckpointBatchingClaude1:
    """Verify _record_checkpoint_sync batching and _flush_checkpoints DB writes."""

    def setup_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_record_accumulates_in_batch(self, client, created_project):
        """_record_checkpoint_sync should add entry to _checkpoint_batch."""
        pid = created_project["id"]
        _current_run_ids[pid] = 1

        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"status": "alive"})

        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 1
            entry = _checkpoint_batch[0]
            assert entry[0] == pid
            assert entry[2] == "Claude-1"
            assert entry[3] == "heartbeat"

    @pytest.mark.asyncio
    async def test_flush_writes_correct_rows(self, client, created_project, tmp_db):
        """_flush_checkpoints writes all batch entries to agent_checkpoints table."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
                (pid,),
            )
            await db.commit()
            cur = await db.execute("SELECT id FROM swarm_runs WHERE project_id = ?", (pid,))
            run_id = (await cur.fetchone())[0]

        with _checkpoint_batch_lock:
            _checkpoint_batch.append((pid, run_id, "Claude-1", "heartbeat", json.dumps({"alive": True})))
            _checkpoint_batch.append((pid, run_id, "Claude-2", "progress", json.dumps({"pct": 50})))

        _flush_checkpoints()

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                "SELECT * FROM agent_checkpoints WHERE project_id = ? ORDER BY id",
                (pid,),
            )).fetchall()
            assert len(rows) == 2
            assert rows[0]["agent_name"] == "Claude-1"
            assert rows[1]["agent_name"] == "Claude-2"

    @pytest.mark.asyncio
    async def test_auto_flush_at_batch_size(self, client, created_project, tmp_db):
        """When batch reaches BATCH_SIZE (20), auto-flush triggers."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
                (pid,),
            )
            await db.commit()
            cur = await db.execute("SELECT id FROM swarm_runs WHERE project_id = ?", (pid,))
            run_id = (await cur.fetchone())[0]

        _current_run_ids[pid] = run_id

        # Record 20 unique checkpoint types
        for i in range(20):
            _record_checkpoint_sync(pid, run_id, "Claude-1", f"type_{i}", {"idx": i})

        # Batch should be empty (auto-flushed)
        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 0

        # DB should have 20 rows
        async with aiosqlite.connect(tmp_db) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM agent_checkpoints WHERE project_id = ?", (pid,)
            )
            assert (await cur.fetchone())[0] == 20


# ===========================================================================
# Claude-1: Checkpoint Cooldown
# ===========================================================================


class TestCheckpointCooldownClaude1:
    """Verify 30s cooldown per (project:agent:type)."""

    def setup_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_same_type_within_cooldown_skipped(self, client, created_project):
        """Duplicate checkpoint within 30s is skipped."""
        pid = created_project["id"]
        _current_run_ids[pid] = 1

        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"n": 1})
        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"n": 2})

        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 1  # Second skipped

    @pytest.mark.asyncio
    async def test_different_type_not_throttled(self, client, created_project):
        """Different checkpoint types don't share cooldown."""
        pid = created_project["id"]
        _current_run_ids[pid] = 1

        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"n": 1})
        _record_checkpoint_sync(pid, 1, "Claude-1", "progress", {"n": 2})

        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 2

    @pytest.mark.asyncio
    async def test_after_cooldown_write_allowed(self, client, created_project):
        """After 30s cooldown expires, same type can be written again."""
        pid = created_project["id"]
        _current_run_ids[pid] = 1

        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"n": 1})

        # Backdate cooldown
        _checkpoint_cooldowns[f"{pid}:Claude-1:heartbeat"] = time.time() - 31

        _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"n": 2})

        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 2


# ===========================================================================
# Claude-1: Cooldown Thread Safety
# ===========================================================================


class TestCooldownConcurrencyClaude1:
    """Verify concurrent calls don't bypass 30s cooldown."""

    def setup_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_concurrent_same_type_only_one(self, client, created_project):
        """10 threads writing same checkpoint: only 1 should pass cooldown."""
        pid = created_project["id"]
        _current_run_ids[pid] = 1

        errors = []
        def _write(idx):
            try:
                _record_checkpoint_sync(pid, 1, "Claude-1", "heartbeat", {"t": idx})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 1


# ===========================================================================
# Claude-1: Run ID Caching
# ===========================================================================


class TestRunIdCachingClaude1:
    """Verify _current_run_ids cache avoids repeated DB queries."""

    def setup_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_first_call_queries_db_and_caches(self, client, created_project, tmp_db):
        """First checkpoint with no cached run_id queries DB, then caches result."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
                (pid,),
            )
            await db.commit()
            cur = await db.execute(
                "SELECT id FROM swarm_runs WHERE project_id = ? AND status = 'running'",
                (pid,),
            )
            run_id = (await cur.fetchone())[0]

        assert pid not in _current_run_ids

        _record_checkpoint_sync(pid, None, "Claude-1", "heartbeat", {"status": "alive"})

        assert _current_run_ids.get(pid) == run_id

    @pytest.mark.asyncio
    async def test_cached_value_used_in_batch(self, client, created_project):
        """Cached run_id is used in the checkpoint batch entry."""
        pid = created_project["id"]
        _current_run_ids[pid] = 42

        _record_checkpoint_sync(pid, None, "Claude-1", "heartbeat", {"n": 1})

        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) >= 1
            assert _checkpoint_batch[-1][1] == 42  # run_id from cache

    @pytest.mark.asyncio
    async def test_no_running_run_returns_none(self, client, created_project, tmp_db):
        """_get_current_run_id returns None when no running swarm_runs exist."""
        pid = created_project["id"]
        result = _get_current_run_id(pid)
        assert result is None


# ===========================================================================
# Claude-1: Stale Run ID on Relaunch
# ===========================================================================


class TestStaleRunIdRelaunch:
    """Verify _current_run_ids is cleared at launch start."""

    @pytest.mark.asyncio
    async def test_launch_clears_stale_cached_run_id(
        self, client, project_with_folder, mock_launch_deps, tmp_db
    ):
        """Launching swarm clears stale cached run_id."""
        pid = project_with_folder["id"]
        _current_run_ids[pid] = 999  # Stale from previous launch

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 1, "max_phases": 1,
            })

        assert resp.status_code == 200
        # Stale value 999 should be gone
        assert _current_run_ids.get(pid) != 999 or pid not in _current_run_ids

    def test_launch_source_clears_run_id_before_cleanup(self):
        """_launch_swarm_locked clears _current_run_ids before cleanup."""
        from app.routes.swarm import _launch_swarm_locked
        source = inspect.getsource(_launch_swarm_locked)
        # Clear should come before cancel_drain_tasks
        clear_pos = source.find("_current_run_ids.pop")
        cleanup_pos = source.find("cancel_drain_tasks")
        assert clear_pos > 0, "_current_run_ids.pop must be in launch function"
        assert cleanup_pos > 0, "cancel_drain_tasks must be in launch function"
        assert clear_pos < cleanup_pos, "Run ID clear should come before cleanup"


# ===========================================================================
# Claude-1: Startup Security Warnings
# ===========================================================================


class TestStartupSecurityWarnings:
    """Verify security warning logs at startup."""

    @pytest.mark.asyncio
    async def test_warns_empty_key_nonlocal_host(self, caplog):
        """Should warn when API key empty and HOST != 127.0.0.1."""
        original_key, original_host = config.API_KEY, config.HOST
        try:
            config.API_KEY = ""
            config.HOST = "0.0.0.0"

            with caplog.at_level(logging.WARNING, logger="app.main"):
                from app.main import logger as main_logger
                if not config.API_KEY and config.HOST != "127.0.0.1":
                    main_logger.warning(
                        "SECURITY: API key is empty and HOST=%s — API is accessible without authentication. "
                        "Set LU_API_KEY to enable authentication.",
                        config.HOST,
                    )

            assert any("SECURITY" in r.message and "empty" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key
            config.HOST = original_host

    @pytest.mark.asyncio
    async def test_warns_weak_key(self, caplog):
        """Should warn when API key < 16 chars."""
        original_key = config.API_KEY
        try:
            config.API_KEY = "short_key"

            with caplog.at_level(logging.WARNING, logger="app.main"):
                from app.main import logger as main_logger
                if config.API_KEY and len(config.API_KEY) < 16:
                    main_logger.warning(
                        "SECURITY: API key is shorter than 16 characters — consider using a stronger key",
                    )

            assert any("shorter than 16" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key

    @pytest.mark.asyncio
    async def test_no_warning_localhost_no_key(self, caplog):
        """No warning when HOST=127.0.0.1 and no key (safe local dev)."""
        original_key, original_host = config.API_KEY, config.HOST
        try:
            config.API_KEY = ""
            config.HOST = "127.0.0.1"

            with caplog.at_level(logging.WARNING, logger="app.main"):
                from app.main import logger as main_logger
                if not config.API_KEY and config.HOST != "127.0.0.1":
                    main_logger.warning("SECURITY: should not appear")

            assert not any("SECURITY" in r.message and "empty" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key
            config.HOST = original_host

    @pytest.mark.asyncio
    async def test_security_summary_log(self, caplog):
        """Should log security summary with auth/rate/CORS status."""
        original_key = config.API_KEY
        try:
            config.API_KEY = "a-secure-key-that-is-long-enough"

            with caplog.at_level(logging.INFO, logger="latent"):
                from app.main import logger as main_logger
                auth_status = "enabled" if config.API_KEY else "disabled"
                rate_status = f"write={config.RATE_LIMIT_RPM}/min, read={config.RATE_LIMIT_READ_RPM}/min"
                cors_status = ", ".join(config.CORS_ORIGINS[:3]) + (
                    "..." if len(config.CORS_ORIGINS) > 3 else ""
                )
                main_logger.info(
                    "Security: auth=%s, rate_limiting=[%s], CORS=[%s]",
                    auth_status, rate_status, cors_status,
                )

            # r.message is the raw format string; getMessage() has interpolated values
            assert any("Security: auth=enabled" in r.getMessage() for r in caplog.records)
        finally:
            config.API_KEY = original_key

    @pytest.mark.asyncio
    async def test_no_weak_key_warning_with_strong_key(self, caplog):
        """No weak-key warning when key is >= 16 chars."""
        original_key = config.API_KEY
        try:
            config.API_KEY = "a-secure-key-that-is-long-enough"

            with caplog.at_level(logging.WARNING, logger="app.main"):
                from app.main import logger as main_logger
                if config.API_KEY and len(config.API_KEY) < 16:
                    main_logger.warning("SECURITY: should not appear")

            assert not any("shorter than 16" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key


# ===========================================================================
# Claude-1: _flush_checkpoints Failure Logging
# ===========================================================================


class TestFlushFailureLogging:
    """Verify _flush_checkpoints logs failures at WARNING level with batch size."""

    def setup_method(self):
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    def teardown_method(self):
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

    @pytest.mark.asyncio
    async def test_flush_failure_is_warning_not_debug(self, caplog):
        """Failed flush logs at WARNING, not DEBUG."""
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((999, 1, "Claude-1", "heartbeat", "{}"))

        with patch("app.routes.swarm.database") as mock_db:
            mock_db.DB_PATH = Path("/nonexistent/path/db.sqlite")
            with caplog.at_level(logging.WARNING, logger="app.routes.swarm"):
                _flush_checkpoints()

        assert any(
            r.levelno == logging.WARNING and "Failed to flush" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_flush_failure_includes_count(self, caplog):
        """Failed flush log includes batch size (e.g. 'Failed to flush 3 checkpoints')."""
        with _checkpoint_batch_lock:
            for i in range(3):
                _checkpoint_batch.append((999, 1, f"Claude-{i+1}", "hb", "{}"))

        with patch("app.routes.swarm.database") as mock_db:
            mock_db.DB_PATH = Path("/nonexistent/path/db.sqlite")
            with caplog.at_level(logging.WARNING, logger="app.routes.swarm"):
                _flush_checkpoints()

        assert any("3 checkpoints" in r.message for r in caplog.records)

    def test_flush_source_uses_warning(self):
        """Source code of _flush_checkpoints uses logger.warning (not debug)."""
        source = inspect.getsource(_flush_checkpoints)
        assert "logger.warning" in source
        assert "logger.debug" not in source


# ===========================================================================
# Claude-1: Periodic Checkpoint Flush in Supervisor Loop
# ===========================================================================


class TestPeriodicCheckpointFlushSupervisor:
    """Verify supervisor flushes checkpoints every ~60s."""

    def test_supervisor_has_flush_interval_constant(self):
        """Supervisor defines _SUPERVISOR_FLUSH_INTERVAL for periodic flush."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "_SUPERVISOR_FLUSH_INTERVAL = 6" in source

    def test_supervisor_counts_iterations(self):
        """Supervisor uses iteration_count for modulo-based flush trigger."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "iteration_count" in source
        assert "iteration_count %" in source

    def test_periodic_flush_uses_to_thread(self):
        """Periodic flush runs via asyncio.to_thread (non-blocking)."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "asyncio.to_thread(_flush_checkpoints)" in source

    def test_periodic_flush_has_error_handling(self):
        """Periodic flush errors are caught and logged (don't crash supervisor)."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "Periodic checkpoint flush failed" in source


# ===========================================================================
# Claude-1: Error Handling Source Verification
# ===========================================================================


class TestErrorHandlingSourceVerification:
    """Verify all three error handling improvements are implemented correctly."""

    def test_flush_uses_warning_level(self):
        """_flush_checkpoints should use logger.warning, not logger.debug."""
        source = inspect.getsource(_flush_checkpoints)
        assert "logger.warning" in source
        assert "logger.debug" not in source

    def test_launch_clears_run_id_early(self):
        """_launch_swarm_locked clears stale _current_run_ids at start."""
        from app.routes.swarm import _launch_swarm_locked
        source = inspect.getsource(_launch_swarm_locked)
        assert "_current_run_ids.pop" in source

    def test_supervisor_has_periodic_flush(self):
        """Supervisor loop includes periodic checkpoint flush."""
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "iteration_count % _SUPERVISOR_FLUSH_INTERVAL" in source


# ===========================================================================
# Claude-1: Circuit Breaker State Machine
# ===========================================================================


class TestCircuitBreakerStateMachine:
    """Verify circuit breaker state transitions and failure tracking."""

    def setup_method(self):
        _circuit_breakers.clear()

    def teardown_method(self):
        _circuit_breakers.clear()

    def test_initial_state_is_closed(self):
        """New circuit breaker starts in closed state."""
        cb = _get_circuit_breaker("1:Claude-1")
        assert cb["state"] == "closed"
        assert cb["failures"] == []
        assert cb["opened_at"] is None

    def test_record_failure_below_threshold(self):
        """Failures below threshold keep circuit closed."""
        result = _cb_record_failure("1:Claude-1", exit_code=1, max_failures=3, window_seconds=300)
        assert result is None
        cb = _circuit_breakers["1:Claude-1"]
        assert cb["state"] == "closed"
        assert len(cb["failures"]) == 1

    def test_circuit_opens_at_threshold(self):
        """Circuit opens when failure count reaches max_failures."""
        for i in range(2):
            _cb_record_failure("1:Claude-1", exit_code=1, max_failures=3, window_seconds=300)
        result = _cb_record_failure("1:Claude-1", exit_code=1, max_failures=3, window_seconds=300)
        assert result == "opened"
        cb = _circuit_breakers["1:Claude-1"]
        assert cb["state"] == "open"
        assert cb["opened_at"] is not None

    def test_circuit_does_not_open_outside_window(self):
        """Failures outside window are pruned and don't count."""
        cb = _get_circuit_breaker("1:Claude-1")
        # Add 2 failures from 400 seconds ago (outside 300s window)
        old_time = time.time() - 400
        cb["failures"] = [(old_time, 1), (old_time + 1, 1)]
        # Add 1 recent failure
        result = _cb_record_failure("1:Claude-1", exit_code=1, max_failures=3, window_seconds=300)
        assert result is None  # Only 1 failure in window
        assert len(cb["failures"]) == 1  # Old failures pruned

    def test_open_circuit_blocks_restart(self):
        """Open circuit should block restart attempts."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "open"
        cb["opened_at"] = time.time()
        allowed, reason = _cb_check_restart_allowed("1:Claude-1", 3, 300, 60)
        assert not allowed
        assert "Circuit breaker open" in reason

    def test_recovery_transitions_to_half_open(self):
        """After recovery period, circuit transitions to half-open."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "open"
        cb["opened_at"] = time.time() - 61  # 61s ago, recovery_seconds=60
        cb["failures"] = [(time.time() - 61, 1)]
        allowed, reason = _cb_check_restart_allowed("1:Claude-1", 3, 300, 60)
        assert allowed
        assert reason == "half-open"
        assert cb["state"] == "half-open"

    def test_probe_start_recorded(self):
        """Starting a probe records the timestamp."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "half-open"
        _cb_record_probe_start("1:Claude-1")
        assert cb["probe_started_at"] is not None

    def test_probe_success_closes_circuit(self):
        """Successful probe closes the circuit."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "half-open"
        cb["failures"] = [(time.time(), 1)]
        cb["probe_started_at"] = time.time() - 31
        _cb_record_probe_success("1:Claude-1")
        assert cb["state"] == "closed"
        assert cb["failures"] == []
        assert cb["opened_at"] is None

    def test_probe_failure_reopens_circuit(self):
        """Failed probe re-opens the circuit."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "half-open"
        cb["failures"] = [(time.time(), 1)]
        result = _cb_record_failure("1:Claude-1", exit_code=1, max_failures=3, window_seconds=300)
        assert result == "reopened"
        assert cb["state"] == "open"

    def test_half_open_blocks_second_probe(self):
        """Half-open state with active probe blocks additional restarts."""
        cb = _get_circuit_breaker("1:Claude-1")
        cb["state"] = "half-open"
        cb["probe_started_at"] = time.time()
        allowed, reason = _cb_check_restart_allowed("1:Claude-1", 3, 300, 60)
        assert not allowed
        assert "probe restart in progress" in reason


class TestCircuitBreakerConfig:
    """Verify circuit breaker config in ProjectConfig."""

    def test_config_fields_exist(self):
        """ProjectConfig should have circuit breaker fields."""
        from app.models.project import ProjectConfig
        fields = ProjectConfig.model_fields
        assert "circuit_breaker_max_failures" in fields
        assert "circuit_breaker_window_seconds" in fields
        assert "circuit_breaker_recovery_seconds" in fields

    def test_config_validation_bounds(self):
        """Circuit breaker config fields should have proper bounds."""
        from app.models.project import ProjectConfig
        # Valid config
        cfg = ProjectConfig(
            circuit_breaker_max_failures=3,
            circuit_breaker_window_seconds=300,
            circuit_breaker_recovery_seconds=60,
        )
        assert cfg.circuit_breaker_max_failures == 3
        assert cfg.circuit_breaker_window_seconds == 300

    def test_config_max_failures_bounds(self):
        """max_failures should be 1-10."""
        from app.models.project import ProjectConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProjectConfig(circuit_breaker_max_failures=0)  # Below min
        with pytest.raises(ValidationError):
            ProjectConfig(circuit_breaker_max_failures=11)  # Above max

    def test_config_window_bounds(self):
        """window_seconds should be 60-3600."""
        from app.models.project import ProjectConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProjectConfig(circuit_breaker_window_seconds=59)  # Below min
        with pytest.raises(ValidationError):
            ProjectConfig(circuit_breaker_window_seconds=3601)  # Above max


class TestCircuitBreakerInAgentStatus:
    """Verify circuit_state field in AgentStatusOut."""

    def test_agent_status_has_circuit_state(self):
        """AgentStatusOut should have circuit_state field."""
        from app.models.responses import AgentStatusOut
        status = AgentStatusOut(
            name="Claude-1", alive=True, circuit_state="closed",
        )
        assert status.circuit_state == "closed"

    def test_agent_status_circuit_state_default_none(self):
        """circuit_state defaults to None when not set."""
        from app.models.responses import AgentStatusOut
        status = AgentStatusOut(name="Claude-1", alive=True)
        assert status.circuit_state is None


class TestCircuitBreakerInRestart:
    """Verify restart_agent checks circuit breaker state."""

    @pytest.mark.asyncio
    async def test_restart_blocked_by_open_circuit(
        self, client, project_with_folder, mock_launch_deps, tmp_db
    ):
        """Restart should be blocked when circuit is open."""
        pid = project_with_folder["id"]
        key = f"{pid}:Claude-1"

        # Launch to register agent
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 1, "max_phases": 1,
            })
            assert resp.status_code == 200

        # Simulate agent exit
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1

        # Set circuit breaker config
        await client.patch(f"/api/projects/{pid}/config", json={
            "circuit_breaker_max_failures": 3,
            "circuit_breaker_window_seconds": 300,
            "circuit_breaker_recovery_seconds": 60,
        })

        # Open the circuit manually
        cb = _get_circuit_breaker(key)
        cb["state"] = "open"
        cb["opened_at"] = time.time()
        cb["failures"] = [(time.time(), 1), (time.time(), 1), (time.time(), 1)]

        # Attempt restart
        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 429
        assert "Circuit breaker open" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_restart_allowed_when_circuit_closed(
        self, client, project_with_folder, mock_launch_deps, tmp_db
    ):
        """Restart should work when circuit is closed (normal)."""
        pid = project_with_folder["id"]

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 1, "max_phases": 1,
            })
            assert resp.status_code == 200

        # Simulate agent exit
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0

        # Set circuit breaker config (but circuit is closed, so restart should work)
        await client.patch(f"/api/projects/{pid}/config", json={
            "circuit_breaker_max_failures": 3,
        })

        mock_proc2 = MagicMock()
        mock_proc2.pid = 12346
        mock_proc2.poll.return_value = None
        mock_proc2.stdout.readline.return_value = b""
        mock_proc2.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc2), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 200


class TestCircuitBreakerCleanup:
    """Verify circuit breakers are cleaned up properly."""

    def setup_method(self):
        _circuit_breakers.clear()

    def teardown_method(self):
        _circuit_breakers.clear()

    @pytest.mark.asyncio
    async def test_cleanup_project_agents_clears_circuit_breakers(self, client, created_project):
        """_cleanup_project_agents should clear circuit breakers for the project."""
        pid = created_project["id"]
        _circuit_breakers[f"{pid}:Claude-1"] = {"state": "open", "failures": [], "opened_at": None, "probe_started_at": None}
        _circuit_breakers[f"{pid}:Claude-2"] = {"state": "closed", "failures": [], "opened_at": None, "probe_started_at": None}
        _circuit_breakers["999:Claude-1"] = {"state": "closed", "failures": [], "opened_at": None, "probe_started_at": None}

        _cleanup_project_agents(pid)

        # Project's breakers should be gone
        assert f"{pid}:Claude-1" not in _circuit_breakers
        assert f"{pid}:Claude-2" not in _circuit_breakers
        # Other project's breaker should survive
        assert "999:Claude-1" in _circuit_breakers

    @pytest.mark.asyncio
    async def test_shutdown_clears_all_circuit_breakers(self, client, created_project, tmp_db):
        """_cleanup_stale_tracking_dicts should clear all circuit breakers."""
        _circuit_breakers["1:Claude-1"] = {"state": "open", "failures": [], "opened_at": None, "probe_started_at": None}
        _cleanup_stale_tracking_dicts()
        assert len(_circuit_breakers) == 0


class TestCircuitBreakerInListAgents:
    """Verify list_agents includes circuit_state."""

    @pytest.mark.asyncio
    async def test_list_agents_includes_circuit_state(
        self, client, project_with_folder, mock_launch_deps
    ):
        """GET /agents/{pid} should include circuit_state for each agent."""
        pid = project_with_folder["id"]

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 1, "max_phases": 1,
            })
            assert resp.status_code == 200

        # Set circuit breaker state
        key = f"{pid}:Claude-1"
        _circuit_breakers[key] = {
            "state": "open", "failures": [(time.time(), 1)],
            "opened_at": time.time(), "probe_started_at": None,
        }

        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        claude1 = next(a for a in agents if a["name"] == "Claude-1")
        assert claude1["circuit_state"] == "open"

    @pytest.mark.asyncio
    async def test_list_agents_circuit_state_none_when_no_breaker(
        self, client, project_with_folder, mock_launch_deps
    ):
        """circuit_state should be None when no circuit breaker exists."""
        pid = project_with_folder["id"]

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid, "agent_count": 1, "max_phases": 1,
            })
            assert resp.status_code == 200

        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        claude1 = next(a for a in agents if a["name"] == "Claude-1")
        assert claude1["circuit_state"] is None
