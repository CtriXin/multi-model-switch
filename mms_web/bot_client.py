"""Bounded internal CLI for a Pi Bot worker context.

The context file is private, but the worker endpoint is deliberately narrow:
only an exact loopback URL is accepted and every operation is one authenticated
JSON POST.  This client does not read MMS configuration or start a process.

The command list the Bot is told about is generated from the argparse
registration below (see ``command_catalog_text``), so a new subcommand can
never silently stay unknown to the Bot.
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

# The executor runs this file by path (`python .../mms_web/bot_client.py`), so
# the package root is not on sys.path there.  Keep the module usable both as a
# script and as ``mms_web.bot_client``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mms_web import bot_schedules  # noqa: E402
from mms_web.errors import WebError  # noqa: E402


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


# The command catalog is filled by ``_build_parser`` itself: registration and
# the list the Bot reads are the same act, so the two cannot drift apart.
_COMMANDS: list[dict[str, str]] = []
_PARSER: argparse.ArgumentParser | None = None


def _parser() -> argparse.ArgumentParser:
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER


def command_catalog() -> list[dict[str, str]]:
    """Every registered subcommand as ``{name, summary, usage}``."""
    _parser()
    return [dict(item) for item in _COMMANDS]


def command_catalog_text() -> str:
    """The generated "which commands exist" block embedded in the Bot prompt."""
    return "\n".join(f"- {item['usage']}：{item['summary']}" for item in command_catalog())


def registered_command_names(parser: argparse.ArgumentParser | None = None) -> list[str]:
    """Subcommand names as argparse actually registered them.

    Used by the gate test; it walks the parser itself (including the nested
    ``schedule`` operations) instead of trusting a second hand-written list.
    """
    parser = parser or _parser()
    action = next((item for item in parser._actions if isinstance(item, argparse._SubParsersAction)), None)
    names: list[str] = []
    for name, sub in (action.choices.items() if action else []):
        names.append(name)
        nested = next((item for item in sub._actions if isinstance(item, argparse._SubParsersAction)), None)
        names.extend(f"{name} {op}" for op in (nested.choices if nested else {}))
    return names


def _build_parser() -> argparse.ArgumentParser:
    _COMMANDS.clear()
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

    def add(name: str, summary: str, usage: str, *, target=None, label: str | None = None) -> argparse.ArgumentParser:
        _COMMANDS.append({"name": label or name, "summary": summary, "usage": usage})
        return with_request_id((target if target is not None else commands).add_parser(name, help=summary))

    add("list", "列出可派发的 Bot", "list")

    add("memory-list", "读取当前 Bot 的长期记忆", "memory-list")
    memory_search = add("memory-search", "搜索当前 Bot 的长期记忆", "memory-search QUERY")
    memory_search.add_argument("query", nargs="+")
    memory_remember = add("memory-remember", "保存一条 Bot 长期记忆", "memory-remember '内容'")
    memory_remember.add_argument("content", nargs="+")
    memory_forget = add("memory-forget", "删除一条 Bot 长期记忆", "memory-forget ID")
    memory_forget.add_argument("id")

    dispatch = add("dispatch", "向另一个 Bot 派发子任务", "dispatch BOT_ID '任务'")
    dispatch.add_argument("bot_id")
    dispatch.add_argument("prompt", nargs="+")

    message = add("message", "向另一个 Bot 发消息，空闲时自动唤醒处理", "message BOT_ID '消息'")
    message.add_argument("bot_id")
    message.add_argument("text", nargs="+")
    reply = add("reply", "回复收到的消息，接收方由消息记录确定", "reply MESSAGE_ID '回复'")
    reply.add_argument("message_id")
    reply.add_argument("text", nargs="+")
    add("inbox", "查看当前 Bot 收到的消息与分工", "inbox")

    screenshot = add("screenshot", "请求 worker 回传截图", "screenshot --url 'http(s)://...'")
    screenshot.add_argument("--url")

    browser = add("browser", "在持久 Ego 页面执行一个有限浏览器动作", "browser goto/snapshot/click/fill/press [TARGET] [VALUE]")
    browser.add_argument("operation", choices=("goto", "snapshot", "click", "fill", "press"))
    browser.add_argument("target", nargs="?")
    browser.add_argument("value", nargs="*")

    status = add("status", "查看当前任务或其后代", "status [TASK_ID]")
    status.add_argument("task_id", nargs="?")

    wait = add("wait", "等待子任务或用户", "wait '要问用户的问题' [--question '明确的问题'] [--option A --option B]")
    wait.add_argument("text", nargs="*")
    wait.add_argument("--question", help="要问用户的问题；省略时从 text 里解析")
    wait.add_argument("--option", action="append", dest="options", default=None,
                      help="快捷回复选项，可重复，最多 4 个")

    schedule = with_request_id(commands.add_parser("schedule", help="管理这个 Bot 的周期定时"))
    operations = schedule.add_subparsers(dest="schedule_op", required=True)
    create = add("create", "新建一条周期定时",
                 "schedule create '要执行的说明' --every 3h|180m|10800s / --daily HH:MM / --weekly mon 09:00 / --once ISO8601"
                 " [--overlap skip|queue] [--timezone IANA]", target=operations, label="schedule create")
    create.add_argument("prompt", nargs="+")
    kinds = create.add_mutually_exclusive_group(required=True)
    kinds.add_argument("--every", metavar="3h|180m|10800s")
    kinds.add_argument("--daily", metavar="HH:MM")
    kinds.add_argument("--weekly", nargs=2, metavar=("WEEKDAY", "HH:MM"))
    kinds.add_argument("--once", metavar="ISO8601")
    create.add_argument("--overlap", choices=("skip", "queue"), default="skip")
    create.add_argument("--timezone")
    add("list", "列出这个 Bot 的定时", "schedule list", target=operations, label="schedule list")
    schedule_pause = add("pause", "暂停一条定时", "schedule pause SCHEDULE_ID", target=operations, label="schedule pause")
    schedule_pause.add_argument("schedule_id")
    schedule_resume = add("resume", "恢复一条定时", "schedule resume SCHEDULE_ID", target=operations, label="schedule resume")
    schedule_resume.add_argument("schedule_id")
    schedule_delete = add("delete", "删除一条定时", "schedule delete SCHEDULE_ID", target=operations, label="schedule delete")
    schedule_delete.add_argument("schedule_id")

    for name, help_text in (
        ("complete", "标记当前轮次完成"),
        ("fail", "标记当前轮次失败"),
    ):
        command = add(name, help_text, f"{name} '结果或原因'")
        command.add_argument("text", nargs="*")
    return parser


def _schedule_payload(args: argparse.Namespace, context: dict[str, str]) -> tuple[str, dict[str, Any]]:
    op = str(args.schedule_op)
    payload: dict[str, Any] = {"op": op, "botId": context["botId"], "taskId": context["taskId"], "createdBy": "bot"}
    if op == "create":
        try:
            if args.every is not None:
                rule = {"kind": "interval", "everySeconds": bot_schedules.parse_every(args.every)}
            elif args.daily is not None:
                rule = {"kind": "daily", "atLocalTime": str(args.daily).strip()}
            elif args.once is not None:
                rule = {"kind": "once", "at": str(args.once).strip()}
            else:
                weekday, at_local = args.weekly
                rule = {"kind": "weekly", "weekday": bot_schedules.parse_weekday(weekday),
                        "atLocalTime": str(at_local).strip()}
        except WebError as exc:
            raise BotClientError(exc.message) from exc
        payload.update({"prompt": _text(args.prompt), "rule": rule, "overlapPolicy": args.overlap})
        if args.timezone:
            payload["timezone"] = str(args.timezone).strip()
        return "schedule", payload
    if getattr(args, "schedule_id", None):
        payload["scheduleId"] = args.schedule_id
    return "schedule", payload


def _command_payload(args: argparse.Namespace, context: dict[str, str]) -> tuple[str, dict[str, Any]]:
    command = args.command
    if command == "schedule":
        return _schedule_payload(args, context)
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
        payload = {"taskId": context["taskId"], "reason": _text(args.text, default="等待子任务或用户")}
        question = str(getattr(args, "question", None) or "").strip()
        if question:
            payload["question"] = question
        options = [str(item).strip() for item in (getattr(args, "options", None) or []) if str(item).strip()]
        if options:
            payload["options"] = options
        return "wait", payload
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
    parser = _parser()
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
