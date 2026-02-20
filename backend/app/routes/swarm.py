import asyncio
import itertools
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field
import aiosqlite

from .. import database
from ..database import get_db
from .. import config
from ..sanitize import sanitize_string
from ..models.responses import (
    SwarmLaunchOut, SwarmStopOut, SwarmInputOut, SwarmStatusOut,
    SwarmOutputOut, SwarmHistoryOut, ErrorDetail,
    AgentStatusOut, AgentsListOut, AgentStopOut,
    AgentMetricsOut, SwarmRunAnnotationOut,
    AgentEventOut, AgentEventsListOut,
    OutputSearchOut, RunComparisonOut,
    DirectiveOut, DirectiveStatusOut, PromptUpdateOut,
    QuotaOut, QuotaConfig, QuotaUsage,
    ProjectHealthOut, ProjectHealthScore, HealthTrendsOut,
    CheckpointOut, CheckpointsListOut,
    AgentLogLinesOut, OutputTailOut,
)
from .webhooks import emit_webhook_event
from .websocket import manager as ws_manager

# psutil is lazy-loaded on first use to speed up startup
_psutil = None
_PSUTIL_AVAILABLE = True


def _get_psutil():
    """Lazy-load psutil on first use."""
    global _psutil, _PSUTIL_AVAILABLE
    if _psutil is None:
        try:
            import psutil
            _psutil = psutil
        except ImportError:
            _PSUTIL_AVAILABLE = False
    return _psutil

logger = logging.getLogger("latent.swarm")

# Configurable output buffer size (lines per agent/project)
_MAX_OUTPUT_LINES = int(os.environ.get("LU_OUTPUT_BUFFER_LINES", "5000"))
# Truncate individual lines longer than this to prevent memory abuse
_MAX_LINE_LENGTH = 4000


def _pid_alive(pid: int | None) -> bool:
    """Check if a process with the given PID is still running."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
        return True
    except (OSError, ProcessLookupError):
        return False


router = APIRouter(prefix="/api/swarm", tags=["swarm"])

# ---------------------------------------------------------------------------
# Per-agent process tracking
# Keys use "{project_id}:{agent_name}" (e.g. "7:Claude-1")
# ---------------------------------------------------------------------------
_agent_processes: dict[str, subprocess.Popen] = {}
_agent_output_buffers: dict[str, deque[str]] = {}
_agent_drain_threads: dict[str, list[threading.Thread]] = {}
_agent_drain_events: dict[str, threading.Event] = {}
_agent_started_at: dict[str, str] = {}  # ISO timestamp when agent was spawned
_agent_log_files: dict[str, Path] = {}  # key -> log file path for persistence

# Combined per-project output (interleaved with [AgentName] prefix)
_project_output_buffers: dict[int, deque[str]] = {}

# Supervisor tasks that auto-detect when all agents finish
_supervisor_tasks: dict[int, asyncio.Task] = {}

# Track last output timestamp per project for auto-stop feature
_last_output_at: dict[int, float] = {}

_buffers_lock = threading.Lock()

# Per-agent output line counters for milestone tracking (reset on launch)
_agent_line_counts: dict[str, int] = {}

# Track known directive files per project for consumed-detection
_known_directives: dict[int, set[str]] = {}

# Per-project locks to serialize launch/stop operations and prevent race conditions
_project_locks: dict[int, asyncio.Lock] = {}

# Resource quota tracking: {project_id: {"agent_count": N, "restart_counts": {"Claude-1": M, ...}, "started_at": float}}
_project_resource_usage: dict[int, dict] = {}

# Circuit breaker per agent: prevents crash-loop restarts
# Key: "{project_id}:{agent_name}", Value: {"state": str, "failures": list[(float, int)], "opened_at": float|None, "probe_started_at": float|None}
_circuit_breakers: dict[str, dict] = {}

_CB_DEFAULT_MAX_FAILURES = 3
_CB_DEFAULT_WINDOW_SECONDS = 300
_CB_DEFAULT_RECOVERY_SECONDS = 60


def _get_circuit_breaker(key: str) -> dict:
    """Get or create circuit breaker state for an agent."""
    if key not in _circuit_breakers:
        _circuit_breakers[key] = {
            "state": "closed",
            "failures": [],  # list of (timestamp, exit_code)
            "opened_at": None,
            "probe_started_at": None,
        }
    return _circuit_breakers[key]


def _cb_record_failure(key: str, exit_code: int, max_failures: int, window_seconds: int):
    """Record an agent failure. Opens circuit if threshold exceeded."""
    cb = _get_circuit_breaker(key)
    now = time.time()
    cb["failures"].append((now, exit_code))
    # Prune failures outside the window
    cutoff = now - window_seconds
    cb["failures"] = [(ts, ec) for ts, ec in cb["failures"] if ts >= cutoff]

    if cb["state"] == "half-open":
        # Probe failed — re-open circuit
        cb["state"] = "open"
        cb["opened_at"] = now
        cb["probe_started_at"] = None
        return "reopened"

    if len(cb["failures"]) >= max_failures:
        cb["state"] = "open"
        cb["opened_at"] = now
        return "opened"

    return None


def _cb_check_restart_allowed(
    key: str, max_failures: int, window_seconds: int, recovery_seconds: int,
) -> tuple[bool, str]:
    """Check if circuit breaker allows a restart. Returns (allowed, reason)."""
    cb = _get_circuit_breaker(key)
    now = time.time()

    if cb["state"] == "closed":
        return True, "closed"

    if cb["state"] == "open":
        # Check if recovery period has elapsed → transition to half-open
        if cb["opened_at"] and (now - cb["opened_at"]) >= recovery_seconds:
            cb["state"] = "half-open"
            return True, "half-open"
        elapsed = int(now - (cb["opened_at"] or now))
        remaining = recovery_seconds - elapsed
        return False, f"Circuit breaker open: {len(cb['failures'])} failures in last {window_seconds}s (retry in {remaining}s)"

    if cb["state"] == "half-open":
        # Already in half-open and a probe is pending — don't allow another
        if cb.get("probe_started_at"):
            return False, "Circuit breaker half-open: probe restart in progress"
        return True, "half-open"

    return True, "unknown"


def _cb_record_probe_start(key: str):
    """Mark that a half-open probe restart has begun."""
    cb = _get_circuit_breaker(key)
    cb["probe_started_at"] = time.time()


def _cb_record_probe_success(key: str):
    """Probe restart succeeded (agent ran > 30s). Close circuit."""
    cb = _get_circuit_breaker(key)
    cb["state"] = "closed"
    cb["failures"] = []
    cb["opened_at"] = None
    cb["probe_started_at"] = None


def _record_event_sync(
    project_id: int, agent_name: str, event_type: str, detail: str = "",
    run_id: int | None = None,
):
    """Record an agent event to the database using synchronous sqlite3.

    Safe to call from drain threads (non-async context). Uses a separate
    connection per call to avoid thread-safety issues.
    """
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(database.DB_PATH), timeout=5)
        try:
            conn.execute(
                "INSERT INTO agent_events (project_id, run_id, agent_name, event_type, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, run_id, agent_name, event_type, detail),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to record event %s for %s", event_type, agent_name, exc_info=True)


async def _record_event_async(
    project_id: int, agent_name: str, event_type: str, detail: str = "",
    run_id: int | None = None,
):
    """Record an agent event from async context (wraps sync call in thread)."""
    await asyncio.to_thread(
        _record_event_sync, project_id, agent_name, event_type, detail, run_id,
    )


def _get_current_run_id(project_id: int) -> int | None:
    """Get the current running swarm_run ID for a project (sync, for drain threads)."""
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(database.DB_PATH), timeout=5)
        try:
            cur = conn.execute(
                "SELECT id FROM swarm_runs WHERE project_id = ? AND status = 'running' "
                "ORDER BY id DESC LIMIT 1",
                (project_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None


def _get_project_lock(project_id: int) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific project."""
    return _project_locks.setdefault(project_id, asyncio.Lock())


# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------

async def _get_project_quota(project_id: int) -> dict:
    """Load resource quota config from project config JSON. Returns dict with quota fields."""
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT config FROM projects WHERE id = ?", (project_id,)
            )).fetchone()
            if row and row["config"]:
                cfg = json.loads(row["config"])
                return {
                    "max_agents_concurrent": cfg.get("max_agents_concurrent"),
                    "max_duration_hours": cfg.get("max_duration_hours"),
                    "max_restarts_per_agent": cfg.get("max_restarts_per_agent"),
                    "circuit_breaker_max_failures": cfg.get("circuit_breaker_max_failures"),
                    "circuit_breaker_window_seconds": cfg.get("circuit_breaker_window_seconds"),
                    "circuit_breaker_recovery_seconds": cfg.get("circuit_breaker_recovery_seconds"),
                }
    except Exception:
        pass
    return {
        "max_agents_concurrent": None, "max_duration_hours": None,
        "max_restarts_per_agent": None,
        "circuit_breaker_max_failures": None,
        "circuit_breaker_window_seconds": None,
        "circuit_breaker_recovery_seconds": None,
    }


# Checkpoint batching: accumulate and flush periodically to reduce DB writes
_checkpoint_batch: list[tuple] = []  # [(project_id, run_id, agent_name, type, data_json)]
_checkpoint_batch_lock = threading.Lock()
_CHECKPOINT_BATCH_SIZE = 20  # Flush when batch reaches this size

# Per-agent cooldown: prevent flood from verbose agents (30s between same checkpoint type)
_checkpoint_cooldowns: dict[str, float] = {}  # "project:agent:type" -> last_write_time
_CHECKPOINT_COOLDOWN_SECONDS = 30

# Cache run_id per project to avoid DB query on every checkpoint
_current_run_ids: dict[int, int | None] = {}


def _flush_checkpoints():
    """Batch-insert accumulated checkpoints via single executemany()."""
    with _checkpoint_batch_lock:
        if not _checkpoint_batch:
            return
        batch = list(_checkpoint_batch)
        _checkpoint_batch.clear()

    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(database.DB_PATH), timeout=5)
        try:
            conn.executemany(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, ?, ?, ?)",
                batch,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.warning("Failed to flush %d checkpoints", len(batch), exc_info=True)


def _record_checkpoint_sync(
    project_id: int, run_id: int | None, agent_name: str,
    checkpoint_type: str, data: dict,
):
    """Batch-record an agent checkpoint. Flushes when batch is full."""
    # Resolve run_id from cache or DB before acquiring the lock
    if run_id is None:
        run_id = _current_run_ids.get(project_id)
        if run_id is None:
            run_id = _get_current_run_id(project_id)
            if run_id is not None:
                _current_run_ids[project_id] = run_id

    # Cooldown check + batch append under lock for thread safety
    with _checkpoint_batch_lock:
        cooldown_key = f"{project_id}:{agent_name}:{checkpoint_type}"
        now = time.time()
        last_write = _checkpoint_cooldowns.get(cooldown_key, 0)
        if now - last_write < _CHECKPOINT_COOLDOWN_SECONDS:
            return  # Skip — too frequent
        _checkpoint_cooldowns[cooldown_key] = now
        _checkpoint_batch.append((project_id, run_id, agent_name, checkpoint_type, json.dumps(data)))
        should_flush = len(_checkpoint_batch) >= _CHECKPOINT_BATCH_SIZE

    if should_flush:
        _flush_checkpoints()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_NAME_RE = re.compile(r'^Claude-[0-9]{1,2}$')


def _validate_agent_name(name: str) -> bool:
    """Validate agent name matches expected format (Claude-1 through Claude-16)."""
    return bool(_AGENT_NAME_RE.match(name))


def _agent_key(project_id: int, agent_name: str) -> str:
    return f"{project_id}:{agent_name}"


def _project_agent_keys(project_id: int) -> list[str]:
    prefix = f"{project_id}:"
    return [k for k in list(_agent_processes.keys()) if k.startswith(prefix)]


def _any_agent_alive(project_id: int) -> bool:
    """Check if any agent subprocess for a project is still running."""
    for key in _project_agent_keys(project_id):
        proc = _agent_processes.get(key)
        if proc and proc.poll() is None:
            return True
    return False


def _find_claude_cmd() -> list[str]:
    """Find the claude CLI and return the command list to invoke it.

    On Windows, .cmd wrappers go through cmd.exe which eats piped stdout.
    We resolve the underlying node + cli.js path for direct invocation.
    Returns a list like ["node", "/path/to/cli.js"] or ["claude"].
    """
    cmd_path = shutil.which("claude")
    if not cmd_path:
        for path in [
            os.path.expanduser("~\\AppData\\Roaming\\npm\\claude.cmd"),
            os.path.expanduser("~\\AppData\\Roaming\\npm\\claude"),
        ]:
            if os.path.isfile(path):
                cmd_path = path
                break

    if not cmd_path:
        raise FileNotFoundError("claude CLI not found in PATH or common locations")

    # On Windows, resolve .cmd wrapper to node + cli.js for proper pipe handling
    if cmd_path.lower().endswith(".cmd"):
        npm_dir = os.path.dirname(cmd_path)
        cli_js = os.path.join(npm_dir, "node_modules", "@anthropic-ai", "claude-code", "cli.js")
        if os.path.isfile(cli_js):
            node = shutil.which("node") or "node"
            return [node, cli_js]

    return [cmd_path]


