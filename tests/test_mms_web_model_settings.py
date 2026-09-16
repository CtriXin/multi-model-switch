import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mms_web.catalog import CatalogService
from mms_web.model_settings import ModelSettings
from mms_web.errors import WebError

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from test_mms_web_configuration_flow import model_service
    upstream = model_service()
    url, records = upstream.__enter__()
    home = tmp_path / "home"
    home.mkdir()
    for key in ("HOME", "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        monkeypatch.setenv(key, str(home))
    root = tmp_path / "mms-next"
    root.mkdir()
    (root / "config.toml").write_text("# Fixture: providers are hydrated from the approved Registry.\n")
    payload = {"draft": {"providers": [
        {"id": pid, "name": pid, "protocols": ["openai_chat_completions"], "supported_clis": ["pi", "codex"],
         "models_endpoint": "/models", "openai_base_url": url, "api_key": "private-fixture-key", "update_credentials": True,
         "fallback_models": ["gpt-5", "gpt-4.1"], "models": [{"id": "gpt-5", "capability_touched": True, "capabilities": {"reasoning_effort": "low", "reasoning": True, "thinking": True}}]}
        for pid in ("channel-a", "channel-b")], "provider_default": "channel-a"}, "confirm_v2_preview": True, "confirm_phrase": "写入预览DB"}
    code = 'import json,sys; import mms_config_web as w; p=json.load(sys.stdin); r=w.apply_registry_v2_preview_plan({},p,config_path=sys.argv[1]); print(json.dumps({"ok":r.get("ok"),"status":r.get("status"),"errors":r.get("errors")}))'
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "MMS_CONFIG_ROOT": str(root), "MMS_PREVIEW_MODE": "1"}
    result = subprocess.run([sys.executable, "-c", code, str(root / "config.toml")], input=json.dumps(payload), capture_output=True, text=True, cwd=REPO, env=env)
    assert json.loads(result.stdout.splitlines()[-1])["ok"], result.stdout[-600:]
    service = ModelSettings(CatalogService(config_root=root, state_root=tmp_path / "state"))
    service.test_records = records
    try:
        yield service
    finally:
        upstream.__exit__(None, None, None)


def payload(service):
    snap = service.read()
    return {"fingerprint": snap["fingerprint"], "revision": snap["revision"], "providerId": "channel-a", "models": ["gpt-5", "gpt-4.1"], "efforts": {"gpt-5": "high"}}


def test_defaults_confirm_publish_and_replay(settings):
    before = settings.read()
    assert before["providers"][0]["models"]
    draft = payload(settings)
    preview = settings.preview(draft)
    assert preview["changes"] == [{"kind": "effort", "model": "gpt-5", "before": "low", "after": "high", "channels": ["channel-a", "channel-b"]}]
    with pytest.raises(WebError, match="确认"):
        settings.apply({"previewId": preview["previewId"]})
    assert settings.read()["revision"] == before["revision"]
    result = settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    assert result["applied"] and result["runtimeReady"]
    after = settings.read()
    assert after["revision"] != before["revision"]
    assert all(next(m for m in p["models"] if m["id"] == "gpt-5")["effort"] == "high" for p in after["providers"])
    assert settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"}) == result
    assert "private-fixture-key" not in json.dumps([after, preview, result])


def test_route_changes_preserve_other_channel(settings):
    draft = payload(settings)
    draft.update(models=["gpt-5", "gpt-new"], efforts={})
    preview = settings.preview(draft)
    assert {c["kind"] for c in preview["changes"]} == {"add", "remove"}
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    rows = settings.read()["providers"]
    by_id = {p["id"]: {m["id"] for m in p["models"] if m["visible"]} for p in rows}
    assert by_id["channel-a"] == {"gpt-5", "gpt-new"}
    assert by_id["channel-b"] == {"gpt-5", "gpt-4.1"}


