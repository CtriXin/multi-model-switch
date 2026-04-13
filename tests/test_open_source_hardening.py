from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mms_broker
import mms_launchers


def test_normalize_broker_profile_uses_generic_defaults():
    profile = mms_broker.normalize_broker_profile({})

    assert profile["owner_user_id"] == "default-user"
    assert profile["device_id"] == "local-device"
    assert profile["workspace_id"] == "default-workspace"


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
