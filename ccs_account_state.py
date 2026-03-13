"""账号本地状态同步辅助。"""

import json
import os


def seed_claude_state(home_dir):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    if not home_dir:
        return

    source_path = os.path.expanduser("~/.claude.json")
    if not os.path.exists(source_path):
        return

    target_path = os.path.join(home_dir, ".claude.json")
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            source_data = json.load(f)
        if not isinstance(source_data, dict):
            return
    except (OSError, json.JSONDecodeError):
        return

    target_data = {}
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                target_data = loaded
        except (OSError, json.JSONDecodeError):
            target_data = {}

    merged = dict(source_data)
    merged.update(target_data)
    os.makedirs(home_dir, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(target_path, 0o600)
