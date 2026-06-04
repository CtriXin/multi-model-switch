"""User preference overlay helpers for MMS config."""

from __future__ import annotations

import os


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


def pref_caveman_level(value):
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in {"light", "lite", "low"}:
        return "light"
    if raw in {"standard", "normal", "medium"}:
        return "standard"
    if raw in {"full", "ultra", "high"}:
        return "full"
    return ""


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
    caveman_level = pref_caveman_level(payload.get("caveman_level"))
    if caveman_level:
        result["caveman_level"] = caveman_level
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


def sanitize_managed_assets_root(value):
    path = str(value or "").strip()
    if not path:
        return ""
    return os.path.abspath(os.path.expanduser(path))


def sanitize_disabled_clis(value, *, cli_names):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    allowed = set(cli_names)
    result = []
    seen = set()
    for item in value:
        cli_name = str(item or "").strip().lower()
        if not cli_name or cli_name not in allowed or cli_name in seen:
            continue
        seen.add(cli_name)
        result.append(cli_name)
    return result


def sanitize_user_preferences(raw, *, cli_names, asset_root_keys):
    raw = raw if isinstance(raw, dict) else {}
    launch = raw.get("launch") if isinstance(raw.get("launch"), dict) else {}
    session_surfaces = raw.get("session_surfaces") if isinstance(raw.get("session_surfaces"), dict) else {}
    assets = raw.get("assets") if isinstance(raw.get("assets"), dict) else {}

    result = {
        "launch": {"defaults": {}, "cli": {}, "disabled_clis": []},
        "session_surfaces": {"disabled": {}},
        "assets": {"roots": {}, "managed_enabled": True, "managed_root": ""},
    }
    result["launch"]["defaults"] = sanitize_launch_preferences(launch.get("defaults"))
    disabled_clis = sanitize_disabled_clis(launch.get("disabled_clis", launch.get("disabled")), cli_names=cli_names)
    if disabled_clis:
        result["launch"]["disabled_clis"] = disabled_clis
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
    managed_enabled = pref_bool(assets.get("managed_enabled", assets.get("enabled")))
    if managed_enabled is not None:
        result["assets"]["managed_enabled"] = managed_enabled
    managed_root = sanitize_managed_assets_root(assets.get("managed_root", assets.get("root")))
    if managed_root:
        result["assets"]["managed_root"] = managed_root
    roots = sanitize_asset_roots(assets.get("roots"), asset_root_keys=asset_root_keys)
    if roots:
        result["assets"]["roots"] = roots
    return result


def managed_assets_enabled(*, load_user_preferences, environ=os.environ):
    explicit_root = str(environ.get("MMS_MANAGED_ASSETS_ROOT") or environ.get("MMS_ASSETS_ROOT") or "").strip()
    if explicit_root:
        return True
    try:
        prefs = load_user_preferences()
    except Exception:
        prefs = {}
    prefs = prefs if isinstance(prefs, dict) else {}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    return assets.get("managed_enabled") is not False


def managed_assets_root(*, load_user_preferences, resolve_real_user_home, environ=os.environ):
    explicit = str(environ.get("MMS_MANAGED_ASSETS_ROOT") or environ.get("MMS_ASSETS_ROOT") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    try:
        prefs = load_user_preferences()
    except Exception:
        prefs = {}
    prefs = prefs if isinstance(prefs, dict) else {}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    configured = str(assets.get("managed_root") or "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.join(resolve_real_user_home(), ".local", "share", "mms", "assets")


def preference_disabled_clis(prefs, *, cli_names):
    prefs = prefs if isinstance(prefs, dict) else {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    return set(sanitize_disabled_clis(launch.get("disabled_clis", launch.get("disabled")), cli_names=cli_names))


def disabled_clis_for_cfg(cfg, *, cli_names, load_user_preferences):
    prefs = (cfg or {}).get("_mms_preferences") if isinstance(cfg, dict) else None
    if not isinstance(prefs, dict):
        prefs = load_user_preferences()
    return preference_disabled_clis(prefs, cli_names=cli_names)


def cli_disabled_by_preferences(cfg, cli_name, *, cli_names, load_user_preferences):
    cli_name = str(cli_name or "").strip().lower()
    return bool(cli_name and cli_name in disabled_clis_for_cfg(cfg, cli_names=cli_names, load_user_preferences=load_user_preferences))


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