def test_deselect_and_save_without_legacy_config(settings):
    """A first Pilot setup publishes Registry truth without config.toml."""
    (settings.root / "config.toml").unlink()
    draft = payload(settings)
    draft.update(models=["gpt-5"], efforts={})
    preview = settings.preview(draft)
    result = settings.apply({"previewId": preview["previewId"], "confirmed": True})
    assert result["applied"] and result["runtimeReady"]
    rows = settings.read()["providers"]
    visible = {p["id"]: {m["id"] for m in p["models"] if m["visible"]} for p in rows}
    assert visible == {"channel-a": {"gpt-5"}, "channel-b": {"gpt-5", "gpt-4.1"}}


def test_stale_and_invalid_input(settings):
    draft = payload(settings)
    preview = settings.preview(draft)
    (settings.root / "override.toml").write_text("# human concurrent edit\n")
    with pytest.raises(WebError, match="变化"):
        settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    bad = payload(settings)
    bad["efforts"] = {"gpt-5": "not-a-level"}
    with pytest.raises(WebError, match="effort"):
        settings.preview(bad)


def test_discovery_uses_existing_key_and_does_not_publish(settings):
    before = settings.fingerprint()
    result = settings.discover(payload(settings))
    assert set(result["models"]) == {"gpt-5", "gpt-4.1", "local-extra-model"}
    assert settings.fingerprint() == before
    assert settings.test_records == [{"method": "GET", "path": "/v1/models", "authorization": "Bearer private-fixture-key"}]
    assert "private-fixture-key" not in json.dumps(result)


def test_published_effort_reaches_new_native_pi_session(settings, tmp_path):
    from mms_web.server import WebApplication
    from test_mms_web_interactions import settle
    app = WebApplication(state_root=tmp_path / "web-state", config_root=settings.root)
    workspace = tmp_path / "project"
    workspace.mkdir()
    ws = app.catalog.add_workspace({"path": str(workspace)})
    try:
        preset = "web:pi:channel-a:gpt-5"
        options = app.post(["launch-options"], {"presetId": preset, "workspaceId": ws["id"]})
        assert options["defaultThinkingLevel"] == "low"
        preview = settings.preview(payload(settings))
        settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
        options = app.post(["launch-options"], {"presetId": preset, "workspaceId": ws["id"]})
        assert options["defaultThinkingLevel"] == "high"
        detail = app.post(["sessions"], {"requestId": "effort-default-regression", "presetId": preset, "workspaceId": ws["id"], "prompt": "Reply with the connection marker."})
        result = settle(app, detail["session"]["id"])
        assert any(e.get("text") == "通道连接验证完成。" for e in result["events"])
        posts = [r for r in settings.test_records if r["method"] == "POST"]
        assert posts and posts[0]["body"]["reasoning_effort"] == "high"
    finally:
        app.close()


def test_management_uses_published_models_not_stale_legacy_rows(settings):
    (settings.root / "config.toml").write_text('[[providers]]\nid = "channel-a"\nname = "channel-a"\nfallback_models = ["stale-model"]\nprotocols = ["openai_chat_completions"]\nsupported_clis = ["pi"]\n')
    rows = settings.read()["providers"]
    assert {m["id"] for m in rows[0]["models"]} == {"gpt-5", "gpt-4.1"}
    preview = settings.preview(payload(settings))
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    after = settings.read()["providers"]
    assert all({m["id"] for m in p["models"]} == {"gpt-5", "gpt-4.1"} for p in after)


def test_stable_real_root_is_not_a_preview_write_target(settings, monkeypatch):
    import shutil
    home = Path(os.environ["HOME"])
    stable = home / ".config/mms"
    shutil.copytree(settings.root, stable)
    service = ModelSettings(CatalogService(config_root=stable, state_root=home / "web-state"))
    assert not service.available()
    with pytest.raises(WebError, match="已批准"):
        service.read()


