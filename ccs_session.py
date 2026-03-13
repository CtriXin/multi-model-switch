"""Session envelope, brief extraction, and continuation prompt assembly."""
import json
import re
from uuid import uuid4


def create_session(task_text, models, mode="chat"):
    return {
        "id": uuid4().hex[:12],
        "mode": mode,
        "models": list(models),
        "round": 0,
        "task": {
            "goal": task_text,
            "invariants": [],
        },
        "branch": {
            "selected_model": None,
            "brief": None,
            "display_text": None,
        },
        "decision_log": [],
    }


def advance_round(session, selected_model, brief, display_text, round_models=None, non_selected_reasons=None):
    """Update session after user selects a branch.

    round_models: the model set active during this round (may differ from
    session["models"] when CHANGE_MODELS_THEN_CONTINUE switches models after
    the user makes a selection).
    """
    current_round = session["round"]
    models_this_round = round_models if round_models is not None else session["models"]

    for model in models_this_round:
        if model == selected_model:
            reason = (non_selected_reasons or {}).get(model, f"选中 {model}")
            session["decision_log"].append({
                "round": current_round,
                "type": "selected",
                "model": model,
                "reason": reason,
            })
        else:
            reason = (non_selected_reasons or {}).get(model, f"未选中 {model}")
            session["decision_log"].append({
                "round": current_round,
                "type": "not_selected",
                "model": model,
                "reason": reason,
            })

    session["branch"]["selected_model"] = selected_model
    session["branch"]["brief"] = brief
    session["branch"]["display_text"] = display_text
    session["round"] += 1
    return session


def build_continuation_prompt(session, new_question):
    """Assemble a state-first continuation prompt. Token count is bounded."""
    parts = [f"## 任务目标\n{session['task']['goal']}"]

    if session["task"]["invariants"]:
        parts.append("## 不可忽略的约束\n" + "\n".join(f"- {c}" for c in session["task"]["invariants"]))

    if session["branch"]["brief"]:
        parts.append("## 当前方向\n" + json.dumps(session["branch"]["brief"], ensure_ascii=False))

    recent_log = session["decision_log"][-3:]
    if recent_log:
        parts.append("## 已做决策\n" + "\n".join(f"- R{d['round']}: {d['reason']}" for d in recent_log))

    parts.append(f"## 新问题\n{new_question}")
    return "\n\n".join(parts)


def extract_brief_footer(raw_text: str) -> tuple:
    """Parse hidden JSON footer from model output.

    Takes the *last* valid ---BRIEF--- block to handle cases where
    the model emits multiple footers (front-bad / back-good).
    Returns (display_text, brief_dict_or_None).
    """
    pattern = re.compile(r"---BRIEF---\s*(.*?)\s*---BRIEF---", re.DOTALL)
    last_valid = None
    last_match = None

    for match in pattern.finditer(raw_text):
        json_str = match.group(1).strip()
        try:
            brief = json.loads(json_str)
            if isinstance(brief, dict):
                last_valid = brief
                last_match = match
        except json.JSONDecodeError:
            pass

    if last_match is None:
        return raw_text, None

    display_text = (raw_text[: last_match.start()] + raw_text[last_match.end():]).strip()
    return display_text, last_valid


FOOTER_INSTRUCTION = """

---
在你的回复末尾，请附加一个 JSON 块，用 ---BRIEF--- 分隔符包裹，格式如下：
---BRIEF---
{"approach": "...", "reasoning": "...", "risks": [...], "key_decisions": [...], "next_step": "..."}
---BRIEF---
仅输出分隔符之间合法的 JSON，不要任何额外解释。"""
