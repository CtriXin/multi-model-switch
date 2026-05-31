"""Session MCP root discovery and plugin MCP helpers."""

from __future__ import annotations

import copy
import json
import os


def _launchers():
    import mms_launchers as _module

    return _module


def resolve_hive_root(module_path=None):
    launchers = _launchers()
    candidates = []
    explicit = str(os.environ.get("MMS_HIVE_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    install_home = str(os.environ.get("HIVE_HOME") or "").strip()
    if install_home:
        candidates.append(os.path.abspath(os.path.expanduser(install_home)))

    module_dir = os.path.dirname(os.path.abspath(module_path or launchers.__file__))
    local_candidates = [
        os.path.join(os.path.dirname(module_dir), "hive"),
        launchers._real_user_path("auto-skills", "CtriXin-repo", "hive"),
        launchers._real_user_path("auto-skills", "hive"),
        launchers._real_user_path("hive"),
    ]
    installed_candidates = [
        launchers._real_user_path(".hive-orchestrator"),
        launchers._real_user_path(".local", "share", "hive"),
    ]
    if launchers._is_installed_mms_layout(module_path=module_path):
        candidates.extend(installed_candidates)
        candidates.extend(local_candidates)
    else:
        candidates.extend(local_candidates)
        candidates.extend(installed_candidates)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "bin", "mcp-server.sh")):
            return candidate
    return ""


def default_hive_session_mcp_server():
    hive_root = _launchers()._resolve_hive_root()
    if hive_root:
        hive_command = os.path.join(hive_root, "bin", "mcp-server.sh")
        return {
            "args": [],
            "command": hive_command,
            "env": {"HOME": _launchers()._real_user_home()},
            "type": "stdio",
        }
    return None


def resolve_pilot_root(module_path=None):
    launchers = _launchers()
    candidates = []
    explicit = str(os.environ.get("MMS_PILOT_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))

    module_dir = os.path.dirname(os.path.abspath(module_path or launchers.__file__))
    auto_skills_root = os.path.dirname(os.path.dirname(module_dir))
    local_candidates = [
        os.path.join(auto_skills_root, "shared-skills", "pilot"),
        launchers._real_user_path("auto-skills", "shared-skills", "pilot"),
        os.path.join(os.path.dirname(module_dir), "pilot"),
    ]
    installed_candidates = [
        launchers._real_user_path(".local", "share", "pilot"),
    ]
    if launchers._is_installed_mms_layout(module_path=module_path):
        candidates.extend(installed_candidates)
        candidates.extend(local_candidates)
    else:
        candidates.extend(local_candidates)
        candidates.extend(installed_candidates)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "scripts", "pilot_mcp_server.py")):
            return candidate
    return ""


def default_pilot_session_mcp_server():
    pilot_root = _launchers()._resolve_pilot_root()
    if pilot_root:
        return {
            "command": "python3",
            "args": [os.path.join(pilot_root, "scripts", "pilot_mcp_server.py")],
            "env": {"HOME": _launchers()._real_user_home()},
            "type": "stdio",
        }
    return None


def replace_plugin_root_tokens(value, plugin_root):
    if isinstance(value, str):
        return value.replace("${CLAUDE_PLUGIN_ROOT}", plugin_root).replace("$CLAUDE_PLUGIN_ROOT", plugin_root)
    if isinstance(value, list):
        return [_launchers()._replace_plugin_root_tokens(item, plugin_root) for item in value]
    if isinstance(value, dict):
        return {
            key: _launchers()._replace_plugin_root_tokens(child, plugin_root)
            for key, child in value.items()
        }
    return value


def load_plugin_mcp_servers(plugin_root):
    plugin_root = str(plugin_root or "").strip()
    if not plugin_root:
        return {}
    mcp_path = os.path.join(plugin_root, ".mcp.json")
    if not os.path.isfile(mcp_path):
        return {}
    try:
        with open(mcp_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    servers = payload.get("mcpServers") if isinstance(payload, dict) else {}
    if not isinstance(servers, dict):
        return {}
    normalized = {}
    for name, spec in servers.items():
        key = str(name or "").strip()
        if not key or not isinstance(spec, dict):
            continue
        normalized[key] = _launchers()._replace_plugin_root_tokens(copy.deepcopy(spec), plugin_root)
    return normalized
