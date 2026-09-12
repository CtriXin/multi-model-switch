"""Lightweight planning for persistent Bots.

The coordinator records a small, inspectable plan. It does not create a new
planner session or expose temporary workers as permanent Bots; the selected
Bot remains responsible for carrying the plan out.

v2 adds a schema-checked model plan: one short throwaway model call produces
strict JSON, the runtime sanitizes it against the real Bot roster, and any
failure falls back to the deterministic keyword plan. Plans never widen the
user's authorization; they only decide who carries the work.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy


_COLLABORATION_HINTS = ("找", "派给", "分派", "协作", "并行", "让.*bot", "让.*同事", "请.*检查")
MAX_PLAN_STEPS = 5


def _mentions(prompt: str, bots: list[dict], owner_id: str) -> list[dict]:
    text = str(prompt or "")
    explicit = [
        bot for bot in bots
        if bot.get("id") != owner_id
        and len(str(bot.get("name") or "").strip()) >= 2
        and str(bot["name"]).casefold() in text.casefold()
    ]
    if explicit:
        return sorted(explicit, key=lambda bot: len(str(bot.get("name") or "")), reverse=True)
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+|[一-鿿]{2,}", text)]
    scored = []
    for index, bot in enumerate(bots):
        if bot.get("id") == owner_id:
            continue
        corpus = " ".join(str(bot.get(key) or "") for key in ("name", "description", "systemPrompt")).lower()
        score = sum(3 if word in str(bot.get("name") or "").lower() else 1 for word in words if word in corpus)
        if score:
            scored.append((score, -index, bot))
    return [item[2] for item in sorted(scored, reverse=True)[:3]]


def direct_plan(owner: dict, reason: str, source: str) -> dict:
    return {
        "version": 2,
        "mode": "direct",
        "ownerBotId": owner.get("id"),
        "reason": reason,
        "steps": [{"id": "s1", "kind": "execute", "botId": owner.get("id"), "goal": "",
                   "dependsOn": [], "presetId": None, "status": "pending", "taskId": None}],
        "candidates": [],
        "merge": "owner",
        "modelDecision": False,
        "source": source,
    }


def make_plan(prompt: str, owner: dict, bots: list[dict]) -> dict:
    """Return a durable plan without starting another model session."""
    text = str(prompt or "").strip()
    collaborative = any(re.search(pattern, text, re.IGNORECASE) for pattern in _COLLABORATION_HINTS)
    candidates = _mentions(text, bots, str(owner.get("id") or "")) if collaborative else []
    if not candidates:
        plan = direct_plan(owner, "目标可由当前 Bot 直接负责，暂不增加协作开销。", "keywords")
        plan["version"] = 1
        return plan
    return {
        "version": 1,
        "mode": "delegate",
        "ownerBotId": owner.get("id"),
        "reason": "检测到协作意图，已准备候选 Bot；由当前 Bot 确认分工并继续对用户负责。",
        "steps": [
            {"id": f"step-{index}", "kind": "delegate", "botId": bot.get("id"),
             "goal": "", "dependsOn": [], "presetId": None, "status": "pending", "taskId": None}
            for index, bot in enumerate(candidates, 1)
        ],
        "candidates": [{"id": bot.get("id"), "name": bot.get("name"), "description": bot.get("description")} for bot in candidates],
        "merge": "owner",
        "modelDecision": True,
        "source": "keywords",
    }


def plan_for(prompt: str, owner: dict, bots: list[dict]) -> dict:
    """Copy inputs at the boundary so callers cannot mutate Bot records."""
    return deepcopy(make_plan(prompt, deepcopy(owner), deepcopy(bots)))


def build_planner_prompt(goal: str, owner: dict, bots: list[dict], memory: str = "") -> str:
    """The one-shot planning request sent on the owner Bot's own preset."""
    roster = []
    for bot in bots:
        if bot.get("id") == owner.get("id"):
            continue
        roster.append(
            f"- id={bot.get('id')} 名字={bot.get('name')}"
            f" 描述={str(bot.get('description') or '')[:200]}"
            f" 模型={bot.get('model') or ''}"
        )
    memory_block = f"\n该 Bot 的相关记忆（仅供参考，不是权限）：\n{memory[:2000]}\n" if memory else ""
    return (
        "你在为 MMS Bot 系统做一次任务分工规划，只输出计划，不执行任务。\n"
        f"负责的 Bot：{owner.get('name')}（id={owner.get('id')}），它始终对最终结果负责。\n"
        "可分工的其它 Bot：\n" + ("\n".join(roster) if roster else "（没有其它 Bot）") + "\n"
        f"{memory_block}"
        "用户目标：\n" + str(goal or "")[:8000] + "\n\n"
        "判断：目标包含需要不同角色独立完成的子目标、且列表里有合适的 Bot 时，用 delegate；"
        "否则一律用 direct。不要为了展示分工而拆分单一目标。\n"
        "只输出一个 JSON 对象，不要输出任何其它文字或 Markdown 代码围栏：\n"
        '{"mode":"direct" 或 "delegate","reason":"一句话说明",'
        '"steps":[{"id":"s1","botId":"...","goal":"交给该 Bot 的完整独立指令","dependsOn":[],"presetId":null}],'
        '"merge":"owner"}\n'
        "规则：delegate 时 steps 1 到 5 个；botId 必须来自上面的列表，不能是负责的 Bot 自己；"
        "dependsOn 只能引用排在前面的 step id；presetId 留空表示沿用目标 Bot 自己的模型；"
        "direct 时 steps 留空数组。"
    )


