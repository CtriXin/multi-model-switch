import json
import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest


@pytest.fixture(autouse=True)
def isolate_pi_capability_bundle(monkeypatch):
    import mms_launchers

    real_resolve = mms_launchers._pi_support.resolve_model_capabilities

    def resolve_without_default_bundle(*args, **kwargs):
        kwargs.setdefault("approved_facts", {})
        kwargs.setdefault("model_policy", {})
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(mms_launchers._pi_support, "resolve_model_capabilities", resolve_without_default_bundle)


def test_pi_global_executable_uses_path_binary(monkeypatch, tmp_path):
    import mms_pi_support

    binary = tmp_path / "pi"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(mms_pi_support.shutil, "which", lambda name: str(binary) if name == "pi" else None)

    assert mms_pi_support._pi_global_executable() == str(binary)


def test_glint_pi_bridge_requires_glint_pane_and_managed_extension(monkeypatch, tmp_path):
    import mms_pi_support

    real_home = tmp_path / "real-home"
    bridge = real_home / ".pi" / "agent" / "extensions" / "glint-agent-bridge.ts"
    monkeypatch.setattr(
        mms_pi_support,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    pane_env = {
        "GLINT_PANE_ID": "workspace:pane",
        "GLINT_AGENT_SOCK": "/tmp/glint.sock",
    }

    assert mms_pi_support._glint_pi_bridge_path(pane_env) == ""
    bridge.parent.mkdir(parents=True)
    bridge.write_text("export default function () {}\n", encoding="utf-8")
    assert mms_pi_support._glint_pi_bridge_path(pane_env) == ""

    bridge.write_text("// Glint pi extension\n", encoding="utf-8")
    assert mms_pi_support._glint_pi_bridge_path(pane_env) == str(bridge)
    assert mms_pi_support._glint_pi_bridge_path({"GLINT_PANE_ID": "workspace:pane"}) == ""


def test_launch_pi_adds_glint_bridge_as_explicit_extension(monkeypatch):
    import mms_pi_support

    captured = {}
    bridge = "/tmp/glint-agent-bridge.ts"
    env = {
        "MMS_PI_PROVIDER": "mms-relay-a",
        "MMS_PI_SELECTED_MODEL": "gpt-5.4",
    }
    monkeypatch.setattr(mms_pi_support, "_pi_gateway_env", lambda *_args, **_kwargs: env)
    monkeypatch.setattr(mms_pi_support, "_pi_effective_selected_model", lambda *_args: "gpt-5.4")
    monkeypatch.setattr(mms_pi_support, "_glint_pi_bridge_path", lambda _env: bridge)
    monkeypatch.setattr(
        mms_pi_support,
        "_exec_or_run",
        lambda cmd, launch_env, once: captured.update(cmd=cmd, env=launch_env, once=once),
    )

    mms_pi_support.launch_pi(
        {"model": "gpt-5.4"},
        {"id": "relay-a", "auth_mode": "api_key"},
        once=True,
    )

    assert captured["cmd"] == [
        "pi",
        "--provider",
        "mms-relay-a",
        "--model",
        "gpt-5.4",
        "--extension",
        bridge,
    ]
    assert captured["env"] == env
    assert captured["once"] is True


def test_pi_policy_context_override_beats_provider_profile_default():
    import mms_pi_support

    result = mms_pi_support._pi_apply_profile_capability_overlay(
        {
            "context_window_tokens": 1_048_576,
            "sources": {"context_window_tokens": "model_policy"},
        },
        {
            "context_window_tokens": 262_144,
            "sources": {"context_window_tokens": "provider_profile"},
        },
    )

    assert result["context_window_tokens"] == 1_048_576
    assert result["sources"]["context_window_tokens"] == "model_policy"


def test_core_pi_cli_is_visible_and_provider_compat_is_implied():
    import mms_core

    provider = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "api_key": "sk-test",
        "openai_base_url": "https://relay.example.com/v1",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "supported_clis": ["claude", "codex"],
    }

    assert "pi" in mms_core.CLI_NAMES
    assert mms_core._provider_supports_cli_name(provider, "pi") is True


def test_runtime_resolver_uses_repo_pi_wrapper(monkeypatch, tmp_path):
    import mms_runtime

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "pi-cli-wrapper.sh"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    monkeypatch.setattr(mms_runtime, "__file__", str(tmp_path / "mms_runtime.py"))

    resolved = mms_runtime.resolve_cli_binary("pi", env={"PATH": "/usr/bin"})

    assert resolved == str(wrapper)


