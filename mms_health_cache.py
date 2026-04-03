"""Lightweight model health status cache.

Aggregates existing speed-stats data into per-model health records
with status (ok/slow/degraded/blocked) and latency_bucket (fast/medium/slow).
Uses in-memory cache backed by an optional JSON file at ~/.config/mms/health-cache.json.
No network probes — purely reads data already collected by mms_speed_stats.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from mms_speed_stats import get_speed_entry


def _real_home() -> str:
    """Resolve real user home, respecting MMS_REAL_HOME for gateway sessions."""
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return os.path.expanduser("~")


HEALTH_CACHE_DIR = Path(_real_home()) / ".config" / "mms"
_REAL_SPEED_STATS_PATH = HEALTH_CACHE_DIR / "speed-stats.json"


def _load_speed_stats_real() -> dict:
    """Load speed-stats from real user home, bypassing gateway $HOME redirect."""
    if not _REAL_SPEED_STATS_PATH.exists():
        return {}
    try:
        data = json.loads(_REAL_SPEED_STATS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
HEALTH_CACHE_PATH = HEALTH_CACHE_DIR / "health-cache.json"
CACHE_TTL_MS = 30000

_OK_TTFB_MAX = 3000
_SLOW_TTFB_MAX = 8000
_FAST_TTFB_MAX = 1500
_MEDIUM_TTFB_MAX = 5000
_FRESH_SECONDS = 300
_DEGRADED_SECONDS = 600
_BLOCKED_SECONDS = 1800

_lock = threading.Lock()
_memory_cache: dict = {}
_cache_built_at: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(last_updated: str | None) -> float | None:
    if not last_updated:
        return None
    try:
        stamp = datetime.fromisoformat(last_updated)
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


def _cache_expired() -> bool:
    if not _cache_built_at:
        return True
    age = _age_seconds(_cache_built_at)
    return age is None or age * 1000 > CACHE_TTL_MS


def _determine_status(ttfb_ms: float | None, age_seconds: float | None) -> str:
    if ttfb_ms is None or age_seconds is None:
        return "blocked"
    if age_seconds > _BLOCKED_SECONDS:
        return "blocked"
    if ttfb_ms > _SLOW_TTFB_MAX or age_seconds > _DEGRADED_SECONDS:
        return "degraded"
    if ttfb_ms >= _OK_TTFB_MAX:
        return "slow"
    if age_seconds <= _FRESH_SECONDS:
        return "ok"
    return "slow"


def _determine_latency_bucket(ttfb_ms: float | None) -> str:
    if ttfb_ms is None:
        return "slow"
    if ttfb_ms < _FAST_TTFB_MAX:
        return "fast"
    if ttfb_ms <= _MEDIUM_TTFB_MAX:
        return "medium"
    return "slow"


def _build_health_record(model: str, provider_key: str, entry: dict) -> dict:
    ttfb = entry.get("ttfb_avg_ms")
    age = _age_seconds(entry.get("last_updated"))
    return {
        "model": model,
        "provider_key": provider_key,
        "status": _determine_status(ttfb, age),
        "latency_bucket": _determine_latency_bucket(ttfb),
        "checked_at": _utc_now(),
        "ttl_ms": CACHE_TTL_MS,
    }


def _build_all_health() -> dict[str, dict]:
    stats = _load_speed_stats_real()
    records: dict[str, dict] = {}

    scoped_models = stats.get("_scoped_models") or {}
    for scoped_key, scoped_entry in scoped_models.items():
        if not isinstance(scoped_entry, dict):
            continue
        model_id = scoped_entry.get("model") or ""
        pk = scoped_entry.get("provider_key") or ""
        if not model_id:
            continue
        record = _build_health_record(model_id, pk, scoped_entry)
        existing = records.get(model_id)
        if existing is None or existing["status"] in ("degraded", "blocked"):
            records[model_id] = record

    top_level_keys = [k for k in stats if not k.startswith("_")]
    for model_name in top_level_keys:
        entry = stats[model_name]
        if not isinstance(entry, dict):
            continue
        if entry.get("ttfb_avg_ms") is None:
            continue
        if model_name not in records:
            pk = entry.get("provider_key") or ""
            records[model_name] = _build_health_record(model_name, pk, entry)

    return records


def _rebuild_cache() -> None:
    global _memory_cache, _cache_built_at
    _memory_cache = _build_all_health()
    _cache_built_at = _utc_now()


def _persist_cache() -> None:
    payload = {
        "records": _memory_cache,
        "built_at": _cache_built_at,
        "ttl_ms": CACHE_TTL_MS,
    }
    HEALTH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=HEALTH_CACHE_PATH.name + ".",
        suffix=".tmp",
        dir=str(HEALTH_CACHE_DIR),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, HEALTH_CACHE_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def refresh_health_cache() -> None:
    with _lock:
        _rebuild_cache()
        _persist_cache()


def _ensure_cache() -> None:
    with _lock:
        if _cache_expired():
            _rebuild_cache()
            _persist_cache()


def get_model_health(model: str, provider: dict | None = None) -> dict | None:
    _ensure_cache()

    entry = get_speed_entry(model, provider=provider)
    if entry is not None:
        pk = entry.get("provider_key") or ""
        return _build_health_record(model, pk, entry)

    normalized = model.strip()
    with _lock:
        return _memory_cache.get(normalized)


def get_all_health() -> list[dict]:
    _ensure_cache()
    with _lock:
        return list(_memory_cache.values())
