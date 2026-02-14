"""Phase 21: Agent Observability & Direction — comprehensive test suite.

Tests cover:
- agent_events migration (table, columns, indexes, idempotent re-run)
- Agent event emission (agent_started, agent_stopped, agent_crashed, output_milestone)
- GET /api/swarm/events/{project_id} with filters
- Run summary generation (various scenarios)
- GET /api/swarm/output/{project_id}/search endpoint
- GET /api/swarm/runs/compare endpoint
- Directive system end-to-end (POST/GET directive, urgent restart, cleanup)
- PUT /api/swarm/agents/{project_id}/{agent_name}/prompt endpoint
"""

import asyncio
import json
import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Migration Tests
# ---------------------------------------------------------------------------

class TestMigration004:
    """Test agent_events table creation via migration_004."""

    @pytest.mark.asyncio
    async def test_migration_creates_agent_events_table(self, tmp_path):
        """migration_004 creates agent_events table with correct columns."""
        db_path = tmp_path / "mig.db"
        from app.database import init_db, DB_PATH, SCHEMA_VERSION
        from app import database

        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await init_db()
            async with aiosqlite.connect(db_path) as db:
                # Verify table exists
                row = await (await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_events'"
                )).fetchone()
                assert row is not None, "agent_events table should exist"

                # Verify column names
                cursor = await db.execute("PRAGMA table_info(agent_events)")
                cols = {r[1] for r in await cursor.fetchall()}
                expected = {"id", "project_id", "run_id", "agent_name", "event_type", "detail", "timestamp"}
                assert expected == cols, f"Missing columns: {expected - cols}"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_migration_creates_indexes(self, tmp_path):
        """migration_004 creates the expected indexes."""
        db_path = tmp_path / "mig.db"
        from app import database

        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()
            async with aiosqlite.connect(db_path) as db:
                rows = await (await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_agent_events%'"
                )).fetchall()
                index_names = {r[0] for r in rows}
                assert "idx_agent_events_project_ts" in index_names
                assert "idx_agent_events_type" in index_names
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_migration_adds_summary_column(self, tmp_path):
        """migration_004 adds summary column to swarm_runs."""
        db_path = tmp_path / "mig.db"
        from app import database

        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("PRAGMA table_info(swarm_runs)")
                cols = {r[1] for r in await cursor.fetchall()}
                assert "summary" in cols, "swarm_runs should have summary column"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_migration_idempotent(self, tmp_path):
        """Running init_db twice doesn't fail."""
        db_path = tmp_path / "mig.db"
        from app import database

        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()
            # Second run should be a no-op
            await database.init_db()

            async with aiosqlite.connect(db_path) as db:
                row = await (await db.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )).fetchone()
                assert row[0] == database.SCHEMA_VERSION
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_migration_preserves_data(self, tmp_path):
        """Data inserted before migration_004 is preserved."""
        db_path = tmp_path / "mig.db"
        from app import database

        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()
            async with aiosqlite.connect(db_path) as db:
                # Insert a project and run
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", "/tmp/p1"),
                )
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'completed')",
                )
                await db.commit()

            # Re-run migrations (should be no-op)
            await database.init_db()

            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                proj = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                assert proj["name"] == "P1"
                run = await (await db.execute("SELECT * FROM swarm_runs WHERE id = 1")).fetchone()
                assert run["status"] == "completed"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_schema_version_is_4(self):
        """SCHEMA_VERSION constant matches migration count."""
        from app.database import SCHEMA_VERSION, _MIGRATIONS
        assert SCHEMA_VERSION == 6
        assert len(_MIGRATIONS) == 6
        assert _MIGRATIONS[-1][0] == 6


# ---------------------------------------------------------------------------
# Agent Event Emission Tests
# ---------------------------------------------------------------------------

