from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import mms_registry


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_PATH = ROOT / "scripts" / "mms_health_watchdog.py"


def _load_watchdog():
    spec = importlib.util.spec_from_file_location("mms_health_watchdog", WATCHDOG_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_latest_bundle(config_dir: Path, routes: dict) -> None:
    generated = config_dir / "generated"
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    capabilities = generated / "model-capabilities.approved.json"
    mms_registry.write_json_atomic(router, {"version": 1, "routes": routes})
    mms_registry.write_json_atomic(
        lineup,
        {
            "version": 1,
            "routes": {
                name: {"primary": {"provider_id": route["primary"]["provider_id"], "model_id": name}, "fallbacks": []}
                for name, route in routes.items()
            },
        },
    )
    provider_ids = {
        route["primary"]["provider_id"]
        for route in routes.values()
        if isinstance(route.get("primary"), dict) and route["primary"].get("provider_id")
    }
    mms_registry.write_json_atomic(
        profile,
        {
            "schema_version": 1,
            "profiles": {provider_id: {"models_endpoint": "manual"} for provider_id in provider_ids},
        },
    )
    mms_registry.write_json_atomic(policy, {"version": 1, "models": {}})
    mms_registry.write_json_atomic(capabilities, {"schema": "mms.model_capabilities.approved.v1", "models": []})
    mms_registry.export_latest_approved_bundle_manifest(
        generated / "model-registry.latest-approved.json",
        bundle_revision="bundle_watchdog_test",
        capability_revision="cap_watchdog_test",
        route_revision="route_watchdog_test",
        policy_revision="policy_watchdog_test",
        profile_revision="profile_watchdog_test",
        files={
            "router": {"path": router, "canonical_path": "generated/model-routes.json", "sensitivity": "secret"},
            "lineup": {"path": lineup, "canonical_path": "generated/model-routes.lineup.json", "sensitivity": "non-secret"},
            "profile": {"path": profile, "canonical_path": "generated/provider-profiles.generated.json", "sensitivity": "non-secret"},
            "policy": {"path": policy, "canonical_path": "generated/model-policy.effective.json", "sensitivity": "non-secret"},
            "capabilities": {"path": capabilities, "canonical_path": "generated/model-capabilities.approved.json", "sensitivity": "non-secret"},
        },
    )


def test_watchdog_prefers_verified_latest_bundle_over_stale_root_routes(tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    stale_root = {
        "version": 1,
        "routes": {
            "stale": {
                "primary": {
                    "provider_id": "stale",
                    "openai_base_url": "http://82.156.121.141:4001",
                    "api_key": "sk-stale-root-secret",
                },
                "fallbacks": [],
            }
        },
    }
    (tmp_path / "model-routes.json").write_text(json.dumps(stale_root), encoding="utf-8")
    (tmp_path / "model-policy.json").write_text(json.dumps({"version": 1, "models": {}}), encoding="utf-8")
    _write_latest_bundle(
        tmp_path,
        {
            "fresh-model": {
                "primary": {
                    "provider_id": "fresh",
                    "openai_base_url": "https://fresh.example/v1",
                    "api_key": "sk-fresh-secret",
                },
                "fallbacks": [],
            }
        },
    )

    report = watchdog.build_report(tmp_path, timeout=1, require_bundle=True)

    assert report["route_source"] == "latest-approved"
    assert report["status"] == "ok"
    assert report["bundle"]["status"] == "ok"
    assert not any(item["name"] == "http://82.156.121.141:4001" for item in report["failures"])


def test_watchdog_verified_bundle_ignores_stale_root_provider_metadata(tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    (tmp_path / "config.toml").write_text(
        """
[[providers]]
id = "fresh"
models_endpoint = "https://stale.example.invalid/models"
""".lstrip(),
        encoding="utf-8",
    )
    _write_latest_bundle(
        tmp_path,
        {
            "fresh-model": {
                "primary": {
                    "provider_id": "fresh",
                    "openai_base_url": "https://fresh.example/v1",
                    "api_key": "sk-fresh-secret",
                },
                "fallbacks": [],
            }
        },
    )

    def fail_legacy_probe(*_args, **_kwargs):
        raise AssertionError("verified bundle must not probe stale root config.toml provider metadata")

    watchdog.tcp_tls_check = fail_legacy_probe
    watchdog.http_get_json = fail_legacy_probe

    report = watchdog.build_report(tmp_path, timeout=1, require_bundle=True)

    assert report["route_source"] == "latest-approved"
    assert report["status"] == "ok"
    assert report["bundle"]["status"] == "ok"
    assert not any(item.get("url") == "https://stale.example.invalid/models" for item in report["results"])


def test_watchdog_fails_closed_on_invalid_latest_bundle(tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    _write_latest_bundle(
        tmp_path,
        {
            "fresh-model": {
                "primary": {
                    "provider_id": "fresh",
                    "openai_base_url": "https://fresh.example/v1",
                    "api_key": "sk-fresh-secret",
                },
                "fallbacks": [],
            }
        },
    )
    router = tmp_path / "generated" / "model-routes.json"
    payload = json.loads(router.read_text(encoding="utf-8"))
    payload["routes"]["tampered"] = payload["routes"].pop("fresh-model")
    router.write_text(json.dumps(payload), encoding="utf-8")

    report = watchdog.build_report(tmp_path, timeout=1, require_bundle=True)

    assert report["status"] == "critical"
    assert report["route_source"] == "invalid_latest-approved"
    assert any("stale_or_invalid_bundle" in item["detail"] for item in report["failures"])


def test_watchdog_requires_bundle_for_explicit_config_root(monkeypatch, tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(tmp_path))
    monkeypatch.delenv("MMS_WATCHDOG_REQUIRE_BUNDLE", raising=False)

    args = watchdog.parse_args(["--config-dir", str(tmp_path), "--dry-run"])
    require_bundle = watchdog.resolve_require_bundle(args, tmp_path)
    report = watchdog.build_report(tmp_path, timeout=1, require_bundle=require_bundle)

    assert require_bundle is True
    assert report["status"] == "critical"
    assert report["route_source"] == "invalid_latest-approved"
    assert any("stale_or_invalid_bundle" in item["detail"] for item in report["failures"])


def test_watchdog_stable_default_keeps_legacy_fallback_without_bundle(monkeypatch, tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_WATCHDOG_REQUIRE_BUNDLE", raising=False)

    args = watchdog.parse_args(["--config-dir", str(tmp_path), "--dry-run"])
    require_bundle = watchdog.resolve_require_bundle(args, tmp_path)
    report = watchdog.build_report(tmp_path, timeout=1, require_bundle=require_bundle)

    assert require_bundle is False
    assert report["route_source"] == "legacy-root"


def test_watchdog_require_bundle_env_can_disable_explicit_root_default(monkeypatch, tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("MMS_WATCHDOG_REQUIRE_BUNDLE", "0")

    args = watchdog.parse_args(["--config-dir", str(tmp_path), "--dry-run"])

    assert watchdog.resolve_require_bundle(args, tmp_path) is False


def test_watchdog_default_config_dir_honors_mms_config_dir(monkeypatch, tmp_path: Path) -> None:
    watchdog = _load_watchdog()
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MMS_WATCHDOG_REQUIRE_BUNDLE", raising=False)

    args = watchdog.parse_args(["--dry-run"])
    config_dir = Path(args.config_dir)

    assert config_dir == tmp_path
    assert watchdog.resolve_require_bundle(args, config_dir) is True


def test_watchdog_dry_run_does_not_persist_report_log_or_state(tmp_path: Path, capsys) -> None:
    watchdog = _load_watchdog()

    exit_code = watchdog.main([
        "--config-dir",
        str(tmp_path),
        "--require-bundle",
        "--dry-run",
        "--print-json",
        "--timeout-sec",
        "1",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["notification"]["detail"] == "dry_run"
    assert not (tmp_path / "health-watchdog" / "latest.json").exists()
    assert not (tmp_path / "health-watchdog" / "state.json").exists()
    assert not (tmp_path / "logs" / "health-watchdog.log").exists()


def test_watchdog_non_dry_persists_report_log_and_state(tmp_path: Path, capsys) -> None:
    watchdog = _load_watchdog()

    exit_code = watchdog.main([
        "--config-dir",
        str(tmp_path),
        "--require-bundle",
        "--print-json",
        "--timeout-sec",
        "1",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["notification"]["detail"] == "MMS_FEISHU_WEBHOOK_URL is not set"
    assert (tmp_path / "health-watchdog" / "latest.json").exists()
    assert (tmp_path / "health-watchdog" / "state.json").exists()
    assert (tmp_path / "logs" / "health-watchdog.log").exists()
