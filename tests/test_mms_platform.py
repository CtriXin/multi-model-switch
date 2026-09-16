from pathlib import Path

from mms_platform import browser_capabilities, describe_platform


def test_windows_descriptor_uses_explicit_windows_roots_without_writing(tmp_path):
    env = {
        "USERPROFILE": str(tmp_path / "user"),
        "APPDATA": str(tmp_path / "roaming"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "TEMP": str(tmp_path / "temp"),
        "ComSpec": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
    }
    descriptor = describe_platform(platform_name="win32", env=env)
    assert descriptor.os == "win32"
    assert descriptor.path_style == "windows"
    assert descriptor.process_control == "windows-process-group"
    # No Windows folder chooser exists in the backend yet, so the descriptor
    # must not advertise one.
    assert descriptor.file_picker == "html"
    assert descriptor.state_root == str(Path(env["LOCALAPPDATA"]) / "MMS" / "mms-web")
    assert not (tmp_path / "roaming").exists()


def test_config_root_is_the_one_mms_resolves_not_a_second_opinion(tmp_path):
    """The descriptive field and the effective root are the same directory."""
    from mms_state_io import resolve_mms_config_dir

    env = {
        "USERPROFILE": str(tmp_path / "user"),
        "APPDATA": str(tmp_path / "roaming"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "MMS_CONFIG_ROOT": str(tmp_path / "explicit-root"),
    }
    descriptor = describe_platform(platform_name="win32", env=env)
    assert descriptor.config_root == str(Path(resolve_mms_config_dir(env)).resolve())

    without_override = {key: value for key, value in env.items() if key != "MMS_CONFIG_ROOT"}
    descriptor = describe_platform(platform_name="win32", env=without_override)
    assert descriptor.config_root == str(Path(resolve_mms_config_dir(without_override)).resolve())


def test_windows_browser_capabilities_keep_login_unknown_and_ego_unsupported():
    found = {"playwright", "agent-browser"}
    capabilities = browser_capabilities(platform_name="win32", which=lambda name: name if name in found else None)
    by_name = {item.backend: item for item in capabilities}
    assert by_name["edge-cdp"].supported and by_name["edge-cdp"].logged_in is None
    assert by_name["chrome-cdp"].supported and by_name["chrome-cdp"].logged_in is None
    assert by_name["agent-browser"].supported and by_name["agent-browser"].logged_in is False
    assert not by_name["ego"].supported
    assert "Windows" in by_name["ego"].reason
