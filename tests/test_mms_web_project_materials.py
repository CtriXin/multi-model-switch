import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from mms_web.errors import WebError
from mms_web.project_materials import ProjectMaterials, content_hash
from test_mms_web_interactions import local_app


def save(app, workspace, content="Project context", title="Project guide", **extra):
    current = app.post(["project-materials"], {"workspaceId": workspace["id"]})
    return app.post(["project-materials", "change"], {"workspaceId": workspace["id"], "revision": current["revision"],
        "action": "save", "confirmed": True, "title": title, "content": content, "enabled": True, **extra})


def test_project_isolation_revision_edit_disable_delete_and_restart(local_app, tmp_path):
    app, a, _ = local_app
    folder = tmp_path / "other"; folder.mkdir()
    b = app.post(["workspaces"], {"path": str(folder)})
    saved = save(app, a)
    item = saved["items"][0]
    assert app.post(["project-materials"], {"workspaceId": b["id"]})["items"] == []
    assert "Project context" in app.sessions.materials.prepare(a["id"])[0]
    updated = save(app, a, content="Revised context", id=item["id"])
    assert updated["items"][0]["revision"] == 2
    with pytest.raises(WebError) as error:
        app.post(["project-materials", "change"], {"workspaceId": a["id"], "revision": saved["revision"], "action": "delete", "confirmed": True, "id": item["id"]})
    assert error.value.code == "MATERIALS_CHANGED"
    save(app, a, id=item["id"], enabled=False)
    assert app.sessions.materials.prepare(a["id"]) == ("", [])
    restored = ProjectMaterials(app.catalog, app.state_root)
    current = restored.snapshot(a["id"])
    assert current["items"][0]["enabled"] is False
    deleted = restored.change({"workspaceId": a["id"], "revision": current["revision"], "action": "delete", "confirmed": True, "id": item["id"]})
    assert deleted["items"] == [] and restored.prepare(a["id"]) == ("", [])


def test_confirmed_save_budget_and_own_state_only(local_app):
    app, workspace, root = local_app
    with pytest.raises(WebError) as error:
        save(app, workspace, confirmed=False)
    assert error.value.code == "MATERIAL_CONFIRMATION_REQUIRED"
    with pytest.raises(WebError) as error:
        save(app, workspace, content="x" * 20001)
    assert error.value.code == "MATERIAL_TOO_LARGE"
    save(app, workspace)
    _, path = app.sessions.materials._workspace(workspace["id"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert not (root / "project-materials").exists()
    for i in range(3):
        save(app, workspace, content="x" * 20000, title=f"Large {i}")
    with pytest.raises(WebError) as error:
        save(app, workspace, content="x" * 20000)
    assert error.value.code == "MATERIALS_LIMIT"


def test_concurrent_writers_do_not_overwrite_each_other(local_app):
    app, workspace, _ = local_app
    stores = [ProjectMaterials(app.catalog, app.state_root), ProjectMaterials(app.catalog, app.state_root)]
    def write(pair):
        index, store = pair
        try:
            return store.change({"workspaceId": workspace["id"], "revision": 0, "action": "save", "confirmed": True,
                "title": f"Writer {index}", "content": "One winner", "enabled": True})
        except WebError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, enumerate(stores)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "MATERIALS_CHANGED" in results
    assert len(stores[0].snapshot(workspace["id"])["items"]) == 1


@pytest.mark.parametrize("corruption", ["hash", "duplicate", "oversized", "source", "timestamp", "revision", "workspace"])
def test_corrupt_materials_are_not_injected_or_overwritten(local_app, corruption):
    app, workspace, _ = local_app
    save(app, workspace)
    store = app.sessions.materials
    _, path = store._workspace(workspace["id"])
    data = json.loads(path.read_text())
    item = data["items"][0]
    if corruption == "hash": item["sha256"] = "wrong"
    if corruption == "duplicate": data["items"].append(copy.deepcopy(item))
    if corruption == "oversized":
        item["content"] = "x" * 100_000
        item["sha256"] = content_hash(item["content"])
    if corruption == "source": item.pop("source")
    if corruption == "timestamp": item["createdAt"] = "not a date"
    if corruption == "revision": item["revision"] = 0
    if corruption == "workspace": data["workspace"] = "/another/project"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(WebError) as error:
        store.prepare(workspace["id"])
    assert error.value.code == "MATERIALS_UNAVAILABLE"
    with pytest.raises(WebError):
        save(app, workspace, content="Do not overwrite")
    assert path.read_bytes() == before
