"""MMS curses TUI：箭头键交互选择器 — v2 品类模式"""

import curses
import json
import locale
import os
import sys
import time
import unicodedata
from datetime import datetime, timezone
from math import pow
from mms_fake_upstream import status_payload as _fake_upstream_status_payload
from mms_i18n import pick as _L, get_language as _get_language
from mms_state_io import resolve_mms_config_dir

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


def _wrap_display_lines(text, max_w):
    text = str(text or "")
    if max_w <= 0:
        return [text]
    lines = []
    current = ""
    width = 0
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
            width = 0
            continue
        ch_w = _display_width(ch)
        if current and width + ch_w > max_w:
            lines.append(current)
            current = ch
            width = ch_w
            continue
        current += ch
        width += ch_w
    lines.append(current)
    return lines or [""]


def _slice_display_text(text, start_w, max_w):
    """按显示宽度切片，返回从 start_w 开始、最多 max_w 列的文本。"""
    if max_w <= 0:
        return ""

    skipped = 0
    out = []
    used = 0
    started = False

    for ch in text:
        ch_w = _display_width(ch)
        if not started:
            if skipped + ch_w <= start_w:
                skipped += ch_w
                continue
            started = True
        if used + ch_w > max_w:
            break
        out.append(ch)
        used += ch_w
    return "".join(out)


def _marquee_text(text, max_w, tick, gap=4):
    """长文本的循环横向滚动，仅用于展示层。"""
    if max_w <= 0:
        return ""
    if _display_width(text) <= max_w:
        return text
    spacer = " " * max(2, gap)
    loop = text + spacer + text + spacer
    cycle_w = _display_width(text) + _display_width(spacer)
    start_w = tick % max(1, cycle_w)
    return _slice_display_text(loop, start_w, max_w)


def _draw_separator(stdscr, y, cx, width, attr=0):
    """画一条居中分隔线。"""
    sx = cx - width // 2
    try:
        stdscr.addstr(y, max(0, sx), "─" * width, attr)
    except curses.error:
        pass


def _draw_footer_actions(stdscr, y, x, max_w, actions):
    rows = 1
    cursor_x = x
    current_y = y
    gap = 2
    for chunks in actions:
        chunk_w = sum(_display_width(text) for text, _attr in chunks)
        if cursor_x > x and cursor_x - x + gap + chunk_w > max_w:
            current_y += 1
            rows += 1
            cursor_x = x
        elif cursor_x > x:
            cursor_x += gap
        for text, attr in chunks:
            _safe_addstr(stdscr, current_y, cursor_x, text, attr, max_w=max_w - (cursor_x - x))
            cursor_x += _display_width(text)
    return rows


def _measure_footer_actions(max_w, actions):
    rows = 1
    cursor = 0
    gap = 2
    for chunks in actions:
        chunk_w = sum(_display_width(text) for text, _attr in chunks)
        if cursor > 0 and cursor + gap + chunk_w > max_w:
            rows += 1
            cursor = 0
        elif cursor > 0:
            cursor += gap
        cursor += chunk_w
    return rows


# ── 第 1 步：品类选择 TUI ──────────────────────────────────

_FAMILY_COLORS = {
    "Claude": 3, "GPT": 5, "GLM": 7, "Kimi": 6,
    "Qwen": 4, "MiniMax": 2, "Gemini": 1, "DeepSeek": 1,
}
_CLI_COLORS = {"claude": 3, "codex": 5}
_COLD_FAMILY_BUCKET_ID = "__cold_family_bucket__"


def _build_family_menu_items(families, search_query="", cold_expanded=False):
    if search_query:
        query = str(search_query or "").lower()
        filtered = [entry for entry in (families or []) if query in str(entry.get("family", "")).lower()]
        if not filtered:
            filtered = list(families or [])
        return [("family", entry) for entry in filtered]

    hot_families = [entry for entry in (families or []) if not entry.get("is_cold")]
    cold_families = [entry for entry in (families or []) if entry.get("is_cold")]
    items = [("family", entry) for entry in hot_families]
    if cold_families:
        items.append(("cold_bucket", {
            "id": _COLD_FAMILY_BUCKET_ID,
            "count": len(cold_families),
            "expanded": bool(cold_expanded),
            "families": cold_families,
        }))
        if cold_expanded:
            items.extend(("family", entry) for entry in cold_families)
    return items


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


def _parse_tui_usage_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _tui_recency_score(value, now=None, half_life_days=14):
    parsed = _parse_tui_usage_timestamp(value)
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (current - parsed).total_seconds()) / 86400.0
    return pow(0.5, age_days / float(half_life_days))


def _sort_cli_names_by_last_used(cli_names, last_used=None, now=None):
    indexed = list(enumerate(cli_names or []))

    def _key(item):
        index, cli_name = item
        usage = (last_used or {}).get(cli_name) if isinstance(last_used, dict) else {}
        last_at = usage.get("last_used_at") if isinstance(usage, dict) else ""
        recency = _tui_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        return (-has_recent, -recency, index)

    return [cli_name for _index, cli_name in sorted(indexed, key=_key)]


def _sort_model_entries_for_tui(models, family_name="", now=None):
    def _model_name(item):
        if isinstance(item, dict):
            return str(item.get("model") or "")
        return str(item or "")

    def _key(item):
        if isinstance(item, dict):
            last_at = str(item.get("last_used_at") or "").strip()
        else:
            last_at = ""
        recency = _tui_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        return (
            -has_recent,
            -recency,
            _model_name(item).lower(),
        )

    return sorted(list(models or []), key=_key)


def _normalize_profile_token(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _last_profile_id(last_item):
    if not isinstance(last_item, dict):
        return ""
    for key in ("opencode_profile", "profile", "profile_id"):
        value = str(last_item.get(key) or "").strip()
        if value:
            return value
    for nested_key in ("model_info", "runtime_hint"):
        nested = last_item.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key in ("opencode_profile", "profile", "profile_id"):
            value = str(nested.get(key) or "").strip()
            if value:
                return value
    model_name = ""
    model_info = last_item.get("model_info")
    if isinstance(model_info, dict):
        model_name = str(model_info.get("model") or "").strip()
    model_name = model_name or str(last_item.get("model") or "").strip()
    if _normalize_profile_token(model_name) == "global_omo":
        return "heavy_omo"
    return ""


def _profile_option_matches(option, profile_id):
    target = _normalize_profile_token(profile_id)
    if not target or not isinstance(option, dict):
        return False
    candidates = (
        option.get("id"),
        option.get("profile_id"),
        option.get("canonical_profile_id"),
        option.get("opencode_profile"),
        option.get("label"),
    )
    return target in {_normalize_profile_token(candidate) for candidate in candidates if candidate}


def _sort_profile_options_for_tui(profile_options, last_used=None):
    """Keep the last-used OpenCode profile at the top without mutating config order."""
    options = list(profile_options or [])
    profile_id = _last_profile_id(last_used)
    if not profile_id:
        return options
    indexed = list(enumerate(options))
    indexed.sort(key=lambda item: (0 if _profile_option_matches(item[1], profile_id) else 1, item[0]))
    return [option for _index, option in indexed]


def select_family_tui(
    families_by_cli,
    cli_names,
    last_used=None,
    families_detail=None,
    provider_options_by_cli=None,
    provider_options_loader_by_cli=None,
    broker_enabled_by_cli=None,
    profile_options_by_cli=None,
):
    """主 TUI — H6 双栏风格：左栏品类列表，右栏模型预览。

    Args:
        families_by_cli: dict[str, list[dict]] — cli_name -> [{family, count}]
        cli_names: list[str] — ["claude", "codex", "opencode", "agy"]
        last_used: dict[str, dict] or None — {cli_name: {"model", "cli", "model_info", ...}}
        families_detail: dict[str, dict] or None — {cli_name: {family: [model_list]}}
        provider_options_by_cli: dict[str, dict] or None — {cli_name: {model_name: [provider_options]}}
        provider_options_loader_by_cli: dict[str, callable] or None — {cli_name: fn(model_name) -> [provider_options]}

    Returns:
        ("family", cli_name, family_name) | ("last", cli_name, dict) |
        ("profile", cli_name, profile_id) |
        ("load_balance", cli_name, None) | ("settings", cli_name, None) |
        ("broker", cli_name, None) |
        ("connect", cli_name, None) | ("provider_browse", cli_name, None) | None
    """
    families_detail = families_detail or {}
    cli_names = _sort_cli_names_by_last_used(cli_names, last_used)

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
        cold_expanded_by_cli = {}

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
            provider_options_loader = (provider_options_loader_by_cli or {}).get(cli)
            broker_available = False

            # 上次使用
            cli_last = (last_used or {}).get(cli)
            profile_options = _sort_profile_options_for_tui(
                (profile_options_by_cli or {}).get(cli) or [],
                cli_last,
            )
            use_profile_menu = bool(profile_options)
            has_last = cli_last and cli_last.get("model") and not search_query and not use_profile_menu

            # 构建列表项：默认折叠冷门 family；搜索时平铺所有匹配项
            cold_expanded = bool(cold_expanded_by_cli.get(cli))
            if use_profile_menu:
                query = search_query.lower().strip()
                profile_items = []
                for option in profile_options:
                    haystack = " ".join(
                        str(option.get(key) or "")
                        for key in ("id", "label", "summary")
                    ).lower()
                    if query and query not in haystack:
                        continue
                    profile_items.append(option)
                items = [("profile", option) for option in profile_items]
            else:
                items = _build_family_menu_items(
                    families,
                    search_query=search_query,
                    cold_expanded=cold_expanded,
                )
            visible_family_count = sum(1 for itype, _idata in items if itype == "family")

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
                info = f"{len(items)}/{len(profile_options)}" if use_profile_menu else f"{visible_family_count}/{len(families)}"
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
                elif itype == "cold_bucket":
                    count = int(idata.get("count", 0) or 0)
                    expanded = bool(idata.get("expanded"))
                    label = _L("冷门 / 更多", "Cold / More")
                    marker = "v" if expanded else ">"
                    bucket_attr = curses.color_pair(6) | (curses.A_BOLD if is_sel else curses.A_DIM)
                    if is_sel:
                        _safe_addstr(stdscr, y, ll + 1, " " * max(1, left_w - 4), curses.color_pair(6) | curses.A_REVERSE)
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, f"{marker} {label}", curses.color_pair(6) | curses.A_BOLD | curses.A_REVERSE)
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.color_pair(6) | curses.A_REVERSE)
                    else:
                        _safe_addstr(stdscr, y, ll, marker, bucket_attr)
                        _safe_addstr(stdscr, y, ll + 2, label, bucket_attr)
                        cnt = str(count)
                        _safe_addstr(stdscr, y, lr - len(cnt), cnt, curses.A_DIM)
                elif itype == "profile":
                    label = str(idata.get("label") or idata.get("id") or "Profile")
                    badge = str(idata.get("badge") or "").strip()
                    display = f"{badge} {label}" if badge else label
                    if is_sel:
                        _safe_addstr(stdscr, y, ll + 1, " " * max(1, left_w - 4), curses.color_pair(1) | curses.A_REVERSE)
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, display, curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE, max_w=left_w - 5)
                    else:
                        _safe_addstr(stdscr, y, ll, ".", curses.color_pair(5) | curses.A_DIM)
                        _safe_addstr(stdscr, y, ll + 2, display, curses.color_pair(2), max_w=left_w - 4)

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
                    raw_models = _sort_model_entries_for_tui(raw_models, sel_fam_name)
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
            elif items and 0 <= sel_idx < len(items) and items[sel_idx][0] == "cold_bucket":
                cold_families = items[sel_idx][1].get("families", [])
                preview_lines = [
                    f"{entry.get('family', '?')} ({entry.get('count', 0)})"
                    for entry in cold_families[:max(1, len(items))]
                ]
                for mi, text in enumerate(preview_lines):
                    my = content_y + mi
                    attr = curses.color_pair(6) | curses.A_BOLD if mi == 0 else curses.color_pair(2)
                    _safe_addstr(stdscr, my, rl, text, attr, max_w=right_w - 3)
                if len(cold_families) > len(preview_lines):
                    _safe_addstr(stdscr, content_y + len(preview_lines), rl,
                                 f"... +{len(cold_families) - len(preview_lines)}", curses.A_DIM)
            elif items and 0 <= sel_idx < len(items) and items[sel_idx][0] == "profile":
                option = items[sel_idx][1]
                preview_lines = [
                    str(option.get("label") or option.get("id") or "Profile"),
                    str(option.get("summary") or ""),
                ]
                for mi, text in enumerate([line for line in preview_lines if line]):
                    my = content_y + mi
                    attr = curses.color_pair(5) | curses.A_BOLD if mi == 0 else curses.color_pair(2)
                    _safe_addstr(stdscr, my, rl, text, attr, max_w=right_w - 3)

            # -- 底栏 --
            bot_y = content_y + len(items)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            footer_actions = []
            if search_query:
                footer_actions = [
                    [(_L("Esc 清除", "Esc Clear"), curses.color_pair(4) | curses.A_DIM)],
                    [(_L("BS 删字", "BS Delete"), curses.A_DIM)],
                    [(_L("Enter 确认", "Enter Confirm"), curses.color_pair(1) | curses.A_DIM)],
                ]
            elif use_profile_menu:
                footer_actions = [
                    [("Tab", curses.color_pair(4) | curses.A_BOLD), (_L(" 切CLI", " Switch CLI"), curses.color_pair(4) | curses.A_DIM)],
                    [("Enter", curses.color_pair(1) | curses.A_BOLD), (" Profile", curses.color_pair(1) | curses.A_DIM)],
                    [("O", curses.color_pair(4) | curses.A_BOLD), (_L(" 接入", " Connect"), curses.color_pair(4) | curses.A_DIM)],
                    [("S", curses.color_pair(1) | curses.A_BOLD), (_L(" 设置", " Settings"), curses.A_DIM)],
                ]
            else:
                footer_actions = [
                    [("Tab", curses.color_pair(4) | curses.A_BOLD), (_L(" 切CLI", " Switch CLI"), curses.color_pair(4) | curses.A_DIM)],
                    [("→", curses.color_pair(1) | curses.A_BOLD), (_L(" 进模型", " Models"), curses.color_pair(1) | curses.A_DIM)],
                    [("L", curses.color_pair(5) | curses.A_BOLD), (_L(" 负载", " Load"), curses.color_pair(5) | curses.A_DIM)],
                    [("P", curses.color_pair(6) | curses.A_BOLD), (_L(" 通道", " Channels"), curses.color_pair(6) | curses.A_DIM)],
                    [("O", curses.color_pair(4) | curses.A_BOLD), (_L(" 接入", " Connect"), curses.color_pair(4) | curses.A_DIM)],
                    [("S", curses.color_pair(1) | curses.A_BOLD), (_L(" 设置", " Settings"), curses.A_DIM)],
                ]
            footer_rows = _draw_footer_actions(stdscr, bot_y, ll, max(10, total_w - (ll - px)), footer_actions)
            bot_y += footer_rows
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
                        provider_options_loader=provider_options_loader,
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
                elif itype == "cold_bucket":
                    cold_expanded_by_cli[cli] = not bool(idata.get("expanded"))
                elif itype == "profile":
                    return ("profile", cli, idata.get("id"))
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
                        provider_options_loader=provider_options_loader,
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
                elif itype == "cold_bucket":
                    cold_expanded_by_cli[cli] = not bool(idata.get("expanded"))
                elif itype == "profile":
                    return ("profile", cli, idata.get("id"))
            elif key in (ord('r'), ord('R')) and not search_query and has_last:
                return ("last", cli, cli_last)
            elif key in (ord('l'), ord('L')) and not search_query and not use_profile_menu:
                return ("load_balance", cli, None)
            elif key in (ord('s'), ord('S')) and not search_query:
                return ("settings", cli, None)
            elif key in (ord('p'), ord('P')) and not search_query and not use_profile_menu:
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

