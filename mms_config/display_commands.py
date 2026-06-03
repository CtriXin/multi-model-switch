"""Read-only Config/Registry command display wrappers."""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable


def _json_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def display_config_root(
    *,
    json_output: bool = False,
    config_root_status: Callable[[], dict[str, Any]],
    console: Any,
) -> None:
    status = config_root_status()
    if json_output:
        print(json.dumps(status, ensure_ascii=False, sort_keys=True))
        return
    console.print("[bold]MMS config root[/bold]")
    console.print(f"  [cyan]command[/cyan] = {status['command']}")
    console.print(f"  [cyan]mode[/cyan] = {status['mode']}")
    console.print(f"  [cyan]root_source[/cyan] = {status['root_source']}")
    console.print(f"  [cyan]config_root[/cyan] = {status['config_root']}")
    console.print(f"  [cyan]config_path[/cyan] = {status['config_path']}")
    console.print(f"  [cyan]credentials_path[/cyan] = {status['credentials_path']}")
    console.print(f"  [cyan]usage_path[/cyan] = {status['usage_path']}")
    if status["mode"] == "preview":
        console.print("[yellow]Preview root:[/yellow] fail closed inside this root; no silent fallback to stable credentials/OAuth.")
    else:
        console.print("[dim]Stable root: current default MMS behavior.[/dim]")


def display_model_source_status(*, json_output: bool = False, config_dir: str, command_name: str) -> None:
    from mms_registry.cli import _print_model_source_status, model_source_status

    status = model_source_status(config_dir=config_dir, command_name=f"{command_name} config source")
    if json_output:
        _json_print(status)
    else:
        _print_model_source_status(status)


def display_consumer_bundle_status(
    *,
    json_output: bool = False,
    strict_exit: bool = True,
    config_dir: str,
    command_name: str,
) -> int:
    from mms_registry.cli import _print_consumer_bundle_status, consumer_bundle_status

    summary = consumer_bundle_status(config_dir=config_dir, command_name=f"{command_name} config bundle")
    if json_output:
        _json_print(summary)
    else:
        _print_consumer_bundle_status(summary)
    return 0 if not strict_exit or summary.get("verified") is True else 2


def display_registry_v2_save_plan(*, json_output: bool = False, config_dir: str, command_name: str) -> None:
    from mms_registry.cli import _print_registry_v2_save_plan, registry_v2_save_plan

    plan = registry_v2_save_plan(config_dir=config_dir, command_name=f"{command_name} config save-plan")
    if json_output:
        _json_print(plan)
    else:
        _print_registry_v2_save_plan(plan)


def display_preview_doctor(
    *,
    json_output: bool = False,
    strict_exit: bool = False,
    config_dir: str,
    command_name: str,
) -> int:
    from mms_registry.cli import _print_preview_doctor, preview_doctor

    summary = preview_doctor(config_dir=config_dir, command_name=f"{command_name} config doctor")
    if json_output:
        _json_print(summary)
    else:
        _print_preview_doctor(summary)
    return 0 if not strict_exit or summary.get("ready") is True else 2


def display_preview_check(
    *,
    json_output: bool = False,
    strict_exit: bool = True,
    config_dir: str,
    command_name: str,
) -> int:
    from mms_registry.cli import _print_preview_check, preview_check

    summary = preview_check(config_dir=config_dir, command_name=f"{command_name} config check")
    if json_output:
        _json_print(summary)
    else:
        _print_preview_check(summary)
    return 0 if not strict_exit or summary.get("ready") is True else 2


def display_config_v2_promotion_plan(
    *,
    json_output: bool = False,
    strict_exit: bool = False,
    preview_config_dir: str | None = None,
    stable_config_dir: str | None = None,
    command_name: str,
) -> int:
    from mms_registry.cli import _print_config_v2_promotion_plan, config_v2_promotion_plan

    summary = config_v2_promotion_plan(
        preview_config_dir=preview_config_dir,
        stable_config_dir=stable_config_dir,
        command_name=command_name,
    )
    if json_output:
        _json_print(summary)
    else:
        _print_config_v2_promotion_plan(summary)
    return 0 if not strict_exit or summary.get("ready_for_human_review") is True else 2


def _default_preview_stable_roots(status: dict[str, Any], primary_config_dir: str) -> tuple[str, str]:
    default_preview_root = (
        status.get("config_root")
        if status.get("mode") == "preview"
        else status.get("preview_root")
    ) or primary_config_dir
    default_stable_root = status.get("stable_root") or primary_config_dir
    return default_preview_root, default_stable_root


def display_config_v2_migration_plan(
    args_rest: list[str],
    *,
    config_root_status: Callable[[], dict[str, Any]],
    primary_config_dir: str,
    command_name: str,
) -> int:
    status = config_root_status()
    default_preview_root, default_stable_root = _default_preview_stable_roots(status, primary_config_dir)
    parser = argparse.ArgumentParser(
        prog=f"{command_name} migrate config-v2",
        description="Read-only config v2 migration/promotion plan; stops at the human gate.",
    )
    parser.add_argument("--preview-config-dir", "--config-dir", default=default_preview_root)
    parser.add_argument("--stable-config-dir", default=default_stable_root)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict-exit", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reserved; this command remains read-only and reports apply_enabled=false.",
    )
    args = parser.parse_args(args_rest)
    return display_config_v2_promotion_plan(
        json_output=bool(args.json),
        strict_exit=bool(args.strict_exit),
        preview_config_dir=args.preview_config_dir,
        stable_config_dir=args.stable_config_dir,
        command_name=f"{command_name} migrate config-v2",
    )


def display_config_v2_release_readiness(
    args_rest: list[str],
    *,
    config_root_status: Callable[[], dict[str, Any]],
    primary_config_dir: str,
    command_name: str,
) -> int:
    status = config_root_status()
    default_preview_root, default_stable_root = _default_preview_stable_roots(status, primary_config_dir)
    parser = argparse.ArgumentParser(
        prog=f"{command_name} config release-readiness",
        description="Read-only config v2 / 4.0 readiness audit; stops at the stable human gate.",
    )
    parser.add_argument("--preview-config-dir", "--config-dir", default=default_preview_root)
    parser.add_argument("--stable-config-dir", default=default_stable_root)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(args_rest)

    from mms_registry.cli import _print_config_v2_release_readiness, config_v2_release_readiness

    summary = config_v2_release_readiness(
        preview_config_dir=args.preview_config_dir,
        stable_config_dir=args.stable_config_dir,
        command_name=f"{command_name} config release-readiness",
    )
    if args.json:
        _json_print(summary)
    else:
        _print_config_v2_release_readiness(summary)
    return 0 if not bool(args.strict_exit) or summary.get("ready_for_human_gate") is True else 2


__all__ = [
    "display_config_root",
    "display_model_source_status",
    "display_consumer_bundle_status",
    "display_registry_v2_save_plan",
    "display_preview_doctor",
    "display_preview_check",
    "display_config_v2_promotion_plan",
    "display_config_v2_migration_plan",
    "display_config_v2_release_readiness",
]
