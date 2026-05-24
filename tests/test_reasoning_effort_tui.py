import ast
from pathlib import Path

from mms_tui import (
    _COLD_FAMILY_BUCKET_ID,
    _ECC_TOGGLE_KEY,
    _EFFORT_OPTIONS,
    _build_family_menu_items,
    _confirm_effort_values,
    _confirm_profile_capabilities,
    confirm_tui,
    select_reasoning_effort_tui,
)


def test_reasoning_effort_options_include_xhigh():
    values = [value for value, _label in _EFFORT_OPTIONS]
    assert values == ["low", "medium", "high", "xhigh"]


def test_reasoning_effort_tui_defaults_to_high():
    assert select_reasoning_effort_tui.__defaults__ == ("high",)


def test_confirm_tui_thinking_and_effort_defaults():
    assert confirm_tui.__kwdefaults__["thinking_enabled_default"] is True
    assert confirm_tui.__kwdefaults__["reasoning_effort_default"] == "high"
    assert confirm_tui.__kwdefaults__["ecc_enabled_default"] is False
    assert confirm_tui.__kwdefaults__["agent_pack_default"] == "none"
    assert confirm_tui.__kwdefaults__["nsr_enabled_default"] is True


def test_confirm_profile_capabilities_read_mimo_thinking(monkeypatch, tmp_path):
    import mms_provider_profiles

    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    mms_provider_profiles.load_provider_profiles.cache_clear()

    caps = _confirm_profile_capabilities(
        "mimo-v2-pro",
        {
            "id": "mimo-direct-anthropic",
            "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        },
    )

    assert caps["profile"] == "mimo"
    assert caps["thinking_supported"] is True
    assert caps["effort_supported"] is False
    assert caps["default_enabled"] is True


def test_confirm_profile_capabilities_apply_model_defaults(monkeypatch, tmp_path):
    import mms_provider_profiles

    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    mms_provider_profiles.load_provider_profiles.cache_clear()

    qwen_caps = _confirm_profile_capabilities(
        "qwen-plus",
        {
            "id": "dashscope",
            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    )
    deepseek_caps = _confirm_profile_capabilities(
        "deepseek-v4-pro",
        {
            "id": "deepseek",
            "anthropic_base_url": "https://api.deepseek.com/anthropic",
        },
    )

    assert qwen_caps["profile"] == "dashscope-openai"
    assert qwen_caps["default_enabled"] is False
    assert deepseek_caps["effort_supported"] is True
    assert _confirm_effort_values(deepseek_caps, deepseek_caps["tokens"]) == ["high", "xhigh"]


def test_core_confirm_tui_keeps_ecc_default_off():
    tree = ast.parse(Path("mms_core.py").read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_safe_tui_call":
            continue
        if not node.args or not isinstance(node.args[0], ast.Name) or node.args[0].id != "confirm_tui":
            continue

        keyword_values = {keyword.arg: keyword.value for keyword in node.keywords}
        ecc_default = keyword_values.get("ecc_enabled_default")
        assert isinstance(ecc_default, ast.Constant)
        assert ecc_default.value is False
        pack_default = keyword_values.get("agent_pack_default")
        assert isinstance(pack_default, ast.Call)
        assert "runtime" in keyword_values
        return

    raise AssertionError("confirm_tui launch call was not found")


def test_confirm_tui_ecc_hotkey_is_fixed_x():
    assert _ECC_TOGGLE_KEY == "X"


def test_build_family_menu_items_inserts_cold_bucket_when_collapsed():
    items = _build_family_menu_items(
        [
            {"family": "GPT", "count": 7, "is_cold": False},
            {"family": "DeepSeek", "count": 2, "is_cold": False},
            {"family": "MiniMax", "count": 1, "is_cold": True},
            {"family": "Mimo", "count": 1, "is_cold": True},
        ],
        search_query="",
        cold_expanded=False,
    )

    assert [item[1].get("family", item[1].get("id")) for item in items] == [
        "GPT",
        "DeepSeek",
        _COLD_FAMILY_BUCKET_ID,
    ]


def test_build_family_menu_items_expands_cold_families():
    items = _build_family_menu_items(
        [
            {"family": "GPT", "count": 7, "is_cold": False},
            {"family": "MiniMax", "count": 1, "is_cold": True},
        ],
        search_query="",
        cold_expanded=True,
    )

    assert [item[0] for item in items] == ["family", "cold_bucket", "family"]
    assert items[-1][1]["family"] == "MiniMax"