def select_submodel_tui(
    family_name,
    models,
    provider_options=None,
    provider_options_loader=None,
    last_used=None,
    stdscr=None,
):
    """子模型选择 TUI，P 键弹出 provider 列表，+/- 快速循环切换 provider。

    Args:
        family_name: str — 品类名
        models: list[dict] — [{"model": str, "provider_name": str, "provider_id": str, "provider_ctx": dict}]
        provider_options: dict or None — model_name -> [{"provider_name": str, "provider_id": str, "provider_ctx": dict}]
        provider_options_loader: callable or None — 懒加载 provider options；仅在进入模型页后按需计算
        last_used: dict or None — 当前 CLI 的上次使用记录
        stdscr: curses window or None — 传入时复用当前 TUI session，避免切页闪烁

    Returns:
        dict — 选中的 model entry (含 provider_ctx)，附带 "priority_changes": {provider_id 或 provider_id||family: new_priority}
        "__last__" — 返回上一次使用
        None — 取消 (Esc)
    """
    if not models:
        return None

    sorted_models = _sort_model_entries_for_tui(models, family_name)
    provider_options_cache = dict(provider_options or {})
    try:
        from mms_speed_stats import get_speed_entry as _get_speed_entry
    except Exception:
        _get_speed_entry = None

    # 当前每个模型的 provider 覆盖 (model_name -> provider info)
    provider_overrides = {}
    # provider priority 变更记录 (provider_id 或 provider_id||family -> new_priority)
    priority_changes = {}

    def _priority_change_key(opt):
        if not isinstance(opt, dict):
            return ""
        pid = str(opt.get("provider_id", "")).strip()
        if not pid:
            return ""
        family = str(
            opt.get("priority_family")
            or (opt.get("provider_ctx") or {}).get("priority_family")
            or ""
        ).strip()
        return f"{pid}||{family}" if family else pid

    def _effective_priority(opt):
        change_key = _priority_change_key(opt)
        if change_key and change_key in priority_changes:
            return int(priority_changes[change_key])
        return int((opt.get("provider_ctx") or {}).get("priority", 100) or 100)

    def _provider_options_for_model(model_name):
        model_key = str(model_name or "").strip()
        if not model_key:
            return []
        if model_key in provider_options_cache:
            return provider_options_cache[model_key]
        if callable(provider_options_loader):
            try:
                provider_options_cache[model_key] = list(provider_options_loader(model_key) or [])
            except Exception:
                provider_options_cache[model_key] = []
        else:
            provider_options_cache[model_key] = []
        return provider_options_cache[model_key]

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

        for opt in _provider_options_for_model(m["model"]):
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
        new_key = _priority_change_key(chosen)
        orig_key = _priority_change_key({
            "provider_id": orig_pid,
            "provider_ctx": m.get("provider_ctx", {}),
        })
        if new_key:
            priority_changes.setdefault(new_key, min(200, max(new_base, orig_pri) + 5))
        if orig_key:
            priority_changes.setdefault(orig_key, max(0, min(orig_pri, new_base) - 5))

    def _adjust_provider_priority(opt, delta):
        change_key = _priority_change_key(opt)
        if not change_key:
            return
        current = _effective_priority(opt)
        priority_changes[change_key] = max(0, min(200, current + delta))

    def _format_ttfb(value):
        if isinstance(value, (int, float)):
            return f"{value:.0f}ms"
        return "-"

    def _format_age(seconds):
        if not isinstance(seconds, (int, float)):
            return "-"
        if seconds < 3600:
            minutes = max(1, int(seconds // 60) or 1)
            return f"{minutes}m"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h"
        return f"{int(seconds // 86400)}d"

    def _build_family_autosort_plan():
        if not callable(_get_speed_entry):
            return {
                "items": [],
                "changes": {},
                "can_apply": False,
                "summary": _L("本地测速模块不可用", "Local speed stats unavailable"),
            }

        aggregated = {}
        for m in sorted_models:
            model_name = str(m.get("model") or "").strip()
            if not model_name:
                continue
            seen = set()
            for opt in _provider_choices(m):
                change_key = _priority_change_key(opt)
                if not change_key or change_key in seen:
                    continue
                seen.add(change_key)
                entry = aggregated.setdefault(
                    change_key,
                    {
                        "change_key": change_key,
                        "provider_id": opt.get("provider_id", ""),
                        "provider_name": opt.get("provider_name", ""),
                        "provider_ctx": dict(opt.get("provider_ctx") or {}),
                        "current_priority": _effective_priority(opt),
                        "available_models": 0,
                        "fresh_samples": 0,
                        "fresh_ttfb_sum": 0.0,
                        "fresh_models": 0,
                        "stale_samples": 0,
                        "stale_ttfb_sum": 0.0,
                        "stale_models": 0,
                        "warming_models": 0,
                        "best_age_seconds": None,
                    },
                )
                entry["available_models"] += 1
                speed = _get_speed_entry(model_name, provider=opt.get("provider_ctx"))
                if not isinstance(speed, dict):
                    continue
                ttfb = speed.get("ttfb_avg_ms")
                samples = int(speed.get("samples") or 0)
                age_seconds = speed.get("age_seconds")
                if isinstance(age_seconds, (int, float)):
                    best_age = entry.get("best_age_seconds")
                    if best_age is None or age_seconds < best_age:
                        entry["best_age_seconds"] = float(age_seconds)
                if speed.get("warming_up"):
                    entry["warming_models"] += 1
                if not isinstance(ttfb, (int, float)) or samples <= 0:
                    continue
                if speed.get("is_stale"):
                    entry["stale_samples"] += samples
                    entry["stale_ttfb_sum"] += float(ttfb) * samples
                    entry["stale_models"] += 1
                else:
                    entry["fresh_samples"] += samples
                    entry["fresh_ttfb_sum"] += float(ttfb) * samples
                    entry["fresh_models"] += 1

        items = []
        for entry in aggregated.values():
            fresh_avg = (
                round(entry["fresh_ttfb_sum"] / entry["fresh_samples"], 2)
                if entry["fresh_samples"] > 0
                else None
            )
            stale_avg = (
                round(entry["stale_ttfb_sum"] / entry["stale_samples"], 2)
                if entry["stale_samples"] > 0
                else None
            )
            if fresh_avg is not None:
                state = "fresh"
                effective_ttfb = fresh_avg
                samples = entry["fresh_samples"]
            elif stale_avg is not None:
                state = "stale"
                effective_ttfb = stale_avg
                samples = entry["stale_samples"]
            else:
                state = "none"
                effective_ttfb = None
                samples = 0
            measured_models = int(entry["fresh_models"] + entry["stale_models"])
            item = dict(entry)
            item.update(
                {
                    "state": state,
                    "effective_ttfb_ms": effective_ttfb,
                    "samples": samples,
                    "measured_models": measured_models,
                    "sort_key": (
                        {"fresh": 0, "stale": 1, "none": 2}.get(state, 2),
                        float(effective_ttfb) if isinstance(effective_ttfb, (int, float)) else float("inf"),
                        -measured_models,
                        -samples,
                        str(entry.get("provider_name") or ""),
                        str(entry.get("provider_id") or ""),
                    ),
                }
            )
            items.append(item)

        items.sort(key=lambda item: item["sort_key"])
        base_priority = max((int(item.get("current_priority", 100) or 100) for item in items), default=100)
        changes = {}
        measured_count = 0
        for idx, item in enumerate(items):
            suggested = max(0, min(200, base_priority - idx * 5))
            item["suggested_priority"] = suggested
            item["priority_diff"] = suggested - int(item.get("current_priority", 100) or 100)
            if item.get("state") != "none":
                measured_count += 1
            if suggested != int(item.get("current_priority", 100) or 100):
                changes[item["change_key"]] = suggested

        if not items:
            summary = _L("当前 family 没有可排序的通道", "No sortable channels in this family")
        elif measured_count < 2:
            summary = _L(
                "测速数据不足：至少需要 2 条通道有有效样本",
                "Not enough speed samples: need at least two measured channels",
            )
        elif not changes:
            summary = _L("当前顺序已经和测速结果一致", "Current order already matches speed stats")
        else:
            summary = _L(
                "规则：fresh 优先，其次 stale；同状态按 TTFB 更快优先；无数据放最后",
                "Rule: fresh first, then stale; faster TTFB wins; no-data goes last",
            )

        return {
            "items": items,
            "changes": changes,
            "can_apply": measured_count >= 2 and bool(changes),
            "summary": summary,
            "measured_count": measured_count,
        }

    def _apply_family_autosort():
        plan = _build_family_autosort_plan()
        if plan.get("can_apply"):
            priority_changes.update(plan.get("changes") or {})
            for model_entry in sorted_models:
                active = _active_provider_choice(model_entry)
                _sync_provider_cursor(model_entry, active.get("provider_id", ""))
        return plan

    def _show_family_autosort_modal(stdscr):
        plan = _build_family_autosort_plan()
        items = list(plan.get("items") or [])
        selected_idx = 0
        scroll = 0

        while True:
            max_y, max_w = stdscr.getmaxyx()
            body_h = min(max(6, max_y - 10), max(6, len(items)))
            box_h = min(max_y - 2, body_h + 8)
            box_w = min(max_w - 4, 88)
            py = max(1, (max_y - box_h) // 2)
            px = max(2, (max_w - box_w) // 2)
            visible = max(1, box_h - 8)

            if selected_idx < scroll:
                scroll = selected_idx
            elif selected_idx >= scroll + visible:
                scroll = selected_idx - visible + 1
            scroll = max(0, min(scroll, max(0, len(items) - visible)))

            _draw_box(
                stdscr,
                py,
                px,
                box_h,
                box_w,
                title=_L(f"{family_name} 自动排序", f"{family_name} Auto Rank"),
                color=curses.color_pair(4),
            )
            row = py + 1
            _safe_addstr(
                stdscr,
                row,
                px + 2,
                _L("使用现有 speed-stats.json 预估，不会主动测速", "Preview only; uses existing speed-stats.json"),
                curses.A_DIM,
                max_w=box_w - 4,
            )
            row += 1
            _safe_addstr(stdscr, row, px + 2, str(plan.get("summary") or ""), curses.color_pair(5), max_w=box_w - 4)
            row += 1
            _safe_addstr(stdscr, row, px + 2, "Provider", curses.A_BOLD)
            _safe_addstr(stdscr, row, px + 34, "State", curses.A_BOLD)
            _safe_addstr(stdscr, row, px + 46, "TTFB", curses.A_BOLD)
            _safe_addstr(stdscr, row, px + 56, "Samples", curses.A_BOLD)
            _safe_addstr(stdscr, row, px + 67, "P", curses.A_BOLD)
            row += 1
            _safe_addstr(stdscr, row, px + 1, "─" * (box_w - 2), curses.A_DIM)
            row += 1

            if not items:
                _safe_addstr(
                    stdscr,
                    row,
                    px + 2,
                    _L("没有可展示的 provider", "No providers to preview"),
                    curses.A_DIM,
                    max_w=box_w - 4,
                )
            else:
                for offset in range(visible):
                    index = scroll + offset
                    if index >= len(items):
                        break
                    item = items[index]
                    y = row + offset
                    is_sel = index == selected_idx
                    attr = curses.A_REVERSE if is_sel else 0
                    state = item.get("state")
                    if state == "fresh":
                        state_text = _L("fresh", "fresh")
                        state_attr = curses.color_pair(5)
                    elif state == "stale":
                        state_text = _L("stale", "stale")
                        state_attr = curses.color_pair(4)
                    else:
                        state_text = _L("none", "none")
                        state_attr = curses.A_DIM
                    if item.get("warming_models"):
                        state_text += "+warm"
                    provider_text = str(item.get("provider_name") or item.get("provider_id") or "-")
                    if item.get("available_models"):
                        provider_text += f" ({item['measured_models']}/{item['available_models']})"
                    pri_text = f"{int(item.get('current_priority', 0) or 0)}->{int(item.get('suggested_priority', 0) or 0)}"
                    age_text = _format_age(item.get("best_age_seconds"))

                    _safe_addstr(stdscr, y, px + 2, provider_text, attr, max_w=30)
                    _safe_addstr(stdscr, y, px + 34, state_text, state_attr | attr, max_w=10)
                    _safe_addstr(stdscr, y, px + 46, _format_ttfb(item.get("effective_ttfb_ms")), attr, max_w=8)
                    _safe_addstr(stdscr, y, px + 56, str(item.get("samples", 0) or 0), attr, max_w=8)
                    _safe_addstr(stdscr, y, px + 64, age_text, curses.A_DIM | attr, max_w=4)
                    pri_attr = (curses.color_pair(5) if item.get("priority_diff", 0) > 0 else curses.color_pair(4)) | attr
                    if item.get("priority_diff", 0) == 0:
                        pri_attr = curses.A_DIM | attr
                    _safe_addstr(stdscr, y, px + 67, pri_text, pri_attr, max_w=box_w - 69)

            footer_y = py + box_h - 2
            if plan.get("can_apply"):
                footer = _L("↑↓ 查看  Enter 应用  Esc 返回", "Up/Down Preview  Enter Apply  Esc Back")
                footer_attr = curses.color_pair(4) | curses.A_BOLD
            else:
                footer = _L("↑↓ 查看  Esc 返回", "Up/Down Preview  Esc Back")
                footer_attr = curses.A_DIM
            _safe_addstr(stdscr, footer_y, px + 2, footer, footer_attr, max_w=box_w - 4)
            stdscr.refresh()

            key = stdscr.getch()
            if key == -1:
                continue
            if key == curses.KEY_UP and items:
                selected_idx = (selected_idx - 1) % len(items)
            elif key == curses.KEY_DOWN and items:
                selected_idx = (selected_idx + 1) % len(items)
            elif key in (10, 13, curses.KEY_ENTER):
                if plan.get("can_apply"):
                    return _apply_family_autosort()
            elif key in (27, ord('q'), ord('Q'), curses.KEY_LEFT):
                return None

    def _inner(stdscr):
        curses.curs_set(0)
        stdscr.timeout(120)
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
        provider_scroll_map = {}
        focus = "model"
        search_query = ""
        marquee_tick = 0
        last_tick_at = time.monotonic()
        marquee_key = None

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

        try:
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
                rl = px + left_w + 2
                rr = px + total_w - 2

                row = py

                _safe_addstr(stdscr, row, px, "-" * total_w, fc)
                row += 1

                has_changes = bool(provider_overrides or priority_changes)
                title = f"{family_name}" + (" *" if has_changes else "")
                _safe_addstr(stdscr, row, ll, title, fc | curses.A_BOLD)
                cnt_info = f"{len(filtered)}/{len(sorted_models)}" if search_query else str(len(sorted_models))
                _safe_addstr(stdscr, row, rr - len(cnt_info) - 6, cnt_info, curses.A_DIM)
                _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
                row += 1

                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1

                if search_query:
                    _safe_addstr(stdscr, row, ll, f"/ {search_query}_", curses.color_pair(4) | curses.A_BOLD)
                    row += 1

                model_header_attr = (curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE) if focus == "model" else (fc | curses.A_BOLD)
                provider_header_attr = (curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE) if focus == "provider" else curses.A_DIM
                _safe_addstr(stdscr, row, ll + 1, _L("模型", "Model"), model_header_attr)
                _safe_addstr(stdscr, row, rl + 1, _L("通道", "Channel"), provider_header_attr)
                row += 1

                _safe_addstr(stdscr, row, px, "-" * left_w + "+" + "-" * (right_w - 1), curses.A_DIM)
                row += 1

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
                    provider_scroll = provider_scroll_map.get(model_name, 0)
                    selected_provider_idx = provider_idx_map.get(model_name, 0)
                    provider_visible = max(1, visible)
                    if selected_provider_idx < provider_scroll:
                        provider_scroll = selected_provider_idx
                    elif selected_provider_idx >= provider_scroll + provider_visible:
                        provider_scroll = selected_provider_idx - provider_visible + 1
                    provider_scroll = max(0, min(provider_scroll, max(0, len(current_choices) - provider_visible)))
                    provider_scroll_map[model_name] = provider_scroll
                    new_marquee_key = f"{model_name}:{selected_provider_idx}:{focus}"
                else:
                    provider_scroll = 0
                    new_marquee_key = None

                if new_marquee_key != marquee_key:
                    marquee_key = new_marquee_key
                    marquee_tick = 0
                    last_tick_at = time.monotonic()

                for i in range(scroll, min(scroll + visible, len(filtered))):
                    y = content_y + (i - scroll)
                    m = filtered[i]
                    is_sel = (i == idx)
                    model_name = m["model"]

                    _safe_addstr(stdscr, y, px + left_w, "|", curses.A_DIM)

                    if is_sel:
                        marker_attr = fc | curses.A_BOLD if focus == "model" else curses.color_pair(4) | curses.A_BOLD
                        name_attr = curses.color_pair(1) | curses.A_BOLD | (curses.A_REVERSE if focus == "model" else 0)
                        if focus == "model":
                            _safe_addstr(stdscr, y, ll + 1, " " * max(1, left_w - 4), name_attr)
                        _safe_addstr(stdscr, y, ll - 1, "|", marker_attr)
                        visible_model = _marquee_text(model_name, left_w - 4, marquee_tick)
                        _safe_addstr(stdscr, y, ll + 1, visible_model, name_attr, max_w=left_w - 4)
                    else:
                        _safe_addstr(stdscr, y, ll + 1, model_name, curses.color_pair(2), max_w=left_w - 4)

                for offset in range(visible):
                    y = content_y + offset
                    opt_index = provider_scroll + offset
                    if opt_index >= len(current_choices):
                        continue
                    opt = current_choices[opt_index]
                    is_provider_sel = (
                        current_model is not None
                        and provider_idx_map.get(current_model["model"], 0) == opt_index
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
                        visible_text = _marquee_text(tag_text, right_w - 4, marquee_tick)
                        _safe_addstr(stdscr, y, rl + 1, visible_text, text_attr, max_w=right_w - 4)
                    elif opt.get("provider_id") == active_provider_id:
                        _safe_addstr(stdscr, y, rl + 1, tag_text, curses.color_pair(5), max_w=right_w - 4)
                    else:
                        _safe_addstr(stdscr, y, rl + 1, tag_text, curses.A_DIM, max_w=right_w - 4)

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
                    auto_x = adjust_x + 12
                    _safe_addstr(stdscr, bot_y, auto_x, "A", curses.color_pair(4) | curses.A_BOLD)
                    _safe_addstr(stdscr, bot_y, auto_x + 2, _L("智排", "Auto"), curses.color_pair(4) | curses.A_DIM)
                    enter_x = auto_x + 8
                    _safe_addstr(stdscr, bot_y, enter_x, "Enter", curses.color_pair(1) | curses.A_BOLD)
                    _safe_addstr(stdscr, bot_y, enter_x + 6, _L("确认", "Confirm"), curses.A_DIM)
                    _safe_addstr(stdscr, bot_y, enter_x + 12, "Esc", curses.A_BOLD)
                    _safe_addstr(stdscr, bot_y, enter_x + 16, _L("返回", "Back"), curses.A_DIM)
                bot_y += 1
                _safe_addstr(stdscr, bot_y, px, "-" * total_w, fc)

                stdscr.refresh()
                key = stdscr.getch()

                now = time.monotonic()
                if now - last_tick_at >= 0.18:
                    marquee_tick += 1
                    last_tick_at = now

                if key == -1:
                    continue
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
                        _adjust_provider_priority(chosen, +5)
                        _sync_provider_cursor(current_model, chosen.get("provider_id", ""))
                elif key in (ord('-'), ord('_')) and not search_query:
                    if focus == "provider" and current_model and current_choices:
                        chosen = current_choices[provider_idx_map.get(current_model["model"], 0)]
                        _adjust_provider_priority(chosen, -5)
                        _sync_provider_cursor(current_model, chosen.get("provider_id", ""))
                elif key in (ord('a'), ord('A')) and not search_query:
                    _show_family_autosort_modal(stdscr)
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
                    search_query += chr(key)
                    idx = 0
                    scroll = 0
        finally:
            stdscr.timeout(-1)

    if stdscr is not None:
        try:
            return _inner(stdscr)
        except curses.error:
            return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_review_models_tui(options, selected_models=None, title=None):
    """Review profile multi-select: Space toggles reviewers, Enter confirms."""
    options = [opt for opt in (options or []) if isinstance(opt, dict) and opt.get("model")]
    if not options:
        return None

    selected = {
        str(model or "").strip().lower()
        for model in (selected_models or [])
        if str(model or "").strip()
    }

    def _option_key(opt):
        return str(opt.get("model") or "").strip().lower()

    def _selected_models_in_option_order():
        return [
            str(opt.get("model") or "").strip()
            for opt in options
            if _option_key(opt) in selected and str(opt.get("model") or "").strip()
        ]

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)

        idx = 0
        scroll = 0
        search = ""
        status_text = ""

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            query = search.lower().strip()
            if query:
                filtered = [
                    opt for opt in options
                    if query in str(opt.get("model") or "").lower()
                    or query in str(opt.get("family") or "").lower()
                    or query in str(opt.get("provider_name") or "").lower()
                ]
            else:
                filtered = list(options)
            if not filtered:
                filtered = list(options)
            idx = max(0, min(idx, len(filtered) - 1))

            total_w = min(82, max_w - 4)
            visible = max(1, min(len(filtered), max_y - 9))
            ph = visible + 7 + (1 if search else 0) + (1 if status_text else 0)
            px = max(0, (max_w - total_w) // 2)
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.color_pair(1))
            row += 1
            header = title or _L("Review 模型多选", "Review Model Multi-select")
            _safe_addstr(stdscr, row, ll, header, curses.color_pair(1) | curses.A_BOLD)
            count_text = f"{len(selected)} selected"
            _safe_addstr(stdscr, row, rr - len(count_text), count_text, curses.color_pair(5) | curses.A_BOLD)
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
                y = content_y + i - scroll
                opt = filtered[i]
                model = str(opt.get("model") or "").strip()
                family = str(opt.get("family") or "").strip()
                provider = str(opt.get("provider_name") or "").strip()
                is_selected = _option_key(opt) in selected
                is_cursor = i == idx
                mark = "[x]" if is_selected else "[ ]"
                left = f"{mark} {model}"
                right = " / ".join(part for part in (family, provider) if part)
                attr = curses.color_pair(1) | curses.A_REVERSE if is_cursor else curses.color_pair(2)
                if is_selected and not is_cursor:
                    attr = curses.color_pair(5) | curses.A_BOLD
                _safe_addstr(stdscr, y, ll, " " * max(1, total_w - 4), attr if is_cursor else 0)
                _safe_addstr(stdscr, y, ll, left, attr, max_w=max(10, total_w - 30))
                if right:
                    _safe_addstr(stdscr, y, rr - min(26, _display_width(right)), right, curses.A_DIM, max_w=26)

            bot_y = content_y + visible
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            if status_text:
                _safe_addstr(stdscr, bot_y, ll, status_text, curses.color_pair(4) | curses.A_DIM, max_w=total_w - 4)
                bot_y += 1
            if search:
                _safe_addstr(stdscr, bot_y, ll, _L("Esc 清除", "Esc Clear"), curses.color_pair(4) | curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 11, _L("BS 删字", "BS Delete"), curses.A_DIM)
                _safe_addstr(stdscr, bot_y, ll + 20, _L("Space 勾选", "Space Toggle"), curses.color_pair(5) | curses.A_DIM)
            else:
                footer = "Space 勾选  Enter 启动并记住  A 全选  C 清空  直接输入搜索  Esc 返回"
                _safe_addstr(stdscr, bot_y, ll, footer, curses.A_DIM, max_w=total_w - 4)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.color_pair(1))

            stdscr.refresh()
            key = stdscr.getch()
            status_text = ""

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(filtered)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(filtered)
            elif key == ord(" "):
                if filtered:
                    key_name = _option_key(filtered[idx])
                    if key_name in selected:
                        selected.remove(key_name)
                    else:
                        selected.add(key_name)
            elif key in (10, 13, curses.KEY_ENTER):
                if not selected and filtered:
                    selected.add(_option_key(filtered[idx]))
                chosen = _selected_models_in_option_order()
                if chosen:
                    return chosen
                status_text = _L("至少选择一个模型", "Select at least one model")
            elif key in (ord("a"), ord("A")) and not search:
                for opt in filtered:
                    selected.add(_option_key(opt))
            elif key in (ord("c"), ord("C")) and not search:
                selected.clear()
            elif key == 27:
                if search:
                    search = ""
                    idx = 0
                    scroll = 0
                else:
                    return None
            elif key in (ord("q"), ord("Q")) and not search:
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if search:
                    search = search[:-1]
                    idx = 0
                    scroll = 0
            elif 32 <= key <= 126:
                if key != ord(" "):
                    search += chr(key)
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

_LB_HISTORY_PATH = os.path.join(resolve_mms_config_dir(), "lb_history.json")
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


def _settings_menu():
    current_lang = _get_language()
    language_desc = _L("当前：英文", "Current: English") if current_lang == "en" else _L("当前：中文", "Current: Chinese")
    return [
        {"id": "provider_mgmt", "label": _L("Provider 管理", "Provider Management"), "desc": _L("查看/调整 role 与 priority", "Inspect and adjust role / priority")},
        {"id": "account_mgmt", "label": _L("账号管理", "Account Management"), "desc": _L("查看 OAuth 账号状态", "Inspect OAuth account status")},
        {"id": "registry", "label": _L("模型真源", "Registry Truth"), "desc": _L("模型 DB / source truth", "Model DB / source truth")},
        {"id": "guard", "label": _L("启动快照", "Snapshot Guard"), "desc": _L("查看/接受 config drift", "Inspect / accept config drift")},
        {"id": "rescue", "label": _L("中断/救援", "Interrupted / Rescue"), "desc": _L("设置 fallback / 最近失败", "Set fallback / recent failures")},
        {"id": "language", "label": _L("界面语言", "UI Language"), "desc": language_desc},
        {"id": "routes_export", "label": _L("Legacy 路由导出", "Legacy Route Export"), "desc": _L("兼容导出 model-routes.json；v2 发布请进模型真源", "Compatibility export for model-routes.json; use Registry Truth for v2 publish")},
        {"id": "about", "label": _L("关于", "About"), "desc": _L("版本与环境信息", "Version and environment info")},
    ]


def select_language_tui():
    options = [
        {"id": "zh", "label": "中文", "desc": _L("使用中文界面", "Use Simplified Chinese UI")},
        {"id": "en", "label": "English", "desc": _L("使用英文界面", "Use English UI")},
    ]

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        current_lang = _get_language()
        idx = 0 if current_lang == "zh" else 1
        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)
            total_w = min(56, max_w - 4)
            ph = len(options) + 5
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, _L("界面语言", "UI Language"), curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for i, item in enumerate(options):
                y = row + i
                is_sel = i == idx
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(1) | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 14, item["desc"], curses.color_pair(1) | curses.A_DIM)
                else:
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(2))
                    _safe_addstr(stdscr, y, ll + 14, item["desc"], curses.A_DIM)

            bot_y = row + len(options)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, _L("切换", "Apply"), curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 14, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 18, _L("返回", "Back"), curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(options)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                return options[idx]["id"]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


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
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(1) | curses.A_BOLD, max_w=16)
                    _safe_addstr(stdscr, y, ll + 18, item["desc"], curses.color_pair(1) | curses.A_DIM, max_w=max(1, rr - (ll + 18)))
                else:
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(2), max_w=16)
                    _safe_addstr(stdscr, y, ll + 18, item["desc"], curses.A_DIM, max_w=max(1, rr - (ll + 18)))

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


