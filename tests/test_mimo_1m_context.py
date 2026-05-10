from __future__ import annotations


def _empty_context_overrides():
    return {"models": {}, "provider_overrides": {}}


def test_mimo_pro_1m_suffix_uses_one_m_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )
    assert (
        mms_launchers._effective_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 1_000_000
    )


def test_mimo_pro_without_1m_suffix_keeps_safe_context(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_model_context_overrides", _empty_context_overrides)

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro",
            provider_id="mimo-direct-anthropic",
        )
        == 262_144
    )


def test_exact_1m_context_override_wins_before_suffix_stripping(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_load_model_context_overrides",
        lambda: {
            "models": {"mimo-v2.5-pro[1m]": 900_000, "mimo-v2.5-pro": 262_144},
            "provider_overrides": {},
        },
    )

    assert (
        mms_launchers._lookup_context_window(
            "mimo-v2.5-pro[1m]",
            provider_id="mimo-direct-anthropic",
        )
        == 900_000
    )
