from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


HOST_CONTEXT_VERSION = 1
HOST_CONTEXT_DIR = ".mms/context"
HOST_CONTEXT_JSON_NAME = "host-context.json"
DEFAULT_WEB_ACCESS_PROXY = "http://127.0.0.1:3456"
DEFAULT_CHROME_DEBUG_PORT = 9222


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _real_path(home: str, *parts: str) -> str:
    return str(Path(home).joinpath(*parts))


def default_config_path(real_home: str | os.PathLike[str]) -> str:
    return _real_path(str(real_home), ".config", "mms", "ops-env-safe.toml")


def load_host_capability_config(
    *,
    real_home: str | os.PathLike[str],
    config_path: str | os.PathLike[str] | None = None,
) -> tuple[dict[str, Any], str, bool]:
    path = _clean(config_path) or _clean(os.environ.get("MMS_OPS_ENV_SAFE_CONFIG")) or default_config_path(real_home)
    if not path or not os.path.isfile(path) or tomllib is None:
        return {}, path, False
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
        return data if isinstance(data, dict) else {}, path, True
    except Exception:
        return {}, path, False


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def _config_text(data: dict[str, Any], table_name: str, key: str, default: str = "") -> str:
    table = _table(data, table_name)
    return _clean(table.get(key)) or default


