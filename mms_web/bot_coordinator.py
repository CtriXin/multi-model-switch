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
from datetime import datetime, timezone


_COLLABORATION_HINTS = (
    "找", "派给", "分派", "协作", "并行", "让.*bot", "让.*同事", "请.*检查",
    r"让\s+(?!我|你|他|它|我们|自己)[A-Za-z0-9_-]{1,40}\s",
    r"让\s*(?!我|你|他|它|我们|自己)[\u4e00-\u9fff]{1,8}(?:帮|写|检查|处理|做|整理|核对|各)",
)
MAX_PLAN_STEPS = 5
MAX_FLEET_STEPS = 12
DEFAULT_FLEET_FAMILIES = 2
UI_FLEET_FAMILIES = 12
MAX_PLAN_HISTORY = 50
ON_FAILURE_POLICIES = {"retry", "skip", "abort"}
SPLIT_PLAN_MODES = {"delegate", "fleet"}
FLEET_INTENSITIES = {"opinions", "intense"}
DEFAULT_FLEET_POLICY = {
    "enabled": True,
    "intensity": "opinions",
    "maxFamilies": DEFAULT_FLEET_FAMILIES,
    "families": [],
    "models": {},
    "hintShown": False,
}
UNDERFILLED_REASON = "现在只有一家能用，我自己看了，不是多方评审。"
FLEET_DISABLED_REASON = "没叫别人，我自己做。"
FLEET_FIRST_HINT = (
    "这次会再问 {n} 家。想只问我，把上面关掉就行。"
)
FLEET_WORKER_PROMPT = (
    "只用下面三行，每行不超过 40 字，不要空行、不要 markdown、不要再分发：\n"
    "结论：\n"
    "不同意：\n"
    "风险：\n\n"
)
FLEET_MERGE_INTRO = (
    "各家意见如下。只按下面四段输出，不要作文、不要再分发。"
    "没有分歧就写「分歧：无」。\n"
    "分歧：\n- （谁 vs 谁：争什么）\n"
    "风险：\n- \n"
    "共识：\n- \n"
    "判断：\n（你站哪边，一句话）\n"
)
_VERDICT_HEADING = re.compile(
    r"^\*{0,2}(分歧|风险|共识|判断)\*{0,2}\s*[:：]?\s*(.*)$"
)
_SECTION_SPLIT = re.compile(r"(分歧|风险|共识|判断)\s*[:：]\s*")
_TAKE_SPLIT = re.compile(r"(结论|不同意|风险)\s*[:：]\s*")
_EMPTY_VERDICT = {"无", "没有", "无。", "无分歧", "无风险"}

_CHEAP_MARKERS = ("flash", "turbo", "highspeed", "mini", "air", "lite", "haiku", "small", "fast")
_INTENSE_MARKERS = ("opus", "sonnet", "thinking", "max", "pro", "heavy", "astra", "k3", "5.4", "5.6", "gpt-6")

# Multi-model review on ONE named Bot. Single-model "帮我评审" must stay False.
_FLEET_REVIEW = re.compile(
    r"几个模型|多家模型|多个模型|各家模型|跨家族|交叉审|交叉评|"
    r"委员会|committee review|review across|"
    r"对比.{0,12}(意见|评审|review)|"
    r"(用|让).{0,12}(能用的|可用的)?模型.{0,8}(一起|分别|各自)?(看|审|评)|"
    r"一起(评审|review)",
    re.IGNORECASE,
)

# Multi-goal shape signals: two or more list markers on their own lines,
# inline full-width enumerations (1）2）…), circled numbers, parallel adverbs,
# or at least two roster Bot names in one prompt.
_LIST_LINE = re.compile(r"^\s*(?:\d{1,2}[.、)]\s*\S|[-*•]\s+\S|[①-⑩]\s*\S)", re.MULTILINE)
_INLINE_ENUM = re.compile(r"\d+）")
_CIRCLED = re.compile(r"[①-⑩]")
_PARALLEL_WORDS = re.compile(r"分别|同时|各自|一边.{0,20}一边")

# Plan-level state machine. `rejected` from auto/approved/running is the 30s
# undo path; `failed -> running` is the explicit retry-step reopen.
PLAN_TRANSITIONS = {
    "proposed": {"approved", "rejected", "cancelled"},
    "auto": {"running", "rejected", "cancelled"},
    "approved": {"running", "rejected", "cancelled"},
    "running": {"merging", "failed", "cancelled", "rejected"},
    "merging": {"done", "failed", "cancelled"},
    "rejected": set(),
    "failed": {"running"},
    "done": set(),
    "cancelled": set(),
}

