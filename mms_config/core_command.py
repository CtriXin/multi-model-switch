"""Core-facing adapters for the legacy `config` command surface."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from mms_commands import tools as command_tools


def build_config_command_adapters(
    *,
    command_name: str,
    config_path: str,
    preferences_doc_path: str,
    preference_paths: list[str],
    preferences_example_toml: str,
    default_provider_id: str,
    default_priority: int,
    resolve_provider_context: Callable[..., dict[str, Any]],
    provider_openai_base_url: Callable[[dict[str, Any]], str],
    provider_anthropic_base_url: Callable[[dict[str, Any]], str],
    probe_account_status: Callable[[dict[str, Any]], dict[str, Any]],
    load_usage_stats: Callable[[], dict[str, Any]],
    usage_path: str,
    table_cls: Any,
    top_source_companies: list[dict[str, Any]],
    default_adapter_policy: dict[str, Any],
    mask_key: Callable[[str], str],
    active_credentials_path: Callable[[], str],
    active_usage_path: Callable[[], str],
    probe_async_refresh_after: float,
    probe_async_min_interval: float,
    existing_override_paths: Callable[[], list[str]],
    override_paths: list[str],
    existing_preferences_paths: Callable[[], list[str]],
    coerce_config_value: Callable[[str, str], Any],
    normalize_config_sections: Callable[[dict[str, Any]], dict[str, Any]],
    save_config: Callable[[dict[str, Any]], None],
    validate_config: Callable[[dict[str, Any]], list[str]],
    console: Any,
) -> dict[str, Callable[..., Any]]:
    """Build callables injected into `mms_commands.tools.handle_config`."""

    def display_providers(cfg):
        return command_tools.display_providers(
            cfg,
            default_provider_id=default_provider_id,
            default_priority=default_priority,
            resolve_provider_context=resolve_provider_context,
            provider_openai_base_url=provider_openai_base_url,
            provider_anthropic_base_url=provider_anthropic_base_url,
            command_name=command_name,
            table_cls=table_cls,
            console=console,
        )

    def display_accounts(cfg):
        return command_tools.display_accounts(
            cfg,
            default_priority=default_priority,
            probe_account_status=probe_account_status,
            command_name=command_name,
            table_cls=table_cls,
            console=console,
        )

    def display_config(cfg, prefix="", depth=0):
        return command_tools.display_config(
            cfg,
            prefix=prefix,
            depth=depth,
            resolve_provider_context=resolve_provider_context,
            provider_openai_base_url=provider_openai_base_url,
            provider_anthropic_base_url=provider_anthropic_base_url,
            mask_key=mask_key,
            active_credentials_path=active_credentials_path,
            active_usage_path=active_usage_path,
            display_providers=display_providers,
            display_accounts=display_accounts,
            probe_async_refresh_after=probe_async_refresh_after,
            probe_async_min_interval=probe_async_min_interval,
            existing_override_paths=existing_override_paths,
            override_paths=override_paths,
            existing_preferences_paths=existing_preferences_paths,
            preference_paths=preference_paths,
            command_name=command_name,
            console=console,
        )

    def display_preferences_path():
        return command_tools.display_preferences_path(
            preference_paths=preference_paths,
            preferences_doc_path=preferences_doc_path,
            console=console,
        )

    def display_preferences_example():
        return command_tools.display_preferences_example(
            preferences_example_toml=preferences_example_toml,
            console=console,
        )

    def display_human_gate_help():
        return command_tools.display_human_gate_help(
            command_name=command_name,
            preferences_doc_path=preferences_doc_path,
            console=console,
        )

    def display_preferences_help():
        return command_tools.display_preferences_help(
            command_name=command_name,
            preference_paths=preference_paths,
            preferences_doc_path=preferences_doc_path,
            console=console,
        )

    def display_usage_stats():
        return command_tools.display_usage_stats(
            load_usage_stats=load_usage_stats,
            usage_path=usage_path,
            table_cls=table_cls,
            console=console,
        )

    def display_adapter_registry():
        return command_tools.display_adapter_registry(
            top_source_companies=top_source_companies,
            default_adapter_policy=default_adapter_policy,
            command_name=command_name,
            table_cls=table_cls,
            console=console,
        )

    def handle_config_get(cfg, args_rest):
        return command_tools.handle_config_get(cfg, args_rest, command_name=command_name, console=console)

    def handle_config_set(cfg, args_rest):
        return command_tools.handle_config_set(
            cfg,
            args_rest,
            command_name=command_name,
            coerce_config_value=coerce_config_value,
            normalize_config_sections=normalize_config_sections,
            save_config=save_config,
            console=console,
        )

    def handle_config_unset(cfg, args_rest):
        return command_tools.handle_config_unset(
            cfg,
            args_rest,
            command_name=command_name,
            normalize_config_sections=normalize_config_sections,
            save_config=save_config,
            console=console,
        )

    def handle_config_validate(cfg):
        return command_tools.handle_config_validate(cfg, validate_config=validate_config, console=console)

    return {
        "display_config": display_config,
        "handle_config_file": partial(command_tools.handle_config_file, config_path=config_path, console=console),
        "handle_config_validate": handle_config_validate,
        "display_preferences_help": display_preferences_help,
        "display_preferences_path": display_preferences_path,
        "display_preferences_example": display_preferences_example,
        "display_human_gate_help": display_human_gate_help,
        "handle_config_get": handle_config_get,
        "handle_config_set": handle_config_set,
        "handle_config_unset": handle_config_unset,
        "display_adapter_registry": display_adapter_registry,
        "display_providers": display_providers,
        "display_accounts": display_accounts,
        "display_usage_stats": display_usage_stats,
    }


def handle_core_config_from_module(core, cfg, args_rest):
    """Dispatch the legacy config command while preserving mms_core monkeypatch hooks."""
    def _run_config_web(*args, **kwargs):
        from mms_config.web import run_config_web

        return run_config_web(*args, **kwargs)

    config_adapters = core._config_command_adapters()

    return command_tools.handle_config(
        cfg,
        args_rest,
        preferences_doc_path=core.PREFERENCES_DOC_PATH,
        preference_paths=core.PREFERENCES_PATHS,
        display_config=config_adapters["display_config"],
        display_config_help=core._display_config_help,
        handle_config_migrate=core._handle_config_migrate,
        handle_config_file=config_adapters["handle_config_file"],
        handle_config_validate=config_adapters["handle_config_validate"],
        display_preferences_help=config_adapters["display_preferences_help"],
        display_preferences_path=config_adapters["display_preferences_path"],
        display_preferences_example=config_adapters["display_preferences_example"],
        run_config_web=_run_config_web,
        command_name=core.current_command(),
        config_write_target_path=core._config_write_target_path,
        display_human_gate_help=config_adapters["display_human_gate_help"],
        handle_config_get=config_adapters["handle_config_get"],
        handle_config_set=config_adapters["handle_config_set"],
        handle_config_unset=config_adapters["handle_config_unset"],
        run_connect_wizard=core.run_connect_wizard,
        handle_openrouter_extension_config=core._handle_openrouter_extension_config,
        display_adapter_registry=config_adapters["display_adapter_registry"],
        display_providers=config_adapters["display_providers"],
        handle_provider_default_config=core._handle_provider_default_config,
        handle_provider_add_config=core._handle_provider_add_config,
        handle_provider_edit_config=core._handle_provider_edit_config,
        handle_provider_rename_config=core._handle_provider_rename_config,
        handle_provider_remove_config=core._handle_provider_remove_config,
        handle_provider_credentials_config=core._handle_provider_credentials_config,
        display_accounts=config_adapters["display_accounts"],
        handle_account_default_config=core._handle_account_default_config,
        handle_account_add_config=core._handle_account_add_config,
        handle_account_edit_config=core._handle_account_edit_config,
        handle_account_remove_config=core._handle_account_remove_config,
        handle_account_rename_config=core._handle_account_rename_config,
        handle_account_status_config=core._handle_account_status_config,
        handle_account_login_config=core._handle_account_login_config,
        display_usage_stats=config_adapters["display_usage_stats"],
        resolve_provider_context=core.resolve_provider_context,
        setup_provider_credentials=core.setup_provider_credentials,
        handle_api_config=core._handle_api_config,
        console=core.console,
    )


__all__ = ["build_config_command_adapters", "handle_core_config_from_module"]
