from __future__ import annotations

import json
import stat


def _patch_export_dependencies(monkeypatch, *, contexts):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "resolve_provider_context",
        lambda _cfg, provider_id: dict(contexts[provider_id]),
    )
    monkeypatch.setattr(
        mms_core,
        "_probe_models",
        lambda ctx, emit_output=False: {"models": list(ctx.get("models", []))},
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda provider_def, cached_models, _cfg: list(cached_models or provider_def.get("models", [])),
    )
    monkeypatch.setattr(mms_core, "_provider_label", lambda ctx: str(ctx.get("provider_name") or ctx.get("id") or "provider"))
    monkeypatch.setattr(mms_core, "_load_usage_stats", lambda: {"sources": {}})


def test_export_model_routes_marks_anthropic_domestic_route_as_claude_native(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "kimi-direct": {
                "id": "kimi-direct",
                "provider_name": "Kimi Direct",
                "anthropic_base_url": "https://kimi.example.com/anthropic",
                "openai_base_url": "",
                "api_key": "sk-kimi",
                "models": ["kimi-k2.5"],
            }
        },
    )
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_PATH", str(tmp_path / "model-routes.json"))

    cfg = {
        "provider": {"default": "kimi-direct"},
        "providers": [
            {
                "id": "kimi-direct",
                "role": "auto",
                "priority": 75,
                "enabled": True,
                "protocols": ["anthropic_messages"],
                "supported_clis": ["kimi"],
                "models": ["kimi-k2.5"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["kimi-k2.5"]
    assert info["cli_modes"]["claude"] == "native"
    assert "claude" in info["native_clis"]
    assert "claude" not in info["bridge_clis"]
    assert "bridge_required" not in info["capabilities"]

    written = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))
    assert written["routes"]["kimi-k2.5"]["cli_modes"]["claude"] == "native"
    assert stat.S_IMODE((tmp_path / "model-routes.json").stat().st_mode) == 0o600


def test_export_model_routes_keeps_openai_only_domestic_route_as_claude_bridge(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "qwen-openai": {
                "id": "qwen-openai",
                "provider_name": "Qwen OpenAI",
                "anthropic_base_url": "",
                "openai_base_url": "https://qwen.example.com/v1",
                "api_key": "sk-qwen",
                "models": ["qwen3.5-plus"],
            }
        },
    )
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_PATH", str(tmp_path / "model-routes.json"))

    cfg = {
        "provider": {"default": "qwen-openai"},
        "providers": [
            {
                "id": "qwen-openai",
                "role": "auto",
                "priority": 60,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3.5-plus"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["qwen3.5-plus"]
    assert info["cli_modes"]["claude"] == "bridge"
    assert "claude" in info["bridge_clis"]
    assert "bridge_required" in info["capabilities"]


def test_export_model_routes_prefers_claude_compatible_kimi_route_over_higher_priority_bridge_only_route(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "openai-relay-high-priority": {
                "id": "openai-relay-high-priority",
                "provider_name": "OpenAI Relay",
                "anthropic_base_url": "https://crs.example.com/openai",
                "openai_base_url": "https://crs.example.com/openai",
                "api_key": "sk-relay",
                "models": ["kimi-k2.5"],
            },
            "kimi-direct-compatible": {
                "id": "kimi-direct-compatible",
                "provider_name": "Kimi Direct",
                "anthropic_base_url": "https://kimi.example.com/anthropic",
                "openai_base_url": "https://kimi.example.com/v1",
                "api_key": "sk-kimi",
                "models": ["kimi-k2.5"],
            },
        },
    )
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_PATH", str(tmp_path / "model-routes.json"))

    cfg = {
        "provider": {"default": "openai-relay-high-priority"},
        "providers": [
            {
                "id": "openai-relay-high-priority",
                "role": "auto",
                "priority": 110,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["codex"],
                "models": ["kimi-k2.5"],
            },
            {
                "id": "kimi-direct-compatible",
                "role": "auto",
                "priority": 100,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["kimi"],
                "models": ["kimi-k2.5"],
            },
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["kimi-k2.5"]
    assert info["provider_id"] == "kimi-direct-compatible"
    assert info["cli_modes"]["claude"] == "native"
    assert info["fallback_routes"][0]["provider_id"] == "openai-relay-high-priority"
