"""Runtime dependency wiring for MMS About/version helpers."""

from __future__ import annotations

from typing import Any, Callable

from mms_commands.tools import (
    about_status_snapshot as build_about_status_snapshot,
    cli_version_status,
    compare_semver_text,
    detect_cli_version,
    fetch_npm_package_latest_version,
    mms_update_status,
    mms_upgrade_shell_command as build_mms_upgrade_shell_command,
    refresh_update_cache_for_about,
    run_about_upgrade as run_about_upgrade_impl,
)


def about_status_snapshot(
    *,
    force_update: bool = False,
    release_version_info: Callable[[], dict[str, Any]],
    load_update_check_cache: Callable[[], dict[str, Any]],
    fetch_latest_semver_tags: Callable[[], list[str]],
    save_update_check_cache: Callable[[dict[str, Any]], Any],
    cli_version_packages: dict[str, str],
    which: Callable[[str], str | None],
    subprocess_run: Callable[..., Any],
    extract_semver_text: Callable[[str], str],
    localize: Callable[[str, str], str],
    now: Callable[[], float],
) -> dict[str, Any]:
    def refresh_cache(*, force_update: bool = False) -> dict[str, Any]:
        return refresh_update_cache_for_about(
            force_update=force_update,
            load_update_check_cache=load_update_check_cache,
            fetch_latest_semver_tags=fetch_latest_semver_tags,
            save_update_check_cache=save_update_check_cache,
            now=now,
        )

    def detect_cli(command_name: str) -> dict[str, Any]:
        return detect_cli_version(
            command_name,
            which=which,
            subprocess_run=subprocess_run,
            extract_semver_text=extract_semver_text,
            localize=localize,
        )

    def fetch_latest_package(package_name: str) -> str:
        return fetch_npm_package_latest_version(
            package_name,
            which=which,
            subprocess_run=subprocess_run,
            extract_semver_text=extract_semver_text,
        )

    def cli_status(*, force_update: bool = False) -> dict[str, Any]:
        return cli_version_status(
            force_update=force_update,
            load_update_check_cache=load_update_check_cache,
            save_update_check_cache=save_update_check_cache,
            cli_version_packages=cli_version_packages,
            detect_cli_version=detect_cli,
            fetch_npm_package_latest_version=fetch_latest_package,
            compare_semver_text=compare_semver_text,
            localize=localize,
            now=now,
        )

    def mms_status(version_info: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
        return mms_update_status(version_info, cache, localize=localize)

    return build_about_status_snapshot(
        force_update=force_update,
        release_version_info=release_version_info,
        refresh_update_cache_for_about=refresh_cache,
        cli_version_status=cli_status,
        mms_update_status=mms_status,
    )


def run_about_upgrade(
    *,
    target: str = "mms",
    include_clis: bool = False,
    ensure_rich: Callable[[], Any],
    cli_upgrade_shell_command: Callable[..., str],
    load_version_meta: Callable[[], dict[str, Any]],
    normalize_language: Callable[[str], str],
    confirm_ask: Callable[..., bool],
    subprocess_run: Callable[..., Any],
    console: Any,
    localize: Callable[[str, str], str],
) -> bool:
    def mms_upgrade_command(*, include_clis: bool = False) -> str:
        return build_mms_upgrade_shell_command(
            include_clis=include_clis,
            preferred_language=load_version_meta().get("preferred_language", ""),
            normalize_language=normalize_language,
        )

    return run_about_upgrade_impl(
        target=target,
        include_clis=include_clis,
        ensure_rich=ensure_rich,
        cli_upgrade_shell_command=cli_upgrade_shell_command,
        mms_upgrade_shell_command=mms_upgrade_command,
        confirm_ask=confirm_ask,
        subprocess_run=subprocess_run,
        console=console,
        localize=localize,
    )


__all__ = ["about_status_snapshot", "run_about_upgrade"]
