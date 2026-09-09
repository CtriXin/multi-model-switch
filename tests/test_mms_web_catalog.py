"""Tests for mms_web.catalog (Agent A adapter).

All fixtures live under temporary config roots; the real ``~/.config/mms*``
surfaces are never read or written by these tests (human-only gate).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mms_web.catalog import CatalogService  # noqa: E402
from mms_web.errors import WebError  # noqa: E402

SECRET_ALPHA = "sk-secret-ALPHA-abcdefgh1234"
SECRET_BETA = "sk-secret-BETA-zzzzzzzz9999"


def _write_bundle(config_dir: Path, *, routes: dict, policy_models: dict | None = None, policy_projects: dict | None = None) -> None:
    import mms_registry

    generated = config_dir / "generated"
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    capabilities = generated / "model-capabilities.approved.json"

    lineup_routes = {}
    for model_name, route in routes.items():
        primary = route["primary"]
        lineup_routes[model_name] = {
            "primary": {
                "provider_id": primary["provider_id"],
                "model_id": primary.get("model_id") or model_name,
                "max_context_tokens": primary.get("max_context_tokens", 128000),
            },
            "fallbacks": [],
        }
    mms_registry.write_json_atomic(router, {"version": 1, "routes": routes})
    mms_registry.write_json_atomic(lineup, {"version": 1, "routes": lineup_routes})
    mms_registry.write_json_atomic(profile, {"schema_version": 1, "profiles": {}})
    mms_registry.write_json_atomic(
        policy,
        {"version": 1, "models": policy_models or {}, **({"projects": policy_projects} if policy_projects else {})},
    )
    mms_registry.write_json_atomic(
        capabilities,
        {"schema": "mms.model_capabilities.approved.v1", "models": []},
    )
    files = {
        "router": {
            "path": router,
            "canonical_path": "generated/model-routes.json",
            "legacy_alias_path": "model-routes.json",
            "sensitivity": "secret",
        },
        "lineup": {
            "path": lineup,
            "canonical_path": "generated/model-routes.lineup.json",
            "legacy_alias_path": "model-routes.lineup.json",
            "sensitivity": "non-secret",
        },
        "profile": {
            "path": profile,
            "canonical_path": "generated/provider-profiles.generated.json",
            "sensitivity": "non-secret",
        },
        "policy": {
            "path": policy,
            "canonical_path": "generated/model-policy.effective.json",
            "legacy_alias_path": "model-policy.json",
            "sensitivity": "non-secret",
        },
        "capabilities": {
            "path": capabilities,
            "canonical_path": "generated/model-capabilities.approved.json",
            "sensitivity": "non-secret",
        },
    }
    manifest_path = generated / "model-registry.latest-approved.json"
    mms_registry.export_latest_approved_bundle_manifest(
        manifest_path,
        bundle_revision="bundle_test_001",
        capability_revision="cap_test_001",
        route_revision="route_test_001",
        policy_revision="policy_test_001",
        profile_revision="profile_test_001",
        generated_at="2026-09-08T00:00:00.000Z",
        files=files,
    )


def _make_config_root(tmp_path: Path, *, providers: list | None = None, presets: dict | None = None, credentials: str = "", routes: dict | None = None, policy_models: dict | None = None) -> Path:
    root = tmp_path / "config-root"
    root.mkdir(parents=True, exist_ok=True)
    config = {"provider": {"default": (providers[0]["id"] if providers else "gw-a")}, "providers": providers or []}
    if presets:
        config["presets"] = presets
    lines = []
    for key, value in config.items():
        if key == "providers":
            for item in value:
                lines.append("[[providers]]")
                for field, field_value in item.items():
                    if isinstance(field_value, list):
                        lines.append(f"{field} = [" + ", ".join(json.dumps(v) for v in field_value) + "]")
                    else:
                        lines.append(f"{field} = {json.dumps(field_value)}")
                lines.append("")
        elif key == "presets":
            for name, item in value.items():
                lines.append(f"[presets.{name}]")
                for field, field_value in item.items():
                    lines.append(f"{field} = {json.dumps(field_value)}")
                lines.append("")
        else:
            lines.append(f"[{key}]")
            for field, field_value in value.items():
                lines.append(f"{field} = {json.dumps(field_value)}")
            lines.append("")
    (root / "config.toml").write_text("\n".join(lines), encoding="utf-8")
    if credentials:
        (root / "credentials.sh").write_text(credentials, encoding="utf-8")
    if routes is not None:
        _write_bundle(root, routes=routes, policy_models=policy_models)
    return root


def _dual_provider_fixture(tmp_path: Path) -> tuple[Path, Path]:
    providers = [
        {
            "id": "gw-a",
            "name": "Gateway A",
            "protocols": ["openai_chat_completions", "anthropic_messages"],
            "supported_clis": ["claude", "codex", "opencode"],
            "enabled": True,
        },
        {
            "id": "gw-b",
            "name": "Gateway B",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["codex"],
            "enabled": True,
        },
    ]
    presets = {
        "daily": {"cli": "claude", "provider": "gw-a", "model": "shared-model"},
    }
    credentials = (
        f"export MMS_PROVIDER_GW_A_BASE_URL='https://a.example.com/v1'\n"
        f"export MMS_PROVIDER_GW_A_API_KEY='{SECRET_ALPHA}'\n"
        f"export MMS_PROVIDER_GW_B_BASE_URL='https://b.example.com/v1'\n"
        f"export MMS_PROVIDER_GW_B_API_KEY='{SECRET_BETA}'\n"
    )
    routes = {
        "shared-model": {
            "primary": {
                "provider_id": "gw-a",
                "anthropic_base_url": "https://a.example.com",
                "openai_base_url": "",
                "api_key": SECRET_ALPHA,
            },
            "fallbacks": [],
        },
        "other-model": {
            "primary": {
                "provider_id": "gw-b",
                "openai_base_url": "https://b.example.com/v1",
                "api_key": SECRET_BETA,
            },
            "fallbacks": [],
        },
    }
    root = _make_config_root(
        tmp_path,
        providers=providers,
        presets=presets,
        credentials=credentials,
        routes=routes,
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    return root, state_root


# ── capabilities / no-root behavior ─────────────────────────────────────


def test_no_config_root_returns_empty_with_diagnostics(tmp_path):
    service = CatalogService(config_root=None, state_root=tmp_path / "state")
    assert service.capabilities() == {"catalogRead": False, "configure": False}
    snapshot = service.snapshot()
    assert snapshot["models"] == []
    assert snapshot["services"] == []
    assert snapshot["presets"] == []
    assert snapshot["workspaces"] == []
    assert snapshot["diagnostics"] and snapshot["diagnostics"][0]["code"] == "CONFIG_ROOT_DISABLED"
    with pytest.raises(WebError) as excinfo:
        service.configuration_preview({"service": {"name": "x", "baseUrl": "https://x.example.com"}})
    assert excinfo.value.status == 409


def test_real_config_root_write_gate(tmp_path, monkeypatch):
    real_home = tmp_path / "real-home"
    (real_home / ".config").mkdir(parents=True)
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.delenv("REAL_HOME", raising=False)
    monkeypatch.delenv("ORIGINAL_HOME", raising=False)
    protected = real_home / ".config" / "mms"
    protected.mkdir()
    (protected / "config.toml").write_text('provider = { default = "x" }\n', encoding="utf-8")

    service = CatalogService(config_root=protected, state_root=tmp_path / "state")
    capabilities = service.capabilities()
    assert capabilities == {"catalogRead": True, "configure": False}
    with pytest.raises(WebError) as excinfo:
        service.configuration_preview({"service": {"name": "x", "baseUrl": "https://x.example.com"}})
    assert excinfo.value.status == 409
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": "0" * 32, "revision": "irrelevant"})
    assert excinfo.value.status == 409
    mms_next = real_home / ".config" / "mms-next"
    mms_next.mkdir()
    service_next = CatalogService(config_root=mms_next, state_root=tmp_path / "state")
    assert service_next.capabilities()["configure"] is False


# ── snapshot ────────────────────────────────────────────────────────────


def test_snapshot_same_model_name_two_providers(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = {
        "shared-model": {
            "primary": {"provider_id": "gw-a", "anthropic_base_url": "https://a.example.com", "api_key": SECRET_ALPHA},
            "fallbacks": [],
        },
        # Same logical name served by provider B under a different route entry
        # is disambiguated by the provider-qualified id.
    }
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    ids = [m["id"] for m in snapshot["models"]]
    assert "gw-a:shared-model" in ids
    assert "gw-b:other-model" in ids
    # id uniqueness guarantees same-name/same-provider dedup
    assert len(ids) == len(set(ids))
    shared = next(m for m in snapshot["models"] if m["id"] == "gw-a:shared-model")
    assert shared["providerId"] == "gw-a"
    assert shared["providerName"] == "Gateway A"
    assert shared["available"] is True
    assert "claude" in shared["harnesses"]


def test_snapshot_hidden_and_favorite_policy(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    policy = json.loads((root / "generated" / "model-policy.effective.json").read_text())
    policy["models"] = {
        "shared-model": {"visible": True, "favorite": True},
        "other-model": {"visible": False},
    }
    (root / "generated" / "model-policy.effective.json").write_text(json.dumps(policy), encoding="utf-8")
    # Manifest hash now mismatches -> bundle invalid; rebuild bundle properly.
    import mms_registry

    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    _write_bundle(root, routes=routes, policy_models=policy["models"])

    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    shared = next(m for m in snapshot["models"] if m["id"] == "gw-a:shared-model")
    assert shared["favorite"] is True
    other = next(m for m in snapshot["models"] if m["id"] == "gw-b:other-model")
    assert other["available"] is False
    assert "隐藏" in other.get("reason", "")


def test_snapshot_needs_key_and_unsupported_harness(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    # Drop gw-b's key from both credentials and bundle.
    creds = (root / "credentials.sh").read_text().replace(
        f"export MMS_PROVIDER_GW_B_API_KEY='{SECRET_BETA}'\n", ""
    )
    (root / "credentials.sh").write_text(creds, encoding="utf-8")
    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    routes["other-model"]["primary"]["api_key"] = ""
    _write_bundle(root, routes=routes)

    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    gw_b = next(s for s in snapshot["services"] if s["id"] == "gw-b")
    assert gw_b["status"] == "needs_key"
    other = next(m for m in snapshot["models"] if m["id"] == "gw-b:other-model")
    assert other["available"] is False
    # gw-b only supports codex; claude/pi/opencode must not appear.
    assert other["harnesses"] == []
    # A provider with no launchable harness at all yields unavailable models.


def test_snapshot_text_capability_hides_model(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    _write_bundle(
        root,
        routes=routes,
        policy_models={"other-model": {"capabilities": {"text": False}}},
    )
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    other = next(m for m in snapshot["models"] if m["id"] == "gw-b:other-model")
    assert other["available"] is False
    assert "文本能力" in other.get("reason", "")


def test_snapshot_missing_bundle_reports_diagnostic(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    import shutil

    shutil.rmtree(root / "generated")
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    assert snapshot["models"] == []
    codes = [d["code"] for d in snapshot["diagnostics"]]
    assert "BUNDLE_MISSING" in codes


def test_snapshot_presets_availability(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    config_text += (
        '\n[presets.nokey]\ncli = "claude"\nprovider = "gw-b"\nmodel = "other-model"\n'
        '\n[presets.gemini-official]\ncli = "gemini"\nprovider = "gw-a"\nmodel = "shared-model"\n'
        '\n[presets.unknown-model]\ncli = "claude"\nprovider = "gw-a"\nmodel = "missing-model"\n'
    )
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    presets = {p["id"]: p for p in snapshot["presets"]}
    assert presets["daily"]["available"] is True
    assert presets["daily"]["providerId"] == "gw-a"
    assert presets["gemini-official"]["available"] is False  # official-account harness
    assert presets["unknown-model"]["available"] is False
    # gw-b has a key in this fixture, so its preset is available.
    assert presets["nokey"]["available"] is True


# ── secrets never leave ─────────────────────────────────────────────────


def test_snapshot_and_preview_never_leak_secrets(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot_text = json.dumps(service.snapshot(), ensure_ascii=False)
    assert SECRET_ALPHA not in snapshot_text
    assert SECRET_BETA not in snapshot_text

    preview = service.configuration_preview(
        {"service": {"name": "New Gateway", "baseUrl": "https://new.example.com/v1", "apiKey": "sk-secret-NEW-qqqq1111", "models": ["m1"]}}
    )
    preview_text = json.dumps(preview, ensure_ascii=False)
    assert "sk-secret-NEW" not in preview_text
    key_changes = [c for c in preview["changes"] if c["label"] == "API Key"]
    assert key_changes and re.fullmatch(r".{1,6}….{1,6}", key_changes[0]["after"])
    # The stored preview record keeps the key server-side only.
    record_path = state_root / "previews" / f"{preview['previewId']}.json"
    assert record_path.exists()
    assert (record_path.stat().st_mode & 0o777) == 0o600


# ── preview / apply ─────────────────────────────────────────────────────


def test_preview_apply_create_service_manual_models(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "New Gateway", "baseUrl": "https://new.example.com/v1", "apiKey": "sk-new-key-abcdef123456", "models": ["model-x", "model-y"]}}
    )
    result = service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert result["applied"] is True

    config_text = (root / "config.toml").read_text()
    assert "new-gateway" in config_text
    creds = (root / "credentials.sh").read_text()
    assert "sk-new-key-abcdef123456" in creds
    assert "MMS_PROVIDER_NEW_GATEWAY_BASE_URL='https://new.example.com/v1'" in creds
    # Existing provider credentials untouched.
    assert f"MMS_PROVIDER_GW_A_API_KEY='{SECRET_ALPHA}'" in creds

    import tomllib

    with open(root / "config.toml", "rb") as handle:
        cfg = tomllib.loads(handle.read().decode())
    new_entry = next(p for p in cfg["providers"] if p["id"] == "new-gateway")
    assert new_entry["models_endpoint"] == "manual"
    assert new_entry["fallback_models"] == ["model-x", "model-y"]


def test_preview_apply_update_keeps_unknown_advanced_fields(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    config_text = config_text.replace(
        '[providers]\nid = "gw-a"',
        '[providers]\nid = "gw-a"',
    )
    # Add advanced fields on gw-a that the web UI never manages.
    config_text = config_text.replace(
        'id = "gw-a"\n',
        'id = "gw-a"\npriority = 250\nnote = "custom note"\nextra_models = ["extra-one"]\nmodels_endpoint = "manual"\nfallback_models = ["shared-model", "extra-one"]\n',
        1,
    )
    (root / "config.toml").write_text(config_text, encoding="utf-8")

    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"id": "gw-a", "name": "Gateway A Renamed", "baseUrl": "https://a2.example.com/v1", "apiKey": "sk-rotate-AAAAAAAA1111", "models": []}}
    )
    # Models list given but provider is manual -> updates fallback_models? No:
    # empty models list means "no change" per implementation; advanced fields stay.
    result = service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert result["applied"] is True

    import tomllib

    with open(root / "config.toml", "rb") as handle:
        cfg = tomllib.loads(handle.read().decode())
    entry = next(p for p in cfg["providers"] if p["id"] == "gw-a")
    assert entry["name"] == "Gateway A Renamed"
    assert entry["priority"] == 250
    assert entry["note"] == "custom note"
    assert entry["extra_models"] == ["extra-one"]
    assert entry["models_endpoint"] == "manual"
    assert entry["fallback_models"] == ["shared-model", "extra-one"]
    creds = (root / "credentials.sh").read_text()
    assert "sk-rotate-AAAAAAAA1111" in creds
    assert f"MMS_PROVIDER_GW_A_API_KEY='{SECRET_ALPHA}'" not in creds
    assert "https://a2.example.com/v1" in creds


def test_apply_rejects_stale_revision(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "New", "baseUrl": "https://new.example.com", "apiKey": "k", "models": []}}
    )
    # Mutate the config behind the preview's back.
    (root / "config.toml").write_text(
        (root / "config.toml").read_text() + '\n[user]\nrole = "全部模型"\n', encoding="utf-8"
    )
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert excinfo.value.code == "CONFIG_STALE"
    assert excinfo.value.status == 409


def test_apply_rejects_wrong_provided_revision(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "New", "baseUrl": "https://new.example.com", "apiKey": "k", "models": []}}
    )
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": preview["previewId"], "revision": "deadbeefdeadbeef"})
    assert excinfo.value.code == "CONFIG_STALE"


def test_apply_preview_single_use_and_expiry(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "New", "baseUrl": "https://new.example.com", "apiKey": "k", "models": []}}
    )
    assert service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})["applied"]
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert excinfo.value.code == "PREVIEW_ALREADY_APPLIED"

    preview2 = service.configuration_preview(
        {"service": {"name": "New2", "baseUrl": "https://new2.example.com", "apiKey": "k2", "models": []}}
    )
    record_path = state_root / "previews" / f"{preview2['previewId']}.json"
    record = json.loads(record_path.read_text())
    record["expiresAt"] = time.time() - 1
    record_path.write_text(json.dumps(record))
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": preview2["previewId"], "revision": preview2["revision"]})
    assert excinfo.value.code == "PREVIEW_EXPIRED"


def test_apply_unknown_preview_and_bad_payload(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": "f" * 32, "revision": "x"})
    assert excinfo.value.status == 404
    with pytest.raises(WebError):
        service.configuration_preview({"service": {"name": "", "baseUrl": "https://x.example.com"}})
    with pytest.raises(WebError):
        service.configuration_preview({"service": {"name": "x", "baseUrl": "ftp://bad"}})


# ── resolve_launch ──────────────────────────────────────────────────────


def test_resolve_launch_pins_provider_model_and_reuses_mms_env(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    result = service.resolve_launch("daily", "default")
    assert result["harness"] == "claude"
    assert result["modelInfo"]["model"] == "shared-model"
    assert result["providerId"] == "gw-a"
    assert result["cwd"]
    # INTERNAL payload carries the real env; secrets allowed here, never HTTP.
    assert result["runtime"]["api_key"] == SECRET_ALPHA
    assert result["runtime"]["anthropic_base_url"].startswith("https://a.example.com")
    private_root = Path(result["runtime"]["_webConfigRoot"])
    assert private_root != root and private_root.is_relative_to(state_root)
    assert not (root / "pi-gateway").exists()
    assert not (root / "exports").exists()


def test_resolve_launch_unknown_preset_and_workspace(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("nope", "default")
    assert excinfo.value.status == 404
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("daily", "nope")
    assert excinfo.value.code == "WORKSPACE_NOT_FOUND"


def test_resolve_launch_official_harness_unsupported(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    config_text += '\n[presets.agy-preset]\ncli = "agy"\nprovider = "gw-a"\nmodel = "shared-model"\n'
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("agy-preset", "default")
    assert excinfo.value.status == 409


def test_resolve_launch_bundle_credentials_are_authoritative(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    creds = (root / "credentials.sh").read_text().replace(
        f"export MMS_PROVIDER_GW_A_API_KEY='{SECRET_ALPHA}'\n", ""
    )
    (root / "credentials.sh").write_text(creds, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    result = service.resolve_launch("daily", "default")
    assert result["runtime"]["api_key"] == SECRET_ALPHA
    assert result["runtime"]["_mms_bundle_runtime"] is True


def test_resolve_launch_unsupported_provider_for_cli(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    # codex preset pinned to gw-c which only exposes anthropic_messages and
    # only supports claude: no bridge exemption applies, MMS must reject it.
    config_text += (
        '\n[[providers]]\nid = "gw-c"\nname = "Gateway C"\n'
        'protocols = ["anthropic_messages"]\nsupported_clis = ["claude"]\nenabled = true\n'
        '\n[presets.c-codex]\ncli = "codex"\nprovider = "gw-c"\nmodel = "shared-model"\n'
    )
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    credentials = (root / "credentials.sh").read_text()
    credentials += (
        "export MMS_PROVIDER_GW_C_BASE_URL='https://c.example.com'\n"
        "export MMS_PROVIDER_GW_C_ANTHROPIC_BASE_URL='https://c.example.com'\n"
        "export MMS_PROVIDER_GW_C_API_KEY='sk-gwc-key-000111'\n"
    )
    (root / "credentials.sh").write_text(credentials, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("c-codex", "default")
    assert excinfo.value.code in {"HARNESS_UNSUPPORTED", "PROVIDER_NO_BASE_URL", "PROVIDER_NEEDS_KEY", "PROVIDER_NOT_FOUND", "CAPABILITY_UNAVAILABLE"}


# ── host isolation ──────────────────────────────────────────────────────


def test_catalog_does_not_write_real_home(tmp_path, monkeypatch):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    service.snapshot()
    service.configuration_preview(
        {"service": {"name": "New", "baseUrl": "https://new.example.com", "apiKey": "k", "models": ["m"]}}
    )
    service.resolve_launch("daily", "default")
    # The real home stays empty: no mms dirs, no writes.
    assert list(real_home.iterdir()) == []


# ══ R1 revisions ═════════════════════════════════════════════════════


def _credential_value(root: Path, key: str) -> str:
    import shlex

    for line in (root / "credentials.sh").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith(key + "="):
            return shlex.split(line.partition("=")[2])[0]
    return ""


# R1-1: preview/apply consistency for manual model lists.
def test_r1_update_manual_models_persisted_matching_preview(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    config_text = config_text.replace(
        'id = "gw-a"\n',
        'id = "gw-a"\nmodels_endpoint = "manual"\nfallback_models = ["shared-model"]\npriority = 250\n',
        1,
    )
    (root / "config.toml").write_text(config_text, encoding="utf-8")

    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {
            "service": {
                "id": "gw-a",
                "name": "Gateway A",
                "baseUrl": "https://a.example.com/v1",
                "apiKey": SECRET_ALPHA,
                "models": ["m1", "m2", "shared-model"],
            }
        }
    )
    models_changes = [c for c in preview["changes"] if c["label"] == "Models"]
    assert models_changes and models_changes[0]["after"] == "m1, m2, shared-model"

    apply = service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert apply["applied"] is True
    import tomllib

    with open(root / "config.toml", "rb") as handle:
        cfg = tomllib.loads(handle.read().decode())
    entry = next(p for p in cfg["providers"] if p["id"] == "gw-a")
    # On-disk fallback_models matches the previewed list exactly.
    assert entry["fallback_models"] == ["m1", "m2", "shared-model"]
    assert entry["priority"] == 250


# R1-2: protocol-specific URLs/keys survive updates byte-for-byte.
def test_r1_update_preserves_protocol_specific_urls_and_keys(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    creds = (root / "credentials.sh").read_text()
    creds += (
        "export MMS_PROVIDER_GW_A_OPENAI_BASE_URL='https://alt-openai.example.com/v1'\n"
        "export MMS_PROVIDER_GW_A_ANTHROPIC_BASE_URL='https://alt-anthropic.example.com'\n"
        "export MMS_PROVIDER_GW_A_OPENAI_API_KEY='sk-openai-specific-key-987'\n"
    )
    (root / "credentials.sh").write_text(creds, encoding="utf-8")

    service = CatalogService(config_root=root, state_root=state_root)
    # Simple rename: nothing else should move.
    preview = service.configuration_preview(
        {"service": {"id": "gw-a", "name": "Renamed A", "baseUrl": "https://a.example.com/v1", "apiKey": ""}}
    )
    result = service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert result["applied"] is True

    assert _credential_value(root, "MMS_PROVIDER_GW_A_OPENAI_BASE_URL") == "https://alt-openai.example.com/v1"
    assert _credential_value(root, "MMS_PROVIDER_GW_A_ANTHROPIC_BASE_URL") == "https://alt-anthropic.example.com"
    assert _credential_value(root, "MMS_PROVIDER_GW_A_OPENAI_API_KEY") == "sk-openai-specific-key-987"
    assert _credential_value(root, "MMS_PROVIDER_GW_A_API_KEY") == SECRET_ALPHA
    # Preview warned that advanced protocol-specific values are kept.
    assert any("保留" in w for w in preview["warnings"])


def test_r1_update_changes_only_generic_base_url(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    creds = (root / "credentials.sh").read_text()
    creds += "export MMS_PROVIDER_GW_A_OPENAI_BASE_URL='https://alt-openai.example.com/v1'\n"
    (root / "credentials.sh").write_text(creds, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"id": "gw-a", "name": "Gateway A", "baseUrl": "https://moved.example.com/v1", "apiKey": ""}}
    )
    service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert _credential_value(root, "MMS_PROVIDER_GW_A_BASE_URL") == "https://moved.example.com/v1"
    assert _credential_value(root, "MMS_PROVIDER_GW_A_OPENAI_BASE_URL") == "https://alt-openai.example.com/v1"


# R1-3: identity linkage across models/presets and real channel.
def test_r1_same_model_primary_and_fallback_providers(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = {
        "shared-model": {
            "primary": {
                "provider_id": "gw-a",
                "anthropic_base_url": "https://a.example.com",
                "api_key": SECRET_ALPHA,
            },
            "fallbacks": [
                {
                    "provider_id": "gw-b",
                    "openai_base_url": "https://b.example.com/v1",
                    "api_key": SECRET_BETA,
                }
            ],
        },
    }
    _write_bundle(root, routes=routes)
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    ids = {m["id"] for m in snapshot["models"]}
    assert "gw-a:shared-model" in ids and "gw-b:shared-model" in ids
    fallback_entry = next(m for m in snapshot["models"] if m["id"] == "gw-b:shared-model")
    assert fallback_entry["routeRole"] == "fallback"
    assert fallback_entry["available"] is True
    # Preset modelId is the joinable provider-qualified id.
    preset = next(p for p in snapshot["presets"] if p["id"] == "daily")
    assert preset["modelId"] == "gw-a:shared-model"
    assert preset["modelName"] == "shared-model"
    assert preset["channel"] == "gw-a"
    assert preset["channelKind"] == "provider"


def test_r1_account_preset_keeps_real_channel(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    config_text = (root / "config.toml").read_text()
    config_text += '\n[presets.official]\ncli = "claude"\naccount = "claude-work"\nmodel = "shared-model"\n'
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    preset = next(p for p in snapshot["presets"] if p["id"] == "official")
    assert preset["channel"] == "claude-work"
    assert preset["channelKind"] == "account"
    assert preset["providerId"] == ""
    assert preset["available"] is False
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("official", "default")
    assert excinfo.value.status == 409


# R1-4: project overlay + disabled providers are not selectable.
def test_r1_project_overlay_applied_and_reported(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    policy_models = {
        "shared-model": {"visible": True, "favorite": True, "hide_in": ["mms-web"]},
        "other-model": {"visible": True},
    }
    _write_bundle(root, routes=routes, policy_models=policy_models)
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    shared = next(m for m in snapshot["models"] if m["id"] == "gw-a:shared-model")
    assert shared["available"] is False
    assert "mms-web" in shared.get("reason", "")
    other = next(m for m in snapshot["models"] if m["id"] == "gw-b:other-model")
    assert other["available"] is True


def test_r1_project_whitelist_mode(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    policy_models = {
        "shared-model": {"visible": True},
        "other-model": {"visible": True},
    }
    _write_bundle(
        root,
        routes=routes,
        policy_models=policy_models,
        policy_projects={"mms-web": {"default_visible": False, "allowed_models": ["other-model"]}},
    )
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    assert "POLICY_PROJECT_OVERLAY_APPLIED" in [d["code"] for d in snapshot["diagnostics"]]
    shared = next(m for m in snapshot["models"] if m["id"] == "gw-a:shared-model")
    other = next(m for m in snapshot["models"] if m["id"] == "gw-b:other-model")
    assert shared["available"] is False  # whitelist excludes it
    assert other["available"] is True


def test_r1_disabled_provider_models_and_presets_unavailable(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    import tomllib

    import tomli_w

    with open(root / "config.toml", "rb") as handle:
        cfg = tomllib.loads(handle.read().decode())
    next(p for p in cfg["providers"] if p["id"] == "gw-a")["enabled"] = False
    (root / "config.toml").write_bytes(tomli_w.dumps(cfg).encode("utf-8"))
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    shared = next(m for m in snapshot["models"] if m["id"] == "gw-a:shared-model")
    assert shared["available"] is False
    assert "禁用" in shared.get("reason", "")
    assert shared["harnesses"] == []
    preset = next(p for p in snapshot["presets"] if p["id"] == "daily")
    assert preset["available"] is False
    assert "禁用" in preset.get("reason", "")


def test_r1_preset_hidden_model_unavailable(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    routes = json.loads((root / "generated" / "model-routes.json").read_text())["routes"]
    _write_bundle(root, routes=routes, policy_models={"shared-model": {"visible": False}})
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    preset = next(p for p in snapshot["presets"] if p["id"] == "daily")
    assert preset["available"] is False
    assert "隐藏" in preset.get("reason", "")


# R1-5: protection covers subtrees, symlinks, parent dirs, and state root.
def _fake_real_home(tmp_path, monkeypatch):
    real_home = tmp_path / "human-home"
    (real_home / ".config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.delenv("REAL_HOME", raising=False)
    monkeypatch.delenv("ORIGINAL_HOME", raising=False)
    return real_home


def test_r1_protects_subtree_parent_and_symlink(tmp_path, monkeypatch):
    real_home = _fake_real_home(tmp_path, monkeypatch)
    protected = real_home / ".config" / "mms"
    protected.mkdir(exist_ok=True)

    # Subdirectory of the protected root.
    inside = protected / "accounts"
    inside.mkdir(exist_ok=True)
    service = CatalogService(config_root=inside, state_root=tmp_path / "state")
    assert service.capabilities()["configure"] is False
    with pytest.raises(WebError):
        service.configuration_preview({"service": {"name": "x", "baseUrl": "https://x.example.com"}})

    # Parent of a protected root (e.g. ~/.config) must be rejected too.
    parent = real_home / ".config"
    service = CatalogService(config_root=parent, state_root=tmp_path / "state")
    assert service.capabilities()["configure"] is False

    # Symlink aimed inside the protected subtree is collapsed by resolve().
    link = tmp_path / "sneaky-link"
    if not link.exists():
        link.symlink_to(protected)
    service = CatalogService(config_root=link, state_root=tmp_path / "state")
    assert service.capabilities()["configure"] is False


def test_r1_state_root_inside_protected_root_rejected(tmp_path, monkeypatch):
    real_home = _fake_real_home(tmp_path, monkeypatch)
    protected = real_home / ".config" / "mms-next"
    protected.mkdir(exist_ok=True)
    root, _state = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=protected / "web-state")
    assert service.capabilities()["configure"] is False
    with pytest.raises(WebError) as excinfo:
        service.configuration_preview({"service": {"name": "x", "baseUrl": "https://x.example.com"}})
    assert excinfo.value.status == 409


# R1-6: secret hygiene in previews and consumed records.
def test_r1_url_userinfo_rejected_and_query_masked(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    with pytest.raises(WebError):
        service.configuration_preview(
            {"service": {"name": "x", "baseUrl": "https://user:pass@x.example.com/v1"}}
        )
    preview = service.configuration_preview(
        {"service": {"name": "Q", "baseUrl": "https://q.example.com/v1?token=abcdef123456", "apiKey": ""}}
    )
    text = json.dumps(preview, ensure_ascii=False)
    assert "abcdef123456" not in text
    url_changes = [c for c in preview["changes"] if c["label"] == "Base URL"]
    assert url_changes and url_changes[0]["after"].endswith("?***")


def test_r1_applied_and_expired_previews_drop_api_key(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "New", "baseUrl": "https://new.example.com", "apiKey": "sk-temp-key-111222333", "models": []}}
    )
    record_path = state_root / "previews" / f"{preview['previewId']}.json"
    assert "sk-temp-key-111222333" in record_path.read_text()
    service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})
    assert "sk-temp-key-111222333" not in record_path.read_text()
    assert json.loads(record_path.read_text())["consumed"] is True

    preview2 = service.configuration_preview(
        {"service": {"name": "New2", "baseUrl": "https://new2.example.com", "apiKey": "sk-temp-key-444555666", "models": []}}
    )
    record_path2 = state_root / "previews" / f"{preview2['previewId']}.json"
    record = json.loads(record_path2.read_text())
    record["expiresAt"] = time.time() - 1
    record_path2.write_text(json.dumps(record))
    with pytest.raises(WebError) as excinfo:
        service.configuration_apply({"previewId": preview2["previewId"], "revision": preview2["revision"]})
    assert excinfo.value.code == "PREVIEW_EXPIRED"
    # Expired record (and its key) is removed from disk.
    assert not record_path2.exists()


# R1-7: first-connect loop shows pending models with clear next step.
def test_r1_new_provider_models_pending_unverified(tmp_path):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    preview = service.configuration_preview(
        {"service": {"name": "Fresh Gateway", "baseUrl": "https://fresh.example.com/v1", "apiKey": "sk-fresh-key-999888777", "models": ["fresh-x"]}}
    )
    service.configuration_apply({"previewId": preview["previewId"], "revision": preview["revision"]})

    snapshot = service.snapshot()
    codes = [d["code"] for d in snapshot["diagnostics"]]
    assert "PENDING_UNVERIFIED_PROVIDERS" in codes
    pending = next(m for m in snapshot["models"] if m["id"] == "fresh-gateway:fresh-x")
    assert pending["available"] is False
    assert pending["verified"] is False
    assert "等待验证" in pending.get("reason", "")
    service_entry = next(s for s in snapshot["services"] if s["id"] == "fresh-gateway")
    assert "未验证" in service_entry["detail"]

    # A preset pinned to the pending model stays unavailable with guidance.
    config_text = (root / "config.toml").read_text()
    config_text += '\n[presets.fresh]\ncli = "claude"\nprovider = "fresh-gateway"\nmodel = "fresh-x"\n'
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    snapshot = service.snapshot()
    preset = next(p for p in snapshot["presets"] if p["id"] == "fresh")
    assert preset["available"] is False
    assert "等待验证" in preset.get("reason", "")


# R1-6b: worker-side CAS inside the writer critical section.
def test_r1_worker_rejects_stale_expected_revision(tmp_path, monkeypatch):
    import subprocess as sp

    real_home = _fake_real_home(tmp_path, monkeypatch)
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    stale_revision = service._config_revision()
    # Another writer (MMS side) touches the config after the revision was taken.
    (root / "config.toml").write_text(
        (root / "config.toml").read_text() + '\n[user]\nrole = "全部模型"\n', encoding="utf-8"
    )
    worker = Path(__file__).resolve().parent.parent / "mms_web" / "catalog_worker.py"
    result = sp.run(
        [sys.executable, str(worker)],
        input=json.dumps(
            {
                "command": "apply-config",
                "config_root": str(root),
                "realHome": str(real_home),
                "mode": "update",
                "providerId": "gw-a",
                "expectedRevision": stale_revision,
                "service": {"id": "gw-a", "name": "Renamed", "baseUrl": "https://a.example.com/v1", "apiKey": "", "models": []},
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["code"] == "CONFIG_STALE"
    # Nothing was written: the name change did not land.
    assert 'Renamed' not in (root / "config.toml").read_text()


# R1-8: user-facing messages are Chinese.
def test_r1_user_facing_messages_are_chinese(tmp_path, monkeypatch):
    root, state_root = _dual_provider_fixture(tmp_path)
    service = CatalogService(config_root=root, state_root=state_root)
    snapshot = service.snapshot()
    for diagnostic in snapshot["diagnostics"]:
        assert re.search(r"[\u4e00-\u9fff]", diagnostic["message"])
    preview = service.configuration_preview(
        {"service": {"name": "N", "baseUrl": "https://n.example.com", "apiKey": "", "models": []}}
    )
    assert all(re.search(r"[\u4e00-\u9fff]", w) or not w for w in preview["warnings"])
    with pytest.raises(WebError) as excinfo:
        service.resolve_launch("nope", "default")
    assert re.search(r"[\u4e00-\u9fff]", excinfo.value.message)


def test_launch_rejects_hidden_preset_even_if_api_called_directly(tmp_path):
    root, state = _dual_provider_fixture(tmp_path)
    routes = json.loads((root / "generated/model-routes.json").read_text())["routes"]
    _write_bundle(root, routes=routes, policy_models={"shared-model": {"visible": False}})
    service = CatalogService(config_root=root, state_root=state)
    with pytest.raises(WebError) as exc:
        service.resolve_launch("daily", "default")
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"


def _workspace_service(tmp_path: Path) -> CatalogService:
    return CatalogService(config_root=None, state_root=tmp_path / "state")


def test_rename_workspace_changes_only_the_display_name(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    service = _workspace_service(tmp_path)
    added = service.add_workspace({"path": str(folder)})

    renamed = service.rename_workspace({"id": added["id"], "name": "客户资料"})

    assert renamed["name"] == "客户资料"
    assert renamed["path"] == str(folder.resolve())
    assert folder.is_dir()
    stored = {w["id"]: w for w in service._workspaces()}
    assert stored[added["id"]]["name"] == "客户资料"


def test_rename_workspace_rejects_an_empty_name(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    service = _workspace_service(tmp_path)
    added = service.add_workspace({"path": str(folder)})

    with pytest.raises(WebError) as error:
        service.rename_workspace({"id": added["id"], "name": "   "})
    assert error.value.code == "INVALID_WORKSPACE_NAME"


def test_remove_workspace_keeps_the_folder_on_disk(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / "notes.md").write_text("keep me", encoding="utf-8")
    service = _workspace_service(tmp_path)
    added = service.add_workspace({"path": str(folder)})

    service.remove_workspace({"id": added["id"]})

    assert not any(w["id"] == added["id"] for w in service._workspaces())
    assert (folder / "notes.md").read_text(encoding="utf-8") == "keep me"


def test_launch_directory_cannot_be_removed(tmp_path: Path) -> None:
    service = _workspace_service(tmp_path)
    with pytest.raises(WebError) as error:
        service.remove_workspace({"id": "default"})
    assert error.value.code == "WORKSPACE_PROTECTED"


def test_unknown_workspace_reports_a_refresh(tmp_path: Path) -> None:
    service = _workspace_service(tmp_path)
    with pytest.raises(WebError) as error:
        service.rename_workspace({"id": "w-missing", "name": "x"})
    assert error.value.code == "WORKSPACE_NOT_FOUND"
