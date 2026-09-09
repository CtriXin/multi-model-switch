"""Fresh Web settings use the same published defaults as actual Pi requests."""
import hashlib
import json

import pytest

from mms_web.errors import WebError
from mms_web.server import WebApplication
from test_mms_web_interactions import local_app, settle
from test_mms_web_configuration_flow import connection, model_service


def save_effort(app, provider, value):
    before = app.get(["model-settings"])
    row = next(p for p in before["providers"] if p["id"] == provider)
    preview = app.post(["model-settings", "preview"], {
        "fingerprint": before["fingerprint"], "revision": before["revision"],
        "providerId": provider, "models": [m["id"] for m in row["models"] if m["visible"]],
        "efforts": {"gpt-5": value}})
    assert preview["confirmPhrase"] == "保存设置"
    result = app.post(["model-settings", "apply"], {
        "previewId": preview["previewId"], "confirmPhrase": preview["confirmPhrase"]})
    assert result["applied"] and result["runtimeReady"]
    return app.get(["model-settings"])


def tree_hash(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_defaults_two_saves_restart_and_existing_native_session(local_app):
    app, workspace, _ = local_app
    with model_service() as (url, requests):
        connection(app, "First", url, "standalone-fixture-key")
        assert app.bootstrap()["capabilities"]["modelSettings"]
        first = save_effort(app, "first", "low")
        assert first["configScope"] == "standalone"
        request = {"workspaceId": workspace["id"], "presetId": "web:pi:first:gpt-5", "prompt": "Reply."}
        sid = app.post(["sessions"], {**request, "requestId": "before-default-change"})["session"]["id"]
        settle(app, sid)
        assert [r for r in requests if r["method"] == "POST"][-1]["body"]["reasoning_effort"] == "low"
        second = save_effort(app, "first", "high")
        assert first["revision"] != second["revision"]
        app.sessions._get(sid).runtime_checked = 0
        assert app.get(["sessions", sid, "runtime"])["thinkingLevel"] == "low"
        state = app.catalog._state_root
        app.close()
        restored = WebApplication(state_root=state)
        try:
            row = restored.get(["model-settings"])["providers"][0]["models"][0]
            assert row["effort"] == row["effectiveEffort"] == "high"
            detail = restored.post(["sessions"], {**request, "requestId": "after-restart"})
            settle(restored, detail["session"]["id"])
            post = [r for r in requests if r["method"] == "POST"][-1]
            assert post["body"]["reasoning_effort"] == "high"
            assert post["authorization"] == "Bearer standalone-fixture-key"
            assert post["path"] == "/v1/chat/completions"
            # Adding a channel after publishing defaults must preserve them.
            connection(restored, "Second", url, "second-fixture-key")
            rows = restored.get(["model-settings"])["providers"]
            assert {p["id"] for p in rows} == {"first", "second"}
            assert all(p["models"][0]["effort"] == "high" for p in rows)
            assert {p["providerId"] for p in restored.bootstrap()["presets"]} == {"first", "second"}
            save_effort(restored, "second", "")
            assert all(p["models"][0]["effort"] == "" for p in restored.get(["model-settings"])["providers"])
        finally:
            restored.close()


def test_old_standalone_read_and_preview_are_readonly_then_publish(local_app):
    app, workspace, _ = local_app
    with model_service() as (url, old_requests), model_service() as (new_url, new_requests):
        # Recreate the v4 standalone writer, before this iteration's Registry path.
        app.catalog._run_worker({"command": "apply-config", "config_root": str(app.catalog.config_root),
            "providerId": "legacy", "service": {"name": "Legacy", "baseUrl": url,
            "apiKey": "legacy-fixture-key", "protocol": "openai", "models": ["gpt-5"]}})
        app.catalog._run_worker({"command": "apply-config", "config_root": str(app.catalog.config_root),
            "providerId": "untouched", "service": {"name": "Untouched", "baseUrl": url,
            "apiKey": "other-legacy-key", "protocol": "openai", "models": ["gpt-4.1"]}})
        root = app.catalog.config_root
        before = tree_hash(root)
        snap = app.get(["model-settings"])
        assert snap["providers"][0]["models"][0]["effortLevels"]
        preview = app.post(["model-settings", "preview"], {
            "fingerprint": snap["fingerprint"], "revision": snap["revision"],
            "providerId": "legacy", "models": ["gpt-5"], "efforts": {"gpt-5": "low"}})
        assert tree_hash(root) == before
        assert "legacy-fixture-key" not in json.dumps([snap, preview])
        save_effort(app, "legacy", "low")
        save_effort(app, "legacy", "high")
        assert (root / "generated/model-registry.latest-approved.json").is_file()
        after = app.get(["model-settings"])
        assert next(p for p in after["providers"] if p["id"] == "untouched")["models"][0]["id"] == "gpt-4.1"
        preview = app.post(["model-settings", "preview"], {
            "fingerprint": after["fingerprint"], "revision": after["revision"],
            "providerId": "legacy", "models": ["gpt-5"], "efforts": {},
            "connection": {"openaiBaseUrl": new_url, "apiKey": "replacement-fixture-key"}})
        app.post(["model-settings", "apply"], {"previewId": preview["previewId"], "confirmPhrase": "保存设置"})
        for pid, model, records, key in [("legacy", "gpt-5", new_requests, "replacement-fixture-key"),
                                         ("untouched", "gpt-4.1", old_requests, "other-legacy-key")]:
            detail = app.post(["sessions"], {"workspaceId": workspace["id"], "presetId": f"web:pi:{pid}:{model}",
                "requestId": "legacy-" + pid, "prompt": "Check preserved channel."})
            settle(app, detail["session"]["id"])
            assert records[-1]["authorization"] == "Bearer " + key
        assert next(p for p in app.get(["model-settings"])["providers"] if p["id"] == "legacy")["connection"]["openaiBaseUrl"] == new_url


def test_connection_preview_becomes_stale_when_defaults_change(local_app):
    app, _, _ = local_app
    with model_service() as (url, _):
        connection(app, "First", url, "fixture-key")
        preview = app.post(["configuration", "preview"], {"service": {
            "name": "Second", "baseUrl": url, "apiKey": "other-key", "protocol": "openai", "models": ["gpt-5"]}})
        save_effort(app, "first", "low")
        with pytest.raises(WebError) as error:
            app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
        assert error.value.code == "CONFIG_STALE"


def test_adding_channel_to_legacy_root_first_publication(local_app):
    app, _, _ = local_app
    with model_service() as (url, _):
        app.catalog._run_worker({"command": "apply-config", "config_root": str(app.catalog.config_root),
            "providerId": "legacy", "service": {"name": "Legacy", "baseUrl": url,
            "apiKey": "legacy-fixture-key", "protocol": "openai", "models": ["gpt-4.1"]}})
        # Applying a connection already holds the source config lock. Legacy
        # preparation must not write and try to acquire the same lock again.
        connection(app, "Second", url, "second-fixture-key")
        rows = app.get(["model-settings"])["providers"]
        assert {p["id"]: [m["id"] for m in p["models"]] for p in rows} == {
            "legacy": ["gpt-4.1"], "second": ["gpt-5"]}


def test_corrupt_standalone_bundle_does_not_fall_back_to_legacy(local_app):
    app, _, _ = local_app
    with model_service() as (url, _):
        connection(app, "First", url, "fixture-key")
        path = app.catalog.config_root / "generated/model-policy.effective.json"
        path.write_text('{}')
        before = tree_hash(app.catalog.config_root)
        with pytest.raises(WebError) as error:
            app.get(["model-settings"])
        assert error.value.code == "INVALID_BUNDLE"
        assert tree_hash(app.catalog.config_root) == before


def test_generic_connection_update_keeps_protocol_specific_url(local_app):
    app, workspace, _ = local_app
    app.catalog._run_worker({"command": "apply-config", "config_root": str(app.catalog.config_root),
        "providerId": "legacy-a", "service": {"name": "Legacy", "baseUrl": "http://127.0.0.1:12340/v1",
        "apiKey": "fixture-key", "protocol": "openai", "models": ["gpt-5"]}})
    path = app.catalog.config_root / "credentials.sh"
    path.write_text(path.read_text() + "\nexport MMS_PROVIDER_LEGACY_A_OPENAI_BASE_URL='http://127.0.0.1:12342/v1'\n")
    save_effort(app, "legacy-a", "low")
    before = app.catalog.resolve_launch("web:pi:legacy-a:gpt-5", workspace["id"])["runtime"]
    assert before["openai_base_url"] == "http://127.0.0.1:12342/v1"
    preview = app.post(["configuration", "preview"], {"service": {
        "id": "legacy-a", "name": "Renamed A", "baseUrl": "http://127.0.0.1:12340/v1", "apiKey": ""}})
    assert any("保留" in warning for warning in preview["warnings"])
    app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
    after = app.catalog.resolve_launch("web:pi:legacy-a:gpt-5", workspace["id"])["runtime"]
    assert after["openai_base_url"] == before["openai_base_url"]


def test_first_connection_loads_bundled_defaults_without_a_generation_call(local_app):
    """The new-user save can read usable defaults without making users edit them."""
    app, workspace, _ = local_app
    before = app.get(["bootstrap"])
    assert before["capabilities"]["configure"] and not before["services"]
    with model_service() as (url, requests):
        service = {"name": "First-use", "baseUrl": url, "apiKey": "setup-fixture-key",
                   "protocol": "openai", "models": ["MiniMax-M3"]}
        preview = app.post(["configuration", "preview"], {"service": service})
        assert "setup-fixture-key" not in json.dumps(preview)
        assert not app.get(["bootstrap"])["services"]
        saved = app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
        assert saved["presetIds"] == ["web:pi:first-use:MiniMax-M3"]
        payload = {"presetId": saved["presetIds"][0], "workspaceId": workspace["id"]}
        facts = app.post(["launch-options"], payload)
        assert facts["model"]["id"] == "MiniMax-M3"
        assert facts["model"]["contextWindow"] == 1_000_000
        assert facts["defaultThinkingLevel"] in facts["supportedThinkingLevels"]
        assert facts["capabilitySources"]["context_window_tokens"] == "provider_profile"
        assert not [r for r in requests if r["method"] == "POST"]
        state = app.catalog._state_root
        app.close()
        restored = WebApplication(state_root=state)
        try:
            assert restored.post(["launch-options"], payload) == facts
            assert restored.get(["bootstrap"])["presets"][0]["available"]
        finally:
            restored.close()


def test_shutdown_replaces_pi_process_but_history_remains_sendable(local_app):
    app, workspace, _ = local_app
    with model_service() as (url, requests):
        preview = app.post(["configuration", "preview"], {"service": {
            "name": "Upgrade", "baseUrl": url, "apiKey": "upgrade-fixture-key",
            "protocol": "openai", "models": ["MiniMax-M3"]}})
        saved = app.post(["configuration", "apply"], {"previewId": preview["previewId"], "revision": preview["revision"]})
        sid = app.post(["sessions"], {"requestId": "before-upgrade", "presetId": saved["presetIds"][0],
            "workspaceId": workspace["id"], "prompt": "before-upgrade-history-marker"})["session"]["id"]
        before = settle(app, sid)
        driver = app.sessions._get(sid).driver
        pid = driver._proc.pid
        state = app.catalog._state_root
        app.close()
        assert not driver.alive()  # Data recovery is not uninterrupted execution.
        restored = WebApplication(state_root=state)
        try:
            recovered = restored.get(["sessions", sid])
            assert recovered["session"]["state"] == "stopped"
            assert recovered["session"]["capabilities"]["send"]
            assert {e["id"] for e in before["events"]}.issubset({e["id"] for e in recovered["events"]})
            restored.post(["sessions", sid, "messages"], {"requestId": "after-upgrade", "text": "continue-history-marker"})
            after = settle(restored, sid)
            assert restored.sessions._get(sid).driver._proc.pid != pid
            posts = [r for r in requests if r["method"] == "POST"]
            assert len(posts) == 2 and posts[-1]["body"]["model"] == "MiniMax-M3"
            assert "before-upgrade-history-marker" in json.dumps(posts[-1]["body"]["messages"])
            assert any(e.get("text") == "通道连接验证完成。" for e in after["events"])
        finally:
            restored.close()
