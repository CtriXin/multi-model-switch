"""Bounded internal CLI for a Pi Bot worker context.

The context file is private, but the worker endpoint is deliberately narrow:
only an exact loopback URL is accepted and every operation is one authenticated
JSON POST.  This client does not read MMS configuration or start a process.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


_LOOPBACK_PATH = "/api/v1/bot-worker"
_PORT_RE = re.compile(r"^[1-9][0-9]{0,4}$")
_TIMEOUT_SECONDS = 20
_MAX_RESPONSE_BYTES = 512 * 1024
_MAX_OUTPUT_CHARS = 16_000


class BotClientError(Exception):
    """A user-facing, secret-free client error."""


def _context_error(message: str) -> BotClientError:
    return BotClientError(f"context 无效：{message}")


def _load_context(path: str | Path) -> dict[str, str]:
    context_path = Path(path).expanduser()
    try:
        raw = json.loads(context_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _context_error("文件不存在") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _context_error("无法读取 JSON 文件") from exc
    if not isinstance(raw, dict):
        raise _context_error("必须是 JSON object")

    values: dict[str, str] = {}
    for key in ("url", "token", "taskId", "botId"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise _context_error(f"缺少 {key}")
        values[key] = value.strip()
    _validate_worker_url(values["url"])
    return values


def _validate_worker_url(value: str) -> None:
    split = urlsplit(value)
    if (
        split.scheme != "http"
        or split.hostname != "127.0.0.1"
        or split.username is not None
        or split.password is not None
        or split.path != _LOOPBACK_PATH
        or split.query
        or split.fragment
    ):
        raise _context_error("url 必须是 http://127.0.0.1:<port>/api/v1/bot-worker")
    try:
        port = split.port
    except ValueError as exc:
        raise _context_error("url 端口无效") from exc
    if port is None or not _PORT_RE.fullmatch(str(port)) or port > 65535:
        raise _context_error("url 必须包含有效端口")
    # urlsplit normalizes the hostname, but this keeps alternate netloc forms
    # such as an IPv6 spelling or a trailing dot outside the contract.
    if split.netloc != f"127.0.0.1:{port}":
        raise _context_error("url 必须使用 127.0.0.1 和明确端口")


def _redact(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, "[已隐藏 token]")
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item, token) for key, item in value.items()}
    return value


def _response_payload(data: bytes, token: str) -> Any:
    if len(data) > _MAX_RESPONSE_BYTES:
        raise BotClientError("worker 返回内容过大")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BotClientError("worker 返回了无效 JSON") from exc
    return _redact(payload, token)


def _post(context: dict[str, str], action: str, payload: dict[str, Any], request_id: str) -> Any:
    body = dict(payload)
    body.update(action=action, requestId=request_id)
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        context["url"],
        data=encoded,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {context['token']}",
        },
    )
    try:
        with urlopen(request, timeout=100 if action == "screenshot" else _TIMEOUT_SECONDS) as response:
            return _response_payload(response.read(_MAX_RESPONSE_BYTES + 1), context["token"])
    except HTTPError as exc:
        try:
            detail = _response_payload(exc.read(_MAX_RESPONSE_BYTES + 1), context["token"])
        except BotClientError:
            detail = None
        if isinstance(detail, dict):
            error = detail.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("code")
            else:
                message = detail.get("message")
            if message:
                raise BotClientError(f"worker 请求失败（HTTP {exc.code}）：{message}") from exc
        raise BotClientError(f"worker 请求失败（HTTP {exc.code}）") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise BotClientError("无法连接 Bot worker") from exc


def _text(parts: list[str] | None, *, default: str = "") -> str:
    return " ".join(parts or []).strip() or default


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mms_web.bot_client",
        description="在 Pi Bot worker context 中执行一次受限的 Bot 操作",
    )
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--request-id", help="复用已有 requestId，网络重试时避免重复执行")
    commands = parser.add_subparsers(dest="command", required=True)

    def with_request_id(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
        # Accept the retry option before or after the subcommand.  The
        # subparser default must not overwrite a value parsed by the parent.
        command.add_argument(
            "--request-id",
            dest="request_id",
            default=argparse.SUPPRESS,
            help="复用已有 requestId，网络重试时避免重复执行",
        )
        return command

    with_request_id(commands.add_parser("list", help="列出可派发的 Bot"))

    with_request_id(commands.add_parser("memory-list", help="读取当前 Bot 的长期记忆"))
    memory_search = with_request_id(commands.add_parser("memory-search", help="搜索当前 Bot 的长期记忆"))
    memory_search.add_argument("query", nargs="+")
    memory_remember = with_request_id(commands.add_parser("memory-remember", help="保存一条 Bot 长期记忆"))
    memory_remember.add_argument("content", nargs="+")
    memory_forget = with_request_id(commands.add_parser("memory-forget", help="删除一条 Bot 长期记忆"))
    memory_forget.add_argument("id")

    dispatch = with_request_id(commands.add_parser("dispatch", help="派发子任务"))
    dispatch.add_argument("bot_id")
    dispatch.add_argument("prompt", nargs="+")

    message = with_request_id(commands.add_parser("message", help="向另一个 Bot 发消息，空闲时自动唤醒处理"))
    message.add_argument("bot_id")
    message.add_argument("text", nargs="+")
    reply = with_request_id(commands.add_parser("reply", help="回复收到的消息，接收方由消息记录确定"))
    reply.add_argument("message_id")
    reply.add_argument("text", nargs="+")
    with_request_id(commands.add_parser("inbox", help="查看当前 Bot 收到的消息与分工"))

    screenshot = with_request_id(commands.add_parser("screenshot", help="请求 worker 回传截图"))
    screenshot.add_argument("--url")

    browser = with_request_id(commands.add_parser("browser", help="在持久 Ego 页面执行一个有限浏览器动作"))
    browser.add_argument("operation", choices=("goto", "snapshot", "click", "fill", "press"))
    browser.add_argument("target", nargs="?")
    browser.add_argument("value", nargs="*")

    status = with_request_id(commands.add_parser("status", help="查看当前任务或其后代"))
    status.add_argument("task_id", nargs="?")

    for name, help_text in (
        ("complete", "标记当前轮次完成"),
        ("wait", "等待子任务或用户"),
        ("fail", "标记当前轮次失败"),
    ):
        command = with_request_id(commands.add_parser(name, help=help_text))
        command.add_argument("text", nargs="*")
    return parser


def _command_payload(args: argparse.Namespace, context: dict[str, str]) -> tuple[str, dict[str, Any]]:
    command = args.command
    if command == "list":
        return "list", {"botId": context["botId"], "taskId": context["taskId"]}
    if command == "memory-list":
        return "memory_list", {"botId": context["botId"], "taskId": context["taskId"]}
    if command == "memory-search":
        return "memory_search", {"query": _text(args.query), "botId": context["botId"], "taskId": context["taskId"]}
    if command == "memory-remember":
        return "memory_remember", {"content": _text(args.content), "botId": context["botId"], "taskId": context["taskId"]}
    if command == "memory-forget":
        return "memory_forget", {"id": args.id, "botId": context["botId"], "taskId": context["taskId"]}
    if command == "dispatch":
        return "dispatch", {
            "botId": args.bot_id,
            "prompt": _text(args.prompt),
            "parentTaskId": context["taskId"],
            "senderBotId": context["botId"],
        }
    if command == "message":
        return "message", {
            "recipientBotId": args.bot_id,
            "content": _text(args.text),
            "taskId": context["taskId"],
            "senderBotId": context["botId"],
        }
    if command == "reply":
        return "reply", {"replyTo": args.message_id, "content": _text(args.text)}
    if command == "inbox":
        return "inbox", {}
    if command == "screenshot":
        payload: dict[str, Any] = {
            "taskId": context["taskId"],
            "botId": context["botId"],
        }
        if args.url:
            payload["url"] = args.url
        return "screenshot", payload
    if command == "browser":
        payload = {"taskId": context["taskId"], "botId": context["botId"],
                   "operation": args.operation}
        if args.target:
            payload["target"] = args.target
        if args.value:
            payload["value"] = _text(args.value)
        return "browser", payload
    if command == "status":
        return "status", {
            "taskId": args.task_id or context["taskId"],
            "includeDescendants": True,
        }
    if command == "complete":
        return "complete", {"taskId": context["taskId"], "result": _text(args.text)}
    if command == "wait":
        return "wait", {"taskId": context["taskId"], "reason": _text(args.text, default="等待子任务或用户")}
    if command == "fail":
        text = _text(args.text)
        if not text:
            raise BotClientError("fail 需要填写失败原因")
        return "fail", {"taskId": context["taskId"], "error": text}
    raise BotClientError("未知命令")


def _emit(payload: Any, token: str) -> None:
    output = json.dumps(_redact(payload, token), ensure_ascii=False, separators=(",", ":"))
    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[:_MAX_OUTPUT_CHARS] + "…"
    print(output)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        context = _load_context(args.context)
        action, payload = _command_payload(args, context)
        request_id = str(args.request_id or uuid.uuid4().hex).strip()
        if not request_id:
            raise BotClientError("requestId 不能为空")
        result = _post(context, action, payload, request_id)
        _emit(result, context["token"])
        return 0
    except BotClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        # Keep parser/context failures concise and ensure no exception repr
        # containing a request URL or token reaches the terminal.
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