def test_pi_skill_overlay_keeps_project_skill_over_global_duplicate(monkeypatch, tmp_path):
    import mms_pi_support

    real_home = tmp_path / "real-home"
    global_skill = real_home / ".agents" / "skills" / "duplicate"
    project_skill = tmp_path / "project" / ".agents" / "skills" / "duplicate"
    global_only_skill = real_home / ".agents" / "skills" / "global-only"
    for skill_dir in (global_skill, project_skill, global_only_skill):
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\n", encoding="utf-8")
    (tmp_path / "project" / ".git").mkdir()
    monkeypatch.setattr(mms_pi_support, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    overlay = Path(mms_pi_support._pi_materialize_skill_overlay(tmp_path / "session", tmp_path / "project"))

    assert (overlay / "duplicate").is_symlink()
    assert (overlay / "duplicate").resolve() == project_skill
    assert (overlay / "global-only").resolve() == global_only_skill


def _pi_wrapper_env(tmp_path, cache_dir, *, bin_dir=None, **extra):
    """A PATH with node/npm/npx but no installed pi anywhere.

    The wrapper prefers an installed Pi over its npx cache (#205), and on a
    developer machine both `command -v pi` and `npm prefix -g` find the real
    one. Inheriting os.environ therefore made these cache tests exec the real
    pi instead. npm_config_prefix points at an empty prefix so `npm prefix -g`
    answers honestly that pi is not installed there.
    """
    bin_dir = Path(bin_dir) if bin_dir else (tmp_path / "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("node", "npm", "npx"):
        target = bin_dir / name
        real = shutil.which(name)
        if real and not target.exists():
            target.symlink_to(real)
    npm_prefix = tmp_path / "npm-prefix"
    (npm_prefix / "bin").mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"]),
        "HOME": str(home),
        "npm_config_prefix": str(npm_prefix),
        "MMS_PI_NPX_CACHE": str(cache_dir),
    }
    env.update(extra)
    assert shutil.which("pi", path=env["PATH"]) is None
    return env

def test_pi_wrapper_uses_the_cache_when_no_pi_is_installed(tmp_path):
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "pi-cli-wrapper.sh"
    cache_dir = tmp_path / "pi-npx"
    cached_pi = cache_dir / "_npx" / "cached" / "node_modules" / ".bin" / "pi"
    cached_pi.parent.mkdir(parents=True)
    (cached_pi.parent.parent / "@earendil-works" / "pi-coding-agent").mkdir(parents=True)
    (cached_pi.parent.parent / "@earendil-works" / "pi-coding-agent" / "package.json").write_text(
        '{"name":"@earendil-works/pi-coding-agent"}\n', encoding="utf-8"
    )
    cached_pi.write_text("#!/bin/sh\nprintf 'cached-pi:%s\\n' \"$*\"\n", encoding="utf-8")
    cached_pi.chmod(0o755)

    result = subprocess.run(
        [str(wrapper), "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_pi_wrapper_env(tmp_path, cache_dir),
    )

    assert result.stdout == "cached-pi:--version\n"


def test_pi_wrapper_warms_a_missing_cache_before_running(tmp_path):
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "pi-cli-wrapper.sh"
    cache_dir = tmp_path / "pi-npx"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_npx = fake_bin / "npx"
    fake_npx.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            set -eu
            mkdir -p "$MMS_PI_NPX_CACHE/_npx/hash/node_modules/.bin"
            mkdir -p "$MMS_PI_NPX_CACHE/_npx/hash/node_modules/@earendil-works/pi-coding-agent"
            printf '#!/bin/sh\\nprintf "warmed-pi:%%s\\\\n" "$*"\\n' > "$MMS_PI_NPX_CACHE/_npx/hash/node_modules/.bin/pi"
            printf '{"name":"@earendil-works/pi-coding-agent"}\\n' > "$MMS_PI_NPX_CACHE/_npx/hash/node_modules/@earendil-works/pi-coding-agent/package.json"
            chmod +x "$MMS_PI_NPX_CACHE/_npx/hash/node_modules/.bin/pi"
            """
        ),
        encoding="utf-8",
    )
    fake_npx.chmod(0o755)

    result = subprocess.run(
        [str(wrapper), "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_pi_wrapper_env(tmp_path, cache_dir, bin_dir=fake_bin),
    )

    assert result.stdout == "warmed-pi:--version\n"


def test_pi_gateway_root_and_sessions_honor_explicit_mms_config_root(monkeypatch, tmp_path):
    import mms_launchers
    import mms_pi_support

    preview_root = tmp_path / "mms-next"
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setattr(
        mms_launchers,
        "_selected_mms_config_root",
        lambda _env: str(preview_root),
    )

    assert mms_pi_support._pi_gateway_root() == str(preview_root / "pi-gateway")
    assert mms_pi_support._pi_session_dir() == str(preview_root / "pi-gateway" / "sessions")
    assert mms_pi_support._pi_shared_agent_bin() == str(preview_root / "pi-gateway" / "agent-bin")


def test_pi_shared_agent_bin_link_is_reused_across_sessions(monkeypatch, tmp_path):
    import mms_launchers
    import mms_pi_support

    preview_root = tmp_path / "mms-next"
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setattr(
        mms_launchers,
        "_selected_mms_config_root",
        lambda _env: str(preview_root),
    )

    shared_bin = mms_pi_support._pi_shared_agent_bin()

    sessions_dir = preview_root / "pi-gateway" / "s"
    sessions_dir.mkdir(parents=True)

    first_agent = sessions_dir / "111" / ".pi" / "agent"
    mms_pi_support._pi_link_shared_agent_bin(str(first_agent))
    assert os.path.islink(str(first_agent / "bin"))
    assert os.readlink(str(first_agent / "bin")) == shared_bin

    tool_marker = first_agent / "bin" / "rg"
    tool_marker.write_text("binary")

    second_agent = sessions_dir / "222" / ".pi" / "agent"
    mms_pi_support._pi_link_shared_agent_bin(str(second_agent))
    assert os.path.islink(str(second_agent / "bin"))
    assert os.readlink(str(second_agent / "bin")) == shared_bin
    assert (second_agent / "bin" / "rg").read_text() == "binary"

    import shutil
    shutil.rmtree(str(sessions_dir / "111"))
    assert (Path(shared_bin) / "rg").exists(), "shared bin must survive per-PID cleanup"


def test_pi_wrapper_serializes_cold_npx_prewarm(tmp_path):
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "pi-cli-wrapper.sh"
    bin_dir = tmp_path / "bin"
    cache_dir = tmp_path / "pi-npx"
    log_path = tmp_path / "npx.log"
    bin_dir.mkdir()
    fake_npx = bin_dir / "npx"
    fake_npx.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            set -eu
            printf '%s\\n' "$*" >> "$FAKE_NPX_LOG"
            case " $* " in
              *" --version "*)
                mkdir -p "$FAKE_PI_CACHE/_npx/hash/node_modules/.bin"
                mkdir -p "$FAKE_PI_CACHE/_npx/hash/node_modules/@earendil-works/pi-coding-agent"
                printf '#!/bin/sh\\nexit 0\\n' > "$FAKE_PI_CACHE/_npx/hash/node_modules/.bin/pi"
                printf '{"name":"@earendil-works/pi-coding-agent"}\\n' > "$FAKE_PI_CACHE/_npx/hash/node_modules/@earendil-works/pi-coding-agent/package.json"
                chmod +x "$FAKE_PI_CACHE/_npx/hash/node_modules/.bin/pi"
                exit 0
                ;;
            esac
            exit 0
            """
        ),
        encoding="utf-8",
    )
    fake_npx.chmod(0o755)
    env = _pi_wrapper_env(
        tmp_path,
        cache_dir,
        bin_dir=bin_dir,
        MMS_PI_NPX_INSTALL_LOCK_TIMEOUT="10",
        FAKE_NPX_LOG=str(log_path),
        FAKE_PI_CACHE=str(cache_dir),
    )

    processes = [
        subprocess.Popen([str(wrapper), "--probe", str(index)], env=env)
        for index in range(4)
    ]
    for process in processes:
        assert process.wait(timeout=15) == 0

    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert sum("--version" in call for call in calls) == 1
    # Once prewarmed, the wrapper executes the cached binary directly.
    assert sum("--probe" in call for call in calls) == 0


