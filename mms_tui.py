"""MMS curses TUI：箭头键交互选择器 — v2 品类模式"""

import curses
import json
import locale
import os
import sys
import unicodedata
from mms_i18n import pick as _L

# CJK locale 下 ambiguous-width 字符渲染为 2 列
_lang = os.environ.get("LANG", "") or locale.getdefaultlocale()[0] or ""
_AMBIGUOUS_WIDE = any(_lang.lower().startswith(p) for p in ("zh", "ja", "ko"))


# ── ASCII Art Logos（来自各 CLI 源码）──

CLI_LOGOS = {
    "claude": [  # 来自 Claude Code 源码
        "▐▛███▜▌",
        "▜█████▛",
        " ▘▘ ▝▝",
    ],
    "codex": [  # Codex CLI 启动界面风格
        ">_ OpenAI Codex",
    ],
}

# 统一 logo 高度（居中补空行）
_MAX_LOGO_H = max(len(v) for v in CLI_LOGOS.values())
for _cli in CLI_LOGOS:
    lines = CLI_LOGOS[_cli]
    pad = _MAX_LOGO_H - len(lines)
    top_pad = pad // 2
    bot_pad = pad - top_pad
    CLI_LOGOS[_cli] = [""] * top_pad + lines + [""] * bot_pad


def _connect_actions():
    return [
        {
            "id": "connect_gateway",
            "title": _L("添加网关通道", "Add Gateway Channel"),
            "summary": _L("输入接口地址和 API Key，接入兼容 OpenAI / Anthropic 的服务", "Connect any OpenAI / Anthropic compatible service with Base URL and API key"),
        },
        {
            "id": "connect_official",
            "title": _L("添加官方通道", "Add Official Channel"),
            "summary": _L("创建 OAuth 账号并进入官方登录流程", "Create an OAuth account and continue to the official login flow"),
        },
        {
            "id": "manage_channels",
            "title": _L("管理现有通道", "Manage Channels"),
            "summary": _L("查看状态、设默认、删除通道、查看本地统计", "Inspect status, set defaults, remove channels, and view local stats"),
        },
    ]


# ── 辅助函数 ──────────────────────────────────────────────

def _draw_box(stdscr, y, x, h, w, title="", color=None):
    attr = color if color is not None else 0
    try:
        stdscr.addstr(y, x, "╭" + "─" * (w - 2) + "╮", attr)
        for i in range(1, h - 1):
            stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│", attr)
        stdscr.addstr(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", attr)
        if title:
            t = f" {title} "
            tx = x + (w - _display_width(t)) // 2
            stdscr.addstr(y, tx, t, curses.A_BOLD | attr)
    except curses.error:
        pass


def _display_width(text, ambiguous_wide=None):
    """计算字符串的终端显示宽度。
    W/F → 2 列；A(ambiguous) → CJK locale 下 2 列，否则 1 列；其余 1 列。
    """
    if ambiguous_wide is None:
        ambiguous_wide = _AMBIGUOUS_WIDE
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):
            w += 2
        elif eaw == 'A':
            w += 2 if ambiguous_wide else 1
        else:
            w += 1
    return w


def _center_text(stdscr, y, center_x, text, attr=0):
    dw = _display_width(text)
    x = center_x - dw // 2
    try:
        stdscr.addstr(y, max(0, x), text, attr)
    except curses.error:
        pass


def _draw_centered_block(stdscr, y, center_x, lines, attr=0):
    # Logo 里的 box/block 字符在常见终端里通常按 1 列渲染；
    # 若按 CJK ambiguous=2 计算，会把整块 logo 错误地推向左侧。
    block_w = max((_display_width(line, ambiguous_wide=False) for line in lines if line), default=0)
    start_x = center_x - block_w // 2
    for i, line in enumerate(lines):
        if not line:
            continue
        try:
            stdscr.addstr(y + i, max(0, start_x), line, attr)
        except curses.error:
            pass


def _safe_addstr(stdscr, y, x, text, attr=0, max_w=None):
    """安全写入，自动截断避免 curses.error。"""
    if max_w:
        # 按 display width 截断
        out = ""
        w = 0
        for ch in text:
            cw = _display_width(ch)
            if w + cw > max_w:
                break
            out += ch
            w += cw
        text = out
    try:
        stdscr.addstr(y, max(0, x), text, attr)
    except curses.error:
        pass


def _draw_separator(stdscr, y, cx, width, attr=0):
    """画一条居中分隔线。"""
    sx = cx - width // 2
    try:
        stdscr.addstr(y, max(0, sx), "─" * width, attr)
    except curses.error:
        pass


# ── 第 1 步：品类选择 TUI ──────────────────────────────────

_FAMILY_COLORS = {
    "Claude": 3, "GPT": 5, "GLM": 7, "Kimi": 6,
    "Qwen": 4, "MiniMax": 2, "Gemini": 1,
}
_CLI_COLORS = {"claude": 3, "codex": 5}


def _last_used_label(last_item):
    if not isinstance(last_item, dict):
        return "?"
    model_info = last_item.get("model_info")
    if isinstance(model_info, dict):
        heavy = str(model_info.get("model") or "").strip()
        medium = str(model_info.get("lb_medium") or "").strip()
        light = str(model_info.get("lb_light") or "").strip()
        if heavy and (medium or light):
            parts = [heavy]
            if medium:
                parts.append(medium)
            if light:
                parts.append(light)
            return " / ".join(parts)
    return str(last_item.get("model") or "?")


