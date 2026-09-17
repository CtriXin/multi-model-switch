#!/usr/bin/env python3
"""Fail a pull request only for tests it newly breaks.

The suite is not green on any branch: a set of tests depends on the developer's
real machine (an installed ``pi``, a populated Codex home) and fails wherever
that state is missing. A plain ``pytest`` gate would therefore be red on every
PR and get ignored within a day.

So compare instead of assert: run the suite at the PR's base commit, run it
again at the PR's head, and fail only on tests that pass on the base and fail
on the head. Nothing needs to be allowlisted, and the baseline cannot drift out
of date, because it is recomputed from the base commit every run.

Usage:
    python3 scripts/ci_pytest_regression.py --base <ref> [--head <ref>]

With no ``--head`` the current working tree is used, which is what CI wants:
``actions/checkout`` already places the merge result there.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = "tests"
# Scratch checkouts live here, inside the repo, for the reason in base_worktree().
GATE_DIR_NAME = ".pytest-gate"
# Reruns of a candidate regression, to keep an order-dependent or port-flaky
# test from blocking a PR that did not touch it.
FLAKE_RERUNS = 2


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def _clean_env() -> dict[str, str]:
    """Drop the ambient MMS state a developer shell leaks into the suite."""
    env = dict(os.environ)
    for key in (
        "MMS_CONFIG_ROOT",
        "MMS_CONFIG_DIR",
        "MMS_REAL_HOME",
        "REAL_HOME",
        "ORIGINAL_HOME",
        "MMS_SESSION_HOME",
        "MMS_PI_EXECUTABLE",
        "XDG_CONFIG_HOME",
        "MMS_COMMAND_NAME",
        "MMS_PI_SKILLS_OVERLAY",
        "LANG",
        "LC_ALL",
    ):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MMS_TEST_ALLOW_REAL_CONFIG"] = "0"
    return env


def run_suite(checkout: Path, target: str, report: Path, *, only: list[str] | None = None):
    """Run pytest; return ``(failing node ids, tests collected, failure details)``."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:randomly",
        "-q",
        "--tb=line" if only else "--tb=no",
        f"--junitxml={report}",
    ]
    cmd.extend(only or [target])
    proc = subprocess.run(cmd, cwd=str(checkout), text=True, capture_output=True, env=_clean_env())
    report.with_suffix(".log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if not report.exists():
        # pytest died before writing a report: a collection error, a missing
        # dependency. That is a hard failure, not a comparison input.
        sys.stdout.write(proc.stdout[-8000:])
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"pytest produced no report in {checkout} (exit {proc.returncode})")
    failures, collected, details = parse_report(report, checkout)
    if only and failures:
        sys.stdout.write(proc.stdout[-8000:])
        sys.stderr.write(proc.stderr[-2000:])
    return failures, collected, details


def _node_id(case, checkout: Path) -> str:
    """Rebuild the pytest node id a testcase element came from.

    junit only records a dotted ``classname``: ``tests.test_x`` for a plain
    function, ``tests.test_x.SomeCase`` for a unittest class. Where the module
    path stops and the class name starts is not encoded, so find the split by
    asking the checkout which prefix is a real file.
    """
    name = (case.get("name") or "").strip()
    classname = (case.get("classname") or "").strip()
    if not classname:
        return name
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = Path(*parts[:cut]).with_suffix(".py")
        if (checkout / candidate).is_file():
            return "::".join([candidate.as_posix(), *parts[cut:], name])
    # No matching file: keep the dotted form so the id is still comparable
    # between the two runs, and let the rerun guard refuse to clear it.
    return f"{classname}::{name}"


def parse_report(report: Path, checkout: Path):
    root = ET.parse(report).getroot()
    failures: set[str] = set()
    details: dict[str, str] = {}
    collected = 0
    for case in root.iter("testcase"):
        collected += 1
        node = case.find("failure")
        if node is None:
            node = case.find("error")
        if node is None:
            continue
        node_id = _node_id(case, checkout)
        failures.add(node_id)
        message = (node.get("message") or "").strip()
        body = (node.text or "").strip()
        snippet = "\n".join(part for part in (message, body) if part)
        if snippet:
            details[node_id] = snippet[:1200]
    return failures, collected, details


