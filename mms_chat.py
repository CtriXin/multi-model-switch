import argparse
import asyncio
import base64
import curses
import json
import os
import re
import select as _select
import sys
import termios
import time
import tty

try:
    import httpx
except ImportError:
    httpx = None

try:
    from rich.columns import Columns
    from rich.live import Live
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("缺少依赖，请执行: pip install rich httpx")
    sys.exit(1)

from mms_core import (
    categorize_models,
    console,
    current_command,
    display_title,
    ensure_provider_credentials,
    fetch_models,
)
from mms_provider_profiles import apply_profile_auth_headers, apply_profile_body_patches

MAX_SELECT = 5

# Shared mutable references for Ctrl+C recovery and cross-module view state
_last_buffers: dict = {}
_current_view_state: dict = {"mode": "columns", "focus": 0}


def _nonblock_read_key() -> str | None:
    """Non-blocking read of one key/escape-sequence from stdin.
    Returns 'LEFT', 'RIGHT', 'TAB', or None.
    Assumes stdin is already in cbreak mode (set by run_compare).
    """
    fd = sys.stdin.fileno()
    if not _select.select([fd], [], [], 0)[0]:
        return None
    try:
        ch = os.read(fd, 1)
    except OSError:
        return None
    if ch == b"\x1b":
        # Read rest of escape sequence with a short timeout
        rest = b""
        for _ in range(3):
            if _select.select([fd], [], [], 0.02)[0]:
                rest += os.read(fd, 1)
            else:
                break
        seq = ch + rest
        if seq == b"\x1b[D":
            return "LEFT"
        if seq == b"\x1b[C":
            return "RIGHT"
        return None
    if ch == b"\t":
        return "TAB"
    return None

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_IMAGE_REF_RE = re.compile(r"@(\S+)")


def _profile_runtime_thinking_enabled(runtime):
    if not isinstance(runtime, dict) or "thinking_mode" not in runtime:
        return None
    value = str(runtime.get("thinking_mode") or "").strip().lower()
    if value in {"disable", "disabled", "off", "false", "0", "no"}:
        return False
    if value in {"enable", "enabled", "on", "true", "1", "yes"}:
        return True
    return None


def _profile_runtime_id(runtime):
    if not isinstance(runtime, dict):
        return "", ""
    return (
        str(runtime.get("id") or runtime.get("provider_id") or "").strip(),
        str(runtime.get("profile") or runtime.get("provider_profile") or "").strip(),
    )


