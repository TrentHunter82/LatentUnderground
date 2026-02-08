import asyncio
import json
import re
from pathlib import Path
from typing import Callable, Awaitable

from watchfiles import awatch, Change


class FolderWatcher:
    """Watches a project folder for .claude/ and tasks/ changes, emits events."""

    def __init__(self, folder: str, broadcast: Callable[[dict], Awaitable[None]]):
        self.folder = Path(folder)
        self.broadcast = broadcast
        self._task: asyncio.Task | None = None
        # Track byte positions for incremental log reading (path_str -> byte offset)
        self._file_positions: dict[str, int] = {}

    async def start(self):
        self._task = asyncio.create_task(self._watch())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch(self):
        watch_paths = []
        for sub in [".claude/heartbeats", ".claude/signals", "tasks", "logs"]:
            p = self.folder / sub
            if p.exists():
                watch_paths.append(str(p))

        if not watch_paths:
            return

        try:
            async for changes in awatch(*watch_paths, step=1000):
                for change_type, path_str in changes:
                    await self._handle_change(change_type, path_str)
        except asyncio.CancelledError:
            return

    async def _handle_change(self, change_type: Change, path_str: str):
        path = Path(path_str)
        rel = path.relative_to(self.folder)
        parts = rel.parts

        event = None

        if "heartbeats" in parts and path.suffix == ".heartbeat":
            try:
                content = path.read_text(encoding="utf-8-sig").strip()
            except Exception:
                content = None
            event = {
                "type": "heartbeat",
                "agent": path.stem,
                "timestamp": content,
            }

        elif "signals" in parts and path.suffix == ".signal":
            event = {
                "type": "signal",
                "name": path.stem,
                "active": change_type != Change.deleted,
            }

        elif parts[0] == "tasks" and path.suffix == ".md":
            if path.name == "TASKS.md":
                try:
                    content = path.read_text()
                    total = len(re.findall(r"- \[[ x]\]", content))
                    done = len(re.findall(r"- \[x\]", content))
                    event = {
                        "type": "tasks",
                        "total": total,
                        "done": done,
                        "percent": round((done / total) * 100, 1) if total > 0 else 0,
                    }
                except Exception:
                    pass
            else:
                event = {
                    "type": "file_changed",
                    "file": str(rel).replace("\\", "/"),
                }

        elif parts[0] == "logs" and path.suffix == ".log":
            try:
                key = path_str
                last_pos = self._file_positions.get(key, 0)
                file_size = path.stat().st_size
                if file_size < last_pos:
                    # File was truncated/rotated, reset position
                    last_pos = 0
                if file_size > last_pos:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_data = f.read()
                        new_pos = f.tell()
                    self._file_positions[key] = new_pos
                    new_lines = [l for l in new_data.splitlines() if l.strip()]
                    if new_lines:
                        event = {
                            "type": "log",
                            "agent": path.stem,
                            "lines": new_lines,
                        }
            except Exception:
                pass

        if event:
            await self.broadcast(event)
