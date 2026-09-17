import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mms_web.errors import WebError
from mms_web.workspace_browse import (
    EXCLUDED,
    GENERIC_CODE,
    GENERIC_MESSAGE,
    _is_under,
    _list_drives,
    browse_workspaces,
    classify_user_path,
)
from mms_web.server import WebApplication


def _catalog(*paths: Path):
    return SimpleNamespace(_workspaces=lambda: [
        {"id": f"w{index}", "name": path.name, "path": str(path)}
        for index, path in enumerate(paths)
    ])


def _err(call):
    with pytest.raises(WebError) as caught:
        call()
    assert caught.value.code == GENERIC_CODE
    assert caught.value.message == GENERIC_MESSAGE
    assert caught.value.status == 409
    return caught.value


def test_classify_windows_path_shapes_on_posix():
    assert classify_user_path("C:\\", windows=True) == "drive_root"
    assert classify_user_path("C:/", windows=True) == "drive_root"
    assert classify_user_path(r"C:\Users\Admin", windows=True) == "drive_abs"
    assert classify_user_path("C:foo", windows=True) == "drive_relative"
    assert classify_user_path(r"\\server\share", windows=True) == "unc"
    assert classify_user_path(r"\\server\share\folder", windows=True) == "unc"
    assert classify_user_path("/Users/xin", windows=False) == "posix"
    assert classify_user_path("~/Documents") == "posix"
    assert classify_user_path("") == "empty"
    assert classify_user_path("relative") == "other"
    assert classify_user_path("bad\x00path") == "invalid"


def test_browse_lists_home_directories_and_hides_dot_excluded_and_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    visible = home / "Documents"
    hidden = home / ".ssh"
    aws = home / ".aws"
    excluded = home / "node_modules"
    a_file = home / "readme.txt"
    for folder in (visible, hidden, aws, excluded):
        folder.mkdir(parents=True)
    (hidden / "id_rsa").write_text("no")
    a_file.write_text("file")
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    names = {row["name"] for row in browse_workspaces(_catalog(), {"path": str(home)})["entries"]}
    assert names == {"Documents"}
    assert "readme.txt" not in names
    assert ".ssh" not in names
    assert ".aws" not in names
    assert "node_modules" not in names


