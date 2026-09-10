"""Vision capability truth and Pi's image relay.

Covers issue #112: a model's vision verdict must come from one shared source
so the same setting holds in every harness, and the relay must only load for
models that genuinely cannot read images themselves.
"""

import json
import re

import pytest

import mms_pi_support as pi_support
from mms_capability_resolver import resolve_model_capabilities


def _caps(model, **kwargs):
    return resolve_model_capabilities(model, **kwargs)


def test_user_policy_vision_setting_reaches_pi():
    """A vision flag set in the WebUI must change what Pi tells the model."""
    for wanted in (True, False):
        caps = _caps(
            "deepseek-v4-flash",
            profile_id="deepseek",
            model_policy={"models": {"deepseek-v4-flash": {"capabilities": {"supports_vision": wanted}}}},
        )
        types = pi_support._pi_model_input_types("deepseek-v4-flash", caps=caps)
        assert ("image" in types) is wanted


def test_provider_profile_vision_reaches_pi_without_a_hint_entry():
    caps = _caps("minimax-m3", profile_id="minimax")
    assert pi_support._pi_model_input_types("minimax-m3", caps=caps) == ["text", "image"]


def test_models_without_declared_vision_stay_text_only():
    for model, profile in (
        ("deepseek-v4-pro", "deepseek"),
        ("glm-5.2", "glm"),
    ):
        caps = _caps(model, profile_id=profile)
        assert pi_support._pi_model_input_types(model, caps=caps) == ["text"], model


def test_pi_specific_hint_outranks_stale_calibration_facts():
    """minimax-m2.7 is pinned text-only by a Pi-side finding; keep it pinned."""
    caps = {"supports_vision": True, "sources": {"supports_vision": "approved_facts"}}
    assert caps["sources"]["supports_vision"] == "approved_facts"
    assert caps["supports_vision"] is True
    assert pi_support._pi_model_input_types("minimax-m2.7", caps=caps) == ["text"]


def test_conservative_fallback_is_not_read_as_a_no_vision_answer():
    """An undeclared model falls through to the hint tables, not to "no vision"."""
    fallback_caps = {"supports_vision": False, "sources": {"supports_vision": "conservative_fallback"}}
    assert pi_support._pi_model_input_types("k3", caps=fallback_caps) == ["text", "image"]
    assert pi_support._pi_model_input_types("k3", caps=None) == ["text", "image"]


def _vision_runtime(monkeypatch, models):
    runtime = {
        "id": "relay-vision",
        "name": "Relay Vision",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
    }
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": list(models)}
    )
    return runtime


def test_multimodal_start_keeps_pool_for_later_text_model(monkeypatch):
    runtime = _vision_runtime(monkeypatch, ["k3", "minimax-m3"])
    plan = pi_support._pi_vision_plan(runtime, "k3")
    assert plan["main_model_vision"] is True
    assert [entry["selector"] for entry in plan["pool"]] == ["k3", "minimax-m3"]


def test_text_only_main_model_gets_the_channel_vision_models(monkeypatch):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    plan = pi_support._pi_vision_plan(runtime, "deepseek-v4-pro")
    assert plan["main_model_vision"] is False
    assert [entry["selector"] for entry in plan["pool"]] == ["minimax-m3"]


def test_pool_holds_every_vision_model_on_the_channel(monkeypatch):
    """No preferred model and no built-in name list: the pool is the capability."""
    runtime = _vision_runtime(
        monkeypatch, ["deepseek-v4-pro", "k3", "minimax-m3", "glm-5.2"]
    )
    plan = pi_support._pi_vision_plan(runtime, "deepseek-v4-pro")
    assert [entry["selector"] for entry in plan["pool"]] == ["k3", "minimax-m3"]


def test_channel_without_minimax_still_has_a_pool(monkeypatch):
    """No MiniMax on this channel must not mean no image support at all."""
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "k3"])
    plan = pi_support._pi_vision_plan(runtime, "deepseek-v4-pro")
    assert [entry["selector"] for entry in plan["pool"]] == ["k3"]


def test_channel_with_no_vision_model_reports_an_empty_pool(monkeypatch):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "glm-5.2"])
    plan = pi_support._pi_vision_plan(runtime, "deepseek-v4-pro")
    assert plan["pool"] == []


def test_disabled_vision_sidecar_registers_no_relay(monkeypatch):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    monkeypatch.setattr(pi_support, "_pi_vision_relay_enabled", lambda: False)
    plan = pi_support._pi_vision_plan(runtime, "deepseek-v4-flash")
    assert plan["pool"] == []


def test_relay_is_enabled_unless_config_turns_it_off(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core, "load_config", lambda *a, **k: {})
    assert pi_support._pi_vision_relay_enabled() is True
    monkeypatch.setattr(
        mms_core, "load_config", lambda *a, **k: {"vision_sidecar": {"enabled": False}}
    )
    assert pi_support._pi_vision_relay_enabled() is False


def _without_comments(source: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def test_no_model_name_selects_the_relay(monkeypatch):
    """Selection must follow configuration, not a maintained name list."""
    extension = (
        pi_support.Path(pi_support.__file__).resolve().parent
        / "scripts/pi-vision-extension.ts"
    ).read_text(encoding="utf-8")
    code = _without_comments(extension)
    for name in ("MiniMax", "minimax", "kimi", "mimo", "gpt-5"):
        assert name not in code, name
    assert "PRIORITY" not in code

    plan_source = pi_support.Path(pi_support.__file__).read_text(encoding="utf-8")
    body = plan_source[plan_source.index("def _pi_vision_plan"):]
    body = body[: body.index("\ndef ", 1)]
    for name in ("minimax", "kimi", "gpt-", "mimo"):
        assert name not in body.lower(), name