def select_family_tui(families_by_cli, cli_names, last_used=None, families_detail=None, provider_options_by_cli=None):
    """主 TUI — H6 双栏风格：左栏品类列表，右栏模型预览。

    Args:
        families_by_cli: dict[str, list[dict]] — cli_name -> [{family, count}]
        cli_names: list[str] — ["claude", "codex"]
        last_used: dict[str, dict] or None — {cli_name: {"model", "cli", "model_info", ...}}
        families_detail: dict[str, dict] or None — {cli_name: {family: [model_list]}}
        provider_options_by_cli: dict[str, dict] or None — {cli_name: {model_name: [provider_options]}}

    Returns:
        ("family", cli_name, family_name) | ("last", cli_name, dict) |
        ("load_balance", cli_name, None) | ("settings", cli_name, None) |
        ("connect", cli_name, None) | ("provider_browse", cli_name, None) | None
    """
    families_detail = families_detail or {}

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        curses.init_pair(7, curses.COLOR_BLUE, -1)
        curses.init_pair(10, curses.COLOR_RED, -1)
        curses.init_pair(11, curses.COLOR_WHITE, -1)

        cli_idx = 0
        initial_last = ((last_used or {}).get(cli_names[0]) or {}) if cli_names else {}
        sel_idx = -1 if initial_last.get("model") else 0
        search_query = ""

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            if not cli_names:
                return None
            if cli_idx >= len(cli_names):
                cli_idx = max(0, len(cli_names) - 1)
            cli = cli_names[cli_idx]
            accent = _CLI_COLORS.get(cli, 1)
            ac = curses.color_pair(accent)
            families = families_by_cli.get(cli, [])
            detail = families_detail.get(cli, {})
            provider_options_map = (provider_options_by_cli or {}).get(cli, {})

            # 搜索过滤
            if search_query:
                q = search_query.lower()
                fams = [f for f in families if q in f["family"].lower()]
                if not fams:
                    fams = families
            else:
                fams = families

            # 上次使用
            cli_last = (last_used or {}).get(cli)
            has_last = cli_last and cli_last.get("model") and not search_query

            # 构建列表项：只有品类；上次使用保持独立显示，但参与默认焦点
            items = []
            for f in fams:
                items.append(("family", f))

            max_idx = len(items) - 1
            min_idx = -1 if has_last else 0
            if sel_idx < min_idx:
                sel_idx = min_idx
            if sel_idx > max_idx:
                sel_idx = max(0, len(items) - 1)

            # 尺寸
            total_w = min(60, max_w - 4)
            left_w = 22
            right_w = total_w - left_w
            ph = len(items) + 6 + (1 if search_query else 0) + (1 if has_last else 0)
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py

            # -- 顶线（CLI 色）--
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1

            # -- MMS + CLI tabs --
            _safe_addstr(stdscr, row, ll, "MMS", curses.color_pair(1) | curses.A_BOLD)
            tab_x = rr
            for i in range(len(cli_names) - 1, -1, -1):
                name = cli_names[i]
                label = name.upper() if i == cli_idx else name.lower()
                tab_x -= len(label)
                if i == cli_idx:
                    _safe_addstr(stdscr, row, tab_x, label, ac | curses.A_BOLD)
                    _safe_addstr(stdscr, row + 1, tab_x, "-" * len(label), ac)
                else:
                    _safe_addstr(stdscr, row, tab_x, label, curses.A_DIM)
                tab_x -= 4
            row += 2

            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            # -- 上次使用（独立区，但可选）--
            if has_last:
                last_model = _last_used_label(cli_last)
                is_last_sel = (sel_idx == -1)
                last_attr = curses.color_pair(4) | curses.A_BOLD | (curses.A_REVERSE if is_last_sel else 0)
                marker_attr = curses.color_pair(4) | curses.A_BOLD
                if is_last_sel:
                    _safe_addstr(stdscr, row, ll + 1, " " * (rr - ll - 1), last_attr)
                    _safe_addstr(stdscr, row, ll - 1, "|", marker_attr)
                else:
                    _safe_addstr(stdscr, row, ll, "<-", curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, row, ll + 1, _L("继续上次", "Resume Last"), last_attr)
                _safe_addstr(stdscr, row, ll + 11, last_model, last_attr, max_w=total_w - 24)
                _safe_addstr(stdscr, row, rr - 1, "R", last_attr if is_last_sel else curses.color_pair(4) | curses.A_DIM)
                row += 1

            # -- 搜索栏 --
            if search_query:
                _safe_addstr(stdscr, row, ll, f"/ {search_query}_", curses.color_pair(4) | curses.A_BOLD)
                info = f"{len(fams)}/{len(families)}"
                _safe_addstr(stdscr, row, lr - len(info), info, curses.A_DIM)
                row += 1

            # 双栏分隔
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            # -- 双栏内容 --
            content_y = row
            sel_fam_name = None

            for i, (itype, idata) in enumerate(items):
                y = content_y + i
                is_sel = (i == sel_idx)

                # 竖分割
                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                if itype == "family":
                    name = idata["family"]
                    count = idata["count"]
                    fc = curses.color_pair(_FAMILY_COLORS.get(name, 2))
                    if is_sel:
                        sel_fam_name = name
                        _safe_addstr(stdscr, y, ll + 1, " " * max(1, left_w - 4), curses.color_pair(1) | curses.A_REVERSE)
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, name, curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE)
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.color_pair(1) | curses.A_REVERSE)
                    else:
                        _safe_addstr(stdscr, y, ll, ".", fc | curses.A_DIM)
                        _safe_addstr(stdscr, y, ll + 2, name, curses.color_pair(2))
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.A_DIM)

            # -- 右栏预览 --
            if has_last and sel_idx == -1 and cli_last:
                model_names = [cli_last.get("model", "?")]
                fc = curses.color_pair(4)
                max_p = max(1, len(items))
                for mi, model in enumerate(model_names[:max_p]):
                    my = content_y + mi
                    attr = fc | curses.A_BOLD if mi == 0 else curses.color_pair(2)
                    _safe_addstr(stdscr, my, rl, model, attr, max_w=right_w - 3)
            elif sel_fam_name and detail.get(sel_fam_name):
                raw_models = detail[sel_fam_name]
                if raw_models and isinstance(raw_models[0], dict):
                    raw_models = sorted(
                        raw_models,
                        key=lambda item: (
                            -int(item.get("use_count", 0) or 0),
                            str(item.get("model", "")),
                        ),
                    )
                # raw_models 可能是 str 列表或 dict 列表（含 model/provider_id 等）
                model_names = []
                for m in raw_models:
                    if isinstance(m, dict):
                        model_names.append(m.get("model", str(m)))
                    else:
                        model_names.append(str(m))
                fc = curses.color_pair(_FAMILY_COLORS.get(sel_fam_name, 2))
                max_p = len(items)
                for mi, model in enumerate(model_names[:max_p]):
                    my = content_y + mi
                    attr = fc | curses.A_BOLD if mi == 0 else curses.color_pair(2)
                    _safe_addstr(stdscr, my, rl, model, attr, max_w=right_w - 3)
                if len(model_names) > max_p:
                    _safe_addstr(stdscr, content_y + max_p, rl,
                                 f"... +{len(model_names) - max_p}", curses.A_DIM)

            # -- 底栏 --
            bot_y = content_y + len(items)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if search_query:
                _safe_addstr(stdscr, bot_y, ll, _L("Esc 清除", "Esc Clear"), curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, _L("BS 删字", "BS Delete"), curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 20, _L("Enter 确认", "Enter Confirm"), curses.color_pair(1) | curses.A_DIM)
            else:
                _safe_addstr(stdscr, bot_y, ll, "Tab", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 4, _L("切CLI", "Switch CLI"), curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, "→", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 13, _L("进模型", "Models"), curses.color_pair(1) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 21, "L", curses.color_pair(5) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 23, _L("负载", "Load"), curses.color_pair(5) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 29, "S", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 31, _L("设置", "Settings"), curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 37, "P", curses.color_pair(6) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 39, _L("通道", "Channels"), curses.color_pair(6) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 45, "O", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 47, _L("接入", "Connect"), curses.color_pair(4) | curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                if not items and has_last:
                    sel_idx = -1
                elif items:
                    if has_last and sel_idx == 0:
                        sel_idx = -1
                    elif sel_idx == -1:
                        sel_idx = len(items) - 1
                    else:
                        sel_idx = (sel_idx - 1) % len(items)
            elif key == curses.KEY_DOWN:
                if not items and has_last:
                    sel_idx = -1
                elif items:
                    if has_last and sel_idx == -1:
                        sel_idx = 0
                    else:
                        sel_idx = (sel_idx + 1) % len(items)
            elif key in (9, ):
                cli_idx = (cli_idx + 1) % len(cli_names)
                next_cli = cli_names[cli_idx]
                next_last = (last_used or {}).get(next_cli)
                sel_idx = -1 if next_last and next_last.get("model") else 0
                search_query = ""
            elif key == curses.KEY_BTAB:
                cli_idx = (cli_idx - 1) % len(cli_names)
                next_cli = cli_names[cli_idx]
                next_last = (last_used or {}).get(next_cli)
                sel_idx = -1 if next_last and next_last.get("model") else 0
                search_query = ""
            elif key == curses.KEY_RIGHT:
                if has_last and sel_idx == -1:
                    return ("last", cli, cli_last)
                if not items:
                    continue
                itype, idata = items[sel_idx]
                if itype == "family":
                    family_name = idata["family"]
                    models = detail.get(family_name, [])
                    if not models:
                        continue
                    selected = select_submodel_tui(
                        family_name,
                        models,
                        provider_options=provider_options_map,
                        last_used=cli_last,
                        stdscr=stdscr,
                    )
                    if selected == "__last__":
                        return ("last", cli, cli_last)
                    if selected is not None:
                        if isinstance(selected, dict):
                            selected = dict(selected)
                            selected["_family_name"] = family_name
                        return ("submodel", cli, selected)
            elif key in (10, 13, curses.KEY_ENTER):
                if has_last and sel_idx == -1:
                    return ("last", cli, cli_last)
                if not items:
                    continue
                itype, idata = items[sel_idx]
                if itype == "family":
                    family_name = idata["family"]
                    models = detail.get(family_name, [])
                    if not models:
                        continue
                    selected = select_submodel_tui(
                        family_name,
                        models,
                        provider_options=provider_options_map,
                        last_used=cli_last,
                        stdscr=stdscr,
                    )
                    if selected == "__last__":
                        return ("last", cli, cli_last)
                    if selected is not None:
                        if isinstance(selected, dict):
                            selected = dict(selected)
                            selected["_family_name"] = family_name
                        return ("submodel", cli, selected)
            elif key in (ord('r'), ord('R')) and not search_query and has_last:
                return ("last", cli, cli_last)
            elif key in (ord('l'), ord('L')) and not search_query:
                return ("load_balance", cli, None)
            elif key in (ord('s'), ord('S')) and not search_query:
                return ("settings", cli, None)
            elif key in (ord('p'), ord('P')) and not search_query:
                return ("provider_browse", cli, None)
            elif key in (ord('o'), ord('O')) and not search_query:
                return ("connect", cli, None)
            elif key == 27:
                if search_query:
                    search_query = ""
                    sel_idx = -1 if has_last else 0
                else:
                    return None
            elif key in (ord('q'), ord('Q')) and not search_query:
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
                    sel_idx = -1 if has_last else 0
            elif 32 <= key <= 126:
                search_query += chr(key)
                sel_idx = 0

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


# ── 第 2 步：子模型选择 TUI ──────────────────────────────────

def select_submodel_tui(family_name, models, provider_options=None, last_used=None, stdscr=None):
    """子模型选择 TUI，P 键弹出 provider 列表，+/- 快速循环切换 provider。

    Args:
        family_name: str — 品类名
        models: list[dict] — [{"model": str, "provider_name": str, "provider_id": str, "provider_ctx": dict}]
        provider_options: dict or None — model_name -> [{"provider_name": str, "provider_id": str, "provider_ctx": dict}]
        last_used: dict or None — 当前 CLI 的上次使用记录
        stdscr: curses window or None — 传入时复用当前 TUI session，避免切页闪烁

    Returns:
        dict — 选中的 model entry (含 provider_ctx)，附带 "priority_changes": {provider_id: new_priority}
        "__last__" — 返回上一次使用
        None — 取消 (Esc)
    """
    if not models:
        return None

    sorted_models = sorted(
        models,
        key=lambda m: (
            -int(m.get("use_count", 0) or 0),
            str(m.get("model", "")),
        ),
    )

    # 当前每个模型的 provider 覆盖 (model_name -> provider info)
    provider_overrides = {}
    # provider priority 变更记录 (provider_id -> new_priority)
    priority_changes = {}

    def _effective_priority(opt):
        pid = opt.get("provider_id", "")
        if pid in priority_changes:
            return int(priority_changes[pid])
        return int((opt.get("provider_ctx") or {}).get("priority", 100) or 100)

    def _provider_choices(m):
        choices = []
        seen = set()

        current = {
            "provider_name": m.get("provider_name", ""),
            "provider_id": m.get("provider_id", ""),
            "provider_ctx": m.get("provider_ctx", {}),
        }
        current_id = current.get("provider_id")
        if current_id:
            choices.append(current)
            seen.add(current_id)

        for opt in provider_options.get(m["model"], []) if provider_options else []:
            pid = opt.get("provider_id", "")
            if not pid or pid in seen:
                continue
            choices.append(opt)
            seen.add(pid)

        choices.sort(
            key=lambda opt: (
                -_effective_priority(opt),
                opt.get("provider_name", ""),
            )
        )
        return choices

    def _active_provider_choice(m):
        override = provider_overrides.get(m["model"])
        if override:
            return override
        choices = _provider_choices(m)
        if choices:
            return choices[0]
        return {
            "provider_name": m.get("provider_name", ""),
            "provider_id": m.get("provider_id", ""),
            "provider_ctx": m.get("provider_ctx", {}),
        }

    def _get_provider_info(m):
        """返回当前生效的 (provider_name, provider_id, priority)"""
        active = _active_provider_choice(m)
        ctx = active.get("provider_ctx", {})
        name = active.get("provider_name", "")
        pid = active.get("provider_id", "")
        pri = _effective_priority(active)
        return name, pid, pri

    def _get_result(m):
        active = _active_provider_choice(m)
        result = {
            **m,
            "provider_name": active.get("provider_name", ""),
            "provider_id": active.get("provider_id", ""),
            "provider_ctx": {
                **(active.get("provider_ctx", {}) or {}),
                "priority": _effective_priority(active),
            },
        }
        if priority_changes:
            result["priority_changes"] = dict(priority_changes)
        return result

    def _record_priority_swap(m, chosen):
        new_pid = chosen.get("provider_id", "")
        orig_pid = m.get("provider_id", "")
        if not new_pid or not orig_pid or new_pid == orig_pid:
            return

        orig_pri = _effective_priority({
            "provider_id": orig_pid,
            "provider_ctx": m.get("provider_ctx", {}),
        })
        new_base = _effective_priority(chosen)

        # 当前系统语义是数字越大越优先；手动选中的 provider 应提升到默认前面。
        # 若用户已经用 +/- 显式调过任一通道，保留用户值，不在确认时覆盖。
        priority_changes.setdefault(new_pid, min(200, max(new_base, orig_pri) + 5))
        priority_changes.setdefault(orig_pid, max(0, min(orig_pri, new_base) - 5))

    def _adjust_provider_priority(opt, delta):
        pid = opt.get("provider_id", "")
        if not pid:
            return
        current = _effective_priority(opt)
        priority_changes[pid] = max(0, min(200, current + delta))

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        curses.init_pair(7, curses.COLOR_BLUE, -1)

        idx = 0
        scroll = 0
        provider_idx_map = {}
        focus = "model"
        search_query = ""

        def _sync_provider_cursor(m, pid):
            if not m or not pid:
                return
            choices = _provider_choices(m)
            for i, opt in enumerate(choices):
                if opt.get("provider_id") == pid:
                    provider_idx_map[m["model"]] = i
                    return
            provider_idx_map[m["model"]] = 0

        fam_color = _FAMILY_COLORS.get(family_name, 1)
        fc = curses.color_pair(fam_color)

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()

            # 搜索过滤
            if search_query:
                q = search_query.lower()
                filtered = [m for m in sorted_models if q in m["model"].lower()]
            else:
                filtered = sorted_models
            if not filtered:
                filtered = sorted_models

            if idx >= len(filtered):
                idx = max(0, len(filtered) - 1)

            # 尺寸
            total_w = min(60, max_w - 4)
            left_w = 28
            right_w = total_w - left_w
            visible = min(len(filtered), max_y - 8)
            ph = visible + 6 + (1 if search_query else 0)
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py

            # -- 顶线（品类色）--
            _safe_addstr(stdscr, row, px, "-" * total_w, fc)
            row += 1

            # -- 标题 --
            has_changes = bool(provider_overrides or priority_changes)
            title = f"{family_name}" + (" *" if has_changes else "")
            _safe_addstr(stdscr, row, ll, title, fc | curses.A_BOLD)
            cnt_info = f"{len(filtered)}/{len(sorted_models)}" if search_query else str(len(sorted_models))
            _safe_addstr(stdscr, row, rr - len(cnt_info) - 6, cnt_info, curses.A_DIM)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1

            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            # -- 搜索栏 --
            if search_query:
                _safe_addstr(stdscr, row, ll, f"/ {search_query}_", curses.color_pair(4) | curses.A_BOLD)
                row += 1

            model_header_attr = (curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE) if focus == "model" else (fc | curses.A_BOLD)
            provider_header_attr = (curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE) if focus == "provider" else curses.A_DIM
            _safe_addstr(stdscr, row, ll + 1, _L("模型", "Model"), model_header_attr)
            _safe_addstr(stdscr, row, rl + 1, _L("通道", "Channel"), provider_header_attr)
            row += 1

            # 双栏分隔
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            # 滚动
            content_y = row
            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            current_model = filtered[idx] if filtered else None
            current_choices = _provider_choices(current_model) if current_model else []
            active_provider_id = _get_provider_info(current_model)[1] if current_model else ""
            if current_model:
                model_name = current_model["model"]
                if model_name not in provider_idx_map:
                    active_idx = 0
                    for i, opt in enumerate(current_choices):
                        if opt.get("provider_id") == active_provider_id:
                            active_idx = i
                            break
                    provider_idx_map[model_name] = active_idx
                provider_idx_map[model_name] = max(0, min(provider_idx_map[model_name], max(0, len(current_choices) - 1)))

            for i in range(scroll, min(scroll + visible, len(filtered))):
                y = content_y + (i - scroll)
                m = filtered[i]
                is_sel = (i == idx)
                model_name = m["model"]
                prov_name, prov_id, prov_pri = _get_provider_info(m)

                # 竖分割
                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                # 左栏：模型名
                if is_sel:
                    marker_attr = fc | curses.A_BOLD if focus == "model" else curses.color_pair(4) | curses.A_BOLD
                    name_attr = curses.color_pair(1) | curses.A_BOLD | (curses.A_REVERSE if focus == "model" else 0)
                    if focus == "model":
                        _safe_addstr(stdscr, y, ll + 1, " " * max(1, left_w - 4), name_attr)
                    _safe_addstr(stdscr, y, ll - 1, "|", marker_attr)
                    _safe_addstr(stdscr, y, ll + 1, model_name, name_attr, max_w=left_w - 4)
                else:
                    _safe_addstr(stdscr, y, ll + 1, model_name, curses.color_pair(2), max_w=left_w - 4)

            provider_content_h = visible
            for offset in range(provider_content_h):
                y = content_y + offset
                if offset >= len(current_choices):
                    continue
                opt = current_choices[offset]
                is_provider_sel = (
                    current_model is not None
                    and provider_idx_map.get(current_model["model"], 0) == offset
                )
                opt_name = opt.get("provider_name", "")
                opt_pri = _effective_priority(opt)
                tag_text = f"{opt_name} P:{opt_pri}"
                if opt.get("provider_id") == active_provider_id:
                    tag_text += " *"

                if is_provider_sel:
                    marker_attr = curses.color_pair(4) | curses.A_BOLD if focus == "provider" else fc | curses.A_BOLD
                    text_attr = curses.color_pair(4) | curses.A_BOLD | (curses.A_REVERSE if focus == "provider" else 0)
                    if focus == "provider":
                        _safe_addstr(stdscr, y, rl + 1, " " * max(1, right_w - 4), text_attr)
                    _safe_addstr(stdscr, y, rl - 1, "|", marker_attr)
                    _safe_addstr(stdscr, y, rl + 1, tag_text, text_attr, max_w=right_w - 4)
                elif opt.get("provider_id") == active_provider_id:
                    _safe_addstr(stdscr, y, rl + 1, tag_text, curses.color_pair(5), max_w=right_w - 4)
                else:
                    _safe_addstr(stdscr, y, rl + 1, tag_text, curses.A_DIM, max_w=right_w - 4)

            # -- 底栏 --
            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if search_query:
                _safe_addstr(stdscr, bot_y, ll, _L("Esc 清除", "Esc Clear"), curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, _L("BS 删字", "BS Delete"), curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 20, _L("Enter 确认", "Enter Confirm"), curses.color_pair(1) | curses.A_DIM)
            else:
                focus_text = _L("模型", "Model") if focus == "model" else _L("通道", "Channel")
                _safe_addstr(stdscr, bot_y, ll, "←/→", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 5, _L(f"焦点:{focus_text}", f"Focus:{focus_text}"), curses.color_pair(4) | curses.A_DIM)
                if last_used and last_used.get("model"):
                    _safe_addstr(stdscr, bot_y, ll + 16, "R", curses.color_pair(5) | curses.A_BOLD)
                    _safe_addstr(stdscr, bot_y, ll + 18, _L("上次", "Last"), curses.color_pair(5) | curses.A_DIM)
                    adjust_x = ll + 24
                else:
                    adjust_x = ll + 16
                _safe_addstr(stdscr, bot_y, adjust_x, "+/-", curses.color_pair(5) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, adjust_x + 4, _L("权重", "Weight"), curses.color_pair(5) | curses.A_DIM)
                enter_x = adjust_x + 10
                _safe_addstr(stdscr, bot_y, enter_x, "Enter", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, enter_x + 6, _L("确认", "Confirm"), curses.A_DIM)
                _safe_addstr(stdscr, bot_y, enter_x + 12, "Esc", curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, enter_x + 16, _L("返回", "Back"), curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, fc)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                if focus == "provider" and current_model and current_choices:
                    model_name = current_model["model"]
                    provider_idx_map[model_name] = (provider_idx_map.get(model_name, 0) - 1) % len(current_choices)
                else:
                    idx = (idx - 1) % len(filtered)
            elif key == curses.KEY_DOWN:
                if focus == "provider" and current_model and current_choices:
                    model_name = current_model["model"]
                    provider_idx_map[model_name] = (provider_idx_map.get(model_name, 0) + 1) % len(current_choices)
                else:
                    idx = (idx + 1) % len(filtered)
            elif key == curses.KEY_RIGHT and not search_query:
                if current_choices:
                    focus = "provider"
            elif key == curses.KEY_LEFT and not search_query:
                if focus == "provider":
                    focus = "model"
                else:
                    return None
            elif key in (ord('r'), ord('R')) and not search_query and last_used and last_used.get("model"):
                return "__last__"
            elif key in (ord('+'), ord('=')) and not search_query:
                if focus == "provider" and current_model and current_choices:
                    chosen = current_choices[provider_idx_map.get(current_model["model"], 0)]
                    # 当前语义是数字越大越优先；"+" 应提升优先级并把通道往上排。
                    _adjust_provider_priority(chosen, +5)
                    _sync_provider_cursor(current_model, chosen.get("provider_id", ""))
            elif key in (ord('-'), ord('_')) and not search_query:
                if focus == "provider" and current_model and current_choices:
                    chosen = current_choices[provider_idx_map.get(current_model["model"], 0)]
                    _adjust_provider_priority(chosen, -5)
                    _sync_provider_cursor(current_model, chosen.get("provider_id", ""))
            elif key in (10, 13, curses.KEY_ENTER):
                if filtered:
                    m = filtered[idx]
                    if focus == "provider" and current_choices:
                        chosen = current_choices[provider_idx_map.get(m["model"], 0)]
                        provider_overrides[m["model"]] = chosen
                        _record_priority_swap(m, chosen)
                    else:
                        override = provider_overrides.get(m["model"])
                        if override:
                            _record_priority_swap(m, override)
                    return _get_result(m)
            elif key == 27:
                if search_query:
                    search_query = ""
                    idx = 0
                    scroll = 0
                    focus = "model"
                else:
                    return None
            elif key in (ord('q'), ord('Q')) and not search_query:
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
                    idx = 0
                    scroll = 0
            elif 32 <= key <= 126:
                # 可打印 ASCII 字符 → 搜索
                search_query += chr(key)
                idx = 0
                scroll = 0

    if stdscr is not None:
        try:
            return _inner(stdscr)
        except curses.error:
            return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


# ── 旧版兼容入口（保留签名，内部不再使用）──────────────────

def select_scene_tui(scenes, cli_names, source_choices=None, last_used=None, scene_counts=None):
    """旧版主 TUI，保留兼容。新流程使用 select_family_tui + select_submodel_tui。"""
    return None


# ── 简单模型列表 TUI ──────────────────────────────────────

def select_model_tui(models, title="选择模型"):
    if not models:
        return None

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        idx = 0
        scroll = 0
        search_query = ""

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            # 搜索过滤
            if search_query:
                q = search_query.lower()
                filtered = [m for m in models if q in m.lower()]
            else:
                filtered = models
            if not filtered:
                filtered = models

            if idx >= len(filtered):
                idx = max(0, len(filtered) - 1)

            visible = max_y - 5

            stdscr.addstr(0, 2, title, curses.color_pair(1) | curses.A_BOLD)
            header_y = 1
            if search_query:
                stdscr.addstr(1, 2, f"🔍 {search_query}_ ({len(filtered)}/{len(models)})", curses.color_pair(4) | curses.A_BOLD)
                header_y = 2
            else:
                stdscr.addstr(1, 2, f"{len(models)} models  ↑↓  Enter  输入搜索  Q", curses.A_DIM)
                header_y = 2

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(filtered))):
                y = header_y + 1 + i - scroll
                prefix = " ▸ " if i == idx else "   "
                line = f"{prefix}{i + 1:3d}. {filtered[i]}"
                attr = curses.color_pair(3) | curses.A_BOLD if i == idx else 0
                try:
                    stdscr.addstr(y, 1, line[:max_w - 2], attr)
                except curses.error:
                    pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(filtered)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(filtered)
            elif key in (10, 13, curses.KEY_ENTER):
                if filtered:
                    return filtered[idx]
            elif key == 27:
                if search_query:
                    search_query = ""
                    idx = 0
                    scroll = 0
                else:
                    return None
            elif key in (ord('q'), ord('Q')) and not search_query:
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
                    idx = 0
                    scroll = 0
            elif 32 <= key <= 126:
                search_query += chr(key)
                idx = 0
                scroll = 0

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