def test_reset_effort_preserves_other_policy_and_reaches_launcher(settings, tmp_path):
    from mms_web.server import WebApplication
    draft = payload(settings)
    draft['efforts'] = {'gpt-5': ''}
    preview = settings.preview(draft)
    assert preview['changes'][0]['after'] == ''
    settings.apply({'previewId': preview['previewId'], 'confirmPhrase': '写入预览DB'})
    rows = settings.read()['providers']
    assert all(next(m for m in p['models'] if m['id'] == 'gpt-5')['effort'] == '' for p in rows)
    manifest = json.loads((settings.root / 'generated/model-registry.latest-approved.json').read_text())
    policy = json.loads((settings.root / manifest['files']['policy']['canonical_path']).read_text())
    caps = policy['models']['gpt-5']['capabilities']
    assert 'reasoning_effort' not in caps and caps['thinking']
    app = WebApplication(state_root=tmp_path / 'web-reset', config_root=settings.root)
    project = tmp_path / 'project-reset'
    project.mkdir()
    try:
        ws = app.catalog.add_workspace({'path': str(project)})
        options = app.post(['launch-options'], {'presetId': 'web:pi:channel-a:gpt-5', 'workspaceId': ws['id']})
        assert options['defaultThinkingLevel'] != 'low'
    finally:
        app.close()


def test_connection_check_uses_draft_key_without_publishing(settings):
    draft = payload(settings)
    before = settings.fingerprint()
    assert settings.check(draft)['connected']
    draft['connection'] = {'apiKey': 'invalid-fixture-key'}
    with pytest.raises(WebError, match='拉取失败'):
        settings.check(draft)
    assert settings.fingerprint() == before
    assert settings.test_records[-1]['authorization'] == 'Bearer invalid-fixture-key'


def test_key_preview_is_private_and_apply_only_changes_selected_channel(settings):
    draft = payload(settings)
    draft.update(efforts={}, connection={'apiKey': 'invalid-fixture-key'})
    original = settings.fingerprint()
    preview = settings.preview(draft)
    assert settings.fingerprint() == original
    records = list(settings.state.glob('*.json'))
    assert records and all('invalid-fixture-key' not in p.read_text() for p in records)
    assert 'invalid-fixture-key' not in json.dumps(preview)
    result = settings.apply({'previewId': preview['previewId'], 'confirmPhrase': '写入预览DB'})
    assert result['applied']
    snapshot = settings.read()
    common = {'revision': snapshot['revision'], 'fingerprint': snapshot['fingerprint']}
    with pytest.raises(WebError):
        settings.check({**common, 'providerId': 'channel-a'})
    assert settings.test_records[-1]['authorization'] == 'Bearer invalid-fixture-key'
    assert settings.check({**common, 'providerId': 'channel-b'})['connected']
    assert settings.test_records[-1]['authorization'] == 'Bearer private-fixture-key'
    assert not settings.secret_drafts


def test_address_edit_preserves_key_and_other_channel(settings):
    from test_mms_web_configuration_flow import model_service
    with model_service() as (url, calls):
        draft = payload(settings)
        draft.update(efforts={}, connection={'openaiBaseUrl': url})
        assert settings.check(draft)['connected']
        assert calls[-1]['authorization'] == 'Bearer private-fixture-key'
        preview = settings.preview(draft)
        settings.apply({'previewId': preview['previewId'], 'confirmPhrase': '写入预览DB'})
        rows = settings.read()['providers']
        assert rows[0]['connection']['openaiBaseUrl'] == url
        assert rows[1]['connection']['openaiBaseUrl'] != url
        common = payload(settings)
        assert settings.check(common)['connected']
        assert calls[-1]['authorization'] == 'Bearer private-fixture-key'


@pytest.mark.parametrize('url', ['file:///tmp/key', 'https://user:pass@example.com', 'https://example.com?key=secret', 'bad-url'])
def test_reject_unsafe_connection_input(settings, url):
    draft = payload(settings)
    draft['connection'] = {'openaiBaseUrl': url}
    with pytest.raises(WebError):
        settings.preview(draft)


