"""T7c: blocked_reasons must reach the user as actionable text."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mms_web.catalog import CatalogService
from mms_web.config_block_reasons import FALLBACK_MESSAGE, describe_blocked_reasons
from mms_web.errors import WebError
from mms_web.model_settings import ModelSettings

REPO = Path(__file__).resolve().parents[1]


def test_known_codes_each_map_to_their_own_sentence():
    assert "旧目录" in describe_blocked_reasons(["stable_root_human_only"])
    assert "~/.config/mms-next" in describe_blocked_reasons(["stable_root_human_only"])
    assert "没有区别" in describe_blocked_reasons(["no_draft_changes"])
    assert "重新加载配置" in describe_blocked_reasons(["stale_preview_bundle_revision"])
    assert "路由数量减少" in describe_blocked_reasons(["route_shrink_guard"])
    assert "守卫拦下" in describe_blocked_reasons(["route_publish_guard_blocked"])


def test_colon_prefixed_guard_reason_matches_by_prefix():
    reason = ("route_shrink_guard: candidate would shrink latest-approved route groups "
              "from 16 to 8; refresh WebUI or use an explicit recovery flow")
    assert describe_blocked_reasons([reason]) == describe_blocked_reasons(["route_shrink_guard"])
    stale = "stale_preview_bundle_revision: latest-approved bundle changed since this WebUI draft was loaded"
    assert describe_blocked_reasons([stale]) == describe_blocked_reasons(["stale_preview_bundle_revision"])


def test_unknown_code_is_kept_verbatim():
    message = describe_blocked_reasons(["some_future_guard"])
    assert "some_future_guard" in message
    assert "维护者" in message
    unknown_sentence = "future_guard: something unexpected happened"
    assert unknown_sentence in describe_blocked_reasons([unknown_sentence])


def test_multiple_reasons_all_shown_in_original_order():
    message = describe_blocked_reasons(["stable_root_human_only", "no_draft_changes"])
    assert "旧目录" in message and "没有区别" in message
    assert message.index("旧目录") < message.index("没有区别")
    reverse = describe_blocked_reasons(["no_draft_changes", "stable_root_human_only"])
    assert reverse.index("没有区别") < reverse.index("旧目录")
    combined = describe_blocked_reasons(
        ["stable_root_human_only", "no_draft_changes", "route_shrink_guard: from 16 to 8"])
    assert "旧目录" in combined and "没有区别" in combined and "路由数量减少" in combined


def test_empty_reasons_fall_back_to_generic_message():
    assert describe_blocked_reasons([]) == FALLBACK_MESSAGE
    assert describe_blocked_reasons(None) == FALLBACK_MESSAGE
    assert describe_blocked_reasons(["", "  "]) == FALLBACK_MESSAGE


def test_output_never_leaks_plan_internals_or_paths():
    plan = {
        "ok": False,
        "registry_v2_save_plan": {
            "blocked_reasons": ["stable_root_human_only", "mystery_code"],
            "root": {"config_root": "/private/tmp/secret-root/mms",
                     "stable_root": "/Users/alice/.config/mms",
                     "preview_root": "/Users/alice/.config/mms-next"},
        },
    }
    reasons = plan["registry_v2_save_plan"]["blocked_reasons"]
    message = describe_blocked_reasons(reasons)
    assert "/private/tmp/secret-root" not in message
    assert "/Users/alice" not in message
    assert "config_root" not in message and "preview_root" not in message
    # The only path-like text allowed is the static, written-in doc reference.
    assert message.count("mms-next") == message.count("~/.config/mms-next")


@pytest.fixture
def two_channel_settings(tmp_path, monkeypatch):
    """Real worker path: an approved bundle where channel-b owns unique routes."""
    # The worker subprocess saves through mms_core.save_config, which hard-exits
    # without tomli-w. install.sh ships it, but the ubuntu digger job installs
    # only pytest/httpx/rich, so the whole ModelSettings worker path fails there
    # at base (31 pre-existing failures in test_mms_web_model_settings.py).
    pytest.importorskip("tomli_w", reason="ModelSettings worker 子进程需要 tomli-w（install.sh 安装的运行依赖）")
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

    def provider(pid, models):
        return {"id": pid, "name": pid, "protocols": ["openai_chat_completions"], "supported_clis": ["pi", "codex"],
                "models_endpoint": "/models", "openai_base_url": url, "api_key": "private-fixture-key",
                "update_credentials": True, "fallback_models": models,
                "models": [{"id": m, "capability_touched": True,
                            "capabilities": {"reasoning_effort": "low", "reasoning": True, "thinking": True}}
                           for m in models]}

    models_a = [f"gpt-shared-{i}" for i in range(8)]
    models_b = [f"gpt-uniq-{i}" for i in range(8)]
    payload = {"draft": {"providers": [provider("channel-a", models_a), provider("channel-b", models_b)],
                         "provider_default": "channel-a"},
               "confirm_v2_preview": True, "confirm_phrase": "写入预览DB"}
    code = ('import json,sys; import mms_config_web as w; p=json.load(sys.stdin); '
            'r=w.apply_registry_v2_preview_plan({},p,config_path=sys.argv[1]); '
            'print(json.dumps({"ok":r.get("ok"),"errors":r.get("errors")}))')
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "MMS_CONFIG_ROOT": str(root), "MMS_PREVIEW_MODE": "1"}
    result = subprocess.run([sys.executable, "-c", code, str(root / "config.toml")],
                            input=json.dumps(payload), capture_output=True, text=True, cwd=REPO, env=env)
    assert json.loads(result.stdout.splitlines()[-1])["ok"], result.stdout[-600:]
    service = ModelSettings(CatalogService(config_root=root, state_root=tmp_path / "state"))
    try:
        yield service
    finally:
        upstream.__exit__(None, None, None)


def test_route_shrink_block_reaches_the_user_through_the_worker(two_channel_settings):
    """Deleting a channel with unique routes trips route_shrink_guard (426-428)."""
    service = two_channel_settings
    snap = service.read()
    with pytest.raises(WebError) as caught:
        service.preview({"fingerprint": snap["fingerprint"], "revision": snap["revision"],
                         "providerId": "channel-b", "removeProviderId": "channel-b"})
    error = caught.value
    assert error.code == "CONFIG_PLAN_BLOCKED"
    assert error.status == 409
    assert "路由数量减少" in error.message
    assert "逐个调整" in error.message
    # The old guessed sentence is gone, and no internal path crosses the wire.
    assert "请检查是否移除了全部可用模型" not in error.message
    assert str(service.root) not in error.message


def test_legacy_named_root_does_not_block_web_preview(two_channel_settings, tmp_path):
    """plan runs on a uuid snapshot, so stable_root_human_only is unreachable via WebUI preview."""
    import shutil
    legacy = tmp_path / "mms"
    shutil.copytree(two_channel_settings.root, legacy)
    service = ModelSettings(CatalogService(config_root=legacy, state_root=tmp_path / "state-legacy"))
    assert service.available()
    snap = service.read()
    # Removing one shared model is a real draft change but stays far below the
    # shrink-guard thresholds (16 routes -> 15, only 1 removed).
    preview = service.preview({"fingerprint": snap["fingerprint"], "revision": snap["revision"],
                               "providerId": "channel-a", "models": [f"gpt-shared-{i}" for i in range(7)],
                               "efforts": {}})
    assert preview["previewId"]