# ── 负载模式 TUI ──────────────────────────────────────────────

_LB_HISTORY_PATH = os.path.expanduser("~/.config/mms/lb_history.json")
_LB_SLOT_NAMES = ("heavy", "medium", "light")


def _lb_slot_model(slot_value):
    if isinstance(slot_value, dict):
        return str(slot_value.get("model", "")).strip()
    if isinstance(slot_value, str):
        return slot_value.strip()
    return ""


def _lb_slot_provider(slot_value):
    if not isinstance(slot_value, dict):
        return ""
    return str(slot_value.get("provider", "")).strip()


def _lb_choice_payload(heavy, medium, light, *, label="", slot_providers=None, profile_name=""):
    slot_providers = {k: v for k, v in (slot_providers or {}).items() if v}
    payload = {
        "model": heavy,
        "lb_medium": medium,
        "lb_light": light,
    }
    if label:
        payload["lb_label"] = label
    if slot_providers:
        payload["lb_slot_providers"] = slot_providers
    if profile_name:
        payload["lb_profile"] = profile_name
    return payload


def _lb_profile_option(profile_name, profile, default_profile=""):
    if not isinstance(profile, dict):
        return None
    heavy = _lb_slot_model(profile.get("heavy"))
    medium = _lb_slot_model(profile.get("medium"))
    light = _lb_slot_model(profile.get("light"))
    if not heavy:
        return None
    label = str(profile.get("label") or profile_name).strip() or profile_name
    if profile_name == default_profile:
        label = f"{label} / 默认"
    slot_providers = {
        slot: _lb_slot_provider(profile.get(slot))
        for slot in _LB_SLOT_NAMES
        if _lb_slot_provider(profile.get(slot))
    }
    return {
        "label": label,
        "heavy": heavy,
        "medium": medium,
        "light": light,
        "slot_providers": slot_providers,
        "profile_name": profile_name,
        "type": "profile",
    }


