"""OpenCode route health snapshot helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

OPENCODE_HEALTH_REL_PATH = os.path.join(".ai", "opencode-health", "latest.json")
OPENCODE_HEALTH_UNHEALTHY_TTL_SEC = 15 * 60
OPENCODE_HEALTH_STATUS_RANK = {
    "live_healthy": 0,
    "degraded": 1,
    "untested": 2,
    "unhealthy": 3,
    "blocked": 4,
}


def opencode_health_repo_root(repo_root=None):
    root = str(repo_root or os.environ.get("MMS_TARGET_REPO") or os.path.dirname(os.path.abspath(__file__))).strip()
    return os.path.abspath(os.path.expanduser(root))


def opencode_health_latest_path(repo_root=None):
    return os.path.join(opencode_health_repo_root(repo_root), OPENCODE_HEALTH_REL_PATH)


def opencode_route_health_key(profile, role, model, provider_id, protocol):
    return "|".join(str(item or "") for item in (profile, role, model, provider_id, protocol))


def load_opencode_route_health_latest(repo_root=None):
    path = opencode_health_latest_path(repo_root)
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    routes = payload.get("routes")
    if not isinstance(routes, dict):
        return {}
    latest = {}
    for key, row in routes.items():
        if isinstance(row, dict):
            latest[str(key)] = dict(row)
    return latest


def opencode_parse_health_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def opencode_route_health_for_route(latest_health, profile, role, route):
    if not isinstance(route, dict):
        return None
    key = opencode_route_health_key(
        profile,
        role or route.get("id"),
        route.get("model"),
        route.get("provider_id"),
        route.get("protocol"),
    )
    row = latest_health.get(key) if isinstance(latest_health, dict) else None
    if not isinstance(row, dict):
        return None
    model = str(route.get("model") or "").strip().lower()
    protocol = str(route.get("protocol") or "").strip()
    if (
        model.startswith("mimo-")
        and protocol == "openai_chat_completions"
        and row.get("error_class") == "cache_sensitive_wrong_protocol"
    ):
        # Older smoke policy incorrectly marked direct MiMo OpenAI-compatible
        # routes as "wrong protocol". The current MiMo OpenCode docs make this
        # the official protocol, so ignore stale rows until the next smoke run.
        return None
    return row


def opencode_route_health_is_fresh(row, *, now=None, ttl_sec=OPENCODE_HEALTH_UNHEALTHY_TTL_SEC):
    finished_at = opencode_parse_health_timestamp(row.get("finished_at") if isinstance(row, dict) else None)
    if finished_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = (current - finished_at).total_seconds()
    return age >= 0 and age <= ttl_sec


def opencode_route_health_allows_route(row, *, now=None, is_fresh=opencode_route_health_is_fresh):
    if not row:
        return True
    status = str(row.get("status") or "untested")
    if status == "blocked":
        return False
    if status == "unhealthy" and is_fresh(row, now=now):
        return False
    return True


def opencode_route_health_sort_key(row):
    status = str((row or {}).get("status") or "untested")
    return (
        OPENCODE_HEALTH_STATUS_RANK.get(status, OPENCODE_HEALTH_STATUS_RANK["untested"]),
        -int((row or {}).get("health_score") or 0),
        str((row or {}).get("finished_at") or ""),
    )


__all__ = [
    "OPENCODE_HEALTH_REL_PATH",
    "OPENCODE_HEALTH_STATUS_RANK",
    "OPENCODE_HEALTH_UNHEALTHY_TTL_SEC",
    "load_opencode_route_health_latest",
    "opencode_health_latest_path",
    "opencode_health_repo_root",
    "opencode_parse_health_timestamp",
    "opencode_route_health_allows_route",
    "opencode_route_health_for_route",
    "opencode_route_health_is_fresh",
    "opencode_route_health_key",
    "opencode_route_health_sort_key",
]
