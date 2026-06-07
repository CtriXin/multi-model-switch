"""Config normalization helpers for command flows."""

from __future__ import annotations

from mms_commands.provider_config import normalize_account_id, normalize_positive_seconds


def normalize_ui_config(cfg, *, normalize_language, default_language="zh"):
    cfg = dict(cfg)
    raw_ui = cfg.get("ui")
    current = raw_ui if isinstance(raw_ui, dict) else {}
    lang = normalize_language(current.get("language", "")) or default_language
    new_cfg = dict(cfg)
    new_cfg["ui"] = {"language": lang}
    return new_cfg, new_cfg != cfg


def normalize_user_role(role, *, mode_all, mode_recommended):
    value = str(role or "").strip()
    if value in {"dev", "all", mode_all}:
        return mode_all
    if value in {"ops", "recommended", mode_recommended}:
        return mode_recommended
    return mode_all


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


def normalize_config_sections(
    cfg,
    *,
    ensure_provider_config,
    ensure_account_config,
    ensure_broker_config,
    normalize_ui_config,
    normalize_presets_config,
    normalize_user_config,
    normalize_cache_config,
):
    cfg, _ = ensure_provider_config(cfg)
    cfg, _ = ensure_account_config(cfg)
    cfg, _ = ensure_broker_config(cfg)
    cfg, _ = normalize_ui_config(cfg)
    cfg, _ = normalize_presets_config(cfg)
    cfg, _ = normalize_user_config(cfg)
    cfg, _ = normalize_cache_config(cfg)
    return cfg


def load_runtime_config(*, load_config, apply_local_overrides):
    cfg = load_config()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


def probe_async_refresh_after(cfg, *, default, normalize_positive_seconds=normalize_positive_seconds):
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return normalize_positive_seconds(
                cache_cfg.get("probe_async_refresh_after_sec", default),
                default,
            )
    return default


def probe_async_min_interval(cfg, *, default, normalize_positive_seconds=normalize_positive_seconds):
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return normalize_positive_seconds(
                cache_cfg.get("probe_async_min_interval_sec", default),
                default,
            )
    return default