def _load_lb_history(default_entry=None):
    """读取负载模式历史。返回 {"default": {...}, "recent": [{...}, ...]}"""
    fallback = {"default": default_entry or {}, "recent": []}
    if not os.path.exists(_LB_HISTORY_PATH):
        return fallback
    try:
        with open(_LB_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return fallback
        return data
    except Exception:
        return fallback


def save_lb_history(heavy, medium, light, slot_providers=None, label=None):
    """保存一条负载模式选择到历史。保留最近 3 条。"""
    slot_providers = {k: v for k, v in (slot_providers or {}).items() if v}
    entry = {
        "heavy": heavy,
        "medium": medium,
        "light": light,
        "label": label or f"{heavy} / {medium} / {light}",
    }
    if slot_providers:
        entry["slot_providers"] = slot_providers
    history = _load_lb_history()
    recent = history.get("recent", [])
    # 去重
    recent = [
        r for r in recent
        if not (
            r.get("heavy") == heavy
            and r.get("medium") == medium
            and r.get("light") == light
            and (r.get("slot_providers") or {}) == slot_providers
        )
    ]
    recent.insert(0, entry)
    history["recent"] = recent[:3]
    try:
        os.makedirs(os.path.dirname(_LB_HISTORY_PATH), exist_ok=True)
        with open(_LB_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _delete_lb_recent(entry):
    """删除一条最近负载历史。"""
    history = _load_lb_history()
    recent = history.get("recent", [])
    slot_providers = {k: v for k, v in (entry.get("slot_providers") or {}).items() if v}
    filtered = [
        item for item in recent
        if not (
            item.get("heavy") == entry.get("heavy")
            and item.get("medium", "") == entry.get("medium", "")
            and item.get("light") == entry.get("light")
            and (item.get("slot_providers") or {}) == slot_providers
        )
    ]
    history["recent"] = filtered[:3]
    try:
        os.makedirs(os.path.dirname(_LB_HISTORY_PATH), exist_ok=True)
        with open(_LB_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _lb_option_label(option):
    label = str(option.get("label") or "").strip()
    combo = f"{option.get('heavy','')} / {option.get('medium','')} / {option.get('light','')}".strip()
    combo = combo.strip(" /")
    if option.get("type") == "custom":
        return label or "自定义..."
    if label == "自定义负载":
        return f"{label} · {combo}" if combo else label
    return label or combo


def select_load_balance_tui(available_models=None, families_detail=None, provider_options_map=None, profiles=None, default_profile=""):
    """负载模式 TUI — H6 风格：profiles + 最近 3 条 + 自定义。"""
    profile_options = []
    for profile_name, profile in (profiles or {}).items():
        option = _lb_profile_option(profile_name, profile, default_profile=default_profile)
        if option is not None:
            profile_options.append(option)
    profile_options.sort(key=lambda item: (0 if item.get("profile_name") == default_profile else 1, item.get("label", "")))

    def _build_options():
        history = _load_lb_history(default_entry=profile_options[0] if profile_options else {})
        recent = history.get("recent", [])
        opts = []
        opts.extend(profile_options)
        seen = set()
        for r in recent[:3]:
            key = (r["heavy"], r.get("medium", ""), r["light"], json.dumps(r.get("slot_providers", {}), sort_keys=True, ensure_ascii=False))
            if key not in seen:
                seen.add(key)
                opts.append({
                    "label": r.get("label") or f"{r['heavy']} / {r.get('medium','')} / {r['light']}",
                    "heavy": r["heavy"],
                    "medium": r.get("medium", ""),
                    "light": r["light"],
                    "slot_providers": r.get("slot_providers", {}),
                    "type": "recent",
                })
        opts.append({"label": "自定义...", "type": "custom"})
        return opts

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        options = _build_options()
        idx = 0
        pending_delete_key = None
        status_text = ""

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(5)

            total_w = min(60, max_w - 4)
            ph = len(options) + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "负载均衡", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, ll + 11, "heavy / medium / light", curses.A_DIM)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for i, opt in enumerate(options):
                y = row + i
                is_sel = (i == idx)
                label = _lb_option_label(opt)
                if is_sel:
                    _safe_addstr(stdscr, y, ll, " " * max(1, total_w - 4), curses.color_pair(1) | curses.A_REVERSE)
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, label, curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE, max_w=total_w - 6)
                elif opt.get("type") == "recent":
                    _safe_addstr(stdscr, y, ll + 1, label, curses.color_pair(4), max_w=total_w - 6)
                else:
                    _safe_addstr(stdscr, y, ll + 1, label, curses.color_pair(2), max_w=total_w - 6)

            bot_y = row + len(options)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if status_text:
                _safe_addstr(stdscr, bot_y, ll, status_text, curses.color_pair(4) | curses.A_DIM, max_w=total_w - 4)
                bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "确认", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "D", curses.color_pair(4) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 15, "删除(最近项)", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 28, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 32, "取消", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            status_text = ""
            if key == curses.KEY_UP:
                pending_delete_key = None
                idx = (idx - 1) % len(options)
            elif key == curses.KEY_DOWN:
                pending_delete_key = None
                idx = (idx + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                pending_delete_key = None
                chosen = options[idx]
                if chosen["type"] == "custom":
                    return "custom"
                return _lb_choice_payload(
                    chosen["heavy"],
                    chosen.get("medium", ""),
                    chosen["light"],
                    label=chosen.get("label", ""),
                    slot_providers=chosen.get("slot_providers", {}),
                    profile_name=chosen.get("profile_name", ""),
                )
            elif key in (ord('d'), ord('D')):
                chosen = options[idx]
                if chosen.get("type") != "recent":
                    pending_delete_key = None
                    status_text = "只能删除 recent 项"
                    continue
                chosen_key = (
                    chosen.get("heavy"),
                    chosen.get("medium", ""),
                    chosen.get("light"),
                    json.dumps(chosen.get("slot_providers", {}), sort_keys=True, ensure_ascii=False),
                )
                if pending_delete_key == chosen_key:
                    _delete_lb_recent(chosen)
                    options = _build_options()
                    idx = max(0, min(idx, len(options) - 1))
                    pending_delete_key = None
                    status_text = "已删除该最近项"
                else:
                    pending_delete_key = chosen_key
                    status_text = "再按一次 D 确认删除当前最近项"
            elif key in (ord('q'), ord('Q'), 27):
                pending_delete_key = None
                return None

    try:
        result = curses.wrapper(_inner)
    except curses.error:
        return None
    if result == "custom":
        return _select_lb_custom_tui(families_detail, provider_options_map)
    return result


def _select_lb_custom_tui(families_detail=None, provider_options_map=None):
    """负载自定义 TUI — H6 风格：3 slot + 启动。"""
    SLOT_NAMES = ["heavy", "medium", "light"]
    SLOT_COLORS = {"heavy": 3, "medium": 4, "light": 5}  # red, yellow, green
    slots = {s: {"model": "(未选)", "provider_name": "", "provider_id": "", "provider_ctx": {}} for s in SLOT_NAMES}
    family_names = list((families_detail or {}).keys())

    def _pick_model_for_slot(stdscr):
        """品类 → 子模型，H6 风格。"""
        fam_idx = 0
        fam_scroll = 0
        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)
            total_w = min(50, max_w - 4)
            visible = min(len(family_names), max_y - 7)
            ph = visible + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "选择品类", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            if fam_idx < fam_scroll:
                fam_scroll = fam_idx
            elif fam_idx >= fam_scroll + visible:
                fam_scroll = fam_idx - visible + 1

            content_y = row
            for fi in range(fam_scroll, min(fam_scroll + visible, len(family_names))):
                fy = content_y + (fi - fam_scroll)
                is_sel = (fi == fam_idx)
                cnt = len((families_detail or {}).get(family_names[fi], []))
                fc = curses.color_pair(_FAMILY_COLORS.get(family_names[fi], 2))
                if is_sel:
                    _safe_addstr(stdscr, fy, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, fy, ll + 1, family_names[fi], curses.color_pair(1) | curses.A_BOLD)
                    _safe_addstr(stdscr, fy, rr - len(str(cnt)), str(cnt), curses.color_pair(1))
                else:
                    _safe_addstr(stdscr, fy, ll, ".", fc | curses.A_DIM)
                    _safe_addstr(stdscr, fy, ll + 2, family_names[fi], curses.color_pair(2))
                    _safe_addstr(stdscr, fy, rr - len(str(cnt)), str(cnt), curses.A_DIM)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "展开", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                fam_idx = (fam_idx - 1) % len(family_names)
            elif key == curses.KEY_DOWN:
                fam_idx = (fam_idx + 1) % len(family_names)
            elif key in (10, 13, curses.KEY_ENTER):
                chosen_fam = family_names[fam_idx]
                model_list = (families_detail or {}).get(chosen_fam, [])
                if not model_list:
                    continue
                result = _pick_submodel(stdscr, chosen_fam, model_list)
                if result is not None:
                    return result
            elif key == 27:
                return None

    def _pick_submodel(stdscr, fam_name, model_list):
        """子模型选择，H6 双栏风格。"""
        m_idx = 0
        m_scroll = 0
        fc = curses.color_pair(_FAMILY_COLORS.get(fam_name, 1))
        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            total_w = min(56, max_w - 4)
            left_w = 26
            right_w = total_w - left_w
            visible = min(len(model_list), max_y - 7)
            ph = visible + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, fc)
            row += 1
            _safe_addstr(stdscr, row, ll, fam_name, fc | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            if m_idx < m_scroll:
                m_scroll = m_idx
            elif m_idx >= m_scroll + visible:
                m_scroll = m_idx - visible + 1

            content_y = row
            for mi in range(m_scroll, min(m_scroll + visible, len(model_list))):
                my = content_y + (mi - m_scroll)
                me = model_list[mi]
                is_sel = (mi == m_idx)
                mname = me.get("model", "") if isinstance(me, dict) else str(me)
                mprov = me.get("provider_name", "") if isinstance(me, dict) else ""
                mpri = me.get("provider_ctx", {}).get("priority", "") if isinstance(me, dict) else ""
                tag = f"{mprov} P:{mpri}" if mprov else ""

                _safe_addstr(stdscr, my, px + left_w, "|", curses.A_DIM)
                if is_sel:
                    _safe_addstr(stdscr, my, ll - 1, "|", fc | curses.A_BOLD)
                    _safe_addstr(stdscr, my, ll + 1, mname, curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                    if tag:
                        _safe_addstr(stdscr, my, rl, tag, curses.color_pair(4) | curses.A_BOLD, max_w=right_w - 3)
                else:
                    _safe_addstr(stdscr, my, ll + 1, mname, curses.color_pair(2), max_w=left_w - 4)
                    if tag:
                        _safe_addstr(stdscr, my, rl, tag, curses.A_DIM, max_w=right_w - 3)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "选择", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, fc)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                m_idx = (m_idx - 1) % len(model_list)
            elif key == curses.KEY_DOWN:
                m_idx = (m_idx + 1) % len(model_list)
            elif key in (10, 13, curses.KEY_ENTER):
                return model_list[m_idx]
            elif key == 27:
                return None

    def _lb_cycle_provider(slot, direction):
        model_name = slot.get("model", "")
        if not model_name or model_name == "(未选)" or not provider_options_map:
            return
        opts = provider_options_map.get(model_name, [])
        if len(opts) <= 1:
            return
        cur_id = slot.get("provider_id", "")
        cur_idx = 0
        for i, opt in enumerate(opts):
            if opt.get("provider_id") == cur_id:
                cur_idx = i
                break
        new_idx = (cur_idx + direction) % len(opts)
        chosen = opts[new_idx]
        slot["provider_name"] = chosen.get("provider_name", "")
        slot["provider_id"] = chosen.get("provider_id", "")
        slot["provider_ctx"] = chosen.get("provider_ctx", {})

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        n_items = 4  # 3 slots + launch
        idx = 0

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(5)

            total_w = min(56, max_w - 4)
            ph = 12
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "自定义负载", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for si, sname in enumerate(SLOT_NAMES):
                y = row + si * 2
                is_sel = (si == idx)
                slot = slots[sname]
                model = slot["model"]
                prov = slot["provider_name"]
                pri = slot["provider_ctx"].get("priority", "")
                sc = curses.color_pair(SLOT_COLORS[sname])

                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, sname.capitalize(), sc | curses.A_BOLD)
                    _safe_addstr(stdscr, y + 1, ll + 3, model, curses.color_pair(1) | curses.A_BOLD, max_w=total_w - 10)
                    if prov:
                        tag = f"{prov} P:{pri}"
                        _safe_addstr(stdscr, y, rr - len(tag), tag, curses.color_pair(4))
                else:
                    _safe_addstr(stdscr, y, ll + 1, sname.capitalize(), sc | curses.A_DIM)
                    _safe_addstr(stdscr, y + 1, ll + 3, model, curses.color_pair(2))

            # 启动按钮
            launch_y = row + 6
            is_launch = (idx == 3)
            can_launch = slots["heavy"]["model"] != "(未选)"
            _safe_addstr(stdscr, launch_y, px, "-" * total_w, curses.A_DIM)
            launch_y += 1
            if is_launch:
                _safe_addstr(stdscr, launch_y, ll - 1, "|", ac | curses.A_BOLD)
            if can_launch:
                la = curses.color_pair(5) | curses.A_BOLD if is_launch else curses.color_pair(5)
                _safe_addstr(stdscr, launch_y, ll + 1, "启动", la)
            else:
                _safe_addstr(stdscr, launch_y, ll + 1, "启动 (请先选 Heavy)", curses.A_DIM)

            bot_y = launch_y + 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "编辑/启动", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 18, "+/-", curses.color_pair(5) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 22, "切通道", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 31, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 35, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % n_items
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % n_items
            elif key in (10, 13, curses.KEY_ENTER):
                if idx < 3:
                    if not family_names:
                        continue
                    chosen = _pick_model_for_slot(stdscr)
                    if chosen is not None:
                        sname = SLOT_NAMES[idx]
                        if isinstance(chosen, dict):
                            slots[sname] = {
                                "model": chosen.get("model", ""),
                                "provider_name": chosen.get("provider_name", ""),
                                "provider_id": chosen.get("provider_id", ""),
                                "provider_ctx": chosen.get("provider_ctx", {}),
                            }
                        else:
                            slots[sname] = {"model": str(chosen), "provider_name": "", "provider_id": "", "provider_ctx": {}}
                elif can_launch:
                    slot_providers = {
                        slot_name: slot.get("provider_id", "")
                        for slot_name, slot in slots.items()
                        if slot.get("provider_id")
                    }
                    return _lb_choice_payload(
                        slots["heavy"]["model"],
                        slots["medium"]["model"] if slots["medium"]["model"] != "(未选)" else "",
                        slots["light"]["model"] if slots["light"]["model"] != "(未选)" else "",
                        label="自定义负载",
                        slot_providers=slot_providers,
                    )
            elif key in (ord('+'), ord('=')):
                if idx < 3:
                    _lb_cycle_provider(slots[SLOT_NAMES[idx]], +1)
            elif key in (ord('-'), ord('_')):
                if idx < 3:
                    _lb_cycle_provider(slots[SLOT_NAMES[idx]], -1)
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


