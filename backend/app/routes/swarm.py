import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse
from pydantic import BaseModel
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
_MAX_OUTPUT_LINES = 500

# Track background drain tasks for cancellation on stop/shutdown
_drain_tasks: dict[int, list[asyncio.Task]] = {}


async def cancel_drain_tasks(project_id: int | None = None):
    """Cancel drain tasks. If project_id is None, cancel all."""
    if project_id is not None:
        tasks = _drain_tasks.pop(project_id, [])
        for t in tasks:
            t.cancel()
        return
    for pid, tasks in _drain_tasks.items():
        for t in tasks:
            t.cancel()
    _drain_tasks.clear()


async def _drain_stream(project_id: int, stream: asyncio.StreamReader, label: str):
    """Read lines from a subprocess stream and store them."""
    buf = _output_buffers.setdefault(project_id, [])
    try:
        async for line in stream:
            text = line.decode("utf-8", errors="replace").rstrip()
            buf.append(f"[{label}] {text}")
            if len(buf) > _MAX_OUTPUT_LINES:
                del buf[: len(buf) - _MAX_OUTPUT_LINES]
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.error("_drain_stream failed for project %d [%s]", project_id, label, exc_info=True)


class SwarmLaunchRequest(BaseModel):
    project_id: int
    resume: bool = False
    no_confirm: bool = True
    agent_count: int = 4
    max_phases: int = 3


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

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(folder),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Cancel any existing drain tasks for this project, then start new ones
    await cancel_drain_tasks(req.project_id)
    _output_buffers[req.project_id] = []
    _drain_tasks[req.project_id] = [
        asyncio.create_task(_drain_stream(req.project_id, process.stdout, "stdout")),
        asyncio.create_task(_drain_stream(req.project_id, process.stderr, "stderr")),
    ]

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

    # Cancel drain tasks and clean up output buffer for this project
    await cancel_drain_tasks(req.project_id)
    _output_buffers.pop(req.project_id, None)

    if stop_script.exists():
        process = await asyncio.create_subprocess_exec(
            "powershell", "-ExecutionPolicy", "Bypass", "-File", str(stop_script),
            cwd=str(folder),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except asyncio.TimeoutError:
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
        content = tasks_file.read_text()
        total = len(re.findall(r"- \[[ x]\]", content))
        done = len(re.findall(r"- \[x\]", content))
        task_progress = {
            "total": total,
            "done": done,
            "percent": round((done / total) * 100, 1) if total > 0 else 0,
        }

    # Read phase info
    phase_info = None
    phase_file = folder / ".claude" / "swarm-phase.json"
    if phase_file.exists():
        try:
            phase_info = json.loads(phase_file.read_text())
        except Exception:
            pass

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
            buf = _output_buffers.get(project_id, [])
            if offset < len(buf):
                for line in buf[offset:]:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                offset = len(buf)
            else:
                # If no active drain tasks (swarm not running), we're done
                if project_id not in _drain_tasks or not _drain_tasks[project_id]:
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