def test_launch_pi_writes_openai_models_config_and_uses_wrapper(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    preview_root = tmp_path / "mms-next"
    monkeypatch.setattr(mms_launchers, "_selected_mms_config_root", lambda _env: str(preview_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers._pi_support, "_pi_materialize_skill_overlay", lambda *_args: "/tmp/pi-skills")
    monkeypatch.setattr(mms_launchers, "_scrub_inherited_runtime_env", lambda env, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_inject_real_home_hints", lambda env, include_xdg=False: env)
    monkeypatch.setattr(mms_launchers, "_inject_host_capability_hints", lambda env: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4", "gpt-5.5"]})
    monkeypatch.setattr(mms_launchers.os, "getpid", lambda: 4242)

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    runtime = {
        "id": "relay-a",
        "name": "Relay A",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-openai",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["codex"],
        "thinking_mode": "disable",
    }

    mms_launchers.launch_pi({"model": "gpt-5.4"}, runtime, once=True)

    assert captured["cmd"] == [
        "pi",
        "--provider",
        "mms-relay-a",
        "--model",
        "gpt-5.4",
        "--no-skills",
        "--skill",
        "/tmp/pi-skills",
        "--thinking",
        "off",
    ]
    assert captured["once"] is True
    assert captured["env"]["MMS_PI_BIN"] == "/tmp/pi-wrapper"
    assert captured["env"]["MMS_PI_NPX_CACHE"].endswith(".ai/cache/pi-npx")
    assert captured["env"]["MMS_PI_SETTINGS_JSON"].endswith("settings.json")
    assert captured["env"]["PI_CODING_AGENT_SESSION_DIR"] == str(
        preview_root / "pi-gateway" / "sessions"
    )

    models_path = preview_root / "pi-gateway" / "s" / "4242" / ".pi" / "agent" / "models.json"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-a"]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["apiKey"] == "sk-openai"
    assert provider["models"][0]["id"] == "gpt-5.4"
    assert provider["models"][1]["id"] == "gpt-5.5"
    settings_payload = json.loads(
        (preview_root / "pi-gateway" / "s" / "4242" / ".pi" / "agent" / "settings.json").read_text(
            encoding="utf-8"
        )
    )
    assert settings_payload["retry"] == {"enabled": True, "maxRetries": 8, "baseDelayMs": 1000}
    assert settings_payload["quietStartup"] is True
    assert settings_payload["extensions"][0].endswith("scripts/pi-retry-extension.mjs")
    assert not (real_home / ".config" / "mms-next" / "pi-gateway").exists()


def test_launch_pi_rewrites_deprecated_antigravity_gemini_alias_to_live_replacement(monkeypatch, tmp_path):
    import mms_launchers

    captured = {}
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers._pi_support, "_pi_materialize_skill_overlay", lambda *_args: "")
    monkeypatch.setattr(mms_launchers, "_scrub_inherited_runtime_env", lambda env, **_kwargs: env)
    monkeypatch.setattr(mms_launchers, "_inject_real_home_hints", lambda env, include_xdg=False: env)
    monkeypatch.setattr(mms_launchers, "_inject_host_capability_hints", lambda env: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gemini-3-pro-high", "gemini-3.1-pro-low"]},
    )
    monkeypatch.setattr(mms_launchers.os, "getpid", lambda: 4242)

    def fake_exec(cmd, env, once, **_kwargs):
        captured["cmd"] = cmd
        captured["env"] = dict(env)
        captured["once"] = once

    monkeypatch.setattr(mms_launchers, "_exec_or_run", fake_exec)

    runtime = {
        "id": "us-cpa-local-antigravity",
        "name": "Antigravity",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-antigravity",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["codex"],
        "thinking_mode": "disable",
    }

    mms_launchers.launch_pi({"model": "gemini-3-pro-high"}, runtime, once=True)

    assert captured["cmd"] == [
        "pi",
        "--provider",
        "mms-us-cpa-local-antigravity",
        "--model",
        "gemini-3.1-pro-low",
        "--thinking",
        "off",
    ]
    assert captured["once"] is True
    assert captured["env"]["MMS_PI_SELECTED_MODEL"] == "gemini-3.1-pro-low"


def test_get_export_env_for_pi_writes_anthropic_models_config(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6", "claude-opus-4-7"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-b",
            "name": "Relay B",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["claude"],
            "model": "claude-sonnet-4-6",
        },
    )

    assert exports["MMS_PI_BIN"] == "/tmp/pi-wrapper"
    assert exports["MMS_PI_NPX_CACHE"].endswith(".ai/cache/pi-npx")
    assert exports["MMS_PI_SETTINGS_JSON"].endswith("settings.json")
    models_path = real_home / ".config" / "mms-next" / "pi-gateway" / "exports" / "relay-b-claude-sonnet-4-6" / "agent" / "models.json"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-b"]
    assert provider["api"] == "anthropic-messages"
    assert provider["baseUrl"] == "https://relay.example.com/anthropic"
    assert provider["models"][0]["id"] == "claude-sonnet-4-6"
    assert provider["models"][1]["id"] == "claude-opus-4-7"
    assert provider["models"][0]["input"] == ["text", "image"]
    assert provider["models"][0]["reasoning"] is True
    assert provider["models"][0]["contextWindow"] == 1_000_000
    # Sonnet 4.6 official model page lists 128K max output (verified 2026-09-09).
    # https://platform.claude.com/docs/en/models/sonnet-4-6/overview
    assert provider["models"][0]["maxTokens"] == 128_000
    assert provider["models"][0]["compat"] == {"forceAdaptiveThinking": True}
    assert provider["models"][1]["compat"] == {"forceAdaptiveThinking": True}
    settings_payload = json.loads(Path(exports["MMS_PI_SETTINGS_JSON"]).read_text(encoding="utf-8"))
    assert settings_payload["retry"] == {"enabled": True, "maxRetries": 8, "baseDelayMs": 1000}
    assert settings_payload["extensions"][0].endswith("scripts/pi-retry-extension.mjs")


def test_get_export_env_for_pi_accepts_model_info_when_runtime_has_no_model(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda runtime, emit_output=False: {"models": ["gpt-5.4", "gpt-5.5"]})

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-c",
            "name": "Relay C",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-openai",
            "openai_base_url": "https://relay.example.com/v1",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.4"},
    )

    assert exports["MMS_PI_BIN"] == "/tmp/pi-wrapper"
    assert exports["MMS_PI_NPX_CACHE"].endswith(".ai/cache/pi-npx")
    assert exports["MMS_PI_SETTINGS_JSON"].endswith("settings.json")
    models_path = Path(exports["MMS_PI_MODELS_JSON"])
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-relay-c"]
    assert provider["api"] == "openai-completions"
    assert provider["models"][0]["id"] == "gpt-5.4"
    assert provider["models"][1]["id"] == "gpt-5.5"
    settings_payload = json.loads(Path(exports["MMS_PI_SETTINGS_JSON"]).read_text(encoding="utf-8"))
    assert settings_payload["retry"] == {"enabled": True, "maxRetries": 8, "baseDelayMs": 1000}
    assert settings_payload["extensions"][0].endswith("scripts/pi-retry-extension.mjs")


def test_pi_dual_protocol_payload_splits_models_by_preferred_protocol(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.6-plus", "gpt-5.4"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "pi"],
        },
        model_info={"model": "qwen3.6-plus"},
    )

    assert exports["MMS_PI_SELECTED_MODEL"] == "qwen3.6-plus"
    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    assert set(payload["providers"]) == {
        "mms-newapi-personal-tokyo-anthropic",
        "mms-newapi-personal-tokyo-openai",
    }
    assert exports["MMS_PI_PROVIDER"] == "mms-newapi-personal-tokyo-anthropic"
    anthropic_models = payload["providers"]["mms-newapi-personal-tokyo-anthropic"]["models"]
    openai_models = payload["providers"]["mms-newapi-personal-tokyo-openai"]["models"]
    assert [item["id"] for item in anthropic_models] == ["qwen3.6-plus"]
    assert [item["id"] for item in openai_models] == ["gpt-5.4"]
    assert anthropic_models[0]["reasoning"] is True
    assert anthropic_models[0]["contextWindow"] == 1_000_000
    assert anthropic_models[0]["maxTokens"] == 65_536
    assert openai_models[0]["input"] == ["text", "image"]
    assert openai_models[0]["maxTokens"] == 128_000


