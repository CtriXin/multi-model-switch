"""Read-only session asset inventory for MMS WebUI.

This module intentionally does not write preferences or real CLI config.  It
turns the existing launch-confirm preview catalog into a user-facing inventory
so WebUI can explain which skills, MCP servers, and hooks are global/inherited
versus MMS session-managed.
"""

from __future__ import annotations

import os
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
        ("Claude 全局技能目录", "~/.claude/skills"),
        ("Codex 全局技能目录", "~/.codex/skills"),
        ("共享 agent 技能目录", "~/.agents/skills"),
        ("Claude MCP 旧配置文件", "~/.claude.json"),
        ("Codex 配置文件", "~/.codex/config.toml"),
        ("Codex hooks 文件", "~/.codex/hooks.json"),
        ("OpenCode 配置目录", "~/.config/opencode"),
    ]
    rows = []
    for label, raw_path in candidates:
        expanded = _expand_path(raw_path, home=home)
        exists = os.path.exists(expanded)
        skill_count = 0
        if os.path.isdir(expanded):
            try:
                skill_count = sum(
                    1
                    for name in os.listdir(expanded)
                    if os.path.isfile(os.path.join(expanded, name, "SKILL.md"))
                )
            except OSError:
                skill_count = 0
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
    caveman = _safe_text(defaults.get("caveman_mode") or "enable")
    nsr = _safe_text(defaults.get("nsr_mode") or "enable")
    agent_pack = _safe_text(defaults.get("agent_pack") or "none")
    bypass = defaults.get("bypass")
    bypass_text = "true" if bypass is not False else "false"
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
        ]
    )


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
    for cli in CLI_ORDER:
        runtime = {
            "bypass": defaults.get("bypass", True),
            "disabled_session_surfaces": disabled,
        }
        catalog, flags = _preview_for_cli(mms_core, cli, runtime)
        cli_rows = _flatten_catalog(cli, catalog, home=home)
        rows.extend(cli_rows)
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
        "rows": rows,
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
            "launch_override": "TUI 启动确认页本次切换优先级最高，但不写回真实配置。",
            "webui_write_scope": "当前 WebUI 面板先做 read-only inventory + snippet；后续保存 preferences 仍需 HumanGate。",
        },
        "guidance": [
            "先看 MMS dynamic：这些是 MMS session 才注入的能力，适合按 CLI/任务开关。",
            "再看 Global / inherited：这些会影响 MMS 外的 CLI，默认只读，不建议新手直接改。",
            "Caveman/NSR/ECC/OMC 是能力包开关；MCP、skills、hooks 是能力包实际展开后的 surface。",
        ],
    }


__all__ = ["build_session_assets_snapshot"]
