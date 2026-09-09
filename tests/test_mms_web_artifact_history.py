import base64
import json
from pathlib import Path

import pytest

from mms_web.artifact_history import ArtifactHistory
from mms_web.artifact_preview import offline_html, read_output
from mms_web.errors import WebError
from test_mms_web_interactions import PNG


@pytest.fixture
def history(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    meta = {"id": "test-session", "cwd": str(workspace)}
    return ArtifactHistory(tmp_path / "state", meta, ["private-fixture-key"]), workspace, meta


def capture(history, path="result.md", content="# One\nFirst paragraph.\n", eid="write-one"):
    store, root, _ = history
    (root / path).write_text(content)
    store.observe({"id": eid, "kind": "tool", "title": "write", "status": "done", "arguments": {"path": path}}, eid)
    return next(item for item in store.list([]) if item["path"] == path)


def test_recorded_bytes_survive_changes_deletion_and_restart(history):
    store, root, meta = history
    one = capture(history)
    assert "content" not in one and one["revision"] == 1
    two = capture(history, content="# One\nRevised paragraph.\n", eid="write-two")
    view = store.read(two["id"], [], compare=1)
    assert "-First paragraph." in view["diff"] and "+Revised paragraph." in view["diff"]
    (root / "result.md").write_text("Edited by another application")
    assert store.list([])[0]["status"] == "changed"
    (root / "result.md").unlink()
    restored = ArtifactHistory(root.parent / "state", meta, [])
    old = restored.read(one["id"], [], revision=1)
    assert old["content"] == "# One\nFirst paragraph.\n" and old["status"] == "missing"
    assert len(old["versions"]) == 2


def test_command_observes_real_changes_only(history):
    store, root, _ = history
    (root / "existing.txt").write_text("unchanged")
    store.observe({"id": "bash-1", "kind": "tool", "title": "bash", "status": "running"}, "start")
    (root / "data.csv").write_text('name,value\n"quoted, cell",3\n')
    store.observe({"id": "bash-1", "kind": "tool", "title": "bash", "status": "done"}, "end")
    items = store.list([])
    assert len(items) == 1 and items[0]["path"] == "data.csv" and items[0]["source"] == "observed"
    assert store.read(items[0]["id"], [])["rows"][1] == ["quoted, cell", "3"]


def test_automatic_capture_does_not_follow_symlinks_or_show_keys(history, tmp_path):
    store, root, _ = history
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside content")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "file.txt").symlink_to(outside / "secret.txt")
    for path in ["linked/secret.txt", "file.txt", "../outside/secret.txt"]:
        with pytest.raises(WebError):
            read_output(root, path)
        store.capture(path, "event", "now", "tool")
    (root / "notes.txt").write_text("private-fixture-key")
    store.capture("notes.txt", "event", "now", "tool")
    assert store.list([]) == []
    assert not (store.root / "blobs").exists()


def test_select_current_quote_then_reject_after_external_edit(history):
    store, root, _ = history
    item = capture(history)
    selection = {"artifactId": item["id"], "sha256": item["sha256"], "revision": 1, "quote": "First paragraph."}
    clean, suffix = store.selection(selection, [])
    assert clean["path"] == "result.md" and "First paragraph." in suffix
    (root / "result.md").write_text("external edit")
    with pytest.raises(WebError) as error:
        store.selection(selection, [])
    assert error.value.code == "FILE_CHANGED"


def test_image_region_and_recorded_version(history):
    store, root, _ = history
    data = base64.b64decode(PNG)
    (root / "image.png").write_bytes(data)
    store.capture("image.png", "image-event", "now", "observed")
    item = store.list([])[0]
    view = store.read(item["id"], [])
    assert base64.b64decode(view["downloadData"]) == data
    selection = {"artifactId": item["id"], "sha256": item["sha256"], "revision": 1,
                 "region": {"x": 0.1, "y": 0.2, "width": 0.4, "height": 0.3}}
    assert store.selection(selection, [])[0]["region"] == selection["region"]
    for value in (float("nan"), -0.1, 1.1, True):
        selection["region"]["width"] = value
        with pytest.raises(WebError):
            store.selection(selection, [])


def test_cached_path_replaced_by_symlink_is_unavailable_and_cannot_be_selected(history):
    store, root, _ = history
    (root / "folder").mkdir()
    item = capture(history, "folder/result.md")
    assert store.list([])[0]["status"] == "current"
    outside = root.parent / "moved"
    (root / "folder").rename(outside)
    (root / "folder").symlink_to(outside, target_is_directory=True)
    assert store.list([])[0]["status"] == "unavailable"
    assert store.read(item["id"], [])["status"] == "unavailable"
    with pytest.raises(WebError) as error:
        store.selection({"artifactId": item["id"], "sha256": item["sha256"], "revision": 1, "quote": "First paragraph."}, [])
    assert error.value.code == "FILE_CHANGED"


def test_current_file_can_be_compared_without_inventing_a_version_and_quote_must_match(history):
    store, root, _ = history
    item = capture(history)
    (root / "result.md").write_text("Changed outside Pi\n")
    current = store.read(item["id"], [], revision=0, compare=1)
    assert current["revision"] == 0 and len(current["versions"]) == 1
    assert "+Changed outside Pi" in current["diff"]
    selection = {"artifactId": item["id"], "sha256": current["sha256"], "revision": 0, "quote": "Changed outside Pi"}
    assert store.selection(selection, [])[0]["quote"] == "Changed outside Pi"
    selection["quote"] = "Invented quotation"
    with pytest.raises(WebError) as error:
        store.selection(selection, [])
    assert error.value.code == "INVALID_SELECTION"


def test_capacity_keeps_existing_versions_without_deleting(history, monkeypatch):
    monkeypatch.setattr("mms_web.artifact_history.MAX_VERSIONS", 2)
    store, root, meta = history
    one = capture(history)
    capture(history, content="second", eid="second")
    capture(history, content="third", eid="third")
    assert len(store.read(one["id"], [])["versions"]) == 2
    assert store.list([])[0]["status"] == "changed"
    assert "上限" in store.note
    assert "上限" in ArtifactHistory(root.parent / "state", meta, []).note
    assert store.read(one["id"], [], revision=1)["content"].startswith("# One")


def test_corrupt_blob_fails_closed(history):
    store, _, _ = history
    item = capture(history)
    (store.root / "blobs" / item["sha256"]).write_text("corrupt")
    with pytest.raises(WebError) as error:
        store.read(item["id"], [])
    assert error.value.code == "ARTIFACT_INVALID"


def test_legacy_session_read_does_not_invent_or_save_versions(history):
    store, root, _ = history
    (root / "old.txt").write_text("current old file")
    events = [{"id": "old-write", "kind": "tool", "title": "write", "status": "done", "arguments": {"path": "old.txt"}}]
    item = store.list(events)[0]
    assert item["revision"] == 0 and item["source"] == "legacy"
    assert store.read(item["id"], events)["content"] == "current old file"
    assert not store.root.exists()


def test_html_removes_navigation_and_executable_content():
    source = '''<html><head><meta http-equiv="refresh" content="0;url=http://localhost:8765">
    <base href="http://localhost:8765"><style>body{color:red}</style></head><body>
    <script>fetch('/api/v1/bootstrap')</script><iframe src="http://localhost:8765"></iframe>
    <a href="http://example.invalid" ping="http://example.invalid/log">link</a>
    <form action="/api/v1/sessions"><input formaction="/api/v1/sessions"></form>
    <img src="http://example.invalid/pixel" srcset="http://example.invalid/pixel 1x" onerror="alert(1)">
    <h1>Visible result</h1></body></html>'''
    result = offline_html(source).decode()
    for forbidden in ("http-equiv", "<base", "<script", "<iframe", "href=", "ping=", "action=", "srcset=", "onerror=", "example.invalid", "fetch("):
        assert forbidden not in result
    assert "Visible result" in result and "body{color:red}" in result
