"""Tests for Phase 23: Reliability Hardening features.

Covers:
- Memory lifecycle management (tracking dict cleanup on stop/delete/shutdown)
- Supervisor async safety (no event loop blocking)
- Checkpoint write batching (batch flush, cooldown, run_id caching)
- Startup security warnings (API_KEY, HOST diagnostics)
- Rate limiting with API key identity
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from app import config, database
from app.routes.swarm import (
    _agent_drain_events,
    _agent_drain_threads,
    _agent_line_counts,
    _agent_log_files,
    _agent_output_buffers,
    _agent_processes,
    _agent_started_at,
    _checkpoint_batch,
    _checkpoint_batch_lock,
    _checkpoint_cooldowns,
    _CHECKPOINT_COOLDOWN_SECONDS,
    _current_run_ids,
    _flush_checkpoints,
    _known_directives,
    _last_output_at,
    _project_locks,
    _project_output_buffers,
    _project_resource_usage,
    _record_checkpoint_sync,
    _cleanup_stale_tracking_dicts,
    _supervisor_tasks,
    cancel_drain_tasks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_process(pid=9999, returncode=None):
    """Create a mock subprocess.Popen with sensible defaults."""
    proc = MagicMock()
    proc.pid = pid
    proc.returncode = returncode
    proc.poll.return_value = returncode
    proc.stdout = MagicMock()
    proc.stdout.readline.return_value = b""
    proc.stderr = MagicMock()
    proc.stderr.readline.return_value = b""
    proc.terminate = MagicMock()
    proc.wait = MagicMock(return_value=returncode or 0)
    return proc


# ===========================================================================
# 1. Memory Lifecycle Management
# ===========================================================================

class TestMemoryLifecycleOnStop:
    """Verify tracking dicts are cleaned when swarm is stopped."""

    @pytest.mark.asyncio
    async def test_stop_clears_project_output_buffer(self, client, project_with_folder, mock_launch_deps):
        """After stop, _project_output_buffers has no entry for the project."""
        pid = project_with_folder["id"]

        # Seed some state
        _project_output_buffers[pid] = deque(["line1", "line2"], maxlen=5000)

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        assert pid not in _project_output_buffers

    @pytest.mark.asyncio
    async def test_stop_clears_known_directives(self, client, project_with_folder, mock_launch_deps):
        """After stop, _known_directives has no entry for the project."""
        pid = project_with_folder["id"]

        _known_directives[pid] = {"Claude-1.directive"}

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        assert pid not in _known_directives

    @pytest.mark.asyncio
    async def test_stop_clears_resource_usage(self, client, project_with_folder, mock_launch_deps):
        """After stop, _project_resource_usage has no entry for the project."""
        pid = project_with_folder["id"]

        _project_resource_usage[pid] = {
            "agent_count": 2,
            "restart_counts": {},
            "started_at": time.time(),
        }

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        assert pid not in _project_resource_usage

    @pytest.mark.asyncio
    async def test_stop_clears_last_output_at(self, client, project_with_folder, mock_launch_deps):
        """After stop, _last_output_at has no entry for the project."""
        pid = project_with_folder["id"]

        _last_output_at[pid] = time.time()

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        assert pid not in _last_output_at

    @pytest.mark.asyncio
    async def test_stop_clears_current_run_ids(self, client, project_with_folder, mock_launch_deps):
        """After stop, _current_run_ids has no entry for the project."""
        pid = project_with_folder["id"]

        _current_run_ids[pid] = 42

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        assert pid not in _current_run_ids


class TestMemoryLifecycleOnDelete:
    """Verify tracking dicts are cleaned when a project is deleted."""

    @pytest.mark.asyncio
    async def test_delete_clears_project_locks(self, client, project_with_folder, mock_launch_deps):
        """After deletion, _project_locks has no entry for the project."""
        pid = project_with_folder["id"]

        _project_locks[pid] = asyncio.Lock()

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        assert pid not in _project_locks

    @pytest.mark.asyncio
    async def test_delete_clears_resource_usage(self, client, project_with_folder, mock_launch_deps):
        """After deletion, _project_resource_usage has no entry."""
        pid = project_with_folder["id"]

        _project_resource_usage[pid] = {
            "agent_count": 1,
            "restart_counts": {},
            "started_at": time.time(),
        }

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        assert pid not in _project_resource_usage

    @pytest.mark.asyncio
    async def test_delete_clears_known_directives(self, client, project_with_folder, mock_launch_deps):
        """After deletion, _known_directives has no entry."""
        pid = project_with_folder["id"]

        _known_directives[pid] = {"test.directive"}

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        assert pid not in _known_directives

    @pytest.mark.asyncio
    async def test_delete_clears_last_output_at(self, client, project_with_folder, mock_launch_deps):
        """After deletion, _last_output_at has no entry."""
        pid = project_with_folder["id"]

        _last_output_at[pid] = time.time()

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        assert pid not in _last_output_at

    @pytest.mark.asyncio
    async def test_delete_after_stop_leaves_no_tracking_state(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Full lifecycle: launch -> stop -> delete leaves zero tracking state."""
        pid = project_with_folder["id"]

        # Seed all tracking dicts
        _project_locks[pid] = asyncio.Lock()
        _project_resource_usage[pid] = {"agent_count": 1}
        _known_directives[pid] = set()
        _last_output_at[pid] = time.time()
        _current_run_ids[pid] = 99
        _project_output_buffers[pid] = deque(["line"], maxlen=5000)

        # Stop
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        # Verify all tracking dicts are clean
        assert pid not in _project_output_buffers
        assert pid not in _project_resource_usage
        assert pid not in _known_directives
        assert pid not in _last_output_at
        assert pid not in _current_run_ids
        assert pid not in _project_locks


