"""Tests for the image reference feature: upload/list/delete, raw serving,
manifest generation, prompt injection, and project-delete cleanup."""

import json
from pathlib import Path

import aiosqlite
import pytest

# A tiny payload that passes extension-based validation (content isn't decoded).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
async def image_project(client, sample_project_data, tmp_path):
    """Create a project whose folder actually exists on disk."""
    folder = tmp_path / "ImgProject"
    folder.mkdir(parents=True, exist_ok=True)
    data = {**sample_project_data, "folder_path": str(folder).replace("\\", "/")}
    resp = await client.post("/api/projects", json=data)
    assert resp.status_code == 201
    project = resp.json()
    project["_folder"] = folder
    return project


def _upload_files(items):
    """Build httpx multipart `files` arg: items = [(filename, bytes, content_type)]."""
    return [("files", (name, body, ctype)) for name, body, ctype in items]


def _meta(*entries):
    return {"metadata": json.dumps(list(entries))}


# --- Upload ---------------------------------------------------------------

async def test_upload_single_image(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("mock.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "mock.png", "caption": "hero shot",
                    "targetRoles": ["designer", "frontend"]}),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["errors"] == []
    assert len(body["uploaded"]) == 1
    img = body["uploaded"][0]
    assert img["filename"] == "mock.png"
    assert img["caption"] == "hero shot"
    assert img["targetRoles"] == ["designer", "frontend"]
    assert img["url"] == f"/api/projects/{pid}/images/{img['id']}/raw"
    assert img["path"].startswith("references/images/")

    # File persisted on disk
    disk = image_project["_folder"] / img["path"]
    assert disk.exists()
    assert disk.read_bytes() == PNG_BYTES


async def test_upload_multiple_and_list(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([
            ("a.png", PNG_BYTES, "image/png"),
            ("b.webp", PNG_BYTES, "image/webp"),
        ]),
        data=_meta({"filename": "a.png"}, {"filename": "b.webp"}),
    )
    assert resp.status_code == 201
    assert len(resp.json()["uploaded"]) == 2

    listed = await client.get(f"/api/projects/{pid}/images")
    assert listed.status_code == 200
    names = {i["filename"] for i in listed.json()}
    assert names == {"a.png", "b.webp"}


async def test_upload_defaults_target_roles(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),  # no targetRoles
    )
    assert resp.json()["uploaded"][0]["targetRoles"] == ["designer", "frontend"]


async def test_upload_all_roles_preserved(client, image_project):
    pid = image_project["id"]
    roles = ["designer", "frontend", "backend", "qa", "architect", "product_owner"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png", "targetRoles": roles}),
    )
    assert resp.json()["uploaded"][0]["targetRoles"] == roles


async def test_upload_filters_invalid_roles(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png", "targetRoles": ["designer", "evil", 123]}),
    )
    assert resp.json()["uploaded"][0]["targetRoles"] == ["designer"]


async def test_upload_rejects_bad_extension(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("doc.pdf", PNG_BYTES, "application/pdf")]),
        data=_meta({"filename": "doc.pdf"}),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["uploaded"] == []
    assert len(body["errors"]) == 1
    assert "unsupported" in body["errors"][0].lower()


async def test_upload_rejects_oversized(client, image_project):
    pid = image_project["id"]
    big = b"\x89PNG" + b"\x00" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("big.png", big, "image/png")]),
        data=_meta({"filename": "big.png"}),
    )
    body = resp.json()
    assert body["uploaded"] == []
    assert "5mb" in body["errors"][0].lower()


async def test_upload_exceeds_max_images(client, image_project):
    pid = image_project["id"]
    items = [(f"img{i}.png", PNG_BYTES, "image/png") for i in range(11)]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files(items),
        data=_meta(*[{"filename": f"img{i}.png"} for i in range(11)]),
    )
    assert resp.status_code == 400
    assert "max" in resp.json()["detail"].lower()


async def test_upload_unknown_project_404(client):
    resp = await client.post(
        "/api/projects/99999/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),
    )
    assert resp.status_code == 404


async def test_upload_missing_folder_400(client, sample_project_data, tmp_path):
    # Project creation makes the folder; simulate it being removed externally.
    import shutil
    folder = tmp_path / "ghost"
    data = {**sample_project_data, "folder_path": str(folder).replace("\\", "/")}
    created = await client.post("/api/projects", json=data)
    pid = created.json()["id"]
    shutil.rmtree(folder)
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),
    )
    assert resp.status_code == 400


async def test_upload_invalid_metadata_400(client, image_project):
    pid = image_project["id"]
    resp = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data={"metadata": "{not json"},
    )
    assert resp.status_code == 400