class TestAgentEventEmission:
    """Test that events are correctly recorded during agent lifecycle."""

    @pytest.mark.asyncio
    async def test_record_event_sync_writes_to_db(self, tmp_db):
        """_record_event_sync inserts an event into agent_events table."""
        from app.routes.swarm import _record_event_sync
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # First create a project to satisfy FK
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", "/tmp/p1"),
                )
                await db.commit()

            _record_event_sync(1, "Claude-1", "agent_started", "pid=1234")

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM agent_events WHERE project_id = 1"
                )).fetchone()
                assert row is not None
                assert row["agent_name"] == "Claude-1"
                assert row["event_type"] == "agent_started"
                assert row["detail"] == "pid=1234"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_record_event_async_works(self, tmp_db):
        """_record_event_async wraps the sync call correctly."""
        from app.routes.swarm import _record_event_async
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", "/tmp/p1"),
                )
                await db.commit()

            await _record_event_async(1, "Claude-2", "agent_crashed", "exit_code=1")

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM agent_events WHERE project_id = 1"
                )).fetchone()
                assert row is not None
                assert row["event_type"] == "agent_crashed"
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_record_event_with_run_id(self, tmp_db):
        """Events can be linked to a specific swarm run."""
        from app.routes.swarm import _record_event_sync
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", "/tmp/p1"),
                )
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
                )
                await db.commit()

            _record_event_sync(1, "Claude-1", "agent_started", "pid=100", run_id=1)

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM agent_events WHERE project_id = 1"
                )).fetchone()
                assert row["run_id"] == 1
        finally:
            database.DB_PATH = original

    @pytest.mark.asyncio
    async def test_record_event_fails_silently(self, tmp_path):
        """Recording an event to a non-existent DB fails silently."""
        from app.routes.swarm import _record_event_sync
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_path / "nonexistent.db"
        try:
            # Should not raise
            _record_event_sync(999, "Claude-1", "agent_started", "pid=1")
        finally:
            database.DB_PATH = original


# ---------------------------------------------------------------------------
# GET /api/swarm/events/{project_id} Tests
# ---------------------------------------------------------------------------

