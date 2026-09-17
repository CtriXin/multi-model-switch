#!/usr/bin/env python3
"""T5d real-machine check: does a plan step's presetId really apply?

Drives one task-owned Pilot instance through the real HTTP API and real Pi
models. Nothing here writes MMS config: the instance is started separately with
`--state-root <tmp> --config-root ~/.config/mms-next` (read-only) on a port in
61000-62000, and this script only talks to that instance's /api/v1.

Two scenarios, both using the real plan route (a delegate plan whose step
carries `presetId`, replaced and approved through POST /tasks/:id/plan):

A. a Bot that already owns a conversation and has a pending model switch
   (T5c contract: a planned step must not eat it);
B. a Bot whose main conversation must survive the step untouched (memory
   disabled, so the follow-up answer can only come from that conversation).

Usage:
    python3 run-verify.py --port 61731 --out docs/mms-web/design/t5d/base \
      --owner-preset <P> --worker-preset <W1> --override-preset <OV> --pending-preset <W2>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request

PHRASE = "紫色河马在弹钢琴 42"


def call(base, method, path, payload=None, csrf=None, timeout=60):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + "/api/v1/" + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if csrf:
        request.add_header("X-MMS-CSRF", csrf)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()}") from None


def write(out_dir, name, payload):
    path = out_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.name}")
    return payload


def wait_until(fn, seconds, what):
    """Poll fn() until it returns something truthy."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(1.5)
    raise SystemExit(f"timeout waiting for {what}")


def task_by_id(base, csrf, task_id):
    return call(base, "GET", f"tasks/{task_id}", csrf=csrf)


def bot_by_id(base, csrf, bot_id):
    """There is no GET /bots/:id; the list is the read route."""
    return next(b for b in call(base, "GET", "bots", csrf=csrf)["bots"] if b["id"] == bot_id)


def session_by_id(base, csrf, session_id):
    return call(base, "GET", f"sessions/{session_id}", csrf=csrf)


