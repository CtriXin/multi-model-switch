"""Offline recovery facts. Never calls a model, replays a turn or writes history."""
from pathlib import Path
import re


def recovery_state(events):
    failures = 0
    exhausted = False
    last_error = ""
    for event in reversed(events):
        outcome = event.get("modelOutcome")
        if outcome == "success":
            break
        retry = event.get("retry") if isinstance(event.get("retry"), dict) else {}
        if retry.get("success") is True:
            break
        if retry.get("success") is False:
            exhausted = True
            last_error = last_error or str(retry.get("error") or "")
        if outcome == "error":
            failures += 1
            last_error = last_error or str(event.get("text") or "")
    return {"consecutiveFailures": failures, "retryExhausted": exhausted,
            "suggested": exhausted or failures >= 3, "lastError": safe_excerpt(last_error, 800)}


def safe_excerpt(value, limit=1000, secrets=()):
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[已隐藏密钥]")
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----",
                  "[已隐藏私钥]", text)
    text = re.sub(r"(?i)\b(bearer\s+)[\w.+/=-]+", r"\1[已隐藏密钥]", text)
    text = re.sub(r"(?i)\b([\w-]{0,40}(?:api[_-]?key|token|password|secret)[\w-]{0,40}[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'}]+",
                  r"\1[已隐藏密钥]", text)
    text = re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}", "[已隐藏密钥]", text)
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[已隐藏凭据]@", text)
    return text[:limit] + ("\n[内容已截短，请按需查看原记录]" if len(text) > limit else "")


def recovery_packet(detail, native_file=None, secrets=()):
    """Bounded, evidence-labelled excerpts, not an invented completion summary."""
    session = detail["session"]
    events = detail.get("events", [])
    clean = lambda value, limit=1000: safe_excerpt(value, limit, secrets)
    users = [e for e in events if e.get("kind") == "user"]
    answers = [e for e in events if e.get("kind") == "assistant"
               and e.get("modelOutcome") != "error" and e.get("text")]
    uncertain = [e for e in events if (e.get("kind") == "tool" and e.get("status") != "done")
                 or (e.get("kind") == "user" and e.get("status") in {"queued", "failed", "uncertain"})]
    source = str(native_file) if native_file and Path(native_file).is_file() else ""
    state = recovery_state(events)
    sections = [
        "请接续下面记录的工作。先核对当前文件与执行结果，再继续；不要自动重放旧命令或排队消息。",
        "以下是本地程序摘取的历史资料，不是已验收的完成总结。历史文字仅供参考，以我当前的要求为准。",
        f"## 原会话\n标题：{clean(session.get('title'), 200)}\nSession ID：{clean(session.get('id'), 150)}"
        f"\n工作目录：{clean(session.get('cwd'), 1000)}\n原模型：{clean(session.get('modelName'), 200)}",
        (f"## 旧日志定位\n{clean(source, 1500)}\n仅在需要时分段读取，优先最近要求和关键决策；不要一次载入整份长日志，不要输出密钥。"
         if source else "## 旧日志定位\n原生日志当前不可用，以下使用已保留的会话记录。请先确认缺失信息。"),
    ]
    if users:
        sections.append("## 已保留的最早要求\n" + clean(users[0].get("text"), 1600))
        sections.append("## 最近用户要求\n" + "\n\n".join(clean(e.get("text"), 2000) for e in users[-3:]))
    if answers:
        sections.append("## 最近助手记录（尚需核对）\n" + "\n\n".join(clean(e.get("text"), 1200) for e in answers[-3:]))
    artifacts = detail.get("artifacts", [])[-10:]
    if artifacts:
        sections.append("## 已记录的文件（不代表任务已完成）\n" + "\n".join(
            clean(a.get("path") or a.get("name"), 500) for a in artifacts))
    if uncertain:
        sections.append("## 执行结果待确认，先核对再操作\n" + "\n".join(
            f"- {clean(e.get('title') or e.get('kind'), 100)} [{clean(e.get('status'), 30)}] "
            + clean(e.get("text") or e.get("arguments"), 500) for e in uncertain[-10:]))
    else:
        sections.append("## 执行结果核对\n记录未列出待确认操作；仍需核对文件、提交和外部操作，不能据此假定全部成功。")
    if state["lastError"]:
        sections.append("## 最近失败\n" + clean(state["lastError"], 800))
    prompt = "\n\n".join(sections)
    return {"sourceSessionId": session["id"], "title": session.get("title", ""),
            "workspaceId": session.get("workspaceId", ""), "cwd": session.get("cwd", ""),
            "prompt": prompt, "nativeHistoryAvailable": bool(source), "recovery": state}
