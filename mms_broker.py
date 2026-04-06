"""MMS broker profile support.

This path is intentionally isolated from provider/account routing so the
existing gateway and OAuth flows keep their current behavior.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_BROKER_REPO = os.path.expanduser("~/auto-skills/CtriXin-repo/cc-official-broker")


def _normalize_broker_profile_id(profile_id: str) -> str:
    value = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(profile_id or "").strip().lower()
    ).strip("-_")
    return value or "broker-profile"


def _normalize_optional_str(value: Any) -> str:
    return str(value or "").strip()


def _resolve_secret_value(profile: dict[str, Any], direct_key: str, env_key: str) -> str:
    env_name = _normalize_optional_str(profile.get(env_key))
    if env_name:
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value.strip()
    return _normalize_optional_str(profile.get(direct_key))


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
        "device_key": _normalize_optional_str(profile.get("device_key")),
        "device_key_env": _normalize_optional_str(profile.get("device_key_env")),
        "owner_user_id": _normalize_optional_str(profile.get("owner_user_id") or "xin") or "xin",
        "device_id": _normalize_optional_str(profile.get("device_id") or "mac") or "mac",
        "workspace_id": _normalize_optional_str(profile.get("workspace_id") or "personal") or "personal",
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
        "remote_service_label": _normalize_optional_str(profile.get("remote_service_label")),
        "remote_service_base_url": _normalize_optional_str(profile.get("remote_service_base_url")).rstrip("/"),
        "remote_service_endpoint": _normalize_optional_str(profile.get("remote_service_endpoint") or "responses")
        or "responses",
        "remote_service_model": _normalize_optional_str(profile.get("remote_service_model")),
        "remote_service_bearer_token": _normalize_optional_str(profile.get("remote_service_bearer_token")),
        "remote_service_bearer_token_env": _normalize_optional_str(profile.get("remote_service_bearer_token_env")),
        "remote_service_api_key": _normalize_optional_str(profile.get("remote_service_api_key")),
        "remote_service_api_key_env": _normalize_optional_str(profile.get("remote_service_api_key_env")),
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
    env["CC_BROKER_BASE_URL"] = profile.get("broker_base_url", "")
    env["CC_BROKER_DEVICE_KEY"] = _resolve_secret_value(profile, "device_key", "device_key_env")
    env["CC_BROKER_OWNER_USER_ID"] = profile.get("owner_user_id", "xin")
    env["CC_BROKER_DEVICE_ID"] = profile.get("device_id", "mac")
    env["CC_BROKER_WORKSPACE_ID"] = profile.get("workspace_id", "personal")
    env["CC_BROKER_CLIENT_NAME"] = profile.get("client_name", "mms")
    env["CC_BROKER_CLIENT_VERSION"] = profile.get("client_version", "0.1.0")
    env["CC_BROKER_REQUEST_SOURCE"] = profile.get("request_source", "multi-model-switch")
    env["CC_BROKER_WORKSPACE_ROOT"] = workspace_root
    runner_tools = profile.get("runner_tools") or []
    if runner_tools:
        env["CC_BROKER_RUNNER_TOOLS"] = ",".join(runner_tools)
    env["CC_BROKER_RUNNER_WRITABLE_SCOPE"] = profile.get("runner_writable_scope", "none")
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
    return env


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
        ("broker_repo_path", profile.get("broker_repo_path") or "-"),
        ("runner_tools", ", ".join(profile.get("runner_tools") or []) or "-"),
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
    env = _build_broker_env(profile, workspace_root=workspace_root, model_override=model_override)
    entry_mode = _normalize_optional_str(profile.get("entry_mode") or "shell").lower()
    entry_command = "official:connect" if entry_mode in {"official_attach", "official_connect"} else "mms:run"
    cmd = [node, entry_path, entry_command]
    if resume_last and session_id:
        print("--resume-last 不能和 --session 同时使用", file=sys.stderr)
        return 1
    if resume and resume_last:
        print("--resume 和 --resume-last 只能二选一", file=sys.stderr)
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
    elif resume or resume_last or session_id:
        print("entry_mode=official_attach/official_connect 时会忽略 --session / --resume / --resume-last", flush=True)

    print(
        f"启动 broker profile {profile['id']} "
        f"({profile['device_id']}/{profile['workspace_id']}) -> {profile['broker_base_url']}",
        flush=True,
    )
    print(f"entry_mode: {entry_mode}", flush=True)
    if profile.get("remote_service_base_url"):
        remote_service_name = profile.get("remote_service_label") or profile.get("remote_service_base_url")
        remote_service_model = _normalize_optional_str(model_override) or profile.get("remote_service_model") or "-"
        print(
            f"remote service: {remote_service_name} [{profile.get('remote_service_endpoint', 'responses')}] model={remote_service_model}",
            flush=True,
        )
    print(f"workspace: {workspace_root}", flush=True)
    return subprocess.run(cmd, env=env, cwd=workspace_root).returncode


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
    model_override: str = "",
) -> int:
    return _run_profile(
        cfg,
        profile_id,
        session_id=session_id,
        resume=resume,
        resume_last=resume_last,
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
        return run_broker_profile(
            cfg,
            args.profile_id,
            session_id=args.session,
            resume=bool(args.resume),
            resume_last=bool(args.resume_last),
        )
    if args.subcommand == "smoke":
        return _run_official_smoke(cfg, args.profile_id, prompt=args.prompt)

    parser.print_help()
    return 1
