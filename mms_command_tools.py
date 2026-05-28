"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    import tomllib
except ImportError:
    import tomli as tomllib


CONFIG_HELP_TOPICS = {
    "-h",
    "--help",
    "help",
    "preferences",
    "preferences.help",
    "preference.help",
    "preferences.path",
    "preference.path",
    "preferences.example",
    "preference.example",
    "preferences.doc",
    "preference.doc",
    "web",
    "webui",
    "setup.web",
    "setup-web",
    "gates",
    "human-gate",
    "humangate",
    "human-gates",
}


def normalize_ui_config(cfg, *, normalize_language, default_language="zh"):
    cfg = dict(cfg)
    raw_ui = cfg.get("ui")
    current = raw_ui if isinstance(raw_ui, dict) else {}
    lang = normalize_language(current.get("language", "")) or default_language
    new_cfg = dict(cfg)
    new_cfg["ui"] = {"language": lang}
    return new_cfg, new_cfg != cfg


def resolve_ui_language(
    cfg=None,
    cli_override=None,
    *,
    normalize_language,
    load_version_meta,
    environ=None,
    default_language="zh",
):
    environ = os.environ if environ is None else environ
    cli_lang = normalize_language(cli_override)
    if cli_lang:
        return cli_lang
    env_lang = normalize_language(environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    if isinstance(cfg, dict):
        ui_lang = normalize_language((cfg.get("ui") or {}).get("language", ""))
        if ui_lang:
            return ui_lang
    locale_lang = normalize_language(environ.get("LC_ALL", "") or environ.get("LANG", ""))
    if locale_lang:
        return locale_lang
    version_meta = load_version_meta()
    version_lang = normalize_language(
        version_meta.get("preferred_language", "") if isinstance(version_meta, dict) else ""
    )
    if version_lang:
        return version_lang
    return default_language


def extract_global_lang(argv, *, normalize_language):
    cleaned = []
    lang = ""
    idx = 0
    while idx < len(argv):
        item = argv[idx]
        if item == "--lang" and idx + 1 < len(argv):
            candidate = normalize_language(argv[idx + 1])
            if candidate:
                lang = candidate
                idx += 2
                continue
        cleaned.append(item)
        idx += 1
    return cleaned, lang


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


def load_toml_file(path, *, toml_loads):
    with open(path, "rb") as handle:
        return toml_loads(handle.read().decode("utf-8"))


def existing_paths(paths, *, path_exists=os.path.exists):
    return [path for path in paths if path_exists(path)]


def load_user_preferences_from_paths(
    *,
    existing_preferences_paths,
    load_toml_file,
    merge_dicts,
    sanitize_user_preferences,
    console,
    toml_error_types=(),
):
    merged = {}
    errors = (OSError,) + tuple(toml_error_types or ())
    for path in existing_preferences_paths():
        try:
            prefs = load_toml_file(path)
        except errors as exc:
            console.print(f"[yellow]跳过无效 preferences 文件 {path}: {exc}[/yellow]")
            continue
        if isinstance(prefs, dict):
            merged = merge_dicts(merged, prefs)
    return sanitize_user_preferences(merged)


def apply_local_overrides(
    cfg,
    *,
    existing_override_paths,
    load_toml_file,
    merge_dicts,
    load_user_preferences,
    console,
    toml_error_types=(),
):
    merged = dict(cfg)
    errors = (OSError,) + tuple(toml_error_types or ())
    for path in existing_override_paths():
        try:
            override_cfg = load_toml_file(path)
        except errors as exc:
            console.print(f"[yellow]跳过无效 override 文件 {path}: {exc}[/yellow]")
            continue
        if isinstance(override_cfg, dict):
            merged = merge_dicts(merged, override_cfg)
    merged["_mms_preferences"] = load_user_preferences()
    return merged


def preference_asset_root(asset_name, *, asset_root_keys, load_user_preferences):
    key = asset_root_keys.get(str(asset_name or "").strip().lower())
    if not key:
        return ""
    return str(load_user_preferences().get("assets", {}).get("roots", {}).get(key) or "").strip()


def iso_now(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now_slug(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now()
    return now.strftime("%Y%m%d-%H%M%S")


def load_usage_stats_from_path(usage_path, *, path_exists=os.path.exists):
    if not path_exists(usage_path):
        return {"sources": {}}
    try:
        with open(usage_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("sources", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sources": {}}


def write_usage_stats_locked(
    usage_path,
    data,
    *,
    ensure_mms_config_guard_files,
    config_write_target_path,
    makedirs=os.makedirs,
    replace=os.replace,
    chmod=os.chmod,
):
    ensure_mms_config_guard_files(config_write_target_path())
    makedirs(os.path.dirname(usage_path), exist_ok=True)
    tmp_path = usage_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    replace(tmp_path, usage_path)
    chmod(usage_path, 0o600)


def trigger_routes_export_after_usage_write(
    *,
    lock,
    is_running,
    set_running,
    get_last_started_at,
    set_last_started_at,
    min_interval_sec,
    refresh_routes_export_for_hive,
    thread_cls,
    monotonic,
):
    now = monotonic()
    with lock:
        if is_running():
            return
        if now - get_last_started_at() < min_interval_sec:
            return
        set_running(True)
        set_last_started_at(now)

    def _run():
        try:
            refresh_routes_export_for_hive(force=True, quiet=True)
        except Exception:
            pass
        finally:
            with lock:
                set_running(False)

    thread_cls(
        target=_run,
        daemon=True,
        name="mms-usage-routes-export",
    ).start()


def backup_config_tree(
    label,
    *,
    resolve_real_user_home,
    primary_config_dir,
    local_now_slug,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    copytree=shutil.copytree,
):
    backup_root = os.path.join(resolve_real_user_home(), ".config", "mms-backups")
    makedirs(backup_root, exist_ok=True)
    backup_dir = os.path.join(backup_root, f"{label}-{local_now_slug()}")
    makedirs(backup_dir, exist_ok=True)
    if path_exists(primary_config_dir):
        copytree(
            primary_config_dir,
            os.path.join(backup_dir, os.path.basename(primary_config_dir)),
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
    return backup_dir


def refresh_routes_export_for_hive(
    cfg=None,
    *,
    force=True,
    quiet=False,
    startup_safe=False,
    load_config,
    apply_local_overrides,
    export_model_routes,
    console,
):
    try:
        current_cfg = cfg
        if current_cfg is None:
            current_cfg = load_config()
            if current_cfg is None:
                return False
            current_cfg = apply_local_overrides(current_cfg)
        export_model_routes(current_cfg, force=force, startup_safe=startup_safe)
        return True
    except Exception as exc:
        if not quiet:
            console.print(f"[yellow]⚠ Hive routes export 刷新失败: {exc}[/yellow]")
        return False


def confirm_guard_accept_from_tui(
    cfg,
    *,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    confirm_startup_snapshot_drift,
    console,
):
    config_path = config_write_target_path()
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []
    if not diff_lines:
        console.print("[green]当前快照没有 drift，不需要 accept。[/green]")
        return False
    return confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
    )


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def save_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def record_trace_override(trace_enabled, trace_overrides, source, **kv):
    if not trace_enabled:
        return
    trace_overrides.append((source, {k: v for k, v in kv.items() if v is not None}))


def trace_source_for(field, value, trace_overrides):
    expected = str(value or "").strip()
    if not expected:
        return "(not set)"
    fallback_source = ""
    generic_match = ""
    prefer_explicit = field in {"cli", "provider", "account", "model"}
    for source, kv in reversed(trace_overrides or []):
        if field not in kv:
            continue
        candidate = str(kv.get(field) or "").strip()
        if candidate == expected:
            if prefer_explicit and source == "runtime resolve":
                generic_match = source
                continue
            return source
        if not fallback_source:
            fallback_source = source
    return fallback_source or generic_match or "runtime result"


def format_launch_trace(
    cli_name,
    model_info,
    runtime,
    trace_overrides,
    *,
    runtime_provider_id,
    runtime_account_id,
    runtime_bridge,
):
    model = ""
    if isinstance(model_info, dict):
        model = model_info.get("model", "")
    elif isinstance(model_info, str):
        model = model_info

    provider_id = runtime_provider_id(runtime)
    account_id = runtime_account_id(runtime)
    auth_mode = runtime.get("auth_mode", "") if isinstance(runtime, dict) else ""
    bridge = runtime_bridge(runtime)

    lines = [
        "",
        "[MMS Trace]",
        f"  cli:      {cli_name or '-'} <- {trace_source_for('cli', cli_name, trace_overrides)}",
        f"  provider: {provider_id or '-'} <- {trace_source_for('provider', provider_id, trace_overrides)}",
        f"  account:  {account_id or '-'} <- {trace_source_for('account', account_id, trace_overrides)}",
        f"  model:    {model or '-'} <- {trace_source_for('model', model, trace_overrides)}",
        f"  bridge:   {bridge or '-'} <- {trace_source_for('bridge', bridge, trace_overrides)}",
        f"  runtime:  {auth_mode or '-'} <- {trace_source_for('runtime', auth_mode, trace_overrides)}",
        "",
        "Override chain:",
    ]
    if trace_overrides:
        for source, kv in trace_overrides:
            if kv:
                parts = ", ".join(f"{k}={v}" for k, v in kv.items())
                lines.append(f"  {source:<16s}-> {parts}")
            else:
                lines.append(f"  {source:<16s}-> (none)")
    else:
        lines.append("  (no overrides recorded)")
    lines.append("")
    return "\n".join(lines)


def compact_tui_report_value(value, max_len=96):
    text = str(value if value is not None else "-").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text or "-"
    return text[: max(1, max_len - 1)].rstrip() + "…"


def settings_result_tui_payload(title, rows, note="", *, ok=True, localize):
    prefix = "✓ " if ok else "✗ "
    info_lines = [(localize("状态", "Status"), localize("成功", "OK") if ok else localize("失败", "Failed"))]
    info_lines.extend(
        (str(label or "-"), compact_tui_report_value(value, max_len=120))
        for label, value in list(rows or [])
    )
    if note:
        info_lines.append((localize("说明", "Note"), compact_tui_report_value(note, max_len=160)))
    return (
        f"{prefix}{title}",
        info_lines,
        [("back", localize("返回", "Back"))],
    )


def settings_result_tui_available(*, env=None, stdin=None, stdout=None):
    env = os.environ if env is None else env
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    disabled = str(env.get("MMS_DISABLE_SETTINGS_RESULT_TUI") or "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    try:
        return bool(stdin.isatty() and stdout.isatty())
    except Exception:
        return False


def select_settings_result_tui(title, rows, note="", *, ok=True, settings_result_tui_payload, select_channel_action_tui):
    tui_title, info_lines, actions = settings_result_tui_payload(title, rows, note, ok=ok)
    return select_channel_action_tui(tui_title, info_lines, actions)


def print_settings_result_report(
    title,
    rows,
    note="",
    *,
    ok=True,
    settings_result_tui_available,
    select_settings_result_tui,
    mark_tui_rendered,
    clear_tui_rendered,
    ensure_rich,
    display_settings_result_report,
    console,
):
    if settings_result_tui_available():
        try:
            select_settings_result_tui(title, rows, note, ok=ok)
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception:
            clear_tui_rendered()
        else:
            mark_tui_rendered()
            return

    ensure_rich()
    return display_settings_result_report(title, rows, note, ok=ok, console=console)


def print_settings_error_report(title, exc, *, print_settings_result_report, localize):
    return print_settings_result_report(
        title,
        [(localize("错误", "Error"), exc)],
        localize("操作未完成；没有改变 runtime defaults。", "Operation did not complete; runtime defaults unchanged."),
        ok=False,
    )


def pause_after_tui_report(prompt_text="按 Enter 返回", *, tui_rendered, clear_tui_rendered, ensure_rich, input_func, console):
    if tui_rendered():
        clear_tui_rendered()
        return

    ensure_rich()
    try:
        console.print(f"[dim]{prompt_text}[/dim]")
    except Exception:
        pass
    try:
        input_func()
    except (EOFError, KeyboardInterrupt):
        pass


def display_settings_result_report(title, rows, note="", *, ok=True, console):
    color = "green" if ok else "red"
    prefix = "✓ " if ok else "✗ "
    console.print(f"[{color}]{prefix}{title}[/{color}]")
    for label, value in rows:
        console.print(f"[cyan]{label}[/cyan] {compact_tui_report_value(value)}")
    if note:
        console.print(f"[dim]{note}[/dim]")


def model_validation_findings(provider, probe, *, provider_label):
    findings = []
    error_kind = probe.get("error_kind")
    provider_name = provider_label(provider)
    if error_kind == "protocol_unsupported":
        findings.append({
            "severity": "high",
            "title": "当前 provider 不支持模型探测",
            "summary": f"{provider_name} 没有声明 openai_chat_completions，无法访问 /v1/models。",
        })
    elif error_kind in {"missing_credentials", "missing_base_url", "missing_api_key"}:
        findings.append({
            "severity": "high",
            "title": "当前 provider 凭据不完整",
            "summary": f"{provider_name} 还缺少地址或 Key，无法验证可用模型。",
        })
    elif error_kind == "empty_models":
        findings.append({
            "severity": "medium",
            "title": "接口连通，但没有拿到模型列表",
            "summary": f"{provider_name} 返回了空列表，可能是账号权限或网关映射问题。",
        })
    elif error_kind == "missing_httpx":
        findings.append({
            "severity": "high",
            "title": "本地缺少依赖",
            "summary": "当前环境缺少 httpx，暂时无法做模型探测。",
        })
    else:
        findings.append({
            "severity": "high",
            "title": "模型校验失败",
            "summary": probe.get("error") or f"{provider_name} 暂时无法拉取模型列表。",
        })
    if provider.get("id"):
        findings.append({
            "severity": "low",
            "title": "可以跳过校验继续",
            "summary": "预设和直接 CLI 启动仍然可以继续使用，但模型浏览会受限。",
        })
    return findings


def rank_recovery_actions(actions):
    return sorted(
        actions,
        key=lambda item: (
            item.get("priority", 999),
            0 if item.get("recommended") else 1,
            item.get("title", ""),
        ),
    )


def build_model_recovery_actions(cfg, provider, probe, *, provider_map):
    providers = provider_map(cfg)
    active_provider_id = provider.get("id")
    actions = [
        {
            "id": "edit_credentials",
            "title": "重新输入地址和 Key",
            "summary": "修复当前 provider 的地址或认证信息。",
            "priority": 10,
            "recommended": probe.get("error_kind") != "protocol_unsupported",
        },
        {
            "id": "show_details",
            "title": "查看详细错误",
            "summary": "展开本次校验的 provider、协议和错误明细。",
            "priority": 20,
            "recommended": False,
        },
        {
            "id": "continue_without_validation",
            "title": "跳过校验并继续",
            "summary": "继续使用预设或直接 CLI 启动，但不会有模型浏览列表。",
            "priority": 30,
            "recommended": False,
        },
    ]
    if len(providers) > 1:
        actions.insert(
            1,
            {
                "id": "switch_provider",
                "title": "切换到其他 provider",
                "summary": f"当前可切到其他已配置 provider，避免卡在 {active_provider_id}。",
                "priority": 12,
                "recommended": probe.get("error_kind") == "protocol_unsupported",
            },
        )
    return rank_recovery_actions(actions)


def display_model_probe_details(probe, *, panel_cls, console):
    lines = [f"- {line}" for line in probe.get("details", [])]
    console.print(panel_cls("\n".join(lines), title="校验详情", border_style="yellow"))


def select_provider_interactive(cfg, current_provider_id, *, resolve_provider_context, table_cls, prompt_cls, console):
    providers = [
        provider for provider in cfg.get("providers", [])
        if provider.get("enabled", True) and provider.get("id") != current_provider_id
    ]
    if not providers:
        console.print("[yellow]没有可切换的其他 provider[/yellow]")
        return None

    table = table_cls(title="可切换的 Providers")
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("协议", style="magenta")
    for index, item in enumerate(providers, 1):
        table.add_row(
            str(index),
            item.get("id", ""),
            item.get("name", ""),
            ", ".join(item.get("protocols", [])),
        )
    console.print(table)

    while True:
        choice = prompt_cls.ask("切换到哪个 provider？输入编号，留空取消", default="")
        if not choice:
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(providers):
                return resolve_provider_context(cfg, providers[idx - 1]["id"])
        console.print(f"[red]请输入 1-{len(providers)} 的编号，或直接回车取消[/red]")


def pick_recovery_actions(findings, actions, *, use_tui=False, select_actions_tui=None, panel_cls, prompt_cls, console):
    if use_tui and select_actions_tui is not None:
        selected = select_actions_tui(findings, actions, title="处理发现")
        if selected != "fallback":
            return selected

    console.print(panel_cls(
        "\n".join(f"- {item['title']}: {item['summary']}" for item in findings),
        title="发现",
        border_style="yellow",
    ))
    console.print("[bold]可处理动作：[/bold]")
    for index, action in enumerate(actions, 1):
        tag = " [推荐]" if action.get("recommended") else ""
        console.print(f"  {index}. {action['title']}{tag} — {action['summary']}")
    console.print("[dim]输入编号，支持逗号分隔多选；直接回车等于取消。[/dim]")

    while True:
        raw = prompt_cls.ask("选择动作", default="")
        if not raw:
            return []
        try:
            indexes = []
            for chunk in raw.split(","):
                value = int(chunk.strip())
                if not 1 <= value <= len(actions):
                    raise ValueError
                if value not in indexes:
                    indexes.append(value)
            return [actions[index - 1]["id"] for index in indexes]
        except ValueError:
            console.print(f"[red]请输入 1-{len(actions)} 的编号，可用逗号分隔多选[/red]")


def run_recovery_action(
    cfg,
    provider,
    probe,
    action_id,
    *,
    display_model_probe_details,
    setup_provider_credentials,
    select_provider_interactive,
    console,
):
    if action_id == "show_details":
        display_model_probe_details(probe)
        return provider, False
    if action_id == "edit_credentials":
        return setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        ), False
    if action_id == "switch_provider":
        selected = select_provider_interactive(cfg, provider.get("id"))
        return (selected or provider), False
    if action_id == "continue_without_validation":
        console.print("[yellow]已跳过模型校验。模型浏览将暂时不可用，但预设和直接 CLI 启动仍可继续。[/yellow]")
        return provider, True
    return provider, False


def rescue_default_fallback_report_payload(model, *, cleared=False, hot_fallback_enabled=False, localize):
    if cleared:
        return (
            localize("全局 fallback 已清除", "Global fallback cleared"),
            [
                (localize("保存位置", "saved at"), "[rescue].fallback_model"),
                (localize("安全边界", "safety"), "routed providers only; no global OAuth"),
            ],
            "",
        )
    return (
        localize("全局 fallback 已设置", "Global fallback set"),
        [
            ("Model", model or "-"),
            ("Hot fallback", localize("开启", "on") if hot_fallback_enabled else localize("关闭", "off")),
            (localize("保存位置", "saved at"), "[rescue].fallback_model"),
            (localize("生效方式", "applies"), "bridge failure -> model-routes.json"),
            (localize("安全边界", "safety"), "no global OAuth"),
        ],
        (
            localize("真实 failure 会先写 rescue packet，再尝试该 routed model。", "Real failures write a rescue packet before trying this routed model.")
            if hot_fallback_enabled
            else localize("默认只记录 rescue / fallback handoff；开启 hot fallback 后才会自动模型调用。", "By default MMS records rescue / fallback handoff only; automatic model calls require hot fallback to be enabled.")
        ),
    )


def rescue_hot_fallback_toggle_report_payload(enabled, *, has_default=True, localize):
    if enabled and not has_default:
        return (
            localize("无法开启 hot fallback", "Cannot enable hot fallback"),
            [
                (localize("原因", "reason"), localize("请先设置全局 fallback model", "Set a global fallback model first")),
                (localize("安全边界", "safety"), "no global OAuth"),
            ],
            "",
        )
    return (
        localize("hot fallback 已开启", "hot fallback enabled") if enabled else localize("hot fallback 已关闭", "hot fallback disabled"),
        [
            ("Hot fallback", localize("开启", "on") if enabled else localize("关闭", "off")),
            (localize("前置条件", "requires"), "[rescue].fallback_model"),
            (localize("默认行为", "default"), localize("关闭时只记录 rescue / handoff", "off means rescue / handoff only")),
        ],
        localize("开关保存到 [rescue].hot_fallback_enabled。", "Switch is saved to [rescue].hot_fallback_enabled."),
    )


def rescue_route_fallback_model_candidates(config_dir=None, *, failed_model="", limit=80, default_config_dir=""):
    failed = str(failed_model or "").strip().lower()
    root = os.path.expanduser(str(config_dir or default_config_dir))
    paths = [
        os.path.join(root, "generated", "model-routes.json"),
        os.path.join(root, "model-routes.json"),
    ]
    candidates = []
    seen = set()

    def route_is_openai_usable(route):
        if not isinstance(route, dict):
            return False
        return bool(str(route.get("openai_base_url") or "").strip() and str(route.get("api_key") or "").strip())

    for path in paths:
        try:
            payload = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        routes = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
        for model_name, entry in routes.items():
            name = str(model_name or "").strip()
            if not name or name.lower() == failed or name.lower() in seen:
                continue
            if not isinstance(entry, dict):
                continue
            leaves = [entry.get("primary")]
            if isinstance(entry.get("fallbacks"), list):
                leaves.extend(entry.get("fallbacks") or [])
            if not any(route_is_openai_usable(route) for route in leaves):
                continue
            seen.add(name.lower())
            candidates.append(name)
        if candidates:
            break
    return candidates[: max(1, int(limit or 1))]


def rescue_fallback_model_candidates(
    cfg,
    rescue_event,
    *,
    limit=6,
    load_usage_stats,
    rescue_route_fallback_model_candidates=rescue_route_fallback_model_candidates,
):
    failed_model = str((rescue_event or {}).get("failed_model") or "").strip().lower()
    rows = {}

    def add(model, *, last_used_at="", source_rank=1000):
        name = str(model or "").strip()
        if not name or name.lower() == failed_model:
            return
        key = name.lower()
        existing = rows.get(key)
        candidate = {
            "model": name,
            "last_used_at": str(last_used_at or "").strip(),
            "source_rank": int(source_rank),
        }
        if existing is None:
            rows[key] = candidate
            return
        existing_key = (str(existing.get("last_used_at") or ""), -int(existing.get("source_rank") or 0))
        candidate_key = (candidate["last_used_at"], -candidate["source_rank"])
        if candidate_key > existing_key:
            rows[key] = candidate

    stats = load_usage_stats()
    for item in (stats.get("last_by_cli") or {}).values():
        if not isinstance(item, dict):
            continue
        add(item.get("model"), last_used_at=item.get("last_used_at"), source_rank=0)
    for source in (stats.get("sources") or {}).values():
        if not isinstance(source, dict):
            continue
        model_last_used = source.get("model_last_used_at") if isinstance(source.get("model_last_used_at"), dict) else {}
        for model_name in (source.get("models") or {}).keys():
            add(model_name, last_used_at=model_last_used.get(model_name), source_rank=10)
        add(source.get("last_model"), last_used_at=source.get("last_used_at"), source_rank=5)

    rank = 100
    for provider_def in (cfg or {}).get("providers", []) or []:
        if not isinstance(provider_def, dict) or not provider_def.get("enabled", True):
            continue
        for field in ("extra_models", "fallback_models"):
            for model_name in provider_def.get(field) or []:
                add(model_name, source_rank=rank)
                rank += 1

    for model_name in rescue_route_fallback_model_candidates(failed_model=failed_model, limit=80):
        add(model_name, source_rank=rank)
        rank += 1

    values = list(rows.values())
    recent = sorted(
        [item for item in values if item.get("last_used_at")],
        key=lambda item: (str(item.get("last_used_at") or ""), -int(item.get("source_rank") or 0)),
        reverse=True,
    )
    cold = sorted(
        [item for item in values if not item.get("last_used_at")],
        key=lambda item: (int(item.get("source_rank") or 0), str(item.get("model") or "").lower()),
    )
    ordered = recent + cold
    return [item["model"] for item in ordered[: max(int(limit or 1), 1)]]


def rescue_default_fallback(cfg):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    return {
        "model": str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip(),
        "cli": str(rescue_cfg.get("fallback_cli") or rescue_cfg.get("default_fallback_cli") or "").strip(),
    }


def rescue_hot_fallback_enabled_cfg(cfg, *, pref_bool=None):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    pref_bool_fn = pref_bool or globals()["pref_bool"]
    return bool(pref_bool_fn(rescue_cfg.get("hot_fallback_enabled", rescue_cfg.get("enable_hot_fallback"))))


def set_rescue_default_fallback(cfg, *, model="", cli=""):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    model = str(model or "").strip()
    cli = str(cli or "").strip()
    for legacy_key in ("default_fallback_model", "default_fallback_cli"):
        rescue_cfg.pop(legacy_key, None)
    if model:
        rescue_cfg["fallback_model"] = model
        if cli:
            rescue_cfg["fallback_cli"] = cli
        else:
            rescue_cfg.pop("fallback_cli", None)
    else:
        rescue_cfg.pop("fallback_model", None)
        rescue_cfg.pop("fallback_cli", None)
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
    return cfg


def set_rescue_hot_fallback_enabled(cfg, enabled=False):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    has_model = bool(str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip())
    if not has_model:
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
        return cfg, False
    rescue_cfg.pop("enable_hot_fallback", None)
    rescue_cfg["hot_fallback_enabled"] = bool(enabled)
    return cfg, bool(enabled)


def rescue_demo_packet_report_payload(payload, *, localize):
    payload = payload if isinstance(payload, dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    return (
        localize("测试 rescue packet 已生成", "Demo rescue packet created"),
        [
            ("rescue.md", artifacts.get("markdown") or "-"),
            ("rescue.json", artifacts.get("json") or "-"),
        ],
        "",
    )


def rescue_paths_report_payload(selected_rescue, *, localize):
    selected_rescue = selected_rescue if isinstance(selected_rescue, dict) else {}
    return (
        localize("Rescue 文件路径", "Rescue file paths"),
        [
            ("rescue.md", selected_rescue.get("artifact_markdown") or "-"),
            ("rescue.json", selected_rescue.get("artifact_json") or "-"),
        ],
        "",
    )


def rescue_handover_report_payload(handover, fallback_model, *, localize):
    handover = handover if isinstance(handover, dict) else {}
    artifacts = handover.get("artifacts") if isinstance(handover.get("artifacts"), dict) else {}
    return (
        localize("fallback handover 已生成", "fallback handover created"),
        [
            ("Model", fallback_model or "-"),
            ("handover.md", artifacts.get("markdown") or "-"),
            ("latest", artifacts.get("latest_markdown") or "-"),
        ],
        localize("handover 只写本地 rescue artifact；不切换当前 session。", "handover writes local rescue artifacts only; it does not switch the current session."),
    )


def registry_source_staleness_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        ("DB", summary.get("db_path") or "-"),
        (localize("到期 Source", "sources due"), f"{summary.get('due_count')} / {summary.get('source_count')}"),
    ]
    for idx, item in enumerate((summary.get("sources") or [])[:5], start=1):
        due = localize("到期", "due") if item.get("due") else localize("未到期", "not due")
        rows.append(
            (
                f"Source {idx}",
                f"{due} · {item.get('reason') or '-'} · {item.get('checked_at') or '-'} · {item.get('source_path') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("sources") or []) - 5)
    if hidden:
        rows.append((localize("更多 Source", "more sources"), hidden))
    return localize("模型真源 Source Staleness", "Registry Source Staleness"), rows, ""


def registry_refresh_sources_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("刷新 Sources 完成", "Refresh Sources Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            (localize("导入", "imported"), summary.get("imported_count")),
            (localize("跳过", "skipped"), summary.get("skipped_count", 0)),
            (localize("模型", "models"), summary.get("model_count")),
            (localize("事实", "facts"), summary.get("fact_count")),
        ],
        localize("只写 source truth / candidate evidence；不改变当前 runtime defaults。", "Writes source truth / candidate evidence only; runtime defaults unchanged."),
    )


def registry_scheduled_refresh_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    source_refresh = summary.get("source_refresh") if isinstance(summary.get("source_refresh"), dict) else {}
    openrouter_fetch = summary.get("openrouter_fetch") if isinstance(summary.get("openrouter_fetch"), dict) else {}
    return (
        localize("定时刷新结果", "Scheduled Refresh Result"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Dry Run", summary.get("dry_run")),
            (localize("到期 Source", "source due"), summary.get("source_due_count")),
            (localize("导入 Source", "source imported"), source_refresh.get("imported_count", 0)),
            (localize("OpenRouter 到期", "OpenRouter due"), summary.get("openrouter_due")),
            ("OpenRouter", openrouter_fetch.get("reason") or localize("No Network 模式未拉取", "not fetched in no-network mode")),
        ],
        localize("安全 schedule wrapper：不接入 startup，不发布 latest-approved。", "Safe schedule wrapper: no startup hook and no latest-approved publish."),
    )


def registry_openrouter_fetch_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("OpenRouter Catalog 拉取完成", "OpenRouter Catalog Fetch Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Snapshot", summary.get("snapshot_id") or "-"),
            (localize("模型", "models"), summary.get("model_count")),
        ],
        localize("只写 provider_catalog source snapshot；不改变当前 runtime defaults。", "Writes provider_catalog source snapshot only; runtime defaults unchanged."),
    )


def registry_openrouter_diff_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        (localize("变化", "changes"), f"{summary.get('change_count')} stored={summary.get('stored_count')}"),
        (localize("缺少 reference", "missing reference"), summary.get("missing_reference_count")),
        (localize("未追踪 catalog", "untracked catalog"), summary.get("untracked_catalog_count")),
    ]
    for idx, item in enumerate((summary.get("changes") or [])[:5], start=1):
        rows.append(
            (
                f"Change {idx}",
                f"{item.get('field_key') or '-'} · {item.get('model_key') or '-'} -> {item.get('provider_model_id') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("changes") or []) - 5)
    if hidden:
        rows.append((localize("更多变化", "more changes"), hidden))
    return (
        localize("OpenRouter Candidate Diff", "OpenRouter Candidate Diff"),
        rows,
        localize("只写 candidate_change evidence；不改变当前 runtime defaults。", "Writes candidate_change evidence only; runtime defaults unchanged."),
    )


def registry_publish_approved_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("发布 Approved Bundle 完成", "Publish Approved Bundle Complete"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", summary.get("bundle_revision") or "-"),
        ],
        localize("发布 generated/latest-approved bundle；不改 root aliases，不改 runtime defaults。", "Publishes generated/latest-approved bundle; root aliases and runtime defaults unchanged."),
    )


def registry_verify_approved_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    files = summary.get("verified_files") if isinstance(summary.get("verified_files"), dict) else {}
    return (
        localize("Latest-approved hash 验证完成", "Latest-approved hash verified"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", manifest.get("bundle_revision") or "-"),
            (localize("文件", "files"), len(files)),
        ],
        "",
    )


def registry_doctor_report_payload(status, *, localize):
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    rows = [
        ("DB", status.get("db_path") or "-"),
        ("user_version", status.get("user_version") or "-"),
    ]
    for key in sorted(counts):
        rows.append((key, counts[key]))
    return localize("Registry Doctor / 状态", "Registry Doctor / Status"), rows, ""


def short_update_status_label(status, *, localize):
    status = str(status or "").strip()
    if not status:
        return ""
    if status.startswith(localize("有新版", "update available")):
        return localize("有新版", "update available")
    if status.startswith(localize("高于 latest", "newer than latest")):
        return localize("高于 latest", "newer than latest")
    return status


def format_cli_about_line(cli_status, *, localize):
    current = str(cli_status.get("version") or cli_status.get("label") or "").strip()
    status = short_update_status_label(cli_status.get("status"), localize=localize)
    status_suffix = f" · {status}" if status else ""
    return f"{current}{status_suffix}".strip() or "-"


def format_about_latest_value(status, *, localize):
    latest = str((status or {}).get("latest") or "").strip()
    return latest or localize("未检查", "not checked")


def about_check_error_summary(error_text, *, localize):
    raw = str(error_text or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if "ssl" in lower or "handshake" in lower:
        return localize("MMS latest 检查失败：SSL handshake，可稍后重试", "MMS latest check failed: SSL handshake; retry later")
    if "timed out" in lower or "timeout" in lower:
        return localize("MMS latest 检查超时，可稍后重试", "MMS latest check timed out; retry later")
    if len(raw) > 72:
        raw = raw[:69].rstrip() + "..."
    return raw


def mms_upgrade_shell_command(*, include_clis=False, preferred_language="", normalize_language):
    args = ["--latest-tag", "--lang", normalize_language(preferred_language) or "zh"]
    if include_clis:
        args.extend(["--install-cli", "claude,codex"])
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    return f"curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- {quoted_args}"


def cli_upgrade_shell_command(cli_name, *, cli_version_packages):
    cli = str(cli_name or "").strip().lower()
    package = cli_version_packages.get(cli)
    if not package:
        return ""
    return "npm install -g " + shlex.quote(f"{package}@latest")


def run_about_upgrade(
    *,
    target="mms",
    include_clis=False,
    ensure_rich,
    cli_upgrade_shell_command,
    mms_upgrade_shell_command,
    confirm_ask,
    subprocess_run,
    console,
    localize,
):
    ensure_rich()
    target = str(target or "mms").strip().lower()
    if target in {"codex", "claude"}:
        command = cli_upgrade_shell_command(target)
        label = "Codex CLI" if target == "codex" else "Claude CLI"
    else:
        command = mms_upgrade_shell_command(include_clis=include_clis)
        label = localize("MMS + Codex/Claude CLI", "MMS + Codex/Claude CLI") if include_clis else "MMS"
    if not command:
        console.print(f"[red]{localize('没有可执行的升级命令。', 'No upgrade command available.')}[/red]")
        return False
    console.print(f"[yellow]{localize(f'即将升级 {label}', f'About to upgrade {label}')}[/yellow]")
    console.print(f"[dim]{command}[/dim]")
    if not confirm_ask(localize("确认执行升级？", "Run upgrade now?"), default=False):
        console.print(f"[yellow]{localize('已取消升级。', 'Upgrade cancelled.')}[/yellow]")
        return False
    result = subprocess_run(
        ["bash", "-lc", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        console.print(result.stdout)
    if result.returncode == 0:
        console.print(f"[green]✓ {localize('升级命令完成。重新打开终端或重新启动 mms 后生效。', 'Upgrade command completed. Restart the terminal or MMS to apply.')}[/green]")
        return True
    console.print(f"[red]{localize('升级命令失败', 'Upgrade command failed')} (exit {result.returncode})[/red]")
    return False


def about_tui_payload(about_snapshot, *, config_path, localize):
    about_snapshot = about_snapshot if isinstance(about_snapshot, dict) else {}
    version_info = about_snapshot.get("version_info") if isinstance(about_snapshot.get("version_info"), dict) else {}
    mms_status = about_snapshot.get("mms") if isinstance(about_snapshot.get("mms"), dict) else {}
    clis = about_snapshot.get("clis") if isinstance(about_snapshot.get("clis"), dict) else {}
    codex_status = clis.get("codex") if isinstance(clis.get("codex"), dict) else {}
    claude_status = clis.get("claude") if isinstance(clis.get("claude"), dict) else {}
    info_lines = [
        ("MMS", f"{mms_status.get('current') or version_info.get('release') or 'dev'} · {mms_status.get('status') or '-'}"),
        (localize("MMS 最新", "MMS latest"), mms_status.get("latest") or localize("未检查", "not checked")),
        ("Codex", format_cli_about_line(codex_status, localize=localize)),
        (localize("Codex 最新", "Codex latest"), format_about_latest_value(codex_status, localize=localize)),
        ("Claude", format_cli_about_line(claude_status, localize=localize)),
        (localize("Claude 最新", "Claude latest"), format_about_latest_value(claude_status, localize=localize)),
        ("Git", f"{version_info.get('git_branch') or '-'} @ {version_info.get('git_commit') or '-'}"),
        (localize("安装", "Install"), f"{version_info.get('install_channel') or '-'} / {version_info.get('source') or '-'}"),
        ("Config", config_path),
    ]
    if mms_status.get("last_error"):
        info_lines.append((localize("检查错误", "Check error"), about_check_error_summary(mms_status.get("last_error"), localize=localize)))
    actions = [("refresh_versions", localize("刷新版本检查", "Refresh Version Check"))]
    if mms_status.get("outdated"):
        actions.append(("upgrade_mms", localize("升级 MMS", "Upgrade MMS")))
    if codex_status.get("outdated"):
        actions.append(("upgrade_codex_cli", localize("升级 Codex CLI", "Upgrade Codex CLI")))
    if claude_status.get("outdated"):
        actions.append(("upgrade_claude_cli", localize("升级 Claude CLI", "Upgrade Claude CLI")))
    actions.append(("back", localize("返回", "Back")))
    return localize("关于 / About", "About"), info_lines, actions


def snapshot_guard_tui_payload(*, command_name, localize):
    info_lines = [
        (localize("用途", "Purpose"), localize("检查/接受 MMS config drift", "Inspect / accept MMS config drift")),
        ("CLI", f"{command_name} guard status / accept"),
    ]
    actions = [
        ("status", localize("查看当前 Snapshot 状态", "Status")),
        ("accept", localize("接受当前 Snapshot", "Accept Current Snapshot")),
        ("back", localize("返回", "Back")),
    ]
    return localize("启动快照 / Snapshot Guard", "Snapshot Guard"), info_lines, actions


def display_about_version_summary(about_snapshot, *, payload_builder, console):
    title, info_lines, _actions = payload_builder(about_snapshot)
    console.print(f"[cyan]{title}[/cyan]")
    for label, value in info_lines:
        console.print(f"[cyan]{label}[/cyan] {value}")


def render_mms_config_agents_guard():
    return """# AGENTS.md

This folder stores the real MMS user config.

## MMS Config Human Gate

- Any agent, any repo, any automation touching this folder must stop and require human confirmation before write.
- Before every write, create a timestamped backup first. Never overwrite in place without a backup.
- Applies to the whole MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and any account state under this folder.
- Agents may inspect, diff, and propose changes, but must not auto-apply user config edits without human confirmation.
- Any proposed change must show target path, affected fields/files, before/after values, and reason.
- If the process is running inside an isolated HOME or gateway session, still resolve and protect the real user config under `~/.config/mms`.
"""


def render_mms_config_claude_guard():
    return """# CLAUDE.md

This folder stores the real MMS user config.

## Claude Hard Rule

- Claude must treat this folder as human-only config.
- Claude must never auto-write MMS user config without explicit human confirmation.
- Before every write, Claude must create a timestamped backup first.
- Claude may only inspect, explain, and generate manual diffs for changes to this folder until the human confirms.
- This applies to the full MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and account state files.
- If Claude is about to touch these files, it must stop and report the exact path, intended change, before/after values, and reason.
"""


def build_manage_targets(
    cfg,
    *,
    default_provider_id,
    resolve_provider_context,
    usage_summary_for_runtime,
    probe_account_status,
):
    targets = []
    account_defaults = cfg.get("account", {}).get("defaults", {})

    for provider in cfg.get("providers", []):
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id", "")).strip()
        if not provider_id:
            continue
        provider_ctx = resolve_provider_context(cfg, provider_id)
        launches, last_used_at = usage_summary_for_runtime("provider", provider_id)
        targets.append({
            "kind": "provider",
            "id": provider_id,
            "title": provider.get("name", provider_id),
            "summary": "默认网关通道" if provider_id == default_provider_id else "网关通道",
            "is_default": provider_id == default_provider_id,
            "default_label": "网关" if provider_id == default_provider_id else "备选",
            "status": "已配置" if provider_ctx.get("base_url") and provider_ctx.get("api_key") else "未配置",
            "launches": launches,
            "last_used_at": last_used_at,
        })

    for account in cfg.get("accounts", []):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id", "")).strip()
        if not account_id:
            continue
        cli_name = str(account.get("cli", "")).strip()
        launches, last_used_at = usage_summary_for_runtime("account", account_id)
        login_state = probe_account_status(account)
        default_tag = " / 默认" if account_defaults.get(cli_name) == account_id else ""
        targets.append({
            "kind": "account",
            "id": account_id,
            "cli": cli_name,
            "title": account.get("name", account_id),
            "summary": f"官方通道 · {cli_name.upper()}{default_tag}",
            "is_default": account_defaults.get(cli_name) == account_id,
            "default_label": cli_name.upper() if account_defaults.get(cli_name) == account_id else "备选",
            "status": login_state.get("summary") or login_state.get("state", ""),
            "launches": launches,
            "last_used_at": last_used_at,
        })
    targets.sort(
        key=lambda item: (
            0 if item.get("is_default") else 1,
            0 if item.get("kind") == "account" else 1,
            -int(item.get("launches", 0)),
            item.get("last_used_at", ""),
            item.get("title", ""),
        )
    )
    return targets


def select_manage_target_fallback(targets, *, ensure_rich, panel_cls, table_cls, prompt_cls, console):
    ensure_rich()
    console.print(panel_cls(
        f"[bold]通道总数:[/bold] {len(targets)} 个",
        title="管理现有通道",
        border_style="cyan",
    ))
    table = table_cls(show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("类型", style="green")
    table.add_column("显示名", style="yellow")
    table.add_column("默认入口", style="white", width=10)
    table.add_column("状态", style="magenta")
    table.add_column("启动", style="cyan", width=6)
    for index, target in enumerate(targets, 1):
        target_type = "官方" if target.get("kind") == "account" else "网关"
        table.add_row(
            str(index), target_type, target.get("title", ""),
            target.get("default_label", ""), target.get("status", ""),
            str(target.get("launches", 0)),
        )
    console.print(table)

    while True:
        ensure_rich()
        raw = prompt_cls.ask("选择要管理的通道，直接回车返回", default="")
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(targets):
                return targets[idx - 1]
        console.print(f"[red]请输入 1-{len(targets)} 的编号[/red]")


def format_rescue_hot_fallback_event(event):
    if not isinstance(event, dict) or not event:
        return "-"
    at = str(event.get("at") or "")[:19].replace("T", " ")
    model = str(event.get("model") or "").strip()
    note = str(event.get("note") or "").strip()
    parts = [item for item in (at, model, note) if item]
    return " · ".join(parts) if parts else "-"


def latest_rescue_hot_fallback_event(*, get_recent_events, limit=40):
    try:
        events = get_recent_events(limit=limit)
    except Exception:
        return None
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "fallback":
            continue
        if "rescue_hot_fallback" not in str(event.get("note") or ""):
            continue
        return event
    return None


def rescue_landing_tui_payload(default_label, rescue_events, latest_fallback_event=None, hot_fallback_enabled=False):
    events = list(rescue_events or [])
    latest = events[0] if events else {}
    if latest:
        latest_line = " ".join(
            item
            for item in (
                str(latest.get("created_at") or "")[:19].replace("T", " "),
                str(latest.get("failed_model") or ""),
                str(latest.get("status_code") or latest.get("failure_kind") or ""),
            )
            if item
        )
    else:
        latest_line = "-"
    packet_summary = f"{len(events)} 个 packet" if events else "没有 packet"
    has_default = bool(str(default_label or "").strip() and str(default_label or "").strip() != "未设置")
    info_lines = [
        ("全局默认", str(default_label or "未设置")),
        ("Hot fallback", "开启" if hot_fallback_enabled and has_default else "关闭"),
        ("生效范围", "MMS 全局默认；bridge 失败时读取"),
        ("触发时机", "429 / 503 / context / provider failure"),
        ("最近失败", f"{packet_summary} · {latest_line}" if latest else packet_summary),
        ("最近 fallback 尝试", format_rescue_hot_fallback_event(latest_fallback_event)),
        ("安全边界", "只走 routed provider；不使用 global OAuth"),
    ]
    actions = [
        ("choose_route_default", "设置全局默认 fallback（routed models）"),
        ("manual_default", "手动输入 fallback model"),
        ("clear_default", "清除全局默认 fallback"),
    ]
    if has_default:
        actions.append(
            (
                "disable_hot_fallback" if hot_fallback_enabled else "enable_hot_fallback",
                "关闭 hot fallback（只记录 handoff）" if hot_fallback_enabled else "开启 hot fallback（当前会话热切）",
            )
        )
    if events:
        actions.append(("view_packets", "查看最近失败 / rescue packet"))
    actions.extend(
        [
            ("create_demo", "生成测试 rescue packet"),
            ("back", "返回"),
        ]
    )
    return info_lines, actions


def registry_truth_tui_payload(status, *, localize):
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    freshness = status.get("source_freshness") if isinstance(status.get("source_freshness"), dict) else {}
    info_lines = [
        ("DB", status.get("db_path") or "-"),
        (localize("来源快照", "source snapshots"), counts.get("source_snapshot", 0)),
        (localize("模型身份", "model identities"), counts.get("model_identity", 0)),
        (localize("模型事实", "model facts"), counts.get("model_fact", 0)),
        (localize("待刷新来源", "sources due"), freshness.get("due_count", 0)),
        (localize("最新来源", "latest source"), latest.get("source_path") or "none"),
    ]
    actions = [
        ("check_staleness", localize("检查 Source Staleness", "Check Source Staleness")),
        ("refresh_due_sources", localize("刷新到期 Sources", "Refresh Due Sources")),
        ("scheduled_dry_run", localize("定时刷新 Dry Run", "Scheduled Refresh Dry Run")),
        ("scheduled_no_network", localize("定时刷新 No Network", "Scheduled Refresh No Network")),
        ("refresh_sources", localize("刷新全部 Sources", "Refresh Sources")),
        ("fetch_openrouter", localize("拉取 OpenRouter Catalog", "Fetch OpenRouter Catalog")),
        ("diff_openrouter", localize("对比 OpenRouter Candidate", "OpenRouter Candidate Diff")),
        ("publish_approved", localize("发布 Approved Bundle", "Publish Approved Bundle")),
        ("verify_approved", localize("验证 Approved Bundle", "Verify Approved Bundle")),
        ("doctor", localize("Registry Doctor / 状态", "Registry Doctor / Status")),
        ("back", localize("返回", "Back")),
    ]
    return localize("模型真源 / Registry Truth", "Registry Truth"), info_lines, actions


def model_source_label(source):
    mapping = {
        "remote": "远端列表",
        "fallback": "内置回退",
        "manual": "手工列表",
        "extra": "手工补充",
        "derived_alias": "本地别名",
    }
    return mapping.get(str(source or "").strip(), str(source or "-").strip() or "-")


def ttfb_label(ttfb_ms):
    if not isinstance(ttfb_ms, (int, float)):
        return "暂无数据"
    if ttfb_ms < 1200:
        return "很快"
    if ttfb_ms < 2500:
        return "正常"
    if ttfb_ms < 4500:
        return "偏慢"
    return "很慢"


def tps_label(tps_value):
    if not isinstance(tps_value, (int, float)):
        return "暂无数据"
    if tps_value >= 80:
        return "很快"
    if tps_value >= 40:
        return "正常"
    if tps_value >= 20:
        return "偏慢"
    return "很慢"


def provider_map(cfg):
    providers = cfg.get("providers", [])
    return {provider["id"]: provider for provider in providers if isinstance(provider, dict) and provider.get("id")}


def provider_label(provider, *, default_provider_id):
    return provider.get("name", provider.get("id", default_provider_id))


def provider_openai_base_url(provider):
    explicit = str(provider.get("openai_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(provider.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def provider_anthropic_base_url(provider):
    explicit = str(provider.get("anthropic_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    if "anthropic_messages" not in protocols:
        return ""
    return str(provider.get("base_url", "")).strip().rstrip("/")


def provider_has_configured_base_url(provider):
    return bool(
        provider_openai_base_url(provider)
        or provider_anthropic_base_url(provider)
        or str(provider.get("base_url", "")).strip().rstrip("/")
    )


def provider_id_variants(provider_id):
    raw = str(provider_id or "").strip()
    if not raw:
        return []
    variants = [raw]
    for candidate in (raw.replace("_", "-"), raw.replace("-", "_")):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def resolve_config_provider_id(provider_defs, provider_id):
    provider_defs = provider_defs or {}
    for candidate in provider_id_variants(provider_id):
        if candidate in provider_defs:
            return candidate
    return ""


def config_truthy(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


def provider_template_payload(template_key, *, provider_templates):
    template = provider_templates.get(template_key) or provider_templates["generic"]
    payload = {
        "id": template["id"],
        "name": template["name"],
        "protocols": list(template["protocols"]),
        "supported_clis": list(template["supported_clis"]),
        "enabled": True,
        "priority": template["priority"],
        "note": template["note"],
    }
    if "default_openai_base_url" in template:
        payload["default_openai_base_url"] = template["default_openai_base_url"]
    if "default_anthropic_base_url" in template:
        payload["default_anthropic_base_url"] = template["default_anthropic_base_url"]
    if "key_prefix" in template:
        payload["key_prefix"] = template["key_prefix"]
    if "fallback_models" in template:
        payload["fallback_models"] = list(template["fallback_models"])
    if "models_endpoint" in template:
        payload["models_endpoint"] = template["models_endpoint"]
    if "provider_profile" in template:
        payload["provider_profile"] = template["provider_profile"]
    if "extension" in template:
        payload["extension"] = template["extension"]
    if "capabilities" in template:
        payload["capabilities"] = dict(template["capabilities"])
    return payload


def select_provider_template(preset_id=None, *, console):
    if preset_id == "openrouter":
        return "openrouter"
    if preset_id and preset_id != "generic":
        console.print("[yellow]已统一收敛为“通用兼容网关”，将直接进入通用网关配置。[/yellow]")
    return "generic"


def ensure_interactive_terminal(
    action_hint,
    *,
    stdin,
    ensure_rich,
    console,
    current_command,
    exit_func=sys.exit,
):
    if stdin.isatty():
        ensure_rich()
        return
    console.print(
        f"[red]当前不是交互终端，无法执行 {action_hint}，请在终端里运行 {current_command()}[/red]"
    )
    exit_func(1)


def parse_csv_values(raw_value, allowed_values=None, *, console=None):
    values = []
    for chunk in str(raw_value or "").split(","):
        item = chunk.strip()
        if item and item not in values:
            values.append(item)
    if allowed_values is None:
        return values
    invalid = [item for item in values if item not in allowed_values]
    if invalid:
        if console is not None:
            console.print(f"[red]不支持的值: {', '.join(invalid)}[/red]")
            console.print(f"[dim]可选值: {', '.join(allowed_values)}[/dim]")
        sys.exit(1)
    return values


def prompt_csv_values(
    label,
    default_values,
    allowed_values,
    *,
    ensure_rich,
    prompt_ask,
    parse_csv_values,
    console,
    exit_func=sys.exit,
):
    ensure_rich()
    default_text = ",".join(default_values)
    raw_value = prompt_ask(label, default=default_text)
    values = parse_csv_values(raw_value, allowed_values=allowed_values)
    if not values:
        console.print(f"[red]{label} 不能为空[/red]")
        exit_func(1)
    return values


def merge_dicts(base, override):
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def pref_bool(value):
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def pref_enable_disable(value):
    enabled = pref_bool(value)
    if enabled is True:
        return "enable"
    if enabled is False:
        return "disable"
    raw = str(value or "").strip().lower()
    if raw in {"enable", "enabled", "disable", "disabled"}:
        return "enable" if raw.startswith("enable") else "disable"
    return ""


def pref_reasoning_effort(value):
    raw = str(value or "").strip().lower()
    return raw if raw in {"low", "medium", "high", "xhigh"} else ""


def pref_agent_pack(value):
    if value is None:
        return ""
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    if raw in {"none", "off", "disable", "disabled", "false", "0"}:
        return "none"
    if raw in {"ecc", "everything-claude-code"}:
        return "ecc"
    if raw in {"omc", "oh-my-claudecode", "oh-my-claude-code"}:
        return "omc"
    return ""


def sanitize_surface_list(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    result = []
    seen = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def sanitize_disabled_session_surfaces(payload):
    payload = payload if isinstance(payload, dict) else {}
    aliases = {
        "mcp": "mcp",
        "mcps": "mcp",
        "mcp_servers": "mcp",
        "skills": "skills",
        "skill": "skills",
        "hooks": "hooks",
        "hook": "hooks",
    }
    result = {}
    for key, values in payload.items():
        normalized_key = aliases.get(str(key or "").strip().lower())
        if not normalized_key:
            continue
        cleaned = sanitize_surface_list(values)
        if cleaned:
            result[normalized_key] = cleaned
    return result


def sanitize_launch_preferences(payload):
    payload = payload if isinstance(payload, dict) else {}
    result = {}
    thinking_mode = pref_enable_disable(payload.get("thinking_mode"))
    if thinking_mode:
        result["thinking_mode"] = thinking_mode
    effort = pref_reasoning_effort(payload.get("reasoning_effort"))
    if effort:
        result["reasoning_effort"] = effort
    caveman_mode = pref_enable_disable(payload.get("caveman_mode"))
    if caveman_mode:
        result["caveman_mode"] = caveman_mode
    nsr_mode = pref_enable_disable(payload.get("nsr_mode"))
    if nsr_mode:
        result["nsr_mode"] = nsr_mode
    bypass = pref_bool(payload.get("bypass"))
    if bypass is not None:
        result["bypass"] = bypass

    agent_pack = pref_agent_pack(payload.get("agent_pack"))
    if not agent_pack and pref_enable_disable(payload.get("omc_mode")) == "enable":
        agent_pack = "omc"
    if not agent_pack and pref_enable_disable(payload.get("ecc_mode")) == "enable":
        agent_pack = "ecc"
    if agent_pack:
        result["agent_pack"] = agent_pack
        result["ecc_mode"] = "enable" if agent_pack == "ecc" else "disable"
        result["omc_mode"] = "enable" if agent_pack == "omc" else "disable"

    surfaces = sanitize_disabled_session_surfaces(payload.get("disabled_session_surfaces"))
    if surfaces:
        result["disabled_session_surfaces"] = surfaces
    return result


def sanitize_asset_roots(payload, *, asset_root_keys):
    payload = payload if isinstance(payload, dict) else {}
    result = {}
    for key, value in payload.items():
        normalized_key = asset_root_keys.get(str(key or "").strip().lower())
        path = str(value or "").strip()
        if not normalized_key or not path:
            continue
        result[normalized_key] = os.path.abspath(os.path.expanduser(path))
    return result


def sanitize_user_preferences(raw, *, cli_names, asset_root_keys):
    raw = raw if isinstance(raw, dict) else {}
    launch = raw.get("launch") if isinstance(raw.get("launch"), dict) else {}
    session_surfaces = raw.get("session_surfaces") if isinstance(raw.get("session_surfaces"), dict) else {}
    assets = raw.get("assets") if isinstance(raw.get("assets"), dict) else {}

    result = {"launch": {"defaults": {}, "cli": {}}, "session_surfaces": {"disabled": {}}, "assets": {"roots": {}}}
    result["launch"]["defaults"] = sanitize_launch_preferences(launch.get("defaults"))
    cli_tables = launch.get("cli") if isinstance(launch.get("cli"), dict) else {}
    for cli_name, table in cli_tables.items():
        normalized_cli = str(cli_name or "").strip().lower()
        if normalized_cli not in set(cli_names) | {"gemini"}:
            continue
        cleaned = sanitize_launch_preferences(table)
        if cleaned:
            result["launch"]["cli"][normalized_cli] = cleaned
    global_disabled = sanitize_disabled_session_surfaces(session_surfaces.get("disabled"))
    if global_disabled:
        result["session_surfaces"]["disabled"] = global_disabled
    roots = sanitize_asset_roots(assets.get("roots"), asset_root_keys=asset_root_keys)
    if roots:
        result["assets"]["roots"] = roots
    return result


def merge_disabled_session_surfaces(*payloads):
    merged = {"mcp": [], "skills": [], "hooks": []}
    seen = {key: set() for key in merged}
    for payload in payloads:
        cleaned = sanitize_disabled_session_surfaces(payload)
        for key, values in cleaned.items():
            for value in values:
                if value in seen[key]:
                    continue
                seen[key].add(value)
                merged[key].append(value)
    return {key: values for key, values in merged.items() if values}


def preference_runtime_overlay(prefs, cli_name):
    prefs = prefs if isinstance(prefs, dict) else {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    merged = dict(launch.get("defaults") or {})
    cli_overrides = launch.get("cli") if isinstance(launch.get("cli"), dict) else {}
    cli_specific = cli_overrides.get(str(cli_name or "").strip().lower())
    if isinstance(cli_specific, dict):
        merged = merge_dicts(merged, cli_specific)
    global_disabled = (prefs.get("session_surfaces") or {}).get("disabled") if isinstance(prefs.get("session_surfaces"), dict) else {}
    disabled = merge_disabled_session_surfaces(global_disabled, merged.get("disabled_session_surfaces"))
    if disabled:
        merged["disabled_session_surfaces"] = disabled
    return merged


def runtime_with_launch_preferences(cfg, runtime, cli_name, *, load_user_preferences):
    if not isinstance(runtime, dict):
        return runtime
    if runtime.get("_mms_preferences_applied"):
        return runtime
    prefs = (cfg or {}).get("_mms_preferences") if isinstance(cfg, dict) else None
    if not isinstance(prefs, dict):
        prefs = load_user_preferences()
    overlay = preference_runtime_overlay(prefs, cli_name)
    if not overlay:
        result = dict(runtime)
        result["_mms_preferences_applied"] = True
        return result
    result = dict(runtime)
    existing_disabled = result.get("disabled_session_surfaces")
    for key, value in overlay.items():
        if key == "disabled_session_surfaces":
            continue
        result[key] = value
    disabled = merge_disabled_session_surfaces(existing_disabled, overlay.get("disabled_session_surfaces"))
    if disabled:
        result["disabled_session_surfaces"] = disabled
    result["_mms_preferences_applied"] = True
    return result


def usage_rows_for_runtime(runtime_kind, runtime_id, *, load_usage_stats):
    stats = load_usage_stats()
    rows = []
    for item in stats.get("sources", {}).values():
        if item.get("runtime_kind") == runtime_kind and item.get("id") == runtime_id:
            rows.append(item)
    rows.sort(key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)), reverse=True)
    return rows


def usage_summary_for_runtime(runtime_kind, runtime_id, *, usage_rows_for_runtime):
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    launches = sum(int(item.get("launches", 0)) for item in rows)
    last_used_at = rows[0].get("last_used_at", "") if rows else ""
    return launches, last_used_at


def infer_model_family(model_name, *, model_families):
    raw = str(model_name or "").strip().lower()
    parts = raw.rsplit("/", 1)
    candidates = [raw] if len(parts) == 1 else [raw, parts[-1]]
    for entry in model_families:
        for candidate in candidates:
            if any(kw in candidate for kw in entry["keywords"]):
                return entry["family"], entry["category"]
    return "其他", "其他"


def model_info_looks_domestic(model_info, *, infer_model_family, domestic_model_families, domestic_model_keywords):
    values = []
    if isinstance(model_info, dict):
        primary = str(model_info.get("model") or "").strip()
        if primary:
            values.append(primary)
        values.extend(
            str(value or "").strip()
            for key, value in model_info.items()
            if key not in {"subagent", "model"} and str(value or "").strip()
        )
    else:
        values.append(str(model_info or "").strip())

    for value in values:
        lower = value.lower()
        family, _ = infer_model_family(value)
        if family in domestic_model_families:
            return True
        if any(keyword in lower for keyword in domestic_model_keywords):
            return True
    return False


def mms_model_visible(model_name, *, infer_model_family, hidden_models, hidden_model_families):
    normalized = str(model_name or "").strip()
    if not normalized:
        return True
    if normalized.lower() in hidden_models:
        return False
    family, _ = infer_model_family(normalized)
    return family not in hidden_model_families


def filter_visible_models(models, *, mms_model_visible):
    return [
        str(model_name).strip()
        for model_name in (models or [])
        if str(model_name or "").strip() and mms_model_visible(model_name)
    ]


def model_info_has_visible_models(model_info, *, mms_model_visible):
    if isinstance(model_info, str):
        return mms_model_visible(model_info)
    if not isinstance(model_info, dict):
        return True
    model_like_keys = ("model", "opus", "sonnet", "haiku", "subagent")
    found_model = False
    for key in model_like_keys:
        value = str(model_info.get(key) or "").strip()
        if not value:
            continue
        found_model = True
        if mms_model_visible(value):
            return True
    return not found_model


def vision_sidecar_model_candidates_for_provider(provider_id):
    normalized = str(provider_id or "").strip().lower()
    generic = [
        "mimo-v2.5",
        "mimo-v2-omni",
        "K2.6",
        "K2.6-code-preview",
        "kimi-k2.5",
        "qwen3.6-flash",
        "qwen3.6-plus",
    ]
    if "mimo" in normalized:
        return ["mimo-v2.5", "mimo-v2-omni"]
    if "kimi" in normalized:
        return ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    if "qwen" in normalized:
        return ["qwen3.6-plus", "qwen3.6-flash"]
    return generic


def vision_sidecar_candidate_pairs(raw, provider_ids, *, explicit_model="", explicit_provider_id=""):
    configured = (raw.get("candidates") or raw.get("routes")) if isinstance(raw, dict) else None
    pairs = []

    def _append(provider_id, model):
        provider_id = str(provider_id or "").strip()
        model = str(model or "").strip()
        if provider_id and model and (provider_id, model) not in pairs:
            pairs.append((provider_id, model))

    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict):
                continue
            provider_id = item.get("provider_id") or item.get("provider")
            model = item.get("model") or item.get("vision_model")
            _append(provider_id, model)

    if explicit_model:
        for provider_id in provider_ids:
            _append(provider_id, explicit_model)
        return pairs

    if explicit_provider_id:
        for model in vision_sidecar_model_candidates_for_provider(explicit_provider_id):
            _append(explicit_provider_id, model)
        return pairs

    preferred_pairs = [
        ("mimo-direct-anthropic", "mimo-v2.5"),
        ("direct-mimo", "mimo-v2.5"),
        ("direct-kimi", "K2.6"),
        ("newapi-personal-kimi", "K2.6-code-preview"),
        ("newapi-personal-kimi", "kimi-k2.5"),
        ("direct-qwen", "qwen3.6-plus"),
        ("newapi-personal-qwen", "qwen3.6-plus"),
        ("newapi-personal-tokyo", "K2.6"),
        ("xin", "K2.6"),
    ]
    for provider_id, model in preferred_pairs:
        _append(provider_id, model)
    for provider_id in provider_ids:
        for model in vision_sidecar_model_candidates_for_provider(provider_id):
            _append(provider_id, model)
    return pairs


def runtime_with_vision_sidecar(
    cfg,
    runtime,
    *,
    config_truthy,
    provider_map,
    resolve_config_provider_id,
    vision_sidecar_candidate_pairs=vision_sidecar_candidate_pairs,
    resolve_provider_context,
    provider_anthropic_base_url,
    load_probe_file_cache,
    provider_effective_models,
    environ=None,
):
    if not isinstance(runtime, dict) or runtime.get("vision_sidecar"):
        return runtime
    raw = cfg.get("vision_sidecar") if isinstance(cfg, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    if raw and not config_truthy(raw.get("enabled"), default=True):
        return runtime

    environ = os.environ if environ is None else environ
    explicit_model = str(
        environ.get("MMS_VISION_SIDECAR_MODEL")
        or raw.get("model")
        or raw.get("vision_model")
        or ""
    ).strip()
    explicit_provider_id = str(
        environ.get("MMS_VISION_SIDECAR_PROVIDER")
        or raw.get("provider_id")
        or raw.get("provider")
        or ""
    ).strip()
    preferred_ids = (
        [explicit_provider_id]
        if explicit_provider_id
        else [
            "mimo-direct-anthropic",
            "direct-mimo",
            "direct-kimi",
            "newapi-personal-kimi",
            "newapi-personal-tokyo",
            "xin",
        ]
    )
    providers = cfg.get("providers", []) if isinstance(cfg, dict) else []
    provider_defs = provider_map(cfg) if isinstance(cfg, dict) else {}
    explicit_provider_id = resolve_config_provider_id(provider_defs, explicit_provider_id)
    all_ids = [
        str(item.get("id") or "").strip()
        for item in providers
        if isinstance(item, dict) and item.get("id")
    ]
    candidate_ids = []
    for provider_id in preferred_ids + all_ids:
        if provider_id and provider_id not in candidate_ids:
            candidate_ids.append(provider_id)

    for provider_id, model in vision_sidecar_candidate_pairs(
        raw,
        candidate_ids,
        explicit_model=explicit_model,
        explicit_provider_id=explicit_provider_id,
    ):
        if provider_id not in provider_defs:
            continue
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            continue
        if not provider or not provider.get("enabled", True):
            continue
        api_key = str(provider.get("api_key") or provider.get("openai_api_key") or "").strip()
        anthropic_url = provider_anthropic_base_url(provider)
        if not api_key or not anthropic_url:
            continue
        if not explicit_provider_id:
            try:
                cached = load_probe_file_cache(provider_id, allow_stale=True)
                cached_models = (cached or {}).get("raw_models") or (cached or {}).get("models")
                models = provider_effective_models(provider, cached_models, cfg)
            except Exception:
                models = []
            model_l = model.lower()
            if models and model_l not in {str(item or "").strip().lower() for item in models}:
                continue
        updated = dict(runtime)
        updated["vision_sidecar"] = {
            "enabled": True,
            "provider_id": provider_id,
            "provider_profile": str(provider.get("profile") or provider.get("provider_profile") or ""),
            "model": model,
            "anthropic_base_url": anthropic_url,
            "api_key": api_key,
            "proxy_url": str(provider.get("proxy") or "").strip(),
            "no_proxy": str(provider.get("no_proxy") or "").strip(),
        }
        return updated
    return runtime


def native_clis_for_model(model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    if normalized.startswith("claude-"):
        return ["claude"]
    if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
        return ["codex"]
    return []


def model_context_window(
    model_name,
    *,
    resolve_model_capabilities,
    model_context_windows,
):
    clean = str(model_name or "").replace("[1m]", "").strip()
    if not clean:
        return None
    try:
        caps = resolve_model_capabilities(clean)
        if caps.get("sources", {}).get("context_window_tokens") == "approved_facts":
            window = int(caps.get("context_window_tokens"))
            if window > 0:
                return window
    except Exception:
        pass
    try:
        windows = model_context_windows()
    except Exception:
        return None
    window = windows.get(clean)
    if window is not None:
        return window
    lower = clean.lower()
    for key, value in windows.items():
        if key.lower() == lower:
            return value
    return None


def model_matches_account_cli(cli_name, model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    if cli_name == "claude":
        return normalized.startswith("claude-")
    if cli_name == "codex":
        return normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))
    if cli_name == "gemini":
        return normalized.startswith("gemini-")
    return False


def model_matches_cli_family(cli_name, model_name, *, cli_model_family_hints):
    hints = cli_model_family_hints.get(cli_name, ())
    normalized = str(model_name or "").lower()
    return any(hint in normalized for hint in hints)


def models_for_cli_family(
    cli_name,
    models,
    *,
    cli_model_family_hints,
    model_matches_cli_family=model_matches_cli_family,
):
    if cli_name not in cli_model_family_hints:
        return list(models or [])
    return [
        model_name
        for model_name in (models or [])
        if model_matches_cli_family(cli_name, model_name, cli_model_family_hints=cli_model_family_hints)
    ]


def provider_models_for_cli(cli_name, models, *, cli_model_family_hints):
    if cli_name in cli_model_family_hints:
        return models_for_cli_family(cli_name, models, cli_model_family_hints=cli_model_family_hints)
    return list(models or [])


def provider_supports_cli_name(provider, cli_name):
    provider_id = str(provider.get("id", "")).strip().lower()
    if cli_name == "agy":
        return False
    if cli_name == "codex" and provider_id.startswith("kimi"):
        return False
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    if cli_name == "opencode" and "opencode" not in supported_clis:
        protocols = provider.get("protocols", [])
        if isinstance(protocols, str):
            protocols = [protocols]
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    return cli_name in supported_clis


def provider_supports_model_for_cli(
    provider,
    cli_name,
    model_name=None,
    *,
    model_matches_account_cli,
    provider_supports_cli_name,
    bridge_clis_for_model,
):
    normalized_model = str(model_name or "").strip()
    if cli_name == "claude" and normalized_model:
        if model_matches_account_cli("claude", normalized_model):
            return provider_supports_cli_name(provider, "claude")
        bridge_clis = bridge_clis_for_model(normalized_model)
        return cli_name in bridge_clis and provider_supports_cli_name(provider, cli_name)

    if provider_supports_cli_name(provider, cli_name):
        return True
    if not normalized_model:
        return False
    return False


def probe_file_cache_path(provider_id, *, probe_file_cache_dir):
    return os.path.join(probe_file_cache_dir, f"models_{provider_id}.json")


def invalidate_probe_cache(
    provider_id,
    *,
    probe_cache,
    probe_file_cache_path,
    path_exists=os.path.exists,
    remove=os.remove,
):
    probe_cache.pop(provider_id, None)
    path = probe_file_cache_path(provider_id)
    if path_exists(path):
        try:
            remove(path)
        except OSError:
            pass


def probe_cache_age(
    provider_id,
    *,
    probe_file_cache_path,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    path = probe_file_cache_path(provider_id)
    if not path_exists(path):
        return None
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        return max(0.0, time_func() - getmtime(path))
    except OSError:
        return None


def load_probe_file_cache(
    provider_id,
    allow_stale=False,
    *,
    probe_file_cache_path,
    normalize_model_id_list,
    file_cache_ttl,
    negative_ttl,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    """Read provider model probe cache without owning global MMS paths."""
    path = probe_file_cache_path(provider_id)
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        if not path_exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        raw_models = normalize_model_id_list(data.get("raw_models") or data.get("models") or [])
        error_kind = data.get("error_kind")
        ttl = negative_ttl if error_kind or not raw_models else file_cache_ttl
        age = time_func() - getmtime(path)
        is_stale = age > ttl
        if is_stale and not allow_stale:
            return None
        normalized = dict(data)
        normalized["raw_models"] = raw_models
        normalized["models"] = list(raw_models)
        normalized.setdefault("base_source", "remote")
        normalized.setdefault("error", None)
        normalized.setdefault("error_kind", None)
        normalized.setdefault("details", [])
        normalized["is_stale"] = is_stale
        return normalized
    except Exception:
        pass
    return None


def save_probe_file_cache(
    provider_id,
    result,
    *,
    probe_file_cache_dir,
    probe_file_cache_path,
    makedirs=os.makedirs,
):
    base_source = result.get("base_source")
    if base_source not in {"remote", "fallback", "manual"}:
        return
    try:
        makedirs(probe_file_cache_dir, exist_ok=True)
        path = probe_file_cache_path(provider_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "raw_models": result.get("raw_models") or [],
                    "working_url": result.get("working_url"),
                    "base_source": base_source or "remote",
                    "error": result.get("error"),
                    "error_kind": result.get("error_kind"),
                },
                handle,
            )
    except Exception:
        pass


def base_probe_result_from_cache(provider_id, file_cached):
    return {
        "provider_id": provider_id,
        "raw_models": list(file_cached["raw_models"]),
        "models": list(file_cached["raw_models"]),
        "error": file_cached.get("error"),
        "error_kind": file_cached.get("error_kind"),
        "working_url": file_cached.get("working_url"),
        "details": list(file_cached.get("details") or []),
        "base_source": file_cached.get("base_source", "remote"),
        "is_stale": bool(file_cached.get("is_stale")),
    }


def provider_supports_mimo_anthropic_selectors(provider):
    provider = provider if isinstance(provider, dict) else {}
    identity = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("id", "name", "label", "provider_profile")
    )
    urls = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("anthropic_base_url", "openai_base_url", "base_url")
    )
    if "openrouter" in identity or "openrouter.ai" in urls:
        return False
    anthropic_base = str(provider.get("anthropic_base_url") or "").strip().lower()
    if "xiaomimimo.com" in anthropic_base:
        return True
    base_url = str(provider.get("base_url") or "").strip().lower()
    if "xiaomimimo.com" in base_url and "/anthropic" in base_url:
        return True
    return bool(anthropic_base and any(token in identity for token in ("mimo", "xiaomi")))


def derived_model_aliases(
    base_models,
    provider=None,
    *,
    provider_supports_mimo_anthropic_selectors=provider_supports_mimo_anthropic_selectors,
):
    aliases = []
    if any(model_id.startswith("claude-sonnet-4-") for model_id in base_models):
        aliases.append("claude-sonnet-4-6")
    if any(model_id.startswith("claude-opus-4-") for model_id in base_models):
        aliases.append("claude-opus-4-6")
    if provider_supports_mimo_anthropic_selectors(provider):
        model_set = set(base_models)
        for model_id in ("mimo-v2.5-pro", "mimo-v2.5"):
            selector = f"{model_id}[1m]"
            if model_id in model_set and selector not in model_set:
                aliases.append(selector)
    return aliases


def apply_provider_model_patch(
    provider,
    base_result,
    *,
    normalize_model_id_list=None,
    derived_model_aliases=derived_model_aliases,
):
    if normalize_model_id_list is None:
        normalize_model_id_list = globals()["normalize_model_id_list"]
    result = dict(base_result)
    base_models = normalize_model_id_list(result.get("raw_models") or result.get("models") or [])
    extra_models = normalize_model_id_list(provider.get("extra_models", []))
    aliases = derived_model_aliases(base_models, provider)
    hidden_requested = set(normalize_model_id_list(provider.get("hidden_models", [])))
    base_source = result.get("base_source") or ("fallback" if result.get("used_fallback") else "remote")

    effective_models = []
    model_sources = {}
    for model_id in base_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = base_source
        effective_models.append(model_id)

    for model_id in extra_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "extra"
        effective_models.append(model_id)

    for model_id in aliases:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "derived_alias"
        effective_models.append(model_id)

    domestic_keywords = ("glm", "kimi", "qwen", "minimax", "deepseek", "doubao", "seed", "bailian")
    claude_keep = {
        "claude-opus-4-6", "claude-opus-4-6-thinking", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    effective_models = [
        model_id for model_id in effective_models
        if not (model_id.startswith("claude-") and any(kw in model_id.lower() for kw in domestic_keywords))
        and not (model_id.startswith("claude-") and model_id not in claude_keep)
    ]

    hidden_applied = [model_id for model_id in effective_models if model_id in hidden_requested]
    if hidden_requested:
        effective_models = [model_id for model_id in effective_models if model_id not in hidden_requested]
    visible_sources = {model_id: model_sources.get(model_id, base_source) for model_id in effective_models}

    result["raw_models"] = base_models
    result["models"] = effective_models
    result["model_sources"] = visible_sources
    result["extra_models"] = extra_models + [model_id for model_id in aliases if model_id not in extra_models]
    result["hidden_models"] = hidden_applied
    result["base_source"] = base_source
    return result


def provider_candidates(
    cfg,
    default_provider,
    default_models,
    *,
    load_probe_file_cache,
    resolve_provider_context,
):
    candidates = [(default_provider, list(default_models or []))]
    seen_ids = {default_provider.get("id")}
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id in seen_ids:
            continue
        file_cached = load_probe_file_cache(provider_id, allow_stale=True)
        cached_models = None
        if file_cached is not None and not file_cached.get("is_stale"):
            cached_models = list((file_cached or {}).get("raw_models") or [])
        candidates.append((resolve_provider_context(cfg, provider_id), cached_models))
        seen_ids.add(provider_id)
    return candidates


def provider_effective_models(
    provider,
    cached_models,
    cfg=None,
    *,
    schedule_probe_refresh,
    apply_provider_model_patch,
):
    if cached_models is None:
        if provider.get("models_endpoint") == "manual":
            base_models = list(provider.get("fallback_models") or [])
            base_source = "manual"
        else:
            schedule_probe_refresh(provider, cfg, reason="cache_miss")
            base_models = list(provider.get("fallback_models") or [])
            base_source = "fallback" if base_models else "remote"
    else:
        base_models = list(cached_models or [])
        base_source = "remote"

    patched = apply_provider_model_patch(
        provider,
        {"raw_models": base_models, "models": base_models, "base_source": base_source},
    )
    return list(patched.get("models") or [])


def is_installed_mms_layout(
    module_path,
    *,
    real_user_home,
    abspath=os.path.abspath,
    commonpath=os.path.commonpath,
):
    current_path = abspath(module_path)
    installed_root = abspath(os.path.join(real_user_home(), ".mms"))
    try:
        return commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def default_gpt_reasoning_effort(*, module_path, is_installed_mms_layout):
    return "high" if is_installed_mms_layout(module_path) else "xhigh"


def default_reasoning_effort_for_model_info(
    model_info,
    *,
    model_matches_account_cli,
    default_gpt_reasoning_effort,
):
    values = []
    if isinstance(model_info, dict):
        values.extend(str(value or "") for key, value in model_info.items() if key != "subagent")
    else:
        values.append(str(model_info or ""))
    for item in values:
        normalized = str(item or "").strip().lower()
        if "/" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]
        if model_matches_account_cli("codex", normalized):
            return default_gpt_reasoning_effort()
    return "high"


def bridge_clis_for_model(model_name, *, infer_model_family):
    family, _ = infer_model_family(model_name)
    if family == "Unknown":
        return []
    native = set(native_clis_for_model(model_name))
    bridge = []
    for cli_name in ("claude", "codex"):
        if cli_name not in native:
            bridge.append(cli_name)
    return bridge


def model_supports_vision(model_name, *, vision_capable_model_names, vision_capable_model_hints):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    model_id = normalized.rsplit("/", 1)[-1]
    if model_id in vision_capable_model_names:
        return True
    return any(hint in model_id for hint in vision_capable_model_hints)


def model_cli_modes(model_name, *, infer_model_family):
    native = set(native_clis_for_model(model_name))
    bridge = set(bridge_clis_for_model(model_name, infer_model_family=infer_model_family))
    modes = {}
    for cli_name in ("claude", "codex"):
        if cli_name in native:
            modes[cli_name] = "native"
        elif cli_name in bridge:
            modes[cli_name] = "bridge"
        else:
            modes[cli_name] = "unsupported"
    return modes


def model_cli_summary(model_name, *, infer_model_family):
    modes = model_cli_modes(model_name, infer_model_family=infer_model_family)
    parts = []
    for cli_name in ("claude", "codex"):
        mode = modes.get(cli_name)
        if mode == "native":
            parts.append(f"{cli_name}:native")
        elif mode == "bridge":
            parts.append(f"{cli_name}:bridge")
    return ", ".join(parts) if parts else "-"


def model_capability_tags(
    model_name,
    *,
    infer_model_family,
    model_context_window,
    reasoning_model_hints,
    tool_use_families,
    vision_capable_model_names,
    vision_capable_model_hints,
):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    family, _ = infer_model_family(model_name)
    tags = []
    if model_supports_vision(
        model_name,
        vision_capable_model_names=vision_capable_model_names,
        vision_capable_model_hints=vision_capable_model_hints,
    ):
        tags.append("vision")
    if family in tool_use_families:
        tags.append("tool_use")
    if any(hint in normalized for hint in reasoning_model_hints):
        tags.append("reasoning")
    context_window = model_context_window(model_name)
    if context_window and context_window >= 200_000:
        tags.append("long_context")
    if "claude" in bridge_clis_for_model(model_name, infer_model_family=infer_model_family):
        tags.append("bridge_required")
    return tags


def model_capability_summary(model_name, *, model_capability_tags):
    tags = model_capability_tags(model_name)
    return ", ".join(tags) if tags else "-"


def env_file_path(cli_name, *, env_dir):
    return os.path.join(env_dir, f"{cli_name}.sh")


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_shell_value(raw):
    raw = raw.strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(f"v {raw}")
    except ValueError:
        return raw.strip("\"'")
    return parts[1] if len(parts) > 1 else ""


def load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, sep, raw_value = line.partition("=")
            if not sep:
                continue
            values[key.strip()] = parse_shell_value(raw_value)
    return values


def account_map(cfg):
    accounts = cfg.get("accounts", [])
    return {account["id"]: account for account in accounts if isinstance(account, dict) and account.get("id")}


def accounts_for_cli(cfg, cli_name):
    return [
        account for account in account_map(cfg).values()
        if account.get("cli") == cli_name and account.get("enabled", True)
    ]


def get_provider_definition(
    cfg,
    provider_id=None,
    *,
    provider_map,
    default_provider,
    default_provider_id,
    console,
    exit_func=sys.exit,
):
    providers = provider_map(cfg)
    resolved_id = provider_id or cfg.get("provider", {}).get("default") or default_provider_id
    provider = providers.get(resolved_id)
    if provider:
        return provider
    if provider_id:
        console.print(f"[red]未找到 provider: {provider_id}[/red]")
        exit_func(1)
    if providers:
        return next(iter(providers.values()))
    return default_provider()


def get_account_definition(
    cfg,
    account_id=None,
    cli_name=None,
    *,
    account_map,
    console,
    exit_func=sys.exit,
):
    accounts = account_map(cfg)
    resolved_id = account_id
    if not resolved_id and cli_name:
        resolved_id = cfg.get("account", {}).get("defaults", {}).get(cli_name)
    if resolved_id:
        account = accounts.get(resolved_id)
        if account:
            return account
        console.print(f"[red]未找到账号档案: {resolved_id}[/red]")
        exit_func(1)
    return None


def normalize_provider_id_input(provider_id, *, default_provider_id):
    value = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(provider_id or "").strip().lower()
    )
    value = value.strip("-_")
    return value or default_provider_id


def sanitize_provider_id(provider_id, *, default_provider_id):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id).upper())
    cleaned = cleaned.strip("_")
    return cleaned or default_provider_id.upper()


def normalize_model_id_list(values):
    if isinstance(values, str):
        values = [chunk.strip() for chunk in values.split(",")]
    normalized = []
    seen = set()
    for item in values or []:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return normalized


def unique_runtime_id(existing_ids, base_id):
    normalized = str(base_id or "").strip()
    if not normalized:
        normalized = "default"
    if normalized not in existing_ids:
        return normalized
    suffix = 2
    while True:
        candidate = f"{normalized}-{suffix}"
        if candidate not in existing_ids:
            return candidate
        suffix += 1


def normalize_models_endpoint(value):
    endpoint = str(value or "").strip()
    if not endpoint:
        return "/models"
    if endpoint.lower() in {"manual", "none", "off"}:
        return "manual"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def provider_env_name(provider_id, field, *, default_provider_id):
    return f"MMS_PROVIDER_{sanitize_provider_id(provider_id, default_provider_id=default_provider_id)}_{field}"


def load_provider_credentials(
    provider_id,
    *,
    default_provider_id,
    provider_env_name,
    api_url_env_name,
    api_key_env_name,
    credentials_paths,
    load_env_file,
    active_config_path,
    environ=os.environ,
    path_exists=os.path.exists,
):
    base_key = provider_env_name(provider_id, "BASE_URL")
    openai_base_key = provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = environ.get(base_key, "").strip()
    openai_base_url = environ.get(openai_base_key, "").strip()
    anthropic_base_url = environ.get(anthropic_base_key, "").strip()
    api_key = environ.get(api_key_name, "").strip()
    openai_api_key = environ.get(openai_api_key_name, "").strip()

    if provider_id == default_provider_id:
        base_url = base_url or environ.get(api_url_env_name, "").strip()
        api_key = api_key or environ.get(api_key_env_name, "").strip()

    for credentials_path in credentials_paths:
        if not path_exists(credentials_path):
            continue
        file_values = load_env_file(credentials_path)
        base_url = base_url or file_values.get(base_key, "").strip()
        openai_base_url = openai_base_url or file_values.get(openai_base_key, "").strip()
        anthropic_base_url = anthropic_base_url or file_values.get(anthropic_base_key, "").strip()
        api_key = api_key or file_values.get(api_key_name, "").strip()
        openai_api_key = openai_api_key or file_values.get(openai_api_key_name, "").strip()
        if provider_id == default_provider_id:
            base_url = base_url or file_values.get(api_url_env_name, "").strip()
            api_key = api_key or file_values.get(api_key_env_name, "").strip()

    config_path = active_config_path()
    if provider_id == default_provider_id and (not base_url or not api_key) and path_exists(config_path):
        with open(config_path, "rb") as f:
            legacy_cfg = tomllib.loads(f.read().decode("utf-8"))
        legacy_api = legacy_cfg.get("api", {})
        if isinstance(legacy_api, dict):
            base_url = base_url or str(legacy_api.get("base_url", "")).strip()
            api_key = api_key or str(legacy_api.get("api_key", "")).strip()

    return {
        "base_url": base_url.rstrip("/") if base_url else "",
        "openai_base_url": openai_base_url.rstrip("/") if openai_base_url else "",
        "anthropic_base_url": anthropic_base_url.rstrip("/") if anthropic_base_url else "",
        "api_key": api_key,
        "openai_api_key": openai_api_key,
    }


def save_provider_credentials(
    provider_id,
    base_url,
    api_key,
    openai_base_url="",
    anthropic_base_url="",
    openai_api_key=None,
    *,
    config_dir,
    credentials_path,
    provider_env_name,
    default_provider_id,
    api_url_env_name,
    api_key_env_name,
    load_env_file,
    shell_quote,
    trigger_routes_export_after_credentials_write,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    chmod=os.chmod,
):
    makedirs(config_dir, exist_ok=True)
    values = load_env_file(credentials_path) if path_exists(credentials_path) else {}
    base_key = provider_env_name(provider_id, "BASE_URL")
    openai_base_key = provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = base_url.rstrip("/")
    openai_base_url = openai_base_url.rstrip("/")
    anthropic_base_url = anthropic_base_url.rstrip("/")
    values[base_key] = base_url
    if openai_base_url:
        values[openai_base_key] = openai_base_url
    else:
        values.pop(openai_base_key, None)
    if anthropic_base_url:
        values[anthropic_base_key] = anthropic_base_url
    else:
        values.pop(anthropic_base_key, None)
    values[api_key_name] = api_key
    if openai_api_key is None:
        if openai_base_url:
            values[openai_api_key_name] = api_key
        else:
            values.pop(openai_api_key_name, None)
    elif openai_api_key:
        values[openai_api_key_name] = openai_api_key
    else:
        values.pop(openai_api_key_name, None)

    if provider_id == default_provider_id:
        values[api_url_env_name] = base_url
        values[api_key_env_name] = api_key

    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={shell_quote(str(values[key]))}")
    lines.append("")

    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    chmod(credentials_path, 0o600)
    trigger_routes_export_after_credentials_write()


def load_api_credentials(*, default_provider_id, load_provider_credentials):
    provider_creds = load_provider_credentials(default_provider_id)
    return provider_creds["base_url"], provider_creds["api_key"]


def save_api_credentials(base_url, api_key, *, default_provider_id, save_provider_credentials):
    return save_provider_credentials(default_provider_id, base_url, api_key)


def resolve_provider_context(
    cfg,
    provider_id=None,
    *,
    get_provider_definition,
    normalize_provider,
    load_provider_credentials,
):
    provider = normalize_provider(get_provider_definition(cfg, provider_id))
    credentials = load_provider_credentials(provider["id"])
    provider["base_url"] = credentials["base_url"]
    provider["openai_base_url"] = credentials["openai_base_url"] or provider.get("default_openai_base_url", "")
    provider["anthropic_base_url"] = credentials["anthropic_base_url"] or provider.get("default_anthropic_base_url", "")
    provider["api_key"] = credentials["api_key"]
    provider["openai_api_key"] = credentials.get("openai_api_key", "")
    provider["auth_mode"] = "api_key"
    provider["runtime_kind"] = "provider"
    return provider


def resolve_account_context(
    cfg,
    account_id=None,
    cli_name=None,
    *,
    get_account_definition,
    expanduser=os.path.expanduser,
):
    account = get_account_definition(cfg, account_id=account_id, cli_name=cli_name)
    if account is None:
        return None
    resolved = dict(account)
    resolved["auth_mode"] = "oauth"
    resolved["runtime_kind"] = "account"
    resolved["home_dir"] = expanduser(resolved.get("home_dir", ""))
    return resolved


def save_provider_credentials_with_probe(
    provider,
    base_url,
    api_key,
    openai_base_url="",
    anthropic_base_url="",
    *,
    probe_models,
    provider_openai_base_url,
    save_provider_credentials,
    resolve_provider_context,
    credentials_path,
    console,
):
    provider_ctx = dict(provider)
    provider_ctx["base_url"] = base_url
    provider_ctx["openai_base_url"] = openai_base_url
    provider_ctx["anthropic_base_url"] = anthropic_base_url
    provider_ctx["api_key"] = api_key

    console.print("\n正在测试连接...", style="dim")
    probe = probe_models(provider_ctx)
    models = probe.get("models")
    if models is None:
        console.print("[yellow]⚠ 连接失败，但配置仍会保存。请检查地址和 Key。[/yellow]")
    else:
        console.print(f"[green]✓ 连接成功！发现 {len(models)} 个可用模型[/green]")
        working_url = probe.get("working_url")
        computed_openai = provider_openai_base_url(provider_ctx)
        if working_url and working_url != computed_openai:
            fixed_base = working_url
            console.print(f"[yellow]→ 自动修正地址为 {fixed_base}[/yellow]")
            openai_base_url = fixed_base
            base_url = fixed_base

    save_provider_credentials(provider["id"], base_url, api_key, openai_base_url, anthropic_base_url)
    console.print(f"[green]✓ provider '{provider['id']}' 的凭据已保存到 {credentials_path}[/green]")
    console.print("[dim]API Key 在配置显示里会以掩码形式展示，不会直接回显明文。[/dim]")
    return resolve_provider_context({"providers": [provider], "provider": {"default": provider["id"]}}, provider["id"])


def provider_env_value(provider_id, field, *, default_provider_id, environ=None):
    environ = os.environ if environ is None else environ
    return environ.get(provider_env_name(provider_id, field, default_provider_id=default_provider_id), "").strip()


def normalize_supported_clis(value, *, protocols=None, cli_names, legacy_provider_cli_aliases):
    if isinstance(value, str):
        raw_items = [value]
    else:
        raw_items = list(value or [])
    protocol_set = {str(item).strip() for item in (protocols or []) if str(item).strip()}
    normalized = []
    seen = set()

    def add(cli_name):
        if cli_name in cli_names and cli_name not in seen:
            normalized.append(cli_name)
            seen.add(cli_name)

    for item in raw_items:
        cli_name = str(item or "").strip().lower()
        if not cli_name:
            continue
        if cli_name in legacy_provider_cli_aliases:
            if "anthropic_messages" in protocol_set:
                add("claude")
            if "openai_chat_completions" in protocol_set:
                add("codex")
            continue
        add(cli_name)
    return normalized


def normalize_role(value, *, valid_roles):
    role = str(value or "auto").strip().lower()
    return role if role in valid_roles else "auto"


def normalize_positive_seconds(value, default, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def default_provider(*, default_provider_id, default_provider_protocols, provider_capable_clis):
    return {
        "id": default_provider_id,
        "name": "Default Gateway",
        "protocols": list(default_provider_protocols),
        "supported_clis": list(provider_capable_clis),
        "enabled": True,
        "role": "auto",
    }


def normalize_priority(value, *, default_priority):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default_priority


def canonical_model_family(value, *, model_families):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    for entry in model_families:
        family = str(entry.get("family") or "").strip()
        if family.lower() == raw:
            return family
    return ""


def normalize_family_priority_overrides(value, *, model_families, default_priority):
    if not isinstance(value, dict):
        return {}
    normalized = {}
    for family_name, priority in value.items():
        canonical = canonical_model_family(family_name, model_families=model_families)
        if not canonical:
            continue
        normalized[canonical] = normalize_priority(priority, default_priority=default_priority)
    return normalized


def runtime_priority_for_family(
    runtime,
    family_name,
    *,
    canonical_model_family,
    normalize_priority,
    default_priority,
):
    canonical = canonical_model_family(family_name)
    overrides = runtime.get("family_priority_overrides", {}) if isinstance(runtime, dict) else {}
    if canonical and isinstance(overrides, dict) and canonical in overrides:
        return normalize_priority(overrides.get(canonical))
    if isinstance(runtime, dict):
        return normalize_priority(runtime.get("priority", default_priority))
    return default_priority


def runtime_priority_for_model(
    runtime,
    model_name,
    *,
    infer_model_family,
    runtime_priority_for_family,
):
    family_name, _ = infer_model_family(model_name)
    return runtime_priority_for_family(runtime, family_name)


def runtime_with_priority(
    runtime,
    *,
    model_name="",
    family_name="",
    canonical_model_family,
    infer_model_family,
    runtime_priority_for_family,
    normalize_priority,
    default_priority,
):
    if not isinstance(runtime, dict):
        return runtime
    canonical_family = canonical_model_family(family_name)
    if not canonical_family and model_name:
        canonical_family, _ = infer_model_family(model_name)
    merged = dict(runtime)
    merged["priority"] = (
        runtime_priority_for_family(runtime, canonical_family)
        if canonical_family
        else normalize_priority(runtime.get("priority", default_priority))
    )
    if canonical_family:
        merged["priority_family"] = canonical_family
    return merged


def normalize_claude_1m_mode(value, *, default="auto", valid_modes):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in valid_modes else "auto"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in valid_modes else "auto"


def normalize_timezone_name(value, *, default):
    timezone_name = str(value or "").strip() or default
    if timezone_name:
        try:
            ZoneInfo(timezone_name)
        except Exception:
            timezone_name = default
    return timezone_name


def normalize_provider(
    provider,
    *,
    default_provider_id,
    default_provider_protocols,
    provider_capable_clis,
    default_priority,
    model_families,
    default_account_timezone,
    claude_1m_valid_modes,
    cli_names,
    legacy_provider_cli_aliases,
):
    merged = dict(
        default_provider(
            default_provider_id=default_provider_id,
            default_provider_protocols=default_provider_protocols,
            provider_capable_clis=provider_capable_clis,
        )
    )
    merged.update(provider)
    merged.pop("cost_level", None)
    merged.pop("daily_budget", None)
    merged["id"] = str(merged.get("id") or default_provider_id).strip() or default_provider_id
    merged["name"] = str(merged.get("name") or merged["id"]).strip() or merged["id"]

    protocols = merged.get("protocols", default_provider_protocols)
    if isinstance(protocols, str):
        protocols = [protocols]
    merged["protocols"] = [str(item).strip() for item in protocols if str(item).strip()]
    if not merged["protocols"]:
        merged["protocols"] = list(default_provider_protocols)

    merged["supported_clis"] = normalize_supported_clis(
        merged.get("supported_clis", provider_capable_clis),
        protocols=merged["protocols"],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_provider_cli_aliases,
    )
    if not merged["supported_clis"]:
        merged["supported_clis"] = list(provider_capable_clis)

    merged["enabled"] = bool(merged.get("enabled", True))
    merged["priority"] = normalize_priority(merged.get("priority", default_priority), default_priority=default_priority)
    merged["family_priority_overrides"] = normalize_family_priority_overrides(
        merged.get("family_priority_overrides", {}),
        model_families=model_families,
        default_priority=default_priority,
    )
    merged["claude_1m_mode"] = normalize_claude_1m_mode(
        merged.get("claude_1m_mode", "auto"),
        valid_modes=claude_1m_valid_modes,
    )
    merged["proxy"] = str(merged.get("proxy", "")).strip()
    merged["no_proxy"] = str(merged.get("no_proxy", "")).strip()
    merged["timezone"] = normalize_timezone_name(merged.get("timezone"), default=default_account_timezone)
    merged["force_ipv4"] = runtime_force_ipv4(merged)
    merged["note"] = str(merged.get("note", "")).strip()
    merged["default_openai_base_url"] = str(merged.get("default_openai_base_url", "")).strip().rstrip("/")
    merged["default_anthropic_base_url"] = str(merged.get("default_anthropic_base_url", "")).strip().rstrip("/")
    merged["fallback_models"] = normalize_model_id_list(merged.get("fallback_models", []))
    merged["extra_models"] = normalize_model_id_list(merged.get("extra_models", []))
    merged["hidden_models"] = normalize_model_id_list(merged.get("hidden_models", []))
    merged["models_endpoint"] = normalize_models_endpoint(merged.get("models_endpoint", "/models"))
    return merged


def default_account_home(account_id, *, accounts_dir):
    return os.path.join(accounts_dir, account_id)


def normalize_account(
    account,
    *,
    oauth_capable_clis,
    accounts_dir,
    default_priority,
    model_families,
    default_account_timezone,
    claude_1m_valid_modes,
):
    cli = str(account.get("cli") or "claude").strip().lower()
    if cli not in oauth_capable_clis:
        cli = "claude"
    account_id = normalize_account_id(account.get("id") or f"{cli}-account")
    default_home = default_account_home(account_id, accounts_dir=accounts_dir)
    home_dir = str(account.get("home_dir") or default_home).strip() or default_home
    proxy = str(account.get("proxy") or "").strip()
    no_proxy = str(account.get("no_proxy") or "").strip()
    timezone_name = normalize_timezone_name(account.get("timezone"), default=default_account_timezone)
    return {
        "id": account_id,
        "name": str(account.get("name") or account_id).strip() or account_id,
        "cli": cli,
        "auth_mode": "oauth",
        "enabled": bool(account.get("enabled", True)),
        "home_dir": os.path.expanduser(home_dir),
        "priority": normalize_priority(account.get("priority", default_priority), default_priority=default_priority),
        "family_priority_overrides": normalize_family_priority_overrides(
            account.get("family_priority_overrides", {}),
            model_families=model_families,
            default_priority=default_priority,
        ),
        "claude_1m_mode": normalize_claude_1m_mode(
            account.get("claude_1m_mode", "auto"),
            valid_modes=claude_1m_valid_modes,
        ),
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "force_ipv4": runtime_force_ipv4(account),
        "note": str(account.get("note", "")).strip(),
    }


def normalize_account_id(account_id):
    value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(account_id or "").strip().lower())
    value = value.strip("-_")
    return value or "account"


def account_label(account):
    return account.get("name", account.get("id", "account"))


def scrub_account_command_env(
    env,
    *,
    prefix_blocklist,
    proxy_env_keys,
    fake_env_keys,
    ca_env_keys,
):
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if any(normalized.startswith(prefix) for prefix in prefix_blocklist):
            env.pop(key, None)
            continue
        if normalized in proxy_env_keys or normalized in fake_env_keys or normalized in ca_env_keys:
            env.pop(key, None)
    return env


def account_env(
    account,
    *,
    scrub_account_command_env,
    seed_claude_state,
    seed_agy_state,
    seed_gemini_state,
    environ=os.environ,
    expanduser=os.path.expanduser,
    path_join=os.path.join,
):
    home_dir = expanduser(str(account.get("home_dir", "")).strip())
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
    elif cli_name == "agy":
        seed_agy_state(home_dir)
    env = dict(environ)
    scrub_account_command_env(env)
    if cli_name == "gemini":
        seed_gemini_state(home_dir)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        xdg_config_home = path_join(home_dir, ".config")
        env["HOME"] = home_dir
        env["XDG_CONFIG_HOME"] = xdg_config_home
    proxy = str(account.get("proxy", "")).strip()
    no_proxy = str(account.get("no_proxy", "")).strip()
    timezone_name = str(account.get("timezone", "")).strip()
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = proxy
        for key in ("NO_PROXY", "no_proxy"):
            env[key] = no_proxy
    if timezone_name:
        env["TZ"] = timezone_name
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


def account_status_command(cli_name):
    if cli_name == "claude":
        return ["claude", "auth", "status"]
    if cli_name == "codex":
        return ["codex", "login", "status"]
    if cli_name == "gemini":
        return None
    if cli_name == "agy":
        return None
    return None


def probe_account_status(
    account,
    *,
    account_env,
    account_status_command=account_status_command,
    expanduser=os.path.expanduser,
    path_exists=os.path.exists,
    path_isdir=os.path.isdir,
    run_command=subprocess.run,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        return {
            "state": "delegated",
            "summary": "Claude OAuth 独立入口已下线；MMS 不再探测或登录这个账号",
        }
    if cli_name == "gemini":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        gemini_dir = os.path.join(home_dir, ".gemini")
        oauth_path = os.path.join(gemini_dir, "oauth_creds.json")
        accounts_path = os.path.join(gemini_dir, "google_accounts.json")
        settings_path = os.path.join(gemini_dir, "settings.json")
        if path_exists(oauth_path) or path_exists(accounts_path):
            return {
                "state": "configured",
                "summary": "已配置 OAuth，建议直接启动 Gemini 验证",
            }
        has_state = path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，待登录" if has_state else "待登录",
        }
    if cli_name == "agy":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        agy_dir = os.path.join(home_dir, ".gemini", "antigravity-cli")
        settings_path = os.path.join(agy_dir, "settings.json")
        has_state = path_isdir(agy_dir) or path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，登录状态需启动 agy 验证" if has_state else "待登录",
        }
    command = account_status_command(cli_name)
    if command is None:
        return {"state": "unsupported", "summary": "不支持状态探测"}
    try:
        result = run_command(
            command,
            env=account_env(account),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return {"state": "cli_missing", "summary": f"{cli_name} 未安装"}
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "summary": "状态探测超时"}

    output_text = (result.stdout or result.stderr or "").strip()
    output = output_text.splitlines()
    summary = output[0].strip() if output else ""
    if cli_name == "claude" and output_text.startswith("{"):
        try:
            payload = json.loads(output_text)
            email = payload.get("email", "")
            sub = payload.get("subscriptionType", "")
            summary = " / ".join(part for part in [email, sub] if part) or summary
        except json.JSONDecodeError:
            pass
    if result.returncode == 0:
        return {"state": "logged_in", "summary": summary or "已登录"}
    return {"state": "logged_out", "summary": summary or "未登录"}


def run_account_login(
    account,
    *,
    account_env,
    account_label,
    makedirs=os.makedirs,
    run_command=subprocess.run,
    console,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    env = account_env(account)
    makedirs(account.get("home_dir", ""), exist_ok=True)
    if cli_name == "codex":
        command = ["codex", "login"]
    elif cli_name == "gemini":
        command = ["gemini"]
    elif cli_name == "agy":
        command = ["agy"]
    else:
        console.print(f"[red]不支持的官方账号类型: {cli_name}[/red]")
        sys.exit(1)
    env_hint = f"HOME={account.get('home_dir')}"
    if cli_name == "gemini":
        env_hint = f"GEMINI_CLI_HOME={account.get('home_dir')}"
    console.print(
        f"[cyan]正在为账号档案 {account_label(account)} 打开 {cli_name} 登录流程[/cyan]\n"
        f"[dim]{env_hint}[/dim]"
    )
    if cli_name == "gemini":
        console.print("[dim]Gemini 会在自己的 CLI 内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    if cli_name == "agy":
        console.print("[dim]Antigravity CLI 会在自己的流程内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    result = run_command(command, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)


def upsert_provider(cfg, provider, *, ensure_provider_config):
    providers = []
    replaced = False
    for item in cfg.get("providers", []):
        if item.get("id") == provider["id"]:
            providers.append(provider)
            replaced = True
        else:
            providers.append(item)
    if not replaced:
        providers.append(provider)

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = providers
    updated_cfg, _ = ensure_provider_config(updated_cfg)
    return updated_cfg


def delete_provider_credentials(
    provider_id,
    *,
    credentials_path,
    load_env_file,
    provider_env_name,
    default_provider_id,
    api_url_env_name,
    api_key_env_name,
    shell_quote,
    path_exists=os.path.exists,
    chmod=os.chmod,
):
    if not path_exists(credentials_path):
        return
    values = load_env_file(credentials_path)
    keys_to_remove = {
        provider_env_name(provider_id, "BASE_URL"),
        provider_env_name(provider_id, "OPENAI_BASE_URL"),
        provider_env_name(provider_id, "ANTHROPIC_BASE_URL"),
        provider_env_name(provider_id, "API_KEY"),
    }
    if provider_id == default_provider_id:
        keys_to_remove.update({api_url_env_name, api_key_env_name})
    changed = False
    for key in keys_to_remove:
        if key in values:
            values.pop(key, None)
            changed = True
    if not changed:
        return
    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={shell_quote(str(values[key]))}")
    lines.append("")
    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    chmod(credentials_path, 0o600)


def ensure_provider_config(cfg, *, default_provider_id, default_provider, normalize_provider):
    cfg = dict(cfg)
    raw_providers = cfg.get("providers")
    normalized = []
    seen_ids = set()

    if isinstance(raw_providers, list):
        for item in raw_providers:
            if not isinstance(item, dict):
                continue
            provider = normalize_provider(item)
            if provider["id"] in seen_ids:
                continue
            normalized.append(provider)
            seen_ids.add(provider["id"])

    if not normalized:
        normalized = [default_provider()]

    provider_cfg = cfg.get("provider", {})
    default_provider_value = default_provider_id
    if isinstance(provider_cfg, dict):
        default_provider_value = str(provider_cfg.get("default") or default_provider_id).strip() or default_provider_id
    if default_provider_value not in seen_ids and default_provider_value not in {p["id"] for p in normalized}:
        default_provider_value = normalized[0]["id"]

    new_cfg = dict(cfg)
    new_cfg["providers"] = normalized
    new_cfg["provider"] = {"default": default_provider_value}
    changed = new_cfg != cfg
    return new_cfg, changed


def ensure_account_config(cfg, *, oauth_capable_clis, normalize_account):
    cfg = dict(cfg)
    raw_accounts = cfg.get("accounts")
    normalized = []
    seen_ids = set()

    if isinstance(raw_accounts, list):
        for item in raw_accounts:
            if not isinstance(item, dict):
                continue
            account = normalize_account(item)
            if account["id"] in seen_ids:
                continue
            normalized.append(account)
            seen_ids.add(account["id"])

    raw_defaults = cfg.get("account", {})
    defaults = {}
    if isinstance(raw_defaults, dict):
        raw_cli_defaults = raw_defaults.get("defaults", raw_defaults)
        if isinstance(raw_cli_defaults, dict):
            for cli in oauth_capable_clis:
                account_id = str(raw_cli_defaults.get(cli, "")).strip()
                if account_id:
                    defaults[cli] = account_id

    defaults = {
        cli: account_id for cli, account_id in defaults.items()
        if account_id in seen_ids
    }

    new_cfg = dict(cfg)
    new_cfg["accounts"] = normalized
    new_cfg["account"] = {"defaults": defaults}
    changed = new_cfg != cfg
    return new_cfg, changed


def normalize_preset_entry(name, preset, *, normalize_account_id=normalize_account_id):
    if isinstance(preset, str):
        preset = {"cli": "claude", "model": preset}
    elif not isinstance(preset, dict):
        preset = {"cli": "claude"}

    normalized = {"cli": str(preset.get("cli") or "claude").strip().lower() or "claude"}

    description = str(preset.get("description") or "").strip()
    if description:
        normalized["description"] = description

    provider = str(preset.get("provider") or "").strip()
    if provider:
        normalized["provider"] = provider

    account = str(preset.get("account") or "").strip()
    if account:
        normalized["account"] = normalize_account_id(account)

    bridge = str(preset.get("bridge") or "").strip()
    if bridge:
        normalized["bridge"] = bridge

    model = str(preset.get("model") or "").strip()
    if not model:
        for legacy_key in ("sonnet", "opus", "haiku"):
            value = str(preset.get(legacy_key) or "").strip()
            if value:
                model = value
                break
    if model:
        normalized["model"] = model

    for key, value in preset.items():
        if key in {"cli", "description", "provider", "account", "bridge", "model", "sonnet", "opus", "haiku"}:
            continue
        normalized[key] = value

    return normalized


def normalize_presets_config(cfg, *, normalize_preset_entry=normalize_preset_entry):
    raw_presets = cfg.get("presets")
    if raw_presets is None:
        return cfg, False
    if not isinstance(raw_presets, dict):
        updated = dict(cfg)
        updated["presets"] = {}
        return updated, True

    normalized = {}
    changed = False
    for name, preset in raw_presets.items():
        normalized_name = str(name).strip()
        if not normalized_name:
            changed = True
            continue
        normalized_preset = normalize_preset_entry(normalized_name, preset)
        normalized[normalized_name] = normalized_preset
        if normalized_name != name or normalized_preset != preset:
            changed = True

    if not changed:
        return cfg, False

    updated = dict(cfg)
    updated["presets"] = normalized
    return updated, True


def normalize_user_config(cfg, *, mode_all, normalize_user_role):
    user_cfg = cfg.get("user", {})
    if not isinstance(user_cfg, dict):
        new_cfg = dict(cfg)
        new_cfg["user"] = {"role": mode_all}
        return new_cfg, True

    normalized_role = normalize_user_role(user_cfg.get("role", mode_all))
    if user_cfg.get("role") == normalized_role:
        return cfg, False

    new_cfg = dict(cfg)
    new_user = dict(user_cfg)
    new_user["role"] = normalized_role
    new_cfg["user"] = new_user
    return new_cfg, True


def normalize_cache_config(
    cfg,
    *,
    probe_async_refresh_after,
    probe_async_min_interval,
    normalize_positive_seconds=normalize_positive_seconds,
):
    cache_cfg = cfg.get("cache", {})
    if not isinstance(cache_cfg, dict):
        cache_cfg = {}

    normalized = {
        "probe_async_refresh_after_sec": normalize_positive_seconds(
            cache_cfg.get("probe_async_refresh_after_sec", probe_async_refresh_after),
            probe_async_refresh_after,
        ),
        "probe_async_min_interval_sec": normalize_positive_seconds(
            cache_cfg.get("probe_async_min_interval_sec", probe_async_min_interval),
            probe_async_min_interval,
        ),
    }

    if cache_cfg == normalized:
        return cfg, False

    new_cfg = dict(cfg)
    new_cfg["cache"] = normalized
    return new_cfg, True


def snapshot_diff_lines(previous_snapshot, current_snapshot, *, is_snapshot_ignored_file):
    diffs = []
    previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current_snapshot = current_snapshot if isinstance(current_snapshot, dict) else {}

    previous_defaults = previous_snapshot.get("defaults") or {}
    current_defaults = current_snapshot.get("defaults") or {}
    if previous_defaults != current_defaults:
        diffs.append("default route/account changed")

    previous_accounts = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    current_accounts = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    for account_id in sorted(set(previous_accounts) | set(current_accounts)):
        previous_entry = previous_accounts.get(account_id)
        current_entry = current_accounts.get(account_id)
        if previous_entry is None:
            diffs.append(f"account added: {account_id}")
            continue
        if current_entry is None:
            diffs.append(f"account removed: {account_id}")
            continue
        field_labels = {
            "cli": "cli",
            "enabled": "enabled",
            "home_dir": "home_dir",
            "priority": "priority",
            "claude_1m_mode": "claude_1m_mode",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
            "identity_sha256": "identity",
        }
        for field_name, field_label in field_labels.items():
            if field_name == "identity_sha256":
                previous_value = previous_entry.get(field_name, "")
                current_value = current_entry.get(field_name, "")
            else:
                previous_value = previous_entry.get(field_name)
                current_value = current_entry.get(field_name)
            if field_name == "identity_sha256" and field_name not in previous_entry:
                continue
            if previous_value != current_value:
                if field_name == "proxy_sha256":
                    old_value = previous_entry.get("proxy_fingerprint")
                    new_value = current_entry.get("proxy_fingerprint")
                elif field_name == "identity_sha256":
                    old_value = previous_entry.get("identity_fingerprint")
                    new_value = current_entry.get("identity_fingerprint")
                else:
                    old_value = previous_entry.get(field_name)
                    new_value = current_entry.get(field_name)
                diffs.append(f"account {account_id} {field_label}: {old_value} -> {new_value}")

    previous_providers = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    current_providers = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    for provider_id in sorted(set(previous_providers) | set(current_providers)):
        previous_entry = previous_providers.get(provider_id)
        current_entry = current_providers.get(provider_id)
        if previous_entry is None:
            diffs.append(f"provider added: {provider_id}")
            continue
        if current_entry is None:
            diffs.append(f"provider removed: {provider_id}")
            continue
        field_labels = {
            "enabled": "enabled",
            "priority": "priority",
            "models_endpoint": "models_endpoint",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
        }
        for field_name, field_label in field_labels.items():
            if previous_entry.get(field_name) != current_entry.get(field_name):
                old_value = previous_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else previous_entry.get(field_name)
                new_value = current_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else current_entry.get(field_name)
                diffs.append(f"provider {provider_id} {field_label}: {old_value} -> {new_value}")

    previous_files = {
        str(item.get("path") or ""): item
        for item in previous_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    current_files = {
        str(item.get("path") or ""): item
        for item in current_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    for path in sorted(set(previous_files) | set(current_files)):
        if os.path.basename(str(path or "")) == ".claude.json":
            continue
        previous_entry = previous_files.get(path)
        current_entry = current_files.get(path)
        if previous_entry is None:
            diffs.append(f"file added: {path}")
            continue
        if current_entry is None:
            diffs.append(f"file removed: {path}")
            continue
        if bool(previous_entry.get("exists")) != bool(current_entry.get("exists")):
            diffs.append(f"file presence changed: {path}")
            continue
        if previous_entry.get("sha256") != current_entry.get("sha256"):
            diffs.append(f"file changed: {path}")
    return diffs


def runtime_force_ipv4(runtime):
    raw = False if not isinstance(runtime, dict) else runtime.get("force_ipv4", False)
    if isinstance(raw, bool):
        return raw
    value = str(raw or "").strip().lower()
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if value in {"1", "true", "yes", "on", "enable", "enabled", ""}:
        return True
    return False


def url_matches_host_suffix(url, host_suffixes):
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    for suffix in host_suffixes:
        normalized = str(suffix or "").strip().lower().lstrip(".")
        if not normalized:
            continue
        if host == normalized or host.endswith("." + normalized):
            return True
    return False


def runtime_should_disable_ambient_env(
    runtime,
    *,
    target_url="",
    official_hosts,
    url_matches_host_suffix=url_matches_host_suffix,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    if str(runtime.get("proxy") or "").strip():
        return True
    return url_matches_host_suffix(target_url, official_hosts)


def runtime_httpx_kwargs(
    runtime,
    *,
    target_url="",
    official_hosts,
    runtime_force_ipv4=runtime_force_ipv4,
    runtime_should_disable_ambient_env=runtime_should_disable_ambient_env,
):
    transport_kwargs = {}
    proxy_url = str((runtime or {}).get("proxy") or "").strip()
    if proxy_url:
        transport_kwargs["proxy"] = proxy_url
    if runtime_should_disable_ambient_env(runtime, target_url=target_url, official_hosts=official_hosts):
        transport_kwargs["trust_env"] = False
    if runtime_force_ipv4(runtime):
        transport_kwargs["local_address"] = "0.0.0.0"
    return transport_kwargs


def validate_proxy_url(proxy_url, *, supported_proxy_schemes):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return None
    try:
        parsed = urlparse(proxy_url)
    except Exception:
        return "代理地址解析失败"
    if parsed.scheme.lower() not in supported_proxy_schemes:
        return "代理协议仅支持 http / https / socks5 / socks5h"
    if not parsed.hostname:
        return "代理地址缺少 host"
    if parsed.port is None:
        return "代理地址缺少 port"
    return None


def test_proxy_connectivity(
    proxy_url,
    no_proxy="",
    target_url="https://api.anthropic.com",
    force_ipv4=True,
    *,
    fake_upstream_enabled,
    fake_proxy_probe,
    http_status_is_success,
    which=shutil.which,
    run_command=subprocess.run,
):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return True, "未配置代理，跳过检测"
    if fake_upstream_enabled():
        probe = fake_proxy_probe(
            target_url,
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=False,
        )
        return bool(probe.get("ok")), str(probe.get("detail") or probe.get("http_code") or "fake upstream")
    curl_bin = which("curl")
    if not curl_bin:
        return False, "当前系统没有 curl，无法测试代理连通性"
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        proxy_url,
        target_url,
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = run_command(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode == 0 and http_status_is_success(http_code):
        return True, f"代理连通性测试通过：{target_url} (HTTP {http_code})"
    detail = (result.stderr or "").strip()
    if http_code and http_code not in {"000"}:
        detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return False, detail or f"代理连通性测试失败：{target_url}"


def parse_semver_tag(tag):
    value = str(tag or "").strip()
    if not value.startswith("v"):
        return None
    parts = value[1:].split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def normalize_semver_tags(raw_tags):
    if not isinstance(raw_tags, list):
        return []

    normalized = []
    seen = set()
    for item in raw_tags:
        tag = str(item or "").strip()
        parsed = parse_semver_tag(tag)
        if parsed is None or tag in seen:
            continue
        seen.add(tag)
        normalized.append((parsed, tag))

    normalized.sort(key=lambda item: item[0], reverse=True)
    return [tag for _, tag in normalized]


def fetch_latest_semver_tags(*, limit, request_cls, urlopen_func, json_load, normalize_semver_tags):
    req = request_cls(
        f"https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page={int(limit)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mms-update-check",
        },
    )
    with urlopen_func(req, timeout=3) as resp:
        data = json_load(resp)

    if not isinstance(data, list):
        return ""

    semver_tags = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("name") or "").strip()
        semver_tags.append(tag)
    return normalize_semver_tags(semver_tags)


def fetch_latest_semver_tag(*, fetch_latest_semver_tags):
    semver_tags = fetch_latest_semver_tags()
    return semver_tags[0] if semver_tags else ""


def extract_semver_text(value):
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value or ""))
    return match.group(0) if match else ""


def parse_semver_text(value):
    version = extract_semver_text(value)
    if not version:
        return None
    core = re.split(r"[-+]", version, maxsplit=1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def compare_semver_text(current, latest):
    current_semver = parse_semver_text(current)
    latest_semver = parse_semver_text(latest)
    if current_semver is None or latest_semver is None:
        return None
    if current_semver < latest_semver:
        return -1
    if current_semver > latest_semver:
        return 1
    return 0


def detect_cli_version(command_name, *, which, subprocess_run, extract_semver_text, localize):
    command = str(command_name or "").strip()
    if not command:
        return {"installed": False, "label": localize("未安装", "not installed"), "version": "", "path": ""}
    path = which(command)
    if not path:
        return {"installed": False, "label": localize("未安装", "not installed"), "version": "", "path": ""}
    try:
        result = subprocess_run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return {
            "installed": True,
            "label": localize(f"读取失败: {exc}", f"version failed: {exc}"),
            "version": "",
            "path": path,
        }
    raw = str(result.stdout or "").strip().splitlines()
    label = raw[0].strip() if raw else (path if result.returncode == 0 else localize("读取失败", "version failed"))
    return {
        "installed": True,
        "label": label,
        "version": extract_semver_text(label),
        "path": path,
    }


def fetch_npm_package_latest_version(package_name, *, which, subprocess_run, extract_semver_text):
    package = str(package_name or "").strip()
    if not package:
        return ""
    npm_bin = which("npm")
    if not npm_bin:
        return ""
    try:
        result = subprocess_run(
            [npm_bin, "view", package, "version", "--silent"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=6,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return extract_semver_text(str(result.stdout or "").strip())


def git_output(args, *, subprocess_run, file_path):
    try:
        result = subprocess_run(
            ["git", "-C", os.path.dirname(os.path.abspath(file_path)), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def semver_tag_gap(installed_version, known_tags, latest_tag=""):
    installed_version = str(installed_version or "").strip()
    tags = normalize_semver_tags(known_tags)
    if not tags:
        latest_semver = parse_semver_tag(latest_tag)
        installed_semver = parse_semver_tag(installed_version)
        if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
            return 0
        return None

    latest_tag = tags[0]
    latest_semver = parse_semver_tag(latest_tag)
    installed_semver = parse_semver_tag(installed_version)
    if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
        return 0

    try:
        return tags.index(installed_version)
    except ValueError:
        return len(tags)


def installed_update_semver(version_meta, *, update_notice_sources):
    source = str(version_meta.get("source") or "").strip()
    install_channel = str(version_meta.get("install_channel") or "").strip()
    if source:
        is_install_managed = source in update_notice_sources
    else:
        is_install_managed = bool(install_channel)
    if not is_install_managed:
        return None, None

    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_semver = parse_semver_tag(installed_version)
    if installed_semver is None:
        return None, None
    return installed_version, installed_semver


def update_notice(
    *,
    stdin,
    stdout,
    load_version_meta,
    installed_update_semver,
    load_update_check_cache,
    parse_semver_tag,
    semver_tag_gap,
    save_update_check_cache,
    now,
    version_gap,
    prompt_interval_sec,
):
    if not (stdin.isatty() and stdout.isatty()):
        return None

    version_meta = load_version_meta()
    installed_version, installed_semver = installed_update_semver(version_meta)
    if installed_semver is None:
        return None

    cache = load_update_check_cache()
    latest_tag = str(cache.get("latest_tag") or "").strip()
    latest_semver = parse_semver_tag(latest_tag)
    if latest_semver is None or latest_semver <= installed_semver:
        return None

    gap_count = semver_tag_gap(installed_version, cache.get("semver_tags"), latest_tag)
    is_major_upgrade = latest_semver[0] > installed_semver[0]
    if not is_major_upgrade and (gap_count is None or gap_count < version_gap):
        return None

    now_value = now()
    last_prompted_for = str(cache.get("last_prompted_for") or "").strip()
    last_prompted_at = float(cache.get("last_prompted_at") or 0)
    if last_prompted_for == latest_tag and now_value - last_prompted_at < prompt_interval_sec:
        return None

    cache["last_prompted_for"] = latest_tag
    cache["last_prompted_at"] = now_value
    save_update_check_cache(cache)
    return {
        "installed_version": installed_version,
        "latest_tag": latest_tag,
        "gap_count": gap_count,
        "upgrade_command": "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash",
    }


def major_update_notice(*, update_notice):
    return update_notice()


def start_async_update_check(
    *,
    load_version_meta,
    installed_update_semver,
    load_update_check_cache,
    fetch_latest_semver_tags,
    save_update_check_cache,
    lock,
    get_running,
    set_running,
    thread_cls,
    now,
    interval_sec,
):
    version_meta = load_version_meta()
    _installed_version, installed_semver = installed_update_semver(version_meta)
    if installed_semver is None:
        return

    cache = load_update_check_cache()
    last_checked_at = float(cache.get("checked_at") or 0)
    if now() - last_checked_at < interval_sec:
        return

    with lock:
        if get_running():
            return
        set_running(True)

    def _run():
        try:
            semver_tags = fetch_latest_semver_tags()
            payload = load_update_check_cache()
            payload["checked_at"] = now()
            if semver_tags:
                payload["latest_tag"] = semver_tags[0]
                payload["semver_tags"] = semver_tags
            save_update_check_cache(payload)
        except Exception:
            pass
        finally:
            with lock:
                set_running(False)

    thread_cls(
        target=_run,
        daemon=True,
        name="mms-update-check",
    ).start()


def mms_update_status(version_info, cache, *, localize):
    current = str(version_info.get("installed_version") or version_info.get("release") or "").strip()
    latest = str(cache.get("latest_tag") or "").strip()
    current_semver = parse_semver_tag(current)
    latest_semver = parse_semver_tag(latest)
    if current_semver is None:
        status = localize("开发版/无法判断", "dev/unknown")
        outdated = False
    elif latest_semver is None:
        status = localize("未检查 latest", "latest not checked")
        outdated = False
    elif current_semver < latest_semver:
        status = localize(f"有新版 {latest}", f"update available {latest}")
        outdated = True
    else:
        status = localize("最新", "latest")
        outdated = False
    return {
        "current": current or "dev",
        "latest": latest,
        "status": status,
        "outdated": outdated,
        "last_error": str(cache.get("last_error") or "").strip(),
    }


def release_version_info(*, load_version_meta, git_output):
    version_meta = load_version_meta()
    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_ref = str(version_meta.get("installed_ref") or "").strip()
    git_describe = git_output(["describe", "--tags", "--always", "--dirty"])
    git_branch = git_output(["branch", "--show-current"])
    git_commit = git_output(["rev-parse", "--short", "HEAD"])
    release = installed_version or git_describe or git_commit or "dev"
    return {
        "release": release,
        "installed_version": installed_version,
        "installed_ref": installed_ref,
        "git_describe": git_describe,
        "git_branch": git_branch,
        "git_commit": git_commit,
        "install_channel": str(version_meta.get("install_channel") or "").strip(),
        "source": str(version_meta.get("source") or "").strip(),
    }


def cli_version_status(
    *,
    force_update=False,
    load_update_check_cache,
    save_update_check_cache,
    cli_version_packages,
    detect_cli_version,
    fetch_npm_package_latest_version,
    compare_semver_text,
    localize,
    now,
):
    cache = load_update_check_cache()
    cached_latest = cache.get("cli_latest_versions") if isinstance(cache.get("cli_latest_versions"), dict) else {}
    latest_versions = dict(cached_latest)
    if force_update:
        latest_versions = {}
        for cli_name, package_name in cli_version_packages.items():
            latest_versions[cli_name] = fetch_npm_package_latest_version(package_name)
        cache["cli_latest_versions"] = latest_versions
        cache["cli_latest_checked_at"] = now()
        save_update_check_cache(cache)

    status = {}
    for cli_name in ("codex", "claude"):
        current = detect_cli_version(cli_name)
        latest = str(latest_versions.get(cli_name) or "").strip()
        comparison = compare_semver_text(current.get("version"), latest)
        if not current.get("installed"):
            label = localize("未安装", "not installed")
            outdated = False
        elif comparison == -1:
            label = localize(f"有新版 {latest}", f"update available {latest}")
            outdated = True
        elif comparison == 0:
            label = localize("最新", "latest")
            outdated = False
        elif latest:
            label = localize(f"高于 latest {latest}", f"newer than latest {latest}")
            outdated = False
        else:
            label = localize("未检查 latest", "latest not checked")
            outdated = False
        status[cli_name] = {
            **current,
            "latest": latest,
            "status": label,
            "outdated": outdated,
            "package": cli_version_packages.get(cli_name, ""),
        }
    return status


def refresh_update_cache_for_about(*, force_update=False, load_update_check_cache, fetch_latest_semver_tags, save_update_check_cache, now):
    cache = load_update_check_cache()
    if not force_update:
        return cache
    try:
        semver_tags = fetch_latest_semver_tags()
    except Exception as exc:
        cache["last_error"] = str(exc)
        cache["checked_at"] = now()
        save_update_check_cache(cache)
        return cache
    cache["checked_at"] = now()
    cache["last_error"] = ""
    if semver_tags:
        cache["latest_tag"] = semver_tags[0]
        cache["semver_tags"] = semver_tags
    save_update_check_cache(cache)
    return cache


def about_status_snapshot(*, force_update=False, release_version_info, refresh_update_cache_for_about, cli_version_status, mms_update_status):
    version_info = release_version_info()
    cache = refresh_update_cache_for_about(force_update=force_update)
    cli_status = cli_version_status(force_update=force_update)
    return {
        "version_info": version_info,
        "mms": mms_update_status(version_info, cache),
        "clis": cli_status,
        "checked_at": cache.get("checked_at"),
    }


def runtime_usage_key(runtime, cli_name):
    kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")
    return f"{kind}:{cli_name}:{runtime_id}"


def resolve_model_name(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = model_info.get(key)
            if value:
                return str(value)
        return "official-default"
    return str(model_info or "official-default")


def runtime_hint_from_runtime(runtime, *, runtime_provider_id, runtime_account_id):
    if not isinstance(runtime, dict):
        return {}
    hint = {
        "runtime_kind": str(runtime.get("runtime_kind", "")).strip(),
        "auth_mode": str(runtime.get("auth_mode", "")).strip(),
    }
    provider_id = runtime_provider_id(runtime)
    account_id = runtime_account_id(runtime)
    runtime_id = str(runtime.get("id") or "").strip()
    if provider_id:
        hint["provider_id"] = provider_id
    if account_id:
        hint["account_id"] = account_id
    if runtime_id:
        hint["runtime_id"] = runtime_id
    return {k: v for k, v in hint.items() if v}


def record_usage(
    runtime,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    runtime_usage_key=runtime_usage_key,
    resolve_model_name=resolve_model_name,
    runtime_hint_from_runtime,
):
    def _mutate(stats):
        sources = stats.setdefault("sources", {})
        key = runtime_usage_key(runtime, cli_name)
        model_name = resolve_model_name(model_info)
        now = iso_now()
        entry = sources.setdefault(key, {
            "runtime_kind": runtime.get("runtime_kind", "provider"),
            "id": runtime.get("id", "default"),
            "name": runtime.get("name", runtime.get("id", "default")),
            "cli": cli_name,
            "launches": 0,
            "last_used_at": "",
            "last_model": "",
            "models": {},
            "model_last_used_at": {},
        })
        entry["launches"] += 1
        entry["last_used_at"] = now
        entry["last_model"] = model_name
        models = entry.setdefault("models", {})
        models[model_name] = int(models.get(model_name, 0)) + 1
        model_last_used_at = entry.setdefault("model_last_used_at", {})
        model_last_used_at[model_name] = now
        last_by_cli = stats.setdefault("last_by_cli", {})
        last_by_cli[cli_name] = {
            "cli": cli_name,
            "model": model_name,
            "model_info": model_info if isinstance(model_info, dict) else {"model": str(model_info)},
            "runtime_hint": runtime_hint_from_runtime(runtime),
            "last_used_at": now,
        }

    update_usage_stats(_mutate)


def record_scene_usage(
    scene_name,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    resolve_model_name=resolve_model_name,
):
    if not scene_name or str(scene_name).startswith("__"):
        return

    def _mutate(stats):
        scene_stats = stats.setdefault("scenes", {})
        model_name = resolve_model_name(model_info)
        entry = scene_stats.setdefault(scene_name, {
            "launches": 0,
            "last_used_at": "",
            "last_cli": "",
            "last_model": "",
        })
        entry["launches"] += 1
        entry["last_used_at"] = iso_now()
        entry["last_cli"] = cli_name
        entry["last_model"] = model_name

    update_usage_stats(_mutate)


def infer_runtime_hint_from_usage_stats(stats, cli_name, model_name):
    latest_entry = None
    latest_at = ""
    normalized_model = str(model_name or "").strip()
    for entry in (stats.get("sources", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        if str(entry.get("last_model") or "").strip() != normalized_model:
            continue
        used_at = str(entry.get("last_used_at") or "").strip()
        if used_at < latest_at:
            continue
        latest_at = used_at
        latest_entry = entry

    if not isinstance(latest_entry, dict):
        return {}

    runtime_kind = str(latest_entry.get("runtime_kind") or "").strip()
    runtime_id = str(latest_entry.get("id") or "").strip()
    if not runtime_kind or not runtime_id:
        return {}

    hint = {
        "runtime_kind": runtime_kind,
        "runtime_id": runtime_id,
    }
    if runtime_kind == "provider":
        hint["auth_mode"] = "api_key"
        hint["provider_id"] = runtime_id
    elif runtime_kind == "account":
        hint["auth_mode"] = "oauth"
        hint["account_id"] = runtime_id
    else:
        return {}
    return hint


def get_scene_usage(
    *,
    load_usage_stats,
    resolve_model_name=resolve_model_name,
    infer_runtime_hint_from_usage_stats=infer_runtime_hint_from_usage_stats,
):
    stats = load_usage_stats()
    scene_counts = {}
    for name, entry in stats.get("scenes", {}).items():
        scene_counts[name] = entry.get("launches", 0)
    last_by_cli = {}
    for cli_name, item in (stats.get("last_by_cli", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if not isinstance(normalized.get("runtime_hint"), dict):
            model_name = resolve_model_name(
                normalized.get("model_info") if isinstance(normalized.get("model_info"), dict) else normalized.get("model")
            )
            inferred = infer_runtime_hint_from_usage_stats(stats, cli_name, model_name)
            if inferred:
                normalized["runtime_hint"] = inferred
        last_by_cli[cli_name] = normalized
    return last_by_cli, scene_counts


def resolve_last_used_runtime(
    cfg,
    cli_name,
    last_item,
    default_models,
    *,
    resolve_model_name=resolve_model_name,
    resolve_provider_context,
    provider_supports_model_for_cli,
    probe_models,
    provider_effective_models,
    runtime_with_priority,
    resolve_account_context,
    model_matches_account_cli,
):
    if not isinstance(last_item, dict):
        return None, None, None

    hint = last_item.get("runtime_hint")
    if not isinstance(hint, dict):
        return None, None, None

    model_info = last_item.get("model_info") if isinstance(last_item.get("model_info"), dict) else {
        "model": str(last_item.get("model") or "")
    }
    model_name = resolve_model_name(model_info)

    provider_id = str(hint.get("provider_id") or "").strip()
    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            provider = None
        if provider and provider_supports_model_for_cli(provider, cli_name, model_name):
            models = probe_models(provider, emit_output=False).get("models")
            models = provider_effective_models(provider, models, cfg)
            if str(model_name or "").strip().lower() in {
                str(item or "").strip().lower() for item in (models or [])
            }:
                return (
                    runtime_with_priority(provider, model_name=model_name),
                    models,
                    f"last used provider:{provider_id}",
                )

    auth_mode = str(hint.get("auth_mode") or "").strip()
    account_id = str(hint.get("account_id") or "").strip()
    if account_id and auth_mode != "oauth_bridge":
        try:
            account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        except Exception:
            account = None
        if account and model_matches_account_cli(cli_name, model_name):
            return (
                runtime_with_priority(account, model_name=model_name),
                list(default_models or []),
                f"last used account:{account_id}",
            )

    return None, None, None


def all_provider_models_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    mms_model_visible,
    provider_supports_model_for_cli,
):
    merged = []
    seen = set()
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or normalized in seen:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def aggregate_provider_models(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_label,
    mms_model_visible,
    provider_supports_model_for_cli,
    default_provider_id,
):
    aggregated = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            aggregated.append({
                "model": normalized,
                "provider_id": provider_id,
                "provider_name": provider_name,
            })
    return aggregated


def categorize_models(models, *, filter_visible_models, infer_model_family):
    categorized = {}
    for model_name in filter_visible_models(models):
        _, category = infer_model_family(model_name)
        categorized.setdefault(category, []).append(model_name)
    return categorized


def display_models(
    models,
    role,
    recommend,
    *,
    ensure_rich,
    categorize_models,
    normalize_user_role,
    mode_recommended,
    model_capability_summary,
    model_cli_summary,
    table_cls,
    console,
):
    ensure_rich()
    categorized = categorize_models(models)
    table = table_cls(title="可用模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    table.add_column("分类", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")

    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))

    if normalize_user_role(role) == mode_recommended and recommend:
        flat = [(model_name, category) for model_name, category in flat if model_name in recommend]

    for index, (model_name, category) in enumerate(flat, 1):
        tag = " ⭐" if recommend and model_name in recommend else ""
        table.add_row(
            str(index),
            model_name + tag,
            category,
            model_capability_summary(model_name),
            model_cli_summary(model_name),
        )

    console.print(table)
    return [model_name for model_name, _ in flat]


def filter_models_for_display(models, role, recommend, *, categorize_models, normalize_user_role, mode_recommended):
    categorized = categorize_models(models)
    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))
    if normalize_user_role(role) == mode_recommended and recommend:
        allowed = set(recommend)
        flat = [(model_name, category) for model_name, category in flat if model_name in allowed]
    return flat


def group_models_for_custom(models, role, recommend, *, filter_models_for_display, infer_model_family):
    grouped = {}
    order = []
    for model_name, _ in filter_models_for_display(models, role, recommend):
        family, _ = infer_model_family(model_name)
        if family not in grouped:
            grouped[family] = []
            order.append(family)
        grouped[family].append(model_name)
    return [(family, grouped[family]) for family in order]


def group_models_by_family_and_provider(
    aggregated_models,
    role,
    recommend,
    *,
    filter_models_for_display,
    infer_model_family,
):
    plain_models = [entry["model"] for entry in aggregated_models]
    allowed = {
        model_name for model_name, _ in filter_models_for_display(plain_models, role, recommend)
    }

    family_order = []
    family_providers = {}
    for entry in aggregated_models:
        model_name = entry["model"]
        if model_name not in allowed:
            continue
        family, _ = infer_model_family(model_name)
        provider_key = f"{entry['provider_name']}||{entry['provider_id']}"

        if family not in family_providers:
            family_providers[family] = {}
            family_order.append(family)
        providers = family_providers[family]
        providers.setdefault(provider_key, [])
        if model_name not in providers[provider_key]:
            providers[provider_key].append(model_name)

    return [(family, dict(family_providers[family])) for family in family_order]


def build_provider_options_map(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_names,
    *,
    infer_model_family,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_supports_model_for_cli,
    runtime_with_priority,
    provider_label,
    account_options_for_model,
    default_provider_id,
):
    result = {}
    for model_name in model_names:
        selected_family, _ = infer_model_family(model_name)
        options = []
        for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
            if not provider.get("enabled", True):
                continue
            if not provider_has_configured_base_url(provider):
                continue
            if not provider.get("api_key"):
                continue
            models = provider_effective_models(provider, cached_models, cfg)
            model_lower = [str(item or "").strip().lower() for item in models]
            if model_name.strip().lower() not in model_lower:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, model_name):
                continue
            runtime = runtime_with_priority(provider, model_name=model_name, family_name=selected_family)
            options.append({
                "provider_name": provider_label(provider),
                "provider_id": provider.get("id", default_provider_id),
                "priority_family": selected_family,
                "provider_ctx": runtime,
            })
        account_options = account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info={"model": model_name},
            allow_selected_model=True,
        )
        for option in account_options:
            runtime = option.get("runtime") or {}
            options.append({
                "provider_name": f"{option.get('title', runtime.get('id', 'account'))} OAuth",
                "provider_id": runtime.get("id", ""),
                "priority_family": option.get("priority_family", selected_family),
                "provider_ctx": runtime,
            })
        if len(options) > 1:
            result[model_name] = options
    return result


def make_provider_options_loader(cfg, cli_name, default_provider, default_models, *, build_provider_options_map):
    cache = {}

    def _loader(model_name):
        key = str(model_name or "").strip()
        if not key:
            return []
        if key not in cache:
            cache[key] = build_provider_options_map(
                cfg, cli_name, default_provider, default_models, [key]
            ).get(key, [])
        return cache[key]

    return _loader


def apply_runtime_priority_changes(
    cfg,
    pri_changes,
    *,
    canonical_model_family,
    normalize_family_priority_overrides,
    normalize_priority,
):
    changed = False
    if not pri_changes:
        return changed

    for runtime_id, new_priority in pri_changes.items():
        family_name = ""
        actual_runtime_id = runtime_id
        if "||" in str(runtime_id):
            actual_runtime_id, family_name = str(runtime_id).split("||", 1)
            family_name = canonical_model_family(family_name)
        matched = False
        for provider_def in cfg.get("providers", []):
            if provider_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        provider_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    provider_def["family_priority_overrides"] = overrides
                else:
                    provider_def["priority"] = normalize_priority(new_priority)
                changed = True
                matched = True
                break
        if matched:
            continue
        for account_def in cfg.get("accounts", []):
            if account_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        account_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    account_def["family_priority_overrides"] = overrides
                else:
                    account_def["priority"] = normalize_priority(new_priority)
                changed = True
                break
    return changed


def resolve_visible_clis(
    cfg,
    default_provider,
    default_models,
    *,
    cli_names,
    managed_oauth_clis,
    cli_model_family_hints,
    accounts_for_cli,
    check_cli_installed,
    resolve_provider_for_cli,
):
    visible = []

    for cli_name in cli_names:
        if cli_name in managed_oauth_clis:
            if accounts_for_cli(cfg, cli_name):
                visible.append(cli_name)
                continue
            # Antigravity is OAuth-native, so show the tab before account setup
            # when the binary exists and let the TUI connect flow handle setup.
            if cli_name == "agy":
                try:
                    if check_cli_installed(cli_name):
                        visible.append(cli_name)
                        continue
                except Exception:
                    pass
        provider, family_models = resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)
        if provider is None:
            continue
        if cli_name in cli_model_family_hints and not family_models:
            continue
        visible.append(cli_name)

    return visible


def use_tui(stdin, get_terminal_size, *, min_columns=40):
    if not stdin.isatty():
        return False
    try:
        cols = get_terminal_size().columns
        return cols >= min_columns
    except OSError:
        return False


def clean_model_info(model_info):
    if not isinstance(model_info, dict):
        return model_info
    return {key: value for key, value in model_info.items() if key != "provider"}


def uses_native_account_entry(runtime, cli, *, oauth_capable_clis):
    return bool(runtime and runtime.get("auth_mode") == "oauth" and cli in oauth_capable_clis)


def uses_broker_entry(runtime, cli):
    return bool(runtime and runtime.get("runtime_kind") == "broker" and cli == "claude")


def uses_managed_entry(runtime, cli, *, oauth_capable_clis):
    return uses_native_account_entry(runtime, cli, oauth_capable_clis=oauth_capable_clis)


def preset_model_info(preset, *, excluded_keys=frozenset({"cli", "provider", "account", "description", "bridge"})):
    if not isinstance(preset, dict):
        return {}
    return {key: value for key, value in preset.items() if key not in excluded_keys}


def available_broker_profiles_for_cli(_cfg, _cli_name):
    return []


def broker_enabled_by_cli(cfg, cli_names, *, available_broker_profiles_for_cli=available_broker_profiles_for_cli):
    return {
        cli_name: bool(available_broker_profiles_for_cli(cfg, cli_name))
        for cli_name in (cli_names or [])
    }


def select_broker_profile_interactive(
    cfg,
    cli_name,
    *,
    available_broker_profiles_for_cli,
    ensure_rich,
    table_cls,
    prompt_ask,
    console,
):
    profiles = available_broker_profiles_for_cli(cfg, cli_name)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    ensure_rich()
    table = table_cls(title="Broker Experiment", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("设备/工作区", style="yellow")
    table.add_column("Broker", style="blue")
    table.add_column("Remote", style="magenta")
    for idx, profile in enumerate(profiles, 1):
        table.add_row(
            str(idx),
            str(profile.get("id", "")),
            f"{profile.get('device_id', '-')}/{profile.get('workspace_id', '-')}",
            str(profile.get("broker_base_url") or "-"),
            str(profile.get("remote_service_label") or profile.get("remote_service_base_url") or "-"),
        )
    console.print(table)

    while True:
        raw = prompt_ask("选择 broker profile，直接回车取消", default="").strip()
        if not raw:
            return None
        if raw.isdigit():
            picked = int(raw)
            if 1 <= picked <= len(profiles):
                return profiles[picked - 1]
        console.print("[yellow]请输入有效编号[/yellow]")


def launch_broker_experiment_interactive(
    cfg,
    cli_name,
    *,
    select_broker_profile_interactive,
    run_broker_profile_interactive,
    console,
):
    profile = select_broker_profile_interactive(cfg, cli_name)
    if profile is None:
        return False

    console.print(
        f"[cyan]Broker experiment[/cyan] -> {profile['name']} "
        f"[dim]({profile['device_id']}/{profile['workspace_id']})[/dim]"
    )
    console.print("[dim]支持续最近 / 新开 / 切换旧会话；默认直接回车续最近。[/dim]")
    exit_code = run_broker_profile_interactive(cfg, profile["id"])
    if exit_code != 0:
        console.print(f"[red]broker experiment 启动失败，退出码 {exit_code}[/red]")
    return True


def opencode_default_profile_from_config(cfg, *, opencode_profile_selection):
    opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
    return opencode_profile_selection(opencode.get("default_profile") or opencode.get("profile"))


def usage_key(runtime_kind, cli_name, runtime_id):
    return f"{runtime_kind}:{cli_name}:{runtime_id}"


def rename_usage_account(
    old_id,
    new_id,
    new_name,
    cli_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        old_key = usage_key("account", cli_name, old_id)
        entry = sources.pop(old_key, None)
        if entry is None:
            return False
        entry["id"] = new_id
        entry["name"] = new_name
        sources[usage_key("account", cli_name, new_id)] = entry
        return True

    return bool(update_usage_stats(_mutate))


def rename_usage_provider(
    old_id,
    new_id,
    new_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        changed = False
        rewritten = {}
        for key, entry in list(sources.items()):
            if entry.get("runtime_kind") != "provider" or entry.get("id") != old_id:
                continue
            sources.pop(key, None)
            updated = dict(entry)
            updated["id"] = new_id
            updated["name"] = new_name
            cli_name = str(updated.get("cli", "default")).strip() or "default"
            rewritten[usage_key("provider", cli_name, new_id)] = updated
            changed = True
        sources.update(rewritten)
        return changed

    return bool(update_usage_stats(_mutate))


def target_account_home(old_home, new_id, *, accounts_dir, default_account_home):
    expanded = os.path.expanduser(str(old_home or "").strip())
    if not expanded:
        return default_account_home(new_id)
    known_roots = {
        os.path.realpath(accounts_dir),
    }
    parent = os.path.realpath(os.path.dirname(expanded))
    if parent in known_roots:
        return os.path.join(accounts_dir, new_id)
    return os.path.join(os.path.dirname(expanded), new_id)


def migrate_accounts_dirs(
    cfg,
    *,
    target_account_home,
    normalize_account,
    path_exists=os.path.exists,
    makedirs=os.makedirs,
    move,
):
    changed = False
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if not isinstance(item, dict):
            continue
        account = dict(item)
        home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
        target_home = target_account_home(home_dir, account.get("id", "account"))
        if os.path.realpath(home_dir) != os.path.realpath(target_home):
            if path_exists(home_dir) and not path_exists(target_home):
                makedirs(os.path.dirname(target_home), exist_ok=True)
                move(home_dir, target_home)
            account["home_dir"] = target_home
            changed = True
        updated_accounts.append(normalize_account(account))

    return updated_accounts, changed


def provider_looks_openrouter(provider):
    if not isinstance(provider, dict):
        return False
    fields = [
        provider.get("id"),
        provider.get("name"),
        provider.get("provider_profile"),
        provider.get("profile"),
        provider.get("extension"),
        provider.get("base_url"),
        provider.get("openai_base_url"),
        provider.get("default_openai_base_url"),
    ]
    return any("openrouter" in str(item or "").lower() for item in fields)


def openrouter_provider_candidates(
    cfg,
    *,
    provider_looks_openrouter=provider_looks_openrouter,
    resolve_provider_context,
):
    providers = []
    for item in cfg.get("providers", []):
        if not provider_looks_openrouter(item):
            continue
        try:
            providers.append(resolve_provider_context(cfg, item.get("id")))
        except Exception:
            providers.append(item)
    return providers


def parse_openrouter_extension_args(args_rest):
    args = list(args_rest or [])
    action = "status"
    provider_id = ""
    limit = 12
    assume_paid = False
    json_output = False
    if args and not args[0].startswith("-"):
        action = args.pop(0).strip().lower() or "status"
    if args and not args[0].startswith("-"):
        provider_id = args.pop(0).strip()
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {"--limit", "-n"} and idx + 1 < len(args):
            try:
                limit = max(1, int(args[idx + 1]))
            except ValueError:
                limit = 12
            idx += 2
            continue
        if token == "--assume-paid":
            assume_paid = True
        elif token == "--json":
            json_output = True
        idx += 1
    if action in {"ls", "list"}:
        action = "models"
    if action in {"-h", "--help", "help"}:
        action = "help"
    return {
        "action": action,
        "provider_id": provider_id,
        "limit": limit,
        "assume_paid": assume_paid,
        "json": json_output,
    }


def openrouter_extension_provider(
    cfg,
    provider_id="",
    *,
    provider_map,
    resolve_provider_context,
    provider_looks_openrouter=provider_looks_openrouter,
    openrouter_provider_candidates,
):
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            return None, f"未找到 provider: {provider_id}"
        provider = resolve_provider_context(cfg, provider_id)
        if not provider_looks_openrouter(provider):
            return provider, f"provider '{provider_id}' 不是 OpenRouter 模板，但仍可用其 Key 做探测"
        return provider, ""
    candidates = openrouter_provider_candidates(cfg)
    if candidates:
        return candidates[0], ""
    return None, ""


def handle_openrouter_extension_config(
    cfg,
    args_rest,
    *,
    parse_openrouter_extension_args,
    display_openrouter_extension_help,
    quick_connect_gateway,
    openrouter_extension_provider,
    openrouter_api_key_from_env,
    probe_openrouter_extension,
    display_openrouter_extension_summary,
    console,
):
    parsed = parse_openrouter_extension_args(args_rest)
    action = parsed["action"]
    if action == "help":
        display_openrouter_extension_help()
        return
    if action in {"add", "enable"}:
        quick_connect_gateway(cfg, preset_id="openrouter")
        return

    provider, warning = openrouter_extension_provider(cfg, parsed["provider_id"])
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    api_key = ""
    provider_label = ""
    if provider:
        provider_label = f"{provider.get('name') or provider.get('id')} ({provider.get('id')})"
        api_key = str(provider.get("api_key") or "").strip()
    if not api_key:
        api_key = openrouter_api_key_from_env()
        if api_key and not provider_label:
            provider_label = "OPENROUTER_API_KEY"
    summary = probe_openrouter_extension(
        api_key,
        assume_paid=bool(parsed["assume_paid"]),
    )
    if parsed["json"]:
        console.print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    display_openrouter_extension_summary(
        summary,
        provider_label=provider_label,
        limit=int(parsed["limit"]),
        show_models=action == "models",
    )


def parse_usage_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def usage_recency_score(value, now=None, half_life_days=14, *, parse_usage_timestamp=parse_usage_timestamp):
    parsed = parse_usage_timestamp(value)
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (current - parsed).total_seconds()) / 86400.0
    return 0.5 ** (age_days / float(half_life_days))


def sort_family_entries_for_tui(families, preferred_family="", now=None, *, usage_recency_score=usage_recency_score):
    def _key(item):
        family = str(item.get("family") or "") if isinstance(item, dict) else ""
        last_at = str(item.get("last_used_at") or "").strip() if isinstance(item, dict) else ""
        recency = usage_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        preferred_rank = 0 if family == str(preferred_family or "").strip() else 1
        return (-has_recent, -recency, preferred_rank, family.lower())

    return sorted(list(families or []), key=_key)


def family_is_cold_for_tui(
    family_name,
    total_use,
    last_used_at="",
    *,
    preferred_family="",
    known_model_family_names,
    cold_max_use_count,
    cold_idle_days,
    parse_usage_timestamp=parse_usage_timestamp,
    now=None,
):
    if str(family_name or "").strip() == str(preferred_family or "").strip():
        return False
    if str(family_name or "").strip() in known_model_family_names:
        return False
    if int(total_use or 0) > cold_max_use_count:
        return False
    parsed = parse_usage_timestamp(last_used_at)
    if parsed is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return parsed < (current - timedelta(days=cold_idle_days))


def build_model_families_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    provider_label,
    mms_model_visible,
    infer_model_family,
    load_usage_stats,
    provider_supports_model_for_cli,
    role_weights,
    default_provider_id,
):
    """Aggregate provider models by family and attach the best runtime provider."""
    model_best = {}
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue

        models = provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue

        role = normalize_role(provider.get("role", "auto"))
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)

        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            priority = runtime_priority_for_model(provider, normalized)
            score = (role_weights.get(role, 1), -priority)
            existing = model_best.get(normalized)
            if existing is None or score < existing[0]:
                model_best[normalized] = (
                    score,
                    runtime_with_priority(provider, model_name=normalized),
                    provider_name,
                    provider_id,
                )

    use_counts = {}
    last_used_at_by_model = {}
    stats = load_usage_stats()
    for source in stats.get("sources", {}).values():
        if str(source.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        used_at = str(source.get("last_used_at") or "").strip()
        model_last_used_at = source.get("model_last_used_at")
        if not isinstance(model_last_used_at, dict):
            model_last_used_at = {}
        for model_name, count in source.get("models", {}).items():
            use_counts[model_name] = use_counts.get(model_name, 0) + count
            model_used_at = str(model_last_used_at.get(model_name) or "").strip()
            if model_used_at and model_used_at > last_used_at_by_model.get(model_name, ""):
                last_used_at_by_model[model_name] = model_used_at
        last_model = str(source.get("last_model") or "").strip()
        if (
            last_model
            and used_at
            and last_model not in model_last_used_at
            and used_at > last_used_at_by_model.get(last_model, "")
        ):
            last_used_at_by_model[last_model] = used_at

    family_map = {}
    family_order = []

    for model_name, (_, provider_ctx, provider_name, provider_id) in model_best.items():
        if not mms_model_visible(model_name):
            continue
        family, _ = infer_model_family(model_name)
        if family not in family_map:
            family_map[family] = []
            family_order.append(family)
        family_map[family].append({
            "model": model_name,
            "family": family,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "provider_ctx": provider_ctx,
            "use_count": use_counts.get(model_name, 0),
            "last_used_at": last_used_at_by_model.get(model_name, ""),
        })

    return [{"family": family, "models": family_map[family]} for family in family_order]


def resolve_best_provider(
    cfg,
    model_name,
    default_provider,
    default_models,
    *,
    cli_name=None,
    protocol=None,
    provider_candidates,
    provider_supports_model_for_cli,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    provider_label,
    runtime_with_priority,
    role_weights,
):
    model_lower = str(model_name or "").strip().lower()
    if not model_lower:
        return None, None

    scored = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if cli_name and not provider_supports_model_for_cli(provider, cli_name, model_name):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue
        if protocol:
            protocols = provider.get("protocols", [])
            if protocol not in protocols:
                continue

        models = provider_effective_models(provider, cached_models, cfg)
        model_names_lower = [str(item or "").strip().lower() for item in models]
        if model_lower not in model_names_lower:
            continue

        role = normalize_role(provider.get("role", "auto"))
        priority = runtime_priority_for_model(provider, model_name)
        scored.append((role_weights.get(role, 1), -priority, provider, provider_label(provider)))

    if not scored:
        return None, None

    scored.sort(key=lambda item: (item[0], item[1]))
    return runtime_with_priority(scored[0][2], model_name=model_name), scored[0][3]


def provider_options_for_model(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_info=None,
    *,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    probe_debug_logger,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_models_for_cli,
    provider_supports_model_for_cli,
    provider_supports_cli_name,
    runtime_with_priority,
    runtime_choice_label,
    provider_label,
    runtime_priority_for_family,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    probe_debug_logger.info("=== _provider_options_for_model(cli=%s, selected_model=%s) ===", cli_name, selected_model)
    options = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        provider_id = provider.get("id", "?")
        if not provider.get("enabled", True):
            probe_debug_logger.debug("  %s: SKIP (disabled)", provider_id)
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            probe_debug_logger.debug(
                "  %s: SKIP (no configured base_url=%s or api_key=%s)",
                provider_id,
                provider_has_configured_base_url(provider),
                bool(provider.get("api_key")),
            )
            continue

        models = cached_models
        if models is None:
            probe_debug_logger.debug("  %s: cached_models=None, schedule async refresh", provider_id)
            models = provider_effective_models(provider, None, cfg)
        else:
            probe_debug_logger.debug("  %s: cached_models=%s (len=%d)", provider_id, type(cached_models).__name__, len(cached_models))
        models = provider_effective_models(provider, models, cfg)
        cli_models = provider_models_for_cli(cli_name, models)

        if selected_model:
            if not provider_supports_model_for_cli(provider, cli_name, selected_model):
                probe_debug_logger.info("  %s: SKIP (cli/model incompatible for %s -> %s)", provider_id, cli_name, selected_model)
                continue
            if selected_model not in models:
                probe_debug_logger.info("  %s: SKIP (model '%s' not in %s)", provider_id, selected_model, models[:5])
                continue
            option_models = [selected_model]
        else:
            if not provider_supports_cli_name(provider, cli_name):
                probe_debug_logger.debug("  %s: SKIP (cli not supported)", provider_id)
                continue
            option_models = cli_models

        if not option_models:
            probe_debug_logger.info("  %s: SKIP (no option models for cli=%s)", provider_id, cli_name)
            continue

        probe_debug_logger.info("  %s: ADDED (option_models=%s)", provider_id, option_models)
        options.append({
            "kind": "provider",
            "id": provider.get("id"),
            "runtime": runtime_with_priority(provider, model_name=selected_model, family_name=selected_family),
            "models": option_models,
            "label": runtime_choice_label(provider),
            "title": provider_label(provider),
            "desc": "网关",
            "icon": "🌐",
            "priority": (
                runtime_priority_for_family(provider, selected_family)
                if selected_family
                else provider.get("priority", default_priority)
            ),
            "priority_family": selected_family,
            "is_default": provider.get("id") == default_provider.get("id"),
            "launch_cli": cli_name,
        })
    return options


def account_options_for_model(
    cfg,
    cli_name,
    default_models,
    model_info=None,
    *,
    allow_selected_model=False,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    oauth_capable_clis,
    model_matches_account_cli,
    resolve_account_context,
    runtime_with_priority,
    runtime_choice_label,
    account_label,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    options = []
    defaults = cfg.get("account", {}).get("defaults", {})

    for account_def in cfg.get("accounts", []):
        if not isinstance(account_def, dict) or not account_def.get("enabled", True):
            continue
        account_cli = account_def.get("cli")
        if account_cli not in oauth_capable_clis:
            continue
        bridgeable_to_claude = False
        if account_cli != cli_name and not bridgeable_to_claude:
            continue
        if selected_model and not allow_selected_model and not bridgeable_to_claude:
            continue
        if selected_model and not model_matches_account_cli(account_cli, selected_model):
            continue
        runtime = resolve_account_context(cfg, account_id=account_def["id"], cli_name=account_cli)
        launch_cli = account_cli
        desc = "官方"
        if bridgeable_to_claude:
            bridged = dict(runtime)
            bridged["auth_mode"] = "oauth_bridge"
            bridged["bridge_source_cli"] = account_cli
            bridged["bridge_target_cli"] = "claude"
            bridged["bridge_model"] = selected_model
            bridged["bridge_account_id"] = runtime.get("id")
            runtime = bridged
            launch_cli = "claude"
            desc = "官方桥接"
        runtime = runtime_with_priority(runtime, model_name=selected_model, family_name=selected_family)
        options.append({
            "kind": "account",
            "id": runtime.get("id"),
            "runtime": runtime,
            "models": [selected_model] if selected_model else list(default_models or []),
            "label": runtime_choice_label(runtime),
            "title": account_label(runtime),
            "desc": desc,
            "icon": "🔑",
            "priority": runtime.get("priority", default_priority),
            "priority_family": selected_family,
            "is_default": runtime.get("id") == defaults.get(account_cli),
            "launch_cli": launch_cli,
        })
    return options


def resolve_provider_for_cli(cfg, cli_name, default_provider, default_models, *, provider_options_for_model, cli_model_family_hints):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models)
    for option in options:
        runtime = option["runtime"]
        models = option["models"]
        if cli_name not in cli_model_family_hints:
            return runtime, models
        if models:
            return runtime, models
    return None, []


def resolve_launch_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
    managed_oauth_clis,
    resolve_account_context,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    if cli_name in managed_oauth_clis:
        account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        if account_id and account is not None:
            return account, list(default_models or [])
        if account is not None and account.get("enabled", True):
            return account, list(default_models or [])
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_provider_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_source_default_index(options, preferred_cli):
    if not options:
        return 0
    for idx, option in enumerate(options):
        if option.get("kind") == "provider" and option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli:
            return idx
    for idx, option in enumerate(options):
        if option.get("is_default"):
            return idx
    return 0


def runtime_choice_label(runtime, *, account_label, provider_label):
    if runtime.get("auth_mode") == "broker_profile":
        return f"Broker / {runtime.get('name', runtime.get('id', 'broker'))}"
    if runtime.get("auth_mode") == "oauth_bridge":
        return f"官方桥接 / {account_label(runtime)}"
    if runtime.get("auth_mode") == "oauth":
        return f"官方 / {account_label(runtime)}"
    return f"网关 / {provider_label(runtime)}"


def list_runtime_sources(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    model_info=None,
    allow_selected_model_accounts=False,
    provider_options_for_model,
    account_options_for_model,
    broker_options_for_cli,
    resolve_source_default_index=resolve_source_default_index,
    default_priority,
):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=model_info)
    options.extend(
        account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info=model_info,
            allow_selected_model=allow_selected_model_accounts,
        )
    )
    options.extend(broker_options_for_cli(cfg, cli_name, model_info=model_info))
    options.sort(key=lambda item: (
        -int(item.get("priority", default_priority) or default_priority),
        0 if item.get("launch_cli") == cli_name else 1,
        0 if item["kind"] == "provider" else 1 if item["kind"] == "account" else 2,
        item.get("title", ""),
    ))
    default_choice = resolve_source_default_index(options, cli_name)
    return options, default_choice


def trace_runtime_provider_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("runtime_kind") == "provider" or runtime.get("auth_mode") == "api_key":
        return str(runtime.get("id", "")).strip()
    return ""


def trace_runtime_account_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") == "oauth_bridge":
        return str(runtime.get("bridge_account_id") or runtime.get("id") or "").strip()
    if runtime.get("auth_mode") == "oauth":
        return str(runtime.get("id") or runtime.get("account_id") or "").strip()
    return str(runtime.get("account_id") or "").strip()


def trace_runtime_bridge(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") != "oauth_bridge":
        return ""
    return str(runtime.get("bridge_url") or runtime.get("base_url") or "").strip()


def runtime_source_kind_label(runtime):
    if not runtime:
        return "网关"
    if runtime.get("runtime_kind") == "opencode_profile":
        return "OpenCode"
    auth_mode = runtime.get("auth_mode")
    if auth_mode == "broker_profile" or runtime.get("runtime_kind") == "broker":
        return "Broker"
    if auth_mode == "oauth_bridge":
        return "官方桥接"
    if auth_mode == "oauth":
        return "官方"
    return "网关"


def trace_runtime_choice(
    source,
    runtime,
    *,
    launch_cli=None,
    choice=None,
    trace_record,
    trace_runtime_provider_id=trace_runtime_provider_id,
    trace_runtime_account_id=trace_runtime_account_id,
    trace_runtime_bridge=trace_runtime_bridge,
):
    payload = {
        "cli": launch_cli,
        "provider": trace_runtime_provider_id(runtime),
        "account": trace_runtime_account_id(runtime),
        "bridge": trace_runtime_bridge(runtime),
        "runtime": runtime.get("auth_mode") if isinstance(runtime, dict) else None,
        "choice": choice,
    }
    trace_record(source, **payload)


def http_status_is_success(value):
    try:
        status_code = int(str(value or "").strip())
    except (TypeError, ValueError):
        return False
    return 200 <= status_code < 300


def mask_key(value):
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def set_nested(target, parts, value):
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def get_nested(target, parts):
    current = target
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def unset_nested(target, parts):
    current = target
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current.pop(parts[-1], None)
    return True


def coerce_config_value(key_path, raw_value, *, validate_user_role, normalize_language, normalize_positive_seconds):
    if key_path == "user.role":
        return validate_user_role(raw_value)
    if key_path == "ui.language":
        lang = normalize_language(raw_value)
        if not lang:
            raise ValueError("ui.language 只支持 zh 或 en")
        return lang
    if key_path == "provider.default":
        return str(raw_value).strip()
    if key_path in {"cache.probe_async_refresh_after_sec", "cache.probe_async_min_interval_sec"}:
        return normalize_positive_seconds(raw_value, 1)
    if key_path.startswith("provider.") and key_path.endswith(".enabled"):
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    return raw_value


def validate_config(
    cfg,
    *,
    default_provider_protocols,
    cli_names,
    legacy_provider_cli_aliases,
    default_priority,
    oauth_capable_clis,
    mode_all,
    mode_recommended,
    canonical_model_family,
    normalize_priority,
    normalize_claude_1m_mode,
    normalize_user_role,
):
    errors = []

    def _validate_family_priority_overrides(value, label):
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(f"{label} 的 family_priority_overrides 必须是对象")
            return
        for family_name, priority in value.items():
            canonical_family = canonical_model_family(family_name)
            if not canonical_family:
                errors.append(f"{label} 的 family_priority_overrides 存在不支持的 family: {family_name}")
                continue
            if normalize_priority(priority) != priority:
                errors.append(f"{label} 的 family_priority_overrides.{canonical_family} 必须是正整数")

    cache_cfg = cfg.get("cache", {})
    if cache_cfg and not isinstance(cache_cfg, dict):
        errors.append("cache 必须是对象")
    elif isinstance(cache_cfg, dict):
        for key in ("probe_async_refresh_after_sec", "probe_async_min_interval_sec"):
            value = cache_cfg.get(key)
            if value is None:
                continue
            try:
                if int(value) <= 0:
                    errors.append(f"{key} 必须是正整数")
            except (TypeError, ValueError):
                errors.append(f"{key} 必须是正整数")
    providers = cfg.get("providers", [])
    if not isinstance(providers, list) or not providers:
        errors.append("providers 不能为空")
    else:
        seen_ids = set()
        for item in providers:
            if not isinstance(item, dict):
                errors.append("providers 中存在非对象条目")
                continue
            provider_id = str(item.get("id", "")).strip()
            if not provider_id:
                errors.append("存在缺少 id 的模型源")
                continue
            if provider_id in seen_ids:
                errors.append(f"模型源 ID 重复: {provider_id}")
            seen_ids.add(provider_id)

            protocols = item.get("protocols", [])
            if isinstance(protocols, str):
                protocols = [protocols]
            invalid_protocols = [value for value in protocols if value not in default_provider_protocols]
            if invalid_protocols:
                errors.append(f"模型源 {provider_id} 存在不支持的协议: {', '.join(invalid_protocols)}")

            supported_clis = item.get("supported_clis", [])
            if isinstance(supported_clis, str):
                supported_clis = [supported_clis]
            invalid_clis = [
                value for value in supported_clis
                if value not in cli_names and value not in legacy_provider_cli_aliases
            ]
            if invalid_clis:
                errors.append(f"模型源 {provider_id} 存在不支持的 CLI: {', '.join(invalid_clis)}")
            if normalize_priority(item.get("priority", default_priority)) != item.get("priority", default_priority):
                errors.append(f"模型源 {provider_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"模型源 {provider_id}",
            )
            if normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"模型源 {provider_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    default_id = cfg.get("provider", {}).get("default")
    provider_ids = {item.get("id") for item in providers if isinstance(item, dict)}
    if default_id and default_id not in provider_ids:
        errors.append(f"默认模型源不存在: {default_id}")

    accounts = cfg.get("accounts", [])
    seen_account_ids = set()
    if not isinstance(accounts, list):
        errors.append("accounts 必须是列表")
    else:
        for item in accounts:
            if not isinstance(item, dict):
                errors.append("accounts 中存在非对象条目")
                continue
            account_id = str(item.get("id", "")).strip()
            if not account_id:
                errors.append("存在缺少 id 的账号档案")
                continue
            if account_id in seen_account_ids:
                errors.append(f"账号档案 ID 重复: {account_id}")
            seen_account_ids.add(account_id)
            cli_name = str(item.get("cli", "")).strip()
            if cli_name not in oauth_capable_clis:
                errors.append(f"账号档案 {account_id} 绑定了不支持的 CLI: {cli_name}")
            auth_mode = str(item.get("auth_mode", "oauth")).strip()
            if auth_mode != "oauth":
                errors.append(f"账号档案 {account_id} 目前只支持 oauth 模式")
            if not str(item.get("home_dir", "")).strip():
                errors.append(f"账号档案 {account_id} 缺少 home_dir")
            if normalize_priority(item.get("priority", default_priority)) != item.get("priority", default_priority):
                errors.append(f"账号档案 {account_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"账号档案 {account_id}",
            )
            if normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"账号档案 {account_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    account_defaults = cfg.get("account", {}).get("defaults", {})
    if isinstance(account_defaults, dict):
        for cli_name, account_id in account_defaults.items():
            if cli_name not in oauth_capable_clis:
                errors.append(f"存在不支持的默认账号 CLI: {cli_name}")
            elif account_id not in seen_account_ids:
                errors.append(f"{cli_name} 的默认账号不存在: {account_id}")

    role = cfg.get("user", {}).get("role", mode_all)
    if normalize_user_role(role) not in {mode_all, mode_recommended}:
        errors.append(f"不支持的模型模式: {role}")

    return errors


def handle_config_get(cfg, args_rest, *, command_name, console):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config get <dot.path>[/red]")
        return
    key_path = args_rest[0]
    value, found = get_nested(cfg, key_path.split("."))
    if not found:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    display = mask_key(str(value)) if "key" in key_path.lower() else str(value)
    console.print(f"[cyan]{key_path}[/cyan] = {display}")


def handle_config_set(
    cfg,
    args_rest,
    *,
    command_name,
    coerce_config_value,
    normalize_config_sections,
    save_config,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config set <dot.path> <value>[/red]")
        return
    key_path = args_rest[0]
    raw_value = args_rest[1]
    new_value = coerce_config_value(key_path, raw_value)
    updated_cfg = dict(cfg)
    set_nested(updated_cfg, key_path.split("."), new_value)
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    display = mask_key(str(new_value)) if "key" in key_path.lower() else str(new_value)
    console.print(f"[green]✓ {key_path} = {display}[/green]")


def handle_config_unset(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_config_sections,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config unset <dot.path>[/red]")
        return
    key_path = args_rest[0]
    updated_cfg = dict(cfg)
    removed = unset_nested(updated_cfg, key_path.split("."))
    if not removed:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已移除 {key_path}[/green]")


def handle_config_validate(cfg, *, validate_config, console):
    errors = validate_config(cfg)
    if errors:
        console.print("[red]配置校验失败:[/red]")
        for item in errors:
            console.print(f"  - {item}")
        sys.exit(1)
    console.print("[green]✓ 配置校验通过[/green]")


def handle_config(
    cfg,
    args_rest,
    *,
    preferences_doc_path,
    preference_paths,
    display_config,
    display_config_help,
    handle_config_migrate,
    handle_config_file,
    handle_config_validate,
    display_preferences_help,
    display_preferences_path,
    display_preferences_example,
    run_config_web,
    command_name,
    config_write_target_path,
    display_human_gate_help,
    handle_config_get,
    handle_config_set,
    handle_config_unset,
    run_connect_wizard,
    handle_openrouter_extension_config,
    display_adapter_registry,
    display_providers,
    handle_provider_default_config,
    handle_provider_add_config,
    handle_provider_edit_config,
    handle_provider_rename_config,
    handle_provider_remove_config,
    handle_provider_credentials_config,
    display_accounts,
    handle_account_default_config,
    handle_account_add_config,
    handle_account_edit_config,
    handle_account_remove_config,
    handle_account_rename_config,
    handle_account_status_config,
    handle_account_login_config,
    display_usage_stats,
    resolve_provider_context,
    setup_provider_credentials,
    handle_api_config,
    console,
):
    if not args_rest:
        display_config(cfg)
        return

    key_path = args_rest[0]
    if key_path in {"-h", "--help", "help"}:
        display_config_help()
        return
    if key_path == "migrate":
        handle_config_migrate()
        return
    if key_path == "file":
        handle_config_file()
        return
    if key_path == "validate":
        handle_config_validate(cfg)
        return
    if key_path in {"preferences", "preferences.help", "preference.help"}:
        display_preferences_help()
        return
    if key_path in {"preferences.path", "preference.path"}:
        display_preferences_path()
        return
    if key_path in {"preferences.example", "preference.example"}:
        display_preferences_example()
        return
    if key_path in {"preferences.doc", "preference.doc"}:
        console.print(preferences_doc_path)
        return
    if key_path in {"web", "webui", "setup.web", "setup-web"}:
        raise SystemExit(run_config_web(
            cfg,
            args_rest[1:],
            command_name=command_name,
            config_path=config_write_target_path(),
            preferences_path=preference_paths[0],
        ))
    if key_path in {"gates", "human-gate", "humangate", "human-gates"}:
        display_human_gate_help()
        return
    if key_path == "get":
        handle_config_get(cfg, args_rest[1:])
        return
    if key_path == "set":
        handle_config_set(cfg, args_rest[1:])
        return
    if key_path == "unset":
        handle_config_unset(cfg, args_rest[1:])
        return
    if key_path == "connect":
        run_connect_wizard(cfg)
        return
    if key_path in {"extension.openrouter", "openrouter"}:
        handle_openrouter_extension_config(cfg, args_rest[1:])
        return
    if key_path in {"adapter.registry", "source.registry", "source.top10"}:
        display_adapter_registry()
        return
    if key_path == "provider.list":
        display_providers(cfg)
        return
    if key_path == "provider.default":
        handle_provider_default_config(cfg, args_rest[1:])
        return
    if key_path == "provider.add":
        handle_provider_add_config(cfg, args_rest[1:])
        return
    if key_path == "provider.edit":
        handle_provider_edit_config(cfg, args_rest[1:])
        return
    if key_path == "provider.rename":
        handle_provider_rename_config(cfg, args_rest[1:])
        return
    if key_path == "provider.remove":
        handle_provider_remove_config(cfg, args_rest[1:])
        return
    if key_path == "provider.credentials":
        handle_provider_credentials_config(cfg, args_rest[1:])
        return
    if key_path == "account.list":
        display_accounts(cfg)
        return
    if key_path == "account.default":
        handle_account_default_config(cfg, args_rest[1:])
        return
    if key_path == "account.add":
        handle_account_add_config(cfg, args_rest[1:])
        return
    if key_path == "account.edit":
        handle_account_edit_config(cfg, args_rest[1:])
        return
    if key_path == "account.remove":
        handle_account_remove_config(cfg, args_rest[1:])
        return
    if key_path == "account.rename":
        handle_account_rename_config(cfg, args_rest[1:])
        return
    if key_path == "account.status":
        handle_account_status_config(cfg, args_rest[1:])
        return
    if key_path == "account.login":
        handle_account_login_config(cfg, args_rest[1:])
        return
    if key_path in {"usage", "stats"}:
        display_usage_stats()
        return
    if key_path in ("api.setup", "api.edit"):
        provider = resolve_provider_context(cfg)
        setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        )
        return

    if key_path.startswith("api."):
        handle_api_config(key_path, args_rest[1:])
        return

    if len(args_rest) == 1:
        handle_config_get(cfg, [key_path])
        return
    if len(args_rest) == 2:
        handle_config_set(cfg, [key_path, args_rest[1]])
        return


def handle_config_file(*, config_path, console):
    console.print(config_path)


def handle_api_config(
    key_path,
    args_rest,
    *,
    load_api_credentials,
    save_api_credentials,
    credentials_path,
    mask_key,
    console,
):
    base_url, api_key, _ = load_api_credentials()

    if key_path == "api.base_url":
        if not args_rest:
            display = base_url or "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            return
        save_api_credentials(args_rest[0].rstrip("/"), api_key)
        console.print(f"[green]✓ {key_path} = {args_rest[0].rstrip('/')}[/green]")
        return

    if key_path == "api.api_key":
        if not args_rest:
            display = mask_key(api_key) if api_key else "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            console.print(f"[dim]真实值保存在 {credentials_path}，这里始终只显示掩码。[/dim]")
            return
        save_api_credentials(base_url, args_rest[0])
        console.print(f"[green]✓ {key_path} = {mask_key(args_rest[0])}[/green]")
        console.print(f"[dim]真实值已保存到 {credentials_path}，这里显示为掩码。[/dim]")
        return

    console.print(f"[red]配置项 '{key_path}' 不存在[/red]")


def handle_config_migrate(
    *,
    backup_config_tree,
    load_config,
    migrate_accounts_dirs,
    save_config,
    config_path,
    active_credentials_path,
    active_usage_path,
    console,
):
    backup_dir = backup_config_tree("config-migrate")
    cfg = load_config()
    if cfg is None:
        console.print("[yellow]未找到可迁移配置，当前无需执行 migrate[/yellow]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts, moved_accounts = migrate_accounts_dirs(cfg)
    if moved_accounts:
        updated_cfg["accounts"] = updated_accounts
    save_config(updated_cfg)

    console.print("[green]✓ 配置迁移完成[/green]")
    console.print(f"[dim]config: {config_path}[/dim]")
    console.print(f"[dim]credentials: {active_credentials_path()}[/dim]")
    console.print(f"[dim]usage: {active_usage_path()}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def handle_provider_default_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    save_config,
    refresh_routes_export_for_hive,
    console,
):
    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    if not args_rest:
        console.print(f"[cyan]provider.default[/cyan] = {default_id}")
        console.print("[dim]当前默认模型源[/dim]")
        return

    requested_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if requested_id not in providers:
        console.print(f"[red]未找到 provider: {requested_id}[/red]")
        console.print(f"[dim]可用 provider: {', '.join(providers.keys())}[/dim]")
        return

    cfg.setdefault("provider", {})
    cfg["provider"]["default"] = requested_id
    save_config(cfg)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ provider.default = {requested_id}[/green]")
    console.print("[dim]默认模型源已更新[/dim]")


def handle_provider_add_config(
    cfg,
    args_rest,
    *,
    quick_connect_gateway,
):
    preset_id = args_rest[0].strip() if args_rest else None
    quick_connect_gateway(cfg, preset_id=preset_id)


def update_provider_model_overrides(
    cfg,
    provider_id,
    *,
    extra_models=None,
    hidden_models=None,
    models_endpoint=None,
    normalize_model_id_list=normalize_model_id_list,
    normalize_models_endpoint=normalize_models_endpoint,
    normalize_provider,
    save_config,
    invalidate_probe_cache,
    load_config,
):
    updated_cfg = dict(cfg)
    providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != provider_id:
            providers.append(item)
            continue
        updated = dict(item)
        if extra_models is not None:
            updated["extra_models"] = normalize_model_id_list(extra_models)
        if hidden_models is not None:
            updated["hidden_models"] = normalize_model_id_list(hidden_models)
        if models_endpoint is not None:
            updated["models_endpoint"] = normalize_models_endpoint(models_endpoint)
        providers.append(normalize_provider(updated))
    updated_cfg["providers"] = providers
    save_config(updated_cfg)
    invalidate_probe_cache(provider_id)
    return load_config()


def handle_provider_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    provider_map,
    prompt_provider_metadata,
    upsert_provider,
    save_config,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config provider.edit <id>[/red]")
        return
    provider_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    provider = prompt_provider_metadata(existing=providers[provider_id], preset_id=provider_id)
    updated_cfg = upsert_provider(cfg, provider)
    save_config(updated_cfg)
    invalidate_probe_cache(provider_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已更新模型源: {provider_id}[/green]")


def handle_provider_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    default_provider_id,
    ensure_interactive_terminal,
    provider_map,
    confirm_ask,
    save_config,
    delete_provider_credentials,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config provider.remove <id>[/red]")
        return
    ensure_interactive_terminal("模型源删除确认")
    provider_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    if len(providers) == 1:
        console.print("[red]至少需要保留一个模型源，无法删除最后一个[/red]")
        return
    if not confirm_ask(f"确认删除模型源 '{provider_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = [
        provider for provider in cfg.get("providers", [])
        if provider.get("id") != provider_id
    ]
    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    if default_id == provider_id:
        updated_cfg["provider"] = {"default": updated_cfg["providers"][0]["id"]}
    save_config(updated_cfg)
    delete_provider_credentials(provider_id)
    invalidate_probe_cache(provider_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已删除模型源: {provider_id}[/green]")


def handle_provider_credentials_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    resolve_provider_context,
    setup_provider_credentials,
    console,
):
    target_id = args_rest[0].strip() if args_rest else cfg.get("provider", {}).get("default", default_provider_id)
    providers = provider_map(cfg)
    if target_id not in providers:
        console.print(f"[red]未找到模型源: {target_id}[/red]")
        return
    provider = resolve_provider_context(cfg, target_id)
    setup_provider_credentials(
        provider,
        provider.get("base_url", ""),
        provider.get("api_key", ""),
        allow_keep=True,
    )


def handle_provider_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_provider_id_input,
    provider_map,
    normalize_provider,
    backup_config_tree,
    save_config,
    rename_usage_provider,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config provider.rename <old_id> <new_id> [new_name][/red]")
        return
    old_id = args_rest[0].strip()
    new_id = normalize_provider_id_input(args_rest[1].strip())
    providers = provider_map(cfg)
    provider = providers.get(old_id)
    if not provider:
        console.print(f"[red]未找到模型源: {old_id}[/red]")
        return
    if old_id == new_id and len(args_rest) < 3:
        console.print("[yellow]名称和标识都未变化，无需重命名[/yellow]")
        return
    if new_id != old_id and new_id in providers:
        console.print(f"[red]目标模型源标识已存在: {new_id}[/red]")
        return

    new_name = args_rest[2].strip() if len(args_rest) >= 3 else new_id
    backup_dir = backup_config_tree("provider-rename")
    updated_cfg = dict(cfg)
    updated_providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != old_id:
            updated_providers.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_name
        updated_providers.append(normalize_provider(renamed))
    updated_cfg["providers"] = updated_providers

    provider_cfg = dict(cfg.get("provider", {}))
    if provider_cfg.get("default") == old_id:
        provider_cfg["default"] = new_id
    updated_cfg["provider"] = provider_cfg
    save_config(updated_cfg)
    rename_usage_provider(old_id, new_id, new_name)
    invalidate_probe_cache(old_id)
    invalidate_probe_cache(new_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已重命名模型源: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]显示名: {new_name}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def handle_account_default_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    account_map,
    save_config,
    command_name,
    console,
):
    defaults = cfg.get("account", {}).get("defaults", {})
    if not args_rest:
        for cli_name in managed_oauth_clis:
            value = defaults.get(cli_name, "(未设置)")
            console.print(f"[cyan]account.default.{cli_name}[/cyan] = {value}")
        console.print("[dim]Claude OAuth 独立入口已下线，不再支持 account.default.claude。[/dim]")
        return
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config account.default <cli> <account_id>[/red]")
        return
    cli_name, account_id = args_rest[0].strip(), args_rest[1].strip()
    if cli_name in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再支持设置 account.default.claude。[/yellow]")
        return
    if cli_name not in managed_oauth_clis:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        return
    accounts = account_map(cfg)
    account = accounts.get(account_id)
    if not account:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if account.get("cli") != cli_name:
        console.print(f"[red]账号档案 '{account_id}' 绑定的是 {account.get('cli')}，不能设为 {cli_name} 默认账号[/red]")
        return
    cfg.setdefault("account", {}).setdefault("defaults", {})
    cfg["account"]["defaults"][cli_name] = account_id
    save_config(cfg)
    console.print(f"[green]✓ account.default.{cli_name} = {account_id}[/green]")


def handle_account_add_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    quick_connect_official,
    console,
):
    requested_cli = args_rest[0].strip() if args_rest and args_rest[0].strip() else None
    if requested_cli in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再管理 Claude 官方登录。[/yellow]")
        return
    preset_cli = requested_cli if requested_cli in managed_oauth_clis else None
    quick_connect_official(cfg, preset_cli=preset_cli)


def handle_account_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    account_map,
    delegated_oauth_clis,
    prompt_account_metadata,
    ensure_account_config,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.edit <id>[/red]")
        return
    account_id = args_rest[0].strip()
    accounts = account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if accounts[account_id].get("cli") in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再编辑 Claude 官方账号。[/yellow]")
        return
    account = prompt_account_metadata(existing=accounts[account_id], preset_id=account_id)
    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        updated_accounts.append(account if item.get("id") == account_id else item)
    updated_cfg["accounts"] = updated_accounts
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已更新账号档案: {account_id}[/green]")


def handle_account_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    ensure_interactive_terminal,
    account_map,
    confirm_ask,
    ensure_account_config,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.remove <id>[/red]")
        return
    ensure_interactive_terminal("账号档案删除确认")
    account_id = args_rest[0].strip()
    accounts = account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if not confirm_ask(f"确认删除账号档案 '{account_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = [
        item for item in cfg.get("accounts", [])
        if item.get("id") != account_id
    ]
    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in list(defaults.items()):
        if value == account_id:
            defaults.pop(cli_name, None)
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已删除账号档案: {account_id}[/green]")


def handle_account_status_config(
    cfg,
    args_rest,
    *,
    resolve_account_context,
    probe_account_status,
    display_accounts,
    console,
):
    if args_rest:
        account = resolve_account_context(cfg, account_id=args_rest[0].strip())
        status = probe_account_status(account)
        console.print(f"[cyan]{account['id']}[/cyan] = {status['state']}")
        if status.get("summary"):
            console.print(f"[dim]{status['summary']}[/dim]")
        return
    display_accounts(cfg)


def handle_account_login_config(
    cfg,
    args_rest,
    *,
    command_name,
    delegated_oauth_clis,
    resolve_account_context,
    run_account_login,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.login <id>[/red]")
        return
    account = resolve_account_context(cfg, account_id=args_rest[0].strip())
    if account and account.get("cli") in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    run_account_login(account)


def handle_account_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_account_id,
    account_map,
    backup_config_tree,
    target_account_home,
    path_exists,
    makedirs,
    move,
    normalize_account,
    ensure_account_config,
    save_config,
    rename_usage_account,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config account.rename <old_id> <new_id>[/red]")
        return
    old_id = args_rest[0].strip()
    new_id = normalize_account_id(args_rest[1].strip())
    accounts = account_map(cfg)
    account = accounts.get(old_id)
    if not account:
        console.print(f"[red]未找到账号档案: {old_id}[/red]")
        return
    if old_id == new_id:
        console.print("[yellow]新旧文件夹名相同，无需重命名[/yellow]")
        return
    if new_id in accounts:
        console.print(f"[red]目标文件夹名已存在: {new_id}[/red]")
        return

    backup_dir = backup_config_tree("account-rename")
    old_home = os.path.expanduser(str(account.get("home_dir", "")).strip())
    new_home = target_account_home(old_home, new_id)
    if path_exists(new_home):
        console.print(f"[red]目标目录已存在: {new_home}[/red]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if item.get("id") != old_id:
            updated_accounts.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_id
        renamed["home_dir"] = new_home
        updated_accounts.append(normalize_account(renamed))
    updated_cfg["accounts"] = updated_accounts

    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in defaults.items():
        if value == old_id:
            defaults[cli_name] = new_id
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = ensure_account_config(updated_cfg)

    if path_exists(old_home):
        makedirs(os.path.dirname(new_home), exist_ok=True)
        move(old_home, new_home)

    save_config(updated_cfg)
    rename_usage_account(old_id, new_id, new_id, account.get("cli", ""))
    console.print(f"[green]✓ 已重命名账号档案: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]新目录: {new_home}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def session_status_label(item):
    session_id = str(item.get("session_id") or "").strip()
    if not session_id:
        return "active"
    if item.get("stale_cleanup"):
        return "stale-finalized"
    if item.get("exit_code") is None:
        return "active"
    return f"exit:{item.get('exit_code')}"


def session_display_id(item):
    session_id = str(item.get("session_id") or "").strip()
    if session_id:
        return session_id
    pid = item.get("pid")
    return f"pid-{pid}" if pid is not None else "-"


def handle_session_ls(cli_name, *, list_indexed_sessions, table_cls, console):
    rows = list_indexed_sessions(cli_name=cli_name)
    if not rows:
        console.print(f"[yellow]当前没有已索引的 {cli_name} session[/yellow]")
        return

    table = table_cls(title=f"{cli_name} session 列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("项目", style="green")
    table.add_column("来源", style="magenta")
    table.add_column("状态", style="yellow")
    table.add_column("最近活动", style="blue")
    for item in rows:
        project_name = os.path.basename(str(item.get("project_path", "")).rstrip(os.sep)) or "-"
        source_label = str(item.get("account_id") or item.get("runtime_kind") or "-")
        last_active = str(item.get("last_active_at") or item.get("started_at") or "-")
        table.add_row(
            session_display_id(item),
            project_name,
            source_label,
            session_status_label(item),
            last_active,
        )
    console.print(table)


def handle_session_info(session_id, cli_name, *, get_indexed_session, table_cls, console):
    item = get_indexed_session(session_id, cli_name=cli_name)
    if item is None:
        console.print(f"[red]找不到 session: {session_id}[/red]")
        sys.exit(1)

    table = table_cls(title=f"{cli_name} session 详情")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    ordered_keys = [
        "session_id",
        "project_key",
        "project_path",
        "account_id",
        "runtime_kind",
        "pid",
        "cwd",
        "started_at",
        "last_active_at",
        "exit_code",
        "stale_cleanup",
        "slot_home",
        "_path",
    ]
    seen = set()
    for key in ordered_keys:
        seen.add(key)
        table.add_row(key, str(item.get(key, "")))
    for key in sorted(item):
        if key in seen:
            continue
        table.add_row(str(key), str(item.get(key, "")))
    console.print(table)


def session_gateway_roots(cli_name, *, real_home):
    gateway_names = []
    if cli_name in {"all", "claude"}:
        gateway_names.append(("claude", "claude-gateway"))
    if cli_name in {"all", "codex"}:
        gateway_names.append(("codex", "codex-gateway"))
    if cli_name in {"all", "opencode"}:
        gateway_names.append(("opencode", "opencode-gateway"))
    return [
        (cli, os.path.join(real_home, ".config", "mms", gateway_name, "s"))
        for cli, gateway_name in gateway_names
    ]


def session_dir_size_bytes(path):
    total = 0
    for root, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                if os.path.islink(file_path):
                    continue
                total += os.path.getsize(file_path)
            except OSError:
                continue
    return total


def format_bytes(size):
    value = float(max(0, int(size or 0)))
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def list_stale_gateway_sessions(
    cli_name,
    *,
    session_gateway_roots,
    session_home_is_active,
    session_dir_size_bytes,
):
    rows = []
    for cli, root in session_gateway_roots(cli_name):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            session_home = os.path.join(root, name)
            if not os.path.isdir(session_home) or os.path.islink(session_home):
                continue
            if session_home_is_active(session_home):
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(session_home)).isoformat(timespec="seconds")
            except OSError:
                mtime = "-"
            rows.append(
                {
                    "cli": cli,
                    "name": name,
                    "path": session_home,
                    "size": session_dir_size_bytes(session_home),
                    "mtime": mtime,
                }
            )
    rows.sort(key=lambda item: (int(item.get("size") or 0), str(item.get("mtime") or "")), reverse=True)
    return rows


def split_cli_prefixed_resume_ref(session_ref):
    ref = str(session_ref or "").strip()
    if ":" not in ref:
        return "", ref
    prefix, rest = ref.split(":", 1)
    prefix = prefix.strip().lower()
    rest = rest.strip()
    if prefix in {"codex", "claude"} and rest:
        return prefix, rest
    return "", ref


def codex_resume_roots(env, *, real_home):
    roots = []

    def add(path):
        normalized = str(path or "").strip()
        if not normalized:
            return
        expanded = os.path.abspath(os.path.expanduser(normalized))
        if expanded not in roots:
            roots.append(expanded)

    for env_name in ("MMS_CODEX_RESUME_WRITEBACK_ROOT", "CODEX_HOME"):
        add(env.get(env_name))
    add(os.path.join(real_home, ".config", "mms", "codex-gateway", ".codex"))
    add(os.path.join(real_home, ".codex"))
    return roots


def iter_codex_index_records(roots):
    seen = set()
    for root in roots:
        path = os.path.join(root, "session_index.jsonl")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    session_id = str(item.get("id") or "").strip()
                    if not session_id or session_id in seen:
                        continue
                    seen.add(session_id)
                    payload = dict(item)
                    payload["_root"] = root
                    yield payload
        except OSError:
            continue


def resolve_codex_resume_ref(session_ref, *, iter_codex_index_records, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    records = list(iter_codex_index_records())
    exact = [item for item in records if str(item.get("id") or "").strip() == ref]
    if exact:
        return str(exact[0]["id"]), exact[0], None
    matches = [item for item in records if str(item.get("id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0], None
    if len(matches) > 1:
        return None, None, f"Codex session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Codex session: {ref}"


def resolve_claude_resume_ref(session_ref, *, list_indexed_sessions, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    sessions = [
        item for item in list_indexed_sessions(cli_name="claude")
        if str(item.get("session_id") or "").strip()
    ]
    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(sessions):
            item = sessions[index - 1]
            return str(item.get("session_id") or "").strip(), item, None
        return None, None, f"找不到第 {index} 条 Claude session"
    exact = [item for item in sessions if str(item.get("session_id") or "").strip() == ref]
    if exact:
        return str(exact[0].get("session_id") or "").strip(), exact[0], None
    matches = [item for item in sessions if str(item.get("session_id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0].get("session_id") or "").strip(), matches[0], None
    if len(matches) > 1:
        return None, None, f"Claude session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Claude session: {ref}"


def resolve_resume_target(
    session_ref,
    cli_hint="auto",
    *,
    split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
):
    prefix_cli, ref = split_cli_prefixed_resume_ref(session_ref)
    cli_hint = prefix_cli or str(cli_hint or "auto").strip().lower()
    if cli_hint not in {"auto", "codex", "claude"}:
        return None, None, None, f"不支持的 CLI: {cli_hint}"
    if cli_hint == "codex":
        session_id, record, error = resolve_codex_resume_ref(ref, allow_passthrough=True)
        return "codex", session_id, record, error
    if cli_hint == "claude":
        session_id, record, error = resolve_claude_resume_ref(ref, allow_passthrough=True)
        return "claude", session_id, record, error

    codex_id, codex_record, codex_error = resolve_codex_resume_ref(ref, allow_passthrough=False)
    claude_id, claude_record, claude_error = resolve_claude_resume_ref(ref)
    if codex_id and not claude_id:
        return "codex", codex_id, codex_record, None
    if claude_id and not codex_id:
        return "claude", claude_id, claude_record, None
    if codex_id and claude_id:
        return None, None, None, f"session id 同时匹配 Codex 和 Claude，请使用 codex:{ref} 或 claude:{ref}"
    uuid_cli = uuid_resume_cli_hint(ref)
    if uuid_cli == "codex":
        return "codex", ref, {"id": ref, "_unindexed": True}, None
    if uuid_cli == "claude":
        return "claude", ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, None, codex_error or claude_error or f"找不到 session: {ref}"


def uuid_resume_cli_hint(session_ref):
    ref = str(session_ref or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ref):
        return ""
    version = ref.split("-", 3)[2][:1]
    if version == "7":
        return "codex"
    if version == "4":
        return "claude"
    return ""


def first_resume_model(cli_models, default_models, recommend=None):
    names = []
    for item in list(cli_models or []) + list(default_models or []):
        name = str(item.get("model") if isinstance(item, dict) else item or "").strip()
        if name and name not in names:
            names.append(name)
    for preferred in recommend or []:
        if preferred in names:
            return preferred
    return names[0] if names else ""


def session_resume_model(session_record):
    if not isinstance(session_record, dict):
        return ""
    for key in ("resume_model", "selected_model", "display_model", "model"):
        value = str(session_record.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_resume_runtime_and_model(
    cfg,
    cli,
    args,
    default_provider,
    default_models,
    session_record,
    *,
    get_scene_usage,
    session_resume_model=session_resume_model,
    resolve_last_used_runtime,
    trace_runtime_choice,
    choose_runtime_source,
    resolve_model_name=resolve_model_name,
    first_resume_model=first_resume_model,
    uses_managed_entry,
    runtime_with_launch_preferences,
):
    requested_model = str(args.model or "").strip()
    if requested_model:
        model_info = {"model": requested_model}
    elif cli == "claude" and session_resume_model(session_record):
        model_info = {"model": session_resume_model(session_record)}
    else:
        last_by_cli, _scene_counts = get_scene_usage()
        last_item = last_by_cli.get(cli)
        last_model_info = last_item.get("model_info") if isinstance(last_item, dict) else None
        model_info = last_model_info if isinstance(last_model_info, dict) else {}

    account_id = str(args.account or "").strip()
    provider_id = str(args.provider or "").strip()
    if cli == "claude" and not account_id and not provider_id and isinstance(session_record, dict):
        source_id = str(session_record.get("account_id") or "").strip()
        runtime_kind = str(session_record.get("runtime_kind") or "").strip()
        if source_id and runtime_kind == "api_key":
            provider_id = source_id
        elif source_id and runtime_kind == "oauth":
            account_id = source_id

    runtime = cli_models = launch_cli_name = None
    if not account_id and not provider_id:
        last_by_cli, _scene_counts = get_scene_usage()
        last_item = last_by_cli.get(cli)
        runtime, cli_models, choice = resolve_last_used_runtime(cfg, cli, last_item, default_models)
        if runtime is not None:
            launch_cli_name = cli
            trace_runtime_choice("runtime resolve", runtime, launch_cli=cli, choice=choice)
    if runtime is None:
        runtime, cli_models, launch_cli_name = choose_runtime_source(
            cfg,
            cli,
            default_provider,
            default_models,
            account_id=account_id or None,
            provider_id=provider_id or None,
            model_info=model_info or None,
            allow_selected_model_accounts=True,
        )

    if not isinstance(model_info, dict) or not resolve_model_name(model_info):
        model_name = first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        model_info = {"model": model_name} if model_name else {}
    if resolve_model_name(model_info) == "official-default" and not uses_managed_entry(runtime or {}, cli):
        model_name = first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        if model_name:
            model_info = {"model": model_name}
    runtime = runtime_with_launch_preferences(cfg, runtime, launch_cli_name or cli)
    return runtime, cli_models or [], launch_cli_name or cli, model_info


def handle_resume_command(
    argv,
    preloaded_command_cfg=None,
    bootstrap_cfg=None,
    lang_override=None,
    *,
    command_name,
    resolve_resume_target,
    load_config,
    setup_wizard,
    resolve_ui_language,
    apply_local_overrides,
    set_language,
    ensure_provider_credentials,
    ensure_models_ready,
    resolve_resume_runtime_and_model,
    launch_with_tracking,
    path_isdir=os.path.isdir,
    chdir=os.chdir,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} resume",
        description="通过 Codex/Claude session id 一键恢复 MMS 托管会话",
    )
    parser.add_argument("session_ref", help="session id、前缀，或 codex:<id> / claude:<id>")
    parser.add_argument("prompt", nargs="*", help="恢复后追加给 CLI 的可选 prompt；若 prompt 以 -- 开头请先写 --")
    parser.add_argument("--cli", choices=["auto", "codex", "claude"], default="auto", help="强制指定恢复目标 CLI")
    parser.add_argument("--provider", help="临时指定 provider")
    parser.add_argument("--account", help="临时指定官方账号档案")
    parser.add_argument("--model", help="临时指定恢复时使用的模型")
    parser.add_argument("--once", action="store_true", help="以一次性会话模式启动底层 CLI")
    args = parser.parse_intermixed_args(argv)

    if args.account and args.provider:
        parser.error("--account 和 --provider 不能同时使用")

    cli, session_id, session_record, error = resolve_resume_target(args.session_ref, args.cli)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    if cli not in {"codex", "claude"} or not session_id:
        console.print(f"[red]无法识别 session: {args.session_ref}[/red]")
        raise SystemExit(1)

    user_cfg = preloaded_command_cfg or bootstrap_cfg or load_config()
    if user_cfg is None:
        user_cfg = setup_wizard(resolve_ui_language(None, lang_override))
    cfg = apply_local_overrides(user_cfg)
    set_language(resolve_ui_language(cfg, lang_override))

    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _cli_models, launch_cli_name, model_info = resolve_resume_runtime_and_model(
        cfg,
        cli,
        args,
        default_provider,
        models_cache,
        session_record,
    )
    if runtime is None:
        console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
        raise SystemExit(1)
    if launch_cli_name != cli:
        console.print(f"[red]resume 只支持原 CLI 恢复，当前解析为 {launch_cli_name}[/red]")
        raise SystemExit(1)
    if cli == "claude":
        project_path = str((session_record or {}).get("project_path") or (session_record or {}).get("cwd") or "").strip()
        if project_path and path_isdir(project_path):
            chdir(project_path)
        extra_args = ["--resume", session_id] + list(args.prompt or [])
    else:
        extra_args = ["resume", session_id] + list(args.prompt or [])

    source = "未写入 MMS index，交给 Codex 原生 resume 校验" if (session_record or {}).get("_unindexed") else "MMS index"
    console.print(f"[cyan]恢复 {cli} session:[/cyan] {session_id}")
    console.print(f"[dim]来源: {source}[/dim]")
    launch_with_tracking(cli, model_info, runtime, once=bool(args.once), extra_args=extra_args)


def handle_session_prune(
    cli_name,
    *,
    apply=False,
    yes=False,
    list_stale_gateway_sessions,
    finalize_claude_slot,
    remove_tree,
    format_bytes,
    table_cls,
    console,
):
    rows = list_stale_gateway_sessions(cli_name)
    if not rows:
        console.print("[green]没有可清理的 stale MMS session[/green]")
        return

    table = table_cls(title="Stale MMS session dry-run" if not apply else "Stale MMS session prune")
    table.add_column("CLI", style="cyan")
    table.add_column("Session", style="green")
    table.add_column("Size", style="yellow")
    table.add_column("Modified", style="blue")
    table.add_column("Path", style="white")
    for item in rows:
        table.add_row(
            str(item["cli"]),
            str(item["name"]),
            format_bytes(item["size"]),
            str(item["mtime"]),
            str(item["path"]),
        )
    console.print(table)

    if not apply:
        console.print(f"[dim]dry-run only：加 --apply --yes 才会删除 {len(rows)} 个 stale session[/dim]")
        return
    if not yes:
        console.print("[red]拒绝删除：需要显式传 --yes[/red]")
        return

    removed = 0
    for item in rows:
        session_home = str(item.get("path") or "")
        root = os.path.dirname(session_home)
        try:
            if os.path.commonpath([os.path.abspath(session_home), os.path.abspath(root)]) != os.path.abspath(root):
                continue
        except ValueError:
            continue
        if item.get("cli") == "claude":
            try:
                finalize_claude_slot(session_home, stale_cleanup=True)
            except Exception:
                pass
        remove_tree(session_home, ignore_errors=True)
        removed += 1
    console.print(f"[green]已删除 {removed} 个 stale MMS session[/green]")


def is_config_help_request(args_rest):
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    return key_path in CONFIG_HELP_TOPICS


def is_help_request(argv):
    if not argv:
        return False
    if argv[0] == "help":
        return True
    if argv[0] == "config" and is_config_help_request(argv[1:]):
        return True
    return any(str(arg).strip() in {"-h", "--help"} for arg in argv)


def is_setup_web_request(argv):
    if not argv:
        return False
    command = str(argv[0] or "").strip()
    if command in {"setup", "setup-web", "web-setup"}:
        return True
    if command != "config" or len(argv) < 2:
        return False
    return str(argv[1] or "").strip() in {"web", "webui", "setup.web", "setup-web"}


def is_session_prune_dry_run(argv):
    if len(argv) < 2:
        return False
    if argv[0] != "session" or argv[1] != "prune":
        return False
    return "--apply" not in argv


def handle_fake_upstream_command(
    argv,
    *,
    command_name,
    set_enabled,
    status_payload,
    tail_log,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} fake-upstream",
        description="开发期 fake upstream：不访问真实上游，并把请求写入日志",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看 fake upstream 状态")
    subparsers.add_parser("on", help="开启 fake upstream")
    subparsers.add_parser("off", help="关闭 fake upstream")
    log_parser = subparsers.add_parser("log", help="查看 fake upstream 日志")
    log_parser.add_argument("--tail", type=int, default=20, help="最后 N 条")

    args = parser.parse_args(argv)

    if args.subcommand == "on":
        set_enabled(True)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已开启[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        console.print(f"[dim]log:   {payload['log_path']}[/dim]")
        return
    if args.subcommand == "off":
        set_enabled(False)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已关闭[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        return
    if args.subcommand == "log":
        rows = tail_log(args.tail)
        if not rows:
            console.print("[yellow]暂无 fake upstream 日志[/yellow]")
            return
        table = table_cls(title="Fake Upstream Log")
        table.add_column("Time", style="cyan")
        table.add_column("Kind", style="green")
        table.add_column("Target", style="magenta")
        table.add_column("Detail", style="white")
        for row in rows:
            target = str(row.get("url") or row.get("host") or "-")
            if str(row.get("kind") or "") == "upstream":
                detail = row.get("request_body_preview") or row.get("path") or "-"
            else:
                detail = (
                    row.get("path")
                    or row.get("request_body_preview")
                    or row.get("body")
                    or row.get("proxy")
                    or row.get("listen")
                    or "-"
                )
            table.add_row(str(row.get("ts") or "-"), str(row.get("kind") or "-"), target, str(detail))
        console.print(table)
        return

    payload = status_payload()
    table = table_cls(title="Fake Upstream")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("enabled", "yes" if payload.get("enabled") else "no")
    table.add_row("state_path", str(payload.get("state_path") or "-"))
    table.add_row("log_path", str(payload.get("log_path") or "-"))
    table.add_row("proxy_url", str(payload.get("proxy_url") or "-"))
    table.add_row("ca_cert_path", str(payload.get("ca_cert_path") or "-"))
    table.add_row("proxy_pid", str(payload.get("proxy_pid") or "-"))
    table.add_row("proxy_started_at", str(payload.get("proxy_started_at") or "-"))
    table.add_row("updated_at", str(payload.get("updated_at") or "-"))
    console.print(table)


def handle_logs_command(
    argv,
    *,
    command_name,
    fake_upstream_status_payload,
    config_root,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} logs",
        description="显示 MMS 常用日志路径与可直接复制的查看命令",
    )
    parser.add_argument("--tail", type=int, default=20, help="默认 tail 行数")
    args = parser.parse_args(argv)

    fake_payload = fake_upstream_status_payload()
    fake_log_path = str(fake_payload.get("log_path") or "-")
    fake_status_cmd = f"{command_name} fake-upstream status"
    fake_log_cmd = f"{command_name} fake-upstream log --tail {args.tail}"
    raw_tail_cmd = f"tail -n {args.tail} {shlex.quote(fake_log_path)}" if fake_log_path not in {"", "-"} else "-"
    guard_status_cmd = f"{command_name} guard status"

    table = table_cls(title="MMS Logs")
    table.add_column("项", style="cyan", no_wrap=True)
    table.add_column("值", style="green")
    table.add_row("config_root", config_root)
    table.add_row("fake_upstream", "on" if fake_payload.get("enabled") else "off")
    table.add_row("fake_log_path", fake_log_path)
    table.add_row("cmd.status", fake_status_cmd)
    table.add_row("cmd.fake_log", fake_log_cmd)
    table.add_row("cmd.raw_tail", raw_tail_cmd)
    table.add_row("cmd.guard", guard_status_cmd)
    console.print(table)


def handle_exposure_command(
    argv,
    *,
    command_name,
    cli_names,
    load_command_config,
    ensure_provider_credentials,
    ensure_models_ready,
    choose_runtime_source,
    inspect_runtime_exposure,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} exposure",
        description="审计当前 runtime 会向 CLI 暴露哪些 env / settings / HOME 信息",
    )
    parser.add_argument("cli", nargs="?", default="claude", choices=cli_names, help="目标 CLI")
    parser.add_argument("--account", help="指定账号 id")
    parser.add_argument("--provider", help="指定 provider id")
    args = parser.parse_args(argv)

    cfg = load_command_config()
    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _models, launch_cli = choose_runtime_source(
        cfg,
        args.cli,
        default_provider,
        models_cache,
        account_id=args.account,
        provider_id=args.provider,
    )
    if runtime is None:
        console.print(f"[red]{args.cli} 当前没有可用运行来源[/red]")
        return

    payload = inspect_runtime_exposure(launch_cli, runtime)

    summary = table_cls(title="MMS Exposure Audit")
    summary.add_column("字段", style="cyan")
    summary.add_column("值", style="green")
    summary.add_row("cli", str(payload.get("cli") or "-"))
    summary.add_row("runtime", str(payload.get("runtime_name") or payload.get("runtime_id") or "-"))
    summary.add_row("auth_mode", str(payload.get("auth_mode") or "-"))
    network = payload.get("network") or {}
    summary.add_row("net", str(network.get("proxy_mode") or "-"))
    summary.add_row("dns", str(network.get("dns_mode") or "-"))
    summary.add_row("proxy", str(network.get("proxy_fingerprint") or "-"))
    summary.add_row("timezone", str(network.get("timezone") or "-"))
    summary.add_row("locale", str(network.get("locale") or "-"))
    summary.add_row("fake_upstream", "on" if network.get("fake_upstream") else "off")
    summary.add_row("ipv4", "on" if network.get("force_ipv4") else "off")
    console.print(summary)

    home = payload.get("home") or {}
    home_table = table_cls(title="Session Home / Settings")
    home_table.add_column("字段", style="cyan")
    home_table.add_column("值", style="green")
    home_table.add_row("real_home", str(home.get("real_home") or "-"))
    home_table.add_row("account_home", str(home.get("account_home") or "-"))
    home_table.add_row("session_home", str(home.get("session_home") or "-"))
    home_table.add_row("settings_path", str(home.get("settings_path") or "-"))
    console.print(home_table)

    env_table = table_cls(title="Process Env Exposed To CLI")
    env_table.add_column("Key", style="cyan")
    env_table.add_column("Value", style="green")
    for item in payload.get("process_env") or []:
        env_table.add_row(str(item.get("key") or "-"), str(item.get("value") or "-"))
    console.print(env_table)

    settings = payload.get("settings") or {}
    settings_table = table_cls(title="Session Settings Exposure")
    settings_table.add_column("字段", style="cyan")
    settings_table.add_column("值", style="green")
    settings_table.add_row("statusLine", "on" if settings.get("statusline") else "off")
    settings_table.add_row("hook_events", ", ".join(settings.get("hook_events") or []) or "-")
    settings_table.add_row("env_keys", ", ".join(settings.get("env_keys") or []) or "-")
    console.print(settings_table)

    notes = payload.get("notes") or []
    if notes:
        console.print("[yellow]可观察性说明：[/yellow]")
        for note in notes:
            console.print(f"  - {note}")


def _save_cache_config_value(
    cfg,
    key,
    value,
    *,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
):
    updated_cfg = dict(cfg)
    cache_cfg = dict(updated_cfg.get("cache", {}) if isinstance(updated_cfg.get("cache"), dict) else {})
    cache_cfg[key] = normalize_positive_seconds(value, 1)
    updated_cfg["cache"] = cache_cfg
    updated_cfg, _ = ensure_provider_config(updated_cfg)
    updated_cfg, _ = ensure_account_config(updated_cfg)
    updated_cfg, _ = normalize_user_config(updated_cfg)
    updated_cfg, _ = normalize_cache_config(updated_cfg)
    save_config(updated_cfg)
    return updated_cfg


def _display_cache_settings(
    cfg,
    *,
    probe_async_refresh_after,
    probe_async_min_interval,
    command_name,
    table_cls,
    console,
):
    cache_cfg = cfg.get("cache", {}) if isinstance(cfg.get("cache"), dict) else {}
    refresh_after = cache_cfg.get("probe_async_refresh_after_sec", probe_async_refresh_after)
    min_interval = cache_cfg.get("probe_async_min_interval_sec", probe_async_min_interval)
    table = table_cls(title="MMS Cache Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Meaning", style="white")
    table.add_row("probe_async_refresh_after_sec", str(refresh_after), "cache 超过多久后，启动时后台刷新")
    table.add_row("probe_async_min_interval_sec", str(min_interval), "同一 provider 两次异步刷新最小间隔")
    console.print(table)
    console.print(f"[dim]命令示例: {command_name} cache refresh-after 1800[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache min-interval 300[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache reset[/dim]")


def handle_cache_command(
    argv,
    *,
    command_name,
    load_command_config,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
    probe_async_refresh_after,
    probe_async_min_interval,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} cache",
        description="查看或调整启动期 provider model cache 的异步刷新窗口",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("show", help="显示当前 cache 异步刷新参数")

    refresh_parser = subparsers.add_parser("refresh-after", help="设置 cache 多久后触发后台刷新")
    refresh_parser.add_argument("seconds", type=int, help="正整数秒数")

    interval_parser = subparsers.add_parser("min-interval", help="设置同一 provider 最小异步刷新间隔")
    interval_parser.add_argument("seconds", type=int, help="正整数秒数")

    subparsers.add_parser("reset", help="恢复默认异步刷新参数")

    args = parser.parse_args(argv)
    cfg = load_command_config()

    display_kwargs = {
        "probe_async_refresh_after": probe_async_refresh_after,
        "probe_async_min_interval": probe_async_min_interval,
        "command_name": command_name,
        "table_cls": table_cls,
        "console": console,
    }

    if args.subcommand in {None, "show"}:
        _display_cache_settings(cfg, **display_kwargs)
        return
    if args.subcommand == "refresh-after":
        _save_cache_config_value(
            cfg,
            "probe_async_refresh_after_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_refresh_after_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "min-interval":
        _save_cache_config_value(
            cfg,
            "probe_async_min_interval_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_min_interval_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "reset":
        updated_cfg = dict(cfg)
        updated_cfg["cache"] = {
            "probe_async_refresh_after_sec": probe_async_refresh_after,
            "probe_async_min_interval_sec": probe_async_min_interval,
        }
        updated_cfg, _ = normalize_cache_config(updated_cfg)
        save_config(updated_cfg)
        console.print("[green]✓ 已恢复默认 cache 异步刷新参数[/green]")
        _display_cache_settings(updated_cfg, **display_kwargs)
        return

    parser.print_help()


def handle_guard_command(
    argv,
    *,
    command_name,
    bootstrap_cfg,
    load_config,
    default_config,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    iso_now,
    snapshot_digest,
    write_json_snapshot,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} guard",
        description="查看或接受 MMS 配置/关键文件快照",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看当前快照状态")
    subparsers.add_parser("accept", help="把当前状态设为新的已确认快照")

    args = parser.parse_args(argv)
    config_path = config_write_target_path()
    cfg = bootstrap_cfg if isinstance(bootstrap_cfg, dict) else (load_config() or default_config())
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    pending_path = config_snapshot_path("startup", "pending.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []

    if args.subcommand == "accept":
        payload = {
            "kind": "startup",
            "captured_at": iso_now(),
            "digest": snapshot_digest(current_snapshot),
            "snapshot": current_snapshot,
        }
        write_json_snapshot(latest_path, payload)
        write_json_snapshot(accepted_path, payload)
        if os.path.exists(pending_path):
            try:
                os.remove(pending_path)
            except OSError:
                pass
        console.print(f"[green]✓ 已接受当前快照[/green]\n[dim]{accepted_path}[/dim]")
        return

    status = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
    table = table_cls(title="MMS Snapshot Guard")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("status", status)
    table.add_row("accepted", accepted_path)
    table.add_row("latest", latest_path)
    table.add_row("pending", pending_path if os.path.exists(pending_path) else "-")
    table.add_row("real_home", current_snapshot.get("real_home", "-"))
    table.add_row("config_path", current_snapshot.get("config_path", "-"))
    table.add_row("accounts", str(len(current_snapshot.get("accounts", []))))
    table.add_row("providers", str(len(current_snapshot.get("providers", []))))
    console.print(table)
    if diff_lines:
        console.print("[red]检测到漂移：[/red]")
        for item in diff_lines[:20]:
            console.print(f"  - {item}")
        if len(diff_lines) > 20:
            console.print(f"[dim]... 还有 {len(diff_lines) - 20} 项[/dim]")


def handle_session_command(
    argv,
    *,
    command_name,
    handle_session_ls,
    handle_session_info,
    handle_session_prune,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} session",
        description="查看 MMS 托管 CLI session",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    ls_parser = subparsers.add_parser("ls", help="列出已索引 session")
    ls_parser.add_argument("--cli", default="claude", choices=["claude"])

    info_parser = subparsers.add_parser("info", help="查看单个 session 详情")
    info_parser.add_argument("session_id", help="session_id 或 pid-<pid>")
    info_parser.add_argument("--cli", default="claude", choices=["claude"])

    prune_parser = subparsers.add_parser("prune", help="列出或删除 stale MMS gateway session")
    prune_parser.add_argument("--cli", default="all", choices=["claude", "codex", "opencode", "all"])
    prune_parser.add_argument("--dry-run", action="store_true", help="只列出候选项；默认行为")
    prune_parser.add_argument("--apply", action="store_true", help="实际删除 stale session；默认只 dry-run")
    prune_parser.add_argument("--yes", action="store_true", help="配合 --apply，确认删除")

    args = parser.parse_args(argv)
    if args.subcommand == "ls":
        handle_session_ls(args.cli)
        return
    if args.subcommand == "info":
        handle_session_info(args.session_id, args.cli)
        return
    if args.subcommand == "prune":
        handle_session_prune(args.cli, apply=bool(args.apply), yes=bool(args.yes))
        return
    parser.print_help()


def handle_env_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
    env_dir,
    preset_env_file_path,
    display_title,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} env",
        description="输出预设对应的 export 环境变量",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--apply", action="store_true", help="写入 ~/.config/mms/env/<preset>.sh")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name)
    if preset is None:
        return

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider)
    if result is None:
        return

    cli, exports, _runtime = result
    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{args.preset_name} ({cli}) 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if args.apply:
        os.makedirs(env_dir, exist_ok=True)
        env_path = preset_env_file_path(args.preset_name)
        with open(env_path, "w") as handle:
            handle.write(f"# Generated by {display_title()} — preset: {args.preset_name}\n")
            handle.write(export_block + "\n")
        console.print(f"\n[green]✓ 已写入 {env_path}[/green]")
        console.print(f"[dim]需要时手动执行: source {env_path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {command_name} env {args.preset_name} --apply 生成独立 env 文件[/dim]"
        )


def handle_activate_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} activate",
        description="输出可 eval 的 export 语句",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name, stderr_only=True)
    if preset is None:
        sys.exit(1)

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider, stderr_only=True)
    if result is None:
        sys.exit(1)

    _cli, exports, _runtime = result
    for key, value in exports.items():
        print(f"export {key}={shlex.quote(str(value))}")

    if sys.stderr.isatty():
        print(f"# ✓ preset '{args.preset_name}' activated", file=sys.stderr)


def handle_models_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_models,
    manage_provider_models,
    text_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} ls [provider_id]"))
        console.print("[dim]不带参数时先选通道，再进入模型列表与测速页。[/dim]")
        return
    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_models(cfg)
        if not provider_id:
            return

    manage_provider_models(cfg, provider_id)


def select_provider_for_models(
    cfg,
    *,
    list_manage_targets,
    table_cls,
    prompt_cls,
    console,
):
    providers = [item for item in list_manage_targets(cfg) if item.get("kind") == "provider"]
    if not providers:
        console.print("[yellow]当前还没有可管理的网关通道[/yellow]")
        return None

    table = table_cls(title="模型与测速 · 选择通道", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("显示名", style="yellow")
    table.add_column("内部标识", style="green")
    table.add_column("默认", style="magenta", width=6)
    table.add_column("状态", style="white")
    for index, provider in enumerate(providers, 1):
        table.add_row(
            str(index),
            provider.get("title", ""),
            provider.get("id", ""),
            provider.get("default_label", ""),
            provider.get("status", ""),
        )
    console.print(table)

    while True:
        raw = prompt_cls.ask("选择要查看的通道，直接回车返回", default="")
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(providers):
                return providers[idx - 1]["id"]
        console.print(f"[red]请输入 1-{len(providers)} 的编号[/red]")


def pick_manual_models(models, *, table_cls, prompt_cls, console):
    if not models:
        return []
    table = table_cls(title="选择要预热的模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    for idx, model_name in enumerate(models, 1):
        table.add_row(str(idx), model_name)
    console.print(table)
    raw = prompt_cls.ask("输入模型编号，支持逗号分隔；直接回车取消", default="")
    if not raw.strip():
        return []
    selected = []
    seen = set()
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value.isdigit():
            continue
        idx = int(value)
        if 1 <= idx <= len(models):
            model_name = models[idx - 1]
            if model_name not in seen:
                seen.add(model_name)
                selected.append(model_name)
    return selected


def handle_warm_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_warm,
    resolve_provider_context,
    probe_models,
    recent_models_for_provider,
    pick_manual_models,
    warm_model_request,
    text_cls,
    panel_cls,
    prompt_cls,
    confirm_cls,
    table_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} warm [provider_id]"))
        console.print("[dim]不带参数时先选通道，再选择最近使用 / 手动选择 / 全部模型。[/dim]")
        return

    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_warm(cfg)
        if not provider_id:
            return

    provider = resolve_provider_context(cfg, provider_id)
    probe = probe_models(provider, emit_output=False)
    models = list(probe.get("models") or [])
    if not models:
        console.print("[yellow]当前通道没有可预热的模型[/yellow]")
        return

    recent_models = [item for item in recent_models_for_provider(provider_id) if item in models]

    console.print(panel_cls(
        f"[bold]通道:[/bold] {provider.get('name', provider_id)}\n"
        f"[bold]可用模型数:[/bold] {len(models)}\n"
        f"[dim]预热会真实发请求，建议优先预热最近常用模型，不建议默认全量预热。[/dim]",
        title="模型预热",
        border_style="cyan",
    ))
    console.print("  1. 预热最近使用模型（推荐）")
    console.print("  2. 手动选择模型")
    console.print("  3. 预热全部模型（不推荐）")
    console.print("  4. 返回")
    choice = prompt_cls.ask("选择操作", choices=["1", "2", "3", "4"], default="1")

    selected_models = []
    if choice == "1":
        selected_models = recent_models
        if not selected_models:
            console.print("[yellow]当前没有最近使用模型，已改为手动选择[/yellow]")
            selected_models = pick_manual_models(models)
    elif choice == "2":
        selected_models = pick_manual_models(models)
    elif choice == "3":
        if not confirm_cls.ask("确认预热当前通道全部模型？这会产生真实请求成本。", default=False):
            console.print("[yellow]已取消全量预热[/yellow]")
            return
        selected_models = models
    else:
        return

    if not selected_models:
        console.print("[yellow]没有选择任何模型，已取消预热[/yellow]")
        return

    results = []
    for model_name in selected_models:
        console.print(f"[dim]正在预热 {model_name} ...[/dim]")
        ok, detail = warm_model_request(provider, model_name)
        results.append((model_name, ok, detail))

    table = table_cls(title=f"{provider.get('name', provider_id)} · 预热结果", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("详情", style="yellow")
    success_count = 0
    for model_name, ok, detail in results:
        if ok:
            success_count += 1
        table.add_row(model_name, "成功" if ok else "失败", detail)
    console.print(table)
    console.print(f"[green]✓ 已完成预热：成功 {success_count} / {len(results)}[/green]")


def handle_export(
    cli_name,
    provider,
    *,
    apply=False,
    cli_names,
    get_export_env,
    env_dir,
    env_file_path,
    display_title,
    export_command_hint,
    console,
):
    if cli_name not in cli_names:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(cli_names)}")
        return

    exports = get_export_env(cli_name, provider)
    if not exports:
        console.print(f"[yellow]{cli_name} 无需 export；启动时会按 CLI 自己的参数或登录方式处理[/yellow]")
        return

    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{cli_name} 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if apply:
        os.makedirs(env_dir, exist_ok=True)
        path = env_file_path(cli_name)
        with open(path, "w") as handle:
            handle.write(f"# Generated by {display_title()}\n")
            handle.write(export_block + "\n")

        console.print(f"\n[green]✓ 已写入 {path}[/green]")
        console.print("[dim]这是独立 env 文件，不会自动修改 ~/.zshrc 或 ~/.bashrc[/dim]")
        console.print(f"[dim]需要时手动执行: source {path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {export_command_hint(cli_name)} 生成独立 env 文件[/dim]"
        )


def emit_preset_error(message, *, stderr_only=False, console):
    if stderr_only:
        print(message, file=sys.stderr)
    else:
        console.print(message)


def preset_env_file_path(preset_name, *, env_dir):
    safe_name = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(preset_name or "").strip().lower()
    ).strip("-_")
    safe_name = safe_name or "preset"
    return os.path.join(env_dir, f"{safe_name}.sh")


def resolve_named_preset(
    cfg,
    preset_name,
    *,
    normalize_preset_entry,
    emit_preset_error,
    stderr_only=False,
):
    presets = cfg.get("presets", {})
    if preset_name not in presets:
        emit_preset_error(f"预设 '{preset_name}' 不存在", stderr_only=stderr_only)
        if presets:
            emit_preset_error(f"可用预设: {', '.join(presets.keys())}", stderr_only=stderr_only)
        return None
    return normalize_preset_entry(preset_name, presets[preset_name])


def infer_preset_auth_mode(preset):
    if not isinstance(preset, dict):
        return None
    if preset.get("bridge"):
        return "oauth_bridge"
    if preset.get("account"):
        return "oauth"
    if preset.get("provider"):
        return "api_key"
    return None


def resolve_preset_export_runtime(
    cfg,
    preset,
    provider_override=None,
    *,
    stderr_only=False,
    infer_preset_auth_mode,
    emit_preset_error,
    ensure_provider_credentials,
    validate_provider_for_cli,
    get_export_env,
):
    cli = preset.get("cli", "claude")
    auth_mode = infer_preset_auth_mode(preset)

    if auth_mode in ("oauth", "oauth_bridge"):
        emit_preset_error(f"此预设使用 {auth_mode} 模式，不支持 env export", stderr_only=stderr_only)
        return None

    provider_id = provider_override or preset.get("provider") or None

    runtime = ensure_provider_credentials(cfg, provider_id)
    if runtime is None:
        emit_preset_error(f"无法解析 provider: {provider_id or 'default'}", stderr_only=stderr_only)
        return None

    if not provider_id and sys.stderr.isatty():
        default_name = runtime.get("id", "default") if isinstance(runtime, dict) else "default"
        print(f"预设未指定 provider，使用默认: {default_name}", file=sys.stderr)

    try:
        validate_provider_for_cli(cli, runtime)
    except Exception as exc:
        emit_preset_error(str(exc), stderr_only=stderr_only)
        return None

    exports = get_export_env(cli, runtime)
    if not exports:
        emit_preset_error(f"{cli} 无需 export；启动时会按 CLI 自己的参数或登录方式处理", stderr_only=stderr_only)
        return None

    return cli, exports, runtime


def handle_presets_command(
    cfg,
    *,
    preset_has_visible_model_options,
    infer_preset_auth_mode,
    default_provider_id,
    table_cls,
    console,
):
    presets = cfg.get("presets", {})
    visible_presets = {
        name: preset for name, preset in presets.items()
        if preset_has_visible_model_options(preset)
    }
    if visible_presets:
        table = table_cls(title="已保存预设")
        table.add_column("名称", style="cyan")
        table.add_column("CLI", style="green")
        table.add_column("Provider", style="magenta")
        table.add_column("模型", style="yellow")
        table.add_column("描述", style="dim")
        table.add_column("模式", style="blue")
        for name, preset in visible_presets.items():
            model_str = preset.get("model", f"opus={preset.get('opus','')}, sonnet={preset.get('sonnet','')}")
            desc = preset.get("description", "")
            auth = infer_preset_auth_mode(preset) or "—"
            table.add_row(
                name,
                preset.get("cli", "?"),
                preset.get("provider", default_provider_id),
                str(model_str),
                desc,
                auth,
            )
        console.print(table)


def display_config_help(*, command_name, console):
    console.print(f"[bold]{command_name} config[/bold] — 配置查看与管理")
    console.print(f"[dim]用法: {command_name} config [子命令] [参数][/dim]")
    console.print("\n[bold]常用子命令:[/bold]")
    console.print(f"  {command_name} config")
    console.print(f"  {command_name} config file")
    console.print(f"  {command_name} config validate")
    console.print(f"  {command_name} config get <dot.path>")
    console.print(f"  {command_name} config set <dot.path> <value>")
    console.print(f"  {command_name} config unset <dot.path>")
    console.print(f"  {command_name} config connect")
    console.print(f"  {command_name} config web [--no-open]")
    console.print(f"  {command_name} config preferences.help")
    console.print(f"  {command_name} config human-gate")
    console.print(f"  [dim]可调参数示例: cache.probe_async_refresh_after_sec / cache.probe_async_min_interval_sec[/dim]")
    console.print("\n[bold]Provider:[/bold]")
    console.print(f"  {command_name} config provider.list")
    console.print(f"  {command_name} config provider.default [id]")
    console.print(f"  {command_name} config provider.add [id]")
    console.print(f"  {command_name} config provider.edit <id>")
    console.print(f"  {command_name} config provider.remove <id>")
    console.print(f"  {command_name} config provider.credentials [id]")
    console.print(f"  {command_name} config extension.openrouter [add|status|models]")
    console.print("\n[bold]Account:[/bold]")
    console.print(f"  {command_name} config account.list")
    console.print(f"  {command_name} config account.add \\[codex|agy]")
    console.print(f"  {command_name} config account.edit <id>")
    console.print(f"  {command_name} config account.remove <id>")
    console.print(f"  {command_name} config account.status [id]")
    console.print(f"  {command_name} config account.login <id>")
    console.print(f"  {command_name} config account.default <cli> <id>")
    console.print("  [dim]Claude OAuth 独立入口已下线；MMS 不再新增/登录/设默认 Claude 官方账号。[/dim]")
    console.print("\n[bold]其他:[/bold]")
    console.print(f"  {command_name} config stats")
    console.print(f"  {command_name} config api.edit")


def display_preferences_path(*, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS preferences.toml[/bold]")
    for path in preference_paths:
        marker = "active" if os.path.exists(path) else "create-if-needed"
        console.print(f"  {path}  [dim]({marker})[/dim]")
    console.print(f"[dim]文档: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents may inspect/propose, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_preferences_example(*, preferences_example_toml, console):
    console.print(preferences_example_toml.rstrip(), markup=False)


def display_human_gate_help(*, command_name, preferences_doc_path, console):
    console.print("[bold]MMS Human Gate[/bold]")
    console.print("- real config tree `~/.config/mms/**` is human-only for agents.")
    console.print("- allowed for agents: inspect, explain, generate manual diff, print examples.")
    console.print("- blocked without human confirmation: writing config.toml, preferences.toml, override.toml, credentials.sh, accounts/**, env/**, usage/account state, or Claude config.")
    console.print("- required write flow: plan -> backup -> human double check -> audited write -> post-write human double check.")
    console.print("- `preferences.toml` is safer than `override.toml`, but it is still real user config and stays behind the same human gate.")
    console.print(f"[dim]LLM entry: run `{command_name} config preferences.help` and read {preferences_doc_path} before advising config edits.[/dim]")


def display_preferences_help(*, command_name, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS User Preferences[/bold]")
    console.print(f"Path: {preference_paths[0]}")
    console.print("Purpose: user-owned, install-safe, allowlisted launch preference overlay.")
    console.print("\n[bold]Commands:[/bold]")
    console.print(f"  {command_name} config preferences.path")
    console.print(f"  {command_name} config preferences.example")
    console.print(f"  {command_name} config preferences.doc")
    console.print(f"  {command_name} config human-gate")
    console.print("\n[bold]Allowed keys:[/bold]")
    console.print("  launch.defaults: thinking_mode, reasoning_effort, caveman_mode, nsr_mode, agent_pack, bypass")
    console.print("  launch.cli.<claude|codex|opencode|agy>: same launch keys")
    console.print("  session_surfaces.disabled: skills, mcp, hooks")
    console.print("  assets.roots: web_access, weber, agent_browser, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor")
    console.print("\n[bold]Denied / ignored:[/bold]")
    console.print("  api_key, base_url, proxy, account identity, provider routes, OAuth tokens, credentials, Claude config, real HOME/XDG/auth state")
    console.print("\n[bold]Overlay order:[/bold]")
    console.print("  config.toml -> override.toml -> preferences.toml launch allowlist -> confirm screen changes -> launcher")
    console.print(f"[dim]Full doc: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents can propose edits, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_usage_stats(*, load_usage_stats, usage_path, table_cls, console):
    stats = load_usage_stats()
    sources = stats.get("sources", {})
    if not sources:
        console.print("[yellow]还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件会写入 {usage_path}[/dim]")
        return

    table = table_cls(title="本地启动统计", show_lines=True)
    table.add_column("来源", style="cyan")
    table.add_column("CLI", style="green")
    table.add_column("启动次数", style="yellow")
    table.add_column("最近模型", style="magenta")
    table.add_column("最近使用", style="white")

    rows = sorted(
        sources.values(),
        key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)),
        reverse=True,
    )
    for item in rows:
        table.add_row(
            f"{item.get('runtime_kind', 'source')} / {item.get('name', item.get('id', 'default'))}",
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这是本地软统计，用于排序/推荐参考；不等于真实计费数据。[/dim]")


def display_adapter_registry(*, top_source_companies, default_adapter_policy, command_name, table_cls, console):
    table = table_cls(title="来源公司 / Adapter Registry (Top 10)", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("公司/品牌", style="green")
    table.add_column("模型族", style="yellow")
    table.add_column("推荐 Adapter", style="magenta")
    table.add_column("当前状态", style="white")
    table.add_column("OAuth", style="white")
    table.add_column("默认 Claude Bridge", style="white")

    for idx, item in enumerate(top_source_companies, 1):
        table.add_row(
            str(idx),
            f"{item.get('company', '')} / {item.get('brand', '')}",
            ", ".join(item.get("families", [])),
            str(item.get("default_adapter", "")),
            str(item.get("current_support", "")),
            "yes" if item.get("oauth_native") else "no",
            "yes" if item.get("claude_bridge_default") else "no",
        )
    console.print(table)
    console.print("[bold]默认策略:[/bold]")
    for key, text in default_adapter_policy.items():
        console.print(f"  [cyan]{key}[/cyan]: {text}")
    console.print(
        f"[dim]详情文档: docs/ADAPTER_REGISTRY.md；命令: {command_name} config adapter.registry[/dim]"
    )


def display_providers(
    cfg,
    *,
    default_provider_id,
    default_priority,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    command_name,
    table_cls,
    console,
):
    providers = cfg.get("providers", [])
    if not providers:
        console.print("[yellow]未配置模型源[/yellow]")
        return

    table = table_cls(title="模型源列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("协议", style="yellow")
    table.add_column("CLI", style="magenta")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="white")
    table.add_column("地址", style="blue")

    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    for provider in providers:
        provider_ctx = resolve_provider_context(cfg, provider.get("id"))
        status = "默认" if provider.get("id") == default_id else ""
        status = f"{status} 启用" if provider.get("enabled", True) else f"{status} 禁用".strip()
        table.add_row(
            str(provider.get("id", "")),
            str(provider.get("name", "")),
            ", ".join(provider.get("protocols", [])),
            ", ".join(provider.get("supported_clis", [])),
            str(provider.get("priority", default_priority)),
            status.strip(),
            provider_openai_base_url(provider_ctx) or provider_anthropic_base_url(provider_ctx) or "(未设置)",
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config provider.default <id> 切换默认模型源。[/dim]"
    )


def display_accounts(
    cfg,
    *,
    default_priority,
    probe_account_status,
    command_name,
    table_cls,
    console,
):
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]未配置账号档案[/yellow]")
        return

    defaults = cfg.get("account", {}).get("defaults", {})
    table = table_cls(title="账号档案列表", show_lines=True)
    table.add_column("文件夹名", style="cyan")
    table.add_column("显示名", style="green")
    table.add_column("CLI", style="yellow")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="magenta")
    table.add_column("登录态", style="white")
    table.add_column("文件夹目录", style="blue")

    for account in accounts:
        login_state = probe_account_status(account)
        status = []
        if defaults.get(account.get("cli")) == account.get("id"):
            status.append("默认")
        status.append("启用" if account.get("enabled", True) else "禁用")
        table.add_row(
            str(account.get("id", "")),
            str(account.get("name", "")),
            str(account.get("cli", "")),
            str(account.get("priority", default_priority)),
            " ".join(status).strip(),
            login_state.get("summary") or login_state.get("state", ""),
            str(account.get("home_dir", "")),
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config account.default <cli> <id> 设置默认账号，"
        f"{command_name} config account.login <id> 进入官方登录。[/dim]"
    )
    console.print("[dim]注: Claude OAuth 独立入口已下线，这里仅保留旧配置只读兼容。[/dim]")


def recent_models_for_provider(provider_id, *, usage_rows_for_runtime):
    recent = []
    seen = set()
    for item in usage_rows_for_runtime("provider", provider_id):
        last_model = str(item.get("last_model", "")).strip()
        if last_model and last_model not in seen:
            seen.add(last_model)
            recent.append(last_model)
        for model_name, _count in sorted((item.get("models") or {}).items(), key=lambda pair: pair[1], reverse=True):
            model_name = str(model_name or "").strip()
            if model_name and model_name not in seen:
                seen.add(model_name)
                recent.append(model_name)
    return recent


def display_runtime_usage(
    runtime_kind,
    runtime_id,
    title,
    *,
    use_tui,
    clear_console,
    usage_rows_for_runtime,
    active_usage_path,
    pause_after_tui_report,
    table_cls,
    console,
):
    if use_tui():
        try:
            clear_console()
        except Exception:
            pass
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    if not rows:
        console.print(f"[yellow]{title} 还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件: {active_usage_path()}[/dim]")
        if use_tui():
            pause_after_tui_report("按 Enter 返回通道详情")
        return

    table = table_cls(title=f"{title} · 本地统计", show_lines=True)
    table.add_column("CLI", style="cyan")
    table.add_column("启动次数", style="green")
    table.add_column("最近模型", style="yellow")
    table.add_column("最近使用", style="magenta")
    for item in rows:
        table.add_row(
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这里只是本地启动统计，不代表官方真实余额或剩余额度。[/dim]")
    if use_tui():
        pause_after_tui_report("按 Enter 返回通道详情")


def display_provider_model_table(
    provider,
    probe,
    *,
    get_speed_entry,
    infer_model_family,
    model_capability_summary,
    model_cli_summary,
    model_source_label,
    ttfb_label,
    tps_label,
    table_cls,
    console,
):
    table = table_cls(title=f"{provider.get('name', provider.get('id'))} · 模型列表", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("家族", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")
    table.add_column("来源", style="green")
    table.add_column("首字节延迟", style="yellow")
    table.add_column("生成速度", style="magenta")
    table.add_column("样本", style="white")
    table.add_column("最近更新", style="blue")

    for model_id in probe.get("models") or []:
        speed = get_speed_entry(model_id, provider=provider)
        ttfb = "暂无数据"
        tps = "暂无数据"
        samples = "-"
        updated = "-"
        if speed:
            ttfb_value = speed.get("ttfb_avg_ms")
            ttfb = f"{ttfb_value:.0f}ms / {ttfb_label(ttfb_value)}" if isinstance(ttfb_value, (int, float)) else "暂无数据"
            tps_value = speed.get("tps_avg")
            tps = f"{tps_value:.1f} / {tps_label(tps_value)}" if isinstance(tps_value, (int, float)) else "暂无数据"
            samples = str(speed.get("samples", 0))
            if speed.get("warming_up"):
                samples = f"{samples}（预热中）"
            updated = str(speed.get("last_updated") or "-")
            if speed.get("is_stale"):
                updated = f"{updated} (stale)"
        table.add_row(
            model_id,
            infer_model_family(model_id)[0],
            model_capability_summary(model_id),
            model_cli_summary(model_id),
            model_source_label((probe.get("model_sources") or {}).get(model_id, probe.get("base_source", "remote"))),
            ttfb,
            tps,
            samples,
            updated,
        )
    console.print(table)
    hidden_models = probe.get("hidden_models") or []
    extra_models = probe.get("extra_models") or []
    if extra_models:
        console.print(f"[dim]手工补充模型: {', '.join(extra_models)}[/dim]")
    if hidden_models:
        console.print(f"[dim]已隐藏模型: {', '.join(hidden_models)}[/dim]")
    raw_models = probe.get("raw_models") or []
    if raw_models and raw_models != (probe.get("models") or []):
        console.print(f"[dim]原始模型数: {len(raw_models)} | 最终展示模型数: {len(probe.get('models') or [])}[/dim]")


def display_openrouter_extension_help(command_name, *, console):
    console.print(f"[bold]{command_name} config extension.openrouter[/bold] — OpenRouter 可选扩展")
    console.print(f"  {command_name} config extension.openrouter add")
    console.print(f"  {command_name} config extension.openrouter status [provider_id] [--limit N] [--json]")
    console.print(f"  {command_name} config extension.openrouter models [provider_id] [--limit N] [--json]")
    console.print("[dim]status/models 默认不写真实 MMS 配置；add 会进入交互式 provider 接入。[/dim]")


def display_openrouter_model_rows(title, rows, *, limit, table_cls, console):
    table = table_cls(title=title, show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("免费", style="yellow", width=6)
    table.add_column("输入", style="magenta")
    table.add_column("输出", style="magenta")
    table.add_column("Context", justify="right")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            "yes" if item.get("is_free") else "no",
            ",".join(item.get("input_modalities") or []),
            ",".join(item.get("output_modalities") or []),
            str(item.get("context_length") or ""),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_video_rows(rows, *, limit, table_cls, console):
    table = table_cls(title="OpenRouter Video 模型", show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("分辨率", style="yellow")
    table.add_column("时长", style="magenta")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            ",".join(str(value) for value in item.get("supported_resolutions") or []),
            ",".join(str(value) for value in item.get("supported_durations") or []),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_extension_summary(
    summary,
    *,
    provider_label="",
    limit=12,
    show_models=False,
    table_cls,
    console,
):
    account = summary.get("account") or {}
    counts = summary.get("counts") or {}
    requests = summary.get("requests") or {}
    table = table_cls(title="OpenRouter Extension", show_lines=True)
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("provider/key", provider_label or "env/public")
    table.add_row("account tier", f"{account.get('tier')} ({account.get('reason')})")
    table.add_row("model source", str(summary.get("model_source") or "-"))
    table.add_row("visible text", str(counts.get("visible_text", 0)))
    table.add_row("image/video", f"{'on' if summary.get('image_enabled') else 'off'} / {'on' if summary.get('video_enabled') else 'off'}")
    table.add_row("requests", ", ".join(f"{key}:{value.get('status')}" for key, value in requests.items()))
    console.print(table)
    if summary.get("free_only"):
        console.print("[yellow]当前按 free-only 策略展示：只列免费文本模型，隐藏 OpenRouter Image / Video。[/yellow]")
    if not show_models:
        return
    display_openrouter_model_rows("OpenRouter Text 模型", summary.get("text_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("image_enabled"):
        display_openrouter_model_rows("OpenRouter Image 模型", summary.get("image_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("video_enabled"):
        display_openrouter_video_rows(summary.get("video_models") or [], limit=limit, table_cls=table_cls, console=console)


def display_config(
    cfg,
    *,
    prefix="",
    depth=0,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    mask_key,
    active_credentials_path,
    active_usage_path,
    display_providers,
    display_accounts,
    probe_async_refresh_after,
    probe_async_min_interval,
    existing_override_paths,
    override_paths,
    existing_preferences_paths,
    preference_paths,
    command_name,
    console,
):
    if depth == 0:
        provider = resolve_provider_context(cfg)
        console.print("[bold]模型源:[/bold]")
        console.print(f"  [cyan]default[/cyan] = {cfg.get('provider', {}).get('default', 'default')}")
        console.print(f"  [cyan]openai_base_url[/cyan] = {provider_openai_base_url(provider) or '(未设置)'}")
        console.print(f"  [cyan]anthropic_base_url[/cyan] = {provider_anthropic_base_url(provider) or '(未设置)'}")
        key_display = mask_key(provider.get("api_key", "")) if provider.get("api_key") else "(未设置)"
        console.print(f"  [cyan]api_key[/cyan] = {key_display}")
        console.print(f"  [cyan]credentials_file[/cyan] = {active_credentials_path()}")
        console.print("  [dim]api_key 为掩码显示；真实值请查看 credentials_file。[/dim]")
        display_providers(cfg)
        display_accounts(cfg)
        console.print(f"  [cyan]usage_file[/cyan] = {active_usage_path()}")
        console.print("  [dim]usage 只记录本地启动统计，不代表真实余额或官方剩余额度。[/dim]")
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            console.print(f"  [cyan]probe_async_refresh_after_sec[/cyan] = {cache_cfg.get('probe_async_refresh_after_sec', probe_async_refresh_after)}")
            console.print(f"  [cyan]probe_async_min_interval_sec[/cyan] = {cache_cfg.get('probe_async_min_interval_sec', probe_async_min_interval)}")
            console.print("  [dim]以上窗口控制模型列表异步刷新：首屏先读 cache，后台再 refresh。[/dim]")
        active_overrides = existing_override_paths()
        if active_overrides:
            console.print(f"  [cyan]override_files[/cyan] = {active_overrides}")
            console.print("  [dim]override 仅在运行时叠加，不会直接写回 config.toml。[/dim]")
        else:
            console.print(f"  [cyan]override_files[/cyan] = {override_paths}")
            console.print("  [dim]如需团队共享默认值，可在以上路径创建 override.toml。[/dim]")
        active_preferences = existing_preferences_paths()
        console.print(f"  [cyan]preferences_files[/cyan] = {active_preferences or preference_paths}")
        console.print(f"  [dim]用户偏好 allowlist: {command_name} config preferences.help；真实配置仍受 human-gate 保护。[/dim]")

    for key, value in cfg.items():
        if depth == 0 and key in {"providers", "provider", "accounts", "account", "_mms_preferences"}:
            continue
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            console.print(f"{'  ' * depth}[bold]{key}:[/bold]")
            display_config(
                value,
                prefix=full_key,
                depth=depth + 1,
                resolve_provider_context=resolve_provider_context,
                provider_openai_base_url=provider_openai_base_url,
                provider_anthropic_base_url=provider_anthropic_base_url,
                mask_key=mask_key,
                active_credentials_path=active_credentials_path,
                active_usage_path=active_usage_path,
                display_providers=display_providers,
                display_accounts=display_accounts,
                probe_async_refresh_after=probe_async_refresh_after,
                probe_async_min_interval=probe_async_min_interval,
                existing_override_paths=existing_override_paths,
                override_paths=override_paths,
                existing_preferences_paths=existing_preferences_paths,
                preference_paths=preference_paths,
                command_name=command_name,
                console=console,
            )
        elif isinstance(value, list):
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {value}")
        else:
            display = mask_key(str(value)) if "key" in key.lower() else str(value)
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {display}")


def run_script_subcommand(script_name, argv, subcommand_name, *, script_dir, command_name, console):
    script_path = os.path.join(script_dir, script_name)
    if not os.path.exists(script_path):
        console.print(f"[red]找不到脚本: {script_path}[/red]")
        return 1
    env = os.environ.copy()
    env["MMS_SUBCOMMAND_PROG"] = f"{command_name} {subcommand_name}"
    try:
        completed = subprocess.run([sys.executable, script_path, *argv], env=env)
        return int(completed.returncode or 0)
    except KeyboardInterrupt:
        return 130


def handle_doctor_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "doctor_claude_models.py",
        argv,
        "doctor",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_test_command(argv, *, subcommand_name, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_cli_channels.py",
        argv,
        subcommand_name,
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_opencode_smoke_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_opencode_profile.py",
        argv,
        "opencode-smoke",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )
