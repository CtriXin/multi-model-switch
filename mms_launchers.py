"""MMS 启动器：按 provider 或账号档案启动 CLI。"""

import json
import copy
import os
import re
import shlex
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from mms_account_state import activated_claude_account_state, seed_agy_state, seed_claude_state, seed_gemini_state
from mms_launcher.account_guard import (
    account_guard_profile as _account_guard_profile_impl,
    build_account_guard_report as _build_account_guard_report_impl,
    claude_account_guard_entry as _claude_account_guard_entry_impl,
    claude_guard_runtime as _claude_guard_runtime_impl,
    count_live_session_dirs as _count_live_session_dirs_impl,
    format_account_guard_summary as _format_account_guard_summary_impl,
    persist_account_guard_launch as _persist_account_guard_launch_impl,
    proxy_fingerprint as _proxy_fingerprint_impl,
    record_account_guard_finalize as _record_account_guard_finalize_impl,
)
from mms_runtime.i18n import normalize_language
from mms_launcher.console import LauncherLazyConsole
from mms_launcher.health import (
    health_check_due as _health_check_due_impl,
    load_gateway_health_cache as _load_gateway_health_cache_impl,
    save_gateway_health_cache as _save_gateway_health_cache_impl,
)
from mms_opencode.agents import (
    opencode_apply_agent_bypass_permissions,
    opencode_lite_agent_configs,
    opencode_lite_pro_agent_configs,
    opencode_permission_bypass_value,
)
from mms_opencode.config import (
    OPENCODE_API_KEY_ENV,
    OPENCODE_BYPASS_FLAG,
    OPENCODE_BYPASS_PERMISSION_ENV,
    OPENCODE_DEFAULT_OUTPUT_LIMIT,
    OPENCODE_IMAGE_INPUT_MODELS,
    OPENCODE_LITE_DEFAULT_AGENT,
    OPENCODE_MODEL_LIMIT_OVERRIDES,
    OPENCODE_PROVIDER_ID,
    opencode_agent_model_refs as _opencode_agent_model_refs,
    opencode_apply_bypass_env as _opencode_apply_bypass_env,
    opencode_apply_route_env as _opencode_apply_route_env,
    opencode_build_config_content as _opencode_build_config_content_impl,
    opencode_build_config_payload as _opencode_build_config_payload_impl,
    opencode_bypass_enabled as _opencode_bypass_enabled,
    opencode_config_slug as _opencode_config_slug,
    opencode_entrypoint as _opencode_entrypoint,
    opencode_env_bool as _opencode_env_bool,
    opencode_explicit_output_limit as _opencode_explicit_output_limit,
    opencode_launch_candidates as _opencode_launch_candidates,
    opencode_launch_preflight_enabled as _opencode_launch_preflight_enabled,
    opencode_model_config as _opencode_model_config_impl,
    opencode_model_limit_override as _opencode_model_limit_override,
    opencode_model_names as _opencode_model_names,
    opencode_model_output_limit as _opencode_model_output_limit,
    opencode_model_ref as _opencode_model_ref,
    opencode_model_requires_reasoning_roundtrip_guard as _opencode_model_requires_reasoning_roundtrip_guard,
    opencode_output_limit as _opencode_output_limit,
    opencode_preflight_timeout as _opencode_preflight_timeout,
    opencode_provider_base_url as _opencode_provider_base_url,
    opencode_route_by_id as _opencode_route_by_id,
    opencode_route_env_key as _opencode_route_env_key,
    opencode_route_model_ref as _opencode_route_model_ref,
    opencode_route_provider_ref as _opencode_route_provider_ref,
    opencode_runtime_bool as _opencode_runtime_bool,
    opencode_runtime_routes as _opencode_runtime_routes,
)
from mms_opencode.env import (
    opencode_export_config_path as _opencode_export_config_path_impl,
    opencode_gateway_env as _opencode_gateway_env_impl,
    opencode_global_export_env as _opencode_global_export_env_impl,
    opencode_global_omo_env as _opencode_global_omo_env_impl,
    opencode_provider_export_env as _opencode_provider_export_env_impl,
    opencode_set_soft_home as _opencode_set_soft_home_impl,
    opencode_write_config as _opencode_write_config_impl,
)
from mms_opencode.launch import (
    launch_opencode as _opencode_launch_impl,
    opencode_gateway_health_check as _opencode_gateway_health_check_impl,
    opencode_global_command as _opencode_global_command_impl,
    opencode_is_global_profile_runtime as _opencode_is_global_profile_runtime_impl,
    opencode_session_command as _opencode_session_command_impl,
)
from mms_opencode.preflight import (
    opencode_run_preflight as _opencode_run_preflight_impl,
    opencode_select_launch_candidate as _opencode_select_launch_candidate_impl,
)
from mms_opencode.session import (
    clear_opencode_config_env as _clear_opencode_config_env,
    overlay_opencode_session_assets as _overlay_opencode_session_assets_impl,
    opencode_rtk_plugin_path as _opencode_rtk_plugin_path_impl,
    opencode_session_plugin_runtime as _opencode_session_plugin_runtime,
    opencode_xmem_plugin_path as _opencode_xmem_plugin_path_impl,
    overlay_opencode_plugin as _overlay_opencode_plugin_impl,
)
from mms_core import (
    DEFAULT_ACCOUNT_TIMEZONE,
    _normalize_claude_1m_mode,
    _model_supports_vision,
    _probe_models,
    _runtime_force_ipv4,
    _runtime_httpx_request,
    detect_working_base_url,
    load_config,
    preference_asset_root,
)
from mms_capability_resolver import resolve_model_capabilities
from mms_runtime.fake_upstream import (
    ensure_local_proxy as _ensure_fake_upstream_proxy,
    fake_proxy_probe as _fake_proxy_probe,
    is_enabled as _fake_upstream_enabled,
    status_payload as _fake_upstream_status_payload,
)
from mms_runtime.host_context import host_capability_env, resolve_tool_bins, write_host_context
from mms_claude.project_store import CLAUDE_PERSISTENT_ENTRIES, claude_raw_entry_path, ensure_claude_project_store, read_slot_marker, write_slot_marker
from mms_provider_profiles import profile_context_window, resolve_provider_profile
from mms_pi import support as _pi_support
from mms_runtime import cli_search_dirs, prepare_cli_command
from mms_runtime.env import (
    apply_runtime_locale_profile as _apply_runtime_locale_profile_impl,
    runtime_locale_env as _runtime_locale_env_impl,
    validate_timezone_or_exit as _validate_timezone_or_exit_impl,
)
from mms_runtime.context import (
    DEFAULT_CONTEXT_WINDOW as _DEFAULT_CONTEXT_WINDOW,
    MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS as _MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS,
    MODEL_CONTEXT_WINDOWS as _MODEL_CONTEXT_WINDOWS,
    ONE_M_CONTEXT_SUFFIX as _ONE_M_CONTEXT_SUFFIX,
    ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS as _ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS,
    ONE_M_SUFFIX_CONTEXT_WINDOWS as _ONE_M_SUFFIX_CONTEXT_WINDOWS,
    load_model_context_overrides as _load_model_context_overrides_impl,
    lookup_context_window as _lookup_context_window_impl,
)
from mms_runtime.home import (
    build_home_context as _build_home_context_impl,
    home_context_lines as _home_context_lines_impl,
    normalize_path as _normalize_path_impl,
    path_is_within as _path_is_within_impl,
    prepare_oauth_home_context as _prepare_oauth_home_context_impl,
    runtime_dns_mode as _runtime_dns_mode_impl,
    runtime_net_mode as _runtime_net_mode_impl,
    validate_home_context_or_exit as _validate_home_context_or_exit_impl,
)
from mms_runtime.network import (
    CLAUDE_NO_PROXY_TOKENS as _CLAUDE_NO_PROXY_TOKENS,
    CLAUDE_PROXY_GUARD_TARGETS as _CLAUDE_PROXY_GUARD_TARGETS,
    apply_proxy_env as _apply_proxy_env_impl,
    apply_runtime_ip_stack_profile as _apply_runtime_ip_stack_profile_impl,
    apply_runtime_network_profile as _apply_runtime_network_profile_impl,
    base_claude_network_guard as _base_claude_network_guard_impl,
    build_claude_network_guard as _build_claude_network_guard_impl,
    claude_bypass_requires_proxy as _claude_bypass_requires_proxy_impl,
    check_proxy_connectivity_or_exit as _check_proxy_connectivity_or_exit_impl,
    claude_network_guard_cache_key as _claude_network_guard_cache_key_impl,
    claude_no_proxy_conflicts as _claude_no_proxy_conflicts_impl,
    enforce_claude_network_guard_or_exit as _enforce_claude_network_guard_or_exit_impl,
    get_claude_network_guard_preview as _get_claude_network_guard_preview_impl,
    mask_proxy_url as _mask_proxy_url_impl,
    mask_secret as _mask_secret_impl,
    provider_id_set_from_env as _provider_id_set_from_env_impl,
    proxy_dns_mode as _proxy_dns_mode_impl,
    run_proxy_probe as _run_proxy_probe_impl,
    runtime_declares_sensitive_claude as _runtime_declares_sensitive_claude_impl,
    runtime_is_sensitive_claude_provider as _runtime_is_sensitive_claude_provider_impl,
    runtime_network_summary as _runtime_network_summary_impl,
    split_no_proxy_values as _split_no_proxy_values_impl,
)
from mms_session.features import (
    asset_root_preference as _asset_root_preference_impl,
    default_gpt_reasoning_effort as _default_gpt_reasoning_effort_impl,
    is_installed_mms_layout as _is_installed_mms_layout_impl,
    normalize_agent_pack as _normalize_agent_pack_impl,
    normalize_caveman_level as _normalize_caveman_level_impl,
    normalize_caveman_mode as _normalize_caveman_mode_impl,
    normalize_ecc_mode as _normalize_ecc_mode_impl,
    normalize_nsr_mode as _normalize_nsr_mode_impl,
    normalize_reasoning_effort as _normalize_reasoning_effort_impl,
    normalize_thinking_mode as _normalize_thinking_mode_impl,
    resolve_agent_browser_root as _resolve_agent_browser_root_impl,
    resolve_auto_github_contributor_root as _resolve_auto_github_contributor_root_impl,
    resolve_caveman_root as _resolve_caveman_root_impl,
    resolve_codegraph_root as _resolve_codegraph_root_impl,
    resolve_ecc_root as _resolve_ecc_root_impl,
    resolve_nsr_root as _resolve_nsr_root_impl,
    resolve_omc_root as _resolve_omc_root_impl,
    resolve_token_saver_root as _resolve_token_saver_root_impl,
    resolve_toon_root as _resolve_toon_root_impl,
    resolve_web_access_root as _resolve_web_access_root_impl,
    resolve_weber_root as _resolve_weber_root_impl,
    resolve_xmem_root as _resolve_xmem_root_impl,
    runtime_agent_pack as _runtime_agent_pack_impl,
    runtime_caveman_enabled as _runtime_caveman_enabled_impl,
    runtime_caveman_level as _runtime_caveman_level_impl,
    runtime_ecc_enabled as _runtime_ecc_enabled_impl,
    runtime_nsr_enabled as _runtime_nsr_enabled_impl,
    runtime_omc_enabled as _runtime_omc_enabled_impl,
    runtime_reasoning_effort as _runtime_reasoning_effort_impl,
    runtime_thinking_enabled as _runtime_thinking_enabled_impl,
    runtime_vision_sidecar as _runtime_vision_sidecar_impl,
)
from mms_session.guard import (
    bounded_env_float as _bounded_env_float_impl,
    read_session_guard_marker as _read_session_guard_marker_impl,
    reserve_session_home as _reserve_session_home_impl,
    session_guard_lock_path as _session_guard_lock_path_impl,
    session_guard_marker_path as _session_guard_marker_path_impl,
    session_guard_pid_alive as _session_guard_pid_alive_impl,
    session_guard_process_identity as _session_guard_process_identity_impl,
    session_home_is_active as _session_home_is_active_impl,
    write_session_guard_marker as _write_session_guard_marker_impl,
)
from mms_session.assets import resolve_local_hooks_dir as _resolve_local_hooks_dir_impl
from mms_session.index import finalize_claude_session, list_indexed_sessions, record_claude_session_start
from mms_session.packet import write_session_packet
from mms_state_io import (
    atomic_write_json,
    atomic_write_text,
    load_json_dict_unlocked as _load_json_dict_unlocked_impl,
    locked_state_file,
    mms_config_root_mode,
    resolve_mms_config_dir as _resolve_mms_config_dir,
    utc_now_z as _utc_now_z_impl,
)
from mms_state_io import resolve_current_workdir as _safe_getcwd

_build_gateway_url = None
codex_claude_bridge = None
gemini_claude_bridge = None
gateway_claude_bridge = None
codex_chatcompletions_bridge = None
codex_responses_bridge = None
_write_route_status = None
build_provider_speed_scope = None

try:
    from mms_runtime.health_cache import get_model_health as _get_model_health
except ImportError:
    def _get_model_health(*_a, **_kw): return None


def _ensure_bridge_helpers():
    global _build_gateway_url, codex_claude_bridge, gemini_claude_bridge
    global gateway_claude_bridge, codex_chatcompletions_bridge, codex_responses_bridge, _write_route_status
    if _build_gateway_url is not None:
        return
    from mms_launcher.bridge import load_bridge_helpers

    helpers = load_bridge_helpers()
    _build_gateway_url = helpers["_build_gateway_url"]
    codex_claude_bridge = helpers["codex_claude_bridge"]
    gemini_claude_bridge = helpers["gemini_claude_bridge"]
    gateway_claude_bridge = helpers["gateway_claude_bridge"]
    codex_chatcompletions_bridge = helpers["codex_chatcompletions_bridge"]
    codex_responses_bridge = helpers["codex_responses_bridge"]
    _write_route_status = helpers["_write_route_status"]


def _gateway_claude_bridge_context(*args, **kwargs):
    """Compatibility wrapper for gateway Claude bridge signature downgrade."""
    from mms_launcher.bridge import gateway_claude_bridge_context

    return gateway_claude_bridge_context(gateway_claude_bridge, *args, console=console, **kwargs)


def _ensure_speed_stats():
    global build_provider_speed_scope
    if build_provider_speed_scope is not None:
        return
    from mms_launcher.bridge import load_speed_stats_helper

    build_provider_speed_scope = load_speed_stats_helper()

console = LauncherLazyConsole()

# Keep the former private helper names importable while the implementation lives in mms_opencode.agents.
_opencode_lite_agent_configs = opencode_lite_agent_configs
_opencode_lite_pro_agent_configs = opencode_lite_pro_agent_configs
_opencode_permission_bypass_value = opencode_permission_bypass_value
_opencode_apply_agent_bypass_permissions = opencode_apply_agent_bypass_permissions


def _mask_proxy_url(proxy_url):
    """Compatibility wrapper for proxy URL masking."""
    return _mask_proxy_url_impl(proxy_url, mask_secret_fn=_mask_secret_impl)


def _runtime_network_summary(runtime):
    """Compatibility wrapper for runtime network display summaries."""
    return _runtime_network_summary_impl(
        runtime,
        mask_proxy_url_fn=_mask_proxy_url,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        proxy_dns_mode_fn=_proxy_dns_mode,
        runtime_locale_env_fn=_runtime_locale_env,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
    )


def _guard_utc_now():
    """Compatibility wrapper for UTC guard timestamps."""
    return _utc_now_z_impl()


def _runtime_locale_env(runtime=None):
    """Compatibility wrapper for runtime locale env projection."""
    return _runtime_locale_env_impl(runtime, normalize_language_fn=normalize_language)


def _apply_runtime_locale_profile(env, runtime=None):
    """Compatibility wrapper for applying runtime locale env."""
    return _apply_runtime_locale_profile_impl(
        env,
        runtime,
        runtime_locale_env_fn=_runtime_locale_env,
    )

def _provider_id_set_from_env(env_name):
    """Compatibility wrapper for provider id env-set parsing."""
    return _provider_id_set_from_env_impl(env_name, environ=os.environ)


def _runtime_declares_sensitive_claude(runtime):
    """Compatibility wrapper for runtime-declared sensitive Claude provider markers."""
    return _runtime_declares_sensitive_claude_impl(runtime)


def _load_model_context_overrides():
    """Compatibility wrapper for model context-window overrides."""
    return _load_model_context_overrides_impl(
        _model_context_overrides_path(),
        _MODEL_CONTEXT_OVERRIDES_CACHE,
    )


def _lookup_context_window(model_name, provider_id=None):
    """Compatibility wrapper for runtime context-window lookup."""
    return _lookup_context_window_impl(
        model_name,
        provider_id=provider_id,
        context_overrides_loader=_load_model_context_overrides,
        model_context_windows=_MODEL_CONTEXT_WINDOWS,
    )


def _runtime_supports_claude_1m(runtime):
    """Compatibility wrapper for Claude 1M support policy."""
    from mms_claude.model import runtime_supports_claude_1m

    return runtime_supports_claude_1m(runtime)


def _effective_context_window(*models, enable_claude_1m=True, provider_id=None):
    """Compatibility wrapper for Claude-routed context window resolution."""
    from mms_claude.model import effective_context_window

    return effective_context_window(
        *models,
        enable_claude_1m=enable_claude_1m,
        provider_id=provider_id,
    )


