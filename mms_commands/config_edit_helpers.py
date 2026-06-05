"""Config get/set/unset value helpers."""

from __future__ import annotations


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
