"""MMS curses TUI：箭头键交互选择器 — v2 品类模式"""

import curses
import json
import locale
import os
import sys
import unicodedata

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


CONNECT_ACTIONS = [
    {
        "id": "connect_gateway",
        "title": "添加网关通道",
        "summary": "输入 API URL 和 API Key，接入 newapi 或兼容网关",
    },
    {
        "id": "connect_official",
        "title": "添加官方通道",
        "summary": "创建 OAuth 账号并进入官方登录流程",
    },
    {
        "id": "manage_channels",
        "title": "管理现有通道",
        "summary": "查看状态、设默认、删除通道、查看本地统计",
    },
    {
        "id": "migrate_config",
        "title": "迁移配置到 mms",
        "summary": "把旧 ccs 配置、账号目录和统计统一迁到 mms 路径",
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


def select_family_tui(families_by_cli, cli_names, last_used=None, families_detail=None):
    """主 TUI — H6 双栏风格：左栏品类列表，右栏模型预览。

    Args:
        families_by_cli: dict[str, list[dict]] — cli_name -> [{family, count}]
        cli_names: list[str] — ["claude", "codex"]
        last_used: dict[str, dict] or None — {cli_name: {"model", "cli", "model_info", ...}}
        families_detail: dict[str, dict] or None — {cli_name: {family: [model_list]}}

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
        sel_idx = 0
        search_query = ""

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            cli = cli_names[cli_idx]
            accent = _CLI_COLORS.get(cli, 1)
            ac = curses.color_pair(accent)
            families = families_by_cli.get(cli, [])
            detail = families_detail.get(cli, {})

            # 搜索过滤
            if search_query:
                q = search_query.lower()
                fams = [f for f in families if q in f["family"].lower()]
                if not fams:
                    fams = families
            else:
                fams = families

            # 构建列表项：(type, data)
            items = []
            cli_last = (last_used or {}).get(cli)
            if cli_last and cli_last.get("model") and not search_query:
                items.append(("last", cli_last))
            for f in fams:
                items.append(("family", f))

            if sel_idx >= len(items):
                sel_idx = max(0, len(items) - 1)

            # 尺寸
            total_w = min(60, max_w - 4)
            left_w = 22
            right_w = total_w - left_w
            ph = len(items) + 6 + (1 if search_query else 0)
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

                if itype == "last":
                    model = idata.get("model", "?")
                    if is_sel:
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, model, curses.color_pair(4) | curses.A_BOLD, max_w=left_w - 8)
                        _safe_addstr(stdscr, y, lr - 2, "<-", curses.color_pair(4))
                    else:
                        _safe_addstr(stdscr, y, ll, "<-", curses.color_pair(4) | curses.A_DIM)
                        _safe_addstr(stdscr, y, ll + 3, model, curses.color_pair(4), max_w=left_w - 8)

                elif itype == "family":
                    name = idata["family"]
                    count = idata["count"]
                    fc = curses.color_pair(_FAMILY_COLORS.get(name, 2))
                    if is_sel:
                        sel_fam_name = name
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, name, curses.color_pair(1) | curses.A_BOLD)
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.color_pair(1))
                    else:
                        _safe_addstr(stdscr, y, ll, ".", fc | curses.A_DIM)
                        _safe_addstr(stdscr, y, ll + 2, name, curses.color_pair(2))
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.A_DIM)

            # -- 右栏预览 --
            if sel_fam_name and detail.get(sel_fam_name):
                raw_models = detail[sel_fam_name]
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
            elif items and items[sel_idx][0] == "last":
                _safe_addstr(stdscr, content_y, rl, "继续上次", curses.color_pair(1) | curses.A_DIM)

            # -- 底栏 --
            bot_y = content_y + len(items)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if search_query:
                _safe_addstr(stdscr, bot_y, ll, "Esc 清除", curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, "BS 删字", curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 20, "Enter 确认", curses.color_pair(1) | curses.A_DIM)
            else:
                _safe_addstr(stdscr, bot_y, ll, "L", curses.color_pair(5) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 2, "负载", curses.color_pair(5) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 8, "S", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 10, "设置", curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 16, "P", curses.color_pair(6) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 18, "通道", curses.color_pair(6) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 24, "O", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 26, "接入", curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 32, "Q", curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 34, "退出", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                sel_idx = (sel_idx - 1) % len(items) if items else 0
            elif key == curses.KEY_DOWN:
                sel_idx = (sel_idx + 1) % len(items) if items else 0
            elif key == curses.KEY_LEFT:
                cli_idx = (cli_idx - 1) % len(cli_names)
                sel_idx = 0
                search_query = ""
            elif key == curses.KEY_RIGHT:
                cli_idx = (cli_idx + 1) % len(cli_names)
                sel_idx = 0
                search_query = ""
            elif key in (10, 13, curses.KEY_ENTER):
                if not items:
                    continue
                itype, idata = items[sel_idx]
                if itype == "family":
                    return ("family", cli, idata["family"])
                elif itype == "last":
                    return ("last", cli, idata)
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
                    sel_idx = 0
                else:
                    return None
            elif key in (ord('q'), ord('Q')) and not search_query:
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search_query:
                    search_query = search_query[:-1]
                    sel_idx = 0
            elif 32 <= key <= 126:
                search_query += chr(key)
                sel_idx = 0

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


# ── 第 2 步：子模型选择 TUI ──────────────────────────────────

def select_submodel_tui(family_name, models, provider_options=None):
    """子模型选择 TUI，P 键弹出 provider 列表，+/- 快速循环切换 provider。

    Args:
        family_name: str — 品类名
        models: list[dict] — [{"model": str, "provider_name": str, "provider_id": str, "provider_ctx": dict}]
        provider_options: dict or None — model_name -> [{"provider_name": str, "provider_id": str, "provider_ctx": dict}]

    Returns:
        dict — 选中的 model entry (含 provider_ctx)，附带 "priority_changes": {provider_id: new_priority}
        None — 取消 (Esc)
    """
    if not models:
        return None

    sorted_models = sorted(models, key=lambda m: m.get("use_count", 0), reverse=True)

    # 当前每个模型的 provider 覆盖 (model_name -> provider info)
    provider_overrides = {}
    # provider priority 变更记录 (provider_id -> new_priority)
    priority_changes = {}

    def _get_provider_info(m):
        """返回当前生效的 (provider_name, provider_id, priority)"""
        override = provider_overrides.get(m["model"])
        ctx = override["provider_ctx"] if override else m.get("provider_ctx", {})
        name = override["provider_name"] if override else m.get("provider_name", "")
        pid = override["provider_id"] if override else m.get("provider_id", "")
        pri = ctx.get("priority", 100)
        return name, pid, pri

    def _cycle_provider(m, direction):
        """在可用 provider 中循环切换（+1 或 -1），仅改显示，不动 priority。"""
        model_name = m["model"]
        if not provider_options or model_name not in provider_options:
            return
        opts = provider_options[model_name]
        if len(opts) <= 1:
            return
        cur_name, cur_id, cur_pri = _get_provider_info(m)
        cur_idx = 0
        for i, o in enumerate(opts):
            if o.get("provider_id") == cur_id:
                cur_idx = i
                break
        new_idx = (cur_idx + direction) % len(opts)
        chosen = opts[new_idx]
        provider_overrides[model_name] = chosen

    def _get_result(m):
        override = provider_overrides.get(m["model"])
        if override:
            result = {**m, "provider_name": override["provider_name"],
                      "provider_id": override["provider_id"],
                      "provider_ctx": override["provider_ctx"]}
        else:
            result = dict(m)
        if priority_changes:
            result["priority_changes"] = dict(priority_changes)
        return result

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
        in_provider_popup = False
        popup_idx = 0
        popup_options = []
        search_query = ""

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
            has_changes = bool(provider_overrides)
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

            # 双栏分隔
            _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
            row += 1

            # 滚动
            content_y = row
            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(filtered))):
                y = content_y + (i - scroll)
                m = filtered[i]
                is_sel = (i == idx)
                model_name = m["model"]
                prov_name, prov_id, prov_pri = _get_provider_info(m)
                tag_text = f"{prov_name} P:{prov_pri}"

                # 竖分割
                _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                # 左栏：模型名
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", fc | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, model_name, curses.color_pair(1) | curses.A_BOLD, max_w=left_w - 4)
                else:
                    _safe_addstr(stdscr, y, ll + 1, model_name, curses.color_pair(2), max_w=left_w - 4)

                # 右栏：provider + priority
                is_overridden = m["model"] in provider_overrides
                if is_sel:
                    tag_attr = curses.color_pair(4) | curses.A_BOLD
                elif is_overridden:
                    tag_attr = curses.color_pair(5)
                else:
                    tag_attr = curses.A_DIM
                _safe_addstr(stdscr, y, rl, tag_text, tag_attr, max_w=right_w - 3)

            # -- 底栏 --
            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if search_query:
                _safe_addstr(stdscr, bot_y, ll, "Esc 清除", curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, "BS 删字", curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 20, "Enter 确认", curses.color_pair(1) | curses.A_DIM)
            else:
                _safe_addstr(stdscr, bot_y, ll, "P", curses.color_pair(6) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 2, "通道", curses.color_pair(6) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 8, "+/-", curses.color_pair(5) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 12, "切通道", curses.color_pair(5) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 21, "Enter", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 27, "确认", curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 33, "Esc", curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, ll + 37, "返回", curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, fc)

            # -- Provider popup --
            if in_provider_popup and popup_options:
                popup_h = len(popup_options) + 4
                popup_w = max(30, max((_display_width(o.get("provider_name", "")) for o in popup_options), default=10) + 12)
                popup_sx = (max_w - popup_w) // 2
                popup_sy = max(0, (max_y - popup_h) // 2)
                # 画弹窗
                _safe_addstr(stdscr, popup_sy, popup_sx, "-" * popup_w, fc)
                for pi_y in range(1, popup_h - 1):
                    _safe_addstr(stdscr, popup_sy + pi_y, popup_sx, " " * popup_w, 0)
                _safe_addstr(stdscr, popup_sy + 1, popup_sx + 2, "选择通道", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, popup_sy + popup_h - 1, popup_sx, "-" * popup_w, fc)
                for pi, opt in enumerate(popup_options):
                    p_y = popup_sy + 3 + pi
                    if pi == popup_idx:
                        _safe_addstr(stdscr, p_y, popup_sx + 2, "|", fc | curses.A_BOLD)
                        _safe_addstr(stdscr, p_y, popup_sx + 4, opt.get("provider_name", ""), curses.color_pair(1) | curses.A_BOLD)
                    else:
                        _safe_addstr(stdscr, p_y, popup_sx + 4, opt.get("provider_name", ""), curses.color_pair(2))

            stdscr.refresh()
            key = stdscr.getch()

            if in_provider_popup:
                if key == curses.KEY_UP:
                    popup_idx = (popup_idx - 1) % len(popup_options)
                elif key == curses.KEY_DOWN:
                    popup_idx = (popup_idx + 1) % len(popup_options)
                elif key in (10, 13, curses.KEY_ENTER):
                    chosen = popup_options[popup_idx]
                    model_name = sorted_models[idx]["model"]
                    provider_overrides[model_name] = chosen
                    in_provider_popup = False
                elif key == 27 or key in (ord('p'), ord('P')):
                    in_provider_popup = False
                continue

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(filtered)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(filtered)
            elif key in (10, 13, curses.KEY_ENTER):
                if filtered:
                    m = filtered[idx]
                    override = provider_overrides.get(m["model"])
                    if override:
                        new_pid = override.get("provider_id", "")
                        orig_pid = m.get("provider_id", "")
                        if new_pid != orig_pid:
                            orig_pri = m.get("provider_ctx", {}).get("priority", 100)
                            new_base = override.get("provider_ctx", {}).get("priority", 100)
                            priority_changes[new_pid] = max(new_base, orig_pri + 5)
                            priority_changes[orig_pid] = max(0, orig_pri - 5)
                    return _get_result(m)
            elif key in (ord('p'), ord('P')) and not search_query:
                if filtered:
                    model_name = filtered[idx]["model"]
                    if provider_options and model_name in provider_options:
                        popup_options = provider_options[model_name]
                        if len(popup_options) > 1:
                            popup_idx = 0
                            in_provider_popup = True
            elif key in (ord('+'), ord('=')) and not search_query:
                if filtered:
                    _cycle_provider(filtered[idx], +1)
            elif key in (ord('-'), ord('_')) and not search_query:
                if filtered:
                    _cycle_provider(filtered[idx], -1)
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
            elif 32 <= key <= 126 and not in_provider_popup:
                # 可打印 ASCII 字符 → 搜索
                search_query += chr(key)
                idx = 0
                scroll = 0

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

# 默认预设（3-slot: heavy / medium / light）
_LB_PRESETS = [
    {"label": "常规降本",   "heavy": "claude-sonnet-4-6", "medium": "kimi-k2.5",       "light": "claude-haiku-4-5"},
    {"label": "全力 Claude", "heavy": "claude-opus-4-6",   "medium": "claude-sonnet-4-6", "light": "claude-haiku-4-5"},
    {"label": "GPT 全栈",   "heavy": "gpt-5.4",           "medium": "gpt-4.1",           "light": "gpt-4.1-mini"},
]


def _load_lb_history():
    """读取负载模式历史。返回 {"default": {...}, "recent": [{...}, ...]}"""
    fallback = {"default": _LB_PRESETS[0], "recent": []}
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


def save_lb_history(heavy, medium, light):
    """保存一条负载模式选择到历史。保留最近 3 条。"""
    entry = {"heavy": heavy, "medium": medium, "light": light,
             "label": f"{heavy} / {medium} / {light}"}
    history = _load_lb_history()
    recent = history.get("recent", [])
    # 去重
    recent = [r for r in recent if not (r.get("heavy") == heavy and r.get("medium") == medium and r.get("light") == light)]
    recent.insert(0, entry)
    history["recent"] = recent[:3]
    try:
        os.makedirs(os.path.dirname(_LB_HISTORY_PATH), exist_ok=True)
        with open(_LB_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def select_load_balance_tui(available_models=None, families_detail=None, provider_options_map=None):
    """负载模式 TUI：最近 3 条 + 自定义（slot 编辑）。

    Args:
        available_models: list[str] — 可用模型名列表（flat）
        families_detail: dict — {family_name: [model_entry, ...]} 用于自定义 M 弹窗
        provider_options_map: dict — {model_name: [provider_option, ...]} 用于 +/- 切 provider

    返回 {"model": heavy, "lb_medium": medium, "lb_light": light, "priority_changes": {...}} 或 None。
    """
    history = _load_lb_history()
    recent = history.get("recent", [])

    def _build_options():
        opts = []
        seen = set()
        for r in recent[:3]:
            key = (r["heavy"], r.get("medium", ""), r["light"])
            if key not in seen:
                seen.add(key)
                opts.append({"label": f"{r['heavy']} / {r.get('medium','')} / {r['light']}",
                             "heavy": r["heavy"], "medium": r.get("medium", ""), "light": r["light"], "type": "recent"})
        opts.append({"label": "✏  自定义...", "type": "custom"})
        return opts

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(7, curses.COLOR_MAGENTA, -1)

        options = _build_options()
        idx = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            w = max(54, min(max_w - 2, int(max_w * 0.85)))
            h = len(options) + 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            _draw_box(stdscr, sy, sx, h, w, "⚖ 负载模式")

            _safe_addstr(stdscr, sy + 2, sx + 4,
                         "heavy / medium / light",
                         curses.A_DIM)

            for i, opt in enumerate(options):
                y = sy + 4 + i
                if y >= sy + h - 1:
                    break
                prefix = "▸ " if i == idx else "  "
                line = f"{prefix}{opt['label']}"
                if opt.get("type") == "recent":
                    attr = curses.color_pair(3) | curses.A_BOLD if i == idx else curses.color_pair(4)
                else:
                    attr = curses.color_pair(3) | curses.A_BOLD if i == idx else curses.color_pair(2)
                _safe_addstr(stdscr, y, sx + 4, line, attr, max_w=w - 8)

            footer = " ↑↓ 选择   Enter 确认   Esc 取消 "
            _center_text(stdscr, sy + h - 1, cx, footer,
                         curses.color_pair(1) | curses.A_BOLD)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(options)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                chosen = options[idx]
                if chosen["type"] == "custom":
                    return "custom"
                return {"model": chosen["heavy"], "lb_medium": chosen.get("medium", ""), "lb_light": chosen["light"]}
            elif key in (ord('q'), ord('Q'), 27):
                return None

    try:
        result = curses.wrapper(_inner)
    except curses.error:
        return None

    if result == "custom":
        return _select_lb_custom_tui(families_detail, provider_options_map)

    return result


def _select_lb_custom_tui(families_detail=None, provider_options_map=None):
    """负载自定义 TUI：3 个 slot + 启动。Enter 进入 slot 编辑（品类→子模型），+/- 切 provider。

    流程：
      主视图：heavy / medium / light / ▶ 启动
        ↑↓ 选 slot，Enter 进入编辑或启动
        +/- 在当前 slot 切换 provider
      编辑 slot（Enter）：
        全屏品类列表 → Enter → 全屏子模型列表 → Enter 选中 → 回主视图
    """
    SLOT_NAMES = ["heavy", "medium", "light"]
    SLOT_LABELS = {"heavy": "Heavy  (复杂)", "medium": "Medium (常规)", "light": "Light  (简单)"}
    slots = {s: {"model": "(未选)", "provider_name": "", "provider_id": "", "provider_ctx": {}} for s in SLOT_NAMES}
    family_names = list((families_detail or {}).keys())

    def _pick_model_for_slot(stdscr):
        """全屏两步选模型：品类 → 子模型。返回 model entry dict 或 None。"""
        fam_idx = 0
        fam_scroll = 0
        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            w = max(40, min(max_w - 2, int(max_w * 0.75)))
            visible = min(len(family_names), max_y - 6)
            h = visible + 4
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            _draw_box(stdscr, sy, sx, h, w, "选择品类")

            if fam_idx < fam_scroll:
                fam_scroll = fam_idx
            elif fam_idx >= fam_scroll + visible:
                fam_scroll = fam_idx - visible + 1

            for fi in range(fam_scroll, min(fam_scroll + visible, len(family_names))):
                fy = sy + 2 + (fi - fam_scroll)
                fm = "▸ " if fi == fam_idx else "  "
                cnt = len((families_detail or {}).get(family_names[fi], []))
                fattr = curses.color_pair(3) | curses.A_BOLD if fi == fam_idx else curses.color_pair(2)
                _safe_addstr(stdscr, fy, sx + 4, f"{fm}{family_names[fi]} ({cnt})", fattr, max_w=w - 8)

            _center_text(stdscr, sy + h - 1, cx, " ↑↓ 选择  Enter 展开  Esc 返回 ",
                         curses.color_pair(1) | curses.A_BOLD)
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
        """全屏子模型选择。返回 model entry dict 或 None (Esc)。"""
        m_idx = 0
        m_scroll = 0
        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            w = max(50, min(max_w - 2, int(max_w * 0.85)))
            inner_w = w - 8
            visible = min(len(model_list), max_y - 6)
            h = visible + 4
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            tag_samples = [m.get("provider_name", "") + " P:" + str(m.get("provider_ctx", {}).get("priority", ""))
                           for m in model_list]
            max_tag_w = max((_display_width(t) for t in tag_samples), default=10)

            _draw_box(stdscr, sy, sx, h, w, fam_name)

            if m_idx < m_scroll:
                m_scroll = m_idx
            elif m_idx >= m_scroll + visible:
                m_scroll = m_idx - visible + 1

            tag_x = sx + w - 4 - max_tag_w
            for mi in range(m_scroll, min(m_scroll + visible, len(model_list))):
                my = sy + 2 + (mi - m_scroll)
                me = model_list[mi]
                is_sel = (mi == m_idx)
                mm = "▸ " if is_sel else "  "
                mname = me.get("model", "")
                mprov = me.get("provider_name", "")
                mpri = me.get("provider_ctx", {}).get("priority", "")
                mtag = f"{mprov} P:{mpri}" if mprov else ""

                mattr = curses.color_pair(3) | curses.A_BOLD if is_sel else curses.color_pair(2)
                _safe_addstr(stdscr, my, sx + 4, f"{mm}{mname}", mattr, max_w=inner_w - max_tag_w - 2)
                if mtag:
                    tattr = curses.color_pair(4) | curses.A_BOLD if is_sel else curses.color_pair(4) | curses.A_DIM
                    _safe_addstr(stdscr, my, tag_x, mtag, tattr)

            _center_text(stdscr, sy + h - 1, cx, " ↑↓ 选择  Enter 选中  Esc 返回 ",
                         curses.color_pair(1) | curses.A_BOLD)
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
        """在可用 provider 间循环切换 slot 的 provider。"""
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
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        items = 4
        idx = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            w = max(58, min(max_w - 2, int(max_w * 0.85)))
            inner_w = w - 8
            h = items + 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            _draw_box(stdscr, sy, sx, h, w, "⚖ 自定义负载")

            for si, sname in enumerate(SLOT_NAMES):
                y = sy + 2 + si
                is_sel = (si == idx)
                marker = "▸ " if is_sel else "  "
                slot = slots[sname]
                label = SLOT_LABELS[sname]
                model = slot["model"]
                prov = slot["provider_name"]
                pri = slot["provider_ctx"].get("priority", "")
                tag = f"{prov} P:{pri}" if prov else ""

                left = f"{marker}{label}  {model}"
                attr = curses.color_pair(3) | curses.A_BOLD if is_sel else curses.color_pair(2)
                max_left = inner_w - _display_width(tag) - 2 if tag else inner_w
                _safe_addstr(stdscr, y, sx + 4, left, attr, max_w=max_left)

                if tag:
                    tag_attr = curses.color_pair(4) | curses.A_BOLD if is_sel else curses.color_pair(4) | curses.A_DIM
                    tag_x = sx + w - 4 - _display_width(tag)
                    _safe_addstr(stdscr, y, tag_x, tag, tag_attr)

            _draw_separator(stdscr, sy + 5, sx, w)

            launch_y = sy + 6
            is_launch = (idx == 3)
            can_launch = slots["heavy"]["model"] != "(未选)"
            launch_marker = "▸ " if is_launch else "  "
            if can_launch:
                launch_attr = curses.color_pair(5) | curses.A_BOLD if is_launch else curses.color_pair(5)
                launch_text = f"{launch_marker}▶ 启动"
            else:
                launch_attr = curses.A_DIM
                launch_text = f"{launch_marker}▶ 启动  (请先选择 Heavy 模型)"
            _safe_addstr(stdscr, launch_y, sx + 4, launch_text, launch_attr, max_w=inner_w)

            footer = "Enter 编辑/启动  +/- 切Provider  ↑↓ 选择  Esc 返回"
            _center_text(stdscr, sy + h - 1, cx, f" {footer} ",
                         curses.color_pair(1) | curses.A_BOLD)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % items
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % items
            elif key in (10, 13, curses.KEY_ENTER):
                if idx < 3:
                    if not family_names:
                        continue
                    chosen = _pick_model_for_slot(stdscr)
                    if chosen is not None:
                        sname = SLOT_NAMES[idx]
                        slots[sname] = {
                            "model": chosen.get("model", ""),
                            "provider_name": chosen.get("provider_name", ""),
                            "provider_id": chosen.get("provider_id", ""),
                            "provider_ctx": chosen.get("provider_ctx", {}),
                        }
                elif can_launch:
                    return {
                        "model": slots["heavy"]["model"],
                        "lb_medium": slots["medium"]["model"] if slots["medium"]["model"] != "(未选)" else "",
                        "lb_light": slots["light"]["model"] if slots["light"]["model"] != "(未选)" else "",
                    }
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

SETTINGS_MENU = [
    {"id": "provider_mgmt", "label": "Provider 管理", "desc": "查看/调整 role 与 priority"},
    {"id": "account_mgmt", "label": "账号管理", "desc": "查看 OAuth 账号状态"},
    {"id": "recommend", "label": "推荐模型", "desc": "编辑推荐模型列表"},
    {"id": "routes_export", "label": "路由导出", "desc": "导出 model-routes.json"},
    {"id": "about", "label": "关于", "desc": "版本与环境信息"},
]


def select_settings_tui():
    """设置主菜单。返回选中项的 id 或 None。"""

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            w = max(54, min(max_w - 2, int(max_w * 0.78)))
            h = len(SETTINGS_MENU) + 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            _draw_box(stdscr, sy, sx, h, w, "⚙ 设置")

            for i, item in enumerate(SETTINGS_MENU):
                y = sy + 2 + i
                marker = "▸ " if i == idx else "  "
                # 左：label，右：desc
                label = f"{marker}{item['label']}"
                desc = item["desc"]
                attr = curses.color_pair(3) | curses.A_BOLD if i == idx else curses.color_pair(2)
                _safe_addstr(stdscr, y, sx + 4, label, attr)
                desc_attr = curses.A_DIM if i != idx else curses.color_pair(3)
                desc_x = sx + w - 4 - _display_width(desc)
                _safe_addstr(stdscr, y, max(sx + 24, desc_x), desc, desc_attr)

            footer = " ↑↓ 选择  Enter 进入  Esc 返回 "
            _center_text(stdscr, sy + h - 1, cx, footer,
                         curses.color_pair(1) | curses.A_BOLD)

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(SETTINGS_MENU)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(SETTINGS_MENU)
            elif key in (10, 13, curses.KEY_ENTER):
                return SETTINGS_MENU[idx]["id"]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


# ── Provider 浏览 TUI（首页 P 键入口） ──────────────────────

def select_provider_browse_tui(providers):
    """Provider 列表选择。

    Args:
        providers: list[dict] — [{"id", "name", "role", "priority"}, ...]

    Returns:
        (provider_id, provider_name) — 选中的 provider
        None — 取消
    """
    if not providers:
        return None

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            w = max(48, min(max_w - 2, int(max_w * 0.75)))
            visible = max_y - 6
            h = min(len(providers) + 4, max_y - 2)
            if h < 6:
                h = 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2
            pad = sx + 3

            _draw_box(stdscr, sy, sx, h, w, "选择 Provider")

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(providers))):
                y = sy + 2 + i - scroll
                p = providers[i]
                prefix = " ▸ " if i == idx else "   "
                name = p.get("name", p.get("id", "?"))
                role = p.get("role", "auto")
                pri = p.get("priority", 100)

                if i == idx:
                    attr = curses.color_pair(3) | curses.A_BOLD
                elif role == "primary":
                    attr = curses.color_pair(5)
                elif role == "fallback":
                    attr = curses.color_pair(4)
                else:
                    attr = 0

                label = f"{prefix}{name}{' ' * max(1, 24 - _display_width(name))}{role:<10} P:{pri}"
                _safe_addstr(stdscr, y, pad, label, attr, max_w=w - 6)

            footer = f" {len(providers)} providers  ↑↓ 选择  Enter 确认  Esc 返回 "
            _center_text(stdscr, sy + h - 1, cx, footer, curses.color_pair(1) | curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(providers)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(providers)
            elif key in (10, 13, curses.KEY_ENTER):
                p = providers[idx]
                return (p.get("id"), p.get("name", p.get("id")))
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_provider_models_tui(provider_name, models):
    """选中 provider 后展示其全部模型列表。

    Args:
        provider_name: str
        models: list[str] — 模型名列表

    Returns:
        {"model": str} — 选中的模型
        None — 取消
    """
    if not models:
        return None

    sorted_models = sorted(models)

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            w = max(52, min(max_w - 2, int(max_w * 0.75)))
            visible = max_y - 6
            h = min(len(sorted_models) + 4, max_y - 2)
            if h < 6:
                h = 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2
            pad = sx + 3

            _draw_box(stdscr, sy, sx, h, w, f"{provider_name} — 模型列表")

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(sorted_models))):
                y = sy + 2 + i - scroll
                prefix = " ▸ " if i == idx else "   "
                attr = curses.color_pair(3) | curses.A_BOLD if i == idx else curses.color_pair(2)
                label = f"{prefix}{sorted_models[i]}"
                _safe_addstr(stdscr, y, pad, label, attr, max_w=w - 6)

            footer = f" {len(sorted_models)} models  ↑↓ 选择  Enter 确认  B 返回  Esc 退出 "
            _center_text(stdscr, sy + h - 1, cx, footer, curses.color_pair(1) | curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(sorted_models)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(sorted_models)
            elif key in (10, 13, curses.KEY_ENTER):
                return {"model": sorted_models[idx]}
            elif key in (ord('b'), ord('B')):
                return None  # 返回 provider 列表
            elif key in (27, ord('q'), ord('Q')):
                return "__exit__"  # 完全退出

    try:
        result = curses.wrapper(_inner)
        return result
    except curses.error:
        return None


def select_provider_mgmt_tui(providers):
    """Provider 管理 TUI。

    Args:
        providers: list[dict] — [{"id", "name", "role", "priority", "enabled", "protocols", ...}]

    Returns:
        list[dict] — 修改后的 providers 列表（含 role/priority 变更）
        None — 取消（无变更）
    """
    if not providers:
        return None

    ROLE_CYCLE = ["auto", "primary", "fallback"]
    ROLE_BADGES = {"primary": "primary", "auto": "auto", "fallback": "fallback"}

    # 深拷贝以便修改
    import copy
    items = copy.deepcopy(providers)
    changed = False

    def _inner(stdscr):
        nonlocal items, changed
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(7, curses.COLOR_RED, -1)

        idx = 0
        scroll = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            w = max(60, min(max_w - 2, int(max_w * 0.85)))
            visible = min(len(items), max_y - 7)
            h = visible + 6
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2
            inner_w = w - 8

            title = "Provider 管理" + (" *" if changed else "")
            _draw_box(stdscr, sy, sx, h, w, title)

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            list_y = sy + 2
            for i in range(scroll, min(scroll + visible, len(items))):
                y = list_y + (i - scroll)
                p = items[i]
                is_sel = (i == idx)
                marker = "▸ " if is_sel else "  "
                name = p.get("name") or p.get("id", "?")
                role = p.get("role", "auto")
                priority = p.get("priority", 100)
                enabled = "✓" if p.get("enabled", True) else "✗"

                # 格式：marker name   role  P:priority  enabled
                role_badge = ROLE_BADGES.get(role, role)
                line_left = f"{marker}{name}"
                line_right = f"{role_badge:<10} P:{priority:<4} {enabled}"

                if is_sel:
                    attr_l = curses.color_pair(3) | curses.A_BOLD
                    attr_r = curses.color_pair(3)
                else:
                    attr_l = curses.color_pair(2)
                    if role == "primary":
                        attr_r = curses.color_pair(5)
                    elif role == "fallback":
                        attr_r = curses.color_pair(4) | curses.A_DIM
                    else:
                        attr_r = curses.color_pair(2) | curses.A_DIM

                _safe_addstr(stdscr, y, sx + 4, line_left, attr_l, max_w=inner_w - 24)
                right_x = sx + w - 4 - _display_width(line_right)
                _safe_addstr(stdscr, y, max(sx + 30, right_x), line_right, attr_r)

            footer = " R 改Role  +/- 改Priority  Enter 保存  Esc 取消 "
            _center_text(stdscr, sy + h - 1, cx, footer,
                         curses.color_pair(1) | curses.A_BOLD)

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
            elif key in (ord('-'), ord('_')):
                items[idx]["priority"] = max(0, items[idx].get("priority", 100) - 5)
                changed = True
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


def select_connect_tui():
    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            w = max(54, min(max_w - 2, int(max_w * 0.78)))
            h = len(CONNECT_ACTIONS) + 8
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2
            _draw_box(stdscr, sy, sx, h, w, "接入新通道")
            _center_text(stdscr, sy + 2, cx, "你想接入哪一类通道？", curses.color_pair(5) | curses.A_BOLD)

            for action_idx, action in enumerate(CONNECT_ACTIONS):
                y = sy + 4 + action_idx
                line = f"{'▸ ' if action_idx == idx else '  '}{action['title']}  {action['summary']}"
                attr = curses.color_pair(3) | curses.A_BOLD if action_idx == idx else curses.color_pair(2)
                try:
                    stdscr.addstr(y, sx + 2, line[:w - 4], attr)
                except curses.error:
                    pass

            footer = " ↑ ↓ 选择    Enter 进入    Esc/Q 返回 "
            _center_text(stdscr, sy + h - 1, cx, footer, curses.color_pair(1) | curses.A_BOLD)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(CONNECT_ACTIONS)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(CONNECT_ACTIONS)
            elif key in (10, 13, curses.KEY_ENTER):
                return CONNECT_ACTIONS[idx]["id"]
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

    has_bypass = cli in ("codex", "claude")

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        curses.init_pair(7, curses.COLOR_RED, -1)

        bypass_mode = True  # 默认 bypass，Tab 切换回正常

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            w = max(54, min(max_w - 2, int(max_w * 0.85)))
            bypass_h = 1 if has_bypass else 0
            env_h = len(env_lines) + 1 if env_lines else 0
            h = 7 + env_h + bypass_h
            sx = (max_w - w) // 2
            sy = (max_y - h) // 2
            cx = sx + w // 2
            pad = sx + 4

            box_color = curses.color_pair(7) if bypass_mode else None
            title = "⚠ BYPASS 确认" if bypass_mode else "确认启动"
            _draw_box(stdscr, sy, sx, h, w, title, color=box_color)

            row = sy + 2
            try:
                stdscr.addstr(row, pad, f"CLI   {cli}", curses.color_pair(2) | curses.A_BOLD)
                row += 1
                mdl = model_display[:w - 12]
                stdscr.addstr(row, pad, f"模型  {mdl}", curses.color_pair(2))
                row += 1
                scope = "一次性命令" if once else "交互会话"
                stdscr.addstr(row, pad, f"启动  {scope}", curses.color_pair(2))
                row += 1
                if has_bypass:
                    if bypass_mode:
                        mode_text = "模式  [Tab] ⚠ BYPASS（跳过审批）"
                        stdscr.addstr(row, pad, mode_text,
                                      curses.color_pair(7) | curses.A_BOLD)
                    else:
                        mode_text = "模式  [Tab] 正常"
                        stdscr.addstr(row, pad, mode_text, curses.color_pair(2))
                    row += 1
                if env_lines:
                    stdscr.addstr(row, pad, "环境  临时注入，仅当前 CLI 进程可见",
                                  curses.color_pair(3) | curses.A_DIM)
                    row += 1
                    stdscr.addstr(row, pad, "ENV", curses.color_pair(3) | curses.A_BOLD)
                    row += 1
                    for line in env_lines:
                        stdscr.addstr(row, pad + 2, line[:w - 10],
                                      curses.color_pair(4) | curses.A_DIM)
                        row += 1
                else:
                    stdscr.addstr(row, pad, "环境  无需额外注入",
                                  curses.color_pair(3) | curses.A_DIM)
                    row += 1
            except curses.error:
                pass

            footer_color = curses.color_pair(7) if bypass_mode else curses.color_pair(1)
            if has_bypass:
                footer = " Enter 启动  Tab 切换模式  B 返回  Q 取消 "
            else:
                footer = " Enter 启动  B 返回  Q 取消 "
            _center_text(stdscr, sy + h - 1, cx, footer, footer_color)
            stdscr.refresh()

            key = stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return ("", bypass_mode)
            elif key in (ord('b'), ord('B')):
                return ("b", False)
            elif key in (ord('q'), ord('Q'), 27):
                return ("q", False)
            elif key == 9 and has_bypass:  # Tab
                bypass_mode = not bypass_mode

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return ("q", False)