# ── 统一设置面板 TUI ──────────────────────────────────────

def _settings_menu():
    return [
        {"id": "provider_mgmt", "label": _L("Provider 管理", "Provider Management"), "desc": _L("查看/调整 role 与 priority", "Inspect and adjust role / priority")},
        {"id": "account_mgmt", "label": _L("账号管理", "Account Management"), "desc": _L("查看 OAuth 账号状态", "Inspect OAuth account status")},
        {"id": "recommend", "label": _L("推荐模型", "Recommended Models"), "desc": _L("编辑推荐模型列表", "Edit the recommended model list")},
        {"id": "routes_export", "label": _L("路由导出", "Export Routes"), "desc": _L("导出 model-routes.json", "Export model-routes.json")},
        {"id": "about", "label": _L("关于", "About"), "desc": _L("版本与环境信息", "Version and environment info")},
    ]


def select_settings_tui():
    """设置菜单 — H6 风格。"""

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        idx = 0
        while True:
            items = _settings_menu()
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(56, max_w - 4)
            ph = len(items) + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, _L("设置", "Settings"), curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for i, item in enumerate(items):
                y = row + i
                is_sel = (i == idx)
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(1) | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 18, item["desc"], curses.color_pair(1) | curses.A_DIM)
                else:
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(2))
                    _safe_addstr(stdscr, y, ll + 18, item["desc"], curses.A_DIM)

            bot_y = row + len(items)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, _L("进入", "Open"), curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, _L("返回", "Back"), curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(items)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(items)
            elif key in (10, 13, curses.KEY_ENTER):
                return items[idx]["id"]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