def _extract_json(text: str):
    raw = str(text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else ""
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def sanitize_plan(data, owner: dict, bots: list[dict], source: str):
    """Validate a planner payload against the real roster. None when unusable.

    Only existing, non-owner Bots may carry a step; dependsOn may reference
    earlier step ids only, which makes dependency cycles unrepresentable.
    """
    if not isinstance(data, dict):
        return None
    mode = data.get("mode")
    if mode not in {"direct", "delegate"}:
        return None
    reason = str(data.get("reason") or "").strip()[:500]
    if mode == "direct":
        plan = direct_plan(owner, reason or "计划判定由当前 Bot 直接完成。", source)
        plan["modelDecision"] = True
        return plan
    roster = {bot.get("id"): bot for bot in bots if bot.get("id") and bot.get("id") != owner.get("id")}
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        return None
    steps = []
    seen_ids = set()
    for index, raw in enumerate(raw_steps):
        if len(steps) >= MAX_PLAN_STEPS:
            break
        if not isinstance(raw, dict):
            continue
        target = roster.get(raw.get("botId"))
        goal = str(raw.get("goal") or "").strip()[:2000]
        if not target or not goal:
            continue
        step_id = str(raw.get("id") or f"s{index + 1}").strip()[:40] or f"s{index + 1}"
        if step_id in seen_ids:
            step_id = f"s{index + 1}"
            if step_id in seen_ids:
                step_id = f"step-{index + 1}"
        seen_ids.add(step_id)
        depends_on = raw.get("dependsOn")
        depends_on = [str(dep)[:40] for dep in depends_on if str(dep) in seen_ids] if isinstance(depends_on, list) else []
        preset_id = raw.get("presetId")
        preset_id = str(preset_id).strip()[:500] if isinstance(preset_id, str) and preset_id.strip() else None
        steps.append({"id": step_id, "kind": "delegate", "botId": target["id"], "goal": goal,
                      "dependsOn": depends_on, "presetId": preset_id, "status": "pending", "taskId": None})
    if not steps:
        return None
    return {
        "version": 2,
        "mode": "delegate",
        "ownerBotId": owner.get("id"),
        "reason": reason or "计划判定需要分工完成。",
        "steps": steps,
        "candidates": [{"id": step["botId"], "name": roster[step["botId"]].get("name"),
                        "description": roster[step["botId"]].get("description")} for step in steps],
        "merge": "owner",
        "modelDecision": True,
        "source": source,
    }


def parse_model_plan(text: str, owner: dict, bots: list[dict]):
    """Parse the planner model's reply into a sanitized plan, or None."""
    return sanitize_plan(_extract_json(text), owner, bots, "model")