def _rescue_event_title(event):
    created = str(event.get("created_at") or "")[:19].replace("T", " ")
    model = str(event.get("failed_model") or "unknown")
    status = str(event.get("status_code") or event.get("failure_kind") or "")
    return f"{created}  {model}  {status}".strip()


def select_rescue_event_tui(events):
    """选择最近的 Rescue packet。"""
    events = list(events or [])

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
            total_w = min(92, max_w - 4)
            visible_h = max(1, min(len(events), max_y - 10))
            ph = visible_h + 7
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, _L("中断/救援", "Interrupted / Rescue"), curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            if not events:
                _safe_addstr(stdscr, row, ll + 1, _L("没有找到 rescue packet", "No rescue packets found"), curses.A_DIM)
                row += 1
            else:
                start = max(0, min(idx - visible_h + 1, len(events) - visible_h))
                for offset, event in enumerate(events[start:start + visible_h]):
                    i = start + offset
                    y = row + offset
                    is_sel = i == idx
                    repo_name = os.path.basename(str(event.get("repo_path") or "")) or "-"
                    provider = str(event.get("failed_provider_id") or "-")
                    line = f"{_rescue_event_title(event)}  · {provider} · {repo_name}"
                    if is_sel:
                        _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                        _safe_addstr(stdscr, y, ll + 1, line, curses.color_pair(1) | curses.A_BOLD, max_w=total_w - 6)
                    else:
                        _safe_addstr(stdscr, y, ll + 1, line, curses.color_pair(2), max_w=total_w - 6)
                row += visible_h

            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1
            if events:
                _safe_addstr(stdscr, row, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
                _safe_addstr(stdscr, row, ll + 6, _L("详情", "Details"), curses.A_DIM)
                _safe_addstr(stdscr, row, ll + 15, "Esc", curses.A_BOLD)
                _safe_addstr(stdscr, row, ll + 19, _L("返回", "Back"), curses.A_DIM)
            else:
                _safe_addstr(stdscr, row, ll, "Esc", curses.A_BOLD)
                _safe_addstr(stdscr, row, ll + 4, _L("返回", "Back"), curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and events:
                idx = (idx - 1) % len(events)
            elif key == curses.KEY_DOWN and events:
                idx = (idx + 1) % len(events)
            elif key in (10, 13, curses.KEY_ENTER) and events:
                return events[idx]
            elif key in (27, ord('q'), ord('Q')):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_fake_upstream_tui():
    options = [
        {"id": "on", "label": _L("开启", "Enable"), "desc": _L("开发时拦截真实上游请求", "Block real upstream requests in development")},
        {"id": "off", "label": _L("关闭", "Disable"), "desc": _L("恢复真实上游请求", "Restore real upstream requests")},
    ]

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)

        status = _fake_upstream_status_payload()
        idx = 0 if not status.get("enabled") else 1

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(1)

            total_w = min(72, max_w - 4)
            ph = len(options) + 7
            px = (max_w - total_w) // 2
            py = max(1, (max_y - ph) // 2)
            ll = px + 2
            rr = px + total_w - 2

            row = py
            _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            row += 1
            _safe_addstr(stdscr, row, ll, "Fake Upstream", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, row, rr - 5, "Esc <-", curses.A_DIM)
            row += 1
            _safe_addstr(
                stdscr,
                row,
                ll,
                _L("当前状态：开启" if status.get("enabled") else "当前状态：关闭",
                   "Current: Enabled" if status.get("enabled") else "Current: Disabled"),
                curses.A_DIM,
                max_w=total_w - 4,
            )
            row += 1
            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1

            for i, item in enumerate(options):
                y = row + i
                is_sel = i == idx
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(1) | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 14, item["desc"], curses.color_pair(1) | curses.A_DIM, max_w=total_w - 18)
                else:
                    _safe_addstr(stdscr, y, ll + 1, item["label"], curses.color_pair(2))
                    _safe_addstr(stdscr, y, ll + 14, item["desc"], curses.A_DIM, max_w=total_w - 18)

            bot_y = row + len(options)
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, _L("应用", "Apply"), curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 14, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 18, _L("返回", "Back"), curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP:
                idx = (idx - 1) % len(options)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                return options[idx]["id"]
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
    except (curses.error, KeyboardInterrupt):
        return None


def select_channel_action_tui(title, info_lines, actions):
    """通道详情+操作选择 — H6 settings-card style。

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

            total_w = min(76, max_w - 4)
            detail_h = min(len(info_lines), max(2, max_y - len(actions) - 9))
            hidden_details = max(0, len(info_lines) - detail_h)
            content_h = detail_h + len(actions) + 4
            ph = min(max_y - 2, content_h + 5)
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

            _safe_addstr(stdscr, row, ll, _L("信息", "Info"), curses.color_pair(4) | curses.A_BOLD)
            row += 1

            label_w = min(16, max(8, total_w // 4))
            value_x = ll + label_w + 2
            for offset, (label, value) in enumerate(info_lines[:detail_h]):
                y = row + offset
                label_text = str(label or "-")
                value_text = str(value or "-")
                _safe_addstr(stdscr, y, ll, label_text, curses.color_pair(4) | curses.A_DIM, max_w=label_w)
                _safe_addstr(stdscr, y, value_x, value_text, curses.color_pair(2), max_w=max(8, rr - value_x))
            row += detail_h
            if hidden_details:
                _safe_addstr(stdscr, row, ll, _L(f"+ {hidden_details} 项更多", f"+ {hidden_details} more"), curses.A_DIM)
                row += 1

            _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
            row += 1
            _safe_addstr(stdscr, row, ll, _L("操作", "Actions"), curses.color_pair(4) | curses.A_BOLD)
            row += 1

            for offset, (_aid, alabel) in enumerate(actions):
                y = row + offset
                alabel = str(alabel or "-")
                is_sel = (offset == idx)
                if is_sel:
                    _safe_addstr(stdscr, y, ll - 1, "|", ac | curses.A_BOLD)
                    _safe_addstr(stdscr, y, ll + 1, alabel, curses.color_pair(1) | curses.A_BOLD, max_w=total_w - 6)
                else:
                    _safe_addstr(stdscr, y, ll + 1, alabel, curses.color_pair(2), max_w=total_w - 6)
            row += len(actions)

            bot_y = row
            _safe_addstr(stdscr, bot_y, px, "-" * total_w, curses.A_DIM)
            bot_y += 1
            _safe_addstr(stdscr, bot_y, ll, "Enter", curses.color_pair(1) | curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 6, _L("执行", "Run"), curses.A_DIM)
            _safe_addstr(stdscr, bot_y, ll + 13, "Esc", curses.A_BOLD)
            _safe_addstr(stdscr, bot_y, ll + 17, _L("返回", "Back"), curses.A_DIM)
            if len(actions) > 1:
                _safe_addstr(stdscr, bot_y, rr - 12, "Up/Dn", curses.color_pair(4) | curses.A_BOLD)
                _safe_addstr(stdscr, bot_y, rr - 6, _L("选择", "Select"), curses.A_DIM)
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
    except (curses.error, KeyboardInterrupt):
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


def confirm_tui(
    cli,
    model_info,
    env_vars=None,
    once=False,
    context_lines=None,
    *,
    has_caveman=False,
    caveman_enabled_default=False,
    caveman_level_default="light",
    has_nsr=False,
    nsr_enabled_default=True,
    has_ecc=False,
    ecc_enabled_default=False,
    has_omc=False,
    agent_pack_default="none",
    thinking_enabled_default=True,
    reasoning_effort_default="high",
    preview_catalog=None,
    runtime=None,
):
    """确认启动 TUI。

    返回 (action, bypass, claude_1m_enabled, caveman_enabled, agent_pack, thinking_enabled, reasoning_effort, disabled_session_surfaces, nsr_enabled, caveman_level)。
    action: "" = 启动, "b" = 返回, "q" = 取消
        bypass: bool, codex/claude/opencode/agy 有效；OpenCode 会启用 permission allow
    claude_1m_enabled: bool，仅 Claude Opus/Sonnet 有效，True 时本次启动开启 1M
        caveman_enabled: bool，仅 claude/codex/opencode/agy 且 Caveman 可用时有效，True 时本次会话开启 Caveman
    caveman_level: "light" / "standard" / "full"，仅 Caveman 开启时有效
    nsr_enabled: bool，仅 claude/codex 且 NSR hook 可用时有效，True 时本次会话开启 NSR hooks
    agent_pack: "none" / "ecc" / "omc"，仅 Claude 国产模型能力包有效；三选一互斥
    thinking_enabled: bool，仅 GPT / 已验证 domestic thinking 路径有效
    reasoning_effort: str，仅 GPT / 支持 effort 的路径有效
    """
    def _model_tokens(info):
        values = []
        if isinstance(info, dict):
            values.extend(str(v or "") for k, v in info.items() if k != "subagent")
        else:
            values.append(str(info or ""))
        normalized = []
        for item in values:
            value = str(item or "").strip().lower()
            if "/" in value:
                value = value.rsplit("/", 1)[-1]
            if value:
                normalized.append(value)
        return normalized

    def _is_gpt_like_token(token):
        return token.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))

    def _supports_domestic_thinking_token(token):
        if token.startswith(("glm", "kimi", "k2.5", "k2.6", "minimax", "deepseek")):
            return True
        if token.startswith(("mimo", "qwen-coder", "qwen3-coder")):
            return False
        if token.startswith("qwen"):
            return token.startswith(("qwen-plus", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max"))
        return False

    def _supports_domestic_effort_token(token):
        return token.startswith("deepseek")

    def _normalize_caveman_level(value):
        raw = str(value or "").strip().lower().replace("_", "-")
        if raw in {"light", "lite", "low"}:
            return "light"
        if raw in {"standard", "normal", "medium"}:
            return "standard"
        if raw in {"full", "ultra", "high"}:
            return "full"
        return "light"

    def _caveman_level_text(value):
        value = str(value or "").strip().lower()
        if value == "disable":
            return _L("关闭", "Off")
        if value == "standard":
            return "Standard"
        if value == "full":
            return "Full"
        return "Light"

    def _supports_claude_1m_toggle(info):
        values = []
        if isinstance(info, dict):
            values.extend(str(v or "") for k, v in info.items() if k != "subagent")
        else:
            values.append(str(info or ""))
        for item in values:
            lower = item.strip().lower()
            if lower.startswith("claude-") and "haiku" not in lower and ("opus" in lower or "sonnet" in lower):
                return True
        return False

    def _confirm_label(label):
        mapping = {
            "CLI": _L("客户端", "CLI"),
            "Model": _L("模型", "Model"),
            "Launch": _L("启动", "Launch"),
            "Bypass": _L("绕过审批", "Bypass"),
            "Caveman": "Caveman",
            "NSR": "NSR",
            "Thinking": _L("思考", "Thinking"),
            "Effort": _L("强度", "Effort"),
            "Agent Pack": _L("能力包", "Agent Pack"),
            "ECC": "ECC",
            "OMC": "OMC",
            "URL": _L("地址", "URL"),
            "Key": _L("密钥", "Key"),
            "Active": _L("激活", "Active"),
            "Preset": _L("预设", "Preset"),
            "CLI source": _L("CLI 来源", "CLI source"),
            "Source": _L("来源", "Source"),
            "Proxy": _L("代理", "Proxy"),
            "TZ": "TZ",
            "IPv4": "IPv4",
            "Slot": _L("槽位", "Slot"),
            "Session": _L("会话", "Session"),
            "Email": _L("邮箱", "Email"),
            "UserID": _L("用户 ID", "User ID"),
            "OrgID": _L("组织 ID", "Org ID"),
            "DNS": "DNS",
            "Check": _L("检查", "Check"),
            "IPv4Egress": _L("IPv4 出口", "IPv4 egress"),
            "IPv6Egress": _L("IPv6 出口", "IPv6 egress"),
            "Reach": _L("目标", "Reach"),
            "Leak": _L("泄漏", "Leak"),
            "Score": _L("评分", "Score"),
            "Sessions": _L("会话数", "Sessions"),
            "Profile": _L("画像", "Profile"),
            "Fake": _L("伪上游", "Fake"),
        }
        return mapping.get(str(label or ""), str(label or ""))

    def _confirm_panel_title(panel_key):
        mapping = {
            "summary": _L("摘要", "Summary"),
            "mcp": "MCP",
            "skills": _L("技能", "Skills"),
            "hooks": _L("钩子", "Hooks"),
        }
        return mapping.get(str(panel_key or ""), str(panel_key or ""))

    def _confirm_panel_empty_message(panel_key):
        allow_execution_surfaces = True
        if isinstance(preview_catalog, dict):
            allow_execution_surfaces = bool(preview_catalog.get("allow_execution_surfaces", True))
        if not allow_execution_surfaces:
            mapping = {
                "mcp": _L("当前启动路径不会注入托管 MCP。", "This launch path does not inject managed MCP."),
                "skills": _L("当前启动路径不会注入托管技能。", "This launch path does not inject managed skills."),
                "hooks": _L("当前启动路径不会注入托管钩子。", "This launch path does not inject managed hooks."),
            }
            return mapping.get(str(panel_key or ""), _L("当前面板没有可展示内容。", "No managed content for this panel."))
        mapping = {
            "mcp": _L("当前没有可预览的 MCP。", "No managed MCP to preview."),
            "skills": _L("当前没有可预览的技能。", "No managed skills to preview."),
            "hooks": _L("当前没有可预览的钩子。", "No managed hooks to preview."),
        }
        return mapping.get(str(panel_key or ""), _L("当前面板没有可展示内容。", "Nothing to show on this panel."))

    def _collect_preview_items(panel_key, *, caveman_enabled=False, nsr_enabled=False, agent_pack="none"):
        panel_key = str(panel_key or "").strip()
        if not isinstance(preview_catalog, dict):
            return []
        sections = preview_catalog.get(panel_key)
        if not isinstance(sections, dict):
            return []
        items = []
        seen = set()
        for scope in ("always",):
            for item in sections.get(scope) or []:
                if not isinstance(item, dict):
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    item = {"title": str(item[0]), "summary": str(item[1]), "details": []}
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                details = []
                for detail in item.get("details") or []:
                    if not isinstance(detail, (list, tuple)) or len(detail) < 2:
                        continue
                    label = str(detail[0] or "").strip()
                    value = str(detail[1] or "").strip()
                    if label and value:
                        details.append((label, value))
                signature = (title, summary, tuple(details))
                disable_key = str(item.get("disable_key") or title).strip()
                if title and signature not in seen:
                    seen.add(signature)
                    items.append({"title": title, "summary": summary, "details": details, "disable_key": disable_key})
        if caveman_enabled:
            for item in sections.get("caveman") or []:
                if not isinstance(item, dict):
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    item = {"title": str(item[0]), "summary": str(item[1]), "details": []}
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                details = []
                for detail in item.get("details") or []:
                    if not isinstance(detail, (list, tuple)) or len(detail) < 2:
                        continue
                    label = str(detail[0] or "").strip()
                    value = str(detail[1] or "").strip()
                    if label and value:
                        details.append((label, value))
                signature = (title, summary, tuple(details))
                disable_key = str(item.get("disable_key") or title).strip()
                if title and signature not in seen:
                    seen.add(signature)
                    items.append({"title": title, "summary": summary, "details": details, "disable_key": disable_key})
        if nsr_enabled:
            for item in sections.get("nsr") or []:
                if not isinstance(item, dict):
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    item = {"title": str(item[0]), "summary": str(item[1]), "details": []}
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                details = []
                for detail in item.get("details") or []:
                    if not isinstance(detail, (list, tuple)) or len(detail) < 2:
                        continue
                    label = str(detail[0] or "").strip()
                    value = str(detail[1] or "").strip()
                    if label and value:
                        details.append((label, value))
                signature = (title, summary, tuple(details))
                disable_key = str(item.get("disable_key") or title).strip()
                if title and signature not in seen:
                    seen.add(signature)
                    items.append({"title": title, "summary": summary, "details": details, "disable_key": disable_key})
        pack_key = str(agent_pack or "none").strip().lower()
        if pack_key in {"ecc", "omc"}:
            for item in sections.get(pack_key) or []:
                if not isinstance(item, dict):
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    item = {"title": str(item[0]), "summary": str(item[1]), "details": []}
                title = str(item.get("title") or "").strip()
                summary = str(item.get("summary") or "").strip()
                details = []
                for detail in item.get("details") or []:
                    if not isinstance(detail, (list, tuple)) or len(detail) < 2:
                        continue
                    label = str(detail[0] or "").strip()
                    value = str(detail[1] or "").strip()
                    if label and value:
                        details.append((label, value))
                signature = (title, summary, tuple(details))
                disable_key = str(item.get("disable_key") or title).strip()
                if title and signature not in seen:
                    seen.add(signature)
                    items.append({"title": title, "summary": summary, "details": details, "disable_key": disable_key})
        return items

    if isinstance(model_info, dict):
        model_display = ", ".join(f"{k}={v}" for k, v in model_info.items()
                                  if k != "subagent")
    else:
        model_display = str(model_info)

    detail_lines = []
    if env_vars:
        preferred_keys = [
            ("ANTHROPIC_BASE_URL", "URL"),
            ("OPENAI_BASE_URL", "URL"),
            ("ANTHROPIC_AUTH_TOKEN", "Key"),
            ("OPENAI_API_KEY", "Key"),
            ("GEMINI_API_KEY", "Key"),
            ("MMS_ACTIVE_MODEL", "Active"),
            ("MMS_ACTIVE_PRESET", "Preset"),
            ("MMS_ACTIVE_CLI", "CLI source"),
        ]
        seen = set()
        for env_key, label in preferred_keys:
            if env_key in env_vars:
                value = env_vars.get(env_key, "")
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                detail_lines.append((_confirm_label(label), value, "detail"))
                seen.add(env_key)
        for env_key, value in env_vars.items():
            if env_key in seen:
                continue
            upper_key = env_key.upper()
            if any(token in upper_key for token in ("BASE_URL", "API_KEY", "AUTH_TOKEN", "ACTIVE_", "MODEL")):
                if "key" in env_key.lower() or "token" in env_key.lower() or "auth" in env_key.lower():
                    value = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                label = env_key[:6] + "…" if len(env_key) > 7 else env_key
                detail_lines.append((label, value, "detail"))
        detail_lines = detail_lines[:4]
    if context_lines:
        for item in context_lines:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            raw_label = str(item[0])
            detail_lines.append((_confirm_label(raw_label), str(item[1]), "fake" if raw_label == "Fake" else "detail"))
    detail_lines = detail_lines[:10]

    profile_caps = _confirm_profile_capabilities(model_info, runtime=runtime)
    model_tokens = profile_caps["tokens"] or _model_tokens(model_info)
    has_bypass = cli in ("codex", "claude", "opencode", "agy")
    has_reasoning_controls = cli in ("codex", "claude")
    has_claude_1m = cli == "claude" and _supports_claude_1m_toggle(model_info)
    has_thinking = has_reasoning_controls and bool(profile_caps["thinking_supported"])
    has_effort = has_reasoning_controls and bool(profile_caps["effort_supported"])
    effort_values = _confirm_effort_values(profile_caps, model_tokens)
    effort_default = str(reasoning_effort_default or "high").strip().lower()
    if effort_default not in effort_values:
        effort_default = "high" if "high" in effort_values else effort_values[-1]
    initial_bypass_mode = bool((runtime or {}).get("bypass", True)) if isinstance(runtime, dict) else True
    explicit_thinking_default = _confirm_explicit_thinking_default(runtime)
    profile_thinking_default = profile_caps.get("default_enabled")
    if explicit_thinking_default is not None:
        initial_thinking_enabled = explicit_thinking_default
    elif isinstance(profile_thinking_default, bool):
        initial_thinking_enabled = profile_thinking_default
    else:
        initial_thinking_enabled = bool(thinking_enabled_default)
    pack_options = ["none"]
    if has_ecc:
        pack_options.append("ecc")
    if has_omc:
        pack_options.append("omc")
    default_pack = str(agent_pack_default or "").strip().lower()
    if default_pack not in pack_options:
        default_pack = "ecc" if bool(has_ecc and ecc_enabled_default) else "none"
    has_agent_pack = len(pack_options) > 1
    pack_key = _ECC_TOGGLE_KEY
    caveman_options = ["disable", "light", "standard", "full"]
    initial_caveman_level = _normalize_caveman_level(caveman_level_default)
    if not (has_caveman and caveman_enabled_default):
        initial_caveman_level = "disable"

    def _agent_pack_text(value):
        value = str(value or "none").strip().lower()
        if value == "ecc":
            return _L("ECC · 工程 workflow / rules / quality hooks", "ECC · engineering workflow / rules / quality hooks")
        if value == "omc":
            return _L("OMC · orchestration runtime / team / verify loop", "OMC · orchestration runtime / team / verify loop")
        return _L("关闭", "Off")

    def _initial_disabled_surfaces():
        payload = (runtime or {}).get("disabled_session_surfaces") if isinstance(runtime, dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        result = {"mcp": set(), "skills": set(), "hooks": set()}
        aliases = {
            "mcp": "mcp",
            "mcps": "mcp",
            "mcp_servers": "mcp",
            "skills": "skills",
            "skill": "skills",
            "hooks": "hooks",
            "hook": "hooks",
        }
        for raw_key, raw_values in payload.items():
            key = aliases.get(str(raw_key or "").strip().lower())
            if key not in result:
                continue
            if isinstance(raw_values, str):
                raw_values = [raw_values]
            if not isinstance(raw_values, (list, tuple, set)):
                continue
            for item in raw_values:
                value = str(item or "").strip()
                if value:
                    result[key].add(value)
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

        bypass_mode = initial_bypass_mode
        claude_1m_mode = False
        caveman_level = initial_caveman_level
        nsr_mode = bool(has_nsr and nsr_enabled_default)
        agent_pack = default_pack
        thinking_mode = bool(has_thinking and initial_thinking_enabled)
        effort_mode = effort_default
        panel_index = 0
        preview_selection = {"mcp": 0, "skills": 0, "hooks": 0}
        preview_disabled = _initial_disabled_surfaces()
        disable_mode = False

        def _disabled_payload():
            return {
                key: sorted(str(item) for item in values if str(item).strip())
                for key, values in preview_disabled.items()
                if values
            }

        def _caveman_enabled():
            return bool(has_caveman and caveman_level != "disable")

        def _effort_attr(value, enabled=True):
            if not enabled:
                return curses.color_pair(4) | curses.A_DIM
            if value == "low":
                return curses.color_pair(4) | curses.A_BOLD
            if value == "medium":
                return curses.color_pair(1) | curses.A_BOLD
            if value == "high":
                return curses.color_pair(5) | curses.A_BOLD
            return curses.color_pair(6) | curses.A_BOLD

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            ac = curses.color_pair(3) if bypass_mode else curses.color_pair(5)

            total_w = min(90, max_w - 4)
            info_lines = []
            info_lines.append((_confirm_label("CLI"), cli, "plain"))
            info_lines.append((_confirm_label("Model"), model_display, "plain"))
            info_lines.append((_confirm_label("Launch"), _L("一次性命令", "One-shot command") if once else _L("交互会话", "Interactive session"), "plain"))
            if has_bypass:
                bypass_text = (
                    _L("当前开启 · Tab 关闭", "On · Tab to Off")
                    if bypass_mode
                    else _L("当前关闭 · Tab 开启", "Off · Tab to On")
                )
                info_lines.append((_confirm_label("Bypass"), bypass_text, "bypass"))
            if has_claude_1m:
                one_m_text = _L("开启", "On") if claude_1m_mode else _L("关闭", "Off")
                info_lines.append(("1M", f"[M] {one_m_text}", "one_m"))
            if has_caveman:
                caveman_text = _caveman_level_text(caveman_level)
                info_lines.append((_confirm_label("Caveman"), f"[C] {caveman_text}", "caveman"))
            if has_nsr:
                nsr_text = _L("开启", "On") if nsr_mode else _L("关闭", "Off")
                info_lines.append((_confirm_label("NSR"), f"[N] {nsr_text}", "nsr"))
            if has_thinking:
                thinking_text = _L("开启", "On") if thinking_mode else _L("关闭", "Off")
                info_lines.append((_confirm_label("Thinking"), f"[T] {thinking_text}", "thinking"))
            if has_effort:
                info_lines.append((_confirm_label("Effort"), f"[E] {effort_mode.upper()}", "effort"))
            if has_agent_pack:
                info_lines.append((_confirm_label("Agent Pack"), f"[{pack_key}] {_agent_pack_text(agent_pack)}", "agent_pack"))

            panels = [
                {
                    "key": "summary",
                    "title": _confirm_panel_title("summary"),
                    "mode": "summary",
                    "rows": info_lines + detail_lines,
                }
            ]
            if isinstance(preview_catalog, dict):
                for panel_key in ("mcp", "skills", "hooks"):
                    preview_items = _collect_preview_items(
                        panel_key,
                        caveman_enabled=_caveman_enabled(),
                        nsr_enabled=nsr_mode,
                        agent_pack=agent_pack,
                    )
                    panels.append(
                        {
                            "key": panel_key,
                            "title": _confirm_panel_title(panel_key),
                            "mode": "list",
                            "items": preview_items,
                            "empty_message": _confirm_panel_empty_message(panel_key),
                        }
                    )

            if panel_index >= len(panels):
                panel_index = 0
            current_panel = panels[panel_index]
            px = (max_w - total_w) // 2
            ll = px + 2
            rr = px + total_w - 2
            footer_actions = [
                [("Enter", curses.color_pair(5) | curses.A_BOLD), (" ", 0), (_L("启动", "Launch"), curses.color_pair(5) | curses.A_DIM)],
            ]
            if len(panels) > 1:
                footer_actions.append([("←/→", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切面板", "Switch panel"), curses.color_pair(1) | curses.A_DIM)])
            if current_panel.get("mode") == "list":
                footer_actions.append([("↑/↓", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("看条目", "Browse items"), curses.color_pair(1) | curses.A_DIM)])
                footer_actions.append([("D", curses.color_pair(4) | curses.A_BOLD), (" ", 0), (_L("禁用选择", "Disable select"), curses.color_pair(4) | curses.A_DIM)])
                if disable_mode:
                    footer_actions.append([("Space", curses.color_pair(2) | curses.A_BOLD), (" ", 0), (_L("切禁用", "Toggle disable"), curses.color_pair(2) | curses.A_DIM)])
            if has_bypass:
                footer_actions.append([("Tab", curses.color_pair(4) | curses.A_BOLD), (" ", 0), (_L("切 Bypass", "Toggle Bypass"), curses.color_pair(4) | curses.A_DIM)])
            if has_claude_1m:
                footer_actions.append([("M", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切 1M", "Toggle 1M"), curses.color_pair(1) | curses.A_DIM)])
            if has_caveman:
                footer_actions.append([("C", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切 Caveman 档位", "Cycle Caveman"), curses.color_pair(1) | curses.A_DIM)])
            if has_nsr:
                footer_actions.append([("N", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切 NSR", "Toggle NSR"), curses.color_pair(1) | curses.A_DIM)])
            if has_thinking:
                footer_actions.append([("T", curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切思考", "Toggle Thinking"), curses.color_pair(1) | curses.A_DIM)])
            if has_effort:
                footer_actions.append([("E", curses.color_pair(6) | curses.A_BOLD), (" ", 0), (_L("切强度", "Cycle Effort"), curses.color_pair(6) | curses.A_DIM)])
            if has_agent_pack:
                footer_actions.append([(pack_key, curses.color_pair(1) | curses.A_BOLD), (" ", 0), (_L("切能力包", "Cycle Agent Pack"), curses.color_pair(1) | curses.A_DIM)])
            footer_actions.extend([
                [("B", curses.A_BOLD), (" ", 0), (_L("返回", "Back"), curses.A_DIM)],
                [("Q", curses.A_BOLD), (" ", 0), (_L("取消", "Cancel"), curses.A_DIM)],
            ])
            footer_rows = _measure_footer_actions(rr - ll + 1, footer_actions)

            title = _L("绕过审批确认", "Bypass Confirm") if bypass_mode else _L("确认启动", "Confirm Launch")
            if len(panels) > 1:
                title = f"{title} · {current_panel['title']} [{panel_index + 1}/{len(panels)}]"
            if current_panel.get("mode") == "list" and disable_mode:
                title = f"{title} · {_L('禁用选择', 'Disable select')}"

            if current_panel.get("mode") == "list":
                panel_key = str(current_panel.get("key") or "")
                items = list(current_panel.get("items") or [])
                if items:
                    cursor = max(0, min(preview_selection.get(panel_key, 0), len(items) - 1))
                    preview_selection[panel_key] = cursor
                else:
                    cursor = 0
                    preview_selection[panel_key] = 0
                detail_open = bool(items)
                detail_h = 4
                list_h = min(12, max(5, max_y - footer_rows - detail_h - 8))
                ph = list_h + detail_h + footer_rows + 7
                py = max(1, (max_y - ph) // 2)
                row = py
                _safe_addstr(stdscr, row, px, "-" * total_w, ac)
                row += 1
                if items:
                    title = f"{title} ({cursor + 1}/{len(items)})"
                _safe_addstr(stdscr, row, ll, title, ac | curses.A_BOLD)
                row += 1
                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1

                title_w = min(34, max(18, (rr - ll - 6) // 2))
                summary_x = ll + 2 + title_w + 2
                summary_w = max(10, rr - summary_x)
                offset = 0
                if items and cursor >= list_h:
                    offset = cursor - list_h + 1
                if items and cursor < offset:
                    offset = cursor
                visible_items = items[offset: offset + list_h]

                for idx in range(list_h):
                    y = row + idx
                    if idx >= len(visible_items):
                        continue
                    item = visible_items[idx]
                    absolute_idx = offset + idx
                    selected = absolute_idx == cursor
                    disabled_key = str(item.get("disable_key") or item.get("title") or "").strip()
                    is_disabled = disabled_key in preview_disabled.get(panel_key, set())
                    marker_attr = curses.color_pair(1) | curses.A_BOLD if selected else curses.A_DIM
                    title_attr = curses.color_pair(4) if is_disabled else (curses.color_pair(1) | curses.A_BOLD if selected else curses.color_pair(2))
                    summary_attr = curses.color_pair(1) if selected else curses.A_DIM
                    marker = ">" if selected else " "
                    title_text = str(item.get("title") or "")
                    if disable_mode or is_disabled:
                        title_text = ("[x] " if is_disabled else "[ ] ") + title_text
                    _safe_addstr(stdscr, y, ll, marker, marker_attr)
                    _safe_addstr(stdscr, y, ll + 2, title_text, title_attr, max_w=title_w)
                    _safe_addstr(stdscr, y, summary_x, str(item.get("summary") or ""), summary_attr, max_w=summary_w)

                if offset > 0:
                    _safe_addstr(stdscr, row, rr - 1, "^", curses.A_DIM)
                if offset + list_h < len(items):
                    _safe_addstr(stdscr, row + list_h - 1, rr - 1, "v", curses.A_DIM)
                row += list_h
                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1

                detail_preview_lines = []
                if detail_open and items:
                    selected_item = items[cursor]
                    detail_entries = selected_item.get("details") or []
                    label_w = max((_display_width(str(label or "")) for label, _ in detail_entries), default=6)
                    detail_value_x = ll + label_w + 3
                    detail_value_w = max(10, rr - detail_value_x)
                    for label, value in detail_entries:
                        wrapped = _wrap_display_lines(value, detail_value_w)
                        for wrapped_idx, wrapped_value in enumerate(wrapped):
                            detail_preview_lines.append((str(label) if wrapped_idx == 0 else "", wrapped_value))
                    detail_preview_lines = detail_preview_lines[:detail_h]
                if not detail_preview_lines:
                    detail_preview_lines = [
                        ("", _L("↑/↓ 选择条目，底部默认显示路径或命令。", "Use Up/Down to select an item; path or command is shown here by default.")),
                    ]
                detail_label_w = max((_display_width(label) for label, _ in detail_preview_lines if label), default=0)
                detail_value_x = ll + detail_label_w + 3 if detail_label_w else ll + 1
                detail_value_w = max(10, rr - detail_value_x)
                for idx in range(detail_h):
                    y = row + idx
                    if idx >= len(detail_preview_lines):
                        continue
                    label, value = detail_preview_lines[idx]
                    if label:
                        _safe_addstr(stdscr, y, ll + 1, label, curses.A_DIM)
                    _safe_addstr(stdscr, y, detail_value_x, value, curses.color_pair(2) if label else curses.A_DIM, max_w=detail_value_w)
                row += detail_h
                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1
                row += _draw_footer_actions(stdscr, row, ll, rr - ll + 1, footer_actions)
                _safe_addstr(stdscr, row, px, "-" * total_w, ac)
            else:
                current_rows = current_panel["rows"]
                all_labels = [str(label) for label, _, _ in current_rows if str(label)]
                label_w = max((_display_width(label) for label in all_labels), default=6)
                value_x = ll + label_w + 3
                value_w = max(10, rr - value_x)
                wrapped_rows = []
                for label, value, style in current_rows:
                    value_lines = _wrap_display_lines(value, value_w)
                    wrapped_rows.append((label, value_lines, style))

                ph = sum(len(values) for _, values, _ in wrapped_rows) + footer_rows + 5
                py = max(1, (max_y - ph) // 2)

                row = py
                _safe_addstr(stdscr, row, px, "-" * total_w, ac)
                row += 1
                _safe_addstr(stdscr, row, ll, title, ac | curses.A_BOLD)
                row += 1
                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1

                for label, value_lines, style in wrapped_rows:
                    if style == "bypass":
                        val_attr = curses.color_pair(3) | curses.A_BOLD if bypass_mode else curses.color_pair(5)
                    elif style == "caveman":
                        val_attr = curses.color_pair(5) | curses.A_BOLD if _caveman_enabled() else curses.color_pair(4)
                    elif style == "nsr":
                        val_attr = curses.color_pair(5) | curses.A_BOLD if nsr_mode else curses.color_pair(4)
                    elif style == "thinking":
                        val_attr = curses.color_pair(1) | curses.A_BOLD if thinking_mode else curses.color_pair(4)
                    elif style == "effort":
                        val_attr = _effort_attr(effort_mode, enabled=thinking_mode)
                    elif style == "agent_pack":
                        val_attr = curses.color_pair(5) | curses.A_BOLD if agent_pack in {"ecc", "omc"} else curses.color_pair(4)
                    elif style == "fake":
                        val_attr = curses.color_pair(3) | curses.A_BOLD
                    elif style == "empty":
                        val_attr = curses.A_DIM
                    else:
                        val_attr = curses.color_pair(1)
                    for idx, value in enumerate(value_lines):
                        if idx == 0 and label:
                            _safe_addstr(stdscr, row, ll + 1, label, curses.A_DIM)
                        _safe_addstr(stdscr, row, value_x, value, val_attr, max_w=value_w)
                        row += 1

                _safe_addstr(stdscr, row, px, "-" * total_w, curses.A_DIM)
                row += 1
                row += _draw_footer_actions(stdscr, row, ll, rr - ll + 1, footer_actions)
                _safe_addstr(stdscr, row, px, "-" * total_w, ac)

            stdscr.refresh()
            key = stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return (
                    "",
                    bypass_mode,
                    claude_1m_mode,
                    _caveman_enabled(),
                    agent_pack,
                    thinking_mode,
                    effort_mode,
                    _disabled_payload(),
                    nsr_mode,
                    _normalize_caveman_level(caveman_level),
                )
            elif key in (ord('b'), ord('B')):
                return ("b", False, False, False, "none", True, effort_default, {}, False)
            elif key in (ord('q'), ord('Q'), 27):
                return ("q", False, False, False, "none", True, effort_default, {}, False)
            elif key == 9 and has_bypass:
                bypass_mode = not bypass_mode
            elif key in (curses.KEY_LEFT, ord('h'), ord('H')) and len(panels) > 1:
                panel_index = (panel_index - 1) % len(panels)
            elif key in (curses.KEY_RIGHT, ord('l'), ord('L')) and len(panels) > 1:
                panel_index = (panel_index + 1) % len(panels)
            elif key in (curses.KEY_UP, ord('k'), ord('K')) and current_panel.get("mode") == "list":
                panel_key = str(current_panel.get("key") or "")
                items = list(current_panel.get("items") or [])
                if items:
                    preview_selection[panel_key] = (preview_selection.get(panel_key, 0) - 1) % len(items)
            elif key in (curses.KEY_DOWN, ord('j'), ord('J')) and current_panel.get("mode") == "list":
                panel_key = str(current_panel.get("key") or "")
                items = list(current_panel.get("items") or [])
                if items:
                    preview_selection[panel_key] = (preview_selection.get(panel_key, 0) + 1) % len(items)
            elif key == ord(' ') and current_panel.get("mode") == "list" and disable_mode:
                panel_key = str(current_panel.get("key") or "")
                items = list(current_panel.get("items") or [])
                if items:
                    cursor = max(0, min(preview_selection.get(panel_key, 0), len(items) - 1))
                    disable_key = str(items[cursor].get("disable_key") or items[cursor].get("title") or "").strip()
                    if disable_key:
                        target = preview_disabled.setdefault(panel_key, set())
                        if disable_key in target:
                            target.remove(disable_key)
                        else:
                            target.add(disable_key)
            elif key in (ord('d'), ord('D')) and current_panel.get("mode") == "list":
                disable_mode = not disable_mode
            elif key in (ord('m'), ord('M')) and has_claude_1m:
                claude_1m_mode = not claude_1m_mode
            elif key in (ord('c'), ord('C')) and has_caveman:
                current_idx = caveman_options.index(caveman_level) if caveman_level in caveman_options else 0
                caveman_level = caveman_options[(current_idx + 1) % len(caveman_options)]
            elif key in (ord('n'), ord('N')) and has_nsr:
                nsr_mode = not nsr_mode
            elif key in (ord('t'), ord('T')) and has_thinking:
                thinking_mode = not thinking_mode
            elif key in (ord('e'), ord('E')) and has_effort:
                current_idx = effort_values.index(effort_mode) if effort_mode in effort_values else 0
                effort_mode = effort_values[(current_idx + 1) % len(effort_values)]
            elif key in (ord('x'), ord('X')) and has_agent_pack:
                current_idx = pack_options.index(agent_pack) if agent_pack in pack_options else 0
                agent_pack = pack_options[(current_idx + 1) % len(pack_options)]

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return ("q", False, False, False, "none", True, effort_default, {}, False)


# ── Reasoning effort 选择 TUI ────────────────────────────────────

_ECC_TOGGLE_KEY = "X"

_EFFORT_OPTIONS = [
    ("low",    "Low    — 快速，适合简单任务"),
    ("medium", "Medium — 均衡，默认推荐"),
    ("high",   "High   — 深度思考，慢但更准"),
    ("xhigh",  "XHigh  — 更深推理，最慢但更稳"),
]


def _confirm_model_tokens(model_info):
    values = []
    if isinstance(model_info, dict):
        values.extend(str(v or "") for k, v in model_info.items() if k != "subagent")
    else:
        values.append(str(model_info or ""))
    normalized = []
    for item in values:
        value = str(item or "").strip().lower()
        if "/" in value:
            value = value.rsplit("/", 1)[-1]
        if value:
            normalized.append(value)
    return normalized


def _confirm_is_gpt_like_token(token):
    return str(token or "").startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))


def _confirm_supports_domestic_thinking_token(token):
    token = str(token or "")
    if token.startswith(("glm", "kimi", "k2.5", "k2.6", "minimax", "deepseek")):
        return True
    if token.startswith(("mimo", "qwen-coder", "qwen3-coder")):
        return False
    if token.startswith("qwen"):
        return token.startswith(("qwen-plus", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max"))
    return False


def _confirm_supports_domestic_effort_token(token):
    return str(token or "").startswith("deepseek")


def _confirm_explicit_thinking_default(runtime):
    if not isinstance(runtime, dict) or "thinking_mode" not in runtime:
        return None
    value = str(runtime.get("thinking_mode") or "").strip().lower()
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if value in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    return None


def _confirm_policy_capability_flags(tokens):
    flags = {"thinking": [], "reasoning": []}
    try:
        from mms_capability_resolver import load_default_model_policy

        policy = load_default_model_policy()
    except Exception:
        return flags
    models = policy.get("models") if isinstance(policy, dict) else {}
    if not isinstance(models, dict):
        return flags

    def norm(value):
        text = str(value or "").strip().lower()
        return text.rsplit("/", 1)[-1]

    wanted = {norm(token) for token in tokens if norm(token)}
    for key, entry in models.items():
        if norm(key) not in wanted or not isinstance(entry, dict):
            continue
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        if isinstance(caps.get("thinking"), bool):
            flags["thinking"].append(bool(caps["thinking"]))
        elif isinstance(caps.get("supports_thinking"), bool):
            flags["thinking"].append(bool(caps["supports_thinking"]))
        if isinstance(caps.get("reasoning"), bool):
            flags["reasoning"].append(bool(caps["reasoning"]))
        elif isinstance(caps.get("reasoning_effort"), bool):
            flags["reasoning"].append(bool(caps["reasoning_effort"]))
    return flags


def _confirm_profile_capabilities(model_info, runtime=None):
    tokens = _confirm_model_tokens(model_info)
    fallback_thinking = any(
        _confirm_is_gpt_like_token(token) or _confirm_supports_domestic_thinking_token(token)
        for token in tokens
    )
    fallback_effort = any(
        _confirm_is_gpt_like_token(token) or _confirm_supports_domestic_effort_token(token)
        for token in tokens
    )
    result = {
        "tokens": tokens,
        "profile": "",
        "profile_matched": False,
        "thinking_supported": fallback_thinking,
        "effort_supported": fallback_effort,
        "default_enabled": None,
        "effort_allowed": [],
        "effort_map": {},
    }
    try:
        from mms_provider_profiles import profile_thinking_capabilities
    except Exception:
        return result

    defaults = []
    effort_allowed = set()
    effort_map = {}
    profile_thinking = False
    profile_effort = False
    profile_ids = []
    runtime_obj = runtime if isinstance(runtime, dict) else None
    provider_id = str((runtime_obj or {}).get("id") or (runtime_obj or {}).get("provider_id") or "").strip()
    base_url = str(
        (runtime_obj or {}).get("anthropic_base_url")
        or (runtime_obj or {}).get("openai_base_url")
        or (runtime_obj or {}).get("base_url")
        or ""
    ).strip()
    for token in tokens:
        caps = profile_thinking_capabilities(
            token,
            runtime=runtime_obj,
            provider_id=provider_id,
            base_url=base_url,
        )
        profile_id = str(caps.get("profile") or "").strip()
        if not profile_id:
            continue
        profile_ids.append(profile_id)
        result["profile_matched"] = True
        profile_thinking = profile_thinking or bool(caps.get("thinking_supported"))
        profile_effort = profile_effort or bool(caps.get("effort_supported"))
        if isinstance(caps.get("default_enabled"), bool):
            defaults.append(bool(caps["default_enabled"]))
        effort_allowed.update(str(item).strip().lower() for item in (caps.get("effort_allowed") or []) if str(item).strip())
        if isinstance(caps.get("effort_map"), dict):
            effort_map.update({str(k).strip().lower(): str(v).strip().lower() for k, v in caps["effort_map"].items()})

    if result["profile_matched"]:
        result["profile"] = ",".join(dict.fromkeys(profile_ids))
        result["thinking_supported"] = profile_thinking
        result["effort_supported"] = profile_effort
        if any(defaults):
            result["default_enabled"] = True
        elif defaults:
            result["default_enabled"] = False
        result["effort_allowed"] = sorted(effort_allowed)
        result["effort_map"] = effort_map

    policy_flags = _confirm_policy_capability_flags(tokens)
    if policy_flags["thinking"]:
        result["thinking_supported"] = any(policy_flags["thinking"])
        result["default_enabled"] = any(policy_flags["thinking"])
    if policy_flags["reasoning"]:
        result["effort_supported"] = any(policy_flags["reasoning"])
    return result


def _confirm_effort_values(profile_caps, model_tokens):
    values = [value for value, _label in _EFFORT_OPTIONS]
    allowed = set(profile_caps.get("effort_allowed") or [])
    effort_map = profile_caps.get("effort_map") if isinstance(profile_caps.get("effort_map"), dict) else {}
    if allowed:
        filtered = [
            value for value in values
            if value in allowed or (value == "xhigh" and effort_map.get(value) in allowed)
        ]
        return filtered or values
    if not any(_confirm_is_gpt_like_token(token) for token in model_tokens):
        return [value for value in values if value != "xhigh"]
    return values


def select_reasoning_effort_tui(default="high"):
    """选择 GPT reasoning effort。返回 'low' / 'medium' / 'high' / 'xhigh'，Esc 返回 default。"""

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)

        default_idx = next((i for i, (v, _) in enumerate(_EFFORT_OPTIONS) if v == default), 1)
        sel = default_idx

        while True:
            stdscr.erase()
            max_y, max_w = stdscr.getmaxyx()
            title = "GPT Reasoning Effort"
            stdscr.addstr(1, 2, title, curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(2, 2, "─" * min(40, max_w - 4), curses.color_pair(2))

            for i, (_, label) in enumerate(_EFFORT_OPTIONS):
                row = 4 + i
                if row >= max_y - 1:
                    break
                if i == sel:
                    stdscr.addstr(row, 2, f"▶ {label}", curses.color_pair(1) | curses.A_BOLD)
                else:
                    stdscr.addstr(row, 2, f"  {label}", curses.color_pair(2))

            hint = f"↑↓ 选择  Enter 确认  Esc 默认({default})"
            if max_y > 9:
                stdscr.addstr(min(8, max_y - 1), 2, hint, curses.color_pair(2) | curses.A_DIM)
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP:
                sel = (sel - 1) % len(_EFFORT_OPTIONS)
            elif key == curses.KEY_DOWN:
                sel = (sel + 1) % len(_EFFORT_OPTIONS)
            elif key in (10, 13):
                return _EFFORT_OPTIONS[sel][0]
            elif key == 27:
                return default

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return default
