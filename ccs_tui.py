"""CCS curses TUI：箭头键交互选择器"""

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
    "qwen": [  # 来自 @qwen-code/qwen-code cli.js 源码
        " ▄▄▄▄▄▄  ▄▄     ▄▄ ▄▄▄▄▄▄▄ ▄▄▄    ▄▄",
        "██╔═══██╗██║    ██║██╔════╝████╗  ██║",
        "██║   ██║██║ █╗ ██║█████╗  ██╔██╗ ██║",
        "██║▄▄ ██║██║███╗██║██╔══╝  ██║╚██╗██║",
        "╚██████╔╝╚███╔███╔╝███████╗██║ ╚████║",
        " ╚══▀▀═╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═══╝",
    ],
    "kimi": [  # 来自 kimi_cli/ui/shell/__init__.py 源码
        "▐█▛█▛█▌",
        "▐█████▌",
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


DIRECT_CLI_ITEMS = {
    "qwen": {
        "title": "直达模式",
        "primary": "▸ 全部 Qwen 模型",
        "secondary": "不进入场景选择，直接列出当前 provider 的 qwen* 模型",
    },
    "kimi": {
        "title": "直达模式",
        "primary": "▸ 默认 Kimi",
        "secondary": "不进入场景选择，直接使用默认 Kimi 模型启动",
    },
}

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
]


def _sort_scenes_for_cli(scenes, cli_name):
    return list(scenes.keys())


def _auto_variant_scene_for_cli(scenes, cli_name):
    return None


def _auto_default_scene_for_cli(scenes, cli_name):
    return None


def _draw_box(stdscr, y, x, h, w, title=""):
    try:
        stdscr.addstr(y, x, "╭" + "─" * (w - 2) + "╮")
        for i in range(1, h - 1):
            stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│")
        stdscr.addstr(y + h - 1, x, "╰" + "─" * (w - 2) + "╯")
        if title:
            t = f" {title} "
            tx = x + (w - len(t)) // 2
            stdscr.addstr(y, tx, t, curses.A_BOLD)
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


def _format_variant_line(variant, is_selected):
    marker = "▸ " if is_selected else "  "
    tier = {
        "med": "中杯",
        "high": "大杯",
        "xhigh": "超大杯",
    }.get(variant.get("tier", ""), variant.get("tier", ""))
    model = variant.get("model_info", {}).get("model", "")
    return f"{marker}{tier:<6}  {model}"


