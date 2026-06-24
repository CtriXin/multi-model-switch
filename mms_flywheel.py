"""Flywheel/Looper profile resolver and headless worker runner for MMS Next.

`resolve` reports which MMS profile/model would be used for a Flywheel lane.
`run` launches the worker/fixer lane through that resolved MMS route while
preserving Looper's raw completion-marker output contract.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
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
SAFE_TOKEN_METADATA_KEYS = {
    "MAX_CONTEXT_TOKENS",
    "CONTEXT_TOKENS",
    "MAX_OUTPUT_TOKENS",
    "INPUT_TOKENS",
    "OUTPUT_TOKENS",
    "CACHE_READ_INPUT_TOKENS",
    "CACHE_CREATION_INPUT_TOKENS",
    "CACHED_TOKENS",
}
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
            "AI-P2": "flywheel.worker.cn-kimi",
            "AI-P3": "flywheel.worker.cn-qwen",
            "AI-P4": "flywheel.worker.cn-minimax",
        },
        "fixer": {
            "default": "flywheel.fixer.default",
            "AI-P0": "flywheel.fixer.default",
            "AI-P1": "flywheel.fixer.default",
            "AI-P2": "flywheel.fixer.cn-kimi",
            "AI-P3": "flywheel.fixer.cn-qwen",
            "AI-P4": "flywheel.fixer.cn-minimax",
        },
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
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
        },
        "flywheel.worker.cn-glm": {
            "runtime": "claude",
            "model": "glm-5.2",
            "provider": "direct-zai",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
        },
        "flywheel.worker.cn-kimi": {
            "runtime": "claude",
            "model": "kimi-for-coding",
            "provider": "direct-kimi",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-company", "us-cpa-local-codex"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
            },
        },
        "flywheel.worker.cn-qwen": {
            "runtime": "claude",
            "model": "qwen3.7-max",
            "provider": "direct-qwen",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
        },
        "flywheel.worker.cn-minimax": {
            "runtime": "claude",
            "model": "MiniMax-M3",
            "provider": "direct-minimax",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
        },
        "flywheel.fixer.default": {
            "runtime": "codex",
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
        },
        "flywheel.fixer.cn-glm": {
            "runtime": "claude",
            "model": "glm-5.2",
            "provider": "direct-zai",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
        },
        "flywheel.fixer.cn-kimi": {
            "runtime": "claude",
            "model": "kimi-for-coding",
            "provider": "direct-kimi",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-company", "us-cpa-local-codex"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
            },
        },
        "flywheel.fixer.cn-qwen": {
            "runtime": "claude",
            "model": "qwen3.7-max",
            "provider": "direct-qwen",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
        },
        "flywheel.fixer.cn-minimax": {
            "runtime": "claude",
            "model": "MiniMax-M3",
            "provider": "direct-minimax",
            "reasoning_effort": "medium",
            "fallback_providers": ["newapi-personal-tokyo", "newapi-tencent", "us-cpa-local-codex", "newapi-company"],
            "fallback_model_by_provider": {
                "us-cpa-local-codex": "gpt-5.5",
                "newapi-company": "gpt-5.5",
            },
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
    if upper in SAFE_TOKEN_METADATA_KEYS:
        return False
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
        "fallback_reason",
        "allow_model_switch",
        # Intentionally omit endpoint URLs/proxy fields from the resolver output.
        # The resolver is safe to paste into tracker/PR comments and never emits keys.
    }
    for key, value in candidate.items():
        if _is_secret_key(str(key)):
            continue
        if key in allowed and value not in (None, ""):
            safe[key] = value
    return safe


def _merged_route_candidates(
    routes: dict[str, Any],
    lineup_routes: dict[str, Any],
    model: str,
) -> list[tuple[str, dict[str, Any]]]:
    entry = routes.get(model)
    if not isinstance(entry, dict):
        return []
    meta_by_provider = _metadata_by_provider(lineup_routes.get(model))
    candidates: list[tuple[str, dict[str, Any]]] = []
    for name, candidate in _route_candidates(entry):
        candidate_provider = str(candidate.get("provider_id") or "").strip()
        merged = {**meta_by_provider.get(candidate_provider, {}), **candidate}
        candidates.append((name, merged))
    return candidates


def _find_route_candidate(
    routes: dict[str, Any],
    lineup_routes: dict[str, Any],
    *,
    model: str,
    provider: str,
) -> tuple[str, dict[str, Any]] | None:
    provider = str(provider or "").strip()
    if not provider:
        return None
    for name, candidate in _merged_route_candidates(routes, lineup_routes, model):
        if str(candidate.get("provider_id") or "").strip() == provider:
            return name, candidate
    return None


def _normalize_model_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("[1m]", "")


def _provider_declares_model(provider: dict[str, Any], model: str) -> bool:
    wanted = _normalize_model_id(model)
    if not wanted:
        return False
    for key in ("models", "fallback_models", "extra_models"):
        raw = provider.get(key)
        if isinstance(raw, str):
            raw = [raw]
        for item in raw or []:
            if _normalize_model_id(item) == wanted:
                return True
    return False


def _provider_route_candidate_from_config(root: Path, *, model: str, provider_id: str) -> dict[str, Any] | None:
    data = _load_toml(root / "config.toml")
    providers = data.get("providers") if isinstance(data.get("providers"), list) else []
    for provider in providers:
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        if str(provider.get("id") or "").strip() != provider_id:
            continue
        if not _provider_declares_model(provider, model):
            return None
        openai_base_url = str(
            provider.get("openai_base_url")
            or provider.get("default_openai_base_url")
            or provider.get("base_url")
            or ""
        ).strip()
        anthropic_base_url = str(
            provider.get("anthropic_base_url")
            or provider.get("default_anthropic_base_url")
            or ""
        ).strip()
        api_key = str(provider.get("api_key") or provider.get("openai_api_key") or "").strip()
        if not api_key or not (openai_base_url or anthropic_base_url):
            return None
        return {
            "provider_id": provider_id,
            "model_id": model,
            "api_key": api_key,
            "openai_base_url": openai_base_url,
            "anthropic_base_url": anthropic_base_url,
            "protocols": provider.get("protocols") or [],
            "provider_profile": provider.get("provider_profile") or provider.get("profile") or "",
            "proxy": provider.get("proxy") or "",
            "no_proxy": provider.get("no_proxy") or "",
        }
    return None


def _profile_fallback_providers(profile: dict[str, Any]) -> list[str]:
    raw = profile.get("fallback_providers") or profile.get("fallback_order") or []
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.replace(",", " ").split()]
    providers: list[str] = []
    for item in raw or []:
        provider = str(item or "").strip()
        if provider and provider not in providers:
            providers.append(provider)
    return providers


def _profile_fallback_model_map(profile: dict[str, Any]) -> dict[str, str]:
    raw = profile.get("fallback_model_by_provider") or profile.get("fallback_models_by_provider") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key).strip(): str(value).strip() for key, value in raw.items() if str(key).strip() and str(value).strip()}


def _bridge_fallback_route(candidate: dict[str, Any], *, model: str, allow_model_switch: bool = False) -> dict[str, Any]:
    provider_id = str(candidate.get("provider_id") or "").strip()
    api_key = str(candidate.get("api_key") or candidate.get("openai_api_key") or "").strip()
    anthropic_url = str(candidate.get("anthropic_base_url") or "").strip()
    openai_url = str(candidate.get("openai_base_url") or candidate.get("base_url") or "").strip()
    protocol = _preferred_transport_for_route(candidate, model)
    if protocol in {"openai_responses", "openai_chat_completions"}:
        gateway_url = openai_url
    else:
        gateway_url = anthropic_url or openai_url
    if not provider_id or not api_key or not gateway_url:
        return {}
    route = {
        "provider_id": provider_id,
        "provider_profile": str(candidate.get("provider_profile") or candidate.get("profile") or "").strip(),
        "gateway_url": gateway_url.rstrip("/"),
        "gateway_key": api_key,
        "openai_url": openai_url.rstrip("/"),
        "proxy_url": str(candidate.get("proxy") or "").strip(),
        "no_proxy": str(candidate.get("no_proxy") or "").strip(),
        "model": str(model or candidate.get("model_id") or candidate.get("model") or "").strip(),
        "protocol": protocol,
        "fallback_reason": "flywheel_ordered_fallback",
        "try_next_on": [401, 403, 408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, "connect_error", "timeout", "invalid_json", "invalid_text"],
    }
    if allow_model_switch:
        route["allow_model_switch"] = True
    return {key: value for key, value in route.items() if value not in (None, "", [])}


def _resolve_profile_fallbacks(
    *,
    root: Path,
    routes: dict[str, Any],
    lineup_routes: dict[str, Any],
    profile_cfg: dict[str, Any],
    model: str,
    selected_provider: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    providers = _profile_fallback_providers(profile_cfg)
    model_by_provider = _profile_fallback_model_map(profile_cfg)
    if not providers:
        return [], []

    sanitized: list[dict[str, Any]] = []
    raw_routes: list[dict[str, Any]] = []
    for provider in providers:
        fallback_model = model_by_provider.get(provider, model)
        match = _find_route_candidate(routes, lineup_routes, model=fallback_model, provider=provider)
        if match is not None:
            _slot, candidate = match
        else:
            candidate = _provider_route_candidate_from_config(root, model=fallback_model, provider_id=provider)
            if candidate is None:
                continue
        candidate_provider = str(candidate.get("provider_id") or "").strip()
        if candidate_provider == selected_provider and fallback_model == model:
            continue
        allow_model_switch = fallback_model != model
        display_candidate = dict(candidate)
        display_candidate["fallback_reason"] = "flywheel_ordered_fallback"
        if allow_model_switch:
            display_candidate["allow_model_switch"] = True
        sanitized.append({"slot": f"fallback-{len(sanitized) + 1}", **_sanitize_route(display_candidate)})
        bridge_route = _bridge_fallback_route(candidate, model=fallback_model, allow_model_switch=allow_model_switch)
        if bridge_route:
            raw_routes.append(bridge_route)
    return sanitized, raw_routes


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
    if _is_openai_family_model(model):
        return "codex"
    return "claude"


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
    model = str(_profile_value(profile_cfg, "model", "model_id", "model_name") or "").strip()
    if not model:
        raise FlywheelConfigError(f"flywheel profile {profile_id!r} has no model")

    runtime = str(_profile_value(profile_cfg, "runtime", "runtime_kind", "cli") or _infer_runtime(profile_id, model)).strip()
    provider = str(_profile_value(profile_cfg, "provider", "provider_id", "route_provider", "model_route_provider", "channel") or "").strip()

    entry = routes.get(model)
    meta_entry = lineup_routes.get(model)
    selected_name = ""
    selected_route: dict[str, Any] = {}
    fallbacks: list[dict[str, Any]] = []
    native_fallback_routes: list[dict[str, Any]] = []
    route_status = "not_applicable" if runtime == "opencode_profile" else "missing"

    if isinstance(entry, dict):
        route_status = "resolved"
        candidates = _merged_route_candidates(routes, lineup_routes, model)
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
        ordered_fallbacks, native_fallback_routes = _resolve_profile_fallbacks(
            root=root,
            routes=routes,
            lineup_routes=lineup_routes,
            profile_cfg=profile_cfg,
            model=model,
            selected_provider=str(selected_route.get("provider_id") or provider or "").strip(),
        )
        fallbacks = ordered_fallbacks or [
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

    config_meta: dict[str, Any] = {
        "root": str(root),
        "sources": sources,
        "route_path": str(route_file),
        "lineup_path": str(lineup_file),
    }
    if config_path:
        config_meta["config_path"] = str(Path(config_path).expanduser().resolve())

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
        "config": config_meta,
    }
    if profile_cfg.get("opencode_profile"):
        resolved["opencode_profile"] = str(profile_cfg["opencode_profile"])
    # Drop null-ish values while keeping explicit empty provider route objects out.
    return {key: value for key, value in resolved.items() if value not in (None, "")}


def _native_fallback_routes_for_resolved(resolved: dict[str, Any]) -> list[dict[str, Any]]:
    config_meta = resolved.get("config") if isinstance(resolved.get("config"), dict) else {}
    root = Path(str(config_meta.get("root") or "")).expanduser()
    route_path = Path(str(config_meta.get("route_path") or "")).expanduser()
    lineup_path = Path(str(config_meta.get("lineup_path") or "")).expanduser()
    config_path = str(config_meta.get("config_path") or "").strip()
    profile_id = str(resolved.get("profile_id") or "").strip()
    model = str(resolved.get("model") or "").strip()
    selected_provider = str(resolved.get("provider_id") or "").strip()
    if not root or not route_path or not profile_id or not model:
        return []
    try:
        routes = _routes_from(route_path)
        lineup_routes = _routes_from(lineup_path)
        config, _sources = _load_flywheel_config(root, config_path)
        profile_cfg = _profile_config(config, profile_id, routes)
        _sanitized, raw_routes = _resolve_profile_fallbacks(
            root=root,
            routes=routes,
            lineup_routes=lineup_routes,
            profile_cfg=profile_cfg,
            model=model,
            selected_provider=selected_provider,
        )
        return raw_routes
    except Exception:
        return []


def _route_has_launch_secret(route: dict[str, Any]) -> bool:
    return bool(str(route.get("api_key") or route.get("openai_api_key") or "").strip())


def _merge_launch_secret_route(route: dict[str, Any], secret_route: dict[str, Any]) -> dict[str, Any]:
    merged = dict(route)
    for key in (
        "api_key",
        "openai_api_key",
        "openai_base_url",
        "anthropic_base_url",
        "base_url",
        "proxy",
        "no_proxy",
        "provider_profile",
        "profile",
        "protocols",
        "model_id",
    ):
        value = secret_route.get(key)
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _find_raw_route(path: Path, *, model: str, selected_slot: str, provider_id: str) -> dict[str, Any]:
    routes = _routes_from(path)
    entry = routes.get(model)
    provider_id = str(provider_id or "").strip()
    fallback_by_provider: dict[str, Any] = {}
    for slot, candidate in _route_candidates(entry):
        candidate_provider = str(candidate.get("provider_id") or "").strip()
        if slot == selected_slot:
            return dict(candidate)
        if candidate_provider:
            fallback_by_provider[candidate_provider] = candidate
    if provider_id and provider_id in fallback_by_provider:
        return dict(fallback_by_provider[provider_id])
    return {}


def _raw_selected_route(resolved: dict[str, Any]) -> dict[str, Any]:
    config = resolved.get("config") if isinstance(resolved.get("config"), dict) else {}
    root = Path(str(config.get("root") or "")).expanduser()
    route_path = Path(str(config.get("route_path") or "")).expanduser()
    model = str(resolved.get("model") or "").strip()
    provider_id = str(resolved.get("provider_id") or "").strip()
    selected = resolved.get("selected_route") if isinstance(resolved.get("selected_route"), dict) else {}
    selected_slot = str(selected.get("slot") or "").strip()
    if not route_path or not model or not selected_slot:
        return {}
    route = _find_raw_route(route_path, model=model, selected_slot=selected_slot, provider_id=provider_id)
    if _route_has_launch_secret(route):
        return route
    legacy_route_path = (root / "model-routes.json").expanduser() if root else Path()
    if legacy_route_path and legacy_route_path.exists() and legacy_route_path.resolve() != route_path.resolve():
        secret_route = _find_raw_route(legacy_route_path, model=model, selected_slot=selected_slot, provider_id=provider_id)
        if _route_has_launch_secret(secret_route):
            return _merge_launch_secret_route(route, secret_route)
    if route:
        return route
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


def _usage_total(usage: dict[str, Any]) -> int:
    total = 0
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "cached_tokens"):
        try:
            total += max(int(usage.get(key) or 0), 0)
        except (TypeError, ValueError):
            continue
    return total


def _normalize_model_identity(model: str) -> str:
    normalized = str(model or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized.replace("[1m]", "").strip()


def _model_identity_matches(expected: str, served: str) -> bool:
    expected_norm = _normalize_model_identity(expected)
    served_norm = _normalize_model_identity(served)
    return bool(expected_norm and served_norm and expected_norm == served_norm)


def _bridge_wire_evidence_from_server(
    server: Any,
    *,
    expected_model: str,
    provider_id: str,
    protocol: str,
    request_path: str,
) -> dict[str, Any]:
    usage = dict(getattr(server, "wire_usage", {}) or {}) if server is not None else {}
    if not usage:
        usage = _zero_cache_usage()
    for key, value in list(usage.items()):
        try:
            usage[key] = max(int(value or 0), 0)
        except (TypeError, ValueError):
            usage[key] = 0
    for key, fallback_attr in {
        "input_tokens": "session_input_tokens",
        "output_tokens": "session_output_tokens",
    }.items():
        try:
            usage[key] = max(int(usage.get(key) or 0), int(getattr(server, fallback_attr, 0) or 0))
        except (TypeError, ValueError):
            pass
    served_model = str(getattr(server, "last_response_model", "") or "").strip() if server is not None else ""
    requested_model = str(getattr(server, "last_requested_model", "") or expected_model or "").strip() if server is not None else expected_model
    request_count = 0
    if server is not None:
        try:
            request_count = max(int(getattr(server, "session_request_count", 0) or 0), 0)
        except (TypeError, ValueError):
            request_count = 0
    source = "wire_response" if served_model and _usage_total(usage) > 0 else "wire_response_missing"
    return {
        "schema": CACHE_TRANSPORT_EVIDENCE_SCHEMA,
        "model": served_model or requested_model or expected_model,
        "requested_model": requested_model,
        "served_model": served_model,
        "expected_model": expected_model,
        "provider_id": str(getattr(server, "last_provider_id", "") or provider_id or "").strip() if server is not None else provider_id,
        "protocol": str(getattr(server, "last_protocol", "") or protocol or "").strip() if server is not None else protocol,
        "request_url": "",
        "request_path": str(getattr(server, "last_request_path", "") or request_path or "").strip() if server is not None else request_path,
        "route_source": "mms:wire",
        "provider_profile": "",
        "fallback_used": bool(getattr(server, "last_fallback_used", False)) if server is not None else False,
        "fallback_reason": str(getattr(server, "last_fallback_reason", "") or "").strip() if server is not None else "",
        "evidence_source": source,
        "request_count": request_count,
        "usage": usage,
    }


def _wire_evidence_verified(evidence: dict[str, Any], expected_model: str) -> tuple[bool, str]:
    served_model = str(evidence.get("served_model") or evidence.get("model") or "").strip()
    if not served_model:
        return False, "missing_served_model"
    if not _model_identity_matches(expected_model, served_model):
        return False, "served_model_mismatch"
    usage = evidence.get("usage") if isinstance(evidence.get("usage"), dict) else {}
    if _usage_total(usage) <= 0:
        return False, "missing_nonzero_usage"
    return True, "verified"


def _model_provenance(evidence: dict[str, Any], expected_model: str) -> dict[str, Any]:
    verified, reason = _wire_evidence_verified(evidence, expected_model)
    return {
        "schema": "mms.flywheel_model_provenance.v1",
        "expected_model": expected_model,
        "served_model": str(evidence.get("served_model") or evidence.get("model") or "").strip(),
        "evidence_source": str(evidence.get("evidence_source") or ""),
        "usage_total": _usage_total(evidence.get("usage") if isinstance(evidence.get("usage"), dict) else {}),
        "verified": verified,
        "status": reason,
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
    context_tokens = _normalize_context(resolved.get("max_context_tokens"))
    if context_tokens:
        runtime["max_context_tokens"] = context_tokens
    native_fallback_routes = _native_fallback_routes_for_resolved(resolved)
    if native_fallback_routes:
        runtime["native_fallback_routes"] = native_fallback_routes
        runtime["native_fallback_max"] = len(native_fallback_routes)
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
        if key in {
            "api_key",
            "openai_api_key",
            "openai_base_url",
            "anthropic_base_url",
            "base_url",
            "proxy",
            "no_proxy",
            "native_fallback_routes",
        }:
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
    mms_launchers._ensure_speed_stats()  # noqa: SLF001 - keep launcher lazy imports initialized.
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
    native_fallback_routes = list(runtime.get("native_fallback_routes") or [])
    if preferred_transport == "anthropic_messages":
        gateway_url = mms_launchers._anthropic_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected Anthropic transport has no anthropic_base_url")
        bridge_factory = mms_launchers.codex_chatcompletions_bridge
        bridge_kwargs["primary_protocol"] = "anthropic_messages"
        if native_fallback_routes:
            bridge_kwargs["native_fallback_routes"] = native_fallback_routes
    elif is_gpt or preferred_transport == "openai_responses":
        gateway_url = mms_launchers._openai_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected OpenAI Responses transport has no openai_base_url")
        bridge_factory = mms_launchers.codex_responses_bridge
        bridge_kwargs["native_fallback_routes"] = native_fallback_routes or mms_launchers._resolve_codex_responses_fallback_routes(runtime, model)  # noqa: SLF001
    else:
        gateway_url = mms_launchers._openai_base_url(runtime)  # noqa: SLF001
        if not gateway_url:
            raise FlywheelConfigError("selected OpenAI Chat transport has no openai_base_url")
        bridge_factory = mms_launchers.codex_chatcompletions_bridge
        if native_fallback_routes:
            bridge_kwargs["native_fallback_routes"] = native_fallback_routes

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
            'model_providers.custom.name="custom"',
            "-c",
            'model_providers.custom.wire_api="responses"',
            "-c",
            "model_providers.custom.requires_openai_auth=true",
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
        runtime["_wire_evidence_checked"] = True
        evidence = _bridge_wire_evidence_from_server(
            bridge_cfg.get("_server"),
            expected_model=model,
            provider_id=provider_id,
            protocol=preferred_transport,
            request_path=str(runtime.get("transport_request_path") or ""),
        )
        runtime["_wire_evidence"] = evidence
        sink = runtime.get("_wire_evidence_sink") if isinstance(runtime.get("_wire_evidence_sink"), dict) else None
        if sink is not None:
            sink["checked"] = True
            sink["evidence"] = evidence
        return proc.returncode, proc.stdout or "", proc.stderr or ""


@contextmanager
def _quiet_launcher_output():
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        yield


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _claude_shell_model(model: str, mms_launchers: Any) -> tuple[str, str]:
    if mms_launchers._is_claude_family_model_name(model):  # noqa: SLF001
        return model, ""
    if _is_domestic_model(model):
        return model, ""
    return "claude-sonnet-4-6", model


def _claude_print_args(*, cwd: Path, prompt: str, sandbox: str) -> list[str]:
    args: list[str] = []
    if sandbox in {"workspace-write", "danger-full-access"}:
        args.extend(["--add-dir", str(cwd)])
    if sandbox == "danger-full-access":
        args.append("--dangerously-skip-permissions")
    args.extend(["-p", prompt])
    return args


def _run_claude_headless(*, runtime: dict[str, Any], model: str, prompt: str, cwd: Path, sandbox: str) -> tuple[int, str, str]:
    import mms_launchers

    mms_launchers._ensure_bridge_helpers()  # noqa: SLF001 - flywheel runner reuses launcher bridge setup.
    mms_launchers._ensure_speed_stats()  # noqa: SLF001 - keep launcher lazy imports initialized.
    wire_evidence_sink = runtime.get("_wire_evidence_sink") if isinstance(runtime.get("_wire_evidence_sink"), dict) else None
    runtime = dict(runtime)
    runtime.pop("_wire_evidence_sink", None)
    if sandbox == "danger-full-access":
        runtime["bypass"] = True
    provider_id = str(runtime.get("id") or runtime.get("provider_id") or "").strip()
    provider_profile = str(runtime.get("profile") or runtime.get("provider_profile") or "")
    model = str(model or runtime.get("model") or "").strip()
    if not model:
        raise FlywheelConfigError("claude runtime requires a model")

    with _pushd(cwd), _quiet_launcher_output():
        mms_launchers.gateway_health_check(runtime)
        try:
            advertised_models = list(mms_launchers._probe_models(runtime, emit_output=False).get("models") or [])  # noqa: SLF001
        except Exception:
            advertised_models = [model]
        speed_scope = mms_launchers.build_provider_speed_scope(runtime)
        env_model, display_model = _claude_shell_model(model, mms_launchers)
        anthropic_url, _detect_method = mms_launchers._resolve_anthropic_base_url(runtime, probe_model=model)  # noqa: SLF001
        configured_anthropic = str(mms_launchers._anthropic_base_url(runtime) or "").strip()  # noqa: SLF001
        openai_url = str(mms_launchers._openai_base_url(runtime) or "").strip()  # noqa: SLF001
        bridge_url = str(anthropic_url or configured_anthropic or openai_url or "").strip().rstrip("/")
        if not bridge_url:
            raise FlywheelConfigError(f"claude runtime route {provider_id!r} has no usable endpoint")
        if (anthropic_url or configured_anthropic) and not bridge_url.endswith("/v1"):
            bridge_url += "/v1"

        thinking_enabled = bool(mms_launchers._runtime_thinking_enabled(runtime))  # noqa: SLF001
        reasoning_effort = mms_launchers._runtime_reasoning_effort(runtime, default="high")  # noqa: SLF001
        native_fallback_routes = list(runtime.get("native_fallback_routes") or [])
        context_window = int(runtime.get("max_context_tokens") or 0)
        if context_window <= 0:
            context_window = mms_launchers._effective_context_window(  # noqa: SLF001
                model,
                enable_claude_1m=mms_launchers._runtime_supports_claude_1m(runtime),  # noqa: SLF001
                provider_id=provider_id,
            )
        model_capabilities = mms_launchers._runtime_model_capabilities(runtime, model)  # noqa: SLF001
        vision_sidecar = mms_launchers._runtime_vision_sidecar(runtime)  # noqa: SLF001
        if mms_launchers._model_capabilities_support_vision(model_capabilities, model) is True:  # noqa: SLF001
            vision_sidecar = {}

        bridge_kwargs = {
            "heavy_model": model,
            "advertised_models": advertised_models,
            "speed_scope": speed_scope,
            "route_status_paths": mms_launchers._claude_route_status_paths(),  # noqa: SLF001
            "provider_id": provider_id,
            "provider_profile": provider_profile,
            "openai_url": openai_url or None,
            "proxy_url": runtime.get("proxy"),
            "no_proxy": runtime.get("no_proxy"),
            "strip_upstream_user_agent": "cliproxyapi" in provider_id.lower(),
            "minimal_claude_header_passthrough": mms_launchers._runtime_is_sensitive_claude_provider(runtime),  # noqa: SLF001
            "reasoning_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort,
            "native_fallback_routes": native_fallback_routes,
            "vision_sidecar": vision_sidecar,
            "model_capabilities": model_capabilities,
            "force_heavy_model": True,
            "context_windows": mms_launchers._context_windows_for_models(  # noqa: SLF001
                model,
                enable_claude_1m=mms_launchers._runtime_supports_claude_1m(runtime),  # noqa: SLF001
                provider_id=provider_id,
            ),
            "session_context_window": context_window,
            **mms_launchers._rescue_bridge_kwargs(),  # noqa: SLF001
        }
        with mms_launchers._gateway_claude_bridge_context(bridge_url, runtime["api_key"], **bridge_kwargs) as bridge_cfg:  # noqa: SLF001
            env = mms_launchers._claude_gateway_env(  # noqa: SLF001
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=env_model,
                selected_model=env_model,
                display_model=display_model,
            )
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
            env["CLAUDE_CODE_ATTRIBUTION_HEADER"] = "0"
            env["API_TIMEOUT_MS"] = "3000000"
            env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(context_window)
            env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(context_window - 3000, 10000))
            effort_env = mms_launchers._claude_code_effort_env_value(model, runtime)  # noqa: SLF001
            if effort_env:
                env["CLAUDE_CODE_EFFORT_LEVEL"] = effort_env
            mms_launchers._apply_claude_shell_context_slots(  # noqa: SLF001
                env,
                context_window=context_window,
                fallback_model=env.get("ANTHROPIC_MODEL") or env_model,
                enable_1m=mms_launchers._runtime_supports_claude_1m(runtime),  # noqa: SLF001
                provider_id=provider_id,
            )
            claude_bin = mms_launchers._resolve_real_home_command_path("claude", env) or "claude"  # noqa: SLF001
            cmd = [claude_bin, *_claude_print_args(cwd=cwd, prompt=prompt, sandbox=sandbox)]
            cmd, env, exe = mms_launchers.prepare_cli_command(cmd, env)
            if not exe:
                raise FlywheelConfigError("claude executable not found")
            proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=False)
            runtime["_wire_evidence_checked"] = True
            evidence = _bridge_wire_evidence_from_server(
                bridge_cfg.get("_server"),
                expected_model=model,
                provider_id=provider_id,
                protocol=str(runtime.get("preferred_transport") or "anthropic_messages"),
                request_path=str(runtime.get("transport_request_path") or ""),
            )
            runtime["_wire_evidence"] = evidence
            if wire_evidence_sink is not None:
                wire_evidence_sink["checked"] = True
                wire_evidence_sink["evidence"] = evidence
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
    model = str(resolved.get("model") or "")
    if runtime_kind not in {"codex", "claude"}:
        raise FlywheelConfigError(f"flywheel run currently supports codex/claude runtime only, got {runtime_kind!r}")
    if runtime_kind == "codex" and not _is_openai_family_model(model):
        raise FlywheelConfigError(f"codex runtime is limited to GPT/OpenAI-family models, got {model!r}; use runtime_kind='claude'")
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
            "cli": runtime_kind,
            "args": (
                _codex_exec_args(cwd=workdir, prompt="<prompt>", sandbox=sandbox)
                if runtime_kind == "codex"
                else _claude_print_args(cwd=workdir, prompt="<prompt>", sandbox=sandbox)
            ),
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

    wire_evidence_sink: dict[str, Any] = {}
    runtime["_wire_evidence_sink"] = wire_evidence_sink
    runner = _run_codex_headless if runtime_kind == "codex" else _run_claude_headless
    rc, stdout_text, stderr_text = runner(
        runtime=runtime,
        model=model,
        prompt=prompt_text,
        cwd=workdir,
        sandbox=sandbox,
    )
    wire_checked = bool(runtime.get("_wire_evidence_checked") or wire_evidence_sink.get("checked"))
    if wire_checked:
        wire_evidence = runtime.get("_wire_evidence") if isinstance(runtime.get("_wire_evidence"), dict) else {}
        if not wire_evidence and isinstance(wire_evidence_sink.get("evidence"), dict):
            wire_evidence = wire_evidence_sink["evidence"]
        if wire_evidence:
            transport_evidence = wire_evidence
            result["cache_transport_evidence"] = wire_evidence
            result["transport_evidence"] = [wire_evidence]
            result["served_model"] = wire_evidence.get("served_model") or wire_evidence.get("model")
            result["usage"] = wire_evidence.get("usage")
            result["model_provenance"] = _model_provenance(wire_evidence, model)
    agent_text = _extract_codex_agent_text(stdout_text) if runtime_kind == "codex" else stdout_text
    if not agent_text and stdout_text:
        agent_text = stdout_text
    result["exit_code"] = rc
    result["ok"] = rc == 0
    result["status"] = "completed" if rc == 0 else "failed"
    result["agent_text"] = agent_text
    result["stderr"] = stderr_text
    provenance = result.get("model_provenance") if isinstance(result.get("model_provenance"), dict) else {}
    if rc == 0 and wire_checked and not provenance.get("verified"):
        result["ok"] = False
        result["status"] = "wire_evidence_failed"
        result["wire_evidence_error"] = provenance.get("status") or "missing_wire_evidence"
        detail = f"flywheel wire evidence failed: {result['wire_evidence_error']}"
        result["stderr"] = f"{stderr_text.rstrip()}\n{detail}\n".lstrip()
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
