import json
from datetime import datetime, timedelta


def test_gateway_health_cache_preserves_legacy_single_provider_shape(tmp_path):
    from mms_launcher_health import load_gateway_health_cache

    cache_path = tmp_path / "health.json"
    cache_path.write_text(
        json.dumps({"provider_id": "relay-a", "timestamp": "2026-05-31T00:00:00", "ok": True}),
        encoding="utf-8",
    )

    assert load_gateway_health_cache(str(cache_path)) == {
        "relay-a": {"timestamp": "2026-05-31T00:00:00", "ok": True}
    }


def test_gateway_health_cache_saves_provider_map(tmp_path):
    from mms_launcher_health import load_gateway_health_cache, save_gateway_health_cache

    cache_path = tmp_path / "state" / "health.json"
    providers = {"relay-a": {"timestamp": "2026-05-31T00:00:00", "ok": False}}

    save_gateway_health_cache(str(cache_path), providers)

    assert load_gateway_health_cache(str(cache_path)) == providers
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {"providers": providers}


def test_health_check_due_uses_per_provider_timestamp():
    from mms_launcher_health import health_check_due

    now = datetime(2026, 5, 31, 12, 0, 0)
    providers = {
        "fresh": {"timestamp": (now - timedelta(hours=1)).isoformat(), "ok": True},
        "stale": {"timestamp": (now - timedelta(days=2)).isoformat(), "ok": True},
    }

    assert health_check_due(providers, "fresh", now=now) is False
    assert health_check_due(providers, "stale", now=now) is True
    assert health_check_due(providers, "missing", now=now) is True
