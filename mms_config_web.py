"""Local interactive WebUI for MMS setup, model policy, and audited config saves."""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import shutil
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


_SECRET_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "gateway_key", "token", "secret", "authorization"}
_ALLOWED_PROTOCOLS = ("anthropic_messages", "openai_chat_completions")
_ALLOWED_CLIS = ("claude", "codex", "opencode", "agy")
_ALLOWED_ROLES = ("primary", "auto", "fallback")
_OPENCODE_ROSTER_PRESETS = ("builder", "executor", "explore", "bughunt", "vision", "reviewer", "spec", "fixer")
_OPENCODE_REQUIRED_BUILDER_AGENTS = {"mobius-builder-pro", "builder_primary"}

_KNOWN_VISION_MODELS = {
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.5",
    "k2.6",
    "k2.6-code-preview",
    "kimi-k2.5",
    "kimi-k2.6",
    "mimo-v2.5",
    "mimo-v2-omni",
    "qwen3.5-plus",
    "qwen3.6-flash",
    "qwen3.6-plus",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
}
_CACHE_SENSITIVE_PREFIXES = ("qwen", "kimi", "k2.", "glm", "deepseek", "minimax", "mimo")
_REASONING_HINTS = ("gpt-5", "o1-", "o3-", "o4-", "qwen3", "kimi-k2", "glm-5", "deepseek", "claude-opus", "claude-sonnet")


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled", "是", "开启"}


def _redact(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:3]}***{text[-3:]}"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slug(value: Any, default: str = "provider") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = text.strip("-_")
    return text or default


def _split_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    elif isinstance(value, str):
        raw = re.split(r"[,\n]", value)
    else:
        raw = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_model_list(value: Any) -> list[str]:
    return _split_values(value)


def _normalize_choice_list(value: Any, allowed: tuple[str, ...], default: tuple[str, ...]) -> list[str]:
    values = []
    seen = set()
    for item in _split_values(value):
        normalized = item.strip().lower()
        if normalized in allowed and normalized not in seen:
            seen.add(normalized)
            values.append(normalized)
    return values or list(default)


