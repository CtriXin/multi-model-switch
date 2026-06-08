"""Core-facing handlers for standalone MMS command surfaces."""

from __future__ import annotations

import os
from typing import Any, Callable

from mms_commands import tools as command_tools


def build_core_command_handlers(
    *,
    command_name: str,
    script_dir: str,
    load_command_config: Callable[[], dict[str, Any]],
    normalize_positive_seconds: Callable[[Any, int], int],
    ensure_provider_config: Callable[[dict[str, Any]], tuple[dict[str, Any], bool]],
    ensure_account_config: Callable[[dict[str, Any]], tuple[dict[str, Any], bool]],
    normalize_user_config: Callable[[dict[str, Any]], tuple[dict[str, Any], bool]],
    normalize_cache_config: Callable[[dict[str, Any]], tuple[dict[str, Any], bool]],
    save_config: Callable[[dict[str, Any]], None],
    probe_async_refresh_after: float,
    probe_async_min_interval: float,
    load_config: Callable[[], dict[str, Any] | None],
    default_config: Callable[[], dict[str, Any]],
    config_write_target_path: Callable[[], str],
    build_config_guard_snapshot: Callable[..., dict[str, Any]],
    config_snapshot_path: Callable[..., str],
    load_json_snapshot: Callable[[str], dict[str, Any]],
    snapshot_diff_lines: Callable[[dict[str, Any] | None, dict[str, Any]], list[str]],
    iso_now: Callable[[], str],
    snapshot_digest: Callable[[dict[str, Any]], str],
    write_json_snapshot: Callable[[str, dict[str, Any]], None],
    config_root_for_logs: Callable[[], str],
    cli_names: list[str],
    ensure_provider_credentials: Callable[..., dict[str, Any]],
    ensure_models_ready: Callable[..., tuple[dict[str, Any], Any]],
    choose_runtime_source: Callable[..., tuple[dict[str, Any] | None, Any, str]],
    inspect_runtime_exposure: Callable[[str, dict[str, Any]], dict[str, Any]],
    table_cls: Any,
    console: Any,
) -> dict[str, Callable[..., Any]]:
    """Build standalone command handlers with core dependencies injected."""

    def handle_cache_command(argv):
        return command_tools.handle_cache_command(
            argv,
            command_name=command_name,
            load_command_config=load_command_config,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
            probe_async_refresh_after=probe_async_refresh_after,
            probe_async_min_interval=probe_async_min_interval,
            table_cls=table_cls,
            console=console,
        )

    def handle_guard_command(argv, bootstrap_cfg=None):
        return command_tools.handle_guard_command(
            argv,
            command_name=command_name,
            bootstrap_cfg=bootstrap_cfg,
            load_config=load_config,
            default_config=default_config,
            config_write_target_path=config_write_target_path,
            build_config_guard_snapshot=build_config_guard_snapshot,
            config_snapshot_path=config_snapshot_path,
            load_json_snapshot=load_json_snapshot,
            snapshot_diff_lines=snapshot_diff_lines,
            iso_now=iso_now,
            snapshot_digest=snapshot_digest,
            write_json_snapshot=write_json_snapshot,
            table_cls=table_cls,
            console=console,
        )

    def handle_logs_command(argv):
        return command_tools.handle_logs_command(
            argv,
            command_name=command_name,
            config_root=config_root_for_logs(),
            table_cls=table_cls,
            console=console,
        )

    def handle_doctor_command(argv):
        return command_tools.handle_doctor_command(
            argv,
            script_dir=script_dir,
            command_name=command_name,
            console=console,
        )

    def handle_exposure_command(argv):
        return command_tools.handle_exposure_command(
            argv,
            command_name=command_name,
            cli_names=cli_names,
            load_command_config=load_command_config,
            ensure_provider_credentials=ensure_provider_credentials,
            ensure_models_ready=ensure_models_ready,
            choose_runtime_source=choose_runtime_source,
            inspect_runtime_exposure=inspect_runtime_exposure,
            table_cls=table_cls,
            console=console,
        )

    def handle_test_command(argv, subcommand_name="test"):
        return command_tools.handle_test_command(
            argv,
            subcommand_name=subcommand_name,
            script_dir=script_dir,
            command_name=command_name,
            console=console,
        )

    def handle_opencode_smoke_command(argv):
        return command_tools.handle_opencode_smoke_command(
            argv,
            script_dir=script_dir,
            command_name=command_name,
            console=console,
        )

    return {
        "cache": handle_cache_command,
        "guard": handle_guard_command,
        "logs": handle_logs_command,
        "doctor": handle_doctor_command,
        "exposure": handle_exposure_command,
        "test": handle_test_command,
        "opencode_smoke": handle_opencode_smoke_command,
    }


def build_core_command_handlers_from_module(core) -> dict[str, Callable[..., Any]]:
    """Build standalone command handlers from the mms_core module facade."""
    def _inspect_runtime_exposure(cli, runtime):
        from mms_launchers import inspect_runtime_exposure

        return inspect_runtime_exposure(cli, runtime)

    return build_core_command_handlers(
        command_name=core.current_command(),
        script_dir=os.path.join(os.path.dirname(os.path.abspath(core.__file__)), "scripts"),
        load_command_config=core._load_command_config,
        normalize_positive_seconds=core._normalize_positive_seconds,
        ensure_provider_config=core._ensure_provider_config,
        ensure_account_config=core._ensure_account_config,
        normalize_user_config=core._normalize_user_config,
        normalize_cache_config=core._normalize_cache_config,
        save_config=core.save_config,
        probe_async_refresh_after=core._PROBE_ASYNC_REFRESH_AFTER,
        probe_async_min_interval=core._PROBE_ASYNC_MIN_INTERVAL,
        load_config=core.load_config,
        default_config=core._default_config,
        config_write_target_path=core._config_write_target_path,
        build_config_guard_snapshot=core._build_config_guard_snapshot,
        config_snapshot_path=core._config_snapshot_path,
        load_json_snapshot=core._load_json_snapshot,
        snapshot_diff_lines=core._snapshot_diff_lines,
        iso_now=core._iso_now,
        snapshot_digest=core._snapshot_digest,
        write_json_snapshot=core._write_json_snapshot,
        config_root_for_logs=lambda: core._config_guard_root_dir(core._config_write_target_path()),
        cli_names=list(core.CLI_NAMES),
        ensure_provider_credentials=core.ensure_provider_credentials,
        ensure_models_ready=core.ensure_models_ready,
        choose_runtime_source=core._choose_runtime_source,
        inspect_runtime_exposure=_inspect_runtime_exposure,
        table_cls=core.Table,
        console=core.console,
    )


__all__ = ["build_core_command_handlers", "build_core_command_handlers_from_module"]