def _runtime_is_sensitive_claude_provider(runtime):
    """Compatibility wrapper for sensitive Claude provider detection."""
    return _runtime_is_sensitive_claude_provider_impl(
        runtime,
        provider_id_set_from_env_fn=_provider_id_set_from_env,
        runtime_declares_sensitive_claude_fn=_runtime_declares_sensitive_claude,
    )




def _launch_status(message, *, spinner="dots"):
    """为启动慢步骤提供可见 spinner，避免用户干等。"""
    from mms_display.launch import launch_status

    return launch_status(message, spinner=spinner, console=console)


def _print_launch_step_done(label, started_at, detail=None, *, style="dim"):
    from mms_display.launch import print_launch_step_done

    return print_launch_step_done(
        label,
        started_at,
        detail,
        style=style,
        console=console,
        perf_counter_fn=perf_counter,
    )


def _timed_launch_step(timings, label):
    from mms_display.launch import timed_launch_step

    return timed_launch_step(timings, label, perf_counter_fn=perf_counter)


def _prepare_claude_env_with_status(runtime, **kwargs):
    from mms_display.launch import (
        launch_timing_enabled,
        launch_timing_threshold_sec,
        prepare_claude_env_with_status,
        print_launch_timing_breakdown,
    )

    def _print_timing_breakdown(timings, *, total_elapsed):
        return print_launch_timing_breakdown(
            timings,
            total_elapsed=total_elapsed,
            console=console,
            launch_timing_enabled_fn=lambda: launch_timing_enabled(environ=os.environ),
            launch_timing_threshold_sec_fn=lambda: launch_timing_threshold_sec(environ=os.environ),
        )

    return prepare_claude_env_with_status(
        runtime,
        claude_gateway_env_fn=_claude_gateway_env,
        launch_status_fn=_launch_status,
        print_launch_step_done_fn=_print_launch_step_done,
        print_launch_timing_breakdown_fn=_print_timing_breakdown,
        perf_counter_fn=perf_counter,
        **kwargs,
    )


def _real_user_home():
    explicit = str(os.environ.get("MMS_REAL_HOME", "")).strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    home = os.path.abspath(os.environ.get("HOME") or os.path.expanduser("~"))
    markers = (
        f"{os.sep}.config{os.sep}mms{os.sep}codex-gateway{os.sep}",
        f"{os.sep}.config{os.sep}mms{os.sep}claude-gateway{os.sep}",
    )
    for marker in markers:
        if marker in home:
            return home.split(marker, 1)[0]
    return home


def _real_user_path(*parts):
    return os.path.join(_real_user_home(), *parts)


def _account_guard_state_path():
    return _real_user_path(".config", "mms", "account-guard-state.json")


def _load_json_dict_unlocked(path):
    """Compatibility wrapper for best-effort JSON object reads."""
    return _load_json_dict_unlocked_impl(path)


def _read_account_guard_state():
    path = _account_guard_state_path()
    with locked_state_file(path):
        return _load_json_dict_unlocked(path)


def _claude_account_guard_entry(state, account_id):
    """Compatibility wrapper for account guard state entries."""
    return _claude_account_guard_entry_impl(state, account_id)


def _count_live_session_dirs(sessions_dir):
    """Compatibility wrapper for active Claude session counting."""
    return _count_live_session_dirs_impl(
        sessions_dir,
        session_home_is_active_fn=_session_home_is_active,
    )


def _proxy_fingerprint(proxy_url):
    """Compatibility wrapper for proxy fingerprint display."""
    return _proxy_fingerprint_impl(proxy_url)


def _account_guard_profile(runtime):
    """Compatibility wrapper for account guard profile snapshots."""
    return _account_guard_profile_impl(
        runtime,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
    )


def _build_account_guard_report(account):
    """Compatibility wrapper for account guard launch reports."""
    return _build_account_guard_report_impl(
        account,
        read_account_guard_state_fn=_read_account_guard_state,
        count_live_session_dirs_fn=_count_live_session_dirs,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        account_guard_profile_fn=_account_guard_profile,
    )


def _claude_guard_runtime(runtime):
    """Compatibility wrapper for Claude account guard runtime projection."""
    return _claude_guard_runtime_impl(runtime, real_user_path_fn=_real_user_path)


def _format_account_guard_summary(report):
    """Compatibility wrapper for account guard summary text."""
    return _format_account_guard_summary_impl(report)


def _persist_account_guard_launch(account_id, report, *, session_home=""):
    """Compatibility wrapper for account guard launch persistence."""
    return _persist_account_guard_launch_impl(
        account_id,
        report,
        session_home=session_home,
        account_guard_state_path_fn=_account_guard_state_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        guard_utc_now_fn=_guard_utc_now,
        atomic_write_json_fn=atomic_write_json,
    )


def _record_account_guard_finalize(account_id, *, exit_code=None, stale_cleanup=False):
    """Compatibility wrapper for account guard exit persistence."""
    return _record_account_guard_finalize_impl(
        account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
        account_guard_state_path_fn=_account_guard_state_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        guard_utc_now_fn=_guard_utc_now,
        atomic_write_json_fn=atomic_write_json,
    )


_MODEL_CONTEXT_OVERRIDES_CACHE = {"path": None, "mtime": None, "data": {"models": {}, "provider_overrides": {}}}
_CLAUDE_NETWORK_GUARD_CACHE: dict = {}
_CLAUDE_NETWORK_GUARD_TTL_SEC = 20.0
_SESSION_GUARD_MARKER_NAME = ".mms-session-guard.json"
_SESSION_GUARD_LOCK_NAME = ".mms-session-guard.lock"


def _model_context_overrides_path():
    try:
        config_root = _resolve_mms_config_dir()
    except Exception:
        config_root = _real_user_path(".config", "mms")
    return os.path.join(config_root, "model-context-overrides.json")


def _inject_real_home_hints(env, *, include_xdg=False):
    from mms_launcher.export import inject_real_home_hints

    return inject_real_home_hints(
        env,
        include_xdg=include_xdg,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        inject_rescue_launch_env=_inject_rescue_launch_env,
    )


def _truthy(value):
    from mms_launcher.export import truthy

    return truthy(value)


def _rescue_default_fallback_config(env=None):
    from mms_launcher.export import rescue_default_fallback_config

    environ = env if isinstance(env, dict) else os.environ
    return rescue_default_fallback_config(
        environ=environ,
        load_config=load_config,
        truthy=_truthy,
        mms_config_root_mode=mms_config_root_mode,
    )


def _rescue_bridge_kwargs():
    from mms_launcher.export import rescue_bridge_kwargs

    return rescue_bridge_kwargs(
        rescue_default_fallback_config=_rescue_default_fallback_config,
    )


def _merged_config_root_env(env):
    merged_env = dict(os.environ)
    if isinstance(env, dict):
        merged_env.update({str(key): str(value) for key, value in env.items() if value is not None})
        if "XDG_CONFIG_HOME" not in env and any(key in env for key in ("HOME", "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME")):
            merged_env.pop("XDG_CONFIG_HOME", None)
    return merged_env


def _selected_mms_config_root(env):
    merged_env = _merged_config_root_env(env)
    try:
        return _resolve_mms_config_dir(merged_env)
    except Exception:
        return _real_user_path(".config", "mms")


def _config_root_is_explicit(env):
    merged_env = _merged_config_root_env(env)
    return bool(str(merged_env.get("MMS_CONFIG_ROOT") or merged_env.get("MMS_CONFIG_DIR") or "").strip())


def _selected_config_path(*parts):
    return os.path.join(_selected_mms_config_root({}), *parts)


def _inject_rescue_launch_env(env):
    from mms_launcher.export import inject_rescue_launch_env

    return inject_rescue_launch_env(
        env,
        safe_getcwd=_safe_getcwd,
        real_user_path=_real_user_path,
        rescue_default_fallback_config=_rescue_default_fallback_config,
        selected_mms_config_root=_selected_mms_config_root,
    )


def _host_context_real_home():
    from mms_launcher.export import host_context_real_home

    return host_context_real_home(
        real_user_path=_real_user_path,
        real_user_home=_real_user_home,
    )


def _host_tool_context(session_home, env=None):
    from mms_launcher.export import host_tool_context

    return host_tool_context(
        session_home,
        env,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        resolve_tool_bins=resolve_tool_bins,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
    )


def _inject_host_capability_hints(env):
    from mms_launcher.export import inject_host_capability_hints

    return inject_host_capability_hints(
        env,
        host_capability_env=host_capability_env,
        host_context_real_home=_host_context_real_home,
    )


def _install_host_context_env(env, *, cli, runtime=None, model_info=None, session_home=""):
    from mms_launcher.export import install_host_context_env

    return install_host_context_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        host_context_real_home=_host_context_real_home,
        selected_model_name=_selected_model_name,
        safe_getcwd=_safe_getcwd,
        host_tool_context=_host_tool_context,
        write_host_context=write_host_context,
    )


def _set_session_home_hint(env, session_home):
    from mms_launcher.export import set_session_home_hint

    return set_session_home_hint(env, session_home)


def _set_codex_soft_home(env, session_home):
    """Keep real HOME for tools; isolate Codex config/auth in CODEX_HOME."""
    from mms_launcher.export import set_codex_home_hint, set_codex_soft_home

    return set_codex_soft_home(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
        set_codex_home_hint=set_codex_home_hint,
    )


def _set_opencode_soft_home(env, session_home):
    return _opencode_set_soft_home_impl(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
    )


def _selected_model_name(*candidates, model_info=None):
    from mms_launcher.export import selected_model_name

    return selected_model_name(*candidates, model_info=model_info)


def _inject_selected_model_name(env, *candidates, model_info=None):
    from mms_launcher.export import inject_selected_model_name

    return inject_selected_model_name(env, *candidates, model_info=model_info)


def _install_session_packet_env(
    env,
    *,
    cli,
    runtime,
    model_info=None,
    session_home="",
    features=None,
    extra_paths=None,
):
    from mms_launcher.export import install_session_packet_env

    return install_session_packet_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features=features,
        extra_paths=extra_paths,
        write_session_packet=write_session_packet,
    )


def _session_guard_marker_path(session_home):
    """Compatibility wrapper for session guard marker paths."""
    return _session_guard_marker_path_impl(session_home, _SESSION_GUARD_MARKER_NAME)


def _session_guard_lock_path(sessions_dir):
    """Compatibility wrapper for session guard lock paths."""
    return _session_guard_lock_path_impl(sessions_dir, _SESSION_GUARD_LOCK_NAME)


def _session_guard_process_identity(pid):
    """Compatibility wrapper for process identity snapshots."""
    return _session_guard_process_identity_impl(pid)


def _session_guard_pid_alive(pid, *, identity=""):
    """Compatibility wrapper for guarded PID liveness checks."""
    return _session_guard_pid_alive_impl(
        pid,
        identity=identity,
        process_identity_fn=_session_guard_process_identity,
    )


def _read_session_guard_marker(session_home):
    """Compatibility wrapper for session guard marker reads."""
    return _read_session_guard_marker_impl(
        session_home,
        marker_path_fn=_session_guard_marker_path,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
    )


def _write_session_guard_marker(session_home, *, account_id="", runtime_kind="", child_pid=None):
    """Compatibility wrapper for session guard marker writes."""
    return _write_session_guard_marker_impl(
        session_home,
        account_id=account_id,
        runtime_kind=runtime_kind,
        child_pid=child_pid,
        marker_path_fn=_session_guard_marker_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        atomic_write_json_fn=atomic_write_json,
        guard_utc_now_fn=_guard_utc_now,
        process_identity_fn=_session_guard_process_identity,
    )


def _record_session_child_pid(session_home, child_pid):
    _write_session_guard_marker(session_home, child_pid=child_pid)


def _session_home_is_active(session_home):
    """Compatibility wrapper for active session-home checks."""
    return _session_home_is_active_impl(
        session_home,
        read_marker_fn=_read_session_guard_marker,
        pid_alive_fn=_session_guard_pid_alive,
    )


def _bounded_env_float(name, default):
    """Compatibility wrapper for bounded float env parsing."""
    return _bounded_env_float_impl(name, default, environ=os.environ)


def _session_cleanup_launch_max_entries():
    return _bounded_env_int("MMS_SESSION_CLEANUP_MAX_ENTRIES", 3)


def _session_cleanup_launch_max_seconds():
    return _bounded_env_float("MMS_SESSION_CLEANUP_MAX_SECONDS", 2.0)


def _reserve_session_home(
    sessions_dir,
    *,
    account_id="",
    runtime_kind="",
    stale_callback=None,
    max_live_sessions=None,
    timings=None,
):
    """Compatibility wrapper for guarded session-home reservation."""
    return _reserve_session_home_impl(
        sessions_dir,
        account_id=account_id,
        runtime_kind=runtime_kind,
        stale_callback=stale_callback,
        max_live_sessions=max_live_sessions,
        timings=timings,
        timed_launch_step_fn=_timed_launch_step,
        locked_state_file_fn=locked_state_file,
        session_guard_lock_path_fn=_session_guard_lock_path,
        cleanup_stale_sessions_fn=_cleanup_stale_sessions,
        session_cleanup_launch_max_entries_fn=_session_cleanup_launch_max_entries,
        session_cleanup_launch_max_seconds_fn=_session_cleanup_launch_max_seconds,
        count_live_session_dirs_fn=_count_live_session_dirs,
        session_home_is_active_fn=_session_home_is_active,
        write_session_guard_marker_fn=_write_session_guard_marker,
    )


def _real_home_wrapper_scrub_lines():
    from mms_launcher.export import real_home_wrapper_scrub_lines

    return real_home_wrapper_scrub_lines()


def _normalize_path(value):
    """Compatibility wrapper for HOME path normalization."""
    return _normalize_path_impl(value)


def _path_is_within(path, root):
    """Compatibility wrapper for path containment checks."""
    return _path_is_within_impl(path, root)


def _path_under(path, root):
    try:
        path_real = os.path.realpath(os.path.abspath(path))
        root_real = os.path.realpath(os.path.abspath(root))
        return os.path.commonpath([path_real, root_real]) == root_real
    except Exception:
        return False


def _runtime_net_mode(runtime):
    """Compatibility wrapper for runtime network mode labels."""
    return _runtime_net_mode_impl(
        runtime,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
    )


def _runtime_dns_mode(runtime):
    """Compatibility wrapper for runtime DNS mode labels."""
    return _runtime_dns_mode_impl(
        runtime,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        proxy_dns_mode_fn=_proxy_dns_mode,
    )


def _build_home_context(env, runtime, cli_name):
    """Compatibility wrapper for launch HOME context construction."""
    return _build_home_context_impl(
        env,
        runtime,
        cli_name,
        real_user_home_fn=_real_user_home,
        real_user_path_fn=_real_user_path,
        selected_mms_config_root_fn=_selected_mms_config_root,
        config_root_is_explicit_fn=_config_root_is_explicit,
        runtime_locale_env_fn=_runtime_locale_env,
        runtime_net_mode_fn=_runtime_net_mode,
        runtime_dns_mode_fn=_runtime_dns_mode,
    )


def _validate_home_context_or_exit(context):
    """Compatibility wrapper for launch HOME context validation."""
    return _validate_home_context_or_exit_impl(
        context,
        console=console,
        path_is_within_fn=_path_is_within,
        exit_fn=sys.exit,
    )


def _home_context_lines(context):
    """Compatibility wrapper for launch HOME context display lines."""
    return _home_context_lines_impl(context)


def _prepare_oauth_home_context(runtime, env, cli_name):
    """Compatibility wrapper for OAuth HOME context preparation."""
    return _prepare_oauth_home_context_impl(
        runtime,
        env,
        cli_name,
        build_home_context_fn=_build_home_context,
        validate_home_context_fn=_validate_home_context_or_exit,
        home_context_lines_fn=_home_context_lines,
        console=console,
    )


def _apply_proxy_env(env, proxy_url, no_proxy=""):
    """Compatibility wrapper for applying proxy env values."""
    return _apply_proxy_env_impl(env, proxy_url, no_proxy=no_proxy)


def _proxy_dns_mode(proxy_url):
    """Compatibility wrapper for proxy DNS mode classification."""
    return _proxy_dns_mode_impl(proxy_url)


def _split_no_proxy_values(no_proxy):
    """Compatibility wrapper for NO_PROXY token splitting."""
    return _split_no_proxy_values_impl(no_proxy)


def _claude_no_proxy_conflicts(no_proxy):
    """Compatibility wrapper for Claude NO_PROXY conflict detection."""
    return _claude_no_proxy_conflicts_impl(
        no_proxy,
        no_proxy_tokens=_CLAUDE_NO_PROXY_TOKENS,
    )


def _run_proxy_probe(proxy_url, target_url, *, no_proxy="", force_ipv4=True, resolve_ip=False):
    """Compatibility wrapper for proxy reachability probes."""
    return _run_proxy_probe_impl(
        proxy_url,
        target_url,
        no_proxy=no_proxy,
        force_ipv4=force_ipv4,
        resolve_ip=resolve_ip,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_proxy_probe_fn=_fake_proxy_probe,
    )


