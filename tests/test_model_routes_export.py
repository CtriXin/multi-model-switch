from __future__ import annotations

import json
import re
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


def _patch_export_paths(monkeypatch, tmp_path):
    import mms_router

    monkeypatch.setattr(mms_router, "MODEL_ROUTES_PATH", str(tmp_path / "model-routes.json"))
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_SNAPSHOTS_DIR", str(tmp_path / "model-routes.snapshots"))


def test_export_model_routes_writes_minimal_hive_contract_and_snapshot(monkeypatch, tmp_path):
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
    _patch_export_paths(monkeypatch, tmp_path)

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
    assert list(info) == ["primary", "fallbacks"]
    assert info["primary"] == {
        "provider_id": "kimi-direct",
        "anthropic_base_url": "https://kimi.example.com/anthropic",
        "openai_base_url": "",
        "api_key": "sk-kimi",
    }
    assert info["fallbacks"] == []

    latest_path = tmp_path / "model-routes.json"
    written = json.loads(latest_path.read_text(encoding="utf-8"))
    assert list(written) == ["version", "generated_at", "routes"]
    assert written["version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", written["generated_at"])
    assert list(written["routes"]["kimi-k2.5"]) == ["primary", "fallbacks"]
    assert list(written["routes"]["kimi-k2.5"]["primary"]) == [
        "provider_id",
        "anthropic_base_url",
        "openai_base_url",
        "api_key",
    ]

    snapshots = sorted((tmp_path / "model-routes.snapshots").glob("*.json"))
    assert len(snapshots) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", snapshots[0].stem)
    assert json.loads(snapshots[0].read_text(encoding="utf-8")) == written
    assert stat.S_IMODE(latest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshots[0].stat().st_mode) == 0o600


def test_export_model_routes_reuses_snapshot_when_content_unchanged(monkeypatch, tmp_path):
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
    _patch_export_paths(monkeypatch, tmp_path)

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

    first_routes = mms_router.export_model_routes(cfg, force=True)
    first_written = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))

    second_routes = mms_router.export_model_routes(cfg, force=True)
    second_written = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))

    assert second_routes == first_routes
    assert second_written["generated_at"] == first_written["generated_at"]
    assert len(list((tmp_path / "model-routes.snapshots").glob("*.json"))) == 1


def test_export_model_routes_creates_new_snapshot_when_key_changes(monkeypatch, tmp_path):
    import mms_router

    contexts = {
        "qwen-openai": {
            "id": "qwen-openai",
            "provider_name": "Qwen OpenAI",
            "anthropic_base_url": "",
            "openai_base_url": "https://qwen.example.com/v1",
            "api_key": "sk-qwen-old",
            "models": ["qwen3.5-plus"],
        }
    }
    _patch_export_dependencies(monkeypatch, contexts=contexts)
    _patch_export_paths(monkeypatch, tmp_path)

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

    mms_router.export_model_routes(cfg, force=True)
    contexts["qwen-openai"]["api_key"] = "sk-qwen-new"
    mms_router.export_model_routes(cfg, force=True)

    latest = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))
    snapshots = sorted((tmp_path / "model-routes.snapshots").glob("*.json"))

    assert latest["routes"]["qwen3.5-plus"]["primary"]["api_key"] == "sk-qwen-new"
    assert len(snapshots) == 2


def test_export_model_routes_keeps_only_minimal_fields_for_hive(monkeypatch, tmp_path):
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
    _patch_export_paths(monkeypatch, tmp_path)

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
    assert list(info["primary"]) == ["provider_id", "anthropic_base_url", "openai_base_url", "api_key"]
    assert info["primary"]["provider_id"] == "openai-relay-high-priority"
    assert info["fallbacks"][0]["provider_id"] == "kimi-direct-compatible"
    assert "priority" not in info["primary"]
    assert "role" not in info["primary"]