def _source_choice_key(cli_name, model_info=None):
    if not model_info:
        return f"{cli_name}|__default__"
    if isinstance(model_info, dict):
        cleaned = {k: v for k, v in model_info.items() if k != "provider" and v}
        if not cleaned:
            return f"{cli_name}|__default__"
        payload = json.dumps(cleaned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return f"{cli_name}|{payload}"
    return f"{cli_name}|{str(model_info).strip()}"


def _format_source_line(source, is_selected):
    marker = "▸ " if is_selected else "  "
    badge = "官方通道" if source.get("kind") == "account" else "网关通道"
    launcher = str(source.get("launch_cli", "")).upper()
    default_tag = " · 默认" if source.get("is_default") else ""
    return f"{marker}{source.get('icon', '•')} {source.get('title', '')}  {badge} · {launcher}{default_tag}"


def _default_variant_index(scene):
    variants = scene.get("variants", [])
    preferred_tier = scene.get("default_tier", "high")
    for i, variant in enumerate(variants):
        if variant.get("tier") == preferred_tier:
            return i
    return 0


def select_scene_tui(scenes, cli_names, source_choices=None):
    """主 TUI：左右切 CLI tab，上下选场景，Enter 确认，Q 退出"""

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()

        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)
        # 品牌色
        curses.init_pair(10, curses.COLOR_RED, -1)      # claude
        curses.init_pair(11, curses.COLOR_WHITE, -1)     # codex
        curses.init_pair(12, curses.COLOR_MAGENTA, -1)   # qwen
        curses.init_pair(13, curses.COLOR_CYAN, -1)      # kimi
        logo_pairs = {"claude": 10, "codex": 11, "qwen": 12, "kimi": 13}

        cli_idx = 0
        scene_idx = 0
        variant_idx = 0
        variant_scene_name = None
        source_idx = 0
        source_scene_name = None
        source_cli_name = None
        source_model_info = None
        source_back_mode = None

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            cli = cli_names[cli_idx]
            default_source_config = (source_choices or {}).get(_source_choice_key(cli), {})
            available_sources = default_source_config.get("options", [])
            default_source_idx = default_source_config.get("default_index", 0) or 0
            if source_scene_name is not None:
                source_key = _source_choice_key(source_cli_name or cli, source_model_info)
                source_config = (source_choices or {}).get(source_key, default_source_config)
                available_sources = source_config.get("options", [])
                default_source_idx = source_config.get("default_index", 0) or 0

            sorted_scenes = _sort_scenes_for_cli(scenes, cli)
            direct_cli_item = DIRECT_CLI_ITEMS.get(cli)
            auto_default_scene = _auto_default_scene_for_cli(scenes, cli)
            forced_variant_scene = _auto_variant_scene_for_cli(scenes, cli)
            active_variant_scene = variant_scene_name or forced_variant_scene
            in_variant_mode = active_variant_scene is not None
            in_source_mode = source_scene_name is not None
            if direct_cli_item:
                list_count = 3
            elif in_source_mode:
                list_count = max(1, len(available_sources))
            elif auto_default_scene:
                list_count = 1
            elif not in_variant_mode:
                scene_count = len(sorted_scenes) + 1
                if scene_idx >= scene_count:
                    scene_idx = 0
                list_count = scene_count
            else:
                variants = scenes[active_variant_scene].get("variants", [])
                if variant_idx >= len(variants):
                    variant_idx = _default_variant_index(scenes[active_variant_scene])
                list_count = max(1, len(variants))

            w = max(54, min(max_w - 2, int(max_w * 0.85)))
            logo_h = _MAX_LOGO_H
            h = list_count + logo_h + 8
            sx = (max_w - w) // 2
            sy = max(0, (max_y - h) // 2)
            cx = sx + w // 2

            _draw_box(stdscr, sy, sx, h, w, "CCS")

            # ── Logo（居中）──
            logo = CLI_LOGOS.get(cli, [])
            logo_color = curses.color_pair(logo_pairs.get(cli, 2)) | curses.A_BOLD
            _draw_centered_block(stdscr, sy + 2, cx, logo, logo_color)

            # ── CLI Tabs（居中）──
            tab_y = sy + 2 + logo_h + 1
            tab_parts = []
            for i, name in enumerate(cli_names):
                if i == cli_idx:
                    tab_parts.append((f" {name.upper()} ", True))
                else:
                    tab_parts.append((f" {name.capitalize()} ", False))
            total_tab_w = sum(len(p[0]) for p in tab_parts) + (len(tab_parts) - 1) * 2
            tab_x = cx - total_tab_w // 2

            for label, is_active in tab_parts:
                if is_active:
                    attr = curses.color_pair(logo_pairs.get(cli, 1)) | curses.A_BOLD
                else:
                    attr = curses.color_pair(2) | curses.A_DIM
                try:
                    stdscr.addstr(tab_y, tab_x, label, attr)
                except curses.error:
                    pass
                tab_x += len(label) + 2

            # ── 场景列表（居中）──
            list_y = tab_y + 2

            if direct_cli_item:
                title = direct_cli_item["title"]
                _center_text(stdscr, list_y - 1, cx, title, curses.color_pair(5) | curses.A_BOLD)
                item_lines = [
                    ("  快速入口", False),
                    (direct_cli_item["primary"], True),
                    (f"  {direct_cli_item['secondary']}", False),
                ]
                extra_line = None
            elif in_source_mode:
                title_name = source_scene_name if source_scene_name is not None else "自定义"
                title = f"为 {title_name} 选择执行通道"
                _center_text(stdscr, list_y - 1, cx, title, curses.color_pair(5) | curses.A_BOLD)
                if source_idx >= len(available_sources):
                    source_idx = default_source_idx if available_sources else 0
                item_lines = []
                for i, source in enumerate(available_sources):
                    item_lines.append((_format_source_line(source, i == source_idx), i == source_idx))
                extra_line = None
            elif auto_default_scene:
                scene = scenes[auto_default_scene]
                chosen = scene["variants"][_default_variant_index(scene)]
                title = f"{auto_default_scene} 默认模型"
                _center_text(stdscr, list_y - 1, cx, title, curses.color_pair(5) | curses.A_BOLD)
                item_lines = [(_format_variant_line(chosen, True), True)]
                extra_line = None
            elif in_variant_mode:
                variants = scenes[active_variant_scene].get("variants", [])
                title = f"为 {active_variant_scene} 选择档位"
                _center_text(stdscr, list_y - 1, cx, title, curses.color_pair(5) | curses.A_BOLD)
                item_lines = [
                    (_format_variant_line(variant, i == variant_idx), i == variant_idx)
                    for i, variant in enumerate(variants)
                ]
                extra_line = None
            else:
                item_lines = []
                for i, name in enumerate(sorted_scenes):
                    info = scenes[name]
                    is_selected = (i == scene_idx)
                    marker = "▸ " if is_selected else "  "
                    name_w = _display_width(name)
                    padding = max(8, 18 - name_w)
                    full_line = f"{marker}{info['emoji']} {name}{' ' * padding}{info['desc']}"
                    item_lines.append((full_line, is_selected))

                custom_idx = len(sorted_scenes)
                is_custom_sel = (scene_idx == custom_idx)
                custom_marker = "▸ " if is_custom_sel else "  "
                extra_line = (f"{custom_marker}🔧 自定义", is_custom_sel)

            all_lines = [line for line, _ in item_lines]
            if extra_line:
                all_lines.append(extra_line[0])
            max_line_w = max(_display_width(l) for l in all_lines)

            # 整体居中的起始 x
            content_x = cx - max_line_w // 2

            for i, (line, is_selected) in enumerate(item_lines):
                attr = curses.color_pair(3) | curses.A_BOLD if is_selected else curses.color_pair(5 if direct_cli_item else 2)
                try:
                    stdscr.addstr(list_y + i, max(sx + 2, content_x), line[:w - 4], attr)
                except curses.error:
                    pass

            if extra_line:
                sep_y = list_y + len(item_lines)
                sep_w = max_line_w - 4
                sep_x = cx - sep_w // 2
                try:
                    stdscr.addstr(sep_y, max(sx + 2, sep_x), "─" * sep_w,
                                  curses.color_pair(5) | curses.A_DIM)
                except curses.error:
                    pass

                custom_y = sep_y + 1
                attr = curses.color_pair(3) | curses.A_BOLD if extra_line[1] else curses.color_pair(5)
                try:
                    stdscr.addstr(custom_y, max(sx + 2, content_x), extra_line[0], attr)
                except curses.error:
                    pass

            # ── Footer（醒目）──
            footer = " ← → 切换    Enter 确认 "
            if direct_cli_item:
                footer = " ← → 切换    Enter 直达    O 接入    Q 退出 "
            elif auto_default_scene:
                footer += "   O 接入    Q 退出 "
            elif in_source_mode:
                footer = " ← → 切换    ↑ ↓ 通道    Enter 确认    O 接入    Esc 返回    Q 退出 "
            elif in_variant_mode and not forced_variant_scene:
                footer = " ← → 切换    ↑ ↓ 选择    Enter 确认    O 接入 "
                footer += "   Esc 返回    Q 退出 "
            else:
                footer = " ← → 切换    ↑ ↓ 选择    Enter 确认    O 接入 "
                footer += "   Q 退出 "
            _center_text(stdscr, sy + h - 1, cx, footer, curses.color_pair(1) | curses.A_BOLD)

            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_LEFT:
                cli_idx = (cli_idx - 1) % len(cli_names)
                scene_idx = 0
                next_cli = cli_names[cli_idx]
                auto_default_scene = _auto_default_scene_for_cli(scenes, next_cli)
                auto_scene = _auto_variant_scene_for_cli(scenes, next_cli)
                variant_idx = 0 if auto_default_scene else (_default_variant_index(scenes[auto_scene]) if auto_scene else 0)
                variant_scene_name = None
                source_idx = 0
                source_scene_name = None
                source_cli_name = None
                source_model_info = None
                source_back_mode = None
            elif key == curses.KEY_RIGHT:
                cli_idx = (cli_idx + 1) % len(cli_names)
                scene_idx = 0
                next_cli = cli_names[cli_idx]
                auto_default_scene = _auto_default_scene_for_cli(scenes, next_cli)
                auto_scene = _auto_variant_scene_for_cli(scenes, next_cli)
                variant_idx = 0 if auto_default_scene else (_default_variant_index(scenes[auto_scene]) if auto_scene else 0)
                variant_scene_name = None
                source_idx = 0
                source_scene_name = None
                source_cli_name = None
                source_model_info = None
                source_back_mode = None
            elif key == curses.KEY_UP and not auto_default_scene and not direct_cli_item:
                if in_source_mode:
                    source_idx = (source_idx - 1) % max(1, len(available_sources))
                elif in_variant_mode:
                    variant_idx = (variant_idx - 1) % len(variants)
                else:
                    scene_idx = (scene_idx - 1) % scene_count
            elif key == curses.KEY_DOWN and not auto_default_scene and not direct_cli_item:
                if in_source_mode:
                    source_idx = (source_idx + 1) % max(1, len(available_sources))
                elif in_variant_mode:
                    variant_idx = (variant_idx + 1) % len(variants)
                else:
                    scene_idx = (scene_idx + 1) % scene_count
            elif key in (10, 13, curses.KEY_ENTER):
                if direct_cli_item:
                    scene_name = "__direct_qwen__" if cli == "qwen" else "__direct_kimi__"
                    return (scene_name, cli, None, None)
                if auto_default_scene:
                    scene = scenes[auto_default_scene]
                    chosen = scene["variants"][_default_variant_index(scene)]
                    return (auto_default_scene, cli, dict(chosen.get("model_info", {})), None)
                if in_source_mode:
                    selected_source = available_sources[source_idx] if available_sources else None
                    return (source_scene_name, source_cli_name, source_model_info, selected_source)
                if in_variant_mode:
                    chosen = variants[variant_idx]
                    scene_name = active_variant_scene
                    model_info = dict(chosen.get("model_info", {}))
                    source_key = _source_choice_key(cli, model_info)
                    source_config = (source_choices or {}).get(source_key, default_source_config)
                    available_sources = source_config.get("options", [])
                    default_source_idx = source_config.get("default_index", 0) or 0
                    if len(available_sources) > 1:
                        source_scene_name = scene_name
                        source_cli_name = cli
                        source_model_info = model_info
                        source_back_mode = "variant"
                        source_idx = default_source_idx
                        continue
                    selected_source = available_sources[0] if len(available_sources) == 1 else None
                    return (scene_name, cli, model_info, selected_source)
                if scene_idx == custom_idx:
                    if len(available_sources) > 1:
                        source_scene_name = None
                        source_cli_name = cli
                        source_model_info = None
                        source_back_mode = "scene"
                        source_idx = default_source_idx
                        continue
                    selected_source = available_sources[0] if len(available_sources) == 1 else None
                    return (None, cli, None, selected_source)
                scene_name = sorted_scenes[scene_idx]
                info = scenes[scene_name]
                if info.get("variants"):
                    variant_scene_name = scene_name
                    variant_idx = _default_variant_index(info)
                    continue
                model_info = {k: v for k, v in info.items()
                              if k not in ("emoji", "desc", "cli", "variants")}
                source_key = _source_choice_key(cli, model_info)
                source_config = (source_choices or {}).get(source_key, default_source_config)
                available_sources = source_config.get("options", [])
                default_source_idx = source_config.get("default_index", 0) or 0
                if len(available_sources) > 1:
                    source_scene_name = scene_name
                    source_cli_name = cli
                    source_model_info = model_info
                    source_back_mode = "scene"
                    source_idx = default_source_idx
                    continue
                selected_source = available_sources[0] if len(available_sources) == 1 else None
                return (scene_name, cli, model_info, selected_source)
            elif key == 27 and in_source_mode:
                source_scene_name = None
                source_cli_name = None
                source_model_info = None
                source_idx = 0
                if source_back_mode == "scene":
                    variant_scene_name = None
                    variant_idx = 0
                source_back_mode = None
            elif key == 27 and in_variant_mode and not forced_variant_scene:
                variant_scene_name = None
                variant_idx = 0
            elif key in (ord('o'), ord('O')):
                return "__connect__"
            elif key in (ord('q'), ord('Q'), 27):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


def select_model_tui(models, title="选择模型"):
    if not models:
        return None

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)

        idx = 0
        scroll = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            visible = max_y - 4

            stdscr.addstr(0, 2, title, curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(1, 2, f"{len(models)} models  ↑↓  Enter  Q", curses.A_DIM)

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(models))):
                y = 3 + i - scroll
                prefix = " ▸ " if i == idx else "   "
                line = f"{prefix}{i + 1:3d}. {models[i]}"
                attr = curses.color_pair(3) | curses.A_BOLD if i == idx else 0
                try:
                    stdscr.addstr(y, 1, line[:max_w - 2], attr)
                except curses.error:
                    pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(models)
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(models)
            elif key in (10, 13, curses.KEY_ENTER):
                return models[idx]
            elif key in (ord('q'), ord('Q'), 27):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return None


