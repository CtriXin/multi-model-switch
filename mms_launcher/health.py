"""Health-cache helpers for launcher provider checks."""

import json
import os
from datetime import datetime


def load_gateway_health_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    providers = data.get("providers")
    if isinstance(providers, dict):
        return providers
    provider_id = str(data.get("provider_id") or "").strip()
    timestamp = str(data.get("timestamp") or "").strip()
    if provider_id and timestamp:
        return {
            provider_id: {
                "timestamp": timestamp,
                "ok": bool(data.get("ok")),
            }
        }
    return {}


def save_gateway_health_cache(path, providers):
    if not isinstance(providers, dict):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError:
        pass


def health_check_due(providers, provider_id, *, now=None, ttl_seconds=86400):
    try:
        entry = providers.get(str(provider_id or "").strip())
        if not isinstance(entry, dict):
            return True
        last = datetime.fromisoformat(str(entry.get("timestamp") or ""))
        current = now or datetime.now()
        return (current - last).total_seconds() > ttl_seconds
    except Exception:
        return True