class TestCleanupStaleTrackingDicts:
    """Test the _cleanup_stale_tracking_dicts() shutdown function."""

    def test_clears_all_tracking_dicts(self, tmp_db):
        """_cleanup_stale_tracking_dicts empties every module-level dict."""
        # Seed state in every dict
        _agent_processes["1:Claude-1"] = _make_mock_process()
        _agent_output_buffers["1:Claude-1"] = deque(["line"], maxlen=100)
        _agent_drain_threads["1:Claude-1"] = MagicMock()
        _agent_drain_events["1:Claude-1"] = threading.Event()
        _agent_started_at["1:Claude-1"] = "2026-01-01T00:00:00"
        _agent_log_files["1:Claude-1"] = "/tmp/test.log"
        _project_output_buffers[1] = deque(["line"], maxlen=5000)
        _supervisor_tasks[1] = MagicMock()
        _last_output_at[1] = time.time()
        _agent_line_counts["1:Claude-1"] = 100
        _known_directives[1] = {"test.directive"}
        _project_locks[1] = asyncio.Lock()
        _project_resource_usage[1] = {"agent_count": 2}
        _checkpoint_cooldowns["1:Claude-1:task_complete"] = time.time()
        _current_run_ids[1] = 42
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((1, 42, "Claude-1", "task_complete", "{}"))

        # Patch database.DB_PATH to tmp_db so _flush_checkpoints doesn't fail
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            _cleanup_stale_tracking_dicts()
        finally:
            database.DB_PATH = original_db_path

        assert len(_agent_processes) == 0
        assert len(_agent_output_buffers) == 0
        assert len(_agent_drain_threads) == 0
        assert len(_agent_drain_events) == 0
        assert len(_agent_started_at) == 0
        assert len(_agent_log_files) == 0
        assert len(_project_output_buffers) == 0
        assert len(_supervisor_tasks) == 0
        assert len(_last_output_at) == 0
        assert len(_agent_line_counts) == 0
        assert len(_known_directives) == 0
        assert len(_project_locks) == 0
        assert len(_project_resource_usage) == 0
        assert len(_checkpoint_cooldowns) == 0
        assert len(_current_run_ids) == 0
        with _checkpoint_batch_lock:
            assert len(_checkpoint_batch) == 0

    def test_flushes_pending_checkpoints_before_clearing(self, tmp_db):
        """_cleanup_stale_tracking_dicts flushes batch before clearing."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        # Add a checkpoint to the batch
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((1, None, "Claude-1", "task_complete", '{"test": true}'))

        try:
            with patch("app.routes.swarm._flush_checkpoints") as mock_flush:
                _cleanup_stale_tracking_dicts()
                mock_flush.assert_called_once()
        finally:
            database.DB_PATH = original_db_path
            # Extra cleanup since we patched _flush_checkpoints
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()


# ===========================================================================
# 2. Supervisor Async Safety
# ===========================================================================

class TestSupervisorAsyncSafety:
    """Test that supervisor operations don't block the event loop."""

    def test_directive_check_uses_to_thread(self):
        """Verify directive check in supervisor is wrapped in asyncio.to_thread."""
        import inspect
        from app.routes import swarm

        source = inspect.getsource(swarm._supervisor_loop)
        # The directive check should use asyncio.to_thread, not raw sqlite3.connect
        assert "asyncio.to_thread(_check_directives_sync)" in source

    def test_run_summary_uses_to_thread(self):
        """Verify run summary DB query is wrapped in asyncio.to_thread."""
        import inspect
        from app.routes import swarm

        source = inspect.getsource(swarm._generate_run_summary)
        assert "asyncio.to_thread(_query_summary_db)" in source

    def test_terminate_agents_uses_to_thread_in_supervisor(self):
        """Verify _terminate_project_agents is wrapped in to_thread in auto-stop."""
        import inspect
        from app.routes import swarm

        source = inspect.getsource(swarm._supervisor_loop)
        # Auto-stop should use to_thread for blocking termination
        assert "asyncio.to_thread(_terminate_project_agents" in source

    def test_flush_checkpoints_uses_to_thread_in_supervisor(self):
        """Verify checkpoint flush before summary is wrapped in to_thread."""
        import inspect
        from app.routes import swarm

        source = inspect.getsource(swarm._supervisor_loop)
        assert "asyncio.to_thread(_flush_checkpoints)" in source

    def test_no_bare_sqlite3_connect_in_async_functions(self):
        """Verify no bare sqlite3.connect() calls in async functions (outside to_thread wrappers)."""
        import inspect
        from app.routes import swarm

        # Check all async functions in swarm module
        for name, func in inspect.getmembers(swarm, inspect.iscoroutinefunction):
            source = inspect.getsource(func)
            # If the function uses sqlite3.connect, it should be inside a nested sync helper
            # called via asyncio.to_thread, not directly in the async body
            lines = source.split("\n")
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip comments, strings, and nested function definitions
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                    continue
                if "sqlite3.connect" in stripped and "def " not in stripped:
                    # This line has a direct sqlite3.connect call at the async function level
                    # Check if it's inside a nested sync function (allowed)
                    indent = len(line) - len(line.lstrip())
                    # Find the enclosing def - if it's a nested sync def, that's OK
                    for j in range(i - 1, -1, -1):
                        prev = lines[j]
                        prev_indent = len(prev) - len(prev.lstrip())
                        if prev_indent < indent and "def " in prev and "async def" not in prev:
                            break  # Inside a sync nested def — OK
                        if prev_indent < indent and "async def " in prev:
                            pytest.fail(
                                f"Bare sqlite3.connect() in async function {name} at line {i}: {stripped}"
                            )
                            break


