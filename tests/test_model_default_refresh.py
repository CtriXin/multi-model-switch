from __future__ import annotations


def test_refresh_all_provider_model_defaults_preserves_manual_overrides(monkeypatch):
    import mms_core

    saved = []

    def fake_probe(provider, emit_output=False, force_refresh=False):
        assert force_refresh is True
        return {"models": ["new-model", "keep-hidden"], "base_source": "remote"}

    monkeypatch.setattr(mms_core, "_probe_models", fake_probe)
    monkeypatch.setattr(mms_core, "save_config", lambda cfg: saved.append(cfg))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda _provider_id: None)

    cfg = {
        "providers": [
            {
                "id": "demo",
                "name": "Demo",
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "fallback_models": ["old-default"],
                "extra_models": ["manual-extra"],
                "hidden_models": ["keep-hidden"],
                "models": [
                    {"id": "new-model", "source": "remote", "capabilities": {"thinking": True}},
                ],
            }
        ],
    }

    result = mms_core._refresh_all_provider_model_defaults(cfg, emit_output=False)

    assert result["ok"] is True
    assert result["refreshed_providers"] == 1
    assert saved
    provider = result["config"]["providers"][0]
    assert provider["extra_models"] == ["manual-extra"]
    assert provider["hidden_models"] == ["keep-hidden"]
    rows = {row["id"]: row for row in provider["models"]}
    assert rows["new-model"]["source"] == "remote"
    assert rows["new-model"]["capabilities"] == {"thinking": True}
    assert rows["keep-hidden"]["visible"] is False


def test_refresh_all_provider_model_defaults_skips_identical_rows(monkeypatch):
    import mms_core

    saved = []

    monkeypatch.setattr(
        mms_core,
        "_probe_models",
        lambda provider, emit_output=False, force_refresh=False: {
            "models": ["same-model"],
            "base_source": "remote",
        },
    )
    monkeypatch.setattr(mms_core, "save_config", lambda cfg: saved.append(cfg))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda _provider_id: None)

    cfg = {
        "providers": [
            {
                "id": "demo",
                "enabled": True,
                "models": [{"id": "same-model", "source": "remote", "visible": True}],
            }
        ],
    }

    result = mms_core._refresh_all_provider_model_defaults(cfg, emit_output=False)

    assert result["ok"] is True
    assert result["refreshed_providers"] == 0
    assert saved == []
