import argparse
import asyncio
import json

try:
    import httpx
except ImportError:
    httpx = None

from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from ccs_chat import StreamError, select_models_tui, stream_model
from ccs_core import (
    Prompt as CorePrompt,
    console,
    current_command,
    display_title,
    ensure_provider_credentials,
    fetch_models,
)

PHASE1_SYSTEM_PROMPT = """你是一个严格压缩输出的技术分析助手。
你会收到一个任务，请独立思考，并且只输出 JSON。
禁止输出 markdown、禁止代码块、禁止额外解释。
JSON 必须包含这些字段：
- approach: 一句话核心方案
- reasoning: 2-3 句原因
- risks: 1-3 条风险数组
- key_decisions: 1-3 条关键决策数组
- next_step: 一句话建议下一步
输出必须是合法 JSON。"""

PHASE2_SYSTEM_PROMPT = """你是一个严格挑刺的 reviewer。
你会看到另一位模型的简短方案摘要。
你的任务不是表扬，而是指出最关键的问题，并给出更好的替代方向。
只输出 JSON，禁止 markdown、禁止代码块、禁止额外解释。
JSON 必须包含：
- agreement: 一句你认可的点
- challenge: 一个最关键的质疑
- better_option: 如果要改，怎么改更好
输出必须是合法 JSON。"""

PHASE3_SYSTEM_PROMPT = """你是一个严格的 reviewer 和 architect。
你会拿到原始任务、多个候选摘要，以及可选的交叉审查意见。
你必须：
1. 指出每个方案最致命的不足
2. 提炼形成共识的部分
3. 指出真正存在分歧的地方
4. 给出最终融合建议
5. 给出推荐下一步动作
输出面向最终用户，使用清晰可读的中文结构化文本。
不要返回 JSON，不要空泛表扬。"""


def parse_discuss_args(argv):
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} discuss",
        description=f"{display_title()} discuss — 多模型摘要发散与综合裁定",
    )
    parser.add_argument("--provider", help="临时使用指定模型源")
    parser.add_argument("--cross", action="store_true", help="启用环形交叉审查")
    parser.add_argument("prompt", nargs="*", help="讨论任务")
    return parser.parse_args(argv)


def _extract_message_text(message_content):
    if isinstance(message_content, str):
        return message_content.strip()
    if isinstance(message_content, list):
        parts = []
        for item in message_content:
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
        return "".join(parts).strip()
    return ""


def _strip_code_fence(content):
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _compact_text(value, limit=88):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_json_error(raw_text, exc):
    preview = _compact_text(raw_text, limit=140)
    return f"JSON 解析失败: {exc}; 原始响应: {preview}"


async def _collect_stream_text(client, base_url, api_key, model, messages, max_tokens):
    chunks = []
    async for chunk in stream_model(
        client,
        base_url,
        api_key,
        model,
        messages,
        max_tokens=max_tokens,
    ):
        chunks.append(chunk)
    return "".join(chunks).strip()


async def call_model_json(client, base_url, api_key, model, messages, max_tokens=500):
    if httpx is None:
        raise StreamError("当前环境缺少 httpx，无法发起请求")

    raw_text = _strip_code_fence(
        await _collect_stream_text(
            client,
            base_url,
            api_key,
            model,
            messages,
            max_tokens=max_tokens,
        )
    )
    if not raw_text:
        raise StreamError(f"{model} 没有返回内容")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StreamError(_format_json_error(raw_text, exc)) from exc


async def _run_json_phase(progress, task_id, coro):
    try:
        result = await coro
        progress.advance(task_id)
        return result
    except Exception:
        progress.advance(task_id)
        raise


async def phase1_diverge(provider_ctx, client, models, task_text):
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    )
    phase_task = progress.add_task("Phase 1 摘要发散", total=len(models))

    async def _one_model(model):
        messages = [
            {"role": "system", "content": PHASE1_SYSTEM_PROMPT},
            {"role": "user", "content": task_text},
        ]
        try:
            data = await _run_json_phase(
                progress,
                phase_task,
                call_model_json(
                    client,
                    provider_ctx["base_url"],
                    provider_ctx["api_key"],
                    model,
                    messages,
                    max_tokens=420,
                ),
            )
            return model, {"ok": True, "data": data}
        except Exception as exc:
            return model, {"ok": False, "error": str(exc)}

    with progress:
        results = await asyncio.gather(*[_one_model(model) for model in models])
    return dict(results)


async def phase2_cross_review(provider_ctx, client, ordered_models, summaries):
    if len(ordered_models) < 2:
        return {}

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    )
    phase_task = progress.add_task("Phase 2 环形交叉审查", total=len(ordered_models))

    async def _one_review(index, model):
        target = ordered_models[(index + 1) % len(ordered_models)]
        target_summary = summaries.get(target, {})
        if not target_summary.get("ok"):
            progress.advance(phase_task)
            return model, {
                "ok": False,
                "skipped": True,
                "target": target,
                "error": f"上游摘要不可用: {target_summary.get('error', 'unknown error')}",
            }

        review_payload = {
            "target_model": target,
            "summary": target_summary.get("data"),
        }
        messages = [
            {"role": "system", "content": PHASE2_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(review_payload, ensure_ascii=False, indent=2)},
        ]
        try:
            data = await _run_json_phase(
                progress,
                phase_task,
                call_model_json(
                    client,
                    provider_ctx["base_url"],
                    provider_ctx["api_key"],
                    model,
                    messages,
                    max_tokens=260,
                ),
            )
            return model, {"ok": True, "target": target, "data": data}
        except Exception as exc:
            return model, {"ok": False, "target": target, "error": str(exc)}

    with progress:
        results = await asyncio.gather(*[_one_review(index, model) for index, model in enumerate(ordered_models)])
    return dict(results)