class TestEventsEndpoint:
    """Test the events query endpoint with filters."""

    @pytest.mark.asyncio
    async def test_get_events_empty(self, client, created_project):
        """Returns empty list for a project with no events."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/events/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["events"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_events_404(self, client):
        """Returns 404 for nonexistent project."""
        resp = await client.get("/api/swarm/events/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_events_with_data(self, client, created_project, tmp_db):
        """Returns events that were inserted."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-1", "agent_started", "pid=100"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-2", "agent_started", "pid=101"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-1", "agent_stopped", "exit_code=0"),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["events"]) == 3

    @pytest.mark.asyncio
    async def test_get_events_filter_by_agent(self, client, created_project, tmp_db):
        """Filter events by agent name."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-1", "agent_started", "pid=100"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-2", "agent_started", "pid=101"),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}?agent=Claude-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["agent_name"] == "Claude-1"

    @pytest.mark.asyncio
    async def test_get_events_filter_by_event_type(self, client, created_project, tmp_db):
        """Filter events by event type."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-1", "agent_started", "pid=100"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                (pid, "Claude-1", "agent_crashed", "exit_code=1"),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}?event_type=agent_crashed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "agent_crashed"

    @pytest.mark.asyncio
    async def test_get_events_pagination(self, client, created_project, tmp_db):
        """Pagination with limit and offset works."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            for i in range(10):
                await db.execute(
                    "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                    (pid, "Claude-1", "output_milestone", f"line {i * 500}"),
                )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}?limit=3&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert len(data["events"]) == 3

        resp2 = await client.get(f"/api/swarm/events/{pid}?limit=3&offset=3")
        data2 = resp2.json()
        assert len(data2["events"]) == 3
        # Events should be different (different pages)
        ids1 = {e["id"] for e in data["events"]}
        ids2 = {e["id"] for e in data2["events"]}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_get_events_timestamp_filter(self, client, created_project, tmp_db):
        """Filter events by from/to timestamps."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (pid, "Claude-1", "agent_started", "early", "2026-01-01 10:00:00"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (pid, "Claude-1", "agent_stopped", "late", "2026-02-15 10:00:00"),
            )
            await db.commit()

        # Filter for events after Jan 15
        resp = await client.get(f"/api/swarm/events/{pid}", params={"from": "2026-01-15"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["detail"] == "late"

    @pytest.mark.asyncio
    async def test_get_events_newest_first(self, client, created_project, tmp_db):
        """Events are returned newest first."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (pid, "Claude-1", "agent_started", "first", "2026-01-01 10:00:00"),
            )
            await db.execute(
                "INSERT INTO agent_events (project_id, agent_name, event_type, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (pid, "Claude-2", "agent_started", "second", "2026-01-01 11:00:00"),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}")
        data = resp.json()
        assert data["events"][0]["detail"] == "second"
        assert data["events"][1]["detail"] == "first"


# ---------------------------------------------------------------------------
# Run Summary Tests
# ---------------------------------------------------------------------------

class TestRunSummary:
    """Test run summary generation and storage."""

    @pytest.mark.asyncio
    async def test_generate_summary_basic(self, tmp_db, tmp_path):
        """_generate_run_summary produces correct structure."""
        from app.routes.swarm import (
            _generate_run_summary, _agent_processes, _agent_output_buffers,
            _agent_started_at, _buffers_lock,
        )
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # Set up a project with folder containing tasks
            folder = tmp_path / "proj"
            folder.mkdir()
            (folder / "tasks").mkdir()
            (folder / "tasks" / "TASKS.md").write_text("- [x] Done\n- [ ] Todo\n")
            (folder / ".claude" / "signals").mkdir(parents=True)
            (folder / ".claude" / "signals" / "backend-ready.signal").touch()

            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", str(folder)),
                )
                await db.commit()

            # Simulate 2 agents with output
            mock_proc1 = MagicMock()
            mock_proc1.returncode = 0
            mock_proc2 = MagicMock()
            mock_proc2.returncode = 1

            _agent_processes["1:Claude-1"] = mock_proc1
            _agent_processes["1:Claude-2"] = mock_proc2

            with _buffers_lock:
                _agent_output_buffers["1:Claude-1"] = deque(["line1", "line2"])
                _agent_output_buffers["1:Claude-2"] = deque(["line3"])

            _agent_started_at["1:Claude-1"] = "2026-02-13T10:00:00"
            _agent_started_at["1:Claude-2"] = "2026-02-13T10:00:01"

            summary = await _generate_run_summary(1)
            assert summary is not None
            assert summary["agent_count"] == 2
            assert summary["total_output_lines"] == 3
            assert "Claude-1" in summary["agents"]
            assert summary["agents"]["Claude-1"]["exit_code"] == 0
            assert summary["agents"]["Claude-2"]["exit_code"] == 1
            assert "backend-ready" in summary["signals_created"]
            assert summary["tasks_completed_percent"] == 50.0
        finally:
            database.DB_PATH = original
            _agent_processes.pop("1:Claude-1", None)
            _agent_processes.pop("1:Claude-2", None)
            with _buffers_lock:
                _agent_output_buffers.pop("1:Claude-1", None)
                _agent_output_buffers.pop("1:Claude-2", None)
            _agent_started_at.pop("1:Claude-1", None)
            _agent_started_at.pop("1:Claude-2", None)

    @pytest.mark.asyncio
    async def test_summary_stored_in_swarm_run(self, client, created_project, tmp_db):
        """Summary is stored as JSON in swarm_runs.summary when supervisor completes."""
        pid = created_project["id"]
        # Insert a completed run with summary
        summary = json.dumps({
            "agent_count": 2,
            "agents": {"Claude-1": {"exit_code": 0, "output_lines": 100}},
            "total_output_lines": 200,
            "error_count": 0,
            "signals_created": [],
            "tasks_completed_percent": 75.0,
        })
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) VALUES (?, ?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 10:00:00", "2026-02-13 10:30:00", summary),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["summary"] is not None
        assert run["summary"]["agent_count"] == 2
        assert run["summary"]["total_output_lines"] == 200

    @pytest.mark.asyncio
    async def test_summary_empty_agents(self, tmp_db, tmp_path):
        """Summary handles 0 agents gracefully."""
        from app.routes.swarm import _generate_run_summary
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            folder = tmp_path / "proj2"
            folder.mkdir()
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P2", "G2", str(folder)),
                )
                await db.commit()

            summary = await _generate_run_summary(1)
            assert summary is not None
            assert summary["agent_count"] == 0
            assert summary["total_output_lines"] == 0
        finally:
            database.DB_PATH = original


# ---------------------------------------------------------------------------
# Output Search Tests
# ---------------------------------------------------------------------------

class TestOutputSearch:
    """Test output buffer search endpoint."""

    @pytest.mark.asyncio
    async def test_search_empty_buffer(self, client, created_project):
        """Searching an empty buffer returns no matches."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}/search?q=error")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 0
        assert data["matches"] == []

    @pytest.mark.asyncio
    async def test_search_finds_matches(self, client, created_project):
        """Search finds matching lines in output buffer."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([
                "[Claude-1] Starting task",
                "[Claude-1] Error: file not found",
                "[Claude-2] All tests pass",
                "[Claude-1] Error: timeout",
            ])
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=error")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 2
        assert data["query"] == "error"
        # Verify matches contain the error lines
        texts = [m["text"] for m in data["matches"]]
        assert any("file not found" in t for t in texts)
        assert any("timeout" in t for t in texts)

    @pytest.mark.asyncio
    async def test_search_context_lines(self, client, created_project):
        """Search returns context lines around matches."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([
                "[Claude-1] line 0",
                "[Claude-1] line 1",
                "[Claude-1] ERROR here",
                "[Claude-1] line 3",
                "[Claude-1] line 4",
            ])
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=ERROR&context=2")
        data = resp.json()
        assert data["total_matches"] == 1
        match = data["matches"][0]
        assert match["line_number"] == 2
        assert len(match["context_before"]) == 2
        assert len(match["context_after"]) == 2
        assert "line 1" in match["context_before"][1]
        assert "line 3" in match["context_after"][0]

    @pytest.mark.asyncio
    async def test_search_regex_pattern(self, client, created_project):
        """Search supports regex patterns."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([
                "[Claude-1] exit_code=0",
                "[Claude-2] exit_code=137",
                "[Claude-3] exit_code=0",
            ])
            _project_output_buffers[pid] = buf

        # Regex for non-zero exit codes
        resp = await client.get(f"/api/swarm/output/{pid}/search?q=exit_code=[1-9]")
        data = resp.json()
        assert data["total_matches"] == 1
        assert "137" in data["matches"][0]["text"]

    @pytest.mark.asyncio
    async def test_search_invalid_regex(self, client, created_project):
        """Invalid regex returns 400."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}/search?q=[invalid")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_per_agent_filter(self, client, created_project):
        """Search can filter by agent when using per-agent buffer."""
        pid = created_project["id"]
        from app.routes.swarm import _agent_output_buffers, _buffers_lock

        with _buffers_lock:
            key = f"{pid}:Claude-1"
            buf = deque(maxlen=5000)
            buf.extend(["error in module A", "success", "error in module B"])
            _agent_output_buffers[key] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=error&agent=Claude-1")
        data = resp.json()
        assert data["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, client, created_project):
        """Search respects the limit parameter."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([f"[Claude-1] error line {i}" for i in range(20)])
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=error&limit=5")
        data = resp.json()
        assert data["total_matches"] == 5

    @pytest.mark.asyncio
    async def test_search_agent_attribution(self, client, created_project):
        """Search extracts agent name from line prefix."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([
                "[Claude-1] found an error",
                "[Claude-2] another error",
            ])
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=error")
        data = resp.json()
        # Matches returned in buffer order (by line number ascending)
        assert data["matches"][0]["agent"] == "Claude-1"
        assert data["matches"][1]["agent"] == "Claude-2"

    @pytest.mark.asyncio
    async def test_search_404_project(self, client):
        """Search on nonexistent project returns 404."""
        resp = await client.get("/api/swarm/output/9999/search?q=test")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_search_special_characters(self, client, created_project):
        """Search handles special characters in output."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend([
                "[Claude-1] File: C:\\Users\\test\\file.py",
                "[Claude-1] regex test: foo.bar",
            ])
            _project_output_buffers[pid] = buf

        # Literal search (escaped regex)
        resp = await client.get(f"/api/swarm/output/{pid}/search", params={"q": "foo\\.bar"})
        data = resp.json()
        assert data["total_matches"] == 1


# ---------------------------------------------------------------------------
# Run Comparison Tests
# ---------------------------------------------------------------------------

class TestRunComparison:
    """Test run comparison endpoint."""

    @pytest.mark.asyncio
    async def test_compare_basic(self, client, created_project, tmp_db):
        """Compare two runs returns correct delta calculations."""
        pid = created_project["id"]
        summary_a = json.dumps({"agent_count": 4, "total_output_lines": 1000, "error_count": 2})
        summary_b = json.dumps({"agent_count": 3, "total_output_lines": 800, "error_count": 0})

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) VALUES (?, ?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 10:00:00", "2026-02-13 10:30:00", summary_a),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) VALUES (?, ?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 11:00:00", "2026-02-13 11:20:00", summary_b),
            )
            await db.commit()

        resp = await client.get("/api/swarm/runs/compare?run_a=1&run_b=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_a"]["run_id"] == 1
        assert data["run_b"]["run_id"] == 2
        assert data["run_a"]["duration_seconds"] == 1800  # 30 min
        assert data["run_b"]["duration_seconds"] == 1200  # 20 min
        assert data["duration_delta_seconds"] == -600  # 10 min faster
        assert data["agent_count_delta"] == -1  # 3 - 4
        assert data["output_lines_delta"] == -200  # 800 - 1000
        assert data["error_count_delta"] == -2  # 0 - 2

    @pytest.mark.asyncio
    async def test_compare_nonexistent_run(self, client, created_project, tmp_db):
        """Compare with nonexistent run returns 404."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                (pid, "completed"),
            )
            await db.commit()

        resp = await client.get("/api/swarm/runs/compare?run_a=1&run_b=999")
        assert resp.status_code == 404
        assert "999" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_compare_same_run(self, client, created_project, tmp_db):
        """Comparing a run to itself returns zero deltas."""
        pid = created_project["id"]
        summary = json.dumps({"agent_count": 2, "total_output_lines": 500, "error_count": 1})
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) VALUES (?, ?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 10:00:00", "2026-02-13 10:30:00", summary),
            )
            await db.commit()

        resp = await client.get("/api/swarm/runs/compare?run_a=1&run_b=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["duration_delta_seconds"] == 0
        assert data["agent_count_delta"] == 0
        assert data["output_lines_delta"] == 0
        assert data["error_count_delta"] == 0

    @pytest.mark.asyncio
    async def test_compare_no_summary(self, client, created_project, tmp_db):
        """Runs without summary use zero defaults."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) VALUES (?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 10:00:00", "2026-02-13 10:30:00"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) VALUES (?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 11:00:00", "2026-02-13 11:30:00"),
            )
            await db.commit()

        resp = await client.get("/api/swarm/runs/compare?run_a=1&run_b=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_a"]["agent_count"] == 0
        assert data["run_b"]["agent_count"] == 0
        assert data["agent_count_delta"] == 0

    @pytest.mark.asyncio
    async def test_compare_no_ended_at(self, client, created_project, tmp_db):
        """Running run (no ended_at) has duration_seconds=None."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                (pid, "running"),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) VALUES (?, ?, ?, ?)",
                (pid, "completed", "2026-02-13 10:00:00", "2026-02-13 10:30:00"),
            )
            await db.commit()

        resp = await client.get("/api/swarm/runs/compare?run_a=1&run_b=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_a"]["duration_seconds"] is None
        assert data["duration_delta_seconds"] is None


