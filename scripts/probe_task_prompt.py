#!/usr/bin/env python3
"""Send the tunnel task to real models and report what each one's first turn did.

The task in the remote-access settings row tells the agent to ask two
questions and stop. Whether a model actually does that is not something a
string assertion can answer, so this asks them. It launches one session per
model through a running Pilot, reads the first assistant turn, and reports
whether the two questions were asked and whether any tool ran.

It costs money and needs configured channels, so it is never part of the test
suite. `tests/frontend/tunnel-task.test.ts` holds the prompt's shape in place
for free; this is for when the wording changes and you want to know whether
the behaviour changed with it.

    python3 scripts/probe_task_prompt.py --port 8765
    python3 scripts/probe_task_prompt.py --port 8765 --model glm-5.3 --model k3

Plan mode stays off on purpose: restraint has to come from the prompt, not
from the harness. A model that decides to act therefore can, which is the
point of measuring it. Run it against a Pilot you are willing to have a model
poke at, not one pointed at work you care about.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK_MODULE = ROOT / "apps/mms-web/src/tunnel-task.ts"
# What a correct first turn looks like: both questions, and no move to act.
ASKS = (re.compile(r"域名"), re.compile(r"服务器|Tailscale|虚拟网"))
UPSTREAM = re.compile(r"^\s*(4\d\d|5\d\d)[\s:]")


def rendered_task(port: int) -> str:
    """The exact text the button sends, read from the module the app uses."""
    body = TASK_MODULE.read_text(encoding="utf-8").replace("export function", "function")
    body = body.replace("(port: number)", "(port)")
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(body + f"\nprocess.stdout.write(tunnelTask({port}));\n")
        script = handle.name
    try:
        done = subprocess.run(["node", script], capture_output=True, text=True,
                              timeout=30, check=True)
        return done.stdout
    finally:
        os.unlink(script)


class Pilot:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/") + "/api/v1"
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        boot = self.get("/bootstrap")
        self.csrf = boot["csrfToken"]
        self.workspace = (boot["workspaces"] or [{}])[0].get("id", "")
        self.presets = [p for p in boot["presets"] if p.get("available")]

    def get(self, path: str):
        return json.load(self.opener.open(self.base + path))

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-MMS-CSRF": self.csrf})
        return json.load(self.opener.open(request))

    def preset_for(self, wanted: str) -> str:
        for preset in self.presets:
            if preset["id"] == wanted or preset["name"] == wanted:
                return preset["id"]
        return ""


def probe(pilot: Pilot, preset: str, prompt: str, index: int, wait: int) -> dict:
    detail = pilot.post("/sessions", {
        "requestId": f"probe-{index}-{int(time.time())}",
        "workspaceId": pilot.workspace, "presetId": preset,
        "title": f"提示词检验 {preset}", "prompt": prompt, "planMode": False})
    session = detail["session"]["id"]
    current = detail
    for _ in range(wait):
        time.sleep(2)
        current = pilot.get(f"/sessions/{session}")
        if current["session"]["state"] in ("idle", "completed", "stopped", "error"):
            break
    replies = [e for e in current["events"]
               if e["kind"] == "assistant" and (e.get("text") or "").strip()]
    tools = [e for e in current["events"] if e["kind"] == "tool"]
    first = replies[0]["text"].strip() if replies else ""
    return {
        "session": session,
        "model": current["session"].get("modelName") or preset,
        "tools": len(tools),
        "upstream_error": bool(UPSTREAM.match(first)),
        "asked": all(pattern.search(first) for pattern in ASKS),
        "text": first,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="", help="Pilot base URL")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", action="append", default=[], metavar="NAME",
                        help="Model name or preset id. Repeatable. Default: all "
                             "available presets, one per model name.")
    parser.add_argument("--wait", type=int, default=90,
                        help="Polls of two seconds to allow per session")
    parser.add_argument("--archive", action="store_true",
                        help="Archive the probe sessions when done")
    args = parser.parse_args(argv)

    base = args.base or f"http://127.0.0.1:{args.port}"
    try:
        pilot = Pilot(base)
    except (urllib.error.URLError, OSError) as error:
        print(f"no Pilot at {base}: {error}", file=sys.stderr)
        return 2
    prompt = rendered_task(args.port)

    wanted = args.model or sorted({p["name"] for p in pilot.presets})
    results = []
    for index, name in enumerate(wanted):
        preset = pilot.preset_for(name)
        if not preset:
            print(f"{name:<30} no available preset")
            continue
        try:
            result = probe(pilot, preset, prompt, index, args.wait)
        except Exception as error:  # a channel can fail in many ways
            print(f"{name:<30} launch failed: {error}")
            continue
        results.append(result)
        if result["upstream_error"]:
            verdict = "channel error"
        elif result["asked"] and result["tools"] == 0:
            verdict = "asked, ran nothing"
        elif result["asked"]:
            verdict = f"asked BUT ran {result['tools']} tool(s)"
        else:
            verdict = "DID NOT ASK"
        print(f"{name:<30} {verdict}")
        if not result["asked"] and not result["upstream_error"]:
            for line in result["text"].splitlines()[:8]:
                print(f"    {line}")
        if args.archive:
            try:
                pilot.post(f"/sessions/{result['session']}/manage",
                           {"archived": True,
                            "requestId": f"probe-tidy-{index}-{int(time.time())}"})
            except Exception:
                pass

    answered = [r for r in results if not r["upstream_error"]]
    good = [r for r in answered if r["asked"] and r["tools"] == 0]
    print(f"\n{len(good)}/{len(answered)} answered correctly "
          f"({len(results) - len(answered)} channel errors)")
    return 0 if answered and len(good) == len(answered) else 1


if __name__ == "__main__":
    raise SystemExit(main())
