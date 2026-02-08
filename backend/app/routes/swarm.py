import asyncio
import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field
import aiosqlite
from ..database import get_db

logger = logging.getLogger("latent.swarm")


def _pid_alive(pid: int | None) -> bool:
    """Check if a process with the given PID is still running."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
        return True
    except (OSError, ProcessLookupError):
        return False

router = APIRouter(prefix="/api/swarm", tags=["swarm"])

# In-memory output buffers for swarm processes, keyed by project_id
_output_buffers: dict[int, list[str]] = {}
_buffers_lock = threading.Lock()
_MAX_OUTPUT_LINES = 500

# Track background drain threads for cleanup on stop/shutdown
_drain_threads: dict[int, list[threading.Thread]] = {}
_drain_stop_events: dict[int, threading.Event] = {}


async def cancel_drain_tasks(project_id: int | None = None):
    """Signal drain threads to stop. If project_id is None, stop all."""
    if project_id is not None:
        evt = _drain_stop_events.pop(project_id, None)
        if evt:
            evt.set()
        _drain_threads.pop(project_id, None)
        return
    for evt in _drain_stop_events.values():
        evt.set()
    _drain_stop_events.clear()
    _drain_threads.clear()


def _drain_stream_sync(project_id: int, stream, label: str, stop_event: threading.Event):
    """Read lines from a subprocess stream in a background thread."""
    try:
        for line in iter(stream.readline, b""):
            if stop_event.is_set():
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            with _buffers_lock:
                buf = _output_buffers.setdefault(project_id, [])
                buf.append(f"[{label}] {text}")
                if len(buf) > _MAX_OUTPUT_LINES:
                    del buf[: len(buf) - _MAX_OUTPUT_LINES]
    except Exception:
        logger.error("_drain_stream failed for project %d [%s]", project_id, label, exc_info=True)
    finally:
        stream.close()


class SwarmLaunchRequest(BaseModel):
    project_id: int
    resume: bool = False
    no_confirm: bool = True
    agent_count: int = Field(default=4, ge=1, le=16)
    max_phases: int = Field(default=24, ge=1, le=24)


class SwarmStopRequest(BaseModel):
    project_id: int


@router.post("/launch")
async def launch_swarm(req: SwarmLaunchRequest, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (req.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])
    swarm_script = folder / "swarm.ps1"

    if not swarm_script.exists():
        raise HTTPException(status_code=400, detail="swarm.ps1 not found in project folder")

    args = [
        "powershell", "-ExecutionPolicy", "Bypass", "-File", str(swarm_script),
    ]
    if req.resume:
        args.append("-Resume")
    if req.no_confirm:
        args.append("-NoConfirm")
    args += [
        "-AgentCount", str(req.agent_count),
        "-MaxPhases", str(req.max_phases),
    ]

    # Use subprocess.Popen instead of asyncio.create_subprocess_exec because
    # uvicorn's reloader on Windows uses SelectorEventLoop which doesn't
    # support async subprocesses (NotImplementedError).
    process = subprocess.Popen(
        args,
        cwd=str(folder),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Cancel any existing drain threads for this project, then start new ones
    await cancel_drain_tasks(req.project_id)
    with _buffers_lock:
        _output_buffers[req.project_id] = []
    stop_event = threading.Event()
    _drain_stop_events[req.project_id] = stop_event
    stdout_thread = threading.Thread(
        target=_drain_stream_sync, args=(req.project_id, process.stdout, "stdout", stop_event), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_drain_stream_sync, args=(req.project_id, process.stderr, "stderr", stop_event), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    _drain_threads[req.project_id] = [stdout_thread, stderr_thread]

    await db.execute(
        "UPDATE projects SET status = 'running', swarm_pid = ?, updated_at = datetime('now') WHERE id = ?",
        (process.pid, req.project_id),
    )
    await db.commit()

    # Record swarm run in history
    await db.execute(
        "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
        (req.project_id,),
    )
    await db.commit()

    logger.info("Swarm launched for project %d (pid=%d)", req.project_id, process.pid)
    return {"status": "launched", "pid": process.pid, "project_id": req.project_id}


@router.post("/stop")
async def stop_swarm(req: SwarmStopRequest, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (req.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])
    stop_script = folder / "stop-swarm.ps1"

    # Signal drain threads to stop and wait briefly for final output
    evt = _drain_stop_events.pop(req.project_id, None)
    if evt:
        evt.set()
    threads = _drain_threads.pop(req.project_id, None)
    if threads:
        for t in threads:
            t.join(timeout=2)
    with _buffers_lock:
        _output_buffers.pop(req.project_id, None)

    if stop_script.exists():
        process = subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(stop_script)],
            cwd=str(folder),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("stop-swarm.ps1 timed out after 30s for project %d, killing", req.project_id)
            process.kill()

    await db.execute(
        "UPDATE projects SET status = 'stopped', swarm_pid = NULL, updated_at = datetime('now') WHERE id = ?",
        (req.project_id,),
    )
    await db.commit()

    # Close any open swarm run in history
    await db.execute(
        """UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped'
           WHERE project_id = ? AND status = 'running'""",
        (req.project_id,),
    )
    await db.commit()

    logger.info("Swarm stopped for project %d", req.project_id)
    return {"status": "stopped", "project_id": req.project_id}


@router.get("/status/{project_id}")
async def swarm_status(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = dict(row)
    folder = Path(project["folder_path"])

    # Check if stored PID is still alive; auto-correct stale "running" status
    if project["status"] == "running" and not _pid_alive(project.get("swarm_pid")):
        logger.warning("Stale PID %s for project %d, auto-correcting to stopped", project.get("swarm_pid"), project_id)
        await db.execute(
            "UPDATE projects SET status = 'stopped', swarm_pid = NULL, updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        # Close orphaned swarm_runs that are still marked as running
        await db.execute(
            "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'crashed' "
            "WHERE project_id = ? AND status = 'running'",
            (project_id,),
        )
        await db.commit()
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
        "process_alive": _pid_alive(project.get("swarm_pid")),
        "agents": agents,
        "signals": signals,
        "tasks": task_progress,
        "phase": phase_info,
    }


@router.get("/output/{project_id}")
async def swarm_output(project_id: int, offset: int = 0, db: aiosqlite.Connection = Depends(get_db)):
    """Get captured stdout/stderr from the swarm process."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    with _buffers_lock:
        buf = _output_buffers.get(project_id, [])
        lines = buf[offset:]
    return {
        "project_id": project_id,
        "offset": offset,
        "next_offset": offset + len(lines),
        "lines": lines,
    }


