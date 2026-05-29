#!/usr/bin/env python3
"""Smoke MMS-generated OpenCode profile config and optional live agent routes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import mms_core
import mms_launchers

MOEBIUS_RUN = Path(
    os.environ.get("MMS_MOEBIUS_RUN")
    or ROOT_DIR.parent / "moebius" / "scripts" / "moebius_run.py"
).expanduser()
HEALTH_SCHEMA = "mms.opencode_route_health.v1"
HEALTH_LATEST_SCHEMA = "mms.opencode_route_health_latest.v1"
HEALTH_DIR = Path(".ai") / "opencode-health"
HEALTH_LEDGER_NAME = "route-health.jsonl"
HEALTH_LATEST_NAME = "latest.json"
SLOW_ROUTE_THRESHOLD_SEC = 30.0


def _now_slug() -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime())


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_from_epoch(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _trim(value: str, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _safe_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("env", None)
    return cleaned


def _init_trace(repo_root: Path, trace_id: str, profile: str, live: bool) -> None:
    trace_root = repo_root / ".ai" / "trace"
    trace_root.mkdir(parents=True, exist_ok=True)
    if not MOEBIUS_RUN.exists():
        return
    cmd = [
        sys.executable,
        str(MOEBIUS_RUN),
        "trace",
        "init",
        "--run-id",
        f"mms-opencode-smoke-{_now_slug()}",
        "--task-id",
        "mms-opencode-profile-smoke",
        "--milestone",
        "S-opencode-smoke",
        "--goal",
        f"Smoke OpenCode profile {profile} live={live}",
        "--repo-root",
        str(repo_root),
        "--trace-root",
        str(trace_root),
        "--trace-id",
        trace_id,
        "--backend",
        "opencode",
        "--source",
        "mms",
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _record_trace_event(repo_root: Path, trace_id: str, status: str, data: dict[str, Any]) -> None:
    trace_root = repo_root / ".ai" / "trace"
    if not MOEBIUS_RUN.exists():
        return
    cmd = [
        sys.executable,
        str(MOEBIUS_RUN),
        "trace",
        "event",
        "--trace-id",
        trace_id,
        "--trace-root",
        str(trace_root),
        "--event-type",
        "opencode_profile_smoke",
        "--module",
        "mms_opencode",
        "--action",
        "smoke",
        "--status",
        status,
        "--backend",
        "opencode",
        "--lane",
        "opencode_agent",
        "--data-json",
        json.dumps(_safe_event_payload(data), ensure_ascii=False),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _resolve_profile(profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = mms_core.load_runtime_config()
    if cfg is None:
        raise RuntimeError("未找到 MMS config")
    provider = mms_core.ensure_provider_credentials(cfg)
    default_models = mms_core._probe_models(provider, emit_output=False).get("models")
    model_info, runtime = mms_core._resolve_opencode_profile_runtime(cfg, provider, default_models, profile)
    if runtime is None:
        raise RuntimeError(f"无法解析 OpenCode profile: {profile}")
    return model_info, runtime


def _build_temp_env(runtime: dict[str, Any], model_info: dict[str, Any], temp_root: Path) -> tuple[dict[str, str], Path, dict[str, Any]]:
    home = temp_root / "home"
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "opencode.json"
    model = str(model_info.get("model") or runtime.get("model") or "")
    payload = mms_launchers._build_opencode_config_payload(runtime, model)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    env = os.environ.copy()
    mms_launchers._scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["OPENCODE_CONFIG"] = str(config_path)
    env["OPENCODE_CONFIG_DIR"] = str(config_dir)
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_CLIENT"] = "mms-smoke"
    mms_launchers._opencode_apply_route_env(env, runtime, selected_model=model)
    return env, config_path, payload


def _agent_model_map(payload: dict[str, Any]) -> dict[str, str]:
    agents = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    return {
        str(name): str(config.get("model") or payload.get("model") or "")
        for name, config in agents.items()
        if isinstance(config, dict)
    }


def _route_lookup(runtime: dict[str, Any], model: str) -> dict[str, dict[str, Any]]:
    routes = mms_launchers._opencode_runtime_routes(runtime, model)
    return {
        mms_launchers._opencode_route_model_ref(route, index): route
        for index, route in enumerate(routes)
    }


def _configured_transport_evidence(route: dict[str, Any], *, fallback_used: bool, fallback_reason: str) -> dict[str, Any]:
    protocol = str(route.get("protocol") or "openai_chat_completions").strip()
    if protocol == "anthropic_messages":
        base_url = str(route.get("anthropic_base_url") or "").strip().rstrip("/")
        request_url = f"{base_url}/messages" if base_url else ""
    elif protocol == "openai_responses":
        base_url = str(route.get("openai_base_url") or "").strip().rstrip("/")
        request_url = f"{base_url}/responses" if base_url else ""
    else:
        base_url = str(route.get("openai_base_url") or "").strip().rstrip("/")
        request_url = f"{base_url}/chat/completions" if base_url else ""
    return {
        "schema": "cache_transport_evidence.v1",
        "model": route.get("model"),
        "provider_id": route.get("provider_id"),
        "protocol": protocol,
        "request_url": request_url,
        "route_source": "mms_opencode_profile",
        "provider_profile": "anthropic" if protocol == "anthropic_messages" else (
            "openai" if protocol == "openai_responses" else "openai_compatible"
        ),
        "fallback_used": bool(fallback_used),
        "fallback_reason": fallback_reason,
        "usage": {
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "cache_creation_input_tokens": None,
        },
        "evidence_note": "configured OpenCode provider route; OpenCode CLI stdout does not expose raw upstream request log",
    }


def _is_gpt_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized.startswith("gpt-") or normalized.startswith("o1") or normalized.startswith("o3")


def _is_mimo_model(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized.startswith("mimo-")


def _protocol_correct(route: dict[str, Any], evidence: dict[str, Any]) -> bool:
    model = str(route.get("model") or evidence.get("model") or "").strip()
    protocol = str(evidence.get("protocol") or route.get("protocol") or "").strip()
    if model and _is_gpt_model(model):
        return protocol in {"openai_responses", "openai_chat_completions"}
    if model and _is_mimo_model(model):
        return protocol == "openai_chat_completions"
    if model and not _is_gpt_model(model):
        return protocol == "anthropic_messages"
    return bool(protocol)


def _combined_check_text(check: dict[str, Any]) -> str:
    return " ".join(
        str(check.get(key) or "")
        for key in ("returncode", "stdout", "stderr", "error", "status")
    ).lower()


def _classify_error(check: dict[str, Any], route: dict[str, Any]) -> str:
    evidence = check.get("cache_transport_evidence") if isinstance(check.get("cache_transport_evidence"), dict) else {}
    text = _combined_check_text(check)
    if "must be passed back" in text and (
        "reasoning_content" in text or "content[].thinking" in text
    ):
        return "reasoning_content_roundtrip_required"
    if not _protocol_correct(route, evidence):
        return "cache_sensitive_wrong_protocol"
    model = str(route.get("model") or evidence.get("model") or "").strip()
    protocol = str(evidence.get("protocol") or route.get("protocol") or "").strip()
    if model and _is_gpt_model(model) and protocol == "openai_chat_completions":
        return "cache_unfriendly_chat_completions"
    if check.get("ok"):
        return "ok"
    if check.get("returncode") == "timeout":
        return "timeout"

    if any(token in text for token in ("401", "403", "unauthorized", "auth", "invalid api key", "api key")):
        return "auth_error"
    if "429" in text or "rate limit" in text or "rate_limited" in text:
        return "rate_limited"
    if "overloaded" in text or "capacity" in text or "529" in text:
        return "overloaded"
    if any(token in text for token in ("model not found", "invalid model", "model_not_found")):
        return "model_not_found"
    if any(token in text for token in ("protocol", "anthropic-version", "messages api", "chat/completions")):
        return "protocol_mismatch"
    if any(token in text for token in ("500", "502", "503", "504", "5xx")):
        return "provider_5xx"
    if any(token in text for token in ("econn", "enotfound", "etimedout", "socket", "fetch failed", "network")):
        return "network_error"
    if str(check.get("returncode")) == "0" and not str(check.get("stdout") or "").strip():
        return "empty_response"
    if check.get("returncode") not in (None, 0, "0"):
        return "tool_cli_error"
    return "unknown_error"


def _health_status(error_class: str, latency_sec: float | None) -> str:
    if error_class == "ok":
        if latency_sec is not None and latency_sec > SLOW_ROUTE_THRESHOLD_SEC:
            return "degraded"
        return "live_healthy"
    if error_class == "cache_unfriendly_chat_completions":
        return "degraded"
    if error_class in {
        "auth_error",
        "cache_sensitive_wrong_protocol",
        "protocol_mismatch",
        "reasoning_content_roundtrip_required",
    }:
        return "blocked"
    return "unhealthy"


def _health_score(
    *,
    ok: bool,
    error_class: str,
    status: str,
    protocol_correct: bool,
    latency_sec: float | None,
    evidence: dict[str, Any],
) -> int:
    score = 0
    if ok:
        score += 40
    if protocol_correct:
        score += 25
    else:
        score -= 100
    if latency_sec is not None and latency_sec <= SLOW_ROUTE_THRESHOLD_SEC:
        score += 10
    if evidence.get("schema") == "cache_transport_evidence.v1" and evidence.get("request_url"):
        score += 10
    if error_class not in {"ok"}:
        score -= 60
    if status == "blocked":
        score = min(score, 0)
    return max(-100, min(100, score))


def _route_health_key(row: dict[str, Any]) -> str:
    parts = [
        row.get("profile"),
        row.get("role"),
        row.get("model"),
        row.get("provider_id"),
        row.get("protocol"),
    ]
    return "|".join(str(part or "") for part in parts)


def _build_route_health_row(result: dict[str, Any], check: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    evidence = check.get("cache_transport_evidence") if isinstance(check.get("cache_transport_evidence"), dict) else {}
    role = str(check.get("role") or check.get("route_id") or route.get("id") or "").strip()
    model = str(route.get("model") or evidence.get("model") or check.get("model") or "").strip()
    provider_id = str(route.get("provider_id") or evidence.get("provider_id") or check.get("provider_id") or "").strip()
    protocol = str(evidence.get("protocol") or route.get("protocol") or check.get("protocol") or "").strip()
    request_url = str(evidence.get("request_url") or check.get("request_url") or "").strip()
    latency_sec = check.get("latency_sec", check.get("elapsed_sec"))
    try:
        latency_value = round(float(latency_sec), 3)
    except (TypeError, ValueError):
        latency_value = None
    protocol_ok = _protocol_correct(route, evidence)
    error_class = _classify_error(check, route)
    status = _health_status(error_class, latency_value)
    row: dict[str, Any] = {
        "schema": HEALTH_SCHEMA,
        "profile": result.get("profile"),
        "trace_id": result.get("trace_id"),
        "source_result_path": result.get("result_path"),
        "role": role,
        "route_id": role,
        "agent": check.get("agent"),
        "model": model,
        "provider_id": provider_id,
        "protocol": protocol,
        "request_url": request_url,
        "route_source": evidence.get("route_source") or "mms_opencode_profile",
        "provider_profile": evidence.get("provider_profile") or (
            "anthropic" if protocol == "anthropic_messages" else (
                "openai" if protocol == "openai_responses" else "openai_compatible"
            )
        ),
        "started_at": check.get("started_at"),
        "finished_at": check.get("finished_at") or result.get("generated_at"),
        "elapsed_sec": latency_value,
        "latency_sec": latency_value,
        "status": status,
        "error_class": error_class,
        "health_score": _health_score(
            ok=bool(check.get("ok")),
            error_class=error_class,
            status=status,
            protocol_correct=protocol_ok,
            latency_sec=latency_value,
            evidence=evidence,
        ),
        "fallback_used": bool(evidence.get("fallback_used") or check.get("fallback_used")),
        "fallback_reason": str(evidence.get("fallback_reason") or check.get("fallback_reason") or ""),
        "cache_transport_evidence": evidence,
    }
    row["route_key"] = _route_health_key(row)
    return row


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _latest_health_payload(ledger_path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("route_key") or _route_health_key(row))
        existing = latest.get(key)
        if existing is None or str(row.get("finished_at") or "") >= str(existing.get("finished_at") or ""):
            latest[key] = row
    status_counts: dict[str, int] = {}
    for row in latest.values():
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": HEALTH_LATEST_SCHEMA,
        "generated_at": _now_iso(),
        "ledger_path": str(ledger_path),
        "route_count": len(latest),
        "status_counts": dict(sorted(status_counts.items())),
        "routes": {
            key: latest[key]
            for key in sorted(
                latest,
                key=lambda item: (
                    str(latest[item].get("profile") or ""),
                    str(latest[item].get("role") or ""),
                    str(latest[item].get("model") or ""),
                    str(latest[item].get("provider_id") or ""),
                    str(latest[item].get("protocol") or ""),
                ),
            )
        },
    }


def _write_health_ledgers(repo_root: Path, result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("live"):
        return {"enabled": False, "reason": "dry_smoke"}

    routes_by_id = {
        str(route.get("id") or ""): route
        for route in result.get("routes", [])
        if isinstance(route, dict)
    }
    rows: list[dict[str, Any]] = []
    for check in result.get("checks", []):
        if not isinstance(check, dict) or not check.get("agent"):
            continue
        route_id = str(check.get("route_id") or check.get("role") or "")
        rows.append(_build_route_health_row(result, check, routes_by_id.get(route_id, {})))

    health_dir = repo_root / HEALTH_DIR
    health_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = health_dir / HEALTH_LEDGER_NAME
    latest_path = health_dir / HEALTH_LATEST_NAME
    if rows:
        with ledger_path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    all_rows = _load_jsonl_rows(ledger_path)
    latest_payload = _latest_health_payload(ledger_path, all_rows)
    tmp_path = latest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(latest_path)
    return {
        "enabled": True,
        "rows_written": len(rows),
        "ledger_path": str(ledger_path),
        "latest_path": str(latest_path),
        "status_counts": latest_payload.get("status_counts", {}),
        "route_count": latest_payload.get("route_count", 0),
    }


def _health_summary_for_routes(repo_root: Path, profile: str, routes: list[dict[str, Any]]) -> dict[str, Any]:
    latest = mms_core._load_opencode_route_health_latest(repo_root)
    route_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for route in routes:
        if not isinstance(route, dict):
            continue
        role = str(route.get("id") or "").strip()
        row = mms_core._opencode_route_health_for_route(latest, profile, role, route)
        status = str((row or {}).get("status") or "untested")
        status_counts[status] = status_counts.get(status, 0) + 1
        route_rows.append(
            {
                "role": role,
                "model": route.get("model"),
                "provider_id": route.get("provider_id"),
                "protocol": route.get("protocol"),
                "status": status,
                "error_class": (row or {}).get("error_class") or ("untested" if row is None else ""),
                "health_score": (row or {}).get("health_score"),
                "latency_sec": (row or {}).get("latency_sec"),
                "finished_at": (row or {}).get("finished_at"),
                "fallback_reason": (row or {}).get("fallback_reason") or "",
            }
        )
    return {
        "schema": "mms.opencode_route_health_summary.v1",
        "profile": profile,
        "latest_path": mms_core._opencode_health_latest_path(repo_root),
        "route_count": len(route_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "routes": route_rows,
    }


def _run_agent_list(env: dict[str, str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["opencode", "--pure", "agent", "list"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "cmd": "opencode --pure agent list",
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "_raw": f"{completed.stdout}\n{completed.stderr}",
        "stdout": _trim(completed.stdout),
        "stderr": _trim(completed.stderr),
    }


def _run_live_agent(
    env: dict[str, str],
    agent: str,
    model_ref: str,
    timeout: int,
    routes_by_model_ref: dict[str, dict[str, Any]],
    *,
    primary_model_ref: str,
) -> dict[str, Any]:
    message = "MMS OpenCode route smoke. Reply exactly OK and nothing else."
    cmd = ["opencode", "run", "--pure", "--agent", agent, "-m", model_ref, message]
    started = time.time()
    started_at = _iso_from_epoch(started)
    route = routes_by_model_ref.get(model_ref, {})
    fallback_used = bool(primary_model_ref and model_ref != primary_model_ref)
    fallback_reason = "smoke selected non-primary route" if fallback_used else ""
    try:
        completed = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        finished = time.time()
        elapsed = round(finished - started, 3)
        combined = f"{completed.stdout}\n{completed.stderr}"
        evidence = _configured_transport_evidence(
            route,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        return {
            "agent": agent,
            "model": model_ref,
            "role": route.get("id"),
            "route_id": route.get("id"),
            "provider_id": route.get("provider_id"),
            "protocol": evidence.get("protocol"),
            "request_url": evidence.get("request_url"),
            "ok": completed.returncode == 0 and "OK" in combined.upper(),
            "returncode": completed.returncode,
            "started_at": started_at,
            "finished_at": _iso_from_epoch(finished),
            "elapsed_sec": elapsed,
            "latency_sec": elapsed,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "stdout": _trim(completed.stdout),
            "stderr": _trim(completed.stderr),
            "cache_transport_evidence": evidence,
        }
    except subprocess.TimeoutExpired as exc:
        finished = time.time()
        elapsed = round(finished - started, 3)
        evidence = _configured_transport_evidence(
            route,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        return {
            "agent": agent,
            "model": model_ref,
            "role": route.get("id"),
            "route_id": route.get("id"),
            "provider_id": route.get("provider_id"),
            "protocol": evidence.get("protocol"),
            "request_url": evidence.get("request_url"),
            "ok": False,
            "returncode": "timeout",
            "started_at": started_at,
            "finished_at": _iso_from_epoch(finished),
            "elapsed_sec": elapsed,
            "latency_sec": elapsed,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "stdout": _trim(exc.stdout or ""),
            "stderr": _trim(exc.stderr or ""),
            "cache_transport_evidence": evidence,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke MMS OpenCode profile config; --live performs real model calls.")
    parser.add_argument(
        "--profile",
        default="agent",
        help="OpenCode mode/profile to smoke: agent / omo / raw",
    )
    parser.add_argument("--live", action="store_true", help="Run real opencode run calls for each selected agent")
    parser.add_argument("--agent", action="append", help="Agent to live-smoke. Repeatable. Default: all profile agents")
    parser.add_argument("--timeout", type=int, default=90, help="Timeout per opencode command")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--health-summary", action="store_true", help="Include repo-local route health summary from latest.json")
    parser.add_argument("--trace-id", help="Existing/new Moebius trace id")
    args = parser.parse_args()

    canonical_profile, _entrypoint = mms_core._opencode_profile_selection(args.profile)
    if not canonical_profile:
        parser.error(f"--profile 仅支持 OpenCode mode：{', '.join(mms_core._opencode_profile_selection_ids())}")

    repo_root = Path(os.environ.get("MMS_TARGET_REPO") or ROOT_DIR).resolve()
    trace_id = args.trace_id or f"trc-{_now_slug()}-opencode-smoke"
    _init_trace(repo_root, trace_id, canonical_profile, args.live)

    result: dict[str, Any] = {
        "schema": "mms.opencode_profile_smoke.v1",
        "profile": canonical_profile,
        "requested_profile": args.profile,
        "live": bool(args.live),
        "trace_id": trace_id,
        "trace_path": str(repo_root / ".ai" / "trace" / trace_id),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agents": {},
        "checks": [],
    }

    try:
        model_info, runtime = _resolve_profile(args.profile)
        runtime_profile = str(runtime.get("opencode_profile") or args.profile)
        result["model_info"] = model_info
        result["runtime"] = {
            "id": runtime.get("id"),
            "name": runtime.get("name"),
            "profile": runtime_profile,
            "entrypoint": runtime.get("opencode_entrypoint") or "tui",
            "agent": runtime.get("opencode_agent"),
        }
        result["routes"] = [
            {
                "id": route.get("id"),
                "model": route.get("model"),
                "provider_id": route.get("provider_id"),
                "protocol": route.get("protocol"),
                "openai_base_url": route.get("openai_base_url"),
                "anthropic_base_url": route.get("anthropic_base_url"),
            }
            for route in runtime.get("opencode_routes", [])
            if isinstance(route, dict)
        ]
        with tempfile.TemporaryDirectory(prefix="mms-opencode-smoke-") as tmp:
            env, config_path, payload = _build_temp_env(runtime, model_info, Path(tmp))
            result["config_path"] = str(config_path)
            result["default_model"] = payload.get("model")
            result["default_agent"] = payload.get("default_agent")
            result["agents"] = _agent_model_map(payload)
            routes_by_ref = _route_lookup(runtime, model_info.get("model") or runtime.get("model") or "")
            result["launch_candidates"] = [
                {
                    "route_key": item.get("route_key"),
                    "agent": item.get("agent"),
                    "model": item.get("model_ref"),
                }
                for item in mms_launchers._opencode_launch_candidates(
                    runtime,
                    mms_launchers._opencode_runtime_routes(runtime, model_info.get("model") or runtime.get("model") or ""),
                    model_info.get("model") or runtime.get("model") or "",
                )
            ]
            list_check = _run_agent_list(env, args.timeout)
            expected_agents = set(result["agents"])
            listed = str(list_check.pop("_raw", ""))
            list_check["all_agents_listed"] = all(agent in listed for agent in expected_agents)
            list_check["ok"] = bool(list_check["ok"] and list_check["all_agents_listed"])
            result["checks"].append(list_check)

            if args.live:
                target_agents = args.agent or sorted(result["agents"])
                for agent in target_agents:
                    model_ref = result["agents"].get(agent)
                    if not model_ref:
                        result["checks"].append({"agent": agent, "ok": False, "status": "missing_agent"})
                        continue
                    result["checks"].append(
                        _run_live_agent(
                            env,
                            agent,
                            model_ref,
                            args.timeout,
                            routes_by_ref,
                            primary_model_ref=str(result.get("default_model") or ""),
                        )
                    )
    except Exception as exc:  # noqa: BLE001 - command should produce durable failure JSON
        result["error"] = str(exc)
        result["ok"] = False
    else:
        result["ok"] = all(bool(item.get("ok")) for item in result.get("checks", []))

    trace_dir = repo_root / ".ai" / "trace" / trace_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    result_path = trace_dir / "opencode-smoke-result.json"
    result["result_path"] = str(result_path)
    if args.live:
        try:
            result["health"] = _write_health_ledgers(repo_root, result)
        except Exception as exc:  # noqa: BLE001 - health persistence is part of live smoke correctness
            result["health_error"] = str(exc)
            result["ok"] = False
    if args.health_summary:
        result["health_summary"] = _health_summary_for_routes(
            repo_root,
            str((result.get("runtime") or {}).get("profile") or args.profile),
            [route for route in result.get("routes", []) if isinstance(route, dict)],
        )
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _record_trace_event(repo_root, trace_id, "pass" if result.get("ok") else "fail", result)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"[{status}] profile={canonical_profile} requested={args.profile} live={args.live} trace={trace_id}")
        print(f"result={result_path}")
        print(f"default={result.get('default_agent')} {result.get('default_model')}")
        for agent, model in sorted((result.get("agents") or {}).items()):
            print(f"agent={agent} model={model}")
        for check in result.get("checks", []):
            label = check.get("agent") or check.get("cmd") or check.get("status") or "check"
            print(f"check={'PASS' if check.get('ok') else 'FAIL'} {label}")
        if args.health_summary:
            summary = result.get("health_summary") or {}
            print(f"health={summary.get('status_counts', {})} latest={summary.get('latest_path')}")
            for row in summary.get("routes", []):
                print(
                    "route-health="
                    f"{row.get('status')} "
                    f"{row.get('role')} "
                    f"{row.get('model')} "
                    f"{row.get('provider_id')} "
                    f"{row.get('protocol')} "
                    f"error={row.get('error_class')}"
                )

    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
