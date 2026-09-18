from types import SimpleNamespace

from mms_web.workspace_browse import browse_workspaces, classify_user_path


def test_windows_drive_root_and_unc_shapes_without_a_windows_host():
    assert classify_user_path("C:\\", windows=True) == "drive_root"
    assert classify_user_path(r"C:\Users\Admin\下载", windows=True) == "drive_abs"
    assert classify_user_path(r"\\server\share", windows=True) == "unc"


def test_windows_computer_root_lists_drive_letters(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("mms_web.workspace_browse.real_home", lambda: home)
    monkeypatch.setattr("mms_web.workspace_browse._windows_platform", lambda: True)
    monkeypatch.setattr("mms_web.workspace_browse._list_drives", lambda: ["C:\\", "D:\\"])
    catalog = SimpleNamespace(_workspaces=lambda: [])
    result = browse_workspaces(catalog, {"path": ""})
    drives = [row for row in result["entries"] if row["kind"] == "drive"]
    assert [row["path"] for row in drives] == ["C:\\", "D:\\"]
    assert [row["name"] for row in drives] == ["C:", "D:"]
