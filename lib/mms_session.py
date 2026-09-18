"""Session envelope, brief extraction, continuation prompt, and persistence."""
import json
import os
import re
from pathlib import Path
from uuid import uuid4

_SESSIONS_DIR = Path.home() / ".mms" / "sessions"


def _normalize_cwd(cwd: str | os.PathLike | None) -> Path | None:
    if not cwd:
        return None
    try:
        return Path(cwd).expanduser().resolve()
    except OSError:
        return Path(cwd).expanduser().absolute()


def _project_sessions_dir(cwd: str | os.PathLike | None) -> Path | None:
    root = _normalize_cwd(cwd)
    if root is None:
        return None
    return root / ".mms" / "sessions"


def _candidate_session_dirs(cwd: str | os.PathLike | None = None) -> list[tuple[str, Path]]:
    dirs: list[tuple[str, Path]] = []
    project_dir = _project_sessions_dir(cwd)
    if project_dir is not None:
        dirs.append(("project", project_dir))
    if project_dir != _SESSIONS_DIR:
        dirs.append(("global", _SESSIONS_DIR))
    return dirs


def _ensure_session_dir(cwd: str | os.PathLike | None = None) -> Path:
    project_dir = _project_sessions_dir(cwd)
    target = project_dir or _SESSIONS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_session(session: dict, cwd: str | os.PathLike | None = None) -> Path:
    """Persist session to <cwd>/.mms/sessions or ~/.mms/sessions/<id>.json."""
    path = _ensure_session_dir(cwd) / f"{session['id']}.json"
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2))
    return path


def load_session(session_id: str, cwd: str | os.PathLike | None = None) -> dict | None:
    """Load a session by id. Checks project-local first, then legacy global."""
    for scope, session_dir in _candidate_session_dirs(cwd):
        path = session_dir / f"{session_id}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                data.setdefault("_session_scope", scope)
                data.setdefault("_session_path", str(path))
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def list_sessions(limit: int = 10, cwd: str | os.PathLike | None = None) -> list[dict]:
    """Return recent sessions, preferring project-local entries then global fallback."""
    files: list[tuple[str, Path, float]] = []
    seen_ids: set[str] = set()
    for scope, session_dir in _candidate_session_dirs(cwd):
        if not session_dir.exists():
            continue
        for path in session_dir.glob("*.json"):
            session_id = path.stem
            if session_id in seen_ids:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            files.append((scope, path, mtime))
            seen_ids.add(session_id)

    files.sort(key=lambda item: item[2], reverse=True)
    results = []
    for scope, path, mtime in files[:limit]:
        try:
            data = json.loads(path.read_text())
            results.append({
                "id": data.get("id", path.stem),
                "mode": data.get("mode", "?"),
                "goal": data.get("task", {}).get("goal", "")[:60],
                "round": data.get("round", 0),
                "mtime": mtime,
                "scope": scope,
                "path": str(path),
            })
        except (json.JSONDecodeError, OSError):
            pass
    return results


def resolve_session_ref(
    session_ref: str,
    cwd: str | os.PathLike | None = None,
    limit: int = 50,
) -> tuple[str | None, str | None]:
    """Resolve exact id / unique prefix / 1-based index to a concrete session id."""
    normalized = str(session_ref or "").strip()
    if not normalized:
        return None, "session 标识不能为空"

    direct = load_session(normalized, cwd=cwd)
    if direct is not None:
        return normalized, None

    sessions = list_sessions(limit=max(limit, 50), cwd=cwd)
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(sessions):
            return sessions[index - 1]["id"], None
        return None, f"找不到序号 {index}，当前仅有 {len(sessions)} 个 session"

    matches = [item for item in sessions if item["id"].startswith(normalized)]
    if len(matches) == 1:
        return matches[0]["id"], None
    if len(matches) > 1:
        ids = ", ".join(item["id"] for item in matches[:5])
        more = " ..." if len(matches) > 5 else ""
        return None, f"前缀 {normalized} 匹配多个 session: {ids}{more}"
    return None, f"找不到 session: {normalized}"


def load_session_ref(
    session_ref: str,
    cwd: str | os.PathLike | None = None,
    limit: int = 50,
) -> tuple[dict | None, str | None, str | None]:
    """Resolve then load a session. Returns (session, resolved_id, error)."""
    resolved_id, error = resolve_session_ref(session_ref, cwd=cwd, limit=limit)
    if not resolved_id:
        return None, None, error
    session = load_session(resolved_id, cwd=cwd)
    if session is None:
        return None, resolved_id, f"session 已解析为 {resolved_id}，但读取失败"
    return session, resolved_id, None


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


_BUDGET_FULL = 3000     # chars; below this → full tier
_BUDGET_COMPACT = 6000  # chars; below this → compact tier; above → minimal


def _estimate_chars(parts: list[str]) -> int:
    return sum(len(p) for p in parts) + len(parts) * 2  # separator overhead


def build_continuation_prompt(session, new_question):
    """Assemble a state-first continuation prompt with token-governor tiers.

    Tiers (estimated chars, ~4 chars per token):
      full    (<3000): task + invariants + full brief JSON + last 5 decisions + question
      compact (3000-6000): task + approach+next_step only + last 3 decisions + question
      minimal (>6000): task + next_step hint only + question
    """
    task = session["task"]["goal"]
    invariants = session["task"]["invariants"]
    brief = session["branch"]["brief"] or {}
    log = session["decision_log"]

    # ── full tier attempt ──
    parts = [f"## 任务目标\n{task}"]
    if invariants:
        parts.append("## 不可忽略的约束\n" + "\n".join(f"- {c}" for c in invariants))
    if brief:
        parts.append("## 当前方向\n" + json.dumps(brief, ensure_ascii=False))
    recent = log[-5:]
    if recent:
        parts.append("## 已做决策\n" + "\n".join(f"- R{d['round']}: {d['reason']}" for d in recent))
    parts.append(f"## 新问题\n{new_question}")

    if _estimate_chars(parts) <= _BUDGET_FULL:
        return "\n\n".join(parts)

    # ── compact tier ──
    compact_brief = {}
    if brief.get("approach"):
        compact_brief["approach"] = brief["approach"]
    if brief.get("next_step"):
        compact_brief["next_step"] = brief["next_step"]

    parts = [f"## 任务目标\n{task}"]
    if compact_brief:
        parts.append("## 当前方向\n" + json.dumps(compact_brief, ensure_ascii=False))
    recent3 = log[-3:]
    if recent3:
        parts.append("## 已做决策\n" + "\n".join(f"- R{d['round']}: {d['reason']}" for d in recent3))
    parts.append(f"## 新问题\n{new_question}")

    if _estimate_chars(parts) <= _BUDGET_COMPACT:
        return "\n\n".join(parts)

    # ── minimal tier ──
    parts = [f"## 任务目标\n{task}"]
    if brief.get("next_step"):
        parts.append(f"## 当前下一步\n{brief['next_step']}")
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
