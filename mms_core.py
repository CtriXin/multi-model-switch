"""MMS 核心逻辑：交互选择、模型拉取、分类、预设管理"""

import sys
import os
import argparse
import shlex
import subprocess
import json
import shutil
import logging
import threading
import time
import re
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # pragma: no cover - not expected on macOS/Linux
    fcntl = None

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None

# ── 延迟导入：httpx 和 rich 按需加载以加速启动 ──
httpx = None  # 首次使用时由 _ensure_httpx() 加载


def _ensure_httpx():
    global httpx
    if httpx is None:
        try:
            import httpx as _httpx
            httpx = _httpx
        except ImportError:
            pass
    return httpx


class _LazyConsole:
    """Rich Console 代理：首次访问时才 import rich，节省 ~90ms 启动时间。"""
    _instance = None

    def __getattr__(self, name):
        if _LazyConsole._instance is None:
            try:
                from rich.console import Console
                _LazyConsole._instance = Console()
            except ImportError:
                print("缺少依赖，请执行: pip install rich httpx tomli-w")
                sys.exit(1)
            _ensure_rich()
        return getattr(_LazyConsole._instance, name)


console = _LazyConsole()

# rich 组件：首次使用时加载（通过模块级 __getattr__）


_STATE_FILE_PROCESS_LOCK = threading.RLock()
Panel = Table = Prompt = IntPrompt = Confirm = Text = None


def _ensure_rich():
    global Panel, Table, Prompt, IntPrompt, Confirm, Text
    if Panel is not None:
        return
    from rich.panel import Panel as _P
    from rich.table import Table as _T
    from rich.prompt import Prompt as _Pr, IntPrompt as _IP, Confirm as _C
    from rich.text import Text as _Tx
    Panel, Table, Prompt, IntPrompt, Confirm, Text = _P, _T, _Pr, _IP, _C, _Tx

from mms_account_state import seed_agy_state, seed_claude_state, seed_gemini_state
from mms_adapter_registry import TOP_SOURCE_COMPANIES, DEFAULT_ADAPTER_POLICY, PROVIDER_TEMPLATES
from mms_broker import (
    ensure_broker_config,
    handle_broker_command,
    list_broker_profiles,
    run_broker_profile_interactive,
    run_broker_profile,
)
from mms_fake_upstream import (
    fake_httpx_response as _fake_httpx_response,
    fake_proxy_probe as _fake_proxy_probe,
    is_enabled as _fake_upstream_enabled,
    is_local_url as _fake_upstream_is_local_url,
    set_enabled as _set_fake_upstream_enabled,
    status_payload as _fake_upstream_status_payload,
    tail_log as _fake_upstream_tail_log,
)
from mms_i18n import normalize_language, set_language, pick as _L
from mms_opencode_health import (
    OPENCODE_HEALTH_REL_PATH as _OPENCODE_HEALTH_REL_PATH,
    OPENCODE_HEALTH_STATUS_RANK as _OPENCODE_HEALTH_STATUS_RANK,
    OPENCODE_HEALTH_UNHEALTHY_TTL_SEC as _OPENCODE_HEALTH_UNHEALTHY_TTL_SEC,
    load_opencode_route_health_latest as _load_opencode_route_health_latest,
    opencode_health_latest_path as _opencode_health_latest_path,
    opencode_health_repo_root as _opencode_health_repo_root,
    opencode_parse_health_timestamp as _opencode_parse_health_timestamp,
    opencode_route_health_allows_route as _opencode_route_health_allows_route_impl,
    opencode_route_health_for_route as _opencode_route_health_for_route,
    opencode_route_health_is_fresh as _opencode_route_health_is_fresh,
    opencode_route_health_key as _opencode_route_health_key,
    opencode_route_health_sort_key as _opencode_route_health_sort_key,
)
from mms_opencode_profiles import (
    OPENCODE_AGENT_PROFILE_ID as _OPENCODE_AGENT_PROFILE_ID,
    OPENCODE_BASE_PROFILE_OPTIONS as _OPENCODE_BASE_PROFILE_OPTIONS,
    OPENCODE_DEFAULT_PROFILE_ID as _OPENCODE_DEFAULT_PROFILE_ID,
    OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS as _OPENCODE_LITE_PRO_ORCHESTRATED_EXTRA_SPECS,
    OPENCODE_LITE_PRO_SPECS as _OPENCODE_LITE_PRO_SPECS,
    OPENCODE_PROFILE_OPTIONS as _OPENCODE_PROFILE_OPTIONS,
    apply_opencode_entrypoint as _apply_opencode_entrypoint,
    apply_opencode_profile as _apply_opencode_profile,
    normalize_opencode_entrypoint as _normalize_opencode_entrypoint,
    normalize_opencode_profile_id as _normalize_opencode_profile_id,
    opencode_lite_pro_specs as _opencode_lite_pro_specs,
    opencode_profile_label as _opencode_profile_label,
    opencode_profile_selection as _opencode_profile_selection,
    opencode_profile_selection_ids as _opencode_profile_selection_ids,
)
from mms_opencode_routes import (
    opencode_mimo_openai_base_from_anthropic as _opencode_mimo_openai_base_from_anthropic,
    opencode_provider_protocols as _opencode_provider_protocols,
    opencode_route_transport_candidates as _opencode_route_transport_candidates_impl,
)
from mms_opencode_resolver import (
    OpenCodeResolverDeps as _OpenCodeResolverDeps,
    find_opencode_model_route as _find_opencode_model_route_impl,
    resolve_opencode_profile_runtime as _resolve_opencode_profile_runtime_impl,
)
from mms_state_io import (
    mms_config_root_is_explicit,
    mms_config_root_status,
    resolve_mms_config_dir,
    resolve_real_user_home,
)
from mms_state_io import resolve_current_workdir as _safe_getcwd

# Provider 调试日志（按需写入文件，不影响 TUI 输出）
_PROBE_DEBUG_DIR = os.path.join(
    resolve_mms_config_dir(),
    "cache",
)
_probe_debug_logger = logging.getLogger("probe_debug")
_probe_debug_logger.setLevel(logging.DEBUG)
_probe_debug_logger.propagate = False


def _ensure_probe_debug_logger():
    if _probe_debug_logger.handlers:
        return _probe_debug_logger
    os.makedirs(_PROBE_DEBUG_DIR, exist_ok=True)
    _dh = logging.FileHandler(
        os.path.join(_PROBE_DEBUG_DIR, "provider_debug.log"),
        mode="a", encoding="utf-8",
    )
    _dh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    _probe_debug_logger.addHandler(_dh)
    return _probe_debug_logger

APP_NAME = "Multi-Model Switch"
PRIMARY_COMMAND = "mms"

PRIMARY_CONFIG_DIR = resolve_mms_config_dir()
CONFIG_DIR = PRIMARY_CONFIG_DIR
CONFIG_PATH = os.path.join(PRIMARY_CONFIG_DIR, "config.toml")
CREDENTIALS_PATH = os.path.join(PRIMARY_CONFIG_DIR, "credentials.sh")
ENV_DIR = os.path.join(PRIMARY_CONFIG_DIR, "env")
ACCOUNTS_DIR = os.path.join(PRIMARY_CONFIG_DIR, "accounts")
USAGE_PATH = os.path.join(PRIMARY_CONFIG_DIR, "usage.json")
VERSION_META_PATH = os.path.join(PRIMARY_CONFIG_DIR, "version.json")
UPDATE_CHECK_PATH = os.path.join(PRIMARY_CONFIG_DIR, "update-check.json")
OVERRIDE_PATHS = [
    os.path.join(PRIMARY_CONFIG_DIR, "override.toml"),
]
PREFERENCES_PATHS = [
    os.path.join(PRIMARY_CONFIG_DIR, "preferences.toml"),
]
PREFERENCES_DOC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "MMS_USER_PREFERENCES.md")
PREFERENCES_EXAMPLE_TOML = """# ~/.config/mms/preferences.toml
# User-owned preference overlay. Install/update never overwrites this file.

[launch.defaults]
thinking_mode = "enable"      # enable | disable
reasoning_effort = "high"     # low | medium | high | xhigh
caveman_mode = "enable"       # enable | disable
caveman_level = "light"       # light | standard | full
nsr_mode = "enable"           # enable | disable
agent_pack = "none"           # none | ecc | omc
bypass = true                 # true | false

[launch.cli.codex]
reasoning_effort = "high"

[launch.cli.claude]
agent_pack = "ecc"

[launch.cli.agy]
caveman_mode = "enable"
caveman_level = "light"

[session_surfaces.disabled]
skills = []                   # e.g. ["agent-browser", "token-saver"]
mcp = []                      # e.g. ["pilot", "hive"]
hooks = []                    # hook names or paths shown on confirm screen

[assets.roots]
# Optional custom roots; env vars like MMS_WEB_ACCESS_ROOT still win.
# web_access = "~/my-skills/web-access"
# weber = "~/my-skills/weber"
# codegraph = "~/vendor/codegraph"
# token_saver = "~/vendor/token-saver"
# toon = "~/vendor/toon"
# xmem = "~/auto-skills/shared-skills/xmem"
# caveman = "~/vendor/caveman"
# nsr = "~/vendor/non-stop-run"
# ecc = "~/.mms/agent-packs/everything-claude-code"
# omc = "~/.mms/agent-packs/oh-my-claudecode"
"""


def _runtime_caveman_enabled_default(runtime, default=True):
    from mms_session_features import normalize_caveman_mode

    fallback = "enable" if default else "disable"
    return normalize_caveman_mode((runtime or {}).get("caveman_mode", fallback), default=fallback) == "enable"


CONFIG_AUDIT_LOG = "config-audit.jsonl"
CONFIG_LOCK_FILE = "config.toml.lock"
CONFIG_GUARD_FILES = ("AGENTS.md", "CLAUDE.md")
CONFIG_SNAPSHOT_DIR = "snapshots"
CONFIG_SNAPSHOT_SCHEMA = 1
CONFIG_GUARD_EXIT_CODE = 41
SNAPSHOT_IGNORED_FILES = (
    "config.toml",
    CONFIG_AUDIT_LOG,
    "usage.json",
    "account-guard-state.json",
)

_CONFIG_WRITE_PROCESS_LOCK = threading.Lock()

_GATEWAY_SESSION_MARKERS = (
    os.path.join(".config", "mms", "codex-gateway", "s") + os.sep,
    os.path.join(".config", "mms", "claude-gateway", "s") + os.sep,
)


def _base_user_config_path_from_gateway(config_path):
    from mms_command_tools import base_user_config_path_from_gateway

    return base_user_config_path_from_gateway(config_path, gateway_session_markers=_GATEWAY_SESSION_MARKERS)


def _base_user_primary_dir_from_gateway(path):
    from mms_command_tools import base_user_primary_dir_from_gateway

    return base_user_primary_dir_from_gateway(path, gateway_session_markers=_GATEWAY_SESSION_MARKERS)


def _merge_base_user_broker_profiles(cfg, config_path):
    from mms_command_tools import merge_base_user_broker_profiles

    return merge_base_user_broker_profiles(
        cfg,
        config_path,
        base_user_config_path_from_gateway=_base_user_config_path_from_gateway,
        ensure_broker_config=ensure_broker_config,
    )
DEFAULT_BASE_URL = "https://your-api.example.com"
API_URL_ENV_NAME = "MMS_API_BASE_URL"
API_KEY_ENV_NAME = "MMS_API_KEY"
DEFAULT_PROVIDER_ID = "default"
DEFAULT_PROVIDER_PROTOCOLS = ["anthropic_messages", "openai_chat_completions"]
DEFAULT_ACCOUNT_TIMEZONE = "Asia/Singapore"
VALID_CLAUDE_1M_MODES = {"auto", "enable", "disable"}
OAUTH_CAPABLE_CLIS = ("claude", "codex", "gemini", "agy")
MMS_MANAGED_OAUTH_CLIS = ("codex", "agy")
MMC_DELEGATED_OAUTH_CLIS = ("claude",)
PROVIDER_CAPABLE_CLIS = ("claude", "codex", "opencode")
DEFAULT_PRIORITY = 100
MODE_ALL = "全部模型"
MODE_RECOMMENDED = "推荐模型"
DIRECT_CLI_MODES = set()
LEGACY_PROVIDER_CLI_ALIASES = {"qwen", "kimi"}
UPDATE_CHECK_INTERVAL_SEC = 24 * 60 * 60
UPDATE_PROMPT_INTERVAL_SEC = 24 * 60 * 60
UPDATE_NOTICE_VERSION_GAP = 3
UPDATE_NOTICE_SOURCES = frozenset({"install.sh"})
UPDATE_CHECK_TAG_LIMIT = 100
CLI_VERSION_CHECK_INTERVAL_SEC = 24 * 60 * 60
CLI_VERSION_PACKAGES = {
    "codex": "@openai/codex",
    "claude": "@anthropic-ai/claude-code",
}

_UPDATE_CHECK_LOCK = threading.Lock()
_UPDATE_CHECK_RUNNING = False


class WizardBack(Exception):
    pass


class WizardCancel(Exception):
    pass


def _load_json_file(path, default):
    from mms_command_tools import load_json_file

    return load_json_file(path, default)


def _save_json_file(path, payload):
    from mms_command_tools import save_json_file

    return save_json_file(path, payload)


def _http_status_is_success(value):
    from mms_command_tools import http_status_is_success

    return http_status_is_success(value)


def _load_version_meta():
    return _load_json_file(VERSION_META_PATH, {})


def _load_update_check_cache():
    return _load_json_file(UPDATE_CHECK_PATH, {})


def _save_update_check_cache(payload):
    _save_json_file(UPDATE_CHECK_PATH, payload)


def _fetch_latest_semver_tags(limit=UPDATE_CHECK_TAG_LIMIT):
    from mms_command_tools import fetch_latest_semver_tags, normalize_semver_tags

    return fetch_latest_semver_tags(
        limit=limit,
        request_cls=Request,
        urlopen_func=urlopen,
        json_load=json.load,
        normalize_semver_tags=normalize_semver_tags,
    )


def _extract_semver_text(value):
    from mms_command_tools import extract_semver_text

    return extract_semver_text(value)


def _installed_update_semver(version_meta):
    from mms_command_tools import installed_update_semver

    return installed_update_semver(version_meta, update_notice_sources=UPDATE_NOTICE_SOURCES)


def _semver_tag_gap(installed_version, known_tags, latest_tag=""):
    from mms_command_tools import semver_tag_gap

    return semver_tag_gap(installed_version, known_tags, latest_tag)


def _update_notice():
    from mms_command_tools import parse_semver_tag, update_notice

    return update_notice(
        stdin=sys.stdin,
        stdout=sys.stdout,
        load_version_meta=_load_version_meta,
        installed_update_semver=_installed_update_semver,
        load_update_check_cache=_load_update_check_cache,
        parse_semver_tag=parse_semver_tag,
        semver_tag_gap=_semver_tag_gap,
        save_update_check_cache=_save_update_check_cache,
        now=time.time,
        version_gap=UPDATE_NOTICE_VERSION_GAP,
        prompt_interval_sec=UPDATE_PROMPT_INTERVAL_SEC,
    )


def _start_async_update_check():
    global _UPDATE_CHECK_RUNNING
    from mms_command_tools import start_async_update_check

    def get_running():
        return bool(_UPDATE_CHECK_RUNNING)

    def set_running(value):
        global _UPDATE_CHECK_RUNNING
        _UPDATE_CHECK_RUNNING = bool(value)

    return start_async_update_check(
        load_version_meta=_load_version_meta,
        installed_update_semver=_installed_update_semver,
        load_update_check_cache=_load_update_check_cache,
        fetch_latest_semver_tags=_fetch_latest_semver_tags,
        save_update_check_cache=_save_update_check_cache,
        lock=_UPDATE_CHECK_LOCK,
        get_running=get_running,
        set_running=set_running,
        thread_cls=threading.Thread,
        now=time.time,
        interval_sec=UPDATE_CHECK_INTERVAL_SEC,
    )

# 统一模型家族规则表（有序）。
# keywords 匹配模型名任意部分（不限前缀），支持 provider/model 格式。
# display_category 用于 Rich 表格的分类列。
MODEL_FAMILIES = [
    {"family": "Claude",  "keywords": ("claude",),                          "category": "Claude 系 ⭐"},
    {"family": "GPT",     "keywords": ("gpt-", "o1-", "o3-", "o4-", "codex-"), "category": "GPT 系"},
    {"family": "Gemini",  "keywords": ("gemini",),                          "category": "Google 系"},
    {"family": "DeepSeek","keywords": ("deepseek",),                       "category": "国产系"},
    {"family": "Qwen",    "keywords": ("qwen",),                           "category": "国产系"},
    {"family": "Kimi",    "keywords": ("kimi", "k2.6-code-preview", "k2.6"), "category": "国产系"},
    {"family": "Mimo",    "keywords": ("mimo",),                           "category": "国产系"},
    {"family": "MiniMax", "keywords": ("minimax",),                        "category": "国产系"},
    {"family": "GLM",     "keywords": ("glm",),                            "category": "国产系"},
]
KNOWN_MODEL_FAMILY_NAMES = {entry["family"] for entry in MODEL_FAMILIES}
DOMESTIC_MODEL_FAMILIES = {"DeepSeek", "Qwen", "Kimi", "Mimo", "MiniMax", "GLM"}
DOMESTIC_MODEL_KEYWORDS = ("glm", "kimi", "qwen", "mimo", "minimax", "deepseek", "doubao", "seed", "bailian")


def _infer_model_family(model_name):
    """从模型全名推断 (family, category)。

    支持 provider/model 格式（如 bailian/kimi-2.5）：
    先用完整名匹配，再用 '/' 后面的部分匹配。
    """
    from mms_command_tools import infer_model_family

    return infer_model_family(model_name, model_families=MODEL_FAMILIES)


def _model_info_looks_domestic(model_info):
    from mms_command_tools import model_info_looks_domestic

    return model_info_looks_domestic(
        model_info,
        infer_model_family=_infer_model_family,
        domestic_model_families=DOMESTIC_MODEL_FAMILIES,
        domestic_model_keywords=DOMESTIC_MODEL_KEYWORDS,
    )


_MMS_HIDDEN_MODEL_FAMILIES = set()
_MMS_HIDDEN_MODELS = set()


def _mms_model_visible(model_name):
    from mms_command_tools import mms_model_visible

    return mms_model_visible(
        model_name,
        infer_model_family=_infer_model_family,
        hidden_models=_MMS_HIDDEN_MODELS,
        hidden_model_families=_MMS_HIDDEN_MODEL_FAMILIES,
    )


def _filter_visible_models(models):
    from mms_command_tools import filter_visible_models

    return filter_visible_models(models, mms_model_visible=_mms_model_visible)


def _model_info_has_visible_models(model_info):
    from mms_command_tools import model_info_has_visible_models

    return model_info_has_visible_models(model_info, mms_model_visible=_mms_model_visible)


def _preset_has_visible_model_options(preset):
    return _model_info_has_visible_models(_preset_model_info(preset))


CLI_NAMES = ["claude", "codex", "opencode", "pi", "agy"]
CLI_MODEL_FAMILY_HINTS = {}


def current_command():
    from mms_command_tools import current_command as current_command_helper

    return current_command_helper(primary_command=PRIMARY_COMMAND, environ=os.environ, argv0=sys.argv[0] if sys.argv else "")


def display_title():
    from mms_command_tools import display_title as display_title_helper

    return display_title_helper(current_command_fn=current_command)


def _git_output(args):
    from mms_command_tools import git_output

    return git_output(args, subprocess_run=subprocess.run, file_path=__file__)


def _release_version_info():
    from mms_command_tools import release_version_info

    return release_version_info(load_version_meta=_load_version_meta, git_output=_git_output)


def _about_status_snapshot(force_update=False):
    from mms_command_tools import (
        about_status_snapshot,
        cli_version_status,
        compare_semver_text,
        detect_cli_version,
        fetch_npm_package_latest_version,
        mms_update_status,
        refresh_update_cache_for_about,
    )

    def refresh_cache(*, force_update=False):
        return refresh_update_cache_for_about(
            force_update=force_update,
            load_update_check_cache=_load_update_check_cache,
            fetch_latest_semver_tags=_fetch_latest_semver_tags,
            save_update_check_cache=_save_update_check_cache,
            now=time.time,
        )

    def detect_cli(command_name):
        return detect_cli_version(
            command_name,
            which=shutil.which,
            subprocess_run=subprocess.run,
            extract_semver_text=_extract_semver_text,
            localize=_L,
        )

    def fetch_latest_package(package_name):
        return fetch_npm_package_latest_version(
            package_name,
            which=shutil.which,
            subprocess_run=subprocess.run,
            extract_semver_text=_extract_semver_text,
        )

    def cli_status(*, force_update=False):
        return cli_version_status(
            force_update=force_update,
            load_update_check_cache=_load_update_check_cache,
            save_update_check_cache=_save_update_check_cache,
            cli_version_packages=CLI_VERSION_PACKAGES,
            detect_cli_version=detect_cli,
            fetch_npm_package_latest_version=fetch_latest_package,
            compare_semver_text=compare_semver_text,
            localize=_L,
            now=time.time,
        )

    def mms_status(version_info, cache):
        return mms_update_status(version_info, cache, localize=_L)

    return about_status_snapshot(
        force_update=force_update,
        release_version_info=_release_version_info,
        refresh_update_cache_for_about=refresh_cache,
        cli_version_status=cli_status,
        mms_update_status=mms_status,
    )


def _cli_upgrade_shell_command(cli_name):
    from mms_command_tools import cli_upgrade_shell_command

    return cli_upgrade_shell_command(cli_name, cli_version_packages=CLI_VERSION_PACKAGES)


def _run_about_upgrade(*, target="mms", include_clis=False):
    from mms_command_tools import mms_upgrade_shell_command, run_about_upgrade

    _ensure_rich()

    def mms_upgrade_command(*, include_clis=False):
        return mms_upgrade_shell_command(
            include_clis=include_clis,
            preferred_language=_load_version_meta().get("preferred_language", ""),
            normalize_language=normalize_language,
        )

    return run_about_upgrade(
        target=target,
        include_clis=include_clis,
        ensure_rich=_ensure_rich,
        cli_upgrade_shell_command=_cli_upgrade_shell_command,
        mms_upgrade_shell_command=mms_upgrade_command,
        confirm_ask=Confirm.ask,
        subprocess_run=subprocess.run,
        console=console,
        localize=_L,
    )


def config_command_hint():
    from mms_command_tools import config_command_hint as config_command_hint_helper

    return config_command_hint_helper(current_command=current_command)


def export_command_hint(cli_name):
    from mms_command_tools import export_command_hint as export_command_hint_helper

    return export_command_hint_helper(cli_name, current_command=current_command)


def normalize_user_role(role):
    from mms_command_tools import normalize_user_role as normalize_user_role_helper

    return normalize_user_role_helper(role, mode_all=MODE_ALL, mode_recommended=MODE_RECOMMENDED)


def _normalize_ui_config(cfg):
    from mms_command_tools import normalize_ui_config

    return normalize_ui_config(cfg, normalize_language=normalize_language)


def _resolve_ui_language(cfg=None, cli_override=None):
    from mms_command_tools import resolve_ui_language

    return resolve_ui_language(
        cfg,
        cli_override,
        normalize_language=normalize_language,
        load_version_meta=_load_version_meta,
    )


def _extract_global_lang(argv):
    from mms_command_tools import extract_global_lang

    return extract_global_lang(argv, normalize_language=normalize_language)


ROLE_WEIGHTS = {"primary": 0, "auto": 1, "fallback": 2}
VALID_ROLES = set(ROLE_WEIGHTS.keys())
_REASONING_MODEL_HINTS = (
    "claude-opus", "claude-sonnet", "gpt-5", "o1-", "o3-", "o4-",
    "gemini-2.5-pro", "gemini-3", "qwen3-max", "qwen3-coder",
    "kimi-k2.5", "kimi-for-coding", "glm-5", "glm-4.7",
    "minimax-m2", "deepseek-reasoner", "doubao-thinking",
)
_TOOL_USE_FAMILIES = {"Claude", "GPT", "Gemini", "Qwen", "Kimi", "GLM", "MiniMax"}
_VISION_CAPABLE_MODEL_NAMES = {
    "mimo-v2.5",
    "mimo-v2-omni",
    "k2.6",
    "k2.6-code-preview",
    "kimi-k2.5",
    "kimi-k2.6",
    "qwen3.6-flash",
    "qwen3.6-plus",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
}
_VISION_CAPABLE_MODEL_HINTS = ("gemini-",)


def _normalize_role(value):
    """Normalize provider role to one of: primary, auto, fallback."""
    from mms_command_tools import normalize_role

    return normalize_role(value, valid_roles=VALID_ROLES)


def _normalize_positive_seconds(value, default, minimum=1):
    from mms_command_tools import normalize_positive_seconds

    return normalize_positive_seconds(value, default, minimum=minimum)


def _default_provider():
    from mms_command_tools import default_provider

    return default_provider(
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_provider_protocols=DEFAULT_PROVIDER_PROTOCOLS,
        provider_capable_clis=PROVIDER_CAPABLE_CLIS,
    )


def _default_account_home(account_id):
    from mms_command_tools import default_account_home

    return default_account_home(account_id, accounts_dir=ACCOUNTS_DIR)


def _normalize_priority(value):
    from mms_command_tools import normalize_priority

    return normalize_priority(value, default_priority=DEFAULT_PRIORITY)


def _canonical_model_family(value):
    from mms_command_tools import canonical_model_family

    return canonical_model_family(value, model_families=MODEL_FAMILIES)


def _normalize_family_priority_overrides(value):
    from mms_command_tools import normalize_family_priority_overrides

    return normalize_family_priority_overrides(
        value,
        model_families=MODEL_FAMILIES,
        default_priority=DEFAULT_PRIORITY,
    )


def _runtime_priority_for_family(runtime, family_name):
    from mms_command_tools import runtime_priority_for_family

    return runtime_priority_for_family(
        runtime,
        family_name,
        canonical_model_family=_canonical_model_family,
        normalize_priority=_normalize_priority,
        default_priority=DEFAULT_PRIORITY,
    )


def _runtime_priority_for_model(runtime, model_name):
    from mms_command_tools import runtime_priority_for_model

    return runtime_priority_for_model(
        runtime,
        model_name,
        infer_model_family=_infer_model_family,
        runtime_priority_for_family=_runtime_priority_for_family,
    )


def _runtime_with_priority(runtime, *, model_name="", family_name=""):
    from mms_command_tools import runtime_with_priority

    return runtime_with_priority(
        runtime,
        model_name=model_name,
        family_name=family_name,
        canonical_model_family=_canonical_model_family,
        infer_model_family=_infer_model_family,
        runtime_priority_for_family=_runtime_priority_for_family,
        normalize_priority=_normalize_priority,
        default_priority=DEFAULT_PRIORITY,
    )


def _normalize_claude_1m_mode(value, default="auto"):
    from mms_command_tools import normalize_claude_1m_mode

    return normalize_claude_1m_mode(value, default=default, valid_modes=VALID_CLAUDE_1M_MODES)


def _normalize_timezone_name(value, default=DEFAULT_ACCOUNT_TIMEZONE):
    from mms_command_tools import normalize_timezone_name

    return normalize_timezone_name(value, default=default)


