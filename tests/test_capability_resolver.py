from __future__ import annotations

import json
from pathlib import Path

import pytest

from mms_registry.capability_resolver import CapabilityBundleError
from mms_registry.capability_resolver import resolve_model_capabilities


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_JSON = ROOT / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"


def _reference_payload() -> dict:
    return json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))


def test_manual_override_wins_over_registry_profile_and_fallback() -> None:
    provider_profiles = {
        "profiles": {
            "fake": {
                "match": {"provider_id_contains": ["fake"], "model_prefixes": ["fake-model"]},
                "thinking": {"supported": True},
                "budget": {
                    "openai_chat": {
                        "path": "thinkingConfig.thinkingBudget",
                        "default": 2048,
                    }
                },
                "context_windows": {"fake-model": 100_000},
                "max_output_tokens": {"fake-model": 32_000},
            }
        }
    }
    approved = {
        "fake-model": {
            "context_window_tokens": 200_000,
            "max_output_tokens": 64_000,
            "supports_thinking": True,
            "thinking_control": {"control_type": "thinkingBudget", "path": "thinkingConfig.thinkingBudget"},
            "expected_protocol": "openai_chat_completions",
        }
    }

    caps = resolve_model_capabilities(
        "fake-model",
        provider_id="fake-provider",
        provider_profiles=provider_profiles,
        approved_facts=approved,
        manual_override={
            "context_window_tokens": 12_345,
            "max_output_tokens": 678,
            "supports_thinking": False,
            "thinking_control": {"control_type": "manual", "path": "manual.path"},
            "expected_protocol": "anthropic_messages",
        },
    )

    assert caps["context_window_tokens"] == 12_345
    assert caps["max_output_tokens"] == 678
    assert caps["supports_thinking"] is False
    assert caps["thinking_control"]["path"] == "manual.path"
    assert caps["expected_protocol"] == "anthropic_messages"
    assert caps["protocol_hints"]["preferred_protocol"] == "anthropic_messages"
    for field in ("context_window_tokens", "max_output_tokens", "supports_thinking", "thinking_control"):
        assert caps["sources"][field] == "manual_override"


def test_approved_registry_export_facts_win_over_provider_profile() -> None:
    provider_profiles = {
        "profiles": {
            "fake": {
                "match": {"provider_id_contains": ["fake"], "model_prefixes": ["fake-model"]},
                "thinking": {"supported": True},
                "budget": {
                    "openai_chat": {
                        "path": "thinkingConfig.thinkingBudget",
                        "default": 2048,
                    }
                },
                "context_windows": {"fake-model": 100_000},
                "max_output_tokens": {"fake-model": 32_000},
                "api_formats": {"openai_chat": {"request_path": "/chat/completions"}},
            }
        }
    }
    approved = {
        "models": [
            {
                "alias": "fake-model",
                "official_context_window_tokens": 300_000,
                "official_max_output_tokens": 96_000,
                "supports_thinking": True,
                "thinking_control": {"control_type": "thinking.type"},
                "expected_protocol": "anthropic_messages/openai_chat_completions",
            }
        ]
    }

    caps = resolve_model_capabilities(
        "fake-model",
        provider_id="fake-provider",
        provider_profiles=provider_profiles,
        approved_facts=approved,
    )

    assert caps["context_window_tokens"] == 300_000
    assert caps["max_output_tokens"] == 96_000
    assert caps["thinking_control"]["path"] == "thinking.type"
    assert caps["expected_protocol"] == "anthropic_messages/openai_chat_completions"
    assert caps["protocol_hints"]["preferred_protocol"] == "anthropic_messages"
    for field in ("context_window_tokens", "max_output_tokens", "thinking_control", "expected_protocol"):
        assert caps["sources"][field] == "approved_facts"


def test_model_policy_context_wins_over_approved_facts() -> None:
    caps = resolve_model_capabilities(
        "mimo-v2.5",
        approved_facts={"mimo-v2.5": {"context_window_tokens": 262_144}},
        model_policy={
            "models": {
                "mimo-v2.5": {
                    "capabilities": {
                        "context_window_tokens": 1_000_000,
                    }
                }
            }
        },
    )

    assert caps["context_window_tokens"] == 1_000_000
    assert caps["sources"]["context_window_tokens"] == "model_policy"


def test_model_policy_one_m_and_thinking_aliases_drive_capabilities() -> None:
    caps = resolve_model_capabilities(
        "mimo-v2.5",
        approved_facts={},
        model_policy={
            "models": {
                "mimo-v2.5": {
                    "capabilities": {
                        "one_m_context": True,
                        "thinking": True,
                    }
                }
            }
        },
    )

    assert caps["context_window_tokens"] == 1_000_000
    assert caps["sources"]["context_window_tokens"] == "model_policy"
    assert caps["supports_thinking"] is True
    assert caps["sources"]["supports_thinking"] == "model_policy"