def test_published_vision_setting_reaches_a_new_pi_session(settings, tmp_path):
    """A vision flag set here must change what the launched Pi session sees."""
    from mms_web.server import WebApplication

    draft = payload(settings)
    draft.update(efforts={}, visions={"gpt-5": False})
    preview = settings.preview(draft)
    assert preview["changes"] == [{"kind": "vision", "model": "gpt-5", "before": "可读取图片",
                                   "after": "不可读取图片", "channels": ["channel-a", "channel-b"]}]
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    rows = settings.read()["providers"]
    assert all(next(m for m in p["models"] if m["id"] == "gpt-5")["vision"] is False for p in rows)

    app = WebApplication(state_root=tmp_path / "web-vision", config_root=settings.root)
    project = tmp_path / "project-vision"
    project.mkdir()
    try:
        workspace = app.catalog.add_workspace({"path": str(project)})
        options = app.post(["launch-options"], {"presetId": "web:pi:channel-a:gpt-5",
                                                "workspaceId": workspace["id"]})
        assert "image" not in options["model"]["input"]
        assert options["capabilitySources"]["supports_vision"] == "model_policy"
    finally:
        app.close()


def test_published_context_window_reaches_a_new_pi_session(settings, tmp_path):
    from mms_web.server import WebApplication

    draft = payload(settings)
    draft.update(efforts={}, contextWindows={"gpt-5": 262144})
    preview = settings.preview(draft)
    assert preview["changes"][0]["kind"] == "context"
    assert preview["changes"][0]["after"] == "262144"
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    rows = settings.read()["providers"]
    assert all(next(m for m in p["models"] if m["id"] == "gpt-5")["contextWindow"] == 262144 for p in rows)

    app = WebApplication(state_root=tmp_path / "web-context", config_root=settings.root)
    project = tmp_path / "project-context"
    project.mkdir()
    try:
        workspace = app.catalog.add_workspace({"path": str(project)})
        options = app.post(["launch-options"], {"presetId": "web:pi:channel-a:gpt-5",
                                                "workspaceId": workspace["id"]})
        assert options["model"]["contextWindow"] == 262144
    finally:
        app.close()


@pytest.mark.parametrize("bad", [
    {"visions": {"gpt-5": "yes"}},
    {"visions": {"unknown-model": True}},
    {"contextWindows": {"gpt-5": 12}},
    {"contextWindows": {"gpt-5": 99_000_000}},
    {"contextWindows": {"gpt-5": True}},
    {"contextWindows": {"gpt-5": "262144"}},
])
def test_reject_unsafe_capability_input(settings, bad):
    draft = payload(settings)
    draft.update(efforts={}, **bad)
    with pytest.raises(WebError):
        settings.preview(draft)


def refresh(service, sources=None, models=("gpt-5", "gpt-4.1")):
    snap = service.read()
    request = {"fingerprint": snap["fingerprint"], "revision": snap["revision"],
               "providerId": "channel-a", "models": list(models)}
    if sources is not None:
        request["sources"] = sources
    return service.refresh(request)


def picked(result, wanted=("vision", "context", "effort")):
    """Collect the proposal the way the page does when a row is checked."""
    edits = {"visions": {}, "contextWindows": {}, "efforts": {}}
    key = {"vision": "visions", "context": "contextWindows", "effort": "efforts"}
    for item in result["proposals"]:
        for field in item["fields"]:
            if field["field"] in wanted:
                edits[key[field["field"]]][item["model"]] = field["value"]
    return edits


def test_capability_review_only_drafts_until_the_human_saves(settings, tmp_path):
    """The review sheet must behave like typing in the rows, not like a save."""
    from mms_web.server import WebApplication

    before = settings.read()
    result = refresh(settings)
    # Reading snapshots is not a write: nothing about the config moved.
    assert settings.read()["revision"] == before["revision"]
    assert settings.fingerprint() == before["fingerprint"]
    proposal = {item["model"]: item["fields"] for item in result["proposals"]}
    assert proposal["gpt-5"][0]["after"] == "medium"
    assert proposal["gpt-5"][0]["source"] == "official"
    assert next(m for m in before["providers"][0]["models"] if m["id"] == "gpt-5")["effort"] == "low"
    assert [r["source"] for r in result["reports"]] == ["official", "approved"]

    # Checked rows produce the same shape the row controls produce, so they go
    # through the one existing preview and publish path.
    draft = payload(settings)
    draft.update(picked(result))
    preview = settings.preview(draft)
    assert {c["model"]: c["after"] for c in preview["changes"] if c["kind"] == "effort"} == {"gpt-5": "medium", "gpt-4.1": "medium"}
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})

    app = WebApplication(state_root=tmp_path / "web-refresh", config_root=settings.root)
    project = tmp_path / "project-refresh"
    project.mkdir()
    try:
        workspace = app.catalog.add_workspace({"path": str(project)})
        options = app.post(["launch-options"], {"presetId": "web:pi:channel-a:gpt-5",
                                                "workspaceId": workspace["id"]})
        assert options["configuredThinkingLevel"] == "medium"
    finally:
        app.close()


