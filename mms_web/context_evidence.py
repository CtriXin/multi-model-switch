"""Bounded Pi provenance. Availability and reading are separate observations."""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

_HASH = re.compile(r"[a-f0-9]{64}\Z")


def prompt_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_evidence(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        return None
    result = {"version": 1, "available": value.get("available") is True,
              "truncated": value.get("truncated") is True, "rules": [], "skills": []}
    for key in ("promptSha256", "sourcePromptSha256", "systemPromptSha256"):
        item = value.get(key)
        if isinstance(item, str) and _HASH.fullmatch(item):
            result[key] = item
    if "promptSha256" not in result:
        return None
    for key in ("rules", "skills"):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        result["truncated"] |= len(rows) > 200
        for row in rows[:200]:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                continue
            item = {k: row[k][:2048] for k in ("path", "name", "source") if isinstance(row.get(k), str)}
            if isinstance(row.get("sha256"), str) and _HASH.fullmatch(row["sha256"]):
                item["sha256"] = row["sha256"]
            if key == "rules":
                item["state"] = "loaded"
            else:
                item["state"] = "available"
                item["listed"] = row.get("listed") is True
                if row.get("invoked") is True and result.get("sourcePromptSha256"):
                    item.update(state="loaded", invoked=True, proof="skill_command")
            result[key].append(item)
    return result


def consume_prompt(session, prompt):
    """Bind the consumed native prompt to an exact, as-yet unconsumed Web turn."""
    digest = prompt_hash(prompt)
    evidence = session.meta.get("contextEvidence", {})
    source_digest = evidence.get("sourcePromptSha256") if evidence.get("promptSha256") == digest else digest
    source_digest = source_digest or digest
    event = next((e for e in session.events if e.get("kind") == "user"
                  and e.get("contextUsage", {}).get("promptSha256") == source_digest
                  and not e["contextUsage"].get("consumed")
                  and e.get("status") != "cancelled" and e["contextUsage"].get("state") != "failed"), None)
    session.meta.pop("activeContextEvent", None)
    if not event:
        return None
    usage = event["contextUsage"]
    usage["consumed"] = True
    if evidence:
        usage["native"] = copy.deepcopy(evidence)
    for item in usage.get("items", []):
        if item.get("kind") in {"skill", "material", "selection"}:
            item["loadState"] = "loaded"
        else:
            item["loadState"] = "referenced"
    session.meta["activeContextEvent"] = event["id"]
    return event["id"]


def observe_read(session, event):
    """Use actual read tool IDs and results; never infer usage from the reply."""
    if event.get("kind") != "tool" or event.get("title") != "read":
        return
    raw = event.get("arguments", {}).get("path")
    if not isinstance(raw, str):
        return
    owner = event.get("contextEventId")
    if not owner:
        owner = session.meta.get("activeContextEvent")
        if owner:
            event["contextEventId"] = owner
    usage = session.event_index.get(owner, {}).get("contextUsage", {})
    cwd = session.meta.get("cwd") or "."
    def canonical(path):
        return str((Path(cwd) / path).resolve())
    try:
        path = canonical(raw)
    except (OSError, ValueError, RuntimeError):
        return
    items = usage.get("items", []) + usage.get("native", {}).get("skills", [])
    for item in items:
        source = item.get("filePath") or item.get("path")
        if not isinstance(source, str):
            continue
        try:
            if canonical(source) != path:
                continue
        except (OSError, ValueError, RuntimeError):
            continue
        state = {"done": "loaded", "error": "failed"}.get(event.get("status"), "loading")
        item.update(loadState=state, invoked=True, proof="read_tool", toolEventId=event["id"])
        # A bounded read may be partial. Do not claim the complete skill was loaded.
        item["partial"] = True