# ── Provider 浏览 TUI（首页 P 键入口） ──────────────────────

def select_provider_browse_tui(providers):
    """Provider 列表 — H6 风格。"""
    if not providers:
        return None

    _ROLE_COLORS = {"primary": 3, "auto": 4, "fallback": 5}
    providers = sorted(
        providers,
        key=lambda p: (
            -int(p.get("priority", 100) or 100),
            p.get("name", p.get("id", "")),
        ),
    )

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(60, max_w - 4)
            left_w = 24
            right_w = total_w - left_w
            visible = min(len(providers), max_y - 7)
            ph = visible + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "通道浏览", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            content_y = row
            for i in range(scroll, min(scroll + visible, len(providers))):
                y = content_y + (i - scroll)
                p = providers[i]
                is_sel = (i == idx)
                name = p.get("name", p.get("id", "?"))
                role = p.get("role", "auto")
                pri = p.get("priority", 100)
                rc = curses.color_pair(_ROLE_COLORS.get(role, 2))

                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, name, curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                    _safe_addstr(stdscr, y, rl, f"{role} P:{pri}", rc | curses.A_BOLD)
                else:
                    _safe_addstr(stdscr, y, ll + 1, name, curses.color_pair(2), max_w=left_w - 4)
                    _safe_addstr(stdscr, y, rl, f"{role} P:{pri}", rc | curses.A_DIM)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "R", curses.color_pair(4) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 2, "角色", curses.color_pair(4) | curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 8, "+/-", curses.color_pair(5) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 12, "优先级", curses.color_pair(5) | curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 21, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 27, "模型", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 34, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 38, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(providers)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(providers)
            elif key in (10, 13, curses.KEY_ENTER):
                p = providers[idx]
                return (p.get("id"), p.get("name", p.get("id")))
            elif key in (ord('r'), ord('R')):
                _ROLE_CYCLE = ["auto", "primary", "fallback"]
                p = providers[idx]
                cur = p.get("role", "auto")
                try:
                    ni = (_ROLE_CYCLE.index(cur) + 1) % len(_ROLE_CYCLE)
                except ValueError:
                    ni = 0
                p["role"] = _ROLE_CYCLE[ni]
                p["_changed"] = True
            elif key in (ord('+'), ord('=')):
                providers[idx]["priority"] = min(200, providers[idx].get("priority", 100) + 5)
                providers[idx]["_changed"] = True
                selected_id = providers[idx].get("id")
                providers.sort(key=lambda p: (-int(p.get("priority", 100) or 100), p.get("name", p.get("id", ""))))
                idx = next((i for i, item in enumerate(providers) if item.get("id") == selected_id), idx)
            elif key in (ord('-'), ord('_')):
                providers[idx]["priority"] = max(0, providers[idx].get("priority", 100) - 5)
                providers[idx]["_changed"] = True
                selected_id = providers[idx].get("id")
                providers.sort(key=lambda p: (-int(p.get("priority", 100) or 100), p.get("name", p.get("id", ""))))
                idx = next((i for i, item in enumerate(providers) if item.get("id") == selected_id), idx)
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_provider_models_tui(provider_name, models):
    """Provider 模型列表 — H6 风格。"""
    if not models:
        return None
    sorted_models = sorted(models)

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        idx = 0
        scroll = 0
        search = ""

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            if search:
                filtered = [m for m in sorted_models if search.lower() in m.lower()]
                if not filtered:
                    filtered = sorted_models
            else:
                filtered = sorted_models
            if idx >= len(filtered):
                idx = max(0, len(filtered) - 1)

            total_w = min(50, max_w - 4)
            visible = min(len(filtered), max_y - 7)
            ph = visible + 5 + (1 if search else 0)
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, provider_name, curses.color_pair(1) | curses.A_BOLD)
            cnt = str(len(filtered))
            _safe_addstr(stdscr, row, rr - len(cnt) - 6, cnt, curses.A_DIM)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            if search:
                _safe_addstr(stdscr, row, ll, f"/ {search}_", curses.color_pair(4) | curses.A_BOLD)
                row += 1

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            content_y = row
            for i in range(scroll, min(scroll + visible, len(filtered))):
                y = content_y + (i - scroll)
                is_sel = (i == idx)
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, filtered[i], curses.color_pair(1) | curses.A_BOLD, max_w=total_w - 6)
                else:
                    _safe_addstr(stdscr, y, ll + 1, filtered[i], curses.color_pair(2), max_w=total_w - 6)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "选择", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "B", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 15, "返回", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 22, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 26, "退出", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(filtered)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(filtered)
            elif key in (10, 13, curses.KEY_ENTER):
                if filtered:
                    return {"model": filtered[idx]}
            elif key in (ord('b'), ord('B')) and not search:
                return None
            elif key == 27:
                if search:
                    search = ""
                    idx = 0
                else:
                    return "__exit__"
            elif key in (ord('q'), ord('Q')) and not search:
                return "__exit__"
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search:
                    search = search[:-1]
                    idx = 0
            elif 32 <= key <= 126:
                search += chr(key)
                idx = 0

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_provider_mgmt_tui(providers):
    """Provider 管理 — H6 风格。"""
    if not providers:
        return None

    ROLE_CYCLE = ["auto", "primary", "fallback"]
    _ROLE_COLORS = {"primary": 3, "auto": 4, "fallback": 5}

    import copy
    items = copy.deepcopy(providers)
    items.sort(
        key=lambda p: (
            -int(p.get("priority", 100) or 100),
            p.get("name") or p.get("id", ""),
        ),
    )
    changed = False

    def _inner(stdscr):
        nonlocal items, changed
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(60, max_w - 4)
            left_w = 24
            right_w = total_w - left_w
            visible = min(len(items), max_y - 7)
            ph = visible + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            title = "通道管理" + (" *" if changed else "")
            _safe_addstr(stdscr, row, ll, title, curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            content_y = row
            for i in range(scroll, min(scroll + visible, len(items))):
                y = content_y + (i - scroll)
                p = items[i]
                is_sel = (i == idx)
                name = p.get("name") or p.get("id", "?")
                role = p.get("role", "auto")
                pri = p.get("priority", 100)
                enabled = p.get("enabled", True)
                rc = curses.color_pair(_ROLE_COLORS.get(role, 2))

                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, name, curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                    info = f"{role} P:{pri}"
                    if not enabled:
                        info += " [off]"
                    _safe_addstr(stdscr, y, rl, info, rc | curses.A_BOLD)
                else:
                    name_attr = curses.color_pair(2) if enabled else curses.A_DIM
                    _safe_addstr(stdscr, y, ll + 1, name, name_attr, max_w=left_w - 4)
                    info = f"{role} P:{pri}"
                    if not enabled:
                        info += " [off]"
                    _safe_addstr(stdscr, y, rl, info, rc | curses.A_DIM)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "R", curses.color_pair(4) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 2, "角色", curses.color_pair(4) | curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 8, "+/-", curses.color_pair(5) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 12, "优先级", curses.color_pair(5) | curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 21, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 27, "保存", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 34, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 38, "取消", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(items)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(items)
            elif key in (ord('r'), ord('R')):
                p = items[idx]
                cur = p.get("role", "auto")
                try:
                    ni = (ROLE_CYCLE.index(cur) + 1) % len(ROLE_CYCLE)
                except ValueError:
                    ni = 0
                p["role"] = ROLE_CYCLE[ni]
                changed = True
            elif key in (ord('+'), ord('=')):
                items[idx]["priority"] = min(200, items[idx].get("priority", 100) + 5)
                changed = True
                selected_id = items[idx].get("id")
                items.sort(key=lambda p: (-int(p.get("priority", 100) or 100), p.get("name") or p.get("id", "")))
                idx = next((i for i, item in enumerate(items) if item.get("id") == selected_id), idx)
            elif key in (ord('-'), ord('_')):
                items[idx]["priority"] = max(0, items[idx].get("priority", 100) - 5)
                changed = True
                selected_id = items[idx].get("id")
                items.sort(key=lambda p: (-int(p.get("priority", 100) or 100), p.get("name") or p.get("id", "")))
                idx = next((i for i, item in enumerate(items) if item.get("id") == selected_id), idx)
            elif key in (10, 13, curses.KEY_ENTER):
                if changed:
                    return items
                return None
            elif key == 27:
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_manage_target_tui(targets):
    """通道管理列表 — H6 风格。

    Args:
        targets: list[dict] — [{kind, id, title, summary, default_label, status, launches, last_used_at}]

    Returns:
        dict — 选中的 target
        None — 取消
    """
    if not targets:
        return None

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(64, max_w - 4)
            left_w = 24
            right_w = total_w - left_w
            visible = min(len(targets), max_y - 7)
            ph = visible + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            lr = px + left_w - 1
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "管理通道", curses.color_pair(1) | curses.A_BOLD)
            cnt = f"{len(targets)}"
            _safe_addstr(stdscr, row, rr - len(cnt) - 6, cnt, curses.A_DIM)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            content_y = row
            for i in range(scroll, min(scroll + visible, len(targets))):
                y = content_y + (i - scroll)
                t = targets[i]
                is_sel = (i == idx)
                title = t.get("title", t.get("id", "?"))
                kind = t.get("kind", "")
                status = t.get("status", "")
                default_label = t.get("default_label", "")
                launches = t.get("launches", 0)

                kind_label = "官方" if kind == "account" else "网关"
                kind_color = curses.color_pair(6) if kind == "account" else curses.color_pair(4)

                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, title, curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                    info = f"{kind_label}  {default_label}  {status}  {launches}次"
                    _safe_addstr(stdscr, y, rl, info, curses.color_pair(1) | curses.A_DIM, max_w=right_w - 3)
                else:
                    _safe_addstr(stdscr, y, ll + 1, title, curses.color_pair(2), max_w=left_w - 4)
                    info = f"{kind_label}  {default_label}  {launches}次"
                    _safe_addstr(stdscr, y, rl, info, kind_color | curses.A_DIM, max_w=right_w - 3)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "管理", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(targets)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(targets)
            elif key in (10, 13, curses.KEY_ENTER):
                return targets[idx]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_channel_action_tui(title, info_lines, actions):
    """通道详情+操作选择 — H6 风格。

    Args:
        title: str — 页面标题
        info_lines: list[(label, value)] — 信息行
        actions: list[(id, label)] — 操作列表

    Returns:
        action_id (str) — 选中的操作
        None — 取消
    """
    if not actions:
        return None

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(60, max_w - 4)
            ph = len(info_lines) + len(actions) + 6
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, title, curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            # 信息区
            for label, value in info_lines:
                _safe_addstr(stdscr, row, ll + 1, label, curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, row, ll + 12, str(value), curses.color_pair(2), max_w=total_w - 16)
                row += 1

            # 分隔
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            # 操作列表
            for i, (aid, alabel) in enumerate(actions):
                y = row + i
                is_sel = (i == idx)
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, alabel, curses.color_pair(1) | curses.A_BOLD)
                else:
                    _safe_addstr(stdscr, y, ll + 1, alabel, curses.color_pair(2))

            bot_y = row + len(actions)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, "执行", curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(actions)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(actions)
            elif key in (10, 13, curses.KEY_ENTER):
                return actions[idx][0]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_connect_tui():
    """接入通道选择 — H6 风格。"""
    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        while True:
            actions = _connect_actions()
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(5)

            total_w = min(56, max_w - 4)
            left_w = 18
            right_w = total_w - left_w
            ph = len(actions) + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rl = px + left_w + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, _L("接入通道", "Connect Channels"), curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            content_y = row
            for i, action in enumerate(actions):
                y = content_y + i
                is_sel = (i == idx)
                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, action["title"], curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                    _safe_addstr(stdscr, y, rl, action["summary"], curses.color_pair(1) | curses.A_DIM, max_w=right_w - 3)
                else:
                    _safe_addstr(stdscr, y, ll + 1, action["title"], curses.color_pair(2), max_w=left_w - 4)
                    _safe_addstr(stdscr, y, rl, action["summary"], curses.A_DIM, max_w=right_w - 3)

            bot_y = content_y + len(actions)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, _L("进入", "Open"), curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, _L("返回", "Back"), curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(actions)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(actions)
            elif key in (10, 13, curses.KEY_ENTER):
                return actions[idx]["id"]
            elif key in (27, ord("q"), ord("Q")):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


