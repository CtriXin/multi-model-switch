"""Session capability preview catalog helpers for MMS launch confirmation."""

from __future__ import annotations

import json
import os
import shlex


def mask_identity_value(value, *, keep=4):
    text = str(value or "").strip()
    if len(text) <= keep * 2:
        return text or "-"
    return f"{text[:keep]}***{text[-keep:]}"


def mask_email_value(value):
    text = str(value or "").strip()
    if not text or "@" not in text:
        return mask_identity_value(text)
    name, domain = text.split("@", 1)
    if len(name) <= 2:
        masked_name = name[:1] + "*"
    else:
        masked_name = name[:2] + "***"
    return f"{masked_name}@{domain}"


def runtime_network_summary_for_confirm(
    runtime,
    *,
    default_account_timezone,
    runtime_force_ipv4,
    snapshot_proxy_fingerprint,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    proxy = str(runtime.get("proxy") or "").strip()
    timezone_name = str(runtime.get("timezone") or default_account_timezone).strip() or default_account_timezone
    force_ipv4 = bool(runtime_force_ipv4(runtime))
    mode = snapshot_proxy_fingerprint(proxy)
    return f"{mode} | TZ {timezone_name} | IPv4 {'on' if force_ipv4 else 'auto'}"


def load_runtime_identity_preview(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    home_dir = os.path.expanduser(str(runtime.get("home_dir") or "").strip())
    if not home_dir:
        return {}
    target = os.path.join(home_dir, ".claude.json")
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    oauth_account = data.get("oauthAccount") if isinstance(data.get("oauthAccount"), dict) else {}
    return {
        "user_id": str(data.get("userID") or oauth_account.get("accountUuid") or "").strip(),
        "account_uuid": str(oauth_account.get("accountUuid") or "").strip(),
        "org_uuid": str(oauth_account.get("organizationUuid") or "").strip(),
        "email": str(oauth_account.get("emailAddress") or "").strip(),
    }


def confirm_context_lines(
    cli,
    runtime,
    *,
    default_account_timezone,
    runtime_force_ipv4,
    snapshot_proxy_fingerprint,
    fake_upstream_enabled,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    lines = []
    if runtime:
        runtime_id = str(runtime.get("id") or runtime.get("name") or "").strip()
        if runtime_id:
            lines.append(("Source", runtime_id))
        if cli == "claude":
            sidecar = runtime.get("vision_sidecar") if isinstance(runtime.get("vision_sidecar"), dict) else {}
            if sidecar and sidecar.get("enabled", True):
                provider_id = str(sidecar.get("provider_id") or "-").strip() or "-"
                model = str(sidecar.get("model") or "-").strip() or "-"
                lines.append(("Vision", f"{provider_id}/{model}"))
    if cli == "opencode":
        profile_label = str(runtime.get("opencode_profile_label") or runtime.get("opencode_profile") or "").strip()
        if profile_label:
            lines.append(("Profile", profile_label))
    if cli == "claude" and runtime.get("auth_mode") == "oauth":
        if fake_upstream_enabled():
            lines.append(("Fake", "ON"))
        lines.append(("Proxy", str(snapshot_proxy_fingerprint(runtime.get("proxy")))))
        lines.append(("TZ", str(runtime.get("timezone") or default_account_timezone)))
        lines.append(("IPv4", "on" if runtime_force_ipv4(runtime) else "auto"))
        lines.append(("Slot", f"pid-{os.getpid()}"))
        home_dir = os.path.expanduser(str(runtime.get("home_dir") or "").strip())
        if home_dir:
            lines.append(("Session", os.path.join(home_dir, "s", str(os.getpid()))))
        identity = load_runtime_identity_preview(runtime)
        if identity.get("email"):
            lines.append(("Email", mask_email_value(identity.get("email"))))
        if identity.get("user_id"):
            lines.append(("UserID", mask_identity_value(identity.get("user_id"))))
        if identity.get("org_uuid"):
            lines.append(("OrgID", mask_identity_value(identity.get("org_uuid"))))
        network_guard = runtime.get("_network_guard") if isinstance(runtime.get("_network_guard"), dict) else {}
        if network_guard:
            lines.append(("DNS", str(network_guard.get("dns_mode") or "-")))
            proxy_validation = str(network_guard.get("proxy_validation") or "").strip()
            if proxy_validation == "skipped_fake":
                lines.append(("Check", "skipped(fake)"))
            if network_guard.get("ipv4_egress") not in {"", "-"}:
                lines.append(("IPv4Egress", str(network_guard.get("ipv4_egress") or "-")))
            if network_guard.get("ipv6_egress") not in {"", "-", "blocked"}:
                lines.append(("IPv6Egress", str(network_guard.get("ipv6_egress") or "-")))
            target_states = []
            for item in network_guard.get("targets") or []:
                label = str(item.get("label") or "?")
                target_states.append(f"{label}:{'ok' if item.get('ok') else 'fail'}")
            if target_states:
                lines.append(("Reach", " ".join(target_states[:3])))
            no_proxy_conflicts = network_guard.get("no_proxy_conflicts") or []
            if no_proxy_conflicts:
                lines.append(("Leak", ",".join(no_proxy_conflicts[:2])))
        report = runtime.get("_account_guard_report") if isinstance(runtime.get("_account_guard_report"), dict) else {}
        if report:
            lines.append(("Score", str(report.get("score", "-"))))
            lines.append(("Sessions", str(report.get("active_sessions_after", "-"))))
            drift = report.get("drift_fields") or []
            lines.append(("Profile", "stable" if not drift else ",".join(drift)))
    return lines[:12]


def confirm_launch(
    cli,
    model_info,
    once=False,
    runtime=None,
    *,
    console,
    panel_cls,
    prompt_cls,
    runtime_source_kind_label,
    normalize_opencode_entrypoint,
):
    if isinstance(model_info, dict):
        model_items = [f"{k}={v}" for k, v in model_info.items() if k != "subagent" and v]
        model_display = ", ".join(model_items) if model_items else "官方默认"
    else:
        model_display = model_info or "官方默认"

    mode_str = "一次性命令" if once else "交互会话"
    env_str = "临时注入，仅当前 CLI 进程可见" if cli in ("claude", "codex", "opencode", "agy") else "无需额外注入"
    source_line = ""
    if runtime:
        source_kind = runtime_source_kind_label(runtime)
        source_label = runtime.get("name", runtime.get("id", "default"))
        source_line = f"[bold]来源:[/bold]   {source_kind} / {source_label}\n"
    profile_line = ""
    if cli == "opencode" and runtime:
        profile_label = str(runtime.get("opencode_profile_label") or runtime.get("opencode_profile") or "").strip()
        if profile_label:
            profile_line = f"[bold]Profile:[/bold] {profile_label}\n"
        entrypoint = normalize_opencode_entrypoint(runtime.get("opencode_entrypoint")) or "tui"
        if entrypoint != "tui":
            profile_line += f"[bold]Entry:[/bold]   {entrypoint}\n"
    panel_text = (
        f"[bold]CLI:[/bold]    {cli}\n"
        f"[bold]模型:[/bold]   {model_display}\n"
        f"{source_line}"
        f"{profile_line}"
        f"[bold]启动:[/bold]   {mode_str}\n"
        f"[bold]环境:[/bold]   {env_str}\n"
        f"\n"
        f"[dim]Enter=启动  S=保存为预设  Q=取消[/dim]"
    )
    console.print(panel_cls(panel_text, title="确认启动", border_style="green"))

    choice = prompt_cls.ask("操作", choices=["", "s", "q"], default="")
    return choice


def build_confirm_preview_catalog(
    cli,
    runtime,
    *,
    localize,
    resolve_real_user_home,
    safe_getcwd,
    has_caveman=False,
    has_nsr=False,
    has_ecc=False,
    has_omc=False,
):
    _L = localize
    _safe_getcwd = safe_getcwd
    runtime = runtime if isinstance(runtime, dict) else {}
    allow_execution_surfaces = not (cli == "claude" and runtime.get("auth_mode") == "oauth")
    preview = {
        "allow_execution_surfaces": allow_execution_surfaces,
        "mcp": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
        "skills": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
        "hooks": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
    }

    if cli not in {"claude", "codex", "opencode", "agy"}:
        return preview

    try:
        from mms_launchers import (
            _build_codex_session_hooks,
            _configure_claude_caveman_hooks,
            _configure_claude_nsr_hooks,
            _configure_claude_ecc_hooks,
            _configure_claude_omc_hooks,
            _agent_pack_mcp_servers,
            _default_hive_session_mcp_server,
            _default_pilot_session_mcp_server,
            _filter_claude_session_hooks,
            _load_global_claude_settings_template,
            _load_mms_claude_settings_template,
            _load_real_claude_settings,
            _merge_claude_settings,
            _merge_mms_session_hooks,
            _opencode_rtk_plugin_path,
            _opencode_xmem_plugin_path,
            _resolve_agent_browser_root,
            _resolve_auto_github_contributor_root,
            _resolve_caveman_root,
            _resolve_ecc_root,
            _resolve_nsr_root,
            _resolve_omc_root,
            _resolve_token_saver_root,
            _resolve_toon_root,
            _resolve_weber_root,
            _resolve_web_access_root,
            _resolve_xmem_root,
            _sanitize_claude_inherited_settings_payload,
            _session_managed_mcp_servers,
            _strip_agent_im_hooks,
        )
    except Exception:
        return preview

    def _append(panel_key, scope, *, title, summary="", details=None, disable_key=None):
        panel = preview.get(panel_key)
        if not isinstance(panel, dict):
            return
        bucket = panel.get(scope)
        if not isinstance(bucket, list):
            return
        title = str(title or "").strip()
        summary = str(summary or "").strip()
        normalized_details = []
        for item in details or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            label = str(item[0] or "").strip()
            value = str(item[1] or "").strip()
            if label and value:
                normalized_details.append((label, value))
        entry = {
            "title": title,
            "summary": summary,
            "details": normalized_details,
        }
        disable_key = str(disable_key or "").strip()
        if disable_key:
            entry["disable_key"] = disable_key
        if not title:
            return
        signature = (
            entry["title"],
            entry["summary"],
            tuple(entry["details"]),
        )
        for existing in bucket:
            if not isinstance(existing, dict):
                continue
            existing_signature = (
                str(existing.get("title") or "").strip(),
                str(existing.get("summary") or "").strip(),
                tuple(
                    (str(label or "").strip(), str(value or "").strip())
                    for label, value in (existing.get("details") or [])
                    if str(label or "").strip() and str(value or "").strip()
                ),
            )
            if existing_signature == signature:
                return
        bucket.append(entry)

    def _event_label(event_name, matcher=""):
        mapping = {
            "SessionStart": _L("会话启动", "SessionStart"),
            "Stop": _L("会话结束", "Stop"),
            "UserPromptSubmit": _L("提交提示", "UserPromptSubmit"),
            "PreToolUse": _L("工具前", "PreToolUse"),
            "PostToolUse": _L("工具后", "PostToolUse"),
            "PreCompact": _L("压缩前", "PreCompact"),
            "PostCompact": _L("压缩后", "PostCompact"),
        }
        label = mapping.get(str(event_name or "").strip(), str(event_name or "").strip())
        matcher_text = str(matcher or "").strip()
        return f"{label} · {matcher_text}" if matcher_text else label

    def _abbrev_path(path_text):
        path_text = str(path_text or "").strip()
        if not path_text:
            return ""
        if "://" in path_text:
            return path_text
        if os.path.isabs(path_text):
            normalized = os.path.abspath(path_text)
            real_home = os.path.abspath(resolve_real_user_home())
            cwd = os.path.abspath(_safe_getcwd())
            try:
                if os.path.commonpath([normalized, cwd]) == cwd:
                    return f".{os.sep}{os.path.relpath(normalized, cwd)}"
            except ValueError:
                pass
            try:
                if os.path.commonpath([normalized, real_home]) == real_home:
                    suffix = os.path.relpath(normalized, real_home)
                    return "~" if suffix == "." else os.path.join("~", suffix)
            except ValueError:
                pass
            return normalized
        return path_text

    def _command_target(command, args=None):
        text = str(command or "").strip()
        parts = []
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if isinstance(args, list):
            parts.extend(str(item or "").strip() for item in args if str(item or "").strip())
        generic_runners = {
            "bash", "sh", "node", "python", "python3",
            "/bin/bash", "/bin/sh", "/usr/bin/env",
        }
        for token in reversed(parts):
            token = str(token or "").strip()
            if not token or token.startswith("-") or token.startswith("--"):
                continue
            if "/" in token:
                return os.path.basename(token), token
        for token in reversed(parts):
            token = str(token or "").strip()
            if not token or token.startswith("-") or "=" in token or token in generic_runners:
                continue
            return token[:64], token
        return (_L("内联命令", "inline command"), text[:256] if text else "")

    def _skill_path(root_path):
        root_path = str(root_path or "").strip()
        if not root_path:
            return ""
        skill_md = os.path.join(root_path, "SKILL.md")
        return skill_md if os.path.isfile(skill_md) else root_path

    def _hook_descriptor(command):
        display_name, target_path = _command_target(command)
        lower_command = str(command or "").strip().lower()
        lower_target = str(target_path or "").strip().lower()
        basename = os.path.basename(target_path or display_name).lower()

        if (
            "brainkeeper-session-start-hook" in lower_target
            or "mindkeeper-session-start-hook" in lower_target
            or basename in {"brainkeeper-session-start-hook.sh", "mindkeeper-session-start-hook.sh"}
        ):
            return _L("恢复上次进度", "Resume last work"), _L("BrainKeeper 恢复提示", "BrainKeeper restore hint")
        if (
            "brainkeeper-session-end-hook" in lower_target
            or "mindkeeper-session-end-hook" in lower_target
            or basename in {"brainkeeper-session-end-hook.sh", "mindkeeper-session-end-hook.sh"}
        ):
            return _L("保存当前进度", "Save current progress"), _L("BrainKeeper 会话归档", "BrainKeeper session checkpoint")
        if (
            "brainkeeper-token-monitor-hook" in lower_target
            or "mindkeeper-token-monitor-hook" in lower_target
            or basename in {"brainkeeper-token-monitor-hook.sh", "mindkeeper-token-monitor-hook.sh"}
        ):
            return _L("监控 token 用量", "Monitor token usage"), _L("BrainKeeper token 监控", "BrainKeeper token monitor")
        if "map-auto-index" in lower_target or basename == "map-auto-index.sh":
            return _L("Map 自动索引", "Map auto-index"), _L("刷新项目结构索引", "Refresh project structure index")
        if "codegraph-auto-index" in lower_target or basename == "claude-codegraph-auto-index.sh":
            return "CodeGraph 自动索引", _L("刷新项目 CodeGraph 索引", "Refresh project CodeGraph index")
        if "xmem-session-start-hook" in lower_target or basename == "xmem-session-start-hook.sh":
            return "xmem 自动同步", _L("注册/同步当前项目 truth index", "Register/sync the current project truth index")
        if "xmem-session-end-hook" in lower_target or basename == "xmem-session-end-hook.sh":
            return "xmem 收尾同步", _L("记录会话结束，不注入知识正文", "Record session close without injecting memory body")
        if "nsr-claude-hook" in lower_target or "nsr-codex-hook" in lower_target or "nsr-builtin-hook" in lower_target:
            return "NSR 持续运行", _L("按 active NSR goal 注入继续执行提示", "Inject active NSR goal continuation hints")
        if "claude-feishu-webfetch-guard" in lower_target or basename == "claude-feishu-webfetch-guard.sh":
            return _L("飞书 WebFetch 防护", "Feishu WebFetch guard"), _L("拦截高风险飞书抓取", "Guard risky Feishu fetches")
        if "rtk-rewrite" in lower_target or basename == "rtk-rewrite.sh":
            return "RTK Bash 改写", _L("压缩高 token Bash 命令", "Rewrite token-heavy Bash commands")
        if basename == "hook.sh" and "read-once" in (lower_target or lower_command):
            return _L("Read-once 读取拦截", "Read-once read hook"), _L("避免重复全文读取", "Avoid redundant full-file rereads")
        if basename == "compact.sh" and "read-once" in (lower_target or lower_command):
            return _L("Read-once 压缩整理", "Read-once compact"), _L("编辑后优先回看 diff", "Prefer diff after edits")
        if "hive-compact-hook" in lower_target or basename == "hive-compact-hook.sh":
            return _L("Hive 压缩整理", "Hive compact"), _L("compact 前后整理上下文", "Summarize context before and after compact")
        if "caveman-activate" in lower_target or basename == "caveman-activate.js":
            return "Caveman 激活", _L("会话启动时载入 Caveman 模式", "Load Caveman mode on session start")
        if "caveman-mode-tracker" in lower_target or basename == "caveman-mode-tracker.js":
            return "Caveman 模式跟踪", _L("跟踪用户是否继续使用 Caveman", "Track whether Caveman stays enabled")
        if "plugin-hook-bootstrap" in lower_target or basename == "plugin-hook-bootstrap.js":
            return "ECC Hook 初始化", _L("载入 ECC hook 集", "Load ECC hook bundle")
        if "session-start-bootstrap" in lower_target or basename == "session-start-bootstrap.js":
            return "ECC 会话初始化", _L("会话启动时准备 ECC 运行环境", "Prepare ECC runtime on session start")
        if "run-with-flags" in lower_target or basename in {"run-with-flags.js", "run-with-flags-shell.sh"}:
            return "ECC Flag 包装", _L("为命令补充 ECC flags", "Wrap commands with ECC flags")
        if "pre-bash-dispatcher" in lower_target or basename == "pre-bash-dispatcher.js":
            return "ECC Bash 前置分发", _L("Bash 执行前做规则分发", "Dispatch ECC rules before Bash")
        if "post-bash-dispatcher" in lower_target or basename == "post-bash-dispatcher.js":
            return "ECC Bash 后置分发", _L("Bash 执行后补充检查", "Dispatch ECC checks after Bash")
        if "quality-gate" in lower_target or basename == "quality-gate.js":
            return "ECC 质量门", _L("关键阶段做质量检查", "Run ECC quality gates")
        if "stop-format-typecheck" in lower_target or basename == "stop-format-typecheck.js":
            return "ECC 停止前检查", _L("停止前做格式化与类型检查", "Run format and type checks before stop")
        if "design-quality-check" in lower_target or basename == "design-quality-check.js":
            return "ECC 设计质量检查", _L("设计相关质量检查", "Run design quality checks")
        if "post-edit-accumulator" in lower_target or basename == "post-edit-accumulator.js":
            return "ECC 编辑累积", _L("编辑后累积上下文与检查", "Accumulate edit context after changes")
        if "keyword-detector" in lower_target or basename == "keyword-detector.mjs":
            return "OMC 关键词检测", _L("识别 autopilot / ralph / team 等触发词", "Detect autopilot / ralph / team keywords")
        if "skill-injector" in lower_target or basename == "skill-injector.mjs":
            return "OMC Skill 注入", _L("按任务注入 OMC workflow skills", "Inject OMC workflow skills")
        if "session-start" in lower_target or basename == "session-start.mjs":
            return "OMC 会话初始化", _L("准备 OMC runtime 与会话状态", "Prepare OMC runtime and session state")
        if "pre-tool-enforcer" in lower_target or basename == "pre-tool-enforcer.mjs":
            return "OMC 工具前检查", _L("工具执行前做约束检查", "Run checks before tool use")
        if "permission-handler" in lower_target or basename == "permission-handler.mjs":
            return "OMC 权限处理", _L("处理 OMC permission request", "Handle OMC permission requests")
        if "post-tool-verifier" in lower_target or basename == "post-tool-verifier.mjs":
            return "OMC 工具后验证", _L("工具执行后验证交付物", "Verify outputs after tool use")
        if "subagent-tracker" in lower_target or basename == "subagent-tracker.mjs":
            return "OMC Agent 跟踪", _L("跟踪 subagent 生命周期", "Track subagent lifecycle")
        if "context-guard-stop" in lower_target or basename == "context-guard-stop.mjs":
            return "OMC 上下文防护", _L("停止前检查上下文安全", "Check context safety on stop")
        if "persistent-mode" in lower_target or basename == "persistent-mode.mjs":
            return "OMC 持续模式", _L("维持 ralph/verify loop 状态", "Maintain ralph / verify loop state")
        if "code-simplifier" in lower_target or basename == "code-simplifier.mjs":
            return "OMC 简化检查", _L("停止前触发 code simplifier", "Run code simplifier on stop")
        if "oh-my-claudecode" in lower_target or "oh-my-claudecode" in lower_command:
            return "OMC Hook", _L("OMC orchestration runtime hook", "OMC orchestration runtime hook")
        if basename:
            return os.path.splitext(os.path.basename(target_path or display_name))[0], _L("托管 hook", "Managed hook")
        return display_name, _L("托管 hook", "Managed hook")

    def _mcp_detail(spec):
        spec = spec if isinstance(spec, dict) else {}
        url = str(spec.get("url") or "").strip()
        if url:
            shortened = _abbrev_path(url)
            return {
                "summary": f"url · {shortened}",
                "details": [
                    ("URL", url),
                    (_L("类型", "Type"), str(spec.get("type") or "sse").strip() or "sse"),
                ],
            }
        command = str(spec.get("command") or "").strip()
        if command:
            type_name = str(spec.get("type") or "stdio").strip() or "stdio"
            display_name, target_path = _command_target(command, spec.get("args"))
            path_value = target_path or command
            return {
                "summary": f"{type_name} · {_abbrev_path(path_value)}",
                "details": [
                    (_L("类型", "Type"), type_name),
                    (_L("路径", "Path"), path_value),
                    (_L("命令", "Command"), command),
                ],
                "target_name": display_name,
            }
        type_name = str(spec.get("type") or "").strip()
        return {
            "summary": type_name or _L("托管", "Managed"),
            "details": [(_L("类型", "Type"), type_name or _L("托管", "Managed"))],
        }

    def _append_hooks(scope, hooks_data):
        hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
        for event_name in sorted(hooks_data):
            groups = hooks_data.get(event_name)
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                for hook in group.get("hooks") or []:
                    if not isinstance(hook, dict):
                        continue
                    if str(hook.get("type") or "").strip() != "command":
                        continue
                    command_text = str(hook.get("command") or "").strip()
                    title, hint = _hook_descriptor(command_text)
                    display_name, target_path = _command_target(command_text)
                    event_label = _event_label(event_name, matcher)
                    details = [
                        (_L("触发", "Trigger"), event_label),
                        (_L("路径", "Path"), target_path or display_name),
                    ]
                    if command_text and command_text != (target_path or display_name):
                        details.append((_L("命令", "Command"), command_text))
                    _append(
                        "hooks",
                        scope,
                        title=title,
                        summary=f"{event_label} · {hint}",
                        details=details,
                        disable_key=command_text,
                    )

    def _list_skill_entries(*parent_dirs):
        entries = []
        seen = set()
        for parent_dir in parent_dirs:
            parent_dir = str(parent_dir or "").strip()
            if not parent_dir or not os.path.isdir(parent_dir):
                continue
            try:
                child_names = sorted(os.listdir(parent_dir))
            except OSError:
                continue
            for entry_name in child_names:
                skill_dir = os.path.join(parent_dir, entry_name)
                skill_md = os.path.join(skill_dir, "SKILL.md")
                if not os.path.isdir(skill_dir) or not os.path.isfile(skill_md):
                    continue
                if entry_name in seen:
                    continue
                seen.add(entry_name)
                entries.append({"name": entry_name, "path": skill_md})
        return entries

    def _append_skill_entries(scope, entries, detail):
        for entry in entries:
            if isinstance(entry, str):
                name = str(entry).strip()
                path = ""
            else:
                name = str((entry or {}).get("name") or "").strip()
                path = str((entry or {}).get("path") or "").strip()
            if not name:
                continue
            details = [(_L("来源", "Source"), detail)]
            if path:
                details.insert(0, (_L("路径", "Path"), path))
            _append(
                "skills",
                scope,
                title=name,
                summary=detail,
                details=details,
                disable_key=name,
            )

    def _count_files(*parent_dirs):
        total = 0
        seen = set()
        for parent_dir in parent_dirs:
            parent_dir = str(parent_dir or "").strip()
            if not parent_dir or not os.path.isdir(parent_dir):
                continue
            for root_dir, _dirnames, filenames in os.walk(parent_dir):
                for filename in filenames:
                    file_path = os.path.join(root_dir, filename)
                    if file_path in seen:
                        continue
                    seen.add(file_path)
                    total += 1
        return total

    def _append_skill_collection(
        scope,
        entries,
        detail,
        *,
        bundle_title="",
        bundle_root="",
        collapse_threshold=12,
        bundle_note="",
        extra_details=None,
        bundle_disable_key="",
    ):
        entries = list(entries or [])
        if len(entries) <= max(1, int(collapse_threshold or 1)):
            _append_skill_entries(scope, entries, detail)
            return

        sample_names = ", ".join(
            str((entry or {}).get("name") or "").strip()
            for entry in entries[:5]
            if str((entry or {}).get("name") or "").strip()
        )
        details = []
        if bundle_root:
            details.append((_L("路径", "Path"), bundle_root))
        details.append((_L("数量", "Count"), str(len(entries))))
        if sample_names:
            suffix = " …" if len(entries) > 5 else ""
            details.append((_L("样例", "Samples"), f"{sample_names}{suffix}"))
        for item in extra_details or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            label = str(item[0] or "").strip()
            value = str(item[1] or "").strip()
            if label and value:
                details.append((label, value))
        details.append((_L("来源", "Source"), detail))
        if bundle_note:
            details.append((_L("说明", "Note"), bundle_note))
        _append(
            "skills",
            scope,
            title=bundle_title or detail,
            summary=_L(f"{len(entries)} 个 skill", f"{len(entries)} skills"),
            details=details,
            disable_key=bundle_disable_key or bundle_title or detail,
        )

    if cli == "claude":
        base_settings = _load_real_claude_settings()
        managed_mcp = _session_managed_mcp_servers(
            base_settings,
            allow_execution_surfaces=allow_execution_surfaces,
        )
        for name in sorted(managed_mcp):
            mcp_entry = _mcp_detail(managed_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )

        template_settings = _load_mms_claude_settings_template()
        inherited_settings = _sanitize_claude_inherited_settings_payload(
            base_settings,
            allow_execution_surfaces=allow_execution_surfaces,
        )
        merged_settings = _merge_claude_settings(
            inherited_settings,
            _load_global_claude_settings_template(),
        )
        base_hooks = _filter_claude_session_hooks(
            _merge_mms_session_hooks(
                _strip_agent_im_hooks(merged_settings.get("hooks")),
                template_settings.get("hooks"),
            ),
            allow_execution_surfaces=allow_execution_surfaces,
        )
        base_hooks = _configure_claude_nsr_hooks(base_hooks, enable_nsr=False)
        _append_hooks("always", base_hooks)
        if has_caveman and allow_execution_surfaces:
            _append_hooks(
                "caveman",
                _configure_claude_caveman_hooks({}, enable_caveman=True),
            )
        if has_nsr and allow_execution_surfaces:
            _append_hooks(
                "nsr",
                _configure_claude_nsr_hooks({}, enable_nsr=True),
            )
        if has_ecc and allow_execution_surfaces:
            _append_hooks(
                "ecc",
                _configure_claude_ecc_hooks({}, enable_ecc=True),
            )
        if has_omc and allow_execution_surfaces:
            _append_hooks(
                "omc",
                _configure_claude_omc_hooks({}, enable_omc=True),
            )
    elif cli == "codex":
        real_claude_json = os.path.join(resolve_real_user_home(), ".claude.json")
        try:
            with open(real_claude_json, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            codex_mcp = loaded.get("mcpServers", {}) if isinstance(loaded, dict) else {}
        except Exception:
            codex_mcp = {}
        codex_mcp = dict(codex_mcp) if isinstance(codex_mcp, dict) else {}
        hive_spec = _default_hive_session_mcp_server()
        if isinstance(hive_spec, dict) and str(hive_spec.get("command") or "").strip():
            codex_mcp.setdefault("hive", hive_spec)
        pilot_spec = _default_pilot_session_mcp_server()
        if isinstance(pilot_spec, dict) and str(pilot_spec.get("command") or "").strip():
            codex_mcp.setdefault("pilot", pilot_spec)
        for name in sorted(codex_mcp):
            mcp_entry = _mcp_detail(codex_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )

        real_codex_hooks = os.path.join(resolve_real_user_home(), ".codex", "hooks.json")
        try:
            with open(real_codex_hooks, "r", encoding="utf-8") as f:
                loaded_hooks = json.load(f)
            codex_hooks = _build_codex_session_hooks(loaded_hooks, enable_caveman=False)
        except Exception:
            codex_hooks = {}
        _append_hooks("always", (codex_hooks or {}).get("hooks"))
        if has_caveman:
            caveman_hooks = _build_codex_session_hooks({}, enable_caveman=True)
            _append_hooks("caveman", (caveman_hooks or {}).get("hooks"))
        if has_nsr:
            nsr_hooks = _build_codex_session_hooks({}, enable_nsr=True)
            _append_hooks("nsr", (nsr_hooks or {}).get("hooks"))
    elif cli == "opencode":
        rtk_plugin = _opencode_rtk_plugin_path(runtime)
        if rtk_plugin:
            _append(
                "hooks",
                "always",
                title="RTK OpenCode plugin",
                summary=_L("静默改写高 token Bash 命令", "Silently rewrite token-heavy Bash commands"),
                details=[
                    (_L("类型", "Type"), "OpenCode plugin"),
                    (_L("路径", "Path"), rtk_plugin),
                ],
                disable_key="opencode-rtk",
            )
        xmem_plugin = _opencode_xmem_plugin_path(runtime)
        if xmem_plugin:
            _append(
                "hooks",
                "always",
                title="xmem OpenCode plugin",
                summary=_L("会话启动/结束时轻量同步当前项目", "Lightly sync the current project on session start/end"),
                details=[
                    (_L("类型", "Type"), "OpenCode plugin"),
                    (_L("路径", "Path"), xmem_plugin),
                ],
                disable_key="opencode-xmem",
            )
    elif cli == "agy":
        agy_mcp = _session_managed_mcp_servers(
            {},
            allow_execution_surfaces=allow_execution_surfaces,
            disabled_session_surfaces=runtime.get("disabled_session_surfaces"),
        )
        for name in sorted(agy_mcp):
            mcp_entry = _mcp_detail(agy_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )
        agy_hooks = _merge_mms_session_hooks({})
        _append_hooks("always", agy_hooks)
        if has_caveman:
            _append_hooks(
                "caveman",
                _configure_claude_caveman_hooks({}, enable_caveman=True),
            )

    if allow_execution_surfaces:
        for pack_key, enabled in (("ecc", has_ecc), ("omc", has_omc)):
            if enabled:
                pack_mcp = _agent_pack_mcp_servers(pack_key)
                for name in sorted(pack_mcp):
                    mcp_entry = _mcp_detail(pack_mcp.get(name))
                    _append(
                        "mcp",
                        pack_key,
                        title=name,
                        summary=str(mcp_entry.get("summary") or ""),
                        details=mcp_entry.get("details") or [],
                        disable_key=name,
                    )

        if _resolve_web_access_root():
            web_access_root = _resolve_web_access_root()
            _append_skill_entries(
                "always",
                [{"name": "web-access", "path": _skill_path(web_access_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_weber_root():
            weber_root = _resolve_weber_root()
            _append_skill_entries(
                "always",
                [{"name": "weber", "path": _skill_path(weber_root)}],
                _L("会话技能", "Session skill"),
            )
        if cli in {"codex", "agy"} and _resolve_agent_browser_root():
            agent_browser_root = _resolve_agent_browser_root()
            _append_skill_entries(
                "always",
                [{"name": "agent-browser", "path": _skill_path(agent_browser_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_toon_root():
            toon_root = _resolve_toon_root()
            _append_skill_entries(
                "always",
                [{"name": "toon", "path": _skill_path(toon_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_token_saver_root():
            token_saver_root = _resolve_token_saver_root()
            _append_skill_entries(
                "always",
                [{"name": "token-saver", "path": _skill_path(token_saver_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_xmem_root():
            xmem_root = _resolve_xmem_root()
            _append_skill_entries(
                "always",
                [{"name": "xmem", "path": _skill_path(xmem_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_auto_github_contributor_root():
            auto_github_contributor_root = _resolve_auto_github_contributor_root()
            _append_skill_entries(
                "always",
                [
                    {
                        "name": "auto-github-contributor",
                        "path": _skill_path(auto_github_contributor_root),
                    }
                ],
                _L("会话技能", "Session skill"),
            )

        caveman_root = _resolve_caveman_root() if has_caveman else ""
        if caveman_root:
            caveman_skills = _list_skill_entries(os.path.join(caveman_root, "skills"))
            if not caveman_skills:
                caveman_skills = [{"name": "caveman", "path": _skill_path(caveman_root)}]
            _append_skill_collection(
                "caveman",
                caveman_skills,
                _L("Caveman 包", "Caveman bundle"),
                bundle_title=_L("Caveman 能力包", "Caveman bundle"),
                bundle_root=caveman_root,
                collapse_threshold=12,
                bundle_note=_L("这些是可用技能目录，不代表本次会全部执行。", "These are available skills, not all executed on launch."),
                bundle_disable_key="caveman",
            )

        nsr_root = _resolve_nsr_root() if has_nsr else ""
        if nsr_root:
            _append_skill_entries(
                "nsr",
                [{"name": "nsr", "path": _skill_path(nsr_root)}],
                _L("NSR 运行时", "NSR runtime"),
            )

        ecc_root = _resolve_ecc_root() if has_ecc else ""
        if ecc_root:
            ecc_skills = _list_skill_entries(
                os.path.join(ecc_root, ".claude", "skills"),
                os.path.join(ecc_root, ".agents", "skills"),
                os.path.join(ecc_root, "skills"),
            )
            if not ecc_skills:
                ecc_skills = [{"name": "ecc", "path": _skill_path(ecc_root)}]
            ecc_command_count = _count_files(
                os.path.join(ecc_root, ".claude", "commands"),
                os.path.join(ecc_root, "commands"),
            )
            ecc_rule_count = _count_files(
                os.path.join(ecc_root, ".claude", "rules"),
                os.path.join(ecc_root, "rules"),
            )
            _append_skill_collection(
                "ecc",
                ecc_skills,
                _L("ECC 包", "ECC bundle"),
                bundle_title=_L("ECC 能力包", "ECC bundle"),
                bundle_root=ecc_root,
                collapse_threshold=12,
                bundle_note=_L("这些是可用技能目录，不代表本次会全部执行；自动生效主要看 hooks 面板。", "These are available skills, not all executed on launch; automatic behavior mainly comes from hooks."),
                extra_details=[
                    (_L("命令", "Commands"), str(ecc_command_count)),
                    (_L("规则", "Rules"), str(ecc_rule_count)),
                ],
                bundle_disable_key="ecc",
            )

        omc_root = _resolve_omc_root() if has_omc else ""
        if omc_root:
            omc_skills = _list_skill_entries(os.path.join(omc_root, "skills"))
            if not omc_skills:
                omc_skills = [{"name": "omc", "path": _skill_path(omc_root)}]
            omc_agent_count = _count_files(os.path.join(omc_root, "agents"))
            _append_skill_collection(
                "omc",
                omc_skills,
                _L("OMC 包", "OMC bundle"),
                bundle_title=_L("OMC 能力包", "OMC bundle"),
                bundle_root=omc_root,
                collapse_threshold=12,
                bundle_note=_L("启用 orchestration runtime；可能写入 .omc/ 并使用 team/tmux/CLI worker。", "Enables orchestration runtime; may write .omc/ and use team/tmux/CLI workers."),
                extra_details=[
                    (_L("Agents", "Agents"), str(omc_agent_count)),
                ],
                bundle_disable_key="omc",
            )

    return preview