# --- Raw serving ----------------------------------------------------------

async def test_get_raw_image(client, image_project):
    pid = image_project["id"]
    up = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),
    )
    img_id = up.json()["uploaded"][0]["id"]
    raw = await client.get(f"/api/projects/{pid}/images/{img_id}/raw")
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/png"
    assert raw.content == PNG_BYTES


async def test_get_raw_unknown_404(client, image_project):
    pid = image_project["id"]
    resp = await client.get(f"/api/projects/{pid}/images/abc123def456/raw")
    assert resp.status_code == 404


async def test_get_raw_rejects_bad_id(client, image_project):
    pid = image_project["id"]
    # Path-traversal-ish id is rejected by the id regex
    resp = await client.get(f"/api/projects/{pid}/images/..%2f..%2fsecret/raw")
    assert resp.status_code == 404


# --- Delete ---------------------------------------------------------------

async def test_delete_image(client, image_project):
    pid = image_project["id"]
    up = await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),
    )
    img = up.json()["uploaded"][0]
    disk = image_project["_folder"] / img["path"]
    assert disk.exists()

    resp = await client.delete(f"/api/projects/{pid}/images/{img['id']}")
    assert resp.status_code == 204
    assert not disk.exists()

    listed = await client.get(f"/api/projects/{pid}/images")
    assert listed.json() == []


async def test_delete_unknown_404(client, image_project):
    pid = image_project["id"]
    resp = await client.delete(f"/api/projects/{pid}/images/deadbeef0000")
    assert resp.status_code == 404


# --- Project delete cleanup ----------------------------------------------

async def test_project_delete_removes_references(client, image_project):
    pid = image_project["id"]
    await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png"}),
    )
    references = image_project["_folder"] / "references"
    assert references.exists()

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 204
    assert not references.exists()


# --- Manifest generation + prompt injection -------------------------------

async def test_manifest_and_injection(client, image_project, tmp_db):
    from app.routes.images import build_manifest_and_inject

    pid = image_project["id"]
    folder = image_project["_folder"]
    await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("hero.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "hero.png", "caption": "nav layout",
                    "targetRoles": ["designer", "frontend"]}),
    )

    # Simulate freshly-generated prompt files
    prompts = folder / ".claude" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "Claude-1.txt").write_text(
        "You are Claude-1 (Backend/Core) working on: X\n\nDo backend things.",
        encoding="utf-8",
    )
    (prompts / "Claude-2.txt").write_text(
        "You are Claude-2 (Frontend/Interface) working on: X\n\nDo frontend things.",
        encoding="utf-8",
    )

    async with aiosqlite.connect(tmp_db) as db:
        db.row_factory = aiosqlite.Row
        count = await build_manifest_and_inject(db, pid, folder)
    assert count == 1

    # Manifest written
    manifest_path = folder / "references" / "image_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["designReferences"][0]["caption"] == "nav layout"
    assert manifest["designReferences"][0]["filename"] == "hero.png"
    assert "instructions" in manifest

    # Frontend agent got the section; backend agent did not
    backend_prompt = (prompts / "Claude-1.txt").read_text(encoding="utf-8")
    frontend_prompt = (prompts / "Claude-2.txt").read_text(encoding="utf-8")
    assert "Visual References" not in backend_prompt
    assert "Visual References" in frontend_prompt
    assert "references/image_manifest.json" in frontend_prompt


async def test_manifest_noop_without_images(client, image_project, tmp_db):
    from app.routes.images import build_manifest_and_inject

    pid = image_project["id"]
    folder = image_project["_folder"]
    async with aiosqlite.connect(tmp_db) as db:
        db.row_factory = aiosqlite.Row
        count = await build_manifest_and_inject(db, pid, folder)
    assert count == 0
    assert not (folder / "references" / "image_manifest.json").exists()


async def test_injection_targets_all_roles(client, image_project, tmp_db):
    from app.routes.images import build_manifest_and_inject

    pid = image_project["id"]
    folder = image_project["_folder"]
    await client.post(
        f"/api/projects/{pid}/images",
        files=_upload_files([("a.png", PNG_BYTES, "image/png")]),
        data=_meta({"filename": "a.png",
                    "targetRoles": ["designer", "frontend", "backend", "qa",
                                    "architect", "product_owner"]}),
    )
    prompts = folder / ".claude" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "Claude-1.txt").write_text(
        "You are Claude-1 (Backend/Core) working on: X", encoding="utf-8")

    async with aiosqlite.connect(tmp_db) as db:
        db.row_factory = aiosqlite.Row
        await build_manifest_and_inject(db, pid, folder)

    assert "Visual References" in (prompts / "Claude-1.txt").read_text(encoding="utf-8")