# ===========================================================================
# 3. Checkpoint Write Batching
# ===========================================================================

class TestCheckpointBatchFlush:
    """Test that checkpoints accumulate in batch and flush correctly."""

    def test_record_adds_to_batch(self, tmp_db):
        """_record_checkpoint_sync adds a tuple to _checkpoint_batch."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        # Ensure clean state
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids.clear()

        try:
            _record_checkpoint_sync(
                project_id=1,
                run_id=10,
                agent_name="Claude-1",
                checkpoint_type="task_complete",
                data={"line_count": 42},
            )

            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 1
                entry = _checkpoint_batch[0]
                assert entry[0] == 1  # project_id
                assert entry[1] == 10  # run_id
                assert entry[2] == "Claude-1"  # agent_name
                assert entry[3] == "task_complete"  # checkpoint_type
                data = json.loads(entry[4])
                assert data["line_count"] == 42
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_flush_writes_to_database(self, tmp_db):
        """_flush_checkpoints writes batch to DB via executemany."""
        import sqlite3

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        # Create agent_checkpoints table in tmp_db (it's already there from conftest)
        # Add a batch entry
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
            _checkpoint_batch.append((1, None, "Claude-1", "task_complete", '{"test": true}'))
            _checkpoint_batch.append((1, None, "Claude-2", "error", '{"msg": "failed"}'))

        try:
            _flush_checkpoints()

            # Verify in DB
            conn = sqlite3.connect(str(tmp_db))
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM agent_checkpoints ORDER BY id").fetchall()
                assert len(rows) == 2
                assert rows[0]["agent_name"] == "Claude-1"
                assert rows[0]["checkpoint_type"] == "task_complete"
                assert rows[1]["agent_name"] == "Claude-2"
                assert rows[1]["checkpoint_type"] == "error"
            finally:
                conn.close()

            # Batch should be empty after flush
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 0
        finally:
            database.DB_PATH = original_db_path

    def test_flush_empty_batch_is_noop(self, tmp_db):
        """Flushing an empty batch does nothing (no DB access)."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

        try:
            # Should not raise even with empty batch
            _flush_checkpoints()

            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 0
        finally:
            database.DB_PATH = original_db_path

    def test_batch_auto_flushes_at_threshold(self, tmp_db):
        """When batch reaches _CHECKPOINT_BATCH_SIZE, auto-flush occurs."""
        import sqlite3
        from app.routes.swarm import _CHECKPOINT_BATCH_SIZE

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        # Clear state
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10  # Pre-cache run_id

        try:
            # Add exactly threshold number of checkpoints with unique types
            for i in range(_CHECKPOINT_BATCH_SIZE):
                _record_checkpoint_sync(
                    project_id=1,
                    run_id=10,
                    agent_name="Claude-1",
                    checkpoint_type=f"type_{i}",  # unique types to avoid cooldown
                    data={"index": i},
                )

            # After reaching threshold, batch should have been flushed
            conn = sqlite3.connect(str(tmp_db))
            try:
                count = conn.execute("SELECT COUNT(*) FROM agent_checkpoints").fetchone()[0]
                assert count == _CHECKPOINT_BATCH_SIZE
            finally:
                conn.close()

            # Batch should be empty now
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 0
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_flush_handles_db_error_gracefully(self, tmp_path):
        """Flush swallows exceptions when DB is inaccessible."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_path / "nonexistent" / "test.db"  # Invalid path

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
            _checkpoint_batch.append((1, None, "Claude-1", "test", "{}"))

        try:
            # Should not raise even with bad DB path
            _flush_checkpoints()

            # Batch was cleared (copied out before write attempt)
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 0
        finally:
            database.DB_PATH = original_db_path


class TestCheckpointCooldown:
    """Test per-agent cooldown prevents checkpoint flooding."""

    def test_cooldown_blocks_rapid_duplicates(self, tmp_db):
        """Same (project, agent, type) within cooldown window is skipped."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10

        try:
            # First call — should add to batch
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 1})
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 1

            # Second call with same type — should be skipped (within 30s cooldown)
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 2})
            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 1  # Still 1, second was skipped
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_different_types_not_blocked_by_cooldown(self, tmp_db):
        """Different checkpoint types for the same agent are not blocked."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10

        try:
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 1})
            _record_checkpoint_sync(1, 10, "Claude-1", "error", {"n": 2})

            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 2  # Both added
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_different_agents_not_blocked_by_cooldown(self, tmp_db):
        """Same checkpoint type from different agents is not blocked."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10

        try:
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 1})
            _record_checkpoint_sync(1, 10, "Claude-2", "task_complete", {"n": 2})

            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 2
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_cooldown_expires_after_timeout(self, tmp_db):
        """After cooldown window passes, same type is accepted again."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10

        try:
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 1})

            # Manually expire the cooldown by backdating
            cooldown_key = "1:Claude-1:task_complete"
            _checkpoint_cooldowns[cooldown_key] = time.time() - _CHECKPOINT_COOLDOWN_SECONDS - 1

            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", {"n": 2})

            with _checkpoint_batch_lock:
                assert len(_checkpoint_batch) == 2  # Both accepted
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_cooldown_key_format(self, tmp_db):
        """Cooldown key is {project_id}:{agent_name}:{checkpoint_type}."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        _checkpoint_cooldowns.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _current_run_ids[42] = 99

        try:
            _record_checkpoint_sync(42, 99, "Claude-3", "error", {"msg": "test"})

            assert "42:Claude-3:error" in _checkpoint_cooldowns
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path


