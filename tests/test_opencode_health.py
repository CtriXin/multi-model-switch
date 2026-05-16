from __future__ import annotations

import json
from pathlib import Path

from scripts import smoke_opencode_profile as smoke


def _route(**overrides):
    route = {
        "id": "explore_primary",
        "model": "glm-5-turbo",
        "provider_id": "newapi",
        "protocol": "anthropic_messages",
        "openai_base_url": "https://newapi.example/v1",
        "anthropic_base_url": "https://newapi.example/v1",
    }
    route.update(overrides)
    return route


def _check(**overrides):
    check = {
        "agent": "mobius-explore-glm",
        "model": "mms-explore_primary/glm-5-turbo",
        "role": "explore_primary",
        "route_id": "explore_primary",
        "provider_id": "newapi",
        "ok": True,
        "returncode": 0,
        "started_at": "2026-05-16T10:00:00Z",
        "finished_at": "2026-05-16T10:00:03Z",
        "elapsed_sec": 3.0,
        "latency_sec": 3.0,
        "fallback_used": False,
        "fallback_reason": "",
        "stdout": "OK",
        "stderr": "",
        "cache_transport_evidence": smoke._configured_transport_evidence(
            _route(),
            fallback_used=False,
            fallback_reason="",
        ),
    }
    check.update(overrides)
    return check


def _result(checks):
    return {
        "schema": "mms.opencode_profile_smoke.v1",
        "profile": "lite_pro",
        "live": True,
        "trace_id": "trc-test",
        "generated_at": "2026-05-16T10:00:03Z",
        "result_path": "/repo/.ai/trace/trc-test/opencode-smoke-result.json",
        "routes": [_route()],
        "checks": checks,
    }


def test_opencode_health_row_contains_required_route_fields():
    row = smoke._build_route_health_row(_result([]), _check(), _route())

    assert row["schema"] == "mms.opencode_route_health.v1"
    assert row["profile"] == "lite_pro"
    assert row["role"] == "explore_primary"
    assert row["agent"] == "mobius-explore-glm"
    assert row["model"] == "glm-5-turbo"
    assert row["provider_id"] == "newapi"
    assert row["protocol"] == "anthropic_messages"
    assert row["request_url"] == "https://newapi.example/v1/messages"
    assert row["status"] == "live_healthy"
    assert row["error_class"] == "ok"
    assert row["latency_sec"] == 3.0
    assert row["fallback_reason"] == ""
    assert row["cache_transport_evidence"]["schema"] == "cache_transport_evidence.v1"


def test_opencode_health_ledger_appends_rows_and_refreshes_latest(tmp_path):
    result = _result(
        [
            _check(),
            _check(
                ok=False,
                returncode="timeout",
                finished_at="2026-05-16T10:00:10Z",
                elapsed_sec=10.0,
                latency_sec=10.0,
                stdout="",
                stderr="",
            ),
        ]
    )

    summary = smoke._write_health_ledgers(tmp_path, result)
    ledger_path = Path(summary["ledger_path"])
    latest_path = Path(summary["latest_path"])
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    latest = json.loads(latest_path.read_text(encoding="utf-8"))

    assert summary["rows_written"] == 2
    assert len(rows) == 2
    assert rows[0]["status"] == "live_healthy"
    assert rows[1]["error_class"] == "timeout"
    assert latest["schema"] == "mms.opencode_route_health_latest.v1"
    assert latest["route_count"] == 1
    assert latest["status_counts"] == {"unhealthy": 1}
    assert next(iter(latest["routes"].values()))["finished_at"] == "2026-05-16T10:00:10Z"


def test_opencode_health_blocks_cache_sensitive_non_gpt_chat_completion():
    wrong_route = _route(
        protocol="openai_chat_completions",
        anthropic_base_url="",
    )
    wrong_check = _check(
        cache_transport_evidence=smoke._configured_transport_evidence(
            wrong_route,
            fallback_used=False,
            fallback_reason="",
        ),
        protocol="openai_chat_completions",
        request_url="https://newapi.example/v1/chat/completions",
    )

    row = smoke._build_route_health_row(_result([]), wrong_check, wrong_route)

    assert row["status"] == "blocked"
    assert row["error_class"] == "cache_sensitive_wrong_protocol"
    assert row["health_score"] < 0


def test_opencode_health_summary_reads_latest_snapshot(tmp_path):
    health_dir = tmp_path / ".ai" / "opencode-health"
    health_dir.mkdir(parents=True)
    key = "lite_pro|explore_primary|glm-5-turbo|newapi|anthropic_messages"
    (health_dir / "latest.json").write_text(
        json.dumps(
            {
                "schema": "mms.opencode_route_health_latest.v1",
                "routes": {
                    key: {
                        "status": "degraded",
                        "error_class": "ok",
                        "health_score": 75,
                        "latency_sec": 31.2,
                        "finished_at": "2026-05-16T10:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    summary = smoke._health_summary_for_routes(tmp_path, "lite_pro", [_route()])

    assert summary["status_counts"] == {"degraded": 1}
    assert summary["routes"][0]["role"] == "explore_primary"
    assert summary["routes"][0]["status"] == "degraded"
    assert summary["routes"][0]["error_class"] == "ok"