def test_pi_gpt_without_declared_responses_uses_openai_chat(monkeypatch):
    import mms_launchers

    runtime = {
        "id": "relay-a",
        "openai_base_url": "https://relay.example.com/v1",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
    }
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda *_args, **_kwargs: {"models": ["gpt-5.6-luna"]})

    variants = mms_launchers._pi_protocol_variants(runtime)
    selected, _caps = mms_launchers._pi_pick_protocol(runtime, "gpt-5.6-luna")
    payload, provider_ref = mms_launchers._pi_build_models_payload(runtime, "gpt-5.6-luna")

    assert [variant["protocol"] for variant in variants] == [
        "anthropic_messages",
        "openai_chat_completions",
    ]
    assert selected["protocol"] == "openai_chat_completions"
    assert payload["providers"][provider_ref]["api"] == "openai-completions"
    assert payload["providers"][provider_ref]["models"][0]["input"] == ["text", "image"]


def test_pi_explicit_responses_alias_preserves_responses_transport():
    import mms_launchers

    runtime = {
        "id": "responses-relay",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai-responses"],
    }

    variants = mms_launchers._pi_protocol_variants(runtime)
    selected, _caps = mms_launchers._pi_pick_protocol(runtime, "gpt-5.6-luna")

    assert [variant["protocol"] for variant in variants] == ["responses"]
    assert selected["api"] == "openai-responses"