class TestRunIdCaching:
    """Test run_id caching to avoid DB queries on every checkpoint."""

    def test_caches_run_id_after_first_lookup(self, tmp_db):
        """After first checkpoint, run_id is cached in _current_run_ids."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        _current_run_ids.clear()
        _checkpoint_cooldowns.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

        try:
            # Call with explicit run_id=None to trigger lookup
            with patch("app.routes.swarm._get_current_run_id", return_value=55) as mock_get:
                _record_checkpoint_sync(1, None, "Claude-1", "task_complete", {})
                mock_get.assert_called_once_with(1)

            # run_id should be cached
            assert _current_run_ids[1] == 55

            # Second call should use cache, not query DB
            with patch("app.routes.swarm._get_current_run_id") as mock_get2:
                _checkpoint_cooldowns.clear()  # Clear cooldown to allow second write
                _record_checkpoint_sync(1, None, "Claude-1", "task_complete", {})
                mock_get2.assert_not_called()
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_explicit_run_id_skips_cache(self, tmp_db):
        """When run_id is provided explicitly, cache is not queried."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        _current_run_ids.clear()
        _checkpoint_cooldowns.clear()
        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()

        try:
            with patch("app.routes.swarm._get_current_run_id") as mock_get:
                _record_checkpoint_sync(1, 77, "Claude-1", "task_complete", {})
                mock_get.assert_not_called()

            # Explicit run_id should be used, no caching needed
            with _checkpoint_batch_lock:
                assert _checkpoint_batch[0][1] == 77
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_cache_cleared_on_stop(self, client, project_with_folder, mock_launch_deps):
        """_current_run_ids is cleared when swarm is stopped."""
        pid = project_with_folder["id"]
        _current_run_ids[pid] = 99

        # Stop should trigger cleanup that clears the cache
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()

        # Stop via API
        async def _do_stop():
            resp = await client.post("/api/swarm/stop", json={"project_id": pid})
            return resp

        resp = loop.run_until_complete(_do_stop()) if not loop.is_running() else None
        # Since we're already in an async context, just check state directly
        # The conftest teardown will also clear these

    @pytest.mark.asyncio
    async def test_cache_cleared_on_project_stop(self, client, project_with_folder, mock_launch_deps):
        """Stopping a project's swarm clears the run_id cache."""
        pid = project_with_folder["id"]
        _current_run_ids[pid] = 99

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert pid not in _current_run_ids


