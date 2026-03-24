"""Best-effort model speed stats for MMS bridge traffic."""

from __future__ import annotations

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

_PROCESS_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_model_name(model_name: str | None) -> str:
    return str(model_name or "").strip()


def _load_stats_unlocked() -> dict:
    if not SPEED_STATS_PATH.exists():
        return {}
    try:
        return json.loads(SPEED_STATS_PATH.read_text(encoding="utf-8"))
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


def load_speed_stats() -> dict:
    with _locked_stats() as stats:
        return json.loads(json.dumps(stats))


def get_speed_entry(model_name: str, *, max_age_seconds: int | None = None) -> dict | None:
    normalized = _normalize_model_name(model_name)
    if not normalized:
        return None
    stats = load_speed_stats()
    entry = stats.get(normalized)
    if not isinstance(entry, dict):
        return None
    age = _age_seconds(entry.get("last_updated"))
    entry["age_seconds"] = age
    entry["is_stale"] = bool(age is not None and age > STALE_AFTER_SECONDS)
    if max_age_seconds is not None and age is not None and age > max_age_seconds:
        return None
    return entry


def record_model_speed(model_name: str, *, ttfb_ms: float, total_ms: float | None = None, output_tokens: int | None = None) -> None:
    normalized = _normalize_model_name(model_name)
    if not normalized or ttfb_ms <= 0:
        return

    tps = None
    if total_ms is not None and total_ms > ttfb_ms and output_tokens and output_tokens > 0:
        body_seconds = (total_ms - ttfb_ms) / 1000.0
        if body_seconds > 0:
            tps = output_tokens / body_seconds

    with _locked_stats() as stats:
        entry = stats.get(normalized) or {}
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

        stats[normalized] = updated
        _atomic_write_json(SPEED_STATS_PATH, stats)