def wait_bool(fn, seconds):
    """Poll fn() for a yes/no answer; False on timeout instead of raising."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(1.0)
    return False


def run_round(base, csrf, bot_id, prompt, seconds=240):
    """One ordinary task for a Bot, waited out to a terminal state."""
    task = call(base, "POST", f"bots/{bot_id}/tasks", {"prompt": prompt}, csrf)

    def finished():
        view = task_by_id(base, csrf, task["id"])
        return view if view["status"] in {"completed", "failed", "cancelled", "interrupted"} else None

    return wait_until(finished, seconds, f"task {task['id']} ({prompt[:24]})")


def run_plan_step(base, csrf, owner, worker, override_preset, goal, seconds=300):
    """Real plan route: propose a delegate plan, replace it naming the model, run it."""
    owner_task = call(base, "POST", f"bots/{owner['id']}/tasks",
                      {"prompt": f"需要协作：让 {worker['name']} 回复一句它准备好了。"}, csrf)
    owner_task_id = owner_task["id"]

    def proposed():
        view = task_by_id(base, csrf, owner_task_id)
        plan = view.get("coordinatorPlan") or {}
        return view if plan.get("mode") == "delegate" and plan.get("status") == "proposed" else None

    planned = wait_until(proposed, seconds, "owner plan proposed")
    replaced = call(base, "POST", f"tasks/{owner_task_id}/plan",
                    {"action": "replace", "plan": {
                        "mode": "delegate", "reason": "T5d 验证：把这一步交给目标 Bot，并指定模型。",
                        "steps": [{"id": "s1", "botId": worker["id"], "goal": goal,
                                   "presetId": override_preset}]}}, csrf)

    def child_done():
        for task in call(base, "GET", "tasks", csrf=csrf)["tasks"]:
            if task.get("parentTaskId") == owner_task_id and task.get("botId") == worker["id"]:
                if task["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                    return task_by_id(base, csrf, task["id"])
        return None

    child = wait_until(child_done, seconds, "plan step child task")
    return {"ownerTask": task_by_id(base, csrf, owner_task_id), "planned": planned,
            "replaced": replaced, "child": child}


def make_worker(base, csrf, name, preset, workspace, memory=True):
    bot = call(base, "POST", "bots",
               {"name": name, "description": "计划步骤的目标 Bot", "workspaceId": workspace,
                "presetId": preset}, csrf)
    if not memory:
        bot = call(base, "POST", f"bots/{bot['id']}", {"memoryEnabled": False}, csrf)
    return bot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rev", default="", help="code revision the instance runs (for the record)")
    parser.add_argument("--owner-preset", required=True)
    parser.add_argument("--worker-preset", required=True, help="the worker Bot's own model (W1)")
    parser.add_argument("--override-preset", required=True, help="the model the plan step names (OV)")
    parser.add_argument("--pending-preset", required=True, help="the worker's pending switch (W2)")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    boot = call(base, "GET", "bootstrap")
    csrf = boot["csrfToken"]
    available = {p["id"]: p for p in boot["presets"] if p.get("harness") == "pi" and p.get("available")}
    workspaces = [w["id"] for w in boot["workspaces"]]
    wanted = [args.owner_preset, args.worker_preset, args.override_preset, args.pending_preset]
    write(out_dir, "00-instance.json", {
        "port": args.port, "appVersion": boot.get("appVersion"), "rev": args.rev,
        "presets": {pid: available[pid]["name"] for pid in wanted if pid in available},
        "missing": [pid for pid in wanted if pid not in available],
    })
    workspace = "default" if "default" in workspaces else workspaces[0]

    owner = call(base, "POST", "bots",
                 {"name": "作者", "description": "计划发起方", "workspaceId": workspace,
                  "presetId": args.owner_preset}, csrf)
    # Keywords planning keeps the plan deterministic and model-free: the models
    # under test are the workers', and the step still goes through the real
    # replace/approve/dispatch route.
    owner = call(base, "POST", f"bots/{owner['id']}",
                 {"orchestrationPolicy": "plan-approve", "planner": "keywords"}, csrf)

    # --- Scenario A: pending switch must survive the step, and is still next-round-only
    pending_bot = make_worker(base, csrf, "执行者甲", args.worker_preset, workspace)
    first = run_round(base, csrf, pending_bot["id"], "记住这句话：紫色河马在弹钢琴 42。只回复“已记住”，不要做别的事。")
    after_first = bot_by_id(base, csrf, pending_bot["id"])
    main_session = after_first["sessionId"]
    if not main_session:
        raise SystemExit("worker has no durable session after the first round")
    call(base, "POST", f"bots/{pending_bot['id']}", {"pendingPresetId": args.pending_preset}, csrf)

    step_a = run_plan_step(base, csrf, owner, pending_bot, args.override_preset,
                           "只回复一句：我按计划指定的模型跑完了这一步。")
    after_step = bot_by_id(base, csrf, pending_bot["id"])
    child = step_a["child"]
    child_session = session_by_id(base, csrf, child["sessionId"]) if child.get("sessionId") else {}
    main_view = session_by_id(base, csrf, main_session)
    write(out_dir, "01-scenario-a-step.json", {
        "ownerTask": step_a["ownerTask"], "planBeforeReplace": step_a["planned"].get("coordinatorPlan"),
        "childTask": child,
        "workerAfterStep": after_step,
        "messages": call(base, "GET", f"tasks/{child['id']}/messages", csrf=csrf)["messages"],
        "stepSession": child_session.get("session"),
        "mainSession": main_view.get("session"),
        "checks": {
            "step_asked_for": child.get("presetIdOverride"),
            "step_effective_model": child.get("model"),
            "step_effective_preset": (child_session.get("session") or {}).get("presetId"),
            "worker_session_unchanged": after_step.get("sessionId") == main_session,
            "step_session_is_not_main_conversation": child.get("sessionId") != main_session,
            "pending_survived": after_step.get("pendingPresetId") == args.pending_preset,
            "reusedSession_field_present": "reusedSession" in child,
        },
    })

    # A1: the ordinary round after it is the one that consumes the pending switch.
    pending_round = run_round(base, csrf, pending_bot["id"], "只回复：收到。")
    after_pending = bot_by_id(base, csrf, pending_bot["id"])
    write(out_dir, "02-scenario-a-next-ordinary-round.json", {
        "task": pending_round, "worker": after_pending,
        "checks": {"model": pending_round.get("model"),
                   "pending_cleared": after_pending.get("pendingPresetId") == "",
                   "new_session": pending_round.get("sessionId") != main_session},
    })

    # --- Scenario B: the Bot's own conversation keeps running on its own model
    continuity_bot = make_worker(base, csrf, "执行者乙", args.worker_preset, workspace, memory=False)
    first_b = run_round(base, csrf, continuity_bot["id"],
                        f"记住这句话：{PHRASE}。只回复“已记住”，不要做别的事。")
    main_b = bot_by_id(base, csrf, continuity_bot["id"])["sessionId"]
    step_b = run_plan_step(base, csrf, owner, continuity_bot, args.override_preset,
                           "只回复一句：这一步由计划指定的模型完成。")
    child_b = step_b["child"]
    child_b_session = session_by_id(base, csrf, child_b["sessionId"]) if child_b.get("sessionId") else {}
    write(out_dir, "03-scenario-b-step.json", {
        "childTask": child_b,
        "workerAfterStep": bot_by_id(base, csrf, continuity_bot["id"]),
        "stepSession": child_b_session.get("session"),
        "mainSession": session_by_id(base, csrf, main_b).get("session"),
        "checks": {"step_asked_for": child_b.get("presetIdOverride"),
                   "step_effective_model": child_b.get("model"),
                   "step_effective_preset": (child_b_session.get("session") or {}).get("presetId"),
                   "worker_session_unchanged": bot_by_id(base, csrf, continuity_bot["id"])["sessionId"] == main_b,
                   "step_session_is_not_main_conversation": child_b.get("sessionId") != main_b},
    })

    # B1: an ordinary round must continue the same conversation, on the same model.
    resume_round = run_round(base, csrf, continuity_bot["id"],
                             "我刚才让你记住的那句话是什么？只回那一句。")
    write(out_dir, "04-scenario-b-main-conversation-continues.json", {
        "task": resume_round, "firstRound": first_b,
        "checks": {"session_is_main_conversation": resume_round.get("sessionId") == main_b,
                   "model": resume_round.get("model"),
                   "answered_from_history": PHRASE in str(resume_round.get("result") or "")},
    })

    # --- Residue: a one-off session must not stay alive after the step
    def is_archived(session_id):
        if not session_id:
            return False
        return bool((session_by_id(base, csrf, session_id).get("session") or {}).get("archived"))

    write(out_dir, "05-session-residue.json", {
        "step_session_a": (session_by_id(base, csrf, child["sessionId"]).get("session") or {})
        if child.get("sessionId") and child.get("sessionId") != main_session else None,
        "step_session_b": (session_by_id(base, csrf, child_b["sessionId"]).get("session") or {})
        if child_b.get("sessionId") and child_b.get("sessionId") != main_b else None,
        "pilot_sidebar": [{k: s.get(k) for k in ("id", "title", "owner", "botId", "archived")}
                          for s in call(base, "GET", "sessions", csrf=csrf)["sessions"]],
        "checks": {
            "step_session_a_archived": wait_bool(lambda: is_archived(child.get("sessionId")), 12)
            if child.get("sessionId") != main_session else False,
            "main_session_a_still_live": not (session_by_id(base, csrf, main_session).get("session") or {}).get("archived"),
            "pilot_sidebar_hides_bot_sessions": call(base, "GET", "sessions", csrf=csrf)["sessions"] == [],
        },
    })
    print("done")


if __name__ == "__main__":
    main()