def select_actions_tui(findings, actions, title="处理发现"):
    if not actions:
        return []

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)

        idx = 0
        scroll = 0
        selected = set()
        message = ""

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            findings_lines = []
            for finding in findings:
                findings_lines.append(f"- {finding['title']}: {finding['summary']}")
            visible = max(3, max_y - len(findings_lines) - 7)

            try:
                stdscr.addstr(0, 2, title, curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(1, 2, "发现", curses.color_pair(4) | curses.A_BOLD)
            except curses.error:
                pass

            for line_idx, line in enumerate(findings_lines[:3], start=2):
                try:
                    stdscr.addstr(line_idx, 2, line[:max_w - 4], curses.color_pair(2))
                except curses.error:
                    pass

            list_y = min(max_y - 4, len(findings_lines[:3]) + 3)
            try:
                stdscr.addstr(list_y, 2, "动作", curses.color_pair(5) | curses.A_BOLD)
            except curses.error:
                pass

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for action_idx in range(scroll, min(scroll + visible, len(actions))):
                action = actions[action_idx]
                y = list_y + 1 + action_idx - scroll
                checked = "[x]" if action["id"] in selected else "[ ]"
                recommended = " 推荐" if action.get("recommended") else ""
                prefix = "▸ " if action_idx == idx else "  "
                line = f"{prefix}{checked} {action['title']}{recommended}  {action['summary']}"
                attr = curses.color_pair(3) | curses.A_BOLD if action_idx == idx else curses.color_pair(2)
                try:
                    stdscr.addstr(y, 1, line[:max_w - 2], attr)
                except curses.error:
                    pass

            footer = " ↑↓ 移动   Space 勾选   Enter 下一步   D 详情   Q 退出 "
            try:
                stdscr.addstr(max_y - 2, max(1, (max_w - len(footer)) // 2), footer, curses.color_pair(1) | curses.A_BOLD)
            except curses.error:
                pass
            if message:
                try:
                    stdscr.addstr(max_y - 1, 2, message[:max_w - 4], curses.color_pair(6))
                except curses.error:
                    pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = (idx - 1) % len(actions)
                message = ""
            elif key == curses.KEY_DOWN:
                idx = (idx + 1) % len(actions)
                message = ""
            elif key == ord(" "):
                action_id = actions[idx]["id"]
                if action_id in selected:
                    selected.remove(action_id)
                else:
                    selected.add(action_id)
                message = ""
            elif key in (10, 13, curses.KEY_ENTER):
                if selected:
                    return [action["id"] for action in actions if action["id"] in selected]
                message = "请至少勾选一个动作"
            elif key in (ord("d"), ord("D")):
                action = actions[idx]
                message = action.get("summary", "")
            elif key in (ord("q"), ord("Q"), 27):
                return []

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


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

            footer = " ↑ ↓ 选择    Enter 进入    Esc 返回 "
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

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)

        stdscr.clear()
        max_y, max_w = stdscr.getmaxyx()

        w = max(54, min(max_w - 2, int(max_w * 0.85)))
        env_h = len(env_lines) + 1 if env_lines else 0
        h = 7 + env_h
        sx = (max_w - w) // 2
        sy = (max_y - h) // 2
        cx = sx + w // 2
        pad = sx + 4

        _draw_box(stdscr, sy, sx, h, w, "确认启动")

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

        footer = " Enter 启动  B 返回  Q 取消 "
        _center_text(stdscr, sy + h - 1, cx, footer, curses.color_pair(1))
        stdscr.refresh()

        while True:
            key = stdscr.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return ""
            elif key in (ord('b'), ord('B')):
                return "b"
            elif key in (ord('q'), ord('Q'), 27):
                return "q"

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "q"
