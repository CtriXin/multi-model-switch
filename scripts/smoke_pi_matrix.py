#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_core
import mms_launchers


DEFAULT_PROMPT = "Reply with exactly PONG."
DEFAULT_ACCEPT_TEXT = ("PONG", "PONG.")
DEFAULT_TIMEOUT_SEC = 90


def parse_args() -> argparse.Namespace:
    today = datetime.now().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(
        description="Run a live Pi smoke matrix against MMS provider/model routes.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".ai" / "regression-reports" / f"{today}-pi-live-matrix.json"),
        help="Incremental JSON report path.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help="Provider id filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Case-insensitive substring filter for model names. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt sent to Pi.",
    )
    parser.add_argument(
        "--accept-text",
        action="append",
        default=[],
        help="Accepted final assistant text. Repeat to allow more variants.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help="Per-case timeout in seconds.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="Run each provider/model case this many times and aggregate the result.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Stop after N cases (0 means all matched cases).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from an existing JSON report and skip completed cases.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List matched provider/model cases without executing them.",
    )
    parser.add_argument(
        "--include-blocked",
        action="store_true",
        help="Include Pi-blocked provider/model pairs so recovery can be rechecked.",
    )
    parser.add_argument(
        "--blocked-only",
        action="store_true",
        help="Run only currently Pi-blocked provider/model pairs. Implies --include-blocked.",
    )
    return parser.parse_args()


