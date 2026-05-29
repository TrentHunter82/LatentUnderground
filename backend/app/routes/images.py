"""Image reference endpoints.

Lets a project attach design reference images (screenshots, mockups, mood
boards). Files are persisted to ``<project_folder>/references/images/`` so
projects stay portable; metadata is tracked in the ``project_images`` table.

At swarm launch, :func:`build_manifest_and_inject` writes a manifest the agents
can read and appends a "Visual References" section to the prompt files of agents
whose role matches each image's ``target_roles``.
"""

import json
import logging
import re
import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from ..database import get_db
from ..models.responses import ErrorDetail
from ..models.image import ImageReferenceOut, ImageUploadResponse
from ..sanitize import sanitize_string

logger = logging.getLogger("latent.images")

router = APIRouter(prefix="/api/projects", tags=["images"])

# --- Limits & validation (mirror frontend ImageReferenceUpload.jsx) ---
MAX_IMAGES = 10
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB per image
MAX_CAPTION = 500

_EXT_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
ALLOWED_EXTENSIONS = set(_EXT_MEDIA.keys())

VALID_ROLES = {"designer", "frontend", "backend", "qa", "architect", "product_owner"}
DEFAULT_ROLES = ["designer", "frontend"]

# Image ids are uuid hex stems; reject anything else before touching the disk.
_ID_RE = re.compile(r"^[0-9a-f]{6,32}$")

