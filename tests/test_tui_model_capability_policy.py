from __future__ import annotations

import json


def test_tui_profile_capabilities_read_model_policy_think_and_reasoning(monkeypatch, tmp_path):
    import mms_tui

    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    (tmp_path / "model-policy.json").write_text(
        json.dumps(
            {
                "models": {
                    "mimo-v2.5": {
                        "capabilities": {
                            "thinking": True,
                            "reasoning": True,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    caps = mms_tui._confirm_profile_capabilities({"model": "mimo-v2.5"})

    assert caps["thinking_supported"] is True
    assert caps["default_enabled"] is True
    assert caps["effort_supported"] is True
