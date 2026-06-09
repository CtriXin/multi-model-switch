from __future__ import annotations

from mms_display.confirm_state import (
    build_confirm_detail_lines,
    collect_preview_items,
    initial_disabled_surfaces,
    normalize_caveman_level,
    supports_claude_1m_toggle,
)


def test_collect_preview_items_merges_enabled_scopes_and_dedupes() -> None:
    catalog = {
        "hooks": {
            "always": [
                {"title": "base", "summary": "always", "details": [("path", "/tmp/a")]},
                ("tuple", "item"),
            ],
            "caveman": [{"title": "caveman", "summary": "enabled"}],
            "nsr": [{"title": "base", "summary": "always", "details": [("path", "/tmp/a")]}],
            "omc": [{"title": "omc", "summary": "pack", "disable_key": "pack/omc"}],
        }
    }

    items = collect_preview_items(
        catalog,
        "hooks",
        caveman_enabled=True,
        nsr_enabled=True,
        agent_pack="omc",
    )

    assert [item["title"] for item in items] == ["base", "tuple", "caveman", "omc"]
    assert items[-1]["disable_key"] == "pack/omc"


def test_build_confirm_detail_lines_masks_secrets_and_limits_env_before_context() -> None:
    lines = build_confirm_detail_lines(
        {
            "ANTHROPIC_BASE_URL": "https://example.test",
            "OPENAI_API_KEY": "sk-1234567890",
            "MMS_ACTIVE_MODEL": "gpt-5",
            "CUSTOM_MODEL": "custom",
            "IGNORED": "value",
        },
        [("Fake", "enabled")],
    )

    assert any(value == "https://example.test" and style == "detail" for _label, value, style in lines)
    assert any(value == "sk-1****7890" and style == "detail" for _label, value, style in lines)
    assert ("MMS_AC…", "gpt-5", "detail") not in lines
    assert lines[-1][1:] == ("enabled", "fake")
    assert len(lines) == 5


def test_initial_disabled_surfaces_normalizes_aliases() -> None:
    result = initial_disabled_surfaces(
        {
            "disabled_session_surfaces": {
                "mcp_servers": ["filesystem", ""],
                "skill": "caveman",
                "hook": {"not": "accepted"},
                "hooks": {"stop", "compact"},
            }
        }
    )

    assert result == {
        "mcp": {"filesystem"},
        "skills": {"caveman"},
        "hooks": {"stop", "compact"},
    }


def test_caveman_level_and_claude_1m_helpers() -> None:
    assert normalize_caveman_level("lite") == "light"
    assert normalize_caveman_level("ULTRA") == "full"
    assert supports_claude_1m_toggle({"model": "claude-sonnet-4"}) is True
    assert supports_claude_1m_toggle({"model": "claude-haiku-4"}) is False
