from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mms_runtime import broker as mms_broker
import mms_launchers


def test_normalize_broker_profile_uses_generic_defaults():
    profile = mms_broker.normalize_broker_profile({})

    assert profile["owner_user_id"] == "default-user"
    assert profile["device_id"] == "local-device"
    assert profile["workspace_id"] == "default-workspace"


def test_broker_launch_defaults_to_new_when_model_override_present():
    assert mms_broker._default_launch_mode_for_model_override("") == "resume_last"
    assert mms_broker._default_launch_mode_for_model_override("glm-5.1") == "new"


def test_prune_session_only_snapshot_entries_uses_local_hooks_dir(monkeypatch, tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    feishu_guard = hooks_dir / "claude-feishu-webfetch-guard.sh"
    hive_compact = hooks_dir / "hive-compact-hook.sh"
    feishu_guard.write_text("#!/bin/sh\n", encoding="utf-8")
    hive_compact.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(mms_launchers, "_LOCAL_HOOKS_DIR", str(hooks_dir))
    snapshot = {
        "hooks": {
            "preToolUse": [
                {
                    "matcher": "*",
                    "commands": [
                        str(feishu_guard),
                        f"bash {hive_compact}",
                        "echo keep-me",
                    ],
                }
            ]
        }
    }

    pruned = mms_launchers._prune_session_only_snapshot_entries(snapshot)

    assert pruned["hooks"]["preToolUse"][0]["commands"] == ["echo keep-me"]


def test_sensitive_claude_provider_can_be_marked_without_hardcoded_id(monkeypatch):
    monkeypatch.delenv("MMS_CLAUDE_SENSITIVE_PROVIDER_IDS", raising=False)
    monkeypatch.delenv("MMS_CLAUDE_DISABLE_1M_PROVIDER_IDS", raising=False)
    runtime = {"id": "relay-a", "skip_anthropic_probe": True, "claude_1m_mode": "auto"}

    assert mms_launchers._runtime_is_sensitive_claude_provider(runtime) is True
    assert mms_launchers._runtime_supports_claude_1m(runtime) is False


def test_sensitive_claude_provider_ids_can_come_from_local_env(monkeypatch):
    monkeypatch.setenv("MMS_CLAUDE_SENSITIVE_PROVIDER_IDS", "relay-a, relay-b")
    monkeypatch.setenv("MMS_CLAUDE_DISABLE_1M_PROVIDER_IDS", "relay-b")

    assert mms_launchers._runtime_is_sensitive_claude_provider({"id": "relay-a"}) is True
    assert mms_launchers._runtime_supports_claude_1m({"id": "relay-b", "claude_1m_mode": "auto"}) is False


def test_known_k26_context_window_is_not_unknown():
    assert mms_launchers._lookup_context_window("K2.6-code-preview", provider_id="newapi-personal-tokyo") == 262_144