def base_worktree(base_ref: str) -> Path:
    """Check the base commit out *inside* the repository.

    Not in a temp directory: some tests discover a sibling checkout by walking
    up from their own file, so a base run in /tmp skips what the head run
    executes, and the comparison invents regressions. Keeping both checkouts
    under the same parent keeps that discovery identical.
    """
    checkout = REPO_ROOT / GATE_DIR_NAME / "base"
    proc = _run(["git", "worktree", "add", "--detach", str(checkout), base_ref], cwd=REPO_ROOT)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"could not check out base ref {base_ref!r}")
    return checkout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=os.environ.get("PR_BASE_SHA") or "",
        help="Commit the PR branches from. Defaults to $PR_BASE_SHA.",
    )
    parser.add_argument("--head", default="", help="Commit to test. Defaults to the working tree.")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Test path to run. Defaults to tests/.")
    parser.add_argument("--report-dir", default="", help="Keep JUnit XML and captured output here for audit.")
    args = parser.parse_args()

    if not args.base.strip():
        print("No base commit given; nothing to compare against.", file=sys.stderr)
        return 2

    workdir = Path(args.report_dir).resolve() if args.report_dir else Path(tempfile.mkdtemp(prefix="mms-pytest-gate-"))
    workdir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        head_checkout = REPO_ROOT
        if args.head.strip():
            head_checkout = REPO_ROOT / GATE_DIR_NAME / "head"
            proc = _run(["git", "worktree", "add", "--detach", str(head_checkout), args.head], cwd=REPO_ROOT)
            if proc.returncode != 0:
                sys.stderr.write(proc.stdout + proc.stderr)
                raise SystemExit(f"could not check out head ref {args.head!r}")
            created.append(head_checkout)

        print(f"== base {args.base} ==", flush=True)
        base_checkout = base_worktree(args.base)
        created.append(base_checkout)
        base_failures, base_collected, _base_details = run_suite(
            base_checkout, args.target, workdir / "base.xml"
        )
        print(f"base: {len(base_failures)} failing of {base_collected}", flush=True)

        print(f"== head {args.head or 'working tree'} ==", flush=True)
        head_failures, head_collected, head_details = run_suite(
            head_checkout, args.target, workdir / "head.xml"
        )
        print(f"head: {len(head_failures)} failing of {head_collected}", flush=True)

        candidates = sorted(head_failures - base_failures)
        details = dict(head_details)
        if candidates:
            print(f"\n{len(candidates)} test(s) newly failing; rerunning to rule out flakes", flush=True)
            for attempt in range(FLAKE_RERUNS):
                if not candidates:
                    break
                still, rerun_collected, rerun_details = run_suite(
                    head_checkout,
                    args.target,
                    workdir / f"rerun{attempt}.xml",
                    only=list(candidates),
                )
                details.update(rerun_details)
                if rerun_collected != len(candidates):
                    # The rerun did not select what we asked for, so a pass here
                    # proves nothing. Keep the candidates and report them.
                    print(
                        f"  rerun selected {rerun_collected} of {len(candidates)} tests; "
                        "treating the failures as real",
                        flush=True,
                    )
                    break
                candidates = [item for item in candidates if item in still]

        fixed = sorted(base_failures - head_failures)
        if fixed:
            print(f"\nRepaired by this PR ({len(fixed)}):")
            for item in fixed:
                print(f"  + {item}")

        if candidates:
            print(f"\nBroken by this PR ({len(candidates)}):")
            for item in candidates:
                print(f"  - {item}")
                snippet = details.get(item) or ""
                for line in snippet.splitlines()[:16]:
                    print(f"      {line}")
            print(
                "\nThese pass at the base commit and fail here. Fix them, or say in the PR "
                "why the old expectation was wrong and update it."
            )
            return 1

        print("\nNo test that passes on the base commit fails here.")
        return 0
    finally:
        for checkout in created:
            _run(["git", "worktree", "remove", "--force", str(checkout)], cwd=REPO_ROOT)
        shutil.rmtree(REPO_ROOT / GATE_DIR_NAME, ignore_errors=True)
        if not args.report_dir:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
