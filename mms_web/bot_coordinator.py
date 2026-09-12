"""Lightweight planning for persistent Bots.

The coordinator records a small, inspectable plan. It does not create a new
planner session or expose temporary workers as permanent Bots; the selected
Bot remains responsible for carrying the plan out.
"""
from __future__ import annotations

import re
from copy import deepcopy


_COLLABORATION_HINTS = ("找", "派给", "分派", "协作", "并行", "让.*bot", "让.*同事", "请.*检查")


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
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text)]
    scored = []
    for index, bot in enumerate(bots):
        if bot.get("id") == owner_id:
            continue
        corpus = " ".join(str(bot.get(key) or "") for key in ("name", "description", "systemPrompt")).lower()
        score = sum(3 if word in str(bot.get("name") or "").lower() else 1 for word in words if word in corpus)
        if score:
            scored.append((score, -index, bot))
    return [item[2] for item in sorted(scored, reverse=True)[:3]]


def make_plan(prompt: str, owner: dict, bots: list[dict]) -> dict:
    """Return a durable plan without starting another model session."""
    text = str(prompt or "").strip()
    collaborative = any(re.search(pattern, text, re.IGNORECASE) for pattern in _COLLABORATION_HINTS)
    candidates = _mentions(text, bots, str(owner.get("id") or "")) if collaborative else []
    if not candidates:
        return {
            "version": 1,
            "mode": "direct",
            "ownerBotId": owner.get("id"),
            "reason": "目标可由当前 Bot 直接负责，暂不增加协作开销。",
            "steps": [{"id": "step-1", "kind": "execute", "botId": owner.get("id"), "status": "pending"}],
            "candidates": [],
            "modelDecision": False,
        }
    return {
        "version": 1,
        "mode": "delegate",
        "ownerBotId": owner.get("id"),
        "reason": "检测到协作意图，已准备候选 Bot；由当前 Bot 确认分工并继续对用户负责。",
        "steps": [
            {"id": f"step-{index}", "kind": "delegate", "botId": bot.get("id"), "status": "pending"}
            for index, bot in enumerate(candidates, 1)
        ],
        "candidates": [{"id": bot.get("id"), "name": bot.get("name"), "description": bot.get("description")} for bot in candidates],
        "modelDecision": True,
    }


def plan_for(prompt: str, owner: dict, bots: list[dict]) -> dict:
    """Copy inputs at the boundary so callers cannot mutate Bot records."""
    return deepcopy(make_plan(prompt, deepcopy(owner), deepcopy(bots)))
