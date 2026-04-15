"""MMS broker profile support.

This path is intentionally isolated from provider/account routing so the
existing gateway and OAuth flows keep their current behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_broker_repo() -> str:
    explicit = str(os.environ.get("MMS_BROKER_REPO") or "").strip()
    if explicit:
        return os.path.expanduser(explicit)

    sibling_repo = os.path.join(os.path.dirname(_ROOT_DIR), "cc-official-broker")
    home_repo = os.path.expanduser("~/cc-official-broker")
    for candidate in (sibling_repo, home_repo):
        if os.path.exists(os.path.join(candidate, "src", "index.mjs")):
            return candidate
    return home_repo


DEFAULT_BROKER_REPO = _default_broker_repo()
PRIMARY_CREDENTIALS_PATH = os.path.expanduser("~/.config/mms/credentials.sh")
LEGACY_CREDENTIALS_PATH = os.path.expanduser("~/.config/ccs/credentials.sh")
BROKER_CACHE_DIR = os.path.expanduser("~/.config/mms/cache/broker")
_BROKER_PARENT_ENV_PREFIX_BLOCKLIST = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)


def _normalize_broker_profile_id(profile_id: str) -> str:
    value = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(profile_id or "").strip().lower()
    ).strip("-_")
    return value or "broker-profile"


def _normalize_optional_str(value: Any) -> str:
    return str(value or "").strip()


def _scrub_inherited_ai_env(env: dict[str, str]) -> dict[str, str]:
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if any(normalized.startswith(prefix) for prefix in _BROKER_PARENT_ENV_PREFIX_BLOCKLIST):
            env.pop(key, None)
    return env


@lru_cache(maxsize=2)
def _load_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return values
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line.startswith("export ") or "=" not in line:
                    continue
                key, raw_value = line[len("export "):].split("=", 1)
                key = key.strip()
                raw_value = raw_value.strip()
                if not key:
                    continue
                if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
                    raw_value = raw_value[1:-1]
                values[key] = raw_value
    except OSError:
        return {}
    return values


def _resolve_secret_value(profile: dict[str, Any], direct_key: str, env_key: str) -> str:
    return _resolve_profile_value(profile, direct_key, env_key)[0]


def _resolve_profile_value(profile: dict[str, Any], direct_key: str, env_key: str) -> tuple[str, bool]:
    env_name = _normalize_optional_str(profile.get(env_key))
    if env_name:
        if env_name in os.environ:
            return str(os.environ.get(env_name, "")).strip(), True
        for credentials_path in (PRIMARY_CREDENTIALS_PATH, LEGACY_CREDENTIALS_PATH):
            values = _load_env_file(credentials_path)
            if env_name in values:
                return str(values.get(env_name, "")).strip(), True
    if direct_key in profile:
        return _normalize_optional_str(profile.get(direct_key)), True
    return "", False


def normalize_broker_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile_id = _normalize_broker_profile_id(profile.get("id") or profile.get("name") or "broker-profile")
    runner_tools = profile.get("runner_tools", [])
    if isinstance(runner_tools, str):
        runner_tools = [chunk.strip() for chunk in runner_tools.split(",")]
    runner_tools = [str(item).strip() for item in runner_tools if str(item).strip()]

    return {
        "id": profile_id,
        "name": str(profile.get("name") or profile_id).strip() or profile_id,
        "enabled": bool(profile.get("enabled", True)),
        "broker_base_url": _normalize_optional_str(profile.get("broker_base_url")).rstrip("/"),
        "entry_mode": _normalize_optional_str(profile.get("entry_mode") or "shell") or "shell",
        "fallback_entry_mode": _normalize_optional_str(profile.get("fallback_entry_mode") or ""),
        "device_key": _normalize_optional_str(profile.get("device_key")),
        "device_key_env": _normalize_optional_str(profile.get("device_key_env")),
        "owner_user_id": _normalize_optional_str(profile.get("owner_user_id") or "default-user") or "default-user",
        "device_id": _normalize_optional_str(profile.get("device_id") or "local-device") or "local-device",
        "workspace_id": _normalize_optional_str(profile.get("workspace_id") or "default-workspace")
        or "default-workspace",
        "remote_runtime": _normalize_optional_str(profile.get("remote_runtime") or "official-claude-code")
        or "official-claude-code",
        "broker_repo_path": os.path.expanduser(
            _normalize_optional_str(profile.get("broker_repo_path") or DEFAULT_BROKER_REPO) or DEFAULT_BROKER_REPO
        ),
        "client_name": _normalize_optional_str(profile.get("client_name") or "mms") or "mms",
        "client_version": _normalize_optional_str(profile.get("client_version") or "0.1.0") or "0.1.0",
        "request_source": _normalize_optional_str(profile.get("request_source") or "multi-model-switch")
        or "multi-model-switch",
        "runner_tools": runner_tools,
        "runner_writable_scope": _normalize_optional_str(profile.get("runner_writable_scope") or "none") or "none",
        "claude_bypass_permissions": bool(profile.get("claude_bypass_permissions", False)),
        "remote_service_label": _normalize_optional_str(profile.get("remote_service_label")),
        "remote_service_base_url": _normalize_optional_str(profile.get("remote_service_base_url")).rstrip("/"),
        "remote_service_endpoint": _normalize_optional_str(profile.get("remote_service_endpoint") or "responses")
        or "responses",
        "remote_service_model": _normalize_optional_str(profile.get("remote_service_model")),
        "remote_service_bearer_token": _normalize_optional_str(profile.get("remote_service_bearer_token")),
        "remote_service_bearer_token_env": _normalize_optional_str(profile.get("remote_service_bearer_token_env")),
        "remote_service_api_key": _normalize_optional_str(profile.get("remote_service_api_key")),
        "remote_service_api_key_env": _normalize_optional_str(profile.get("remote_service_api_key_env")),
        "remote_claude_ssh_target": _normalize_optional_str(profile.get("remote_claude_ssh_target")),
        "remote_claude_ssh_target_env": _normalize_optional_str(profile.get("remote_claude_ssh_target_env")),
        "remote_claude_container_name": _normalize_optional_str(profile.get("remote_claude_container_name")),
        "remote_claude_container_name_env": _normalize_optional_str(profile.get("remote_claude_container_name_env")),
        "remote_claude_credentials_path": _normalize_optional_str(profile.get("remote_claude_credentials_path")),
        "remote_claude_credentials_path_env": _normalize_optional_str(profile.get("remote_claude_credentials_path_env")),
        "remote_claude_global_config_path": _normalize_optional_str(profile.get("remote_claude_global_config_path")),
        "remote_claude_global_config_path_env": _normalize_optional_str(profile.get("remote_claude_global_config_path_env")),
        "note": _normalize_optional_str(profile.get("note")),
    }


def ensure_broker_config(cfg: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    cfg = dict(cfg)
    raw_profiles = cfg.get("broker_profiles")
    normalized = []
    seen_ids = set()

    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            profile = normalize_broker_profile(item)
            if profile["id"] in seen_ids:
                continue
            normalized.append(profile)
            seen_ids.add(profile["id"])

    updated = dict(cfg)
    updated["broker_profiles"] = normalized
    return updated, updated != cfg


def broker_profiles_map(cfg: dict[str, Any], *, enabled_only: bool = False) -> dict[str, dict[str, Any]]:
    items = {}
    for item in cfg.get("broker_profiles", []):
        if not isinstance(item, dict):
            continue
        profile = normalize_broker_profile(item)
        if enabled_only and not profile.get("enabled", True):
            continue
        items[profile["id"]] = profile
    return items


def resolve_broker_profile(cfg: dict[str, Any], profile_id: str) -> dict[str, Any] | None:
    target = _normalize_broker_profile_id(profile_id)
    return broker_profiles_map(cfg).get(target)


def list_broker_profiles(cfg: dict[str, Any], *, enabled_only: bool = False) -> list[dict[str, Any]]:
    return list(broker_profiles_map(cfg, enabled_only=enabled_only).values())


def _broker_entry_path(profile: dict[str, Any]) -> str:
    repo_path = profile.get("broker_repo_path") or DEFAULT_BROKER_REPO
    return os.path.join(repo_path, "src", "index.mjs")


def _build_broker_env(profile: dict[str, Any], *, workspace_root: str, model_override: str = "") -> dict[str, str]:
    env = os.environ.copy()
    _scrub_inherited_ai_env(env)
    env["CC_BROKER_BASE_URL"] = profile.get("broker_base_url", "")
    env["CC_BROKER_DEVICE_KEY"] = _resolve_secret_value(profile, "device_key", "device_key_env")
    env["CC_BROKER_OWNER_USER_ID"] = profile.get("owner_user_id", "default-user")
    env["CC_BROKER_DEVICE_ID"] = profile.get("device_id", "local-device")
    env["CC_BROKER_WORKSPACE_ID"] = profile.get("workspace_id", "default-workspace")
    env["CC_BROKER_CLIENT_NAME"] = profile.get("client_name", "mms")
    env["CC_BROKER_CLIENT_VERSION"] = profile.get("client_version", "0.1.0")
    env["CC_BROKER_REQUEST_SOURCE"] = profile.get("request_source", "multi-model-switch")
    env["CC_BROKER_WORKSPACE_ROOT"] = workspace_root
    runner_tools = profile.get("runner_tools") or []
    if runner_tools:
        env["CC_BROKER_RUNNER_TOOLS"] = ",".join(runner_tools)
    env["CC_BROKER_RUNNER_WRITABLE_SCOPE"] = profile.get("runner_writable_scope", "none")
    if profile.get("claude_bypass_permissions"):
        env["CC_BROKER_CLAUDE_BYPASS_PERMISSIONS"] = "1"
    if profile.get("remote_service_label"):
        env["CC_BROKER_REMOTE_SERVICE_LABEL"] = profile.get("remote_service_label", "")
    if profile.get("remote_service_base_url"):
        env["CC_BROKER_REMOTE_SERVICE_BASE_URL"] = profile.get("remote_service_base_url", "")
    if profile.get("remote_service_endpoint"):
        env["CC_BROKER_REMOTE_SERVICE_ENDPOINT"] = profile.get("remote_service_endpoint", "")
    effective_model = _normalize_optional_str(model_override) or profile.get("remote_service_model", "")
    if effective_model:
        env["CC_BROKER_REMOTE_SERVICE_MODEL"] = effective_model

    remote_service_bearer_token = _resolve_secret_value(
        profile, "remote_service_bearer_token", "remote_service_bearer_token_env"
    )
    remote_service_api_key = _resolve_secret_value(
        profile, "remote_service_api_key", "remote_service_api_key_env"
    )
    if remote_service_bearer_token:
        env["CC_BROKER_REMOTE_SERVICE_BEARER_TOKEN"] = remote_service_bearer_token
    if remote_service_api_key:
        env["CC_BROKER_REMOTE_SERVICE_X_API_KEY"] = remote_service_api_key

    remote_claude_ssh_target, has_ssh_target = _resolve_profile_value(
        profile, "remote_claude_ssh_target", "remote_claude_ssh_target_env"
    )
    remote_claude_container_name, has_container_name = _resolve_profile_value(
        profile, "remote_claude_container_name", "remote_claude_container_name_env"
    )
    remote_claude_credentials_path, has_credentials_path = _resolve_profile_value(
        profile, "remote_claude_credentials_path", "remote_claude_credentials_path_env"
    )
    remote_claude_global_config_path, has_global_config_path = _resolve_profile_value(
        profile, "remote_claude_global_config_path", "remote_claude_global_config_path_env"
    )

    if has_ssh_target:
        env["CC_BROKER_REMOTE_CLAUDE_SSH_TARGET"] = remote_claude_ssh_target
    if has_container_name:
        env["CC_BROKER_REMOTE_CLAUDE_CONTAINER_NAME"] = remote_claude_container_name
    if has_credentials_path:
        env["CC_BROKER_REMOTE_CLAUDE_CREDENTIALS_PATH"] = remote_claude_credentials_path
    if has_global_config_path:
        env["CC_BROKER_REMOTE_CLAUDE_GLOBAL_CONFIG_PATH"] = remote_claude_global_config_path
    return env


def _is_loopback_broker_base_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _broker_healthz_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/healthz"


def _fetch_json(url: str, timeout: float = 1.5) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (OSError, URLError, TimeoutError, ValueError):
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _broker_is_healthy(base_url: str) -> bool:
    payload = _fetch_json(_broker_healthz_url(base_url))
    return bool(payload and payload.get("ok"))


def _start_broker_live_background(profile: dict[str, Any]) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 node，无法自动拉起本地 broker")

    entry_path = _broker_entry_path(profile)
    if not os.path.exists(entry_path):
        raise RuntimeError(f"未找到 broker launcher: {entry_path}")

    os.makedirs(BROKER_CACHE_DIR, exist_ok=True)
    log_path = os.path.join(BROKER_CACHE_DIR, f"{profile['id']}.log")
    log_handle = open(log_path, "ab")
    process = subprocess.Popen(
        [node, entry_path, "broker:live", profile["id"]],
        cwd=profile.get("broker_repo_path") or DEFAULT_BROKER_REPO,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    log_handle.close()
    return {
        "pid": process.pid,
        "log_path": log_path,
    }


def _ensure_local_broker_running(profile: dict[str, Any]) -> dict[str, Any]:
    base_url = profile.get("broker_base_url", "")
    if not base_url or not _is_loopback_broker_base_url(base_url):
        return {
            "started": False,
            "base_url": base_url,
            "log_path": "",
        }

    if _broker_is_healthy(base_url):
        return {
            "started": False,
            "base_url": base_url,
            "log_path": "",
        }

    started = _start_broker_live_background(profile)
    deadline = time.time() + 12
    while time.time() < deadline:
        if _broker_is_healthy(base_url):
            return {
                "started": True,
                "base_url": base_url,
                "pid": started["pid"],
                "log_path": started["log_path"],
            }
        time.sleep(0.4)

    raise RuntimeError(
        f"本地 broker 没能在预期时间内起来: {base_url}；可查看日志 {started['log_path']}"
    )


def _probe_official_doctor(profile: dict[str, Any], *, workspace_root: str, model_override: str = "") -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"ok": False, "error": "未找到 node"}

    entry_path = _broker_entry_path(profile)
    if not os.path.exists(entry_path):
        return {"ok": False, "error": f"未找到 broker launcher: {entry_path}"}

    env = _build_broker_env(profile, workspace_root=workspace_root, model_override=model_override)
    result = subprocess.run(
        [node, entry_path, "official:doctor"],
        env=env,
        cwd=workspace_root,
        capture_output=True,
        text=True,
    )

    raw = (result.stdout or result.stderr or "").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    if isinstance(payload, dict):
        payload.setdefault("ok", result.returncode == 0)
        return payload

    return {
        "ok": result.returncode == 0,
        "raw": raw,
    }


def _run_broker_json_command(
    profile: dict[str, Any],
    command: str,
    *,
    workspace_root: str,
    model_override: str = "",
) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"ok": False, "error": "未找到 node"}

    entry_path = _broker_entry_path(profile)
    if not os.path.exists(entry_path):
        return {"ok": False, "error": f"未找到 broker launcher: {entry_path}"}

    env = _build_broker_env(profile, workspace_root=workspace_root, model_override=model_override)
    result = subprocess.run(
        [node, entry_path, command],
        env=env,
        cwd=workspace_root,
        capture_output=True,
        text=True,
    )

    raw = (result.stdout or result.stderr or "").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": raw or f"{command} returned non-json output"}

    if isinstance(payload, dict):
        payload.setdefault("ok", result.returncode == 0)
        return payload

    return {"ok": result.returncode == 0, "raw": raw}


def _load_official_proxy_history(
    profile: dict[str, Any],
    *,
    workspace_root: str,
    model_override: str = "",
) -> list[dict[str, Any]]:
    payload = _run_broker_json_command(
        profile,
        "session:history",
        workspace_root=workspace_root,
        model_override=model_override,
    )
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, list):
        return []
    return [item for item in sessions if isinstance(item, dict) and _normalize_optional_str(item.get("session_id"))]


def _summarize_history_item(item: dict[str, Any]) -> str:
    session_id = _normalize_optional_str(item.get("session_id")) or "-"
    remote_session_id = _normalize_optional_str(item.get("remote_session_id")) or "-"
    updated_at = _normalize_optional_str(item.get("updated_at"))
    short_time = updated_at.replace("T", " ").replace("Z", "")[:16] if updated_at else "-"
    return f"{short_time} | local={session_id} | remote={remote_session_id}"


def _default_launch_mode_for_model_override(model_override: str) -> str:
    return "new" if _normalize_optional_str(model_override) else "resume_last"


def _resolve_profile_launch_mode_interactive(
    profile: dict[str, Any],
    *,
    workspace_root: str,
    model_override: str = "",
) -> tuple[str, str]:
    default_mode = _default_launch_mode_for_model_override(model_override)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return default_mode, ""

    history = _load_official_proxy_history(
        profile,
        workspace_root=workspace_root,
        model_override=model_override,
    )
    if not history:
        return "new", ""

    if default_mode == "new":
        print(
            "[broker] 当前显式选择了模型；为避免续到旧模型会话，默认新开。回车/2 新开，输入 1 续最近，输入 3 切换旧会话。",
            flush=True,
        )
    else:
        print(
            "[broker] 当前项目检测到历史会话；直接回车续最近，输入 2 新开，输入 3 切换旧会话。",
            flush=True,
        )
    while True:
        raw = input(f"选择 [1/2/3] (默认 {'2' if default_mode == 'new' else '1'}): ").strip()
        if raw == "":
            return default_mode, ""
        if raw == "1":
            return "resume_last", ""
        if raw == "2":
            return "new", ""
        if raw == "3":
            print("可切换的历史会话：", flush=True)
            for index, item in enumerate(history, 1):
                print(f"  {index}. {_summarize_history_item(item)}", flush=True)
            while True:
                picked = input(
                    f"输入编号，直接回车取消并{'新开' if default_mode == 'new' else '续最近'}: "
                ).strip()
                if not picked:
                    return default_mode, ""
                if picked.isdigit():
                    pos = int(picked)
                    if 1 <= pos <= len(history):
                        return "resume", _normalize_optional_str(history[pos - 1].get("session_id"))
                print("请输入有效编号。", flush=True)
        print("请输入 1、2 或 3。", flush=True)


def _resolve_entry_command(
    profile: dict[str, Any],
    *,
    workspace_root: str,
    model_override: str = "",
) -> tuple[str, str]:
    entry_mode = _normalize_optional_str(profile.get("entry_mode") or "shell").lower()
    fallback_entry_mode = _normalize_optional_str(profile.get("fallback_entry_mode") or "").lower()

    if entry_mode not in {"official_attach", "official_connect", "official_proxy"}:
        return "mms:run", entry_mode

    if entry_mode == "official_proxy":
        return "official:proxy", entry_mode

    doctor = _probe_official_doctor(profile, workspace_root=workspace_root, model_override=model_override)
    direct_connect = doctor.get("direct_connect") if isinstance(doctor, dict) else {}
    local_auth = doctor.get("local_auth") if isinstance(doctor, dict) else {}
    remote_auth = doctor.get("remote_auth") if isinstance(doctor, dict) else {}
    current_direction = doctor.get("current_direction") if isinstance(doctor, dict) else {}
    supported = bool(isinstance(direct_connect, dict) and direct_connect.get("supported"))
    logged_in = bool(isinstance(local_auth, dict) and local_auth.get("logged_in"))
    remote_auth_ready = bool(isinstance(remote_auth, dict) and remote_auth.get("available"))
    recommended_entry = (
        _normalize_optional_str(current_direction.get("recommended_entry"))
        if isinstance(current_direction, dict)
        else ""
    )

    if supported and (logged_in or remote_auth_ready):
        return "official:connect", entry_mode

    if recommended_entry == "official:proxy":
        print(
            "[broker] official_connect 当前不可用，自动改走 official_proxy。",
            flush=True,
        )
        return "official:proxy", "official_proxy"

    if fallback_entry_mode == "shell":
        version = ""
        local_claude = doctor.get("local_claude") if isinstance(doctor, dict) else {}
        if isinstance(local_claude, dict):
            version = _normalize_optional_str(local_claude.get("version"))
        reason = ""
        if isinstance(direct_connect, dict):
            reason = _normalize_optional_str(direct_connect.get("reason"))
        if supported and not logged_in and not remote_auth_ready:
            auth_method = ""
            if isinstance(local_auth, dict):
                auth_method = _normalize_optional_str(local_auth.get("auth_method"))
            remote_reason = ""
            if isinstance(remote_auth, dict):
                remote_reason = _normalize_optional_str(remote_auth.get("reason"))
            message = "本机 Claude Code 尚未登录，且远端 claude auth bundle 也不可用"
            if remote_reason:
                message = f"{message}（remote_auth={remote_reason}）"
            if auth_method and auth_method != "unknown":
                message = f"{message}（当前 auth_method={auth_method}）"
        else:
            message = reason or "当前本机 Claude Code 还不支持 direct-connect"
        if version:
            print(f"[broker] official entry 暂不可用，回退到 shell：{version} | {message}", flush=True)
        else:
            print(f"[broker] official entry 暂不可用，回退到 shell：{message}", flush=True)
        return "mms:run", fallback_entry_mode

    raise RuntimeError(
        "当前 profile 配置为 official_connect，但本机 Claude Code 还不支持 direct-connect；"
        "请升级 Claude Code，或给 profile 增加 fallback_entry_mode = \"shell\""
    )


def _run_with_shell_fallback(
    cmd: list[str],
    *,
    env: dict[str, str],
    workspace_root: str,
    requested_entry_mode: str,
    effective_entry_mode: str,
    fallback_entry_mode: str,
) -> int:
    result = subprocess.run(cmd, env=env, cwd=workspace_root)
    if result.returncode == 0:
        return 0

    if requested_entry_mode not in {"official_connect", "official_proxy"}:
        return result.returncode

    if effective_entry_mode not in {"official_connect", "official_proxy"}:
        return result.returncode

    if fallback_entry_mode != "shell":
        return result.returncode

    print(
        "[broker] official entry 退出，自动回退到 broker shell。",
        flush=True,
    )
    fallback_cmd = [cmd[0], cmd[1], "mms:run"]
    return subprocess.run(fallback_cmd, env=env, cwd=workspace_root).returncode


def _print_profile_table(cfg: dict[str, Any]) -> None:
    profiles = list(broker_profiles_map(cfg).values())
    if not profiles:
        print("当前未配置 broker_profiles")
        print('示例：在 config.toml 里添加 [[broker_profiles]]，然后运行 "mms broker run <id>"')
        return

    print("Broker Profiles:")
    for item in profiles:
        status = "enabled" if item.get("enabled", True) else "disabled"
        print(
            f"- {item['id']} | {item['name']} | {status} | "
            f"{item['device_id']}/{item['workspace_id']} | {item['broker_base_url'] or '-'}"
        )


def _show_profile(cfg: dict[str, Any], profile_id: str) -> int:
    profile = resolve_broker_profile(cfg, profile_id)
    if profile is None:
        print(f"未找到 broker profile: {profile_id}", file=sys.stderr)
        return 1

    fields = [
        ("id", profile["id"]),
        ("name", profile["name"]),
        ("enabled", "true" if profile.get("enabled", True) else "false"),
        ("broker_base_url", profile.get("broker_base_url") or "-"),
        ("entry_mode", profile.get("entry_mode") or "shell"),
        ("fallback_entry_mode", profile.get("fallback_entry_mode") or "-"),
        ("device_key_source", profile.get("device_key_env") or "inline"),
        ("owner_user_id", profile.get("owner_user_id") or "-"),
        ("device_id", profile.get("device_id") or "-"),
        ("workspace_id", profile.get("workspace_id") or "-"),
        ("remote_runtime", profile.get("remote_runtime") or "-"),
        ("remote_service_label", profile.get("remote_service_label") or "-"),
        ("remote_service_base_url", profile.get("remote_service_base_url") or "-"),
        ("remote_service_endpoint", profile.get("remote_service_endpoint") or "-"),
        ("remote_service_model", profile.get("remote_service_model") or "-"),
        ("remote_service_auth", profile.get("remote_service_bearer_token_env") or profile.get("remote_service_api_key_env") or "inline/none"),
        ("remote_claude_ssh_target_source", profile.get("remote_claude_ssh_target_env") or "inline/none"),
        ("remote_claude_container_name_source", profile.get("remote_claude_container_name_env") or "inline/none"),
        ("remote_claude_credentials_path_source", profile.get("remote_claude_credentials_path_env") or "inline/none"),
        ("remote_claude_global_config_path_source", profile.get("remote_claude_global_config_path_env") or "inline/none"),
        ("broker_repo_path", profile.get("broker_repo_path") or "-"),
        ("runner_tools", ", ".join(profile.get("runner_tools") or []) or "-"),
        ("runner_writable_scope", profile.get("runner_writable_scope") or "-"),
        ("claude_bypass_permissions", "true" if profile.get("claude_bypass_permissions") else "false"),
    ]
    for key, value in fields:
        print(f"{key}: {value}")
    return 0


def _run_profile(
    cfg: dict[str, Any],
    profile_id: str,
    *,
    session_id: str = "",
    resume: bool = False,
    resume_last: bool = False,
    new_session: bool = False,
    model_override: str = "",
) -> int:
    profile = resolve_broker_profile(cfg, profile_id)
    if profile is None:
        print(f"未找到 broker profile: {profile_id}", file=sys.stderr)
        return 1
    if not profile.get("enabled", True):
        print(f"broker profile 已禁用: {profile['id']}", file=sys.stderr)
        return 1
    if not profile.get("broker_base_url"):
        print(f"broker profile 缺少 broker_base_url: {profile['id']}", file=sys.stderr)
        return 1
    if not _resolve_secret_value(profile, "device_key", "device_key_env"):
        print(f"broker profile 缺少 device_key: {profile['id']}", file=sys.stderr)
        return 1

    node = shutil.which("node")
    if not node:
        print("未找到 node，无法启动 cc-official-broker", file=sys.stderr)
        return 1

    entry_path = _broker_entry_path(profile)
    if not os.path.exists(entry_path):
        print(f"未找到 broker launcher: {entry_path}", file=sys.stderr)
        return 1

    workspace_root = os.getcwd()
    broker_boot = _ensure_local_broker_running(profile)
    env = _build_broker_env(profile, workspace_root=workspace_root, model_override=model_override)
    entry_command, effective_entry_mode = _resolve_entry_command(
        profile,
        workspace_root=workspace_root,
        model_override=model_override,
    )
    requested_entry_mode = _normalize_optional_str(profile.get("entry_mode") or "shell").lower()
    fallback_entry_mode = _normalize_optional_str(profile.get("fallback_entry_mode") or "").lower()
    cmd = [node, entry_path, entry_command]
    if resume_last and session_id:
        print("--resume-last 不能和 --session 同时使用", file=sys.stderr)
        return 1
    if resume and resume_last:
        print("--resume 和 --resume-last 只能二选一", file=sys.stderr)
        return 1
    if new_session and (resume or resume_last or session_id):
        print("--new 不能和 --session / --resume / --resume-last 同时使用", file=sys.stderr)
        return 1

    if entry_command == "mms:run":
        if resume_last:
            cmd.append("resume-last")
        elif session_id:
            cmd.append(session_id)
        if resume:
            if not session_id:
                print("--resume 需要配合 --session 使用", file=sys.stderr)
                return 1
            if len(cmd) == 2:
                cmd.append(session_id)
            cmd.append("resume")
    elif entry_command == "official:proxy":
        if resume_last:
            cmd.append("--continue")
        elif resume:
            if not session_id:
                print("--resume 需要配合 --session 使用", file=sys.stderr)
                return 1
            cmd.extend(["--resume", session_id])
        elif session_id:
            cmd.extend(["--resume", session_id])
    elif resume or resume_last or session_id:
        print(
            "entry_mode=official_attach/official_connect/official_proxy 时会忽略 --session / --resume / --resume-last",
            flush=True,
        )

    return _run_with_shell_fallback(
        cmd,
        env=env,
        workspace_root=workspace_root,
        requested_entry_mode=requested_entry_mode,
        effective_entry_mode=effective_entry_mode,
        fallback_entry_mode=fallback_entry_mode,
    )


def _run_official_smoke(cfg: dict[str, Any], profile_id: str, *, prompt: str = "") -> int:
    profile = resolve_broker_profile(cfg, profile_id)
    if profile is None:
        print(f"未找到 broker profile: {profile_id}", file=sys.stderr)
        return 1
    if not profile.get("enabled", True):
        print(f"broker profile 已禁用: {profile['id']}", file=sys.stderr)
        return 1
    if not profile.get("broker_base_url"):
        print(f"broker profile 缺少 broker_base_url: {profile['id']}", file=sys.stderr)
        return 1
    if not _resolve_secret_value(profile, "device_key", "device_key_env"):
        print(f"broker profile 缺少 device_key: {profile['id']}", file=sys.stderr)
        return 1

    node = shutil.which("node")
    if not node:
        print("未找到 node，无法启动 cc-official-broker", file=sys.stderr)
        return 1

    entry_path = _broker_entry_path(profile)
    if not os.path.exists(entry_path):
        print(f"未找到 broker launcher: {entry_path}", file=sys.stderr)
        return 1

    workspace_root = os.getcwd()
    env = _build_broker_env(profile, workspace_root=workspace_root)
    cmd = [node, entry_path, "official:attach"]
    if prompt.strip():
        cmd.append(prompt.strip())

    print(
        f"MMS broker smoke {profile['id']} "
        f"({profile['device_id']}/{profile['workspace_id']}) -> {profile['broker_base_url']}",
        flush=True,
    )
    print(f"workspace: {workspace_root}", flush=True)
    return subprocess.run(cmd, env=env, cwd=workspace_root).returncode


def run_broker_profile(
    cfg: dict[str, Any],
    profile_id: str,
    *,
    session_id: str = "",
    resume: bool = False,
    resume_last: bool = False,
    new_session: bool = False,
    model_override: str = "",
) -> int:
    return _run_profile(
        cfg,
        profile_id,
        session_id=session_id,
        resume=resume,
        resume_last=resume_last,
        new_session=new_session,
        model_override=model_override,
    )


def run_broker_profile_interactive(
    cfg: dict[str, Any],
    profile_id: str,
    *,
    model_override: str = "",
) -> int:
    profile = resolve_broker_profile(cfg, profile_id)
    if profile is None:
        print(f"未找到 broker profile: {profile_id}", file=sys.stderr)
        return 1

    workspace_root = os.getcwd()
    entry_command, _effective_entry_mode = _resolve_entry_command(
        profile,
        workspace_root=workspace_root,
        model_override=model_override,
    )
    if entry_command not in {"mms:run", "official:proxy"}:
        return run_broker_profile(
            cfg,
            profile_id,
            model_override=model_override,
        )

    launch_mode, selected_session_id = _resolve_profile_launch_mode_interactive(
        profile,
        workspace_root=workspace_root,
        model_override=model_override,
    )
    return run_broker_profile(
        cfg,
        profile_id,
        session_id=selected_session_id,
        resume=launch_mode == "resume",
        resume_last=launch_mode == "resume_last",
        new_session=launch_mode == "new",
        model_override=model_override,
    )


def handle_broker_command(cfg: dict[str, Any], argv: list[str], *, command_name: str = "mms") -> int:
    parser = argparse.ArgumentParser(
        prog=f"{command_name} broker",
        description="MMS broker profile management and launch entry",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("ls", help="列出 broker profiles")

    show_parser = subparsers.add_parser("show", help="查看单个 broker profile")
    show_parser.add_argument("profile_id")

    run_parser = subparsers.add_parser("run", help="启动 broker profile")
    run_parser.add_argument("profile_id")
    run_parser.add_argument("--session", default="", help="显式指定 session id")
    run_parser.add_argument("--resume", action="store_true", help="恢复指定 session id")
    run_parser.add_argument("--resume-last", action="store_true", help="恢复当前项目最近一次本地记住的 session")
    run_parser.add_argument("--new", action="store_true", help="明确新开一条 broker 会话")
    run_parser.add_argument("--pick", action="store_true", help="交互选择续最近 / 新开 / 切换旧会话")

    smoke_parser = subparsers.add_parser("smoke", help="跑一条 official child attach smoke test")
    smoke_parser.add_argument("profile_id")
    smoke_parser.add_argument(
        "--prompt",
        default="",
        help="覆盖默认 smoke prompt"
    )

    args = parser.parse_args(argv)

    if args.subcommand in {None, "ls"}:
        _print_profile_table(cfg)
        return 0
    if args.subcommand == "show":
        return _show_profile(cfg, args.profile_id)
    if args.subcommand == "run":
        if args.pick:
            return run_broker_profile_interactive(
                cfg,
                args.profile_id,
            )
        return run_broker_profile(
            cfg,
            args.profile_id,
            session_id=args.session,
            resume=bool(args.resume),
            resume_last=bool(args.resume_last),
            new_session=bool(args.new),
        )
    if args.subcommand == "smoke":
        return _run_official_smoke(cfg, args.profile_id, prompt=args.prompt)

    parser.print_help()
    return 1