def test_provider_profile_wins_over_conservative_fallback_and_preserves_mimo_alias(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    from mms_registry import provider_profiles

    provider_profiles.load_provider_profiles.cache_clear()
    caps = resolve_model_capabilities(
        "mimo-v2.5-pro",
        provider_id="mimo-direct",
        base_url="https://api.xiaomimimo.com/v1",
        approved_facts={},
    )

    assert caps["context_window_tokens"] == 1_048_576
    assert caps["max_output_tokens"] == 131_072
    assert caps["body_patch_aliases"]["parameter_aliases"]["openai_chat"]["max_tokens"] == "max_completion_tokens"
    assert caps["sources"]["context_window_tokens"] == "provider_profile"
    assert caps["sources"]["max_output_tokens"] == "provider_profile"
    assert caps["sources"]["body_patch_aliases"] == "provider_profile"


def test_provider_profile_marks_minimax_m3_as_one_m_context(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    from mms_registry import provider_profiles as mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()
    caps = resolve_model_capabilities(
        "MiniMax-M3",
        provider_id="minimax-direct",
        base_url="https://api.minimax.io/v1",
        approved_facts={},
    )

    assert caps["context_window_tokens"] == 1_000_000
    assert caps["supports_thinking"] is True
    assert caps["sources"]["context_window_tokens"] == "provider_profile"
    assert caps["sources"]["supports_thinking"] == "provider_profile"


def test_missing_or_corrupt_registry_facts_fall_back_safely(tmp_path) -> None:
    corrupt_path = tmp_path / "capabilities.json"
    corrupt_path.write_text("{not json", encoding="utf-8")

    caps = resolve_model_capabilities("unknown-model", approved_facts_path=corrupt_path)

    assert caps["context_window_tokens"] == 8_192
    assert caps["max_output_tokens"] == 4_096
    assert caps["supports_thinking"] is False
    assert caps["thinking_control"]["control_type"] == "none"
    assert caps["sources"]["context_window_tokens"] == "conservative_fallback"


def test_gemini_3_family_uses_thinking_level_not_numeric_budget() -> None:
    reference = _reference_payload()

    for model in ("gemini-3-flash-agent(high)", "gemini-3.1-pro-low", "gemini-3.5-flash-low"):
        caps = resolve_model_capabilities(
            model,
            provider_id="us-cpa-local-antigravity",
            approved_facts=reference,
        )

        assert caps["thinking_control"]["path"] == "thinkingConfig.thinkingLevel"
        assert caps["thinking_control"]["control_type"] == "thinkingLevel"
        assert caps["thinking_control"]["numeric_budget_tokens"] is None
        assert caps["thinking_control"]["path"] != "thinkingConfig.thinkingBudget"
        assert caps["sources"]["thinking_control"] == "approved_facts"


def test_gemini_25_profile_uses_numeric_thinking_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    from mms_registry import provider_profiles

    provider_profiles.load_provider_profiles.cache_clear()
    caps = resolve_model_capabilities(
        "gemini-2.5-pro",
        provider_id="gemini-direct",
        base_url="https://generativelanguage.googleapis.com",
        approved_facts={},
    )

    assert caps["thinking_control"]["path"] == "thinkingConfig.thinkingBudget"
    assert caps["thinking_control"]["control_type"] == "thinkingBudget"
    assert caps["thinking_control"]["numeric_budget_tokens"] == 8_192
    assert caps["sources"]["thinking_control"] == "provider_profile"


def test_glm_registry_facts_use_thinking_type_and_128k_output() -> None:
    caps = resolve_model_capabilities(
        "glm-5.1",
        provider_id="newapi-personal-tokyo",
        approved_facts=_reference_payload(),
    )

    assert caps["context_window_tokens"] == 200_000
    assert caps["max_output_tokens"] == 128_000
    assert caps["thinking_control"]["path"] == "thinking.type"
    assert caps["thinking_control"]["control_type"] == "thinking.type"
    assert caps["thinking_control"]["numeric_budget_tokens"] is None
    assert caps["thinking_control"]["path"] != "thinkingConfig.thinkingBudget"
    assert caps["sources"]["max_output_tokens"] == "approved_facts"


def test_cache_sensitive_dual_protocol_routes_keep_anthropic_first() -> None:
    approved = {
        "private-claude-like": {
            "context_window_tokens": 200_000,
            "max_output_tokens": 8_192,
            "expected_protocol": "anthropic_messages/openai_chat_completions",
            "cache_sensitive": True,
        }
    }

    caps = resolve_model_capabilities("private-claude-like", approved_facts=approved)

    assert caps["expected_protocol"] == "anthropic_messages/openai_chat_completions"
    assert caps["protocol_hints"]["preferred_protocol"] == "anthropic_messages"
    assert caps["protocol_hints"]["cache_sensitive_transport"] is True
    assert caps["protocol_hints"]["openai_chat_completions_is_fallback"] is True
    assert caps["protocol_hints"]["preferred_protocol"] != "openai_chat_completions"


def test_selected_root_missing_latest_approved_capabilities_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    with pytest.raises(CapabilityBundleError, match="latest-approved capabilities unavailable"):
        resolve_model_capabilities("missing-approved-model")


def test_stable_legacy_root_missing_latest_approved_capabilities_falls_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)

    caps = resolve_model_capabilities("legacy-unknown-model")

    assert caps["context_window_tokens"] == 8_192
    assert caps["sources"]["context_window_tokens"] == "conservative_fallback"
