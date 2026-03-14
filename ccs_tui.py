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


def _sort_scenes_for_cli(scenes, cli_name):
    return list(scenes.keys())


def _auto_variant_scene_for_cli(scenes, cli_name):
    return None


def _auto_default_scene_for_cli(scenes, cli_name):
    return None


def _draw_box(stdscr, y, x, h, w, title="", color=None):
    attr = color if color is not None else 0
    try:
        stdscr.addstr(y, x, "╭" + "─" * (w - 2) + "╮", attr)
        for i in range(1, h - 1):
            stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│", attr)
        stdscr.addstr(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", attr)
        if title:
            t = f" {title} "
            tx = x + (w - len(t)) // 2
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
    badge = "官方" if source.get("kind") == "account" else "网关"
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


def select_scene_tui(scenes, cli_names, source_choices=None, last_used=None, scene_counts=None):
    """主 TUI：左右切 CLI tab，上下选场景，Enter 确认，Q 退出"""
    scene_counts = scene_counts or {}

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
                # 预计算虚拟列表行数
                has_last = (last_used and last_used.get("scene") in scenes
                            and last_used["scene"] in sorted_scenes)
                ranked = [(name, scene_counts.get(name, 0))
                          for name in sorted_scenes if scene_counts.get(name, 0) > 0]
                ranked.sort(key=lambda x: x[1], reverse=True)
                # 行数 = 上次使用(1+sep) + 场景 + 排行(sep+N) + 自定义(sep+1)
                virt_count = len(sorted_scenes) + 1  # scenes + custom
                virt_count += 1  # sep_custom
                if has_last:
                    virt_count += 2  # last + sep_last
                if ranked:
                    virt_count += 1 + len(ranked)  # sep_ranked + ranked items
                selectable_count = virt_count - 1 - (1 if has_last else 0) - (1 if ranked else 0)  # minus separators
                if scene_idx >= selectable_count:
                    scene_idx = 0
                list_count = virt_count
                scene_count = selectable_count
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
                title = f"为 {title_name} 选择使用入口"
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
                # ── 构建虚拟列表：上次使用 + 场景 + 启动排行 + 自定义 ──
                # virt_items: list of (type, scene_name_or_none)
                # types: "last", "scene", "ranked", "custom", "sep_last", "sep_ranked"
                virt_items = []

                # 上次使用（仅当存在且场景在当前列表中）
                has_last = (last_used and last_used.get("scene") in scenes
                            and last_used["scene"] in sorted_scenes)
                if has_last:
                    virt_items.append(("last", last_used["scene"]))
                    virt_items.append(("sep_last", None))

                # 正常场景
                for name in sorted_scenes:
                    virt_items.append(("scene", name))

                # 启动排行（有启动记录的场景，按次数降序，排除上次使用已显示的）
                ranked = [(name, scene_counts.get(name, 0))
                          for name in sorted_scenes if scene_counts.get(name, 0) > 0]
                ranked.sort(key=lambda x: x[1], reverse=True)
                if ranked:
                    virt_items.append(("sep_ranked", None))
                    for name, _ in ranked:
                        virt_items.append(("ranked", name))

                # 自定义
                virt_items.append(("sep_custom", None))
                virt_items.append(("custom", None))

                # 可选中的索引列表（跳过分隔符）
                selectable_indices = [i for i, (t, _) in enumerate(virt_items) if t not in ("sep_last", "sep_ranked", "sep_custom")]
                scene_count = len(selectable_indices)
                if scene_idx >= scene_count:
                    scene_idx = 0

                item_lines = []
                for vi, (vtype, vname) in enumerate(virt_items):
                    # 当前选中的 selectable 位置
                    sel_pos = selectable_indices.index(vi) if vi in selectable_indices else -1
                    is_selected = (sel_pos == scene_idx)

                    if vtype == "last":
                        marker = "▸ " if is_selected else "  "
                        model_str = last_used.get("model", "")
                        line = f"{marker}⏱ 上次使用          {model_str}"
                        item_lines.append((line, is_selected))
                    elif vtype in ("sep_last", "sep_ranked", "sep_custom"):
                        item_lines.append(("", False))
                    elif vtype == "scene":
                        info = scenes[vname]
                        marker = "▸ " if is_selected else "  "
                        name_w = _display_width(vname)
                        padding = max(8, 18 - name_w)
                        full_line = f"{marker}{info['emoji']} {vname}{' ' * padding}{info['desc']}"
                        item_lines.append((full_line, is_selected))
                    elif vtype == "ranked":
                        info = scenes[vname]
                        marker = "▸ " if is_selected else "  "
                        count = scene_counts.get(vname, 0)
                        line = f"{marker}{info['emoji']} {vname}  ×{count}"
                        item_lines.append((line, is_selected))
                    elif vtype == "custom":
                        marker = "▸ " if is_selected else "  "
                        item_lines.append((f"{marker}🔧 自定义", is_selected))

                extra_line = None

            all_lines = [line for line, _ in item_lines if line]
            if extra_line:
                all_lines.append(extra_line[0])
            max_line_w = max((_display_width(l) for l in all_lines), default=20)

            # 整体居中的起始 x
            content_x = cx - max_line_w // 2

            for i, (line, is_selected) in enumerate(item_lines):
                if not line:
                    # 分隔符
                    sep_w = max_line_w - 4
                    sep_x = cx - sep_w // 2
                    try:
                        stdscr.addstr(list_y + i, max(sx + 2, sep_x), "─" * max(1, sep_w),
                                      curses.color_pair(5) | curses.A_DIM)
                    except curses.error:
                        pass
                    continue
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
                # 通过 virt_items 和 selectable_indices 查找当前选中项
                virt_idx = selectable_indices[scene_idx] if scene_idx < len(selectable_indices) else 0
                vtype, vname = virt_items[virt_idx]

                if vtype == "custom":
                    return (None, cli, None, None)
                if vtype == "last":
                    # 直接用上次的 model_info 启动
                    scene_name = last_used["scene"]
                    model_info = dict(last_used.get("model_info") or {})
                    if not model_info:
                        model_info = {"model": last_used.get("model", "")}
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

                # scene 或 ranked 类型：都是正常场景
                scene_name = vname
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


# ── 负载模式 TUI ──────────────────────────────────────────────

_LB_HISTORY_PATH = os.path.expanduser("~/.config/mms/lb_history.json")

# 默认预设
_LB_PRESETS = [
    {"label": "Opus + Haiku",   "heavy": "claude-opus-4-6",   "light": "claude-haiku-4-5"},
    {"label": "Sonnet + Haiku", "heavy": "claude-sonnet-4-6", "light": "claude-haiku-4-5"},
    {"label": "GPT + Mini",     "heavy": "gpt-5.4",           "light": "gpt-4.1-mini"},
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


def save_lb_history(heavy, light):
    """保存一条负载模式选择到历史。保留最近 2 条。"""
    entry = {"heavy": heavy, "light": light, "label": f"{heavy} + {light}"}
    history = _load_lb_history()
    recent = history.get("recent", [])
    # 去重：相同 heavy+light 的不重复添加
    recent = [r for r in recent if not (r.get("heavy") == heavy and r.get("light") == light)]
    recent.insert(0, entry)
    history["recent"] = recent[:2]
    try:
        os.makedirs(os.path.dirname(_LB_HISTORY_PATH), exist_ok=True)
        with open(_LB_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def select_load_balance_tui(available_models=None):
    """负载模式 TUI：选择 heavy + light 模型组合。

    返回 {"model": heavy, "lb_light": light} 或 None（取消）。
    """
    history = _load_lb_history()
    recent = history.get("recent", [])

    def _build_options():
        """构建选项列表：最近使用 + 预设 + 自定义"""
        opts = []
        seen = set()
        # 最近使用（最多 2 条）
        for r in recent[:2]:
            key = (r["heavy"], r["light"])
            if key not in seen:
                seen.add(key)
                opts.append({"label": f"🕐 {r['heavy']} + {r['light']}", "heavy": r["heavy"], "light": r["light"], "type": "recent"})
        # 预设
        for p in _LB_PRESETS:
            key = (p["heavy"], p["light"])
            if key not in seen:
                seen.add(key)
                opts.append({"label": f"   {p['label']}", "heavy": p["heavy"], "light": p["light"], "type": "preset"})
        # 自定义
        opts.append({"label": "   ✏️  自定义...", "type": "custom"})
        return opts

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)

        options = _build_options()
        idx = 0

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()

            try:
                stdscr.addstr(0, 2, "⚖️ 负载模式 — 选择模型组合", curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(1, 2, "heavy 处理复杂任务，light 处理简单任务", curses.A_DIM)
                stdscr.addstr(2, 2, "─" * min(40, max_w - 4), curses.A_DIM)
            except curses.error:
                pass

            for i, opt in enumerate(options):
                y = 4 + i
                if y >= max_y - 2:
                    break
                prefix = " ▸" if i == idx else "  "
                line = f"{prefix} {opt['label']}"
                attr = curses.color_pair(3) | curses.A_BOLD if i == idx else curses.A_NORMAL
                if opt.get("type") == "recent":
                    attr = curses.color_pair(4) | curses.A_BOLD if i == idx else curses.color_pair(4)
                try:
                    stdscr.addstr(y, 1, line[:max_w - 2], attr)
                except curses.error:
                    pass

            footer = " ↑↓ 选择   Enter 确认   Q 取消 "
            try:
                stdscr.addstr(max_y - 1, max(1, (max_w - len(footer)) // 2), footer, curses.A_DIM)
            except curses.error:
                pass

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
                return {"model": chosen["heavy"], "lb_light": chosen["light"]}
            elif key in (ord('q'), ord('Q'), 27):
                return None

    try:
        result = curses.wrapper(_inner)
    except curses.error:
        return None

    if result == "custom":
        # 自定义流程：先选 heavy，再选 light
        models = available_models or []
        if not models:
            # 无可用模型列表时提供默认选项
            models = [
                "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
                "gpt-5.4", "gpt-4.1-mini",
            ]
        heavy = select_model_tui(models, title="选择 Heavy 模型（复杂任务）")
        if heavy is None:
            return None
        light = select_model_tui(models, title="选择 Light 模型（简单任务）")
        if light is None:
            return None
        return {"model": heavy, "lb_light": light}

    return result


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
    bypass: bool, 仅 codex 有效，True 时附加 --dangerously-bypass-approvals-and-sandbox
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

        bypass_mode = False

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