def test_export_model_routes_prefers_higher_priority_before_default_provider(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "default-low-priority": {
                "id": "default-low-priority",
                "provider_name": "Default Low",
                "anthropic_base_url": "",
                "openai_base_url": "https://default.example.com/v1",
                "api_key": "sk-default",
                "models": ["qwen3-coder-plus"],
            },
            "high-priority": {
                "id": "high-priority",
                "provider_name": "High Priority",
                "anthropic_base_url": "",
                "openai_base_url": "https://high.example.com/v1",
                "api_key": "sk-high",
                "models": ["qwen3-coder-plus"],
            },
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "default-low-priority"},
        "providers": [
            {
                "id": "default-low-priority",
                "role": "auto",
                "priority": 10,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
            {
                "id": "high-priority",
                "role": "auto",
                "priority": 90,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["qwen3-coder-plus"]
    assert info["primary"]["provider_id"] == "high-priority"
    assert info["fallbacks"][0]["provider_id"] == "default-low-priority"


def test_export_model_routes_keeps_gemini_models_for_gemini_provider(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "us-cpa-local-gemini": {
                "id": "us-cpa-local-gemini",
                "provider_name": "US CPA Gemini",
                "anthropic_base_url": "http://127.0.0.1:18417/v1",
                "openai_base_url": "http://127.0.0.1:18417/v1",
                "api_key": "sk-gemini",
                "models": ["gemini-3.1-pro-preview"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "us-cpa-local-gemini"},
        "providers": [
            {
                "id": "us-cpa-local-gemini",
                "role": "auto",
                "priority": 80,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["gemini"],
                "models": ["gemini-3.1-pro-preview"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    assert routes["gemini-3.1-pro-preview"]["primary"]["provider_id"] == "us-cpa-local-gemini"
    assert routes["gemini-3.1-pro-preview"]["fallbacks"] == []


def test_save_provider_credentials_triggers_routes_export(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_core, "CREDENTIALS_PATH", str(tmp_path / "credentials.sh"))
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False: calls.append((cfg, force)) or {},
    )

    mms_core.save_provider_credentials("demo", "https://demo.example.com/v1", "sk-demo")

    assert (tmp_path / "credentials.sh").exists()
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True)
    ]


def test_refresh_routes_export_for_hive_loads_current_config(monkeypatch):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False: calls.append((cfg, force)) or {},
    )

    assert mms_core._refresh_routes_export_for_hive(force=True, quiet=True) is True
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True)
    ]


def test_handle_provider_default_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [{"id": "demo-a"}, {"id": "demo-b"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "save_config", lambda updated_cfg: calls.append(("save", updated_cfg["provider"]["default"])))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_default_config(cfg, ["demo-b"])

    assert cfg["provider"]["default"] == "demo-b"
    assert calls == [
        ("save", "demo-b"),
        ("refresh", True, False),
    ]


def test_handle_provider_remove_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [{"id": "demo-a"}, {"id": "demo-b"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "_ensure_interactive_terminal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core.Confirm, "ask", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(mms_core, "save_config", lambda updated_cfg: calls.append(("save", [item["id"] for item in updated_cfg["providers"]])))
    monkeypatch.setattr(mms_core, "_delete_provider_credentials", lambda provider_id: calls.append(("delete_creds", provider_id)))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda provider_id: calls.append(("invalidate", provider_id)))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_remove_config(cfg, ["demo-a"])

    assert calls == [
        ("save", ["demo-b"]),
        ("delete_creds", "demo-a"),
        ("invalidate", "demo-a"),
        ("refresh", True, False),
    ]


def test_handle_provider_edit_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo"},
        "providers": [{"id": "demo", "name": "Demo"}],
    }
    updated_cfg = {
        "provider": {"default": "demo"},
        "providers": [{"id": "demo", "name": "Renamed Demo"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "_prompt_provider_metadata", lambda **_kwargs: {"id": "demo", "name": "Renamed Demo"})
    monkeypatch.setattr(mms_core, "_upsert_provider", lambda _cfg, _provider: updated_cfg)
    monkeypatch.setattr(mms_core, "save_config", lambda saved_cfg: calls.append(("save", saved_cfg["providers"][0]["name"])))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda provider_id: calls.append(("invalidate", provider_id)))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_edit_config(cfg, ["demo"])

    assert calls == [
        ("save", "Renamed Demo"),
        ("invalidate", "demo"),
        ("refresh", True, False),
    ]


def test_main_refreshes_routes_snapshot_before_subcommand_dispatch(monkeypatch):
    import mms_core

    cfg = {"provider": {"default": "demo"}, "providers": []}
    events = []
    monkeypatch.setattr(mms_core.sys, "argv", ["mms", "ls"])
    monkeypatch.setattr(mms_core, "_extract_global_lang", lambda argv: (argv, None))
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "set_language", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda *_args, **_kwargs: "zh")
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_load_command_config", lambda: cfg)
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda current_cfg=None, **kwargs: events.append(("refresh", current_cfg, kwargs.get("force"))) or True,
    )
    monkeypatch.setattr(
        mms_core,
        "handle_models_command",
        lambda current_cfg, args: events.append(("models", current_cfg, list(args))),
    )

    mms_core.main()

    assert events == [
        ("refresh", cfg, True),
        ("models", cfg, []),
    ]


def test_select_provider_template_always_defaults_to_generic(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core.Prompt,
        "ask",
        staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Prompt.ask should not be called"))),
    )

    assert mms_core._select_provider_template() == "generic"
    assert mms_core._select_provider_template("qwen") == "generic"
