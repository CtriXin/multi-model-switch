"""Read-only global plugin inventory helpers for launcher session setup."""

from __future__ import annotations

import os
import re
from typing import Any, Callable


JsonLoader = Callable[[str], dict[str, Any]]
PathUnder = Callable[[str, str], bool]


def installed_claude_plugin_paths(
    *,
    real_user_path: Callable[..., str],
    load_json_dict_unlocked: JsonLoader,
    path_under: PathUnder,
) -> list[str]:
    plugins_root = real_user_path(".claude", "plugins")
    installed_path = os.path.join(plugins_root, "installed_plugins.json")
    loaded = load_json_dict_unlocked(installed_path)
    plugins = loaded.get("plugins") if isinstance(loaded, dict) else {}
    if not isinstance(plugins, dict):
        return []

    resolved_paths = []
    seen = set()
    for records in plugins.values():
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            install_path = os.path.abspath(
                os.path.expanduser(str(record.get("installPath") or "").strip())
            )
            if not install_path or install_path in seen:
                continue
            if not os.path.isdir(install_path):
                continue
            if not path_under(install_path, plugins_root):
                continue
            seen.add(install_path)
            resolved_paths.append(install_path)
    return resolved_paths


def installed_claude_plugin_mcp_manifest_paths(
    install_path: str,
    *,
    load_json_dict_unlocked: JsonLoader,
    path_under: PathUnder,
) -> list[str]:
    install_root = os.path.abspath(os.path.expanduser(str(install_path or "").strip()))
    if not install_root:
        return []

    candidates = []
    metadata_paths = (
        os.path.join(install_root, ".cursor-plugin", "plugin.json"),
        os.path.join(install_root, ".claude-plugin", "plugin.json"),
    )
    for metadata_path in metadata_paths:
        metadata = load_json_dict_unlocked(metadata_path)
        manifest_rel = metadata.get("mcpServers")
        if not isinstance(manifest_rel, str) or not manifest_rel.strip():
            continue
        manifest_path = os.path.abspath(os.path.join(install_root, manifest_rel.strip()))
        if path_under(manifest_path, install_root):
            candidates.append(manifest_path)

    candidates.append(os.path.join(install_root, ".mcp.json"))

    manifests = []
    seen = set()
    for candidate in candidates:
        normalized = os.path.abspath(os.path.expanduser(str(candidate or "").strip()))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            manifests.append(normalized)
    return manifests


def installed_claude_plugin_mcp_servers(
    *,
    installed_claude_plugin_paths: Callable[[], list[str]],
    installed_claude_plugin_mcp_manifest_paths: Callable[[str], list[str]],
    load_json_dict_unlocked: JsonLoader,
    mcp_server_spec_has_entrypoint: Callable[[Any], bool],
    copy_deepcopy: Callable[[Any], Any],
) -> dict[str, Any]:
    servers = {}
    for install_path in installed_claude_plugin_paths():
        for manifest_path in installed_claude_plugin_mcp_manifest_paths(install_path):
            payload = load_json_dict_unlocked(manifest_path)
            plugin_servers = payload.get("mcpServers") if isinstance(payload, dict) else {}
            if not isinstance(plugin_servers, dict):
                continue
            for name, spec in plugin_servers.items():
                key = str(name or "").strip()
                if not key or key in servers or not mcp_server_spec_has_entrypoint(spec):
                    continue
                servers[key] = copy_deepcopy(spec)
    return servers


def enabled_real_codex_plugin_names(
    *,
    real_user_path: Callable[..., str],
    decode_toml_basic_key: Callable[[str], str],
) -> set[str]:
    config_path = real_user_path(".codex", "config.toml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return set()

    header_pattern = re.compile(
        r'^\[plugins\."((?:\\.|[^"\\])*)"\]\s*$',
        flags=re.MULTILINE,
    )
    matches = list(header_pattern.finditer(text))
    enabled = set()
    for index, match in enumerate(matches):
        plugin_id = decode_toml_basic_key(match.group(1))
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[block_start:block_end]
        enabled_match = re.search(
            r'^\s*enabled\s*=\s*(true|false)\s*$',
            block,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if not enabled_match or enabled_match.group(1).lower() != "true":
            continue
        plugin_name = str(plugin_id or "").split("@", 1)[0].strip().lower()
        if plugin_name:
            enabled.add(plugin_name)
    return enabled


__all__ = [
    "installed_claude_plugin_paths",
    "installed_claude_plugin_mcp_manifest_paths",
    "installed_claude_plugin_mcp_servers",
    "enabled_real_codex_plugin_names",
]