def confirm_tui(cli, model_info, env_vars=None, once=False):
    """确认启动 TUI。返回 (action, bypass) 二元组。
    action: "" = 启动, "b" = 返回, "q" = 取消
    bypass: bool, 仅 codex/claude 有效，True 时附加 --dangerously-bypass-approvals-and-sandbox
    """
    if isinstance(model_info, dict):
        model_display = ", ".join(f"{k}={v}" for k, v in model_info.items()
                                  if k != "subagent")
    else:
        model_display = str(model_info)

    env_lines = []
    if env_vars:
        for k, v in env_vars.items():
            if "key" in k.lower() or "token" in k.lower() or "auth" in k.lower():
                display_v = v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
            else:
                display_v = v
            env_lines.append(f"{k}={display_v}")

    detail_lines = []
    if env_vars:
        preferred_keys = [
            ("ANTHROPIC_BASE_URL", "URL"),
            ("OPENAI_BASE_URL", "URL"),
            ("ANTHROPIC_AUTH_TOKEN", "Key"),
            ("OPENAI_API_KEY", "Key"),
            ("GEMINI_API_KEY", "Key"),
            ("MMS_ACTIVE_MODEL", _L("激活", "Active")),
            ("MMS_ACTIVE_PRESET", _L("预设", "Preset")),
            ("MMS_ACTIVE_CLI", _L("CLI源", "CLI source")),
        ]
        seen = set()
        for env_key, label in preferred_keys:
            if env_key in env_vars:
                value = env_vars.get(env_key, "")
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                detail_lines.append((label, value))
                seen.add(env_key)
        for env_key, value in env_vars.items():
            if env_key in seen:
                continue
            upper_key = env_key.upper()
            if any(token in upper_key for token in ("BASE_URL", "API_KEY", "AUTH_TOKEN", "ACTIVE_", "MODEL")):
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                label = env_key[:6] + "…" if len(env_key) > 7 else env_key
                detail_lines.append((label, value))
        detail_lines = detail_lines[:4]

    has_bypass = cli in ("codex", "claude")

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        bypass_mode = True

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(3) if bypass_mode else curses.color_pair(5)

            total_w = min(56, max_w - 4)
            info_lines = []
            info_lines.append(("CLI", cli))
            info_lines.append((_L("模型", "Model"), model_display[:total_w - 14]))
            info_lines.append((_L("启动", "Launch"), _L("一次性命令", "One-shot command") if once else _L("交互会话", "Interactive session")))
            if has_bypass:
                mode_text = _L("BYPASS（跳过审批）", "BYPASS (skip approvals)") if bypass_mode else _L("正常", "Normal")
                info_lines.append((_L("模式", "Mode"), f"[Tab] {mode_text}"))

            ph = len(info_lines) + len(detail_lines) + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            title = _L("BYPASS 确认", "BYPASS Confirm") if bypass_mode else _L("确认启动", "Confirm Launch")
            _safe_addstr(stdscr, row, ll, title, ac | curses.A_BOLD)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for label, value in info_lines:
                if label in {"模式", "Mode"}:
                    val_attr = curses.color_pair(3) | curses.A_BOLD if bypass_mode else curses.color_pair(5)
                else:
                    val_attr = curses.color_pair(1)
                _safe_addstr(stdscr, row, ll + 1, label, curses.A_DIM)
                _safe_addstr(stdscr, row, ll + 7, value, val_attr, max_w=total_w - 12)
                row += 1

            for label, value in detail_lines:
                _safe_addstr(stdscr, row, ll + 1, label, curses.A_DIM)
                _safe_addstr(stdscr, row, ll + 7, str(value), curses.color_pair(2), max_w=total_w - 12)
                row += 1

            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, ll, "Enter", curses.color_pair(5) | curses.A_BOLD)
            _safe_addstr(stdscr, row, ll + 6, _L("启动", "Launch"), curses.color_pair(5) | curses.A_DIM)
            if has_bypass:
                _safe_addstr(stdscr, row, ll + 13, "Tab", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, row, ll + 17, _L("切模式", "Switch mode"), curses.color_pair(4) | curses.A_DIM)
            _safe_addstr(stdscr, row, ll + 27, "B", curses.A_BOLD)
            _safe_addstr(stdscr, row, ll + 29, _L("返回", "Back"), curses.A_DIM)
            _safe_addstr(stdscr, row, ll + 36, "Q", curses.A_BOLD)
            _safe_addstr(stdscr, row, ll + 38, _L("取消", "Cancel"), curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return ("", bypass_mode)
            elif key in (ord('b'), ord('B')):
                return ("b", False)
            elif key in (ord('q'), ord('Q'), 27):
                return ("q", False)
            elif key == 9 and has_bypass:
                bypass_mode = not bypass_mode

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return ("q", False)
