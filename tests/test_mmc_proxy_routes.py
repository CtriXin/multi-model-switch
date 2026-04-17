from __future__ import annotations

import json

import pytest


def _write_routes(path, routes):
    path.write_text(
        json.dumps({"schema_version": 1, "routes": routes}),
        encoding="utf-8",
    )
    return path


def test_load_proxy_routes_rejects_non_loopback_local_proxy(tmp_path):
    from mmc_proxy_routes import load_proxy_routes_file

    routes_file = _write_routes(
        tmp_path / "proxy-routes.json",
        [
            {
                "id": "route-a",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://10.0.0.9:31001",
                "sticky_account_binding": {"email": "demo@example.com"},
                "expected_exit_ip": "1.2.3.4",
            }
        ],
    )

    with pytest.raises(ValueError, match="loopback"):
        load_proxy_routes_file(str(routes_file))


def test_load_proxy_routes_rejects_duplicate_sticky_binding(tmp_path):
    from mmc_proxy_routes import load_proxy_routes_file

    routes_file = _write_routes(
        tmp_path / "proxy-routes.json",
        [
            {
                "id": "route-a",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://127.0.0.1:31001",
                "sticky_account_binding": {"email": "demo@example.com"},
                "expected_exit_ip": "1.2.3.4",
            },
            {
                "id": "route-b",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://127.0.0.1:31002",
                "sticky_account_binding": {"email": "demo@example.com"},
                "expected_exit_ip": "2.2.2.2",
            },
        ],
    )

    with pytest.raises(ValueError, match="sticky_account_binding.email"):
        load_proxy_routes_file(str(routes_file))


def test_load_proxy_routes_matches_localhost_and_normalizes_health_targets(tmp_path):
    from mmc_proxy_routes import find_route_by_local_proxy_url, load_proxy_routes_file

    routes_file = _write_routes(
        tmp_path / "proxy-routes.json",
        [
            {
                "id": "route-a",
                "purpose": "oauth_claude",
                "local_proxy_url": "http://localhost:31001",
                "sticky_account_binding": {"account_uuid": "acc-1"},
                "expected_exit_ip": "1.2.3.4",
                "health_targets": [{"label": "claude", "url": "https://claude.ai"}],
            }
        ],
    )

    catalog = load_proxy_routes_file(str(routes_file))
    route = find_route_by_local_proxy_url(catalog, "http://127.0.0.1:31001")

    assert route is not None
    assert route["id"] == "route-a"
    assert route["expected_exit_ip"] == "1.2.3.4"
    assert route["health_targets"] == [{"label": "claude", "url": "https://claude.ai"}]
