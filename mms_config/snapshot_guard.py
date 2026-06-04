"""Audited config writes and snapshot guard helpers."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def config_write_target_path(*, active_config_path, config_path):
    return active_config_path() or config_path


def config_lock_path(config_path=None, *, config_write_target_path, config_lock_file):
    target_path = os.path.abspath(str(config_path or config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), config_lock_file)


def config_audit_path(config_path=None, *, config_write_target_path, config_audit_log):
    target_path = os.path.abspath(str(config_path or config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), config_audit_log)


def config_backup_root(config_path=None, *, config_write_target_path):
    target_path = os.path.abspath(str(config_path or config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), "backups")


def sha1_file(path):
    if not path or not os.path.exists(path):
        return ""
    h = hashlib.sha1()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def backup_config_file(
    config_path,
    *,
    config_backup_root,
    local_now_slug,
    path_exists=os.path.exists,
    makedirs=os.makedirs,
    copy2=shutil.copy2,
):
    if not path_exists(config_path):
        return ""
    backup_dir = os.path.join(config_backup_root(config_path), f"config-write-{local_now_slug()}")
    makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(config_path))
    copy2(config_path, backup_path)
    return backup_path


def append_config_audit_entry(entry, *, config_path, config_audit_path, makedirs=os.makedirs):
    audit_path = config_audit_path(config_path)
    makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def atomic_write_toml(path, cfg, *, tomli_w_module):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as handle:
            tomli_w_module.dump(cfg, handle)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def config_write_caller(
    *,
    current_file,
    stack_getter=inspect.stack,
    skip_functions=("save_config",),
):
    current = os.path.abspath(current_file)
    stack = stack_getter()
    try:
        for frame in stack[1:]:
            filename = os.path.abspath(str(frame.filename))
            if filename == current and frame.function in skip_functions:
                continue
            return {
                "path": filename,
                "line": int(frame.lineno),
                "function": str(frame.function or ""),
            }
    finally:
        del stack
    return {"path": current, "line": 0, "function": "unknown"}


@contextmanager
def locked_file_context(lock_path, *, process_lock, fcntl_module, makedirs=os.makedirs):
    makedirs(os.path.dirname(lock_path), exist_ok=True)
    with process_lock:
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl_module is not None:
                fcntl_module.flock(lock_file.fileno(), fcntl_module.LOCK_EX)
            try:
                yield
            finally:
                if fcntl_module is not None:
                    fcntl_module.flock(lock_file.fileno(), fcntl_module.LOCK_UN)


@contextmanager
def locked_config_write(config_path, *, config_lock_path, process_lock, fcntl_module):
    with locked_file_context(
        config_lock_path(config_path),
        process_lock=process_lock,
        fcntl_module=fcntl_module,
    ):
        yield


@contextmanager
def locked_state_file(path, *, process_lock, fcntl_module):
    lock_path = os.path.abspath(str(path or "")) + ".lock"
    with locked_file_context(lock_path, process_lock=process_lock, fcntl_module=fcntl_module):
        yield


def config_command_hint(*, current_command):
    return f"{current_command()} config api.edit"


def export_command_hint(cli_name, *, current_command):
    return f"{current_command()} --export {cli_name} --apply"


def base_user_config_path_from_gateway(config_path, *, gateway_session_markers):
    normalized = os.path.normpath(str(config_path or ""))
    for marker in gateway_session_markers:
        idx = normalized.find(marker)
        if idx == -1:
            continue
        base_home = normalized[:idx]
        if base_home:
            return os.path.join(base_home, ".config", "mms", "config.toml")
    return ""


def base_user_primary_dir_from_gateway(path, *, gateway_session_markers):
    normalized = os.path.normpath(str(path or ""))
    for marker in gateway_session_markers:
        idx = normalized.find(marker)
        if idx == -1:
            continue
        base_home = normalized[:idx]
        if base_home:
            return os.path.join(base_home, ".config", "mms")
    return ""


def active_sibling_path_from_gateway(
    path,
    *,
    filename,
    base_user_primary_dir_from_gateway,
    path_exists=os.path.exists,
):
    base_primary_dir = base_user_primary_dir_from_gateway(path)
    if base_primary_dir:
        base_path = os.path.join(base_primary_dir, filename)
        if path_exists(base_path):
            return base_path
    return path


def merge_base_user_broker_profiles(
    cfg,
    config_path,
    *,
    base_user_config_path_from_gateway,
    ensure_broker_config,
    path_exists=os.path.exists,
    normpath=os.path.normpath,
):
    base_config_path = base_user_config_path_from_gateway(config_path)
    if not base_config_path:
        return cfg, False
    if normpath(base_config_path) == normpath(config_path):
        return cfg, False
    if not path_exists(base_config_path):
        return cfg, False

    try:
        with open(base_config_path, "rb") as handle:
            base_cfg = tomllib.loads(handle.read().decode("utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return cfg, False

    if not isinstance(base_cfg, dict):
        return cfg, False

    active_profiles = cfg.get("broker_profiles")
    base_profiles = base_cfg.get("broker_profiles")
    if not isinstance(base_profiles, list) or not base_profiles:
        return cfg, False

    merged = dict(cfg)
    merged["broker_profiles"] = (
        list(active_profiles) if isinstance(active_profiles, list) else []
    ) + list(base_profiles)
    merged, _ = ensure_broker_config(merged)
    return merged, merged.get("broker_profiles") != cfg.get("broker_profiles")


def config_guard_root_dir(*, config_path=None, config_write_target_path, base_user_primary_dir_from_gateway):
    target_path = os.path.abspath(str(config_path or config_write_target_path()))
    base_primary_dir = base_user_primary_dir_from_gateway(target_path)
    if base_primary_dir:
        return base_primary_dir
    return os.path.dirname(target_path)


def config_snapshot_root(*, config_path=None, config_guard_root_dir, config_snapshot_dir):
    return os.path.join(config_guard_root_dir(config_path), config_snapshot_dir)


def config_snapshot_path(
    snapshot_kind,
    filename="latest.json",
    *,
    config_path=None,
    config_snapshot_root,
):
    return os.path.join(config_snapshot_root(config_path), snapshot_kind, filename)


def ensure_mms_config_guard_files(
    *,
    config_path=None,
    config_guard_root_dir,
    render_agents_guard,
    render_claude_guard,
    config_backup_root,
    local_now_slug,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    read_text=None,
    write_text=None,
    copy2=shutil.copy2,
    chmod=os.chmod,
):
    def default_read_text(path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def default_write_text(path, content):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    read_text = default_read_text if read_text is None else read_text
    write_text = default_write_text if write_text is None else write_text

    root_dir = config_guard_root_dir(config_path)
    makedirs(root_dir, exist_ok=True)
    guard_payloads = {
        "AGENTS.md": render_agents_guard(),
        "CLAUDE.md": render_claude_guard(),
    }
    backup_dir = ""
    for filename, content in guard_payloads.items():
        target_path = os.path.join(root_dir, filename)
        existing = ""
        if path_exists(target_path):
            try:
                existing = read_text(target_path)
            except OSError:
                existing = ""
        if existing == content:
            continue
        if existing:
            if not backup_dir:
                backup_dir = os.path.join(
                    config_backup_root(os.path.join(root_dir, "config.toml")),
                    f"guardrails-{local_now_slug()}",
                )
                makedirs(backup_dir, exist_ok=True)
            copy2(target_path, os.path.join(backup_dir, filename))
        write_text(target_path, content)
        try:
            chmod(target_path, 0o600)
        except OSError:
            pass


def snapshot_proxy_fingerprint(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    parsed = urlparse(proxy_url)
    scheme = parsed.scheme or "proxy"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    auth = "+auth" if parsed.username or parsed.password else ""
    return f"{scheme}://{host}{port}{auth}"


def is_snapshot_ignored_file(path, *, ignored_files):
    name = os.path.basename(str(path or ""))
    return name in ignored_files


def sha256_text(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def snapshot_cli_state(home_dir, cli_name):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    if not home_dir:
        return []
    if cli_name == "claude":
        return [
            os.path.join(home_dir, ".claude", "settings.json"),
        ]
    if cli_name == "codex":
        return [
            os.path.join(home_dir, ".codex", "auth.json"),
            os.path.join(home_dir, ".codex", "config.toml"),
        ]
    if cli_name == "gemini":
        return [
            os.path.join(home_dir, ".gemini", "settings.json"),
            os.path.join(home_dir, ".gemini", ".env"),
        ]
    if cli_name == "agy":
        return [
            os.path.join(home_dir, ".gemini", "antigravity-cli", "settings.json"),
        ]
    return []


def normalize_claude_state_snapshot_payload(data):
    data = data if isinstance(data, dict) else {}
    oauth_account = data.get("oauthAccount") if isinstance(data.get("oauthAccount"), dict) else {}
    return {
        "userID": str(data.get("userID") or "").strip(),
        "oauthAccount": {
            "accountUuid": str(oauth_account.get("accountUuid") or "").strip(),
            "emailAddress": str(oauth_account.get("emailAddress") or "").strip(),
            "organizationUuid": str(oauth_account.get("organizationUuid") or "").strip(),
            "billingType": str(oauth_account.get("billingType") or "").strip(),
            "displayName": str(oauth_account.get("displayName") or "").strip(),
            "organizationRole": str(oauth_account.get("organizationRole") or "").strip(),
            "workspaceRole": str(oauth_account.get("workspaceRole") or "").strip(),
            "organizationName": str(oauth_account.get("organizationName") or "").strip(),
        },
    }


def normalize_claude_settings_snapshot_payload(data, *, session_env_keys):
    data = dict(data) if isinstance(data, dict) else {}
    env_data = data.get("env")
    if isinstance(env_data, dict):
        cleaned_env = {
            key: value
            for key, value in env_data.items()
            if str(key or "").strip() not in session_env_keys
        }
        if cleaned_env:
            data["env"] = cleaned_env
        else:
            data.pop("env", None)
    return data


def snapshot_claude_identity_entry(
    home_dir,
    *,
    normalize_claude_state_snapshot_payload,
    mask_identity_value,
    mask_email_value,
    sha256_text,
):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    target = os.path.join(home_dir, ".claude.json")
    if not target or not os.path.exists(target):
        return {"fingerprint": "", "sha256": ""}
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"fingerprint": "", "sha256": ""}
    normalized = normalize_claude_state_snapshot_payload(data)
    oauth = normalized.get("oauthAccount") if isinstance(normalized.get("oauthAccount"), dict) else {}
    fingerprint = "|".join(
        [
            mask_identity_value(normalized.get("userID") or "", keep=4),
            mask_identity_value(oauth.get("accountUuid") or "", keep=4),
            mask_identity_value(oauth.get("organizationUuid") or "", keep=4),
            mask_email_value(oauth.get("emailAddress") or ""),
        ]
    )
    return {
        "fingerprint": fingerprint,
        "sha256": sha256_text(json.dumps(normalized, ensure_ascii=False, sort_keys=True)),
    }


def snapshot_account_entry(
    account,
    *,
    default_priority,
    default_timezone,
    normalize_priority,
    normalize_timezone_name,
    runtime_force_ipv4,
    snapshot_proxy_fingerprint,
    sha256_text,
    snapshot_claude_identity_entry,
):
    account = account if isinstance(account, dict) else {}
    proxy_value = str(account.get("proxy") or "").strip()
    home_dir = os.path.expanduser(str(account.get("home_dir") or "").strip())
    identity = snapshot_claude_identity_entry(home_dir) if str(account.get("cli") or "").strip() == "claude" else {}
    return {
        "id": str(account.get("id") or "").strip(),
        "cli": str(account.get("cli") or "").strip(),
        "enabled": bool(account.get("enabled", True)),
        "home_dir": home_dir,
        "priority": normalize_priority(account.get("priority", default_priority)),
        "claude_1m_mode": str(account.get("claude_1m_mode") or "auto").strip(),
        "timezone": normalize_timezone_name(account.get("timezone"), default_timezone),
        "force_ipv4": bool(runtime_force_ipv4(account)),
        "no_proxy": str(account.get("no_proxy") or "").strip(),
        "proxy_fingerprint": snapshot_proxy_fingerprint(proxy_value),
        "proxy_sha256": sha256_text(proxy_value),
        "identity_fingerprint": identity.get("fingerprint", ""),
        "identity_sha256": identity.get("sha256", ""),
    }


def snapshot_provider_entry(
    provider,
    *,
    default_priority,
    default_timezone,
    normalize_priority,
    normalize_timezone_name,
    runtime_force_ipv4,
    snapshot_proxy_fingerprint,
    sha256_text,
):
    provider = provider if isinstance(provider, dict) else {}
    proxy_value = str(provider.get("proxy") or "").strip()
    return {
        "id": str(provider.get("id") or "").strip(),
        "name": str(provider.get("name") or "").strip(),
        "enabled": bool(provider.get("enabled", True)),
        "priority": normalize_priority(provider.get("priority", default_priority)),
        "models_endpoint": str(provider.get("models_endpoint") or "").strip(),
        "timezone": normalize_timezone_name(provider.get("timezone"), default_timezone),
        "force_ipv4": bool(runtime_force_ipv4(provider)),
        "no_proxy": str(provider.get("no_proxy") or "").strip(),
        "proxy_fingerprint": snapshot_proxy_fingerprint(proxy_value),
        "proxy_sha256": sha256_text(proxy_value),
    }


def build_config_guard_snapshot(
    cfg,
    *,
    config_path=None,
    default_config,
    config_write_target_path,
    config_guard_root_dir,
    config_snapshot_schema,
    iso_now,
    snapshot_account_entry,
    snapshot_cli_state,
    snapshot_provider_entry,
    is_snapshot_ignored_file,
    snapshot_file_entry,
    environ=None,
):
    cfg = cfg if isinstance(cfg, dict) else default_config()
    config_path = os.path.abspath(str(config_path or config_write_target_path()))
    config_root = config_guard_root_dir(config_path)
    environ = os.environ if environ is None else environ
    real_home = os.path.expanduser(
        str(environ.get("MMS_REAL_HOME") or environ.get("ORIGINAL_HOME") or environ.get("REAL_HOME") or "~")
    )

    files = [
        os.path.join(config_root, "override.toml"),
        os.path.join(config_root, "credentials.sh"),
        os.path.join(config_root, "usage.json"),
        os.path.join(config_root, "account-guard-state.json"),
        os.path.join(config_root, "AGENTS.md"),
        os.path.join(config_root, "CLAUDE.md"),
    ]
    accounts = []
    for account in cfg.get("accounts", []):
        if not isinstance(account, dict):
            continue
        entry = snapshot_account_entry(account)
        accounts.append(entry)
        files.extend(snapshot_cli_state(entry.get("home_dir"), entry.get("cli")))
    providers = [
        snapshot_provider_entry(provider)
        for provider in cfg.get("providers", [])
        if isinstance(provider, dict)
    ]

    deduped_files = []
    seen_paths = set()
    for path in files:
        normalized = os.path.abspath(os.path.expanduser(str(path)))
        if is_snapshot_ignored_file(normalized):
            continue
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        deduped_files.append(snapshot_file_entry(normalized))

    return {
        "schema": config_snapshot_schema,
        "captured_at": iso_now(),
        "config_root": config_root,
        "config_path": config_path,
        "real_home": real_home,
        "defaults": {
            "provider_default": str(cfg.get("provider", {}).get("default") or "").strip(),
            "account_defaults": dict(cfg.get("account", {}).get("defaults") or {}),
        },
        "accounts": sorted(accounts, key=lambda item: item.get("id", "")),
        "providers": sorted(providers, key=lambda item: item.get("id", "")),
        "files": sorted(deduped_files, key=lambda item: item.get("path", "")),
    }


def snapshot_file_content_bytes(path, *, session_env_keys):
    absolute_path = os.path.abspath(os.path.expanduser(str(path)))
    if os.path.basename(absolute_path) == ".claude.json":
        with open(absolute_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        normalized = normalize_claude_state_snapshot_payload(data)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8"), "claude_state_identity"
    if (
        os.path.basename(absolute_path) == "settings.json"
        and os.path.basename(os.path.dirname(absolute_path)) == ".claude"
    ):
        with open(absolute_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        normalized = normalize_claude_settings_snapshot_payload(data, session_env_keys=session_env_keys)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8"), "claude_settings_runtime_stripped"
    with open(absolute_path, "rb") as handle:
        return handle.read(), ""


def snapshot_file_entry(path, *, snapshot_file_content_bytes):
    absolute_path = os.path.abspath(os.path.expanduser(str(path)))
    entry = {"path": absolute_path, "exists": os.path.exists(absolute_path)}
    if not entry["exists"]:
        return entry
    try:
        stat = os.stat(absolute_path)
        entry["size"] = int(stat.st_size)
        entry["mtime"] = int(stat.st_mtime)
    except OSError:
        entry["size"] = 0
        entry["mtime"] = 0
    try:
        normalized_bytes, normalized_kind = snapshot_file_content_bytes(absolute_path)
    except OSError:
        entry["read_error"] = True
        return entry
    entry["sha256"] = hashlib.sha256(normalized_bytes).hexdigest()
    if normalized_kind:
        entry["normalized_kind"] = normalized_kind
    return entry


def snapshot_digest(snapshot_data):
    payload = json.dumps(snapshot_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json_snapshot(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_json_snapshot(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def snapshot_period_bucket(period_name, *, now_func=datetime.now):
    now = now_func()
    if period_name == "daily":
        return now.strftime("%Y-%m-%d")
    if period_name == "weekly":
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
    return now.strftime("%Y-%m-%dT%H:%M")


def update_periodic_snapshot(
    period_name,
    snapshot_data,
    *,
    config_path=None,
    config_snapshot_path,
    snapshot_period_bucket,
    iso_now,
    snapshot_digest,
    write_json_snapshot,
):
    path = config_snapshot_path(period_name, "latest.json", config_path=config_path)
    payload = {
        "period": period_name,
        "bucket": snapshot_period_bucket(period_name),
        "captured_at": iso_now(),
        "digest": snapshot_digest(snapshot_data),
        "snapshot": snapshot_data,
    }
    write_json_snapshot(path, payload)


def snapshot_prompt_allowed(*, stdin=None, stdout=None):
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    try:
        return stdin.isatty() and stdout.isatty()
    except Exception:
        return False


def confirm_startup_snapshot_drift(
    diff_lines,
    *,
    accepted_path,
    latest_path,
    ensure_rich,
    panel_cls,
    confirm_ask,
    snapshot_prompt_allowed,
    console,
):
    ensure_rich()
    preview = "\n".join(f"- {line}" for line in diff_lines[:12])
    if len(diff_lines) > 12:
        preview += f"\n- ... 还有 {len(diff_lines) - 12} 项"
    panel_text = (
        "检测到 MMS 配置/关键文件与上次确认快照不一致，已阻止静默启动。\n\n"
        f"{preview}\n\n"
        f"accepted: {accepted_path}\n"
        f"latest:   {latest_path}\n"
    )
    console.print(panel_cls(panel_text, title="MMS Snapshot Guard", border_style="red"))
    if not snapshot_prompt_allowed():
        return False
    return bool(confirm_ask("是否接受当前快照并继续启动？", default=False))


def ensure_startup_snapshot_guard(
    cfg,
    *,
    enforce=True,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    iso_now,
    snapshot_digest,
    write_json_snapshot,
    update_periodic_snapshot,
    load_json_snapshot,
    snapshot_diff_lines,
    confirm_startup_snapshot_drift,
    command_name,
    config_guard_exit_code,
    console,
    exit_func=sys.exit,
):
    config_path = config_write_target_path()
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)

    latest_payload = {
        "kind": "startup",
        "captured_at": iso_now(),
        "digest": snapshot_digest(current_snapshot),
        "snapshot": current_snapshot,
    }
    write_json_snapshot(latest_path, latest_payload)
    update_periodic_snapshot("daily", current_snapshot, config_path=config_path)
    update_periodic_snapshot("weekly", current_snapshot, config_path=config_path)

    accepted_payload = load_json_snapshot(accepted_path)
    accepted_snapshot = (accepted_payload or {}).get("snapshot") if isinstance(accepted_payload, dict) else None
    if not accepted_snapshot:
        write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot)
    if not diff_lines:
        write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    pending_path = config_snapshot_path("startup", "pending.json", config_path=config_path)
    write_json_snapshot(
        pending_path,
        {
            "kind": "startup-pending",
            "captured_at": iso_now(),
            "accepted_path": accepted_path,
            "latest_path": latest_path,
            "diffs": diff_lines,
            "accepted": accepted_snapshot,
            "current": current_snapshot,
        },
    )
    if not enforce:
        return current_snapshot
    if confirm_startup_snapshot_drift(diff_lines, accepted_path=accepted_path, latest_path=latest_path):
        write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    command = command_name() if callable(command_name) else str(command_name)
    console.print(
        f"[red]启动已阻止：检测到配置/关键文件漂移，请先确认快照。[/red]\n"
        f"[dim]漂移详情: {pending_path}[/dim]\n"
        f"[dim]查看: {command} guard status[/dim]\n"
        f"[dim]接受: {command} guard accept[/dim]"
    )
    exit_func(config_guard_exit_code)