_ANTHROPIC_OFFICIAL_HOSTS = (
    "api.anthropic.com",
    "claude.ai",
    "anthropic.auth0.com",
)
_ACCOUNT_ENV_PREFIX_BLOCKLIST = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
    "OPENAI_",
)
_ACCOUNT_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_ACCOUNT_FAKE_ENV_KEYS = (
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)
_ACCOUNT_CA_ENV_KEYS = (
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)


def _url_matches_host_suffix(url, host_suffixes):
    from mms_command_tools import url_matches_host_suffix

    return url_matches_host_suffix(url, host_suffixes)


def _runtime_should_disable_ambient_env(runtime, *, target_url=""):
    from mms_command_tools import runtime_should_disable_ambient_env

    return runtime_should_disable_ambient_env(
        runtime,
        target_url=target_url,
        official_hosts=_ANTHROPIC_OFFICIAL_HOSTS,
        url_matches_host_suffix=_url_matches_host_suffix,
    )


def _scrub_account_command_env(env):
    from mms_command_tools import scrub_account_command_env

    return scrub_account_command_env(
        env,
        prefix_blocklist=_ACCOUNT_ENV_PREFIX_BLOCKLIST,
        proxy_env_keys=_ACCOUNT_PROXY_ENV_KEYS,
        fake_env_keys=_ACCOUNT_FAKE_ENV_KEYS,
        ca_env_keys=_ACCOUNT_CA_ENV_KEYS,
    )


def _runtime_httpx_kwargs(runtime, *, target_url=""):
    from mms_command_tools import runtime_httpx_kwargs

    def should_disable(current, *, target_url, official_hosts):
        return _runtime_should_disable_ambient_env(current, target_url=target_url)

    return runtime_httpx_kwargs(
        runtime,
        target_url=target_url,
        official_hosts=_ANTHROPIC_OFFICIAL_HOSTS,
        runtime_force_ipv4=_runtime_force_ipv4,
        runtime_should_disable_ambient_env=should_disable,
    )


def _runtime_force_ipv4(runtime):
    from mms_command_tools import runtime_force_ipv4

    return runtime_force_ipv4(runtime)


def _runtime_httpx_request(method, url, *, runtime=None, follow_redirects=False, **kwargs):
    _ensure_httpx()
    if httpx is None:
        raise RuntimeError("missing httpx")
    request_kwargs = dict(kwargs)
    try:
        from mms_provider_profiles import ensure_default_user_agent
        headers = request_kwargs.get("headers") or {}
        if not isinstance(headers, dict):
            headers = dict(headers)
        request_kwargs["headers"] = ensure_default_user_agent(headers)
    except Exception:
        request_kwargs = kwargs
    if _fake_upstream_enabled() and not _fake_upstream_is_local_url(url):
        return _fake_httpx_response(httpx, method, url, **request_kwargs)
    transport = httpx.HTTPTransport(**_runtime_httpx_kwargs(runtime, target_url=url))
    with httpx.Client(transport=transport, follow_redirects=follow_redirects) as client:
        return client.request(method, url, **request_kwargs)


_SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def _validate_proxy_url(proxy_url):
    from mms_command_tools import validate_proxy_url

    return validate_proxy_url(proxy_url, supported_proxy_schemes=_SUPPORTED_PROXY_SCHEMES)


def _test_proxy_connectivity(proxy_url, no_proxy="", target_url="https://api.anthropic.com", force_ipv4=True):
    from mms_command_tools import test_proxy_connectivity

    return test_proxy_connectivity(
        proxy_url,
        no_proxy=no_proxy,
        target_url=target_url,
        force_ipv4=force_ipv4,
        fake_upstream_enabled=_fake_upstream_enabled,
        fake_proxy_probe=_fake_proxy_probe,
        http_status_is_success=_http_status_is_success,
        which=shutil.which,
        run_command=subprocess.run,
    )


def _prompt_validated_proxy_fields(current_proxy="", current_no_proxy="", *, wizard=False, target_url="https://api.anthropic.com"):
    from mms_command_tools import prompt_validated_proxy_fields

    return prompt_validated_proxy_fields(
        current_proxy,
        current_no_proxy,
        wizard=wizard,
        target_url=target_url,
        wizard_prompt=_wizard_prompt,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        localize=_L,
        validate_proxy_url=_validate_proxy_url,
        test_proxy_connectivity=_test_proxy_connectivity,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        console=console,
    )


def _prompt_validated_timezone(current_timezone="", *, wizard=False):
    from mms_command_tools import prompt_validated_timezone

    return prompt_validated_timezone(
        current_timezone,
        wizard=wizard,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        wizard_prompt=_wizard_prompt,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        localize=_L,
        zone_info_cls=ZoneInfo,
        console=console,
    )


def _normalize_account_id(account_id):
    from mms_command_tools import normalize_account_id

    return normalize_account_id(account_id)


def _wizard_prompt(label, default="", password=False, required=False):
    _ensure_rich()
    prompt = f"{label}（输入 b 返回，q 退出）"
    kwargs = {"password": password}
    if default != "":
        kwargs["default"] = default
    value = Prompt.ask(prompt, **kwargs)
    trimmed = value.strip()
    lowered = trimmed.lower()
    if lowered in {"b", "back"}:
        raise WizardBack()
    if lowered in {"q", "quit", "exit"}:
        raise WizardCancel()
    if required and not trimmed:
        console.print("[red]这个字段不能为空[/red]")
        return _wizard_prompt(label, default=default, password=password, required=required)
    return value


def _normalize_account(account):
    from mms_command_tools import normalize_account

    return normalize_account(
        account,
        oauth_capable_clis=OAUTH_CAPABLE_CLIS,
        accounts_dir=ACCOUNTS_DIR,
        default_priority=DEFAULT_PRIORITY,
        model_families=MODEL_FAMILIES,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        claude_1m_valid_modes=VALID_CLAUDE_1M_MODES,
    )


def _normalize_provider_id_input(provider_id):
    from mms_command_tools import normalize_provider_id_input

    return normalize_provider_id_input(provider_id, default_provider_id=DEFAULT_PROVIDER_ID)


def _normalize_model_id_list(values):
    from mms_command_tools import normalize_model_id_list

    return normalize_model_id_list(values)


def _unique_runtime_id(existing_ids, base_id):
    from mms_command_tools import unique_runtime_id

    return unique_runtime_id(existing_ids, base_id)


def _normalize_models_endpoint(value):
    from mms_command_tools import normalize_models_endpoint

    return normalize_models_endpoint(value)


def _model_source_label(source):
    from mms_command_tools import model_source_label

    return model_source_label(source)


def _ttfb_label(ttfb_ms):
    from mms_command_tools import ttfb_label

    return ttfb_label(ttfb_ms)


def _tps_label(tps_value):
    from mms_command_tools import tps_label

    return tps_label(tps_value)


def _provider_env_name(provider_id, field):
    from mms_command_tools import provider_env_name

    return provider_env_name(provider_id, field, default_provider_id=DEFAULT_PROVIDER_ID)


def _normalize_provider(provider):
    from mms_command_tools import normalize_provider

    return normalize_provider(
        provider,
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_provider_protocols=DEFAULT_PROVIDER_PROTOCOLS,
        provider_capable_clis=PROVIDER_CAPABLE_CLIS,
        default_priority=DEFAULT_PRIORITY,
        model_families=MODEL_FAMILIES,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        claude_1m_valid_modes=VALID_CLAUDE_1M_MODES,
        cli_names=CLI_NAMES,
        legacy_provider_cli_aliases=LEGACY_PROVIDER_CLI_ALIASES,
    )


def _normalize_supported_clis(value, protocols=None):
    from mms_command_tools import normalize_supported_clis

    return normalize_supported_clis(
        value,
        protocols=protocols,
        cli_names=CLI_NAMES,
        legacy_provider_cli_aliases=LEGACY_PROVIDER_CLI_ALIASES,
    )


def _ensure_provider_config(cfg):
    from mms_command_tools import ensure_provider_config

    return ensure_provider_config(
        cfg,
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_provider=_default_provider,
        normalize_provider=_normalize_provider,
    )


def _ensure_account_config(cfg):
    from mms_command_tools import ensure_account_config

    return ensure_account_config(
        cfg,
        oauth_capable_clis=OAUTH_CAPABLE_CLIS,
        normalize_account=_normalize_account,
    )


def _normalize_preset_entry(name, preset):
    from mms_command_tools import normalize_preset_entry

    return normalize_preset_entry(name, preset, normalize_account_id=_normalize_account_id)


def _normalize_presets_config(cfg):
    from mms_command_tools import normalize_presets_config

    return normalize_presets_config(cfg, normalize_preset_entry=_normalize_preset_entry)


def _normalize_config_sections(cfg):
    from mms_command_tools import normalize_config_sections

    return normalize_config_sections(
        cfg,
        ensure_provider_config=_ensure_provider_config,
        ensure_account_config=_ensure_account_config,
        ensure_broker_config=ensure_broker_config,
        normalize_ui_config=_normalize_ui_config,
        normalize_presets_config=_normalize_presets_config,
        normalize_user_config=_normalize_user_config,
        normalize_cache_config=_normalize_cache_config,
    )


def _normalize_user_config(cfg):
    from mms_command_tools import normalize_user_config

    return normalize_user_config(cfg, mode_all=MODE_ALL, normalize_user_role=normalize_user_role)


def _normalize_cache_config(cfg):
    from mms_command_tools import normalize_cache_config

    return normalize_cache_config(
        cfg,
        probe_async_refresh_after=_PROBE_ASYNC_REFRESH_AFTER,
        probe_async_min_interval=_PROBE_ASYNC_MIN_INTERVAL,
        normalize_positive_seconds=_normalize_positive_seconds,
    )


def _provider_map(cfg):
    from mms_command_tools import provider_map

    return provider_map(cfg)


def _model_context_window(model_name):
    from mms_command_tools import model_context_window

    def resolve_capabilities(clean):
        from mms_capability_resolver import resolve_model_capabilities

        return resolve_model_capabilities(clean)

    def load_context_windows():
        from mms_launchers import _MODEL_CONTEXT_WINDOWS

        return _MODEL_CONTEXT_WINDOWS

    return model_context_window(
        model_name,
        resolve_model_capabilities=resolve_capabilities,
        model_context_windows=load_context_windows,
    )


def _native_clis_for_model(model_name):
    from mms_command_tools import native_clis_for_model

    return native_clis_for_model(model_name)


def _is_installed_mms_layout(module_path=None):
    from mms_command_tools import is_installed_mms_layout

    return is_installed_mms_layout(
        module_path or __file__,
        real_user_home=resolve_real_user_home,
    )


def _default_gpt_reasoning_effort(module_path=None):
    from mms_command_tools import default_gpt_reasoning_effort

    return default_gpt_reasoning_effort(
        module_path=module_path or __file__,
        is_installed_mms_layout=lambda path: _is_installed_mms_layout(module_path=path),
    )


def _default_reasoning_effort_for_model_info(model_info):
    from mms_command_tools import default_reasoning_effort_for_model_info

    return default_reasoning_effort_for_model_info(
        model_info,
        model_matches_account_cli=_model_matches_account_cli,
        default_gpt_reasoning_effort=_default_gpt_reasoning_effort,
    )


def _bridge_clis_for_model(model_name):
    from mms_command_tools import bridge_clis_for_model

    return bridge_clis_for_model(model_name, infer_model_family=_infer_model_family)


def _model_capability_tags(model_name):
    from mms_command_tools import model_capability_tags

    return model_capability_tags(
        model_name,
        infer_model_family=_infer_model_family,
        model_context_window=_model_context_window,
        reasoning_model_hints=_REASONING_MODEL_HINTS,
        tool_use_families=_TOOL_USE_FAMILIES,
        vision_capable_model_names=_VISION_CAPABLE_MODEL_NAMES,
        vision_capable_model_hints=_VISION_CAPABLE_MODEL_HINTS,
    )


def _model_supports_vision(model_name):
    from mms_command_tools import model_supports_vision

    return model_supports_vision(
        model_name,
        vision_capable_model_names=_VISION_CAPABLE_MODEL_NAMES,
        vision_capable_model_hints=_VISION_CAPABLE_MODEL_HINTS,
    )


def _model_cli_summary(model_name):
    from mms_command_tools import model_cli_summary

    return model_cli_summary(model_name, infer_model_family=_infer_model_family)


def _model_capability_summary(model_name):
    from mms_command_tools import model_capability_summary

    return model_capability_summary(model_name, model_capability_tags=_model_capability_tags)


def _account_map(cfg):
    from mms_command_tools import account_map

    return account_map(cfg)


def _accounts_for_cli(cfg, cli_name):
    from mms_command_tools import accounts_for_cli

    return accounts_for_cli(cfg, cli_name)


def get_provider_definition(cfg, provider_id=None):
    from mms_command_tools import get_provider_definition as get_provider_definition_helper

    return get_provider_definition_helper(
        cfg,
        provider_id,
        provider_map=_provider_map,
        default_provider=_default_provider,
        default_provider_id=DEFAULT_PROVIDER_ID,
        console=console,
        exit_func=sys.exit,
    )


def get_account_definition(cfg, account_id=None, cli_name=None):
    from mms_command_tools import get_account_definition as get_account_definition_helper

    return get_account_definition_helper(
        cfg,
        account_id=account_id,
        cli_name=cli_name,
        account_map=_account_map,
        console=console,
        exit_func=sys.exit,
    )


# ── Config ──────────────────────────────────────────────


def _active_config_path():
    from mms_command_tools import active_sibling_path_from_gateway

    return active_sibling_path_from_gateway(
        CONFIG_PATH,
        filename="config.toml",
        base_user_primary_dir_from_gateway=_base_user_primary_dir_from_gateway,
    )


def _active_credentials_path():
    from mms_command_tools import active_sibling_path_from_gateway

    return active_sibling_path_from_gateway(
        CREDENTIALS_PATH,
        filename="credentials.sh",
        base_user_primary_dir_from_gateway=_base_user_primary_dir_from_gateway,
    )


def _active_usage_path():
    from mms_command_tools import active_sibling_path_from_gateway

    return active_sibling_path_from_gateway(
        USAGE_PATH,
        filename="usage.json",
        base_user_primary_dir_from_gateway=_base_user_primary_dir_from_gateway,
    )


def _config_guard_root_dir(config_path=None):
    from mms_command_tools import config_guard_root_dir

    return config_guard_root_dir(
        config_path=config_path,
        config_write_target_path=_config_write_target_path,
        base_user_primary_dir_from_gateway=_base_user_primary_dir_from_gateway,
    )


def _config_snapshot_root(config_path=None):
    from mms_command_tools import config_snapshot_root

    return config_snapshot_root(
        config_path=config_path,
        config_guard_root_dir=_config_guard_root_dir,
        config_snapshot_dir=CONFIG_SNAPSHOT_DIR,
    )


def _config_snapshot_path(snapshot_kind, filename="latest.json", *, config_path=None):
    from mms_command_tools import config_snapshot_path

    return config_snapshot_path(
        snapshot_kind,
        filename,
        config_path=config_path,
        config_snapshot_root=_config_snapshot_root,
    )


def _is_snapshot_ignored_file(path):
    from mms_command_tools import is_snapshot_ignored_file

    return is_snapshot_ignored_file(path, ignored_files=SNAPSHOT_IGNORED_FILES)


def _render_mms_config_agents_guard():
    from mms_command_tools import render_mms_config_agents_guard

    return render_mms_config_agents_guard()


def _render_mms_config_claude_guard():
    from mms_command_tools import render_mms_config_claude_guard

    return render_mms_config_claude_guard()


def _ensure_mms_config_guard_files(config_path=None):
    from mms_command_tools import ensure_mms_config_guard_files

    return ensure_mms_config_guard_files(
        config_path=config_path,
        config_guard_root_dir=_config_guard_root_dir,
        render_agents_guard=_render_mms_config_agents_guard,
        render_claude_guard=_render_mms_config_claude_guard,
        config_backup_root=_config_backup_root,
        local_now_slug=_local_now_slug,
    )


def _sha256_text(value):
    from mms_command_tools import sha256_text

    return sha256_text(value)


def _snapshot_proxy_fingerprint(proxy_url):
    from mms_command_tools import snapshot_proxy_fingerprint

    return snapshot_proxy_fingerprint(proxy_url)


def _snapshot_cli_state(home_dir, cli_name):
    from mms_command_tools import snapshot_cli_state

    return snapshot_cli_state(home_dir, cli_name)


def _snapshot_file_entry(path):
    from mms_command_tools import snapshot_file_entry

    return snapshot_file_entry(path, snapshot_file_content_bytes=_snapshot_file_content_bytes)


def _normalize_claude_state_snapshot_payload(data):
    from mms_command_tools import normalize_claude_state_snapshot_payload

    return normalize_claude_state_snapshot_payload(data)


_CLAUDE_SESSION_ENV_KEYS = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "TZ",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "MMS_FORCE_IPV4",
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
}


def _normalize_claude_settings_snapshot_payload(data):
    from mms_command_tools import normalize_claude_settings_snapshot_payload

    return normalize_claude_settings_snapshot_payload(data, session_env_keys=_CLAUDE_SESSION_ENV_KEYS)


def _snapshot_file_content_bytes(path):
    from mms_command_tools import snapshot_file_content_bytes

    return snapshot_file_content_bytes(path, session_env_keys=_CLAUDE_SESSION_ENV_KEYS)


def _snapshot_account_entry(account):
    from mms_command_tools import snapshot_account_entry

    return snapshot_account_entry(
        account,
        default_priority=DEFAULT_PRIORITY,
        default_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        normalize_priority=_normalize_priority,
        normalize_timezone_name=_normalize_timezone_name,
        runtime_force_ipv4=_runtime_force_ipv4,
        snapshot_proxy_fingerprint=_snapshot_proxy_fingerprint,
        sha256_text=_sha256_text,
        snapshot_claude_identity_entry=_snapshot_claude_identity_entry,
    )


def _snapshot_claude_identity_entry(home_dir):
    from mms_command_tools import snapshot_claude_identity_entry

    return snapshot_claude_identity_entry(
        home_dir,
        normalize_claude_state_snapshot_payload=_normalize_claude_state_snapshot_payload,
        mask_identity_value=_mask_identity_value,
        mask_email_value=_mask_email_value,
        sha256_text=_sha256_text,
    )


def _snapshot_provider_entry(provider):
    from mms_command_tools import snapshot_provider_entry

    return snapshot_provider_entry(
        provider,
        default_priority=DEFAULT_PRIORITY,
        default_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        normalize_priority=_normalize_priority,
        normalize_timezone_name=_normalize_timezone_name,
        runtime_force_ipv4=_runtime_force_ipv4,
        snapshot_proxy_fingerprint=_snapshot_proxy_fingerprint,
        sha256_text=_sha256_text,
    )


def _build_config_guard_snapshot(cfg, *, config_path=None):
    from mms_command_tools import build_config_guard_snapshot

    return build_config_guard_snapshot(
        cfg,
        config_path=config_path,
        default_config=_default_config,
        config_write_target_path=_config_write_target_path,
        config_guard_root_dir=_config_guard_root_dir,
        config_snapshot_schema=CONFIG_SNAPSHOT_SCHEMA,
        iso_now=_iso_now,
        snapshot_account_entry=_snapshot_account_entry,
        snapshot_cli_state=_snapshot_cli_state,
        snapshot_provider_entry=_snapshot_provider_entry,
        is_snapshot_ignored_file=_is_snapshot_ignored_file,
        snapshot_file_entry=_snapshot_file_entry,
        environ=os.environ,
    )


def _snapshot_digest(snapshot_data):
    from mms_command_tools import snapshot_digest

    return snapshot_digest(snapshot_data)


def _load_json_snapshot(path):
    from mms_command_tools import load_json_snapshot

    return load_json_snapshot(path)


def _write_json_snapshot(path, payload):
    from mms_command_tools import write_json_snapshot

    return write_json_snapshot(path, payload)


def _snapshot_period_bucket(period_name):
    from mms_command_tools import snapshot_period_bucket

    return snapshot_period_bucket(period_name)


def _update_periodic_snapshot(period_name, snapshot_data, *, config_path=None):
    from mms_command_tools import update_periodic_snapshot

    return update_periodic_snapshot(
        period_name,
        snapshot_data,
        config_path=config_path,
        config_snapshot_path=_config_snapshot_path,
        snapshot_period_bucket=_snapshot_period_bucket,
        iso_now=_iso_now,
        snapshot_digest=_snapshot_digest,
        write_json_snapshot=_write_json_snapshot,
    )


def _snapshot_diff_lines(previous_snapshot, current_snapshot):
    from mms_command_tools import snapshot_diff_lines

    return snapshot_diff_lines(
        previous_snapshot,
        current_snapshot,
        is_snapshot_ignored_file=_is_snapshot_ignored_file,
    )


def _snapshot_prompt_allowed():
    from mms_command_tools import snapshot_prompt_allowed

    return snapshot_prompt_allowed()


def _confirm_startup_snapshot_drift(diff_lines, *, accepted_path, latest_path):
    from mms_command_tools import confirm_startup_snapshot_drift

    _ensure_rich()
    return confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
        ensure_rich=_ensure_rich,
        panel_cls=Panel,
        confirm_ask=Confirm.ask,
        snapshot_prompt_allowed=_snapshot_prompt_allowed,
        console=console,
    )


def _ensure_startup_snapshot_guard(cfg, *, enforce=True):
    from mms_command_tools import ensure_startup_snapshot_guard

    return ensure_startup_snapshot_guard(
        cfg,
        enforce=enforce,
        config_write_target_path=_config_write_target_path,
        build_config_guard_snapshot=_build_config_guard_snapshot,
        config_snapshot_path=_config_snapshot_path,
        iso_now=_iso_now,
        snapshot_digest=_snapshot_digest,
        write_json_snapshot=_write_json_snapshot,
        update_periodic_snapshot=_update_periodic_snapshot,
        load_json_snapshot=_load_json_snapshot,
        snapshot_diff_lines=_snapshot_diff_lines,
        confirm_startup_snapshot_drift=_confirm_startup_snapshot_drift,
        command_name=current_command,
        config_guard_exit_code=CONFIG_GUARD_EXIT_CODE,
        console=console,
    )


def load_config(*, persist=False):
    config_path = _config_write_target_path()
    _ensure_mms_config_guard_files(config_path)
    if not os.path.exists(config_path):
        return None
    with open(config_path, "rb") as f:
        cfg = tomllib.loads(f.read().decode("utf-8"))
    cfg = _migrate_legacy_api_config(cfg)
    cfg, gateway_broker_changed = _merge_base_user_broker_profiles(cfg, config_path)
    cfg, changed = _ensure_provider_config(cfg)
    cfg, account_changed = _ensure_account_config(cfg)
    cfg, broker_changed = ensure_broker_config(cfg)
    cfg, preset_changed = _normalize_presets_config(cfg)
    cfg, role_changed = _normalize_user_config(cfg)
    cfg, cache_changed = _normalize_cache_config(cfg)
    changed = changed or gateway_broker_changed or account_changed or broker_changed or preset_changed or role_changed or cache_changed
    if changed and persist:
        save_config(cfg, reason="auto:load_config_normalize")
    return cfg


def load_runtime_config():
    cfg = _load_config_or_preview_bundle()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


def _config_write_target_path():
    from mms_command_tools import config_write_target_path

    return config_write_target_path(active_config_path=_active_config_path, config_path=CONFIG_PATH)


def _config_lock_path(config_path=None):
    from mms_command_tools import config_lock_path

    return config_lock_path(
        config_path,
        config_write_target_path=_config_write_target_path,
        config_lock_file=CONFIG_LOCK_FILE,
    )


def _config_audit_path(config_path=None):
    from mms_command_tools import config_audit_path

    return config_audit_path(
        config_path,
        config_write_target_path=_config_write_target_path,
        config_audit_log=CONFIG_AUDIT_LOG,
    )


def _config_backup_root(config_path=None):
    from mms_command_tools import config_backup_root

    return config_backup_root(config_path, config_write_target_path=_config_write_target_path)


def _sha1_file(path):
    from mms_command_tools import sha1_file

    return sha1_file(path)


def _config_write_caller():
    from mms_command_tools import config_write_caller

    return config_write_caller(
        current_file=__file__,
        skip_functions=("_config_write_caller", "save_config"),
    )


@contextmanager
def _locked_config_write(config_path):
    from mms_command_tools import locked_config_write

    with locked_config_write(
        config_path,
        config_lock_path=_config_lock_path,
        process_lock=_CONFIG_WRITE_PROCESS_LOCK,
        fcntl_module=fcntl,
    ):
        yield


@contextmanager
def _locked_state_file(path):
    from mms_command_tools import locked_state_file

    with locked_state_file(path, process_lock=_STATE_FILE_PROCESS_LOCK, fcntl_module=fcntl):
        yield


def _backup_config_file(config_path):
    from mms_command_tools import backup_config_file

    return backup_config_file(
        config_path,
        config_backup_root=_config_backup_root,
        local_now_slug=_local_now_slug,
    )


def _append_config_audit_entry(entry, *, config_path):
    from mms_command_tools import append_config_audit_entry

    return append_config_audit_entry(entry, config_path=config_path, config_audit_path=_config_audit_path)


def _atomic_write_toml(path, cfg):
    from mms_command_tools import atomic_write_toml

    return atomic_write_toml(path, cfg, tomli_w_module=tomli_w)


def save_config(cfg, *, reason=None):
    if tomli_w is None:
        console.print("[red]缺少 tomli-w，请执行: pip install tomli-w[/red]")
        sys.exit(1)
    config_path = _config_write_target_path()
    _ensure_mms_config_guard_files(config_path)
    caller = _config_write_caller()
    audit_reason = str(reason or "").strip() or f"auto:{caller.get('function') or 'unknown'}"
    with _locked_config_write(config_path):
        before_sha1 = _sha1_file(config_path)
        backup_path = _backup_config_file(config_path)
        _atomic_write_toml(config_path, cfg)
        after_sha1 = _sha1_file(config_path)
        _append_config_audit_entry(
            {
                "timestamp": _iso_now(),
                "reason": audit_reason,
                "target_path": os.path.abspath(config_path),
                "backup_path": backup_path,
                "caller_path": caller.get("path", ""),
                "caller_line": int(caller.get("line", 0) or 0),
                "caller_function": caller.get("function", ""),
                "pid": os.getpid(),
                "before_sha1": before_sha1,
                "after_sha1": after_sha1,
            },
            config_path=config_path,
        )


def _load_toml_file(path):
    from mms_command_tools import load_toml_file

    return load_toml_file(path, toml_loads=tomllib.loads)


def _existing_override_paths():
    from mms_command_tools import existing_paths

    return existing_paths(OVERRIDE_PATHS)


def _existing_preferences_paths():
    from mms_command_tools import existing_paths

    return existing_paths(PREFERENCES_PATHS)


def _merge_dicts(base, override):
    from mms_command_tools import merge_dicts

    return merge_dicts(base, override)


def _pref_bool(value):
    from mms_command_tools import pref_bool

    return pref_bool(value)


_PREFERENCE_ASSET_ROOT_KEYS = {
    "agent_browser": "agent_browser",
    "agent-browser": "agent_browser",
    "auto_github_contributor": "auto_github_contributor",
    "auto-github-contributor": "auto_github_contributor",
    "caveman": "caveman",
    "codegraph": "codegraph",
    "nsr": "nsr",
    "ecc": "ecc",
    "omc": "omc",
    "token_saver": "token_saver",
    "token-saver": "token_saver",
    "toon": "toon",
    "web_access": "web_access",
    "web-access": "web_access",
    "weber": "weber",
    "xmem": "xmem",
}


