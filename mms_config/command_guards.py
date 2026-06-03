"""Pure Config command alias and preview legacy-write guard predicates."""

from __future__ import annotations

from collections.abc import Sequence


PREVIEW_LEGACY_CONFIG_MUTATING_COMMANDS = {
    "migrate",
    "set",
    "unset",
    "load-balance.default",
    "load-balance.profile.add",
    "load-balance.profile.remove",
    "provider.default",
    "provider.add",
    "provider.edit",
    "provider.rename",
    "provider.remove",
    "provider.credentials",
    "account.default",
    "account.add",
    "account.edit",
    "account.remove",
    "account.rename",
    "account.login",
    "connect",
}


def config_subcommand_mutates_legacy_config(args_rest: Sequence[object] | None) -> bool:
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    if not key_path or key_path in {"-h", "--help", "help"}:
        return False
    if key_path in {"web", "webui", "setup.web", "setup-web"}:
        return False
    if key_path in PREVIEW_LEGACY_CONFIG_MUTATING_COMMANDS:
        return True
    if key_path in {"api.setup", "api.edit"}:
        return True
    if key_path in {"api.base_url", "api.api_key"}:
        return len(args_rest) > 1
    if key_path.startswith("api."):
        return True
    if key_path in {"extension.openrouter", "openrouter"}:
        action = str(args_rest[1] if len(args_rest) > 1 else "").strip()
        return action in {"add", "enable"}
    if len(args_rest) == 2 and key_path not in {
        "get",
        "provider.list",
        "account.list",
        "account.status",
        "load-balance.show",
        "validate",
    }:
        return True
    return False


def is_command_alias_request(argv: Sequence[object], command: str, aliases: set[str]) -> bool:
    return len(argv) >= 2 and argv[0] == command and str(argv[1] or "").strip() in aliases


def is_config_root_status_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"root", "root.status", "status.root"})


def is_config_model_source_status_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"source", "sources", "model-source", "model-sources"})


def is_config_consumer_bundle_status_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"bundle", "consumer-bundle", "manifest"})


def is_config_registry_v2_save_plan_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"save-plan", "save.plan", "v2-save-plan", "registry-save-plan"})


def is_config_preview_check_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"check", "preview-check", "preview.check", "v2-check"})


def is_config_v2_promotion_plan_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"promote-plan", "promotion-plan", "promote.check", "promote"})


def is_config_v2_release_readiness_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(
        argv,
        "config",
        {"release-readiness", "readiness", "v2-readiness", "4.0-readiness", "release.check"},
    )


def is_config_v2_migration_plan_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "migrate", {"config-v2", "config.v2", "v2", "config-v2-plan"})


def is_config_registry_v2_apply_plan_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(
        argv,
        "config",
        {"apply-plan", "apply.plan", "preview-apply", "apply-preview", "registry-apply-plan"},
    )


def is_config_preview_doctor_request(argv: Sequence[object]) -> bool:
    return is_command_alias_request(argv, "config", {"doctor", "preview-doctor", "preview.doctor", "v2-doctor"})


__all__ = [
    "PREVIEW_LEGACY_CONFIG_MUTATING_COMMANDS",
    "config_subcommand_mutates_legacy_config",
    "is_command_alias_request",
    "is_config_root_status_request",
    "is_config_model_source_status_request",
    "is_config_consumer_bundle_status_request",
    "is_config_registry_v2_save_plan_request",
    "is_config_preview_check_request",
    "is_config_v2_promotion_plan_request",
    "is_config_v2_release_readiness_request",
    "is_config_v2_migration_plan_request",
    "is_config_registry_v2_apply_plan_request",
    "is_config_preview_doctor_request",
]
