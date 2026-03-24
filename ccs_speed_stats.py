"""Best-effort model speed stats for MMS bridge traffic."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - not expected on macOS/Linux
    fcntl = None


PRIMARY_CONFIG_DIR = Path(os.path.expanduser("~/.config/mms"))
SPEED_STATS_PATH = PRIMARY_CONFIG_DIR / "speed-stats.json"
SPEED_STATS_LOCK_PATH = PRIMARY_CONFIG_DIR / "speed-stats.lock"
ALPHA = 0.2
WARMUP_SAMPLES = 5
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60
SCHEMA_VERSION = 2

_PROCESS_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_model_name(model_name: str | None) -> str:
    return str(model_name or "").strip()


def _normalize_url(url: str | None) -> str:
    return str(url or "").strip().rstrip("/")


def _is_speed_entry(entry: object) -> bool:
    return isinstance(entry, dict) and any(
        key in entry
        for key in ("ttfb_avg_ms", "tps_avg", "samples", "tps_samples", "warming_up", "last_updated")
    )


def _clone_json(data):
    return json.loads(json.dumps(data))


def _load_stats_unlocked() -> dict:
    if not SPEED_STATS_PATH.exists():
        return {}
    try:
        data = json.loads(SPEED_STATS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@contextmanager
def _locked_stats():
    with _PROCESS_LOCK:
        PRIMARY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SPEED_STATS_LOCK_PATH, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield _load_stats_unlocked()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _rolling_average(previous: float | int | None, previous_samples: int, current: float) -> float:
    if previous is None or previous_samples <= 0:
        return current
    if previous_samples < WARMUP_SAMPLES:
        return ((float(previous) * previous_samples) + current) / (previous_samples + 1)
    return (float(previous) * (1 - ALPHA)) + (current * ALPHA)


def _age_seconds(last_updated: str | None) -> float | None:
    if not last_updated:
        return None
    try:
        stamp = datetime.fromisoformat(last_updated)
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())


def build_provider_speed_scope(provider: dict | None) -> dict:
    raw = dict(provider or {})
    provider_id = str(raw.get("id") or raw.get("provider_id") or "").strip()
    provider_name = str(raw.get("name") or raw.get("provider_name") or provider_id or "provider").strip()
    base_url = _normalize_url(raw.get("base_url"))
    openai_base_url = _normalize_url(raw.get("openai_base_url"))
    anthropic_base_url = _normalize_url(raw.get("anthropic_base_url"))

    identity = {
        key: value
        for key, value in {
            "base_url": base_url,
            "openai_base_url": openai_base_url,
            "anthropic_base_url": anthropic_base_url,
        }.items()
        if value
    }
    if identity:
        identity_kind = "endpoint"
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        identity_kind = "provider_id"
        canonical = provider_id or provider_name or "unknown"

    provider_key = f"provider-{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:12]}"
    return {
        "provider_key": provider_key,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "identity_kind": identity_kind,
        "base_url": base_url,
        "openai_base_url": openai_base_url,
        "anthropic_base_url": anthropic_base_url,
    }


def _provider_aliases(scope: dict) -> list[str]:
    aliases = []
    provider_id = str(scope.get("provider_id") or "").strip()
    if provider_id:
        aliases.append(f"id:{provider_id}")
    for field in ("base_url", "openai_base_url", "anthropic_base_url"):
        value = _normalize_url(scope.get(field))
        if value:
            aliases.append(f"url:{field}:{value}")
    return aliases


def _normalized_store(raw_stats: dict | None) -> dict:
    stats = dict(raw_stats or {})
    providers = stats.get("_providers")
    aliases = stats.get("_aliases")
    scoped_models = stats.get("_scoped_models")
    legacy_unscoped = stats.get("_legacy_unscoped")

    if not isinstance(providers, dict):
        providers = {}
    if not isinstance(aliases, dict):
        aliases = {}
    if not isinstance(scoped_models, dict):
        scoped_models = {}
    if not isinstance(legacy_unscoped, dict):
        legacy_unscoped = {}

    if stats.get("_schema_version") != SCHEMA_VERSION and not providers and not legacy_unscoped:
        for key, value in list(stats.items()):
            if key.startswith("_"):
                continue
            if _is_speed_entry(value):
                legacy_unscoped[key] = value

    stats["_schema_version"] = SCHEMA_VERSION
    stats["_providers"] = providers
    stats["_aliases"] = aliases
    stats["_scoped_models"] = scoped_models
    if legacy_unscoped:
        stats["_legacy_unscoped"] = legacy_unscoped
    else:
        stats.pop("_legacy_unscoped", None)
    return stats


def _weighted_average(entries: list[dict], value_key: str, sample_key: str) -> float | None:
    total_weight = 0
    weighted_sum = 0.0
    for entry in entries:
        weight = int(entry.get(sample_key) or 0)
        value = entry.get(value_key)
        if weight <= 0 or not isinstance(value, (int, float)):
            continue
        total_weight += weight
        weighted_sum += float(value) * weight
    if total_weight <= 0:
        return None
    return round(weighted_sum / total_weight, 2)


def _merge_entries(entries: list[dict]) -> dict | None:
    valid_entries = [entry for entry in entries if _is_speed_entry(entry)]
    if not valid_entries:
        return None
    samples = sum(int(entry.get("samples") or 0) for entry in valid_entries)
    tps_samples = sum(int(entry.get("tps_samples") or 0) for entry in valid_entries)
    ttfb_avg_ms = _weighted_average(valid_entries, "ttfb_avg_ms", "samples")
    tps_avg = _weighted_average(valid_entries, "tps_avg", "tps_samples")
    last_updated_values = [str(entry.get("last_updated") or "").strip() for entry in valid_entries if entry.get("last_updated")]
    merged = {
        "ttfb_avg_ms": ttfb_avg_ms,
        "tps_avg": tps_avg,
        "samples": samples,
        "tps_samples": tps_samples,
        "warming_up": samples < WARMUP_SAMPLES,
        "last_updated": max(last_updated_values) if last_updated_values else "",
    }
    return merged


def _rebuild_compat_views(stats: dict, *, touch: bool) -> dict:
    providers = stats.get("_providers") or {}
    legacy_unscoped = stats.get("_legacy_unscoped") or {}
    scoped_models = {}
    aggregated = {}

    for provider_key, provider_entry in providers.items():
        if not isinstance(provider_entry, dict):
            continue
        provider_models = provider_entry.get("models") or {}
        if not isinstance(provider_models, dict):
            continue
        provider_id = str(provider_entry.get("provider_id") or "").strip()
        provider_name = str(provider_entry.get("provider_name") or provider_id or provider_key).strip()
        for model_name, entry in provider_models.items():
            if not _is_speed_entry(entry):
                continue
            model_id = _normalize_model_name(model_name)
            if not model_id:
                continue
            scoped_key = f"{provider_key}::{model_id}"
            scoped_models[scoped_key] = {
                "provider_key": provider_key,
                "provider_id": provider_id,
                "provider_name": provider_name,
                "model": model_id,
                "ttfb_avg_ms": entry.get("ttfb_avg_ms"),
                "tps_avg": entry.get("tps_avg"),
                "samples": int(entry.get("samples") or 0),
                "tps_samples": int(entry.get("tps_samples") or 0),
                "warming_up": bool(entry.get("warming_up")),
                "last_updated": entry.get("last_updated") or "",
            }
            aggregated.setdefault(model_id, []).append(entry)

    for model_name, entry in legacy_unscoped.items():
        if _is_speed_entry(entry):
            aggregated.setdefault(model_name, []).append(entry)

    for key in list(stats.keys()):
        if key.startswith("_"):
            continue
        stats.pop(key, None)

    for model_name in sorted(aggregated):
        merged = _merge_entries(aggregated[model_name])
        if merged is not None:
            stats[model_name] = merged

    stats["_scoped_models"] = scoped_models
    if touch:
        stats["_updated_at"] = _utc_now()
    else:
        stats["_updated_at"] = str(stats.get("_updated_at") or "")
    return stats


def _resolve_provider_entry(stats: dict, provider: dict | None) -> tuple[dict | None, dict | None]:
    if not provider:
        return None, None

    scope = build_provider_speed_scope(provider)
    providers = stats.get("_providers") or {}
    provider_entry = providers.get(scope["provider_key"])
    if isinstance(provider_entry, dict):
        return scope, provider_entry

    for alias in _provider_aliases(scope):
        provider_key = (stats.get("_aliases") or {}).get(alias)
        if provider_key and isinstance(providers.get(provider_key), dict):
            scope["provider_key"] = provider_key
            return scope, providers[provider_key]
    return scope, None


def load_speed_stats() -> dict:
    with _locked_stats() as stats:
        normalized = _normalized_store(stats)
        return _clone_json(_rebuild_compat_views(normalized, touch=False))


def get_speed_entry(model_name: str, *, provider: dict | None = None, max_age_seconds: int | None = None) -> dict | None:
    normalized = _normalize_model_name(model_name)
    if not normalized:
        return None

    stats = load_speed_stats()
    entry = None
    provider_scope = None
    if provider:
        provider_scope, provider_entry = _resolve_provider_entry(stats, provider)
        if provider_entry:
            provider_models = provider_entry.get("models") or {}
            scoped_entry = provider_models.get(normalized)
            if isinstance(scoped_entry, dict):
                entry = dict(scoped_entry)
                entry["provider_key"] = provider_scope.get("provider_key")
                entry["provider_id"] = provider_entry.get("provider_id") or provider_scope.get("provider_id")
                entry["provider_name"] = provider_entry.get("provider_name") or provider_scope.get("provider_name")

    if entry is None:
        fallback = stats.get(normalized)
        if isinstance(fallback, dict):
            entry = dict(fallback)

    if entry is None:
        return None

    age = _age_seconds(entry.get("last_updated"))
    entry["age_seconds"] = age
    entry["is_stale"] = bool(age is not None and age > STALE_AFTER_SECONDS)
    if max_age_seconds is not None and age is not None and age > max_age_seconds:
        return None
    return entry


def record_model_speed(
    model_name: str,
    *,
    ttfb_ms: float,
    total_ms: float | None = None,
    output_tokens: int | None = None,
    provider: dict | None = None,
) -> None:
    normalized = _normalize_model_name(model_name)
    if not normalized or ttfb_ms <= 0:
        return

    tps = None
    if total_ms is not None and total_ms > ttfb_ms and output_tokens and output_tokens > 0:
        body_seconds = (total_ms - ttfb_ms) / 1000.0
        if body_seconds > 0:
            tps = output_tokens / body_seconds

    with _locked_stats() as raw_stats:
        stats = _normalized_store(raw_stats)
        scope = build_provider_speed_scope(provider)
        providers = stats.setdefault("_providers", {})
        provider_key = scope["provider_key"]
        provider_entry = providers.get(provider_key)
        if not isinstance(provider_entry, dict):
            provider_entry = {"provider_key": provider_key, "provider_ids": [], "models": {}}
            providers[provider_key] = provider_entry

        provider_entry["provider_key"] = provider_key
        provider_entry["provider_name"] = scope.get("provider_name") or provider_entry.get("provider_name") or provider_key
        provider_entry["identity_kind"] = scope.get("identity_kind") or provider_entry.get("identity_kind") or "provider_id"
        provider_entry["last_seen_at"] = _utc_now()

        provider_id = str(scope.get("provider_id") or "").strip()
        if provider_id:
            provider_entry["provider_id"] = provider_id
            provider_ids = [str(item).strip() for item in provider_entry.get("provider_ids", []) if str(item).strip()]
            if provider_id not in provider_ids:
                provider_ids.append(provider_id)
            provider_entry["provider_ids"] = provider_ids

        for field in ("base_url", "openai_base_url", "anthropic_base_url"):
            value = _normalize_url(scope.get(field))
            if value:
                provider_entry[field] = value

        aliases = stats.setdefault("_aliases", {})
        for alias in _provider_aliases(scope):
            aliases[alias] = provider_key

        provider_models = provider_entry.get("models")
        if not isinstance(provider_models, dict):
            provider_models = {}
            provider_entry["models"] = provider_models

        entry = provider_models.get(normalized) or {}
        samples = int(entry.get("samples") or 0)
        tps_samples = int(entry.get("tps_samples") or 0)

        updated = {
            "ttfb_avg_ms": round(_rolling_average(entry.get("ttfb_avg_ms"), samples, float(ttfb_ms)), 2),
            "tps_avg": entry.get("tps_avg"),
            "samples": samples + 1,
            "tps_samples": tps_samples,
            "warming_up": samples + 1 < WARMUP_SAMPLES,
            "last_updated": _utc_now(),
        }
        if tps is not None and tps > 0:
            updated["tps_avg"] = round(_rolling_average(entry.get("tps_avg"), tps_samples, float(tps)), 2)
            updated["tps_samples"] = tps_samples + 1

        provider_models[normalized] = updated
        _atomic_write_json(SPEED_STATS_PATH, _rebuild_compat_views(stats, touch=True))