@router.get("/output/{project_id}/stream")
async def swarm_output_stream(project_id: int, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """SSE endpoint for real-time swarm output streaming."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    async def event_generator():
        offset = 0
        while True:
            if await request.is_disconnected():
                break
            with _buffers_lock:
                buf = _output_buffers.get(project_id, [])
                new_lines = buf[offset:]
                buf_len = len(buf)
            if new_lines:
                for line in new_lines:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                offset = buf_len
            else:
                # If no active drain threads (swarm not running), we're done
                threads = _drain_threads.get(project_id, [])
                if not threads or not any(t.is_alive() for t in threads):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                yield f": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history/{project_id}")
async def swarm_history(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get history of swarm runs for a project."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    rows = await (await db.execute(
        """SELECT id, project_id, started_at, ended_at, status, phase, tasks_completed, task_summary
           FROM swarm_runs WHERE project_id = ? ORDER BY started_at DESC, id DESC""",
        (project_id,),
    )).fetchall()

    runs = []
    for r in rows:
        run = dict(r)
        # Calculate duration in seconds if both timestamps exist
        if run["started_at"] and run["ended_at"]:
            try:
                start = datetime.fromisoformat(run["started_at"])
                end = datetime.fromisoformat(run["ended_at"])
                run["duration_seconds"] = int((end - start).total_seconds())
            except (ValueError, TypeError):
                run["duration_seconds"] = None
        else:
            run["duration_seconds"] = None
        runs.append(run)

    return {"project_id": project_id, "runs": runs}