def _normalize_priority(value: Any, default: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _sanitize_for_output(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key or "")
            if key_text.lower() in _SECRET_KEYS or any(token in key_text.lower() for token in ("token", "secret", "api_key")):
                result[key_text] = _redact(child)
            else:
                result[key_text] = _sanitize_for_output(child)
        return result
    if isinstance(value, list):
        return [_sanitize_for_output(item) for item in value]
    return value


def _json_response(payload: Any, *, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(_sanitize_for_output(payload), ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8"), "application/json; charset=utf-8"


def _load_mms_core():
    import mms_core

    return mms_core


def _policy_path_for_config(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.join(os.path.dirname(config_path), "model-policy.json")
    try:
        import mms_router

        return str(getattr(mms_router, "MODEL_POLICY_PATH", ""))
    except Exception:
        return ""


def _config_root_for_snapshot(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.dirname(config_path)
    try:
        from mms_state_io import resolve_mms_config_dir

        return resolve_mms_config_dir()
    except Exception:
        return ""


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import model_source_status

        return model_source_status(
            config_dir=config_root or None,
            command_name=f"{command_name} config source",
        )
    except Exception as exc:
        return {
            "schema": "mms.model_source_status.v1",
            "read_only": True,
            "status": "error",
            "error": str(exc),
            "config_root": config_root,
        }


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pretty_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _toml_text(payload: dict[str, Any]) -> str:
    try:
        import tomli_w

        return tomli_w.dumps(payload)
    except Exception:
        try:
            mms_core = _load_mms_core()
            if getattr(mms_core, "tomli_w", None) is not None:
                return mms_core.tomli_w.dumps(payload)
        except Exception:
            pass
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _diff_text(before: str, after: str, *, before_name: str, after_name: str) -> str:
    if before == after:
        return ""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def _provider_credentials_status(provider_id: str) -> dict[str, Any]:
    try:
        mms_core = _load_mms_core()
        creds = mms_core.load_provider_credentials(provider_id)
    except Exception:
        creds = {}
    return {
        "has_api_key": bool(_safe_text((creds or {}).get("api_key") or (creds or {}).get("openai_api_key"))),
        "base_url": _safe_text((creds or {}).get("base_url")),
        "openai_base_url": _safe_text((creds or {}).get("openai_base_url")),
        "anthropic_base_url": _safe_text((creds or {}).get("anthropic_base_url")),
    }


def _model_capability_defaults(model_id: str, policy_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _safe_text(model_id)
    lower = model.lower().rsplit("/", 1)[-1]
    caps = {
        "text": True,
        "vision": lower in _KNOWN_VISION_MODELS or lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-")),
        "tool_use": lower.startswith(("claude-", "gpt-", "o", "qwen", "kimi", "glm", "minimax", "gemini-")),
        "reasoning": any(hint in lower for hint in _REASONING_HINTS),
        "long_context": "1m" in lower or "long" in lower or lower.startswith(("qwen3", "kimi-k2", "gpt-5", "claude-")),
        "cache_sensitive": lower.startswith(_CACHE_SENSITIVE_PREFIXES),
    }
    if isinstance(policy_entry, dict):
        policy_caps = policy_entry.get("capabilities") if isinstance(policy_entry.get("capabilities"), dict) else {}
        for key in caps:
            if key in policy_caps and isinstance(policy_caps[key], bool):
                caps[key] = policy_caps[key]
            if key == "cache_sensitive" and isinstance(policy_caps.get("cache_sensitive_transport"), bool):
                caps[key] = policy_caps["cache_sensitive_transport"]
    return caps


def _provider_effective_model_rows(provider: dict[str, Any], policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    model_sources: dict[str, str] = {}
    provider_id = _safe_text(provider.get("id"))
    cached_raw: list[str] = []
    cached_source = "fallback"
    try:
        mms_core = _load_mms_core()
        cached = mms_core._load_probe_file_cache(provider_id, allow_stale=True)  # noqa: SLF001 - UI snapshot only
        if cached:
            cached_raw = _normalize_model_list(cached.get("raw_models") or cached.get("models") or [])
            cached_source = _safe_text(cached.get("base_source") or "remote") or "remote"
    except Exception:
        cached_raw = []
    for model in cached_raw or _normalize_model_list(provider.get("fallback_models")):
        model_sources.setdefault(model, cached_source if cached_raw else "fallback")
    for model in _normalize_model_list(provider.get("extra_models")):
        model_sources.setdefault(model, "extra")
    policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    hidden = set(_normalize_model_list(provider.get("hidden_models")))
    rows: list[dict[str, Any]] = []
    for model_id in sorted(model_sources.keys(), key=lambda item: item.lower()):
        entry = policy_models.get(model_id) if isinstance(policy_models.get(model_id), dict) else {}
        visible = model_id not in hidden
        if isinstance(entry, dict) and isinstance(entry.get("visible"), bool):
            visible = bool(entry.get("visible")) and visible
        rows.append(
            {
                "id": model_id,
                "source": model_sources.get(model_id) or "manual",
                "visible": visible,
                "favorite": bool(entry.get("favorite")) if isinstance(entry, dict) else False,
                "capabilities": _model_capability_defaults(model_id, entry if isinstance(entry, dict) else {}),
                "policy_touched": False,
            }
        )
    return rows


def _provider_stale_hidden_models(provider: dict[str, Any], model_rows: list[dict[str, Any]]) -> list[str]:
    current_ids = {str(row.get("id") or "").strip() for row in model_rows if isinstance(row, dict)}
    return [model for model in _normalize_model_list(provider.get("hidden_models")) if model not in current_ids]


def _provider_summary(provider: dict[str, Any], *, policy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = provider if isinstance(provider, dict) else {}
    provider_id = _safe_text(provider.get("id"))
    protocols = provider.get("protocols") if isinstance(provider.get("protocols"), list) else []
    supported_clis = provider.get("supported_clis") if isinstance(provider.get("supported_clis"), list) else []
    models = []
    for key in ("models", "fallback_models", "extra_models"):
        values = provider.get(key)
        if isinstance(values, list):
            models.extend(str(item) for item in values if item)
        elif isinstance(values, dict):
            models.extend(str(item) for item in values.keys() if item)
    creds = _provider_credentials_status(provider_id) if provider_id else {}
    config_openai_base = _safe_text(provider.get("openai_base_url") or provider.get("default_openai_base_url") or provider.get("base_url"))
    config_anthropic_base = _safe_text(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
    credential_openai_base = _safe_text(creds.get("openai_base_url") or creds.get("base_url"))
    credential_anthropic_base = _safe_text(creds.get("anthropic_base_url"))
    openai_base = config_openai_base or credential_openai_base
    anthropic_base = config_anthropic_base or credential_anthropic_base
    api_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key"))
    policy_payload = policy_payload if isinstance(policy_payload, dict) else {}
    model_rows = _provider_effective_model_rows(provider, policy_payload)
    return {
        "id": provider_id,
        "original_id": provider_id,
        "name": _safe_text(provider.get("name") or provider_id),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": provider.get("priority", 100),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "/models"),
        "protocols": [str(item) for item in protocols if item],
        "supported_clis": [str(item) for item in supported_clis if item],
        "openai_base_url": openai_base,
        "anthropic_base_url": anthropic_base,
        "effective_openai_base_url": openai_base,
        "effective_anthropic_base_url": anthropic_base,
        "config_openai_base_url": config_openai_base,
        "config_anthropic_base_url": config_anthropic_base,
        "openai_base_url_source": "config" if config_openai_base else ("credentials" if credential_openai_base else ""),
        "anthropic_base_url_source": "config" if config_anthropic_base else ("credentials" if credential_anthropic_base else ""),
        "api_key": "",
        "has_api_key": bool(api_key or creds.get("has_api_key")),
        "update_credentials": False,
        "fallback_models": _normalize_model_list(provider.get("fallback_models")),
        "extra_models": _normalize_model_list(provider.get("extra_models")),
        "hidden_models": _normalize_model_list(provider.get("hidden_models")),
        "stale_hidden_models": _provider_stale_hidden_models(provider, model_rows),
        "model_count": len(dict.fromkeys(models or [row["id"] for row in model_rows])),
        "models": model_rows,
    }


def _sanitized_mapping(payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if normalized.lower() in _SECRET_KEYS:
            result[normalized] = _redact(value)
        elif isinstance(value, dict):
            result[normalized] = _sanitized_mapping(value)
        elif isinstance(value, list):
            result[normalized] = [_sanitized_mapping(item) if isinstance(item, dict) else item for item in value]
        else:
            result[normalized] = value
    return result


def _normalize_agent_model_overrides(value: Any) -> dict[str, dict[str, str]]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, dict[str, str]] = {}
    for agent, entry in raw.items():
        agent_id = _safe_text(agent)
        if not agent_id:
            continue
        provider_id = ""
        model = ""
        if isinstance(entry, dict):
            provider_id = _safe_text(entry.get("provider_id") or entry.get("provider"))
            model = _safe_text(entry.get("model") or entry.get("model_id"))
        elif isinstance(entry, str):
            model = _safe_text(entry)
        if model:
            payload = {"model": model}
            if provider_id:
                payload["provider_id"] = provider_id
            result[agent_id] = payload
    return result


def _opencode_agent_preset(agent_id: str, category: str = "") -> str:
    text = _safe_text(agent_id).lower()
    category = _safe_text(category).lower()
    if "vision" in text or category == "vision":
        return "vision"
    if "bughunt" in text or "找茬" in category:
        return "bughunt"
    if "explore" in text or "探索" in category:
        return "explore"
    if "review" in text or "compliance" in text or "审查" in category:
        return "reviewer"
    if "spec" in text:
        return "spec"
    if "executor" in text:
        return "executor"
    if "fixer" in text:
        return "fixer"
    return "builder"


def _opencode_roster_defaults(profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(_opencode_agent_catalog(profile_id), 1):
        agent_id = _safe_text(row.get("agent"))
        if not agent_id:
            continue
        defaults[agent_id] = {
            "enabled": True,
            "preset": _opencode_agent_preset(agent_id, _safe_text(row.get("category"))),
            "priority": index * 10,
            "custom": False,
        }
    return defaults


def _normalize_opencode_agent_roster(value: Any, *, profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    defaults = _opencode_roster_defaults(profile_id)
    result: dict[str, dict[str, Any]] = {}
    for agent, entry in raw.items():
        agent_id = _safe_text(agent)
        if not agent_id or not isinstance(entry, dict):
            continue
        is_required_builder = agent_id in _OPENCODE_REQUIRED_BUILDER_AGENTS
        default = defaults.get(agent_id, {"enabled": True, "preset": "builder", "custom": False} if is_required_builder else {})
        preset = _safe_text(entry.get("preset") or entry.get("category") or default.get("preset") or "explore").lower()
        if preset not in _OPENCODE_ROSTER_PRESETS:
            preset = "explore"
        payload: dict[str, Any] = {"preset": preset}
        custom = bool(entry.get("custom") is True or (agent_id not in defaults and not is_required_builder))
        if custom:
            payload["custom"] = True
        if "enabled" in entry:
            enabled = _truthy(entry.get("enabled"), True)
            payload["enabled"] = True if is_required_builder and not enabled else enabled
        elif custom:
            payload["enabled"] = True
        provider_id = _safe_text(entry.get("provider_id") or entry.get("provider"))
        model = _safe_text(entry.get("model") or entry.get("model_id"))
        if provider_id and (model or custom):
            payload["provider_id"] = provider_id
        if model:
            payload["model"] = model
        try:
            priority = int(entry.get("priority"))
        except (TypeError, ValueError):
            priority = 0
        if priority > 0:
            payload["priority"] = priority
        description = _safe_text(entry.get("description"))
        if description:
            payload["description"] = description[:240]
        prompt = _safe_text(entry.get("prompt"))
        if prompt:
            payload["prompt"] = prompt[:4000]

        comparable = dict(payload)
        if not custom:
            if comparable.get("enabled", True) is True:
                comparable.pop("enabled", None)
            if comparable.get("preset") == default.get("preset"):
                comparable.pop("preset", None)
            if comparable.get("priority") == default.get("priority"):
                comparable.pop("priority", None)
        if comparable or custom:
            result[agent_id] = payload
    return result


def _strip_empty_provider_model_lists(cfg: dict[str, Any]) -> dict[str, Any]:
    """Keep WebUI saves from materializing absent empty fallback model lists."""
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if "fallback_models" in provider and not _normalize_model_list(provider.get("fallback_models")):
            provider.pop("fallback_models", None)
    return cfg


def _opencode_agent_catalog(profile_id: str = "agent") -> list[dict[str, Any]]:
    try:
        mms_core = _load_mms_core()
        specs = mms_core._opencode_lite_pro_specs(profile_id)  # noqa: SLF001 - setup UI mirrors launcher roster
    except Exception:
        specs = ()
    rows = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        agent = _safe_text(spec.get("agent"))
        if not agent:
            continue
        key = _safe_text(spec.get("key"))
        models = _normalize_model_list(spec.get("models"))
        category = "执行/协调"
        if "explore" in agent:
            category = "探索"
        elif "bughunt" in agent:
            category = "找茬"
        elif "vision" in agent:
            category = "Vision"
        elif "review" in agent or "compliance" in agent:
            category = "审查"
        elif "executor" in agent or "fixer" in agent:
            category = "执行"
        rows.append(
            {
                "agent": agent,
                "route_key": key,
                "category": category,
                "preset": _opencode_agent_preset(agent, category),
                "priority": len(rows) * 10 + 10,
                "default_models": models,
                "fallback_allowed": spec.get("gpt_fallback", True) is not False,
            }
        )
    return rows


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return a redacted, UI-friendly config snapshot; never mutates config."""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    policy_path = _policy_path_for_config(config_path)
    policy_payload = _load_json_file(policy_path)
    provider_rows = [_provider_summary(item, policy_payload=policy_payload) for item in providers if isinstance(item, dict)]
    vision_sidecar = cfg.get("vision_sidecar") if isinstance(cfg.get("vision_sidecar"), dict) else {}
    rescue = cfg.get("rescue") if isinstance(cfg.get("rescue"), dict) else {}
    provider_default = _safe_text((cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}).get("default"))
    presets = cfg.get("presets") if isinstance(cfg.get("presets"), dict) else {}
    coding_preset = presets.get("coding") if isinstance(presets.get("coding"), dict) else {}
    opencode_cfg = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    opencode_agent_models = _normalize_agent_model_overrides(opencode_cfg.get("agent_models") or opencode_cfg.get("agent_model_overrides"))
    opencode_profile = _safe_text(opencode_cfg.get("default_profile") or "agent")
    opencode_agent_catalog = _opencode_agent_catalog("agent")
    opencode = {
        "default_profile": opencode_profile,
        "recommended_profile": "agent",
        "profiles": ["agent", "omo", "raw"],
        "agent_models": opencode_agent_models,
        "agent_roster": _normalize_opencode_agent_roster(opencode_cfg.get("agent_roster"), profile_id="agent"),
        "agent_catalog": opencode_agent_catalog,
        "roster_presets": list(_OPENCODE_ROSTER_PRESETS),
        "vision_agents": ["mobius-vision-mimo", "mobius-vision-kimi", "mobius-vision-qwen"],
        "executor": "mobius-executor-gpt54",
        "release_gate": "mobius-reviewer-gpt55",
    }
    recommendations = []
    if not provider_rows:
        recommendations.append("先添加至少一个通道，然后再配置模型列表和 fallback。")
    if not vision_sidecar:
        recommendations.append("如果常用模型不直接支持图片，建议配置 vision sidecar。")
    if not _safe_text(rescue.get("fallback_model")):
        recommendations.append("建议先设置 rescue fallback model，失败时可以稳定交接。")
    if not any(row.get("anthropic_base_url") for row in provider_rows):
        recommendations.append("CN / dual-protocol 模型建议保留 Anthropic /v1/messages 路径，避免 cache 退化。")
    return {
        "schema": "mms.setup_web.snapshot.v2",
        "mode": "interactive_audited_save",
        "command": command_name,
        "setup_flow": build_setup_flow(),
        "test_contracts": build_test_contracts(),
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "providers": provider_rows,
        "provider_default": provider_default or (provider_rows[0]["id"] if provider_rows else ""),
        "vision_sidecar": _sanitized_mapping(vision_sidecar),
        "rescue": _sanitized_mapping(rescue),
        "runtime": {
            "preferred_cli": _safe_text(coding_preset.get("cli") or "opencode"),
            "coding_preset_model": _safe_text(coding_preset.get("model")),
        },
        "opencode": opencode,
        "policy_summary": {
            "path": policy_path,
            "model_count": len((policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}) or {}),
            "project_count": len((policy_payload.get("projects") if isinstance(policy_payload.get("projects"), dict) else {}) or {}),
        },
        "model_source_status": _model_source_status_for_snapshot(config_path, command_name=command_name),
        "references": build_reference_cards(),
        "recommendations": recommendations,
        "snippets": build_config_snippets(),
        "save_contract": {
            "requires_diff_preview": True,
            "requires_confirm_save": True,
            "confirm_phrase": "保存配置",
            "writes": ["config.toml", "credentials.sh(仅当输入新 key 并勾选更新凭据)", "model-policy.json"],
            "safety": "保存走 lock + backup + audit；已存在的写入目标会额外生成 *.bak；页面不会回显真实 API Key。",
        },
    }


def build_config_snippets() -> dict[str, str]:
    """Manual snippets shown in WebUI; callers choose whether to apply."""
    vision = """# config.toml: vision sidecar
[vision_sidecar]
enabled = true
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "direct-kimi"
model = "K2.6"

[[vision_sidecar.candidates]]
provider_id = "direct-qwen"
model = "qwen3.6-plus"
""".strip()
    rescue = """# config.toml: rescue fallback
[rescue]
fallback_model = "deepseek-v4-flash"
fallback_cli = "codex"
hot_fallback_enabled = false
""".strip()
    opencode = """# OpenCode launch examples
mms opencode --profile agent
mms opencode --profile omo
mms opencode-smoke --profile agent --health-summary
""".strip()
    policy = """// model-policy.json: visibility and capability overrides
{
  "models": {
    "qwen3.6-plus": {
      "visible": true,
      "favorite": true,
      "capabilities": {
        "text": true,
        "vision": true,
        "tool_use": true,
        "cache_sensitive_transport": true
      }
    },
    "retired-or-noisy-model": {
      "visible": false,
      "hide_in": ["mms", "hive", "pilot", "ant", "mobius"]
    }
  },
  "projects": {
    "mms": {
      "default_visible": true,
      "hidden_models": ["retired-or-noisy-model"],
      "favorite_models": ["qwen3.6-plus"]
    }
  }
}
""".strip()
    preferred_cli = """# config.toml: practical WebUI target
[presets.coding]
cli = "opencode"
model = "gpt-5.5"

[opencode]
default_profile = "agent"

[opencode.agent_models.mobius-explore-glm]
provider_id = "domestic"
model = "glm-5-turbo"
""".strip()
    return {
        "vision_sidecar": vision,
        "rescue": rescue,
        "opencode": opencode,
        "model_policy": policy,
        "preferred_cli": preferred_cli,
    }


def build_setup_flow() -> list[dict[str, Any]]:
    """Product IA for the visual setup flow; kept in snapshot for WebUI/Markdown."""
    return [
        {
            "id": "channel",
            "title": "1. 通道配置",
            "summary": "配置通道名称、URL、Key、协议和模型列表接口，然后拉取模型。",
            "fields": ["provider_id", "display_name", "openai_base_url", "anthropic_base_url", "api_key", "models_endpoint", "protocols"],
            "actions": ["fetch_models", "test_models_endpoint", "save_credentials_with_audit"],
        },
        {
            "id": "model_inventory",
            "title": "2. 模型列表",
            "summary": "查看拉取结果，隐藏噪音模型，像 NewAPI 一样手动补充模型。",
            "fields": ["visible", "favorite", "hidden_models", "manual_models", "model_aliases"],
            "actions": ["hide_selected", "add_manual_model", "copy_selected"],
        },
        {
            "id": "capability",
            "title": "3. 能力标记",
            "summary": "手动标记 text、vision/multimodal、tool use、reasoning、long context 和 cache-sensitive。",
            "fields": ["text", "vision", "long_context", "tool_use", "reasoning", "cache_sensitive"],
            "actions": ["apply_known_defaults", "save_model_policy"],
        },
        {
            "id": "validation",
            "title": "4. 模型测试",
            "summary": "测试拉取、指定模型 ping/pong、可选 simple chat，并记录 request path evidence。",
            "fields": ["stream", "protocol", "request_url", "request_path", "latency", "error"],
            "actions": ["test_list", "test_selected_model", "test_chat"],
        },
        {
            "id": "fallbacks",
            "title": "5. Fallback 设置",
            "summary": "设置 rescue fallback、vision sidecar/fallback 模型和 hot fallback 开关。",
            "fields": ["fallback_model", "fallback_cli", "vision_model", "vision_candidates", "hot_fallback_enabled"],
            "actions": ["preview_config_diff", "run_non_live_smoke"],
        },
        {
            "id": "runtime",
            "title": "6. 运行默认值",
            "summary": "设置 preferred CLI、coding preset 和 OpenCode Multi-Agent profile。",
            "fields": ["preferred_cli", "opencode_profile", "executor", "reviewer", "explore", "vision_agents"],
            "actions": ["preview_launch", "save_audited"],
        },
    ]


def build_test_contracts() -> list[dict[str, str]]:
    return [
        {
            "id": "models_endpoint",
            "title": "模型列表测试",
            "method": "GET /models 或配置的 models_endpoint",
            "result": "模型 ID、endpoint 状态、协议提示和脱敏 transport evidence",
        },
        {
            "id": "model_ping",
            "title": "指定模型 smoke",
            "method": "通过选定 protocol 发送最小非流式 prompt",
            "result": "ok/fail、latency、response shape、request_url/request_path",
        },
        {
            "id": "simple_chat",
            "title": "简单 chat 测试",
            "method": "一条 user message，限制短回答",
            "result": "回复预览 + cache_transport_evidence.v1",
        },
        {
            "id": "vision_probe",
            "title": "Vision probe",
            "method": "仅当模型标记 vision-capable 时发小图片/OCR 请求",
            "result": "确认直接 vision 支持，或建议启用 sidecar fallback",
        },
    ]


def build_reference_cards() -> list[dict[str, str]]:
    return [
        {
            "title": "模型配置契约",
            "path": "docs/MODEL_CONFIG_CONTRACT.md",
            "summary": "Router / Lineup / Profile / Policy 四份配置的职责边界。",
        },
        {
            "title": "用户偏好 allowlist",
            "path": "docs/MMS_USER_PREFERENCES.md",
            "summary": "哪些日常偏好适合 preferences.toml，哪些真实配置必须 human gate。",
        },
        {
            "title": "OpenCode Lite Pro",
            "path": "docs/OPENCODE_LITE_LAUNCHER.md",
            "summary": "OpenSpec Multi、GPT executor、国产只读 explore/bug-hunt 的当前策略。",
        },
        {
            "title": "能力校准快照",
            "path": "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.md",
            "summary": "当前模型能力证据输入，WebUI 默认能力标记会参考这些本地事实。",
        },
    ]


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    providers = snapshot.get("providers") or []
    lines = [
        "# MMS Setup Configuration",
        "",
        f"- mode: `{snapshot.get('mode')}`",
        f"- config: `{snapshot.get('paths', {}).get('config') or '-'}`",
        f"- model_policy: `{snapshot.get('paths', {}).get('model_policy') or '-'}`",
        f"- preferences: `{snapshot.get('paths', {}).get('preferences') or '-'}`",
        "",
        "## Providers",
    ]
    if providers:
        for item in providers:
            lines.append(
                "- `{id}` enabled={enabled} protocols={protocols} clis={clis} models={models} key={key}".format(
                    id=item.get("id") or "-",
                    enabled=item.get("enabled"),
                    protocols=",".join(item.get("protocols") or []) or "-",
                    clis=",".join(item.get("supported_clis") or []) or "-",
                    models=item.get("model_count", 0),
                    key="set" if item.get("has_api_key") else "missing",
                )
            )
    else:
        lines.append("- No providers found.")
    flow = snapshot.get("setup_flow") or []
    if flow:
        lines.extend(["", "## Visual Setup Flow"])
        for item in flow:
            lines.append(f"- **{item.get('title')}**: {item.get('summary')}")
            actions = ", ".join(item.get("actions") or [])
            if actions:
                lines.append(f"  - actions: `{actions}`")
    tests = snapshot.get("test_contracts") or []
    if tests:
        lines.extend(["", "## Model Test Contracts"])
        for item in tests:
            lines.append(f"- **{item.get('title')}**: {item.get('method')} -> {item.get('result')}")
    snippets = snapshot.get("snippets") or {}
    lines.extend(["", "## Vision Sidecar", "", "```toml", snippets.get("vision_sidecar", ""), "```"])
    lines.extend(["", "## Rescue Fallback", "", "```toml", snippets.get("rescue", ""), "```"])
    lines.extend(["", "## Model Visibility And Capability Policy", "", "```json", snippets.get("model_policy", ""), "```"])
    lines.extend(["", "## Preferred CLI", "", "```toml", snippets.get("preferred_cli", ""), "```"])
    lines.extend(["", "## OpenCode", "", "```bash", snippets.get("opencode", ""), "```"])
    recommendations = snapshot.get("recommendations") or []
    if recommendations:
        lines.extend(["", "## Recommendations"])
        lines.extend(f"- {item}" for item in recommendations)
    lines.extend(
        [
            "",
            "## Safety",
            "- WebUI writes are interactive only: preview diff, check confirmation, then save.",
            "- Saves use MMS config lock, backup, and config audit log.",
            "- API keys are accepted only in POST bodies and are never echoed back.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _extract_draft(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
    return draft if isinstance(draft, dict) else {}


def _copy_existing_provider(existing: dict[str, Any] | None, provider_payload: dict[str, Any]) -> dict[str, Any]:
    provider = dict(existing or {})
    provider_id = _slug(provider_payload.get("id") or provider_payload.get("original_id") or provider.get("id"), "provider")
    provider["id"] = provider_id
    provider["name"] = _safe_text(provider_payload.get("name") or provider_id)
    provider["enabled"] = _truthy(provider_payload.get("enabled"), True)
    role = _safe_text(provider_payload.get("role") or provider.get("role") or "auto").lower()
    provider["role"] = role if role in _ALLOWED_ROLES else "auto"
    provider["priority"] = _normalize_priority(provider_payload.get("priority", provider.get("priority", 100)))
    provider["protocols"] = _normalize_choice_list(provider_payload.get("protocols"), _ALLOWED_PROTOCOLS, _ALLOWED_PROTOCOLS)
    provider["supported_clis"] = _normalize_choice_list(provider_payload.get("supported_clis"), _ALLOWED_CLIS, ("claude", "codex", "opencode"))
    endpoint = _safe_text(provider_payload.get("models_endpoint") or provider.get("models_endpoint") or "/models")
    if endpoint.lower() in {"manual", "none", "off"}:
        endpoint = "manual"
    elif endpoint and not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    provider["models_endpoint"] = endpoint or "/models"
    if "openai_base_url" in provider_payload or "base_url" in provider_payload:
        openai_base = _safe_text(provider_payload.get("openai_base_url") or provider_payload.get("base_url"))
        if (
            _safe_text(provider_payload.get("openai_base_url_source")) == "credentials"
            and not _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url"))
            and openai_base == _safe_text(provider_payload.get("effective_openai_base_url"))
        ):
            openai_base = ""
    else:
        openai_base = _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url"))
    if "anthropic_base_url" in provider_payload:
        anthropic_base = _safe_text(provider_payload.get("anthropic_base_url"))
        if (
            _safe_text(provider_payload.get("anthropic_base_url_source")) == "credentials"
            and not _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
            and anthropic_base == _safe_text(provider_payload.get("effective_anthropic_base_url"))
        ):
            anthropic_base = ""
    else:
        anthropic_base = _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
    if openai_base:
        provider["default_openai_base_url"] = openai_base.rstrip("/")
    elif "default_openai_base_url" in provider:
        provider["default_openai_base_url"] = ""
    else:
        provider.pop("default_openai_base_url", None)
    if anthropic_base:
        provider["default_anthropic_base_url"] = anthropic_base.rstrip("/")
    elif "default_anthropic_base_url" in provider:
        provider["default_anthropic_base_url"] = ""
    else:
        provider.pop("default_anthropic_base_url", None)
    provider["fallback_models"] = _normalize_model_list(provider_payload.get("fallback_models"))
    provider["extra_models"] = _normalize_model_list(provider_payload.get("extra_models"))
    provider["hidden_models"] = _normalize_model_list(provider_payload.get("hidden_models"))
    return provider


def _build_model_policy_from_draft(policy_before: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    original_policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy.setdefault("version", 1)
    policy.setdefault("description", "User-maintained model visibility and preference policy. MMS never stores provider secrets here.")
    models = policy.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        policy["models"] = models
    providers = draft.get("providers") if isinstance(draft.get("providers"), list) else []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        hidden = set(_normalize_model_list(provider.get("hidden_models")))
        caps_map = dict(provider.get("model_capabilities") if isinstance(provider.get("model_capabilities"), dict) else {})
        rows = provider.get("models") if isinstance(provider.get("models"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _safe_text(row.get("id"))
            if not model_id:
                continue
            touched = row.get("policy_touched") is True or row.get("touched") is True
            if not touched:
                continue
            caps_map.setdefault(model_id, row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {})
            if model_id in hidden or row.get("visible") is False:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = False
            elif row.get("visible") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = True
            if row.get("favorite") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["favorite"] = True
            elif row.get("favorite") is False and isinstance(models.get(model_id), dict) and "favorite" in models[model_id]:
                models[model_id]["favorite"] = False
        for model_id, caps in caps_map.items():
            model_id = _safe_text(model_id)
            if not model_id or not isinstance(caps, dict):
                continue
            entry = models.setdefault(model_id, {})
            if not isinstance(entry, dict):
                entry = {}
                models[model_id] = entry
            cap_payload = entry.setdefault("capabilities", {})
            if not isinstance(cap_payload, dict):
                cap_payload = {}
                entry["capabilities"] = cap_payload
            for key in ("text", "vision", "tool_use", "reasoning", "long_context"):
                if isinstance(caps.get(key), bool):
                    cap_payload[key] = bool(caps[key])
            if isinstance(caps.get("cache_sensitive"), bool):
                cap_payload["cache_sensitive_transport"] = bool(caps["cache_sensitive"])
    def comparable(payload: dict[str, Any]) -> dict[str, Any]:
        copy_payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        copy_payload.pop("updated_at", None)
        return copy_payload

    if _mapping_digest(comparable(policy)) != _mapping_digest(comparable(original_policy)):
        policy["updated_at"] = _now_iso()
    elif isinstance(original_policy, dict) and "updated_at" in original_policy:
        policy["updated_at"] = original_policy["updated_at"]
    return policy


def _provider_urls(provider: dict[str, Any] | None) -> dict[str, str]:
    provider = provider if isinstance(provider, dict) else {}
    return {
        "openai": _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url")),
        "anthropic": _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url")),
    }


def _provider_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    return {
        _safe_text(provider.get("id")): provider
        for provider in providers
        if isinstance(provider, dict) and _safe_text(provider.get("id"))
    }


def _provider_default_id(cfg: dict[str, Any]) -> str:
    provider_cfg = cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}
    return _safe_text(provider_cfg.get("default"))


def _mapping_digest(payload: Any) -> str:
    return json.dumps(_sanitize_for_output(payload if isinstance(payload, dict) else {}), ensure_ascii=False, sort_keys=True)


def _build_review_summary(
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    policy_before: dict[str, Any],
    policy_after: dict[str, Any],
    credential_updates: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a human-readable save review; raw diff remains the audit detail."""
    items: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    before_providers = _provider_by_id(current_cfg)
    after_providers = _provider_by_id(next_cfg)
    before_ids = set(before_providers)
    after_ids = set(after_providers)

    def add_item(kind: str, title: str, detail: str, *, provider_id: str = "", level: str = "info", meta: dict[str, Any] | None = None) -> None:
        items.append({
            "kind": kind,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
            "meta": meta or {},
        })

    def add_risk(risk_id: str, title: str, detail: str, *, level: str = "warn", provider_id: str = "") -> None:
        risks.append({
            "id": risk_id,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
        })

    for provider_id in sorted(after_ids - before_ids):
        add_item("provider_added", "新增通道", f"`{provider_id}` 将被加入配置。", provider_id=provider_id)
    for provider_id in sorted(before_ids - after_ids):
        add_item("provider_removed", "删除通道", f"`{provider_id}` 将从配置里移除。", provider_id=provider_id, level="danger")
        add_risk("provider_removed", "删除通道", f"`{provider_id}` 删除后新 session 不会再使用该通道。", level="danger", provider_id=provider_id)

    before_default = _provider_default_id(current_cfg)
    after_default = _provider_default_id(next_cfg)
    if before_default != after_default:
        add_item("default_provider", "默认通道变化", f"`{before_default or '-'}` -> `{after_default or '-'}`", level="warn")
        add_risk("default_provider_changed", "默认通道变化", "默认 provider 改变会影响后续新 session 的默认路由。", provider_id=after_default)

    hidden_removed_total = 0
    hidden_added_total = 0
    for provider_id in sorted(after_ids):
        before = before_providers.get(provider_id, {})
        after = after_providers[provider_id]
        before_urls = _provider_urls(before)
        after_urls = _provider_urls(after)
        if provider_id in before_ids:
            for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
                if before_urls[field] == after_urls[field]:
                    continue
                add_item(
                    "provider_url",
                    f"通道 URL 变化：{provider_id}",
                    f"{label}: `{before_urls[field] or '-'}` -> `{after_urls[field] or '-'}`",
                    provider_id=provider_id,
                    level="warn",
                    meta={"field": field, "before": before_urls[field], "after": after_urls[field]},
                )
        elif after_urls["openai"] or after_urls["anthropic"]:
            url_parts = []
            if after_urls["openai"]:
                url_parts.append(f"OpenAI: `{after_urls['openai']}`")
            if after_urls["anthropic"]:
                url_parts.append(f"Anthropic: `{after_urls['anthropic']}`")
            add_item("provider_url", f"通道 URL：{provider_id}", "；".join(url_parts), provider_id=provider_id)
        url_changed_by_field: dict[str, bool] = {}
        for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
            url_changed_by_field[field] = before_urls[field] != after_urls[field]
            url = after_urls[field]
            if url.lower().startswith("http://") and (provider_id not in before_ids or url_changed_by_field[field]):
                add_risk("http_base_url", "HTTP URL", f"`{provider_id}` 的 {label} 使用 `http://`，请确认这是内网/代理预期。", provider_id=provider_id)
        before_enabled = before.get("enabled", True) is not False
        after_enabled = after.get("enabled", True) is not False
        became_empty = bool(before_urls["openai"] or before_urls["anthropic"]) and not after_urls["openai"] and not after_urls["anthropic"]
        became_enabled = not before_enabled and after_enabled
        if after_enabled and not after_urls["openai"] and not after_urls["anthropic"] and (provider_id not in before_ids or became_empty or became_enabled):
            add_risk("empty_provider_url", "启用通道缺少 URL", f"`{provider_id}` 已启用但没有 OpenAI/Anthropic URL。", provider_id=provider_id)
        before_hidden = set(_normalize_model_list(before.get("hidden_models")))
        after_hidden = set(_normalize_model_list(after.get("hidden_models")))
        removed = sorted(before_hidden - after_hidden, key=str.lower)
        added = sorted(after_hidden - before_hidden, key=str.lower)
        hidden_removed_total += len(removed)
        hidden_added_total += len(added)
        if removed:
            preview = ", ".join(removed[:8])
            suffix = f" 等 {len(removed)} 个" if len(removed) > 8 else ""
            add_item("hidden_removed", f"清理 hidden_models：{provider_id}", f"将移除 `{preview}`{suffix}", provider_id=provider_id, meta={"models": removed})
        if added:
            preview = ", ".join(added[:8])
            suffix = f" 等 {len(added)} 个" if len(added) > 8 else ""
            add_item("hidden_added", f"新增隐藏模型：{provider_id}", f"将隐藏 `{preview}`{suffix}", provider_id=provider_id, meta={"models": added})
        before_extra = set(_normalize_model_list(before.get("extra_models")))
        after_extra = set(_normalize_model_list(after.get("extra_models")))
        if before_extra != after_extra:
            add_item(
                "extra_models",
                f"手动模型变化：{provider_id}",
                f"新增 {len(after_extra - before_extra)} 个，移除 {len(before_extra - after_extra)} 个。",
                provider_id=provider_id,
            )

    rescue_before = current_cfg.get("rescue") if isinstance(current_cfg.get("rescue"), dict) else {}
    rescue_after = next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {}
    if _mapping_digest(rescue_before) != _mapping_digest(rescue_after):
        add_item("rescue", "Rescue fallback 变化", f"`{_safe_text(rescue_before.get('fallback_model')) or '-'}` -> `{_safe_text(rescue_after.get('fallback_model')) or '-'}`")

    vision_before = current_cfg.get("vision_sidecar") if isinstance(current_cfg.get("vision_sidecar"), dict) else {}
    vision_after = next_cfg.get("vision_sidecar") if isinstance(next_cfg.get("vision_sidecar"), dict) else {}
    if _mapping_digest(vision_before) != _mapping_digest(vision_after):
        before_ref = f"{_safe_text(vision_before.get('provider_id') or vision_before.get('provider')) or '-'}/{_safe_text(vision_before.get('model') or vision_before.get('vision_model')) or '-'}"
        after_ref = f"{_safe_text(vision_after.get('provider_id') or vision_after.get('provider')) or '-'}/{_safe_text(vision_after.get('model') or vision_after.get('vision_model')) or '-'}"
        add_item("vision_sidecar", "Vision sidecar 变化", f"`{before_ref}` -> `{after_ref}`")

    opencode_before = current_cfg.get("opencode") if isinstance(current_cfg.get("opencode"), dict) else {}
    opencode_after = next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {}
    if _safe_text(opencode_before.get("default_profile")) != _safe_text(opencode_after.get("default_profile")):
        add_item("opencode_profile", "OpenCode profile 变化", f"`{_safe_text(opencode_before.get('default_profile')) or '-'}` -> `{_safe_text(opencode_after.get('default_profile')) or '-'}`")
    before_agents = _normalize_agent_model_overrides(opencode_before.get("agent_models") or opencode_before.get("agent_model_overrides"))
    after_agents = _normalize_agent_model_overrides(opencode_after.get("agent_models") or opencode_after.get("agent_model_overrides"))
    if _mapping_digest(before_agents) != _mapping_digest(after_agents):
        added_agents = sorted(set(after_agents) - set(before_agents))
        removed_agents = sorted(set(before_agents) - set(after_agents))
        updated_agents = sorted(
            agent for agent in (set(before_agents) & set(after_agents))
            if _mapping_digest(before_agents.get(agent)) != _mapping_digest(after_agents.get(agent))
        )
        changed_agents = sorted(
            set(added_agents) | set(removed_agents) | set(updated_agents)
        )
        preview = ", ".join(changed_agents[:8])
        suffix = f" 等 {len(changed_agents)} 个" if len(changed_agents) > 8 else ""
        buckets = []
        if added_agents:
            buckets.append(f"新增 {len(added_agents)}")
        if removed_agents:
            buckets.append(f"移除 {len(removed_agents)}")
        if updated_agents:
            buckets.append(f"修改 {len(updated_agents)}")
        add_item(
            "opencode_agent_models",
            "OpenCode agent 模型覆盖变化",
            f"{'，'.join(buckets)}；agent：{preview}{suffix}",
            meta={
                "agents": changed_agents,
                "added_agents": added_agents,
                "removed_agents": removed_agents,
                "updated_agents": updated_agents,
            },
        )
    before_roster = _normalize_opencode_agent_roster(opencode_before.get("agent_roster"), profile_id="agent")
    after_roster = _normalize_opencode_agent_roster(opencode_after.get("agent_roster"), profile_id="agent")
    if _mapping_digest(before_roster) != _mapping_digest(after_roster):
        changed_roster = sorted(
            agent for agent in (set(before_roster) | set(after_roster))
            if _mapping_digest(before_roster.get(agent)) != _mapping_digest(after_roster.get(agent))
        )
        disabled = sorted(agent for agent, entry in after_roster.items() if entry.get("enabled") is False)
        custom = sorted(agent for agent, entry in after_roster.items() if entry.get("custom") is True)
        parts = []
        if disabled:
            parts.append(f"禁用 {len(disabled)}")
        if custom:
            parts.append(f"自定义 {len(custom)}")
        if not parts:
            parts.append(f"更新 {len(changed_roster)}")
        preview = ", ".join(changed_roster[:8])
        suffix = f" 等 {len(changed_roster)} 个" if len(changed_roster) > 8 else ""
        add_item(
            "opencode_agent_roster",
            "OpenCode roster 变化",
            f"{'，'.join(parts)}；agent：{preview}{suffix}",
            meta={"agents": changed_roster, "disabled_agents": disabled, "custom_agents": custom},
        )

    if credential_updates:
        provider_ids = ", ".join(item["provider_id"] for item in credential_updates)
        add_item("credentials", "凭据写入", f"将更新 credentials.sh：{provider_ids}", level="warn")
        add_risk("credential_update", "凭据写入", "只有输入了新 API Key 且勾选更新凭据的通道会写 credentials.sh。", level="warn")

    policy_before_models = policy_before.get("models") if isinstance(policy_before.get("models"), dict) else {}
    policy_after_models = policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}
    if _mapping_digest({"models": policy_before_models}) != _mapping_digest({"models": policy_after_models}):
        changed_models = sorted(set(policy_before_models) ^ set(policy_after_models))
        common_changed = sorted(
            model for model in (set(policy_before_models) & set(policy_after_models))
            if _mapping_digest(policy_before_models.get(model)) != _mapping_digest(policy_after_models.get(model))
        )
        total = len(changed_models) + len(common_changed)
        add_item("model_policy", "模型能力/偏好策略变化", f"将更新 {total} 个 model-policy 条目。")

    if not items:
        add_item("no_change", "没有配置变化", "当前草稿与已加载配置一致。")
    return {
        "schema": "mms.setup_web.review_summary.v1",
        "counts": {
            "items": len(items),
            "risks": len(risks),
            "providers_before": len(before_ids),
            "providers_after": len(after_ids),
            "hidden_removed": hidden_removed_total,
            "hidden_added": hidden_added_total,
            "credential_updates": len(credential_updates),
        },
        "items": items,
        "risks": risks,
    }


def build_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    include_secrets: bool = False,
) -> dict[str, Any]:
    current_cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    draft = _extract_draft(payload or {})
    providers_payload = draft.get("providers") if isinstance(draft.get("providers"), list) else []
    existing_by_id = {str(item.get("id") or ""): item for item in current_cfg.get("providers", []) if isinstance(item, dict)}
    next_providers: list[dict[str, Any]] = []
    credential_updates: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for provider_payload in providers_payload:
        if not isinstance(provider_payload, dict):
            continue
        original_id = _safe_text(provider_payload.get("original_id") or provider_payload.get("id"))
        provider = _copy_existing_provider(existing_by_id.get(original_id), provider_payload)
        next_providers.append(provider)
        if _truthy(provider_payload.get("update_credentials"), False):
            api_key = _safe_text(provider_payload.get("api_key"))
            openai_base = _safe_text(provider_payload.get("openai_base_url") or provider_payload.get("base_url") or provider.get("default_openai_base_url"))
            anthropic_base = _safe_text(provider_payload.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
            if not api_key:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 API Key 为空。")
            if not openai_base and not anthropic_base:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 URL 为空。")
            credential_updates.append(
                {
                    "provider_id": provider["id"],
                    "base_url": (openai_base or anthropic_base).rstrip("/"),
                    "openai_base_url": openai_base.rstrip("/"),
                    "anthropic_base_url": anthropic_base.rstrip("/"),
                    "api_key": api_key if include_secrets else _redact(api_key),
                }
            )
        if provider.get("anthropic_base_url") and "anthropic_messages" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 Anthropic URL，但 protocols 未包含 anthropic_messages。")
        if provider.get("openai_base_url") and "openai_chat_completions" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 OpenAI URL，但 protocols 未包含 openai_chat_completions。")

    if providers_payload:
        seen: set[str] = set()
        deduped = []
        for provider in next_providers:
            provider_id = provider.get("id")
            if provider_id in seen:
                errors.append(f"通道 ID 重复: {provider_id}")
                continue
            seen.add(provider_id)
            deduped.append(provider)
        next_providers = deduped
    else:
        next_providers = list(current_cfg.get("providers") or [])

    next_cfg = copy.deepcopy(current_cfg)
    if next_providers:
        next_cfg["providers"] = next_providers
    provider_default = _safe_text(draft.get("provider_default") or (next_cfg.get("provider") if isinstance(next_cfg.get("provider"), dict) else {}).get("default"))
    provider_ids = {provider.get("id") for provider in next_providers if isinstance(provider, dict)}
    if provider_default and provider_default not in provider_ids:
        warnings.append(f"默认通道 {provider_default} 不在通道列表中，保存时会使用第一个通道。")
        provider_default = ""
    if next_providers:
        next_cfg["provider"] = {"default": provider_default or str(next_providers[0].get("id"))}

    rescue_payload = draft.get("rescue") if isinstance(draft.get("rescue"), dict) else {}
    if rescue_payload:
        rescue = dict(next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {})
        fallback_model = _safe_text(rescue_payload.get("fallback_model"))
        fallback_cli = _safe_text(rescue_payload.get("fallback_cli"))
        if fallback_model:
            rescue["fallback_model"] = fallback_model
            if fallback_cli:
                rescue["fallback_cli"] = fallback_cli
            else:
                rescue.pop("fallback_cli", None)
            rescue["hot_fallback_enabled"] = _truthy(rescue_payload.get("hot_fallback_enabled"), False)
        else:
            rescue.pop("fallback_model", None)
            rescue.pop("fallback_cli", None)
            rescue.pop("hot_fallback_enabled", None)
        if rescue:
            next_cfg["rescue"] = rescue
        else:
            next_cfg.pop("rescue", None)

    vision_payload = draft.get("vision_sidecar") if isinstance(draft.get("vision_sidecar"), dict) else {}
    if vision_payload:
        vision = {
            "enabled": _truthy(vision_payload.get("enabled"), True),
            "provider_id": _safe_text(vision_payload.get("provider_id") or vision_payload.get("provider")),
            "model": _safe_text(vision_payload.get("model") or vision_payload.get("vision_model")),
        }
        candidates = []
        for item in vision_payload.get("candidates") or []:
            if not isinstance(item, dict):
                continue
            provider_id = _safe_text(item.get("provider_id") or item.get("provider"))
            model = _safe_text(item.get("model") or item.get("vision_model"))
            if provider_id and model:
                candidates.append({"provider_id": provider_id, "model": model})
        if candidates:
            vision["candidates"] = candidates
        if vision["provider_id"] or vision["model"] or candidates or vision["enabled"] is False:
            next_cfg["vision_sidecar"] = vision

    runtime_payload = draft.get("runtime") if isinstance(draft.get("runtime"), dict) else {}
    preferred_cli = _safe_text(runtime_payload.get("preferred_cli"))
    if preferred_cli:
        if preferred_cli not in _ALLOWED_CLIS:
            errors.append(f"preferred CLI 不支持: {preferred_cli}")
        else:
            presets = dict(next_cfg.get("presets") if isinstance(next_cfg.get("presets"), dict) else {})
            coding = dict(presets.get("coding") if isinstance(presets.get("coding"), dict) else {})
            coding_model = _safe_text(runtime_payload.get("coding_preset_model"))
            if coding or preferred_cli != "opencode" or coding_model:
                coding["cli"] = preferred_cli
            if coding_model:
                coding["model"] = coding_model
            if coding:
                presets["coding"] = coding
                next_cfg["presets"] = presets

    opencode_payload = draft.get("opencode") if isinstance(draft.get("opencode"), dict) else {}
    default_profile = _safe_text(opencode_payload.get("default_profile"))
    agent_model_overrides = _normalize_agent_model_overrides(opencode_payload.get("agent_models") or opencode_payload.get("agent_model_overrides"))
    agent_roster = _normalize_opencode_agent_roster(opencode_payload.get("agent_roster"), profile_id="agent")
    if default_profile or "agent_models" in opencode_payload or "agent_model_overrides" in opencode_payload or "agent_roster" in opencode_payload:
        opencode_cfg = dict(next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {})
        current_default_profile = _safe_text(opencode_cfg.get("default_profile"))
        if default_profile and (current_default_profile or default_profile != "agent"):
            opencode_cfg["default_profile"] = default_profile
        if agent_model_overrides:
            opencode_cfg["agent_models"] = agent_model_overrides
            opencode_cfg.pop("agent_model_overrides", None)
        else:
            opencode_cfg.pop("agent_models", None)
            opencode_cfg.pop("agent_model_overrides", None)
        if agent_roster:
            opencode_cfg["agent_roster"] = agent_roster
        else:
            opencode_cfg.pop("agent_roster", None)
        if opencode_cfg:
            next_cfg["opencode"] = opencode_cfg
        else:
            next_cfg.pop("opencode", None)

    policy_path = _policy_path_for_config(config_path)
    policy_before = _load_json_file(policy_path)
    if not policy_before:
        policy_before = {
            "version": 1,
            "updated_at": _now_iso(),
            "description": "User-maintained model visibility and preference policy. MMS never stores provider secrets here.",
            "models": {},
            "projects": {},
        }
    policy_after = _build_model_policy_from_draft(policy_before, draft)

    try:
        mms_core = _load_mms_core()
        if hasattr(mms_core, "_ensure_provider_config"):
            next_cfg, _ = mms_core._ensure_provider_config(next_cfg)  # noqa: SLF001 - reuse existing normalization
    except Exception:
        pass
    next_cfg = _strip_empty_provider_model_lists(next_cfg)

    before_config_text = _toml_text(_sanitize_for_output(current_cfg))
    after_config_text = _toml_text(_sanitize_for_output(next_cfg))
    before_policy_text = _pretty_json(_sanitize_for_output(policy_before))
    after_policy_text = _pretty_json(_sanitize_for_output(policy_after))
    diffs = {
        "config_toml": _diff_text(before_config_text, after_config_text, before_name="config.toml(before)", after_name="config.toml(after)"),
        "model_policy_json": _diff_text(before_policy_text, after_policy_text, before_name="model-policy.json(before)", after_name="model-policy.json(after)"),
        "credentials": "\n".join(f"credentials.sh: update provider {item['provider_id']} (secret hidden)" for item in credential_updates),
    }
    review_summary = _build_review_summary(current_cfg, next_cfg, policy_before, policy_after, credential_updates)
    return {
        "schema": "mms.setup_web.plan.v1",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "config": next_cfg,
        "model_policy": policy_after,
        "credential_updates": credential_updates,
        "diffs": diffs,
        "review_summary": review_summary,
        "summary": {
            "providers": len(next_cfg.get("providers") or []),
            "credential_updates": len(credential_updates),
            "policy_models": len((policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}) or {}),
            "will_write_config": bool(diffs["config_toml"]),
            "will_write_policy": bool(diffs["model_policy_json"]),
            "will_write_credentials": bool(credential_updates),
        },
    }


def _latest_audit_rows(config_path: str, limit: int = 8) -> list[dict[str, Any]]:
    try:
        mms_core = _load_mms_core()
        audit_path = mms_core._config_audit_path(config_path)  # noqa: SLF001
        if not os.path.exists(audit_path):
            return []
        rows = []
        with open(audit_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]
    except Exception:
        return []


def _copy_backup_file(target_path: str, *, config_path: str, label: str) -> str:
    if not target_path or not os.path.exists(target_path):
        return ""
    mms_core = _load_mms_core()
    backup_root = mms_core._config_backup_root(config_path)  # noqa: SLF001
    backup_dir = os.path.join(backup_root, f"{label}-{mms_core._local_now_slug()}")  # noqa: SLF001
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(target_path))
    shutil.copy2(target_path, backup_path)
    shutil.copy2(target_path, f"{backup_path}.bak")
    return backup_path


def _bak_path_for_backup(backup_path: str) -> str:
    bak_path = f"{backup_path}.bak" if backup_path else ""
    return bak_path if bak_path and os.path.exists(bak_path) else ""


def _append_audit(*, config_path: str, target_path: str, backup_path: str, reason: str, before_sha1: str, after_sha1: str, function: str) -> None:
    mms_core = _load_mms_core()
    mms_core._append_config_audit_entry(  # noqa: SLF001
        {
            "timestamp": mms_core._iso_now(),  # noqa: SLF001
            "reason": reason,
            "target_path": os.path.abspath(target_path),
            "backup_path": backup_path,
            "caller_path": os.path.abspath(__file__),
            "caller_line": 0,
            "caller_function": function,
            "pid": os.getpid(),
            "before_sha1": before_sha1,
            "after_sha1": after_sha1,
        },
        config_path=config_path,
    )


def _save_provider_credentials_audited(update: dict[str, str], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    target_path = getattr(mms_core, "CREDENTIALS_PATH")
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        backup_path = _copy_backup_file(target_path, config_path=lock_path, label="credentials-write")
        mms_core.save_provider_credentials(
            update["provider_id"],
            update.get("base_url", ""),
            update.get("api_key", ""),
            openai_base_url=update.get("openai_base_url", ""),
            anthropic_base_url=update.get("anthropic_base_url", ""),
        )
        after_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=target_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_credentials",
        )
    return {"provider_id": update["provider_id"], "target_path": os.path.abspath(target_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def _write_model_policy_audited(policy_path: str, payload: dict[str, Any], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        backup_path = _copy_backup_file(policy_path, config_path=lock_path, label="model-policy-write")
        os.makedirs(os.path.dirname(policy_path), exist_ok=True)
        tmp_path = f"{policy_path}.tmp-{os.getpid()}-{time.time_ns()}"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(_pretty_json(payload))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, policy_path)
        os.chmod(policy_path, 0o600)
        after_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=policy_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_model_policy",
        )
    return {"target_path": os.path.abspath(policy_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def apply_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_save"), False):
        return {"ok": False, "errors": ["保存前必须勾选确认保存。"], "status": "blocked"}
    if _safe_text(payload.get("confirm_phrase")) != "保存配置":
        return {"ok": False, "errors": ["确认文字必须输入：保存配置"], "status": "blocked"}
    plan = build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, include_secrets=True)
    if not plan.get("ok"):
        return {
            "ok": False,
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "status": "blocked",
            "plan": _sanitize_for_output(plan),
        }

    mms_core = _load_mms_core()
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:interactive-save"
    target_config_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    save_report: dict[str, Any] = {"config": {}, "credentials": [], "model_policy": {}, "routes_export": False}
    webui_config_backup_path = _copy_backup_file(target_config_path, config_path=target_config_path, label="setup-web-config-write")
    mms_core.save_config(plan["config"], reason=reason)
    save_report["config"] = {
        "target_path": os.path.abspath(target_config_path),
        "backup_path": webui_config_backup_path,
        "bak_path": _bak_path_for_backup(webui_config_backup_path),
    }

    for update in plan.get("credential_updates") or []:
        save_report["credentials"].append(_save_provider_credentials_audited(update, config_path=target_config_path, reason=f"{reason}:credentials"))

    policy_path = plan.get("paths", {}).get("model_policy") or _policy_path_for_config(target_config_path)
    if policy_path:
        save_report["model_policy"] = _write_model_policy_audited(policy_path, plan["model_policy"], config_path=target_config_path, reason=f"{reason}:model-policy")

    try:
        save_report["routes_export"] = bool(mms_core._refresh_routes_export_for_hive(plan["config"], force=True, quiet=True, startup_safe=True))  # noqa: SLF001
    except Exception:
        save_report["routes_export"] = False

    return {
        "ok": True,
        "schema": "mms.setup_web.save_result.v1",
        "status": "saved",
        "summary": plan.get("summary") or {},
        "warnings": plan.get("warnings") or [],
        "paths": plan.get("paths") or {},
        "save_report": save_report,
        "audit_tail": _latest_audit_rows(target_config_path),
    }


def _provider_from_payload(cfg: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    provider_payload = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    provider_id = _safe_text(payload.get("provider_id") or provider_payload.get("id"))
    provider = dict(provider_payload)
    cfg_provider_ids = {
        _safe_text(item.get("id"))
        for item in (cfg.get("providers", []) if isinstance(cfg, dict) else [])
        if isinstance(item, dict)
    }
    if provider_id and provider_id in cfg_provider_ids:
        try:
            mms_core = _load_mms_core()
            resolved = mms_core.resolve_provider_context(cfg, provider_id)
            if isinstance(resolved, dict):
                merged = dict(resolved)
                merged.update({key: value for key, value in provider.items() if value not in (None, "")})
                provider = merged
        except BaseException:
            for item in cfg.get("providers", []) or []:
                if isinstance(item, dict) and item.get("id") == provider_id:
                    base = dict(item)
                    base.update({key: value for key, value in provider.items() if value not in (None, "")})
                    provider = base
                    break
    provider["id"] = _safe_text(provider.get("id") or provider_id or "web-test-provider")
    provider["protocols"] = _normalize_choice_list(provider.get("protocols"), _ALLOWED_PROTOCOLS, _ALLOWED_PROTOCOLS)
    if provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("openai_base_url")).rstrip("/")
    if provider.get("anthropic_base_url"):
        provider["anthropic_base_url"] = _safe_text(provider.get("anthropic_base_url")).rstrip("/")
    if provider.get("base_url") and not provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("base_url")).rstrip("/")
    return provider


def probe_provider_models(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    mms_core = _load_mms_core()
    return mms_core._probe_models(provider, emit_output=False, force_refresh=force_refresh)  # noqa: SLF001


def test_provider_models(cfg: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    provider = _provider_from_payload(cfg, payload)
    started = time.time()
    try:
        probe = probe_provider_models(provider, force_refresh=_truthy(payload.get("force_refresh"), True))
        latency_ms = int((time.time() - started) * 1000)
        models = _normalize_model_list(probe.get("models") or [])
        return {
            "ok": not bool(probe.get("error")),
            "provider_id": provider.get("id"),
            "models": models,
            "raw_models": _normalize_model_list(probe.get("raw_models") or models),
            "model_count": len(models),
            "base_source": probe.get("base_source") or "remote",
            "working_url": probe.get("working_url") or "",
            "error": probe.get("error") or "",
            "error_kind": probe.get("error_kind") or "",
            "latency_ms": latency_ms,
            "details": probe.get("details") or [],
            "cache_transport_evidence": {
                "schema": "cache_transport_evidence.v1",
                "provider_id": provider.get("id"),
                "request_url": probe.get("working_url") or provider.get("openai_base_url") or provider.get("anthropic_base_url") or "",
                "request_path": provider.get("models_endpoint") or "/models",
                "protocol": "openai_chat_completions" if "openai_chat_completions" in provider.get("protocols", []) else "anthropic_messages",
            },
        }
    except Exception as exc:
        return {"ok": False, "provider_id": provider.get("id"), "models": [], "error": str(exc), "trace": traceback.format_exc(limit=3)}


def _join_openai_chat_url(base_url: str) -> str:
    base = _safe_text(base_url).rstrip("/")
    if not base:
        return ""
    return base + "/chat/completions"


def _join_anthropic_messages_url(base_url: str) -> str:
    base = _safe_text(base_url).rstrip("/")
    if not base:
        return ""
    return base + ("/messages" if base.endswith("/v1") else "/v1/messages")


def run_model_smoke(cfg: dict[str, Any], payload: dict[str, Any], *, chat: bool = False) -> dict[str, Any]:
    provider = _provider_from_payload(cfg, payload)
    model = _safe_text(payload.get("model") or payload.get("model_id"))
    if not model:
        return {"ok": False, "error": "请选择要测试的模型。"}
    protocol = _safe_text(payload.get("protocol") or "auto")
    if protocol == "auto":
        protocol = "anthropic_messages" if "anthropic_messages" in provider.get("protocols", []) and provider.get("anthropic_base_url") else "openai_chat_completions"
    prompt = _safe_text(payload.get("prompt")) or ("用中文简短回复 pong" if chat else "只回复 pong")
    started = time.time()
    try:
        mms_core = _load_mms_core()
        if protocol == "anthropic_messages":
            api_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key"))
            url = _join_anthropic_messages_url(provider.get("anthropic_base_url") or provider.get("base_url"))
            if not url or not api_key:
                return {"ok": False, "error": "Anthropic 测试缺少 anthropic_base_url 或 API Key。"}
            body = {
                "model": model,
                "max_tokens": 64 if chat else 8,
                "messages": [{"role": "user", "content": prompt}],
            }
            response = mms_core._runtime_httpx_request(  # noqa: SLF001
                "POST",
                url,
                runtime=provider,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            data = response.json()
            content = data.get("content") if isinstance(data, dict) else None
            preview = ""
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    preview = _safe_text(first.get("text"))
            preview = preview or _safe_text(data.get("text") if isinstance(data, dict) else "")
            request_path = "/v1/messages" if "/v1/messages" in url else "/messages"
        else:
            api_key = _safe_text(provider.get("openai_api_key") or provider.get("api_key"))
            url = _join_openai_chat_url(provider.get("openai_base_url") or provider.get("base_url"))
            if not url or not api_key:
                return {"ok": False, "error": "OpenAI 测试缺少 openai_base_url 或 API Key。"}
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64 if chat else 8,
                "temperature": 0,
            }
            response = mms_core._runtime_httpx_request(  # noqa: SLF001
                "POST",
                url,
                runtime=provider,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            data = response.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            preview = ""
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else {}
                if isinstance(message, dict):
                    preview = _safe_text(message.get("content"))
            request_path = "/chat/completions"
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "provider_id": provider.get("id"),
            "model": model,
            "protocol": protocol,
            "latency_ms": latency_ms,
            "response_preview": preview[:500],
            "cache_transport_evidence": {
                "schema": "cache_transport_evidence.v1",
                "provider_id": provider.get("id"),
                "model": model,
                "protocol": protocol,
                "request_url": url,
                "request_path": request_path,
                "latency_ms": latency_ms,
            },
        }
    except Exception as exc:
        return {"ok": False, "provider_id": provider.get("id"), "model": model, "protocol": protocol, "error": str(exc), "trace": traceback.format_exc(limit=3)}


_HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMS 配置中心</title>
  <style>
    :root{
      --ink:#16211d; --muted:#65746f; --paper:#f7f1e6; --panel:#fffaf0; --panel2:#fefdf8;
      --line:#d9cdb8; --accent:#0f7b5f; --accent2:#db7c26; --danger:#b42318; --ok:#16803d;
      --shadow:0 24px 70px rgba(55,45,28,.14); --mono:"SFMono-Regular","Cascadia Code",monospace;
      --sans:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
      --serif:"Songti SC","STSong","Noto Serif CJK SC",serif;
    }
    *{box-sizing:border-box} body{margin:0;color:var(--ink);font-family:var(--sans);background:radial-gradient(circle at 10% -5%,#d7eadb 0,transparent 34rem),radial-gradient(circle at 92% 10%,#ffe1b8 0,transparent 30rem),linear-gradient(135deg,#fbf5e8,#eef4ef 58%,#f6efe2);}
    header{padding:34px clamp(18px,4vw,56px) 18px;display:grid;grid-template-columns:1.4fr .6fr;gap:20px;align-items:end}
    h1{margin:0;font-family:var(--serif);font-size:clamp(34px,6vw,70px);line-height:.95;letter-spacing:-.05em}.lead{max-width:760px;color:#46564f;font-size:17px;line-height:1.7}.statusbar{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.pill{border:1px solid var(--line);border-radius:999px;padding:7px 11px;background:rgba(255,250,240,.7);font-size:12px;color:#55645f}.pill.ok{color:var(--ok);border-color:#94d3a2}.pill.warn{color:#9a5b00;border-color:#ecc37d}
    .shell{display:grid;grid-template-columns:280px 1fr;gap:18px;padding:0 clamp(18px,4vw,56px) 48px}.side{position:sticky;top:12px;align-self:start;border:1px solid var(--line);background:rgba(255,250,240,.78);backdrop-filter:blur(16px);border-radius:26px;padding:14px;box-shadow:var(--shadow)}.navbtn{width:100%;border:0;background:transparent;text-align:left;border-radius:18px;padding:13px 14px;margin:3px 0;cursor:pointer;color:#44554e;font-weight:700}.navbtn.active{background:#163d32;color:#fff}.navbtn small{display:block;font-weight:500;opacity:.75;margin-top:4px}.content{display:grid;gap:18px}.panel{border:1px solid var(--line);border-radius:28px;background:rgba(255,250,240,.88);padding:22px;box-shadow:var(--shadow)}.panel h2{margin:0 0 10px;font-size:25px}.panel p{color:var(--muted);line-height:1.65}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.card{border:1px solid var(--line);border-radius:20px;background:var(--panel2);padding:16px}.span4{grid-column:span 4}.span5{grid-column:span 5}.span6{grid-column:span 6}.span7{grid-column:span 7}.span8{grid-column:span 8}.span12{grid-column:span 12}.provider-editor{position:sticky;top:14px;align-self:start;max-height:calc(100vh - 28px);overflow:auto;scrollbar-gutter:stable}
    label{display:block;font-size:12px;font-weight:800;color:#566760;margin:0 0 6px}input,select,textarea{width:100%;border:1px solid #cfc2ae;background:#fffef8;border-radius:14px;padding:11px 12px;font:inherit;color:var(--ink)}textarea{min-height:92px;resize:vertical;font-family:var(--mono);font-size:13px}.checks{display:flex;gap:8px;flex-wrap:wrap}.check{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);border-radius:999px;padding:8px 10px;background:#fffef8}.check input{width:auto}.btns{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}button,.button{border:0;border-radius:999px;padding:10px 15px;background:#173d33;color:#fff;font-weight:800;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}button.secondary{background:#f0e4d0;color:#22342e}button.ghost{background:transparent;color:#173d33;border:1px solid var(--line)}button.danger{background:var(--danger)}button:disabled{opacity:.5;cursor:not-allowed}.provider-list{display:grid;gap:8px}.provider-item{border:1px solid var(--line);border-radius:18px;padding:12px;background:#fffef8;cursor:pointer}.provider-item.active{outline:3px solid rgba(15,123,95,.18);border-color:var(--accent)}.provider-item strong{display:block}.muted{color:var(--muted)}.mono{font-family:var(--mono);font-size:12px}.tag{display:inline-block;border-radius:999px;background:#e9f3ed;color:#0f674f;padding:4px 8px;font-size:12px;margin:2px}.tag.off{background:#f3e2dc;color:#9f2d20}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:20px;background:#fffef8}table{width:100%;border-collapse:collapse;min-width:860px}th,td{border-bottom:1px solid #eadfce;padding:10px;text-align:left;font-size:13px}th{position:sticky;top:0;background:#f8efdf;z-index:1}td input[type="checkbox"]{width:auto}.chips{display:flex;flex-wrap:wrap;gap:7px}.chip{border:1px solid #d8c8b1;border-radius:999px;padding:6px 9px;background:#fffdf5;font-size:12px}.chip button{padding:0 4px;background:transparent;color:#8a2d22}.result{white-space:pre-wrap;background:#13231d;color:#e8f8ed;border-radius:18px;padding:14px;max-height:420px;overflow:auto;font-family:var(--mono);font-size:12px}.diff{white-space:pre;overflow:auto;background:#111d19;color:#e8f8ed;border-radius:18px;padding:16px;max-height:520px;font-family:var(--mono);font-size:12px}.toast{position:fixed;right:18px;bottom:18px;background:#163d32;color:#fff;border-radius:18px;padding:14px 16px;box-shadow:var(--shadow);max-width:520px;display:none}.toast.show{display:block}.danger-text{color:var(--danger);font-weight:800}.ok-text{color:var(--ok);font-weight:800}.hide{display:none!important}
    .oc-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px}.oc-metric{border:1px solid var(--line);border-radius:18px;background:#fffef8;padding:12px}.oc-metric strong{display:block;font-size:22px;color:#173d33}.oc-advanced{border:1px dashed #c9b898;border-radius:20px;padding:14px;background:rgba(255,253,248,.7)}.oc-advanced summary{cursor:pointer;font-weight:900;color:#173d33}.filterbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0}.filterbar button{background:#f0e4d0;color:#22342e}.filterbar button.active{background:#173d33;color:#fff}.empty-row{padding:18px;color:var(--muted);text-align:center}.default-route{max-width:300px;white-space:normal}.oc-order-note{border-left:4px solid #173d33;background:#f7efe0;border-radius:14px;padding:10px 12px;margin:12px 0;color:#46564f}.oc-enabled{width:auto}
    @media(max-width:980px){header{grid-template-columns:1fr}.statusbar{justify-content:flex-start}.shell{grid-template-columns:1fr}.side,.provider-editor{position:relative;top:auto;max-height:none;overflow:visible}.span4,.span5,.span6,.span7,.span8,.span12{grid-column:span 12}.oc-summary{grid-template-columns:1fr}}
  </style>
</head>
<body>
<header>
  <div><h1>MMS 配置中心</h1><p class="lead">不是展示页：这里可以配置通道、拉取模型、隐藏/补充模型、标记能力、测试模型、设置 fallback，并在预览 diff 后直接走 backup + audit 保存。</p></div>
  <div class="statusbar" id="statusbar"><span class="pill warn">加载中</span></div>
</header>
<div class="shell">
  <aside class="side" id="nav"></aside>
  <main class="content">
    <section class="panel" data-section="source"><h2>真源状态</h2><p>只读汇总当前 config root、registry DB、legacy import 冲突和 latest-approved bundle 校验状态。</p><div class="grid" id="sourceStatus"></div></section>
    <section class="panel" data-section="channel"><h2>通道配置</h2><p>先建通道：内部 ID、显示名、OpenAI/Anthropic URL、API Key、协议和模型列表接口。Key 只会通过 POST 发送，不会回显。</p><div class="grid"><div class="card span4"><div class="provider-list" id="providerList"></div><div class="btns"><button id="addProvider" class="secondary">+ 添加通道</button><button id="duplicateProvider" class="ghost">复制当前</button></div></div><div class="card span8 provider-editor" id="providerForm"></div></div></section>
    <section class="panel" data-section="models"><h2>模型列表</h2><p>可拉取远端列表，也可像 NewAPI 一样手动补充；取消“显示”会写入 provider.hidden_models。拉取只更新缓存/当前表格，不会自动写入 fallback_models；需要固定保留的模型请用“手动补充模型”。</p><div class="grid"><div class="card span12"><div class="btns"><button id="fetchModels">拉取当前通道模型</button><button id="testList" class="secondary">测试 /models</button><input id="modelSearch" placeholder="搜索模型" style="max-width:260px"></div><label style="margin-top:14px">手动补充模型（逗号或换行分隔）</label><textarea id="manualModels" placeholder="例如：gpt-5.5, qwen3.6-plus, K2.6"></textarea><div class="btns"><button id="addManualModels" class="secondary">添加到列表</button><button id="clearHidden" class="ghost">取消当前通道全部隐藏</button><button id="clearAllStaleHidden" class="ghost">一键清理全部通道过期隐藏项</button></div><div id="modelChips" class="chips" style="margin-top:10px"></div></div><div class="card span12" id="staleHiddenBox"></div><div class="span12 table-wrap"><table id="modelTable"></table></div></div></section>
    <section class="panel" data-section="test"><h2>模型测试</h2><p>支持模型列表 smoke、指定模型 ping/pong 和简单 chat。结果会显示脱敏 request_url/request_path evidence。</p><div class="grid"><div class="card span5"><label>测试通道</label><select id="testProvider"></select><label>测试模型</label><select id="testModel"></select><label>协议</label><select id="testProtocol"><option value="auto">auto</option><option value="anthropic_messages">anthropic_messages</option><option value="openai_chat_completions">openai_chat_completions</option></select><label>Prompt</label><textarea id="testPrompt">只回复 pong</textarea><div class="btns"><button id="testModelBtn">Ping 模型</button><button id="chatTestBtn" class="secondary">Simple chat</button></div></div><div class="card span7"><div class="result" id="testResult">暂无测试结果</div></div></div></section>
    <section class="panel" data-section="fallback"><h2>Fallback 设置</h2><p>这里会写入 config.toml 的 [rescue] 和 [vision_sidecar]，用于失败交接和 text-only 模型的图片 sidecar。</p><div class="grid"><div class="card span6"><h3>Rescue fallback</h3><label>fallback_model</label><input id="rescueModel" placeholder="deepseek-v4-flash"><label>fallback_cli</label><select id="rescueCli"><option value="">不指定</option><option>codex</option><option>claude</option><option>opencode</option><option>agy</option></select><div class="check" style="margin-top:10px"><input id="rescueHot" type="checkbox"><span>开启 hot_fallback_enabled</span></div></div><div class="card span6"><h3>Vision sidecar</h3><div class="check"><input id="visionEnabled" type="checkbox"><span>启用 vision sidecar</span></div><label>provider_id</label><select id="visionProvider"></select><label>model</label><select id="visionModel"></select><p class="muted">模型下拉优先显示当前通道中标记为 vision/multimodal 的模型；当前值不在列表时会保留为“当前配置值”。</p><label>候选列表</label><div id="visionCandidates" class="grid"></div><div class="btns"><button id="addVisionCandidate" class="secondary">+ 添加 vision 候选</button></div></div></div></section>
    <section class="panel" data-section="runtime"><h2>运行默认值</h2><p>Preferred CLI 会写入 presets.coding.cli；OpenCode profile 和 agent roster 会写入 [opencode]，launcher 会生成 session-local opencode.json；不会写全局 OpenCode 配置。</p><div class="grid"><div class="card span5"><label>preferred CLI</label><select id="preferredCli"><option>opencode</option><option>codex</option><option>claude</option><option>agy</option></select><label>coding preset model（可选）</label><input id="codingModel" placeholder="gpt-5.5"></div><div class="card span7"><label>OpenCode default profile</label><select id="opencodeProfile"><option>agent</option><option>omo</option><option>raw</option></select><p class="muted">推荐：5.5 总控/终审，5.4 长跑 executor，国产模型用于 explore / bug-hunt / vision。逐 agent 固定模型放在 Advanced，不作为默认必填项。</p></div><div class="card span12"><h3>OpenCode Agent Roster</h3><p class="muted">默认使用 Lite Pro 自动路线；这里管理哪些 agent 进入 session-local opencode.json。Order 是 priority/fallback order, not round-robin。</p><div class="oc-summary" id="opencodeOverrideSummary"></div><div class="oc-order-note">Lean 默认只开关键链路；Balanced 适合日常；Deep 再启用第二意见。国产模型适合 explore / bughunt / vision，不默认做最终裁决。</div><details class="oc-advanced" id="opencodeAdvanced"><summary>Advanced: OpenCode per-agent roster</summary><div class="filterbar" id="opencodeAgentFilters"></div><div class="table-wrap"><table id="opencodeAgents"></table></div></details></div></div></section>
    <section class="panel" data-section="save"><h2>保存 / 审计</h2><p>保存前先生成 diff。真正写入时会使用 MMS audited writer：lock、backup、audit log。API Key 不会出现在 diff 或响应里。</p><div class="grid"><div class="card span5"><div class="btns"><button id="previewPlan">生成保存预览</button><button id="saveBtn" class="danger">确认保存</button></div><div class="check" style="margin-top:12px"><input id="confirmSave" type="checkbox"><span>我已检查摘要、风险和 diff，同意写入配置</span></div><label style="margin-top:12px">输入确认文字：保存配置</label><input id="confirmPhrase" placeholder="保存配置"><label>保存原因 / audit reason</label><input id="saveReason" value="setup-web-ui:interactive-save"></div><div class="card span7"><div class="result" id="saveResult">尚未生成预览</div></div><div class="card span12"><h3>保存摘要</h3><div id="reviewSummary"><p class="muted">点击“生成保存预览”后，这里会先用人话列出 URL、隐藏模型、fallback、OpenCode 和风险变化。</p></div></div><div class="span12"><h3>Raw diff / 审计详情</h3><div class="diff" id="diffBox">点击“生成保存预览”</div></div></div></section>
    <section class="panel" data-section="refs"><h2>本地参考</h2><p>这些是当前配置页面使用的本地参考入口；联网查最新厂商文档应作为后续显式动作，不在保存时自动外连。</p><div class="grid" id="refsGrid"></div></section>
  </main>
</div>
<div class="toast" id="toast"></div>
<script>
const sections=[
  ['source','真源状态','DB / legacy / bundle'],['channel','通道配置','URL / Key / 协议'],['models','模型列表','拉取 / 隐藏 / 补充'],['test','模型测试','ping / chat smoke'],['fallback','Fallback','rescue / vision'],['runtime','运行默认值','preferred CLI / OpenCode'],['save','保存审计','diff / backup / audit'],['refs','本地参考','配置契约 / docs']
];
let state=null; let activeProvider=0; let lastPlan=null; let opencodeAgentFilter="all"; let opencodeOnlyOverridden=false;
const $=id=>document.getElementById(id);
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await res.json();if(!res.ok){data.ok=false;data.http_status=res.status;data.error=data.error||res.statusText}return data}
function current(){return state.providers[activeProvider]}
function setSection(id){document.querySelectorAll('[data-section]').forEach(el=>el.classList.toggle('hide',el.dataset.section!==id));document.querySelectorAll('.navbtn').forEach(el=>el.classList.toggle('active',el.dataset.id===id))}
function renderNav(){ $('nav').innerHTML=sections.map(([id,title,sub])=>`<button class="navbtn" data-id="${id}">${title}<small>${sub}</small></button>`).join(''); document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>setSection(b.dataset.id)); setSection('source') }
function renderStatus(){const providers=state.providers||[];const root=(state.model_source_status||{}).root||{};$('statusbar').innerHTML=`<span class="pill ok">${state.mode}</span><span class="pill">${escapeHtml(root.mode||'stable')}</span><span class="pill">通道 ${providers.length}</span><span class="pill">config: ${escapeHtml(state.paths.config||'-')}</span><span class="pill">policy: ${state.policy_summary.model_count} models</span>`}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function renderSourceStatus(){const box=$('sourceStatus');if(!box)return;const status=state.model_source_status||{};const root=status.root||{};const db=status.registry_db||{};const legacy=status.legacy_import||{};const candidates=legacy.candidates||db.legacy_import_candidates||{};const bundle=status.generated_bundle||{};const counts=db.counts||{};const okBundle=bundle.verified?'ok':'warn';const ready=bundle.runtime_ready===true?'ready':bundle.runtime_ready===false?'not ready':'unknown';box.innerHTML=`<div class="card span6"><h3>Root</h3><p class="mono">${escapeHtml(root.config_root||status.config_root||'-')}</p><span class="tag">${escapeHtml(root.command||state.command||'-')}</span><span class="tag">${escapeHtml(root.mode||'-')}</span><span class="tag">${escapeHtml(root.root_source||'-')}</span></div><div class="card span6"><h3>Registry DB</h3><p class="mono">${escapeHtml(db.path||'-')}</p><span class="tag ${db.status==='ok'?'':'off'}">${escapeHtml(db.status||'missing')}</span><span class="tag">sources ${counts.source_snapshot||0}</span><span class="tag">facts ${counts.model_fact||0}</span><span class="tag">routes ${counts.provider_route||0}</span></div><div class="card span6"><h3>Legacy Import</h3><p class="muted">${escapeHtml(legacy.next_action||'-')}</p><span class="tag">providers ${legacy.provider_count||0}</span><span class="tag ${legacy.conflict_count?'off':''}">conflicts ${legacy.conflict_count||0}</span><span class="tag ${candidates.status==='imported'?'':'off'}">candidates ${escapeHtml(candidates.status||'not_imported')}</span><span class="tag">candidate routes ${candidates.provider_route_count||0}</span></div><div class="card span6"><h3>Latest Approved Bundle</h3><p class="mono">${escapeHtml(bundle.manifest_path||'-')}</p><span class="tag ${okBundle==='ok'?'':'off'}">${escapeHtml(bundle.status||'missing')}</span><span class="tag">verified ${bundle.verified?'yes':'no'}</span><span class="tag ${bundle.runtime_ready===true?'':'off'}">runtime ${ready}</span><span class="tag">missing keys ${bundle.router_missing_api_key_count||0}</span><span class="tag">files ${bundle.file_count||0}</span></div><div class="card span12"><h3>Raw Status</h3><div class="result">${escapeHtml(JSON.stringify(status,null,2))}</div></div>`}
function providerEntries(){return (state.providers||[]).map((p,i)=>({p,i})).sort((a,b)=>{if(!!a.p.enabled!==!!b.p.enabled)return a.p.enabled?-1:1;return a.i-b.i})}
function renderProviderList(){const list=$('providerList');list.innerHTML=providerEntries().map(({p,i})=>`<div class="provider-item ${i===activeProvider?'active':''}" data-i="${i}"><strong>${escapeHtml(p.name||p.id)}</strong><span class="muted mono">${escapeHtml(p.id)}</span><br>${p.enabled?'<span class="tag">enabled</span>':'<span class="tag off">disabled</span>'}${p.has_api_key?'<span class="tag">key set</span>':'<span class="tag off">no key</span>'}<span class="tag">${p.models?.length||0} models</span></div>`).join('');document.querySelectorAll('.provider-item').forEach(el=>el.onclick=()=>{activeProvider=Number(el.dataset.i);renderAll()})}
function renderProviders(){renderProviderList();renderProviderForm();renderTestSelectors();renderModelTable();}
function checks(name,values,allowed){values=values||[];return `<div class="checks">${allowed.map(v=>`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${values.includes(v)?'checked':''}><span>${v}</span></label>`).join('')}</div>`}
function checkedValues(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value)}
function renderProviderForm(){const p=current(); if(!p){$('providerForm').innerHTML='<p>暂无通道</p>';return} $('providerForm').innerHTML=`<div class="grid"><div class="span6"><label>内部 ID</label><input id="pId" value="${escapeHtml(p.id)}"></div><div class="span6"><label>显示名</label><input id="pName" value="${escapeHtml(p.name)}"></div><div class="span4"><label>状态</label><select id="pEnabled"><option value="true" ${p.enabled?'selected':''}>启用</option><option value="false" ${!p.enabled?'selected':''}>禁用</option></select></div><div class="span4"><label>role</label><select id="pRole">${['primary','auto','fallback'].map(v=>`<option ${p.role===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="span4"><label>priority</label><input id="pPriority" type="number" value="${escapeHtml(p.priority||100)}"></div><div class="span6"><label>OpenAI base URL</label><input id="pOpenAI" value="${escapeHtml(p.openai_base_url||'')}" placeholder="https://.../v1"></div><div class="span6"><label>Anthropic base URL</label><input id="pAnthropic" value="${escapeHtml(p.anthropic_base_url||'')}" placeholder="https://.../v1 或 /anthropic"></div><div class="span6"><label>API Key（留空不更新）</label><input id="pKey" type="password" placeholder="${p.has_api_key?'已保存；输入新 key 才会覆盖':'sk-...'}"></div><div class="span6"><label>models_endpoint</label><input id="pModelsEndpoint" value="${escapeHtml(p.models_endpoint||'/models')}" placeholder="/models 或 manual"></div><div class="span12"><label>protocols</label>${checks('pProtocols',p.protocols,['anthropic_messages','openai_chat_completions'])}</div><div class="span12"><label>supported CLIs</label>${checks('pClis',p.supported_clis,['claude','codex','opencode','agy'])}</div><div class="span12 check"><input id="pUpdateCreds" type="checkbox"><span>保存时更新 credentials.sh（需要填写 API Key；会 backup + audit）</span></div><div class="span12 check"><input id="pDefault" type="checkbox" ${state.provider_default===p.id?'checked':''}><span>设为默认 provider</span></div></div>`; bindProviderForm();}
function bindProviderForm(){['pId','pName','pEnabled','pRole','pPriority','pOpenAI','pAnthropic','pModelsEndpoint'].forEach(id=>$(id).oninput=syncProvider);$('pKey').oninput=syncProvider;$('pUpdateCreds').onchange=syncProvider;$('pDefault').onchange=()=>{syncProvider(); if($('pDefault').checked) state.provider_default=current().id; renderProviders();};document.querySelectorAll('input[name="pProtocols"],input[name="pClis"]').forEach(x=>x.onchange=syncProvider)}
function syncProvider(){const p=current(); if(!p)return; const old=p.id;p.id=$('pId').value.trim()||p.id;p.name=$('pName').value.trim()||p.id;p.enabled=$('pEnabled').value==='true';p.role=$('pRole').value;p.priority=Number($('pPriority').value||100);p.openai_base_url=$('pOpenAI').value.trim();p.anthropic_base_url=$('pAnthropic').value.trim();p.models_endpoint=$('pModelsEndpoint').value.trim()||'/models';p.protocols=checkedValues('pProtocols');p.supported_clis=checkedValues('pClis');p.api_key=$('pKey').value;p.update_credentials=$('pUpdateCreds').checked;if(state.provider_default===old)state.provider_default=p.id;renderProviderList();renderTestSelectors();}
function providerModels(p){p=p||{};const map=new Map();const baseRows=(p.models||[]).filter(r=>r&&r.id&&r.source!=='hidden');baseRows.forEach(r=>map.set(r.id,{...r,capabilities:{...(r.capabilities||{})}}));if(!baseRows.length){(p.fallback_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'fallback',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)})})}(p.extra_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'extra',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)})});(p.hidden_models||[]).forEach(id=>{if(map.has(id))map.get(id).visible=false});return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id))}
function defaultCaps(id){const l=String(id||'').toLowerCase();return {text:true,vision:['mimo-v2.5','mimo-v2-omni','k2.6','k2.6-code-preview','kimi-k2.5','qwen3.6-plus','qwen3.6-flash','qwen3.5-plus'].includes(l)||l.startsWith('claude-')||l.startsWith('gemini-'),tool_use:/^(claude|gpt|o|qwen|kimi|glm|minimax|gemini)/.test(l),reasoning:/gpt-5|qwen3|kimi-k2|glm-5|deepseek|claude/.test(l),long_context:/1m|long|qwen3|kimi-k2|gpt-5|claude/.test(l),cache_sensitive:/^(qwen|kimi|k2\.|glm|deepseek|minimax|mimo)/.test(l)}}
function providerCurrentIds(p){return new Set(providerModels(p).map(r=>r.id))}
function staleHiddenModels(p){const ids=providerCurrentIds(p);return [...new Set([...(p.stale_hidden_models||[]),...(p.hidden_models||[]).filter(id=>!ids.has(id))])]}
function cleanupStaleHidden(p){const stale=staleHiddenModels(p);const doomed=new Set(stale);p.hidden_models=(p.hidden_models||[]).filter(x=>!doomed.has(x));p.stale_hidden_models=[];return stale.length}
function cleanupAllStaleHidden(){let total=0;(state.providers||[]).forEach(p=>{total+=cleanupStaleHidden(p)});renderProviders();toast(total?`已清理 ${total} 个过期 hidden_models`:'没有需要清理的过期隐藏项')}
function visibleModelsForProvider(providerId,{visionFirst=false,includeHidden=false,enabledOnly=false}={}){let rows=[];(state.providers||[]).forEach(p=>{if(providerId&&p.id!==providerId)return;if(enabledOnly&&p.enabled===false)return;providerModels(p).forEach(r=>{if(!includeHidden&&r.visible===false)return;rows.push({...r,provider_id:p.id,provider_name:p.name||p.id,capabilities:{...(r.capabilities||defaultCaps(r.id))}})})});const seen=new Set();rows=rows.filter(r=>{const key=(providerId?'':r.provider_id+'::')+r.id;if(seen.has(key))return false;seen.add(key);return true});rows.sort((a,b)=>{const av=!!(a.capabilities||{}).vision,bv=!!(b.capabilities||{}).vision;if(visionFirst&&av!==bv)return av?-1:1;return (a.provider_id+' '+a.id).localeCompare(b.provider_id+' '+b.id)});return rows}
function providerOptions(selected,{blankLabel='请选择通道',auto=false,enabledOnly=false}={}){const opts=[];const providers=providerEntries().filter(({p})=>!enabledOnly||p.enabled||p.id===selected);if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动选择 provider</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>${escapeHtml(blankLabel)}</option>`);opts.push(...providers.map(({p})=>{const disabled=p.enabled?'':' [disabled 当前配置值]';return `<option value="${escapeHtml(p.id)}" ${p.id===selected?'selected':''}>${escapeHtml(p.name||p.id)} / ${escapeHtml(p.id)}${disabled}</option>`}));if(selected&&!state.providers.some(p=>p.id===selected))opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function modelOptionValue(providerId,row){return providerId?row.id:`${row.provider_id}::${row.id}`}
function decodeModelSelection(value,currentProvider){const text=String(value||'');if(!text)return{provider_id:currentProvider||'',model:''};const marker='::';if(text.includes(marker)){const [provider_id,...rest]=text.split(marker);return{provider_id,model:rest.join(marker)}}return{provider_id:currentProvider||'',model:text}}
function modelOptions(providerId,selected,{visionFirst=false,auto=false,defaultModels=[],enabledOnly=false,selectedProvider=''}={}){const rows=visibleModelsForProvider(providerId,{visionFirst,enabledOnly});let opts=[];if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动路线${defaultModels.length?'：'+escapeHtml(defaultModels.join(' / ')):''}</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>请选择模型</option>`);let matched=false;opts.push(...rows.map(r=>{const value=modelOptionValue(providerId,r);const label=providerId?r.id:`${r.provider_id} / ${r.id}`;const tag=(r.capabilities||{}).vision?' [vision]':'';const isSelected=providerId?r.id===selected:((selectedProvider&&r.provider_id===selectedProvider&&r.id===selected)||(!selectedProvider&&r.id===selected));if(isSelected)matched=true;return `<option value="${escapeHtml(value)}" ${isSelected?'selected':''}>${escapeHtml(label)}${tag}</option>`}));if(selected&&!matched)opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function renderStaleHiddenBox(p){const stale=staleHiddenModels(p);const box=$('staleHiddenBox');if(!box)return;if(!stale.length){box.innerHTML='<strong>过期隐藏项</strong><p class="muted">当前没有“已不在通道模型列表里”的 hidden_models。</p>';return}box.innerHTML=`<strong>过期隐藏项（不在当前通道模型列表）</strong><p class="muted">这些多半是之前手动隐藏过、后来通道不再返回的模型。默认保留配置但不放进主表；确认无用后可清理。</p><div class="chips">${stale.map(m=>`<span class="chip">${escapeHtml(m)} <button data-stale-rm="${escapeHtml(m)}">清理</button></span>`).join('')}</div><div class="btns"><button id="clearStaleHidden" class="ghost">清理当前通道过期隐藏项</button></div>`;document.querySelectorAll('[data-stale-rm]').forEach(b=>b.onclick=()=>{p.hidden_models=(p.hidden_models||[]).filter(x=>x!==b.dataset.staleRm);p.stale_hidden_models=(p.stale_hidden_models||[]).filter(x=>x!==b.dataset.staleRm);renderModelTable()});$('clearStaleHidden').onclick=()=>{const count=cleanupStaleHidden(p);renderModelTable();toast(count?`已清理 ${count} 个当前通道过期 hidden_models`:'没有需要清理的过期隐藏项')}}
function renderModelTable(){const p=current(); if(!p)return;const q=($('modelSearch')?.value||'').toLowerCase();const rows=providerModels(p).filter(r=>r.id.toLowerCase().includes(q));$('modelChips').innerHTML=(p.extra_models||[]).map(m=>`<span class="chip">${escapeHtml(m)} <button data-rm="${escapeHtml(m)}">×</button></span>`).join('');document.querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>{p.extra_models=(p.extra_models||[]).filter(x=>x!==b.dataset.rm);renderModelTable()});renderStaleHiddenBox(p);$('modelTable').innerHTML=`<thead><tr><th>显示</th><th>模型</th><th>来源</th><th>收藏</th><th>text</th><th>vision</th><th>tool</th><th>reason</th><th>long</th><th>cache</th></tr></thead><tbody>${rows.map(r=>{const c=r.capabilities||{};return `<tr><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="visible" ${r.visible?'checked':''}></td><td class="mono">${escapeHtml(r.id)}</td><td><span class="tag ${r.visible?'':'off'}">${escapeHtml(r.source||'manual')}</span></td><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="favorite" ${r.favorite?'checked':''}></td>${['text','vision','tool_use','reasoning','long_context','cache_sensitive'].map(k=>`<td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-cap="${k}" ${c[k]?'checked':''}></td>`).join('')}</tr>`}).join('')}</tbody>`;document.querySelectorAll('#modelTable input').forEach(x=>x.onchange=onModelToggle);renderTestSelectors();renderFallback();renderRuntime()}
function onModelToggle(e){const p=current();const model=e.target.dataset.model;let row=providerModels(p).find(r=>r.id===model)||{id:model,capabilities:defaultCaps(model)};row.policy_touched=true;if(e.target.dataset.field==='visible'){row.visible=e.target.checked;p.hidden_models=e.target.checked?(p.hidden_models||[]).filter(x=>x!==model):[...(p.hidden_models||[]).filter(x=>x!==model),model]}else if(e.target.dataset.field==='favorite'){row.favorite=e.target.checked}else if(e.target.dataset.cap){row.capabilities=row.capabilities||{};row.capabilities[e.target.dataset.cap]=e.target.checked}p.model_capabilities=p.model_capabilities||{};p.model_capabilities[model]=row.capabilities;p.models=(p.models||[]).filter(r=>r.id!==model).concat(row);renderTestSelectors();renderFallback();renderRuntime()}
function renderTestSelectors(){const tp=$('testProvider');if(!tp)return;tp.innerHTML=providerEntries().map(({p,i})=>`<option value="${i}">${escapeHtml(p.name||p.id)}${p.enabled?'':' [disabled]'}</option>`).join('');tp.value=String(activeProvider);tp.onchange=()=>{activeProvider=Number(tp.value);renderAll()};const models=providerModels(current()||{});$('testModel').innerHTML=models.map(r=>`<option>${escapeHtml(r.id)}</option>`).join('')}
function syncFallback(){state.rescue=state.rescue||{};state.rescue.fallback_model=$('rescueModel').value.trim();state.rescue.fallback_cli=$('rescueCli').value;state.rescue.hot_fallback_enabled=$('rescueHot').checked;state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.enabled=$('visionEnabled').checked;state.vision_sidecar.provider_id=$('visionProvider').value.trim();state.vision_sidecar.model=$('visionModel').value.trim();state.vision_sidecar.candidates=[...document.querySelectorAll('[data-vision-candidate]')].map(row=>({provider_id:row.querySelector('[data-vc-provider]').value.trim(),model:row.querySelector('[data-vc-model]').value.trim()})).filter(x=>x.provider_id&&x.model)}
function bindVisionCandidateRow(row){const provider=row.querySelector('[data-vc-provider]');const model=row.querySelector('[data-vc-model]');provider.onchange=()=>{model.innerHTML=modelOptions(provider.value,'',{visionFirst:true});syncFallback()};model.onchange=syncFallback;row.querySelector('[data-vc-remove]').onclick=()=>{row.remove();syncFallback()}}
function renderVisionCandidates(candidates){const wrap=$('visionCandidates');wrap.innerHTML=(candidates||[]).map((item,i)=>{const provider=item.provider_id||item.provider||'';const model=item.model||item.vision_model||'';return `<div class="grid span12" data-vision-candidate="1"><div class="span5"><label>候选 ${i+1} provider</label><select data-vc-provider>${providerOptions(provider,{blankLabel:'请选择通道'})}</select></div><div class="span5"><label>候选 ${i+1} model</label><select data-vc-model>${modelOptions(provider,model,{visionFirst:true})}</select></div><div class="span2"><label>&nbsp;</label><button class="ghost" data-vc-remove>移除</button></div></div>`}).join('');document.querySelectorAll('[data-vision-candidate]').forEach(bindVisionCandidateRow)}
function renderFallback(){const r=state.rescue||{},v=state.vision_sidecar||{};$('rescueModel').value=r.fallback_model||'';$('rescueCli').value=r.fallback_cli||'';$('rescueHot').checked=!!r.hot_fallback_enabled;$('visionEnabled').checked=v.enabled!==false;const provider=v.provider_id||v.provider||'';const model=v.model||v.vision_model||'';$('visionProvider').innerHTML=providerOptions(provider,{blankLabel:'请选择 vision 通道'});$('visionProvider').value=provider;$('visionModel').innerHTML=modelOptions(provider,model,{visionFirst:true});$('visionModel').value=model;renderVisionCandidates(v.candidates||[]);['rescueModel','rescueCli','rescueHot','visionEnabled','visionModel'].forEach(id=>$(id).oninput=syncFallback);$('visionProvider').onchange=()=>{$('visionModel').innerHTML=modelOptions($('visionProvider').value,'',{visionFirst:true});syncFallback()};$('rescueHot').onchange=syncFallback;$('visionEnabled').onchange=syncFallback;$('addVisionCandidate').onclick=()=>{const provider=(state.providers[0]||{}).id||'';const model=(visibleModelsForProvider(provider,{visionFirst:true})[0]||{}).id||'';const list=[...(state.vision_sidecar?.candidates||[]),{provider_id:provider,model:model}];state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.candidates=list;renderVisionCandidates(list);syncFallback()}}
function opencodeOverrides(){state.opencode=state.opencode||{};state.opencode.agent_models=state.opencode.agent_models||{};return state.opencode.agent_models}
function opencodeRoster(){state.opencode=state.opencode||{};state.opencode.agent_roster=state.opencode.agent_roster||{};return state.opencode.agent_roster}
function opencodeOverrideEntries(){const overrides=opencodeOverrides();return Object.entries(overrides).filter(([,v])=>v&&v.model)}
function opencodeDefaults(){const map={};(state.opencode.agent_catalog||[]).forEach((row,i)=>{map[row.agent]={enabled:true,preset:row.preset||categoryPreset(row.category),priority:row.priority||((i+1)*10),custom:false}});return map}
function categoryPreset(category){const c=String(category||'');if(c==='Vision')return 'vision';if(c==='探索')return 'explore';if(c==='找茬')return 'bughunt';if(c==='审查')return 'reviewer';if(c==='执行')return 'executor';return 'builder'}
function rosterEntry(agent,row={}){const defaults=opencodeDefaults();return {...(defaults[agent]||{enabled:true,preset:row.preset||categoryPreset(row.category),priority:999,custom:!!row.custom}),...(opencodeRoster()[agent]||{})}}
function setOpencodeOverride(agent,provider,model){const overrides=opencodeOverrides();if(model){overrides[agent]={model};if(provider)overrides[agent].provider_id=provider}else{delete overrides[agent]}}
function persistRosterEntry(agent,row,patch={}){const roster=opencodeRoster();const defaults=opencodeDefaults();const base=rosterEntry(agent,row);const next={...base,...patch};const def=defaults[agent]||{};const providerMeaningful=!!next.provider_id&&(!!next.model||!!next.custom);const keep=!!next.custom||next.enabled===false||next.preset!==def.preset||Number(next.priority||0)!==Number(def.priority||0)||providerMeaningful||!!next.model||!!next.description||!!next.prompt;if(!keep){delete roster[agent];return}const payload={preset:next.preset||row.preset||categoryPreset(row.category),enabled:next.enabled!==false,priority:Number(next.priority||def.priority||999)};if(next.custom)payload.custom=true;if(providerMeaningful)payload.provider_id=next.provider_id;if(next.model)payload.model=next.model;if(next.description)payload.description=next.description;if(next.prompt)payload.prompt=next.prompt;roster[agent]=payload}
function setRosterEnabled(agent,row,enabled){persistRosterEntry(agent,row,{enabled})}
function opencodeAllRows(){const base=(state.opencode.agent_catalog||[]).map(row=>({...row,custom:false}));const seen=new Set(base.map(row=>row.agent));Object.entries(opencodeRoster()).forEach(([agent,entry])=>{if(seen.has(agent))return;base.push({agent,route_key:agent,category:presetLabel(entry.preset),preset:entry.preset||'explore',priority:entry.priority||999,default_models:[],custom:true})});return base.sort((a,b)=>Number(rosterEntry(a.agent,a).priority||999)-Number(rosterEntry(b.agent,b).priority||999)||a.agent.localeCompare(b.agent))}
function presetLabel(preset){return {builder:'执行/协调',executor:'执行',explore:'探索',bughunt:'找茬',vision:'Vision',reviewer:'审查',spec:'Spec',fixer:'执行'}[preset]||preset||'custom'}
function customAgentId(preset){const existing=new Set(opencodeAllRows().map(row=>row.agent));let i=1;let id='';do{id=`mobius-${preset}-custom-${i++}`}while(existing.has(id));return id}
function addCustomAgent(preset){const agent=customAgentId(preset);opencodeRoster()[agent]={enabled:true,custom:true,preset,priority:900+Object.keys(opencodeRoster()).length};renderOpencodeAgents();toast(`已添加 ${agent}`)}
function syncRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};state.runtime.preferred_cli=$('preferredCli').value;state.runtime.coding_preset_model=$('codingModel').value.trim();state.opencode.default_profile=$('opencodeProfile').value;state.opencode.agent_models=Object.fromEntries(opencodeOverrideEntries());state.opencode.agent_roster={...opencodeRoster()}}
function renderOpencodeSummary(){const box=$('opencodeOverrideSummary');if(!box)return;const rows=opencodeAllRows();const enabled=rows.filter(row=>rosterEntry(row.agent,row).enabled!==false).length;const count=opencodeOverrideEntries().length;const custom=rows.filter(row=>rosterEntry(row.agent,row).custom).length;const profile=state.opencode.default_profile||'agent';box.innerHTML=`<div class="oc-metric"><span class="muted">Profile</span><strong>${escapeHtml(profile)}</strong><span class="mono">Lite Pro Roster</span></div><div class="oc-metric"><span class="muted">Enabled agents</span><strong>${enabled}/${rows.length}</strong><span class="mono">进入 session-local opencode.json</span></div><div class="oc-metric"><span class="muted">Agent overrides</span><strong>${count}/${rows.length}</strong><span class="mono">Auto 不写 agent_models</span></div><div class="oc-metric"><span class="muted">Custom agents</span><strong>${custom}</strong><span class="mono">按 preset 继承 prompt/permission</span></div>`}
function opencodeFilterMatches(row,overridden){const entry=rosterEntry(row.agent,row);if(opencodeOnlyOverridden&&!overridden&&entry.enabled!==false&&!entry.custom)return false;if(opencodeAgentFilter==='all')return true;if(opencodeAgentFilter==='enabled')return entry.enabled!==false;if(opencodeAgentFilter==='custom')return !!entry.custom;if(opencodeAgentFilter==='execute')return ['builder','executor','fixer','spec'].includes(entry.preset)||String(row.category||'').startsWith('执行');if(opencodeAgentFilter==='explore')return entry.preset==='explore'||row.category==='探索';if(opencodeAgentFilter==='bughunt')return entry.preset==='bughunt'||row.category==='找茬';if(opencodeAgentFilter==='vision')return entry.preset==='vision'||row.category==='Vision';if(opencodeAgentFilter==='review')return entry.preset==='reviewer'||row.category==='审查';return true}
function renderOpencodeFilters(){const wrap=$('opencodeAgentFilters');if(!wrap)return;const filters=[['all','全部'],['enabled','已启用'],['custom','自定义'],['execute','执行/协调'],['explore','探索'],['bughunt','找茬'],['vision','Vision'],['review','审查']];wrap.innerHTML=`${filters.map(([id,label])=>`<button class="ghost ${opencodeAgentFilter===id?'active':''}" data-oc-filter="${id}">${label}</button>`).join('')}<label class="check"><input id="ocOnlyOverridden" type="checkbox" ${opencodeOnlyOverridden?'checked':''}><span>只看改动项</span></label><button class="ghost" data-oc-add="vision">+ Add Vision Agent</button><button class="ghost" data-oc-add="executor">+ Add Executor Agent</button><button class="ghost" data-oc-add="explore">+ Add Explore Agent</button><button class="ghost" id="ocClearAll">全部自动</button>`;document.querySelectorAll('[data-oc-filter]').forEach(btn=>btn.onclick=()=>{opencodeAgentFilter=btn.dataset.ocFilter;renderOpencodeAgents()});document.querySelectorAll('[data-oc-add]').forEach(btn=>btn.onclick=()=>addCustomAgent(btn.dataset.ocAdd));$('ocOnlyOverridden').onchange=()=>{opencodeOnlyOverridden=$('ocOnlyOverridden').checked;renderOpencodeAgents()};$('ocClearAll').onclick=()=>{state.opencode.agent_models={};state.opencode.agent_roster={};syncRuntime();renderOpencodeAgents();toast('OpenCode roster 已恢复默认自动路线')}}
function renderOpencodeAgents(){const table=$('opencodeAgents');if(!table)return;const overrides=opencodeOverrides();renderOpencodeSummary();renderOpencodeFilters();const rows=opencodeAllRows();const visible=rows.filter(row=>{const entry=rosterEntry(row.agent,row);const overridden=!!(overrides[row.agent]&&overrides[row.agent].model)||entry.enabled===false||entry.custom;return opencodeFilterMatches(row,overridden)});const presetOptions=(selected)=>['builder','executor','explore','bughunt','vision','reviewer','spec','fixer'].map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p}</option>`).join('');const body=visible.length?visible.map(row=>{const entry=rosterEntry(row.agent,row);const ov=overrides[row.agent]||{};const provider=ov.provider_id||entry.provider_id||'';const model=ov.model||entry.model||'';const enabled=entry.enabled!==false;const changed=!!model||!enabled||!!entry.custom;return `<tr data-oc-agent="${escapeHtml(row.agent)}"><td><input class="oc-enabled" type="checkbox" data-oc-enabled ${enabled?'checked':''} ${row.agent==='mobius-builder-pro'?'disabled':''}></td><td class="mono">${escapeHtml(row.agent)}<br><span class="muted">${escapeHtml(row.route_key)}</span>${entry.custom?'<br><span class="tag">custom</span>':''}${changed?'<span class="tag">changed</span>':''}</td><td><select data-oc-preset ${entry.custom?'':'disabled'}>${presetOptions(entry.preset)}</select></td><td><input data-oc-priority type="number" value="${escapeHtml(entry.priority||999)}" style="max-width:86px"></td><td><select data-oc-provider>${providerOptions(provider,{auto:true,enabledOnly:true})}</select></td><td><select data-oc-model>${modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})}</select></td><td class="mono default-route">${escapeHtml((row.default_models||[]).join(' / ')||'preset auto')}</td><td><button class="ghost" data-oc-reset>自动</button>${entry.custom?'<button class="ghost" data-oc-remove>移除</button>':''}</td></tr>`}).join(''):`<tr><td colspan="8" class="empty-row">当前过滤条件下没有 agent；关闭“只看改动项”或切换分类。</td></tr>`;table.innerHTML=`<thead><tr><th>启用</th><th>agent</th><th>preset</th><th>priority</th><th>provider</th><th>model</th><th>默认路线</th><th></th></tr></thead><tbody>${body}</tbody>`;document.querySelectorAll('[data-oc-agent]').forEach(rowEl=>{const agent=rowEl.dataset.ocAgent;const row=rows.find(x=>x.agent===agent)||{};const provider=rowEl.querySelector('[data-oc-provider]');const model=rowEl.querySelector('[data-oc-model]');const enabled=rowEl.querySelector('[data-oc-enabled]');const preset=rowEl.querySelector('[data-oc-preset]');const priority=rowEl.querySelector('[data-oc-priority]');provider.onchange=()=>{model.innerHTML=modelOptions(provider.value,'',{auto:true,defaultModels:row.default_models||[],visionFirst:(rosterEntry(agent,row).preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider.value});setOpencodeOverride(agent,provider.value.trim(),'');persistRosterEntry(agent,row,{provider_id:provider.value.trim(),model:''});syncRuntime();renderOpencodeSummary()};model.onchange=()=>{const picked=decodeModelSelection(model.value.trim(),provider.value.trim());if(picked.provider_id&&provider.value!==picked.provider_id){provider.value=picked.provider_id}setOpencodeOverride(agent,picked.provider_id,picked.model);persistRosterEntry(agent,row,{provider_id:picked.provider_id,model:picked.model});syncRuntime();renderOpencodeSummary()};enabled.onchange=()=>{setRosterEnabled(agent,row,enabled.checked);syncRuntime();renderOpencodeAgents()};preset.onchange=()=>{persistRosterEntry(agent,row,{preset:preset.value});syncRuntime();renderOpencodeAgents()};priority.onchange=()=>{persistRosterEntry(agent,row,{priority:Number(priority.value||999)});syncRuntime();renderOpencodeAgents()};rowEl.querySelector('[data-oc-reset]').onclick=()=>{setOpencodeOverride(agent,'','');delete opencodeRoster()[agent];syncRuntime();renderOpencodeAgents()};const remove=rowEl.querySelector('[data-oc-remove]');if(remove)remove.onclick=()=>{setOpencodeOverride(agent,'','');delete opencodeRoster()[agent];syncRuntime();renderOpencodeAgents()}})}
function renderRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};$('preferredCli').value=state.runtime.preferred_cli||'opencode';$('codingModel').value=state.runtime.coding_preset_model||'';$('opencodeProfile').value=state.opencode.default_profile||'agent';$('preferredCli').oninput=syncRuntime;$('codingModel').oninput=syncRuntime;$('opencodeProfile').oninput=()=>{syncRuntime();renderOpencodeSummary()};renderOpencodeAgents()}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function renderReviewSummary(plan){const review=plan?.review_summary||{};const counts=review.counts||{};const risks=review.risks||[];const items=review.items||[];const riskHtml=risks.length?`<h4>风险提示</h4><div>${risks.map(r=>`<p><span class="tag ${r.level==='danger'?'off':''}">${escapeHtml(levelLabel(r.level))}</span> <strong>${escapeHtml(r.title)}</strong> ${escapeHtml(r.detail)}</p>`).join('')}</div>`:'<p><span class="tag">无高风险提示</span></p>';const itemHtml=items.length?items.map(item=>`<p><span class="tag ${item.level==='danger'?'off':''}">${escapeHtml(levelLabel(item.level))}</span> <strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.detail)}</p>`).join(''):'<p class="muted">没有检测到配置变化。</p>';$('reviewSummary').innerHTML=`<div class="chips"><span class="chip">变化 ${counts.items||0}</span><span class="chip">风险 ${counts.risks||0}</span><span class="chip">清理 hidden ${counts.hidden_removed||0}</span><span class="chip">凭据更新 ${counts.credential_updates||0}</span></div>${riskHtml}<h4>将要写入的变化</h4>${itemHtml}`}
function draft(){syncProvider();syncFallback();syncRuntime();return JSON.parse(JSON.stringify({providers:state.providers,provider_default:state.provider_default,rescue:state.rescue,vision_sidecar:state.vision_sidecar,runtime:state.runtime,opencode:state.opencode}))}
function renderAll(){renderStatus();renderSourceStatus();renderProviders();renderFallback();renderRuntime();renderRefs()}
async function load(){const res=await fetch('/api/state');state=await res.json();state.providers=state.providers||[];renderNav();renderAll();}
$('addProvider').onclick=()=>{state.providers.push({id:`provider-${state.providers.length+1}`,original_id:'',name:'新通道',enabled:true,role:'auto',priority:100,models_endpoint:'/models',protocols:['anthropic_messages','openai_chat_completions'],supported_clis:['claude','codex','opencode'],openai_base_url:'',anthropic_base_url:'',api_key:'',update_credentials:false,fallback_models:[],extra_models:[],hidden_models:[],models:[]});activeProvider=state.providers.length-1;renderAll()}
$('duplicateProvider').onclick=()=>{const p=JSON.parse(JSON.stringify(current()));p.id=p.id+'-copy';p.original_id='';p.name=p.name+' Copy';p.api_key='';p.has_api_key=false;state.providers.push(p);activeProvider=state.providers.length-1;renderAll()}
$('modelSearch').oninput=renderModelTable;$('addManualModels').onclick=()=>{const p=current();const vals=$('manualModels').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);p.extra_models=[...new Set([...(p.extra_models||[]),...vals])];p.hidden_models=(p.hidden_models||[]).filter(x=>!vals.includes(x));$('manualModels').value='';renderModelTable();toast(`已添加 ${vals.length} 个模型`)};$('clearHidden').onclick=()=>{current().hidden_models=[];renderModelTable()};$('clearAllStaleHidden').onclick=cleanupAllStaleHidden
$('fetchModels').onclick=async()=>{syncProvider();const data=await api('/api/provider/models',{provider:current(),force_refresh:true});if(data.models){const p=current();p.models=data.models.map(id=>({id,source:data.base_source||'remote',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)}));renderModelTable();$('testResult').textContent=JSON.stringify(data,null,2);toast(`拉取到 ${data.models.length} 个模型；不会自动写入 fallback_models`)}else{$('testResult').textContent=JSON.stringify(data,null,2)}};
$('testList').onclick=async()=>{$('testResult').textContent=JSON.stringify(await api('/api/provider/test',{provider:current(),force_refresh:true}),null,2);setSection('test')}
$('testModelBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/model/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('chatTestBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/chat/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('previewPlan').onclick=async()=>{const data=await api('/api/plan',{draft:draft()});lastPlan=data;renderReviewSummary(data);$('saveResult').textContent=JSON.stringify({ok:data.ok,summary:data.summary,warnings:data.warnings,errors:data.errors,risks:data.review_summary?.risks},null,2);$('diffBox').textContent=[data.diffs?.config_toml,data.diffs?.model_policy_json,data.diffs?.credentials].filter(Boolean).join('\n')||'没有配置变化';toast(data.ok?'预览已生成':'预览有错误')}
$('saveBtn').onclick=async()=>{const data=await api('/api/save',{draft:draft(),confirm_save:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});$('saveResult').textContent=JSON.stringify(data,null,2);toast(data.ok?'保存完成，已写入 audit':'保存被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();renderAll();}}
load().catch(err=>{document.body.innerHTML='<pre style="padding:30px;color:#b42318">'+escapeHtml(err.stack||err.message)+'</pre>'})
</script>
</body>
</html>"""


def _html_page(_snapshot: dict[str, Any]) -> bytes:
    return _HTML_PAGE.encode("utf-8")


class ConfigWebApp:
    def __init__(self, cfg: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> None:
        self.cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
        self.config_path = config_path
        self.preferences_path = preferences_path
        self.command_name = command_name
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return build_config_snapshot(self.cfg, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
            if result.get("ok"):
                plan = build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
                self.cfg = plan.get("config") if isinstance(plan.get("config"), dict) else self.cfg
            return result

    def provider_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return test_provider_models(self.cfg, payload)

    def model_test(self, payload: dict[str, Any], *, chat: bool = False) -> dict[str, Any]:
        with self.lock:
            return run_model_smoke(self.cfg, payload, chat=chat)


class _SetupWebHandler(BaseHTTPRequestHandler):
    app: ConfigWebApp | None = None

    def log_message(self, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc
        return payload if isinstance(payload, dict) else {}

    def do_GET(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        snapshot = app.snapshot()
        if path in {"/", "/index.html"}:
            self._send(200, _html_page(snapshot), "text/html; charset=utf-8")
            return
        if path in {"/api/state", "/api/snapshot"}:
            self._send(*_json_response(snapshot))
            return
        if path == "/api/references":
            self._send(*_json_response({"references": build_reference_cards()}))
            return
        if path == "/setup.md":
            self._send(200, build_setup_markdown(snapshot).encode("utf-8"), "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
            if path == "/api/provider/models" or path == "/api/provider/test":
                self._send(*_json_response(app.provider_test(payload)))
                return
            if path == "/api/model/test":
                self._send(*_json_response(app.model_test(payload, chat=False)))
                return
            if path == "/api/chat/test":
                self._send(*_json_response(app.model_test(payload, chat=True)))
                return
            if path == "/api/plan":
                self._send(*_json_response(app.plan(payload)))
                return
            if path == "/api/save":
                result = app.save(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
        except Exception as exc:
            self._send(*_json_response({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=5)}, status=500))


def serve_config_web(app_or_snapshot: ConfigWebApp | dict[str, Any], *, host: str, port: int, open_browser: bool = True) -> str:
    if isinstance(app_or_snapshot, ConfigWebApp):
        app = app_or_snapshot
    else:
        app = ConfigWebApp({}, command_name="mms")
    handler = type("MMSSetupWebHandler", (_SetupWebHandler,), {"app": app})
    server = ThreadingHTTPServer((host, int(port)), handler)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mms-setup-web")
    thread.start()
    print(f"MMS 配置 WebUI: {url}")
    print("交互配置页面已启动；保存前会要求 diff + 明确确认。按 Ctrl-C 停止。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping MMS setup WebUI.")
    finally:
        server.shutdown()
        server.server_close()
    return url


def run_config_web(
    cfg: dict[str, Any] | None,
    argv: list[str] | None = None,
    *,
    command_name: str = "mms",
    config_path: str = "",
    preferences_path: str = "",
) -> int:
    parser = argparse.ArgumentParser(prog=f"{command_name} config web", description="Start the local interactive MMS configuration WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; default 127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Bind port; default 0 chooses a free port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--print-summary", action="store_true", help="Print redacted setup JSON and exit")
    parser.add_argument("--print-markdown", action="store_true", help="Print setup markdown and exit")
    args = parser.parse_args(argv or [])
    app = ConfigWebApp(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    snapshot = app.snapshot()
    if args.print_summary:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.print_markdown:
        print(build_setup_markdown(snapshot), end="")
        return 0
    serve_config_web(app, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0