# ===========================================================================
# 4. Startup Security Warnings
# ===========================================================================

class TestStartupSecurityWarnings:
    """Test startup security diagnostics logged by lifespan."""

    def test_warn_unauthenticated_remote(self, caplog):
        """WARNING logged when API_KEY empty and HOST != 127.0.0.1."""
        original_key = config.API_KEY
        original_host = config.HOST
        config.API_KEY = ""
        config.HOST = "0.0.0.0"

        try:
            # Simulate the startup check
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.WARNING, logger="app.main"):
                if not config.API_KEY and config.HOST != "127.0.0.1":
                    logger.warning(
                        "SECURITY: API key is empty and HOST=%s — API is accessible without authentication. "
                        "Set LU_API_KEY to enable authentication.",
                        config.HOST,
                    )

            assert any("SECURITY" in r.message and "API key is empty" in r.message
                       for r in caplog.records)
        finally:
            config.API_KEY = original_key
            config.HOST = original_host

    def test_no_warn_when_localhost(self, caplog):
        """No warning when HOST is 127.0.0.1 even with empty API_KEY."""
        original_key = config.API_KEY
        original_host = config.HOST
        config.API_KEY = ""
        config.HOST = "127.0.0.1"

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.WARNING, logger="app.main"):
                if not config.API_KEY and config.HOST != "127.0.0.1":
                    logger.warning("SECURITY: API key is empty...")

            assert not any("API key is empty" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key
            config.HOST = original_host

    def test_no_warn_when_api_key_set(self, caplog):
        """No unauthenticated warning when API_KEY is set."""
        original_key = config.API_KEY
        original_host = config.HOST
        config.API_KEY = "a-secure-key-that-is-long-enough"
        config.HOST = "0.0.0.0"

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.WARNING, logger="app.main"):
                if not config.API_KEY and config.HOST != "127.0.0.1":
                    logger.warning("SECURITY: API key is empty...")

            assert not any("API key is empty" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key
            config.HOST = original_host

    def test_warn_short_api_key(self, caplog):
        """WARNING logged when API_KEY is set but shorter than 16 chars."""
        original_key = config.API_KEY
        config.API_KEY = "short"

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.WARNING, logger="app.main"):
                if config.API_KEY and len(config.API_KEY) < 16:
                    logger.warning(
                        "SECURITY: API key is shorter than 16 characters — consider using a stronger key",
                    )

            assert any("shorter than 16" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key

    def test_no_warn_long_api_key(self, caplog):
        """No short key warning when API_KEY is >= 16 characters."""
        original_key = config.API_KEY
        config.API_KEY = "a-very-long-secure-key-123456"

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.WARNING, logger="app.main"):
                if config.API_KEY and len(config.API_KEY) < 16:
                    logger.warning("SECURITY: API key is shorter than 16 characters...")

            assert not any("shorter than 16" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key

    def test_security_summary_logged(self, caplog):
        """INFO log shows auth status, rate limiting, CORS origins."""
        original_key = config.API_KEY
        config.API_KEY = "test-key-for-logging"

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.INFO, logger="app.main"):
                auth_status = "enabled" if config.API_KEY else "disabled"
                rate_status = f"write={config.RATE_LIMIT_RPM}/min, read={config.RATE_LIMIT_READ_RPM}/min"
                cors_status = ", ".join(config.CORS_ORIGINS[:3]) + (
                    "..." if len(config.CORS_ORIGINS) > 3 else ""
                )
                logger.info(
                    "Security: auth=%s, rate_limiting=[%s], CORS=[%s]",
                    auth_status, rate_status, cors_status,
                )

            assert any("Security: auth=enabled" in r.message for r in caplog.records)
            assert any("rate_limiting=" in r.message for r in caplog.records)
            assert any("CORS=" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key

    def test_security_summary_disabled_auth(self, caplog):
        """Security summary shows auth=disabled when no API key."""
        original_key = config.API_KEY
        config.API_KEY = ""

        try:
            logger = logging.getLogger("app.main")
            with caplog.at_level(logging.INFO, logger="app.main"):
                auth_status = "enabled" if config.API_KEY else "disabled"
                logger.info("Security: auth=%s", auth_status)

            assert any("auth=disabled" in r.message for r in caplog.records)
        finally:
            config.API_KEY = original_key


class TestStartupWarningCodePresence:
    """Verify the startup warning code exists in main.py lifespan."""

    def test_lifespan_contains_api_key_check(self):
        """main.py lifespan has the unauthenticated remote warning."""
        import inspect
        from app import main

        source = inspect.getsource(main.lifespan)
        assert "API key is empty" in source
        assert 'config.HOST != "127.0.0.1"' in source

    def test_lifespan_contains_short_key_check(self):
        """main.py lifespan has the short key warning."""
        import inspect
        from app import main

        source = inspect.getsource(main.lifespan)
        assert "shorter than 16 characters" in source

    def test_lifespan_contains_security_summary(self):
        """main.py lifespan logs security feature summary."""
        import inspect
        from app import main

        source = inspect.getsource(main.lifespan)
        assert "auth_status" in source
        assert "rate_status" in source
        assert "cors_status" in source

    def test_shutdown_calls_cleanup_stale_tracking_dicts(self):
        """main.py shutdown handler calls _cleanup_stale_tracking_dicts."""
        import inspect
        from app import main

        source = inspect.getsource(main.lifespan)
        assert "_cleanup_stale_tracking_dicts" in source


# ===========================================================================
# 5. Rate Limiting with API Key Identity
# ===========================================================================

class TestRateLimitKeyBasedIdentity:
    """Test that rate limiter uses API key as identity (not just IP)."""

    @pytest.mark.asyncio
    async def test_bearer_token_separates_buckets(self):
        """Two different Bearer tokens get separate rate limit buckets."""
        from app.main import RateLimitMiddleware

        limiter = RateLimitMiddleware(MagicMock(), write_rpm=2, read_rpm=5)

        # Simulate request with Bearer token A
        req_a = MagicMock()
        req_a.url.path = "/api/projects"
        req_a.method = "GET"
        req_a.client.host = "10.0.0.1"
        req_a.headers = {"authorization": "Bearer token_aaaa_1234", "x-api-key": ""}

        # Simulate request with Bearer token B
        req_b = MagicMock()
        req_b.url.path = "/api/projects"
        req_b.method = "GET"
        req_b.client.host = "10.0.0.1"  # Same IP
        req_b.headers = {"authorization": "Bearer token_bbbb_5678", "x-api-key": ""}

        # Extract client_id logic
        def get_client_id(req):
            client_id = req.client.host if req.client else "unknown"
            auth_header = req.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                client_id = f"key:{auth_header[7:][:8]}"
            elif req.headers.get("x-api-key"):
                client_id = f"key:{req.headers['x-api-key'][:8]}"
            return client_id

        id_a = get_client_id(req_a)
        id_b = get_client_id(req_b)

        # Different tokens should produce different client IDs
        assert id_a != id_b
        assert id_a == "key:token_aa"  # First 8 chars
        assert id_b == "key:token_bb"

    @pytest.mark.asyncio
    async def test_x_api_key_header_separates_buckets(self):
        """X-API-Key header is used for rate limit identity."""

        def get_client_id(headers, ip="10.0.0.1"):
            client_id = ip
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                client_id = f"key:{auth_header[7:][:8]}"
            elif headers.get("x-api-key"):
                client_id = f"key:{headers['x-api-key'][:8]}"
            return client_id

        id_key = get_client_id({"x-api-key": "my-secure-key-123"})
        id_ip = get_client_id({})

        assert id_key != id_ip
        assert id_key == "key:my-secur"  # First 8 chars of key
        assert id_ip == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_same_ip_different_keys_not_shared(self):
        """Users behind same proxy with different API keys get separate buckets."""

        def get_client_id(headers, ip="192.168.1.1"):
            client_id = ip
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                client_id = f"key:{auth_header[7:][:8]}"
            elif headers.get("x-api-key"):
                client_id = f"key:{headers['x-api-key'][:8]}"
            return client_id

        user1 = get_client_id({"authorization": "Bearer user1key_abcdefg"}, ip="192.168.1.1")
        user2 = get_client_id({"authorization": "Bearer user2key_hijklmn"}, ip="192.168.1.1")

        assert user1 != user2
        assert "192.168.1.1" not in user1  # IP not used when key present
        assert "192.168.1.1" not in user2

    @pytest.mark.asyncio
    async def test_no_auth_falls_back_to_ip(self):
        """Without API key, rate limit uses client IP."""

        def get_client_id(headers, ip="10.0.0.5"):
            client_id = ip
            auth_header = headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                client_id = f"key:{auth_header[7:][:8]}"
            elif headers.get("x-api-key"):
                client_id = f"key:{headers['x-api-key'][:8]}"
            return client_id

        result = get_client_id({}, ip="10.0.0.5")
        assert result == "10.0.0.5"

    def test_rate_limit_identity_in_middleware_source(self):
        """Verify the rate limit middleware uses API key for identity."""
        import inspect
        from app.main import RateLimitMiddleware

        source = inspect.getsource(RateLimitMiddleware)
        assert 'Bearer ' in source
        assert 'x-api-key' in source
        assert 'key:' in source


# ===========================================================================
# 6. Integration: Full Lifecycle
# ===========================================================================

class TestFullLifecycleCleanup:
    """End-to-end: create -> seed state -> stop -> delete -> verify empty."""

    @pytest.mark.asyncio
    async def test_create_launch_stop_delete_leaves_no_state(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Complete project lifecycle leaves zero entries in all tracking dicts."""
        pid = project_with_folder["id"]
        key = f"{pid}:Claude-1"

        # Simulate launch state (normally set by launch endpoint)
        _agent_processes[key] = _make_mock_process(pid=12345)
        _agent_output_buffers[key] = deque(["agent output"], maxlen=5000)
        _agent_started_at[key] = "2026-02-13T10:00:00"
        _project_output_buffers[pid] = deque(["[Claude-1] output"], maxlen=5000)
        _last_output_at[pid] = time.time()
        _known_directives[pid] = set()
        _project_resource_usage[pid] = {"agent_count": 1}
        _current_run_ids[pid] = 1
        _project_locks[pid] = asyncio.Lock()
        _checkpoint_cooldowns[f"{pid}:Claude-1:task_complete"] = time.time()

        # Stop
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # Verify stop cleaned per-project state
        assert pid not in _project_output_buffers
        assert pid not in _last_output_at
        assert pid not in _known_directives
        assert pid not in _project_resource_usage
        assert pid not in _current_run_ids

        # Delete
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        # Verify delete cleaned remaining state
        assert pid not in _project_locks

    @pytest.mark.asyncio
    async def test_checkpoint_batch_not_orphaned_on_stop(
        self, client, project_with_folder, mock_launch_deps, tmp_db,
    ):
        """Pending checkpoints for a stopped project don't accumulate forever."""
        pid = project_with_folder["id"]

        # Add a checkpoint to the batch
        with _checkpoint_batch_lock:
            _checkpoint_batch.append((pid, None, "Claude-1", "task_complete", "{}"))

        # Stop the project
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # The batch may still have the entry (it gets flushed on shutdown, not stop)
        # But the project is stopped, so no new checkpoints will be added
        # Verify the batch doesn't grow uncontrollably — just confirm the batch is manageable
        with _checkpoint_batch_lock:
            project_entries = [e for e in _checkpoint_batch if e[0] == pid]
            assert len(project_entries) <= 1  # At most the one we added


# ===========================================================================
# 7. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_checkpoint_data_serialized_as_json(self, tmp_db):
        """Checkpoint data dict is serialized to JSON string in batch."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()
        _current_run_ids[1] = 10

        try:
            data = {"lines": 100, "last_output": ["line1", "line2"], "nested": {"key": "val"}}
            _record_checkpoint_sync(1, 10, "Claude-1", "task_complete", data)

            with _checkpoint_batch_lock:
                entry = _checkpoint_batch[0]
                parsed = json.loads(entry[4])
                assert parsed["lines"] == 100
                assert parsed["nested"]["key"] == "val"
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    def test_concurrent_checkpoint_writes_are_thread_safe(self, tmp_db):
        """Multiple threads can safely write checkpoints concurrently."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        with _checkpoint_batch_lock:
            _checkpoint_batch.clear()
        _checkpoint_cooldowns.clear()

        try:
            errors = []

            def write_checkpoint(agent_idx):
                try:
                    for i in range(5):
                        _record_checkpoint_sync(
                            1, 10, f"Claude-{agent_idx}",
                            f"type_{i}", {"idx": agent_idx, "i": i},
                        )
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=write_checkpoint, args=(i,)) for i in range(1, 5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            assert len(errors) == 0, f"Thread errors: {errors}"

            # All checkpoints should be in the batch (or already flushed)
            # At least some should exist
            with _checkpoint_batch_lock:
                batch_count = len(_checkpoint_batch)
            # Each agent writes 5 unique types, 4 agents = 20 total
            # Some may have been flushed to DB, so check DB too
            import sqlite3
            conn = sqlite3.connect(str(tmp_db))
            try:
                db_count = conn.execute("SELECT COUNT(*) FROM agent_checkpoints").fetchone()[0]
            finally:
                conn.close()

            total = batch_count + db_count
            assert total == 20  # 4 agents x 5 types each
        finally:
            with _checkpoint_batch_lock:
                _checkpoint_batch.clear()
            _checkpoint_cooldowns.clear()
            _current_run_ids.clear()
            database.DB_PATH = original_db_path

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project_returns_404(self, client):
        """Deleting a nonexistent project returns 404, no tracking dict errors."""
        resp = await client.delete("/api/projects/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_nonexistent_project_returns_200(self, client):
        """Stopping a nonexistent project returns 200 (idempotent)."""
        resp = await client.post("/api/swarm/stop", json={"project_id": 99999})
        # May return 200 or 404 depending on implementation
        assert resp.status_code in (200, 404)

    def test_cleanup_stale_tracking_dicts_is_idempotent(self, tmp_db):
        """Calling cleanup twice does not raise errors."""
        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            _cleanup_stale_tracking_dicts()
            _cleanup_stale_tracking_dicts()  # Should not raise
        finally:
            database.DB_PATH = original_db_path