def _run_setup_only(
    folder: Path, swarm_script: Path, agent_count: int, max_phases: int,
) -> subprocess.CompletedProcess:
    """Run swarm.ps1 -SetupOnly synchronously. Returns CompletedProcess."""
    args = [
        "powershell", "-ExecutionPolicy", "Bypass", "-File", str(swarm_script),
        "-Resume", "-NoConfirm", "-SetupOnly",
        "-AgentCount", str(agent_count),
        "-MaxPhases", str(max_phases),
    ]
    return subprocess.run(
        args, cwd=str(folder), capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _terminate_project_agents(project_id: int):
    """Terminate agent processes and drain threads for a project.

    Does NOT cancel the supervisor task or clear project output buffers.
    Use this from within the supervisor loop itself to avoid self-cancellation.
    """
    keys = _project_agent_keys(project_id)
    for key in keys:
        # Signal drain threads to stop
        evt = _agent_drain_events.pop(key, None)
        if evt:
            evt.set()
        # Terminate process FIRST — this closes stdout/stderr which unblocks
        # drain threads stuck on readline(). Must happen before thread join.
        proc = _agent_processes.pop(key, None)
        if proc:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        # Now join drain threads — they should exit quickly since streams are closed
        threads = _agent_drain_threads.pop(key, None)
        if threads:
            for t in threads:
                t.join(timeout=3)
        # Clear agent metadata and buffer (keep log files on disk for review)
        _agent_started_at.pop(key, None)
        _agent_log_files.pop(key, None)
        _agent_line_counts.pop(key, None)
        with _buffers_lock:
            _agent_output_buffers.pop(key, None)


def _cleanup_project_agents(project_id: int):
    """Full cleanup: terminate agents, clear buffers, cancel supervisor."""
    _terminate_project_agents(project_id)
    # Clear project buffer, auto-stop timer, directive tracking, resource usage, and run ID cache
    with _buffers_lock:
        _project_output_buffers.pop(project_id, None)
    _last_output_at.pop(project_id, None)
    _known_directives.pop(project_id, None)
    _project_resource_usage.pop(project_id, None)
    _current_run_ids.pop(project_id, None)
    # Clear circuit breakers for this project's agents
    cb_keys = [k for k in _circuit_breakers if k.startswith(f"{project_id}:")]
    for k in cb_keys:
        _circuit_breakers.pop(k, None)
    # Note: _project_locks is NOT cleaned here because the caller (launch/stop)
    # may still hold the lock. Locks are cleaned on project deletion only.
    # Cancel supervisor
    task = _supervisor_tasks.pop(project_id, None)
    if task and not task.done():
        task.cancel()


async def cancel_drain_tasks(project_id: int | None = None):
    """Clean up agent processes. If project_id is None, clean up all.

    Runs blocking cleanup (process termination, thread joins) in a thread
    to avoid blocking the event loop.
    """
    if project_id is not None:
        await asyncio.to_thread(_cleanup_project_agents, project_id)
        return
    project_ids = set()
    for key in list(_agent_processes.keys()):
        project_ids.add(int(key.split(":")[0]))
    for pid in project_ids:
        await asyncio.to_thread(_cleanup_project_agents, pid)


def _cleanup_stale_tracking_dicts():
    """Clear all module-level tracking dicts. Called during server shutdown."""
    # Flush any pending checkpoints before clearing
    _flush_checkpoints()
    _agent_processes.clear()
    _agent_output_buffers.clear()
    _agent_drain_threads.clear()
    _agent_drain_events.clear()
    _agent_started_at.clear()
    _agent_log_files.clear()
    _project_output_buffers.clear()
    _supervisor_tasks.clear()
    _last_output_at.clear()
    _agent_line_counts.clear()
    _known_directives.clear()
    _project_locks.clear()
    _project_resource_usage.clear()
    _checkpoint_cooldowns.clear()
    _current_run_ids.clear()
    _circuit_breakers.clear()
    with _checkpoint_batch_lock:
        _checkpoint_batch.clear()
    logger.info("All tracking dicts cleared on shutdown")


def _clean_project_artifacts(folder: Path):
    """Remove stale signal/heartbeat/handoff/log files before fresh launch.

    Ensures new agents start in a clean environment without leftover state
    from previous swarm runs in the same project folder.
    """
    for pattern, subdir in [
        ("*.signal", ".claude/signals"),
        ("*.heartbeat", ".claude/heartbeats"),
        ("*.md", ".claude/handoffs"),
    ]:
        target = folder / subdir
        if target.is_dir():
            for f in target.glob(pattern):
                try:
                    f.unlink()
                except OSError:
                    pass
    # Clear old log files so watcher doesn't re-broadcast stale output
    log_dir = folder / "logs"
    if log_dir.is_dir():
        for f in log_dir.glob("*.log"):
            try:
                f.unlink()
            except OSError:
                pass
    logger.info("Cleaned stale artifacts in %s", folder)


# ---------------------------------------------------------------------------
# Drain thread — reads stdout/stderr from one agent subprocess
# ---------------------------------------------------------------------------

def _parse_stream_json_line(raw: str) -> str | None:
    """Extract human-readable text from a stream-json line.

    Claude --output-format stream-json emits one JSON object per line.
    We extract assistant text, tool usage, and result messages.
    Returns None for events we want to skip (keepalives, metadata).
    """
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Not JSON — return raw (stderr or non-json output)
        return raw

    msg_type = obj.get("type", "")

    # --- Streaming deltas (non-verbose or future use) ---
    if msg_type == "content_block_delta":
        delta = obj.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text", "")
    elif msg_type == "content_block_start":
        cb = obj.get("content_block", {})
        if cb.get("type") == "tool_use":
            return f"[tool] {cb.get('name', '?')}()"

    # --- Verbose mode: complete assistant messages ---
    elif msg_type == "assistant":
        message = obj.get("message", {})
        content = message.get("content", [])
        parts = []
        for block in content:
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    parts.append(text)
            elif block.get("type") == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                # Show compact tool call summary
                if isinstance(inp, dict):
                    summary = ", ".join(f"{k}=..." for k in list(inp.keys())[:3])
                    parts.append(f"[tool] {name}({summary})")
                else:
                    parts.append(f"[tool] {name}()")
        return " ".join(parts) if parts else None

    # --- Verbose mode: user messages (tool results) ---
    elif msg_type == "user":
        # Tool results — show abbreviated summaries
        content = obj.get("content", [])
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result":
                    result = block.get("content", "")
                    if isinstance(result, str) and len(result) > 100:
                        return f"[result] {result[:100]}..."
                    elif result:
                        return f"[result] {result}"
        return None  # Skip empty user messages

    # --- Final result ---
    elif msg_type == "result":
        result_text = obj.get("result", "")
        if result_text:
            return f"[done] {result_text[:200]}"

    # --- System events (init, hooks) — skip most ---
    elif msg_type == "system":
        subtype = obj.get("subtype", "")
        if subtype == "init":
            return "[system] Agent initialized"
        return None  # Skip hook events, etc.

    return None


_LOG_ROTATE_KEEP = config.OUTPUT_LOG_ROTATE_KEEP


def _rotate_log_file(log_path: Path, log_fh):
    """Rotate a log file when it exceeds the configured max size.

    Closes the current file handle, cascades existing rotations (.1 -> .2 -> .3),
    renames current -> .1, and returns a new file handle for the original path.
    Keeps up to LU_OUTPUT_LOG_ROTATE_KEEP rotations (default 3).
    """
    try:
        log_fh.close()
    except OSError:
        pass
    try:
        # Cascade existing rotations: delete oldest, shift others up
        base = str(log_path)
        for i in range(_LOG_ROTATE_KEEP, 0, -1):
            src = Path(f"{base}.{i}")
            if i == _LOG_ROTATE_KEEP:
                # Delete the oldest rotation
                if src.exists():
                    src.unlink()
            else:
                # Rename .N -> .N+1
                dst = Path(f"{base}.{i + 1}")
                if src.exists():
                    src.rename(dst)
        # Current -> .1
        log_path.rename(Path(f"{base}.1"))
        logger.debug("Rotated log %s (keeping %d rotations)", log_path.name, _LOG_ROTATE_KEEP)
    except OSError:
        logger.debug("Failed to rotate log %s", log_path, exc_info=True)
    try:
        return open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        logger.warning("Failed to reopen log file %s after rotation", log_path, exc_info=True)
        return None


def _drain_agent_stream(
    project_id: int, agent_name: str, stream, label: str,
    stop_event: threading.Event,
):
    """Read lines from an agent subprocess stream in a background thread.

    stdout carries stream-json (one JSON object per line).
    stderr carries plain text (tool output, warnings, errors).
    Output is written both to in-memory buffers and to a persistent log file
    in the project's logs/ directory for crash recovery. Log files are rotated
    when they exceed LU_OUTPUT_LOG_MAX_MB.
    """
    key = _agent_key(project_id, agent_name)
    is_stdout = label == "stdout"
    log_path = _agent_log_files.get(key)
    log_fh = None
    if log_path:
        try:
            log_fh = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
        except OSError:
            logger.debug("Failed to open log file %s for writing", log_path, exc_info=True)

    max_log_bytes = config.OUTPUT_LOG_MAX_MB * 1024 * 1024
    lines_since_check = 0
    try:
        for line in iter(stream.readline, b""):
            if stop_event.is_set():
                break
            raw = line.decode("utf-8", errors="replace").rstrip()
            if not raw:
                continue

            if is_stdout:
                text = _parse_stream_json_line(raw)
                if text is None:
                    continue  # Skip uninteresting events
            else:
                text = raw

            # Truncate very long lines to prevent memory abuse
            if len(text) > _MAX_LINE_LENGTH:
                text = text[:_MAX_LINE_LENGTH] + "... [truncated]"

            with _buffers_lock:
                # Per-agent buffer (deque auto-trims oldest entries)
                agent_buf = _agent_output_buffers.setdefault(
                    key, deque(maxlen=_MAX_OUTPUT_LINES),
                )
                agent_buf.append(text)
                # Combined project buffer (with agent prefix)
                proj_buf = _project_output_buffers.setdefault(
                    project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                )
                proj_buf.append(f"[{agent_name}] {text}")
                # Update last output timestamp for auto-stop tracking
                _last_output_at[project_id] = time.time()

                # Track output milestone events (every 500 lines)
                _agent_line_counts[key] = _agent_line_counts.get(key, 0) + 1
                line_count = _agent_line_counts[key]

            if line_count % 500 == 0:
                _record_event_sync(
                    project_id, agent_name, "output_milestone",
                    f"Reached {line_count} output lines",
                )

            # Emit checkpoints on task completion and error patterns
            _lower = text.lower()
            if "[done]" in _lower or "task complete" in _lower or "- [x]" in text:
                # Get last 5 lines from agent buffer for context
                with _buffers_lock:
                    abuf = _agent_output_buffers.get(key, deque())
                    last_lines = list(itertools.islice(reversed(abuf), 5))[::-1]
                _record_checkpoint_sync(
                    project_id, _get_current_run_id(project_id), agent_name,
                    "task_complete",
                    {"output_lines": line_count, "last_lines": last_lines, "elapsed_seconds": None},
                )
            elif "error" in _lower or "traceback" in _lower or "exception" in _lower:
                with _buffers_lock:
                    abuf = _agent_output_buffers.get(key, deque())
                    last_lines = list(itertools.islice(reversed(abuf), 5))[::-1]
                _record_checkpoint_sync(
                    project_id, _get_current_run_id(project_id), agent_name,
                    "error",
                    {"output_lines": line_count, "last_lines": last_lines, "text": text[:500]},
                )

            # Persist to log file for crash recovery
            if log_fh:
                try:
                    log_fh.write(text + "\n")
                except OSError:
                    pass  # Non-critical — memory buffer is primary

                # Check for log rotation every 100 lines (avoid stat() on every write)
                lines_since_check += 1
                if max_log_bytes > 0 and lines_since_check >= 100 and log_path:
                    lines_since_check = 0
                    try:
                        if log_path.exists() and log_path.stat().st_size > max_log_bytes:
                            log_fh = _rotate_log_file(log_path, log_fh)
                    except OSError:
                        pass
    except Exception:
        logger.error("_drain_agent_stream failed for %s [%s]", key, label, exc_info=True)
    finally:
        if log_fh:
            try:
                log_fh.close()
            except OSError:
                pass
        try:
            stream.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Supervisor — background task that auto-completes the swarm run
# ---------------------------------------------------------------------------

async def _get_project_auto_stop(project_id: int) -> int:
    """Get auto-stop minutes from project config, falling back to global default."""
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT config FROM projects WHERE id = ?", (project_id,)
            )).fetchone()
            if row and row["config"]:
                cfg = json.loads(row["config"])
                val = cfg.get("auto_stop_minutes")
                if val is not None and val > 0:
                    return val
    except Exception:
        pass
    return config.AUTO_STOP_MINUTES


async def _get_project_auto_queue(project_id: int) -> tuple[bool, int]:
    """Get auto-queue settings from project config.

    Returns (enabled: bool, delay_seconds: int).
    Default delay is 30 seconds if not specified.
    """
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT config FROM projects WHERE id = ?", (project_id,)
            )).fetchone()
            if row and row["config"]:
                cfg = json.loads(row["config"])
                enabled = cfg.get("auto_queue", False)
                delay = cfg.get("auto_queue_delay_seconds", 30)
                return (bool(enabled), max(5, min(300, int(delay))))
    except Exception:
        pass
    return (False, 30)


_GUARDRAIL_MAX_PATTERN_LEN = 200  # Match output search limit
_GUARDRAIL_MAX_SCAN_BYTES = 1_000_000  # 1MB max text scanned by regex
_GUARDRAIL_REGEX_TIMEOUT = 5.0  # seconds
_ERROR_LINE_PATTERN = re.compile(
    r"\b(error|ERROR|Error|FATAL|fatal|panic|PANIC)\b"
)