def _base_claude_network_guard(runtime, *, require_proxy=False):
    """Compatibility wrapper for Claude network guard base payloads."""
    return _base_claude_network_guard_impl(
        runtime,
        require_proxy=require_proxy,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        proxy_fingerprint_fn=_proxy_fingerprint,
        proxy_dns_mode_fn=_proxy_dns_mode,
        claude_no_proxy_conflicts_fn=_claude_no_proxy_conflicts,
    )


def _claude_bypass_requires_proxy(runtime):
    """Compatibility wrapper for Claude BYPASS proxy requirement policy."""
    return _claude_bypass_requires_proxy_impl(
        runtime,
        runtime_is_sensitive_claude_provider_fn=_runtime_is_sensitive_claude_provider,
    )


def _emit_dns_guard_hint(runtime, *, cli_name, auth_mode):
    """Compatibility wrapper for DNS guard hint display."""
    from mms_display.launch import emit_dns_guard_hint

    return emit_dns_guard_hint(
        runtime,
        cli_name=cli_name,
        auth_mode=auth_mode,
        runtime_dns_mode_fn=_runtime_dns_mode,
        console=console,
    )


def _claude_network_guard_cache_key(runtime, require_proxy):
    """Compatibility wrapper for Claude network guard cache keys."""
    return _claude_network_guard_cache_key_impl(
        runtime,
        require_proxy,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
    )


def get_claude_network_guard_preview(runtime, *, require_proxy=False):
    """Compatibility wrapper for cached Claude network guard previews."""
    return _get_claude_network_guard_preview_impl(
        runtime,
        require_proxy=require_proxy,
        cache=_CLAUDE_NETWORK_GUARD_CACHE,
        ttl_sec=_CLAUDE_NETWORK_GUARD_TTL_SEC,
        perf_counter_fn=perf_counter,
        cache_key_fn=_claude_network_guard_cache_key,
        base_guard_fn=_base_claude_network_guard,
    )


def build_claude_network_guard(runtime, *, require_proxy=False):
    """Compatibility wrapper for Claude network guard validation."""
    return _build_claude_network_guard_impl(
        runtime,
        require_proxy=require_proxy,
        cache=_CLAUDE_NETWORK_GUARD_CACHE,
        ttl_sec=_CLAUDE_NETWORK_GUARD_TTL_SEC,
        perf_counter_fn=perf_counter,
        cache_key_fn=_claude_network_guard_cache_key,
        base_guard_fn=_base_claude_network_guard,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        run_proxy_probe_fn=_run_proxy_probe,
        guard_targets=_CLAUDE_PROXY_GUARD_TARGETS,
    )


def _enforce_claude_network_guard_or_exit(runtime, *, require_proxy=False):
    """Compatibility wrapper for enforced Claude network guard checks."""
    return _enforce_claude_network_guard_or_exit_impl(
        runtime,
        require_proxy=require_proxy,
        build_network_guard_fn=build_claude_network_guard,
        console=console,
        exit_fn=sys.exit,
    )


def _validate_timezone_or_exit(timezone_name, *, label="account"):
    """Compatibility wrapper for startup timezone validation."""
    return _validate_timezone_or_exit_impl(
        timezone_name,
        label=label,
        console=console,
        exit_fn=sys.exit,
    )


def _check_proxy_connectivity_or_exit(proxy_url, no_proxy="", *, label="account", force_ipv4=True):
    """Compatibility wrapper for startup proxy connectivity checks."""
    return _check_proxy_connectivity_or_exit_impl(
        proxy_url,
        no_proxy,
        label=label,
        force_ipv4=force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_proxy_probe_fn=_fake_proxy_probe,
        console=console,
        exit_fn=sys.exit,
    )


def _apply_runtime_network_profile(env, runtime, *, validate_proxy=True):
    """Compatibility wrapper for runtime network env projection."""
    return _apply_runtime_network_profile_impl(
        env,
        runtime,
        validate_proxy=validate_proxy,
        validate_timezone_or_exit_fn=_validate_timezone_or_exit,
        apply_runtime_locale_profile_fn=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile_fn=_apply_runtime_ip_stack_profile,
        check_proxy_connectivity_or_exit_fn=_check_proxy_connectivity_or_exit,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_upstream_status_payload_fn=_fake_upstream_status_payload,
        proxy_fingerprint_fn=_proxy_fingerprint,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
    )


def _apply_runtime_ip_stack_profile(env, runtime):
    """Compatibility wrapper for runtime IP stack env projection."""
    return _apply_runtime_ip_stack_profile_impl(
        env,
        runtime,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
    )


RUNTIME_DIR = _selected_config_path("runtime")
HEALTH_CHECK_PATH = _selected_config_path("health_check.json")
ANTHROPIC_URL_CACHE_PATH = _selected_config_path("cache", "anthropic_base_urls.json")

# Anthropic URL 探测结果缓存（内存，TTL 1h）
# key: provider_id → {"url": str, "ts": datetime}
_ANTHROPIC_URL_CACHE: dict = {}
CLI_PROTOCOL_REQUIREMENTS = {
    "claude": "anthropic_messages",
    "codex": "openai_chat_completions",
    "opencode": "openai_chat_completions",
}
OAUTH_CAPABLE_CLIS = {"claude", "codex", "gemini", "agy"}
# OpenCode constants and pure config helpers live in mms_opencode.config.
_LOCAL_STATUSLINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline-command.sh")
def _resolve_local_hooks_dir(module_file=None):
    """Compatibility wrapper for local hook directory resolution."""
    return _resolve_local_hooks_dir_impl(module_file or __file__)


_LOCAL_HOOKS_DIR = _resolve_local_hooks_dir()
_CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-feishu-webfetch-guard.sh")
_CLAUDE_HIVE_COMPACT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "hive-compact-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-start-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-end-hook.sh")
_CLAUDE_BRAINKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-token-monitor-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-start-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-end-hook.sh")
_CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-token-monitor-hook.sh")
_CLAUDE_CODEGRAPH_AUTO_INDEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-codegraph-auto-index.sh")
_CLAUDE_MMS_RESUME_HINT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mms-resume-hint.sh")
_XMEM_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-start-hook.sh")
_XMEM_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-end-hook.sh")
_XMEM_GATEWAY_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-gateway-hook.sh")
_NSR_CLAUDE_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-claude-hook.sh")
_NSR_CODEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-codex-hook.sh")
_NSR_BUILTIN_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-builtin-hook.py")

_CLAUDE_STATUSLINE_CONFIG = {
    "command": f"/bin/bash {_LOCAL_STATUSLINE_SCRIPT}",
    "type": "command",
}

_CLAUDE_SESSION_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "MMS_FORCE_IPV4",
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)

