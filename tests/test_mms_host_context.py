import json
from pathlib import Path


def test_write_host_context_uses_path_only_config(monkeypatch, tmp_path):
    from mms_runtime.host_context import write_host_context

    real_home = tmp_path / "real-home"
    session_home = tmp_path / "session-home"
    repo_dir = tmp_path / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    config_path = real_home / ".config" / "mms" / "ops-env-safe.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
mode = "path-only"

[web_access]
proxy_url = "http://127.0.0.1:3456"
chrome_debug_port = 9222
extension_id = "ext-test"
check_deps = "/real/check-deps.mjs"

[paths]
shared_bin = "/real/bin"
custom_1 = "/real/custom"

[purposes]
custom_1 = "custom path"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo_dir)

    env = write_host_context(
        session_home,
        real_home=real_home,
        cli="codex",
        model="gpt-5.4",
        config_path=config_path,
        tool_bins={"gh": {"bin": "/opt/homebrew/bin/gh", "wrapper": str(session_home / ".mms" / "bin" / "gh"), "requires_auth": True}},
    )

    context_path = Path(env["MMS_HOST_CONTEXT_JSON"])
    context = json.loads(context_path.read_text(encoding="utf-8"))
    serialized = context_path.read_text(encoding="utf-8")

    assert context["session"]["cwd"] == str(repo_dir.resolve())
    assert context["session"]["repo_root"] == str(repo_dir.resolve())
    assert context["session"]["model"] == "gpt-5.4"
    assert context["host"]["home"] == str(real_home)
    assert context["host"]["config_exists"] is True
    assert context["web_access"]["extension_id"] == "ext-test"
    assert env["WEB_ACCESS_HOST_HOME"] == str(real_home)
    assert env["MMS_CHROME_EXTENSION_ID"] == "ext-test"
    assert "HOME" not in env
    assert "XDG_CONFIG_HOME" not in env
    assert "sk-secret" not in serialized
    assert {"name": "custom_1", "path": "/real/custom", "purpose": "custom path"} in context["paths"]
    assert context["tools"][0]["name"] == "gh"