async def _run_guardrails(project_id: int) -> list[dict] | None:
    """Validate output against configured guardrail rules.

    Returns a list of result dicts if guardrails are configured, None otherwise.
    Each result dict has: rule_type, pattern, threshold, action, passed, detail.
    """
    try:
        # Load project config to get guardrails
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT config FROM projects WHERE id = ?", (project_id,)
            )).fetchone()
            if not row or not row["config"]:
                return None
            cfg = json.loads(row["config"])
            rules = cfg.get("guardrails")
            if not rules:
                return None

        # Collect combined output
        with _buffers_lock:
            buf = _project_output_buffers.get(project_id, deque())
            combined_output = list(buf)

        combined_text = "\n".join(combined_output)
        if len(combined_text) > _GUARDRAIL_MAX_SCAN_BYTES:
            logger.warning(
                "Output too large for guardrail scan (%d bytes), truncating to %d",
                len(combined_text), _GUARDRAIL_MAX_SCAN_BYTES,
            )
            combined_text = combined_text[:_GUARDRAIL_MAX_SCAN_BYTES]
        total_lines = len(combined_output)

        results = []
        for rule in rules:
            rule_type = rule.get("type")
            pattern = rule.get("pattern")
            threshold = rule.get("threshold")
            action = rule.get("action", "warn")

            if rule_type in ("regex_match", "regex_reject"):
                if not pattern:
                    results.append({
                        "rule_type": rule_type, "pattern": pattern, "threshold": None,
                        "action": action,
                        "passed": rule_type != "regex_match",
                        "detail": "No pattern specified",
                    })
                    continue
                # Guard against ReDoS: limit pattern length
                if len(pattern) > _GUARDRAIL_MAX_PATTERN_LEN:
                    results.append({
                        "rule_type": rule_type, "pattern": pattern[:50] + "...",
                        "threshold": None, "action": action, "passed": False,
                        "detail": f"Pattern too long ({len(pattern)} chars, max {_GUARDRAIL_MAX_PATTERN_LEN})",
                    })
                    continue
                try:
                    compiled = re.compile(pattern)
                except re.error as e:
                    results.append({
                        "rule_type": rule_type, "pattern": pattern, "threshold": None,
                        "action": action, "passed": False, "detail": f"Invalid regex: {e}",
                    })
                    continue
                # Run regex in thread with timeout to prevent ReDoS
                try:
                    found = await asyncio.wait_for(
                        asyncio.to_thread(lambda: bool(compiled.search(combined_text))),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    results.append({
                        "rule_type": rule_type, "pattern": pattern, "threshold": None,
                        "action": action, "passed": False,
                        "detail": "Regex timed out (possible catastrophic backtracking)",
                    })
                    continue
                if rule_type == "regex_match":
                    results.append({
                        "rule_type": rule_type, "pattern": pattern, "threshold": None,
                        "action": action, "passed": found,
                        "detail": "Pattern found" if found else "Required pattern not found in output",
                    })
                else:  # regex_reject
                    results.append({
                        "rule_type": rule_type, "pattern": pattern, "threshold": None,
                        "action": action, "passed": not found,
                        "detail": "Rejected pattern not found" if not found else "Rejected pattern found in output",
                    })

            elif rule_type == "min_lines":
                min_req = threshold if threshold is not None else 0
                passed = total_lines >= min_req
                results.append({
                    "rule_type": rule_type, "pattern": None, "threshold": min_req,
                    "action": action, "passed": passed,
                    "detail": f"{total_lines} lines (min {min_req})" if passed
                             else f"Only {total_lines} lines, need at least {min_req}",
                })

            elif rule_type == "max_errors":
                max_err = threshold if threshold is not None else 0
                error_count = sum(
                    1 for line in combined_output
                    if _ERROR_LINE_PATTERN.search(line)
                )
                passed = error_count <= max_err
                results.append({
                    "rule_type": rule_type, "pattern": None, "threshold": max_err,
                    "action": action, "passed": passed,
                    "detail": f"{error_count} errors (max {max_err})" if passed
                             else f"{error_count} errors exceed max of {max_err}",
                })

        return results
    except Exception:
        logger.warning("Failed to run guardrails for project %d", project_id, exc_info=True)
        return None


async def _generate_run_summary(project_id: int) -> dict | None:
    """Generate a summary of the current run based on agent data.

    Called when the supervisor detects all agents have exited.
    Returns a dict suitable for JSON storage in swarm_runs.summary.
    """
    try:
        agents_data = {}
        total_lines = 0
        for key in _project_agent_keys(project_id):
            agent_name = key.split(":")[1]
            proc = _agent_processes.get(key)
            exit_code = proc.returncode if proc else None
            with _buffers_lock:
                line_count = len(_agent_output_buffers.get(key, deque()))
            started = _agent_started_at.get(key)
            agents_data[agent_name] = {
                "exit_code": exit_code,
                "output_lines": line_count,
                "started_at": started,
            }
            total_lines += line_count

        # Query DB for error count, project folder, etc. via thread to avoid blocking
        def _query_summary_db():
            import sqlite3 as _sqlite3
            _error_count = 0
            _signals = []
            _tasks_pct = 0.0
            try:
                conn = _sqlite3.connect(str(database.DB_PATH), timeout=5)
                try:
                    cur = conn.execute(
                        "SELECT COUNT(*) FROM agent_events WHERE project_id = ? AND event_type = 'agent_crashed'",
                        (project_id,),
                    )
                    _error_count = cur.fetchone()[0]

                    cur = conn.execute("SELECT folder_path FROM projects WHERE id = ?", (project_id,))
                    row = cur.fetchone()
                    if row:
                        folder = Path(row[0])
                        sig_dir = folder / ".claude" / "signals"
                        if sig_dir.exists():
                            _signals = [f.stem for f in sig_dir.glob("*.signal")]
                        tasks_file = folder / "tasks" / "TASKS.md"
                        if tasks_file.exists():
                            content = tasks_file.read_text()
                            total = len(re.findall(r"- \[[ x]\]", content))
                            done = len(re.findall(r"- \[x\]", content))
                            _tasks_pct = round((done / total) * 100, 1) if total > 0 else 0
                finally:
                    conn.close()
            except Exception:
                pass
            return _error_count, _signals, _tasks_pct

        error_count, signals_created, tasks_pct = await asyncio.to_thread(_query_summary_db)

        return {
            "agent_count": len(agents_data),
            "agents": agents_data,
            "total_output_lines": total_lines,
            "error_count": error_count,
            "signals_created": signals_created,
            "tasks_completed_percent": tasks_pct,
        }
    except Exception:
        logger.debug("Failed to generate run summary for project %d", project_id, exc_info=True)
        return None


async def _auto_queue_relaunch_agents(project_id: int) -> bool:
    """Relaunch agents for auto-queue continuation.

    Returns True if agents were successfully relaunched, False otherwise.
    This is a lightweight relaunch that preserves existing prompt files
    and does not run setup again.
    """
    try:
        # Get project folder
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                "SELECT folder_path FROM projects WHERE id = ?", (project_id,)
            )).fetchone()
            if not row:
                logger.warning("Auto-queue: project %d not found", project_id)
                return False
            folder = Path(row["folder_path"])

        if not folder.exists():
            logger.warning("Auto-queue: folder %s does not exist", folder)
            return False

        # Find prompt files
        prompts_dir = folder / ".claude" / "prompts"
        if not prompts_dir.exists():
            logger.warning("Auto-queue: no prompts directory for project %d", project_id)
            return False

        prompt_files = sorted(prompts_dir.glob("Claude-*.txt"))
        if not prompt_files:
            logger.warning("Auto-queue: no prompt files found for project %d", project_id)
            return False

        # Find claude CLI
        try:
            claude_cmd = _find_claude_cmd()
        except FileNotFoundError:
            logger.error("Auto-queue: claude CLI not found")
            return False

        # Clean up old processes for this project
        await cancel_drain_tasks(project_id)

        # Spawn agents
        agents_launched = []
        first_pid = None

        for pf in prompt_files:
            agent_name = pf.stem
            try:
                prompt_text = pf.read_text(encoding="utf-8-sig").strip()
            except Exception as e:
                logger.error("Auto-queue: failed to read prompt %s: %s", pf, e)
                continue
            if not prompt_text:
                logger.warning("Auto-queue: empty prompt for %s, skipping", agent_name)
                continue

            key = _agent_key(project_id, agent_name)

            try:
                spawn_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
                spawn_env["AGENT_NAME"] = agent_name
                popen_kwargs = dict(
                    cwd=str(folder),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=spawn_env,
                )
                if os.name == "nt":
                    popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                process = subprocess.Popen(
                    [
                        *claude_cmd,
                        "--print",
                        "--output-format", "stream-json",
                        "--dangerously-skip-permissions",
                        "--verbose",
                        prompt_text,
                    ],
                    **popen_kwargs,
                )
            except Exception as e:
                logger.error("Auto-queue: failed to spawn %s: %s", agent_name, e)
                with _buffers_lock:
                    buf = _project_output_buffers.setdefault(
                        project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                    )
                    buf.append(f"[{agent_name}] ERROR: Auto-queue spawn failed — {e}")
                continue

            # Set up log file
            log_dir = folder / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"{agent_name}_{timestamp}.output.log"
            _agent_log_files[key] = log_file

            # Start drain threads
            stop_event = threading.Event()
            stdout_thread = threading.Thread(
                target=_drain_agent_stream,
                args=(project_id, agent_name, process.stdout, "stdout", stop_event),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_drain_agent_stream,
                args=(project_id, agent_name, process.stderr, "stderr", stop_event),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # Register in tracking dicts
            _agent_processes[key] = process
            _agent_drain_events[key] = stop_event
            _agent_drain_threads[key] = [stdout_thread, stderr_thread]
            _agent_started_at[key] = datetime.now().isoformat()

            if first_pid is None:
                first_pid = process.pid

            with _buffers_lock:
                _agent_output_buffers.setdefault(key, deque(maxlen=_MAX_OUTPUT_LINES))

            agents_launched.append(agent_name)
            with _buffers_lock:
                buf = _project_output_buffers.setdefault(
                    project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                )
                buf.append(f"[auto-queue] Relaunched {agent_name} (pid={process.pid})")
            logger.info("Auto-queue: launched %s (pid=%d) for project %d", agent_name, process.pid, project_id)

            _record_event_sync(
                project_id, agent_name, "agent_started",
                f"pid={process.pid} (auto-queue)",
            )

        if not agents_launched:
            logger.warning("Auto-queue: no agents could be launched for project %d", project_id)
            return False

        # Reset auto-stop timer
        _last_output_at[project_id] = time.time()

        # Update resource tracking
        _project_resource_usage[project_id] = {
            "agent_count": len(agents_launched),
            "restart_counts": {},
            "started_at": time.time(),
        }

        # Update DB — mark project as running again and create new swarm run
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "UPDATE projects SET status = 'running', swarm_pid = ?, updated_at = datetime('now') WHERE id = ?",
                (first_pid, project_id),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
                (project_id,),
            )
            await db.commit()

        logger.info("Auto-queue: successfully relaunched %d agents for project %d", len(agents_launched), project_id)
        return True

    except Exception:
        logger.error("Auto-queue: relaunch failed for project %d", project_id, exc_info=True)
        return False