_CLAUDE_SETTINGS_INHERIT_KEYS = (
    "hooks",
    "statusLine",
    "permissions",
)
_CLAUDE_SESSION_MCP_SERVER_ALLOWLIST = (
    "brainkeeper",
    "codegraph",
)
_CLAUDE_SETTINGS_INHERIT_SCALAR_KEYS = ("theme",)
_CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST = (
    ".mcp.json",
    "CLAUDE.md",
    "RTK.md",
    "commands",
    "hooks",
    "skills",
)
_CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST = (
    "CLAUDE.md",
    "RTK.md",
)
_CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST = _CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST
_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST = ("Keychains",)
_CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE = 86
_SESSION_REAL_HOME_WRAPPER_COMMANDS = (
    "open",
    "osascript",
    "security",
    "git",
    "ssh",
    "ssh-add",
    "scp",
    "sftp",
    "brew",
    "gh",
    "lark-cli",
    "rh",
    "hive",
    "pm2",
    "npm",
    "pnpm",
    "npx",
    "yarn",
    "corepack",
    "node",
    "uv",
    "docker",
    "docker-compose",
)
_CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST = (
    "userID",
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_UI_STATE_SEED_KEYS = (
    "firstStartTime",
    "numStartups",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST = ("tipsHistory",)
_CLAUDE_OAUTH_ACCOUNT_ALLOWLIST = (
    "accountCreatedAt",
    "accountUuid",
    "billingType",
    "displayName",
    "emailAddress",
    "hasExtraUsageEnabled",
    "organizationName",
    "organizationRole",
    "organizationUuid",
    "subscriptionCreatedAt",
    "workspaceRole",
)
_CLAUDE_AI_OAUTH_ALLOWLIST = (
    "accessToken",
    "refreshToken",
    "expiresAt",
    "expiresIn",
    "tokenType",
    "token_type",
    "emailAddress",
    "accountUuid",
    "organizationUuid",
)
_CLAUDE_CODEX_STATE_TOP_LEVEL_ALLOWLIST = (
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "installMethod",
)
_CLAUDE_OAUTH_ENV_PREFIX_BLOCKLIST = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)
_OPENAI_ENV_PREFIX_BLOCKLIST = (
    "OPENAI_",
)
_RUNTIME_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_RUNTIME_FAKE_ENV_KEYS = (
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)
_RUNTIME_CA_ENV_KEYS = (
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)

_CLAUDE_MAILBOX_PREFIX = os.path.join(_real_user_path(".claude"), "mailbox")

_CLAUDE_DEFAULT_PERMISSION_ALLOW = [
    "Read",
    "Edit",
    "Write",
    "Bash(yarn *)",
    "Bash(npm *)",
    "Bash(node *)",
    "Bash(git *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(find *)",
    "Bash(grep *)",
    "Bash(which *)",
    "Bash(chmod *)",
    "Bash(cd *)",
    "Bash(python3 *)",
    "Bash(rsync *)",
    "Bash(coscli *)",
    f"Bash(mkdir -p {_CLAUDE_MAILBOX_PREFIX}*)",
    f"Bash(rm -rf {_CLAUDE_MAILBOX_PREFIX}/*)",
    f"Bash(ls {_CLAUDE_MAILBOX_PREFIX}*)",
    "Skill(*)",
    "Agent(*)",
]

_CLAUDE_DEFAULT_PERMISSION_DENY = [
    "Bash(rm -rf /)*",
    "Bash(git push --force *)",
]


def _claude_gateway_home():
    gateway_base = _real_user_path(".config", "mms", "claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    return os.path.join(sessions_dir, str(os.getpid()))


def _claude_route_status_paths():
    if str(os.environ.get("MMS_CONFIG_ROOT") or os.environ.get("MMS_CONFIG_DIR") or "").strip():
        return [os.path.join(_resolve_mms_config_dir(), "route_status.json")]
    gateway_home = _claude_gateway_home()
    return [os.path.join(gateway_home, ".config", "mms", "route_status.json")]


def _anthropic_cache_key(provider_id, configured_url):
    return f"{provider_id}::{configured_url.rstrip('/')}"


def _load_anthropic_url_file_cache():
    try:
        with open(ANTHROPIC_URL_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_anthropic_url_file_cache(cache_data):
    try:
        os.makedirs(os.path.dirname(ANTHROPIC_URL_CACHE_PATH), exist_ok=True)
        tmp_path = ANTHROPIC_URL_CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cache_data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, ANTHROPIC_URL_CACHE_PATH)
    except Exception:
        pass


def _remember_anthropic_url(provider_id, configured_url, resolved_url):
    now_iso = datetime.now().isoformat()
    cache_key = _anthropic_cache_key(provider_id, configured_url)
    _ANTHROPIC_URL_CACHE[cache_key] = {"url": resolved_url, "ts": datetime.now()}
    cache_data = _load_anthropic_url_file_cache()
    cache_data[cache_key] = {"url": resolved_url, "ts": now_iso}
    _save_anthropic_url_file_cache(cache_data)


def _load_real_claude_settings():
    """Compatibility wrapper for reading real Claude settings."""
    from mms_claude.settings import load_real_claude_settings

    return load_real_claude_settings()


def _load_claude_settings_from_dir(claude_dir):
    """Compatibility wrapper for reading Claude settings from a directory."""
    from mms_claude.settings import load_claude_settings_from_dir

    return load_claude_settings_from_dir(claude_dir)


def _load_claude_settings_template(filename):
    """Compatibility wrapper for Claude settings template loading."""
    from mms_claude.settings import load_claude_settings_template

    return load_claude_settings_template(filename)


def _load_mms_claude_settings_template():
    """Compatibility wrapper for the MMS Claude session settings template."""
    from mms_claude.settings import load_mms_claude_settings_template

    return load_mms_claude_settings_template()


def _load_global_claude_settings_template():
    """Compatibility wrapper for the global Claude managed settings template."""
    from mms_claude.settings import load_global_claude_settings_template

    return load_global_claude_settings_template()


def _global_claude_snapshot_path():
    """Compatibility wrapper for global Claude managed snapshot path."""
    from mms_claude.settings import global_claude_snapshot_path

    return global_claude_snapshot_path()


def _normalize_hook_command(command):
    """Compatibility wrapper for hook command normalization."""
    from mms_claude.settings import normalize_hook_command

    return normalize_hook_command(command)


def _extract_managed_claude_snapshot(settings_data, template_settings):
    """Compatibility wrapper for Claude managed settings snapshot extraction."""
    from mms_claude.settings import extract_managed_claude_snapshot

    return extract_managed_claude_snapshot(settings_data, template_settings)


def _snapshot_to_template(snapshot_data, seed_template):
    """Compatibility wrapper for snapshot-to-template conversion."""
    from mms_claude.settings import snapshot_to_template

    return snapshot_to_template(snapshot_data, seed_template)


def _merge_snapshot_with_current(snapshot_data, current_settings):
    """Compatibility wrapper for managed snapshot/current merge."""
    from mms_claude.settings import merge_snapshot_with_current

    return merge_snapshot_with_current(snapshot_data, current_settings)


def _prune_session_only_snapshot_entries(snapshot_data):
    """Compatibility wrapper for pruning session-only snapshot entries."""
    from mms_claude.settings import prune_session_only_snapshot_entries

    return prune_session_only_snapshot_entries(snapshot_data)


def _sanitize_global_snapshot(snapshot_data):
    """Compatibility wrapper for global Claude snapshot sanitization."""
    from mms_claude.settings import sanitize_global_snapshot

    return sanitize_global_snapshot(snapshot_data)


def _managed_snapshot_differs(previous_snapshot, current_settings, seed_template):
    """Compatibility wrapper for managed Claude snapshot diffing."""
    from mms_claude.settings import managed_snapshot_differs

    return managed_snapshot_differs(previous_snapshot, current_settings, seed_template)


def _managed_snapshot_template(previous_snapshot, seed_template, current_settings):
    """Compatibility wrapper for managed Claude snapshot template building."""
    from mms_claude.settings import managed_snapshot_template

    return managed_snapshot_template(previous_snapshot, seed_template, current_settings)


def _load_global_claude_snapshot():
    """Compatibility wrapper for reading the global Claude managed snapshot."""
    from mms_claude.settings import load_global_claude_snapshot

    return load_global_claude_snapshot()


def _write_global_claude_snapshot(snapshot_data):
    """Compatibility wrapper for writing the global Claude managed snapshot."""
    from mms_claude.settings import write_global_claude_snapshot

    return write_global_claude_snapshot(snapshot_data)


def _merge_claude_settings(base_settings, template_settings):
    """Compatibility wrapper for Claude settings template merging."""
    from mms_claude.settings import merge_claude_settings

    return merge_claude_settings(base_settings, template_settings)


def _repair_real_claude_settings():
    import json as _json

    real_claude_dir = _real_user_path(".claude")
    os.makedirs(real_claude_dir, exist_ok=True)
    settings_path = os.path.join(real_claude_dir, "settings.json")
    current_settings = _load_real_claude_settings()
    seed_template = _load_global_claude_settings_template()
    previous_snapshot = _load_global_claude_snapshot()
    snapshot_data, managed_template = _managed_snapshot_template(
        previous_snapshot,
        seed_template,
        current_settings,
    )

    repaired = _merge_claude_settings(current_settings, managed_template)
    repaired = _sanitize_global_snapshot(repaired)
    repaired_snapshot = _sanitize_global_snapshot(
        _extract_managed_claude_snapshot(repaired, managed_template)
    )
    should_write = (
        _managed_snapshot_differs(previous_snapshot, current_settings, managed_template)
        or repaired_snapshot != snapshot_data
        or not os.path.exists(settings_path)
    )
    if should_write:
        with locked_state_file(settings_path):
            atomic_write_json(settings_path, repaired, mode=0o600)
    _write_global_claude_snapshot(repaired_snapshot)
    return repaired


def repair_real_claude_settings_for_startup():
    return _repair_real_claude_settings()


def repair_current_session_claude_settings(session_claude_dir):
    """Compatibility wrapper for session-local Claude settings repair."""
    from mms_claude.settings import repair_current_session_claude_settings as _repair_current

    return _repair_current(session_claude_dir)


def _strip_agent_im_hooks(hooks_data):
    """Compatibility wrapper for inherited Claude hook filtering."""
    from mms_claude.settings import strip_agent_im_hooks

    return strip_agent_im_hooks(hooks_data)


def _merge_claude_hook_groups(existing_groups, template_groups):
    """Compatibility wrapper for Claude hook-group merging."""
    from mms_claude.settings import merge_claude_hook_groups

    return merge_claude_hook_groups(existing_groups, template_groups)


def _merge_claude_hooks(existing_hooks, template_hooks):
    """Compatibility wrapper for Claude hook merging."""
    from mms_claude.settings import merge_claude_hooks

    return merge_claude_hooks(existing_hooks, template_hooks)


def _merge_claude_statusline(existing):
    """Compatibility wrapper for Claude statusline defaults."""
    from mms_claude.settings import merge_claude_statusline

    return merge_claude_statusline(existing)


def _merge_claude_permissions(existing):
    """Compatibility wrapper for Claude permissions defaults."""
    from mms_claude.settings import merge_claude_permissions

    return merge_claude_permissions(existing)


def _hook_command_exists(hook_items, command_path):
    """Compatibility wrapper for hook command lookup."""
    from mms_claude.settings import hook_command_exists

    return hook_command_exists(hook_items, command_path)


def _append_command_hook(hooks_data, event_name, command_path, matcher=None, timeout=None, status_message=None):
    """Compatibility wrapper for appending file-backed command hooks."""
    from mms_claude.settings import append_command_hook

    return append_command_hook(
        hooks_data,
        event_name,
        command_path,
        matcher=matcher,
        timeout=timeout,
        status_message=status_message,
    )


def _append_shell_command_hook(
    hooks_data,
    event_name,
    command_text,
    *,
    matcher=None,
    timeout=None,
    status_message=None,
):
    """Compatibility wrapper for appending shell command hooks."""
    from mms_claude.settings import append_shell_command_hook

    return append_shell_command_hook(
        hooks_data,
        event_name,
        command_text,
        matcher=matcher,
        timeout=timeout,
        status_message=status_message,
    )


def _merge_mms_session_hooks(existing_hooks, template_hooks=None):
    """Compatibility wrapper for MMS-managed Claude session hooks."""
    from mms_claude.settings import merge_mms_session_hooks

    return merge_mms_session_hooks(existing_hooks, template_hooks=template_hooks)


def _filter_claude_session_hooks(hooks_data, *, allow_execution_surfaces=True):
    """Compatibility wrapper for Claude session hook filtering."""
    from mms_claude.settings import filter_claude_session_hooks

    return filter_claude_session_hooks(
        hooks_data,
        allow_execution_surfaces=allow_execution_surfaces,
    )


def _caveman_available_for_cli(cli_name):
    return str(cli_name or "").strip() in {"claude", "codex", "opencode", "agy"} and bool(_resolve_caveman_root())


def _session_feature_root_kwargs():
    return {
        "module_file": __file__,
        "real_user_path_fn": _real_user_path,
        "asset_root_preference_fn": _asset_root_preference,
        "environ": os.environ,
    }


def _resolve_nsr_root():
    """Compatibility wrapper for NSR root resolution."""
    return _resolve_nsr_root_impl(**_session_feature_root_kwargs())


def _nsr_available_for_cli(cli_name):
    cli_name = str(cli_name or "").strip()
    if cli_name not in {"claude", "codex"}:
        return False
    wrapper = _NSR_CLAUDE_HOOK if cli_name == "claude" else _NSR_CODEX_HOOK
    return os.path.isfile(wrapper) and bool(_resolve_nsr_root() or os.path.isfile(_NSR_BUILTIN_HOOK))


def _normalize_nsr_mode(value, default="enable"):
    """Compatibility wrapper for NSR mode normalization."""
    return _normalize_nsr_mode_impl(value, default=default)


def _runtime_nsr_enabled(runtime):
    """Compatibility wrapper for runtime NSR enablement."""
    return _runtime_nsr_enabled_impl(runtime, normalize_nsr_mode_fn=_normalize_nsr_mode)


def _normalize_caveman_mode(value, default="disable"):
    """Compatibility wrapper for Caveman mode normalization."""
    return _normalize_caveman_mode_impl(value, default=default)


def _runtime_caveman_enabled(runtime):
    """Compatibility wrapper for runtime Caveman enablement."""
    return _runtime_caveman_enabled_impl(runtime, normalize_caveman_mode_fn=_normalize_caveman_mode)


def _normalize_caveman_level(value, default="light"):
    """Compatibility wrapper for Caveman intensity normalization."""
    return _normalize_caveman_level_impl(value, default=default)


def _runtime_caveman_level(runtime):
    """Compatibility wrapper for runtime Caveman intensity."""
    return _runtime_caveman_level_impl(runtime, normalize_caveman_level_fn=_normalize_caveman_level)


def _caveman_hook_mode(caveman_level):
    return {
        "light": "lite",
        "standard": "full",
        "full": "ultra",
    }.get(_normalize_caveman_level(caveman_level), "lite")


def _caveman_hook_env_prefix(caveman_level):
    return f"CAVEMAN_DEFAULT_MODE={shlex.quote(_caveman_hook_mode(caveman_level))} "


def _normalize_thinking_mode(value, default="enable"):
    """Compatibility wrapper for thinking mode normalization."""
    return _normalize_thinking_mode_impl(value, default=default)


def _runtime_thinking_enabled(runtime):
    """Compatibility wrapper for runtime thinking enablement."""
    return _runtime_thinking_enabled_impl(runtime, normalize_thinking_mode_fn=_normalize_thinking_mode)


def _normalize_reasoning_effort(value, default="high"):
    """Compatibility wrapper for reasoning effort normalization."""
    return _normalize_reasoning_effort_impl(value, default=default)


def _runtime_reasoning_effort(runtime, default="high"):
    """Compatibility wrapper for runtime reasoning effort."""
    return _runtime_reasoning_effort_impl(
        runtime,
        default=default,
        normalize_reasoning_effort_fn=_normalize_reasoning_effort,
    )


def _runtime_vision_sidecar(runtime):
    """Compatibility wrapper for runtime vision sidecar config."""
    return _runtime_vision_sidecar_impl(runtime)


def _resolve_native_fallback_routes(runtime, model_name):
    try:
        from mms_runtime.native_fallback import resolve_native_fallback_routes

        return resolve_native_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _resolve_codex_responses_fallback_routes(runtime, model_name):
    try:
        from mms_runtime.native_fallback import resolve_codex_responses_fallback_routes

        return resolve_codex_responses_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _is_installed_mms_layout(module_path=None):
    """Compatibility wrapper for installed MMS layout detection."""
    return _is_installed_mms_layout_impl(
        module_path=os.path.abspath(module_path or __file__),
        real_user_path_fn=_real_user_path,
    )


def _default_gpt_reasoning_effort(module_path=None):
    """Compatibility wrapper for default GPT reasoning effort policy."""
    return _default_gpt_reasoning_effort_impl(
        module_path=os.path.abspath(module_path or __file__),
        is_installed_mms_layout_fn=_is_installed_mms_layout,
    )


def _asset_root_preference(asset_name):
    """Compatibility wrapper for asset root preferences."""
    return _asset_root_preference_impl(asset_name, preference_asset_root_fn=preference_asset_root)


def _resolve_caveman_root():
    """Compatibility wrapper for Caveman root resolution."""
    return _resolve_caveman_root_impl(**_session_feature_root_kwargs())


def _ecc_available_for_claude():
    return bool(_resolve_ecc_root())


def _omc_available_for_claude():
    return bool(_resolve_omc_root())


def _normalize_ecc_mode(value, default="disable"):
    """Compatibility wrapper for ECC/OMC mode normalization."""
    return _normalize_ecc_mode_impl(value, default=default)


def _normalize_agent_pack(value, default="none"):
    """Compatibility wrapper for agent pack normalization."""
    return _normalize_agent_pack_impl(value, default=default)


def _runtime_agent_pack(runtime):
    """Compatibility wrapper for runtime agent pack selection."""
    return _runtime_agent_pack_impl(
        runtime,
        normalize_agent_pack_fn=_normalize_agent_pack,
        normalize_ecc_mode_fn=_normalize_ecc_mode,
    )


def _runtime_ecc_enabled(runtime):
    """Compatibility wrapper for runtime ECC enablement."""
    return _runtime_ecc_enabled_impl(runtime, runtime_agent_pack_fn=_runtime_agent_pack)


def _runtime_omc_enabled(runtime):
    """Compatibility wrapper for runtime OMC enablement."""
    return _runtime_omc_enabled_impl(runtime, runtime_agent_pack_fn=_runtime_agent_pack)


def _resolve_ecc_root():
    """Compatibility wrapper for ECC root resolution."""
    return _resolve_ecc_root_impl(**_session_feature_root_kwargs())


def _resolve_omc_root():
    """Compatibility wrapper for OMC root resolution."""
    return _resolve_omc_root_impl(**_session_feature_root_kwargs())


def _resolve_web_access_root():
    """Compatibility wrapper for web-access root resolution."""
    return _resolve_web_access_root_impl(**_session_feature_root_kwargs())


def _resolve_weber_root():
    """Compatibility wrapper for Weber root resolution."""
    return _resolve_weber_root_impl(**_session_feature_root_kwargs())


def _resolve_agent_browser_root():
    """Compatibility wrapper for Agent Browser root resolution."""
    return _resolve_agent_browser_root_impl(**_session_feature_root_kwargs())


def _resolve_codegraph_root():
    """Compatibility wrapper for CodeGraph skill root resolution."""
    return _resolve_codegraph_root_impl(**_session_feature_root_kwargs())


def _resolve_toon_root():
    """Compatibility wrapper for TOON root resolution."""
    return _resolve_toon_root_impl(**_session_feature_root_kwargs())


def _resolve_token_saver_root():
    """Compatibility wrapper for token-saver root resolution."""
    return _resolve_token_saver_root_impl(**_session_feature_root_kwargs())


def _resolve_xmem_root():
    """Compatibility wrapper for xmem root resolution."""
    return _resolve_xmem_root_impl(**_session_feature_root_kwargs())


def _xmem_cli_path():
    from mms_launcher.export import xmem_cli_path

    return xmem_cli_path(
        environ=os.environ,
        real_user_path=_real_user_path,
        which=shutil.which,
    )


def _resolve_auto_github_contributor_root():
    """Compatibility wrapper for auto-github-contributor root resolution."""
    return _resolve_auto_github_contributor_root_impl(**_session_feature_root_kwargs())


def _mms_toon_script_path():
    from mms_launcher.export import launcher_script_path

    return launcher_script_path(__file__, "mms-toon")


def _mms_context_script_path():
    from mms_launcher.export import launcher_script_path

    return launcher_script_path(__file__, "mms-context")


def _mms_gain_script_path():
    from mms_launcher.export import launcher_script_path

    return launcher_script_path(__file__, "mms-gain")


def _token_saver_script_path():
    from mms_launcher.export import launcher_script_path

    return launcher_script_path(__file__, "token-saver")


def _token_gain_script_path():
    from mms_launcher.export import launcher_script_path

    return launcher_script_path(__file__, "token-gain")


def _is_caveman_hook_command(command_text):
    """Compatibility wrapper for caveman hook command detection."""
    from mms_session.hook_commands import is_caveman_hook_command

    return is_caveman_hook_command(command_text)


def _is_codex_rtk_hook_command(command_text):
    """Compatibility wrapper for Codex RTK hook command detection."""
    from mms_session.hook_commands import is_codex_rtk_hook_command

    return is_codex_rtk_hook_command(command_text)


def _is_ecc_hook_command(command_text):
    """Compatibility wrapper for ECC hook command detection."""
    from mms_session.hook_commands import is_ecc_hook_command

    return is_ecc_hook_command(command_text)


def _is_omc_hook_command(command_text):
    """Compatibility wrapper for OMC hook command detection."""
    from mms_session.hook_commands import is_omc_hook_command

    return is_omc_hook_command(command_text)


def _is_mms_managed_hook_command(command_text):
    """Compatibility wrapper for MMS-managed hook command detection."""
    from mms_session.hook_commands import is_mms_managed_hook_command

    return is_mms_managed_hook_command(command_text)


def _is_legacy_loop_hook_command(command_text):
    """Compatibility wrapper for legacy loop hook command detection."""
    from mms_session.hook_commands import is_legacy_loop_hook_command

    return is_legacy_loop_hook_command(command_text)


def _is_nsr_hook_command(command_text):
    """Compatibility wrapper for NSR hook command detection."""
    from mms_session.hook_commands import is_nsr_hook_command

    return is_nsr_hook_command(command_text)


def _is_loop_family_hook_command(command_text):
    """Compatibility wrapper for loop-family hook command detection."""
    from mms_session.hook_commands import is_loop_family_hook_command

    return is_loop_family_hook_command(command_text)


def _hook_command_targets_exist(command_text):
    """Compatibility wrapper for hook command executable target checks."""
    from mms_session.hook_commands import hook_command_targets_exist

    return hook_command_targets_exist(command_text)


def _filter_missing_managed_hook_commands(hooks_data):
    """Compatibility wrapper for dropping missing managed hook commands."""
    from mms_claude.settings import filter_missing_managed_hook_commands

    return filter_missing_managed_hook_commands(hooks_data)


def _filter_hook_commands(hooks_data, predicate):
    """Compatibility wrapper for filtering hook commands."""
    from mms_claude.settings import filter_hook_commands

    return filter_hook_commands(hooks_data, predicate)


def _normalize_session_surface_disabled(disabled_session_surfaces):
    """Compatibility wrapper for disabled session-surface normalization."""
    from mms_claude.settings import normalize_session_surface_disabled

    return normalize_session_surface_disabled(disabled_session_surfaces)


def _session_surface_disabled(disabled_session_surfaces, surface, value):
    """Compatibility wrapper for disabled session-surface lookup."""
    from mms_claude.settings import session_surface_disabled

    return session_surface_disabled(disabled_session_surfaces, surface, value)


def _filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled MCP filtering."""
    from mms_claude.settings import filter_mcp_servers_by_disabled

    return filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces)


def _mcp_command_has_path(command):
    """Compatibility wrapper for MCP command path detection."""
    from mms_session.hook_commands import mcp_command_has_path

    return mcp_command_has_path(command)


def _normalize_session_mcp_server_spec(name, spec, *, env=None):
    """Make inherited MCP commands session-safe; drop missing local CLIs."""
    from mms_claude.settings import normalize_session_mcp_server_spec

    return normalize_session_mcp_server_spec(name, spec, env=env)


def _mcp_server_spec_has_entrypoint(spec):
    if not isinstance(spec, dict):
        return False
    url = spec.get("url")
    if isinstance(url, str) and url.strip():
        return True
    command = str(spec.get("command") or "").strip()
    return bool(command)


def _normalize_session_mcp_servers(mcp_servers, *, disabled_session_surfaces=None, env=None):
    """Compatibility wrapper for session MCP normalization."""
    from mms_claude.settings import normalize_session_mcp_servers

    return normalize_session_mcp_servers(
        mcp_servers,
        disabled_session_surfaces=disabled_session_surfaces,
        env=env,
    )


def _filter_hooks_by_disabled(hooks_data, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled hook filtering."""
    from mms_claude.settings import filter_hooks_by_disabled

    return filter_hooks_by_disabled(hooks_data, disabled_session_surfaces)


def _session_skill_disabled(disabled_session_surfaces, skill_name):
    """Compatibility wrapper for disabled skill lookup."""
    from mms_claude.settings import session_skill_disabled

    return session_skill_disabled(disabled_session_surfaces, skill_name)


def _caveman_claude_activate_command(caveman_root, caveman_level="light"):
    script_path = os.path.join(caveman_root, "hooks", "caveman-activate.js")
    return (
        _caveman_hook_env_prefix(caveman_level) +
        "CAVEMAN_HOOK_COMPACT=1 "
        "CAVEMAN_HOOK_EVENT=SessionStart "
        f"node {json.dumps(script_path)}"
    )


def _caveman_claude_tracker_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-mode-tracker.js")
    return f"node {json.dumps(script_path)}"


def _caveman_codex_activate_command(caveman_root, caveman_level="light"):
    """Compatibility wrapper for Codex caveman activation command."""
    from mms_codex.hooks import caveman_codex_activate_command

    return caveman_codex_activate_command(caveman_root, caveman_level=caveman_level)


def _caveman_codex_hook_payload(caveman_root, caveman_level="light"):
    """Compatibility wrapper for Codex caveman hook payload."""
    from mms_codex.hooks import caveman_codex_hook_payload

    return caveman_codex_hook_payload(caveman_root, caveman_level=caveman_level)


def _codex_shell_hook_payload(command_text, *, timeout=None, status_message=None):
    """Compatibility wrapper for Codex shell hook payload rendering."""
    from mms_codex.hooks import codex_shell_hook_payload

    return codex_shell_hook_payload(command_text, timeout=timeout, status_message=status_message)


def _codex_caveman_session_hook(caveman_root, caveman_level="light"):
    """Compatibility wrapper for Codex caveman session hook rendering."""
    from mms_codex.hooks import codex_caveman_session_hook

    return codex_caveman_session_hook(caveman_root, caveman_level=caveman_level)


def _configure_codex_caveman_hooks(hooks_data, *, enable_caveman=False, caveman_level="light"):
    """Compatibility wrapper for Codex caveman hook configuration."""
    from mms_codex.hooks import configure_codex_caveman_hooks

    return configure_codex_caveman_hooks(
        hooks_data,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
    )


def _configure_claude_nsr_hooks(hooks_data, *, enable_nsr=False):
    """Compatibility wrapper for Claude NSR hook configuration."""
    from mms_claude.settings import configure_claude_nsr_hooks

    return configure_claude_nsr_hooks(hooks_data, enable_nsr=enable_nsr)


def _configure_codex_nsr_hooks(hooks_data, *, enable_nsr=False):
    """Compatibility wrapper for Codex NSR hook configuration."""
    from mms_codex.hooks import configure_codex_nsr_hooks

    return configure_codex_nsr_hooks(hooks_data, enable_nsr=enable_nsr)


def _configure_claude_caveman_hooks(hooks_data, *, enable_caveman=False, caveman_level="light"):
    """Compatibility wrapper for Claude caveman hook configuration."""
    from mms_claude.settings import configure_claude_caveman_hooks

    return configure_claude_caveman_hooks(
        hooks_data,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
    )


def _load_ecc_claude_hooks():
    """Compatibility wrapper for ECC Claude hook loading."""
    from mms_claude.settings import load_claude_agent_pack_hooks

    return load_claude_agent_pack_hooks(_resolve_ecc_root())


def _load_omc_claude_hooks():
    """Compatibility wrapper for OMC Claude hook loading."""
    from mms_claude.settings import load_claude_agent_pack_hooks

    return load_claude_agent_pack_hooks(_resolve_omc_root())


def _configure_claude_ecc_hooks(hooks_data, *, enable_ecc=False):
    """Compatibility wrapper for Claude ECC hook configuration."""
    from mms_claude.settings import configure_claude_ecc_hooks

    return configure_claude_ecc_hooks(hooks_data, enable_ecc=enable_ecc)


def _configure_claude_omc_hooks(hooks_data, *, enable_omc=False):
    """Compatibility wrapper for Claude OMC hook configuration."""
    from mms_claude.settings import configure_claude_omc_hooks

    return configure_claude_omc_hooks(hooks_data, enable_omc=enable_omc)


def _build_codex_session_hooks(
    base_hooks=None,
    *,
    enable_caveman=False,
    caveman_level="light",
    enable_nsr=False,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for Codex session hook payload construction."""
    from mms_codex.hooks import build_codex_session_hooks

    return build_codex_session_hooks(
        base_hooks,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        enable_nsr=enable_nsr,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _codex_hook_event_state_key(event_name):
    """Compatibility wrapper for Codex hook event state keys."""
    from mms_codex.hook_trust import _codex_hook_event_state_key as codex_hook_event_state_key

    return codex_hook_event_state_key(event_name)


def _codex_hook_fingerprint(hook):
    """Compatibility wrapper for Codex hook fingerprinting."""
    from mms_codex.hook_trust import _codex_hook_fingerprint as codex_hook_fingerprint

    return codex_hook_fingerprint(hook)


def _codex_hook_index(hooks_payload):
    """Compatibility wrapper for Codex hook indexing."""
    from mms_codex.hook_trust import _codex_hook_index as codex_hook_index

    return codex_hook_index(hooks_payload)


def _decode_toml_basic_key(value):
    """Compatibility wrapper for TOML basic key decoding."""
    from mms_codex.hook_trust import _decode_toml_basic_key as decode_toml_basic_key

    return decode_toml_basic_key(value)


def _codex_hook_trust_records_from_config(config_text):
    """Compatibility wrapper for Codex hook trust record parsing."""
    from mms_codex.hook_trust import _codex_hook_trust_records_from_config as records_from_config

    return records_from_config(config_text)


def _normalize_codex_hook_trust_toml_layout(config_text):
    """Compatibility wrapper for Codex hook trust TOML layout cleanup."""
    from mms_codex.hook_trust import _normalize_codex_hook_trust_toml_layout as normalize_layout

    return normalize_layout(config_text)


def _replace_codex_hook_trust_hashes(config_text, trusted_hashes_by_key):
    """Compatibility wrapper for replacing Codex hook trust hashes."""
    from mms_codex.hook_trust import _replace_codex_hook_trust_hashes as replace_hashes

    return replace_hashes(config_text, trusted_hashes_by_key)


def _append_codex_exact_hook_trust_hashes(config_text, trusted_hashes_by_key):
    """Compatibility wrapper for appending exact Codex hook trust hashes."""
    from mms_codex.hook_trust import _append_codex_exact_hook_trust_hashes as append_hashes

    return append_hashes(config_text, trusted_hashes_by_key)


def _codex_hook_trust_refresh_enabled():
    """Compatibility wrapper for Codex hook trust refresh flag parsing."""
    from mms_codex.hook_trust import _codex_hook_trust_refresh_enabled as refresh_enabled

    return refresh_enabled()


def _codex_app_server_hooks_list(codex_home, *, cwds=None, timeout=4.0):
    """Compatibility wrapper for reading current Codex app-server hook hashes."""
    from mms_codex.hook_trust import _codex_app_server_hooks_list as app_server_hooks_list

    return app_server_hooks_list(codex_home, cwds=cwds, timeout=timeout)


def _refresh_codex_current_hook_trust_cache(
    target_codex_dir,
    *,
    cwds=None,
    managed_only=False,
    timeout=4.0,
    allow_non_real_home=False,
):
    """Compatibility wrapper for refreshing Codex hook trust cache."""
    from mms_codex.hook_trust import _refresh_codex_current_hook_trust_cache as refresh_cache

    return refresh_cache(
        target_codex_dir,
        cwds=cwds,
        managed_only=managed_only,
        timeout=timeout,
        allow_non_real_home=allow_non_real_home,
    )


def _collect_codex_hook_trust_seed_sources(codex_roots):
    """Compatibility wrapper for collecting Codex hook trust seed sources."""
    from mms_codex.hook_trust import _collect_codex_hook_trust_seed_sources as collect_seed_sources

    return collect_seed_sources(codex_roots)


def _append_codex_session_hook_trust_states(
    config_text,
    *,
    target_hooks_path,
    target_hooks,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    """Compatibility wrapper for Codex session hook trust state rendering."""
    from mms_codex.hook_trust import _append_codex_session_hook_trust_states as append_trust_states

    return append_trust_states(
        config_text,
        target_hooks_path=target_hooks_path,
        target_hooks=target_hooks,
        trust_config_texts=trust_config_texts,
        source_hook_payloads_by_path=source_hook_payloads_by_path,
    )


def _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, extra_source_root, *, exclude_names=None):
    """Compatibility wrapper for session entry overlays."""
    from mms_session.overlays import _overlay_session_entry_dir as overlay_session_entry_dir

    return overlay_session_entry_dir(
        parent_dir,
        overlay_root,
        entry_name,
        extra_source_root,
        exclude_names=exclude_names,
    )


def _overlay_session_skill_dir(parent_dir, overlay_root, skill_name, skill_root, *, disabled_session_surfaces=None):
    """Compatibility wrapper for session skill overlays."""
    from mms_session.overlays import _overlay_session_skill_dir as overlay_session_skill_dir

    return overlay_session_skill_dir(
        parent_dir,
        overlay_root,
        skill_name,
        skill_root,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_caveman_session_entries(parent_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None):
    """Compatibility wrapper for Caveman session overlays."""
    from mms_session.overlays import _overlay_caveman_session_entries as overlay_caveman_session_entries

    return overlay_caveman_session_entries(
        parent_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_ecc_session_entries(parent_dir, session_home, *, enable_ecc=False, disabled_session_surfaces=None):
    """Compatibility wrapper for ECC session overlays."""
    from mms_session.overlays import _overlay_ecc_session_entries as overlay_ecc_session_entries

    return overlay_ecc_session_entries(
        parent_dir,
        session_home,
        enable_ecc=enable_ecc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_omc_session_entries(parent_dir, session_home, *, enable_omc=False, disabled_session_surfaces=None):
    """Compatibility wrapper for OMC session overlays."""
    from mms_session.overlays import _overlay_omc_session_entries as overlay_omc_session_entries

    return overlay_omc_session_entries(
        parent_dir,
        session_home,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_web_access_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for web-access session overlays."""
    from mms_session.overlays import _overlay_web_access_session_entries as overlay_web_access_session_entries

    return overlay_web_access_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_weber_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for weber session overlays."""
    from mms_session.overlays import _overlay_weber_session_entries as overlay_weber_session_entries

    return overlay_weber_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_agent_browser_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for agent-browser session overlays."""
    from mms_session.overlays import _overlay_agent_browser_session_entries as overlay_agent_browser_session_entries

    return overlay_agent_browser_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_codegraph_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for CodeGraph session overlays."""
    from mms_session.overlays import _overlay_codegraph_session_entries as overlay_codegraph_session_entries

    return overlay_codegraph_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_toon_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for TOON session overlays."""
    from mms_session.overlays import _overlay_toon_session_entries as overlay_toon_session_entries

    return overlay_toon_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_xmem_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for xmem session overlays."""
    from mms_session.overlays import _overlay_xmem_session_entries as overlay_xmem_session_entries

    return overlay_xmem_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_token_saver_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for token-saver session overlays."""
    from mms_session.overlays import _overlay_token_saver_session_entries as overlay_token_saver_session_entries

    return overlay_token_saver_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_auto_github_contributor_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for auto-github-contributor session overlays."""
    from mms_session.overlays import _overlay_auto_github_contributor_session_entries as overlay_auto_gh_session_entries

    return overlay_auto_gh_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_agy_session_assets(
    account_home,
    session_home,
    *,
    enable_caveman=False,
    caveman_level="light",
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for AGY session plugin overlays."""
    from mms_agy.assets import overlay_agy_session_assets

    return overlay_agy_session_assets(
        account_home,
        session_home,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_opencode_session_assets(config_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None, runtime=None):
    return _overlay_opencode_session_assets_impl(
        config_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
        runtime=runtime,
        overlay_opencode_rtk_plugin=_overlay_opencode_rtk_plugin,
        overlay_caveman_session_entries=_overlay_caveman_session_entries,
        overlay_web_access_session_entries=_overlay_web_access_session_entries,
        overlay_weber_session_entries=_overlay_weber_session_entries,
        overlay_codegraph_session_entries=_overlay_codegraph_session_entries,
        overlay_toon_session_entries=_overlay_toon_session_entries,
        overlay_token_saver_session_entries=_overlay_token_saver_session_entries,
        overlay_xmem_session_entries=_overlay_xmem_session_entries,
        overlay_opencode_xmem_plugin=_overlay_opencode_xmem_plugin,
    )


def _configure_ecc_session_env(env_data, *, enable_ecc=False):
    """Compatibility wrapper for ECC session env configuration."""
    from mms_session.env import configure_ecc_session_env

    return configure_ecc_session_env(env_data, enable_ecc=enable_ecc)


def _configure_agent_pack_session_env(env_data, *, agent_pack="none"):
    """Compatibility wrapper for agent-pack session env configuration."""
    from mms_session.env import configure_agent_pack_session_env

    return configure_agent_pack_session_env(env_data, agent_pack=agent_pack)


def _session_required_env_from_runtime_env(env):
    """Compatibility wrapper for session-required runtime env extraction."""
    from mms_session.env import session_required_env_from_runtime_env

    return session_required_env_from_runtime_env(env)


def _sanitize_claude_inherited_settings_payload(settings_data, *, allow_execution_surfaces=True):
    """Compatibility wrapper for Claude settings inheritance allowlist."""
    from mms_claude.settings import sanitize_claude_inherited_settings_payload

    return sanitize_claude_inherited_settings_payload(
        settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
    )


def _sanitize_account_claude_settings_payload(settings_data):
    """Compatibility wrapper for account-scoped Claude settings sanitization."""
    from mms_claude.settings import sanitize_account_claude_settings_payload

    return sanitize_account_claude_settings_payload(settings_data)


def _default_session_mcp_servers():
    """Compatibility wrapper for default session MCP discovery."""
    from mms_claude.settings import default_session_mcp_servers

    return default_session_mcp_servers()


def _installed_claude_plugin_paths():
    plugins_root = _real_user_path(".claude", "plugins")
    installed_path = os.path.join(plugins_root, "installed_plugins.json")
    loaded = _load_json_dict_unlocked(installed_path)
    plugins = loaded.get("plugins") if isinstance(loaded, dict) else {}
    if not isinstance(plugins, dict):
        return []

    resolved_paths = []
    seen = set()
    for records in plugins.values():
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            install_path = os.path.abspath(
                os.path.expanduser(str(record.get("installPath") or "").strip())
            )
            if not install_path or install_path in seen:
                continue
            if not os.path.isdir(install_path):
                continue
            if not _path_under(install_path, plugins_root):
                continue
            seen.add(install_path)
            resolved_paths.append(install_path)
    return resolved_paths


def _installed_claude_plugin_mcp_manifest_paths(install_path):
    install_root = os.path.abspath(os.path.expanduser(str(install_path or "").strip()))
    if not install_root:
        return []

    candidates = []
    metadata_paths = (
        os.path.join(install_root, ".cursor-plugin", "plugin.json"),
        os.path.join(install_root, ".claude-plugin", "plugin.json"),
    )
    for metadata_path in metadata_paths:
        metadata = _load_json_dict_unlocked(metadata_path)
        manifest_rel = metadata.get("mcpServers")
        if not isinstance(manifest_rel, str) or not manifest_rel.strip():
            continue
        manifest_path = os.path.abspath(os.path.join(install_root, manifest_rel.strip()))
        if _path_under(manifest_path, install_root):
            candidates.append(manifest_path)

    candidates.append(os.path.join(install_root, ".mcp.json"))

    manifests = []
    seen = set()
    for candidate in candidates:
        normalized = os.path.abspath(os.path.expanduser(str(candidate or "").strip()))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            manifests.append(normalized)
    return manifests


def _installed_claude_plugin_mcp_servers():
    servers = {}
    for install_path in _installed_claude_plugin_paths():
        for manifest_path in _installed_claude_plugin_mcp_manifest_paths(install_path):
            payload = _load_json_dict_unlocked(manifest_path)
            plugin_servers = payload.get("mcpServers") if isinstance(payload, dict) else {}
            if not isinstance(plugin_servers, dict):
                continue
            for name, spec in plugin_servers.items():
                key = str(name or "").strip()
                if not key or key in servers or not _mcp_server_spec_has_entrypoint(spec):
                    continue
                servers[key] = copy.deepcopy(spec)
    return servers


def _enabled_real_codex_plugin_names():
    import re

    config_path = _real_user_path(".codex", "config.toml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return set()

    header_pattern = re.compile(
        r'^\[plugins\."((?:\\.|[^"\\])*)"\]\s*$',
        flags=re.MULTILINE,
    )
    matches = list(header_pattern.finditer(text))
    enabled = set()
    for index, match in enumerate(matches):
        plugin_id = _decode_toml_basic_key(match.group(1))
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[block_start:block_end]
        enabled_match = re.search(
            r'^\s*enabled\s*=\s*(true|false)\s*$',
            block,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if not enabled_match or enabled_match.group(1).lower() != "true":
            continue
        plugin_name = str(plugin_id or "").split("@", 1)[0].strip().lower()
        if plugin_name:
            enabled.add(plugin_name)
    return enabled


def _resolve_hive_root(module_path=None):
    """Compatibility wrapper for Hive MCP root discovery."""
    from mms_session.mcp import resolve_hive_root

    return resolve_hive_root(module_path=module_path)


def _default_hive_session_mcp_server():
    """Compatibility wrapper for default Hive session MCP server discovery."""
    from mms_session.mcp import default_hive_session_mcp_server

    return default_hive_session_mcp_server()


def _resolve_pilot_root(module_path=None):
    """Compatibility wrapper for Pilot MCP root discovery."""
    from mms_session.mcp import resolve_pilot_root

    return resolve_pilot_root(module_path=module_path)


def _default_pilot_session_mcp_server():
    """Compatibility wrapper for default Pilot session MCP server discovery."""
    from mms_session.mcp import default_pilot_session_mcp_server

    return default_pilot_session_mcp_server()


def _replace_plugin_root_tokens(value, plugin_root):
    """Compatibility wrapper for plugin MCP root token replacement."""
    from mms_session.mcp import replace_plugin_root_tokens

    return replace_plugin_root_tokens(value, plugin_root)


def _load_plugin_mcp_servers(plugin_root):
    """Compatibility wrapper for plugin MCP server loading."""
    from mms_session.mcp import load_plugin_mcp_servers

    return load_plugin_mcp_servers(plugin_root)


def _agent_pack_mcp_servers(agent_pack):
    """Compatibility wrapper for agent-pack MCP discovery."""
    from mms_claude.settings import agent_pack_mcp_servers

    return agent_pack_mcp_servers(agent_pack)


def _merge_agent_pack_mcp_servers(mcp_servers, *, agent_pack="none", disabled_session_surfaces=None):
    """Compatibility wrapper for agent-pack MCP merging."""
    from mms_claude.settings import merge_agent_pack_mcp_servers

    return merge_agent_pack_mcp_servers(
        mcp_servers,
        agent_pack=agent_pack,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _ensure_session_only_claude_mcp_servers(settings_data, *, disabled_session_surfaces=None):
    """Compatibility wrapper for session-only Claude MCP injection."""
    from mms_claude.settings import ensure_session_only_claude_mcp_servers

    return ensure_session_only_claude_mcp_servers(
        settings_data,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _session_managed_mcp_server_allowlist(*, allow_execution_surfaces=True):
    """Compatibility wrapper for session-managed MCP allowlist."""
    from mms_claude.settings import session_managed_mcp_server_allowlist

    return session_managed_mcp_server_allowlist(
        allow_execution_surfaces=allow_execution_surfaces
    )


def _session_managed_mcp_servers(settings_data, *, allow_execution_surfaces=True, disabled_session_surfaces=None):
    """Compatibility wrapper for session-managed Claude MCP collection."""
    from mms_claude.settings import session_managed_mcp_servers

    return session_managed_mcp_servers(
        settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _inject_managed_mcp_servers_into_claude_state(
    payload,
    settings_data=None,
    *,
    allow_execution_surfaces=True,
    disabled_session_surfaces=None,
    agent_pack="none",
):
    """Compatibility wrapper for Claude state managed MCP injection."""
    from mms_claude.settings import inject_managed_mcp_servers_into_claude_state

    return inject_managed_mcp_servers_into_claude_state(
        payload,
        settings_data=settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
        agent_pack=agent_pack,
    )


def _copy_allowed_scalar_fields(payload, allowed_keys):
    """Compatibility wrapper for scalar allowlist copies."""
    from mms_claude.state import copy_allowed_scalar_fields

    return copy_allowed_scalar_fields(payload, allowed_keys)


def _copy_allowed_scalar_dict_fields(payload, allowed_keys):
    """Compatibility wrapper for scalar dict allowlist copies."""
    from mms_claude.state import copy_allowed_scalar_dict_fields

    return copy_allowed_scalar_dict_fields(payload, allowed_keys)


def _sanitize_claude_ui_state_seed_payload(payload):
    """Compatibility wrapper for Claude UI state seed sanitization."""
    from mms_claude.state import sanitize_claude_ui_state_seed_payload

    return sanitize_claude_ui_state_seed_payload(payload)


def _merge_scalar_dict_entries(existing_payload, incoming_payload, *, prefer_max_numeric=False):
    """Compatibility wrapper for scalar dict merging."""
    from mms_claude.state import merge_scalar_dict_entries

    return merge_scalar_dict_entries(
        existing_payload,
        incoming_payload,
        prefer_max_numeric=prefer_max_numeric,
    )


def _merge_claude_ui_state_seed(target_payload, seed_payload):
    """Compatibility wrapper for Claude UI state seed merging."""
    from mms_claude.state import merge_claude_ui_state_seed

    return merge_claude_ui_state_seed(target_payload, seed_payload)


def _merge_claude_gateway_ui_state_payload(existing_payload, incoming_payload):
    """Compatibility wrapper for Claude gateway UI state merging."""
    from mms_claude.state import merge_claude_gateway_ui_state_payload

    return merge_claude_gateway_ui_state_payload(existing_payload, incoming_payload)


def _strip_claude_state_execution_surfaces(payload):
    """Compatibility wrapper for stripping execution surfaces from Claude state."""
    from mms_claude.state import strip_claude_state_execution_surfaces

    return strip_claude_state_execution_surfaces(payload)


def _sanitize_claude_project_state_entry(entry):
    """Compatibility wrapper for Claude project state entry sanitization."""
    from mms_claude.state import sanitize_claude_project_state_entry

    return sanitize_claude_project_state_entry(entry)


def _sanitize_claude_project_state_map(projects_data):
    """Compatibility wrapper for Claude project state map sanitization."""
    from mms_claude.state import sanitize_claude_project_state_map

    return sanitize_claude_project_state_map(projects_data)


def _load_real_claude_ui_state_seed():
    """Compatibility wrapper for reading real Claude UI state seed."""
    from mms_claude.state import load_real_claude_ui_state_seed

    return load_real_claude_ui_state_seed()


def _load_real_claude_project_state(project_path):
    """Compatibility wrapper for reading real Claude project state."""
    from mms_claude.state import load_real_claude_project_state

    return load_real_claude_project_state(project_path)


def _sanitize_oauth_claude_state_payload(data):
    """Compatibility wrapper for OAuth Claude state sanitization."""
    from mms_claude.state import sanitize_oauth_claude_state_payload

    return sanitize_oauth_claude_state_payload(data)


def _sanitize_codex_claude_state_payload(data):
    """Compatibility wrapper for Codex-seeded Claude state sanitization."""
    from mms_claude.state import sanitize_codex_claude_state_payload

    return sanitize_codex_claude_state_payload(data)


_CLAUDE_GATEWAY_SENSITIVE_STATE_KEYS = (
    "oauthAccount",
    "provider",
    "api_key",
    "userID",
    "cachedExtraUsageDisabledReason",
    "customApiKeyResponses",
    "passesEligibilityCache",
    "s1mAccessCache",
    "hasAvailableSubscription",
    "penguinModeOrgEnabled",
    "subscriptionNoticeCount",
)


def _strip_claude_restore_state(data, *, strip_sensitive_auth=False):
    """Compatibility wrapper for Claude restore-state stripping."""
    from mms_claude.state import strip_claude_restore_state

    return strip_claude_restore_state(data, strip_sensitive_auth=strip_sensitive_auth)


def _load_project_scoped_claude_resume_session_id(
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    """Compatibility wrapper for project-scoped Claude resume lookup."""
    from mms_claude.session import load_project_scoped_claude_resume_session_id

    return load_project_scoped_claude_resume_session_id(
        project_path,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )


def _overlay_project_scoped_claude_resume_state(
    data,
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    """Compatibility wrapper for project-scoped Claude resume state overlay."""
    from mms_claude.session import overlay_project_scoped_claude_resume_state

    return overlay_project_scoped_claude_resume_state(
        data,
        project_path,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )


def _ensure_claude_project_trust(
    data,
    project_path,
    project_state=None,
    *,
    allow_execution_surfaces=True,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for Claude project trust state materialization."""
    from mms_claude.state import ensure_claude_project_trust

    return ensure_claude_project_trust(
        data,
        project_path,
        project_state=project_state,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _copy_claude_state_json(src, dst, *, mode="restore"):
    """Compatibility wrapper for Claude state JSON copy/sanitization."""
    from mms_claude.state import copy_claude_state_json

    return copy_claude_state_json(src, dst, mode=mode)


def _parse_iso8601_utc(value):
    """Compatibility wrapper for OAuth token timestamp parsing."""
    from mms_claude.state import parse_iso8601_utc

    return parse_iso8601_utc(value)


def _merge_oauth_token_state(existing_payload, incoming_payload):
    """Compatibility wrapper for OAuth token state merging."""
    from mms_claude.state import merge_oauth_token_state

    return merge_oauth_token_state(existing_payload, incoming_payload)


def _merge_oauth_claude_state_payload(existing_data, incoming_data):
    """Compatibility wrapper for OAuth Claude state merging."""
    from mms_claude.state import merge_oauth_claude_state_payload

    return merge_oauth_claude_state_payload(existing_data, incoming_data)


def _masked_exposure_env_value(key, value):
    """Compatibility wrapper for exposure env masking."""
    from mms_runtime.exposure import masked_exposure_env_value

    return masked_exposure_env_value(key, value)


def inspect_runtime_exposure(cli, runtime):
    """Compatibility wrapper for runtime exposure audits."""
    from mms_runtime.exposure import inspect_runtime_exposure as inspect_runtime_exposure_impl

    return inspect_runtime_exposure_impl(cli, runtime)


def _build_claude_session_settings(
    base_settings=None,
    *,
    required_env=None,
    default_env=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    caveman_level="light",
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for Claude session settings materialization."""
    from mms_claude.settings import build_claude_session_settings

    return build_claude_session_settings(
        base_settings,
        required_env=required_env,
        default_env=default_env,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        enable_nsr=enable_nsr,
        enable_ecc=enable_ecc,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _write_claude_session_settings(
    session_claude_dir,
    *,
    required_env=None,
    default_env=None,
    base_settings=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    caveman_level="light",
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for writing session-local Claude settings."""
    from mms_claude.settings import write_claude_session_settings

    return write_claude_session_settings(
        session_claude_dir,
        required_env=required_env,
        default_env=default_env,
        base_settings=base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        enable_nsr=enable_nsr,
        enable_ecc=enable_ecc,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir):
    """Compatibility wrapper for OAuth session settings seeding."""
    from mms_claude.settings import seed_oauth_claude_session_settings

    return seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir)


def _gateway_ping(base_url, api_key, runtime=None):
    """Quick connectivity check; returns True/False/None (None = can't determine)."""
    _ensure_bridge_helpers()
    try:
        import httpx as _httpx  # noqa: F401
    except ImportError:
        return None
    if not base_url or not api_key:
        return None
    models_url = _build_gateway_url(base_url, "/models")
    headers = {"Authorization": f"Bearer {api_key}"}
    anthropic_base = str(_anthropic_base_url(runtime or {}) or "").strip().rstrip("/")
    if anthropic_base and anthropic_base == str(base_url or "").strip().rstrip("/"):
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    try:
        r = _runtime_httpx_request(
            "GET",
            models_url,
            runtime=runtime,
            headers=headers,
            timeout=8,
        )
        return 200 <= int(getattr(r, "status_code", 0) or 0) < 300
    except Exception:
        return False


def _load_gateway_health_cache():
    return _load_gateway_health_cache_impl(HEALTH_CHECK_PATH)


def _save_gateway_health_cache(providers):
    return _save_gateway_health_cache_impl(HEALTH_CHECK_PATH, providers)


def _health_check_due(provider_id):
    return _health_check_due_impl(_load_gateway_health_cache(), provider_id)


def gateway_health_check(provider):
    """Daily first-use connectivity check for gateway providers."""
    if provider.get("skip_gateway_health_check"):
        return
    provider_id = provider.get("id", "default")
    if not _health_check_due(provider_id):
        return
    base_url = _openai_base_url(provider) or _anthropic_base_url(provider)
    api_key = provider.get("api_key", "")
    ok = _gateway_ping(base_url, api_key, runtime=provider)
    if ok is None:
        return
    providers = _load_gateway_health_cache()
    providers[provider_id] = {
        "timestamp": datetime.now().isoformat(),
        "ok": bool(ok),
    }
    _save_gateway_health_cache(providers)
    if ok:
        console.print(f"[dim]✓ gateway {base_url} 可达[/dim]")
    else:
        console.print(f"[yellow]⚠ gateway {base_url} 健康检查未通过，连接可能不稳定[/yellow]")


def _provider_protocols(provider):
    """Compatibility wrapper for provider protocol normalization."""
    from mms_runtime.urls import provider_protocols

    return provider_protocols(provider)


def _provider_supports_cli(provider, cli):
    """Compatibility wrapper for provider CLI support validation."""
    from mms_runtime.validation import provider_supports_cli

    return provider_supports_cli(provider, cli)


def validate_provider_for_cli(cli, provider):
    """Compatibility wrapper for provider launch validation."""
    from mms_runtime.validation import validate_provider_for_cli as validate_provider_for_cli_impl

    return validate_provider_for_cli_impl(cli, provider)


def _scrub_claude_oauth_env(env):
    """Compatibility wrapper for Claude OAuth env scrubbing."""
    from mms_runtime.env import scrub_claude_oauth_env

    return scrub_claude_oauth_env(env)


def _scrub_inherited_runtime_env(env, *, strip_openai=False, strip_proxy=False):
    """Compatibility wrapper for inherited runtime env scrubbing."""
    from mms_runtime.env import scrub_inherited_runtime_env

    return scrub_inherited_runtime_env(
        env,
        strip_openai=strip_openai,
        strip_proxy=strip_proxy,
    )


def _account_env(account, *, validate_proxy=True, model_info=None):
    """Compatibility wrapper for OAuth/account runtime env materialization."""
    from mms_launcher.account_env import build_account_env

    return build_account_env(
        account,
        validate_proxy=validate_proxy,
        model_info=model_info,
    )


def _overlay_codex_shared_resume(home_dir, session_home):
    """Compatibility wrapper for account Codex shared-resume overlay."""
    from mms_codex.assets import overlay_codex_shared_resume

    return overlay_codex_shared_resume(home_dir, session_home)


_CODEX_BOUNDED_RESUME_FILES = {
    "history.jsonl": 200,
    "session_index.jsonl": 50,
}

_CODEX_BOUNDED_RESUME_DIRS = {
    "sessions": 25,
    "shell_snapshots": 20,
    "archived_sessions": 0,
}

_CODEX_RESUME_SEED_MANIFEST = "mms-resume-seed.json"
_CODEX_RESUME_WRITEBACK_MANIFEST = "mms-resume-writeback.json"
_CODEX_RESUME_WRITEBACK_ROOT_ENV = "MMS_CODEX_RESUME_WRITEBACK_ROOT"
_CODEX_RESUME_MAX_FILE_BYTES = 2_000_000
_CODEX_RESUME_PROJECT_MAX_FILE_BYTES = 32_000_000
_CODEX_COPY_INTO_SESSION_FILES = {"installation_id"}
_CODEX_PLUGIN_MARKETPLACE_CACHE_ENTRIES = (
    "plugins",
    "plugins.sha",
    "bundled-marketplaces",
)
_CODEX_SESSION_LOCAL_ONLY_ENTRIES = {
    ".codex-global-state.json",
    ".tmp",
    "models_cache.json",
    "version.json",
    "sqlite",
    "tmp",
    "app-server-control",
    "app-server-daemon",
}
_CODEX_SESSION_LOCAL_ONLY_PREFIXES = (
    ".codex-global-state.json.",
    ".codex-global-state.json.tmp-",
    "app-server-",
)


def _materialize_codex_session_entry(entry, src, dst):
    """Compatibility wrapper for Codex session entry materialization."""
    from mms_codex.assets import materialize_codex_session_entry

    return materialize_codex_session_entry(entry, src, dst)


def _overlay_codex_plugin_marketplace_cache(session_codex_dir, source_codex_dirs):
    """Compatibility wrapper for Codex marketplace cache overlay."""
    from mms_codex.assets import overlay_codex_plugin_marketplace_cache

    return overlay_codex_plugin_marketplace_cache(session_codex_dir, source_codex_dirs)


def _codex_entry_is_session_local(entry):
    """Compatibility wrapper for Codex session-local entry filtering."""
    from mms_codex.assets import codex_entry_is_session_local

    return codex_entry_is_session_local(entry)


def _bounded_env_int(name, default):
    """Compatibility wrapper for bounded integer env parsing."""
    from mms_codex.resume import _bounded_env_int as bounded_env_int

    return bounded_env_int(name, default)


def _first_existing_child(source_roots, entry_name, *, want_dir=False):
    """Compatibility wrapper for first bounded-resume child lookup."""
    from mms_codex.resume import _first_existing_child as first_existing_child

    return first_existing_child(source_roots, entry_name, want_dir=want_dir)


def _existing_children(source_roots, entry_name, *, want_dir=False):
    """Compatibility wrapper for bounded-resume child lookup."""
    from mms_codex.resume import _existing_children as existing_children

    return existing_children(source_roots, entry_name, want_dir=want_dir)


def _copy_tail_lines(src, dst, max_lines):
    """Compatibility wrapper for bounded resume tail copy."""
    from mms_codex.resume import _copy_tail_lines as copy_tail_lines

    return copy_tail_lines(src, dst, max_lines)


def _safe_relative_path(root, path):
    """Compatibility wrapper for bounded resume relative paths."""
    from mms_codex.resume import _safe_relative_path as safe_relative_path

    return safe_relative_path(root, path)


def _codex_session_file_cwd(path):
    """Compatibility wrapper for Codex session-file cwd extraction."""
    from mms_codex.resume import _codex_session_file_cwd as codex_session_file_cwd

    return codex_session_file_cwd(path)


def _path_is_same_or_child(path, root):
    """Compatibility wrapper for same-or-child path checks."""
    from mms_codex.resume import _path_is_same_or_child as path_is_same_or_child

    return path_is_same_or_child(path, root)


def _copy_latest_files_from_roots(src_roots, dst_root, max_files, *, max_file_bytes, project_path=""):
    """Compatibility wrapper for bounded resume latest-file copy."""
    from mms_codex.resume import _copy_latest_files_from_roots as copy_latest_files_from_roots

    return copy_latest_files_from_roots(
        src_roots,
        dst_root,
        max_files,
        max_file_bytes=max_file_bytes,
        project_path=project_path,
    )


def _copy_latest_files(src_root, dst_root, max_files, *, max_file_bytes):
    """Compatibility wrapper for bounded resume latest-file copy."""
    from mms_codex.resume import _copy_latest_files as copy_latest_files

    return copy_latest_files(src_root, dst_root, max_files, max_file_bytes=max_file_bytes)


def _codex_sibling_session_roots(sessions_dir, *, exclude_session_home="", max_roots=None):
    """Compatibility wrapper for Codex sibling session roots."""
    from mms_codex.resume import _codex_sibling_session_roots as codex_sibling_session_roots

    return codex_sibling_session_roots(
        sessions_dir,
        exclude_session_home=exclude_session_home,
        max_roots=max_roots,
    )


def _seed_codex_bounded_resume(source_roots, session_codex_dir):
    """Compatibility wrapper for Codex bounded resume seeding."""
    from mms_codex.resume import _seed_codex_bounded_resume as seed_codex_bounded_resume

    return seed_codex_bounded_resume(source_roots, session_codex_dir)


def _set_codex_resume_writeback_root(env, target_codex_dir):
    """Compatibility wrapper for Codex resume write-back env injection."""
    from mms_codex.resume import _set_codex_resume_writeback_root as set_writeback_root

    return set_writeback_root(env, target_codex_dir)


def _mms_resume_command_name():
    return "mms"


def _print_mms_resume_hint(cli_name, session_id):
    """Compatibility wrapper for MMS resume hint display."""
    from mms_display.launch import print_mms_resume_hint

    return print_mms_resume_hint(
        cli_name,
        session_id,
        resume_command_name_fn=_mms_resume_command_name,
        console=console,
    )


def _codex_index_records(codex_dir):
    """Compatibility wrapper for Codex bounded index records."""
    from mms_codex.resume import _codex_index_records as codex_index_records

    return codex_index_records(codex_dir)


def _codex_resume_record_fingerprint(record):
    """Compatibility wrapper for Codex resume record fingerprints."""
    from mms_codex.resume import _codex_resume_record_fingerprint as resume_record_fingerprint

    return resume_record_fingerprint(record)


def _codex_resume_index_snapshot(codex_dir):
    """Compatibility wrapper for Codex resume index snapshots."""
    from mms_codex.resume import _codex_resume_index_snapshot as resume_index_snapshot

    return resume_index_snapshot(codex_dir)


def _codex_resume_sort_key(record):
    """Compatibility wrapper for Codex resume sort keys."""
    from mms_codex.resume import _codex_resume_sort_key as resume_sort_key

    return resume_sort_key(record)


def _codex_resume_hint_session_id(codex_dir, baseline_snapshot):
    """Compatibility wrapper for Codex resume hint session selection."""
    from mms_codex.resume import _codex_resume_hint_session_id as resume_hint_session_id

    return resume_hint_session_id(codex_dir, baseline_snapshot)


def _merge_tail_lines(src, dst, max_lines):
    """Compatibility wrapper for Codex bounded resume tail merge."""
    from mms_codex.resume import _merge_tail_lines as merge_tail_lines

    return merge_tail_lines(src, dst, max_lines)


def _copy_resume_dir_back(src_root, dst_root, max_files, *, max_file_bytes):
    """Compatibility wrapper for Codex bounded resume dir write-back."""
    from mms_codex.resume import _copy_resume_dir_back as copy_resume_dir_back

    return copy_resume_dir_back(src_root, dst_root, max_files, max_file_bytes=max_file_bytes)


def _sync_codex_bounded_resume_back(session_codex_dir, target_codex_dir):
    """Compatibility wrapper for Codex bounded resume write-back."""
    from mms_codex.resume import _sync_codex_bounded_resume_back as sync_bounded_resume_back

    return sync_bounded_resume_back(session_codex_dir, target_codex_dir)


def _write_codex_hook_trust_cache(
    target_codex_dir,
    hooks_payload,
    *,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    """Compatibility wrapper for writing Codex hook trust cache."""
    from mms_codex.hook_trust import _write_codex_hook_trust_cache as write_hook_trust_cache

    return write_hook_trust_cache(
        target_codex_dir,
        hooks_payload,
        trust_config_texts=trust_config_texts,
        source_hook_payloads_by_path=source_hook_payloads_by_path,
    )


def _sync_codex_hook_trust_back(session_codex_dir, target_codex_dir):
    """Compatibility wrapper for syncing Codex hook trust back to durable cache."""
    from mms_codex.hook_trust import _sync_codex_hook_trust_back as sync_hook_trust_back

    return sync_hook_trust_back(session_codex_dir, target_codex_dir)


def _sync_codex_bounded_resume_back_from_env(env):
    """Compatibility wrapper for env-driven Codex bounded resume write-back."""
    from mms_codex.resume import _sync_codex_bounded_resume_back_from_env as sync_from_env

    return sync_from_env(env)


def _codex_resume_writeback_callback(env):
    """Compatibility wrapper for Codex resume write-back callback."""
    from mms_codex.resume import _codex_resume_writeback_callback as resume_writeback_callback

    return resume_writeback_callback(env)


def _codex_bounded_resume_entries():
    """Compatibility wrapper for Codex bounded resume entry names."""
    from mms_codex.resume import _codex_bounded_resume_entries as bounded_resume_entries

    return bounded_resume_entries()


def _link_shared_dotfiles(session_home):
    """Compatibility wrapper for shared dotfile links in session homes."""
    from mms_session.assets import link_shared_dotfiles

    return link_shared_dotfiles(session_home)


def _link_real_local_bin(session_home):
    """Compatibility wrapper for exposing real ~/.local/bin in Claude sessions."""
    from mms_claude.session import link_real_local_bin

    return link_real_local_bin(session_home)


def _link_claude_library_entries(session_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for Claude session Library allowlist links."""
    from mms_claude.session import link_claude_library_entries

    return link_claude_library_entries(session_home, entries=entries)


def _ensure_account_library_entries(account_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for account Library allowlist preparation."""
    from mms_claude.session import ensure_account_library_entries

    return ensure_account_library_entries(account_home, entries=entries)


def _macos_security_bin():
    """Compatibility wrapper for macOS security binary discovery."""
    from mms_agy.security import macos_security_bin

    return macos_security_bin()


def _agy_keychain_path(account_home):
    """Compatibility wrapper for AGY account keychain path."""
    from mms_agy.security import agy_keychain_path

    return agy_keychain_path(account_home)


def _agy_security_home_env(security_home):
    """Compatibility wrapper for AGY security command env."""
    from mms_agy.security import agy_security_home_env

    return agy_security_home_env(security_home)


def _run_agy_security_command(security_bin, args, *, security_home, check=False):
    """Compatibility wrapper for AGY security command execution."""
    from mms_agy.security import run_agy_security_command

    return run_agy_security_command(
        security_bin,
        args,
        security_home=security_home,
        check=check,
    )


def _ensure_agy_account_keychain(account_home, session_home=None):
    """Compatibility wrapper for AGY account keychain preparation."""
    from mms_agy.security import ensure_agy_account_keychain

    return ensure_agy_account_keychain(account_home, session_home=session_home)


def _install_agy_security_wrapper(session_home, account_home, env):
    """Compatibility wrapper for AGY session security wrapper install."""
    from mms_agy.security import install_agy_security_wrapper

    return install_agy_security_wrapper(session_home, account_home, env)


def _link_account_library_entries(session_home, account_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for account Library links into session homes."""
    from mms_claude.session import link_account_library_entries

    return link_account_library_entries(session_home, account_home, entries=entries)


def _filter_real_home_wrapper_path(path_value, *, session_home=None):
    from mms_launcher.export import filter_real_home_wrapper_path

    return filter_real_home_wrapper_path(
        path_value,
        session_home=session_home,
        real_user_home=_real_user_home,
        environ=os.environ,
    )


def _dedupe_path_parts(parts):
    from mms_launcher.export import dedupe_path_parts

    return dedupe_path_parts(parts)


def _real_home_wrapper_search_path(session_home, env=None):
    from mms_launcher.export import real_home_wrapper_search_path

    return real_home_wrapper_search_path(
        session_home,
        env,
        real_user_home=_real_user_home,
        environ=os.environ,
        filter_real_home_wrapper_path=_filter_real_home_wrapper_path,
        dedupe_path_parts=_dedupe_path_parts,
        cli_search_dirs=cli_search_dirs,
    )


def _write_real_home_script(path, lines):
    from mms_launcher.export import write_real_home_script

    return write_real_home_script(path, lines)


def _install_chrome_host_wrapper(wrapper_dir, env, wrapper_path_env):
    from mms_launcher.export import install_chrome_host_wrapper

    return install_chrome_host_wrapper(
        wrapper_dir,
        env,
        wrapper_path_env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
    )


def _install_session_command_wrappers(session_home, env):
    from mms_launcher.export import install_session_command_wrappers

    return install_session_command_wrappers(
        session_home,
        env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
        install_chrome_host_wrapper=_install_chrome_host_wrapper,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        mms_gain_script_path=_mms_gain_script_path,
        token_saver_script_path=_token_saver_script_path,
        token_gain_script_path=_token_gain_script_path,
        xmem_cli_path=_xmem_cli_path,
    )


def _resolve_real_home_command_path(command_name, env=None):
    """Compatibility wrapper for real-home command lookup."""
    from mms_launcher.export import resolve_real_home_command_path

    return resolve_real_home_command_path(
        command_name,
        env,
        environ=os.environ,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        which=shutil.which,
        defpath=os.defpath,
    )


def _exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    """Compatibility wrapper for OAuth Claude manual-only hard cut."""
    from mms_launcher.mmc import exit_oauth_claude_manual_only

    return exit_oauth_claude_manual_only(runtime, model_info, caller=caller)


def _sync_codex_session_claude_json(session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for Codex session Claude-state seeding."""
    from mms_codex.claude_state import sync_codex_session_claude_json

    return sync_codex_session_claude_json(
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _toml_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return _toml_quote(value)


def _toml_bare_key(key):
    import re
    if re.fullmatch(r"[A-Za-z0-9_-]+", str(key)):
        return str(key)
    escaped = str(key).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled Codex MCP block stripping."""
    from mms_codex.claude_state import strip_codex_mcp_server_blocks

    return strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces)


def _append_codex_mcp_servers_from_claude_json(config_text, *, disabled_session_surfaces=None):
    """Compatibility wrapper for Claude MCP -> Codex config rendering."""
    from mms_codex.claude_state import append_codex_mcp_servers_from_claude_json

    return append_codex_mcp_servers_from_claude_json(
        config_text,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def validate_account_for_cli(cli, account):
    """Compatibility wrapper for account launch validation."""
    from mms_runtime.validation import validate_account_for_cli as validate_account_for_cli_impl

    return validate_account_for_cli_impl(cli, account)


def _openai_base_url(provider):
    """Compatibility wrapper for effective OpenAI base URL."""
    from mms_runtime.urls import openai_base_url

    return openai_base_url(provider)


def _anthropic_base_url(provider):
    """Compatibility wrapper for effective Anthropic base URL."""
    from mms_runtime.urls import anthropic_base_url

    return anthropic_base_url(provider)


def _anthropic_probe_target(runtime):
    """Compatibility wrapper for Anthropic probe target derivation."""
    from mms_runtime.urls import anthropic_probe_target

    return anthropic_probe_target(runtime)


def _resolve_model(model_info):
    """Compatibility wrapper for runtime model extraction."""
    from mms_runtime.models import resolve_model

    return resolve_model(model_info)


def _normalized_model_name(model_name):
    """Compatibility wrapper for model-name normalization."""
    from mms_runtime.models import normalized_model_name

    return normalized_model_name(model_name)


def _is_claude_family_model_name(model_name):
    """Compatibility wrapper for Claude family model detection."""
    from mms_claude.model import is_claude_family_model_name

    return is_claude_family_model_name(model_name)


def _claude_visible_model_name(model_name, *, fallback_model=""):
    """Compatibility wrapper for Claude-visible model slot names."""
    from mms_claude.model import claude_visible_model_name

    return claude_visible_model_name(model_name, fallback_model=fallback_model)


def _apply_claude_visible_model_overrides(target, model_name, *, fallback_model=""):
    """Compatibility wrapper for Claude-visible model overrides."""
    from mms_claude.model import apply_claude_visible_model_overrides

    return apply_claude_visible_model_overrides(target, model_name, fallback_model=fallback_model)


def _claude_resume_model_name(*candidates):
    """Compatibility wrapper for Claude resume model normalization."""
    from mms_claude.model import claude_resume_model_name

    return claude_resume_model_name(*candidates)


def _with_1m_suffix(model_name, *, enable_1m=True):
    """Compatibility wrapper for Claude 1M model suffixing."""
    from mms_claude.model import with_1m_suffix

    return with_1m_suffix(model_name, enable_1m=enable_1m)


def _apply_claude_model_overrides(target, model_info, *, enable_1m=True):
    """Compatibility wrapper for Claude model env overrides."""
    from mms_claude.model import apply_claude_model_overrides

    return apply_claude_model_overrides(target, model_info, enable_1m=enable_1m)


def launch_claude(model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the Claude launch flow."""
    from mms_claude.launch import launch_claude_runtime

    return launch_claude_runtime(
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
    )



def _resolve_anthropic_base_url(runtime, probe_model="claude-sonnet-4-6"):
    """Compatibility wrapper for Claude Anthropic endpoint resolution."""
    from mms_claude.endpoint import resolve_anthropic_base_url

    return resolve_anthropic_base_url(runtime, probe_model=probe_model)


def _pick_gateway_model(runtime, base_url):
    """Compatibility wrapper for Claude gateway model selection."""
    from mms_claude.endpoint import pick_gateway_model

    return pick_gateway_model(runtime, base_url)


def _cleanup_stale_sessions(sessions_dir, stale_callback=None, *, max_entries=None, max_seconds=None):
    """Compatibility wrapper for Claude stale session cleanup."""
    from mms_claude.session import cleanup_stale_sessions

    return cleanup_stale_sessions(
        sessions_dir,
        stale_callback=stale_callback,
        max_entries=max_entries,
        max_seconds=max_seconds,
    )


def _copy_tree_files_if_missing(src, dst):
    """Compatibility wrapper for Claude session tree backfill copies."""
    from mms_claude.session import copy_tree_files_if_missing

    return copy_tree_files_if_missing(src, dst)


def _claude_project_resume_dir_names(project_path):
    """Compatibility wrapper for Claude project resume dir names."""
    from mms_claude.session import claude_project_resume_dir_names

    return claude_project_resume_dir_names(project_path)


def _claude_resume_scope_id(runtime_id="", *, runtime_kind="api_key", resume_model=""):
    """Compatibility wrapper for Claude resume storage scope."""
    from mms_claude.session import claude_resume_scope_id

    return claude_resume_scope_id(
        runtime_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )


def _claude_resume_scope_is_model_shared(scope_id):
    """Compatibility wrapper for Claude model-shared resume scopes."""
    from mms_claude.session import claude_resume_scope_is_model_shared

    return claude_resume_scope_is_model_shared(scope_id)


def _claude_slot_roots_for_resume_backfill(account_id):
    """Compatibility wrapper for Claude resume backfill roots."""
    from mms_claude.session import claude_slot_roots_for_resume_backfill

    return claude_slot_roots_for_resume_backfill(account_id)


def _backfill_real_claude_project_resume_files(target_projects_dir, current_cwd):
    """Compatibility wrapper for real Claude project resume backfill."""
    from mms_claude.session import backfill_real_claude_project_resume_files

    return backfill_real_claude_project_resume_files(target_projects_dir, current_cwd)


def _backfill_claude_project_resume_files(
    target_projects_dir,
    current_cwd,
    account_id,
    current_session_home="",
    legacy_account_ids=None,
    resume_model="",
):
    """Compatibility wrapper for Claude project resume backfill."""
    from mms_claude.session import backfill_claude_project_resume_files

    return backfill_claude_project_resume_files(
        target_projects_dir,
        current_cwd,
        account_id,
        current_session_home=current_session_home,
        legacy_account_ids=legacy_account_ids,
        resume_model=resume_model,
    )


def _link_claude_persistent_entry(session_claude_dir, entry, target):
    """Compatibility wrapper for Claude persistent entry links."""
    from mms_claude.session import link_claude_persistent_entry

    return link_claude_persistent_entry(session_claude_dir, entry, target)


def _prepare_claude_session_tree(
    session_home,
    session_claude_dir,
    *,
    account_id="",
    account_home="",
    runtime_kind="api_key",
    resume_model="",
    resume_scope_id="",
    legacy_resume_scope_ids=None,
    skip_real_entries=None,
    source_claude_dir=None,
    allowed_source_entries=None,
):
    """Compatibility wrapper for Claude session tree materialization."""
    from mms_claude.session import prepare_claude_session_tree

    return prepare_claude_session_tree(
        session_home,
        session_claude_dir,
        account_id=account_id,
        account_home=account_home,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
        resume_scope_id=resume_scope_id,
        legacy_resume_scope_ids=legacy_resume_scope_ids,
        skip_real_entries=skip_real_entries,
        source_claude_dir=source_claude_dir,
        allowed_source_entries=allowed_source_entries,
    )


def _sync_claude_session_state_to_account_home(session_home, account_home, *, state_mode="oauth"):
    """Compatibility wrapper for Claude session state sync."""
    from mms_claude.session import sync_claude_session_state_to_account_home

    return sync_claude_session_state_to_account_home(
        session_home,
        account_home,
        state_mode=state_mode,
    )


def _finalize_claude_slot(session_home, exit_code=None, stale_cleanup=False):
    """Compatibility wrapper for Claude slot finalization."""
    from mms_claude.session import finalize_claude_slot

    return finalize_claude_slot(session_home, exit_code=exit_code, stale_cleanup=stale_cleanup)


def _claude_gateway_env(
    runtime,
    base_url=None,
    auth_token=None,
    heavy_model=None,
    medium_model=None,
    light_model=None,
    selected_model=None,
    runtime_kind=None,
    display_model=None,
    _timings=None,
):
    """Compatibility wrapper for Claude gateway env materialization."""
    from mms_claude.env import build_claude_gateway_env

    return build_claude_gateway_env(
        runtime,
        base_url=base_url,
        auth_token=auth_token,
        heavy_model=heavy_model,
        medium_model=medium_model,
        light_model=light_model,
        selected_model=selected_model,
        runtime_kind=runtime_kind,
        display_model=display_model,
        _timings=_timings,
    )



def _codex_gateway_env(runtime, base_url, model_info=None):
    """Compatibility wrapper for Codex gateway env materialization."""
    from mms_codex.env import build_codex_gateway_env

    return build_codex_gateway_env(runtime, base_url, model_info=model_info)

def _is_gpt_model(model_name):
    """Check if a model name is a GPT/OpenAI model (supports Responses API natively)."""
    if not model_name:
        return False
    lower = model_name.lower()
    return any(kw in lower for kw in ("gpt-", "gpt4", "gpt5", "o1", "o3", "o4", "codex-"))


def _codex_provider_base_url(base_url):
    normalized = (base_url or "").rstrip("/")
    if normalized and not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized


def _append_codex_bypass_flags(cmd, runtime):
    """In MMS bypass mode, skip Codex approval and hook-review prompts together."""
    # Contract: isolated MMS/Codex sessions must not stop at startup hook review.
    if not (runtime or {}).get("bypass"):
        return
    for flag in (
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
    ):
        if flag not in cmd:
            cmd.append(flag)


def launch_codex(model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the Codex launch flow."""
    from mms_codex.launch import launch_codex_runtime

    return launch_codex_runtime(
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
    )



def _opencode_run_preflight(env, agent, model_ref, timeout=None, bypass=True):
    return _opencode_run_preflight_impl(
        env,
        agent,
        model_ref,
        timeout=timeout,
        bypass=bypass,
        subprocess_run=subprocess.run,
        perf_counter_fn=perf_counter,
        preflight_timeout=_opencode_preflight_timeout,
    )


def _opencode_select_launch_candidate(runtime, routes, model, env):
    return _opencode_select_launch_candidate_impl(
        runtime,
        routes,
        model,
        env,
        launch_candidates=_opencode_launch_candidates,
        launch_preflight_enabled=_opencode_launch_preflight_enabled,
        run_preflight=_opencode_run_preflight,
        bypass_enabled=_opencode_bypass_enabled,
        console=console,
    )


def _opencode_gateway_health_check(runtime):
    return _opencode_gateway_health_check_impl(
        runtime,
        runtime_routes=_opencode_runtime_routes,
        resolve_model=_resolve_model,
        provider_base_url=_opencode_provider_base_url,
        gateway_health_check=gateway_health_check,
    )


def _opencode_model_config(runtime, model_name):
    return _opencode_model_config_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _opencode_rtk_plugin_path(runtime=None):
    return _opencode_rtk_plugin_path_impl(
        runtime,
        module_file=__file__,
        normalize_session_surface_disabled=_normalize_session_surface_disabled,
        runtime_bool=_opencode_runtime_bool,
        env_bool=_opencode_env_bool,
    )


def _opencode_xmem_plugin_path(runtime=None):
    return _opencode_xmem_plugin_path_impl(
        runtime,
        module_file=__file__,
        normalize_session_surface_disabled=_normalize_session_surface_disabled,
        session_skill_disabled=_session_skill_disabled,
        resolve_xmem_root=_resolve_xmem_root,
        xmem_cli_path=_xmem_cli_path,
    )


def _overlay_opencode_rtk_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_rtk_plugin_path(runtime),
        "mms-rtk.ts",
    )


def _overlay_opencode_xmem_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_xmem_plugin_path(runtime),
        "mms-xmem.ts",
    )


def _opencode_rtk_plugin_enabled(runtime=None):
    return bool(_opencode_rtk_plugin_path(runtime))


def _opencode_xmem_plugin_enabled(runtime=None):
    return bool(_opencode_xmem_plugin_path(runtime))


def _build_opencode_config_payload(runtime, model_name=""):
    return _opencode_build_config_payload_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _build_opencode_config_content(runtime, model_name=""):
    return _opencode_build_config_content_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _write_opencode_config(path, runtime, model):
    return _opencode_write_config_impl(
        path,
        runtime,
        model,
        build_config_content=_build_opencode_config_content,
        atomic_write_text=atomic_write_text,
    )


def _opencode_export_config_path(runtime, model):
    return _opencode_export_config_path_impl(
        runtime,
        model,
        real_user_path=_real_user_path,
    )


def _opencode_gateway_env(runtime, model_info=None):
    return _opencode_gateway_env_impl(
        runtime,
        model_info=model_info,
        resolve_model=_resolve_model,
        real_user_path=_real_user_path,
        cleanup_stale_sessions=_cleanup_stale_sessions,
        link_shared_dotfiles=_link_shared_dotfiles,
        scrub_inherited_runtime_env=_scrub_inherited_runtime_env,
        clear_opencode_config_env=_clear_opencode_config_env,
        inject_real_home_hints=_inject_real_home_hints,
        inject_selected_model_name=_inject_selected_model_name,
        set_opencode_soft_home=_set_opencode_soft_home,
        write_opencode_config=_write_opencode_config,
        overlay_opencode_session_assets=_overlay_opencode_session_assets,
        apply_route_env=_opencode_apply_route_env,
        apply_bypass_env=_opencode_apply_bypass_env,
        apply_runtime_network_profile=_apply_runtime_network_profile,
        apply_runtime_locale_profile=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
        install_session_command_wrappers=_install_session_command_wrappers,
        install_session_packet_env=_install_session_packet_env,
        runtime_caveman_enabled=_runtime_caveman_enabled,
        resolve_web_access_root=_resolve_web_access_root,
        resolve_weber_root=_resolve_weber_root,
        resolve_codegraph_root=_resolve_codegraph_root,
        resolve_toon_root=_resolve_toon_root,
        resolve_token_saver_root=_resolve_token_saver_root,
        resolve_xmem_root=_resolve_xmem_root,
        session_skill_disabled=_session_skill_disabled,
        opencode_rtk_plugin_enabled=_opencode_rtk_plugin_enabled,
        opencode_xmem_plugin_enabled=_opencode_xmem_plugin_enabled,
    )


def _opencode_global_omo_env(runtime):
    return _opencode_global_omo_env_impl(
        runtime,
        clear_opencode_config_env=_clear_opencode_config_env,
        inject_real_home_hints=_inject_real_home_hints,
        real_user_path=_real_user_path,
        apply_bypass_env=_opencode_apply_bypass_env,
        apply_runtime_network_profile=_apply_runtime_network_profile,
        apply_runtime_locale_profile=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
    )


def _opencode_global_command(runtime, entrypoint):
    return _opencode_global_command_impl(runtime, entrypoint)


def _opencode_session_command(runtime, entrypoint, launch_model_ref, launch_agent):
    return _opencode_session_command_impl(
        runtime,
        entrypoint,
        launch_model_ref,
        launch_agent,
        default_agent=OPENCODE_LITE_DEFAULT_AGENT,
    )


def _pi_wrapper_path(*args, **kwargs):
    return _pi_support._pi_wrapper_path(*args, **kwargs)

def _pi_retry_extension_path(*args, **kwargs):
    return _pi_support._pi_retry_extension_path(*args, **kwargs)

def _pi_npx_cache_dir(*args, **kwargs):
    return _pi_support._pi_npx_cache_dir(*args, **kwargs)

def _pi_settings_payload(*args, **kwargs):
    return _pi_support._pi_settings_payload(*args, **kwargs)

def _pi_provider_ref(*args, **kwargs):
    return _pi_support._pi_provider_ref(*args, **kwargs)

def _pi_normalize_model_key(*args, **kwargs):
    return _pi_support._pi_normalize_model_key(*args, **kwargs)

def _pi_reference_payload(*args, **kwargs):
    return _pi_support._pi_reference_payload(*args, **kwargs)

def _pi_reference_model_row(*args, **kwargs):
    return _pi_support._pi_reference_model_row(*args, **kwargs)

def _pi_first_positive_int(*args, **kwargs):
    return _pi_support._pi_first_positive_int(*args, **kwargs)

def _pi_hint_max_tokens(*args, **kwargs):
    return _pi_support._pi_hint_max_tokens(*args, **kwargs)

def _pi_hint_context_window(*args, **kwargs):
    return _pi_support._pi_hint_context_window(*args, **kwargs)

def _pi_reference_supports_vision(*args, **kwargs):
    return _pi_support._pi_reference_supports_vision(*args, **kwargs)

def _pi_model_supported(*args, **kwargs):
    return _pi_support._pi_model_supported(*args, **kwargs)

def _pi_model_replacement(*args, **kwargs):
    return _pi_support._pi_model_replacement(*args, **kwargs)

def _pi_model_block_reason(*args, **kwargs):
    return _pi_support._pi_model_block_reason(*args, **kwargs)

def _pi_model_available_for_runtime(*args, **kwargs):
    return _pi_support._pi_model_available_for_runtime(*args, **kwargs)

def _pi_exposed_model_names(*args, **kwargs):
    return _pi_support._pi_exposed_model_names(*args, **kwargs)

def _pi_model_input_types(*args, **kwargs):
    return _pi_support._pi_model_input_types(*args, **kwargs)

def _pi_model_capabilities(*args, **kwargs):
    return _pi_support._pi_model_capabilities(*args, **kwargs)

def _pi_anthropic_base_root(*args, **kwargs):
    return _pi_support._pi_anthropic_base_root(*args, **kwargs)

def _pi_openai_base_url(*args, **kwargs):
    return _pi_support._pi_openai_base_url(*args, **kwargs)

def _pi_protocol_variant(*args, **kwargs):
    return _pi_support._pi_protocol_variant(*args, **kwargs)

def _pi_protocol_variants(*args, **kwargs):
    return _pi_support._pi_protocol_variants(*args, **kwargs)

def _pi_runtime_model_names(*args, **kwargs):
    return _pi_support._pi_runtime_model_names(*args, **kwargs)

def _pi_profile_id(*args, **kwargs):
    return _pi_support._pi_profile_id(*args, **kwargs)

def _pi_pick_protocol(*args, **kwargs):
    return _pi_support._pi_pick_protocol(*args, **kwargs)

def _pi_provider_compat(*args, **kwargs):
    return _pi_support._pi_provider_compat(*args, **kwargs)

def _pi_model_compat(*args, **kwargs):
    return _pi_support._pi_model_compat(*args, **kwargs)

def _pi_model_thinking_level_map(*args, **kwargs):
    return _pi_support._pi_model_thinking_level_map(*args, **kwargs)

def _pi_effective_selected_model(*args, **kwargs):
    return _pi_support._pi_effective_selected_model(*args, **kwargs)

def _pi_wire_model_name(*args, **kwargs):
    return _pi_support._pi_wire_model_name(*args, **kwargs)

def _pi_model_entry(*args, **kwargs):
    return _pi_support._pi_model_entry(*args, **kwargs)

def _pi_group_provider_ref(*args, **kwargs):
    return _pi_support._pi_group_provider_ref(*args, **kwargs)

def _pi_build_models_payload(*args, **kwargs):
    return _pi_support._pi_build_models_payload(*args, **kwargs)

def _pi_gateway_env(*args, **kwargs):
    return _pi_support._pi_gateway_env(*args, **kwargs)

def _pi_provider_export_env(*args, **kwargs):
    return _pi_support._pi_provider_export_env(*args, **kwargs)

def launch_pi(*args, **kwargs):
    return _pi_support.launch_pi(*args, **kwargs)

def launch_opencode(model_info, runtime, once=False):
    """启动 OpenCode，通过 OpenAI-compatible provider 注入 session-local config。"""
    return _opencode_launch_impl(
        model_info,
        runtime,
        once=once,
        entrypoint=_opencode_entrypoint,
        global_omo_env=_opencode_global_omo_env,
        global_command=_opencode_global_command,
        exec_or_run=_exec_or_run,
        gateway_health_check=_opencode_gateway_health_check,
        resolve_model=_resolve_model,
        runtime_routes=_opencode_runtime_routes,
        gateway_env=_opencode_gateway_env,
        select_launch_candidate=_opencode_select_launch_candidate,
        console=console,
        sys_exit=sys.exit,
        inject_selected_model_name=_inject_selected_model_name,
        install_session_packet_env=_install_session_packet_env,
        session_command=_opencode_session_command,
    )


def launch_gemini(model_info, runtime, once=False):
    """启动 Gemini，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Gemini 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "gemini")
    model = _resolve_model(model_info)
    cmd = ["gemini"]
    if model:
        cmd += ["-m", model]
    _exec_or_run(cmd, env, once)


def launch_agy(model_info, runtime, once=False):
    """启动 Antigravity CLI，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Antigravity CLI 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "agy")
    cmd = ["agy"]
    if runtime.get("bypass"):
        cmd.append("--dangerously-skip-permissions")
    if runtime.get("agy_sandbox") or runtime.get("sandbox"):
        cmd.append("--sandbox")
    _exec_or_run(cmd, env, once)


LAUNCHERS = {
    "claude": launch_claude,
    "codex": launch_codex,
    "opencode": launch_opencode,
    "pi": launch_pi,
    "gemini": launch_gemini,
    "agy": launch_agy,
}


def _is_opencode_global_profile_runtime(cli, runtime):
    return _opencode_is_global_profile_runtime_impl(cli, runtime)


def _opencode_global_export_env(runtime):
    return _opencode_global_export_env_impl(
        runtime,
        apply_bypass_env=_opencode_apply_bypass_env,
    )


def _opencode_provider_export_env(runtime, model):
    return _opencode_provider_export_env_impl(
        runtime,
        model,
        export_config_path=_opencode_export_config_path,
        write_opencode_config=_write_opencode_config,
        apply_route_env=_opencode_apply_route_env,
        apply_bypass_env=_opencode_apply_bypass_env,
    )


def _runtime_with_export_model(runtime, model_info=None):
    runtime = dict(runtime) if isinstance(runtime, dict) else {}
    resolved_model = _resolve_model(model_info or runtime)
    if resolved_model and not _resolve_model(runtime):
        runtime["model"] = resolved_model
    return runtime


def get_export_env(cli, runtime, model_info=None):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    from mms_launcher.export import build_export_env

    return build_export_env(
        cli,
        runtime,
        model_info=model_info,
        runtime_with_export_model=_runtime_with_export_model,
        is_opencode_global_profile_runtime=_is_opencode_global_profile_runtime,
        opencode_global_export_env=_opencode_global_export_env,
        validate_account_for_cli=validate_account_for_cli,
        validate_provider_for_cli=validate_provider_for_cli,
        anthropic_base_url=_anthropic_base_url,
        openai_base_url=_openai_base_url,
        resolve_model=_resolve_model,
        opencode_provider_export_env=_opencode_provider_export_env,
        pi_provider_export_env=_pi_provider_export_env,
        inject_host_capability_hints=_inject_host_capability_hints,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        mms_gain_script_path=_mms_gain_script_path,
        token_saver_script_path=_token_saver_script_path,
        token_gain_script_path=_token_gain_script_path,
        xmem_cli_path=_xmem_cli_path,
        safe_getcwd=_safe_getcwd,
    )


def _show_launch_info(cli, runtime, auth_mode):
    """Compatibility wrapper for launch-time display."""
    from mms_display.launch import show_launch_info

    return show_launch_info(cli, runtime, auth_mode)


def launch_cli(cli, model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the unified launcher dispatch entrypoint."""
    from mms_launcher.dispatch import launch_cli as launch_cli_dispatch

    return launch_cli_dispatch(
        cli,
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
        launchers=LAUNCHERS,
        console=console,
        validate_account_for_cli_fn=validate_account_for_cli,
        validate_provider_for_cli_fn=validate_provider_for_cli,
        is_opencode_global_profile_runtime_fn=_is_opencode_global_profile_runtime,
        enforce_claude_network_guard_or_exit_fn=_enforce_claude_network_guard_or_exit,
        claude_bypass_requires_proxy_fn=_claude_bypass_requires_proxy,
        resolve_model_fn=_resolve_model,
        exit_oauth_claude_manual_only_fn=_exit_oauth_claude_manual_only,
        probe_models_fn=_probe_models,
        launch_status_fn=_launch_status,
        print_launch_step_done_fn=_print_launch_step_done,
        show_launch_info_fn=_show_launch_info,
        exit_fn=sys.exit,
    )


def _print_session_summary(bridge_info):
    """Compatibility wrapper for local bridge session summaries."""
    from mms_launcher.exec import print_session_summary

    return print_session_summary(bridge_info)


def _exec_or_run(
    cmd,
    env,
    once,
    cleanup_path=None,
    state_home=None,
    cleanup_context=None,
    exit_callback=None,
    force_subprocess=False,
    bridge_info=None,
):
    """Compatibility wrapper for launcher process execution."""
    from mms_launcher.exec import exec_or_run

    return exec_or_run(
        cmd,
        env,
        once,
        cleanup_path=cleanup_path,
        state_home=state_home,
        cleanup_context=cleanup_context,
        exit_callback=exit_callback,
        force_subprocess=force_subprocess,
        bridge_info=bridge_info,
        prepare_cli_command_fn=prepare_cli_command,
        console=console,
        activated_state=activated_claude_account_state,
        record_session_child_pid=_record_session_child_pid,
        print_session_summary=_print_session_summary,
    )