def _sanitize_user_preferences(raw):
    from mms_command_tools import sanitize_user_preferences

    return sanitize_user_preferences(raw, cli_names=CLI_NAMES, asset_root_keys=_PREFERENCE_ASSET_ROOT_KEYS)


def load_user_preferences():
    from mms_command_tools import load_user_preferences_from_paths

    return load_user_preferences_from_paths(
        existing_preferences_paths=_existing_preferences_paths,
        load_toml_file=_load_toml_file,
        merge_dicts=_merge_dicts,
        sanitize_user_preferences=_sanitize_user_preferences,
        console=console,
        toml_error_types=(tomllib.TOMLDecodeError,),
    )


def preference_asset_root(asset_name):
    from mms_command_tools import preference_asset_root as preference_asset_root_impl

    return preference_asset_root_impl(
        asset_name,
        asset_root_keys=_PREFERENCE_ASSET_ROOT_KEYS,
        load_user_preferences=load_user_preferences,
    )


def _merge_disabled_session_surfaces(*payloads):
    from mms_command_tools import merge_disabled_session_surfaces

    return merge_disabled_session_surfaces(*payloads)


def _runtime_with_launch_preferences(cfg, runtime, cli_name):
    from mms_command_tools import runtime_with_launch_preferences

    return runtime_with_launch_preferences(
        cfg,
        runtime,
        cli_name,
        load_user_preferences=load_user_preferences,
    )


def apply_local_overrides(cfg):
    from mms_command_tools import apply_local_overrides as apply_local_overrides_impl

    return apply_local_overrides_impl(
        cfg,
        existing_override_paths=_existing_override_paths,
        load_toml_file=_load_toml_file,
        merge_dicts=_merge_dicts,
        load_user_preferences=load_user_preferences,
        console=console,
        toml_error_types=(tomllib.TOMLDecodeError,),
    )


def _env_file_path(cli_name):
    from mms_command_tools import env_file_path

    return env_file_path(cli_name, env_dir=ENV_DIR)


def _shell_quote(value):
    from mms_command_tools import shell_quote

    return shell_quote(value)


def _load_env_file(path):
    from mms_command_tools import load_env_file

    return load_env_file(path)


def _iso_now():
    from mms_command_tools import iso_now

    return iso_now()


def _local_now_slug():
    from mms_command_tools import local_now_slug

    return local_now_slug()


def _load_usage_stats():
    from mms_command_tools import load_usage_stats

    return load_usage_stats(
        active_usage_path=_active_usage_path,
        load_usage_stats_from_path=_load_usage_stats_from_path,
    )


def _load_usage_stats_from_path(usage_path):
    from mms_command_tools import load_usage_stats_from_path

    return load_usage_stats_from_path(usage_path)


def _write_usage_stats_locked(usage_path, data):
    from mms_command_tools import write_usage_stats_locked

    return write_usage_stats_locked(
        usage_path,
        data,
        ensure_mms_config_guard_files=_ensure_mms_config_guard_files,
        config_write_target_path=_config_write_target_path,
    )


def _save_usage_stats(data):
    from mms_command_tools import save_usage_stats

    return save_usage_stats(
        data,
        active_usage_path=_active_usage_path,
        locked_state_file=_locked_state_file,
        write_usage_stats_locked=_write_usage_stats_locked,
        trigger_routes_export_after_usage_write=_trigger_routes_export_after_usage_write,
    )


def _update_usage_stats(mutator):
    from mms_command_tools import update_usage_stats

    return update_usage_stats(
        mutator,
        active_usage_path=_active_usage_path,
        locked_state_file=_locked_state_file,
        load_usage_stats_from_path=_load_usage_stats_from_path,
        write_usage_stats_locked=_write_usage_stats_locked,
        trigger_routes_export_after_usage_write=_trigger_routes_export_after_usage_write,
    )


_USAGE_ROUTES_EXPORT_LOCK = threading.Lock()
_USAGE_ROUTES_EXPORT_RUNNING = False
_USAGE_ROUTES_EXPORT_LAST_STARTED_AT = 0.0
_USAGE_ROUTES_EXPORT_MIN_INTERVAL_SEC = 15.0


def _usage_routes_export_should_run():
    """Keep legacy route-export refresh out of preview DB-truth roots."""
    try:
        return _config_root_status().get("mode") != "preview"
    except Exception:
        return True


def _trigger_routes_export_after_usage_write():
    """Best-effort async routes export after usage changes.

    Stable roots keep model-routes.json reasonably fresh for legacy file
    readers. Preview roots use the verified latest-approved bundle instead.
    """
    from mms_command_tools import trigger_routes_export_after_usage_write

    if not _usage_routes_export_should_run():
        return

    def set_running(value):
        global _USAGE_ROUTES_EXPORT_RUNNING
        _USAGE_ROUTES_EXPORT_RUNNING = bool(value)

    def set_last_started_at(value):
        global _USAGE_ROUTES_EXPORT_LAST_STARTED_AT
        _USAGE_ROUTES_EXPORT_LAST_STARTED_AT = value

    return trigger_routes_export_after_usage_write(
        lock=_USAGE_ROUTES_EXPORT_LOCK,
        is_running=lambda: _USAGE_ROUTES_EXPORT_RUNNING,
        set_running=set_running,
        get_last_started_at=lambda: _USAGE_ROUTES_EXPORT_LAST_STARTED_AT,
        set_last_started_at=set_last_started_at,
        min_interval_sec=_USAGE_ROUTES_EXPORT_MIN_INTERVAL_SEC,
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive,
        thread_cls=threading.Thread,
        monotonic=time.monotonic,
    )


def _refresh_routes_export_for_hive(cfg=None, *, force=True, quiet=False, startup_safe=False):
    """Synchronously refresh the Hive-facing routes export from current config."""
    from mms_command_tools import refresh_routes_export_for_hive

    if startup_safe and not _usage_routes_export_should_run():
        return True

    def export_model_routes_current(*args, **kwargs):
        from mms_router import export_model_routes

        return export_model_routes(*args, **kwargs)

    return refresh_routes_export_for_hive(
        cfg,
        force=force,
        quiet=quiet,
        startup_safe=startup_safe,
        load_config=load_config,
        apply_local_overrides=apply_local_overrides,
        export_model_routes=export_model_routes_current,
        console=console,
    )


def _trigger_routes_export_after_credentials_write():
    """Best-effort routes export after provider key / URL changes."""
    from mms_command_tools import trigger_routes_export_after_credentials_write

    return trigger_routes_export_after_credentials_write(
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive
    )


def _backup_config_tree(label):
    from mms_command_tools import backup_config_tree

    return backup_config_tree(
        label,
        resolve_real_user_home=resolve_real_user_home,
        primary_config_dir=PRIMARY_CONFIG_DIR,
        local_now_slug=_local_now_slug,
    )


def _runtime_usage_key(runtime, cli_name):
    from mms_command_tools import runtime_usage_key

    return runtime_usage_key(runtime, cli_name)


def _resolve_model_name(model_info):
    from mms_command_tools import resolve_model_name

    return resolve_model_name(model_info)


def _runtime_hint_from_runtime(runtime):
    from mms_command_tools import runtime_hint_from_runtime

    return runtime_hint_from_runtime(
        runtime,
        runtime_provider_id=_trace_runtime_provider_id,
        runtime_account_id=_trace_runtime_account_id,
    )


def _record_usage(runtime, cli_name, model_info):
    from mms_command_tools import record_usage

    return record_usage(
        runtime,
        cli_name,
        model_info,
        update_usage_stats=_update_usage_stats,
        iso_now=_iso_now,
        runtime_usage_key=_runtime_usage_key,
        resolve_model_name=_resolve_model_name,
        runtime_hint_from_runtime=_runtime_hint_from_runtime,
    )


def _get_scene_usage():
    from mms_command_tools import get_scene_usage

    return get_scene_usage(
        load_usage_stats=_load_usage_stats,
        resolve_model_name=_resolve_model_name,
        infer_runtime_hint_from_usage_stats=_infer_runtime_hint_from_usage_stats,
    )


def _infer_runtime_hint_from_usage_stats(stats, cli_name, model_name):
    from mms_command_tools import infer_runtime_hint_from_usage_stats

    return infer_runtime_hint_from_usage_stats(stats, cli_name, model_name)


def _resolve_last_used_runtime(cfg, cli_name, last_item, default_models):
    from mms_command_tools import resolve_last_used_runtime

    return resolve_last_used_runtime(
        cfg,
        cli_name,
        last_item,
        default_models,
        resolve_model_name=_resolve_model_name,
        resolve_provider_context=resolve_provider_context,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        probe_models=_probe_models,
        provider_effective_models=_provider_effective_models,
        runtime_with_priority=_runtime_with_priority,
        resolve_account_context=resolve_account_context,
        model_matches_account_cli=_model_matches_account_cli,
    )


# ── Trace ─────────────────────────────────────────────

_trace_enabled = False
_trace_overrides = []


def _trace_record(source, **kv):
    """记录一步 override 来源。source 是 config default / preset / CLI flags 等。"""
    from mms_command_tools import record_trace_override

    return record_trace_override(_trace_enabled, _trace_overrides, source, **kv)


def _trace_runtime_provider_id(runtime):
    from mms_command_tools import trace_runtime_provider_id

    return trace_runtime_provider_id(runtime)


def _trace_runtime_account_id(runtime):
    from mms_command_tools import trace_runtime_account_id

    return trace_runtime_account_id(runtime)


def _trace_runtime_bridge(runtime):
    from mms_command_tools import trace_runtime_bridge

    return trace_runtime_bridge(runtime)


def _trace_runtime_choice(source, runtime, launch_cli=None, choice=None):
    if not _trace_enabled:
        return
    from mms_command_tools import trace_runtime_choice

    return trace_runtime_choice(
        source,
        runtime,
        launch_cli=launch_cli,
        choice=choice,
        trace_record=_trace_record,
        trace_runtime_provider_id=_trace_runtime_provider_id,
        trace_runtime_account_id=_trace_runtime_account_id,
        trace_runtime_bridge=_trace_runtime_bridge,
    )


def _print_trace(cli_name, model_info, runtime):
    """打印 [MMS Trace] 到 stderr。"""
    from mms_command_tools import format_launch_trace

    print(
        format_launch_trace(
            cli_name,
            model_info,
            runtime,
            _trace_overrides,
            runtime_provider_id=_trace_runtime_provider_id,
            runtime_account_id=_trace_runtime_account_id,
            runtime_bridge=_trace_runtime_bridge,
        ),
        file=sys.stderr,
    )


def _launch_with_tracking(cli_name, model_info, runtime, once=False, extra_args=None):
    from mms_command_tools import launch_with_tracking
    from mms_launchers import launch_cli

    return launch_with_tracking(
        cli_name,
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
        runtime_with_launch_preferences=_runtime_with_launch_preferences,
        load_user_preferences=load_user_preferences,
        load_config=load_config,
        runtime_with_vision_sidecar=_runtime_with_vision_sidecar,
        trace_enabled=_trace_enabled,
        print_trace=_print_trace,
        record_usage=_record_usage,
        console=console,
        resolve_model_name=_resolve_model_name,
        run_broker_profile_interactive=run_broker_profile_interactive,
        launch_cli=launch_cli,
    )



def load_provider_credentials(provider_id=DEFAULT_PROVIDER_ID):
    from mms_command_tools import load_provider_credentials as load_provider_credentials_helper

    return load_provider_credentials_helper(
        provider_id,
        default_provider_id=DEFAULT_PROVIDER_ID,
        provider_env_name=_provider_env_name,
        api_url_env_name=API_URL_ENV_NAME,
        api_key_env_name=API_KEY_ENV_NAME,
        credentials_paths=(CREDENTIALS_PATH,),
        load_env_file=_load_env_file,
        active_config_path=_active_config_path,
        environ=os.environ,
        path_exists=os.path.exists,
    )


def save_provider_credentials(provider_id, base_url, api_key, openai_base_url="", anthropic_base_url="", openai_api_key=None):
    from mms_command_tools import save_provider_credentials as save_provider_credentials_helper

    return save_provider_credentials_helper(
        provider_id,
        base_url,
        api_key,
        openai_base_url=openai_base_url,
        anthropic_base_url=anthropic_base_url,
        openai_api_key=openai_api_key,
        config_dir=CONFIG_DIR,
        credentials_path=CREDENTIALS_PATH,
        provider_env_name=_provider_env_name,
        default_provider_id=DEFAULT_PROVIDER_ID,
        api_url_env_name=API_URL_ENV_NAME,
        api_key_env_name=API_KEY_ENV_NAME,
        load_env_file=_load_env_file,
        shell_quote=_shell_quote,
        trigger_routes_export_after_credentials_write=_trigger_routes_export_after_credentials_write,
        makedirs=os.makedirs,
        path_exists=os.path.exists,
        chmod=os.chmod,
    )


def load_api_credentials():
    from mms_command_tools import load_api_credentials as load_api_credentials_helper

    return load_api_credentials_helper(
        default_provider_id=DEFAULT_PROVIDER_ID,
        load_provider_credentials=load_provider_credentials,
    )


def save_api_credentials(base_url, api_key):
    from mms_command_tools import save_api_credentials as save_api_credentials_helper

    return save_api_credentials_helper(
        base_url,
        api_key,
        default_provider_id=DEFAULT_PROVIDER_ID,
        save_provider_credentials=save_provider_credentials,
    )


def resolve_provider_context(cfg, provider_id=None):
    from mms_command_tools import resolve_provider_context as resolve_provider_context_helper

    return resolve_provider_context_helper(
        cfg,
        provider_id,
        get_provider_definition=get_provider_definition,
        normalize_provider=_normalize_provider,
        load_provider_credentials=load_provider_credentials,
    )


def resolve_account_context(cfg, account_id=None, cli_name=None):
    from mms_command_tools import resolve_account_context as resolve_account_context_helper

    return resolve_account_context_helper(
        cfg,
        account_id=account_id,
        cli_name=cli_name,
        get_account_definition=get_account_definition,
        expanduser=os.path.expanduser,
    )


def _default_config(role=MODE_ALL):
    from mms_command_tools import default_config

    return default_config(
        role,
        normalize_user_role=normalize_user_role,
        probe_async_refresh_after_sec=_PROBE_ASYNC_REFRESH_AFTER,
        probe_async_min_interval_sec=_PROBE_ASYNC_MIN_INTERVAL,
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_provider=_default_provider,
    )


def _migrate_legacy_api_config(cfg):
    from mms_command_tools import migrate_legacy_api_config

    return migrate_legacy_api_config(
        cfg,
        load_api_credentials=load_api_credentials,
        save_api_credentials=save_api_credentials,
        ensure_provider_config=_ensure_provider_config,
        ensure_account_config=_ensure_account_config,
        normalize_user_config=_normalize_user_config,
        save_config=save_config,
        credentials_path=CREDENTIALS_PATH,
        config_path=CONFIG_PATH,
        console=console,
    )


def _provider_label(provider):
    from mms_command_tools import provider_label

    return provider_label(provider, default_provider_id=DEFAULT_PROVIDER_ID)


def _provider_openai_base_url(provider):
    from mms_command_tools import provider_openai_base_url

    return provider_openai_base_url(provider)


def _provider_anthropic_base_url(provider):
    from mms_command_tools import provider_anthropic_base_url

    return provider_anthropic_base_url(provider)


def _provider_has_configured_base_url(provider):
    from mms_command_tools import provider_has_configured_base_url

    return provider_has_configured_base_url(provider)


def _resolve_config_provider_id(provider_defs, provider_id):
    from mms_command_tools import resolve_config_provider_id

    return resolve_config_provider_id(provider_defs, provider_id)


def _config_truthy(value, default=False):
    from mms_command_tools import config_truthy

    return config_truthy(value, default=default)


def _vision_sidecar_candidate_pairs(raw, provider_ids, *, explicit_model="", explicit_provider_id=""):
    from mms_command_tools import vision_sidecar_candidate_pairs

    return vision_sidecar_candidate_pairs(
        raw,
        provider_ids,
        explicit_model=explicit_model,
        explicit_provider_id=explicit_provider_id,
    )


def _runtime_with_vision_sidecar(cfg, runtime):
    from mms_command_tools import runtime_with_vision_sidecar

    return runtime_with_vision_sidecar(
        cfg,
        runtime,
        config_truthy=_config_truthy,
        provider_map=_provider_map,
        resolve_config_provider_id=_resolve_config_provider_id,
        vision_sidecar_candidate_pairs=_vision_sidecar_candidate_pairs,
        resolve_provider_context=resolve_provider_context,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        load_probe_file_cache=_load_probe_file_cache,
        provider_effective_models=_provider_effective_models,
    )


def _account_label(account):
    from mms_command_tools import account_label

    return account_label(account)


def _account_env(account):
    from mms_command_tools import account_env

    return account_env(
        account,
        scrub_account_command_env=_scrub_account_command_env,
        seed_claude_state=seed_claude_state,
        seed_agy_state=seed_agy_state,
        seed_gemini_state=seed_gemini_state,
    )


def _account_status_command(cli_name):
    from mms_command_tools import account_status_command

    return account_status_command(cli_name)


def _probe_account_status(account):
    from mms_command_tools import probe_account_status

    return probe_account_status(
        account,
        account_env=_account_env,
        account_status_command=_account_status_command,
        expanduser=os.path.expanduser,
        path_exists=os.path.exists,
        path_isdir=os.path.isdir,
        run_command=subprocess.run,
    )


def _run_account_login(account):
    from mms_command_tools import run_account_login

    return run_account_login(
        account,
        account_env=_account_env,
        account_label=_account_label,
        makedirs=os.makedirs,
        run_command=subprocess.run,
        console=console,
    )


def _ensure_interactive_terminal(action_hint):
    from mms_command_tools import ensure_interactive_terminal

    return ensure_interactive_terminal(
        action_hint,
        stdin=sys.stdin,
        ensure_rich=_ensure_rich,
        console=console,
        current_command=current_command,
        exit_func=sys.exit,
    )


def _parse_csv_values(raw_value, allowed_values=None):
    from mms_command_tools import parse_csv_values

    return parse_csv_values(raw_value, allowed_values=allowed_values, console=console)


def _prompt_csv_values(label, default_values, allowed_values):
    from mms_command_tools import prompt_csv_values

    return prompt_csv_values(
        label,
        default_values,
        allowed_values,
        ensure_rich=_ensure_rich,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        parse_csv_values=_parse_csv_values,
        console=console,
        exit_func=sys.exit,
    )


def _upsert_provider(cfg, provider):
    from mms_command_tools import upsert_provider

    return upsert_provider(cfg, provider, ensure_provider_config=_ensure_provider_config)


def _delete_provider_credentials(provider_id):
    from mms_command_tools import delete_provider_credentials

    return delete_provider_credentials(
        provider_id,
        credentials_path=CREDENTIALS_PATH,
        load_env_file=_load_env_file,
        provider_env_name=_provider_env_name,
        default_provider_id=DEFAULT_PROVIDER_ID,
        api_url_env_name=API_URL_ENV_NAME,
        api_key_env_name=API_KEY_ENV_NAME,
        shell_quote=_shell_quote,
        path_exists=os.path.exists,
        chmod=os.chmod,
    )


def _prompt_provider_metadata(existing=None, preset_id=None):
    from mms_command_tools import prompt_provider_metadata

    return prompt_provider_metadata(
        existing,
        preset_id,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        normalize_provider=_normalize_provider,
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_provider_protocols=DEFAULT_PROVIDER_PROTOCOLS,
        provider_capable_clis=PROVIDER_CAPABLE_CLIS,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        prompt_csv_values=_prompt_csv_values,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        normalize_models_endpoint=_normalize_models_endpoint,
        normalize_priority=_normalize_priority,
        default_priority=DEFAULT_PRIORITY,
        normalize_claude_1m_mode=_normalize_claude_1m_mode,
        prompt_validated_proxy_fields=_prompt_validated_proxy_fields,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        prompt_validated_timezone=_prompt_validated_timezone,
    )


def _provider_template_payload(template_key):
    from mms_command_tools import provider_template_payload

    return provider_template_payload(template_key, provider_templates=PROVIDER_TEMPLATES)


def _select_provider_template(preset_id=None):
    from mms_command_tools import select_provider_template

    return select_provider_template(preset_id, console=console)


def _prompt_account_metadata(existing=None, preset_id=None, preset_cli=None):
    from mms_command_tools import prompt_account_metadata

    return prompt_account_metadata(
        existing,
        preset_id,
        preset_cli,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        normalize_account=_normalize_account,
        normalize_account_id=_normalize_account_id,
        default_account_home=_default_account_home,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        normalize_priority=_normalize_priority,
        default_priority=DEFAULT_PRIORITY,
        normalize_claude_1m_mode=_normalize_claude_1m_mode,
        prompt_validated_proxy_fields=_prompt_validated_proxy_fields,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        prompt_validated_timezone=_prompt_validated_timezone,
    )


def _prompt_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    from mms_command_tools import prompt_provider_credentials

    return prompt_provider_credentials(
        provider,
        existing_base_url,
        existing_api_key,
        allow_keep,
        stdin_isatty=lambda: sys.stdin.isatty(),
        console=console,
        current_command=current_command,
        config_command_hint=config_command_hint,
        localize=_L,
        ensure_rich=_ensure_rich,
        default_base_url=DEFAULT_BASE_URL,
        provider_label=_provider_label,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        exit_func=sys.exit,
    )


def _save_provider_credentials_with_probe(provider, base_url, api_key, openai_base_url="", anthropic_base_url=""):
    from mms_command_tools import save_provider_credentials_with_probe

    return save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        openai_base_url=openai_base_url,
        anthropic_base_url=anthropic_base_url,
        probe_models=_probe_models,
        provider_openai_base_url=_provider_openai_base_url,
        save_provider_credentials=save_provider_credentials,
        resolve_provider_context=resolve_provider_context,
        credentials_path=CREDENTIALS_PATH,
        console=console,
    )


def _quick_connect_gateway(cfg, preset_id=None):
    from mms_command_tools import quick_connect_gateway

    return quick_connect_gateway(
        cfg,
        preset_id=preset_id,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        select_provider_template=_select_provider_template,
        provider_template_payload=_provider_template_payload,
        localize=_L,
        panel_cls=Panel,
        console=console,
        provider_map=_provider_map,
        wizard_prompt=_wizard_prompt,
        wizard_back_cls=WizardBack,
        wizard_cancel_cls=WizardCancel,
        normalize_provider_id_input=_normalize_provider_id_input,
        default_provider_id=DEFAULT_PROVIDER_ID,
        unique_runtime_id=_unique_runtime_id,
        normalize_provider=_normalize_provider,
        default_base_url=DEFAULT_BASE_URL,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        normalize_models_endpoint=_normalize_models_endpoint,
        prompt_validated_proxy_fields=_prompt_validated_proxy_fields,
        prompt_validated_timezone=_prompt_validated_timezone,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        upsert_provider=_upsert_provider,
        save_config=save_config,
        save_provider_credentials_with_probe=_save_provider_credentials_with_probe,
        load_config=load_config,
    )


def _quick_connect_official(cfg, preset_cli=None):
    from mms_command_tools import quick_connect_official

    return quick_connect_official(
        cfg,
        preset_cli=preset_cli,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        localize=_L,
        panel_cls=Panel,
        console=console,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        delegated_oauth_clis=MMC_DELEGATED_OAUTH_CLIS,
        wizard_prompt=_wizard_prompt,
        wizard_back_cls=WizardBack,
        wizard_cancel_cls=WizardCancel,
        account_map=_account_map,
        unique_runtime_id=_unique_runtime_id,
        normalize_account_id=_normalize_account_id,
        default_account_home=_default_account_home,
        prompt_validated_proxy_fields=_prompt_validated_proxy_fields,
        prompt_validated_timezone=_prompt_validated_timezone,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        normalize_account=_normalize_account,
        default_priority=DEFAULT_PRIORITY,
        ensure_account_config=_ensure_account_config,
        save_config=save_config,
        load_config=load_config,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
    )


def _usage_rows_for_runtime(runtime_kind, runtime_id):
    from mms_command_tools import usage_rows_for_runtime

    return usage_rows_for_runtime(runtime_kind, runtime_id, load_usage_stats=_load_usage_stats)


def _usage_summary_for_runtime(runtime_kind, runtime_id):
    from mms_command_tools import usage_summary_for_runtime

    return usage_summary_for_runtime(
        runtime_kind,
        runtime_id,
        usage_rows_for_runtime=_usage_rows_for_runtime,
    )


def _rescue_route_fallback_model_candidates(config_dir=None, *, failed_model="", limit=80):
    from mms_command_tools import rescue_route_fallback_model_candidates

    return rescue_route_fallback_model_candidates(
        config_dir,
        failed_model=failed_model,
        limit=limit,
        default_config_dir=CONFIG_DIR,
    )


def _rescue_fallback_model_candidates(cfg, rescue_event, *, limit=6):
    from mms_command_tools import rescue_fallback_model_candidates

    return rescue_fallback_model_candidates(
        cfg,
        rescue_event,
        limit=limit,
        load_usage_stats=_load_usage_stats,
        rescue_route_fallback_model_candidates=_rescue_route_fallback_model_candidates,
    )


def _rescue_default_fallback(cfg):
    from mms_command_tools import rescue_default_fallback

    return rescue_default_fallback(cfg)


def _rescue_hot_fallback_enabled_cfg(cfg):
    from mms_command_tools import rescue_hot_fallback_enabled_cfg

    return rescue_hot_fallback_enabled_cfg(cfg, pref_bool=_pref_bool)


def _set_rescue_default_fallback(cfg, *, model="", cli=""):
    from mms_command_tools import set_rescue_default_fallback

    return set_rescue_default_fallback(cfg, model=model, cli=cli)


def _set_rescue_hot_fallback_enabled(cfg, enabled=False):
    from mms_command_tools import set_rescue_hot_fallback_enabled

    return set_rescue_hot_fallback_enabled(cfg, enabled=enabled)


def _latest_rescue_hot_fallback_event():
    try:
        from mms_events import get_recent_events
    except Exception:
        return None
    from mms_command_tools import latest_rescue_hot_fallback_event

    return latest_rescue_hot_fallback_event(get_recent_events=get_recent_events)


def _rescue_landing_tui_payload(default_label, rescue_events, latest_fallback_event=None, hot_fallback_enabled=False):
    """Build the first Rescue settings page before drilling into packet history."""
    from mms_command_tools import rescue_landing_tui_payload

    return rescue_landing_tui_payload(
        default_label,
        rescue_events,
        latest_fallback_event=latest_fallback_event,
        hot_fallback_enabled=hot_fallback_enabled,
    )


def _registry_truth_tui_payload(status):
    """Build localized Registry Truth status/actions for the Settings detail page."""
    from mms_command_tools import registry_truth_tui_payload

    return registry_truth_tui_payload(status, localize=_L)


