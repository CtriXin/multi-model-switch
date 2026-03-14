"""账号本地状态同步辅助。"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager

# Directory where mms caches per-account OAuth tokens for mms usage
_MMS_TOKEN_CACHE_DIR = os.path.expanduser("~/.mms/token_cache")


def _read_keychain_claude_oauth() -> dict | None:
    """Return the claudeAiOauth dict from macOS Keychain, or None."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip()).get("claudeAiOauth") or None
    except Exception:
        return None


def _jwt_account_id(token: str) -> str | None:
    """Extract the Anthropic account UUID from a Claude OAuth JWT, or None."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(part))
        # Anthropic JWTs embed the account UUID in the 'sub' field or
        # in a custom claim; fall back to hashing the token prefix so
        # the cache key is stable even when we cannot parse it.
        return payload.get("sub") or payload.get("account_id")
    except Exception:
        return None


def cache_current_claude_token() -> str | None:
    """Read the active Claude OAuth token from Keychain and persist it to
    ~/.mms/token_cache/<account_id>.json.

    Returns the account_id string on success, None on failure.
    This should be called at the END of every Claude OAuth session so that
    ``mms usage`` can query any account's plan utilization independently of
    which account is currently active.
    """
    oauth = _read_keychain_claude_oauth()
    if not oauth:
        return None
    token = oauth.get("accessToken")
    if not token:
        return None

    account_id = _jwt_account_id(token) or token[:16]  # stable fallback
    os.makedirs(_MMS_TOKEN_CACHE_DIR, exist_ok=True)
    path = os.path.join(_MMS_TOKEN_CACHE_DIR, f"{account_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(oauth, f, ensure_ascii=False)
        os.chmod(path, 0o600)
        return account_id
    except Exception:
        return None


def load_cached_claude_tokens() -> list[dict]:
    """Return all cached Claude OAuth dicts from ~/.mms/token_cache/."""
    results = []
    if not os.path.isdir(_MMS_TOKEN_CACHE_DIR):
        return results
    for fname in os.listdir(_MMS_TOKEN_CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_MMS_TOKEN_CACHE_DIR, fname)
        try:
            results.append(json.loads(open(path).read()))
        except Exception:
            pass
    return results


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


def seed_gemini_state(home_dir):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    if not home_dir:
        return

    source_dir = os.path.expanduser("~/.gemini")
    target_dir = os.path.join(home_dir, ".gemini")
    os.makedirs(target_dir, exist_ok=True)
    if not os.path.isdir(source_dir):
        return

    for filename in ("settings.json", ".env", "GEMINI.md"):
        source_path = os.path.join(source_dir, filename)
        target_path = os.path.join(target_dir, filename)
        if not os.path.exists(source_path) or os.path.exists(target_path):
            continue
        try:
            shutil.copy2(source_path, target_path)
        except OSError:
            continue
        if filename in {"settings.json", ".env"}:
            try:
                os.chmod(target_path, 0o600)
            except OSError:
                pass


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
        # After CLI session: cache the keychain token (keyed by account UUID)
        # so that `mms usage` can query any account independently later.
        cache_current_claude_token()
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