# ---------------------------------------------------------------------------
# Directive System Tests
# ---------------------------------------------------------------------------

class TestDirectiveSystem:
    """End-to-end tests for the directive system."""

    @pytest.fixture()
    def project_with_agent(self, client, mock_project_folder, project_with_folder):
        """Set up a project with a mock agent process."""
        from app.routes.swarm import _agent_processes

        pid = project_with_folder["id"]
        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # agent is alive
        mock_proc.pid = 12345
        mock_proc.stdin = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""
        _agent_processes[key] = mock_proc
        return pid, key, mock_proc

    @pytest.mark.asyncio
    async def test_send_directive_creates_file(self, client, project_with_agent, mock_project_folder):
        """POST directive creates .directive file on disk."""
        pid, key, _ = project_with_agent
        resp = await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "Focus on module X", "priority": "normal"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["priority"] == "normal"

        # Verify file exists
        directive_file = mock_project_folder / ".claude" / "directives" / "Claude-1.directive"
        assert directive_file.exists()
        content = directive_file.read_text(encoding="utf-8")
        assert "Focus on module X" in content

    @pytest.mark.asyncio
    async def test_check_pending_directive(self, client, project_with_agent, mock_project_folder):
        """GET directive shows pending status after POST."""
        pid, _, _ = project_with_agent

        # Queue a directive
        await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "Switch to testing", "priority": "normal"},
        )

        resp = await client.get(f"/api/swarm/agents/{pid}/Claude-1/directive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] is True
        assert "Switch to testing" in data["text"]
        assert data["queued_at"] is not None

    @pytest.mark.asyncio
    async def test_directive_not_pending_initially(self, client, project_with_folder):
        """GET directive returns pending=false when no directive exists."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/swarm/agents/{pid}/Claude-1/directive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] is False
        assert data["text"] is None

    @pytest.mark.asyncio
    async def test_directive_consumed(self, client, project_with_agent, mock_project_folder):
        """After agent deletes directive file, GET shows not pending."""
        pid, _, _ = project_with_agent

        await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "Do X", "priority": "normal"},
        )

        # Simulate agent consuming directive (delete file)
        directive_file = mock_project_folder / ".claude" / "directives" / "Claude-1.directive"
        assert directive_file.exists()
        directive_file.unlink()

        resp = await client.get(f"/api/swarm/agents/{pid}/Claude-1/directive")
        data = resp.json()
        assert data["pending"] is False

    @pytest.mark.asyncio
    async def test_directive_emits_event(self, client, project_with_agent, tmp_db):
        """Sending a directive records a directive_queued event."""
        pid, _, _ = project_with_agent

        await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "Focus on bugs", "priority": "normal"},
        )

        # Give async event recording time to complete
        await asyncio.sleep(0.2)

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT * FROM agent_events WHERE project_id = ? AND event_type = 'directive_queued'",
                (pid,),
            )).fetchone()
            assert row is not None
            assert row["agent_name"] == "Claude-1"

    @pytest.mark.asyncio
    async def test_directive_on_unknown_agent(self, client, project_with_folder):
        """Directive on agent that was never launched returns error."""
        pid = project_with_folder["id"]
        resp = await client.post(
            f"/api/swarm/agents/{pid}/Claude-9/directive",
            json={"text": "test", "priority": "normal"},
        )
        assert resp.status_code in (400, 404)

    @pytest.mark.asyncio
    async def test_directive_invalid_agent_name(self, client, project_with_folder):
        """Invalid agent name returns 400."""
        pid = project_with_folder["id"]
        resp = await client.post(
            f"/api/swarm/agents/{pid}/BadName/directive",
            json={"text": "test", "priority": "normal"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_directive_project_not_found(self, client):
        """Directive on nonexistent project returns 404."""
        resp = await client.post(
            "/api/swarm/agents/9999/Claude-1/directive",
            json={"text": "test", "priority": "normal"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_directive_invalid_priority(self, client, project_with_agent):
        """Invalid priority value returns 422."""
        pid, _, _ = project_with_agent
        resp = await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "test", "priority": "critical"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_directive_sanitizes_text(self, client, project_with_agent, mock_project_folder):
        """Directive text is HTML-sanitized."""
        pid, _, _ = project_with_agent
        resp = await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "<script>alert('xss')</script>", "priority": "normal"},
        )
        assert resp.status_code == 200

        directive_file = mock_project_folder / ".claude" / "directives" / "Claude-1.directive"
        content = directive_file.read_text(encoding="utf-8")
        assert "<script>" not in content
        assert "&lt;script&gt;" in content

    @pytest.mark.asyncio
    async def test_urgent_directive_stops_agent(self, client, project_with_agent, mock_project_folder):
        """Urgent directive terminates and attempts to restart the agent."""
        pid, key, mock_proc = project_with_agent

        with patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]), \
             patch("subprocess.Popen") as mock_popen:
            new_proc = MagicMock()
            new_proc.pid = 99999
            new_proc.poll.return_value = None
            new_proc.stdout = MagicMock()
            new_proc.stdout.readline.return_value = b""
            new_proc.stderr = MagicMock()
            new_proc.stderr.readline.return_value = b""
            mock_popen.return_value = new_proc

            resp = await client.post(
                f"/api/swarm/agents/{pid}/Claude-1/directive",
                json={"text": "URGENT: switch to debugging", "priority": "urgent"},
            )
            assert resp.status_code == 200

            # Original proc should have been terminated
            mock_proc.terminate.assert_called()

    @pytest.mark.asyncio
    async def test_directive_cleanup_on_stop(self, client, project_with_agent, mock_project_folder):
        """Directive files are cleaned up when swarm is stopped (or can be)."""
        pid, _, _ = project_with_agent

        await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "test directive", "priority": "normal"},
        )

        directive_file = mock_project_folder / ".claude" / "directives" / "Claude-1.directive"
        assert directive_file.exists()

        # Stopping swarm cleans up agent processes; directive files persist
        # (This is expected — directives are project-level artifacts)
        # But project delete should cascade (returns 204 No Content)
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Prompt Modification Tests
# ---------------------------------------------------------------------------

class TestPromptModification:
    """Test prompt hot-swap endpoint."""

    @pytest.mark.asyncio
    async def test_update_prompt_basic(self, client, project_with_folder, mock_project_folder):
        """PUT prompt updates file and returns old prompt."""
        pid = project_with_folder["id"]
        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-1/prompt",
            json={"prompt": "New prompt for Claude-1 with updated instructions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["agent"] == "Claude-1"
        assert "Mock prompt for Claude-1" in data["old_prompt"]

        # Verify file was updated
        prompt_file = mock_project_folder / ".claude" / "prompts" / "Claude-1.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "New prompt" in content or "updated instructions" in content

    @pytest.mark.asyncio
    async def test_update_prompt_returns_old_content(self, client, project_with_folder, mock_project_folder):
        """Old prompt content is returned for undo capability."""
        pid = project_with_folder["id"]
        # Write a known prompt
        prompt_file = mock_project_folder / ".claude" / "prompts" / "Claude-2.txt"
        prompt_file.write_text("Original prompt text", encoding="utf-8")

        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-2/prompt",
            json={"prompt": "Replacement prompt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_prompt"] == "Original prompt text"

    @pytest.mark.asyncio
    async def test_update_prompt_nonexistent_agent(self, client, project_with_folder, mock_project_folder):
        """PUT on agent with no prompt file returns 404."""
        pid = project_with_folder["id"]
        # Delete a prompt file
        pf = mock_project_folder / ".claude" / "prompts" / "Claude-3.txt"
        if pf.exists():
            pf.unlink()

        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-3/prompt",
            json={"prompt": "test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_prompt_empty_body(self, client, project_with_folder):
        """Empty prompt returns 422 (Pydantic min_length=1 validation)."""
        pid = project_with_folder["id"]
        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-1/prompt",
            json={"prompt": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_prompt_invalid_agent_name(self, client, project_with_folder):
        """Invalid agent name returns 400."""
        pid = project_with_folder["id"]
        resp = await client.put(
            f"/api/swarm/agents/{pid}/InvalidName/prompt",
            json={"prompt": "test prompt"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_prompt_project_not_found(self, client):
        """PUT on nonexistent project returns 404."""
        resp = await client.put(
            "/api/swarm/agents/9999/Claude-1/prompt",
            json={"prompt": "test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_prompt_emits_event(self, client, project_with_folder, tmp_db):
        """Prompt update records a prompt_modified event."""
        pid = project_with_folder["id"]
        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-1/prompt",
            json={"prompt": "Updated prompt content"},
        )
        assert resp.status_code == 200

        # Give async event recording time to complete
        await asyncio.sleep(0.2)

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT * FROM agent_events WHERE project_id = ? AND event_type = 'prompt_modified'",
                (pid,),
            )).fetchone()
            assert row is not None
            assert row["agent_name"] == "Claude-1"

    @pytest.mark.asyncio
    async def test_update_prompt_then_verify_restart_reads_new(
        self, client, project_with_folder, mock_project_folder, mock_launch_deps,
    ):
        """After prompt update, restart agent would read the new prompt."""
        pid = project_with_folder["id"]

        # Update the prompt
        new_prompt = "Completely new instructions for Claude-1"
        await client.put(
            f"/api/swarm/agents/{pid}/Claude-1/prompt",
            json={"prompt": new_prompt},
        )

        # Verify the file contains the new prompt (sanitized)
        prompt_file = mock_project_folder / ".claude" / "prompts" / "Claude-1.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "new instructions" in content or "Completely" in content


# ---------------------------------------------------------------------------
# Event Emission During Swarm Lifecycle (Integration)
# ---------------------------------------------------------------------------

class TestEventEmissionIntegration:
    """Test that launching/stopping agents emits correct events."""

    @pytest.mark.asyncio
    async def test_launch_emits_agent_started_events(
        self, client, project_with_folder, mock_launch_deps, tmp_db,
    ):
        """Launching a swarm records agent_started events for each agent."""
        pid = project_with_folder["id"]

        mock_proc = MagicMock()
        mock_proc.pid = 1000
        mock_proc.poll.return_value = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""

        with patch("subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 2,
                "max_phases": 3,
            })
            assert resp.status_code == 200

        # Give event recording threads time
        await asyncio.sleep(0.3)

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                "SELECT * FROM agent_events WHERE project_id = ? AND event_type = 'agent_started'",
                (pid,),
            )).fetchall()
            # At least 1 agent_started event per launched agent
            assert len(rows) >= 2
            agents_started = {r["agent_name"] for r in rows}
            assert "Claude-1" in agents_started
            assert "Claude-2" in agents_started

    @pytest.mark.asyncio
    async def test_milestone_events_at_500_lines(self, tmp_db, tmp_path):
        """Output milestone event is emitted at 500-line intervals."""
        from app.routes.swarm import (
            _drain_agent_stream, _agent_output_buffers, _agent_log_files,
            _buffers_lock, _agent_line_counts, _project_output_buffers,
        )
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", str(tmp_path)),
                )
                await db.commit()

            # Clear any leftover state
            _agent_line_counts.clear()

            # Create a mock stream that produces exactly 501 lines
            lines = [b'{"type":"assistant","message":{"content":[{"type":"text","text":"line %d"}]}}\n' % i
                     for i in range(501)]
            lines.append(b"")  # EOF sentinel

            mock_stream = MagicMock()
            mock_stream.readline.side_effect = lines

            stop_event = threading.Event()
            thread = threading.Thread(
                target=_drain_agent_stream,
                args=(1, "Claude-1", mock_stream, "stdout", stop_event),
            )
            thread.start()
            thread.join(timeout=10)

            # Check that output_milestone event was recorded
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                rows = await (await db.execute(
                    "SELECT * FROM agent_events WHERE project_id = 1 AND event_type = 'output_milestone'"
                )).fetchall()
                assert len(rows) >= 1  # At least one milestone at 500 lines
                assert "500" in rows[0]["detail"]
        finally:
            database.DB_PATH = original
            _agent_line_counts.clear()
            with _buffers_lock:
                _agent_output_buffers.pop("1:Claude-1", None)
                _project_output_buffers.pop(1, None)


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case and error handling tests."""

    @pytest.mark.asyncio
    async def test_events_endpoint_large_dataset(self, client, created_project, tmp_db):
        """Events endpoint handles large numbers of events."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            for i in range(200):
                await db.execute(
                    "INSERT INTO agent_events (project_id, agent_name, event_type, detail) VALUES (?, ?, ?, ?)",
                    (pid, f"Claude-{(i % 4) + 1}", "output_milestone", f"line {i * 500}"),
                )
            await db.commit()

        resp = await client.get(f"/api/swarm/events/{pid}?limit=50")
        data = resp.json()
        assert data["total"] == 200
        assert len(data["events"]) == 50

    @pytest.mark.asyncio
    async def test_search_no_q_parameter(self, client, created_project):
        """Search without q parameter returns 422."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}/search")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_compare_both_missing(self, client):
        """Compare with both run IDs missing returns 422."""
        resp = await client.get("/api/swarm/runs/compare")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_directive_empty_text(self, client, project_with_folder):
        """Directive with empty text returns 422."""
        pid = project_with_folder["id"]
        from app.routes.swarm import _agent_processes
        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        _agent_processes[key] = mock_proc

        resp = await client.post(
            f"/api/swarm/agents/{pid}/Claude-1/directive",
            json={"text": "", "priority": "normal"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_prompt_too_long(self, client, project_with_folder):
        """Prompt exceeding max_length returns 422 (Pydantic validation)."""
        pid = project_with_folder["id"]
        resp = await client.put(
            f"/api/swarm/agents/{pid}/Claude-1/prompt",
            json={"prompt": "x" * 200000},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_context_zero(self, client, created_project):
        """Search with context=0 returns no context lines."""
        pid = created_project["id"]
        from app.routes.swarm import _project_output_buffers, _buffers_lock

        with _buffers_lock:
            buf = deque(maxlen=5000)
            buf.extend(["before", "match_here", "after"])
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/swarm/output/{pid}/search?q=match_here&context=0")
        data = resp.json()
        assert data["total_matches"] == 1
        assert data["matches"][0]["context_before"] == []
        assert data["matches"][0]["context_after"] == []

    @pytest.mark.asyncio
    async def test_get_current_run_id_helper(self, tmp_db):
        """_get_current_run_id returns the running run ID."""
        from app.routes.swarm import _get_current_run_id
        from app import database

        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            async with aiosqlite.connect(tmp_db) as db:
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path) VALUES (?, ?, ?)",
                    ("P1", "G1", "/tmp/p1"),
                )
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')",
                )
                await db.commit()

            run_id = _get_current_run_id(1)
            assert run_id == 1

            # No running run
            run_id2 = _get_current_run_id(999)
            assert run_id2 is None
        finally:
            database.DB_PATH = original
