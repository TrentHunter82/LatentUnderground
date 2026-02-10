import logging
import platform
import string
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("latent.browse")

router = APIRouter(prefix="/api/browse", tags=["browse"])


def _get_drives() -> list[dict]:
    """List available drive letters on Windows."""
    drives = []
    for letter in string.ascii_uppercase:
        p = Path(f"{letter}:\\")
        if p.exists():
            drives.append({"name": f"{letter}:\\", "path": f"{letter}:\\"})
    return drives


@router.get("")
async def browse_directory(path: str = Query("", max_length=1000, description="Directory path to list")):
    """List subdirectories at a given path. Returns drive roots when path is empty on Windows."""
    # No path provided: return drive roots on Windows, home dir contents on Unix
    if not path:
        if platform.system() == "Windows":
            return {"path": "", "parent": None, "dirs": _get_drives()}
        else:
            path = str(Path.home())

    target = Path(path).resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    # Parent directory for navigation
    parent = str(target.parent) if target.parent != target else None

    MAX_DIRS = 500
    dirs = []
    try:
        for entry in sorted(target.iterdir()):
            if entry.is_dir() and not entry.name.startswith((".", "$")):
                try:
                    dirs.append({"name": entry.name, "path": str(entry)})
                except (PermissionError, OSError):
                    pass
                if len(dirs) >= MAX_DIRS:
                    break
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Cannot read directory: {e}")

    return {"path": str(target), "parent": parent, "dirs": dirs, "truncated": len(dirs) >= MAX_DIRS}