async def _supervisor_loop(project_id: int):
    """Monitor agent processes; mark swarm as completed when all exit.

    Logs individual agent exits with exit codes and reports partial failures
    to the project output buffer so the user sees agent crashes in the web UI.
    Also auto-stops swarm if no output for configured idle timeout.
    """
    logger.info("Supervisor started for project %d", project_id)
    # Announce supervisor start to UI
    with _buffers_lock:
        buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
        buf.append("[system] Supervisor started — monitoring agents")
    # Track which agents we've already reported as exited
    reported_exited: set[str] = set()
    # Load auto-stop config once at start
    auto_stop_min = await _get_project_auto_stop(project_id)
    if auto_stop_min > 0:
        logger.info("Auto-stop enabled for project %d: %d minutes", project_id, auto_stop_min)
    _SUPERVISOR_FLUSH_INTERVAL = 6  # Flush checkpoints every 6 iterations (60s)
    try:
        iteration_count = 0
        while True:
            await asyncio.sleep(10)
            iteration_count += 1

            # --- Periodic checkpoint flush (every 60s) to prevent data loss on crash ---
            if iteration_count % _SUPERVISOR_FLUSH_INTERVAL == 0:
                try:
                    await asyncio.to_thread(_flush_checkpoints)
                except Exception:
                    logger.warning("Periodic checkpoint flush failed for project %d", project_id, exc_info=True)

            # --- Auto-stop check ---
            if auto_stop_min > 0 and _any_agent_alive(project_id):
                with _buffers_lock:
                    last_output = _last_output_at.get(project_id)
                if last_output and (time.time() - last_output) > auto_stop_min * 60:
                    logger.warning(
                        "Auto-stopping project %d: no output for %d minutes",
                        project_id, auto_stop_min,
                    )
                    with _buffers_lock:
                        buf = _project_output_buffers.setdefault(
                            project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                        )
                        buf.append(f"[system] Auto-stopped: no output for {auto_stop_min} minutes")
                    # Use _terminate (not _cleanup) to avoid cancelling ourselves
                    await asyncio.to_thread(_terminate_project_agents, project_id)
                    # Mark as stopped in DB
                    try:
                        async with aiosqlite.connect(database.DB_PATH) as db:
                            db.row_factory = aiosqlite.Row
                            await db.execute(
                                "UPDATE projects SET status = 'stopped', swarm_pid = NULL, "
                                "updated_at = datetime('now') WHERE id = ?",
                                (project_id,),
                            )
                            await db.execute(
                                "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped' "
                                "WHERE project_id = ? AND status = 'running'",
                                (project_id,),
                            )
                            await db.commit()
                    except Exception:
                        logger.error("Auto-stop DB update failed for project %d",
                                     project_id, exc_info=True)
                    try:
                        await emit_webhook_event("swarm_stopped", project_id,
                                                 {"reason": "auto_stop_idle"})
                    except Exception:
                        pass
                    break

            # --- Duration watchdog check ---
            usage = _project_resource_usage.get(project_id)
            if usage and _any_agent_alive(project_id):
                quota = await _get_project_quota(project_id)
                max_hours = quota.get("max_duration_hours")
                if max_hours and usage.get("started_at"):
                    elapsed = (time.time() - usage["started_at"]) / 3600
                    if elapsed > max_hours:
                        logger.warning(
                            "Duration quota exceeded for project %d: %.1fh > %.1fh",
                            project_id, elapsed, max_hours,
                        )
                        with _buffers_lock:
                            buf = _project_output_buffers.setdefault(
                                project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                            )
                            buf.append(f"[system] Duration quota exceeded ({elapsed:.1f}h > {max_hours}h) — auto-stopping")
                        await asyncio.to_thread(_terminate_project_agents, project_id)
                        try:
                            async with aiosqlite.connect(database.DB_PATH) as db:
                                db.row_factory = aiosqlite.Row
                                await db.execute(
                                    "UPDATE projects SET status = 'stopped', swarm_pid = NULL, "
                                    "updated_at = datetime('now') WHERE id = ?",
                                    (project_id,),
                                )
                                await db.execute(
                                    "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped' "
                                    "WHERE project_id = ? AND status = 'running'",
                                    (project_id,),
                                )
                                await db.commit()
                        except Exception:
                            logger.error("Duration watchdog DB update failed for project %d",
                                         project_id, exc_info=True)
                        try:
                            await emit_webhook_event("swarm_stopped", project_id,
                                                     {"reason": "duration_quota_exceeded"})
                        except Exception:
                            pass
                        break

            # --- Directive consumed check ---
            # Check if any .directive files were deleted (consumed by agents)
            try:
                def _check_directives_sync():
                    """Check for consumed directives (sync helper for to_thread)."""
                    import sqlite3 as _sqlite3
                    conn = _sqlite3.connect(str(database.DB_PATH), timeout=5)
                    try:
                        cur = conn.execute("SELECT folder_path FROM projects WHERE id = ?", (project_id,))
                        prow = cur.fetchone()
                        if not prow:
                            return []
                        dir_path = Path(prow[0]) / ".claude" / "directives"
                        if not dir_path.exists():
                            return []
                        known = _known_directives.setdefault(project_id, set())
                        current = {f.name for f in dir_path.glob("*.directive")}
                        consumed = known - current
                        result = []
                        for fname in consumed:
                            agent = fname.replace(".directive", "")
                            _record_event_sync(
                                project_id, agent, "directive_consumed",
                                "Agent consumed pending directive",
                            )
                            result.append(agent)
                        known.clear()
                        known.update(current)
                        return result
                    finally:
                        conn.close()

                consumed_agents = await asyncio.to_thread(_check_directives_sync)
                for agent in consumed_agents:
                    logger.info("Directive consumed by %s in project %d", agent, project_id)
                    try:
                        asyncio.create_task(ws_manager.broadcast({
                            "type": "directive_consumed",
                            "project_id": project_id,
                            "agent": agent,
                        }))
                    except Exception:
                        pass
            except Exception:
                logger.debug("Directive check failed for project %d", project_id, exc_info=True)

            # Check each agent individually to detect partial failures
            for key in _project_agent_keys(project_id):
                if key in reported_exited:
                    continue
                proc = _agent_processes.get(key)
                if proc and proc.poll() is not None:
                    agent_name = key.split(":")[1]
                    exit_code = proc.returncode
                    reported_exited.add(key)
                    if exit_code == 0:
                        msg = f"[{agent_name}] --- Agent exited normally (code 0) ---"
                        logger.info("Agent %s exited normally for project %d", agent_name, project_id)
                        _record_event_sync(
                            project_id, agent_name, "agent_stopped",
                            f"exit_code=0",
                        )
                        # Circuit breaker: probe success if agent was in half-open state and ran > 30s
                        cb = _circuit_breakers.get(key)
                        if cb and cb["state"] == "half-open" and cb.get("probe_started_at"):
                            if time.time() - cb["probe_started_at"] > 30:
                                _cb_record_probe_success(key)
                                _record_event_sync(
                                    project_id, agent_name, "circuit_breaker_closed",
                                    "probe succeeded",
                                )
                    else:
                        msg = f"[{agent_name}] --- Agent crashed (exit code {exit_code}) ---"
                        logger.warning(
                            "Agent %s crashed for project %d (exit code %d)",
                            agent_name, project_id, exit_code,
                        )
                        _record_event_sync(
                            project_id, agent_name, "agent_crashed",
                            f"exit_code={exit_code}",
                        )
                        # Circuit breaker: record failure and potentially open circuit
                        cb_cfg = None
                        try:
                            cb_cfg = await _get_project_quota(project_id)
                        except Exception:
                            pass
                        if cb_cfg and cb_cfg.get("circuit_breaker_max_failures") is not None:
                            cb_max = cb_cfg["circuit_breaker_max_failures"]
                            cb_window = cb_cfg.get("circuit_breaker_window_seconds") or _CB_DEFAULT_WINDOW_SECONDS
                            result = _cb_record_failure(key, exit_code, cb_max, cb_window)
                            if result in ("opened", "reopened"):
                                _record_event_sync(
                                    project_id, agent_name, "circuit_breaker_opened",
                                    f"{len(_circuit_breakers.get(key, {}).get('failures', []))} failures in {cb_window}s",
                                )
                    with _buffers_lock:
                        buf = _project_output_buffers.setdefault(
                            project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                        )
                        buf.append(msg)

            if _any_agent_alive(project_id):
                continue

            # All agents exited — wait briefly for drain threads to flush remaining output
            await asyncio.sleep(2)

            logger.info("All agents exited for project %d, marking completed", project_id)
            with _buffers_lock:
                buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
                buf.append("[system] All agents exited — processing completion...")

            # Flush any pending checkpoints before generating summary
            await asyncio.to_thread(_flush_checkpoints)

            # --- Generate run summary ---
            summary = await _generate_run_summary(project_id)
            summary_json = json.dumps(summary) if summary else None

            # --- Run guardrails ---
            guardrail_results = await _run_guardrails(project_id)
            guardrail_json = json.dumps(guardrail_results) if guardrail_results else None
            run_status = "completed"
            if guardrail_results:
                has_halt = any(
                    not r["passed"] and r["action"] == "halt"
                    for r in guardrail_results
                )
                has_violations = any(not r["passed"] for r in guardrail_results)
                if has_halt:
                    run_status = "failed_guardrail"
                    logger.warning(
                        "Guardrail halt triggered for project %d — run marked failed_guardrail",
                        project_id,
                    )
                    with _buffers_lock:
                        buf = _project_output_buffers.setdefault(
                            project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                        )
                        buf.append("[system] Guardrail HALT: run failed validation, phase chaining stopped")
                if has_violations:
                    for r in guardrail_results:
                        if not r["passed"]:
                            try:
                                await _record_event_async(
                                    project_id, "system", "guardrail_violation",
                                    f"{r['rule_type']}({r['action']}): {r['detail']}",
                                )
                            except Exception:
                                pass
                    if not has_halt:
                        # Warn-only violations
                        try:
                            await ws_manager.broadcast(json.dumps({
                                "type": "guardrail_warning",
                                "project_id": project_id,
                                "violations": [r for r in guardrail_results if not r["passed"]],
                            }))
                        except Exception:
                            pass

            # --- Auto-queue check (before marking stopped) ---
            # Check auto_queue FIRST to avoid race condition where frontend
            # sees 'stopped' and triggers a new launch that cancels us
            auto_queue_enabled, auto_queue_delay = await _get_project_auto_queue(project_id)
            will_auto_queue = auto_queue_enabled and run_status != "failed_guardrail"

            # Retry DB update up to 3 times with backoff
            # If auto-queue will trigger, keep status as 'running' to prevent race
            new_status = 'running' if will_auto_queue else 'stopped'
            for attempt in range(3):
                try:
                    async with aiosqlite.connect(database.DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        await db.execute(
                            f"UPDATE projects SET status = '{new_status}', swarm_pid = NULL, "
                            "updated_at = datetime('now') WHERE id = ?",
                            (project_id,),
                        )
                        await db.execute(
                            "UPDATE swarm_runs SET ended_at = datetime('now'), status = ?, "
                            "summary = ?, guardrail_results = ? "
                            "WHERE project_id = ? AND status = 'running'",
                            (run_status, summary_json, guardrail_json, project_id),
                        )
                        await db.commit()
                    break
                except Exception:
                    if attempt == 2:
                        logger.error("Supervisor DB update failed after 3 attempts for project %d",
                                     project_id, exc_info=True)
                    else:
                        await asyncio.sleep(1 * (attempt + 1))
            if not will_auto_queue:
                try:
                    await emit_webhook_event("swarm_stopped", project_id, {"reason": "all_agents_exited"})
                except Exception:
                    logger.error("Webhook emit failed for project %d", project_id, exc_info=True)

            # --- Auto-queue relaunch ---
            if will_auto_queue:
                logger.info(
                    "Auto-queue enabled for project %d, relaunching in %d seconds",
                    project_id, auto_queue_delay,
                )
                with _buffers_lock:
                    buf = _project_output_buffers.setdefault(
                        project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                    )
                    buf.append(f"[system] Auto-queue: relaunching agents in {auto_queue_delay} seconds...")
                try:
                    await ws_manager.broadcast(json.dumps({
                        "type": "auto_queue_pending",
                        "project_id": project_id,
                        "delay_seconds": auto_queue_delay,
                    }))
                except Exception:
                    pass

                await asyncio.sleep(auto_queue_delay)

                # Attempt to relaunch agents
                relaunch_ok = await _auto_queue_relaunch_agents(project_id)
                if relaunch_ok:
                    logger.info("Auto-queue relaunch successful for project %d", project_id)
                    with _buffers_lock:
                        buf = _project_output_buffers.setdefault(
                            project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                        )
                        buf.append("[system] Auto-queue: agents relaunched successfully")
                    try:
                        await ws_manager.broadcast(json.dumps({
                            "type": "auto_queue_launched",
                            "project_id": project_id,
                        }))
                    except Exception:
                        pass
                    # Reset reported_exited for the new agents
                    reported_exited.clear()
                    # Continue the supervisor loop to monitor new agents
                    continue
                else:
                    logger.warning("Auto-queue relaunch failed for project %d", project_id)
                    with _buffers_lock:
                        buf = _project_output_buffers.setdefault(
                            project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                        )
                        buf.append("[system] Auto-queue: relaunch failed — stopping")
                    # Now mark as stopped since relaunch failed
                    try:
                        async with aiosqlite.connect(database.DB_PATH) as db:
                            await db.execute(
                                "UPDATE projects SET status = 'stopped' WHERE id = ?",
                                (project_id,),
                            )
                            await db.commit()
                    except Exception:
                        pass
                    try:
                        await emit_webhook_event("swarm_stopped", project_id, {"reason": "auto_queue_failed"})
                    except Exception:
                        pass
            else:
                # Auto-queue not enabled or guardrail halt
                with _buffers_lock:
                    buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
                    if run_status == "failed_guardrail":
                        buf.append("[system] Supervisor exiting — guardrail halt triggered")
                    else:
                        buf.append("[system] Supervisor exiting — auto-queue disabled")
            break
    except asyncio.CancelledError:
        logger.info("Supervisor cancelled for project %d", project_id)
        with _buffers_lock:
            buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
            buf.append("[system] Supervisor cancelled")
        # Ensure status is stopped on cancellation
        try:
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute(
                    "UPDATE projects SET status = 'stopped', swarm_pid = NULL WHERE id = ?",
                    (project_id,),
                )
                await db.commit()
        except Exception:
            pass
    except Exception:
        logger.error("Supervisor error for project %d", project_id, exc_info=True)
        with _buffers_lock:
            buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
            buf.append("[system] Supervisor error — check server logs")
        # Ensure status is stopped on error
        try:
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute(
                    "UPDATE projects SET status = 'stopped', swarm_pid = NULL WHERE id = ?",
                    (project_id,),
                )
                await db.commit()
        except Exception:
            pass
    finally:
        _supervisor_tasks.pop(project_id, None)
        _known_directives.pop(project_id, None)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SwarmLaunchRequest(BaseModel):
    """Launch a Claude Swarm for a project."""
    project_id: int = Field(examples=[1])
    resume: bool = Field(default=False, description="Resume a previous swarm session")
    no_confirm: bool = Field(default=True, description="Skip confirmation prompts")
    agent_count: int = Field(default=4, ge=1, le=16, examples=[4])
    max_phases: int = Field(default=999, ge=1, le=999, examples=[24])


class SwarmStopRequest(BaseModel):
    """Stop a running swarm process."""
    project_id: int = Field(ge=1, examples=[1])


class SwarmInputRequest(BaseModel):
    """Send stdin input to a running swarm process."""
    project_id: int = Field(ge=1, examples=[1])
    text: str = Field(max_length=1000, examples=["y"])
    agent: Optional[str] = Field(
        default=None,
        description="Target specific agent (e.g. 'Claude-1'). Omit to send to all.",
    )


_404 = {404: {"model": ErrorDetail, "description": "Project not found"}}
_400 = {400: {"model": ErrorDetail, "description": "Invalid request"}}


# ---------------------------------------------------------------------------
# POST /launch — run setup, then spawn per-agent claude subprocesses
# ---------------------------------------------------------------------------

@router.post("/launch", response_model=SwarmLaunchOut,
             summary="Launch swarm", responses={**_404, **_400})
async def launch_swarm(req: SwarmLaunchRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Launch agents as backend-managed subprocesses.

    1. Run swarm.ps1 -SetupOnly to create dirs, prompt files, etc.
    2. Read prompt files from .claude/prompts/
    3. Spawn each agent as `claude --dangerously-skip-permissions <prompt>`
    """
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (req.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Acquire per-project lock to prevent concurrent launch/stop races
    lock = _get_project_lock(req.project_id)
    async with lock:
        return await _launch_swarm_locked(req, db, row)


async def _launch_swarm_locked(req: SwarmLaunchRequest, db: aiosqlite.Connection, row):
    """Inner launch logic, called under per-project lock."""
    project = dict(row)
    folder = Path(project["folder_path"])
    swarm_script = folder / "swarm.ps1"

    if not swarm_script.exists():
        raise HTTPException(status_code=400, detail="swarm.ps1 not found in project folder")

    # --- Quota enforcement: max_agents_concurrent ---
    quota = await _get_project_quota(req.project_id)
    max_agents = quota.get("max_agents_concurrent")
    if max_agents is not None and req.agent_count > max_agents:
        raise HTTPException(
            status_code=429,
            detail=f"Agent quota exceeded (limit: {max_agents}, requested: {req.agent_count})",
        )

    # Find claude CLI
    try:
        claude_cmd = _find_claude_cmd()
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail="claude CLI not found — install with: npm install -g @anthropic-ai/claude-code",
        )

    # Ensure swarm config exists so -Resume skips interactive prompts
    claude_dir = folder / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config_file = claude_dir / "swarm-config.json"

    project_name = project.get("name", "Project")
    project_desc = project.get("description") or project_name

    if not config_file.exists():
        swarm_cfg = {
            "Goal": project_desc,
            "ProjectType": "Custom Project",
            "TechStack": "auto-detect based on project type",
            "Complexity": "Medium",
            "Requirements": "",
            "StartTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "AgentCount": req.agent_count,
        }
        config_file.write_text(json.dumps(swarm_cfg, indent=2), encoding="utf-8")
        logger.info("Created swarm config for project %d", req.project_id)

    # Create fresh TASKS.md only on initial launch, preserve on resume
    tasks_dir = folder / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    tasks_file = tasks_dir / "TASKS.md"

    if req.resume and tasks_file.exists():
        # Resume mode: preserve existing TASKS.md with agent progress
        logger.info("Resume mode: preserving existing TASKS.md for project %d", req.project_id)
    else:
        # Fresh launch: create new TASKS.md
        tasks_file.write_text(
            f"# {project_name}\n\n"
            f"{project_desc}\n\n"
            "## Claude-1 [Backend/Core]\n"
            "- [ ] Analyze project structure and identify tasks\n"
            "- [ ] Implement core functionality\n"
            "- [ ] Add error handling and validation\n\n"
            "## Claude-2 [Frontend/Interface]\n"
            "- [ ] Set up UI scaffolding\n"
            "- [ ] Implement main interface components\n"
            "- [ ] Connect to backend APIs\n\n"
            "## Claude-3 [Integration/Testing]\n"
            "- [ ] Write unit tests for core modules\n"
            "- [ ] Write integration tests\n"
            "- [ ] Verify all components work together\n\n"
            "## Claude-4 [Polish/Review]\n"
            "- [ ] Code review all agent work\n"
            "- [ ] Fix issues found in review\n"
            "- [ ] FINAL: Generate next-swarm.ps1 for next phase\n",
            encoding="utf-8",
        )
        logger.info("Created fresh TASKS.md for project %d", req.project_id)

    # Clear stale cached run_id to prevent reuse from previous launch
    _current_run_ids.pop(req.project_id, None)

    # Clean up any previous agents and cancel existing supervisor for this project
    existing_supervisor = _supervisor_tasks.get(req.project_id)
    if existing_supervisor and not existing_supervisor.done():
        existing_supervisor.cancel()
        try:
            await existing_supervisor
        except asyncio.CancelledError:
            pass
    await cancel_drain_tasks(req.project_id)
    with _buffers_lock:
        _project_output_buffers[req.project_id] = deque(maxlen=_MAX_OUTPUT_LINES)

    # Clean stale filesystem artifacts from previous runs
    await asyncio.to_thread(_clean_project_artifacts, folder)

    # --- Phase 1: Setup ---
    # Run swarm.ps1 -SetupOnly to generate prompt files and project structure
    try:
        result = await asyncio.to_thread(
            _run_setup_only, folder, swarm_script, req.agent_count, req.max_phases,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Setup phase timed out after 60s")
    except Exception as e:
        logger.error("Setup phase failed for project %d: %s", req.project_id, e)
        raise HTTPException(status_code=500, detail=f"Setup phase failed: {e}")

    # Add setup output to buffer for visibility
    with _buffers_lock:
        buf = _project_output_buffers.setdefault(
            req.project_id, deque(maxlen=_MAX_OUTPUT_LINES),
        )
        for line in (result.stdout or "").splitlines():
            stripped = line.strip()
            if stripped:
                buf.append(f"[setup] {stripped}")
        if result.returncode != 0:
            for line in (result.stderr or "").splitlines():
                stripped = line.strip()
                if stripped:
                    buf.append(f"[setup:err] {stripped}")

    if result.returncode != 0:
        stderr_snippet = (result.stderr or "").strip()[-200:] if result.stderr else ""
        logger.error("Setup exited %d: %s", result.returncode, (result.stderr or "")[:500])
        detail = f"Setup phase failed (exit {result.returncode})"
        if stderr_snippet:
            detail += f": {stderr_snippet}"
        raise HTTPException(status_code=500, detail=detail)

    # --- Phase 2: Read prompt files ---
    prompts_dir = folder / ".claude" / "prompts"
    prompt_files = sorted(prompts_dir.glob("Claude-*.txt"))
    if not prompt_files:
        raise HTTPException(
            status_code=500,
            detail="No prompt files found after setup — check swarm.ps1 output",
        )

    # Ensure support directories exist
    (folder / ".claude" / "heartbeats").mkdir(parents=True, exist_ok=True)
    (folder / ".claude" / "signals").mkdir(parents=True, exist_ok=True)
    (folder / ".claude" / "handoffs").mkdir(parents=True, exist_ok=True)
    (folder / ".claude" / "attention").mkdir(parents=True, exist_ok=True)
    (folder / ".swarm").mkdir(parents=True, exist_ok=True)
    (folder / ".swarm" / "bus").mkdir(parents=True, exist_ok=True)
    (folder / "logs").mkdir(parents=True, exist_ok=True)

    # Create bus.json for CLI client discovery
    bus_config = {
        "port": config.PORT,
        "project_id": req.project_id,
        "api_key": config.API_KEY or "",
    }
    bus_json_path = folder / ".swarm" / "bus.json"
    bus_json_path.write_text(json.dumps(bus_config, indent=2), encoding="utf-8")

    # Copy CLI client to project for agent access
    bus_client_dir = Path(__file__).parent.parent.parent / "bus-client"
    bus_dest_dir = folder / ".swarm" / "bus"
    for script_name in ("swarm-msg.ps1", "swarm-msg.cmd"):
        src = bus_client_dir / script_name
        dest = bus_dest_dir / script_name
        if src.exists():
            shutil.copy2(src, dest)
            logger.debug("Copied %s to %s", src, dest)

    # --- Phase 3: Spawn agents ---
    agents_launched = []
    agents_failed = []
    first_pid = None

    for pf in prompt_files:
        agent_name = pf.stem  # e.g. "Claude-1"
        try:
            prompt_text = pf.read_text(encoding="utf-8-sig").strip()
        except Exception as e:
            logger.error("Failed to read prompt %s: %s", pf, e)
            agents_failed.append(agent_name)
            continue
        if not prompt_text:
            logger.warning("Empty prompt for %s, skipping", agent_name)
            agents_failed.append(agent_name)
            continue

        key = _agent_key(req.project_id, agent_name)

        try:
            # Strip CLAUDECODE env var so spawned agents don't think they're nested
            # Add AGENT_NAME for CLI client identification
            spawn_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            spawn_env["AGENT_NAME"] = agent_name
            popen_kwargs = dict(
                cwd=str(folder),
                stdin=subprocess.DEVNULL,  # --print mode needs stdin EOF to start
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=spawn_env,
            )
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(
                [
                    *claude_cmd,  # e.g. ["node", "cli.js"] or ["claude"]
                    "--print",
                    "--output-format", "stream-json",
                    "--dangerously-skip-permissions",
                    "--verbose",
                    prompt_text,
                ],
                **popen_kwargs,
            )
        except Exception as e:
            logger.error("Failed to spawn %s: %s", agent_name, e)
            agents_failed.append(agent_name)
            with _buffers_lock:
                buf = _project_output_buffers.setdefault(
                    req.project_id, deque(maxlen=_MAX_OUTPUT_LINES),
                )
                buf.append(f"[{agent_name}] ERROR: Failed to start — {e}")
            continue

        # Set up persistent log file for crash recovery
        log_dir = folder / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{agent_name}_{timestamp}.output.log"
        _agent_log_files[key] = log_file

        # Start drain threads IMMEDIATELY after spawn to avoid losing early output
        stop_event = threading.Event()
        stdout_thread = threading.Thread(
            target=_drain_agent_stream,
            args=(req.project_id, agent_name, process.stdout, "stdout", stop_event),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_drain_agent_stream,
            args=(req.project_id, agent_name, process.stderr, "stderr", stop_event),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        # Now register in tracking dicts
        _agent_processes[key] = process
        _agent_drain_events[key] = stop_event
        _agent_drain_threads[key] = [stdout_thread, stderr_thread]
        _agent_started_at[key] = datetime.now().isoformat()

        if first_pid is None:
            first_pid = process.pid

        with _buffers_lock:
            _agent_output_buffers.setdefault(key, deque(maxlen=_MAX_OUTPUT_LINES))

        agents_launched.append(agent_name)
        with _buffers_lock:
            buf = _project_output_buffers.setdefault(
                req.project_id, deque(maxlen=_MAX_OUTPUT_LINES),
            )
            buf.append(f"[setup] Launched {agent_name} (pid={process.pid})")
        logger.info("Launched %s (pid=%d) for project %d", agent_name, process.pid, req.project_id)

        # Emit agent_started event (non-blocking, best-effort)
        _record_event_sync(
            req.project_id, agent_name, "agent_started",
            f"pid={process.pid}",
        )

    if not agents_launched:
        raise HTTPException(
            status_code=500,
            detail="No agents could be launched — check claude CLI",
        )

    # Initialize auto-stop timer from launch time
    _last_output_at[req.project_id] = time.time()

    # Initialize resource usage tracking for quota enforcement
    _project_resource_usage[req.project_id] = {
        "agent_count": len(agents_launched),
        "restart_counts": {},
        "started_at": time.time(),
    }

    # Update DB — single transaction for project status + new swarm run
    await db.execute(
        "UPDATE projects SET status = 'running', swarm_pid = ?, updated_at = datetime('now') WHERE id = ?",
        (first_pid, req.project_id),
    )
    await db.execute(
        "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
        (req.project_id,),
    )
    await db.commit()

    # Start supervisor
    _supervisor_tasks[req.project_id] = asyncio.create_task(
        _supervisor_loop(req.project_id)
    )

    logger.info("Swarm launched for project %d: %s", req.project_id, agents_launched)
    await emit_webhook_event("swarm_launched", req.project_id, {
        "agents": agents_launched, "pid": first_pid,
    })
    return {
        "status": "launched",
        "pid": first_pid,
        "project_id": req.project_id,
        "agents_launched": agents_launched,
        "agents_failed": agents_failed,
    }


# ---------------------------------------------------------------------------
# POST /stop — terminate all agents for a project
# ---------------------------------------------------------------------------

@router.post("/stop", response_model=SwarmStopOut,
             summary="Stop swarm", responses=_404)
async def stop_swarm(req: SwarmStopRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Stop all running agents for a project."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (req.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Acquire per-project lock to prevent concurrent launch/stop races
    lock = _get_project_lock(req.project_id)
    async with lock:
        await asyncio.to_thread(_cleanup_project_agents, req.project_id)

        await db.execute(
            "UPDATE projects SET status = 'stopped', swarm_pid = NULL, updated_at = datetime('now') WHERE id = ?",
            (req.project_id,),
        )
        await db.execute(
            """UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped'
               WHERE project_id = ? AND status = 'running'""",
            (req.project_id,),
        )
        await db.commit()

    logger.info("Swarm stopped for project %d", req.project_id)
    await emit_webhook_event("swarm_stopped", req.project_id, {})
    return {"status": "stopped", "project_id": req.project_id}


# ---------------------------------------------------------------------------
# POST /input — send message to agents via message bus
# ---------------------------------------------------------------------------

@router.post("/input", response_model=SwarmInputOut,
             summary="Send swarm input", responses={**_404, **_400})
async def swarm_input(req: SwarmInputRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Send a message to agent(s) via the message bus.

    Routes human messages through the bus instead of broken stdin injection.
    Messages are delivered with critical channel and high priority for
    immediate agent pickup.
    """
    import uuid

    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (req.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])

    if project["status"] != "running":
        raise HTTPException(status_code=400, detail="Swarm is not running")

    # Validate agent if specified
    to_agent = req.agent or "all"
    if req.agent:
        if not _validate_agent_name(req.agent):
            raise HTTPException(status_code=400, detail="Invalid agent name format")
        key = _agent_key(req.project_id, req.agent)
        proc = _agent_processes.get(key)
        if not proc or proc.poll() is not None:
            raise HTTPException(status_code=400, detail=f"Agent {req.agent} is not running")

    # Check at least one agent is running for broadcast
    if not req.agent:
        running = [k for k in _project_agent_keys(req.project_id)
                   if (p := _agent_processes.get(k)) and p.poll() is None]
        if not running:
            raise HTTPException(status_code=400, detail="No running agents found")

    # Get current run_id for message association
    run_row = await (
        await db.execute(
            "SELECT id FROM swarm_runs WHERE project_id = ? AND status = 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            (req.project_id,),
        )
    ).fetchone()
    run_id = run_row["id"] if run_row else None

    # Create message in bus
    message_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    await db.execute(
        """INSERT INTO bus_messages
           (id, project_id, run_id, from_agent, to_agent, channel, priority, msg_type, body, created_at)
           VALUES (?, ?, ?, 'human', ?, 'critical', 'high', 'request', ?, ?)""",
        (message_id, req.project_id, run_id, to_agent, req.text, created_at),
    )
    await db.commit()

    # Create attention file(s) for immediate pickup
    attention_dir = folder / ".claude" / "attention"
    attention_dir.mkdir(parents=True, exist_ok=True)
    attention_content = f"{message_id}\n{created_at}"

    try:
        if to_agent == "all":
            # Create attention file for all running agents
            for key in _project_agent_keys(req.project_id):
                proc = _agent_processes.get(key)
                if proc and proc.poll() is None:
                    agent_name = key.split(":")[1]
                    (attention_dir / f"{agent_name}.attention").write_text(
                        attention_content, encoding="utf-8"
                    )
        else:
            (attention_dir / f"{to_agent}.attention").write_text(
                attention_content, encoding="utf-8"
            )
    except OSError as e:
        logger.warning("Failed to create attention file: %s", e)

    # Broadcast via WebSocket for UI visibility
    await ws_manager.broadcast({
        "type": "bus_message",
        "project_id": req.project_id,
        "message": {
            "id": message_id,
            "from_agent": "human",
            "to_agent": to_agent,
            "channel": "critical",
            "priority": "high",
            "body": req.text[:200] + "..." if len(req.text) > 200 else req.text,
            "created_at": created_at,
        },
    })

    # Echo in output buffers for visibility
    with _buffers_lock:
        buf = _project_output_buffers.setdefault(
            req.project_id, deque(maxlen=_MAX_OUTPUT_LINES),
        )
        buf.append(f"[bus:human->{to_agent}] {req.text}")

    logger.info("Sent bus message to project %d [%s]: %s", req.project_id, to_agent, req.text[:50])
    return {"status": "sent", "project_id": req.project_id}


# ---------------------------------------------------------------------------
# GET /status/{project_id}
# ---------------------------------------------------------------------------

@router.get("/status/{project_id}", response_model=SwarmStatusOut,
            summary="Get swarm status", responses=_404)
async def swarm_status(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get detailed status including agents, signals, tasks, and phase info."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])

    # Check if project is supposed to be running but has no live agents
    alive = _any_agent_alive(project_id)
    if project["status"] == "running" and not alive:
        # Also check the stored PID for legacy processes
        if not _pid_alive(project.get("swarm_pid")):
            logger.warning("No live agents for project %d, auto-correcting to stopped", project_id)
            await db.execute(
                "UPDATE projects SET status = 'stopped', swarm_pid = NULL, updated_at = datetime('now') WHERE id = ?",
                (project_id,),
            )
            await db.execute(
                "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'crashed' "
                "WHERE project_id = ? AND status = 'running'",
                (project_id,),
            )
            await db.commit()
            await emit_webhook_event("swarm_crashed", project_id, {"stale_pid": project.get("swarm_pid")})
            project["status"] = "stopped"
            project["swarm_pid"] = None

    # Read heartbeats
    agents = []
    hb_dir = folder / ".claude" / "heartbeats"
    if hb_dir.exists():
        for f in hb_dir.glob("*.heartbeat"):
            try:
                content = f.read_text(encoding="utf-8-sig").strip()
                agents.append({"name": f.stem, "last_heartbeat": content})
            except Exception:
                logger.debug("Failed to read heartbeat %s", f, exc_info=True)
                agents.append({"name": f.stem, "last_heartbeat": None})

    # Read signals
    signals = {}
    sig_dir = folder / ".claude" / "signals"
    signal_names = ["backend-ready", "frontend-ready", "tests-passing", "phase-complete"]
    if sig_dir.exists():
        for name in signal_names:
            signals[name] = (sig_dir / f"{name}.signal").exists()
    else:
        signals = {name: False for name in signal_names}

    # Read task progress
    tasks_file = folder / "tasks" / "TASKS.md"
    task_progress = {"total": 0, "done": 0, "percent": 0}
    if tasks_file.exists():
        try:
            content = tasks_file.read_text()
            total = len(re.findall(r"- \[[ x]\]", content))
            done = len(re.findall(r"- \[x\]", content))
            task_progress = {
                "total": total,
                "done": done,
                "percent": round((done / total) * 100, 1) if total > 0 else 0,
            }
        except Exception:
            logger.debug("Failed to read tasks file %s", tasks_file, exc_info=True)

    # Read phase info
    phase_info = None
    phase_file = folder / ".claude" / "swarm-phase.json"
    if phase_file.exists():
        try:
            phase_info = json.loads(phase_file.read_text())
        except Exception:
            logger.debug("Failed to read phase file %s", phase_file, exc_info=True)

    return {
        "project_id": project_id,
        "status": project["status"],
        "swarm_pid": project.get("swarm_pid"),
        "process_alive": alive or _pid_alive(project.get("swarm_pid")),
        "agents": agents,
        "signals": signals,
        "tasks": task_progress,
        "phase": phase_info,
    }


# ---------------------------------------------------------------------------
# GET /agents/{project_id} — per-agent status list
# ---------------------------------------------------------------------------

@router.get("/agents/{project_id}", response_model=AgentsListOut,
            summary="List swarm agents", responses=_404)
async def list_agents(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """List all agents for a project with their alive/stopped status."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    keys = sorted(_project_agent_keys(project_id))
    agents = []
    for key in keys:
        agent_name = key.split(":")[1]
        proc = _agent_processes.get(key)
        is_alive = proc is not None and proc.poll() is None
        exit_code = None
        if proc and not is_alive:
            exit_code = proc.returncode
        with _buffers_lock:
            line_count = len(_agent_output_buffers.get(key, deque()))
        cb = _circuit_breakers.get(key)
        circuit_state = cb["state"] if cb else None
        agents.append({
            "name": agent_name,
            "pid": proc.pid if proc else None,
            "alive": is_alive,
            "exit_code": exit_code,
            "output_lines": line_count,
            "started_at": _agent_started_at.get(key),
            "supports_stdin": bool(proc and proc.stdin),
            "circuit_state": circuit_state,
        })
    return {"project_id": project_id, "agents": agents}


# ---------------------------------------------------------------------------
# POST /agents/{project_id}/{agent_name}/stop — stop individual agent
# ---------------------------------------------------------------------------

@router.post("/agents/{project_id}/{agent_name}/stop", response_model=AgentStopOut,
             summary="Stop individual agent", responses={**_404, **_400})
async def stop_agent(project_id: int, agent_name: str, db: aiosqlite.Connection = Depends(get_db)):
    """Stop a specific agent subprocess."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail="Invalid agent name format")

    lock = _get_project_lock(project_id)
    async with lock:
        key = _agent_key(project_id, agent_name)
        proc = _agent_processes.get(key)
        if not proc:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

        def _stop_single_agent():
            # Signal drain threads to stop
            evt = _agent_drain_events.pop(key, None)
            if evt:
                evt.set()
            # Terminate process FIRST — unblocks drain threads on readline
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            # Now join drain threads — streams are closed so they'll exit quickly
            threads = _agent_drain_threads.pop(key, None)
            if threads:
                for t in threads:
                    t.join(timeout=3)
            _agent_processes.pop(key, None)
            _agent_line_counts.pop(key, None)
            # Don't remove agent output buffer or started_at — keep for viewing

        await asyncio.to_thread(_stop_single_agent)

        with _buffers_lock:
            buf = _project_output_buffers.setdefault(
                project_id, deque(maxlen=_MAX_OUTPUT_LINES),
            )
            buf.append(f"[{agent_name}] --- Agent stopped by user ---")

        logger.info("Stopped agent %s for project %d", agent_name, project_id)
        return {"agent": agent_name, "project_id": project_id, "status": "stopped"}


# ---------------------------------------------------------------------------
# POST /agents/{project_id}/{agent_name}/restart — restart a stopped agent
# ---------------------------------------------------------------------------

@router.post("/agents/{project_id}/{agent_name}/restart", response_model=AgentStopOut,
             summary="Restart individual agent", responses={**_404, **_400})
async def restart_agent(project_id: int, agent_name: str, db: aiosqlite.Connection = Depends(get_db)):
    """Restart a stopped agent without restarting the entire swarm.

    Re-reads the agent's prompt file, spawns a new process, and starts drain threads.
    Only works if the agent was previously launched (prompt file must exist).
    """
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail="Invalid agent name format")

    lock = _get_project_lock(project_id)
    async with lock:
        project = dict(row)
        folder = Path(project["folder_path"])
        key = _agent_key(project_id, agent_name)

        # Check if agent is currently alive — can't restart a running agent
        proc = _agent_processes.get(key)
        if proc and proc.poll() is None:
            raise HTTPException(status_code=400, detail=f"Agent {agent_name} is still running")

        # --- Quota enforcement: max_restarts_per_agent ---
        quota = await _get_project_quota(project_id)
        max_restarts = quota.get("max_restarts_per_agent")
        usage = _project_resource_usage.get(project_id, {})
        restart_counts = usage.get("restart_counts", {})
        current_restarts = restart_counts.get(agent_name, 0)
        if max_restarts is not None and current_restarts >= max_restarts:
            raise HTTPException(
                status_code=429,
                detail=f"Restart quota exceeded for {agent_name} (limit: {max_restarts}, used: {current_restarts})",
            )

        # --- Circuit breaker check ---
        cb_max = quota.get("circuit_breaker_max_failures")
        if cb_max is not None:
            cb_window = quota.get("circuit_breaker_window_seconds") or _CB_DEFAULT_WINDOW_SECONDS
            cb_recovery = quota.get("circuit_breaker_recovery_seconds") or _CB_DEFAULT_RECOVERY_SECONDS
            allowed, reason = _cb_check_restart_allowed(key, cb_max, cb_window, cb_recovery)
            if not allowed:
                raise HTTPException(status_code=429, detail=reason)
            cb = _get_circuit_breaker(key)
            if cb["state"] == "half-open":
                _cb_record_probe_start(key)

        # Read the agent's prompt file
        prompt_file = folder / ".claude" / "prompts" / f"{agent_name}.txt"
        if not prompt_file.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Prompt file not found for {agent_name} — agent may not have been launched previously",
            )
        try:
            prompt_text = prompt_file.read_text(encoding="utf-8-sig").strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read prompt file: {e}")
        if not prompt_text:
            raise HTTPException(status_code=400, detail=f"Empty prompt file for {agent_name}")

        # Find claude CLI
        try:
            claude_cmd = _find_claude_cmd()
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="claude CLI not found")

        # Clean up old process state for this agent
        old_evt = _agent_drain_events.pop(key, None)
        if old_evt:
            old_evt.set()
        old_threads = _agent_drain_threads.pop(key, None)
        if old_threads:
            for t in old_threads:
                t.join(timeout=2)
        _agent_processes.pop(key, None)

        # Spawn new process — strip CLAUDECODE env var to avoid nested session error
        spawn_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        popen_kwargs = dict(
            cwd=str(folder),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=spawn_env,
        )
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            process = subprocess.Popen(
                [*claude_cmd, "--print", "--output-format", "stream-json",
                 "--dangerously-skip-permissions", "--verbose", prompt_text],
                **popen_kwargs,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to spawn {agent_name}: {e}")

        # Set up log file
        log_dir = folder / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _agent_log_files[key] = log_dir / f"{agent_name}_{timestamp}.output.log"

        # Start drain threads
        stop_event = threading.Event()
        stdout_thread = threading.Thread(
            target=_drain_agent_stream,
            args=(project_id, agent_name, process.stdout, "stdout", stop_event),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_drain_agent_stream,
            args=(project_id, agent_name, process.stderr, "stderr", stop_event),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        # Register in tracking dicts
        _agent_processes[key] = process
        _agent_drain_events[key] = stop_event
        _agent_drain_threads[key] = [stdout_thread, stderr_thread]
        _agent_started_at[key] = datetime.now().isoformat()
        _agent_line_counts[key] = 0  # Reset line count for milestone tracking

        with _buffers_lock:
            _agent_output_buffers.setdefault(key, deque(maxlen=_MAX_OUTPUT_LINES))
            buf = _project_output_buffers.setdefault(
                project_id, deque(maxlen=_MAX_OUTPUT_LINES),
            )
            buf.append(f"[{agent_name}] --- Agent restarted (pid={process.pid}) ---")

        # Track restart count for quota enforcement
        usage = _project_resource_usage.setdefault(project_id, {"agent_count": 0, "restart_counts": {}, "started_at": time.time()})
        usage["restart_counts"][agent_name] = usage["restart_counts"].get(agent_name, 0) + 1

        _record_event_sync(project_id, agent_name, "agent_restarted", f"pid={process.pid}")

        logger.info("Restarted agent %s (pid=%d) for project %d", agent_name, process.pid, project_id)
        return {"agent": agent_name, "project_id": project_id, "status": "restarted"}


# ---------------------------------------------------------------------------
# GET /agents/{project_id}/metrics — CPU/memory per agent process
# ---------------------------------------------------------------------------

@router.get("/agents/{project_id}/metrics", response_model=AgentMetricsOut,
            summary="Get agent process metrics", responses=_404)
async def agent_metrics(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get CPU and memory usage per agent process. Requires psutil (optional dep)."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    keys = sorted(_project_agent_keys(project_id))
    agents = []

    for key in keys:
        agent_name = key.split(":")[1]
        proc = _agent_processes.get(key)
        is_alive = proc is not None and proc.poll() is None

        metric = {
            "name": agent_name,
            "pid": proc.pid if proc else None,
            "alive": is_alive,
            "cpu_percent": None,
            "memory_mb": None,
            "memory_percent": None,
            "threads": None,
            "uptime_seconds": None,
        }

        _ps = _get_psutil()
        if is_alive and _PSUTIL_AVAILABLE and proc and _ps:
            try:
                p = _ps.Process(proc.pid)
                mem = p.memory_info()
                metric["cpu_percent"] = round(p.cpu_percent(interval=0), 1)
                metric["memory_mb"] = round(mem.rss / (1024 * 1024), 1)
                metric["memory_percent"] = round(p.memory_percent(), 1)
                metric["threads"] = p.num_threads()
                metric["uptime_seconds"] = int(time.time() - p.create_time())
            except (_ps.NoSuchProcess, _ps.AccessDenied, _ps.ZombieProcess):
                pass
        elif is_alive and not _PSUTIL_AVAILABLE:
            # Calculate uptime from our tracked start time
            started = _agent_started_at.get(key)
            if started:
                try:
                    start_dt = datetime.fromisoformat(started)
                    metric["uptime_seconds"] = int((datetime.now() - start_dt).total_seconds())
                except (ValueError, TypeError):
                    pass

        agents.append(metric)

    return {"project_id": project_id, "agents": agents, "psutil_available": _PSUTIL_AVAILABLE}


# ---------------------------------------------------------------------------
# GET /agents/{project_id}/{agent_name}/logs — per-agent log file retrieval
# ---------------------------------------------------------------------------

@router.get("/agents/{project_id}/{agent_name}/logs", response_model=AgentLogLinesOut,
            summary="Get agent output log", responses=_404)
async def agent_logs(
    project_id: int,
    agent_name: str,
    lines: int = Query(default=100, ge=1, le=5000, description="Number of lines to return"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return the last N lines from an agent's output log file.

    Falls back to the in-memory buffer if no log file exists.
    """
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail=f"Invalid agent name: {agent_name}")

    key = _agent_key(project_id, agent_name)

    # Try reading from the persistent log file first
    log_path = _agent_log_files.get(key)
    log_file_str = None
    result_lines: list[str] = []

    if log_path and log_path.exists():
        log_file_str = str(log_path)
        try:
            # Read the file and take the last N lines efficiently
            def _read_tail():
                tail: deque[str] = deque(maxlen=lines)
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        tail.append(line.rstrip("\n"))
                return list(tail)

            result_lines = await asyncio.to_thread(_read_tail)
        except OSError:
            logger.debug("Failed to read log file %s", log_path, exc_info=True)

    # Fall back to in-memory buffer
    if not result_lines:
        with _buffers_lock:
            buf = _agent_output_buffers.get(key, deque())
            total = len(buf)
            # Take last N lines from deque
            start = max(0, total - lines)
            result_lines = list(itertools.islice(buf, start, total))

    return {
        "project_id": project_id,
        "agent": agent_name,
        "lines": result_lines,
        "total_lines": len(result_lines),
        "log_file": log_file_str,
    }


# ---------------------------------------------------------------------------
# PATCH /runs/{run_id} — annotate/label a swarm run
# ---------------------------------------------------------------------------

class SwarmRunUpdate(BaseModel):
    """Update annotations on a completed swarm run."""
    label: Optional[str] = Field(None, max_length=100, description="Short label/tag for the run")
    notes: Optional[str] = Field(None, max_length=5000, description="Detailed notes about the run")


@router.patch("/runs/{run_id}", response_model=SwarmRunAnnotationOut,
              summary="Annotate swarm run",
              responses={404: {"model": ErrorDetail, "description": "Run not found"}})
async def annotate_run(run_id: int, update: SwarmRunUpdate, db: aiosqlite.Connection = Depends(get_db)):
    """Add or update label and notes on a swarm run."""
    row = await (await db.execute(
        "SELECT id, project_id, status, label, notes FROM swarm_runs WHERE id = ?", (run_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Swarm run not found")

    fields = {}
    if update.label is not None:
        fields["label"] = sanitize_string(update.label)
    if update.notes is not None:
        fields["notes"] = sanitize_string(update.notes)

    if not fields:
        return dict(row)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [run_id]
    await db.execute(f"UPDATE swarm_runs SET {set_clause} WHERE id = ?", values)
    await db.commit()

    updated = await (await db.execute(
        "SELECT id, project_id, status, label, notes FROM swarm_runs WHERE id = ?", (run_id,)
    )).fetchone()
    return dict(updated)


# ---------------------------------------------------------------------------
# GET /export/{project_id} — export run output as downloadable file
# ---------------------------------------------------------------------------

@router.get("/export/{project_id}", summary="Export swarm output", responses=_404)
async def export_output(
    project_id: int,
    format: str = Query(default="text", description="Export format: 'text' or 'json'"),
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Export the current output buffer as a downloadable text or JSON file."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)

    with _buffers_lock:
        if agent:
            key = _agent_key(project_id, agent)
            buf = _agent_output_buffers.get(key, deque())
        else:
            buf = _project_output_buffers.get(project_id, deque())
        lines = list(buf)

    project_name = project.get("name", "project").replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    agent_suffix = f"_{agent}" if agent else ""

    if format == "json":
        content = json.dumps({
            "project_id": project_id,
            "project_name": project.get("name"),
            "agent": agent,
            "exported_at": datetime.now().isoformat(),
            "line_count": len(lines),
            "lines": lines,
        }, indent=2)
        filename = f"{project_name}{agent_suffix}_{timestamp}.json"
        media_type = "application/json"
    else:
        content = "\n".join(lines) + "\n" if lines else ""
        filename = f"{project_name}{agent_suffix}_{timestamp}.txt"
        media_type = "text/plain"

    from starlette.responses import Response
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# GET /output/{project_id} — paginated output with optional agent filter
# ---------------------------------------------------------------------------

@router.get("/output/{project_id}", response_model=SwarmOutputOut,
            summary="Get swarm output", responses=_404)
async def swarm_output(
    project_id: int,
    offset: int = 0,
    limit: int = 200,
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get captured output from agents. Use ?agent=Claude-1 for per-agent view."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    limit = min(max(limit, 1), _MAX_OUTPUT_LINES)
    offset = max(offset, 0)

    with _buffers_lock:
        if agent:
            key = _agent_key(project_id, agent)
            buf = _agent_output_buffers.get(key, deque())
        else:
            buf = _project_output_buffers.get(project_id, deque())
        total = len(buf)
        # Use itertools.islice to avoid full list copy (O(offset+limit) vs O(n))
        lines = list(itertools.islice(buf, offset, offset + limit))

    return {
        "project_id": project_id,
        "offset": offset,
        "limit": limit,
        "total": total,
        "next_offset": offset + len(lines),
        "has_more": offset + len(lines) < total,
        "lines": lines,
        "agent": agent,
    }


# ---------------------------------------------------------------------------
# GET /output/{project_id}/tail — last N lines of combined output
# ---------------------------------------------------------------------------

@router.get("/output/{project_id}/tail", response_model=OutputTailOut,
            summary="Tail swarm output", responses=_404)
async def swarm_output_tail(
    project_id: int,
    lines: int = Query(default=50, ge=1, le=5000, description="Number of tail lines"),
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return the last N lines from the output buffer (efficient for large buffers)."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    with _buffers_lock:
        if agent:
            key = _agent_key(project_id, agent)
            buf = _agent_output_buffers.get(key, deque())
        else:
            buf = _project_output_buffers.get(project_id, deque())
        total = len(buf)
        # Take last N lines efficiently: islice from (total - lines) to end
        start = max(0, total - lines)
        tail_lines = list(itertools.islice(buf, start, total))

    return {
        "project_id": project_id,
        "lines": tail_lines,
        "total": total,
        "agent": agent,
    }


# ---------------------------------------------------------------------------
# GET /output/{project_id}/stream — SSE
# ---------------------------------------------------------------------------

@router.get("/output/{project_id}/stream", summary="Stream swarm output",
            responses=_404)
async def swarm_output_stream(
    project_id: int,
    request: Request,
    agent: Optional[str] = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
):
    """SSE endpoint for real-time output streaming, optionally filtered by agent."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    async def event_generator():
        offset = 0
        # Track consecutive idle polls with no agents alive to avoid
        # premature 'done' — drain threads may still be flushing output
        idle_no_agents = 0
        while True:
            if await request.is_disconnected():
                break
            with _buffers_lock:
                if agent:
                    key = _agent_key(project_id, agent)
                    buf = _agent_output_buffers.get(key, deque())
                else:
                    buf = _project_output_buffers.get(project_id, deque())
                # Use itertools.islice to avoid full list copy
                buf_len = len(buf)
                new_lines = list(itertools.islice(buf, offset, None)) if buf_len > offset else []
            if new_lines:
                for line in new_lines:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                offset = buf_len
                idle_no_agents = 0
            else:
                if not _any_agent_alive(project_id):
                    # Require 5 consecutive idle polls (2.5s) before sending done
                    # to give drain threads time to flush remaining output
                    idle_no_agents += 1
                    if idle_no_agents >= 5:
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                else:
                    idle_no_agents = 0
                yield f": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# GET /history/{project_id}
# ---------------------------------------------------------------------------

@router.get("/history/{project_id}", response_model=SwarmHistoryOut,
            summary="Get swarm history", responses=_404)
async def swarm_history(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get history of swarm runs for a project."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    rows = await (await db.execute(
        """SELECT id, project_id, started_at, ended_at, status, phase,
                  tasks_completed, task_summary, label, notes, summary,
                  guardrail_results
           FROM swarm_runs WHERE project_id = ? ORDER BY started_at DESC, id DESC""",
        (project_id,),
    )).fetchall()

    runs = []
    for r in rows:
        run = dict(r)
        if run["started_at"] and run["ended_at"]:
            try:
                start = datetime.fromisoformat(run["started_at"])
                end = datetime.fromisoformat(run["ended_at"])
                run["duration_seconds"] = int((end - start).total_seconds())
            except (ValueError, TypeError):
                run["duration_seconds"] = None
        else:
            run["duration_seconds"] = None
        # Parse summary JSON if present
        if run.get("summary") and isinstance(run["summary"], str):
            try:
                run["summary"] = json.loads(run["summary"])
            except (json.JSONDecodeError, TypeError):
                run["summary"] = None
        # Parse guardrail_results JSON if present
        if run.get("guardrail_results") and isinstance(run["guardrail_results"], str):
            try:
                run["guardrail_results"] = json.loads(run["guardrail_results"])
            except (json.JSONDecodeError, TypeError):
                run["guardrail_results"] = None
        runs.append(run)

    return {"project_id": project_id, "runs": runs}


# ---------------------------------------------------------------------------
# GET /events/{project_id} — agent event log
# ---------------------------------------------------------------------------

@router.get("/events/{project_id}", response_model=AgentEventsListOut,
            summary="Get agent events", responses=_404)
async def get_agent_events(
    project_id: int,
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    from_ts: Optional[str] = Query(default=None, alias="from", description="From ISO timestamp"),
    to_ts: Optional[str] = Query(default=None, alias="to", description="To ISO timestamp"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get agent lifecycle events with optional filters."""
    row = await (await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    conditions = ["project_id = ?"]
    params: list = [project_id]

    if agent:
        conditions.append("agent_name = ?")
        params.append(agent)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if from_ts:
        conditions.append("timestamp >= ?")
        params.append(from_ts)
    if to_ts:
        conditions.append("timestamp <= ?")
        params.append(to_ts)

    where = " AND ".join(conditions)

    # Count total matches
    count_row = await (await db.execute(
        f"SELECT COUNT(*) as cnt FROM agent_events WHERE {where}", params,
    )).fetchone()
    total = count_row["cnt"]

    # Fetch paginated results, newest first
    rows = await (await db.execute(
        f"SELECT * FROM agent_events WHERE {where} ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )).fetchall()

    events = [dict(r) for r in rows]
    return {"project_id": project_id, "events": events, "total": total}


# ---------------------------------------------------------------------------
# GET /output/{project_id}/search — search output buffers
# ---------------------------------------------------------------------------

@router.get("/output/{project_id}/search", response_model=OutputSearchOut,
            summary="Search swarm output", responses=_404)
async def search_output(
    project_id: int,
    q: str = Query(description="Search query (regex supported)"),
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    context: int = Query(default=3, ge=0, le=10, description="Context lines before/after"),
    limit: int = Query(default=50, ge=1, le=200, description="Max matches to return"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Search through output buffers with regex support and context lines."""
    row = await (await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate regex complexity to prevent catastrophic backtracking (ReDoS)
    if len(q) > 200:
        raise HTTPException(status_code=400, detail="Search pattern too long (max 200 chars)")
    try:
        pattern = re.compile(q, re.IGNORECASE)
    except re.error:
        raise HTTPException(status_code=400, detail="Invalid regex pattern")

    with _buffers_lock:
        if agent:
            key = _agent_key(project_id, agent)
            buf = list(_agent_output_buffers.get(key, deque()))
        else:
            buf = list(_project_output_buffers.get(project_id, deque()))

    def _do_search():
        results = []
        for i, line in enumerate(buf):
            if len(results) >= limit:
                break
            if pattern.search(line):
                # Extract agent name from prefixed lines
                line_agent = None
                if line.startswith("[") and "] " in line:
                    bracket_end = line.index("] ")
                    line_agent = line[1:bracket_end]

                ctx_before = buf[max(0, i - context):i]
                ctx_after = buf[i + 1:i + 1 + context]

                results.append({
                    "line_number": i,
                    "text": line,
                    "agent": line_agent,
                    "context_before": ctx_before,
                    "context_after": ctx_after,
                })
        return results

    # Run search in a thread with timeout to prevent ReDoS
    try:
        matches = await asyncio.wait_for(
            asyncio.to_thread(_do_search), timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=400, detail="Search pattern too complex (timed out)")

    return {
        "project_id": project_id,
        "query": q,
        "total_matches": len(matches),
        "matches": matches,
    }


# ---------------------------------------------------------------------------
# GET /runs/compare — compare two swarm runs side-by-side
# ---------------------------------------------------------------------------

@router.get("/runs/compare", response_model=RunComparisonOut,
            summary="Compare two swarm runs")
async def compare_runs(
    run_a: int = Query(description="First run ID"),
    run_b: int = Query(description="Second run ID"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Compare two swarm runs side-by-side with delta calculations."""
    row_a = await (await db.execute(
        "SELECT * FROM swarm_runs WHERE id = ?", (run_a,)
    )).fetchone()
    if not row_a:
        raise HTTPException(status_code=404, detail=f"Run {run_a} not found")
    row_b = await (await db.execute(
        "SELECT * FROM swarm_runs WHERE id = ?", (run_b,)
    )).fetchone()
    if not row_b:
        raise HTTPException(status_code=404, detail=f"Run {run_b} not found")

    def _run_side(row):
        run = dict(row)
        duration = None
        if run["started_at"] and run.get("ended_at"):
            try:
                start = datetime.fromisoformat(run["started_at"])
                end = datetime.fromisoformat(run["ended_at"])
                duration = int((end - start).total_seconds())
            except (ValueError, TypeError):
                pass

        # Extract data from summary if available
        summary = {}
        if run.get("summary"):
            try:
                summary = json.loads(run["summary"])
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "run_id": run["id"],
            "status": run["status"],
            "duration_seconds": duration,
            "agent_count": summary.get("agent_count", 0),
            "output_lines": summary.get("total_output_lines", 0),
            "error_count": summary.get("error_count", 0),
        }

    side_a = _run_side(row_a)
    side_b = _run_side(row_b)

    dur_a = side_a["duration_seconds"]
    dur_b = side_b["duration_seconds"]
    duration_delta = (dur_b - dur_a) if dur_a is not None and dur_b is not None else None

    return {
        "run_a": side_a,
        "run_b": side_b,
        "duration_delta_seconds": duration_delta,
        "agent_count_delta": side_b["agent_count"] - side_a["agent_count"],
        "output_lines_delta": side_b["output_lines"] - side_a["output_lines"],
        "error_count_delta": side_b["error_count"] - side_a["error_count"],
    }


# ---------------------------------------------------------------------------
# Directive system — filesystem-based agent direction
# ---------------------------------------------------------------------------

class DirectiveRequest(BaseModel):
    """Send a directive to a running agent."""
    text: str = Field(min_length=1, max_length=5000, description="Directive text for the agent")
    priority: str = Field(default="normal", pattern="^(normal|urgent)$", description="normal or urgent")


@router.post("/agents/{project_id}/{agent_name}/directive", response_model=DirectiveOut,
             summary="Send directive to agent", responses={**_404, **_400})
async def send_directive(
    project_id: int, agent_name: str, req: DirectiveRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Send a directive to an agent via the filesystem.

    Normal priority: writes directive file for agent to pick up on next task check.
    Urgent priority: writes directive, stops agent, prepends to prompt, restarts.
    """
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail="Invalid agent name format")

    project = dict(row)
    folder = Path(project["folder_path"])

    # Verify agent exists in our tracking
    key = _agent_key(project_id, agent_name)
    proc = _agent_processes.get(key)
    if not proc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Write directive file
    directives_dir = folder / ".claude" / "directives"
    directives_dir.mkdir(parents=True, exist_ok=True)
    directive_file = directives_dir / f"{agent_name}.directive"

    sanitized_text = sanitize_string(req.text)
    directive_content = f"PRIORITY: {req.priority}\nQUEUED_AT: {datetime.now().isoformat()}\n\n{sanitized_text}"

    # Atomic write: write to .tmp then rename
    tmp_file = directive_file.with_suffix(".directive.tmp")
    try:
        tmp_file.write_text(directive_content, encoding="utf-8")
        tmp_file.replace(directive_file)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write directive: {e}")

    # Emit directive_queued event
    await _record_event_async(
        project_id, agent_name, "directive_queued",
        f"priority={req.priority}, length={len(sanitized_text)}",
    )

    # For urgent priority: stop + modify prompt + restart
    if req.priority == "urgent" and proc.poll() is None:
        # Prepend directive to prompt file
        prompt_file = folder / ".claude" / "prompts" / f"{agent_name}.txt"
        if prompt_file.exists():
            try:
                original = prompt_file.read_text(encoding="utf-8-sig")
                prompt_file.write_text(
                    f"URGENT DIRECTIVE (override current task):\n{sanitized_text}\n\n"
                    f"---\n\n{original}",
                    encoding="utf-8",
                )
            except OSError:
                logger.debug("Failed to prepend directive to prompt for %s", agent_name)

        # Stop the agent
        def _stop():
            evt = _agent_drain_events.pop(key, None)
            if evt:
                evt.set()
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            threads = _agent_drain_threads.pop(key, None)
            if threads:
                for t in threads:
                    t.join(timeout=3)
            _agent_processes.pop(key, None)

        await asyncio.to_thread(_stop)

        # Restart the agent with the modified prompt
        try:
            prompt_text = prompt_file.read_text(encoding="utf-8-sig").strip()
            claude_cmd = _find_claude_cmd()
            spawn_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            popen_kwargs = dict(
                cwd=str(folder),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=spawn_env,
            )
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            new_proc = subprocess.Popen(
                [*claude_cmd, "--print", "--output-format", "stream-json",
                 "--dangerously-skip-permissions", "--verbose", prompt_text],
                **popen_kwargs,
            )
            # Set up drain threads
            stop_event = threading.Event()
            for stream_name, stream_obj in [("stdout", new_proc.stdout), ("stderr", new_proc.stderr)]:
                t = threading.Thread(
                    target=_drain_agent_stream,
                    args=(project_id, agent_name, stream_obj, stream_name, stop_event),
                    daemon=True,
                )
                t.start()
                _agent_drain_threads.setdefault(key, []).append(t)
            _agent_processes[key] = new_proc
            _agent_drain_events[key] = stop_event
            _agent_started_at[key] = datetime.now().isoformat()
            _agent_line_counts[key] = 0  # Reset line count for milestone tracking

            # Set up log file
            log_dir = folder / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            _agent_log_files[key] = log_dir / f"{agent_name}_{ts}.output.log"

            with _buffers_lock:
                buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
                buf.append(f"[{agent_name}] --- Restarted with urgent directive (pid={new_proc.pid}) ---")
        except Exception as e:
            logger.error("Failed to restart %s after urgent directive: %s", agent_name, e)
            # The directive file is still there; don't fail the request
            with _buffers_lock:
                buf = _project_output_buffers.setdefault(project_id, deque(maxlen=_MAX_OUTPUT_LINES))
                buf.append(f"[{agent_name}] WARNING: Urgent directive written but restart failed: {e}")

    # Remove the directive file after urgent processing (agent consumed it via restart)
    if req.priority == "urgent" and directive_file.exists():
        try:
            directive_file.unlink()
        except OSError:
            pass

    logger.info("Directive sent to %s for project %d (priority=%s)", agent_name, project_id, req.priority)
    return {"agent": agent_name, "project_id": project_id, "status": "queued", "priority": req.priority}


@router.get("/agents/{project_id}/{agent_name}/directive", response_model=DirectiveStatusOut,
            summary="Check pending directive", responses=_404)
async def get_directive_status(
    project_id: int, agent_name: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Check if a pending directive exists for an agent."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail="Invalid agent name format")

    project = dict(row)
    folder = Path(project["folder_path"])
    directive_file = folder / ".claude" / "directives" / f"{agent_name}.directive"

    if directive_file.exists():
        try:
            content = directive_file.read_text(encoding="utf-8")
            # Parse queued_at from directive content
            queued_at = None
            text_lines = []
            for line in content.splitlines():
                if line.startswith("QUEUED_AT: "):
                    queued_at = line[len("QUEUED_AT: "):]
                elif not line.startswith("PRIORITY: ") and line != "":
                    text_lines.append(line)
            return {"pending": True, "text": "\n".join(text_lines).strip(), "queued_at": queued_at}
        except OSError:
            pass

    return {"pending": False, "text": None, "queued_at": None}


# ---------------------------------------------------------------------------
# PUT /agents/{project_id}/{agent_name}/prompt — hot-swap prompt
# ---------------------------------------------------------------------------

class PromptUpdateRequest(BaseModel):
    """Update an agent's prompt text."""
    prompt: str = Field(min_length=1, max_length=100000, description="New prompt text for the agent")


@router.put("/agents/{project_id}/{agent_name}/prompt", response_model=PromptUpdateOut,
            summary="Update agent prompt", responses={**_404, **_400})
async def update_prompt(
    project_id: int, agent_name: str,
    req: PromptUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Overwrite an agent's prompt file. Does NOT restart the agent.

    Returns the old prompt content for undo capability.
    """
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if not _validate_agent_name(agent_name):
        raise HTTPException(status_code=400, detail="Invalid agent name format")

    new_prompt = req.prompt

    project = dict(row)
    folder = Path(project["folder_path"])
    prompt_file = folder / ".claude" / "prompts" / f"{agent_name}.txt"

    if not prompt_file.exists():
        raise HTTPException(status_code=404, detail=f"Prompt file not found for {agent_name}")

    try:
        old_prompt = prompt_file.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to read prompt: {e}")

    # Sanitize and write
    sanitized = sanitize_string(new_prompt)
    try:
        prompt_file.write_text(sanitized, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write prompt: {e}")

    # Emit event
    await _record_event_async(
        project_id, agent_name, "prompt_modified",
        f"length={len(sanitized)}",
    )

    logger.info("Prompt updated for %s in project %d", agent_name, project_id)
    return {
        "agent": agent_name,
        "project_id": project_id,
        "old_prompt": old_prompt,
        "status": "updated",
    }


# ---------------------------------------------------------------------------
# GET /projects/{id}/quota — resource quota config + live usage
# ---------------------------------------------------------------------------

@router.get("/{project_id}/quota", response_model=QuotaOut,
            summary="Get quota config and usage", responses=_404)
async def get_project_quota_endpoint(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Return resource quota configuration and current live usage for a project."""
    # Note: this endpoint is under /api/swarm/{project_id}/quota since the router prefix is /api/swarm
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    quota = await _get_project_quota(project_id)
    usage = _project_resource_usage.get(project_id, {})

    elapsed_hours = None
    started_at_str = None
    if usage.get("started_at"):
        elapsed_hours = round((time.time() - usage["started_at"]) / 3600, 2)
        started_at_str = datetime.fromtimestamp(usage["started_at"]).isoformat()

    return {
        "project_id": project_id,
        "quota": {
            "max_agents_concurrent": quota.get("max_agents_concurrent"),
            "max_duration_hours": quota.get("max_duration_hours"),
            "max_restarts_per_agent": quota.get("max_restarts_per_agent"),
        },
        "usage": {
            "agent_count": usage.get("agent_count", 0),
            "restart_counts": usage.get("restart_counts", {}),
            "started_at": started_at_str,
            "elapsed_hours": elapsed_hours,
        },
    }


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/checkpoints — agent checkpoint timeline
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/checkpoints", response_model=CheckpointsListOut,
            summary="Get agent checkpoints for a run", responses=_404)
async def get_run_checkpoints(
    run_id: int,
    agent: Optional[str] = Query(None, description="Filter by agent name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Return chronological checkpoint list for a swarm run."""
    # Verify run exists
    run_row = await (await db.execute(
        "SELECT id FROM swarm_runs WHERE id = ?", (run_id,)
    )).fetchone()
    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")

    if agent:
        rows = await (await db.execute(
            "SELECT * FROM agent_checkpoints WHERE run_id = ? AND agent_name = ? ORDER BY timestamp ASC",
            (run_id, agent),
        )).fetchall()
    else:
        rows = await (await db.execute(
            "SELECT * FROM agent_checkpoints WHERE run_id = ? ORDER BY timestamp ASC",
            (run_id,),
        )).fetchall()

    checkpoints = []
    for r in rows:
        data = {}
        try:
            data = json.loads(r["data"]) if r["data"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        checkpoints.append({
            "id": r["id"],
            "project_id": r["project_id"],
            "run_id": r["run_id"],
            "agent_name": r["agent_name"],
            "checkpoint_type": r["checkpoint_type"],
            "data": data,
            "timestamp": r["timestamp"],
        })

    return {"run_id": run_id, "checkpoints": checkpoints, "total": len(checkpoints)}