def _load_image_b64(path: str) -> tuple:
    """Return (mime_type, base64_data) or (None, None) if not a valid image."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _IMAGE_EXTS:
        return None, None
    if not os.path.isfile(path):
        return None, None
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    }.get(ext, "image/png")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return mime, data


def build_messages(prompt: str) -> tuple:
    """Parse @path image refs from prompt.

    Returns (display_prompt, messages_list).
    Messages list contains text + image_url items for multimodal APIs.
    """
    parts = []
    images = []
    remaining = prompt
    for match in _IMAGE_REF_RE.finditer(prompt):
        path = match.group(1)
        mime, data = _load_image_b64(path)
        if mime:
            images.append((match.start(), match.end(), os.path.basename(path), mime, data))

    if not images:
        return prompt, [{"role": "user", "content": prompt}]

    content = []
    prev_end = 0
    for start, end, name, mime, data in images:
        if start > prev_end:
            text_chunk = prompt[prev_end:start].strip()
            if text_chunk:
                content.append({"type": "text", "text": text_chunk})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{data}"},
        })
        prev_end = end

    tail = prompt[prev_end:].strip()
    if tail:
        content.append({"type": "text", "text": tail})
    if not any(c["type"] == "text" for c in content):
        content.insert(0, {"type": "text", "text": "(见图片)"})

    # Display prompt with [图片: name] placeholders
    display = _IMAGE_REF_RE.sub(
        lambda m: f"[图片: {os.path.basename(m.group(1))}]"
        if os.path.splitext(m.group(1))[1].lower() in _IMAGE_EXTS else m.group(0),
        prompt,
    )
    return display, [{"role": "user", "content": content}]


_MD_PATTERNS = [
    (re.compile(r"```[a-z]*\n(.*?)```", re.DOTALL), r"\1"),
    (re.compile(r"`([^`\n]+)`"), r"\1"),
    (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),
    (re.compile(r"\*\*\*(.+?)\*\*\*", re.DOTALL), r"\1"),
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),
    (re.compile(r"\*(.+?)\*"), r"\1"),
    (re.compile(r"__(.+?)__", re.DOTALL), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^\)]+\)"), r"\1"),
]


def strip_markdown(text: str) -> str:
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class StreamError(RuntimeError):
    """Raised when an SSE stream returns an invalid payload or API error."""


def _grouped_model_rows(models):
    rows = []
    for category, names in categorize_models(models).items():
        rows.append({"kind": "group", "label": category})
        for model in names:
            rows.append({"kind": "model", "label": model})
    return rows


def _move_index(rows, start_idx, step):
    if not rows:
        return 0
    idx = start_idx
    for _ in range(len(rows)):
        idx = (idx + step) % len(rows)
        if rows[idx]["kind"] == "model":
            return idx
    return start_idx


def select_models_tui(models, max_select=MAX_SELECT, min_select=2, title="选择模型"):
    if not models:
        return []

    rows = _grouped_model_rows(models)
    first_model_idx = next((i for i, row in enumerate(rows) if row["kind"] == "model"), 0)

    def _inner(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(4, curses.COLOR_GREEN, -1)

        idx = first_model_idx
        scroll = 0
        selected = []
        message = ""

        while True:
            stdscr.clear()
            max_y, max_w = stdscr.getmaxyx()
            visible = max(6, max_y - 5)

            header = f"{title}"
            hint = f"Selected: {len(selected)}/{max_select}   Space=勾选  Enter=开始  Q=退出"
            try:
                stdscr.addstr(0, 2, header[: max_w - 4], curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(1, 2, hint[: max_w - 4], curses.A_DIM)
            except curses.error:
                pass

            if idx < scroll:
                scroll = idx
            elif idx >= scroll + visible:
                scroll = idx - visible + 1

            for i in range(scroll, min(scroll + visible, len(rows))):
                y = 3 + i - scroll
                row = rows[i]
                if row["kind"] == "group":
                    line = f"[{row['label']}]"
                    attr = curses.color_pair(2) | curses.A_BOLD
                else:
                    checked = "[x]" if row["label"] in selected else "[ ]"
                    cursor = "▸" if i == idx else " "
                    line = f"{cursor} {checked} {row['label']}"
                    attr = curses.color_pair(3) | curses.A_BOLD if i == idx else 0
                try:
                    stdscr.addstr(y, 1, line[: max_w - 2], attr)
                except curses.error:
                    pass

            if message:
                try:
                    stdscr.addstr(max_y - 1, 2, message[: max_w - 4], curses.color_pair(4))
                except curses.error:
                    pass

            stdscr.refresh()
            key = stdscr.getch()

            if key == curses.KEY_UP:
                idx = _move_index(rows, idx, -1)
            elif key == curses.KEY_DOWN:
                idx = _move_index(rows, idx, 1)
            elif key == ord(" "):
                row = rows[idx]
                if row["kind"] != "model":
                    continue
                label = row["label"]
                if label in selected:
                    selected.remove(label)
                    message = ""
                elif len(selected) >= max_select:
                    message = f"最多选择 {max_select} 个模型"
                else:
                    selected.append(label)
                    message = ""
            elif key in (10, 13, curses.KEY_ENTER):
                min_required = min(min_select, len(models), max_select)
                if len(selected) < min_required:
                    message = f"至少选择 {min_required} 个模型"
                    continue
                return selected
            elif key in (ord("q"), ord("Q"), 27):
                return None

    try:
        return curses.wrapper(_inner)
    except curses.error:
        return "fallback"


async def parse_sse_stream(response):
    """Parse OpenAI-compatible SSE and yield plain text deltas."""
    buffer = []

    async def _flush_event():
        nonlocal buffer
        if not buffer:
            return []
        payload_text = "\n".join(buffer).strip()
        buffer = []
        if not payload_text:
            return []
        if payload_text == "[DONE]":
            return None
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise StreamError(f"无法解析 SSE 数据: {exc}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            if isinstance(error, dict):
                message = error.get("message") or json.dumps(error, ensure_ascii=False)
            else:
                message = str(error)
            raise StreamError(message)

        choices = payload.get("choices") or []
        if not choices:
            return []
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content is None:
            return []
        if isinstance(content, str):
            return [content]

        parts = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                    continue
                text_value = item.get("text")
                if isinstance(text_value, dict) and isinstance(text_value.get("value"), str):
                    parts.append(text_value["value"])
        return parts

    if response.status_code >= 400:
        body = await response.aread()
        try:
            payload = json.loads(body.decode("utf-8"))
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or json.dumps(error, ensure_ascii=False)
            else:
                message = json.dumps(payload, ensure_ascii=False)
        except Exception:
            message = body.decode("utf-8", errors="replace")
        raise StreamError(message.strip() or f"HTTP {response.status_code}")

    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line:
            event_parts = await _flush_event()
            if event_parts is None:
                return
            for part in event_parts:
                if part:
                    yield part
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            buffer.append(line[5:].lstrip())

    event_parts = await _flush_event()
    if event_parts is None:
        return
    for part in event_parts:
        if part:
            yield part


async def stream_model(
    client,
    base_url,
    api_key,
    model,
    messages,
    max_tokens=1200,
    runtime=None,
    purpose="default",
):
    if httpx is None:
        raise StreamError("当前环境缺少 httpx，无法建立流式请求")

    url = f"{str(base_url).rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
    }
    provider_id, provider_profile = _profile_runtime_id(runtime)
    apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        runtime=runtime if isinstance(runtime, dict) else None,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=str(base_url),
        model_name=model,
        thinking_enabled=_profile_runtime_thinking_enabled(runtime),
        reasoning_effort=(runtime or {}).get("reasoning_effort") if isinstance(runtime, dict) else None,
        purpose=purpose,
    )
    apply_profile_auth_headers(
        headers,
        protocol="openai_chat",
        api_key=api_key,
        runtime=runtime if isinstance(runtime, dict) else None,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=str(base_url),
        model_name=model,
    )
    timeout = httpx.Timeout(connect=10, write=10, read=None, pool=10)

    async with client.stream("POST", url, headers=headers, json=payload, timeout=timeout) as response:
        async for chunk in parse_sse_stream(response):
            yield chunk


async def _stream_compare_model(client, queue, base_url, api_key, model, prompt, with_footer=False, runtime=None):
    from mms_session import FOOTER_INSTRUCTION
    full_prompt = prompt + FOOTER_INSTRUCTION if with_footer else prompt
    _display, messages = build_messages(full_prompt)
    try:
        async for chunk in stream_model(client, base_url, api_key, model, messages, runtime=runtime):
            await queue.put((model, chunk, None))
    except StreamError as exc:
        await queue.put((model, None, str(exc)))
        return
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await queue.put((model, None, f"{type(exc).__name__}: {exc}"))
        return
    await queue.put((model, None, None))


async def run_compare(provider_ctx, models, prompt, with_footer=False):
    global _last_buffers, _current_view_state
    base_url = provider_ctx["base_url"]
    api_key = provider_ctx["api_key"]
    queue = asyncio.Queue()
    timeout = httpx.Timeout(connect=10, write=10, read=None, pool=10)

    buffers = {model: "" for model in models}
    _last_buffers = buffers
    status = {model: "streaming" for model in models}
    errors = {model: "" for model in models}
    start_times = {}
    finish_times = {}

    # View state: "columns" (default side-by-side) or "tab" (single focused model)
    view = {"mode": "columns", "focus": _current_view_state.get("focus", 0) % max(len(models), 1)}

    def _tab_bar():
        """Compact tab indicator for tab mode."""
        parts = []
        for i, m in enumerate(models):
            st = status[m]
            icon = "✓" if st == "done" else ("✗" if st == "error" else ("⚡" if st == "cancelled" else "…"))
            if i == view["focus"]:
                parts.append(f"[reverse bold] {m} {icon} [/reverse bold]")
            else:
                parts.append(f"[dim] {m} {icon} [/dim]")
        return "  ".join(parts)

    def build_panels():
        panels = []
        for model in models:
            if status[model] == "error":
                body = Text(errors[model], style="red")
                suffix = " [red]✗ error[/red]"
            elif status[model] == "cancelled":
                display = strip_markdown(buffers[model])
                body = Text(display + " (未完成)", style="yellow") if display else Text("(未完成)", style="yellow dim")
                suffix = " [yellow]⚡ 中断[/yellow]"
            elif status[model] == "done":
                display = strip_markdown(buffers[model]) if buffers[model] else ""
                body = Text(display) if display else Text("(empty response)", style="dim")
                elapsed = finish_times.get(model, 0) - start_times.get(model, finish_times.get(model, 0))
                time_str = f"  用时{elapsed:.1f}s" if elapsed > 0.05 else ""
                suffix = f" [green]✓ done[/green][dim]{time_str}[/dim]"
            else:
                display = strip_markdown(buffers[model])
                body = Text(display + " ▌", style="white") if display else Text("▌ 等待中...", style="dim")
                suffix = ""
            panels.append(Panel(body, title=f"[bold]{model}[/bold]{suffix}", expand=True))
        return panels

    def render():
        from rich.console import Group
        panels = build_panels()

        if view["mode"] == "tab":
            focused = panels[view["focus"]]
            hint = Text.from_markup(
                f"  {_tab_bar()}  [dim]←/→ 切换  Tab 并排[/dim]",
                overflow="ellipsis",
            )
            return Group(hint, focused)

        # columns mode: ≤3 side by side, >3 vertical
        if len(panels) <= 3:
            return Columns(panels, equal=True, expand=True)
        return Group(*panels)

    # Set stdin to cbreak so we can read arrow keys non-blocking during streaming
    fd = sys.stdin.fileno()
    try:
        old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        _term_saved = True
    except Exception:
        _term_saved = False

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                asyncio.create_task(
                    _stream_compare_model(client, queue, base_url, api_key, model, prompt, with_footer=with_footer, runtime=provider_ctx)
                )
                for model in models
            ]

            done_count = 0
            with Live(render(), console=console, refresh_per_second=10) as live:
                try:
                    while done_count < len(models):
                        try:
                            model, chunk, error = await asyncio.wait_for(queue.get(), timeout=0.1)
                        except (asyncio.TimeoutError, TimeoutError):
                            # Poll for tab-switch key on each timeout
                            key = _nonblock_read_key()
                            if key == "LEFT":
                                view["mode"] = "tab"
                                view["focus"] = (view["focus"] - 1) % len(models)
                            elif key == "RIGHT":
                                view["mode"] = "tab"
                                view["focus"] = (view["focus"] + 1) % len(models)
                            elif key == "TAB":
                                view["mode"] = "columns" if view["mode"] == "tab" else "tab"
                            live.update(render())
                            continue

                        if error is not None:
                            status[model] = "error"
                            errors[model] = error
                            done_count += 1
                        elif chunk is None:
                            status[model] = "done"
                            finish_times[model] = time.time()
                            done_count += 1
                        else:
                            if model not in start_times:
                                start_times[model] = time.time()
                            buffers[model] += chunk
                        live.update(render())
                except (KeyboardInterrupt, asyncio.CancelledError):
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    for m in models:
                        if status[m] == "streaming":
                            status[m] = "cancelled"

            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if _term_saved:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)

    # Persist focus so action bar starts on the same model
    _current_view_state["focus"] = view["focus"]
    _current_view_state["mode"] = "tab"  # action bar always starts in tab mode
    return buffers


def parse_chat_args(argv):
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} chat",
        description=f"{display_title()} chat — 多模型并发对比",
    )
    parser.add_argument("--provider", help="临时使用指定模型源")
    parser.add_argument("--resume", metavar="SESSION_REF", help="恢复已保存的 session（支持 id / 前缀 / 序号）")
    parser.add_argument("--list-sessions", action="store_true", help="列出当前项目最近保存的 sessions")
    parser.add_argument("prompt", nargs="*", help="聊天任务")
    return parser.parse_args(argv)


def _fallback_select_models(models, max_select=MAX_SELECT, min_select=2):
    table = Table(title="选择模型")
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    for index, model in enumerate(models, 1):
        table.add_row(str(index), model)
    console.print(table)
    limit = min(max_select, len(models))
    min_required = min(min_select, limit)
    while True:
        raw = Prompt.ask(f"输入模型编号，支持逗号分隔（至少 {min_required} 个，最多 {limit} 个）", default="")
        try:
            indexes = []
            for chunk in raw.split(","):
                item = chunk.strip()
                if not item:
                    continue
                value = int(item)
                if not 1 <= value <= len(models):
                    raise ValueError
                if value not in indexes:
                    indexes.append(value)
            if min_required <= len(indexes) <= limit:
                return [models[i - 1] for i in indexes]
        except ValueError:
            pass
        console.print(f"[red]请输入 1-{len(models)} 的编号，数量需在 {min_required}-{limit} 之间[/red]")


def chat_main(cfg, argv):
    if httpx is None:
        console.print("[red]缺少 httpx 依赖，请执行: pip install httpx[/red]")
        sys.exit(1)

    args = parse_chat_args(argv)
    session_cwd = os.getcwd()

    if args.list_sessions:
        from mms_session import list_sessions
        sessions = list_sessions(limit=10, cwd=session_cwd)
        if not sessions:
            console.print("[dim]暂无保存的 session[/dim]")
            return
        from rich.table import Table
        t = Table(title="最近保存的 Sessions")
        t.add_column("#", style="cyan", width=4)
        t.add_column("ID", style="cyan", width=14)
        t.add_column("范围", width=8)
        t.add_column("模式", width=6)
        t.add_column("轮次", width=4)
        t.add_column("目标", style="green")
        import datetime
        for index, s in enumerate(sessions, 1):
            ts = datetime.datetime.fromtimestamp(s["mtime"]).strftime("%m-%d %H:%M")
            scope_label = "项目" if s.get("scope") == "project" else "全局"
            t.add_row(str(index), s["id"], scope_label, s["mode"], str(s["round"]), f"{s['goal']}  [dim]{ts}[/dim]")
        console.print(t)
        return

    provider_ctx = ensure_provider_credentials(cfg, args.provider)

    resumed_session = None
    resolved_session_id = None
    if args.resume:
        from mms_session import load_session_ref
        resumed_session, resolved_session_id, error = load_session_ref(args.resume, cwd=session_cwd)
        if resumed_session is None:
            console.print(f"[red]{error or f'找不到 session: {args.resume}'}[/red]")
            return
        scope_label = "项目" if resumed_session.get("_session_scope") == "project" else "全局"
        console.print(f"[cyan]恢复 session {resolved_session_id}[/cyan]  "
                      f"[dim]来源: {scope_label}[/dim]  "
                      f"[dim]轮次 {resumed_session['round']}，目标: {resumed_session['task']['goal'][:60]}[/dim]")

    models = fetch_models(provider_ctx)
    if not models:
        console.print("[red]当前 provider 没有可用模型，无法执行 chat。[/red]")
        return

    if resumed_session:
        # Use the models from the saved session if they are still available
        saved_models = [m for m in resumed_session.get("models", []) if m in models]
        selected_models = saved_models if saved_models else None
        if not selected_models:
            console.print("[yellow]保存的模型已不可用，请重新选择[/yellow]")

    if not resumed_session or not selected_models:
        selected_models = select_models_tui(models, min_select=2)
        if selected_models == "fallback":
            selected_models = _fallback_select_models(models, min_select=2)
        if not selected_models:
            return

    if resumed_session:
        task_text = resumed_session["task"]["goal"]
    else:
        task_text = " ".join(args.prompt).strip()
        if not task_text:
            from mms_action_bar import _readline
            task_text = _readline("You", "@/path/img.png 可附图")
        if not task_text:
            console.print("[red]聊天任务不能为空[/red]")
            return

    console.print(f"[cyan]开始 chat 并发对比[/cyan]")
    console.print(f"[dim]模型: {', '.join(selected_models)}[/dim]")

    try:
        from mms_action_bar import run_chat_loop
        run_chat_loop(cfg, provider_ctx, selected_models, task_text, session=resumed_session)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消 chat[/yellow]")