def _model_source_status_rows(summary):
    summary = summary if isinstance(summary, dict) else {}
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    registry_db = summary.get("registry_db") if isinstance(summary.get("registry_db"), dict) else {}
    legacy = summary.get("legacy_import") if isinstance(summary.get("legacy_import"), dict) else {}
    bundle = summary.get("generated_bundle") if isinstance(summary.get("generated_bundle"), dict) else {}
    counts = registry_db.get("counts") if isinstance(registry_db.get("counts"), dict) else {}
    candidates = legacy.get("candidates") if isinstance(legacy.get("candidates"), dict) else {}
    if not candidates and isinstance(registry_db.get("legacy_import_candidates"), dict):
        candidates = registry_db.get("legacy_import_candidates")
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    return [
        (_L("结果", "result"), summary.get("result") or "-"),
        (_L("状态", "status"), summary.get("status") or "-"),
        (_L("Ready", "Ready"), "yes" if summary.get("ready") else "no"),
        (_L("一句话", "headline"), summary.get("headline") or "-"),
        ("Root", root.get("config_root") or summary.get("config_root") or "-"),
        ("Mode", root.get("mode") or "-"),
        ("DB", registry_db.get("path") or "-"),
        (_L("DB 状态", "DB status"), registry_db.get("status") or "-"),
        (_L("来源快照", "source snapshots"), counts.get("source_snapshot", 0)),
        (_L("模型事实", "model facts"), counts.get("model_fact", 0)),
        (_L("Provider routes", "provider routes"), counts.get("provider_route", 0)),
        (_L("Legacy 冲突", "legacy conflicts"), legacy.get("conflict_count", 0)),
        (_L("Legacy 候选状态", "legacy candidate status"), candidates.get("status") or "not_imported"),
        (_L("Legacy 候选 routes", "legacy candidate routes"), candidates.get("provider_route_count", 0)),
        (_L("Legacy 下一步", "legacy next action"), legacy.get("next_action") or "-"),
        (_L("Bundle 状态", "bundle status"), bundle.get("status") or "-"),
        (_L("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (_L("Bundle runtime", "bundle runtime"), bundle.get("runtime_ready_status") or "unknown"),
        (_L("Router 缺失 key", "router missing keys"), bundle.get("router_missing_api_key_count", 0)),
        (_L("下一步", "next action"), next_action.get("label") or "-"),
        (_L("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]


def _model_source_status_report_payload(summary):
    return (
        _L("Model Source Status", "Model Source Status"),
        _model_source_status_rows(summary),
        _L("只读视图：不写 DB、不发布 bundle、不改变 runtime defaults。", "Read-only view: no DB writes, no bundle publish, runtime defaults unchanged."),
    )


def _consumer_bundle_status_rows(summary):
    summary = summary if isinstance(summary, dict) else {}
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    revisions = summary.get("component_revisions") if isinstance(summary.get("component_revisions"), dict) else {}
    files = summary.get("files") if isinstance(summary.get("files"), dict) else {}
    rules = summary.get("consumer_rules") if isinstance(summary.get("consumer_rules"), list) else []
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    return [
        (_L("结果", "result"), summary.get("result") or "-"),
        (_L("状态", "status"), summary.get("status") or "-"),
        (_L("Bundle 校验", "bundle verified"), "yes" if summary.get("verified") else "no"),
        (_L("入口", "entrypoint"), summary.get("consumer_entrypoint") or summary.get("manifest_path") or "-"),
        ("Root", root.get("config_root") or summary.get("config_root") or "-"),
        (_L("Bundle revision", "bundle revision"), revisions.get("bundle") or "-"),
        (_L("Route revision", "route revision"), revisions.get("route") or "-"),
        (_L("Policy revision", "policy revision"), revisions.get("policy") or "-"),
        (_L("Profile revision", "profile revision"), revisions.get("profile") or "-"),
        (_L("文件数", "file count"), len(files)),
        (_L("消费规则", "consumer rules"), " / ".join(str(item) for item in rules) or "-"),
        (_L("下一步", "next action"), next_action.get("label") or "-"),
        (_L("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]


def _consumer_bundle_status_report_payload(summary):
    return (
        _L("Consumer Bundle Status", "Consumer Bundle Status"),
        _consumer_bundle_status_rows(summary),
        _L("只读视图：验证 latest-approved manifest/hash；不写 DB、不发布 bundle、不读取 SQLite。", "Read-only view: verifies latest-approved manifest/hashes; no DB writes, no bundle publish, no SQLite reads."),
    )


def _registry_v2_save_plan_rows(plan):
    plan = plan if isinstance(plan, dict) else {}
    root = plan.get("root") if isinstance(plan.get("root"), dict) else {}
    db = plan.get("db") if isinstance(plan.get("db"), dict) else {}
    would_write = plan.get("would_write") if isinstance(plan.get("would_write"), dict) else {}
    legacy = would_write.get("legacy_compat_files") if isinstance(would_write.get("legacy_compat_files"), dict) else {}
    plan_json = plan.get("plan_json") if isinstance(plan.get("plan_json"), dict) else {}
    apply_plan = plan.get("apply_plan") if isinstance(plan.get("apply_plan"), dict) else {}
    blocked = ", ".join(str(item) for item in (plan.get("blocked_reasons") or [])) or "-"
    steps = " -> ".join(str(item) for item in (plan.get("ordered_steps") or [])) or "-"
    return [
        ("Root", root.get("config_root") or "-"),
        ("Mode", root.get("mode") or "-"),
        (_L("执行状态", "execution state"), plan.get("execution_state") or "-"),
        (_L("实际保存启用", "actual save enabled"), "yes" if plan.get("actual_save_enabled") else "no"),
        ("DB", db.get("path") or "-"),
        (_L("DB 存在", "DB exists"), "yes" if db.get("exists") else "no"),
        (_L("DB 备份目录", "DB backup dir"), db.get("backup_dir") or "-"),
        (_L("将备份 DB", "would backup DB"), "yes" if db.get("would_backup_existing_db") else "no"),
        (_L("DB candidate revision", "DB candidate revision"), "yes" if would_write.get("db_candidate_revision") else "no"),
        (_L("Secret backend", "secret backend"), "yes" if would_write.get("secret_backend") else "no"),
        (_L("Generated bundle", "generated bundle"), "yes" if would_write.get("generated_latest_approved_bundle") else "no"),
        (_L("Legacy config.toml", "legacy config.toml"), "yes" if legacy.get("config_toml") else "no"),
        (_L("Legacy model-policy.json", "legacy model-policy.json"), "yes" if legacy.get("model_policy_json") else "no"),
        (_L("Legacy credentials.sh", "legacy credentials.sh"), "yes" if legacy.get("credentials_sh") else "no"),
        (_L("阻塞原因", "blocked reasons"), blocked),
        (_L("Plan JSON", "Plan JSON"), plan_json.get("name") or "-"),
        (_L("Plan JSON 密钥", "Plan JSON secrets"), "redacted" if plan_json.get("redacted") else ("included" if plan_json.get("secrets_included") else "-")),
        (_L("WebUI 写入", "WebUI apply"), apply_plan.get("webui_button") or "-"),
        (_L("CLI 写入命令", "CLI apply command"), apply_plan.get("cli_apply_command") or "-"),
        (_L("步骤", "steps"), steps),
        (_L("下一步", "next step"), plan.get("next_implementation_step") or "-"),
    ]


def _registry_v2_save_plan_report_payload(plan):
    return (
        _L("Registry v2 Save Plan", "Registry v2 Save Plan"),
        _registry_v2_save_plan_rows(plan),
        _L("只读计划：不写 DB、不写 secret backend、不发布 bundle、不改变 runtime defaults。", "Read-only plan: no DB writes, no secret backend writes, no bundle publish, runtime defaults unchanged."),
    )


def _preview_doctor_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    bundle = summary.get("bundle") if isinstance(summary.get("bundle"), dict) else {}
    next_actions = [item for item in (summary.get("next_actions") or []) if isinstance(item, dict)]
    next_action = next_actions[0] if next_actions else {}
    rows = [
        (_L("结果", "result"), summary.get("result") or "-"),
        (_L("状态", "status"), summary.get("status") or "-"),
        (_L("Ready", "ready"), "yes" if summary.get("ready") else "no"),
        ("Root", summary.get("config_root") or "-"),
        (_L("候选 routes", "candidate routes"), counts.get("candidate_provider_routes", 0)),
        (_L("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (_L("Bundle runtime", "bundle runtime"), bundle.get("runtime_ready_status") or "unknown"),
        (_L("Router 缺失 key", "router missing keys"), counts.get("missing_api_keys", 0)),
        (_L("Preview secrets", "preview secrets"), counts.get("preview_secret_count", 0)),
        (_L("下一步", "next action"), next_action.get("label") or "-"),
        (_L("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        _L("Preview Doctor", "Preview Doctor"),
        rows,
        _L("只读检查：不写 DB、不发布 bundle、不改变 runtime defaults。", "Read-only check: no DB writes, no bundle publish, runtime defaults unchanged."),
    )


def _config_v2_promotion_plan_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    preview = summary.get("preview") if isinstance(summary.get("preview"), dict) else {}
    stable = summary.get("stable") if isinstance(summary.get("stable"), dict) else {}
    preview_root = preview.get("root") if isinstance(preview.get("root"), dict) else {}
    stable_root = stable.get("root") if isinstance(stable.get("root"), dict) else {}
    preview_check_summary = preview.get("check") if isinstance(preview.get("check"), dict) else {}
    bundle = preview.get("bundle") if isinstance(preview.get("bundle"), dict) else {}
    safety = summary.get("promotion_safety") if isinstance(summary.get("promotion_safety"), dict) else {}
    backup_plan = summary.get("stable_backup_plan") if isinstance(summary.get("stable_backup_plan"), dict) else {}
    comparison = summary.get("bundle_comparison") if isinstance(summary.get("bundle_comparison"), dict) else {}
    comparison_preview = comparison.get("preview") if isinstance(comparison.get("preview"), dict) else {}
    comparison_stable = comparison.get("stable") if isinstance(comparison.get("stable"), dict) else {}
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    rows = [
        (_L("结果", "result"), summary.get("result") or "-"),
        (_L("状态", "status"), summary.get("status") or "-"),
        (_L("Ready for review", "Ready for review"), "yes" if summary.get("ready_for_human_review") else "no"),
        (_L("Preview root", "Preview root"), preview_root.get("config_root") or "-"),
        (_L("Stable root", "Stable root"), stable_root.get("config_root") or "-"),
        (_L("Preview check", "Preview check"), preview_check_summary.get("result") or "-"),
        (_L("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (_L("Bundle 入口", "bundle entrypoint"), bundle.get("entrypoint") or "-"),
        (_L("Stable 写策略", "stable write policy"), safety.get("stable_write_policy") or "human_only"),
        (_L("Apply 启用", "apply enabled"), "yes" if summary.get("apply_enabled") or safety.get("apply_enabled") else "no"),
        (_L("必须备份", "backup required"), "yes" if backup_plan.get("requires_backup_before_apply") or safety.get("requires_backup") else "no"),
        (_L("本命令创建备份", "backup created by this command"), "yes" if backup_plan.get("would_create_backup") else "no"),
        (_L("Bundle 对比", "bundle comparison"), comparison.get("comparison_status") or "-"),
        (_L("Preview bundle", "preview bundle"), comparison_preview.get("bundle_revision") or comparison_preview.get("status") or "-"),
        (_L("Stable bundle", "stable bundle"), comparison_stable.get("bundle_revision") or comparison_stable.get("status") or "-"),
        (_L("阻塞原因", "blocked reasons"), ", ".join(str(item) for item in (summary.get("blocked_reasons") or [])) or "-"),
        (_L("下一步", "next action"), next_action.get("label") or "-"),
        (_L("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        _L("Config v2 Promote Plan", "Config v2 Promote Plan"),
        rows,
        _L("只读计划：停止在 human gate；不写 stable root、不改 Claude config、不发布 stable bundle。", "Read-only plan: stops at the human gate; no stable-root writes, no Claude config writes, no stable bundle publish."),
    )


def _config_v2_release_readiness_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    requirements = [item for item in (summary.get("requirements") or []) if isinstance(item, dict)]
    ok_count = sum(1 for item in requirements if item.get("ok"))
    blocked = [str(item) for item in (summary.get("blocked_requirements") or [])]
    promotion = summary.get("promotion_plan") if isinstance(summary.get("promotion_plan"), dict) else {}
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    rows = [
        (_L("结果", "result"), summary.get("result") or "-"),
        (_L("状态", "status"), summary.get("status") or "-"),
        (_L("Release complete", "release complete"), "yes" if summary.get("release_complete") else "no"),
        (_L("Ready for human gate", "ready for human gate"), "yes" if summary.get("ready_for_human_gate") else "no"),
        (_L("Human gate required", "human gate required"), "yes" if summary.get("human_gate_required") else "no"),
        (_L("完成阻塞", "completion blocker"), summary.get("completion_blocker") or "-"),
        (_L("Preview root", "Preview root"), summary.get("config_root") or "-"),
        (_L("Stable root", "Stable root"), summary.get("stable_config_root") or "-"),
        (_L("Requirements", "requirements"), f"{ok_count}/{len(requirements)} ok"),
        (_L("Blocked requirements", "blocked requirements"), ", ".join(blocked) or "-"),
        (_L("Promotion 状态", "promotion status"), promotion.get("status") or "-"),
        (_L("Promotion apply", "promotion apply"), "yes" if promotion.get("apply_enabled") else "no"),
        (_L("Promotion 阻塞", "promotion blockers"), ", ".join(str(item) for item in (promotion.get("blocked_reasons") or [])) or "-"),
        (_L("下一步", "next action"), next_action.get("label") or "-"),
        (_L("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        _L("Config v2 Release Readiness", "Config v2 Release Readiness"),
        rows,
        _L("只读审计：证明自动检查只到 stable promotion human gate；不写 stable root、不改 Claude config、不写 DB、不发布 bundle。", "Read-only audit: proves automated checks only reach the stable promotion human gate; no stable-root writes, no Claude config writes, no DB writes, no bundle publish."),
    )


def _model_source_status_tui_payload(summary):
    actions = [
        ("model_source_status", _L("查看 Model Source Status", "View Model Source Status")),
        ("consumer_bundle_status", _L("查看 Consumer Bundle", "View Consumer Bundle")),
        ("registry_v2_save_plan", _L("查看 v2 Save Plan", "View v2 Save Plan")),
        ("config_v2_promotion_plan", _L("查看 Promote Plan", "View Promote Plan")),
        ("config_v2_release_readiness", _L("查看 4.0 Readiness", "View 4.0 Readiness")),
        ("preview_doctor", _L("运行 Preview Doctor", "Run Preview Doctor")),
        ("check_staleness", _L("检查 Source Staleness", "Check Source Staleness")),
        ("refresh_due_sources", _L("刷新到期 Sources", "Refresh Due Sources")),
        ("scheduled_dry_run", _L("定时刷新 Dry Run", "Scheduled Refresh Dry Run")),
        ("scheduled_no_network", _L("定时刷新 No Network", "Scheduled Refresh No Network")),
        ("refresh_sources", _L("刷新全部 Sources", "Refresh Sources")),
        ("fetch_openrouter", _L("拉取 OpenRouter Catalog", "Fetch OpenRouter Catalog")),
        ("diff_openrouter", _L("对比 OpenRouter Candidate", "OpenRouter Candidate Diff")),
        ("publish_approved", _L("发布 Approved Bundle", "Publish Approved Bundle")),
        ("verify_approved", _L("验证 Approved Bundle", "Verify Approved Bundle")),
        ("doctor", _L("Registry Doctor / 状态", "Registry Doctor / Status")),
        ("back", _L("返回", "Back")),
    ]
    return _L("模型真源 / Registry Truth", "Registry Truth"), _model_source_status_rows(summary), actions


def _compact_tui_report_value(value, max_len=96):
    from mms_command_tools import compact_tui_report_value

    return compact_tui_report_value(value, max_len=max_len)


_SETTINGS_RESULT_RENDERED_TUI = False


def _settings_result_tui_available():
    from mms_command_tools import settings_result_tui_available

    return settings_result_tui_available(env=os.environ, stdin=sys.stdin, stdout=sys.stdout)


def _settings_result_tui_payload(title, rows, note="", *, ok=True):
    from mms_command_tools import settings_result_tui_payload

    return settings_result_tui_payload(title, rows, note, ok=ok, localize=_L)


def _select_settings_result_tui(title, rows, note="", *, ok=True):
    from mms_tui import select_channel_action_tui
    from mms_command_tools import select_settings_result_tui

    return select_settings_result_tui(
        title,
        rows,
        note,
        ok=ok,
        settings_result_tui_payload=_settings_result_tui_payload,
        select_channel_action_tui=select_channel_action_tui,
    )


def _print_settings_result_report(title, rows, note="", *, ok=True):
    global _SETTINGS_RESULT_RENDERED_TUI
    from mms_command_tools import display_settings_result_report, print_settings_result_report

    def mark_tui_rendered():
        global _SETTINGS_RESULT_RENDERED_TUI
        _SETTINGS_RESULT_RENDERED_TUI = True

    def clear_tui_rendered():
        global _SETTINGS_RESULT_RENDERED_TUI
        _SETTINGS_RESULT_RENDERED_TUI = False

    return print_settings_result_report(
        title,
        rows,
        note,
        ok=ok,
        settings_result_tui_available=_settings_result_tui_available,
        select_settings_result_tui=_select_settings_result_tui,
        mark_tui_rendered=mark_tui_rendered,
        clear_tui_rendered=clear_tui_rendered,
        ensure_rich=_ensure_rich,
        display_settings_result_report=display_settings_result_report,
        console=console,
    )


def _print_settings_error_report(title, exc):
    from mms_command_tools import print_settings_error_report

    return print_settings_error_report(
        title,
        exc,
        print_settings_result_report=_print_settings_result_report,
        localize=_L,
    )


def _rescue_default_fallback_report_payload(model, *, cleared=False, hot_fallback_enabled=False):
    from mms_command_tools import rescue_default_fallback_report_payload

    return rescue_default_fallback_report_payload(
        model,
        cleared=cleared,
        hot_fallback_enabled=hot_fallback_enabled,
        localize=_L,
    )


def _rescue_hot_fallback_toggle_report_payload(enabled, *, has_default=True):
    from mms_command_tools import rescue_hot_fallback_toggle_report_payload

    return rescue_hot_fallback_toggle_report_payload(enabled, has_default=has_default, localize=_L)


def _rescue_demo_packet_report_payload(payload):
    from mms_command_tools import rescue_demo_packet_report_payload

    return rescue_demo_packet_report_payload(payload, localize=_L)


def _rescue_paths_report_payload(selected_rescue):
    from mms_command_tools import rescue_paths_report_payload

    return rescue_paths_report_payload(selected_rescue, localize=_L)


def _rescue_handover_report_payload(handover, fallback_model):
    from mms_command_tools import rescue_handover_report_payload

    return rescue_handover_report_payload(handover, fallback_model, localize=_L)


def _registry_source_staleness_report_payload(summary):
    from mms_command_tools import registry_source_staleness_report_payload

    return registry_source_staleness_report_payload(summary, localize=_L)


def _registry_refresh_sources_report_payload(summary):
    from mms_command_tools import registry_refresh_sources_report_payload

    return registry_refresh_sources_report_payload(summary, localize=_L)


def _registry_scheduled_refresh_report_payload(summary):
    from mms_command_tools import registry_scheduled_refresh_report_payload

    return registry_scheduled_refresh_report_payload(summary, localize=_L)


def _registry_openrouter_fetch_report_payload(summary):
    from mms_command_tools import registry_openrouter_fetch_report_payload

    return registry_openrouter_fetch_report_payload(summary, localize=_L)


def _registry_openrouter_diff_report_payload(summary):
    from mms_command_tools import registry_openrouter_diff_report_payload

    return registry_openrouter_diff_report_payload(summary, localize=_L)


def _registry_publish_approved_report_payload(summary):
    from mms_command_tools import registry_publish_approved_report_payload

    return registry_publish_approved_report_payload(summary, localize=_L)


def _registry_verify_approved_report_payload(summary):
    from mms_command_tools import registry_verify_approved_report_payload

    return registry_verify_approved_report_payload(summary, localize=_L)


def _registry_doctor_report_payload(status):
    from mms_command_tools import registry_doctor_report_payload

    return registry_doctor_report_payload(status, localize=_L)


def _about_tui_payload(about_snapshot):
    """Build localized About status/actions for the Settings detail page."""
    from mms_command_tools import about_tui_payload

    return about_tui_payload(about_snapshot, config_path=CONFIG_PATH, localize=_L)


def _snapshot_guard_tui_payload():
    """Build localized Snapshot Guard status/actions for the Settings detail page."""
    from mms_command_tools import snapshot_guard_tui_payload

    return snapshot_guard_tui_payload(command_name=current_command(), localize=_L)


def _display_runtime_usage(runtime_kind, runtime_id, title):
    from mms_command_tools import display_runtime_usage

    return display_runtime_usage(
        runtime_kind,
        runtime_id,
        title,
        use_tui=_use_tui,
        clear_console=console.clear,
        usage_rows_for_runtime=_usage_rows_for_runtime,
        active_usage_path=_active_usage_path,
        pause_after_tui_report=_pause_after_tui_report,
        table_cls=Table,
        console=console,
    )


def _list_manage_targets(cfg):
    from mms_command_tools import build_manage_targets

    default_provider_id = cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)

    return build_manage_targets(
        cfg,
        default_provider_id=default_provider_id,
        resolve_provider_context=resolve_provider_context,
        usage_summary_for_runtime=_usage_summary_for_runtime,
        probe_account_status=_probe_account_status,
    )


def _select_manage_target(cfg):
    from mms_command_tools import select_manage_target, select_manage_target_fallback

    def select_target_tui(targets):
        from mms_tui import select_manage_target_tui
        return select_manage_target_tui(targets)

    return select_manage_target(
        cfg,
        list_manage_targets=_list_manage_targets,
        use_tui=_use_tui,
        select_manage_target_tui=select_target_tui,
        select_manage_target_fallback=lambda targets: select_manage_target_fallback(
            targets,
            ensure_rich=_ensure_rich,
            panel_cls=Panel,
            table_cls=Table,
            prompt_cls=Prompt,
            console=console,
        ),
        console=console,
    )


def _update_provider_model_overrides(cfg, provider_id, *, extra_models=None, hidden_models=None, models_endpoint=None):
    from mms_command_tools import update_provider_model_overrides

    return update_provider_model_overrides(
        cfg,
        provider_id,
        extra_models=extra_models,
        hidden_models=hidden_models,
        models_endpoint=models_endpoint,
        normalize_model_id_list=_normalize_model_id_list,
        normalize_models_endpoint=_normalize_models_endpoint,
        normalize_provider=_normalize_provider,
        save_config=save_config,
        invalidate_probe_cache=_invalidate_probe_cache,
        load_config=load_config,
    )


def _display_provider_model_table(provider, probe):
    from mms_speed_stats import get_speed_entry
    from mms_command_tools import display_provider_model_table

    _ensure_rich()
    return display_provider_model_table(
        provider,
        probe,
        get_speed_entry=get_speed_entry,
        infer_model_family=_infer_model_family,
        model_capability_summary=_model_capability_summary,
        model_cli_summary=_model_cli_summary,
        model_source_label=_model_source_label,
        ttfb_label=_ttfb_label,
        tps_label=_tps_label,
        table_cls=Table,
        console=console,
    )


def _pause_after_tui_report(prompt_text="按 Enter 返回"):
    global _SETTINGS_RESULT_RENDERED_TUI
    from mms_command_tools import pause_after_tui_report

    def tui_rendered():
        return bool(_SETTINGS_RESULT_RENDERED_TUI)

    def clear_tui_rendered():
        global _SETTINGS_RESULT_RENDERED_TUI
        _SETTINGS_RESULT_RENDERED_TUI = False

    return pause_after_tui_report(
        prompt_text,
        tui_rendered=tui_rendered,
        clear_tui_rendered=clear_tui_rendered,
        ensure_rich=_ensure_rich,
        input_func=input,
        console=console,
    )


def _manage_provider_models(cfg, provider_id):
    from mms_command_tools import manage_provider_models

    def select_action_tui(title, info_lines, actions):
        from mms_tui import select_channel_action_tui
        return select_channel_action_tui(title, info_lines, actions)

    return manage_provider_models(
        cfg,
        provider_id,
        ensure_rich=_ensure_rich,
        resolve_provider_context=resolve_provider_context,
        probe_models=_probe_models,
        model_source_label=_model_source_label,
        use_tui=_use_tui,
        select_channel_action_tui=select_action_tui,
        clear_console=console.clear,
        display_provider_model_table=_display_provider_model_table,
        pause_after_tui_report=_pause_after_tui_report,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        normalize_model_id_list=_normalize_model_id_list,
        normalize_models_endpoint=_normalize_models_endpoint,
        update_provider_model_overrides=_update_provider_model_overrides,
        panel_cls=Panel,
        console=console,
    )


def _select_provider_for_models(cfg):
    from mms_command_tools import select_provider_for_models

    return select_provider_for_models(
        cfg,
        list_manage_targets=_list_manage_targets,
        table_cls=Table,
        prompt_cls=Prompt,
        console=console,
    )


def _select_provider_for_warm(cfg):
    from mms_command_tools import select_provider_for_warm

    return select_provider_for_warm(cfg, select_provider_for_models=_select_provider_for_models)


def _recent_models_for_provider(provider_id):
    from mms_command_tools import recent_models_for_provider

    return recent_models_for_provider(provider_id, usage_rows_for_runtime=_usage_rows_for_runtime)


def _pick_manual_models(models):
    from mms_command_tools import pick_manual_models

    return pick_manual_models(
        models,
        table_cls=Table,
        prompt_cls=Prompt,
        console=console,
    )


def _warm_model_request(provider, model_name):
    from mms_command_tools import warm_model_request

    def resolve_anthropic_base_url(provider, *, probe_model):
        from mms_launchers import _resolve_anthropic_base_url
        return _resolve_anthropic_base_url(provider, probe_model=probe_model)

    return warm_model_request(
        provider,
        model_name,
        ensure_httpx=_ensure_httpx,
        get_httpx=lambda: httpx,
        resolve_anthropic_base_url=resolve_anthropic_base_url,
        runtime_httpx_request=_runtime_httpx_request,
        provider_openai_base_url=_provider_openai_base_url,
    )


def handle_warm_command(cfg, argv):
    from mms_command_tools import handle_warm_command as handle_warm_command_impl

    return handle_warm_command_impl(
        cfg,
        argv,
        command_name=current_command(),
        provider_map=_provider_map,
        select_provider_for_warm=_select_provider_for_warm,
        resolve_provider_context=resolve_provider_context,
        probe_models=_probe_models,
        recent_models_for_provider=_recent_models_for_provider,
        pick_manual_models=_pick_manual_models,
        warm_model_request=_warm_model_request,
        text_cls=Text,
        panel_cls=Panel,
        prompt_cls=Prompt,
        confirm_cls=Confirm,
        table_cls=Table,
        console=console,
    )


def handle_models_command(cfg, argv):
    from mms_command_tools import handle_models_command as handle_models_command_impl

    return handle_models_command_impl(
        cfg,
        argv,
        command_name=current_command(),
        provider_map=_provider_map,
        select_provider_for_models=_select_provider_for_models,
        manage_provider_models=_manage_provider_models,
        text_cls=Text,
        console=console,
    )


def _manage_provider_target(cfg, provider_id):
    from mms_command_tools import manage_provider_target

    def select_action_tui(title, info_lines, actions):
        from mms_tui import select_channel_action_tui
        return select_channel_action_tui(title, info_lines, actions)

    return manage_provider_target(
        cfg,
        provider_id,
        resolve_provider_context=resolve_provider_context,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        use_tui=_use_tui,
        select_channel_action_tui=select_action_tui,
        ensure_rich=_ensure_rich,
        panel_cls=Panel,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        display_runtime_usage=_display_runtime_usage,
        manage_provider_models=_manage_provider_models,
        default_provider_id=DEFAULT_PROVIDER_ID,
        save_config=save_config,
        load_config=load_config,
        normalize_provider_id_input=_normalize_provider_id_input,
        handle_provider_rename_config=_handle_provider_rename_config,
        handle_provider_credentials_config=_handle_provider_credentials_config,
        provider_map=_provider_map,
        handle_provider_remove_config=_handle_provider_remove_config,
        console=console,
    )


def _prompt_account_rename(cfg, account_id):
    from mms_command_tools import prompt_account_rename

    return prompt_account_rename(
        cfg,
        account_id,
        ensure_rich=_ensure_rich,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        account_map=_account_map,
        handle_account_rename_config=_handle_account_rename_config,
        load_config=load_config,
        console=console,
    )


def _manage_account_target(cfg, account_id):
    from mms_command_tools import manage_account_target

    def select_action_tui(title, info_lines, actions):
        from mms_tui import select_channel_action_tui
        return select_channel_action_tui(title, info_lines, actions)

    return manage_account_target(
        cfg,
        account_id,
        resolve_account_context=resolve_account_context,
        probe_account_status=_probe_account_status,
        use_tui=_use_tui,
        select_channel_action_tui=select_action_tui,
        ensure_rich=_ensure_rich,
        panel_cls=Panel,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        display_runtime_usage=_display_runtime_usage,
        run_account_login=_run_account_login,
        save_config=save_config,
        load_config=load_config,
        prompt_account_rename=_prompt_account_rename,
        handle_account_edit_config=_handle_account_edit_config,
        handle_account_remove_config=_handle_account_remove_config,
        account_map=_account_map,
        console=console,
    )


def _run_account_mgmt_tui(cfg):
    """账号管理：列表选择 + 详情操作。"""
    from mms_command_tools import run_account_mgmt_tui

    def select_target_tui(targets):
        from mms_tui import select_manage_target_tui
        return select_manage_target_tui(targets)

    return run_account_mgmt_tui(
        cfg,
        use_tui=_use_tui,
        select_manage_target_tui=select_target_tui,
        manage_account_target=_manage_account_target,
        usage_summary_for_runtime=_usage_summary_for_runtime,
        console=console,
    )


def _run_recommend_mgmt_tui(cfg):
    """推荐模型管理：查看/添加/移除。"""
    from mms_command_tools import run_recommend_mgmt_tui

    def load_select_channel_action_tui():
        from mms_tui import select_channel_action_tui
        return select_channel_action_tui

    return run_recommend_mgmt_tui(
        cfg,
        use_tui=_use_tui,
        load_select_channel_action_tui=load_select_channel_action_tui,
        ensure_rich=_ensure_rich,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        save_config=save_config,
        console=console,
    )


def run_manage_channels(cfg):
    from mms_command_tools import run_manage_channels as run_manage_channels_impl

    return run_manage_channels_impl(
        cfg,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        select_manage_target=_select_manage_target,
        manage_provider_target=_manage_provider_target,
        manage_account_target=_manage_account_target,
    )


def run_connect_wizard(cfg):
    from mms_command_tools import run_connect_wizard as run_connect_wizard_impl

    def load_select_connect_tui():
        from mms_tui import select_connect_tui
        return select_connect_tui

    return run_connect_wizard_impl(
        cfg,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        use_tui=_use_tui,
        load_select_connect_tui=load_select_connect_tui,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        quick_connect_gateway=_quick_connect_gateway,
        quick_connect_official=_quick_connect_official,
        run_manage_channels=run_manage_channels,
        handle_config_migrate=_handle_config_migrate,
        load_config=load_config,
        console=console,
    )


def detect_working_base_url(configured_url, path, headers, body=None, timeout=5, runtime=None):
    """
    公共 URL 探测工具：自动兼容 /v1 有无后缀的 gateway。

    原理：
      候选1 = without_v1  (去掉 /v1，通常正确)
      候选2 = with_v1     (保留/补上 /v1)
      对每个候选发送 candidate + path，返回第一个 HTTP 200 的 candidate。

    参数：
      configured_url  用户配置的原始地址（可带也可不带 /v1）
      path            请求路径，如 "/models" 或 "/v1/messages"
      headers         请求头 dict
      body            POST body bytes；为 None 时发 GET
      timeout         单次超时（秒），默认 5s

    返回：working_base_url (str) | None
    """
    from mms_command_tools import detect_working_base_url as detect_working_base_url_impl

    return detect_working_base_url_impl(
        configured_url,
        path,
        headers,
        body=body,
        timeout=timeout,
        runtime=runtime,
        ensure_httpx=_ensure_httpx,
        get_httpx=lambda: httpx,
        runtime_httpx_request=_runtime_httpx_request,
    )

# _probe_models 结果缓存：key = provider_id, value = (timestamp, result)
_PROBE_CACHE = {}
_PROBE_CACHE_TTL = 300  # 5 分钟内复用（内存）
_PROBE_FILE_CACHE_DIR = os.path.join(PRIMARY_CONFIG_DIR, "cache")
_PROBE_FILE_CACHE_TTL = 86400  # 文件缓存 24 小时
_PROBE_FILE_CACHE_NEGATIVE_TTL = 600  # 失败/空模型列表缓存 10 分钟，避免频繁慢探测
_PROBE_ASYNC_REFRESH_AFTER = 1800  # 30 分钟后启动时触发后台刷新
_PROBE_ASYNC_MIN_INTERVAL = 300  # 5 分钟内同一 provider 最多异步刷新一次
_PROBE_ASYNC_EXECUTOR = None
_PROBE_ASYNC_LOCK = threading.Lock()
_PROBE_ASYNC_INFLIGHT = set()
_PROBE_ASYNC_LAST = {}


def _probe_async_refresh_after(cfg=None):
    from mms_command_tools import probe_async_refresh_after

    return probe_async_refresh_after(
        cfg,
        default=_PROBE_ASYNC_REFRESH_AFTER,
        normalize_positive_seconds=_normalize_positive_seconds,
    )


def _probe_async_min_interval(cfg=None):
    from mms_command_tools import probe_async_min_interval

    return probe_async_min_interval(
        cfg,
        default=_PROBE_ASYNC_MIN_INTERVAL,
        normalize_positive_seconds=_normalize_positive_seconds,
    )


def _probe_file_cache_path(provider_id):
    from mms_command_tools import probe_file_cache_path

    return probe_file_cache_path(provider_id, probe_file_cache_dir=_PROBE_FILE_CACHE_DIR)


def _invalidate_probe_cache(provider_id):
    from mms_command_tools import invalidate_probe_cache

    return invalidate_probe_cache(
        provider_id,
        probe_cache=_PROBE_CACHE,
        probe_file_cache_path=_probe_file_cache_path,
    )


def _probe_cache_age(provider_id):
    from mms_command_tools import probe_cache_age

    return probe_cache_age(provider_id, probe_file_cache_path=_probe_file_cache_path)


def _load_probe_file_cache(provider_id, allow_stale=False):
    """从文件读取 probe 缓存。

    默认仅在 TTL 内返回；allow_stale=True 时，允许读取过期缓存，
    适合启动/TUI 首屏阶段先快速展示，再由后台预热异步刷新。
    """
    from mms_command_tools import load_probe_file_cache

    return load_probe_file_cache(
        provider_id,
        allow_stale=allow_stale,
        probe_file_cache_path=_probe_file_cache_path,
        normalize_model_id_list=_normalize_model_id_list,
        file_cache_ttl=_PROBE_FILE_CACHE_TTL,
        negative_ttl=_PROBE_FILE_CACHE_NEGATIVE_TTL,
    )


def _save_probe_file_cache(provider_id, result):
    """将 probe 结果写入文件缓存。

    remote 成功结果、fallback/manual 模型结果、负缓存都应落盘，
    避免模型选择页反复慢探测。
    """
    from mms_command_tools import save_probe_file_cache

    return save_probe_file_cache(
        provider_id,
        result,
        probe_file_cache_dir=_PROBE_FILE_CACHE_DIR,
        probe_file_cache_path=_probe_file_cache_path,
    )


def _base_probe_result_from_cache(provider_id, file_cached):
    from mms_command_tools import base_probe_result_from_cache

    return base_probe_result_from_cache(provider_id, file_cached)


def _ensure_probe_async_executor():
    from mms_command_tools import ensure_probe_async_executor

    def set_executor(value):
        global _PROBE_ASYNC_EXECUTOR
        _PROBE_ASYNC_EXECUTOR = value

    def executor_factory():
        from concurrent.futures import ThreadPoolExecutor

        return ThreadPoolExecutor(max_workers=4)

    return ensure_probe_async_executor(
        _PROBE_ASYNC_EXECUTOR,
        set_executor=set_executor,
        executor_factory=executor_factory,
    )


def _schedule_probe_refresh(provider, cfg=None, *, reason="stale"):
    from mms_command_tools import schedule_probe_refresh

    return schedule_probe_refresh(
        provider,
        cfg,
        reason=reason,
        default_provider_id=DEFAULT_PROVIDER_ID,
        probe_async_min_interval=_probe_async_min_interval,
        lock=_PROBE_ASYNC_LOCK,
        inflight=_PROBE_ASYNC_INFLIGHT,
        last_started=_PROBE_ASYNC_LAST,
        probe_models=_probe_models,
        ensure_probe_async_executor=_ensure_probe_async_executor,
        time_func=time.time,
    )


def _probe_models_for_startup(cfg, provider, emit_output=True):
    from mms_command_tools import probe_models_for_startup

    return probe_models_for_startup(
        cfg,
        provider,
        emit_output=emit_output,
        default_provider_id=DEFAULT_PROVIDER_ID,
        probe_cache=_PROBE_CACHE,
        probe_cache_ttl=_PROBE_CACHE_TTL,
        load_probe_file_cache=_load_probe_file_cache,
        base_probe_result_from_cache=_base_probe_result_from_cache,
        schedule_probe_refresh=_schedule_probe_refresh,
        apply_provider_model_patch=_apply_provider_model_patch,
        probe_models=_probe_models,
        console=console,
        time_func=time.time,
    )


def _provider_supports_mimo_anthropic_selectors(provider):
    from mms_command_tools import provider_supports_mimo_anthropic_selectors

    return provider_supports_mimo_anthropic_selectors(provider)


def _derived_model_aliases(base_models, provider=None):
    from mms_command_tools import derived_model_aliases

    return derived_model_aliases(
        base_models,
        provider,
        provider_supports_mimo_anthropic_selectors=_provider_supports_mimo_anthropic_selectors,
    )


def _apply_provider_model_patch(provider, base_result):
    from mms_command_tools import apply_provider_model_patch

    return apply_provider_model_patch(
        provider,
        base_result,
        normalize_model_id_list=_normalize_model_id_list,
        derived_model_aliases=_derived_model_aliases,
    )


def _probe_models(provider, emit_output=True, force_refresh=False, skip_cache=False):
    from mms_command_tools import probe_models

    return probe_models(
        provider,
        emit_output=emit_output,
        force_refresh=force_refresh,
        skip_cache=skip_cache,
        default_provider_id=DEFAULT_PROVIDER_ID,
        probe_cache=_PROBE_CACHE,
        probe_cache_ttl=_PROBE_CACHE_TTL,
        invalidate_probe_cache=_invalidate_probe_cache,
        load_probe_file_cache=_load_probe_file_cache,
        base_probe_result_from_cache=_base_probe_result_from_cache,
        apply_provider_model_patch=_apply_provider_model_patch,
        provider_openai_base_url=_provider_openai_base_url,
        ensure_httpx=_ensure_httpx,
        get_httpx=lambda: httpx,
        runtime_httpx_request=_runtime_httpx_request,
        save_probe_file_cache=_save_probe_file_cache,
        provider_label=_provider_label,
        console=console,
        time_func=time.time,
    )


def _warm_probe_cache_async(cfg, default_provider):
    """后台异步刷新 provider probe 文件缓存。

    无缓存或缓存过旧的 provider 会被刷新，但不会阻塞当前启动。
    """
    from mms_command_tools import warm_probe_cache_async

    return warm_probe_cache_async(
        cfg,
        default_provider,
        probe_async_refresh_after=_probe_async_refresh_after,
        probe_cache_age=_probe_cache_age,
        schedule_probe_refresh=_schedule_probe_refresh,
        resolve_provider_context=resolve_provider_context,
    )


def fetch_models(provider):
    from mms_command_tools import fetch_models as fetch_models_helper

    return fetch_models_helper(provider, probe_models=_probe_models)


def _model_validation_findings(provider, probe):
    from mms_command_tools import model_validation_findings

    return model_validation_findings(provider, probe, provider_label=_provider_label)


def _build_model_recovery_actions(cfg, provider, probe):
    from mms_command_tools import build_model_recovery_actions

    return build_model_recovery_actions(cfg, provider, probe, provider_map=_provider_map)


def _print_model_probe_details(probe):
    from mms_command_tools import display_model_probe_details

    return display_model_probe_details(probe, panel_cls=Panel, console=console)


def _select_provider_interactive(cfg, current_provider_id):
    from mms_command_tools import select_provider_interactive

    return select_provider_interactive(
        cfg,
        current_provider_id,
        resolve_provider_context=resolve_provider_context,
        table_cls=Table,
        prompt_cls=Prompt,
        console=console,
    )


def _pick_recovery_actions(findings, actions):
    use_tui = _use_tui()
    select_actions_tui = None
    if use_tui:
        try:
            from mms_tui import select_actions_tui
        except ImportError:
            select_actions_tui = None
    from mms_command_tools import pick_recovery_actions

    return pick_recovery_actions(
        findings,
        actions,
        use_tui=use_tui,
        select_actions_tui=select_actions_tui,
        panel_cls=Panel,
        prompt_cls=Prompt,
        console=console,
    )


def _run_recovery_action(cfg, provider, probe, action_id):
    from mms_command_tools import run_recovery_action

    return run_recovery_action(
        cfg,
        provider,
        probe,
        action_id,
        display_model_probe_details=_print_model_probe_details,
        setup_provider_credentials=setup_provider_credentials,
        select_provider_interactive=_select_provider_interactive,
        console=console,
    )


def setup_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    from mms_command_tools import setup_provider_credentials as setup_provider_credentials_helper

    return setup_provider_credentials_helper(
        provider,
        existing_base_url,
        existing_api_key,
        allow_keep,
        prompt_provider_credentials=_prompt_provider_credentials,
        save_provider_credentials_with_probe=_save_provider_credentials_with_probe,
    )


def setup_api_credentials(existing_base_url="", existing_api_key="", allow_keep=False):
    from mms_command_tools import setup_api_credentials as setup_api_credentials_helper

    return setup_api_credentials_helper(
        existing_base_url,
        existing_api_key,
        allow_keep,
        default_provider=_default_provider,
        setup_provider_credentials=setup_provider_credentials,
    )


def ensure_provider_credentials(cfg, provider_id=None):
    from mms_command_tools import ensure_provider_credentials as ensure_provider_credentials_helper

    return ensure_provider_credentials_helper(
        cfg,
        provider_id,
        get_provider_definition=get_provider_definition,
        load_provider_credentials=load_provider_credentials,
        resolve_provider_context=resolve_provider_context,
        setup_provider_credentials=setup_provider_credentials,
    )


def ensure_api_credentials():
    from mms_command_tools import ensure_api_credentials as ensure_api_credentials_helper

    return ensure_api_credentials_helper(
        default_config=_default_config,
        ensure_provider_credentials=ensure_provider_credentials,
    )


def setup_wizard(ui_language=None):
    from mms_command_tools import setup_wizard as setup_wizard_impl

    return setup_wizard_impl(
        ui_language,
        normalize_language=normalize_language,
        set_language=set_language,
        display_title=display_title,
        localize=_L,
        panel_cls=Panel,
        default_config=_default_config,
        setup_provider_credentials=setup_provider_credentials,
        get_provider_definition=get_provider_definition,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        mode_all=MODE_ALL,
        mode_recommended=MODE_RECOMMENDED,
        save_config=save_config,
        config_path=CONFIG_PATH,
        console=console,
    )


# ── Model Fetching ──────────────────────────────────────

def ensure_models_ready(cfg, provider):
    from mms_command_tools import ensure_models_ready as ensure_models_ready_helper

    return ensure_models_ready_helper(
        cfg,
        provider,
        probe_models_for_startup=_probe_models_for_startup,
        stdin=sys.stdin,
        console=console,
        config_command_hint=config_command_hint,
        exit_func=sys.exit,
        model_validation_findings=_model_validation_findings,
        build_model_recovery_actions=_build_model_recovery_actions,
        pick_recovery_actions=_pick_recovery_actions,
        run_recovery_action=_run_recovery_action,
        probe_cache=_PROBE_CACHE,
        probe_file_cache_path=_probe_file_cache_path,
        remove_file=os.remove,
        probe_models=_probe_models,
        default_provider_id=DEFAULT_PROVIDER_ID,
    )


def categorize_models(models):
    from mms_command_tools import categorize_models as categorize_models_impl

    return categorize_models_impl(
        models,
        filter_visible_models=_filter_visible_models,
        infer_model_family=_infer_model_family,
    )


def display_models(models, role=MODE_ALL, recommend=None):
    _ensure_rich()
    from mms_command_tools import display_models as display_models_impl

    return display_models_impl(
        models,
        role,
        recommend,
        ensure_rich=_ensure_rich,
        categorize_models=categorize_models,
        normalize_user_role=normalize_user_role,
        mode_recommended=MODE_RECOMMENDED,
        model_capability_summary=_model_capability_summary,
        model_cli_summary=_model_cli_summary,
        table_cls=Table,
        console=console,
    )


def _filter_models_for_display(models, role=MODE_ALL, recommend=None):
    from mms_command_tools import filter_models_for_display

    return filter_models_for_display(
        models,
        role,
        recommend,
        categorize_models=categorize_models,
        normalize_user_role=normalize_user_role,
        mode_recommended=MODE_RECOMMENDED,
    )


def _group_models_for_custom(models, role=MODE_ALL, recommend=None):
    from mms_command_tools import group_models_for_custom

    return group_models_for_custom(
        models,
        role,
        recommend,
        filter_models_for_display=_filter_models_for_display,
        infer_model_family=_infer_model_family,
    )


def _group_models_by_family_and_provider(aggregated_models, role=MODE_ALL, recommend=None):
    from mms_command_tools import group_models_by_family_and_provider

    return group_models_by_family_and_provider(
        aggregated_models,
        role,
        recommend,
        filter_models_for_display=_filter_models_for_display,
        infer_model_family=_infer_model_family,
    )


def _select_custom_model(models, cli_name, role=MODE_ALL, recommend=None, use_tui=False, cfg=None, default_provider=None, default_models=None):
    from mms_command_tools import select_custom_model

    return select_custom_model(
        models,
        cli_name,
        role,
        recommend,
        use_tui,
        group_models_by_family_and_provider=_group_models_by_family_and_provider,
        group_models_for_custom=_group_models_for_custom,
        table_cls=Table,
        int_prompt_cls=IntPrompt,
        console=console,
        exit_func=sys.exit,
    )


def _ensure_models_cache_available(models_cache):
    from mms_command_tools import ensure_models_cache_available

    return ensure_models_cache_available(models_cache, console=console)


def _model_matches_account_cli(cli_name, model_name):
    from mms_command_tools import model_matches_account_cli

    return model_matches_account_cli(cli_name, model_name)


def _provider_supports_cli_name(provider, cli_name):
    from mms_command_tools import provider_supports_cli_name

    return provider_supports_cli_name(provider, cli_name)


def _provider_supports_model_for_cli(provider, cli_name, model_name=None):
    from mms_command_tools import provider_supports_model_for_cli
    from mms_launchers import _pi_model_available_for_runtime

    return provider_supports_model_for_cli(
        provider,
        cli_name,
        model_name,
        model_matches_account_cli=_model_matches_account_cli,
        provider_supports_cli_name=_provider_supports_cli_name,
        bridge_clis_for_model=_bridge_clis_for_model,
        pi_model_available_for_runtime=_pi_model_available_for_runtime,
    )


def _provider_candidates(cfg, default_provider, default_models):
    from mms_command_tools import provider_candidates

    return provider_candidates(
        cfg,
        default_provider,
        default_models,
        load_probe_file_cache=_load_probe_file_cache,
        resolve_provider_context=resolve_provider_context,
    )


def _provider_models_for_cli(cli_name, models, provider=None):
    from mms_command_tools import provider_models_for_cli
    from mms_launchers import _pi_model_available_for_runtime

    return provider_models_for_cli(
        cli_name,
        models,
        cli_model_family_hints=CLI_MODEL_FAMILY_HINTS,
        provider=provider,
        pi_model_available_for_runtime=_pi_model_available_for_runtime,
    )


def _provider_effective_models(provider, cached_models, cfg=None):
    from mms_command_tools import provider_effective_models

    return provider_effective_models(
        provider,
        cached_models,
        cfg,
        schedule_probe_refresh=_schedule_probe_refresh,
        apply_provider_model_patch=_apply_provider_model_patch,
    )


def _aggregate_provider_models(cfg, cli_name, default_provider, default_models):
    from mms_command_tools import aggregate_provider_models

    return aggregate_provider_models(
        cfg,
        cli_name,
        default_provider,
        default_models,
        provider_candidates=_provider_candidates,
        provider_has_configured_base_url=_provider_has_configured_base_url,
        provider_effective_models=_provider_effective_models,
        provider_label=_provider_label,
        mms_model_visible=_mms_model_visible,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        default_provider_id=DEFAULT_PROVIDER_ID,
    )


def _resolve_best_provider(cfg, model_name, default_provider, default_models,
                           cli_name=None, protocol=None):
    from mms_command_tools import resolve_best_provider

    return resolve_best_provider(
        cfg,
        model_name,
        default_provider,
        default_models,
        cli_name=cli_name,
        protocol=protocol,
        provider_candidates=_provider_candidates,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        provider_has_configured_base_url=_provider_has_configured_base_url,
        provider_effective_models=_provider_effective_models,
        normalize_role=_normalize_role,
        runtime_priority_for_model=_runtime_priority_for_model,
        provider_label=_provider_label,
        runtime_with_priority=_runtime_with_priority,
        role_weights=ROLE_WEIGHTS,
    )



def _build_model_families_for_cli(cfg, cli_name, default_provider, default_models):
    from mms_command_tools import build_model_families_for_cli

    return build_model_families_for_cli(
        cfg,
        cli_name,
        default_provider,
        default_models,
        provider_candidates=_provider_candidates,
        provider_has_configured_base_url=_provider_has_configured_base_url,
        provider_effective_models=_provider_effective_models,
        normalize_role=_normalize_role,
        runtime_priority_for_model=_runtime_priority_for_model,
        runtime_with_priority=_runtime_with_priority,
        provider_label=_provider_label,
        mms_model_visible=_mms_model_visible,
        infer_model_family=_infer_model_family,
        load_usage_stats=_load_usage_stats,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        role_weights=ROLE_WEIGHTS,
        default_provider_id=DEFAULT_PROVIDER_ID,
    )


def _provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=None):
    from mms_command_tools import provider_options_for_model

    return provider_options_for_model(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_info=model_info,
        resolve_model_name=_resolve_model_name,
        infer_model_family=_infer_model_family,
        probe_debug_logger=_probe_debug_logger,
        provider_candidates=_provider_candidates,
        provider_has_configured_base_url=_provider_has_configured_base_url,
        provider_effective_models=_provider_effective_models,
        provider_models_for_cli=_provider_models_for_cli,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        provider_supports_cli_name=_provider_supports_cli_name,
        runtime_with_priority=_runtime_with_priority,
        runtime_choice_label=_runtime_choice_label,
        provider_label=_provider_label,
        runtime_priority_for_family=_runtime_priority_for_family,
        default_priority=DEFAULT_PRIORITY,
    )


def _account_options_for_model(cfg, cli_name, default_models, model_info=None, allow_selected_model=False):
    from mms_command_tools import account_options_for_model

    return account_options_for_model(
        cfg,
        cli_name,
        default_models,
        model_info=model_info,
        allow_selected_model=allow_selected_model,
        resolve_model_name=_resolve_model_name,
        infer_model_family=_infer_model_family,
        oauth_capable_clis=OAUTH_CAPABLE_CLIS,
        model_matches_account_cli=_model_matches_account_cli,
        resolve_account_context=resolve_account_context,
        runtime_with_priority=_runtime_with_priority,
        runtime_choice_label=_runtime_choice_label,
        account_label=_account_label,
        default_priority=DEFAULT_PRIORITY,
    )


def _broker_options_for_cli(cfg, cli_name, model_info=None):
    # 止血：broker 先退出默认入口，只保留显式 mms broker 命令链。
    return []


def _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models):
    from mms_command_tools import resolve_provider_for_cli

    return resolve_provider_for_cli(
        cfg, cli_name, default_provider, default_models,
        provider_options_for_model=_provider_options_for_model, cli_model_family_hints=CLI_MODEL_FAMILY_HINTS,
    )


def _resolve_source_default_index(options, preferred_cli):
    from mms_command_tools import resolve_source_default_index

    return resolve_source_default_index(options, preferred_cli)


def _resolve_launch_runtime(cfg, cli_name, default_provider, default_models, account_id=None, provider_id=None):
    from mms_command_tools import resolve_launch_runtime

    return resolve_launch_runtime(
        cfg, cli_name, default_provider, default_models, account_id=account_id, provider_id=provider_id,
        resolve_provider_context=resolve_provider_context, resolve_provider_for_cli=_resolve_provider_for_cli,
        probe_models=_probe_models, managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        resolve_account_context=resolve_account_context,
    )


def _runtime_choice_label(runtime):
    from mms_command_tools import runtime_choice_label

    return runtime_choice_label(runtime, account_label=_account_label, provider_label=_provider_label)


def _list_runtime_sources(cfg, cli_name, default_provider, default_models, model_info=None, allow_selected_model_accounts=False):
    from mms_command_tools import list_runtime_sources

    return list_runtime_sources(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_info=model_info,
        allow_selected_model_accounts=allow_selected_model_accounts,
        provider_options_for_model=_provider_options_for_model,
        account_options_for_model=_account_options_for_model,
        broker_options_for_cli=_broker_options_for_cli,
        resolve_source_default_index=_resolve_source_default_index,
        default_priority=DEFAULT_PRIORITY,
    )


def _runtime_source_kind_label(runtime):
    from mms_command_tools import runtime_source_kind_label

    return runtime_source_kind_label(runtime)


def _choose_runtime_source(
    cfg,
    cli_name,
    default_provider,
    default_models,
    account_id=None,
    provider_id=None,
    model_info=None,
    allow_selected_model_accounts=False,
):
    from mms_command_tools import choose_runtime_source

    return choose_runtime_source(
        cfg,
        cli_name,
        default_provider,
        default_models,
        account_id=account_id,
        provider_id=provider_id,
        model_info=model_info,
        allow_selected_model_accounts=allow_selected_model_accounts,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        runtime_with_launch_preferences=_runtime_with_launch_preferences,
        resolve_launch_runtime=_resolve_launch_runtime,
        trace_runtime_choice=_trace_runtime_choice,
        list_runtime_sources=_list_runtime_sources,
        stdin_isatty=lambda: sys.stdin.isatty(),
        ensure_rich=_ensure_rich,
        table_cls=lambda *args, **kwargs: Table(*args, **kwargs),
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        runtime_source_kind_label=_runtime_source_kind_label,
        console=console,
    )


def _resolve_direct_cli_launch_default(cli_name, cfg, default_provider, default_models):
    from mms_command_tools import resolve_direct_cli_launch_default

    return resolve_direct_cli_launch_default(
        cli_name,
        cfg,
        default_provider,
        default_models,
        provider_candidates=_provider_candidates,
        provider_effective_models=_provider_effective_models,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
    )


def _resolve_visible_clis(cfg, default_provider, default_models):
    from mms_command_tools import resolve_visible_clis

    return resolve_visible_clis(
        cfg,
        default_provider,
        default_models,
        cli_names=CLI_NAMES,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        cli_model_family_hints=CLI_MODEL_FAMILY_HINTS,
        accounts_for_cli=_accounts_for_cli,
        check_cli_installed=check_cli_installed,
        resolve_provider_for_cli=_resolve_provider_for_cli,
    )


def _clean_model_info(model_info):
    from mms_command_tools import clean_model_info

    return clean_model_info(model_info)


def select_model_interactive(models_list):
    from mms_command_tools import select_model_interactive as select_model_interactive_helper

    return select_model_interactive_helper(
        models_list,
        int_prompt_cls=IntPrompt,
        console=console,
        exit_func=sys.exit,
    )

# ── Confirmation ────────────────────────────────────────

def _mask_identity_value(value, *, keep=4):
    from mms_confirm_preview import mask_identity_value

    return mask_identity_value(value, keep=keep)


def _mask_email_value(value):
    from mms_confirm_preview import mask_email_value

    return mask_email_value(value)


def _confirm_context_lines(cli, runtime):
    from mms_confirm_preview import confirm_context_lines

    return confirm_context_lines(
        cli,
        runtime,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        runtime_force_ipv4=_runtime_force_ipv4,
        snapshot_proxy_fingerprint=_snapshot_proxy_fingerprint,
        fake_upstream_enabled=_fake_upstream_enabled,
    )


def _build_confirm_preview_catalog(cli, runtime, *, has_caveman=False, has_nsr=False, has_ecc=False, has_omc=False):
    from mms_confirm_preview import build_confirm_preview_catalog

    return build_confirm_preview_catalog(
        cli,
        runtime,
        localize=_L,
        resolve_real_user_home=resolve_real_user_home,
        safe_getcwd=_safe_getcwd,
        has_caveman=has_caveman,
        has_nsr=has_nsr,
        has_ecc=has_ecc,
        has_omc=has_omc,
    )


def confirm_launch(cli, model_info, once=False, runtime=None):
    _ensure_rich()
    from mms_confirm_preview import confirm_launch as confirm_launch_panel

    return confirm_launch_panel(
        cli,
        model_info,
        once=once,
        runtime=runtime,
        console=console,
        panel_cls=Panel,
        prompt_cls=Prompt,
        runtime_source_kind_label=_runtime_source_kind_label,
        normalize_opencode_entrypoint=_normalize_opencode_entrypoint,
    )


def _opencode_lite_pro_health_summary_text(repo_root=None, profile_id="agent"):
    from mms_tui_launcher_flow import opencode_lite_pro_health_summary_text

    return opencode_lite_pro_health_summary_text(
        repo_root,
        profile_id,
        normalize_opencode_profile_id=_normalize_opencode_profile_id,
        agent_profile_id=_OPENCODE_AGENT_PROFILE_ID,
        load_opencode_route_health_latest=_load_opencode_route_health_latest,
        opencode_lite_pro_specs=_opencode_lite_pro_specs,
    )


def _opencode_profile_menu_options():
    from mms_tui_launcher_flow import opencode_profile_menu_options

    return opencode_profile_menu_options(
        profile_options=_OPENCODE_PROFILE_OPTIONS,
        normalize_opencode_profile_id=_normalize_opencode_profile_id,
        agent_profile_id=_OPENCODE_AGENT_PROFILE_ID,
        health_summary_text=_opencode_lite_pro_health_summary_text,
    )


_AGY_CONNECT_PROFILE_ID = "__connect_agy_oauth__"


def _official_account_menu_options(cfg, cli_name):
    from mms_tui_launcher_flow import official_account_menu_options

    return official_account_menu_options(
        cfg,
        cli_name,
        accounts_for_cli=_accounts_for_cli,
        account_label=_account_label,
        localize=_L,
        default_priority=DEFAULT_PRIORITY,
        agy_connect_profile_id=_AGY_CONNECT_PROFILE_ID,
    )


def _select_opencode_profile(use_tui=False):
    from mms_tui_launcher_flow import select_opencode_profile

    return select_opencode_profile(
        use_tui=use_tui,
        profile_menu_options=_opencode_profile_menu_options,
        ensure_rich=_ensure_rich,
        table_cls=lambda: Table,
        int_prompt_cls=lambda: IntPrompt,
        console=console,
    )


def _opencode_default_profile_from_config(cfg):
    from mms_command_tools import opencode_default_profile_from_config

    return opencode_default_profile_from_config(
        cfg,
        opencode_profile_selection=_opencode_profile_selection,
        default_profile="pro",
    )


def _opencode_route_transport_candidates(provider, model_name):
    return _opencode_route_transport_candidates_impl(
        provider,
        model_name,
        infer_model_family=_infer_model_family,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        provider_label=_provider_label,
    )


def _opencode_route_health_allows_route(row, *, now=None):
    return _opencode_route_health_allows_route_impl(row, now=now, is_fresh=_opencode_route_health_is_fresh)


def _opencode_resolver_deps():
    from mms_command_tools import build_opencode_resolver_deps

    return build_opencode_resolver_deps(
        resolver_deps_cls=_OpenCodeResolverDeps,
        provider_candidates=_provider_candidates,
        provider_effective_models=_provider_effective_models,
        provider_supports_cli_name=_provider_supports_cli_name,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        provider_label=_provider_label,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        infer_model_family=_infer_model_family,
        normalize_role=_normalize_role,
        runtime_priority_for_model=_runtime_priority_for_model,
        runtime_with_priority=_runtime_with_priority,
        mms_model_visible=_mms_model_visible,
        load_route_health_latest=_load_opencode_route_health_latest,
        route_health_for_route=_opencode_route_health_for_route,
        route_health_allows_route=_opencode_route_health_allows_route,
        route_health_sort_key=_opencode_route_health_sort_key,
        apply_profile=_apply_opencode_profile,
        apply_entrypoint=_apply_opencode_entrypoint,
        role_weights=ROLE_WEIGHTS,
        default_priority=DEFAULT_PRIORITY,
        default_provider_id=DEFAULT_PROVIDER_ID,
    )


def _find_opencode_model_route(
    cfg,
    default_provider,
    default_models,
    model_names,
    *,
    route_key="route",
    route_policy="",
    profile_id=_OPENCODE_AGENT_PROFILE_ID,
    provider_id="",
):
    from mms_command_tools import find_opencode_model_route

    return find_opencode_model_route(
        cfg,
        default_provider,
        default_models,
        model_names,
        opencode_resolver_deps=_opencode_resolver_deps,
        find_opencode_model_route_impl=_find_opencode_model_route_impl,
        route_key=route_key,
        route_policy=route_policy,
        profile_id=profile_id,
        provider_id=provider_id,
    )


def _resolve_opencode_profile_runtime(cfg, default_provider, default_models, profile_id):
    return _resolve_opencode_profile_runtime_impl(
        cfg,
        default_provider,
        default_models,
        profile_id,
        deps=_opencode_resolver_deps(),
    )


def _select_and_apply_opencode_profile(runtime, *, use_tui=False):
    from mms_opencode_profiles import select_and_apply_opencode_profile

    return select_and_apply_opencode_profile(
        runtime,
        use_tui=use_tui,
        select_opencode_profile=_select_opencode_profile,
        apply_opencode_profile=_apply_opencode_profile,
    )


def save_preset_interactive(cfg, cli, model_info):
    from mms_command_tools import save_preset_interactive as save_preset_interactive_helper

    return save_preset_interactive_helper(
        cfg,
        cli,
        model_info,
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        normalize_preset_entry=_normalize_preset_entry,
        save_config=save_config,
        console=console,
    )


def _uses_native_account_entry(runtime, cli):
    from mms_command_tools import uses_native_account_entry

    return uses_native_account_entry(runtime, cli, oauth_capable_clis=OAUTH_CAPABLE_CLIS)


def _uses_broker_entry(runtime, cli):
    from mms_command_tools import uses_broker_entry

    return uses_broker_entry(runtime, cli)


def _uses_managed_entry(runtime, cli):
    from mms_command_tools import uses_managed_entry

    return uses_managed_entry(runtime, cli, oauth_capable_clis=OAUTH_CAPABLE_CLIS)


def _resolve_interactive_launch_model(cli, runtime, cli_models, models_cache, role, recommend):
    from mms_command_tools import resolve_interactive_launch_model

    return resolve_interactive_launch_model(
        cli,
        runtime,
        cli_models,
        models_cache,
        role,
        recommend,
        uses_native_account_entry=_uses_native_account_entry,
        uses_broker_entry=_uses_broker_entry,
        ensure_models_cache_available=_ensure_models_cache_available,
        display_models=display_models,
        select_model_interactive=select_model_interactive,
        console=console,
    )


def _preset_model_info(preset):
    from mms_command_tools import preset_model_info

    return preset_model_info(preset)


def _emit_preset_error(message, *, stderr_only=False):
    from mms_command_tools import emit_preset_error

    return emit_preset_error(message, stderr_only=stderr_only, console=console)


def _preset_env_file_path(preset_name):
    from mms_command_tools import preset_env_file_path

    return preset_env_file_path(preset_name, env_dir=ENV_DIR)


def _resolve_named_preset(cfg, preset_name, *, stderr_only=False):
    from mms_command_tools import resolve_named_preset

    return resolve_named_preset(
        cfg,
        preset_name,
        normalize_preset_entry=_normalize_preset_entry,
        emit_preset_error=_emit_preset_error,
        stderr_only=stderr_only,
    )


def _infer_preset_auth_mode(preset):
    from mms_command_tools import infer_preset_auth_mode

    return infer_preset_auth_mode(preset)


def _available_broker_profiles_for_cli(cfg, cli_name):
    from mms_command_tools import available_broker_profiles_for_cli

    return available_broker_profiles_for_cli(cfg, cli_name)


def _broker_enabled_by_cli(cfg, cli_names):
    from mms_command_tools import broker_enabled_by_cli

    return broker_enabled_by_cli(
        cfg,
        cli_names,
        available_broker_profiles_for_cli=_available_broker_profiles_for_cli,
    )


def _select_broker_profile_interactive(cfg, cli_name):
    from mms_command_tools import select_broker_profile_interactive

    return select_broker_profile_interactive(
        cfg,
        cli_name,
        available_broker_profiles_for_cli=_available_broker_profiles_for_cli,
        ensure_rich=_ensure_rich,
        table_cls=lambda *args, **kwargs: Table(*args, **kwargs),
        prompt_ask=lambda *args, **kwargs: Prompt.ask(*args, **kwargs),
        console=console,
    )


def _launch_broker_experiment_interactive(cfg, cli_name):
    from mms_command_tools import launch_broker_experiment_interactive

    return launch_broker_experiment_interactive(
        cfg,
        cli_name,
        select_broker_profile_interactive=_select_broker_profile_interactive,
        run_broker_profile_interactive=run_broker_profile_interactive,
        console=console,
    )


# ── CLI Selection (fallback) ───────────────────────────

def check_cli_installed(cli_name):
    from mms_command_tools import check_cli_installed as check_cli_installed_helper
    from mms_runtime import resolve_cli_binary

    return check_cli_installed_helper(cli_name, resolve_cli_binary=resolve_cli_binary)


def select_cli(cli_names=None):
    from mms_command_tools import select_cli as select_cli_helper
    from mms_installer import check_and_offer_install

    cli_names = cli_names or CLI_NAMES
    return select_cli_helper(
        cli_names,
        check_cli_installed=check_cli_installed,
        check_and_offer_install=check_and_offer_install,
        table_cls=Table,
        int_prompt_cls=IntPrompt,
        console=console,
        exit_func=sys.exit,
    )


# ── TUI helpers ────────────────────────────────────────

def _use_tui():
    """判断是否可以使用 curses TUI"""
    from mms_command_tools import use_tui

    return use_tui(sys.stdin, os.get_terminal_size)


_CLI_DEFAULT_FAMILY_FIRST = {
    "claude": "Claude",
    "codex": "GPT",
}

_FAMILY_COLD_MAX_USE_COUNT = 3
_FAMILY_COLD_IDLE_DAYS = 21


def _sort_family_entries_for_tui(families, preferred_family="", now=None):
    from mms_command_tools import sort_family_entries_for_tui

    return sort_family_entries_for_tui(families, preferred_family=preferred_family, now=now)


def _family_is_cold_for_tui(family_name, total_use, last_used_at="", *, preferred_family=""):
    from mms_command_tools import family_is_cold_for_tui

    return family_is_cold_for_tui(
        family_name,
        total_use,
        last_used_at,
        preferred_family=preferred_family,
        known_model_family_names=KNOWN_MODEL_FAMILY_NAMES,
        cold_max_use_count=_FAMILY_COLD_MAX_USE_COUNT,
        cold_idle_days=_FAMILY_COLD_IDLE_DAYS,
    )


def _build_provider_options_map(cfg, cli_name, default_provider, default_models, model_names):
    from mms_command_tools import build_provider_options_map

    return build_provider_options_map(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_names,
        infer_model_family=_infer_model_family,
        provider_candidates=_provider_candidates,
        provider_has_configured_base_url=_provider_has_configured_base_url,
        provider_effective_models=_provider_effective_models,
        provider_supports_model_for_cli=_provider_supports_model_for_cli,
        runtime_with_priority=_runtime_with_priority,
        provider_label=_provider_label,
        account_options_for_model=_account_options_for_model,
        default_provider_id=DEFAULT_PROVIDER_ID,
    )


def _make_provider_options_loader(cfg, cli_name, default_provider, default_models):
    from mms_command_tools import make_provider_options_loader

    return make_provider_options_loader(
        cfg,
        cli_name,
        default_provider,
        default_models,
        build_provider_options_map=_build_provider_options_map,
    )


def _apply_runtime_priority_changes(cfg, pri_changes):
    from mms_command_tools import apply_runtime_priority_changes

    return apply_runtime_priority_changes(
        cfg,
        pri_changes,
        canonical_model_family=_canonical_model_family,
        normalize_family_priority_overrides=_normalize_family_priority_overrides,
        normalize_priority=_normalize_priority,
    )


def _handle_tui_launcher_selection(cfg, provider, once, cli_names, account_id=None, provider_id=None):
    """TUI 交互：品类 → 子模型 → 确认。返回 True 表示已处理，False 表示 fallback"""
    from mms_tui_launcher_entry import handle_tui_launcher_selection

    return handle_tui_launcher_selection(
        sys.modules[__name__],
        cfg,
        provider,
        once,
        cli_names,
        account_id=account_id,
        provider_id=provider_id,
    )


# ── Export command ──────────────────────────────────────

def handle_export(cli_name, provider, apply=False):
    """输出指定 CLI 的 export 命令，或写入独立 env 文件。"""
    from mms_command_tools import handle_export as handle_export_impl
    from mms_launchers import get_export_env

    return handle_export_impl(
        cli_name,
        provider,
        apply=apply,
        cli_names=CLI_NAMES,
        get_export_env=get_export_env,
        env_dir=ENV_DIR,
        env_file_path=_env_file_path,
        display_title=display_title,
        export_command_hint=export_command_hint,
        console=console,
    )


# ── Preset env/activate ───────────────────────────────


def _resolve_preset_export_runtime(cfg, preset, provider_override=None, *, stderr_only=False):
    """解析 preset 的 export 环境变量。只支持 provider runtime (api_key 模式)。

    返回 (cli, exports_dict, runtime) 或 None（如果不可导出）。
    """
    from mms_command_tools import resolve_preset_export_runtime
    from mms_launchers import get_export_env, validate_provider_for_cli

    return resolve_preset_export_runtime(
        cfg,
        preset,
        provider_override=provider_override,
        stderr_only=stderr_only,
        infer_preset_auth_mode=_infer_preset_auth_mode,
        emit_preset_error=_emit_preset_error,
        ensure_provider_credentials=ensure_provider_credentials,
        validate_provider_for_cli=validate_provider_for_cli,
        get_export_env=get_export_env,
        preset_model_info=_preset_model_info,
    )


def handle_env_command(cfg, argv):
    from mms_command_tools import handle_env_command as handle_env_command_impl

    return handle_env_command_impl(
        cfg,
        argv,
        command_name=current_command(),
        resolve_named_preset=_resolve_named_preset,
        resolve_preset_export_runtime=_resolve_preset_export_runtime,
        env_dir=ENV_DIR,
        preset_env_file_path=_preset_env_file_path,
        display_title=display_title,
        console=console,
    )


def handle_activate_command(cfg, argv):
    from mms_command_tools import handle_activate_command as handle_activate_command_impl

    return handle_activate_command_impl(
        cfg,
        argv,
        command_name=current_command(),
        resolve_named_preset=_resolve_named_preset,
        resolve_preset_export_runtime=_resolve_preset_export_runtime,
    )


# ── Config command ─────────────────────────────────────

def handle_config(cfg, args_rest):
    """处理 config 子命令"""
    from mms_command_tools import handle_config as handle_config_impl

    def _run_config_web(*args, **kwargs):
        from mms_config_web import run_config_web

        return run_config_web(*args, **kwargs)

    return handle_config_impl(
        cfg,
        args_rest,
        preferences_doc_path=PREFERENCES_DOC_PATH,
        preference_paths=PREFERENCES_PATHS,
        display_config=_display_config,
        display_config_help=_display_config_help,
        handle_config_migrate=_handle_config_migrate,
        handle_config_file=_handle_config_file,
        handle_config_validate=_handle_config_validate,
        display_preferences_help=_display_preferences_help,
        display_preferences_path=_display_preferences_path,
        display_preferences_example=_display_preferences_example,
        run_config_web=_run_config_web,
        command_name=current_command(),
        config_write_target_path=_config_write_target_path,
        display_human_gate_help=_display_human_gate_help,
        handle_config_get=_handle_config_get,
        handle_config_set=_handle_config_set,
        handle_config_unset=_handle_config_unset,
        run_connect_wizard=run_connect_wizard,
        handle_openrouter_extension_config=_handle_openrouter_extension_config,
        display_adapter_registry=_display_adapter_registry,
        display_providers=_display_providers,
        handle_provider_default_config=_handle_provider_default_config,
        handle_provider_add_config=_handle_provider_add_config,
        handle_provider_edit_config=_handle_provider_edit_config,
        handle_provider_rename_config=_handle_provider_rename_config,
        handle_provider_remove_config=_handle_provider_remove_config,
        handle_provider_credentials_config=_handle_provider_credentials_config,
        display_accounts=_display_accounts,
        handle_account_default_config=_handle_account_default_config,
        handle_account_add_config=_handle_account_add_config,
        handle_account_edit_config=_handle_account_edit_config,
        handle_account_remove_config=_handle_account_remove_config,
        handle_account_rename_config=_handle_account_rename_config,
        handle_account_status_config=_handle_account_status_config,
        handle_account_login_config=_handle_account_login_config,
        display_usage_stats=_display_usage_stats,
        resolve_provider_context=resolve_provider_context,
        setup_provider_credentials=setup_provider_credentials,
        handle_api_config=_handle_api_config,
        console=console,
    )


def _handle_api_config(key_path, args_rest):
    from mms_command_tools import handle_api_config

    return handle_api_config(
        key_path,
        args_rest,
        load_api_credentials=load_api_credentials,
        save_api_credentials=save_api_credentials,
        credentials_path=CREDENTIALS_PATH,
        mask_key=_mask_key,
        console=console,
    )


def _validate_user_role(raw_value):
    normalized = normalize_user_role(raw_value)
    if str(raw_value).strip() not in {"dev", "ops", "all", "recommended", MODE_ALL, MODE_RECOMMENDED}:
        console.print(
            f"[red]不支持的模型模式: {raw_value}[/red]\n[dim]可用值: {MODE_ALL} / {MODE_RECOMMENDED}[/dim]"
        )
        sys.exit(1)
    return normalized


def _handle_provider_default_config(cfg, args_rest):
    from mms_command_tools import handle_provider_default_config

    return handle_provider_default_config(
        cfg,
        args_rest,
        default_provider_id=DEFAULT_PROVIDER_ID,
        provider_map=_provider_map,
        save_config=save_config,
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive,
        console=console,
    )


def _handle_provider_add_config(cfg, args_rest):
    from mms_command_tools import handle_provider_add_config

    return handle_provider_add_config(
        cfg,
        args_rest,
        quick_connect_gateway=_quick_connect_gateway,
    )


def _handle_provider_edit_config(cfg, args_rest):
    from mms_command_tools import handle_provider_edit_config

    return handle_provider_edit_config(
        cfg,
        args_rest,
        command_name=current_command(),
        provider_map=_provider_map,
        prompt_provider_metadata=_prompt_provider_metadata,
        upsert_provider=_upsert_provider,
        save_config=save_config,
        invalidate_probe_cache=_invalidate_probe_cache,
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive,
        console=console,
    )


def _handle_provider_remove_config(cfg, args_rest):
    from mms_command_tools import handle_provider_remove_config

    return handle_provider_remove_config(
        cfg,
        args_rest,
        command_name=current_command(),
        default_provider_id=DEFAULT_PROVIDER_ID,
        ensure_interactive_terminal=_ensure_interactive_terminal,
        provider_map=_provider_map,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        save_config=save_config,
        delete_provider_credentials=_delete_provider_credentials,
        invalidate_probe_cache=_invalidate_probe_cache,
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive,
        console=console,
    )


def _handle_provider_credentials_config(cfg, args_rest):
    from mms_command_tools import handle_provider_credentials_config

    return handle_provider_credentials_config(
        cfg,
        args_rest,
        default_provider_id=DEFAULT_PROVIDER_ID,
        provider_map=_provider_map,
        resolve_provider_context=resolve_provider_context,
        setup_provider_credentials=setup_provider_credentials,
        console=console,
    )


def _provider_looks_openrouter(provider):
    from mms_command_tools import provider_looks_openrouter

    return provider_looks_openrouter(provider)


def _openrouter_provider_candidates(cfg):
    from mms_command_tools import openrouter_provider_candidates

    return openrouter_provider_candidates(
        cfg,
        provider_looks_openrouter=_provider_looks_openrouter,
        resolve_provider_context=resolve_provider_context,
    )


def _parse_openrouter_extension_args(args_rest):
    from mms_command_tools import parse_openrouter_extension_args

    return parse_openrouter_extension_args(args_rest)


def _display_openrouter_extension_help():
    from mms_command_tools import display_openrouter_extension_help

    return display_openrouter_extension_help(current_command(), console=console)


def _openrouter_extension_provider(cfg, provider_id=""):
    from mms_command_tools import openrouter_extension_provider

    return openrouter_extension_provider(
        cfg,
        provider_id,
        provider_map=_provider_map,
        resolve_provider_context=resolve_provider_context,
        provider_looks_openrouter=_provider_looks_openrouter,
        openrouter_provider_candidates=_openrouter_provider_candidates,
    )


def _display_openrouter_extension_summary(summary, *, provider_label="", limit=12, show_models=False):
    from mms_command_tools import display_openrouter_extension_summary

    _ensure_rich()
    return display_openrouter_extension_summary(
        summary,
        provider_label=provider_label,
        limit=limit,
        show_models=show_models,
        table_cls=Table,
        console=console,
    )


def _handle_openrouter_extension_config(cfg, args_rest):
    from mms_openrouter_extension import (
        openrouter_api_key_from_env,
        probe_openrouter_extension,
    )
    from mms_command_tools import handle_openrouter_extension_config

    return handle_openrouter_extension_config(
        cfg,
        args_rest,
        parse_openrouter_extension_args=_parse_openrouter_extension_args,
        display_openrouter_extension_help=_display_openrouter_extension_help,
        quick_connect_gateway=_quick_connect_gateway,
        openrouter_extension_provider=_openrouter_extension_provider,
        openrouter_api_key_from_env=openrouter_api_key_from_env,
        probe_openrouter_extension=probe_openrouter_extension,
        display_openrouter_extension_summary=_display_openrouter_extension_summary,
        console=console,
    )


def _handle_account_default_config(cfg, args_rest):
    from mms_command_tools import handle_account_default_config

    return handle_account_default_config(
        cfg,
        args_rest,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        delegated_oauth_clis=MMC_DELEGATED_OAUTH_CLIS,
        account_map=_account_map,
        save_config=save_config,
        command_name=current_command(),
        console=console,
    )


def _handle_account_add_config(cfg, args_rest):
    from mms_command_tools import handle_account_add_config

    return handle_account_add_config(
        cfg,
        args_rest,
        managed_oauth_clis=MMS_MANAGED_OAUTH_CLIS,
        delegated_oauth_clis=MMC_DELEGATED_OAUTH_CLIS,
        quick_connect_official=_quick_connect_official,
        console=console,
    )


def _handle_account_edit_config(cfg, args_rest):
    from mms_command_tools import handle_account_edit_config

    return handle_account_edit_config(
        cfg,
        args_rest,
        command_name=current_command(),
        account_map=_account_map,
        delegated_oauth_clis=MMC_DELEGATED_OAUTH_CLIS,
        prompt_account_metadata=_prompt_account_metadata,
        ensure_account_config=_ensure_account_config,
        save_config=save_config,
        console=console,
    )


def _handle_account_remove_config(cfg, args_rest):
    from mms_command_tools import handle_account_remove_config

    return handle_account_remove_config(
        cfg,
        args_rest,
        command_name=current_command(),
        ensure_interactive_terminal=_ensure_interactive_terminal,
        account_map=_account_map,
        confirm_ask=lambda *args, **kwargs: Confirm.ask(*args, **kwargs),
        ensure_account_config=_ensure_account_config,
        save_config=save_config,
        console=console,
    )


def _handle_account_status_config(cfg, args_rest):
    from mms_command_tools import handle_account_status_config

    return handle_account_status_config(
        cfg,
        args_rest,
        resolve_account_context=resolve_account_context,
        probe_account_status=_probe_account_status,
        display_accounts=_display_accounts,
        console=console,
    )


def _handle_account_login_config(cfg, args_rest):
    from mms_command_tools import handle_account_login_config

    return handle_account_login_config(
        cfg,
        args_rest,
        command_name=current_command(),
        delegated_oauth_clis=MMC_DELEGATED_OAUTH_CLIS,
        resolve_account_context=resolve_account_context,
        run_account_login=_run_account_login,
        console=console,
    )


def _usage_key(runtime_kind, cli_name, runtime_id):
    from mms_command_tools import usage_key

    return usage_key(runtime_kind, cli_name, runtime_id)


def _rename_usage_account(old_id, new_id, new_name, cli_name):
    from mms_command_tools import rename_usage_account

    return rename_usage_account(
        old_id,
        new_id,
        new_name,
        cli_name,
        usage_path=_active_usage_path(),
        update_usage_stats=_update_usage_stats,
        usage_key=_usage_key,
    )


def _rename_usage_provider(old_id, new_id, new_name):
    from mms_command_tools import rename_usage_provider

    return rename_usage_provider(
        old_id,
        new_id,
        new_name,
        usage_path=_active_usage_path(),
        update_usage_stats=_update_usage_stats,
        usage_key=_usage_key,
    )


def _target_account_home(old_home, new_id):
    from mms_command_tools import target_account_home

    return target_account_home(
        old_home,
        new_id,
        accounts_dir=ACCOUNTS_DIR,
        default_account_home=_default_account_home,
    )


def _handle_provider_rename_config(cfg, args_rest):
    from mms_command_tools import handle_provider_rename_config

    return handle_provider_rename_config(
        cfg,
        args_rest,
        command_name=current_command(),
        normalize_provider_id_input=_normalize_provider_id_input,
        provider_map=_provider_map,
        normalize_provider=_normalize_provider,
        backup_config_tree=_backup_config_tree,
        save_config=save_config,
        rename_usage_provider=_rename_usage_provider,
        invalidate_probe_cache=_invalidate_probe_cache,
        refresh_routes_export_for_hive=_refresh_routes_export_for_hive,
        console=console,
    )


def _handle_account_rename_config(cfg, args_rest):
    from mms_command_tools import handle_account_rename_config

    return handle_account_rename_config(
        cfg,
        args_rest,
        command_name=current_command(),
        normalize_account_id=_normalize_account_id,
        account_map=_account_map,
        backup_config_tree=_backup_config_tree,
        target_account_home=_target_account_home,
        path_exists=os.path.exists,
        makedirs=os.makedirs,
        move=shutil.move,
        normalize_account=_normalize_account,
        ensure_account_config=_ensure_account_config,
        save_config=save_config,
        rename_usage_account=_rename_usage_account,
        console=console,
    )


def _migrate_accounts_dirs(cfg):
    from mms_command_tools import migrate_accounts_dirs

    return migrate_accounts_dirs(
        cfg,
        target_account_home=_target_account_home,
        normalize_account=_normalize_account,
        move=shutil.move,
    )



def _handle_config_migrate():
    from mms_command_tools import handle_config_migrate

    return handle_config_migrate(
        backup_config_tree=_backup_config_tree,
        load_config=load_config,
        migrate_accounts_dirs=_migrate_accounts_dirs,
        save_config=save_config,
        config_path=CONFIG_PATH,
        active_credentials_path=_active_credentials_path,
        active_usage_path=_active_usage_path,
        console=console,
    )


def _display_providers(cfg):
    from mms_command_tools import display_providers

    return display_providers(
        cfg,
        default_provider_id=DEFAULT_PROVIDER_ID,
        default_priority=DEFAULT_PRIORITY,
        resolve_provider_context=resolve_provider_context,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        command_name=current_command(),
        table_cls=Table,
        console=console,
    )


def _display_accounts(cfg):
    from mms_command_tools import display_accounts

    return display_accounts(
        cfg,
        default_priority=DEFAULT_PRIORITY,
        probe_account_status=_probe_account_status,
        command_name=current_command(),
        table_cls=Table,
        console=console,
    )


def _display_config_help():
    from mms_command_tools import display_config_help

    return display_config_help(command_name=current_command(), console=console)


def _config_root_status():
    return mms_config_root_status(command=current_command(), config_dir=PRIMARY_CONFIG_DIR)


def _display_config_root(json_output=False):
    status = _config_root_status()
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


def _display_model_source_status(json_output=False):
    from mms_registry_cli import _print_model_source_status, model_source_status

    status = model_source_status(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config source")
    if json_output:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_model_source_status(status)


def _display_consumer_bundle_status(json_output=False, strict_exit=True):
    from mms_registry_cli import _print_consumer_bundle_status, consumer_bundle_status

    summary = consumer_bundle_status(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config bundle")
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_consumer_bundle_status(summary)
    return 0 if not strict_exit or summary.get("verified") is True else 2


def _display_registry_v2_save_plan(json_output=False):
    from mms_registry_cli import _print_registry_v2_save_plan, registry_v2_save_plan

    plan = registry_v2_save_plan(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config save-plan")
    if json_output:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_registry_v2_save_plan(plan)


def _display_preview_doctor(json_output=False, strict_exit=False):
    from mms_registry_cli import _print_preview_doctor, preview_doctor

    summary = preview_doctor(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config doctor")
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_preview_doctor(summary)
    return 0 if not strict_exit or summary.get("ready") is True else 2


def _display_preview_check(json_output=False, strict_exit=True):
    from mms_registry_cli import _print_preview_check, preview_check

    summary = preview_check(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config check")
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_preview_check(summary)
    return 0 if not strict_exit or summary.get("ready") is True else 2


def _display_config_v2_promotion_plan(
    json_output=False,
    strict_exit=False,
    *,
    preview_config_dir=None,
    stable_config_dir=None,
    command_name=None,
):
    from mms_registry_cli import _print_config_v2_promotion_plan, config_v2_promotion_plan

    summary = config_v2_promotion_plan(
        preview_config_dir=preview_config_dir or PRIMARY_CONFIG_DIR,
        stable_config_dir=stable_config_dir,
        command_name=command_name or f"{current_command()} config promote-plan",
    )
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_config_v2_promotion_plan(summary)
    return 0 if not strict_exit or summary.get("ready_for_human_review") is True else 2


def _display_config_v2_migration_plan(args_rest):
    status = mms_config_root_status(command=current_command())
    default_preview_root = (
        status.get("config_root")
        if status.get("mode") == "preview"
        else status.get("preview_root")
    ) or PRIMARY_CONFIG_DIR
    default_stable_root = status.get("stable_root") or PRIMARY_CONFIG_DIR
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} migrate config-v2",
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
    return _display_config_v2_promotion_plan(
        json_output=bool(args.json),
        strict_exit=bool(args.strict_exit),
        preview_config_dir=args.preview_config_dir,
        stable_config_dir=args.stable_config_dir,
        command_name=f"{current_command()} migrate config-v2",
    )


def _display_config_v2_release_readiness(args_rest):
    status = mms_config_root_status(command=current_command())
    default_preview_root = (
        status.get("config_root")
        if status.get("mode") == "preview"
        else status.get("preview_root")
    ) or PRIMARY_CONFIG_DIR
    default_stable_root = status.get("stable_root") or PRIMARY_CONFIG_DIR
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} config release-readiness",
        description="Read-only config v2 / 4.0 readiness audit; stops at the stable human gate.",
    )
    parser.add_argument("--preview-config-dir", "--config-dir", default=default_preview_root)
    parser.add_argument("--stable-config-dir", default=default_stable_root)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(args_rest)

    from mms_registry_cli import _print_config_v2_release_readiness, config_v2_release_readiness

    summary = config_v2_release_readiness(
        preview_config_dir=args.preview_config_dir,
        stable_config_dir=args.stable_config_dir,
        command_name=f"{current_command()} config release-readiness",
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_config_v2_release_readiness(summary)
    return 0 if not bool(args.strict_exit) or summary.get("ready_for_human_gate") is True else 2


def _display_preferences_path():
    from mms_command_tools import display_preferences_path

    return display_preferences_path(
        preference_paths=PREFERENCES_PATHS,
        preferences_doc_path=PREFERENCES_DOC_PATH,
        console=console,
    )


def _display_preferences_example():
    from mms_command_tools import display_preferences_example

    return display_preferences_example(preferences_example_toml=PREFERENCES_EXAMPLE_TOML, console=console)


def _display_human_gate_help():
    from mms_command_tools import display_human_gate_help

    return display_human_gate_help(
        command_name=current_command(),
        preferences_doc_path=PREFERENCES_DOC_PATH,
        console=console,
    )


def _display_preferences_help():
    from mms_command_tools import display_preferences_help

    return display_preferences_help(
        command_name=current_command(),
        preference_paths=PREFERENCES_PATHS,
        preferences_doc_path=PREFERENCES_DOC_PATH,
        console=console,
    )



def _display_config(cfg, prefix="", depth=0):
    """递归显示配置，遮蔽敏感值"""
    from mms_command_tools import display_config

    return display_config(
        cfg,
        prefix=prefix,
        depth=depth,
        resolve_provider_context=resolve_provider_context,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        mask_key=_mask_key,
        active_credentials_path=_active_credentials_path,
        active_usage_path=_active_usage_path,
        display_providers=_display_providers,
        display_accounts=_display_accounts,
        probe_async_refresh_after=_PROBE_ASYNC_REFRESH_AFTER,
        probe_async_min_interval=_PROBE_ASYNC_MIN_INTERVAL,
        existing_override_paths=_existing_override_paths,
        override_paths=OVERRIDE_PATHS,
        existing_preferences_paths=_existing_preferences_paths,
        preference_paths=PREFERENCES_PATHS,
        command_name=current_command(),
        console=console,
    )


def _display_usage_stats():
    from mms_command_tools import display_usage_stats

    return display_usage_stats(
        load_usage_stats=_load_usage_stats,
        usage_path=USAGE_PATH,
        table_cls=Table,
        console=console,
    )


def _display_adapter_registry():
    from mms_command_tools import display_adapter_registry

    return display_adapter_registry(
        top_source_companies=TOP_SOURCE_COMPANIES,
        default_adapter_policy=DEFAULT_ADAPTER_POLICY,
        command_name=current_command(),
        table_cls=Table,
        console=console,
    )


def _mask_key(val):
    """遮蔽 API key，只显示前 4 和后 4 位"""
    from mms_command_tools import mask_key

    return mask_key(val)


def _set_nested(d, parts, val):
    """设置嵌套 dict 的值"""
    from mms_command_tools import set_nested

    return set_nested(d, parts, val)


def _get_nested(d, parts):
    from mms_command_tools import get_nested

    return get_nested(d, parts)


def _unset_nested(d, parts):
    from mms_command_tools import unset_nested

    return unset_nested(d, parts)


def _coerce_config_value(key_path, raw_value):
    from mms_command_tools import coerce_config_value

    return coerce_config_value(
        key_path,
        raw_value,
        validate_user_role=_validate_user_role,
        normalize_language=normalize_language,
        normalize_positive_seconds=_normalize_positive_seconds,
    )


def _validate_config(cfg):
    from mms_command_tools import validate_config

    return validate_config(
        cfg,
        default_provider_protocols=DEFAULT_PROVIDER_PROTOCOLS,
        cli_names=CLI_NAMES,
        legacy_provider_cli_aliases=LEGACY_PROVIDER_CLI_ALIASES,
        default_priority=DEFAULT_PRIORITY,
        oauth_capable_clis=OAUTH_CAPABLE_CLIS,
        mode_all=MODE_ALL,
        mode_recommended=MODE_RECOMMENDED,
        canonical_model_family=_canonical_model_family,
        normalize_priority=_normalize_priority,
        normalize_claude_1m_mode=_normalize_claude_1m_mode,
        normalize_user_role=normalize_user_role,
    )


def _handle_config_get(cfg, args_rest):
    from mms_command_tools import handle_config_get

    return handle_config_get(cfg, args_rest, command_name=current_command(), console=console)


def _handle_config_set(cfg, args_rest):
    from mms_command_tools import handle_config_set

    return handle_config_set(
        cfg,
        args_rest,
        command_name=current_command(),
        coerce_config_value=_coerce_config_value,
        normalize_config_sections=_normalize_config_sections,
        save_config=save_config,
        console=console,
    )


def _handle_config_unset(cfg, args_rest):
    from mms_command_tools import handle_config_unset

    return handle_config_unset(
        cfg,
        args_rest,
        command_name=current_command(),
        normalize_config_sections=_normalize_config_sections,
        save_config=save_config,
        console=console,
    )


def _handle_config_file():
    from mms_command_tools import handle_config_file

    return handle_config_file(config_path=CONFIG_PATH, console=console)


def _handle_config_validate(cfg):
    from mms_command_tools import handle_config_validate

    return handle_config_validate(cfg, validate_config=_validate_config, console=console)


# ── Main ────────────────────────────────────────────────

def _bundle_runtime_leaf_model(route_model, leaf):
    value = str((leaf or {}).get("model_id") or "").strip()
    return value or str(route_model or "").strip()


def _bundle_runtime_protocols(leaf):
    protocols = []
    if str((leaf or {}).get("anthropic_base_url") or "").strip():
        protocols.append("anthropic_messages")
    if str((leaf or {}).get("openai_base_url") or "").strip():
        protocols.append("openai_chat_completions")
    return protocols


def _bundle_runtime_supported_clis(protocols):
    supported = []
    if "anthropic_messages" in protocols:
        supported.append("claude")
    if "openai_chat_completions" in protocols:
        supported.extend(["claude", "codex", "opencode"])
    return _normalize_supported_clis(supported, protocols=protocols)


def _bundle_runtime_default_provider_id(profile_payload, providers):
    profile_payload = profile_payload if isinstance(profile_payload, dict) else {}
    provider_cfg = profile_payload.get("provider") if isinstance(profile_payload.get("provider"), dict) else {}
    explicit_default = str(provider_cfg.get("default") or profile_payload.get("default_provider") or "").strip()
    if explicit_default:
        for provider in providers or []:
            if provider.get("id") == explicit_default or provider.get("route_provider_id") == explicit_default:
                return provider.get("id")
    return providers[0]["id"] if providers else DEFAULT_PROVIDER_ID


def _load_preview_runtime_config_from_latest_bundle():
    if not _preview_root_mode():
        return None
    try:
        import mms_registry

        bundle = mms_registry.load_latest_approved_bundle(config_dir=PRIMARY_CONFIG_DIR, include_secret=True)
    except Exception:
        return None
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), dict) else {}
    router = payloads.get("router") if isinstance(payloads.get("router"), dict) else {}
    profile_payload = payloads.get("profile") if isinstance(payloads.get("profile"), dict) else {}
    profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), dict) else {}
    routes = router.get("routes") if isinstance(router.get("routes"), dict) else {}
    if not routes:
        return None

    providers_by_key = {}
    providers = []
    provider_ids = set()
    route_models = []
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), dict) else {}

    for route_index, (route_model, entry) in enumerate(routes.items()):
        route_model_name = str(route_model or "").strip()
        if route_model_name:
            route_models.append(route_model_name)
        if not isinstance(entry, dict):
            continue
        leaves = [("primary", entry.get("primary"))]
        if isinstance(entry.get("fallbacks"), list):
            leaves.extend(("fallback", item) for item in entry.get("fallbacks") or [])
        for leaf_kind, leaf in leaves:
            if not isinstance(leaf, dict):
                continue
            model_name = _bundle_runtime_leaf_model(route_model_name, leaf)
            provider_id = str(leaf.get("provider_id") or "").strip()
            api_key = str(leaf.get("api_key") or leaf.get("openai_api_key") or "").strip()
            anthropic_url = str(leaf.get("anthropic_base_url") or "").strip().rstrip("/")
            openai_url = str(leaf.get("openai_base_url") or "").strip().rstrip("/")
            protocols = _bundle_runtime_protocols(leaf)
            if not provider_id or not model_name or not api_key or not protocols:
                continue
            profile = profiles.get(provider_id) if isinstance(profiles.get(provider_id), dict) else {}
            key = (provider_id, anthropic_url, openai_url, api_key)
            provider = providers_by_key.get(key)
            if provider is None:
                unique_id = provider_id
                if unique_id in provider_ids:
                    suffix = 2
                    while f"{provider_id}__bundle_{suffix}" in provider_ids:
                        suffix += 1
                    unique_id = f"{provider_id}__bundle_{suffix}"
                provider_ids.add(unique_id)
                provider = {
                    "id": unique_id,
                    "name": str(profile.get("name") or provider_id) if unique_id == provider_id else f"{provider_id} ({unique_id})",
                    "enabled": True,
                    "role": str(profile.get("role") or ("primary" if leaf_kind == "primary" else "fallback")),
                    "priority": int(profile.get("priority") or max(1, 1000 - route_index)),
                    "protocols": _normalize_model_id_list(profile.get("protocols")) or protocols,
                    "supported_clis": _normalize_supported_clis(
                        profile.get("supported_clis") or _bundle_runtime_supported_clis(protocols),
                        protocols=protocols,
                    ),
                    "models_endpoint": str(profile.get("models_endpoint") or "manual"),
                    "fallback_models": [],
                    "extra_models": [],
                    "hidden_models": _normalize_model_id_list(profile.get("hidden_models")),
                    "default_anthropic_base_url": anthropic_url,
                    "default_openai_base_url": openai_url,
                    "anthropic_base_url": anthropic_url,
                    "openai_base_url": openai_url,
                    "api_key": api_key,
                    "openai_api_key": str(leaf.get("openai_api_key") or api_key).strip(),
                    "route_provider_id": provider_id,
                    "route_source": f"mms:latest-approved:{manifest.get('bundle_revision') or ''}",
                    "_mms_bundle_runtime": True,
                }
                providers_by_key[key] = provider
                providers.append(provider)
            elif leaf_kind == "primary" and not str(profile.get("role") or "").strip():
                provider["role"] = "primary"
            if model_name not in provider["fallback_models"]:
                provider["fallback_models"].append(model_name)

    if not providers:
        return None
    default_provider_id = _bundle_runtime_default_provider_id(profile_payload, providers)
    return {
        "ui": {"language": "zh"},
        "user": {"role": MODE_ALL},
        "cache": {
            "probe_async_refresh_after_sec": _PROBE_ASYNC_REFRESH_AFTER,
            "probe_async_min_interval_sec": _PROBE_ASYNC_MIN_INTERVAL,
        },
        "provider": {"default": default_provider_id},
        "providers": providers,
        "account": {"defaults": {}},
        "accounts": [],
        "recommend": {"models": _normalize_model_id_list(route_models)[:20]},
        "presets": {},
        "_mms_config_source": "latest-approved-bundle",
        "_mms_bundle_revision": manifest.get("bundle_revision") or "",
    }


def _load_config_or_preview_bundle():
    if _preview_root_mode():
        return _load_preview_runtime_config_from_latest_bundle()
    return load_config()


def _load_command_config():
    cfg = _load_config_or_preview_bundle()
    if cfg is None:
        if _preview_root_missing_legacy_config():
            _exit_preview_legacy_config_disabled(["launch"])
        cfg = _default_config()
        save_config(cfg)
    return apply_local_overrides(cfg)


def _handle_session_ls(cli_name):
    from mms_session_index import list_indexed_sessions
    from mms_command_tools import handle_session_ls

    return handle_session_ls(
        cli_name,
        list_indexed_sessions=list_indexed_sessions,
        table_cls=Table,
        console=console,
    )


def _handle_session_info(session_id, cli_name):
    from mms_session_index import get_indexed_session
    from mms_command_tools import handle_session_info

    return handle_session_info(
        session_id,
        cli_name,
        get_indexed_session=get_indexed_session,
        table_cls=Table,
        console=console,
    )


def _session_gateway_roots(cli_name):
    from mms_command_tools import session_gateway_roots

    return session_gateway_roots(cli_name, real_home=resolve_real_user_home())


def _session_dir_size_bytes(path):
    from mms_command_tools import session_dir_size_bytes

    return session_dir_size_bytes(path)


def _format_bytes(size):
    from mms_command_tools import format_bytes

    return format_bytes(size)


def _list_stale_gateway_sessions(cli_name):
    from mms_launchers import _session_home_is_active
    from mms_command_tools import list_stale_gateway_sessions

    return list_stale_gateway_sessions(
        cli_name,
        session_gateway_roots=_session_gateway_roots,
        session_home_is_active=_session_home_is_active,
        session_dir_size_bytes=_session_dir_size_bytes,
    )


def _handle_session_prune(cli_name, *, apply=False, yes=False):
    from mms_launchers import _finalize_claude_slot
    from mms_command_tools import handle_session_prune

    return handle_session_prune(
        cli_name,
        apply=apply,
        yes=yes,
        list_stale_gateway_sessions=_list_stale_gateway_sessions,
        finalize_claude_slot=_finalize_claude_slot,
        remove_tree=shutil.rmtree,
        format_bytes=_format_bytes,
        table_cls=Table,
        console=console,
    )


def handle_session_command(argv):
    _ensure_rich()
    from mms_command_tools import handle_session_command as handle_session_command_impl

    return handle_session_command_impl(
        argv,
        command_name=current_command(),
        handle_session_ls=_handle_session_ls,
        handle_session_info=_handle_session_info,
        handle_session_prune=_handle_session_prune,
    )


def _split_cli_prefixed_resume_ref(session_ref):
    from mms_command_tools import split_cli_prefixed_resume_ref

    return split_cli_prefixed_resume_ref(session_ref)


def _codex_resume_roots():
    from mms_command_tools import codex_resume_roots

    return codex_resume_roots(os.environ, real_home=resolve_real_user_home())


def _iter_codex_index_records():
    from mms_command_tools import iter_codex_index_records

    yield from iter_codex_index_records(_codex_resume_roots())


def _resolve_codex_resume_ref(session_ref, *, allow_passthrough=False):
    from mms_command_tools import resolve_codex_resume_ref

    return resolve_codex_resume_ref(
        session_ref,
        iter_codex_index_records=_iter_codex_index_records,
        allow_passthrough=allow_passthrough,
    )


def _resolve_claude_resume_ref(session_ref, *, allow_passthrough=False):
    from mms_session_index import list_indexed_sessions
    from mms_command_tools import resolve_claude_resume_ref

    return resolve_claude_resume_ref(
        session_ref,
        list_indexed_sessions=list_indexed_sessions,
        allow_passthrough=allow_passthrough,
    )


def _resolve_resume_target(session_ref, cli_hint="auto"):
    from mms_command_tools import resolve_resume_target

    return resolve_resume_target(
        session_ref,
        cli_hint,
        split_cli_prefixed_resume_ref=_split_cli_prefixed_resume_ref,
        resolve_codex_resume_ref=_resolve_codex_resume_ref,
        resolve_claude_resume_ref=_resolve_claude_resume_ref,
        uuid_resume_cli_hint=_uuid_resume_cli_hint,
    )


def _uuid_resume_cli_hint(session_ref):
    from mms_command_tools import uuid_resume_cli_hint

    return uuid_resume_cli_hint(session_ref)


def _first_resume_model(cli_models, default_models, recommend=None):
    from mms_command_tools import first_resume_model

    return first_resume_model(cli_models, default_models, recommend)


def _session_resume_model(session_record):
    from mms_command_tools import session_resume_model

    return session_resume_model(session_record)


def _resolve_resume_runtime_and_model(
    cfg,
    cli,
    args,
    default_provider,
    default_models,
    session_record,
):
    from mms_command_tools import resolve_resume_runtime_and_model

    return resolve_resume_runtime_and_model(
        cfg,
        cli,
        args,
        default_provider,
        default_models,
        session_record,
        get_scene_usage=_get_scene_usage,
        session_resume_model=_session_resume_model,
        resolve_last_used_runtime=_resolve_last_used_runtime,
        trace_runtime_choice=_trace_runtime_choice,
        choose_runtime_source=_choose_runtime_source,
        resolve_model_name=_resolve_model_name,
        first_resume_model=_first_resume_model,
        uses_managed_entry=_uses_managed_entry,
        runtime_with_launch_preferences=_runtime_with_launch_preferences,
    )


def handle_resume_command(argv, preloaded_command_cfg=None, bootstrap_cfg=None, lang_override=None):
    from mms_command_tools import handle_resume_command as handle_resume_command_impl

    return handle_resume_command_impl(
        argv,
        preloaded_command_cfg=preloaded_command_cfg,
        bootstrap_cfg=bootstrap_cfg,
        lang_override=lang_override,
        command_name=current_command(),
        resolve_resume_target=_resolve_resume_target,
        load_config=load_config,
        setup_wizard=setup_wizard,
        resolve_ui_language=_resolve_ui_language,
        apply_local_overrides=apply_local_overrides,
        set_language=set_language,
        ensure_provider_credentials=ensure_provider_credentials,
        ensure_models_ready=ensure_models_ready,
        resolve_resume_runtime_and_model=_resolve_resume_runtime_and_model,
        launch_with_tracking=_launch_with_tracking,
        path_isdir=os.path.isdir,
        chdir=os.chdir,
        console=console,
    )


def handle_cache_command(argv):
    _ensure_rich()
    from mms_command_tools import handle_cache_command as handle_cache_command_impl

    return handle_cache_command_impl(
        argv,
        command_name=current_command(),
        load_command_config=_load_command_config,
        normalize_positive_seconds=_normalize_positive_seconds,
        ensure_provider_config=_ensure_provider_config,
        ensure_account_config=_ensure_account_config,
        normalize_user_config=_normalize_user_config,
        normalize_cache_config=_normalize_cache_config,
        save_config=save_config,
        probe_async_refresh_after=_PROBE_ASYNC_REFRESH_AFTER,
        probe_async_min_interval=_PROBE_ASYNC_MIN_INTERVAL,
        table_cls=Table,
        console=console,
    )


def handle_guard_command(argv, bootstrap_cfg=None):
    _ensure_rich()
    from mms_command_tools import handle_guard_command as handle_guard_command_impl

    return handle_guard_command_impl(
        argv,
        command_name=current_command(),
        bootstrap_cfg=bootstrap_cfg,
        load_config=load_config,
        default_config=_default_config,
        config_write_target_path=_config_write_target_path,
        build_config_guard_snapshot=_build_config_guard_snapshot,
        config_snapshot_path=_config_snapshot_path,
        load_json_snapshot=_load_json_snapshot,
        snapshot_diff_lines=_snapshot_diff_lines,
        iso_now=_iso_now,
        snapshot_digest=_snapshot_digest,
        write_json_snapshot=_write_json_snapshot,
        table_cls=Table,
        console=console,
    )


def _confirm_guard_accept_from_tui(cfg):
    from mms_command_tools import confirm_guard_accept_from_tui

    return confirm_guard_accept_from_tui(
        cfg,
        config_write_target_path=_config_write_target_path,
        build_config_guard_snapshot=_build_config_guard_snapshot,
        config_snapshot_path=_config_snapshot_path,
        load_json_snapshot=_load_json_snapshot,
        snapshot_diff_lines=_snapshot_diff_lines,
        confirm_startup_snapshot_drift=_confirm_startup_snapshot_drift,
        console=console,
    )


def handle_fake_upstream_command(argv):
    _ensure_rich()
    from mms_command_tools import handle_fake_upstream_command as handle_fake_upstream_command_impl

    return handle_fake_upstream_command_impl(
        argv,
        command_name=current_command(),
        set_enabled=_set_fake_upstream_enabled,
        status_payload=_fake_upstream_status_payload,
        tail_log=_fake_upstream_tail_log,
        table_cls=Table,
        console=console,
    )


def handle_logs_command(argv):
    _ensure_rich()
    from mms_command_tools import handle_logs_command as handle_logs_command_impl

    return handle_logs_command_impl(
        argv,
        command_name=current_command(),
        fake_upstream_status_payload=_fake_upstream_status_payload,
        config_root=_config_guard_root_dir(_config_write_target_path()),
        table_cls=Table,
        console=console,
    )


def handle_doctor_command(argv):
    from mms_command_tools import handle_doctor_command as handle_doctor_command_impl

    return handle_doctor_command_impl(
        argv,
        script_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"),
        command_name=current_command(),
        console=console,
    )


def handle_exposure_command(argv):
    _ensure_rich()
    from mms_command_tools import handle_exposure_command as handle_exposure_command_impl
    from mms_launchers import inspect_runtime_exposure

    return handle_exposure_command_impl(
        argv,
        command_name=current_command(),
        cli_names=CLI_NAMES,
        load_command_config=_load_command_config,
        ensure_provider_credentials=ensure_provider_credentials,
        ensure_models_ready=ensure_models_ready,
        choose_runtime_source=_choose_runtime_source,
        inspect_runtime_exposure=inspect_runtime_exposure,
        table_cls=Table,
        console=console,
    )


def handle_test_command(argv, subcommand_name="test"):
    from mms_command_tools import handle_test_command as handle_test_command_impl

    return handle_test_command_impl(
        argv,
        subcommand_name=subcommand_name,
        script_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"),
        command_name=current_command(),
        console=console,
    )


def handle_opencode_smoke_command(argv):
    from mms_command_tools import handle_opencode_smoke_command as handle_opencode_smoke_command_impl

    return handle_opencode_smoke_command_impl(
        argv,
        script_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"),
        command_name=current_command(),
        console=console,
    )


def _is_help_request(argv):
    from mms_command_tools import is_help_request

    return is_help_request(argv)


def _is_setup_web_request(argv):
    from mms_command_tools import is_setup_web_request

    return is_setup_web_request(argv)


def _is_config_help_request(args_rest):
    from mms_command_tools import is_config_help_request

    return is_config_help_request(args_rest)


_PREVIEW_LEGACY_CONFIG_MUTATING_COMMANDS = {
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


def _preview_root_mode():
    try:
        return mms_config_root_status(command=current_command()).get("mode") == "preview"
    except Exception:
        return False


def _preview_root_missing_legacy_config():
    return _preview_root_mode() and not os.path.exists(CONFIG_PATH)


def _config_subcommand_mutates_legacy_config(args_rest):
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    if not key_path or key_path in {"-h", "--help", "help"}:
        return False
    if key_path in {"web", "webui", "setup.web", "setup-web"}:
        return False
    if key_path in _PREVIEW_LEGACY_CONFIG_MUTATING_COMMANDS:
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


def _exit_preview_legacy_config_disabled(args_rest=None):
    status = mms_config_root_status(command=current_command())
    root = status.get("config_root") or CONFIG_DIR
    console.print("[red]Preview root uses v2 DB truth; legacy config.toml writes are disabled.[/red]")
    console.print(f"[dim]config_root={root}[/dim]")
    console.print(f"[cyan]下一步:[/cyan] {current_command()} config doctor --json")
    console.print("[dim]准备预览 root: mmf preview prepare --from ~/.config/mms --json[/dim]")
    console.print(
        f"[dim]已审核 plan 后写入预览 DB: {current_command()} config apply-plan "
        "--plan-json <plan.json> --apply --confirm-preview-apply --json[/dim]"
    )
    raise SystemExit(2)


def _guard_preview_legacy_config_mutation(args_rest):
    if _preview_root_mode() and _config_subcommand_mutates_legacy_config(args_rest):
        _exit_preview_legacy_config_disabled(args_rest)


def _is_config_root_status_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"root", "root.status", "status.root"}


def _is_config_model_source_status_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"source", "sources", "model-source", "model-sources"}


def _is_config_consumer_bundle_status_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"bundle", "consumer-bundle", "manifest"}


def _is_config_registry_v2_save_plan_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"save-plan", "save.plan", "v2-save-plan", "registry-save-plan"}


def _is_config_preview_check_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"check", "preview-check", "preview.check", "v2-check"}


def _is_config_v2_promotion_plan_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"promote-plan", "promotion-plan", "promote.check", "promote"}


def _is_config_v2_release_readiness_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"release-readiness", "readiness", "v2-readiness", "4.0-readiness", "release.check"}


def _is_config_v2_migration_plan_request(argv):
    if len(argv) < 2 or argv[0] != "migrate":
        return False
    return str(argv[1] or "").strip() in {"config-v2", "config.v2", "v2", "config-v2-plan"}


def _is_config_registry_v2_apply_plan_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"apply-plan", "apply.plan", "preview-apply", "apply-preview", "registry-apply-plan"}


def _is_config_preview_doctor_request(argv):
    if len(argv) < 2 or argv[0] != "config":
        return False
    return str(argv[1] or "").strip() in {"doctor", "preview-doctor", "preview.doctor", "v2-doctor"}


def _is_session_prune_dry_run(argv):
    from mms_command_tools import is_session_prune_dry_run

    return is_session_prune_dry_run(argv)


def main():
    argv, lang_override = _extract_global_lang(sys.argv[1:])
    if len(argv) >= 1 and argv[0] == "registry":
        set_language(_resolve_ui_language(None, lang_override))
        from mms_registry_cli import handle_registry_command

        raise SystemExit(handle_registry_command(argv[1:], command_name=f"{current_command()} registry"))
    if _is_config_root_status_request(argv):
        _display_config_root(json_output="--json" in argv[2:])
        return
    if _is_config_model_source_status_request(argv):
        _display_model_source_status(json_output="--json" in argv[2:])
        return
    if _is_config_consumer_bundle_status_request(argv):
        code = _display_consumer_bundle_status(json_output="--json" in argv[2:], strict_exit="--no-strict-exit" not in argv[2:])
        if code:
            raise SystemExit(code)
        return
    if _is_config_registry_v2_save_plan_request(argv):
        _display_registry_v2_save_plan(json_output="--json" in argv[2:])
        return
    if _is_config_preview_check_request(argv):
        code = _display_preview_check(json_output="--json" in argv[2:], strict_exit="--no-strict-exit" not in argv[2:])
        if code:
            raise SystemExit(code)
        return
    if _is_config_v2_promotion_plan_request(argv):
        code = _display_config_v2_promotion_plan(json_output="--json" in argv[2:], strict_exit="--strict-exit" in argv[2:])
        if code:
            raise SystemExit(code)
        return
    if _is_config_v2_release_readiness_request(argv):
        code = _display_config_v2_release_readiness(argv[2:])
        if code:
            raise SystemExit(code)
        return
    if _is_config_v2_migration_plan_request(argv):
        code = _display_config_v2_migration_plan(argv[2:])
        if code:
            raise SystemExit(code)
        return
    if _is_config_registry_v2_apply_plan_request(argv):
        from mms_registry_cli import handle_registry_command

        registry_args = ["apply-plan", "--config-dir", PRIMARY_CONFIG_DIR] + list(argv[2:])
        raise SystemExit(handle_registry_command(registry_args, command_name=f"{current_command()} config"))
    if _is_config_preview_doctor_request(argv):
        code = _display_preview_doctor(json_output="--json" in argv[2:], strict_exit="--strict-exit" in argv[2:])
        if code:
            raise SystemExit(code)
        return

    help_request = _is_help_request(argv) or _is_setup_web_request(argv)
    bootstrap_cfg = _load_config_or_preview_bundle()
    set_language(_resolve_ui_language(bootstrap_cfg, lang_override))

    if len(argv) >= 1:
        command = argv[0]
        if command == "review-launch":
            from mms_review_launch import handle_review_launch_command

            raise SystemExit(handle_review_launch_command(argv[1:], command_name=current_command()))
        if command == "guard":
            handle_guard_command(argv[1:], bootstrap_cfg=bootstrap_cfg)
            return
        if command == "logs":
            handle_logs_command(argv[1:])
            return
        if command == "fake-upstream":
            handle_fake_upstream_command(argv[1:])
            return
        if command == "exposure":
            handle_exposure_command(argv[1:])
            return
        if _is_session_prune_dry_run(argv):
            handle_session_command(argv[1:])
            return
        if command in {"chat", "discuss"}:
            _ensure_rich()
            console.print(f"[red]未知目标: {command}[/red]")
            return

    if not help_request:
        _ensure_startup_snapshot_guard(
            bootstrap_cfg or _default_config(),
            enforce=not _snapshot_prompt_allowed(),
        )

    preloaded_command_cfg = None
    if not help_request and len(argv) >= 1:
        command = argv[0]
        if command not in {"guard", "logs", "fake-upstream", "exposure", "registry", "opencode-smoke"}:
            preloaded_command_cfg = _load_command_config()
            _refresh_routes_export_for_hive(
                preloaded_command_cfg,
                force=True,
                quiet=False,
                startup_safe=True,
            )

    if len(argv) >= 1:
        command = argv[0]
        if command == "config":
            cfg = bootstrap_cfg
            if cfg is None:
                cfg = _default_config()
                if _preview_root_mode():
                    _guard_preview_legacy_config_mutation(argv[1:])
                elif not _is_config_help_request(argv[1:]):
                    save_config(cfg)
            handle_config(cfg, argv[1:])
            return
        if command in {"setup", "setup-web", "web-setup"}:
            from mms_config_web import run_config_web

            setup_args = list(argv[1:])
            if setup_args and setup_args[0] in {"web", "config-web"}:
                setup_args = setup_args[1:]
            raise SystemExit(run_config_web(
                preloaded_command_cfg if preloaded_command_cfg is not None else (bootstrap_cfg or _default_config()),
                setup_args,
                command_name=current_command(),
                config_path=_config_write_target_path(),
                preferences_path=PREFERENCES_PATHS[0],
            ))
        if command == "usage":
            from mms_usage import usage_main

            usage_main(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command in {"models", "ls"}:
            handle_models_command(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command == "warm":
            handle_warm_command(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command == "session":
            handle_session_command(argv[1:])
            return
        if command == "resume":
            handle_resume_command(
                argv[1:],
                preloaded_command_cfg=preloaded_command_cfg,
                bootstrap_cfg=bootstrap_cfg,
                lang_override=lang_override,
            )
            return
        if command == "cache":
            handle_cache_command(argv[1:])
            return
        if command == "routes":
            from mms_router import routes_main

            routes_main(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command == "broker":
            raise SystemExit(handle_broker_command(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:], command_name=current_command()))
        if command == "doctor":
            raise SystemExit(handle_doctor_command(argv[1:]))
        if command in {"test", "smoke"}:
            raise SystemExit(handle_test_command(argv[1:], subcommand_name=command))
        if command == "opencode-smoke":
            raise SystemExit(handle_opencode_smoke_command(argv[1:]))
        if command == "env":
            handle_env_command(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command == "activate":
            handle_activate_command(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return

    parser = argparse.ArgumentParser(
        prog=current_command(),
        description=f"{display_title()} — AI Coding CLI 统一启动器",
        epilog=(
            "非 TUI 常用命令:\n"
            f"  {current_command()} config ...      配置 provider / account / adapter\n"
            f"  {current_command()} models [id]     查看模型列表\n"
            f"  {current_command()} warm [id]       预热模型缓存\n"
            f"  {current_command()} cache ...       查看或调整模型 cache 异步刷新窗口\n"
            f"  {current_command()} session ...     查看托管 session\n"
            f"  {current_command()} resume <id>     通过 Codex/Claude session id 恢复托管 CLI\n"
            f"  {current_command()} routes ...      查看路由配置\n"
            f"  {current_command()} registry ...    刷新/查看本地 model registry source truth\n"
            f"  {current_command()} migrate config-v2 [--json]  只读 config v2 migration / promotion human gate\n"
            f"  {current_command()} config release-readiness [--json]  只读 config v2 / 4.0 readiness audit\n"
            f"  {current_command()} broker ...      启动或查看 broker profiles\n"
            f"  {current_command()} doctor [full]   诊断 provider / model / Claude 兼容性（默认 lite）\n"
            f"  {current_command()} exposure ...    审计当前 runtime 对 CLI 暴露的 env/settings/home\n"
            f"  {current_command()} test ...        最小闭环 smoke 测试 channel URL + key + bridge\n"
            f"  {current_command()} smoke ...       等同于 test\n"
            f"  {current_command()} opencode-smoke ... 测试 OpenCode profile config；--live 才真实请求模型\n"
            f"  {current_command()} opencode --profile agent  启动默认 Agent mode\n"
            f"  {current_command()} opencode --profile omo    启动 global OMO mode\n"
            f"  {current_command()} opencode --profile raw    启动纯 OpenCode mode\n"
            f"  {current_command()} logs ...        显示常用 logs 路径与查看命令\n"
            f"  {current_command()} fake-upstream ... 开发期 fake upstream 开关与日志\n"
            f"  {current_command()} review-launch ... 非交互 multi-review reviewer launcher 握手\n"
            f"  {current_command()} env <preset>    输出预设对应的 export 环境变量\n"
            f"  {current_command()} activate <preset>  输出可 eval 的 export 语句\n"
            f"  {current_command()} usage ...       查看 usage 统计"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="CLI 名称(claude/codex/opencode/pi/agy)")
    parser.add_argument("--preset", help="使用指定预设直接启动")
    parser.add_argument("--once", nargs="?", const=True, default=False,
                        help="一次性会话模式（可附带 CLI 名称）")
    parser.add_argument("--list", action="store_true", help="列出 API 可用模型")
    parser.add_argument("--presets", action="store_true", help="列出已保存预设")
    parser.add_argument("--install", metavar="CLI", help="安装指定 CLI")
    parser.add_argument("--custom", action="store_true", help="强制手动选 CLI + 模型模式")
    parser.add_argument("--export", nargs="?", const="claude", metavar="CLI",
                        help="输出指定 CLI 的 export 环境变量命令")
    parser.add_argument("--apply", action="store_true",
                        help="配合 --export 使用，写入 ~/.config/mms/env/<cli>.sh")
    parser.add_argument("--account", help="临时使用指定官方账号档案启动")
    parser.add_argument("--provider", help="临时使用指定模型源启动")
    parser.add_argument("--profile", dest="opencode_profile", help="直接指定 OpenCode mode，例如 agent / omo / raw")
    parser.add_argument(
        "--opencode-entrypoint",
        choices=["tui", "backend", "backend-agent", "serve", "headless", "acp"],
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--backend-agent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--acp", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--lang", choices=["zh", "en"], help="临时指定 UI 语言")
    parser.add_argument("--trace", action="store_true",
                        help="启动前打印选择链路追踪信息（输出到 stderr）")

    args = parser.parse_args(argv)

    user_cfg = bootstrap_cfg
    set_language(_resolve_ui_language(user_cfg, args.lang or lang_override))

    global _trace_enabled, _trace_overrides
    if args.trace:
        _trace_enabled = True
        _trace_overrides = []

    update_notice = _update_notice()
    if update_notice:
        latest_tag = update_notice.get("latest_tag", "")
        installed_version = update_notice.get("installed_version", "")
        gap_count = update_notice.get("gap_count")
        behind_suffix = (
            f" [dim]({_L(f'落后 {gap_count} 个版本', f'{gap_count} versions behind')})[/dim]"
            if isinstance(gap_count, int) and gap_count > 0
            else ""
        )
        console.print(
            f"[yellow]{_L(f'发现新版本 {latest_tag}', f'New version available: {latest_tag}')}[/yellow] "
            f"[dim]({_L('当前', 'current')} {installed_version})[/dim]"
            f"{behind_suffix}"
        )
        console.print(f"[dim]{_L('升级命令', 'Upgrade command')}: {update_notice['upgrade_command']}[/dim]")
    _start_async_update_check()

    if args.account and args.provider:
        console.print("[red]--account 和 --provider 不能同时使用[/red]")
        sys.exit(1)
    requested_opencode_profile, requested_profile_entrypoint = _opencode_profile_selection(args.opencode_profile)
    if args.opencode_profile and not requested_opencode_profile:
        valid_profiles = ", ".join(_opencode_profile_selection_ids())
        parser.error(f"--profile 仅支持 OpenCode mode：{valid_profiles}")
    if requested_opencode_profile and args.account:
        parser.error("--profile 是 OpenCode 专用参数，不支持同时使用 --account")
    requested_opencode_entrypoints = []
    if requested_profile_entrypoint:
        requested_opencode_entrypoints.append(requested_profile_entrypoint)
    if args.opencode_entrypoint:
        requested_opencode_entrypoints.append(args.opencode_entrypoint)
    if args.backend_agent:
        requested_opencode_entrypoints.append("backend")
    if args.acp:
        requested_opencode_entrypoints.append("acp")
    normalized_entrypoints = {
        _normalize_opencode_entrypoint(item)
        for item in requested_opencode_entrypoints
        if _normalize_opencode_entrypoint(item)
    }
    if len(normalized_entrypoints) > 1:
        parser.error("OpenCode entrypoint 只能选择一个：tui / backend / acp")
    requested_opencode_entrypoint = next(iter(normalized_entrypoints), "")
    if requested_opencode_entrypoints and not requested_opencode_entrypoint:
        parser.error("--opencode-entrypoint 仅支持 tui / backend / serve / headless / acp")
    if requested_opencode_entrypoint and args.account:
        parser.error("OpenCode entrypoint 参数不支持同时使用 --account")

    # --install
    if args.install:
        from mms_installer import install_cli
        install_cli(args.install)
        return

    # Load or create config
    if user_cfg is None:
        if _preview_root_missing_legacy_config():
            _exit_preview_legacy_config_disabled(["launch"])
        user_cfg = setup_wizard(_resolve_ui_language(None, args.lang or lang_override))

    cfg = apply_local_overrides(user_cfg)
    set_language(_resolve_ui_language(cfg, args.lang or lang_override))
    _refresh_routes_export_for_hive(cfg, force=True, quiet=False, startup_safe=True)

    default_provider = ensure_provider_credentials(cfg)
    _trace_record("config default", provider=default_provider.get("id") if isinstance(default_provider, dict) else None)
    role = normalize_user_role(cfg.get("user", {}).get("role", MODE_ALL))
    recommend = cfg.get("recommend", {}).get("models", [])

    # --presets
    if args.presets:
        _ensure_rich()
        from mms_command_tools import handle_presets_command

        handle_presets_command(
            cfg,
            preset_has_visible_model_options=_preset_has_visible_model_options,
            infer_preset_auth_mode=_infer_preset_auth_mode,
            default_provider_id=DEFAULT_PROVIDER_ID,
            table_cls=Table,
            console=console,
        )
        return

    # --export
    if args.export is not None:
        handle_export(args.export, default_provider, apply=args.apply)
        return

    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    _warm_probe_cache_async(cfg, default_provider)
    visible_clis = _resolve_visible_clis(cfg, default_provider, models_cache)
    # --list
    if args.list:
        if not _ensure_models_cache_available(models_cache):
            return
        display_models(models_cache, role, recommend)
        return

    # --preset
    if args.preset:
        p = _resolve_named_preset(cfg, args.preset)
        if p is None:
            return
        cli = p["cli"]
        model_info = _preset_model_info(p)
        _trace_record(f'preset "{args.preset}"', cli=cli, model=p.get("model"), provider=p.get("provider"), account=p.get("account"), bridge=p.get("bridge"))
        if args.account or args.provider:
            _trace_record("CLI flags", account=args.account, provider=args.provider)
        preset_account_id = p.get("account") or p.get("bridge")
        runtime, _, cli = _choose_runtime_source(
            cfg,
            cli,
            ensure_provider_credentials(cfg, p.get("provider")),
            models_cache,
            account_id=args.account or preset_account_id,
            provider_id=args.provider,
            model_info=model_info,
            allow_selected_model_accounts=True,
        )
        once = bool(args.once)
        if runtime is None:
            console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
            return
        if cli == "opencode":
            runtime = _apply_opencode_entrypoint(runtime, requested_opencode_entrypoint)
        _launch_with_tracking(cli, model_info, runtime, once=once)
        return

    # Determine once mode
    once = bool(args.once)
    once_target = args.once if isinstance(args.once, str) and args.once is not True else None

    # Direct target
    target = once_target or args.target
    if requested_opencode_profile or requested_opencode_entrypoint:
        if target is None:
            target = "opencode"
        elif target != "opencode":
            parser.error("--profile / OpenCode entrypoint 仅支持 target=opencode，例如：mms opencode --profile agent")

    if target:
        launch_default = {}
        if not args.account and not args.provider:
            launch_default = _resolve_direct_cli_launch_default(target, cfg, default_provider, models_cache)
        profile_to_launch = requested_opencode_profile
        entrypoint_to_launch = requested_opencode_entrypoint
        if target == "opencode" and not profile_to_launch:
            profile_to_launch, configured_entrypoint = _opencode_default_profile_from_config(cfg)
            if not entrypoint_to_launch:
                entrypoint_to_launch = configured_entrypoint
            if launch_default.get("profile"):
                _trace_record("launch default", profile=launch_default.get("profile"))

        if target == "opencode" and profile_to_launch:
            cli = "opencode"
            _trace_record("OpenCode profile target", profile=profile_to_launch)
            profile_provider = ensure_provider_credentials(cfg, args.provider) if args.provider else default_provider
            profile_models = models_cache
            if args.provider:
                profile_models = _probe_models(profile_provider, emit_output=False).get("models")
            model_info, runtime = _resolve_opencode_profile_runtime(
                cfg,
                profile_provider,
                profile_models,
                profile_to_launch,
            )
            if runtime is None:
                console.print(f"[red]opencode profile {profile_to_launch} 当前没有可用运行来源[/red]")
                return
            runtime = _apply_opencode_entrypoint(runtime, entrypoint_to_launch)
            _trace_runtime_choice("runtime resolve", runtime, launch_cli=cli, choice="opencode profile")
            if not check_cli_installed(cli):
                from mms_installer import check_and_offer_install
                if not check_and_offer_install(cli):
                    return
            action = confirm_launch(cli, model_info, once, runtime=runtime)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model_info)
            _launch_with_tracking(cli, _clean_model_info(model_info), runtime, once=once)
            return

        # Is it a CLI name?
        if target in visible_clis:
            cli = target
            _trace_record("CLI target", cli=cli)
            if args.account or args.provider:
                _trace_record("CLI flags", account=args.account, provider=args.provider)
            launch_default_model_info = launch_default.get("model_info") if isinstance(launch_default, dict) else None
            launch_default_provider = launch_default.get("provider") if isinstance(launch_default, dict) else None
            if launch_default_model_info:
                _trace_record(
                    "launch default",
                    provider=launch_default_provider,
                    model=launch_default_model_info.get("model"),
                )
            runtime, cli_models, cli = _choose_runtime_source(
                cfg,
                cli,
                default_provider,
                models_cache,
                account_id=args.account,
                provider_id=args.provider or launch_default_provider,
                model_info=launch_default_model_info,
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            if not check_cli_installed(cli):
                from mms_installer import check_and_offer_install
                check_and_offer_install(cli)
            if launch_default_model_info and not _uses_managed_entry(runtime, cli):
                ok, model = True, launch_default_model_info.get("model")
            else:
                ok, model = _resolve_interactive_launch_model(
                    cli,
                    runtime,
                    cli_models,
                    models_cache,
                    role,
                    recommend,
                )
                if not ok:
                    return
                if model:
                    _trace_record("manual select", model=model)
            model_info = {} if _uses_managed_entry(runtime, cli) else model
            if cli == "opencode":
                runtime = _select_and_apply_opencode_profile(runtime, use_tui=False)
                if runtime is None:
                    return
                runtime = _apply_opencode_entrypoint(runtime, requested_opencode_entrypoint)
            action = confirm_launch(cli, model_info, once, runtime=runtime)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model_info)
            _launch_with_tracking(cli, {} if _uses_managed_entry(runtime, cli) else {"model": model}, runtime, once=once)
            return
        if target in MMS_MANAGED_OAUTH_CLIS and _accounts_for_cli(cfg, target):
            cli = target
            _trace_record("CLI target", cli=cli)
            if args.account or args.provider:
                _trace_record("CLI flags", account=args.account, provider=args.provider)
            runtime, cli_models, cli = _choose_runtime_source(
                cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=args.provider
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            if not check_cli_installed(cli):
                from mms_installer import check_and_offer_install
                if not check_and_offer_install(cli):
                    return
            ok, model = _resolve_interactive_launch_model(
                cli,
                runtime,
                cli_models,
                models_cache,
                role,
                recommend,
            )
            if not ok:
                return
            if model:
                _trace_record("manual select", model=model)
            model_info = {} if _uses_managed_entry(runtime, cli) else model
            if cli == "opencode":
                runtime = _select_and_apply_opencode_profile(runtime, use_tui=False)
                if runtime is None:
                    return
                runtime = _apply_opencode_entrypoint(runtime, requested_opencode_entrypoint)
            action = confirm_launch(cli, model_info, once, runtime=runtime)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model_info)
            _launch_with_tracking(cli, {} if _uses_managed_entry(runtime, cli) else {"model": model}, runtime, once=once)
            return
        if target in CLI_NAMES:
            console.print(f"[yellow]{target} 当前没有匹配模型或未被 provider 支持，所以已隐藏。[/yellow]")
            console.print(f"[dim]当前可用 CLI: {', '.join(visible_clis)}[/dim]")
            return

        console.print(f"[red]未知目标: {target}[/red]")
        return

    # --custom: manual CLI + model selection
    if args.custom:
        cli = select_cli(visible_clis)
        _trace_record("custom mode", cli=cli)
        if args.account or args.provider:
            _trace_record("CLI flags", account=args.account, provider=args.provider)
        aggregated = _aggregate_provider_models(cfg, cli, default_provider, models_cache)
        if not _ensure_models_cache_available(aggregated):
            return
        model, custom_provider_id = _select_custom_model(
            aggregated,
            cli,
            role=role,
            recommend=recommend,
            use_tui=False,
        )
        if model is None:
            return
        runtime, cli_models, cli = _choose_runtime_source(
            cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=custom_provider_id or args.provider,
            model_info={"model": model}
        )
        if runtime is None:
            console.print(f"[red]{cli} 当前没有可承载模型 {model} 的使用入口[/red]")
            return
        _trace_record("manual select", model=model, provider=custom_provider_id)
        model_info = model
        if cli == "opencode":
            runtime = _select_and_apply_opencode_profile(runtime, use_tui=False)
            if runtime is None:
                return
            runtime = _apply_opencode_entrypoint(runtime, requested_opencode_entrypoint)
        action = confirm_launch(cli, model_info, once, runtime=runtime)
        if action == "q":
            return
        if action == "s":
            save_preset_interactive(user_cfg, cli, model_info)
        _launch_with_tracking(cli, {"model": model}, runtime, once=once)
        return

    # Default: modern TUI launcher selection, no legacy numbered scene menu.
    if _use_tui():
        handled = _handle_tui_launcher_selection(
            cfg, default_provider, once, visible_clis, account_id=args.account, provider_id=args.provider
        )
        if handled:
            return
        # fallback if curses failed

    # Fallback: direct CLI + model selection. The legacy numbered scene menu is retired.
    cli = select_cli(visible_clis)
    _trace_record("custom mode", cli=cli)
    if args.account or args.provider:
        _trace_record("CLI flags", account=args.account, provider=args.provider)
    aggregated = _aggregate_provider_models(cfg, cli, default_provider, models_cache)
    if not _ensure_models_cache_available(aggregated):
        return
    model, custom_provider_id = _select_custom_model(
        aggregated,
        cli,
        role=role,
        recommend=recommend,
        use_tui=False,
    )
    if model is None:
        return
    runtime, _, cli = _choose_runtime_source(
        cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=custom_provider_id or args.provider,
        model_info={"model": model}
    )
    if runtime is None:
        console.print(f"[red]{cli} 当前没有可承载模型 {model} 的使用入口[/red]")
        return
    _trace_record("manual select", model=model, provider=custom_provider_id)
    model_info = model
    if cli == "opencode":
        runtime = _select_and_apply_opencode_profile(runtime, use_tui=False)
        if runtime is None:
            return
        runtime = _apply_opencode_entrypoint(runtime, requested_opencode_entrypoint)
    action = confirm_launch(cli, model_info, once, runtime=runtime)
    if action == "q":
        return
    if action == "s":
        save_preset_interactive(user_cfg, cli, model_info)
    _launch_with_tracking(cli, {"model": model}, runtime, once=once)