# Step-level state machine. `dispatched`/`blocked` are legacy aliases,
# normalized to `running`/`skipped` on read.
STEP_TRANSITIONS = {
    "pending": {"ready", "running", "failed", "skipped"},
    "ready": {"running", "failed", "skipped"},
    "running": {"done", "failed", "skipped"},
    "dispatched": {"done", "failed", "skipped"},
    "failed": {"ready", "skipped"},
    "blocked": {"skipped"},
    "done": set(),
    "skipped": set(),
}
_LEGACY_STEP_STATUS = {"dispatched": "running", "blocked": "skipped"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def looks_multi_goal(text, bots=None, owner_id=None) -> bool:
    """Shape check: does the prompt look like several independent goals?

    Purely structural — any single hit returns True, otherwise False. Single
    goals like “列出当前目录的 txt 文件” must stay False so direct-first
    tasks never pay for a planner call.
    """
    prompt = str(text or "")
    if not prompt.strip():
        return False
    if _PARALLEL_WORDS.search(prompt):
        return True
    if len(_LIST_LINE.findall(prompt)) >= 2:
        return True
    if len(_INLINE_ENUM.findall(prompt)) >= 2:
        return True
    if len(_CIRCLED.findall(prompt)) >= 2:
        return True
    if "@" in prompt or bots:
        mentions = 0
        for bot in bots or []:
            if bot.get("id") == owner_id:
                continue
            name = str(bot.get("name") or "").strip()
            if len(name) >= 2 and name.casefold() in prompt.casefold():
                mentions += 1
        if mentions >= 2:
            return True
    return False


def normalize_fleet_policy(raw) -> dict:
    """Persistable per-Bot fleet controls. Missing fields become defaults."""
    source = raw if isinstance(raw, dict) else {}
    intensity = source.get("intensity") if source.get("intensity") in FLEET_INTENSITIES else "opinions"
    try:
        maximum = int(source.get("maxFamilies") or DEFAULT_FLEET_FAMILIES)
    except (TypeError, ValueError):
        maximum = DEFAULT_FLEET_FAMILIES
    maximum = min(UI_FLEET_FAMILIES, max(1, maximum))
    families = []
    seen = set()
    for item in source.get("families") or []:
        name = str(item or "").strip()
        if not name or name in seen or name == "Other":
            continue
        seen.add(name)
        families.append(name[:40])
        if len(families) >= UI_FLEET_FAMILIES:
            break
    if families:
        maximum = max(maximum, min(UI_FLEET_FAMILIES, len(families)))
    models = {}
    raw_models = source.get("models") if isinstance(source.get("models"), dict) else {}
    for family, preset_id in raw_models.items():
        key = str(family or "").strip()[:40]
        value = str(preset_id or "").strip()[:500]
        if not key or not value or key == "Other":
            continue
        models[key] = value
    enabled = source.get("enabled")
    return {
        "enabled": False if enabled is False else True,
        "intensity": intensity,
        "maxFamilies": maximum,
        "families": families,
        "models": models,
        "hintShown": True if source.get("hintShown") is True else False,
    }


def looks_fleet_review(text) -> bool:
    """True when the user asks this Bot to gather opinions from available models.

    This is not Bot-to-Bot collaboration and does not create permanent workers.
    """
    prompt = str(text or "").strip()
    return bool(prompt) and bool(_FLEET_REVIEW.search(prompt))


def is_split_plan(plan) -> bool:
    return isinstance(plan, dict) and plan.get("mode") in SPLIT_PLAN_MODES


def _preset_family(preset: dict) -> str:
    family = str(preset.get("family") or "").strip()
    if family and family not in {"Other", "其他"}:
        return family
    from .catalog import _model_family
    inferred = _model_family(preset.get("modelName") or preset.get("name") or "")
    return inferred if inferred not in {"Other", "其他"} else "Other"


def _marker_score(text: str, markers: tuple[str, ...]) -> int:
    lowered = str(text or "").lower()
    return sum(1 for marker in markers if marker in lowered)


def _pick_in_family(candidates: list[dict], intensity: str) -> dict:
    def key(preset: dict) -> tuple:
        name = str(preset.get("modelName") or preset.get("name") or "")
        cheap = _marker_score(name, _CHEAP_MARKERS)
        intense = _marker_score(name, _INTENSE_MARKERS)
        if intensity == "intense":
            return (-intense, cheap, name.lower(), str(preset.get("id") or ""))
        return (-cheap, intense, name.lower(), str(preset.get("id") or ""))
    return min(candidates, key=key)


def fleet_presets(presets: list[dict], owner_preset_id=None, policy=None) -> list[dict]:
    """One available Pi preset per family, capped by the Bot's fleet policy."""
    policy = normalize_fleet_policy(policy)
    grouped: dict[str, list[dict]] = {}
    for preset in presets or []:
        if preset.get("harness") != "pi" or not preset.get("available") or not preset.get("id"):
            continue
        family = _preset_family(preset)
        if family == "Other":
            continue
        row = dict(preset)
        row["family"] = family
        grouped.setdefault(family, []).append(row)
    pinned = [name for name in policy["families"] if name in grouped]
    if pinned:
        wanted = pinned[: policy["maxFamilies"]]
    else:
        ranked = []
        for family, candidates in grouped.items():
            pick = _pick_in_family(candidates, policy["intensity"])
            name = str(pick.get("modelName") or pick.get("name") or "")
            cheap = _marker_score(name, _CHEAP_MARKERS)
            intense = _marker_score(name, _INTENSE_MARKERS)
            score = intense if policy["intensity"] == "intense" else cheap
            ranked.append((score, family, pick))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        wanted = [item[1] for item in ranked[: policy["maxFamilies"]]]
    remembered = policy.get("models") if isinstance(policy.get("models"), dict) else {}
    rows = []
    for family in wanted:
        candidates = grouped[family]
        chosen_id = str(remembered.get(family) or "")
        pick = next((item for item in candidates if item.get("id") == chosen_id), None)
        if pick is None and chosen_id:
            pick = next((item for item in candidates if item.get("name") == chosen_id), None)
        if pick is None:
            pick = _pick_in_family(candidates, policy["intensity"])
        rows.append(pick)
    return rows[:MAX_FLEET_STEPS]


def fleet_plan(owner: dict, presets: list[dict], prompt: str, policy=None) -> dict:
    """Same Bot, N model brains, no extra named colleagues."""
    policy = normalize_fleet_policy(policy if policy is not None else owner.get("fleetPolicy"))
    if not policy["enabled"]:
        return direct_plan(owner, FLEET_DISABLED_REASON, "fleet-disabled")
    rows = fleet_presets(presets, owner.get("presetId"), policy)
    if len(rows) < 2:
        return direct_plan(owner, UNDERFILLED_REASON, "fleet-underfilled")
    goal = str(prompt or "").strip()[:8000]
    steps = []
    for index, preset in enumerate(rows, 1):
        family = str(preset.get("family") or "Other")
        model = str(preset.get("modelName") or preset.get("name") or preset["id"])
        label = family if family == model else f"{family} · {model}"
        steps.append({
            "id": f"f{index}",
            "kind": "fleet",
            "botId": owner.get("id"),
            "goal": "",
            "workerPrompt": FLEET_WORKER_PROMPT + goal,
            "dependsOn": [],
            "presetId": str(preset["id"])[:500],
            "label": label[:80],
            "family": family,
            "status": "pending",
            "taskId": None,
            "onFailure": "skip",
        })
    labels = "、".join(step["label"] for step in steps)
    plan = {
        "version": 2,
        "mode": "fleet",
        "ownerBotId": owner.get("id"),
        "reason": f"听 {labels}。",
        "steps": steps,
        "candidates": [],
        "merge": "owner",
        "modelDecision": False,
        "source": "fleet",
        "fleetPolicy": policy,
    }
    if not policy.get("hintShown"):
        plan["notice"] = FLEET_FIRST_HINT.format(n=len(steps))
    return plan


def _strip_verdict_bullet(text: str) -> str:
    return re.sub(r"^[-*•、]+\s*", "", str(text or "").strip()).strip()


def _verdict_items(body: str) -> list[str]:
    chunks = []
    for piece in re.split(r"[\n;；]", str(body or "")):
        item = _strip_verdict_bullet(piece)
        if item and item not in _EMPTY_VERDICT:
            chunks.append(item[:200])
    return chunks[:8]


def parse_fleet_verdict(text) -> dict:
    """Split a merge reply into 分歧 / 风险 / 共识 / 判断. Works on one line too."""
    raw = str(text or "").strip()
    parts = _SECTION_SPLIT.split(raw)
    sections = {"分歧": [], "风险": [], "共识": [], "判断": ""}
    index = 1
    while index + 1 < len(parts):
        heading, body = parts[index], parts[index + 1]
        if heading == "判断":
            sections["判断"] = _strip_verdict_bullet(body.replace("\n", " "))[:800]
        else:
            sections[heading] = _verdict_items(body)
        index += 2
    judgment = sections["判断"].strip()
    if not judgment and not any(sections[key] for key in ("分歧", "风险", "共识")):
        judgment = raw[:400]
    return {
        "disagreements": sections["分歧"][:8],
        "risks": sections["风险"][:8],
        "consensus": sections["共识"][:8],
        "judgment": judgment[:800],
    }


def parse_fleet_take(text) -> dict:
    """Parse a worker's 结论 / 不同意 / 风险, including one-line replies."""
    raw = str(text or "").strip()
    parts = _TAKE_SPLIT.split(raw)
    take = {"conclusion": "", "dissent": "", "risk": ""}
    mapping = {"结论": "conclusion", "不同意": "dissent", "风险": "risk"}
    index = 1
    while index + 1 < len(parts):
        field = mapping.get(parts[index])
        body = _strip_verdict_bullet(parts[index + 1].replace("\n", " "))[:200]
        if field and body and body not in _EMPTY_VERDICT:
            take[field] = body
        index += 2
    return take


def normalize_step_status(status):
    return _LEGACY_STEP_STATUS.get(status, status)


def set_plan_status(plan: dict, status: str, by: str = "system") -> None:
    """Initial status entry; later moves must go through transition_plan."""
    plan["status"] = status
    history = plan.setdefault("history", [])
    history.append({"at": _now(), "from": None, "to": status, "by": str(by)[:80]})
    if len(history) > MAX_PLAN_HISTORY:
        del history[:-MAX_PLAN_HISTORY]


def transition_plan(plan: dict, target: str, by: str = "system") -> bool:
    """Table-driven plan transition; appends to plan.history and caps at 50."""
    current = plan.get("status")
    if current == target:
        return True
    if target not in PLAN_TRANSITIONS.get(current, set()):
        return False
    plan["status"] = target
    history = plan.setdefault("history", [])
    history.append({"at": _now(), "from": current, "to": target, "by": str(by)[:80]})
    if len(history) > MAX_PLAN_HISTORY:
        del history[:-MAX_PLAN_HISTORY]
    return True


def transition_step(step: dict, target: str) -> bool:
    current = normalize_step_status(step.get("status"))
    if current == target:
        step["status"] = target
        return True
    if target not in STEP_TRANSITIONS.get(current, set()):
        return False
    step["status"] = target
    return True


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
                   "dependsOn": [], "presetId": None, "status": "pending", "taskId": None,
                   "onFailure": "retry"}],
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
             "goal": "", "dependsOn": [], "presetId": None, "status": "pending", "taskId": None,
             "onFailure": "retry"}
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


