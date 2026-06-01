"""Lightweight model health status cache.

Aggregates existing speed-stats data into per-model health records
with status (ok/slow/degraded/blocked) and latency_bucket (fast/medium/slow).
Uses in-memory cache backed by an optional JSON file under the selected MMS config root.
No network probes — purely reads data already collected by mms_runtime.speed_stats.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from mms_state_io import resolve_mms_config_dir
from mms_runtime.speed_stats import get_speed_entry


DEFAULT_HEALTH_CACHE_DIR = Path(resolve_mms_config_dir())
HEALTH_CACHE_DIR = DEFAULT_HEALTH_CACHE_DIR
_REAL_SPEED_STATS_PATH = HEALTH_CACHE_DIR / "speed-stats.json"
HEALTH_CACHE_PATH = HEALTH_CACHE_DIR / "health-cache.json"


def _health_cache_dir() -> Path:
    configured = Path(HEALTH_CACHE_DIR)
    if configured != DEFAULT_HEALTH_CACHE_DIR:
        return configured
    return Path(resolve_mms_config_dir())


def _speed_stats_path() -> Path:
    configured = Path(_REAL_SPEED_STATS_PATH)
    default_path = DEFAULT_HEALTH_CACHE_DIR / "speed-stats.json"
    if configured != default_path:
        return configured
    return _health_cache_dir() / "speed-stats.json"


def _health_cache_path() -> Path:
    configured = Path(HEALTH_CACHE_PATH)
    default_path = DEFAULT_HEALTH_CACHE_DIR / "health-cache.json"
    if configured != default_path:
        return configured
    return _health_cache_dir() / "health-cache.json"


def _load_speed_stats_real() -> dict:
    """Load speed-stats from the selected MMS config root."""
    path = _speed_stats_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


CACHE_TTL_MS = 30000

_OK_TTFB_MAX = 3000
_SLOW_TTFB_MAX = 8000
_FAST_TTFB_MAX = 1500
_MEDIUM_TTFB_MAX = 5000
_FRESH_SECONDS = 86400       # 24h — 有数据就算 fresh
_DEGRADED_SECONDS = 86400    # 纯靠 TTFB 判定，不靠数据年龄
_BLOCKED_SECONDS = 604800    # 7 天无数据才 blocked

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


def _determine_status(ttfb_ms: float | None, age_seconds: float | None) -> str | None:
    """纯基于 TTFB 判定，无数据时返回 None（不显示）。"""
    if ttfb_ms is None:
        return None  # 没数据就不判定，不假装 blocked
    if ttfb_ms > _SLOW_TTFB_MAX:
        return "degraded"
    if ttfb_ms >= _OK_TTFB_MAX:
        return "slow"
    return "ok"


def _determine_latency_bucket(ttfb_ms: float | None) -> str:
    if ttfb_ms is None:
        return "slow"
    if ttfb_ms < _FAST_TTFB_MAX:
        return "fast"
    if ttfb_ms <= _MEDIUM_TTFB_MAX:
        return "medium"
    return "slow"


def _build_health_record(model: str, provider_key: str, entry: dict) -> dict | None:
    ttfb = entry.get("ttfb_avg_ms")
    age = _age_seconds(entry.get("last_updated"))
    status = _determine_status(ttfb, age)
    if status is None:
        return None  # 无数据，不生成记录
    return {
        "model": model,
        "provider_key": provider_key,
        "status": status,
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
        if record is None:
            continue
        existing = records.get(model_id)
        if existing is None or existing["status"] == "degraded":
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
    cache_path = _health_cache_path()
    cache_dir = cache_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=cache_path.name + ".",
        suffix=".tmp",
        dir=str(cache_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, cache_path)
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
