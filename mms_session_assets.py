"""Read-only session asset inventory for MMS WebUI.

This module intentionally does not write preferences or real CLI config.  It
turns the existing launch-confirm preview catalog into a user-facing inventory
so WebUI can explain which skills, MCP servers, and hooks are global/inherited
versus MMS session-managed.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tomllib
from typing import Any


CLI_ORDER = ("claude", "codex", "opencode", "agy")
SURFACE_KINDS = ("skills", "mcp", "hooks")
PACK_SCOPES = ("always", "caveman", "nsr", "ecc", "omc")

_CLI_LABELS = {
    "claude": "Claude",
    "codex": "Codex",
    "opencode": "OpenCode",
    "agy": "Antigravity",
}

_MMS_MANAGED_NAMES = {
    "agent-browser",
    "auto-github-contributor",
    "caveman",
    "ecc",
    "hive",
    "nsr",
    "omc",
    "pilot",
    "rtk opencode plugin",
    "toon",
    "token-saver",
    "web-access",
    "weber",
    "xmem",
    "xmem opencode plugin",
}

_KIND_LABELS = {
    "skills": "技能",
    "mcp": "MCP 服务",
    "hooks": "自动钩子",
}

_ASSET_SUMMARIES = {
    "agent-browser": "轻量浏览器自动化，适合不需要登录态的页面检查、截图和本地 WebUI 验证。",
    "auto-github-contributor": "GitHub 贡献辅助能力，安装后才会出现；默认不改用户全局配置。",
    "caveman": "低 token 沟通模式，适合长会话压缩表达；只有启用 Caveman 时才生效。",
    "ecc": "Claude 工程工作流能力包，包含规则、命令和质量检查；适合更重的工程约束。",
    "hive": "多 agent 执行/评审入口，适合把复杂任务拆分给 worker。",
    "nsr": "长任务 continuation 钩子，降低目标中断；默认不挂 startup/prompt 噪音钩子。",
    "omc": "Claude 编排能力包，包含 team / verify loop 等更主动的工作流。",
    "pilot": "规划和执行包生成入口，适合先拆任务、再交给其它执行器。",
    "rtk opencode plugin": "OpenCode 的 token 节省插件，自动压缩或改写高噪音命令输出。",
    "toon": "把结构化 JSON、状态包和 handoff 压成更省 token 的格式。",
    "token-saver": "长日志、大 diff、重复状态的省 token 工具；多数时候由 agent 自动使用。",
    "web-access": "联网和登录态浏览能力，适合搜索、网页读取、公司后台或需要真实 Chrome 的任务。",
    "weber": "网页任务路由器：帮 agent 判断该用本地 WebUI、登录态浏览器还是轻量抓取。",
    "xmem": "跨项目记忆和事实索引能力；适合找历史决策、路径、部署和 bug 线索。",
    "xmem opencode plugin": "OpenCode 会话启动/结束时轻量同步 xmem，不把知识正文硬塞进上下文。",
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _load_mms_core() -> Any | None:
    try:
        import mms_core  # type: ignore

        return mms_core
    except Exception:
        return None


def _real_home(mms_core: Any | None) -> str:
    if mms_core is not None and hasattr(mms_core, "resolve_real_user_home"):
        try:
            return os.path.abspath(mms_core.resolve_real_user_home())
        except Exception:
            pass
    return os.path.expanduser("~")


def _repo_root() -> str:
    return os.path.abspath(os.path.dirname(__file__))


def _abbrev_path(path: str, *, home: str) -> str:
    path = _safe_text(path)
    if not path:
        return ""
    if "://" in path:
        return path
    expanded = os.path.abspath(os.path.expanduser(path.replace("~", home, 1) if path == "~" or path.startswith("~/") else path))
    try:
        if os.path.commonpath([expanded, home]) == home:
            rel = os.path.relpath(expanded, home)
            return "~" if rel == "." else os.path.join("~", rel)
    except ValueError:
        pass
    root = _repo_root()
    try:
        if os.path.commonpath([expanded, root]) == root:
            return f".{os.sep}{os.path.relpath(expanded, root)}"
    except ValueError:
        pass
    return path


def _detail_value(details: list[Any], *labels: str) -> str:
    wanted = {label.lower() for label in labels}
    for item in details:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        label = _safe_text(item[0]).lower()
        if label in wanted:
            return _safe_text(item[1])
    return ""


def _normalize_details(details: Any, *, home: str) -> list[dict[str, str]]:
    normalized = []
    for item in details or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        label = _safe_text(item[0])
        value = _safe_text(item[1])
        if not label or not value:
            continue
        normalized.append({"label": label, "value": value, "display": _abbrev_path(value, home=home) if label.lower() in {"path", "路径"} else value})
    return normalized


def _expand_path(path: str, *, home: str) -> str:
    path = _safe_text(path)
    if not path:
        return ""
    if path == "~" or path.startswith("~/"):
        path = path.replace("~", home, 1)
    return os.path.abspath(os.path.expanduser(path))


def _skill_description(path: str, *, home: str) -> str:
    path = _expand_path(path, home=home)
    if os.path.isdir(path):
        path = os.path.join(path, "SKILL.md")
    if not path.endswith("SKILL.md") or not os.path.isfile(path):
        return ""
    try:
        text = open(path, "r", encoding="utf-8").read(4096)
    except OSError:
        return ""
    lines = text.splitlines()
    in_description = False
    collected = []
    for line in lines[:80]:
        stripped = line.strip()
        if stripped.startswith("description:"):
            value = stripped.split(":", 1)[1].strip().strip('"')
            if value:
                return value[:240]
            in_description = True
            continue
        if in_description:
            if not stripped:
                continue
            if not line.startswith((" ", "\t", "-")):
                break
            cleaned = stripped.lstrip("- ").strip().strip('"')
            if cleaned:
                collected.append(cleaned)
            if len(" ".join(collected)) > 240:
                break
    return " ".join(collected)[:240]


def _classify_origin(kind: str, scope: str, title: str, details: list[Any], *, home: str) -> dict[str, str]:
    title_key = _safe_text(title).lower()
    path = _detail_value(details, "Path", "路径", "URL")
    command = _detail_value(details, "Command", "命令")
    haystack = " ".join([title_key, path.lower(), command.lower()])
    expanded_path = _expand_path(path, home=home) if path and "://" not in path else path
    repo = _repo_root().lower()
    home_lower = home.lower()

    if scope in {"caveman", "nsr", "ecc", "omc"}:
        return {"group": "mms_dynamic", "origin": "MMS optional pack"}
    if title_key in _MMS_MANAGED_NAMES:
        return {"group": "mms_dynamic", "origin": "MMS managed"}
    if kind == "skills":
        return {"group": "mms_dynamic", "origin": "MMS session skill"}
    if "/.mms/" in haystack or "/multi-model-switch/" in haystack or "/vendor/" in haystack:
        return {"group": "mms_dynamic", "origin": "MMS managed path"}
    if expanded_path and expanded_path.lower().startswith(repo):
        return {"group": "mms_dynamic", "origin": "Repo managed"}
    if home_lower and expanded_path and expanded_path.lower().startswith(home_lower):
        if any(token in haystack for token in ("/.claude", "/.codex", "/.config/opencode", "/.agents")):
            return {"group": "global", "origin": "Global CLI config"}
        return {"group": "global", "origin": "User installed path"}
    if "url ·" in haystack or "sse" in haystack:
        return {"group": "global", "origin": "Inherited MCP"}
    return {"group": "other", "origin": "Detected at launch"}


def _scope_label(scope: str) -> str:
    mapping = {
        "always": "默认可见",
        "caveman": "Caveman 开启时",
        "nsr": "NSR 开启时",
        "ecc": "ECC pack 开启时",
        "omc": "OMC pack 开启时",
    }
    return mapping.get(scope, scope)


def _origin_label(origin: str) -> str:
    mapping = {
        "MMS optional pack": "MMS 可选能力包",
        "MMS managed": "MMS 动态注入",
        "MMS session skill": "MMS 会话技能",
        "MMS managed path": "MMS 托管路径",
        "Repo managed": "当前仓库托管",
        "Global CLI config": "全局 CLI 配置",
        "User installed path": "用户安装路径",
        "Inherited MCP": "继承的 MCP",
        "Detected at launch": "启动时检测到",
    }
    return mapping.get(origin, origin or "未知来源")


def _group_label(group: str) -> str:
    mapping = {
        "mms_dynamic": "MMS 动态注入",
        "global": "全局继承",
        "other": "其它检测项",
    }
    return mapping.get(group, group or "其它")


def _asset_summary(kind: str, title: str, summary: str) -> str:
    key = _safe_text(title).lower()
    if key in _ASSET_SUMMARIES:
        return _ASSET_SUMMARIES[key]
    if summary and any("\u4e00" <= ch <= "\u9fff" for ch in summary):
        return summary
    fallback = {
        "skills": "会话内可调用的能力。具体触发方式由 agent 根据任务判断，技术路径在详情里。",
        "mcp": "给当前 CLI 注入的工具服务。通常由 agent 调用，普通用户只需要知道用途和来源。",
        "hooks": "会在特定时机自动运行的钩子。建议谨慎开启，先看触发时机和来源。",
    }
    return fallback.get(kind, "启动预览检测到的能力项。")


def _flatten_catalog(cli: str, catalog: dict[str, Any], *, home: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allow_execution_surfaces = bool(catalog.get("allow_execution_surfaces", True))
    for kind in SURFACE_KINDS:
        panel = catalog.get(kind) if isinstance(catalog.get(kind), dict) else {}
        for scope in PACK_SCOPES:
            entries = panel.get(scope) if isinstance(panel, dict) else []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                title = _safe_text(entry.get("title"))
                if not title:
                    continue
                raw_details = entry.get("details") if isinstance(entry.get("details"), list) else []
                origin = _classify_origin(kind, scope, title, raw_details, home=home)
                path = _detail_value(raw_details, "Path", "路径")
                summary = _safe_text(entry.get("summary"))
                skill_desc = _skill_description(path, home=home) if kind == "skills" else ""
                if skill_desc and (not summary or summary in {"会话技能", "Session skill"}):
                    summary = skill_desc
                rows.append(
                    {
                        "cli": cli,
                        "cli_label": _CLI_LABELS.get(cli, cli),
                        "kind": kind,
                        "kind_label": _KIND_LABELS.get(kind, kind),
                        "scope": scope,
                        "scope_label": _scope_label(scope),
                        "title": title,
                        "summary": _asset_summary(kind, title, summary),
                        "technical_summary": summary,
                        "details": _normalize_details(raw_details, home=home),
                        "disable_key": _safe_text(entry.get("disable_key") or title),
                        "group": origin["group"],
                        "group_label": _group_label(origin["group"]),
                        "origin": origin["origin"],
                        "origin_label": _origin_label(origin["origin"]),
                        "active_by_default": scope == "always" and allow_execution_surfaces,
                    }
                )
    return rows


def _call_bool(mms_core: Any | None, name: str, *args: Any) -> bool:
    if mms_core is None or not hasattr(mms_core, name):
        return False
    try:
        return bool(getattr(mms_core, name)(*args))
    except Exception:
        return False


def _preview_for_cli(mms_core: Any | None, cli: str, runtime: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bool]]:
    has_caveman = _call_bool(mms_core, "_caveman_available_for_cli", cli)
    has_nsr = _call_bool(mms_core, "_nsr_available_for_cli", cli)
    has_ecc = cli == "claude" and _call_bool(mms_core, "_ecc_available_for_claude")
    has_omc = cli == "claude" and _call_bool(mms_core, "_omc_available_for_claude")
    flags = {"caveman": has_caveman, "nsr": has_nsr, "ecc": has_ecc, "omc": has_omc}
    if mms_core is None or not hasattr(mms_core, "_build_confirm_preview_catalog"):
        return {"allow_execution_surfaces": True, "mcp": {}, "skills": {}, "hooks": {}}, flags
    try:
        catalog = mms_core._build_confirm_preview_catalog(
            cli,
            runtime,
            has_caveman=has_caveman,
            has_nsr=has_nsr,
            has_ecc=has_ecc,
            has_omc=has_omc,
        )
    except Exception:
        catalog = {"allow_execution_surfaces": True, "mcp": {}, "skills": {}, "hooks": {}}
    return catalog if isinstance(catalog, dict) else {}, flags


def _load_preferences(mms_core: Any | None) -> dict[str, Any]:
    if mms_core is None or not hasattr(mms_core, "load_user_preferences"):
        return {}
    try:
        prefs = mms_core.load_user_preferences()
        return prefs if isinstance(prefs, dict) else {}
    except Exception:
        return {}


def _global_roots(home: str) -> list[dict[str, Any]]:
    candidates = [
        ("Claude 全局技能目录", "~/.claude/skills", False),
        ("Codex 全局技能目录", "~/.codex/skills", False),
        ("共享 agent 技能目录", "~/.agents/skills", False),
        ("Codex bundled plugin 技能缓存", "~/.codex/plugins/cache/openai-bundled", True),
        ("Codex runtime plugin 技能缓存", "~/.codex/plugins/cache/openai-primary-runtime", True),
        ("Claude MCP 旧配置文件", "~/.claude.json", False),
        ("Codex 配置文件", "~/.codex/config.toml", False),
        ("Codex hooks 文件", "~/.codex/hooks.json", False),
        ("OpenCode 配置目录", "~/.config/opencode", False),
    ]
    rows = []
    for label, raw_path, recursive in candidates:
        expanded = _expand_path(raw_path, home=home)
        exists = os.path.exists(expanded)
        skill_count = 0
        if os.path.isdir(expanded):
            skill_count = len(_skill_dir_entries(raw_path, home=home, recursive=recursive))
        rows.append(
            {
                "label": label,
                "path": raw_path,
                "exists": exists,
                "skill_count": skill_count,
                "note": "只读展示；WebUI 不自动修改全局 CLI 配置。",
            }
        )
    return rows


def _asset_root_kind(path: str, *, home: str) -> str:
    expanded = _expand_path(path, home=home)
    package_root = _repo_root()
    checks = [
        (package_root, "MMS 当前包内"),
        (os.path.join(home, "auto-skills", "installed-skills"), "安装/管理镜像"),
        (os.path.join(home, "auto-skills", "shared-skills"), "共享 skill"),
        (os.path.join(home, "auto-skills", "vendor"), "用户 vendor"),
        (os.path.join(home, ".agents", "skills"), "共享 agent skills"),
        (os.path.join(home, ".codex", "skills"), "Codex 全局 skills"),
    ]
    for root, label in checks:
        try:
            if os.path.commonpath([expanded, os.path.abspath(root)]) == os.path.abspath(root):
                return label
        except (OSError, ValueError):
            continue
    try:
        if os.path.commonpath([expanded, home]) == home:
            return "用户目录"
    except ValueError:
        pass
    return "外部路径"


def _asset_root_skill_count(path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    count = 1 if os.path.isfile(os.path.join(path, "SKILL.md")) else 0
    for child in ("skills", os.path.join(".claude", "skills"), os.path.join(".agents", "skills")):
        root = os.path.join(path, child)
        if not os.path.isdir(root):
            continue
        try:
            count += sum(1 for name in os.listdir(root) if os.path.isfile(os.path.join(root, name, "SKILL.md")))
        except OSError:
            pass
    return count


def _managed_roots(home: str) -> list[dict[str, Any]]:
    try:
        import mms_launchers  # type: ignore
    except Exception:
        return []
    mms_core = _load_mms_core()
    install = _managed_install_contract(home, mms_core)
    install_root = _safe_text(install.get("real_root"))
    install_surface = {"Skill": "skills", "能力包": "packs", "MCP": "mcp"}
    specs = [
        ("web-access", "Skill", "_resolve_web_access_root"),
        ("weber", "Skill", "_resolve_weber_root"),
        ("agent-browser", "Skill", "_resolve_agent_browser_root"),
        ("toon", "Skill", "_resolve_toon_root"),
        ("token-saver", "Skill", "_resolve_token_saver_root"),
        ("xmem", "Skill", "_resolve_xmem_root"),
        ("auto-github-contributor", "Skill", "_resolve_auto_github_contributor_root"),
        ("caveman", "能力包", "_resolve_caveman_root"),
        ("nsr", "能力包", "_resolve_nsr_root"),
        ("ecc", "能力包", "_resolve_ecc_root"),
        ("omc", "能力包", "_resolve_omc_root"),
        ("hive", "MCP", "_resolve_hive_root"),
        ("pilot", "MCP", "_resolve_pilot_root"),
    ]
    rows = []
    for name, surface, resolver_name in specs:
        resolver = getattr(mms_launchers, resolver_name, None)
        if not callable(resolver):
            continue
        try:
            path = _safe_text(resolver())
        except Exception:
            path = ""
        if not path:
            continue
        install_dir = ""
        install_dir_real = ""
        if install_root:
            install_dir_real = os.path.join(install_root, install_surface.get(surface, "packages"), name)
            install_dir = _abbrev_path(install_dir_real, home=home)
        rows.append(
            {
                "name": name,
                "surface": surface,
                "path": _abbrev_path(path, home=home),
                "real_path": os.path.abspath(os.path.expanduser(path)),
                "exists": os.path.exists(path),
                "root_kind": _asset_root_kind(path, home=home),
                "install_path": install_dir,
                "install_real_path": install_dir_real,
                "install_exists": bool(install_dir_real and os.path.exists(install_dir_real)),
                "skill_count": _asset_root_skill_count(path),
                "note": "实际加载位置；固定安装版优先读取 MMS managed assets root，找不到才回退到开发版/vendor/历史路径。",
            }
        )
    return rows


def _managed_install_contract(home: str, mms_core: Any | None = None) -> dict[str, Any]:
    root = ""
    enabled = True
    if mms_core is not None:
        try:
            enabled = bool(mms_core.managed_assets_enabled())
        except Exception:
            enabled = True
        try:
            root = _safe_text(mms_core.managed_assets_root())
        except Exception:
            root = ""
    if not root:
        root = os.path.join(home, ".local", "share", "mms", "assets")
    real_root = os.path.abspath(os.path.expanduser(root))

    def child(name: str) -> dict[str, Any]:
        real = os.path.join(real_root, name)
        return {
            "name": name,
            "path": _abbrev_path(real, home=home),
            "real_path": real,
            "exists": os.path.isdir(real),
        }

    return {
        "enabled": enabled,
        "root": _abbrev_path(real_root, home=home),
        "real_root": real_root,
        "exists": os.path.isdir(real_root),
        "children": [child(name) for name in ("skills", "mcp", "packs", "hooks", "packages")],
        "layout": {
            "skills": "skills/<skill-name>/SKILL.md",
            "mcp": "mcp/<mcp-name>/...",
            "packs": "packs/<pack-name>/...",
            "hooks": "hooks/<hook-name>/...",
            "packages": "packages/<asset-name>/... 作为兼容兜底",
        },
        "note": "这是 MMS 固定 managed assets 安装根；建议用 symlink 指向真实包，launcher 会优先读取这里。",
    }


def _disabled_defaults(prefs: dict[str, Any]) -> dict[str, list[str]]:
    disabled = (((prefs.get("session_surfaces") or {}).get("disabled") or {}) if isinstance(prefs, dict) else {})
    result: dict[str, list[str]] = {}
    for name in SURFACE_KINDS:
        values = disabled.get(name) if isinstance(disabled, dict) else []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple, set)):
            values = []
        cleaned = []
        seen = set()
        for item in values:
            text = _safe_text(item)
            if not text or text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
        result[name] = cleaned
    return result


def _preference_snippet(prefs: dict[str, Any]) -> str:
    disabled = _disabled_defaults(prefs)

    def _list(name: str) -> str:
        values = disabled.get(name) or []
        return "[" + ", ".join(f'"{_safe_text(item)}"' for item in values if _safe_text(item)) + "]"

    defaults = ((prefs.get("launch") or {}).get("defaults") or {}) if isinstance(prefs, dict) else {}
    assets = (prefs.get("assets") or {}) if isinstance(prefs, dict) else {}
    mms_core = _load_mms_core()
    install = _managed_install_contract(_real_home(mms_core), mms_core)
    caveman = _safe_text(defaults.get("caveman_mode") or "enable")
    nsr = _safe_text(defaults.get("nsr_mode") or "enable")
    agent_pack = _safe_text(defaults.get("agent_pack") or "none")
    bypass = defaults.get("bypass")
    bypass_text = "true" if bypass is not False else "false"
    managed_enabled = assets.get("managed_enabled")
    managed_enabled_text = "false" if managed_enabled is False else "true"
    managed_root = _safe_text(assets.get("managed_root") or install.get("real_root") or "~/.local/share/mms/assets")
    return "\n".join(
        [
            "[launch.defaults]",
            f'caveman_mode = "{caveman}"',
            f'nsr_mode = "{nsr}"',
            f'agent_pack = "{agent_pack}"',
            f"bypass = {bypass_text}",
            "",
            "[session_surfaces.disabled]",
            f"skills = {_list('skills')}",
            f"mcp = {_list('mcp')}",
            f"hooks = {_list('hooks')}",
            "",
            "[assets]",
            f"managed_enabled = {managed_enabled_text}",
            f'managed_root = "{managed_root}"',
        ]
    )


def _skill_dir_items(raw_path: str, *, home: str, limit: int = 8) -> tuple[int, list[str]]:
    entries = _skill_dir_entries(raw_path, home=home, recursive=False)
    return len(entries), [entry["name"] for entry in entries[:limit]]


def _skill_dir_entries(raw_path: str, *, home: str, recursive: bool = False) -> list[dict[str, str]]:
    expanded = _expand_path(raw_path, home=home)
    if not os.path.isdir(expanded):
        return []
    entries: list[dict[str, str]] = []
    try:
        if recursive:
            for root, dirs, files in os.walk(expanded, followlinks=False):
                dirs[:] = sorted(dirs)
                if "SKILL.md" not in files:
                    continue
                rel = os.path.relpath(root, expanded)
                name = os.path.basename(root) if rel == "." else rel
                entries.append({"name": name, "path": os.path.join(root, "SKILL.md")})
        else:
            for name in sorted(os.listdir(expanded)):
                skill_md = os.path.join(expanded, name, "SKILL.md")
                if os.path.isfile(skill_md):
                    entries.append({"name": name, "path": skill_md})
    except OSError:
        return []
    return entries


def _global_skill_root_specs(cli: str) -> list[dict[str, Any]]:
    if cli == "claude":
        return [
            {"path": "~/.claude/skills", "label": "Claude 全局技能", "origin": "Global Claude skill", "recursive": False, "disable_supported": True},
            {"path": "~/.agents/skills", "label": "共享 agent 技能（宿主级）", "origin": "Shared agent skill", "recursive": False, "disable_supported": False},
        ]
    if cli == "codex":
        return [
            {"path": "~/.codex/skills", "label": "Codex 全局技能", "origin": "Global Codex skill", "recursive": False, "disable_supported": True},
            {"path": "~/.agents/skills", "label": "共享 agent 技能（宿主级）", "origin": "Shared agent skill", "recursive": False, "disable_supported": False},
            {"path": "~/.codex/plugins/cache/openai-bundled", "label": "Codex bundled plugin 技能", "origin": "Codex plugin skill", "recursive": True, "disable_supported": False},
            {"path": "~/.codex/plugins/cache/openai-primary-runtime", "label": "Codex runtime plugin 技能", "origin": "Codex plugin skill", "recursive": True, "disable_supported": False},
        ]
    return []


def _global_skill_inventory_rows(cli: str, *, home: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in _global_skill_root_specs(cli):
        raw_path = str(spec.get("path") or "")
        root_label = str(spec.get("label") or "全局技能")
        entries = _skill_dir_entries(raw_path, home=home, recursive=bool(spec.get("recursive")))
        for entry in entries:
            name = _safe_text(entry.get("name"))
            path = _safe_text(entry.get("path"))
            if not name or not path:
                continue
            rows.append(
                {
                    "cli": cli,
                    "cli_label": _CLI_LABELS.get(cli, cli),
                    "kind": "skills",
                    "kind_label": _KIND_LABELS["skills"],
                    "scope": "global",
                    "scope_label": "全局继承",
                    "title": os.path.basename(name),
                    "summary": _skill_description(path, home=home) or "来自真实用户全局目录的 skill；WebUI 只读展示它是否会被当前 CLI 继承。",
                    "technical_summary": f"{root_label}: {name}",
                    "details": [
                        {"label": "路径", "value": path, "display": _abbrev_path(path, home=home)},
                        {"label": "全局根", "value": raw_path, "display": raw_path},
                        {"label": "来源", "value": root_label, "display": root_label},
                    ],
                    "disable_key": f"{cli}:{os.path.basename(name)}" if spec.get("disable_supported") else os.path.basename(name),
                    "group": "global",
                    "group_label": _group_label("global"),
                    "origin": str(spec.get("origin") or "Global CLI config"),
                    "origin_label": root_label,
                    "active_by_default": True,
                    "inventory_only": True,
                    "disable_supported": bool(spec.get("disable_supported")),
                }
            )
    return rows


def _load_json_dict(path: str, *, home: str) -> dict[str, Any]:
    expanded = _expand_path(path, home=home)
    try:
        with open(expanded, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _claude_json_mcp_names(home: str) -> list[str]:
    payload = _load_json_dict("~/.claude.json", home=home)
    servers = payload.get("mcpServers") if isinstance(payload.get("mcpServers"), dict) else {}
    return sorted(str(name) for name in servers if _safe_text(name))


def _codex_config_mcp_names(home: str) -> list[str]:
    path = _expand_path("~/.codex/config.toml", home=home)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            payload = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        payload = {}
    names = []
    servers = payload.get("mcp_servers") if isinstance(payload, dict) else {}
    if isinstance(servers, dict):
        names.extend(str(name) for name in servers if _safe_text(name))
    if names:
        return sorted(set(names))
    try:
        text = open(path, "r", encoding="utf-8").read(256_000)
    except OSError:
        return []
    pattern = re.compile(r'^\[mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_-]+))(?:\.[^\]]+)?\]\s*$', re.MULTILINE)
    return sorted({match.group(1) or match.group(2) for match in pattern.finditer(text) if match.group(1) or match.group(2)})


def _codex_hook_names(home: str, limit: int = 8) -> tuple[int, list[str]]:
    payload = _load_json_dict("~/.codex/hooks.json", home=home)
    names: list[str] = []
    hooks = payload.get("hooks") if isinstance(payload.get("hooks"), dict) else payload
    if isinstance(hooks, dict):
        for event_name, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for hook in group.get("hooks") or []:
                    if not isinstance(hook, dict):
                        continue
                    command = _safe_text(hook.get("command"))
                    if not command:
                        continue
                    try:
                        parts = shlex.split(command)
                    except ValueError:
                        parts = command.split()
                    target = parts[-1] if parts else command
                    names.append(f"{event_name}:{os.path.basename(target)}")
    return len(names), names[:limit]


def _append_global_source(
    sources: list[dict[str, Any]],
    *,
    surface: str,
    label: str,
    path: str,
    count: int,
    items: list[str] | None = None,
    note: str = "",
    home: str,
) -> None:
    exists = os.path.exists(_expand_path(path, home=home))
    sources.append(
        {
            "surface": surface,
            "surface_label": _KIND_LABELS.get(surface, surface),
            "label": label,
            "path": path,
            "exists": exists,
            "count": max(0, int(count or 0)),
            "items": list(items or []),
            "note": note or "只读展示；WebUI 不自动修改全局配置。",
        }
    )


def _global_sources_for_cli(cli: str, cli_rows: list[dict[str, Any]], *, home: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    preview_global = [row for row in cli_rows if row.get("group") == "global" and not row.get("inventory_only")]
    for kind in SURFACE_KINDS:
        items = sorted({str(row.get("title") or "") for row in preview_global if row.get("kind") == kind and row.get("title")})
        if items:
            _append_global_source(
                sources,
                surface=kind,
                label="启动预览检测到的全局条目",
                path="TUI launch preview",
                count=len(items),
                items=items[:8],
                note="来自 TUI bypass/确认页同一 preview catalog。",
                home=home,
            )

    if cli == "claude":
        for spec in _global_skill_root_specs(cli):
            raw_path = str(spec.get("path") or "")
            label = str(spec.get("label") or "全局技能")
            entries = _skill_dir_entries(raw_path, home=home, recursive=bool(spec.get("recursive")))
            count, items = len(entries), [entry["name"] for entry in entries[:8]]
            _append_global_source(sources, surface="skills", label=label, path=raw_path, count=count, items=items, home=home)
        mcp_names = _claude_json_mcp_names(home)
        _append_global_source(sources, surface="mcp", label="Claude 全局 MCP", path="~/.claude.json", count=len(mcp_names), items=mcp_names[:8], home=home)
    elif cli == "codex":
        for spec in _global_skill_root_specs(cli):
            raw_path = str(spec.get("path") or "")
            label = str(spec.get("label") or "全局技能")
            entries = _skill_dir_entries(raw_path, home=home, recursive=bool(spec.get("recursive")))
            count, items = len(entries), [entry["name"] for entry in entries[:8]]
            _append_global_source(sources, surface="skills", label=label, path=raw_path, count=count, items=items, home=home)
        claude_mcp_names = _claude_json_mcp_names(home)
        _append_global_source(
            sources,
            surface="mcp",
            label="Codex 继承的 Claude MCP",
            path="~/.claude.json",
            count=len(claude_mcp_names),
            items=claude_mcp_names[:8],
            note="MMS Codex session 会把 Claude 风格 MCP 转成 Codex mcp_servers。",
            home=home,
        )
        codex_mcp_names = _codex_config_mcp_names(home)
        _append_global_source(sources, surface="mcp", label="Codex 全局 MCP", path="~/.codex/config.toml", count=len(codex_mcp_names), items=codex_mcp_names[:8], home=home)
        hook_count, hook_names = _codex_hook_names(home)
        _append_global_source(sources, surface="hooks", label="Codex 全局 hooks", path="~/.codex/hooks.json", count=hook_count, items=hook_names, home=home)
    elif cli == "opencode":
        count, items = _skill_dir_items("~/.agents/skills", home=home)
        _append_global_source(sources, surface="skills", label="共享 agent 技能", path="~/.agents/skills", count=count, items=items, home=home)
        _append_global_source(sources, surface="mcp", label="OpenCode 配置目录", path="~/.config/opencode", count=0, items=[], note="OpenCode 全局配置只读展示；session-local opencode.json 由 launcher 生成。", home=home)
    elif cli == "agy":
        count, items = _skill_dir_items("~/.agents/skills", home=home)
        _append_global_source(sources, surface="skills", label="共享 agent 技能", path="~/.agents/skills", count=count, items=items, home=home)
        _append_global_source(sources, surface="mcp", label="Antigravity 全局/插件配置", path="~/.config", count=0, items=[], note="Antigravity 主要通过 session plugin 注入 MMS 能力；全局项只读展示。", home=home)
    return sources


def _catalog_scope_counts(catalog: dict[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for kind in SURFACE_KINDS:
        panel = catalog.get(kind) if isinstance(catalog.get(kind), dict) else {}
        result[kind] = {}
        for scope in PACK_SCOPES:
            entries = panel.get(scope) if isinstance(panel, dict) else []
            result[kind][scope] = len(entries) if isinstance(entries, list) else 0
    return result


def _confirm_reference() -> dict[str, Any]:
    return {
        "title": "TUI 确认页对照",
        "source": "mms_tui.confirm_launch_tui + mms_core._build_confirm_preview_catalog",
        "panels": [
            {"id": "summary", "label": "摘要", "description": "CLI / Model / Launch / Bypass / Thinking / Effort / Agent Pack 等启动摘要。"},
            {"id": "mcp", "label": "MCP", "description": "本次启动会注入或继承的 MCP server；可在 TUI 里逐项临时禁用。"},
            {"id": "skills", "label": "技能", "description": "本次 session 可发现的 skill；按 always / Caveman / NSR / ECC / OMC 展开。"},
            {"id": "hooks", "label": "钩子", "description": "启动、工具前后、压缩、会话结束等自动 hook；可查看触发点和命令路径。"},
        ],
        "actions": [
            {"key": "Enter", "label": "启动", "description": "按当前开关与禁用选择启动 session。"},
            {"key": "←/→", "label": "切面板", "description": "在 摘要 / MCP / 技能 / 钩子 面板间切换。"},
            {"key": "↑/↓", "label": "看条目", "description": "在 MCP / 技能 / 钩子列表中移动，底部显示路径或命令。"},
            {"key": "D / Space", "label": "禁用选择", "description": "进入禁用模式后，对本次启动逐项关闭 surface。"},
            {"key": "Tab", "label": "切 Bypass", "description": "切换本次启动是否绕过审批。"},
            {"key": "M", "label": "切 1M", "description": "仅支持的 Claude Opus/Sonnet 模型显示。"},
            {"key": "C / N", "label": "Caveman / NSR", "description": "仅对应能力可用时显示。"},
            {"key": "T / E", "label": "思考 / 强度", "description": "仅支持 thinking/effort 的 Claude/Codex 路径显示。"},
            {"key": "X", "label": "能力包", "description": "Claude 可用时在 none / ECC / OMC 间切换。"},
            {"key": "B / Q", "label": "返回 / 取消", "description": "退出确认页，不写回持久配置。"},
        ],
        "constraints": [
            "TUI 确认页是单次启动覆盖层；开关和禁用选择优先级最高，但默认不持久化。",
            "WebUI 的能力清单来自同一个 preview catalog；WebUI 只解释和生成 preferences.toml 片段。",
            "全局 Claude/Codex/OpenCode/Antigravity 配置只读展示；不会在本页自动修改。",
            "Claude OAuth / 受限启动路径可能不注入托管 MCP、技能或钩子。",
        ],
    }


def _cli_panel_cards(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    panels = [{"id": "summary", "label": "摘要", "row_count": 1, "scope_counts": {}}]
    scope_counts = _catalog_scope_counts(catalog)
    for kind in SURFACE_KINDS:
        counts = scope_counts.get(kind) or {}
        panels.append(
            {
                "id": kind,
                "label": _KIND_LABELS.get(kind, kind),
                "row_count": sum(int(value or 0) for value in counts.values()),
                "scope_counts": counts,
            }
        )
    return panels


def _disabled_key_set(disabled: dict[str, Any], kind: str) -> set[str]:
    raw = disabled.get(kind) if isinstance(disabled, dict) else []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {_safe_text(item) for item in raw if _safe_text(item)}


def _row_disabled_by_preference(row: dict[str, Any], disabled: dict[str, Any]) -> bool:
    key = _safe_text(row.get("disable_key") or row.get("title"))
    if not key:
        return False
    kind = row.get("kind")
    if kind == "mcp":
        bucket = "mcp"
    elif kind == "hooks":
        bucket = "hooks"
    else:
        bucket = "skills"
    return key in _disabled_key_set(disabled, bucket)


def _cli_control_cards(cli: str, flags: dict[str, bool], defaults: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, str]]:
    controls = [
        {
            "id": "bypass",
            "label": "绕过审批",
            "key": "Tab",
            "state": "默认开启" if defaults.get("bypass") is not False else "默认关闭",
            "hint": "对应 TUI 确认页 Tab 切换。",
        }
    ]
    if flags.get("caveman"):
        controls.append(
            {
                "id": "caveman",
                "label": "Caveman",
                "key": "C",
                "state": "默认开启" if _safe_text(defaults.get("caveman_mode") or "enable") != "disable" else "默认关闭",
                "hint": "对应 TUI 确认页 C 切换。",
            }
        )
    if flags.get("nsr"):
        controls.append(
            {
                "id": "nsr",
                "label": "NSR",
                "key": "N",
                "state": "默认开启" if _safe_text(defaults.get("nsr_mode") or "enable") != "disable" else "默认关闭",
                "hint": "对应 TUI 确认页 N 切换。",
            }
        )
    if cli == "claude" and (flags.get("ecc") or flags.get("omc")):
        enabled_packs = " / ".join(name.upper() for name in ("ecc", "omc") if flags.get(name))
        controls.append(
            {
                "id": "agent_pack",
                "label": "能力包",
                "key": "X",
                "state": _safe_text(defaults.get("agent_pack") or "none"),
                "hint": f"对应 TUI 确认页 X 切换；可用：{enabled_packs or '无'}。",
            }
        )
    if cli in {"claude", "codex"}:
        controls.append(
            {
                "id": "thinking",
                "label": "思考 / 强度",
                "key": "T / E",
                "state": "随模型显示",
                "hint": "对应 TUI 确认页 T / E；是否出现取决于当前模型能力。",
            }
        )
    if cli == "claude":
        controls.append(
            {
                "id": "claude_1m",
                "label": "1M context",
                "key": "M",
                "state": "随模型显示",
                "hint": "只在支持的 Claude Opus/Sonnet 模型上出现。",
            }
        )
    controls.append(
        {
            "id": "execution_surfaces",
            "label": "MCP/技能/钩子注入",
            "key": "←/→ · D",
            "state": "会注入" if catalog.get("allow_execution_surfaces", True) else "不注入",
            "hint": "与 TUI MCP / 技能 / 钩子面板的数据源一致。",
        }
    )
    return controls


def _cli_view(
    cli: str,
    cli_rows: list[dict[str, Any]],
    catalog: dict[str, Any],
    flags: dict[str, bool],
    defaults: dict[str, Any],
    disabled: dict[str, Any],
    *,
    home: str,
) -> dict[str, Any]:
    by_group = {group: sum(1 for row in cli_rows if row.get("group") == group) for group in ("mms_dynamic", "global", "other")}
    by_kind = {kind: sum(1 for row in cli_rows if row.get("kind") == kind) for kind in SURFACE_KINDS}
    inactive = [row for row in cli_rows if not row.get("active_by_default")]
    disabled_by_preference = [row for row in cli_rows if _row_disabled_by_preference(row, disabled)]
    agent_pack_options = [name for name in ("ecc", "omc") if flags.get(name)]
    optional_scopes = [name for name, enabled in flags.items() if enabled]
    return {
        "id": cli,
        "label": _CLI_LABELS.get(cli, cli),
        "row_count": len(cli_rows),
        "allow_execution_surfaces": bool(catalog.get("allow_execution_surfaces", True)),
        "available_packs": optional_scopes,
        "optional_scopes": optional_scopes,
        "agent_pack_options": agent_pack_options,
        "counts": {
            **by_group,
            **by_kind,
        },
        "scope_counts": _catalog_scope_counts(catalog),
        "panels": _cli_panel_cards(catalog),
        "controls": _cli_control_cards(cli, flags, defaults, catalog),
        "global_sources": _global_sources_for_cli(cli, cli_rows, home=home),
        "constraints": [
            "TUI 启动确认页本次切换优先级最高，不写回真实配置。",
            "全局 CLI 配置只读展示；WebUI 不自动修改 Claude/Codex/OpenCode/Antigravity 全局文件。",
            "Claude OAuth / 受限启动路径不会注入托管 MCP、技能或钩子。" if not catalog.get("allow_execution_surfaces", True) else "当前启动预览允许注入托管 MCP、技能和钩子。",
        ],
        "inactive_by_default": len(inactive),
        "disabled_by_preference": len(disabled_by_preference),
        "disabled_by_default": len(disabled_by_preference),
    }


def build_session_assets_snapshot(
    cfg: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Build a read-only WebUI inventory for session skills/MCP/hooks."""
    _ = cfg, config_path, preferences_path, command_name
    mms_core = _load_mms_core()
    home = _real_home(mms_core)
    prefs = _load_preferences(mms_core)
    rows: list[dict[str, Any]] = []
    cli_cards = []
    defaults = ((prefs.get("launch") or {}).get("defaults") or {}) if isinstance(prefs, dict) else {}
    disabled = ((prefs.get("session_surfaces") or {}).get("disabled") or {}) if isinstance(prefs, dict) else {}
    cli_views = []
    for cli in CLI_ORDER:
        runtime = {
            "bypass": defaults.get("bypass", True),
            "disabled_session_surfaces": disabled,
        }
        catalog, flags = _preview_for_cli(mms_core, cli, runtime)
        cli_rows = _flatten_catalog(cli, catalog, home=home)
        cli_rows.extend(_global_skill_inventory_rows(cli, home=home))
        rows.extend(cli_rows)
        cli_views.append(_cli_view(cli, cli_rows, catalog, flags, defaults, disabled, home=home))
        cli_cards.append(
            {
                "id": cli,
                "label": _CLI_LABELS.get(cli, cli),
                "row_count": len(cli_rows),
                "available_packs": [name for name, enabled in flags.items() if enabled],
                "allow_execution_surfaces": bool(catalog.get("allow_execution_surfaces", True)),
            }
        )

    counts = {group: sum(1 for row in rows if row.get("group") == group) for group in ("mms_dynamic", "global", "other")}
    kind_counts = {kind: sum(1 for row in rows if row.get("kind") == kind) for kind in SURFACE_KINDS}
    return {
        "schema": "mms.session_assets.snapshot.v1",
        "mode": "read_only_inventory",
        "summary": {
            "total": len(rows),
            "mms_dynamic": counts["mms_dynamic"],
            "global": counts["global"],
            "other": counts["other"],
            "skills": kind_counts["skills"],
            "mcp": kind_counts["mcp"],
            "hooks": kind_counts["hooks"],
        },
        "tabs": [
            {
                "id": "mms_dynamic",
                "title": "MMS 动态注入",
                "description": "MMS 在启动 session 时按 CLI 和开关动态注入；默认不污染 global config。",
                "row_count": counts["mms_dynamic"],
            },
            {
                "id": "global",
                "title": "全局继承",
                "description": "来自用户全局 Claude/Codex/OpenCode 配置或已安装插件；WebUI 只读展示。",
                "row_count": counts["global"],
            },
            {
                "id": "other",
                "title": "其它检测项",
                "description": "启动预览能看到但暂未归类的条目，需要保守展示路径。",
                "row_count": counts["other"],
            },
        ],
        "clis": cli_cards,
        "cli_views": cli_views,
        "confirm_reference": _confirm_reference(),
        "rows": rows,
        "managed_roots": _managed_roots(home),
        "managed_install": _managed_install_contract(home, mms_core),
        "global_roots": _global_roots(home),
        "launch_defaults": {
            "caveman_mode": _safe_text(defaults.get("caveman_mode") or "enable"),
            "nsr_mode": _safe_text(defaults.get("nsr_mode") or "enable"),
            "agent_pack": _safe_text(defaults.get("agent_pack") or "none"),
            "bypass": defaults.get("bypass") is not False,
        },
        "disabled_defaults": _disabled_defaults(prefs),
        "preference_snippet": _preference_snippet(prefs),
        "configuration_contract": {
            "persistent_path": preferences_path or "~/.config/mms/preferences.toml",
            "managed_assets_root": _managed_install_contract(home, mms_core).get("root"),
            "launch_override": "TUI 启动确认页本次切换优先级最高，但不写回真实配置。",
            "webui_write_scope": "本页可单独写 preferences.toml；不混入模型/provider 保存。",
        },
        "guidance": [
            "先看 MMS dynamic：这些是 MMS session 才注入的能力，适合按 CLI/任务开关。",
            "再看 Global / inherited：这些会影响 MMS 外的 CLI，默认只读，不建议新手直接改。",
            "Caveman/NSR/ECC/OMC 是能力包开关；MCP、skills、hooks 是能力包实际展开后的 surface。",
        ],
    }


__all__ = ["build_session_assets_snapshot"]
