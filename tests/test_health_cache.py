"""Tests for mms_health_cache module."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# Timestamps for testing age-based logic
NOW = datetime.now(timezone.utc).isoformat()
STALE_2H = datetime.fromtimestamp(time.time() - 7200, tz=timezone.utc).isoformat()
STALE_25H = datetime.fromtimestamp(time.time() - 90000, tz=timezone.utc).isoformat()
STALE_8D = datetime.fromtimestamp(time.time() - 691200, tz=timezone.utc).isoformat()


def _entry(ttfb, last_updated=NOW, provider_key="pk-test", **kw):
    return {
        "ttfb_avg_ms": ttfb, "tps_avg": 50.0, "samples": 10,
        "tps_samples": 8, "warming_up": False,
        "last_updated": last_updated, "age_seconds": 0,
        "is_stale": False, "provider_key": provider_key, **kw,
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset module-level cache state between tests."""
    import mms_health_cache as m
    with patch.object(m, "_memory_cache", {}), \
         patch.object(m, "_cache_built_at", ""):
        yield


@pytest.fixture
def mock_empty_stats():
    with patch("mms_health_cache._load_speed_stats_real", return_value={}), \
         patch("mms_health_cache.get_speed_entry", return_value=None), \
         patch("mms_health_cache._persist_cache"):
        yield


# ── status determination ──

class TestDetermineStatus:
    def test_ok_fresh_fast(self):
        from mms_health_cache import _determine_status
        assert _determine_status(500, 10) == "ok"

    def test_ok_boundary(self):
        from mms_health_cache import _determine_status
        assert _determine_status(2999, 100) == "ok"

    def test_slow_at_3000(self):
        from mms_health_cache import _determine_status
        assert _determine_status(3000, 100) == "slow"

    def test_slow_below_8000(self):
        from mms_health_cache import _determine_status
        assert _determine_status(7999, 100) == "slow"

    def test_degraded_high_ttfb(self):
        from mms_health_cache import _determine_status
        assert _determine_status(8001, 100) == "degraded"

    def test_ok_even_hours_old(self):
        from mms_health_cache import _determine_status
        # Good TTFB + data from 2 hours ago = still ok
        assert _determine_status(500, 7200) == "ok"

    def test_none_when_no_data(self):
        from mms_health_cache import _determine_status
        # No TTFB data = None (don't display), not "blocked"
        assert _determine_status(None, None) is None

    def test_none_when_no_ttfb(self):
        from mms_health_cache import _determine_status
        assert _determine_status(None, 10) is None


# ── latency bucket ──

class TestLatencyBucket:
    def test_fast(self):
        from mms_health_cache import _determine_latency_bucket
        assert _determine_latency_bucket(500) == "fast"
        assert _determine_latency_bucket(1499) == "fast"

    def test_medium(self):
        from mms_health_cache import _determine_latency_bucket
        assert _determine_latency_bucket(1500) == "medium"
        assert _determine_latency_bucket(5000) == "medium"

    def test_slow(self):
        from mms_health_cache import _determine_latency_bucket
        assert _determine_latency_bucket(5001) == "slow"

    def test_none_is_slow(self):
        from mms_health_cache import _determine_latency_bucket
        assert _determine_latency_bucket(None) == "slow"


# ── get_model_health ──

class TestGetModelHealth:
    def test_returns_dict_with_entry(self, mock_empty_stats):
        from mms_health_cache import get_model_health
        with patch("mms_health_cache.get_speed_entry", return_value=_entry(800)):
            result = get_model_health("kimi-k2.5")
            assert result is not None
            assert result["status"] == "ok"
            assert result["latency_bucket"] == "fast"
            assert result["model"] == "kimi-k2.5"
            assert "checked_at" in result
            assert result["ttl_ms"] == 30000

    def test_returns_none_no_data(self, mock_empty_stats):
        from mms_health_cache import get_model_health
        result = get_model_health("nonexistent-model")
        assert result is None


# ── get_all_health ──

class TestGetAllHealth:
    def test_empty_stats(self, mock_empty_stats):
        from mms_health_cache import get_all_health
        assert get_all_health() == []

    def test_returns_list_from_scoped_models(self):
        stats = {
            "_scoped_models": {
                "pk::kimi-k2.5": {
                    "model": "kimi-k2.5", "provider_key": "pk",
                    "ttfb_avg_ms": 1200, "last_updated": NOW,
                },
            },
        }
        with patch("mms_health_cache._load_speed_stats_real", return_value=stats), \
             patch("mms_health_cache.get_speed_entry", return_value=None), \
             patch("mms_health_cache._persist_cache"):
            from mms_health_cache import get_all_health
            result = get_all_health()
            assert len(result) == 1
            assert result[0]["model"] == "kimi-k2.5"
            assert result[0]["status"] == "ok"


# ── refresh_health_cache ──

class TestRefresh:
    def test_refresh_rebuilds(self, mock_empty_stats):
        from mms_health_cache import refresh_health_cache, get_all_health
        refresh_health_cache()
        assert get_all_health() == []


# ── cache TTL ──

class TestCacheTTL:
    def test_cache_expired_when_empty(self):
        from mms_health_cache import _cache_expired
        assert _cache_expired() is True

    def test_cache_not_expired_fresh(self):
        import mms_health_cache as m
        m._cache_built_at = datetime.now(timezone.utc).isoformat()
        assert m._cache_expired() is False
