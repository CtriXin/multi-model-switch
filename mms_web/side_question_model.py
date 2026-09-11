"""The read-only model behind a `/btw` side question.

The question goes to the model the session is already using. That is the whole
point: a side question is not a different assistant, it is a different
*request*. What it may not do is join the main agent loop, because a second
turn inside a busy Pi loop would share that loop's state; so this sends one
plain, stateless completion on the session's own route and returns the text.

What the request is allowed to carry is decided elsewhere. `side_questions.py`
builds a budgeted, redacted snapshot and hands it over; this module adds no
history, reads no files, exposes no tools, and writes nothing back. The answer
returns to the side-question row and never to the transcript.

Protocol follows the route, Anthropic Messages first when the route declares
it, matching what the main task itself is doing on that provider. No endpoint
is probed: only URLs the resolved runtime already carries are used, so asking
a question cannot change what a sensitive relay has cached.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

_MAX_ANSWER_TOKENS = 800
# The snapshot is extra context, not a cage. A side question is often an
# ordinary question the user wants answered while something else runs; the
# only thing the model must not do is invent what the main task did.
_SYSTEM = (
    "用户在一个正在运行的任务旁边问了你一个问题。正常回答，"
    "该用你自己的知识就用，不要因为下面的快照没提到就拒绝回答。\n"
    "关于那个主任务，你唯一知道的就是附上的状态快照：你没有参与它，"
    "也读不到它的对话。涉及主任务时只依据快照，快照里没有的就说不知道，"
    "不要推测它做过什么，也不要假装读过它的上下文。\n"
    "用用户提问的语言回答，简短，直接说结论。"
)


def session_route(session) -> tuple[dict, str] | None:
    """The provider runtime and wire model id this session actually launched
    with, read back from its own private `resume.json`. `None` when the
    session has no private runtime to read, which is the case for adopted
    rows and for any test double."""
    root = str((session.meta or {}).get("runtimeRoot") or "").strip()
    if not root:
        return None
    try:
        saved = json.loads((Path(root) / "resume.json").read_text())
    except (OSError, ValueError):
        return None
    runtime = saved.get("runtime")
    if not isinstance(runtime, dict):
        return None
    model_info = saved.get("modelInfo")
    model = ""
    if isinstance(model_info, dict):
        model = str(model_info.get("model") or model_info.get("name") or "")
    elif model_info:
        model = str(model_info)
    model = model or str(runtime.get("model") or "")
    return (runtime, model) if model else None


def _anthropic_target(runtime: dict) -> str:
    """The Anthropic base the runtime already resolved, or "".

    Deliberately not `_resolve_anthropic_base_url`: that probes and caches, and
    a side question must not add endpoint probes to a sensitive relay.
    """
    protocols = runtime.get("protocols") or []
    if "anthropic_messages" not in {str(p).strip() for p in protocols}:
        return ""
    return str(runtime.get("anthropic_base_url") or "").strip().rstrip("/")


def _openai_target(runtime: dict) -> str:
    explicit = str(runtime.get("openai_base_url") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base = str(runtime.get("base_url") or "").strip().rstrip("/")
    if not base:
        return ""
    return base if base.endswith("/v1") else f"{base}/v1"


def _prompt(context: dict) -> str:
    question = str(context.get("question") or "").strip()
    snapshot = {key: value for key, value in context.items() if key != "question"}
    return (
        "会话状态快照：\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=1)
        + f"\n\n用户的旁问：{question}"
    )


def _text_from_anthropic(payload: Any) -> tuple[str, dict]:
    blocks = (payload or {}).get("content") or []
    text = "".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )
    raw = (payload or {}).get("usage") or {}
    incoming = int(raw.get("input_tokens") or 0)
    outgoing = int(raw.get("output_tokens") or 0)
    return text, {
        "inputTokens": incoming,
        "outputTokens": outgoing,
        "totalTokens": incoming + outgoing,
    }


def _text_from_openai(payload: Any) -> tuple[str, dict]:
    choices = (payload or {}).get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    text = str((message or {}).get("content") or "")
    raw = (payload or {}).get("usage") or {}
    incoming = int(raw.get("prompt_tokens") or 0)
    outgoing = int(raw.get("completion_tokens") or 0)
    return text, {
        "inputTokens": incoming,
        "outputTokens": outgoing,
        "totalTokens": int(raw.get("total_tokens") or incoming + outgoing),
    }


def _request(runtime: dict, model: str, context: dict, timeout: float):
    """One non-streaming completion on the session's own route."""
    from mms_core import _runtime_httpx_request

    prompt = _prompt(context)
    anthropic = _anthropic_target(runtime)
    key = str(runtime.get("api_key") or "").strip()
    if anthropic and key:
        response = _runtime_httpx_request(
            "POST",
            f"{anthropic}/v1/messages",
            runtime=runtime,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": _MAX_ANSWER_TOKENS,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        return response, _text_from_anthropic
    base = _openai_target(runtime)
    openai_key = str(runtime.get("openai_api_key") or key).strip()
    if not base or not openai_key:
        raise RuntimeError("这条会话的路由没有可用的地址或凭据")
    response = _runtime_httpx_request(
        "POST",
        f"{base}/chat/completions",
        runtime=runtime,
        headers={
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": _MAX_ANSWER_TOKENS,
            "temperature": 0,
            "stream": False,
        },
        timeout=timeout,
    )
    return response, _text_from_openai


def runner_for(session) -> Callable | None:
    """A `sidecar_runner` bound to one session's route, or `None` when that
    session has no usable route. `None` is what makes the question fail
    closed with a visible reason instead of degrading silently."""
    route = session_route(session)
    if route is None:
        return None
    runtime, model = route
    if not (_anthropic_target(runtime) or _openai_target(runtime)):
        return None
    if not (runtime.get("api_key") or runtime.get("openai_api_key")):
        return None

    def run(context: dict, *, cancel_event: threading.Event, timeout: float) -> dict:
        if cancel_event.is_set():
            return {}
        response, reader = _request(runtime, model, context, timeout)
        if response.status_code >= 400:
            detail = str(response.text or "").strip().replace("\n", " ")
            raise RuntimeError(f"HTTP {response.status_code}: {detail[:120] or '请求失败'}")
        text, usage = reader(response.json())
        if cancel_event.is_set():
            return {}
        return {"answer": text, "usage": usage}

    return run
