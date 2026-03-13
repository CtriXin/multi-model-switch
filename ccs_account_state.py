"""账号本地状态同步辅助。"""

import json
import os
import tempfile
from contextlib import contextmanager


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


def _claude_state_path(home_dir=None):
    base_dir = os.path.expanduser(str(home_dir or "~").strip())
    return os.path.join(base_dir, ".claude.json")


@contextmanager
def activated_claude_account_state(home_dir):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    if not home_dir:
        yield
        return

    seed_claude_state(home_dir)

    live_path = _claude_state_path("~")
    account_path = _claude_state_path(home_dir)
    backup_path = None
    original_exists = os.path.exists(live_path)

    try:
        if original_exists:
            fd, backup_path = tempfile.mkstemp(prefix="mms-claude-backup-", suffix=".json")
            os.close(fd)
            with open(live_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        if os.path.exists(account_path):
            with open(account_path, "rb") as src, open(live_path, "wb") as dst:
                dst.write(src.read())
            os.chmod(live_path, 0o600)
        yield
    finally:
        try:
            if os.path.exists(live_path):
                with open(live_path, "rb") as src, open(account_path, "wb") as dst:
                    dst.write(src.read())
                os.chmod(account_path, 0o600)
        except OSError:
            pass

        try:
            if original_exists and backup_path and os.path.exists(backup_path):
                with open(backup_path, "rb") as src, open(live_path, "wb") as dst:
                    dst.write(src.read())
                os.chmod(live_path, 0o600)
            elif not original_exists and os.path.exists(live_path):
                os.remove(live_path)
        finally:
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