def _config_int(data: dict[str, Any], table_name: str, key: str, default: int) -> int:
    raw = _config_text(data, table_name, key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_paths(real_home: str) -> dict[str, str]:
    return {
        "shared_bin": _real_path(real_home, ".local", "bin"),
        "codex_home": _real_path(real_home, ".codex"),
        "codex_skills": _real_path(real_home, ".codex", "skills"),
        "claude_home": _real_path(real_home, ".claude"),
        "claude_skills": _real_path(real_home, ".claude", "skills"),
        "gh_config": _real_path(real_home, ".config", "gh"),
        "npm_npx_cache": _real_path(real_home, ".npm", "_npx"),
        "playwright_browsers": _real_path(real_home, "Library", "Caches", "ms-playwright"),
        "chrome_profile_root": _real_path(real_home, "Library", "Application Support", "Google", "Chrome"),
    }


def _default_purposes() -> dict[str, str]:
    return {
        "shared_bin": "stable user bin",
        "codex_home": "Codex config root",
        "codex_skills": "Codex skills root",
        "claude_home": "Claude config root",
        "claude_skills": "Claude skills root",
        "gh_config": "GitHub CLI config/auth path hint",
        "npm_npx_cache": "shared npm npx cache",
        "playwright_browsers": "shared Playwright browser cache",
        "chrome_profile_root": "Chrome profile root path hint",
    }


def _merge_paths(real_home: str, config: dict[str, Any]) -> list[dict[str, str]]:
    paths = _default_paths(real_home)
    for key, value in _table(config, "paths").items():
        text = _clean(value)
        if text:
            paths[str(key)] = text
    purposes = _default_purposes()
    for key, value in _table(config, "purposes").items():
        text = _clean(value)
        if text:
            purposes[str(key)] = text
    return [
        {"name": name, "path": paths[name], "purpose": purposes.get(name, "")}
        for name in sorted(paths)
        if paths[name]
    ]


def _find_repo_root(cwd: str) -> str:
    current = Path(cwd).expanduser().resolve()
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return str(parent)
    return str(current)


def _configured_tools(config: dict[str, Any]) -> dict[str, Any]:
    tools = _table(config, "tools")
    result: dict[str, Any] = {}
    for name, payload in tools.items():
        if isinstance(payload, dict):
            result[str(name).replace("_", "-")] = dict(payload)
    return result


def _tool_rows(tool_bins: dict[str, Any] | None, config: dict[str, Any]) -> list[dict[str, Any]]:
    merged = _configured_tools(config)
    if isinstance(tool_bins, dict):
        for name, payload in tool_bins.items():
            if isinstance(payload, dict) and isinstance(merged.get(str(name)), dict):
                merged[str(name)] = {**merged[str(name)], **payload}
            else:
                merged[str(name)] = payload
    if not merged:
        return []
    rows: list[dict[str, Any]] = []
    for name in sorted(merged):
        payload = merged.get(name)
        if isinstance(payload, str):
            payload = {"bin": payload}
        if not isinstance(payload, dict):
            continue
        row = {
            "name": str(name),
            "mode": _clean(payload.get("mode")) or "host-wrapper",
            "requires_auth": bool(payload.get("requires_auth")),
        }
        for key in ("bin", "wrapper"):
            value = _clean(payload.get(key))
            if value:
                row[key] = value
        if "bin" in row or "wrapper" in row:
            rows.append(row)
    return rows


def build_host_context(
    *,
    real_home: str | os.PathLike[str],
    session_home: str | os.PathLike[str] | None = None,
    cli: str = "",
    model: str = "",
    cwd: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
    tool_bins: dict[str, Any] | None = None,
) -> dict[str, Any]:
    real_home_text = str(Path(real_home).expanduser())
    cwd_text = str(Path(cwd or os.getcwd()).expanduser().resolve())
    config, resolved_config_path, config_exists = load_host_capability_config(
        real_home=real_home_text,
        config_path=config_path,
    )
    check_deps_default = _real_path(real_home_text, ".codex", "skills", "web-access", "scripts", "check-deps.mjs")
    extension_id = (
        _config_text(config, "web_access", "extension_id")
        or _clean(os.environ.get("MMS_CHROME_EXTENSION_ID"))
        or _clean(os.environ.get("WEB_ACCESS_EXTENSION_ID"))
    )
    proxy_url = (
        _config_text(config, "web_access", "proxy_url")
        or _clean(os.environ.get("MMS_WEB_ACCESS_PROXY"))
        or _clean(os.environ.get("MMS_WEB_ACCESS_PROXY_URL"))
        or DEFAULT_WEB_ACCESS_PROXY
    )
    return {
        "version": HOST_CONTEXT_VERSION,
        "generated_at": _utc_now(),
        "session": {
            "cli": _clean(cli),
            "cwd": cwd_text,
            "repo_root": _find_repo_root(cwd_text),
            "model": _clean(model),
            "session_home": _clean(session_home),
        },
        "host": {
            "home": real_home_text,
            "mode": _clean(config.get("mode")) or "path-only",
            "config_path": resolved_config_path,
            "config_exists": config_exists,
        },
        "web_access": {
            "proxy_url": proxy_url,
            "chrome_debug_port": _config_int(config, "web_access", "chrome_debug_port", DEFAULT_CHROME_DEBUG_PORT),
            "extension_id": extension_id,
            "check_deps": _config_text(config, "web_access", "check_deps", check_deps_default),
        },
        "paths": _merge_paths(real_home_text, config),
        "tools": _tool_rows(tool_bins, config),
        "boundaries": {
            "path_only": True,
            "never_export_home": True,
            "never_export_xdg": True,
            "never_export_tokens": True,
            "logged_in_browser_requires_web_access": True,
        },
    }


def _write_json_secure(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def env_from_host_context(context: dict[str, Any], *, context_path: str = "") -> dict[str, str]:
    web_access = context.get("web_access") if isinstance(context.get("web_access"), dict) else {}
    host = context.get("host") if isinstance(context.get("host"), dict) else {}
    env = {
        "WEB_ACCESS_HOST_HOME": _clean(host.get("home")),
        "HOST_HOME": _clean(host.get("home")),
        "MMS_OPS_ENV_SAFE_CONFIG": _clean(host.get("config_path")),
        "MMS_WEB_ACCESS_PROXY": _clean(web_access.get("proxy_url")),
        "MMS_WEB_ACCESS_PROXY_URL": _clean(web_access.get("proxy_url")),
        "MMS_CHROME_DEBUG_PORT": _clean(web_access.get("chrome_debug_port")),
        "MMS_WEB_ACCESS_CHECK_DEPS": _clean(web_access.get("check_deps")),
    }
    extension_id = _clean(web_access.get("extension_id"))
    if extension_id:
        env["MMS_CHROME_EXTENSION_ID"] = extension_id
        env["WEB_ACCESS_EXTENSION_ID"] = extension_id
    if context_path:
        env["MMS_HOST_CONTEXT_JSON"] = context_path
        env["MMS_HOST_CAPABILITIES_JSON"] = context_path
        env["MMS_HOST_CONTEXT_FORMAT"] = "json"
    return {key: value for key, value in env.items() if value}


def host_capability_env(
    *,
    real_home: str | os.PathLike[str],
    config_path: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    context = build_host_context(real_home=real_home, config_path=config_path)
    return env_from_host_context(context)


def write_host_context(
    session_home: str | os.PathLike[str],
    *,
    real_home: str | os.PathLike[str],
    cli: str = "",
    model: str = "",
    cwd: str | os.PathLike[str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
    tool_bins: dict[str, Any] | None = None,
) -> dict[str, str]:
    context = build_host_context(
        real_home=real_home,
        session_home=session_home,
        cli=cli,
        model=model,
        cwd=cwd,
        config_path=config_path,
        tool_bins=tool_bins,
    )
    json_path = Path(session_home).expanduser() / HOST_CONTEXT_DIR / HOST_CONTEXT_JSON_NAME
    _write_json_secure(json_path, context)
    return env_from_host_context(context, context_path=str(json_path))


def resolve_tool_bins(names: list[str] | tuple[str, ...], *, path: str = "") -> dict[str, dict[str, Any]]:
    search_path = path or os.environ.get("PATH", "") or os.defpath
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        tool = _clean(name)
        if not tool:
            continue
        bin_path = shutil.which(tool, path=search_path) or ""
        result[tool] = {
            "bin": bin_path,
            "mode": "host-wrapper",
            "requires_auth": tool in {"gh", "lark-cli", "rh"},
        }
    return result