async def phase3_synthesize(provider_ctx, client, synthesizer_model, task_text, summaries, reviews=None):
    payload = {
        "task": task_text,
        "summaries": summaries,
        "cross_reviews": reviews or {},
    }
    messages = [
        {"role": "system", "content": PHASE3_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]

    chunks = []
    live = Live(
        Panel("正在生成最终综合结论...", title=f"Phase 3 · {synthesizer_model}", border_style="cyan"),
        console=console,
        refresh_per_second=10,
    )
    with live:
        async for chunk in stream_model(
            client,
            provider_ctx["base_url"],
            provider_ctx["api_key"],
            synthesizer_model,
            messages,
            max_tokens=1400,
        ):
            chunks.append(chunk)
            live.update(
                Panel(
                    "".join(chunks) or "正在生成最终综合结论...",
                    title=f"Phase 3 · {synthesizer_model}",
                    border_style="cyan",
                )
            )
    return "".join(chunks).strip()


def _render_summaries_table(summaries):
    table = Table(title="Phase 1 · 摘要发散", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("核心方案", style="green")
    table.add_column("主要风险", style="yellow")
    table.add_column("下一步", style="magenta")

    for model, result in summaries.items():
        if result.get("ok"):
            data = result.get("data", {})
            risks = data.get("risks") or []
            table.add_row(
                model,
                _compact_text(data.get("approach", "")),
                _compact_text("; ".join(str(item) for item in risks)),
                _compact_text(data.get("next_step", "")),
            )
        else:
            table.add_row(model, "[red]失败[/red]", _compact_text(result.get("error", "")), "-")
    console.print(table)


def _render_reviews_table(reviews):
    table = Table(title="Phase 2 · 环形交叉审查", show_lines=True)
    table.add_column("审查模型", style="cyan")
    table.add_column("目标模型", style="green")
    table.add_column("关键质疑", style="yellow")
    table.add_column("更优替代", style="magenta")

    for model, result in reviews.items():
        if result.get("ok"):
            data = result.get("data", {})
            table.add_row(
                model,
                result.get("target", "-"),
                _compact_text(data.get("challenge", "")),
                _compact_text(data.get("better_option", "")),
            )
        elif result.get("skipped"):
            table.add_row(model, result.get("target", "-"), "[yellow]跳过[/yellow]", _compact_text(result.get("error", "")))
        else:
            table.add_row(model, result.get("target", "-"), "[red]失败[/red]", _compact_text(result.get("error", "")))
    console.print(table)


def _fallback_select_models(models, max_select=5, min_select=1):
    table = Table(title="选择模型")
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    for index, model in enumerate(models, 1):
        table.add_row(str(index), model)
    console.print(table)
    limit = min(max_select, len(models))
    min_required = min(min_select, limit)
    while True:
        raw = CorePrompt.ask(f"输入模型编号，支持逗号分隔（至少 {min_required} 个，最多 {limit} 个）", default="")
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


def _select_discuss_models(models):
    selected = select_models_tui(models, min_select=1)
    if selected == "fallback":
        return _fallback_select_models(models, min_select=1)
    if not selected:
        return None
    return selected


async def run_discussion(provider_ctx, models, task_text, cross=False):
    if httpx is None:
        raise StreamError("当前环境缺少 httpx，请先安装 rich/httpx 依赖")

    timeout = httpx.Timeout(connect=10, write=10, read=60, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        summaries = await phase1_diverge(provider_ctx, client, models, task_text)
        _render_summaries_table(summaries)

        reviews = {}
        if cross:
            reviews = await phase2_cross_review(provider_ctx, client, models, summaries)
            _render_reviews_table(reviews)

        successful_models = [model for model in models if summaries.get(model, {}).get("ok")]
        if not successful_models:
            console.print("[red]Phase 1 没有任何模型成功返回摘要，已跳过最终综合。[/red]")
            return {"summaries": summaries, "reviews": reviews, "final": ""}

        synthesizer_model = successful_models[0]
        final_text = await phase3_synthesize(
            provider_ctx,
            client,
            synthesizer_model,
            task_text,
            summaries,
            reviews=reviews,
        )
        console.print(Panel(final_text or "综合阶段没有返回内容。", title="最终综合结论", border_style="green"))
        return {"summaries": summaries, "reviews": reviews, "final": final_text}


def discuss_main(cfg, argv):
    args = parse_discuss_args(argv)
    provider_ctx = ensure_provider_credentials(cfg, args.provider)
    models = fetch_models(provider_ctx)
    if not models:
        console.print("[red]当前 provider 没有可用模型，无法执行 discuss。[/red]")
        return

    selected_models = _select_discuss_models(models)
    if not selected_models:
        return

    task_text = " ".join(args.prompt).strip()
    if not task_text:
        task_text = Prompt.ask("You").strip()
    if not task_text:
        console.print("[red]讨论任务不能为空[/red]")
        return

    mode_label = "模式 C：环形交叉审查 + 对抗收敛" if args.cross else "模式 B：摘要发散 + 对抗收敛"
    console.print(f"[cyan]开始 {mode_label}[/cyan]")
    console.print(f"[dim]模型: {', '.join(selected_models)}[/dim]")

    try:
        asyncio.run(run_discussion(provider_ctx, selected_models, task_text, cross=args.cross))
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消 discuss[/yellow]")
