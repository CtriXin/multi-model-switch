import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _runtime(**overrides):
    runtime = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "api_key": "sk-runtime",
        "openai_base_url": "https://relay.example.com/v1",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "supported_clis": ["claude", "codex"],
        "models": ["gpt-5.4", "gpt-5.5"],
    }
    runtime.update(overrides)
    return runtime


def _patch_real_home(monkeypatch, mms_launchers, real_home: Path):
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )


def test_get_export_env_includes_mms_model_name_for_standard_runners(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    _patch_real_home(monkeypatch, mms_launchers, real_home)

    runtime = _runtime(model="gpt-5.4")
    model_info = {"model": "gpt-5.4"}

    for cli in ("claude", "codex", "opencode", "pi"):
        exports = mms_launchers.get_export_env(cli, runtime, model_info=model_info)
        assert exports["MMS_MODEL_NAME"] == "gpt-5.4"


def test_get_export_env_includes_mms_model_name_for_opencode_heavy_omo(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    _patch_real_home(monkeypatch, mms_launchers, real_home)

    exports = mms_launchers.get_export_env(
        "opencode",
        _runtime(
            model="deepseek-chat",
            models=["deepseek-chat"],
            opencode_profile="heavy_omo",
            opencode_use_global_config=True,
        ),
    )

    assert exports["MMS_MODEL_NAME"] == "deepseek-chat"


def test_opencode_global_omo_env_includes_mms_model_name(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    _patch_real_home(monkeypatch, mms_launchers, real_home)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, *_args, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, *_args, **_kwargs: env)

    env = mms_launchers._opencode_global_omo_env(_runtime(model="deepseek-chat", models=["deepseek-chat"]))

    assert env["MMS_MODEL_NAME"] == "deepseek-chat"
