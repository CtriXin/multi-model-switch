from mms_tui import (
    _COLD_FAMILY_BUCKET_ID,
    _ECC_TOGGLE_KEY,
    _EFFORT_OPTIONS,
    _build_family_menu_items,
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
