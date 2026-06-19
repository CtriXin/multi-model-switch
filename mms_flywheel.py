"""Flywheel/Looper profile resolver for MMS Next.

Phase 1 intentionally does not launch models. It resolves which MMS profile/model
would be used for a Flywheel lane so Looper can later call one stable headless
runner without duplicating model policy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

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
    ns = parser.parse_args(argv)
    if ns.command != "resolve":
        parser.print_help()
        return 2
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
