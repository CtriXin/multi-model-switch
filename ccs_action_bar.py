"""Post-action bar (curses), event reducer, and chat session main loop."""
import asyncio
import curses
import os
import sys
import tempfile
import traceback

from rich.columns import Columns
from rich.panel import Panel

from ccs_chat import run_compare, select_models_tui, strip_markdown, _current_view_state as _chat_view_state
from ccs_core import console, fetch_models
from ccs_session import (
    advance_round,
    build_continuation_prompt,
    create_session,
    extract_brief_footer,
)

_KEY_HINT = (
    "←/→ 切换  ↑/↓ 滚动  Enter 选择此回答  M 选择&换模型继续  "
    "P 并排查看  E 收敛  H 交付  R 重新  Q 退出"
)


def _try_paste_image() -> str | None:
    """Try to read an image from the system clipboard via Pillow.

    Returns a temp file path (PNG) or None.
    """
    try:
        from PIL import ImageGrab  # type: ignore
        img = ImageGrab.grabclipboard()
        if img is not None and hasattr(img, "save"):
            fd, tmp = tempfile.mkstemp(suffix=".png", prefix="mms_paste_")
            os.close(fd)
            img.save(tmp, "PNG")
            return tmp
    except Exception:
        pass
    return None


def _readline(prompt_text="继续提问", hint="Enter=跳过  Ctrl+V=粘贴图片", context=None):  # REDLINE_EXCEPTION: curses event loop, cannot split _inner below 30 lines
    """Curses-based single-line input with optional context displayed above.

    context: text to display in the upper area so the user can read it while typing.
    Layout: [ context area ] [ divider ] [ input line ] [ status ]
    Keys: ←/→ cursor, Home/End, Backspace/Del, Ctrl+A/E/K, Ctrl+V image,
          Cmd+V (bracketed paste) → image or text, Enter, ESC
    Falls back to input() if curses fails.
    """

    # Paste blocks: long pasted text stored as a single logical token.
    # buf element "\x02Pn\x02" represents a whole paste block; treated as one unit.
    _PASTE_THRESHOLD = 60   # chars; below this, insert literally
    paste_blocks: dict[str, str] = {}
    pb_counter = [0]

    def _make_paste_block(text: str) -> str:
        pb_counter[0] += 1
        key = f"\x02P{pb_counter[0]}\x02"
        paste_blocks[key] = text
        return key

    def _is_paste_block(tok: str) -> bool:
        return len(tok) > 1 and tok.startswith("\x02") and tok.endswith("\x02")

    def _tok_display(tok: str) -> str:
        if _is_paste_block(tok):
            return f"[Pasted {len(paste_blocks.get(tok, ''))} chars]"
        return tok

    def _tok_width(tok: str) -> int:
        if _is_paste_block(tok):
            return len(_tok_display(tok))
        return _cjk_width(tok)

    def _dw(toks):
        """Display width of a token list."""
        return sum(_tok_width(t) for t in toks)

    def _chars_fitting(toks, start, max_cols):
        """Number of tokens from toks[start:] that fit in max_cols display columns."""
        w, i = 0, start
        while i < len(toks):
            tw = _tok_width(toks[i])
            if w + tw > max_cols:
                break
            w += tw
            i += 1
        return i - start

    def _buf_to_result(buf):
        """Expand all tokens (paste blocks + image aliases) to final string."""
        parts = []
        for tok in buf:
            if _is_paste_block(tok):
                parts.append(paste_blocks.get(tok, ""))
            else:
                parts.append(tok)
        return _expand_images("".join(parts))

    def _peek(stdscr, n=6):
        """Non-blocking peek at next n chars; returns joined string."""
        stdscr.nodelay(True)
        chars = []
        for _ in range(n):
            try:
                k = stdscr.get_wch()
                chars.append(k if isinstance(k, str) else chr(k))
            except curses.error:
                break
        stdscr.nodelay(False)
        return "".join(chars)

    # image alias map: {"@image1": "/tmp/mms_paste_xxx.png"}
    image_map: dict[str, str] = {}
    img_counter = [0]

    def _show_status_now(stdscr, msg, max_w):
        """Immediately paint a status line and refresh (before blocking IO)."""
        try:
            max_y, _ = stdscr.getmaxyx()
            row = max_y - 1  # always bottom row regardless of layout
            stdscr.addstr(row, 2, msg[:max_w - 4], curses.A_DIM)
            stdscr.refresh()
        except curses.error:
            pass

    def _insert_image(buf, cur, img_path):
        img_counter[0] += 1
        alias = f"@image{img_counter[0]}"
        image_map[alias] = img_path
        marker = list(alias)
        buf[cur:cur] = marker
        return cur + len(marker), alias

    def _expand_images(text):
        # Sort by alias length descending to avoid @image1 clobbering @image10
        for alias in sorted(image_map, key=len, reverse=True):
            text = text.replace(alias, image_map[alias])
        return text

    def _inner(stdscr):
        curses.curs_set(1)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_WHITE, -1)

        # Enable bracketed paste mode (Cmd+V in iTerm2)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()

        prompt = f"〉{prompt_text} ({hint}): "
        buf: list[str] = []
        cur = 0     # cursor char index in buf
        vp = 0      # viewport start char index
        status = ""
        esc_pending = False   # first ESC received, waiting for confirm

        # Pre-wrap context text once
        ctx_lines: list[str] = []
        if context:
            ctx_lines = _wrap_lines(strip_markdown(context), 200)  # will re-wrap per width

        try:
            while True:
                stdscr.clear()
                max_y, max_w = stdscr.getmaxyx()

                # Layout rows:
                #   0 .. ctx_rows-1  : context (if any)
                #   ctx_rows         : divider  (if context)
                #   input_row        : input line
                #   input_row+1      : status
                if ctx_lines:
                    # Reserve bottom 2 rows for input+status; rest is context
                    ctx_rows = max(0, max_y - 2)
                    input_row = max_y - 2
                    # Re-wrap to current terminal width
                    wrapped = _wrap_lines(strip_markdown(context), max(10, max_w - 2))
                    # Show the last ctx_rows-1 lines (tail), leaving row ctx_rows-1 for divider
                    visible_ctx_rows = max(0, ctx_rows - 1)
                    tail = wrapped[max(0, len(wrapped) - visible_ctx_rows):]
                    for i, line in enumerate(tail):
                        try:
                            stdscr.addstr(i, 1, line[:max_w - 2], curses.color_pair(2))
                        except curses.error:
                            pass
                    # Divider
                    try:
                        stdscr.addstr(ctx_rows - 1, 0, "─" * max_w, curses.A_DIM)
                    except curses.error:
                        pass
                else:
                    input_row = 0

                # Compute prompt display width (CJK-aware)
                pw = _str_width(prompt)
                prompt_disp = prompt
                while pw > max_w - 8 and len(prompt_disp) > 4:
                    prompt_disp = prompt_disp[:-1]
                    pw = _str_width(prompt_disp)
                avail = max(4, max_w - pw - 1)

                # Adjust viewport so cursor stays visible
                if cur < vp:
                    vp = cur
                while vp < cur and _dw(buf[vp:cur]) >= avail:
                    vp += 1

                # Draw prompt
                try:
                    stdscr.addstr(input_row, 0, prompt_disp, curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass

                # Draw visible portion of buf (expand paste tokens to display form)
                n_vis = _chars_fitting(buf, vp, avail)
                visible_buf = "".join(_tok_display(t) for t in buf[vp: vp + n_vis])
                try:
                    stdscr.addstr(input_row, pw, visible_buf)
                except curses.error:
                    pass

                # Status row (below input)
                status_row = input_row + 1
                if status and status_row < max_y:
                    try:
                        stdscr.addstr(status_row, 2, status[:max_w - 4], curses.A_DIM)
                    except curses.error:
                        pass

                # CJK-correct cursor column
                cursor_col = pw + _dw(buf[vp:cur])
                try:
                    stdscr.move(input_row, min(cursor_col, max_w - 2))
                except curses.error:
                    pass

                stdscr.refresh()
                status = ""

                try:
                    key = stdscr.get_wch()
                except curses.error:
                    continue

                # Any non-ESC key cancels esc_pending
                is_esc = (key == "\x1b" or key == 27)
                if not is_esc:
                    esc_pending = False

                if isinstance(key, str):
                    if key == "\x1b":
                        rest = _peek(stdscr, 6)
                        if rest.startswith("[200~"):
                            # Bracketed paste: collect until \x1b[201~
                            paste_chars: list[str] = []
                            found_end = False
                            while not found_end:
                                try:
                                    pk = stdscr.get_wch()
                                except curses.error:
                                    break
                                pc = pk if isinstance(pk, str) else chr(pk)
                                if pc == "\x1b":
                                    tail = _peek(stdscr, 5)
                                    if tail.startswith("[201~"):
                                        found_end = True
                                    else:
                                        paste_chars.append(pc)
                                        paste_chars.extend(tail)
                                else:
                                    paste_chars.append(pc)
                            # Image takes priority over pasted text
                            _show_status_now(stdscr, "读取剪贴板...", max_w)
                            img_path = _try_paste_image()
                            if img_path:
                                cur, alias = _insert_image(buf, cur, img_path)
                                status = f"图片已插入 → {alias}"
                            else:
                                text = "".join(c for c in paste_chars if ord(c) >= 32)
                                if len(text) > _PASTE_THRESHOLD:
                                    token = _make_paste_block(text)
                                    buf.insert(cur, token)
                                    cur += 1
                                    status = f"已粘贴 {len(text)} 个字符"
                                else:
                                    for c in text:
                                        buf.insert(cur, c)
                                        cur += 1
                        else:
                            # ESC key: double-press to clear
                            if not buf:
                                return ""           # empty buf → just exit
                            elif esc_pending:
                                buf.clear()
                                cur = 0
                                vp = 0
                                esc_pending = False
                                status = "已清空"
                            else:
                                esc_pending = True
                                status = "再按 ESC 清空全部内容 / 其他键取消"
                    elif key in ("\n", "\r"):
                        return _buf_to_result(buf)
                    elif key == "\x16":  # Ctrl+V — image paste
                        _show_status_now(stdscr, "读取剪贴板...", max_w)
                        img_path = _try_paste_image()
                        if img_path:
                            cur, alias = _insert_image(buf, cur, img_path)
                            status = f"图片已插入 → {alias}"
                        else:
                            status = "剪贴板中没有图片 (PNG/JPEG)"
                    elif key in ("\x7f", "\x08"):
                        if cur > 0:
                            del buf[cur - 1]
                            cur -= 1
                    elif key == "\x01":  # Ctrl+A
                        cur = 0
                    elif key == "\x05":  # Ctrl+E
                        cur = len(buf)
                    elif key == "\x0b":  # Ctrl+K
                        del buf[cur:]
                    elif ord(key) >= 32:
                        buf.insert(cur, key)
                        cur += 1
                elif isinstance(key, int):
                    if key == curses.KEY_LEFT:
                        cur = max(0, cur - 1)
                    elif key == curses.KEY_RIGHT:
                        cur = min(len(buf), cur + 1)
                    elif key == curses.KEY_HOME:
                        cur = 0
                    elif key == curses.KEY_END:
                        cur = len(buf)
                    elif key in (curses.KEY_BACKSPACE, 127, 8):
                        if cur > 0:
                            del buf[cur - 1]
                            cur -= 1
                    elif key == curses.KEY_DC:
                        if cur < len(buf):
                            del buf[cur]
                    elif key in (10, 13, curses.KEY_ENTER):
                        return _buf_to_result(buf)
                    elif key == 27:
                        # Same ESC double-press logic for int path
                        if not buf:
                            return ""
                        elif esc_pending:
                            buf.clear()
                            cur = 0
                            vp = 0
                            esc_pending = False
                            status = "已清空"
                        else:
                            esc_pending = True
                            status = "再按 ESC 清空全部内容 / 其他键取消"
        finally:
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()

    try:
        # Reduce ESC recognition timeout from 1000ms → 25ms
        os.environ.setdefault("ESCDELAY", "25")
        result = curses.wrapper(_inner)
        return result if result is not None else ""
    except curses.error:
        # fallback to readline-enabled input()
        os.system("stty sane 2>/dev/null")
        try:
            import readline  # noqa: F401
        except ImportError:
            pass
        try:
            return input(f"\n〉{prompt_text}: ")
        except (EOFError, KeyboardInterrupt):
            return ""


def _cjk_width(c):
    cp = ord(c)
    if (0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F or
            0xFF00 <= cp <= 0xFFEF or 0x2E80 <= cp <= 0x2EFF or
            0xF900 <= cp <= 0xFAFF or 0x1F300 <= cp <= 0x1F9FF):
        return 2
    return 1


def _str_width(s):
    return sum(_cjk_width(c) for c in s)


def _wrap_lines(text, width):
    """Wrap text respecting CJK double-width characters."""
    result = []
    for line in text.splitlines():
        if not line.strip():
            result.append("")
            continue
        if _str_width(line) <= width:
            result.append(line)
            continue
        # manual wrap
        current, current_w = "", 0
        for char in line:
            cw = _cjk_width(char)
            if current_w + cw > width:
                result.append(current)
                current, current_w = char, cw
            else:
                current += char
                current_w += cw
        if current:
            result.append(current)
    return result


def _print_all_columns(models, display_texts):
    """Print all model outputs side-by-side using Rich (terminal scrollback)."""
    panels = []
    for m in models:
        text = strip_markdown(display_texts.get(m, ""))
        panels.append(Panel(text or "[dim](空)[/dim]", title=f"[bold]{m}[/bold]", expand=True))
    if console.size.width >= 120 and len(panels) <= 3:
        console.print(Columns(panels, equal=True, expand=True))
    else:
        for p in panels:
            console.print(p)
    console.print("\n[dim]── 按 Enter 返回选择 ──[/dim]")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def post_action_bar(models, display_texts, preselect_model=None) -> tuple:  # REDLINE_EXCEPTION: curses event loop
    """Interactive curses action bar.

    Returns (event_name, selected_model_or_None).
    Events: CONTINUE_BRANCH, CHANGE_MODELS_THEN_CONTINUE, CONVERGE_CONCLUSION,
            CONVERGE_HANDOFF, RETRY_TASK, PRINT_ALL, QUIT
    """
    valid_models = [m for m in models if m in display_texts]
    if not valid_models:
        return ("QUIT", None)

    focus_idx = 0
    if preselect_model and preselect_model in valid_models:
        focus_idx = valid_models.index(preselect_model)

    scroll_state = {m: 0 for m in valid_models}

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_GREEN, -1)
        curses.init_pair(5, curses.COLOR_WHITE, -1)

        nonlocal focus_idx

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            model = valid_models[focus_idx]
            content_width = max(10, max_w - 4)
            content_rows = max(3, max_y - 4)

            # Tab bar (row 0)
            tab_x = 1
            for i, m in enumerate(valid_models):
                label = f" {m} "
                attr = (curses.color_pair(3) | curses.A_BOLD) if i == focus_idx else curses.color_pair(1)
                try:
                    stdscr.addstr(0, tab_x, label[: max_w - tab_x - 1], attr)
                except curses.error:
                    pass
                tab_x += len(label) + 1

            # Content
            raw = display_texts.get(model, "")
            clean = strip_markdown(raw)
            all_lines = _wrap_lines(clean, content_width)
            total_lines = len(all_lines)

            scroll = scroll_state[model]
            max_scroll = max(0, total_lines - content_rows)
            scroll = max(0, min(scroll, max_scroll))
            scroll_state[model] = scroll

            for row_offset, line in enumerate(all_lines[scroll: scroll + content_rows]):
                try:
                    stdscr.addstr(2 + row_offset, 2, line[:content_width], curses.color_pair(5))
                except curses.error:
                    pass

            # Scroll indicator
            if total_lines > content_rows:
                pct = int(100 * scroll / max_scroll) if max_scroll else 100
                info = f"行 {scroll+1}-{min(scroll+content_rows, total_lines)}/{total_lines}  {pct}%"
                try:
                    stdscr.addstr(max_y - 2, max(0, max_w - len(info) - 2), info, curses.color_pair(2))
                except curses.error:
                    pass

            # Hint
            try:
                stdscr.addstr(max_y - 1, 1, _KEY_HINT[: max_w - 2], curses.A_DIM)
            except curses.error:
                pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_LEFT:
                focus_idx = (focus_idx - 1) % len(valid_models)
            elif key == curses.KEY_RIGHT:
                focus_idx = (focus_idx + 1) % len(valid_models)
            elif key == curses.KEY_UP:
                scroll_state[model] = max(0, scroll - 1)
            elif key == curses.KEY_DOWN:
                scroll_state[model] = min(max_scroll, scroll + 1)
            elif key == curses.KEY_PPAGE:
                scroll_state[model] = max(0, scroll - content_rows)
            elif key == curses.KEY_NPAGE:
                scroll_state[model] = min(max_scroll, scroll + content_rows)
            elif key in (10, 13, curses.KEY_ENTER):
                return ("CONTINUE_BRANCH", valid_models[focus_idx])
            elif key in (ord("m"), ord("M")):
                return ("CHANGE_MODELS_THEN_CONTINUE", valid_models[focus_idx])
            elif key in (ord("p"), ord("P")):
                return ("PRINT_ALL", valid_models[focus_idx])
            elif key in (ord("e"), ord("E")):
                return ("CONVERGE_CONCLUSION", valid_models[focus_idx])
            elif key in (ord("h"), ord("H")):
                return ("CONVERGE_HANDOFF", valid_models[focus_idx])
            elif key in (ord("r"), ord("R")):
                return ("RETRY_TASK", None)
            elif key in (ord("q"), ord("Q"), 27):
                return ("QUIT", None)

    try:
        return curses.wrapper(_inner)
    except curses.error as exc:
        console.print(f"\n[yellow]curses fallback ({exc})[/yellow]")
        for i, m in enumerate(valid_models, 1):
            console.print(f"  {i}. {m}")
        raw = _readline("编号", "M=换模型 P=并排 R=重新 Q=退出") or "1"
        rl = raw.lower()
        if rl == "q":
            return ("QUIT", None)
        if rl == "r":
            return ("RETRY_TASK", None)
        if rl == "m":
            return ("CHANGE_MODELS_THEN_CONTINUE", valid_models[0])
        if rl == "p":
            return ("PRINT_ALL", valid_models[0])
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(valid_models):
                return ("CONTINUE_BRANCH", valid_models[idx])
        except ValueError:
            pass
        return ("CONTINUE_BRANCH", valid_models[0])