def build_planner_prompt(goal: str, owner: dict, bots: list[dict], memory: str = "", history: dict | None = None) -> str:
    """The one-shot planning request sent on the owner Bot's own preset.

    history maps bot id to that Bot's most recent successful task titles, so
    the planner picks people from evidence rather than from names alone.
    """
    roster = []
    for bot in bots:
        if bot.get("id") == owner.get("id"):
            continue
        titles = [str(title)[:60] for title in (history or {}).get(bot.get("id"), [])][:3]
        recent = f" 近期完成={'；'.join(titles)}" if titles else ""
        roster.append(
            f"- id={bot.get('id')} 名字={bot.get('name')}"
            f" 描述={str(bot.get('description') or '')[:200]}"
            f" 模型={bot.get('model') or ''}{recent}"
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
        # Dependencies may only point to already accepted steps.  Capture
        # the prior set before adding this id so a self-reference cannot pass
        # validation and leave the scheduler waiting forever.
        prior_ids = seen_ids.copy()
        depends_on = raw.get("dependsOn")
        depends_on = [str(dep)[:40] for dep in depends_on if str(dep) in prior_ids] if isinstance(depends_on, list) else []
        seen_ids.add(step_id)
        preset_id = raw.get("presetId")
        preset_id = str(preset_id).strip()[:500] if isinstance(preset_id, str) and preset_id.strip() else None
        on_failure = raw.get("onFailure")
        on_failure = on_failure if on_failure in ON_FAILURE_POLICIES else "retry"
        steps.append({"id": step_id, "kind": "delegate", "botId": target["id"], "goal": goal,
                      "dependsOn": depends_on, "presetId": preset_id, "status": "pending", "taskId": None,
                      "onFailure": on_failure})
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