def test_review_flags_a_value_the_user_set_themselves(settings):
    """Overwriting an explicit setting is opt-in, not the default."""
    # gpt-5 carries an effort from the fixture policy; gpt-4.1 does not.
    result = refresh(settings)
    flags = {item["model"]: [f["userSet"] for f in item["fields"]] for item in result["proposals"]}
    assert flags["gpt-5"] == [True]
    assert flags["gpt-4.1"] == [False]


def test_catalog_rows_are_marked_as_catalog_not_official(settings):
    """OpenRouter reports its own routing limits, so it must be labelled."""
    result = refresh(settings, sources=["catalog"])
    sources = {f["source"] for item in result["proposals"] for f in item["fields"]}
    assert sources == {"catalog"}
    assert [r["source"] for r in result["reports"]] == ["catalog"]
    # A more trusted source wins when both are asked for.
    merged = refresh(settings, sources=["official", "approved", "catalog"])
    efforts = {item["model"]: f["source"]
               for item in merged["proposals"] for f in item["fields"] if f["field"] == "effort"}
    assert set(efforts.values()) == {"official"}


def test_review_never_proposes_a_level_this_route_cannot_run(settings):
    """A clamped effort would report a change the launcher would not honour."""
    rows = {m["id"]: m for m in settings.read()["providers"][0]["models"]}
    for sources in (None, ["catalog"]):
        result = refresh(settings, sources=sources)
        for item in result["proposals"]:
            for field in item["fields"]:
                if field["field"] == "effort":
                    assert field["value"] in rows[item["model"]]["effortLevels"]
                if field["field"] == "context":
                    assert isinstance(field["value"], int) and 1024 <= field["value"] <= 10_000_000


def test_refresh_rejects_an_unknown_source(settings):
    with pytest.raises(WebError, match="能力来源"):
        refresh(settings, sources=["somewhere-else"])


def test_review_protects_unsaved_edits_and_compares_with_the_draft(settings):
    before = settings.fingerprint()
    draft = payload(settings)
    draft.update(visions={"gpt-5": False}, contextWindows={"gpt-5": 524288},
                 efforts={"gpt-4.1": "high"})
    result = settings.refresh(draft)
    fields = [field for item in result["proposals"] for field in item["fields"]
              if (item["model"] == "gpt-5" and field["field"] != "effort") or item["model"] == "gpt-4.1"]
    assert {field["field"] for field in fields} == {"vision", "context", "effort"}
    assert all(field["userSet"] for field in fields)
    by_field = {field["field"]: field for field in fields}
    assert by_field["vision"]["before"] == "不可读取图片"
    assert by_field["context"]["before"] == "524288"
    assert by_field["effort"]["before"] == "high"
    assert settings.fingerprint() == before


