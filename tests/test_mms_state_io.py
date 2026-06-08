from __future__ import annotations

from pathlib import Path


def test_mms_config_dir_counts_as_explicit_selected_root(tmp_path: Path) -> None:
    from mms_runtime.state_io import mms_config_root_is_explicit, mms_config_root_status

    config_root = tmp_path / "selected-root"
    env = {"MMS_CONFIG_DIR": str(config_root), "MMS_REAL_HOME": str(tmp_path / "home")}

    status = mms_config_root_status(env=env)

    assert mms_config_root_is_explicit(env) is True
    assert status["root_source"] == "MMS_CONFIG_DIR"
    assert status["mode"] == "preview"
    assert status["explicit_root"] is True
    assert status["config_root"] == str(config_root)


def test_xdg_config_home_is_not_explicit_preview_root(tmp_path: Path) -> None:
    from mms_runtime.state_io import mms_config_root_is_explicit, mms_config_root_status

    env = {"XDG_CONFIG_HOME": str(tmp_path / "xdg"), "MMS_REAL_HOME": str(tmp_path / "home")}

    status = mms_config_root_status(env=env)

    assert mms_config_root_is_explicit(env) is False
    assert status["root_source"] == "XDG_CONFIG_HOME"
    assert status["mode"] == "stable"
    assert status["explicit_root"] is False
    assert status["config_root"] == str(tmp_path / "xdg" / "mms")


def test_empty_env_does_not_inherit_preview_root(tmp_path: Path) -> None:
    from mms_runtime.state_io import mms_config_root_status

    config_root = tmp_path / "stable-root"

    status = mms_config_root_status(config_dir=config_root, env={})

    assert status["mode"] == "stable"
    assert status["root_source"] == "real_home"
    assert status["explicit_root"] is False
    assert status["config_root"] == str(config_root)