def _fallback_brief(display_text):
    preview = display_text[:200].replace("\n", " ")
    return {"approach": preview, "reasoning": "", "risks": [], "key_decisions": [], "next_step": ""}


async def _run_refine(provider_ctx, session):
    from ccs_chat import stream_model
    from ccs_discuss import REFINE_SYSTEM_PROMPT
    import httpx
    import json as _json
    from rich.live import Live

    brief = session["branch"]["brief"] or {}
    payload = {
        "task": session["task"]["goal"],
        "selected_approach": brief,
        "invariants": session["task"]["invariants"],
    }
    messages = [
        {"role": "system", "content": REFINE_SYSTEM_PROMPT},
        {"role": "user", "content": _json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    model = session["branch"]["selected_model"] or session["models"][0]
    title = "收敛结论"

    timeout = httpx.Timeout(connect=10, write=10, read=None, pool=10)
    chunks = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        with Live(
            Panel(f"正在生成{title}...", title=f"{title} · {model}", border_style="cyan"),
            console=console,
            refresh_per_second=10,
        ) as live:
            async for chunk in stream_model(
                client, provider_ctx["base_url"], provider_ctx["api_key"],
                model, messages, max_tokens=1200,
            ):
                chunks.append(chunk)
                live.update(Panel(
                    strip_markdown("".join(chunks)),
                    title=f"{title} · {model}",
                    border_style="cyan",
                ))
    return "".join(chunks).strip()


async def _run_synthesize(provider_ctx, session, selected_model, summaries):
    import httpx
    from ccs_discuss import phase3_synthesize

    timeout = httpx.Timeout(connect=10, write=10, read=60, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await phase3_synthesize(
            provider_ctx, client, selected_model, session["task"]["goal"], summaries,
        )


def _handle_converge(provider_ctx, session, selected, briefs) -> str:
    """Run refine or synthesize and return the result text."""
    available_briefs = {m: b for m, b in briefs.items() if b is not None}
    if len(available_briefs) <= 1:
        return asyncio.run(_run_refine(provider_ctx, session)) or ""
    else:
        summaries = {m: {"ok": True, "data": b} for m, b in available_briefs.items()}
        return asyncio.run(_run_synthesize(provider_ctx, session, selected, summaries)) or ""


def _handle_handoff(session, selected, display_texts):
    """H = 打印 action brief，给出可直接执行的 mms 命令。"""
    task = session["task"]["goal"]
    selected_text = strip_markdown(display_texts.get(selected, ""))[:800]

    console.print("\n[bold cyan]── 执行交付简报 ──[/bold cyan]")
    console.print(Panel(selected_text or "(无内容)", title=f"选中方案 · {selected}", border_style="yellow"))

    # 打印可复用的命令
    import shlex
    safe_task = shlex.quote(task)
    console.print(f"\n[dim]下一步建议：[/dim]")
    console.print(f"  [green]mms discuss {safe_task}[/green]  [dim]# 多模型综合裁定[/dim]")
    console.print(f"  [green]mms chat {safe_task}[/green]     [dim]# 重新比较[/dim]")
    console.print()


def _pick_event(models, display_texts, initial_focus):
    """Run action bar, re-entering on PRINT_ALL. Returns (event, selected)."""
    event, selected, preselect = "__init__", None, initial_focus
    terminal_events = {
        "CONTINUE_BRANCH", "CHANGE_MODELS_THEN_CONTINUE",
        "CONVERGE_CONCLUSION", "CONVERGE_HANDOFF", "RETRY_TASK", "QUIT",
    }
    while event not in terminal_events:
        try:
            event, selected = post_action_bar(models, display_texts, preselect_model=preselect)
            preselect = selected
        except Exception:
            console.print("\n[red]action bar 出错:[/red]")
            console.print(traceback.format_exc())
            return "QUIT", None
        if event == "PRINT_ALL":
            _print_all_columns(models, display_texts)
            event = "__init__"
    return event, selected


def _on_continue(session, models, selected, briefs, display_texts, provider_ctx, task_text):
    """Handle CONTINUE_BRANCH / CHANGE_MODELS_THEN_CONTINUE. Returns next prompt or None."""
    brief = briefs.get(selected) or _fallback_brief(display_texts.get(selected, ""))
    advance_round(session, selected, brief, display_texts.get(selected, ""), round_models=list(models))
    if session.get("_switch_models"):
        all_models = fetch_models(provider_ctx)
        new_models = select_models_tui(all_models)
        if new_models and new_models != "fallback":
            models[:] = new_models
            session["models"] = models
        session.pop("_switch_models", None)
    try:
        new_q = _readline("继续提问", "Enter=跳过  @/path/img.png 附图")
    except (EOFError, KeyboardInterrupt):
        return None
    return build_continuation_prompt(session, new_q) if new_q else ""


def _on_handoff(session, models, selected, briefs, display_texts, task_text):
    """Handle CONVERGE_HANDOFF. Returns next prompt, '' to retry, or None to quit."""
    brief = briefs.get(selected) or _fallback_brief(display_texts.get(selected, ""))
    advance_round(session, selected, brief, display_texts.get(selected, ""), round_models=list(models))
    _handle_handoff(session, selected, display_texts)
    context = strip_markdown(display_texts.get(selected, ""))
    try:
        follow_up = _readline("继续追问", "Enter=退出  R=重新", context=context)
    except (EOFError, KeyboardInterrupt):
        return None
    if not follow_up or follow_up.lower() == "q":
        return None
    if follow_up.lower() == "r":
        return task_text
    return build_continuation_prompt(session, follow_up)


def _on_converge(provider_ctx, session, models, selected, briefs, display_texts, task_text):
    """Handle CONVERGE_CONCLUSION. Returns next prompt, task_text to retry, or None to quit."""
    brief = briefs.get(selected) or _fallback_brief(display_texts.get(selected, ""))
    advance_round(session, selected, brief, display_texts.get(selected, ""), round_models=list(models))
    converge_text = ""
    try:
        converge_text = _handle_converge(provider_ctx, session, selected, briefs)
    except Exception:
        console.print("\n[red]converge 出错:[/red]")
        console.print(traceback.format_exc())
    try:
        follow_up = _readline("继续追问", "Enter=退出  R=重新", context=converge_text)
    except (EOFError, KeyboardInterrupt):
        return None
    if not follow_up or follow_up.lower() == "q":
        return None
    if follow_up.lower() == "r":
        return task_text
    return build_continuation_prompt(session, follow_up)


def run_chat_loop(cfg, provider_ctx, models, task_text):
    """Main interactive chat loop with session state machine."""
    import ccs_chat as _ccs_chat_mod

    session = create_session(task_text, models)
    prompt = task_text

    while True:
        try:
            buffers = asyncio.run(run_compare(provider_ctx, models, prompt, with_footer=True))
        except (KeyboardInterrupt, asyncio.CancelledError):
            buffers = dict(_ccs_chat_mod._last_buffers)
            if not any(v for v in buffers.values()):
                console.print("\n[yellow]中断时尚无内容，退出[/yellow]")
                break
            console.print("\n[yellow]已中断 — 进入结果查看[/yellow]")
        except Exception:
            console.print("\n[red]run_compare 出错:[/red]")
            console.print(traceback.format_exc())
            break

        if buffers is None:
            break

        briefs, display_texts = {}, {}
        for m, raw in buffers.items():
            display_texts[m], briefs[m] = extract_brief_footer(raw)

        initial_focus = models[_chat_view_state.get("focus", 0) % max(len(models), 1)]
        event, selected = _pick_event(models, display_texts, initial_focus)

        if event == "QUIT":
            break
        elif event == "RETRY_TASK":
            prompt = task_text
        elif event == "CHANGE_MODELS_THEN_CONTINUE":
            session["_switch_models"] = True
            next_prompt = _on_continue(session, models, selected, briefs, display_texts, provider_ctx, task_text)
            if next_prompt is None:
                break
            prompt = next_prompt or task_text
        elif event == "CONTINUE_BRANCH":
            next_prompt = _on_continue(session, models, selected, briefs, display_texts, provider_ctx, task_text)
            if next_prompt is None:
                break
            prompt = next_prompt or task_text
        elif event == "CONVERGE_HANDOFF":
            next_prompt = _on_handoff(session, models, selected, briefs, display_texts, task_text)
            if next_prompt is None:
                break
            prompt = next_prompt
        elif event == "CONVERGE_CONCLUSION":
            next_prompt = _on_converge(provider_ctx, session, models, selected, briefs, display_texts, task_text)
            if next_prompt is None:
                break
            prompt = next_prompt