_404 = {404: {"model": ErrorDetail, "description": "Project or image not found"}}
_400 = {400: {"model": ErrorDetail, "description": "Invalid request"}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _project_or_404(db: aiosqlite.Connection, project_id: int) -> dict:
    row = await (await db.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


def _project_folder(project: dict) -> Path:
    folder = Path(project["folder_path"])
    if not folder.is_absolute():
        raise HTTPException(status_code=400, detail="Project folder_path is not absolute")
    if not folder.exists():
        raise HTTPException(status_code=400, detail="Project folder does not exist on disk")
    return folder


def _images_dir(folder: Path) -> Path:
    return folder / "references" / "images"


def _image_url(project_id: int, image_id: str) -> str:
    return f"/api/projects/{project_id}/images/{image_id}/raw"


def _row_to_out(row: aiosqlite.Row) -> dict:
    d = dict(row)
    roles = [r for r in (d.get("target_roles") or "").split(",") if r]
    return ImageReferenceOut(
        id=d["id"],
        project_id=d["project_id"],
        filename=d.get("original_filename") or d["filename"],
        caption=d.get("caption") or "",
        targetRoles=roles or list(DEFAULT_ROLES),
        url=_image_url(d["project_id"], d["id"]),
        path=d["path"],
        created_at=d["created_at"],
    ).model_dump()


def _normalize_roles(raw) -> list[str]:
    """Filter a client-supplied role list to known roles, preserving order."""
    if not isinstance(raw, list):
        return list(DEFAULT_ROLES)
    seen: list[str] = []
    for r in raw:
        if isinstance(r, str) and r in VALID_ROLES and r not in seen:
            seen.append(r)
    return seen or list(DEFAULT_ROLES)


def _resolve_within(base: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and ensure it stays under ``base`` (anti-traversal)."""
    base_r = base.resolve()
    target = candidate.resolve()
    if base_r != target and base_r not in target.parents:
        raise HTTPException(status_code=400, detail="Resolved path escapes project folder")
    return target


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{project_id}/images", response_model=ImageUploadResponse,
             status_code=201, summary="Upload image references",
             responses={**_404, **_400})
async def upload_images(
    project_id: int,
    files: list[UploadFile] = File(...),
    metadata: str = Form("[]"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Upload one or more reference images for a project.

    ``files`` is a multipart batch; ``metadata`` is a JSON array aligned by index
    with ``files``, each item ``{id, filename, caption, targetRoles}``.
    """
    project = await _project_or_404(db, project_id)
    folder = _project_folder(project)

    try:
        meta_list = json.loads(metadata) if metadata else []
        if not isinstance(meta_list, list):
            raise ValueError("metadata must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {e}")

    # Enforce the per-project cap across existing + incoming images.
    existing = await (await db.execute(
        "SELECT COUNT(*) AS n FROM project_images WHERE project_id = ?", (project_id,)
    )).fetchone()
    existing_count = existing["n"] if existing else 0
    if existing_count + len(files) > MAX_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many images: {existing_count} existing + {len(files)} new exceeds max {MAX_IMAGES}",
        )

    dest_dir = _images_dir(folder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict] = []
    errors: list[str] = []

    for idx, upload in enumerate(files):
        meta = meta_list[idx] if idx < len(meta_list) and isinstance(meta_list[idx], dict) else {}
        original = (meta.get("filename") or upload.filename or "image").strip()
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append(f"{original}: unsupported format (use PNG, JPG, or WebP)")
            continue

        # Reject oversized uploads by their declared size before reading into memory.
        if upload.size is not None and upload.size > MAX_FILE_SIZE:
            errors.append(f"{original}: exceeds 5MB limit ({upload.size / 1024 / 1024:.1f}MB)")
            continue
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{original}: exceeds 5MB limit ({len(content) / 1024 / 1024:.1f}MB)")
            continue
        if not content:
            errors.append(f"{original}: empty file")
            continue

        image_id = uuid.uuid4().hex[:12]
        stored_name = f"{image_id}{ext}"
        rel_path = f"references/images/{stored_name}"
        try:
            (dest_dir / stored_name).write_bytes(content)
        except OSError as e:
            errors.append(f"{original}: failed to save ({e})")
            continue

        caption = sanitize_string((meta.get("caption") or "")[:MAX_CAPTION])
        roles = _normalize_roles(meta.get("targetRoles"))
        await db.execute(
            """INSERT INTO project_images
               (id, project_id, filename, original_filename, caption, target_roles, path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (image_id, project_id, stored_name, sanitize_string(original),
             caption, ",".join(roles), rel_path),
        )
        row = await (await db.execute(
            "SELECT * FROM project_images WHERE id = ?", (image_id,)
        )).fetchone()
        uploaded.append(_row_to_out(row))

    await db.commit()
    logger.info("Uploaded %d image(s) to project %d (%d error(s))",
                len(uploaded), project_id, len(errors))
    return {"uploaded": uploaded, "errors": errors}


@router.get("/{project_id}/images", response_model=list[ImageReferenceOut],
            summary="List image references", responses=_404)
async def list_images(project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """List all image references attached to a project, newest first."""
    await _project_or_404(db, project_id)
    rows = await (await db.execute(
        "SELECT * FROM project_images WHERE project_id = ? "
        "ORDER BY created_at DESC, id DESC",
        (project_id,),
    )).fetchall()
    return [_row_to_out(r) for r in rows]


@router.get("/{project_id}/images/{image_id}/raw", summary="Get raw image bytes",
            responses=_404)
async def get_image_raw(project_id: int, image_id: str,
                        db: aiosqlite.Connection = Depends(get_db)):
    """Serve the raw image bytes (used as the thumbnail src in the UI)."""
    if not _ID_RE.match(image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    project = await _project_or_404(db, project_id)
    row = await (await db.execute(
        "SELECT * FROM project_images WHERE id = ? AND project_id = ?",
        (image_id, project_id),
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")

    folder = Path(project["folder_path"])
    file_path = _resolve_within(folder, folder / dict(row)["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file missing on disk")
    media_type = _EXT_MEDIA.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(file_path, media_type=media_type)


@router.delete("/{project_id}/images/{image_id}", status_code=204,
               summary="Delete image reference", responses=_404)
async def delete_image(project_id: int, image_id: str,
                       db: aiosqlite.Connection = Depends(get_db)):
    """Delete an image reference: remove the file from disk and the DB row."""
    project = await _project_or_404(db, project_id)
    row = await (await db.execute(
        "SELECT * FROM project_images WHERE id = ? AND project_id = ?",
        (image_id, project_id),
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")

    folder = Path(project["folder_path"])
    try:
        file_path = _resolve_within(folder, folder / dict(row)["path"])
        if file_path.exists():
            file_path.unlink()
    except HTTPException:
        raise
    except OSError as e:
        logger.warning("Failed to delete image file for %s: %s", image_id, e)

    await db.execute("DELETE FROM project_images WHERE id = ?", (image_id,))
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Swarm-launch integration: manifest generation + prompt injection
# ---------------------------------------------------------------------------

# Map swarm role-slot titles (from swarm.py _role_slots) to the spec role
# keywords the frontend assigns. Matched as case-insensitive substrings.
_ROLE_KEYWORDS = [
    ("frontend", "frontend"),
    ("interface", "frontend"),
    ("art director", "designer"),
    ("design", "designer"),
    ("polish", "designer"),
    ("backend", "backend"),
    ("core", "backend"),
    ("integration", "qa"),
    ("testing", "qa"),
    ("performance", "architect"),
    ("optimization", "architect"),
    ("architect", "architect"),
    ("documentation", "product_owner"),
    ("product", "product_owner"),
]

_INJECT_MARKER = "<!-- LU:visual-references -->"

_VISUAL_REFERENCES_TEMPLATE = """

{marker}
## Visual References

This project includes design reference images. Before writing any UI code:

1. Read `references/image_manifest.json` for the list of reference images and their annotations.
2. Open each image file listed there and study it carefully.
3. Extract and apply from the references:
   - Color palette (dominant colors, accent colors, background tones)
   - Typography density and weight patterns
   - Spacing rhythm (tight vs airy, padding ratios)
   - Component patterns (card styles, nav patterns, form layouts)
   - Overall aesthetic mood (minimal, dense, playful, corporate, etc.)
4. Your implementation should be *informed by* these references — not pixel-perfect copies.
   Adapt the aesthetic to fit the project's functional requirements.
5. If references conflict with explicit requirements, requirements win.
"""


def _roles_for_title(title: str) -> set[str]:
    t = title.lower()
    return {role for kw, role in _ROLE_KEYWORDS if kw in t}


def _prompt_role_title(first_line: str) -> str:
    """Extract the role title from a prompt's first line.

    Prompt files begin with e.g. ``You are Claude-2 (Frontend/Interface) working on: ...``
    """
    m = re.search(r"\(([^)]+)\)", first_line)
    return m.group(1) if m else ""


async def build_manifest_and_inject(db: aiosqlite.Connection, project_id: int,
                                    folder: Path) -> int:
    """Generate the image manifest and inject Visual References into prompts.

    Returns the number of images found (0 = nothing to do). Safe to call on
    every launch: it overwrites the manifest and appends the section to the
    freshly-generated prompt files of agents whose role matches an image's
    ``target_roles``.
    """
    rows = await (await db.execute(
        "SELECT * FROM project_images WHERE project_id = ? "
        "ORDER BY created_at DESC, id DESC",
        (project_id,),
    )).fetchall()
    if not rows:
        return 0

    images = [dict(r) for r in rows]
    target_roles: set[str] = set()
    references = []
    for img in images:
        roles = [r for r in (img.get("target_roles") or "").split(",") if r] or list(DEFAULT_ROLES)
        target_roles.update(roles)
        references.append({
            "filename": img.get("original_filename") or img["filename"],
            "caption": img.get("caption") or "",
            "path": img["path"],
            "targetRoles": roles,
        })

    # Write the manifest agents read.
    manifest = {
        "designReferences": references,
        "instructions": (
            "These images are available in the project. Open and study them "
            "before making design decisions."
        ),
    }
    refs_dir = folder / "references"
    try:
        refs_dir.mkdir(parents=True, exist_ok=True)
        (refs_dir / "image_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8",
        )
    except OSError as e:
        logger.warning("Failed to write image manifest for project %d: %s", project_id, e)
        return len(images)

    # Inject the Visual References section into matching agents' prompt files.
    prompts_dir = folder / ".claude" / "prompts"
    if not prompts_dir.exists():
        return len(images)

    section = _VISUAL_REFERENCES_TEMPLATE.format(marker=_INJECT_MARKER)
    injected = 0
    for pf in sorted(prompts_dir.glob("Claude-*.txt")):
        try:
            text = pf.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        if _INJECT_MARKER in text:
            continue
        first_line = text.splitlines()[0] if text else ""
        roles = _roles_for_title(_prompt_role_title(first_line))
        if not (roles & target_roles):
            continue
        try:
            pf.write_text(text.rstrip() + section, encoding="utf-8")
            injected += 1
        except OSError as e:
            logger.warning("Failed to inject visual references into %s: %s", pf.name, e)

    logger.info("Image manifest written for project %d (%d images, injected into %d prompt(s))",
                project_id, len(images), injected)
    return len(images)
