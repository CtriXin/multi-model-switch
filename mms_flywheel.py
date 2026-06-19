"""Flywheel/Looper profile resolver and headless worker runner for MMS Next.

`resolve` reports which MMS profile/model would be used for a Flywheel lane.
`run` launches the worker/fixer lane through that resolved MMS route while
preserving Looper's raw completion-marker output contract.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - kept for older local envs
    tomllib = None  # type: ignore[assignment]

VERSION = 1
LANES = {"worker", "fixer", "committee"}
PRIORITIES = {"AI-P0", "AI-P1", "AI-P2", "AI-P3", "AI-P4"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
THINKING_MODES = {"auto", "enable", "disable"}
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
FAKE_RESPONSE_ENV = "MMS_FLYWHEEL_RUN_FAKE_RESPONSE"
FAKE_JSONL_ENV = "MMS_FLYWHEEL_RUN_FAKE_JSONL"
RUN_RESULT_SCHEMA = "mms.flywheel_run_result.v1"
RUN_RESULT_ARTIFACT_SCHEMA = "mms.flywheel_run_artifact.v1"
CACHE_TRANSPORT_EVIDENCE_SCHEMA = "cache_transport_evidence.v1"
TRANSPORT_PROTOCOLS = {"anthropic_messages", "openai_chat_completions", "openai_responses"}
OPENAI_FAMILY_PREFIXES = ("gpt-", "o1", "o3", "o4", "o5", "codex-")
DOMESTIC_MODEL_MARKERS = ("qwen", "kimi", "deepseek", "glm", "minimax", "mimo", "moonshot", "doubao")

DEFAULT_FLYWHEEL_CONFIG: dict[str, Any] = {
    "lanes": {
        "worker": {
            "default": "flywheel.worker.default",
            "AI-P0": "flywheel.worker.default",
            "AI-P1": "flywheel.worker.default",
            "AI-P2": "flywheel.worker.default",
            "AI-P3": "flywheel.worker.default",
            "AI-P4": "flywheel.worker.default",
        },
        "fixer": {"default": "flywheel.fixer.default"},
        "committee": {
            "default": "opencode-committee",
            "AI-P0": "opencode-committee-heavy",
            "AI-P1": "opencode-committee-standard",
            "AI-P2": "opencode-committee-light",
            "AI-P3": "opencode-committee-fast",
            "AI-P4": "opencode-committee-fast",
        },
    },
    "profiles": {
        "flywheel.worker.default": {
            "runtime": "codex",
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
        },
        "flywheel.fixer.default": {
            "runtime": "codex",
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
        },
    },
}


class FlywheelConfigError(ValueError):
    """Raised when a flywheel profile cannot be resolved safely."""


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if tomllib is None:
        raise FlywheelConfigError("tomllib is required to read Flywheel TOML config")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    if not isinstance(data, dict):
        raise FlywheelConfigError(f"{path} must contain a TOML table")
    return data


def _config_root(explicit: str = "") -> Path:
    raw = explicit or os.environ.get("MMS_CONFIG_ROOT") or os.environ.get("MMS_CONFIG_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".config" / "mms").resolve()


def _load_flywheel_config(root: Path, explicit_config: str = "") -> tuple[dict[str, Any], list[str]]:
    cfg = dict(DEFAULT_FLYWHEEL_CONFIG)
    sources = ["builtin-defaults"]

    config_toml = root / "config.toml"
    config_data = _load_toml(config_toml)
    if isinstance(config_data.get("flywheel"), dict):
        cfg = _deep_merge(cfg, config_data["flywheel"])
        sources.append(str(config_toml))

    candidate_paths = [Path(explicit_config).expanduser()] if explicit_config else [root / "flywheel.toml"]
    for path in candidate_paths:
        if not path.exists():
            continue
        data = _load_toml(path)
        # Support either a dedicated flywheel.toml with top-level lanes/profiles
        # or a shared file with [flywheel.*] sections.
        section = data.get("flywheel") if isinstance(data.get("flywheel"), dict) else data
        if not isinstance(section, dict):
            raise FlywheelConfigError(f"{path} must contain flywheel config tables")
        cfg = _deep_merge(cfg, section)
        sources.append(str(path))
    return cfg, sources


def _normalize_lane(value: str) -> str:
    lane = str(value or "").strip().lower()
    aliases = {"work": "worker", "workers": "worker", "fix": "fixer", "reviewer": "committee", "review": "committee"}
    lane = aliases.get(lane, lane)
    if lane not in LANES:
        raise FlywheelConfigError(f"unsupported flywheel lane: {value!r}")
    return lane


def _normalize_priority(value: str) -> str:
    raw = str(value or "").strip().upper().replace("_", "-")
    if raw and raw in {"P0", "P1", "P2", "P3", "P4"}:
        raw = "AI-" + raw
    if raw and raw not in PRIORITIES:
        raise FlywheelConfigError(f"unsupported flywheel priority: {value!r}")
    return raw


def _route_path(root: Path, explicit: str = "") -> Path:
    raw = explicit or os.environ.get("RUNTIMIA_MMS_ROUTE_PATH") or os.environ.get("MMS_MODEL_ROUTES_PATH")
    candidates = [Path(raw).expanduser()] if raw else [
        root / "generated" / "model-routes.json",
        root / "model-routes.json",
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return candidates[0].resolve()


def _lineup_path(root: Path, explicit: str = "") -> Path:
    raw = (
        explicit
        or os.environ.get("RUNTIMIA_MMS_LINEUP_PATH")
        or os.environ.get("MMS_MODEL_ROUTES_LINEUP_PATH")
        or os.environ.get("MMS_MODEL_LINEUP_PATH")
    )
    candidates = [Path(raw).expanduser()] if raw else [
        root / "generated" / "model-routes.lineup.json",
        root / "model-routes.lineup.json",
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return candidates[0].resolve()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise FlywheelConfigError(f"{path} must contain a JSON object")
    return data


def _routes_from(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    routes = data.get("routes") if isinstance(data, dict) else {}
    return routes if isinstance(routes, dict) else {}


def _route_candidates(entry: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(entry, dict):
        return []
    candidates: list[tuple[str, dict[str, Any]]] = []
    primary = entry.get("primary")
    if isinstance(primary, dict):
        candidates.append(("primary", primary))
    for index, item in enumerate(entry.get("fallbacks") or [], start=1):
        if isinstance(item, dict):
            candidates.append((f"fallback-{index}", item))
    return candidates


def _metadata_by_provider(entry: Any) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for _name, candidate in _route_candidates(entry):
        provider = str(candidate.get("provider_id") or "").strip()
        if provider and provider not in meta:
            meta[provider] = candidate
    return meta


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(marker in upper for marker in SECRET_MARKERS)


def _sanitize_route(candidate: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    allowed = {
        "provider_id",
        "model_id",
        "model",
        "profile",
        "provider_profile",
        "protocol",
        "max_context_tokens",
        "context_length",
        "thinking_mode",
        "thinking",
        "reasoning_effort",
        "effort",
        # Intentionally omit endpoint URLs/proxy fields from the resolver output.
        # The resolver is safe to paste into tracker/PR comments and never emits keys.
    }
    for key, value in candidate.items():
        if _is_secret_key(str(key)):
            continue
        if key in allowed and value not in (None, ""):
            safe[key] = value
    return safe


def _profile_value(profile: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = profile.get(key)
        if value not in (None, ""):
            return value
    return ""


def _normalize_thinking(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "auto"}:
        return "auto"
    if raw in {"1", "true", "yes", "on", "enabled", "enable"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disabled", "disable"}:
        return "disable"
    raise FlywheelConfigError(f"invalid thinking_mode: {value!r}")


def _normalize_effort(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw not in EFFORTS:
        raise FlywheelConfigError(f"invalid reasoning_effort: {value!r}")
    return raw


def _normalize_context(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FlywheelConfigError(f"invalid max_context_tokens: {value!r}") from exc
    if parsed <= 0:
        raise FlywheelConfigError(f"invalid max_context_tokens: {value!r}")
    return parsed


def _infer_runtime(profile_id: str, model: str) -> str:
    raw = f"{profile_id} {model}".lower()
    if "opencode-committee" in raw:
        return "opencode_profile"
    if model.lower() in {"gpt-5.5", "gpt-5.4"}:
        return "codex"
    return "opencode"


def _select_profile(config: dict[str, Any], lane: str, priority: str, explicit_profile: str = "") -> str:
    if explicit_profile:
        return explicit_profile.strip()
    lanes = config.get("lanes") if isinstance(config.get("lanes"), dict) else {}
    lane_cfg = lanes.get(lane) if isinstance(lanes.get(lane), dict) else {}
    for key in (priority, priority.upper() if priority else "", "default"):
        if key and lane_cfg.get(key):
            return str(lane_cfg[key]).strip()
    raise FlywheelConfigError(f"flywheel lane {lane!r} has no profile mapping")


def _profile_config(config: dict[str, Any], profile_id: str, routes: dict[str, Any]) -> dict[str, Any]:
    profiles = config.get("profiles") if isinstance(config.get("profiles"), dict) else {}
    profile = profiles.get(profile_id) if isinstance(profiles.get(profile_id), dict) else None
    if profile is not None:
        return dict(profile)
    if profile_id in routes:
        return {"model": profile_id}
    if profile_id.startswith("opencode-committee"):
        return {"runtime": "opencode_profile", "model": profile_id, "opencode_profile": profile_id}
    raise FlywheelConfigError(f"flywheel profile {profile_id!r} is not configured and is not a model route")


def resolve_flywheel_profile(
    *,
    lane: str,
    priority: str = "",
    profile: str = "",
    config_root: str = "",
    config_path: str = "",
    route_path: str = "",
    lineup_path: str = "",
) -> dict[str, Any]:
    root = _config_root(config_root)
    lane = _normalize_lane(lane)
    priority = _normalize_priority(priority)
    route_file = _route_path(root, route_path)
    lineup_file = _lineup_path(root, lineup_path)
    routes = _routes_from(route_file)
    lineup_routes = _routes_from(lineup_file)
    config, sources = _load_flywheel_config(root, config_path)

    profile_id = _select_profile(config, lane, priority, profile)
    profile_cfg = _profile_config(config, profile_id, routes)
    model = str(_profile_value(profile_cfg, "model", "model_id") or "").strip()
    if not model:
        raise FlywheelConfigError(f"flywheel profile {profile_id!r} has no model")

    runtime = str(_profile_value(profile_cfg, "runtime", "runtime_kind", "cli") or _infer_runtime(profile_id, model)).strip()
    provider = str(_profile_value(profile_cfg, "provider", "provider_id", "route_provider", "model_route_provider", "channel") or "").strip()

    entry = routes.get(model)
    meta_entry = lineup_routes.get(model)
    selected_name = ""
    selected_route: dict[str, Any] = {}
    fallbacks: list[dict[str, Any]] = []
    route_status = "not_applicable" if runtime == "opencode_profile" else "missing"

    if isinstance(entry, dict):
        route_status = "resolved"
        meta_by_provider = _metadata_by_provider(meta_entry)
        candidates = []
        for name, candidate in _route_candidates(entry):
            candidate_provider = str(candidate.get("provider_id") or "").strip()
            merged = {**meta_by_provider.get(candidate_provider, {}), **candidate}
            candidates.append((name, merged))
        if not candidates:
            raise FlywheelConfigError(f"model route {model!r} has no usable candidates")
        selected_index = 0
        if provider:
            matches = [
                index
                for index, (_name, item) in enumerate(candidates)
                if str(item.get("provider_id") or "").strip() == provider
            ]
            if not matches:
                raise FlywheelConfigError(f"model route {model!r} has no provider {provider!r}")
            selected_index = matches[0]
        selected_name, selected_route = candidates[selected_index]
        fallbacks = [
            {"slot": name, **_sanitize_route(item)}
            for index, (name, item) in enumerate(candidates)
            if index != selected_index
        ]
    elif runtime != "opencode_profile":
        raise FlywheelConfigError(f"model route {model!r} not found in {route_file}")

    effort = _normalize_effort(
        _profile_value(profile_cfg, "reasoning_effort", "effort")
        or selected_route.get("reasoning_effort")
        or selected_route.get("effort")
    )
    thinking = _normalize_thinking(
        _profile_value(profile_cfg, "thinking_mode", "thinking")
        or selected_route.get("thinking_mode")
        or selected_route.get("thinking")
        or "auto"
    )
    context_tokens = _normalize_context(
        _profile_value(profile_cfg, "max_context_tokens", "context_length")
        or selected_route.get("max_context_tokens")
        or selected_route.get("context_length")
    )

    resolved: dict[str, Any] = {
        "version": VERSION,
        "lane": lane,
        "priority": priority,
        "profile_id": profile_id,
        "runtime_kind": runtime,
        "model": model,
        "provider_id": str(selected_route.get("provider_id") or provider or "").strip(),
        "route_status": route_status,
        "selected_route": {"slot": selected_name, **_sanitize_route(selected_route)} if selected_route else {},
        "fallback_routes": fallbacks,
        "selected_transport": _transport_evidence_for_route(selected_route, model) if selected_route else {},
        "thinking_mode": thinking,
        "reasoning_effort": effort,
        "max_context_tokens": context_tokens,
        "config": {
            "root": str(root),
            "sources": sources,
            "route_path": str(route_file),
            "lineup_path": str(lineup_file),
        },
    }
    if profile_cfg.get("opencode_profile"):
        resolved["opencode_profile"] = str(profile_cfg["opencode_profile"])
    # Drop null-ish values while keeping explicit empty provider route objects out.
    return {key: value for key, value in resolved.items() if value not in (None, "")}


def _raw_selected_route(resolved: dict[str, Any]) -> dict[str, Any]:
    config = resolved.get("config") if isinstance(resolved.get("config"), dict) else {}
    route_path = Path(str(config.get("route_path") or "")).expanduser()
    model = str(resolved.get("model") or "").strip()
    selected = resolved.get("selected_route") if isinstance(resolved.get("selected_route"), dict) else {}
    selected_slot = str(selected.get("slot") or "").strip()
    if not route_path or not model or not selected_slot:
        return {}
    routes = _routes_from(route_path)
    entry = routes.get(model)
    for slot, candidate in _route_candidates(entry):
        if slot == selected_slot:
            return dict(candidate)
    raise FlywheelConfigError(f"selected route slot {selected_slot!r} not found for model {model!r}")


def _protocols_for_route(route: dict[str, Any]) -> list[str]:
    raw_protocols = route.get("protocols")
    if isinstance(raw_protocols, str):
        raw_protocols = [raw_protocols]
    protocols: list[str] = [
        str(item).strip()
        for item in (raw_protocols or [])
        if str(item).strip() in {"anthropic_messages", "openai_chat_completions"}
    ]
    if str(route.get("anthropic_base_url") or "").strip():
        protocols.append("anthropic_messages")
    if str(route.get("openai_base_url") or "").strip():
        protocols.append("openai_chat_completions")
    return list(dict.fromkeys(protocols))


def _is_openai_family_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    if normalized.startswith(OPENAI_FAMILY_PREFIXES):
        return True
    return normalized.startswith(("openai/", "openai."))


def _is_domestic_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return any(marker in normalized for marker in DOMESTIC_MODEL_MARKERS)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _route_cache_sensitive(route: dict[str, Any]) -> bool:
    hints = route.get("protocol_hints") if isinstance(route.get("protocol_hints"), dict) else {}
    return (
        _truthy(route.get("cache_sensitive_transport"))
        or _truthy(route.get("cache_sensitive"))
        or _truthy(hints.get("cache_sensitive_transport"))
    )


def _join_request_path(base_url: str, endpoint: str) -> str:
    parts = urlsplit(str(base_url or "").strip())
    path = parts.path.rstrip("/")
    if endpoint == "messages":
        if path.endswith("/v1/messages") or path.endswith("/messages"):
            return path or "/messages"
        if path.endswith("/v1"):
            return f"{path}/messages"
        return f"{path}/v1/messages" if path else "/v1/messages"
    if endpoint == "responses":
        if path.endswith("/v1/responses") or path.endswith("/responses"):
            return path or "/responses"
        if path.endswith("/v1"):
            return f"{path}/responses"
        return f"{path}/v1/responses" if path else "/v1/responses"
    if path.endswith("/v1/chat/completions") or path.endswith("/chat/completions"):
        return path or "/chat/completions"
    if path.endswith("/v1"):
        return f"{path}/chat/completions"
    return f"{path}/v1/chat/completions" if path else "/v1/chat/completions"


def _transport_request_path(route: dict[str, Any], protocol: str) -> str:
    if protocol == "anthropic_messages":
        base = str(route.get("anthropic_base_url") or route.get("openai_base_url") or route.get("base_url") or "").strip()
        return _join_request_path(base, "messages")
    if protocol == "openai_responses":
        base = str(route.get("openai_base_url") or route.get("base_url") or "").strip()
        return _join_request_path(base, "responses")
    base = str(route.get("openai_base_url") or route.get("base_url") or "").strip()
    return _join_request_path(base, "chat/completions")


def _preferred_transport_for_route(route: dict[str, Any], model: str) -> str:
    explicit = str(route.get("protocol") or route.get("preferred_protocol") or "").strip()
    if explicit in TRANSPORT_PROTOCOLS:
        return explicit
    protocols = set(_protocols_for_route(route))
    anthropic_url = str(route.get("anthropic_base_url") or "").strip()
    openai_url = str(route.get("openai_base_url") or route.get("base_url") or "").strip()
    if _is_openai_family_model(model):
        if openai_url:
            return "openai_responses"
        if anthropic_url:
            raise FlywheelConfigError(f"OpenAI-family model {model!r} requires an OpenAI-compatible endpoint")
    if anthropic_url and (
        "anthropic_messages" in protocols
        or _route_cache_sensitive(route)
        or _is_domestic_model(model)
        or bool(openai_url)
    ):
        return "anthropic_messages"
    if openai_url:
        return "openai_chat_completions"
    if anthropic_url:
        return "anthropic_messages"
    raise FlywheelConfigError("selected route has no usable transport endpoint")


def _zero_cache_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cached_tokens": 0,
    }


def _transport_evidence_for_route(
    route: dict[str, Any],
    model: str,
    *,
    protocol: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str = "",
) -> dict[str, Any]:
    selected_protocol = protocol or _preferred_transport_for_route(route, model)
    return {
        "schema": CACHE_TRANSPORT_EVIDENCE_SCHEMA,
        "model": str(route.get("model_id") or model or "").strip(),
        "provider_id": str(route.get("provider_id") or "").strip(),
        "protocol": selected_protocol,
        # Keep artifacts paste-safe: request_path is concrete, request_url is
        # intentionally omitted because MMS provider endpoints can be private.
        "request_url": "",
        "request_path": _transport_request_path(route, selected_protocol),
        "route_source": "mms:model-routes",
        "provider_profile": str(route.get("provider_profile") or route.get("profile") or "").strip(),
        "fallback_used": bool(fallback_used),
        "fallback_reason": str(fallback_reason or ""),
        "evidence_source": "resolved_route",
        "usage": _zero_cache_usage(),
    }


def _launcher_effort(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"low", "medium", "high", "xhigh"}:
        return raw
    if raw == "max":
        return "xhigh"
    if raw in {"none", "minimal"}:
        return "low"
    return raw


def _runtime_from_route(resolved: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(route.get("provider_id") or resolved.get("provider_id") or "").strip()
    api_key = str(route.get("api_key") or route.get("openai_api_key") or "").strip()
    openai_base_url = str(route.get("openai_base_url") or route.get("base_url") or "").strip()
    anthropic_base_url = str(route.get("anthropic_base_url") or "").strip()
    model = str(route.get("model_id") or resolved.get("model") or "").strip()
    preferred_transport = _preferred_transport_for_route(route, model)
    if preferred_transport in {"openai_responses", "openai_chat_completions"} and not openai_base_url:
        raise FlywheelConfigError(f"selected route {provider_id!r} has no OpenAI-compatible endpoint")
    if preferred_transport == "anthropic_messages" and not (anthropic_base_url or openai_base_url):
        raise FlywheelConfigError(f"selected route {provider_id!r} has no Anthropic-compatible endpoint")
    if not provider_id:
        raise FlywheelConfigError("selected route has no provider_id")
    if not api_key:
        raise FlywheelConfigError(f"selected route {provider_id!r} has no api_key")
    if not openai_base_url and not anthropic_base_url:
        raise FlywheelConfigError(f"selected route {provider_id!r} has no endpoint URL")
    runtime = {
        "id": provider_id,
        "provider_id": provider_id,
        "name": provider_id,
        "auth_mode": "api_key",
        "runtime_kind": "provider",
        "api_key": api_key,
        "openai_api_key": api_key,
        "openai_base_url": openai_base_url,
        "anthropic_base_url": anthropic_base_url,
        "protocols": _protocols_for_route(route),
        "preferred_transport": preferred_transport,
        "transport_request_path": _transport_request_path(route, preferred_transport),
        "cache_transport_evidence": _transport_evidence_for_route(route, model, protocol=preferred_transport),
        "supported_clis": ["codex", "opencode", "claude"],
        "role": "auto",
        "model": model,
        "thinking_mode": str(resolved.get("thinking_mode") or "auto").strip().lower(),
        "native_fallback": True,
    }
    effort = _launcher_effort(resolved.get("reasoning_effort"))
    if effort:
        runtime["reasoning_effort"] = effort
    for key in ("proxy", "no_proxy", "provider_profile", "profile"):
        value = route.get(key)
        if value not in (None, ""):
            runtime[key] = value
    return runtime


def _sanitize_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in (runtime or {}).items():
        if _is_secret_key(str(key)):
            continue
        if key in {"api_key", "openai_api_key", "openai_base_url", "anthropic_base_url", "base_url", "proxy", "no_proxy"}:
            continue
        if value not in (None, ""):
            safe[key] = value
    return safe


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _preview_text(value: Any, *, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _write_run_result_artifact(path: Path, result: dict[str, Any]) -> None:
    metadata = {
        key: value
        for key, value in result.items()
        if key not in {"agent_text", "stderr"} and value not in (None, "")
    }
    payload = {
        "schema": RUN_RESULT_ARTIFACT_SCHEMA,
        "result": metadata,
        "output": {
            "agent_text_preview": _preview_text(result.get("agent_text")),
            "stderr_preview": _preview_text(result.get("stderr")),
        },
    }
    _write_json(path, payload)


def _artifact_dir(cwd: Path, explicit: str = "") -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    stamp = os.environ.get("MMS_FLYWHEEL_RUN_ID") or os.environ.get("LOOPER_TASK_ID") or "latest"
    safe_stamp = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in stamp)
    return (cwd / ".ai" / "flywheel-runs" / safe_stamp).resolve()


def _extract_prompt(remainder: list[str], *, explicit_prompt: str = "", prompt_file: str = "") -> tuple[str, list[str], str]:
    if explicit_prompt:
        return explicit_prompt, list(remainder or []), "prompt"
    if prompt_file:
        return Path(prompt_file).expanduser().read_text(encoding="utf-8"), list(remainder or []), "prompt_file"
    args = list(remainder or [])
    if args and args[0] in {"exec", "run"}:
        args = args[1:]
    prompt = ""
    forwarded: list[str] = []
    i = 0
    while i < len(args):
        item = args[i]
        if item in {"--model", "-m"} and i + 1 < len(args):
            i += 2
            continue
        if item in {"--dir", "-C", "--cd"} and i + 1 < len(args):
            forwarded.extend([item, args[i + 1]])
            i += 2
            continue
        if item == "--":
            i += 1
            if i < len(args):
                prompt = " ".join(args[i:]).strip()
            break
        if item.startswith("-"):
            forwarded.append(item)
        else:
            prompt = item
        i += 1
    if not prompt:
        raise FlywheelConfigError("flywheel run prompt is empty")
    return prompt, forwarded, "argv"


def _extract_codex_agent_text(jsonl_text: str) -> str:
    chunks: list[str] = []
    for line in str(jsonl_text or "").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        item = obj.get("item") if isinstance(obj, dict) else {}
        if obj.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "\n".join(chunks)


def _codex_exec_args(*, cwd: Path, prompt: str, sandbox: str) -> list[str]:
    return [
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--sandbox",
        sandbox,
        "-C",
        str(cwd),
        prompt,
    ]


def _run_codex_headless(*, runtime: dict[str, Any], model: str, prompt: str, cwd: Path, sandbox: str) -> tuple[int, str, str]:
    import mms_launchers

    mms_launchers._ensure_bridge_helpers()  # noqa: SLF001 - flywheel runner reuses launcher bridge setup.
    mms_launchers.gateway_health_check(runtime)
    api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
    provider_id = runtime.get("id", "")
    provider_profile = str(runtime.get("profile") or runtime.get("provider_profile") or "")
    speed_scope = mms_launchers.build_provider_speed_scope(runtime)
    try:
        advertised_models = list(mms_launchers._probe_models(runtime, emit_output=False).get("models") or [])  # noqa: SLF001
    except Exception:
        advertised_models = [model] if model else []

    is_gpt = bool(mms_launchers._is_gpt_model(model))  # noqa: SLF001
    preferred_transport = str(runtime.get("preferred_transport") or "").strip()
    if not preferred_transport:
        preferred_transport = "openai_responses" if is_gpt else "openai_chat_completions"
    bridge_kwargs = {
        "model_name": model or "unknown",
        "advertised_models": advertised_models,
        "speed_scope": speed_scope,
        "provider_id": provider_id,
        "provider_profile": provider_profile,
        "reasoning_enabled": bool(mms_launchers._runtime_thinking_enabled(runtime)),  # noqa: SLF001
        "reasoning_effort": mms_launchers._runtime_reasoning_effort(runtime, default="medium"),  # noqa: SLF001
        "proxy_url": runtime.get("proxy"),
        "no_proxy": runtime.get("no_proxy"),
        **mms_launchers._rescue_bridge_kwargs(),  # noqa: SLF001
    }
    if preferred_transport == "anthropic_messages":
        gateway_url = mms_launchers._anthropic_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected Anthropic transport has no anthropic_base_url")
        bridge_factory = mms_launchers.codex_chatcompletions_bridge
        bridge_kwargs["primary_protocol"] = "anthropic_messages"
    elif is_gpt or preferred_transport == "openai_responses":
        gateway_url = mms_launchers._openai_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected OpenAI Responses transport has no openai_base_url")
        bridge_factory = mms_launchers.codex_responses_bridge
        bridge_kwargs["native_fallback_routes"] = mms_launchers._resolve_codex_responses_fallback_routes(runtime, model)  # noqa: SLF001
    else:
        gateway_url = mms_launchers._openai_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected OpenAI Chat transport has no openai_base_url")
        bridge_factory = mms_launchers.codex_chatcompletions_bridge

    with bridge_factory(gateway_url, api_key, **bridge_kwargs) as bridge_cfg:
        bridge_base_url = mms_launchers._codex_provider_base_url(bridge_cfg["base_url"])  # noqa: SLF001
        env = mms_launchers._codex_gateway_env(runtime, bridge_cfg["base_url"], model_info={"model": model})  # noqa: SLF001
        env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
        env["OPENAI_BASE_URL"] = bridge_base_url
        cmd = ["codex", "-c", 'model_provider="custom"']
        if is_gpt and mms_launchers._runtime_thinking_enabled(runtime):  # noqa: SLF001
            effort = mms_launchers._runtime_reasoning_effort(runtime, default="medium")  # noqa: SLF001
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        cmd += [
            "-c",
            f'openai_base_url="{bridge_base_url}"',
            "-c",
            f'model_providers.custom.base_url="{bridge_base_url}"',
            "-c",
            "features.responses_websockets=false",
            "-c",
            "features.responses_websockets_v2=false",
        ]
        if model:
            cmd += ["-m", model]
        cmd += _codex_exec_args(cwd=cwd, prompt=prompt, sandbox=sandbox)
        cmd, env, exe = mms_launchers.prepare_cli_command(cmd, env)
        if not exe:
            raise FlywheelConfigError("codex executable not found")
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout or "", proc.stderr or ""


def run_flywheel_lane(
    *,
    lane: str,
    priority: str = "",
    profile: str = "",
    config_root: str = "",
    config_path: str = "",
    route_path: str = "",
    lineup_path: str = "",
    cwd: str = "",
    artifact_dir: str = "",
    prompt: str = "",
    prompt_file: str = "",
    runner_args: list[str] | None = None,
    sandbox: str = "danger-full-access",
    dry_run: bool = False,
) -> dict[str, Any]:
    workdir = Path(cwd or os.getcwd()).expanduser().resolve()
    resolved = resolve_flywheel_profile(
        lane=lane,
        priority=priority,
        profile=profile,
        config_root=config_root,
        config_path=config_path,
        route_path=route_path,
        lineup_path=lineup_path,
    )
    runtime_kind = str(resolved.get("runtime_kind") or "").strip()
    if runtime_kind not in {"codex"}:
        raise FlywheelConfigError(f"flywheel run currently supports codex runtime only, got {runtime_kind!r}")
    raw_route = _raw_selected_route(resolved)
    runtime = _runtime_from_route(resolved, raw_route)
    prompt_text, forwarded_args, prompt_source = _extract_prompt(
        runner_args or [],
        explicit_prompt=prompt,
        prompt_file=prompt_file,
    )
    out_dir = _artifact_dir(workdir, artifact_dir)
    resolved_artifact = out_dir / "resolved-route.json"
    run_result_artifact = out_dir / "run-result.json"
    transport_evidence = runtime.get("cache_transport_evidence") if isinstance(runtime.get("cache_transport_evidence"), dict) else {}
    artifact_payload = {
        "schema": "mms.flywheel_resolved_route.v1",
        "resolved": resolved,
        "runtime": _sanitize_runtime(runtime),
        "cache_transport_evidence": transport_evidence,
        "prompt_source": prompt_source,
        "forwarded_args": forwarded_args,
        "cwd": str(workdir),
        "sandbox": sandbox,
    }
    _write_json(resolved_artifact, artifact_payload)

    result: dict[str, Any] = {
        "schema": RUN_RESULT_SCHEMA,
        "ok": True,
        "status": "dry_run" if dry_run else "completed",
        "lane": resolved.get("lane"),
        "priority": resolved.get("priority", ""),
        "profile_id": resolved.get("profile_id"),
        "runtime_kind": runtime_kind,
        "model": resolved.get("model"),
        "provider_id": resolved.get("provider_id"),
        "artifact_dir": str(out_dir),
        "resolved_route_path": str(resolved_artifact),
        "run_result_path": str(run_result_artifact),
        "cache_transport_evidence": transport_evidence,
        "transport_evidence": [transport_evidence] if transport_evidence else [],
        "exit_code": 0,
        "agent_text": "",
        "stderr": "",
    }
    if dry_run:
        result["command_preview"] = {
            "cli": "codex",
            "args": _codex_exec_args(cwd=workdir, prompt="<prompt>", sandbox=sandbox),
        }
        _write_run_result_artifact(run_result_artifact, result)
        return result

    fake_response = str(os.environ.get(FAKE_RESPONSE_ENV) or "")
    fake_jsonl = str(os.environ.get(FAKE_JSONL_ENV) or "")
    if fake_response:
        result["agent_text"] = fake_response
        result["fake_dispatch"] = True
        _write_run_result_artifact(run_result_artifact, result)
        return result
    if fake_jsonl:
        result["agent_text"] = _extract_codex_agent_text(fake_jsonl)
        result["fake_dispatch"] = True
        _write_run_result_artifact(run_result_artifact, result)
        return result

    rc, stdout_text, stderr_text = _run_codex_headless(
        runtime=runtime,
        model=str(resolved.get("model") or ""),
        prompt=prompt_text,
        cwd=workdir,
        sandbox=sandbox,
    )
    agent_text = _extract_codex_agent_text(stdout_text)
    if not agent_text and stdout_text:
        agent_text = stdout_text
    result["exit_code"] = rc
    result["ok"] = rc == 0
    result["status"] = "completed" if rc == 0 else "failed"
    result["agent_text"] = agent_text
    result["stderr"] = stderr_text
    _write_run_result_artifact(run_result_artifact, result)
    return result


def _print_human(payload: dict[str, Any]) -> None:
    print(f"lane: {payload.get('lane')} priority: {payload.get('priority') or '<default>'}")
    print(f"profile: {payload.get('profile_id')}")
    print(f"runtime: {payload.get('runtime_kind')} model: {payload.get('model')}")
    provider = payload.get("provider_id") or "<profile>"
    print(f"provider: {provider} route: {payload.get('route_status')}")
    controls = []
    if payload.get("thinking_mode"):
        controls.append(f"thinking={payload['thinking_mode']}")
    if payload.get("reasoning_effort"):
        controls.append(f"effort={payload['reasoning_effort']}")
    if payload.get("max_context_tokens"):
        controls.append(f"context={payload['max_context_tokens']}")
    if controls:
        print("controls: " + " ".join(controls))


def handle_flywheel_command(argv: list[str], *, command_name: str = "mmf flywheel") -> int:
    parser = argparse.ArgumentParser(prog=command_name, description="Resolve Flywheel/Looper lanes from MMS config.")
    sub = parser.add_subparsers(dest="command")
    resolve = sub.add_parser("resolve", help="resolve a lane/profile without launching a model")
    resolve.add_argument("--lane", required=True, choices=sorted(LANES))
    resolve.add_argument("--priority", default="", help="AI-P0..AI-P4, or P0..P4")
    resolve.add_argument("--profile", default="", help="override profile id for diagnostics")
    resolve.add_argument("--config-root", default="", help="MMS config root; defaults to MMS_CONFIG_ROOT")
    resolve.add_argument("--config", default="", help="explicit flywheel TOML config path")
    resolve.add_argument("--route-path", default="", help="explicit model-routes.json path")
    resolve.add_argument("--lineup-path", default="", help="explicit model-routes.lineup.json path")
    resolve.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    run = sub.add_parser("run", help="run a Flywheel lane headlessly through the resolved MMS runtime")
    run.add_argument("--lane", required=True, choices=sorted(LANES))
    run.add_argument("--priority", default="", help="AI-P0..AI-P4, or P0..P4")
    run.add_argument("--profile", default="", help="override profile id for diagnostics")
    run.add_argument("--config-root", default="", help="MMS config root; defaults to MMS_CONFIG_ROOT")
    run.add_argument("--config", default="", help="explicit flywheel TOML config path")
    run.add_argument("--route-path", default="", help="explicit model-routes.json path")
    run.add_argument("--lineup-path", default="", help="explicit model-routes.lineup.json path")
    run.add_argument("--cwd", default="", help="working directory for the headless agent")
    run.add_argument("--artifact-dir", default="", help="where to write resolved-route.json")
    run.add_argument("--prompt", default="", help="prompt text; overrides trailing argv prompt")
    run.add_argument("--prompt-file", default="", help="read prompt from a file")
    run.add_argument("--sandbox", default="danger-full-access", choices=["read-only", "workspace-write", "danger-full-access"])
    run.add_argument("--dry-run", action="store_true", help="resolve and write artifacts without launching Codex")
    run.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of raw agent text")
    run.add_argument("runner_args", nargs=argparse.REMAINDER, help="Looper-style exec/run args; final positional is the prompt")
    ns = parser.parse_args(argv)
    if ns.command not in {"resolve", "run"}:
        parser.print_help()
        return 2
    if ns.command == "run":
        try:
            result = run_flywheel_lane(
                lane=ns.lane,
                priority=ns.priority,
                profile=ns.profile,
                config_root=ns.config_root,
                config_path=ns.config,
                route_path=ns.route_path,
                lineup_path=ns.lineup_path,
                cwd=ns.cwd,
                artifact_dir=ns.artifact_dir,
                prompt=ns.prompt,
                prompt_file=ns.prompt_file,
                runner_args=ns.runner_args,
                sandbox=ns.sandbox,
                dry_run=ns.dry_run,
            )
        except Exception as exc:
            if ns.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            else:
                print(f"flywheel run failed: {exc}", file=os.sys.stderr)
            return 1
        if ns.json:
            payload = dict(result)
            if len(str(payload.get("agent_text") or "")) > 2000:
                payload["agent_text"] = str(payload["agent_text"])[:2000] + "\n...[truncated]"
            print(json.dumps({"ok": bool(result.get("ok")), "result": payload}, ensure_ascii=False, indent=2))
        else:
            stderr_text = str(result.get("stderr") or "")
            if stderr_text:
                print(stderr_text, file=os.sys.stderr, end="" if stderr_text.endswith("\n") else "\n")
            agent_text = str(result.get("agent_text") or "")
            if agent_text:
                print(agent_text, end="" if agent_text.endswith("\n") else "\n")
        return int(result.get("exit_code") or (0 if result.get("ok") else 1))

    try:
        payload = resolve_flywheel_profile(
            lane=ns.lane,
            priority=ns.priority,
            profile=ns.profile,
            config_root=ns.config_root,
            config_path=ns.config,
            route_path=ns.route_path,
            lineup_path=ns.lineup_path,
        )
    except Exception as exc:
        if ns.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"flywheel resolve failed: {exc}")
        return 1
    if ns.json:
        print(json.dumps({"ok": True, "result": payload}, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(handle_flywheel_command(os.sys.argv[1:]))
