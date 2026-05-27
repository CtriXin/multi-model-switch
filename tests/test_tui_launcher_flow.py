from __future__ import annotations

from mms_tui_launcher_flow import provider_browse_options


def test_provider_browse_options_filters_and_dedupes_candidates() -> None:
    provider = {"id": "current"}
    default_models = ["gpt-5.4"]
    candidates = [
        (
            {
                "id": "p1",
                "name": "Provider One",
                "api_key": "k",
                "role": "primary",
                "priority": 300,
                "supported_clis": ["codex"],
            },
            False,
        ),
        (
            {"id": "p1", "name": "Provider One Duplicate", "api_key": "k", "supported_clis": ["codex"]},
            False,
        ),
        (
            {
                "id": "disabled",
                "name": "Disabled",
                "api_key": "k",
                "enabled": False,
                "supported_clis": ["codex"],
            },
            False,
        ),
        ({"id": "no-key", "name": "No Key", "supported_clis": ["codex"]}, False),
        (
            {"id": "claude-only", "name": "Claude Only", "api_key": "k", "supported_clis": ["claude"]},
            False,
        ),
        ({"name": "Default Provider", "api_key": "k", "supported_clis": ["codex"]}, False),
    ]

    def provider_candidates(cfg, current_provider, models):
        assert cfg == {"cfg": True}
        assert current_provider is provider
        assert models is default_models
        return candidates

    result = provider_browse_options(
        {"cfg": True},
        provider,
        default_models,
        "codex",
        provider_candidates=provider_candidates,
        default_provider_id="default",
        provider_supports_cli_name=lambda item, cli: cli in item.get("supported_clis", []),
        provider_label=lambda item: item.get("name") or item.get("id"),
    )

    assert result == [
        {"id": "p1", "name": "Provider One", "role": "primary", "priority": 300},
        {"id": "default", "name": "Default Provider", "role": "auto", "priority": 100},
    ]
