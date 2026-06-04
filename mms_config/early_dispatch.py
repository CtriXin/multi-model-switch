"""Early read-only config command dispatch.

These commands must run before config loading because they are status/plan
surfaces for selecting or validating the config root itself.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from mms_config import command_guards, display_commands


def dispatch_early_config_command(
    argv: Sequence[object],
    *,
    command_name: str,
    primary_config_dir: str,
    config_root_status: Callable[[], dict[str, Any]],
    console: Any,
) -> tuple[bool, int]:
    """Handle early read-only config commands.

    Returns ``(handled, exit_code)``. ``handled`` means the caller should stop
    normal startup; a non-zero ``exit_code`` should be raised as SystemExit.
    """
    args = list(argv)
    json_output = "--json" in args[2:]

    if command_guards.is_config_root_status_request(args):
        display_commands.display_config_root(
            json_output=json_output,
            config_root_status=config_root_status,
            console=console,
        )
        return True, 0

    if command_guards.is_config_model_source_status_request(args):
        display_commands.display_model_source_status(
            json_output=json_output,
            config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, 0

    if command_guards.is_config_consumer_bundle_status_request(args):
        code = display_commands.display_consumer_bundle_status(
            json_output=json_output,
            strict_exit="--no-strict-exit" not in args[2:],
            config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, int(code or 0)

    if command_guards.is_config_registry_v2_save_plan_request(args):
        display_commands.display_registry_v2_save_plan(
            json_output=json_output,
            config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, 0

    if command_guards.is_config_preview_check_request(args):
        code = display_commands.display_preview_check(
            json_output=json_output,
            strict_exit="--no-strict-exit" not in args[2:],
            config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, int(code or 0)

    if command_guards.is_config_v2_promotion_plan_request(args):
        code = display_commands.display_config_v2_promotion_plan(
            json_output=json_output,
            strict_exit="--strict-exit" in args[2:],
            preview_config_dir=primary_config_dir,
            command_name=f"{command_name} config promote-plan",
        )
        return True, int(code or 0)

    if command_guards.is_config_v2_release_readiness_request(args):
        code = display_commands.display_config_v2_release_readiness(
            args[2:],
            config_root_status=config_root_status,
            primary_config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, int(code or 0)

    if command_guards.is_config_v2_migration_plan_request(args):
        code = display_commands.display_config_v2_migration_plan(
            args[2:],
            config_root_status=config_root_status,
            primary_config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, int(code or 0)

    if command_guards.is_config_registry_v2_apply_plan_request(args):
        from mms_registry.cli import handle_registry_command

        registry_args = ["apply-plan", "--config-dir", primary_config_dir] + list(args[2:])
        code = handle_registry_command(registry_args, command_name=f"{command_name} config")
        return True, int(code or 0)

    if command_guards.is_config_preview_doctor_request(args):
        code = display_commands.display_preview_doctor(
            json_output=json_output,
            strict_exit="--strict-exit" in args[2:],
            config_dir=primary_config_dir,
            command_name=command_name,
        )
        return True, int(code or 0)

    return False, 0


__all__ = ["dispatch_early_config_command"]