def test_pi_qwen38_dual_protocol_prefers_openai(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.8-max-preview"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "qwen3.8-max-preview"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert [item["id"] for item in provider["models"]] == ["qwen3.8-max-preview"]


def test_pi_glm_dual_protocol_prefers_openai(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["glm-5.2"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "glm-5.2"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert [item["id"] for item in provider["models"]] == ["glm-5.2"]


def test_pi_openai_provider_compat_uses_profile_specific_flags(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["deepseek-v4-pro"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "deepseek-direct",
            "name": "DeepSeek Direct",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-deepseek",
            "openai_base_url": "https://api.deepseek.com",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "deepseek-v4-pro"},
    )

    assert exports["MMS_PI_SELECTED_MODEL"] == "deepseek-v4-pro"
    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"]["mms-deepseek-direct"]
    assert provider["compat"] == {
        "requiresReasoningContentOnAssistantMessages": True,
        "supportsDeveloperRole": False,
        "thinkingFormat": "deepseek",
    }
    # The 2026-09-10 live probes moved the whole deepseek family onto the
    # v4.1 backend: 393216 output tokens and every tier accepted as itself,
    # so xhigh is no longer folded into max.
    assert provider["models"][0]["maxTokens"] == 393_216
    assert provider["models"][0]["thinkingLevelMap"] == {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": "max",
    }


def test_pi_profile_derived_effort_maps_expose_only_truthful_levels():
    import mms_launchers

    gpt_map = mms_launchers._pi_model_thinking_level_map(
        {
            "id": "uscrsopenai",
            "openai_base_url": "https://relay.example.com/v1",
        },
        "openai",
        "responses",
        "gpt-5.6-terra",
        {"supports_thinking": True},
    )
    assert gpt_map == {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": "max",
    }

    kimi_map = mms_launchers._pi_model_thinking_level_map(
        {
            "id": "openrouter",
            "openai_base_url": "https://openrouter.ai/api/v1",
        },
        "openrouter-moonshot-kimi-k3",
        "openai_chat_completions",
        "kimi-k3",
        {"supports_thinking": True},
    )
    assert kimi_map == {
        "minimal": None,
        "low": None,
        "medium": None,
        "high": None,
        "xhigh": None,
        "max": "max",
        "off": None,
    }

    kimi_anthropic_map = mms_launchers._pi_model_thinking_level_map(
        {
            "id": "newapi-personal-tokyo",
            "anthropic_base_url": "https://gateway.example.com",
        },
        "",
        "anthropic_messages",
        "k3",
        {"supports_thinking": True},
    )
    assert kimi_anthropic_map == kimi_map

    qwen_map = mms_launchers._pi_model_thinking_level_map(
        {
            "id": "direct-qwen",
            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        "dashscope-openai",
        "openai_chat_completions",
        "qwen3.6-plus",
        {"supports_thinking": True},
    )
    # qwen3.6 accepts six values; only max is refused, and the map has to say
    # so rather than hiding tiers this route can actually execute.
    assert qwen_map == {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": None,
    }


def test_pi_export_enables_gpt_xhigh_when_the_profile_supports_it(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-5.6-terra"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "uscrsopenai",
            "name": "US CRS OpenAI",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "openai_base_url": "https://relay.example.com/v1",
            "protocols": ["responses"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.6-terra"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    model = payload["providers"]["mms-uscrsopenai"]["models"][0]
    assert model["thinkingLevelMap"]["xhigh"] == "xhigh"


def test_pi_shared_root_openai_base_url_is_normalized_to_v1(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-5.4", "mimo-v2.5-pro"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-root",
            "name": "Relay Root",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com",
            "anthropic_base_url": "https://relay.example.com",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.4"},
    )

    assert exports["MMS_PI_SELECTED_MODEL"] == "gpt-5.4"
    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    openai_providers = [provider for provider in payload["providers"].values() if provider["api"].startswith("openai-")]
    assert openai_providers
    assert {provider["baseUrl"] for provider in openai_providers} == {"https://relay.example.com/v1"}


def test_pi_mimo_openai_provider_disables_developer_role(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["mimo-v2.5-pro"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com",
            "anthropic_base_url": "https://relay.example.com",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "mimo-v2.5-pro"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["compat"]["supportsDeveloperRole"] is False


def test_pi_dashscope_openai_provider_disables_developer_role(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.8-max-preview"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-qwen-relay",
            "name": "NewAPI Qwen Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com",
            "anthropic_base_url": "https://relay.example.com",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "qwen3.8-max-preview"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["compat"]["supportsDeveloperRole"] is False
    assert provider["compat"]["thinkingFormat"] == "qwen"


def test_pi_deepseek_openai_provider_disables_developer_role(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["deepseek-reasoner"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-deepseek-relay",
            "name": "NewAPI DeepSeek Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-relay",
            "openai_base_url": "https://relay.example.com",
            "anthropic_base_url": "https://relay.example.com",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "deepseek-reasoner"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://relay.example.com/v1"
    assert provider["compat"]["supportsDeveloperRole"] is False


def test_pi_kimi_family_uses_builtin_max_token_hint(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["kimi-for-coding"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "kimi-direct",
            "name": "Kimi Direct",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-kimi",
            "openai_base_url": "https://api.kimi.com/coding/v1",
            "anthropic_base_url": "https://api.kimi.com/coding",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "kimi-for-coding"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["models"][0]["id"] == "kimi-for-coding"
    assert provider["models"][0]["input"] == ["text", "image"]
    assert provider["models"][0]["contextWindow"] == 262_144
    assert provider["models"][0]["maxTokens"] == 32_768


def test_pi_kimi_k3_exports_1m_context_and_openai_protocol(monkeypatch, tmp_path):
    import mms_capability_resolver
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})
    monkeypatch.setattr(
        mms_capability_resolver,
        "load_default_model_policy",
        lambda: {
            "models": {
                "k3": {
                    "capabilities": {
                        "context_window_tokens": 1_000_000,
                        "supports_thinking": True,
                        "thinking_control": {
                            "path": "thinking.type",
                            "supported": True,
                        },
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["k3[1m]", "k3", "kimi-k3", "kimi-for-coding-highspeed"]
        },
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "kimi-direct",
            "name": "Kimi Direct",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-kimi",
            "openai_base_url": "https://api.kimi.com/coding/v1",
            "anthropic_base_url": "https://api.kimi.com/coding",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "kimi-k3"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    model_by_id = {
        item["id"]: item
        for payload_provider in payload["providers"].values()
        for item in payload_provider["models"]
    }
    assert provider["api"] == "openai-completions"
    assert provider["baseUrl"] == "https://api.kimi.com/coding/v1"
    assert model_by_id["kimi-k3"]["input"] == ["text", "image"]
    assert model_by_id["kimi-k3"]["contextWindow"] == 1_048_576
    assert model_by_id["kimi-k3"]["maxTokens"] == 1_048_576
    assert model_by_id["kimi-k3"]["reasoning"] is True
    assert model_by_id["k3[1m]"]["input"] == ["text", "image"]
    assert model_by_id["k3[1m]"]["contextWindow"] == 1_048_576
    assert model_by_id["k3[1m]"]["maxTokens"] == 1_048_576
    assert model_by_id["k3[1m]"]["reasoning"] is True
    assert model_by_id["k3"]["input"] == ["text", "image"]
    assert model_by_id["k3"]["contextWindow"] == 1_048_576
    assert model_by_id["k3"]["maxTokens"] == 131_072
    assert model_by_id["k3"]["reasoning"] is True
    assert model_by_id["kimi-for-coding-highspeed"]["contextWindow"] == 262_144
    assert model_by_id["kimi-for-coding-highspeed"]["maxTokens"] == 32_768
    anthropic_provider = next(
        item for item in payload["providers"].values() if item["api"] == "anthropic-messages"
    )
    assert [item["id"] for item in anthropic_provider["models"]] == ["kimi-for-coding-highspeed"]


def test_pi_tokyo_k3_anthropic_export_exposes_only_max(monkeypatch, tmp_path):
    import mms_capability_resolver
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})
    monkeypatch.setattr(
        mms_capability_resolver,
        "load_default_model_policy",
        lambda: {"models": {"k3": {"capabilities": {"supports_thinking": True}}}},
    )
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["k3"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "newapi-personal-tokyo",
            "name": "NewAPI Personal Tokyo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "anthropic_base_url": "https://gateway.example.com",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "k3"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "anthropic-messages"
    assert provider["models"][0]["thinkingLevelMap"] == {
        "off": None,
        "minimal": None,
        "low": None,
        "medium": None,
        "high": None,
        "xhigh": None,
        "max": "max",
    }


def test_pi_normalizes_anthropic_base_url_before_export(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-anthropic-v1",
            "name": "Relay Anthropic V1",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "claude-sonnet-4-6"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert provider["api"] == "anthropic-messages"
    assert provider["baseUrl"] == "https://relay.example.com"


def test_pi_skips_image_generation_only_models(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-image-2", "gpt-5.4"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "codex-relay",
            "name": "Codex Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-openai",
            "openai_base_url": "https://relay.example.com/v1",
            "protocols": ["openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gpt-5.4"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert [item["id"] for item in provider["models"]] == ["gpt-5.4"]


def test_pi_anthropic_local_thinking_alias_uses_wire_model_id(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["claude-opus-4-6-thinking", "claude-opus-4-6"],
        },
    )
    monkeypatch.setattr(mms_launchers, "_pi_model_block_reason", lambda runtime, model_name: "")

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "us-cpa-local-antigravity",
            "name": "Antigravity",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "claude-opus-4-6"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    model_by_id = {item["id"]: item for item in provider["models"]}
    assert "claude-opus-4-6" not in model_by_id
    assert model_by_id["claude-opus-4-6-thinking"]["name"] == "claude-opus-4-6"


def test_pi_local_selector_alias_uses_routed_wire_model_id(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["mimo-v2.5-pro[1m]", "mimo-v2.5-pro"],
        },
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "relay-root",
            "name": "relay-root",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-openai",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "mimo-v2.5-pro[1m]"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    model_by_id = {item["id"]: item for item in provider["models"]}
    assert "mimo-v2.5-pro[1m]" not in model_by_id
    assert model_by_id["mimo-v2.5-pro"]["name"] == "mimo-v2.5-pro[1m]"


def test_pi_mimo_plain_1m_alias_strips_to_base_wire_model_id(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["mimo-v2.5[1m]", "mimo-v2.5"],
        },
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "mimo-direct-anthropic",
            "name": "direct-mimo",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-anthropic",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "mimo-v2.5[1m]"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    model_by_id = {item["id"]: item for item in provider["models"]}
    assert "mimo-v2.5[1m]" not in model_by_id
    assert model_by_id["mimo-v2.5"]["name"] == "mimo-v2.5[1m]"


def test_pi_rejects_selected_image_generation_only_model(monkeypatch):
    import mms_launchers
    import pytest

    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gpt-image-2"]},
    )

    with pytest.raises(RuntimeError, match="image-generation-only model"):
        mms_launchers._pi_build_models_payload(
            {
                "id": "codex-relay",
                "name": "Codex Relay",
                "enabled": True,
                "auth_mode": "api_key",
                "api_key": "sk-openai",
                "openai_base_url": "https://relay.example.com/v1",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["pi"],
            },
            "gpt-image-2",
        )


def test_pi_reopens_deprecated_antigravity_gemini_alias_when_replacement_available(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["gemini-3-pro-high", "gemini-3.1-pro-low"],
        },
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "us-cpa-local-antigravity",
            "name": "Antigravity",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-antigravity",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "gemini-3-pro-high"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    provider = payload["providers"][exports["MMS_PI_PROVIDER"]]
    assert [item["id"] for item in provider["models"]] == ["gemini-3.1-pro-low", "gemini-3-pro-high"]


def test_pi_trust_store_scopes_trust_to_launch_project(monkeypatch, tmp_path):
    import mms_pi_support

    real_home = tmp_path / "real-home"
    project = real_home / "project"
    agent_dir = tmp_path / "session" / ".pi" / "agent"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        mms_pi_support,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    mms_pi_support._seed_pi_trust_store(str(agent_dir), str(project))

    payload = json.loads((agent_dir / "trust.json").read_text(encoding="utf-8"))
    assert payload == {str(project.resolve()): True}
    assert str(real_home.resolve()) not in payload


def test_pi_trust_store_does_not_auto_trust_real_home(monkeypatch, tmp_path):
    import mms_pi_support

    real_home = tmp_path / "real-home"
    agent_dir = tmp_path / "session" / ".pi" / "agent"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_pi_support,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    mms_pi_support._seed_pi_trust_store(str(agent_dir), str(real_home))

    assert not (agent_dir / "trust.json").exists()


def test_pi_exposed_model_names_recover_antigravity_opus_after_retry_hardening(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {
            "models": ["claude-opus-4-6-thinking", "claude-opus-4-6", "claude-sonnet-4-6"],
        },
    )

    models = mms_launchers._pi_exposed_model_names(
        {
            "id": "us-cpa-local-antigravity",
            "name": "Antigravity",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-antigravity",
            "anthropic_base_url": "https://relay.example.com/v1",
            "protocols": ["anthropic_messages"],
            "supported_clis": ["pi"],
        }
    )

    assert models == ["claude-opus-4-6-thinking", "claude-opus-4-6", "claude-sonnet-4-6"]


def test_pi_rejects_selected_runtime_blocked_model(monkeypatch):
    import mms_launchers
    import pytest

    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["gemini-3-pro-high"]},
    )

    with pytest.raises(RuntimeError, match="currently blocks model 'gemini-3-pro-high'"):
        mms_launchers._pi_build_models_payload(
            {
                "id": "us-cpa-local-antigravity",
                "name": "Antigravity",
                "enabled": True,
                "auth_mode": "api_key",
                "api_key": "sk-antigravity",
                "anthropic_base_url": "https://relay.example.com/v1",
                "protocols": ["anthropic_messages"],
                "supported_clis": ["pi"],
            },
            "gemini-3-pro-high",
        )


def test_pi_blocks_20260530_live_failures():
    import mms_launchers

    cases = [
        ("newapi-personal-tokyo", "mimo-v2.5[1m]"),
        ("newapi-personal-tokyo", "mimo-v2.5-pro[1m]"),
        ("us-cpa-local-codex", "gpt-5.3-codex-spark"),
        ("openrouter", "claude-opus-4-6"),
    ]
    for provider_id, model_name in cases:
        runtime = {"id": provider_id, "protocols": ["anthropic_messages", "openai_chat_completions"]}
        assert mms_launchers._pi_model_available_for_runtime(runtime, model_name) is False


def test_pi_tokyo_gemini_high_is_unblocked_after_live_smoke():
    import mms_launchers

    runtime = {"id": "newapi-personal-tokyo", "protocols": ["anthropic_messages"]}

    assert mms_launchers._pi_model_block_reason(runtime, "gemini-3-flash-agent(high)") == ""
    assert "upstream 500" in mms_launchers._pi_model_block_reason(runtime, "gemini-3.1-pro-low")


def test_pi_hints_and_profile_cover_new_qwen_flash_and_max_models(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(mms_launchers, "_pi_wrapper_path", lambda: "/tmp/pi-wrapper")
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["qwen3.6-flash", "qwen3.7-max"]},
    )

    exports = mms_launchers.get_export_env(
        "pi",
        {
            "id": "qwen-relay",
            "name": "Qwen Relay",
            "enabled": True,
            "auth_mode": "api_key",
            "api_key": "sk-qwen",
            "openai_base_url": "https://relay.example.com/v1",
            "anthropic_base_url": "https://relay.example.com/anthropic",
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["pi"],
        },
        model_info={"model": "qwen3.6-flash"},
    )

    payload = json.loads(Path(exports["MMS_PI_MODELS_JSON"]).read_text(encoding="utf-8"))
    models = []
    for provider in payload["providers"].values():
        models.extend(provider["models"])
    model_by_id = {item["id"]: item for item in models}

    assert model_by_id["qwen3.6-flash"]["contextWindow"] == 1_000_000
    assert model_by_id["qwen3.6-flash"]["maxTokens"] == 65_536
    assert model_by_id["qwen3.6-flash"]["input"] == ["text", "image"]
    assert model_by_id["qwen3.7-max"]["contextWindow"] == 1_000_000
    # The checked-in Qwen 3.7 provider profile now overrides the older builtin hint.
    assert model_by_id["qwen3.7-max"]["maxTokens"] == 131_072
    assert model_by_id["qwen3.7-max"]["input"] == ["text"]


def test_preset_export_runtime_passes_pi_model_info(monkeypatch):
    import mms_core
    import mms_launchers

    runtime = {
        "id": "relay-c",
        "name": "Relay C",
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-openai",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["pi"],
    }
    captured = {}

    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda cfg, provider_id=None: dict(runtime))
    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)

    def fake_get_export_env(cli, runtime, model_info=None):
        captured["cli"] = cli
        captured["runtime"] = dict(runtime)
        captured["model_info"] = dict(model_info or {})
        return {"PI_TELEMETRY": "0"}

    monkeypatch.setattr(mms_launchers, "get_export_env", fake_get_export_env)

    result = mms_core._resolve_preset_export_runtime(
        {"providers": [runtime]},
        {"cli": "pi", "model": "gpt-5.4", "provider": "relay-c"},
    )

    assert result is not None
    assert captured["cli"] == "pi"
    assert captured["runtime"]["id"] == "relay-c"
    assert captured["model_info"] == {"model": "gpt-5.4"}


@pytest.fixture
def isolated_policy_gateway(monkeypatch, tmp_path):
    """Exercise the real Pi gateway boundary without credentials or a model call."""
    import mms_pi_support as pi

    real_home = tmp_path / 'real-home'
    real_home.mkdir()
    gateway = tmp_path / 'isolated-gateway'
    project = tmp_path / 'project-outside-home'
    project.mkdir()
    (project / 'AGENTS.md').write_text('Project scope: preserve this local contract.\n')
    monkeypatch.chdir(project)
    monkeypatch.setattr(pi, '_real_user_path', lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(pi, '_pi_gateway_root', lambda: str(gateway))
    monkeypatch.setattr(pi, '_pi_effective_selected_model', lambda runtime, model: model)
    for name in (
        '_cleanup_stale_sessions', '_inject_real_home_hints', '_inject_host_capability_hints',
        '_inject_selected_model_name', '_set_session_home_hint',
        '_apply_runtime_network_profile', '_apply_runtime_locale_profile',
        '_apply_runtime_ip_stack_profile', '_install_session_command_wrappers',
        '_install_session_packet_env', 'apply_pi_capture_proxy',
    ):
        monkeypatch.setattr(pi, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(pi, '_write_pi_models_config', lambda agent_dir, runtime, model: (
        str(Path(agent_dir) / 'models.json'), 'synthetic-provider'))
    monkeypatch.setattr(pi, '_write_pi_settings_config', lambda agent_dir: str(Path(agent_dir) / 'settings.json'))
    monkeypatch.setattr(pi._launchers_module(), '_pi_wrapper_path', lambda: '/synthetic/pi')
    return pi, real_home, project


def _installed_pi_context_loader():
    """Discover only an existing installation; never npx/install or start Pi."""
    import shutil

    override = os.environ.get('MMS_TEST_PI_RESOURCE_LOADER')
    if override:
        assert Path(override).is_file(), 'Explicit Pi resource-loader path is missing'
        return Path(override)
    binary = shutil.which('pi')
    if binary:
        for parent in Path(binary).resolve().parents:
            loader = parent / 'dist/core/resource-loader.js'
            if loader.is_file():
                return loader
    pytest.skip('Native Pi context loader not installed; no download attempted')


def _read_native_pi_context(project, agent_dir):
    import shutil

    node = shutil.which('node')
    if not node:
        pytest.skip('Node is not installed; native Pi context probe not run')
    loader = _installed_pi_context_loader()
    script = f"""
        import {{ loadProjectContextFiles }} from {json.dumps(loader.as_uri())};
        const rows = loadProjectContextFiles({{
            cwd: process.argv[1], agentDir: process.argv[2]
        }});
        process.stdout.write(JSON.stringify(rows));
    """
    result = subprocess.run([node, '--input-type=module', '-e', script, str(project), str(agent_dir)],
                            text=True, capture_output=True, timeout=20, check=True)
    return json.loads(result.stdout)


def test_pi_isolated_gateway_loads_global_policy_and_project_context(isolated_policy_gateway):
    pi, real_home, project = isolated_policy_gateway
    global_dir = real_home / '.pi/agent'
    global_dir.mkdir(parents=True)
    policy_path = os.environ.get('MMS_TEST_GLOBAL_POLICY')
    policy = (Path(policy_path).read_text() if policy_path else
              'Global policy: preserve unrelated work; complete only the requested delivery boundary.\n')
    (global_dir / 'AGENTS.md').write_text(policy)
    # Deliberately adjacent auth/config must not be inherited by the policy loader.
    (global_dir / 'auth.json').write_text('{"synthetic_secret":"never-copy"}')
    (global_dir / 'settings.json').write_text('{"synthetic_setting":"never-copy"}')

    env = pi._pi_gateway_env({'model': 'synthetic-model'})
    isolated = Path(env['PI_CODING_AGENT_DIR'])
    assert isolated != global_dir
    rows = _read_native_pi_context(project, isolated)
    assert [(Path(row['path']).name, row['content']) for row in rows] == [
        ('AGENTS.md', policy), ('AGENTS.md', (project / 'AGENTS.md').read_text())]
    assert not (isolated / 'auth.json').exists()
    assert not (isolated / 'settings.json').exists()
    assert not (isolated / 'AGENTS.md').is_symlink()
    (isolated / 'AGENTS.md').write_text('Session-local edit\n')
    assert (global_dir / 'AGENTS.md').read_text() == policy
    pi._pi_gateway_env({'model': 'synthetic-model'})
    assert (isolated / 'AGENTS.md').read_text() == 'Session-local edit\n'


def test_pi_policy_missing_is_optional_and_global_override_wins(isolated_policy_gateway):
    pi, real_home, project = isolated_policy_gateway
    first = pi._pi_gateway_env({'model': 'synthetic-model'})
    assert not (Path(first['PI_CODING_AGENT_DIR']) / 'AGENTS.md').exists()
    global_dir = real_home / '.pi/agent'
    global_dir.mkdir(parents=True)
    (global_dir / 'AGENTS.md').write_text('Superseded global default\n')
    (global_dir / 'AGENTS.override.md').write_text('Explicit global override\n')
    second = pi._pi_gateway_env({'model': 'synthetic-model'})
    isolated = Path(second['PI_CODING_AGENT_DIR'])
    rows = _read_native_pi_context(project, isolated)
    assert rows[0]['content'] == 'Explicit global override\n'
    assert len(rows) == 2
    assert not (isolated / 'AGENTS.md').exists()


def test_pi_policy_copy_fails_explicitly_and_cannot_target_global(isolated_policy_gateway, monkeypatch):
    pi, real_home, project = isolated_policy_gateway
    global_dir = real_home / '.pi/agent'
    global_dir.mkdir(parents=True)
    source = global_dir / 'AGENTS.md'
    source.write_text('Keep this source unchanged\n')
    with pytest.raises(ValueError, match='isolated agent directory'):
        pi._pi_seed_agent_policy(global_dir)
    assert source.read_text() == 'Keep this source unchanged\n'
    original_read = Path.read_text

    def deny_policy(path, *args, **kwargs):
        if path == source:
            raise PermissionError('synthetic unreadable policy')
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', deny_policy)
    with pytest.raises(RuntimeError, match='Cannot load Pi agent policy'):
        pi._pi_gateway_env({'model': 'synthetic-model'})


def test_pi_skill_overlay_links_bundled_skills_below_every_user_root(monkeypatch, tmp_path):
    import mms_pi_support

    real_home = tmp_path / "real-home"
    user_weber = real_home / ".agents" / "skills" / "weber"
    bundled_weber = tmp_path / "bundle" / "weber"
    bundled_grill = tmp_path / "bundle" / "grill-me"
    for skill_dir in (user_weber, bundled_weber, bundled_grill):
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\ndescription: test\n---\n", encoding="utf-8")
    (tmp_path / "project" / ".git").mkdir(parents=True)
    monkeypatch.setattr(mms_pi_support, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_pi_support, "_resolve_weber_root", lambda: str(bundled_weber))
    monkeypatch.setattr(mms_pi_support, "_resolve_grill_me_root", lambda: str(bundled_grill))
    monkeypatch.setattr(mms_pi_support, "_resolve_toon_root", lambda: "")

    overlay = Path(mms_pi_support._pi_materialize_skill_overlay(tmp_path / "session", tmp_path / "project"))

    # A user's own copy replaces the bundled one; a bundled-only skill still lands in the session.
    assert (overlay / "weber").resolve() == user_weber
    assert (overlay / "grill-me").resolve() == bundled_grill
    assert not (overlay / "toon").exists()
    assert list(real_home.rglob("grill-me")) == []
