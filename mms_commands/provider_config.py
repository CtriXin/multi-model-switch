"""Provider config, credentials, and runtime context helpers."""

from __future__ import annotations

import os
import shlex
import sys
from zoneinfo import ZoneInfo

try:
    import tomllib
except ImportError:
    import tomli as tomllib

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


def default_config(
    role,
    *,
    normalize_user_role,
    probe_async_refresh_after_sec,
    probe_async_min_interval_sec,
    default_provider_id,
    default_provider,
):
    return {
        "ui": {"language": "zh"},
        "user": {"role": normalize_user_role(role)},
        "cache": {
            "probe_async_refresh_after_sec": probe_async_refresh_after_sec,
            "probe_async_min_interval_sec": probe_async_min_interval_sec,
        },
        "provider": {"default": default_provider_id},
        "providers": [default_provider()],
        "account": {"defaults": {}},
        "accounts": [],
        "recommend": {"models": [
            "claude-sonnet-4-6", "qwen3-coder-plus", "gpt-4o-mini",
        ]},
        "presets": {
            "coding": {
                "cli": "claude",
                "opus": "claude-opus-4-6",
                "sonnet": "claude-sonnet-4-6",
                "haiku": "claude-haiku-4-5-20251001",
                "subagent": "claude-sonnet-4-6",
            },
            "cheap": {"cli": "claude", "model": "qwen3-coder-plus"},
            "codex-gpt": {"cli": "codex", "model": "gpt-5.4"},
        },
    }


def migrate_legacy_api_config(
    cfg,
    *,
    load_api_credentials,
    save_api_credentials,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    save_config,
    credentials_path,
    config_path,
    console,
):
    api_cfg = cfg.get("api")
    updated_cfg = dict(cfg)

    if isinstance(api_cfg, dict):
        base_url = str(api_cfg.get("base_url", "")).strip()
        api_key = str(api_cfg.get("api_key", "")).strip()
        file_base_url, file_api_key, _ = load_api_credentials()

        if base_url and api_key and (not file_base_url or not file_api_key):
            try:
                save_api_credentials(base_url, api_key)
                console.print(f"[yellow]已将 API 凭据迁移到 {credentials_path}[/yellow]")
            except OSError as exc:
                console.print(f"[yellow]无法迁移 API 凭据到 {credentials_path}: {exc}[/yellow]")
                return cfg

        updated_cfg.pop("api", None)

    updated_cfg, changed = ensure_provider_config(updated_cfg)
    updated_cfg, account_changed = ensure_account_config(updated_cfg)
    updated_cfg, role_changed = normalize_user_config(updated_cfg)
    if changed or account_changed or role_changed or updated_cfg != cfg:
        try:
            save_config(updated_cfg)
        except OSError as exc:
            console.print(f"[yellow]无法更新 {config_path}: {exc}[/yellow]")
            return cfg
    return updated_cfg


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
    if provider.get("_mms_bundle_runtime"):
        provider["base_url"] = credentials["base_url"] or provider.get("base_url", "")
        provider["openai_base_url"] = (
            credentials["openai_base_url"]
            or provider.get("openai_base_url", "")
            or provider.get("default_openai_base_url", "")
        )
        provider["anthropic_base_url"] = (
            credentials["anthropic_base_url"]
            or provider.get("anthropic_base_url", "")
            or provider.get("default_anthropic_base_url", "")
        )
        provider["api_key"] = credentials["api_key"] or provider.get("api_key", "")
        provider["openai_api_key"] = credentials.get("openai_api_key", "") or provider.get("openai_api_key", "")
    else:
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
