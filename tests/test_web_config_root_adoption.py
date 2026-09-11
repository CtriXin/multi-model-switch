"""Pilot installs made before the roots converged must not strand channels."""

import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _seed_v2_root(root: Path, *, model: str) -> None:
    """Publish one channel into ``root`` the way first-run setup does.

    The Web writes through an isolated worker that pins MMS_CONFIG_ROOT to the
    target root, so the seed does the same.
    """
    import os

    import mms_root_bootstrap

    config_payload = {
        "provider": {"default": "web-gateway"},
        "providers": [
            {
                "id": "web-gateway",
                "name": "Web Gateway",
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["claude", "codex", "opencode", "pi"],
                "models_endpoint": "manual",
                "fallback_models": [model],
                "openai_base_url": "https://gateway.example.com/v1",
                "default_openai_base_url": "https://gateway.example.com/v1",
            }
        ],
    }
    previous = os.environ.get("MMS_CONFIG_ROOT")
    os.environ["MMS_CONFIG_ROOT"] = str(root)
    try:
        summary = mms_root_bootstrap.bootstrap_v2_root(
            config_dir=root,
            config_payload=config_payload,
            credential_updates=[
                {
                    "provider_id": "web-gateway",
                    "base_url": "https://gateway.example.com/v1",
                    "openai_base_url": "https://gateway.example.com/v1",
                    "anthropic_base_url": "",
                    "api_key": "sk-web-owned",
                }
            ],
            command_name="mms web",
        )
    finally:
        if previous is None:
            os.environ.pop("MMS_CONFIG_ROOT", None)
        else:
            os.environ["MMS_CONFIG_ROOT"] = previous
    assert summary.get("ok"), summary


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "HOME"):
        monkeypatch.setenv(key, str(home))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


def test_web_owned_config_is_adopted_into_the_shared_root(isolated_home):
    from mms_web.runtime import default_config_root

    state_root = isolated_home / ".local" / "share" / "mms-web"
    web_owned = state_root / "config"
    _seed_v2_root(web_owned, model="web-owned-model")
    shared = isolated_home / ".config" / "mms-next"

    chosen = default_config_root(state_root)

    assert chosen == shared
    marker = json.loads((shared / "web-config-adopted.json").read_text(encoding="utf-8"))
    assert marker["source"] == str(web_owned)
    # The source stays put: adoption is a copy, so a failed upgrade can fall back.
    assert (web_owned / "generated" / "model-registry.latest-approved.json").is_file()

    from mms_registry_cli import verify_approved_bundle

    assert verify_approved_bundle(config_dir=str(shared)).get("verified") is True


def test_adoption_leaves_an_already_configured_shared_root_alone(isolated_home):
    from mms_web.runtime import default_config_root

    state_root = isolated_home / ".local" / "share" / "mms-web"
    _seed_v2_root(state_root / "config", model="web-owned-model")
    shared = isolated_home / ".config" / "mms-next"
    _seed_v2_root(shared, model="cli-model")

    chosen = default_config_root(state_root)

    assert chosen == shared
    assert not (shared / "web-config-adopted.json").exists()
    routes = json.loads((shared / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    assert list(routes["routes"]) == ["cli-model"]


def test_unverifiable_web_config_does_not_fork_runtime_root(isolated_home):
    from mms_web.runtime import default_config_root

    state_root = isolated_home / ".local" / "share" / "mms-web"
    web_owned = state_root / "config"
    (web_owned / "generated").mkdir(parents=True)
    (web_owned / "generated" / "model-registry.latest-approved.json").write_text(
        json.dumps({"schema": "mms.model_registry.latest_approved.v1", "files": {}}),
        encoding="utf-8",
    )

    chosen = default_config_root(state_root)

    assert chosen == isolated_home / ".config" / "mms-next"
    assert not (isolated_home / ".config" / "mms-next" / "web-config-adopted.json").exists()