def test_hidden_and_excluded_roots_are_rejected_without_distinct_errors(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    secret = home / ".ssh"
    secret.mkdir()
    missing = home / "no-such-dir"
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    hidden = _err(lambda: browse_workspaces(_catalog(), {"path": str(secret)}))
    absent = _err(lambda: browse_workspaces(_catalog(), {"path": str(missing)}))
    assert hidden.message == absent.message == GENERIC_MESSAGE


def test_file_path_and_missing_path_share_the_same_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    file_path = home / "notes.txt"
    file_path.write_text("x")
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    as_file = _err(lambda: browse_workspaces(_catalog(), {"path": str(file_path)}))
    missing = _err(lambda: browse_workspaces(_catalog(), {"path": str(home / "gone")}))
    assert as_file.message == missing.message


def test_symlink_directories_are_not_listed_or_followed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    real = home / "real"
    outside = tmp_path / "outside"
    real.mkdir(parents=True)
    outside.mkdir()
    (real / "inside").mkdir()
    link = home / "link"
    link.symlink_to(outside)
    nested = home / "nested"
    nested.mkdir()
    nested_link = nested / "away"
    nested_link.symlink_to(outside)
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    names = {row["name"] for row in browse_workspaces(_catalog(), {"path": str(home)})["entries"]}
    assert "link" not in names
    assert "real" in names
    child_names = {row["name"] for row in browse_workspaces(_catalog(), {"path": str(nested)})["entries"]}
    assert "away" not in child_names
    _err(lambda: browse_workspaces(_catalog(), {"path": str(link)}))


def test_listing_caps_at_400(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for index in range(410):
        (home / f"folder-{index:03d}").mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    result = browse_workspaces(_catalog(), {"path": str(home)})
    assert len(result["entries"]) == 400
    assert result["truncated"] is True


def test_computer_root_includes_home_and_outside_workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    other = tmp_path / "other-project"
    other.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: False)
    result = browse_workspaces(_catalog(other), {"path": ""})
    assert result["path"] == ""
    assert result["selectable"] is False
    paths = {row["path"] for row in result["entries"]}
    assert str(home) in paths
    assert str(other) in paths


def test_windows_computer_root_lists_injected_drives(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: True)
    monkeypatch.setattr("mms_web.workspace_browse._list_drives", lambda: ["C:\\", "D:\\"])
    result = browse_workspaces(_catalog(), {"path": ""})
    kinds = {row["kind"] for row in result["entries"]}
    assert "drive" in kinds
    assert {row["path"] for row in result["entries"] if row["kind"] == "drive"} == {"C:\\", "D:\\"}


def test_drive_relative_and_unc_on_posix_are_generic_failures(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: False)
    _err(lambda: browse_workspaces(_catalog(), {"path": "C:foo"}))
    _err(lambda: browse_workspaces(_catalog(), {"path": r"\\server\share"}))
    _err(lambda: browse_workspaces(_catalog(), {"path": "not-a-path"}))


def test_explicit_path_outside_home_is_listable_for_this_request(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "opt" / "tool"
    child = outside / "src"
    child.mkdir(parents=True)
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    result = browse_workspaces(_catalog(), {"path": str(outside)})
    assert {row["name"] for row in result["entries"]} == {"src"}
    assert result["parent"] == ""


def test_browse_does_not_take_mutation_lock(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    class Boom:
        def __enter__(self):
            raise AssertionError("mutation lock acquired")
        def __exit__(self, *args):
            return False
    app.mutation_lock = Boom()
    try:
        assert ["workspaces", "browse"] in WebApplication._UNLOCKED_POSTS
        result = app.post(["workspaces", "browse"], {"path": ""})
        assert result["name"] == "这台电脑"
    finally:
        app.close()


def test_choose_endpoint_is_gone(tmp_path):
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    try:
        assert ["workspaces", "choose"] not in WebApplication._UNLOCKED_POSTS
        with pytest.raises(WebError) as caught:
            app.post(["workspaces", "choose"], {})
        assert caught.value.status == 404
    finally:
        app.close()


def test_choose_has_no_remaining_source_callers():
    root = Path(__file__).resolve().parents[1]
    watched = [
        root / "mms_web" / "server.py",
        root / "apps" / "mms-web" / "src" / "LaunchOptions.tsx",
        root / "docs" / "mms-web" / "API.md",
    ]
    for path in watched:
        text = path.read_text(encoding="utf-8")
        assert "/workspaces/choose" not in text
        assert "FolderBrowserDialog" not in text
        assert "choose folder" not in text


def test_windows_paths_compare_case_insensitively(monkeypatch):
    """C:\\Users and c:\\users are the same place; relative_to alone is not."""
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: True)
    assert _is_under(Path(r"C:\Users\Admin"), Path(r"c:\users"))
    assert _is_under(Path(r"c:\users\admin\src"), Path(r"C:\Users\Admin"))
    assert _is_under(Path(r"C:\Users"), Path("C:\\Users\\"))
    assert not _is_under(Path(r"C:\UsersElsewhere"), Path(r"C:\Users"))
    assert not _is_under(Path(r"D:\Users\Admin"), Path(r"C:\Users"))


def test_list_drives_uses_os_listdrives_when_available(monkeypatch):
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: True)
    monkeypatch.setattr(os, "listdrives", lambda: ["C:\\", "D:", "c:\\"], raising=False)
    monkeypatch.setattr(os.path, "exists", lambda path: pytest.fail("fallback must not run"))
    assert _list_drives() == ["C:\\", "D:\\"]


def test_list_drives_falls_back_to_letter_probing_without_os_listdrives(monkeypatch):
    """Python 3.11 is still supported and has no os.listdrives()."""
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: True)
    monkeypatch.delattr(os, "listdrives", raising=False)
    monkeypatch.setattr(os.path, "exists", lambda path: path in ("C:\\", "E:\\"))
    assert _list_drives() == ["C:\\", "E:\\"]


def test_list_drives_is_empty_off_windows(monkeypatch):
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: False)
    assert _list_drives() == []


def test_posix_root_is_listable_and_stays_filtered(tmp_path, monkeypatch):
    """Contract: an explicit absolute path is a legal starting point, / included.

    Enumerating directories already exists through creating a workspace and
    browsing it with /files/tree, so this adds no surface. It is asserted here
    so that tightening or loosening it later is a deliberate act.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._mounted_volumes", lambda: [])
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: False)
    result = browse_workspaces(_catalog(), {"path": "/"})
    assert result["path"] == "/"
    names = {row["name"] for row in result["entries"]}
    assert names, "the filesystem root lists its directories"
    assert not any(name.startswith(".") for name in names)
    assert not any(name in EXCLUDED for name in names)
