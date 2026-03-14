import curses
import json

try:
    import httpx
except ImportError:
    httpx = None


class StreamError(RuntimeError):
    """Raised when an SSE stream returns an invalid payload or API error."""


def _grouped_model_rows(models):
    from ccs_core import categorize_models

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


def select_models_tui(models, max_select=5, min_select=2, title="选择模型"):
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


async def stream_model(client, base_url, api_key, model, messages, max_tokens=1200):
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
    timeout = httpx.Timeout(connect=10, write=10, read=None, pool=10)

    async with client.stream("POST", url, headers=headers, json=payload, timeout=timeout) as response:
        async for chunk in parse_sse_stream(response):
            yield chunk