def split_csv(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for part in str(value or "").split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def load_existing_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    results = payload.get("results")
    return list(results) if isinstance(results, list) else []


def summarize_results(results: list[dict]) -> dict[str, int]:
    counts = Counter()
    for row in results:
        counts[str(row.get("status") or "unknown")] += 1
    return dict(sorted(counts.items()))


def write_report(
    path: Path,
    prompt: str,
    results: list[dict],
    *,
    attempts: int,
    include_blocked: bool,
    blocked_only: bool,
) -> None:
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "prompt": prompt,
        "attempts_per_case": attempts,
        "include_blocked": include_blocked,
        "blocked_only": blocked_only,
        "summary": summarize_results(results),
        "results": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def message_text(message: dict) -> str:
    chunks: list[str] = []
    for item in message.get("content") or []:
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "text":
            text = item.get("text")
            if text:
                chunks.append(str(text))
    return "".join(chunks).strip()


def parse_pi_stream(stdout: str) -> tuple[dict, str | None]:
    last_message: dict = {}
    turn_end: dict = {}
    parse_error = None
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type == "message_end":
            message = event.get("message")
            if isinstance(message, dict) and str(message.get("role") or "").strip() == "assistant":
                last_message = message
        elif event_type == "turn_end":
            message = event.get("message")
            if isinstance(message, dict):
                turn_end = message
    return (turn_end or last_message or {}), parse_error


def classify_result(message: dict, rc: int, accepted_text: set[str]) -> str:
    if rc != 0:
        return "launch_fail"
    stop_reason = str(message.get("stopReason") or "").strip().lower()
    error_message = str(message.get("errorMessage") or "").strip()
    content = message_text(message)
    if stop_reason == "error" or error_message:
        return "request_fail"
    if content in accepted_text:
        return "pass"
    if not content:
        return "empty_response"
    return "response_mismatch"


@contextmanager
def temporary_real_home(real_home: str):
    env_keys = ("HOME", "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME")
    old_values = {key: os.environ.get(key) for key in env_keys}
    try:
        for key in env_keys:
            os.environ[key] = real_home
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def temporarily_unblock_case(runtime: dict, model_name: str, *, enabled: bool):
    if not enabled:
        yield
        return
    runtime = runtime if isinstance(runtime, dict) else {}
    provider_id = str(runtime.get("id") or runtime.get("provider_id") or "").strip().lower()
    model_key = mms_launchers._pi_normalize_model_key(model_name)
    original = mms_launchers._pi_model_block_reason

    def _patched(candidate_runtime, candidate_model):
        candidate_runtime = candidate_runtime if isinstance(candidate_runtime, dict) else {}
        candidate_provider = str(
            candidate_runtime.get("id") or candidate_runtime.get("provider_id") or ""
        ).strip().lower()
        candidate_model_key = mms_launchers._pi_normalize_model_key(candidate_model)
        if candidate_provider == provider_id and candidate_model_key == model_key:
            return ""
        return original(candidate_runtime, candidate_model)

    mms_launchers._pi_model_block_reason = _patched
    try:
        yield
    finally:
        mms_launchers._pi_model_block_reason = original


def case_models(
    runtime: dict,
    *,
    include_blocked: bool,
    blocked_only: bool,
) -> list[dict]:
    if not include_blocked and not blocked_only:
        return [
            {
                "model": str(model_name or "").strip(),
                "surface": "exposed",
                "blocked_reason": "",
            }
            for model_name in mms_launchers._pi_exposed_model_names(runtime)
            if str(model_name or "").strip()
        ]

    rows: list[dict] = []
    seen = set()
    for model_name in mms_launchers._pi_runtime_model_names(runtime):
        text = str(model_name or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if not mms_launchers._pi_model_supported(text):
            continue
        blocked_reason = str(mms_launchers._pi_model_block_reason(runtime, text) or "").strip()
        if blocked_reason and not include_blocked:
            continue
        if blocked_only and not blocked_reason:
            continue
        rows.append(
            {
                "model": text,
                "surface": "blocked" if blocked_reason else "exposed",
                "blocked_reason": blocked_reason,
            }
        )
    return rows


def build_cases(
    cfg: dict,
    provider_filters: set[str],
    model_filters: list[str],
    *,
    include_blocked: bool,
    blocked_only: bool,
) -> list[dict]:
    cases: list[dict] = []
    for provider in cfg.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id") or "").strip()
        if not provider_id or not bool(provider.get("enabled")):
            continue
        if provider_filters and provider_id not in provider_filters:
            continue
        runtime = mms_core.resolve_provider_context(cfg, provider_id)
        try:
            model_rows = case_models(
                runtime,
                include_blocked=include_blocked,
                blocked_only=blocked_only,
            )
        except Exception as exc:
            runtime["_pi_probe_error"] = str(exc)
            model_rows = []
        if model_filters:
            model_rows = [
                row for row in model_rows if any(token in row["model"].lower() for token in model_filters)
            ]
        if not model_rows:
            continue
        for row in model_rows:
            cases.append(
                {
                    "provider": provider_id,
                    "runtime": runtime,
                    "model": row["model"],
                    "surface": row["surface"],
                    "blocked_reason": row["blocked_reason"],
                }
            )
    return cases


def run_case(
    provider_id: str,
    runtime: dict,
    model_name: str,
    prompt: str,
    timeout_sec: int,
    accepted_text: set[str],
    blocked_reason: str = "",
) -> dict:
    started = time.monotonic()
    provider_name = str(runtime.get("name") or provider_id).strip() or provider_id
    with tempfile.TemporaryDirectory(prefix=f"mms-pi-live-{provider_id}-") as temp_home:
        try:
            with temporary_real_home(temp_home):
                with temporarily_unblock_case(
                    runtime,
                    model_name,
                    enabled=bool(str(blocked_reason or "").strip()),
                ):
                    exports = mms_launchers.get_export_env("pi", runtime, model_info={"model": model_name})
            env = os.environ.copy()
            env.update(exports)
            if "PATH" in exports:
                env["PATH"] = str(exports["PATH"]).replace("$PATH", os.environ.get("PATH", ""))
            env["HOME"] = temp_home
            env["MMS_REAL_HOME"] = temp_home
            env["REAL_HOME"] = temp_home
            env["ORIGINAL_HOME"] = temp_home
            cmd = [
                exports["MMS_PI_BIN"],
                "--provider",
                exports["MMS_PI_PROVIDER"],
                "--model",
                model_name,
                "--mode",
                "json",
                "--no-session",
                "--no-tools",
                "--no-context-files",
                "--no-skills",
                "--no-prompt-templates",
                "--no-themes",
                "--thinking",
                "off",
                "-p",
                prompt,
            ]
            completed = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "provider": provider_id,
                "provider_name": provider_name,
                "model": model_name,
                "status": "timeout",
                "provider_ref": "",
                "api": "",
                "content": "",
                "stopReason": "timeout",
                "errorMessage": f"Timed out after {timeout_sec}s",
                "rc": None,
                "elapsed_sec": round(time.monotonic() - started, 2),
                "stderr_tail": str(exc.stderr or "")[-400:],
            }
        except Exception as exc:
            return {
                "provider": provider_id,
                "provider_name": provider_name,
                "model": model_name,
                "status": "export_fail",
                "provider_ref": "",
                "api": "",
                "content": "",
                "stopReason": "export_fail",
                "errorMessage": str(exc),
                "rc": None,
                "elapsed_sec": round(time.monotonic() - started, 2),
                "stderr_tail": "",
            }

    message, parse_error = parse_pi_stream(completed.stdout)
    status = classify_result(message, completed.returncode, accepted_text)
    return {
        "provider": provider_id,
        "provider_name": provider_name,
        "model": model_name,
        "status": status,
        "provider_ref": str(message.get("provider") or exports.get("MMS_PI_PROVIDER") or "").strip(),
        "api": str(message.get("api") or "").strip(),
        "content": message_text(message),
        "stopReason": str(message.get("stopReason") or "").strip(),
        "errorMessage": str(message.get("errorMessage") or parse_error or "").strip(),
        "rc": completed.returncode,
        "elapsed_sec": round(time.monotonic() - started, 2),
        "stderr_tail": str(completed.stderr or "")[-400:],
    }


def aggregate_attempts(attempt_results: list[dict]) -> dict:
    if not attempt_results:
        return {}
    statuses = [str(row.get("status") or "unknown") for row in attempt_results]
    pass_count = sum(1 for status in statuses if status == "pass")
    attempt_count = len(attempt_results)
    if pass_count == attempt_count:
        final_status = "pass"
    elif pass_count:
        final_status = "flaky"
    elif len(set(statuses)) == 1:
        final_status = statuses[0]
    else:
        final_status = "mixed_fail"

    chosen = dict(attempt_results[-1])
    if final_status == "pass":
        chosen = dict(attempt_results[-1])
    elif final_status == "flaky":
        first_pass = next((row for row in attempt_results if row.get("status") == "pass"), {})
        first_fail = next((row for row in attempt_results if row.get("status") != "pass"), {})
        if first_pass and not chosen.get("content"):
            chosen["content"] = first_pass.get("content", "")
        if first_fail and not chosen.get("errorMessage"):
            chosen["errorMessage"] = first_fail.get("errorMessage") or first_fail.get("content") or ""

    chosen["status"] = final_status
    chosen["attempt_count"] = attempt_count
    chosen["pass_count"] = pass_count
    chosen["pass_rate"] = round(pass_count / attempt_count, 3) if attempt_count else 0.0
    chosen["attempt_statuses"] = statuses
    chosen["attempts"] = attempt_results
    return chosen


def main() -> int:
    args = parse_args()
    if args.attempts < 1:
        raise SystemExit("--attempts must be >= 1")
    include_blocked = bool(args.include_blocked or args.blocked_only)
    blocked_only = bool(args.blocked_only)
    output_path = Path(args.output).expanduser().resolve()
    provider_filters = {item.strip() for item in split_csv(args.provider)}
    model_filters = [item.lower() for item in split_csv(args.model)]
    accepted_text = set(split_csv(args.accept_text) or DEFAULT_ACCEPT_TEXT)

    cfg = mms_core.load_runtime_config()
    flat_cases = build_cases(
        cfg,
        provider_filters,
        model_filters,
        include_blocked=include_blocked,
        blocked_only=blocked_only,
    )

    if args.max_cases > 0:
        flat_cases = flat_cases[: args.max_cases]

    if args.list_cases:
        for row in flat_cases:
            if include_blocked:
                print(
                    f"{row['provider']}\t{row['model'] or '<no-models>'}\t"
                    f"{row['surface']}\t{row['blocked_reason']}"
                )
            else:
                print(f"{row['provider']}\t{row['model'] or '<no-models>'}")
        return 0

    results = load_existing_results(output_path) if args.resume else []
    seen = {(str(row.get("provider") or ""), str(row.get("model") or "")) for row in results}

    total = len(flat_cases)
    executed = 0
    for index, row in enumerate(flat_cases, start=1):
        provider_id = row["provider"]
        runtime = row["runtime"]
        model_name = row["model"]
        case_key = (provider_id, model_name)
        if args.resume and case_key in seen:
            print(f"[{index}/{total}] skip {provider_id} {model_name or '<no-models>'}")
            continue

        attempt_results = []
        for attempt_index in range(1, args.attempts + 1):
            result = run_case(
                provider_id=provider_id,
                runtime=runtime,
                model_name=model_name,
                prompt=args.prompt,
                timeout_sec=args.timeout,
                accepted_text=accepted_text,
                blocked_reason=row["blocked_reason"],
            )
            result["attempt"] = attempt_index
            attempt_results.append(result)
        result = aggregate_attempts(attempt_results)
        result["surface"] = row["surface"]
        result["blocked_reason"] = row["blocked_reason"]
        results.append(result)
        seen.add(case_key)
        executed += 1
        write_report(
            output_path,
            args.prompt,
            results,
            attempts=args.attempts,
            include_blocked=include_blocked,
            blocked_only=blocked_only,
        )
        attempt_note = ""
        if result.get("attempt_count", 1) > 1:
            attempt_note = f" ({result.get('pass_count', 0)}/{result.get('attempt_count', 1)} pass)"
        print(
            f"[{index}/{total}] {result['status']:<17} "
            f"{provider_id} {model_name or '<no-models>'} "
            f"{result['elapsed_sec']:.2f}s{attempt_note}"
        )
        if result.get("blocked_reason"):
            print(f"  blocked: {result['blocked_reason']}")
        if result.get("errorMessage"):
            print(f"  error: {result['errorMessage']}")
        elif result.get("content") and result["status"] != "pass":
            print(f"  content: {result['content']}")

    summary = summarize_results(results)
    print(json.dumps({"output": str(output_path), "summary": summary, "executed": executed}, ensure_ascii=False))
    failing_statuses = {key for key, value in summary.items() if value and key not in {"pass", "no_models"}}
    return 1 if failing_statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