def test_delete_channel_removes_provider_and_keeps_others(settings):
    before = {p["id"] for p in settings.read()["providers"]}
    assert {"channel-a", "channel-b"} <= before
    snap = settings.read()
    preview = settings.preview({
        "fingerprint": snap["fingerprint"], "revision": snap["revision"],
        "providerId": "channel-b", "removeProviderId": "channel-b",
    })
    assert preview["changes"] == [{"kind": "channel-remove", "model": "channel-b", "channels": ["channel-b"]}]
    # A confirm phrase is still required before anything is written.
    with pytest.raises(WebError, match="确认"):
        settings.apply({"previewId": preview["previewId"]})
    result = settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})
    assert result["applied"]
    after = settings.read()
    ids = {p["id"] for p in after["providers"]}
    assert "channel-b" not in ids and "channel-a" in ids
    # channel-a keeps its published models untouched by the deletion.
    keep = next(p for p in after["providers"] if p["id"] == "channel-a")
    assert {m["id"] for m in keep["models"] if m["visible"]} == {"gpt-5", "gpt-4.1"}


def test_delete_last_channel_is_refused(settings):
    snap = settings.read()
    settings.apply({"previewId": settings.preview({
        "fingerprint": snap["fingerprint"], "revision": snap["revision"],
        "providerId": "channel-b", "removeProviderId": "channel-b",
    })["previewId"], "confirmPhrase": "写入预览DB"})
    snap = settings.read()
    assert [p["id"] for p in snap["providers"]] == ["channel-a"]
    with pytest.raises(WebError, match="最后一个通道"):
        settings.preview({
            "fingerprint": snap["fingerprint"], "revision": snap["revision"],
            "providerId": "channel-a", "removeProviderId": "channel-a",
        })


def test_fetching_models_replaces_the_route_instead_of_merging(settings, tmp_path):
    """A model deleted upstream has to leave this machine, not just lose a tick.

    Fetching used to union the remote list into the local one, so a model the
    channel had dropped stayed selectable in the terminal forever. The remote
    list is authoritative: saving it must remove what it no longer contains,
    from the published routes and from a freshly launched session alike.
    """
    from mms_web.server import WebApplication

    snapshot = settings.read()
    seeded = settings.preview({
        "fingerprint": snapshot["fingerprint"],
        "revision": snapshot["revision"],
        "providerId": "channel-a",
        "models": ["gpt-5", "gpt-4.1", "retired-model"],
        "efforts": {},
    })
    settings.apply({"previewId": seeded["previewId"], "confirmPhrase": "写入预览DB"})
    snapshot = settings.read()
    channel = next(p for p in snapshot["providers"] if p["id"] == "channel-a")
    assert "retired-model" in {m["id"] for m in channel["models"] if m["visible"]}

    # The upstream fixture never serves retired-model, so this is the real shape
    # of "the channel deleted a model".
    found = settings.discover({
        "fingerprint": snapshot["fingerprint"],
        "revision": snapshot["revision"],
        "providerId": "channel-a",
        "models": ["gpt-5"],
    })
    assert "retired-model" not in found["models"]

    preview = settings.preview({
        "fingerprint": snapshot["fingerprint"],
        "revision": snapshot["revision"],
        "providerId": "channel-a",
        "models": sorted(found["models"]),
        "efforts": {},
    })
    assert {"kind": "remove", "model": "retired-model"} in preview["changes"]
    settings.apply({"previewId": preview["previewId"], "confirmPhrase": "写入预览DB"})

    channel = next(p for p in settings.read()["providers"] if p["id"] == "channel-a")
    # Not merely hidden: gone from the rows the page and the terminal read.
    assert {m["id"] for m in channel["models"]} == set(found["models"])

    published = json.loads((settings.root / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    assert "retired-model" not in json.dumps(published)
    assert "retired-model" not in (settings.root / "config.toml").read_text(encoding="utf-8")

    app = WebApplication(state_root=tmp_path / "web-overwrite", config_root=settings.root)
    project = tmp_path / "project-overwrite"
    project.mkdir()
    try:
        workspace = app.catalog.add_workspace({"path": str(project)})
        with pytest.raises(WebError):
            app.post(["launch-options"], {"presetId": "web:pi:channel-a:retired-model",
                                          "workspaceId": workspace["id"]})
        # The models that survived the fetch still launch.
        options = app.post(["launch-options"], {"presetId": "web:pi:channel-a:gpt-5",
                                                "workspaceId": workspace["id"]})
        assert options["model"]["id"] == "gpt-5"
    finally:
        app.close()
