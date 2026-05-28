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
import inspect
import hashlib
import tempfile
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
    OPENCODE_DEFAULT_MODEL_PREFERENCES as _OPENCODE_DEFAULT_MODEL_PREFERENCES,
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
    opencode_default_model_rank as _opencode_default_model_rank_impl,
    opencode_is_mimo_direct_route as _opencode_is_mimo_direct_route_impl,
    opencode_mimo_openai_base_from_anthropic as _opencode_mimo_openai_base_from_anthropic,
    opencode_normalized_anthropic_base_url as _opencode_normalized_anthropic_base_url_impl,
    opencode_normalized_openai_base_url as _opencode_normalized_openai_base_url_impl,
    opencode_provider_matches_route_policy as _opencode_provider_matches_route_policy_impl,
    opencode_provider_protocols as _opencode_provider_protocols,
    opencode_route_candidate_score as _opencode_route_candidate_score_impl,
    opencode_route_transport as _opencode_route_transport_impl,
    opencode_route_transport_candidates as _opencode_route_transport_candidates_impl,
)
from mms_opencode_resolver import (
    OpenCodeResolverDeps as _OpenCodeResolverDeps,
    find_opencode_model_route as _find_opencode_model_route_impl,
    resolve_opencode_lite_pro_runtime as _resolve_opencode_lite_pro_runtime_impl,
    resolve_opencode_profile_runtime as _resolve_opencode_profile_runtime_impl,
)
from mms_state_io import resolve_mms_config_dir, resolve_real_user_home
from mms_state_io import resolve_current_workdir as _safe_getcwd

# Provider 调试日志（写入文件，不影响 TUI 输出）
_PROBE_DEBUG_DIR = os.path.join(
    resolve_mms_config_dir(),
    "cache",
)
_probe_debug_logger = logging.getLogger("probe_debug")
_probe_debug_logger.setLevel(logging.DEBUG)
if not _probe_debug_logger.handlers:
    os.makedirs(_PROBE_DEBUG_DIR, exist_ok=True)
    _dh = logging.FileHandler(
        os.path.join(_PROBE_DEBUG_DIR, "provider_debug.log"),
        mode="a", encoding="utf-8",
    )
    _dh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    _probe_debug_logger.addHandler(_dh)

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
nsr_mode = "enable"           # enable | disable
agent_pack = "none"           # none | ecc | omc
bypass = true                 # true | false

[launch.cli.codex]
reasoning_effort = "high"

[launch.cli.claude]
agent_pack = "ecc"

[launch.cli.agy]
caveman_mode = "enable"

[session_surfaces.disabled]
skills = []                   # e.g. ["agent-browser", "token-saver"]
mcp = []                      # e.g. ["pilot", "hive"]
hooks = []                    # hook names or paths shown on confirm screen

[assets.roots]
# Optional custom roots; env vars like MMS_WEB_ACCESS_ROOT still win.
# web_access = "~/my-skills/web-access"
# weber = "~/my-skills/weber"
# token_saver = "~/vendor/token-saver"
# toon = "~/vendor/toon"
# xmem = "~/auto-skills/shared-skills/xmem"
# caveman = "~/vendor/caveman"
# nsr = "~/vendor/non-stop-run"
# ecc = "~/.mms/agent-packs/everything-claude-code"
# omc = "~/.mms/agent-packs/oh-my-claudecode"
"""
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
    normalized = os.path.normpath(str(config_path or ""))
    for marker in _GATEWAY_SESSION_MARKERS:
        idx = normalized.find(marker)
        if idx == -1:
            continue
        base_home = normalized[:idx]
        if base_home:
            return os.path.join(base_home, ".config", "mms", "config.toml")
    return ""


def _base_user_primary_dir_from_gateway(path):
    normalized = os.path.normpath(str(path or ""))
    for marker in _GATEWAY_SESSION_MARKERS:
        idx = normalized.find(marker)
        if idx == -1:
            continue
        base_home = normalized[:idx]
        if base_home:
            return os.path.join(base_home, ".config", "mms")
    return ""


def _merge_base_user_broker_profiles(cfg, config_path):
    base_config_path = _base_user_config_path_from_gateway(config_path)
    if not base_config_path:
        return cfg, False
    if os.path.normpath(base_config_path) == os.path.normpath(config_path):
        return cfg, False
    if not os.path.exists(base_config_path):
        return cfg, False

    try:
        with open(base_config_path, "rb") as f:
            base_cfg = tomllib.loads(f.read().decode("utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return cfg, False

    if not isinstance(base_cfg, dict):
        return cfg, False

    active_profiles = cfg.get("broker_profiles")
    base_profiles = base_cfg.get("broker_profiles")
    if not isinstance(base_profiles, list) or not base_profiles:
        return cfg, False

    merged = dict(cfg)
    merged["broker_profiles"] = (
        list(active_profiles) if isinstance(active_profiles, list) else []
    ) + list(base_profiles)
    merged, _ = ensure_broker_config(merged)
    return merged, merged.get("broker_profiles") != cfg.get("broker_profiles")
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


def _parse_semver_tag(tag):
    from mms_command_tools import parse_semver_tag

    return parse_semver_tag(tag)


def _load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def _save_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def _http_status_is_success(value):
    from mms_command_tools import http_status_is_success

    return http_status_is_success(value)


def _load_version_meta():
    return _load_json_file(VERSION_META_PATH, {})


def _load_update_check_cache():
    return _load_json_file(UPDATE_CHECK_PATH, {})


def _save_update_check_cache(payload):
    _save_json_file(UPDATE_CHECK_PATH, payload)


def _normalize_semver_tags(raw_tags):
    from mms_command_tools import normalize_semver_tags

    return normalize_semver_tags(raw_tags)


def _fetch_latest_semver_tags(limit=UPDATE_CHECK_TAG_LIMIT):
    req = Request(
        f"https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page={int(limit)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mms-update-check",
        },
    )
    with urlopen(req, timeout=3) as resp:
        data = json.load(resp)

    if not isinstance(data, list):
        return ""

    semver_tags = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("name") or "").strip()
        semver_tags.append(tag)
    return _normalize_semver_tags(semver_tags)


def _fetch_latest_semver_tag():
    semver_tags = _fetch_latest_semver_tags()
    return semver_tags[0] if semver_tags else ""


def _extract_semver_text(value):
    from mms_command_tools import extract_semver_text

    return extract_semver_text(value)


def _parse_semver_text(value):
    from mms_command_tools import parse_semver_text

    return parse_semver_text(value)


def _compare_semver_text(current, latest):
    from mms_command_tools import compare_semver_text

    return compare_semver_text(current, latest)


def _detect_cli_version(command_name):
    command = str(command_name or "").strip()
    if not command:
        return {"installed": False, "label": _L("未安装", "not installed"), "version": "", "path": ""}
    path = shutil.which(command)
    if not path:
        return {"installed": False, "label": _L("未安装", "not installed"), "version": "", "path": ""}
    try:
        result = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return {
            "installed": True,
            "label": _L(f"读取失败: {exc}", f"version failed: {exc}"),
            "version": "",
            "path": path,
        }
    raw = str(result.stdout or "").strip().splitlines()
    label = raw[0].strip() if raw else (path if result.returncode == 0 else _L("读取失败", "version failed"))
    return {
        "installed": True,
        "label": label,
        "version": _extract_semver_text(label),
        "path": path,
    }


def _fetch_npm_package_latest_version(package_name):
    package = str(package_name or "").strip()
    if not package:
        return ""
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return ""
    try:
        result = subprocess.run(
            [npm_bin, "view", package, "version", "--silent"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=6,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return _extract_semver_text(str(result.stdout or "").strip())


def _installed_update_semver(version_meta):
    from mms_command_tools import installed_update_semver

    return installed_update_semver(version_meta, update_notice_sources=UPDATE_NOTICE_SOURCES)


def _semver_tag_gap(installed_version, known_tags, latest_tag=""):
    from mms_command_tools import semver_tag_gap

    return semver_tag_gap(installed_version, known_tags, latest_tag)


def _update_notice():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None

    version_meta = _load_version_meta()
    installed_version, installed_semver = _installed_update_semver(version_meta)
    if installed_semver is None:
        return None

    cache = _load_update_check_cache()
    latest_tag = str(cache.get("latest_tag") or "").strip()
    latest_semver = _parse_semver_tag(latest_tag)
    if latest_semver is None or latest_semver <= installed_semver:
        return None

    gap_count = _semver_tag_gap(installed_version, cache.get("semver_tags"), latest_tag)
    is_major_upgrade = latest_semver[0] > installed_semver[0]
    if not is_major_upgrade and (gap_count is None or gap_count < UPDATE_NOTICE_VERSION_GAP):
        return None

    now = time.time()
    last_prompted_for = str(cache.get("last_prompted_for") or "").strip()
    last_prompted_at = float(cache.get("last_prompted_at") or 0)
    if last_prompted_for == latest_tag and now - last_prompted_at < UPDATE_PROMPT_INTERVAL_SEC:
        return None

    cache["last_prompted_for"] = latest_tag
    cache["last_prompted_at"] = now
    _save_update_check_cache(cache)
    return {
        "installed_version": installed_version,
        "latest_tag": latest_tag,
        "gap_count": gap_count,
        "upgrade_command": "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash",
    }


def _major_update_notice():
    return _update_notice()


def _start_async_update_check():
    global _UPDATE_CHECK_RUNNING

    version_meta = _load_version_meta()
    _installed_version, installed_semver = _installed_update_semver(version_meta)
    if installed_semver is None:
        return

    cache = _load_update_check_cache()
    last_checked_at = float(cache.get("checked_at") or 0)
    if time.time() - last_checked_at < UPDATE_CHECK_INTERVAL_SEC:
        return

    with _UPDATE_CHECK_LOCK:
        if _UPDATE_CHECK_RUNNING:
            return
        _UPDATE_CHECK_RUNNING = True

    def _run():
        global _UPDATE_CHECK_RUNNING
        try:
            semver_tags = _fetch_latest_semver_tags()
            payload = _load_update_check_cache()
            payload["checked_at"] = time.time()
            if semver_tags:
                payload["latest_tag"] = semver_tags[0]
                payload["semver_tags"] = semver_tags
            _save_update_check_cache(payload)
        except Exception:
            pass
        finally:
            with _UPDATE_CHECK_LOCK:
                _UPDATE_CHECK_RUNNING = False

    threading.Thread(
        target=_run,
        daemon=True,
        name="mms-update-check",
    ).start()

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


CLI_NAMES = ["claude", "codex", "opencode", "agy"]
CLI_MODEL_FAMILY_HINTS = {}


def current_command():
    return PRIMARY_COMMAND


def display_title():
    return "MMS"


def _git_output(args):
    try:
        result = subprocess.run(
            ["git", "-C", os.path.dirname(os.path.abspath(__file__)), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def _release_version_info():
    version_meta = _load_version_meta()
    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_ref = str(version_meta.get("installed_ref") or "").strip()
    git_describe = _git_output(["describe", "--tags", "--always", "--dirty"])
    git_branch = _git_output(["branch", "--show-current"])
    git_commit = _git_output(["rev-parse", "--short", "HEAD"])
    release = installed_version or git_describe or git_commit or "dev"
    return {
        "release": release,
        "installed_version": installed_version,
        "installed_ref": installed_ref,
        "git_describe": git_describe,
        "git_branch": git_branch,
        "git_commit": git_commit,
        "install_channel": str(version_meta.get("install_channel") or "").strip(),
        "source": str(version_meta.get("source") or "").strip(),
    }


def _refresh_update_cache_for_about(force_update=False):
    cache = _load_update_check_cache()
    if not force_update:
        return cache
    try:
        semver_tags = _fetch_latest_semver_tags()
    except Exception as exc:
        cache["last_error"] = str(exc)
        cache["checked_at"] = time.time()
        _save_update_check_cache(cache)
        return cache
    cache["checked_at"] = time.time()
    cache["last_error"] = ""
    if semver_tags:
        cache["latest_tag"] = semver_tags[0]
        cache["semver_tags"] = semver_tags
    _save_update_check_cache(cache)
    return cache


def _cli_version_status(force_update=False):
    cache = _load_update_check_cache()
    cached_latest = cache.get("cli_latest_versions") if isinstance(cache.get("cli_latest_versions"), dict) else {}
    # Do not block About on npm/network checks unless the user explicitly refreshes.
    should_fetch_latest = bool(force_update)
    latest_versions = dict(cached_latest)
    if should_fetch_latest:
        latest_versions = {}
        for cli_name, package_name in CLI_VERSION_PACKAGES.items():
            latest_versions[cli_name] = _fetch_npm_package_latest_version(package_name)
        cache["cli_latest_versions"] = latest_versions
        cache["cli_latest_checked_at"] = time.time()
        _save_update_check_cache(cache)

    status = {}
    for cli_name in ("codex", "claude"):
        current = _detect_cli_version(cli_name)
        latest = str(latest_versions.get(cli_name) or "").strip()
        comparison = _compare_semver_text(current.get("version"), latest)
        if not current.get("installed"):
            label = _L("未安装", "not installed")
            outdated = False
        elif comparison == -1:
            label = _L(f"有新版 {latest}", f"update available {latest}")
            outdated = True
        elif comparison == 0:
            label = _L("最新", "latest")
            outdated = False
        elif latest:
            label = _L(f"高于 latest {latest}", f"newer than latest {latest}")
            outdated = False
        else:
            label = _L("未检查 latest", "latest not checked")
            outdated = False
        status[cli_name] = {
            **current,
            "latest": latest,
            "status": label,
            "outdated": outdated,
            "package": CLI_VERSION_PACKAGES.get(cli_name, ""),
        }
    return status


def _mms_update_status(version_info, cache):
    from mms_command_tools import mms_update_status

    return mms_update_status(version_info, cache, localize=_L)


def _about_status_snapshot(force_update=False):
    version_info = _release_version_info()
    cache = _refresh_update_cache_for_about(force_update=force_update)
    cli_status = _cli_version_status(force_update=force_update)
    return {
        "version_info": version_info,
        "mms": _mms_update_status(version_info, cache),
        "clis": cli_status,
        "checked_at": cache.get("checked_at"),
    }


def _short_update_status_label(status):
    from mms_command_tools import short_update_status_label

    return short_update_status_label(status, localize=_L)


def _format_cli_about_line(cli_status):
    from mms_command_tools import format_cli_about_line

    return format_cli_about_line(cli_status, localize=_L)


def _format_about_latest_value(status):
    from mms_command_tools import format_about_latest_value

    return format_about_latest_value(status, localize=_L)


def _about_check_error_summary(error_text):
    from mms_command_tools import about_check_error_summary

    return about_check_error_summary(error_text, localize=_L)


def _mms_upgrade_shell_command(*, include_clis=False):
    args = ["--latest-tag", "--lang", normalize_language(_load_version_meta().get("preferred_language", "")) or "zh"]
    if include_clis:
        args.extend(["--install-cli", "claude,codex"])
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    return f"curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- {quoted_args}"


def _cli_upgrade_shell_command(cli_name):
    cli = str(cli_name or "").strip().lower()
    package = CLI_VERSION_PACKAGES.get(cli)
    if not package:
        return ""
    return "npm install -g " + shlex.quote(f"{package}@latest")


def _print_about_version_summary(about_snapshot):
    from mms_command_tools import display_about_version_summary

    return display_about_version_summary(about_snapshot, payload_builder=_about_tui_payload, console=console)


def _run_about_upgrade(*, target="mms", include_clis=False):
    _ensure_rich()
    target = str(target or "mms").strip().lower()
    if target in {"codex", "claude"}:
        command = _cli_upgrade_shell_command(target)
        label = "Codex CLI" if target == "codex" else "Claude CLI"
    else:
        command = _mms_upgrade_shell_command(include_clis=include_clis)
        if include_clis:
            label = _L("MMS + Codex/Claude CLI", "MMS + Codex/Claude CLI")
        else:
            label = "MMS"
    if not command:
        console.print(f"[red]{_L('没有可执行的升级命令。', 'No upgrade command available.')}[/red]")
        return False
    console.print(f"[yellow]{_L(f'即将升级 {label}', f'About to upgrade {label}')}[/yellow]")
    console.print(f"[dim]{command}[/dim]")
    if not Confirm.ask(_L("确认执行升级？", "Run upgrade now?"), default=False):
        console.print(f"[yellow]{_L('已取消升级。', 'Upgrade cancelled.')}[/yellow]")
        return False
    result = subprocess.run(
        ["bash", "-lc", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        console.print(result.stdout)
    if result.returncode == 0:
        console.print(f"[green]✓ {_L('升级命令完成。重新打开终端或重新启动 mms 后生效。', 'Upgrade command completed. Restart the terminal or MMS to apply.')}[/green]")
        return True
    console.print(f"[red]{_L('升级命令失败', 'Upgrade command failed')} (exit {result.returncode})[/red]")
    return False


def config_command_hint():
    return f"{current_command()} config api.edit"


def export_command_hint(cli_name):
    return f"{current_command()} --export {cli_name} --apply"


def normalize_user_role(role):
    value = str(role or "").strip()
    if value in {"dev", "all", MODE_ALL}:
        return MODE_ALL
    if value in {"ops", "recommended", MODE_RECOMMENDED}:
        return MODE_RECOMMENDED
    return MODE_ALL


def _normalize_ui_config(cfg):
    cfg = dict(cfg)
    raw_ui = cfg.get("ui")
    current = raw_ui if isinstance(raw_ui, dict) else {}
    lang = normalize_language(current.get("language", "")) or "zh"
    new_cfg = dict(cfg)
    new_cfg["ui"] = {"language": lang}
    return new_cfg, new_cfg != cfg


def _resolve_ui_language(cfg=None, cli_override=None):
    cli_lang = normalize_language(cli_override)
    if cli_lang:
        return cli_lang
    env_lang = normalize_language(os.environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    if isinstance(cfg, dict):
        ui_lang = normalize_language((cfg.get("ui") or {}).get("language", ""))
        if ui_lang:
            return ui_lang
    locale_lang = normalize_language(os.environ.get("LC_ALL", "") or os.environ.get("LANG", ""))
    if locale_lang:
        return locale_lang
    version_lang = normalize_language(_load_version_meta().get("preferred_language", ""))
    if version_lang:
        return version_lang
    return "zh"


def _extract_global_lang(argv):
    cleaned = []
    lang = ""
    idx = 0
    while idx < len(argv):
        item = argv[idx]
        if item == "--lang" and idx + 1 < len(argv):
            candidate = normalize_language(argv[idx + 1])
            if candidate:
                lang = candidate
                idx += 2
                continue
        cleaned.append(item)
        idx += 1
    return cleaned, lang


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


def _normalize_supported_clis(value, protocols=None):
    from mms_command_tools import normalize_supported_clis

    return normalize_supported_clis(
        value,
        protocols=protocols,
        cli_names=CLI_NAMES,
        legacy_provider_cli_aliases=LEGACY_PROVIDER_CLI_ALIASES,
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
    canonical = _canonical_model_family(family_name)
    overrides = runtime.get("family_priority_overrides", {}) if isinstance(runtime, dict) else {}
    if canonical and isinstance(overrides, dict) and canonical in overrides:
        return _normalize_priority(overrides.get(canonical))
    if isinstance(runtime, dict):
        return _normalize_priority(runtime.get("priority", DEFAULT_PRIORITY))
    return DEFAULT_PRIORITY


def _runtime_priority_for_model(runtime, model_name):
    family_name, _ = _infer_model_family(model_name)
    return _runtime_priority_for_family(runtime, family_name)


def _runtime_with_priority(runtime, *, model_name="", family_name=""):
    if not isinstance(runtime, dict):
        return runtime
    canonical_family = _canonical_model_family(family_name)
    if not canonical_family and model_name:
        canonical_family, _ = _infer_model_family(model_name)
    merged = dict(runtime)
    merged["priority"] = (
        _runtime_priority_for_family(runtime, canonical_family)
        if canonical_family
        else _normalize_priority(runtime.get("priority", DEFAULT_PRIORITY))
    )
    if canonical_family:
        merged["priority_family"] = canonical_family
    return merged


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
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    for suffix in host_suffixes:
        normalized = str(suffix or "").strip().lower().lstrip(".")
        if not normalized:
            continue
        if host == normalized or host.endswith("." + normalized):
            return True
    return False


def _runtime_should_disable_ambient_env(runtime, *, target_url=""):
    runtime = runtime if isinstance(runtime, dict) else {}
    if str(runtime.get("proxy") or "").strip():
        return True
    # 只对官方 Anthropic 目标 fail-closed，避免把普通 provider 的既有 ambient proxy
    # 行为一刀切打掉。
    return _url_matches_host_suffix(target_url, _ANTHROPIC_OFFICIAL_HOSTS)


def _scrub_account_command_env(env):
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if any(normalized.startswith(prefix) for prefix in _ACCOUNT_ENV_PREFIX_BLOCKLIST):
            env.pop(key, None)
            continue
        if normalized in _ACCOUNT_PROXY_ENV_KEYS or normalized in _ACCOUNT_FAKE_ENV_KEYS or normalized in _ACCOUNT_CA_ENV_KEYS:
            env.pop(key, None)
    return env


def _runtime_httpx_kwargs(runtime, *, target_url=""):
    transport_kwargs = {}
    proxy_url = str((runtime or {}).get("proxy") or "").strip()
    if proxy_url:
        transport_kwargs["proxy"] = proxy_url
    if _runtime_should_disable_ambient_env(runtime, target_url=target_url):
        transport_kwargs["trust_env"] = False
    if _runtime_force_ipv4(runtime):
        transport_kwargs["local_address"] = "0.0.0.0"
    return transport_kwargs


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
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return None
    try:
        parsed = urlparse(proxy_url)
    except Exception:
        return "代理地址解析失败"
    if parsed.scheme.lower() not in _SUPPORTED_PROXY_SCHEMES:
        return "代理协议仅支持 http / https / socks5 / socks5h"
    if not parsed.hostname:
        return "代理地址缺少 host"
    if parsed.port is None:
        return "代理地址缺少 port"
    return None


def _test_proxy_connectivity(proxy_url, no_proxy="", target_url="https://api.anthropic.com", force_ipv4=True):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return True, "未配置代理，跳过检测"
    if _fake_upstream_enabled():
        probe = _fake_proxy_probe(
            target_url,
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=False,
        )
        return bool(probe.get("ok")), str(probe.get("detail") or probe.get("http_code") or "fake upstream")
    curl_bin = shutil.which("curl")
    if not curl_bin:
        return False, "当前系统没有 curl，无法测试代理连通性"
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        proxy_url,
        target_url,
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess.run(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode == 0 and _http_status_is_success(http_code):
        return True, f"代理连通性测试通过：{target_url} (HTTP {http_code})"
    detail = (result.stderr or "").strip()
    if http_code and http_code not in {"000"}:
        detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return False, detail or f"代理连通性测试失败：{target_url}"


def _prompt_validated_proxy_fields(current_proxy="", current_no_proxy="", *, wizard=False, target_url="https://api.anthropic.com"):
    prompt_fn = _wizard_prompt if wizard else Prompt.ask
    proxy_label = "代理地址（可选，直接回车跳过；例 http://127.0.0.1:7890 / socks5h://127.0.0.1:7890）"
    no_proxy_label = "NO_PROXY（可选，直接回车跳过）"
    while True:
        proxy = prompt_fn(
            _L(proxy_label, "Proxy URL (optional, press Enter to skip; e.g. http://127.0.0.1:7890 / socks5h://127.0.0.1:7890)"),
            default=current_proxy or "",
        ).strip()
        error = _validate_proxy_url(proxy)
        if error:
            console.print(f"[red]{error}[/red]")
            continue
        if not proxy:
            return "", ""
        no_proxy = prompt_fn(_L(no_proxy_label, "NO_PROXY (optional, press Enter to skip)"), default=current_no_proxy or "").strip()
        if proxy:
            console.print(f"[dim]正在测试代理连通性: {target_url}[/dim]")
            ok, detail = _test_proxy_connectivity(
                proxy,
                no_proxy=no_proxy,
                target_url=target_url,
                force_ipv4=True,
            )
            if ok:
                console.print(f"[green]✓ {detail}[/green]")
                return proxy, no_proxy
            console.print(
                f"[yellow]代理测试未通过[/yellow]\n"
                f"[dim]{detail}[/dim]\n"
                f"[dim]这可能是 proxy 不通，也可能是当前代理策略不放行 {target_url}。[/dim]"
            )
            if Confirm.ask("仍然保存这个代理配置？", default=False):
                return proxy, no_proxy
            current_proxy = proxy
            current_no_proxy = no_proxy
            continue
        return proxy, no_proxy


def _prompt_validated_timezone(current_timezone="", *, wizard=False):
    prompt_fn = _wizard_prompt if wizard else Prompt.ask
    label = _L(
        f"启动时区（默认 {DEFAULT_ACCOUNT_TIMEZONE}）",
        f"Launch timezone (default {DEFAULT_ACCOUNT_TIMEZONE})",
    )
    while True:
        timezone_name = prompt_fn(label, default=current_timezone or DEFAULT_ACCOUNT_TIMEZONE).strip()
        try:
            ZoneInfo(timezone_name)
            return timezone_name
        except Exception:
            console.print(f"[red]无效时区: {timezone_name}[/red]")


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


def _sanitize_provider_id(provider_id):
    from mms_command_tools import sanitize_provider_id

    return sanitize_provider_id(provider_id, default_provider_id=DEFAULT_PROVIDER_ID)


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


def _provider_env_value(provider_id, field):
    """读取 provider 环境变量。"""
    from mms_command_tools import provider_env_value

    return provider_env_value(provider_id, field, default_provider_id=DEFAULT_PROVIDER_ID)


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
    cfg, _ = _ensure_provider_config(cfg)
    cfg, _ = _ensure_account_config(cfg)
    cfg, _ = ensure_broker_config(cfg)
    cfg, _ = _normalize_ui_config(cfg)
    cfg, _ = _normalize_presets_config(cfg)
    cfg, _ = _normalize_user_config(cfg)
    cfg, _ = _normalize_cache_config(cfg)
    return cfg


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
    clean = str(model_name or "").replace("[1m]", "").strip()
    if not clean:
        return None
    try:
        from mms_capability_resolver import resolve_model_capabilities

        caps = resolve_model_capabilities(clean)
        if caps.get("sources", {}).get("context_window_tokens") == "approved_facts":
            window = int(caps.get("context_window_tokens"))
            if window > 0:
                return window
    except Exception:
        pass
    try:
        from mms_launchers import _MODEL_CONTEXT_WINDOWS
    except Exception:
        return None
    window = _MODEL_CONTEXT_WINDOWS.get(clean)
    if window is not None:
        return window
    lower = clean.lower()
    for key, value in _MODEL_CONTEXT_WINDOWS.items():
        if key.lower() == lower:
            return value
    return None


def _native_clis_for_model(model_name):
    from mms_command_tools import native_clis_for_model

    return native_clis_for_model(model_name)


def _is_installed_mms_layout(module_path=None):
    current_path = os.path.abspath(module_path or __file__)
    installed_root = os.path.abspath(os.path.join(resolve_real_user_home(), ".mms"))
    try:
        return os.path.commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def _default_gpt_reasoning_effort(module_path=None):
    return "high" if _is_installed_mms_layout(module_path=module_path) else "xhigh"


def _default_reasoning_effort_for_model_info(model_info):
    values = []
    if isinstance(model_info, dict):
        values.extend(str(v or "") for k, v in model_info.items() if k != "subagent")
    else:
        values.append(str(model_info or ""))
    for item in values:
        normalized = str(item or "").strip().lower()
        if "/" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]
        if _model_matches_account_cli("codex", normalized):
            return _default_gpt_reasoning_effort()
    return "high"


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


def _model_cli_modes(model_name):
    from mms_command_tools import model_cli_modes

    return model_cli_modes(model_name, infer_model_family=_infer_model_family)


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
    providers = _provider_map(cfg)
    resolved_id = provider_id or cfg.get("provider", {}).get("default") or DEFAULT_PROVIDER_ID
    provider = providers.get(resolved_id)
    if provider:
        return provider
    if provider_id:
        console.print(f"[red]未找到 provider: {provider_id}[/red]")
        sys.exit(1)
    if providers:
        return next(iter(providers.values()))
    return _default_provider()


def get_account_definition(cfg, account_id=None, cli_name=None):
    accounts = _account_map(cfg)
    resolved_id = account_id
    if not resolved_id and cli_name:
        resolved_id = cfg.get("account", {}).get("defaults", {}).get(cli_name)
    if resolved_id:
        account = accounts.get(resolved_id)
        if account:
            return account
        console.print(f"[red]未找到账号档案: {resolved_id}[/red]")
        sys.exit(1)
    return None


# ── Config ──────────────────────────────────────────────


def _active_config_path():
    base_primary_dir = _base_user_primary_dir_from_gateway(CONFIG_PATH)
    if base_primary_dir:
        base_config_path = os.path.join(base_primary_dir, "config.toml")
        if os.path.exists(base_config_path):
            return base_config_path
    return CONFIG_PATH


def _active_credentials_path():
    base_primary_dir = _base_user_primary_dir_from_gateway(CREDENTIALS_PATH)
    if base_primary_dir:
        base_credentials_path = os.path.join(base_primary_dir, "credentials.sh")
        if os.path.exists(base_credentials_path):
            return base_credentials_path
    return CREDENTIALS_PATH


def _active_usage_path():
    base_primary_dir = _base_user_primary_dir_from_gateway(USAGE_PATH)
    if base_primary_dir:
        base_usage_path = os.path.join(base_primary_dir, "usage.json")
        if os.path.exists(base_usage_path):
            return base_usage_path
    return USAGE_PATH


def _config_guard_root_dir(config_path=None):
    target_path = os.path.abspath(str(config_path or _config_write_target_path()))
    base_primary_dir = _base_user_primary_dir_from_gateway(target_path)
    if base_primary_dir:
        return base_primary_dir
    return os.path.dirname(target_path)


def _config_snapshot_root(config_path=None):
    return os.path.join(_config_guard_root_dir(config_path), CONFIG_SNAPSHOT_DIR)


def _config_snapshot_path(snapshot_kind, filename="latest.json", *, config_path=None):
    return os.path.join(_config_snapshot_root(config_path), snapshot_kind, filename)


def _is_snapshot_ignored_file(path):
    name = os.path.basename(str(path or ""))
    return name in SNAPSHOT_IGNORED_FILES


def _render_mms_config_agents_guard():
    from mms_command_tools import render_mms_config_agents_guard

    return render_mms_config_agents_guard()


def _render_mms_config_claude_guard():
    from mms_command_tools import render_mms_config_claude_guard

    return render_mms_config_claude_guard()


def _ensure_mms_config_guard_files(config_path=None):
    root_dir = _config_guard_root_dir(config_path)
    os.makedirs(root_dir, exist_ok=True)
    guard_payloads = {
        "AGENTS.md": _render_mms_config_agents_guard(),
        "CLAUDE.md": _render_mms_config_claude_guard(),
    }
    backup_dir = ""
    for filename, content in guard_payloads.items():
        target_path = os.path.join(root_dir, filename)
        existing = ""
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            except OSError:
                existing = ""
        if existing == content:
            continue
        if existing:
            if not backup_dir:
                backup_dir = os.path.join(
                    _config_backup_root(os.path.join(root_dir, "config.toml")),
                    f"guardrails-{_local_now_slug()}",
                )
                os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(target_path, os.path.join(backup_dir, filename))
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass


def _sha256_text(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _snapshot_proxy_fingerprint(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    parsed = urlparse(proxy_url)
    scheme = parsed.scheme or "proxy"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    auth = "+auth" if parsed.username or parsed.password else ""
    return f"{scheme}://{host}{port}{auth}"


def _snapshot_cli_state(home_dir, cli_name):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    if not home_dir:
        return []
    if cli_name == "claude":
        return [
            os.path.join(home_dir, ".claude", "settings.json"),
        ]
    if cli_name == "codex":
        return [
            os.path.join(home_dir, ".codex", "auth.json"),
            os.path.join(home_dir, ".codex", "config.toml"),
        ]
    if cli_name == "gemini":
        return [
            os.path.join(home_dir, ".gemini", "settings.json"),
            os.path.join(home_dir, ".gemini", ".env"),
        ]
    if cli_name == "agy":
        return [
            os.path.join(home_dir, ".gemini", "antigravity-cli", "settings.json"),
        ]
    return []


def _snapshot_file_entry(path):
    absolute_path = os.path.abspath(os.path.expanduser(str(path)))
    entry = {"path": absolute_path, "exists": os.path.exists(absolute_path)}
    if not entry["exists"]:
        return entry
    try:
        stat = os.stat(absolute_path)
        entry["size"] = int(stat.st_size)
        entry["mtime"] = int(stat.st_mtime)
    except OSError:
        entry["size"] = 0
        entry["mtime"] = 0
    try:
        normalized_bytes, normalized_kind = _snapshot_file_content_bytes(absolute_path)
    except OSError:
        entry["read_error"] = True
        return entry
    entry["sha256"] = hashlib.sha256(normalized_bytes).hexdigest()
    if normalized_kind:
        entry["normalized_kind"] = normalized_kind
    return entry


def _normalize_claude_state_snapshot_payload(data):
    data = data if isinstance(data, dict) else {}
    oauth_account = data.get("oauthAccount") if isinstance(data.get("oauthAccount"), dict) else {}
    return {
        "userID": str(data.get("userID") or "").strip(),
        "oauthAccount": {
            "accountUuid": str(oauth_account.get("accountUuid") or "").strip(),
            "emailAddress": str(oauth_account.get("emailAddress") or "").strip(),
            "organizationUuid": str(oauth_account.get("organizationUuid") or "").strip(),
            "billingType": str(oauth_account.get("billingType") or "").strip(),
            "displayName": str(oauth_account.get("displayName") or "").strip(),
            "organizationRole": str(oauth_account.get("organizationRole") or "").strip(),
            "workspaceRole": str(oauth_account.get("workspaceRole") or "").strip(),
            "organizationName": str(oauth_account.get("organizationName") or "").strip(),
        },
    }


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
    data = dict(data) if isinstance(data, dict) else {}
    env_data = data.get("env")
    if isinstance(env_data, dict):
        cleaned_env = {
            key: value
            for key, value in env_data.items()
            if str(key or "").strip() not in _CLAUDE_SESSION_ENV_KEYS
        }
        if cleaned_env:
            data["env"] = cleaned_env
        else:
            data.pop("env", None)
    return data


def _snapshot_file_content_bytes(path):
    absolute_path = os.path.abspath(os.path.expanduser(str(path)))
    if os.path.basename(absolute_path) == ".claude.json":
        with open(absolute_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        normalized = _normalize_claude_state_snapshot_payload(data)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8"), "claude_state_identity"
    if (
        os.path.basename(absolute_path) == "settings.json"
        and os.path.basename(os.path.dirname(absolute_path)) == ".claude"
    ):
        with open(absolute_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        normalized = _normalize_claude_settings_snapshot_payload(data)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8"), "claude_settings_runtime_stripped"
    with open(absolute_path, "rb") as f:
        return f.read(), ""


def _snapshot_account_entry(account):
    account = account if isinstance(account, dict) else {}
    proxy_value = str(account.get("proxy") or "").strip()
    home_dir = os.path.expanduser(str(account.get("home_dir") or "").strip())
    identity = _snapshot_claude_identity_entry(home_dir) if str(account.get("cli") or "").strip() == "claude" else {}
    return {
        "id": str(account.get("id") or "").strip(),
        "cli": str(account.get("cli") or "").strip(),
        "enabled": bool(account.get("enabled", True)),
        "home_dir": home_dir,
        "priority": _normalize_priority(account.get("priority", DEFAULT_PRIORITY)),
        "claude_1m_mode": str(account.get("claude_1m_mode") or "auto").strip(),
        "timezone": _normalize_timezone_name(account.get("timezone"), DEFAULT_ACCOUNT_TIMEZONE),
        "force_ipv4": bool(_runtime_force_ipv4(account)),
        "no_proxy": str(account.get("no_proxy") or "").strip(),
        "proxy_fingerprint": _snapshot_proxy_fingerprint(proxy_value),
        "proxy_sha256": _sha256_text(proxy_value),
        "identity_fingerprint": identity.get("fingerprint", ""),
        "identity_sha256": identity.get("sha256", ""),
    }


def _snapshot_claude_identity_entry(home_dir):
    home_dir = os.path.expanduser(str(home_dir or "").strip())
    target = os.path.join(home_dir, ".claude.json")
    if not target or not os.path.exists(target):
        return {"fingerprint": "", "sha256": ""}
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"fingerprint": "", "sha256": ""}
    normalized = _normalize_claude_state_snapshot_payload(data)
    oauth = normalized.get("oauthAccount") if isinstance(normalized.get("oauthAccount"), dict) else {}
    fingerprint = "|".join(
        [
            _mask_identity_value(normalized.get("userID") or "", keep=4),
            _mask_identity_value(oauth.get("accountUuid") or "", keep=4),
            _mask_identity_value(oauth.get("organizationUuid") or "", keep=4),
            _mask_email_value(oauth.get("emailAddress") or ""),
        ]
    )
    return {
        "fingerprint": fingerprint,
        "sha256": _sha256_text(json.dumps(normalized, ensure_ascii=False, sort_keys=True)),
    }


def _snapshot_provider_entry(provider):
    provider = provider if isinstance(provider, dict) else {}
    proxy_value = str(provider.get("proxy") or "").strip()
    return {
        "id": str(provider.get("id") or "").strip(),
        "name": str(provider.get("name") or "").strip(),
        "enabled": bool(provider.get("enabled", True)),
        "priority": _normalize_priority(provider.get("priority", DEFAULT_PRIORITY)),
        "models_endpoint": str(provider.get("models_endpoint") or "").strip(),
        "timezone": _normalize_timezone_name(provider.get("timezone"), DEFAULT_ACCOUNT_TIMEZONE),
        "force_ipv4": bool(_runtime_force_ipv4(provider)),
        "no_proxy": str(provider.get("no_proxy") or "").strip(),
        "proxy_fingerprint": _snapshot_proxy_fingerprint(proxy_value),
        "proxy_sha256": _sha256_text(proxy_value),
    }


def _build_config_guard_snapshot(cfg, *, config_path=None):
    cfg = cfg if isinstance(cfg, dict) else _default_config()
    config_path = os.path.abspath(str(config_path or _config_write_target_path()))
    config_root = _config_guard_root_dir(config_path)
    real_home = os.path.expanduser(
        str(os.environ.get("MMS_REAL_HOME") or os.environ.get("ORIGINAL_HOME") or os.environ.get("REAL_HOME") or "~")
    )

    files = [
        os.path.join(config_root, "override.toml"),
        os.path.join(config_root, "credentials.sh"),
        os.path.join(config_root, "usage.json"),
        os.path.join(config_root, "account-guard-state.json"),
        os.path.join(config_root, "AGENTS.md"),
        os.path.join(config_root, "CLAUDE.md"),
    ]
    accounts = []
    for account in cfg.get("accounts", []):
        if not isinstance(account, dict):
            continue
        entry = _snapshot_account_entry(account)
        accounts.append(entry)
        files.extend(_snapshot_cli_state(entry.get("home_dir"), entry.get("cli")))
    providers = [
        _snapshot_provider_entry(provider)
        for provider in cfg.get("providers", [])
        if isinstance(provider, dict)
    ]

    deduped_files = []
    seen_paths = set()
    for path in files:
        normalized = os.path.abspath(os.path.expanduser(str(path)))
        if _is_snapshot_ignored_file(normalized):
            continue
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        deduped_files.append(_snapshot_file_entry(normalized))

    return {
        "schema": CONFIG_SNAPSHOT_SCHEMA,
        "captured_at": _iso_now(),
        "config_root": config_root,
        "config_path": config_path,
        "real_home": real_home,
        "defaults": {
            "provider_default": str(cfg.get("provider", {}).get("default") or "").strip(),
            "account_defaults": dict(cfg.get("account", {}).get("defaults") or {}),
        },
        "accounts": sorted(accounts, key=lambda item: item.get("id", "")),
        "providers": sorted(providers, key=lambda item: item.get("id", "")),
        "files": sorted(deduped_files, key=lambda item: item.get("path", "")),
    }


def _snapshot_digest(snapshot_data):
    payload = json.dumps(snapshot_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json_snapshot(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json_snapshot(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _snapshot_period_bucket(period_name):
    now = datetime.now()
    if period_name == "daily":
        return now.strftime("%Y-%m-%d")
    if period_name == "weekly":
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
    return now.strftime("%Y-%m-%dT%H:%M")


def _update_periodic_snapshot(period_name, snapshot_data, *, config_path=None):
    path = _config_snapshot_path(period_name, "latest.json", config_path=config_path)
    payload = {
        "period": period_name,
        "bucket": _snapshot_period_bucket(period_name),
        "captured_at": _iso_now(),
        "digest": _snapshot_digest(snapshot_data),
        "snapshot": snapshot_data,
    }
    _write_json_snapshot(path, payload)


def _snapshot_diff_lines(previous_snapshot, current_snapshot):
    from mms_command_tools import snapshot_diff_lines

    return snapshot_diff_lines(
        previous_snapshot,
        current_snapshot,
        is_snapshot_ignored_file=_is_snapshot_ignored_file,
    )


def _snapshot_prompt_allowed():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _confirm_startup_snapshot_drift(diff_lines, *, accepted_path, latest_path):
    _ensure_rich()
    preview = "\n".join(f"- {line}" for line in diff_lines[:12])
    if len(diff_lines) > 12:
        preview += f"\n- ... 还有 {len(diff_lines) - 12} 项"
    panel_text = (
        "检测到 MMS 配置/关键文件与上次确认快照不一致，已阻止静默启动。\n\n"
        f"{preview}\n\n"
        f"accepted: {accepted_path}\n"
        f"latest:   {latest_path}\n"
    )
    console.print(Panel(panel_text, title="MMS Snapshot Guard", border_style="red"))
    if not _snapshot_prompt_allowed():
        return False
    return bool(Confirm.ask("是否接受当前快照并继续启动？", default=False))


def _ensure_startup_snapshot_guard(cfg, *, enforce=True):
    config_path = _config_write_target_path()
    current_snapshot = _build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = _config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = _config_snapshot_path("startup", "accepted.json", config_path=config_path)

    latest_payload = {
        "kind": "startup",
        "captured_at": _iso_now(),
        "digest": _snapshot_digest(current_snapshot),
        "snapshot": current_snapshot,
    }
    _write_json_snapshot(latest_path, latest_payload)
    _update_periodic_snapshot("daily", current_snapshot, config_path=config_path)
    _update_periodic_snapshot("weekly", current_snapshot, config_path=config_path)

    accepted_payload = _load_json_snapshot(accepted_path)
    accepted_snapshot = (accepted_payload or {}).get("snapshot") if isinstance(accepted_payload, dict) else None
    if not accepted_snapshot:
        _write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    diff_lines = _snapshot_diff_lines(accepted_snapshot, current_snapshot)
    if not diff_lines:
        _write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    pending_path = _config_snapshot_path("startup", "pending.json", config_path=config_path)
    _write_json_snapshot(
        pending_path,
        {
            "kind": "startup-pending",
            "captured_at": _iso_now(),
            "accepted_path": accepted_path,
            "latest_path": latest_path,
            "diffs": diff_lines,
            "accepted": accepted_snapshot,
            "current": current_snapshot,
        },
    )
    if not enforce:
        return current_snapshot
    if _confirm_startup_snapshot_drift(diff_lines, accepted_path=accepted_path, latest_path=latest_path):
        _write_json_snapshot(accepted_path, latest_payload)
        return current_snapshot

    console.print(
        f"[red]启动已阻止：检测到配置/关键文件漂移，请先确认快照。[/red]\n"
        f"[dim]漂移详情: {pending_path}[/dim]\n"
        f"[dim]查看: {current_command()} guard status[/dim]\n"
        f"[dim]接受: {current_command()} guard accept[/dim]"
    )
    sys.exit(CONFIG_GUARD_EXIT_CODE)

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
    cfg = load_config()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


def _config_write_target_path():
    return _active_config_path() or CONFIG_PATH


def _config_lock_path(config_path=None):
    target_path = os.path.abspath(str(config_path or _config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), CONFIG_LOCK_FILE)


def _config_audit_path(config_path=None):
    target_path = os.path.abspath(str(config_path or _config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), CONFIG_AUDIT_LOG)


def _config_backup_root(config_path=None):
    target_path = os.path.abspath(str(config_path or _config_write_target_path()))
    return os.path.join(os.path.dirname(target_path), "backups")


def _sha1_file(path):
    if not path or not os.path.exists(path):
        return ""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _config_write_caller():
    current = os.path.abspath(__file__)
    stack = inspect.stack()
    try:
        for frame in stack[1:]:
            filename = os.path.abspath(str(frame.filename))
            if filename == current and frame.function == "save_config":
                continue
            return {
                "path": filename,
                "line": int(frame.lineno),
                "function": str(frame.function or ""),
            }
    finally:
        del stack
    return {"path": current, "line": 0, "function": "unknown"}


@contextmanager
def _locked_config_write(config_path):
    lock_path = _config_lock_path(config_path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with _CONFIG_WRITE_PROCESS_LOCK:
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _locked_state_file(path):
    lock_path = os.path.abspath(str(path or "")) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with _STATE_FILE_PROCESS_LOCK:
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _backup_config_file(config_path):
    if not os.path.exists(config_path):
        return ""
    backup_dir = os.path.join(_config_backup_root(config_path), f"config-write-{_local_now_slug()}")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(config_path))
    shutil.copy2(config_path, backup_path)
    return backup_path


def _append_config_audit_entry(entry, *, config_path):
    audit_path = _config_audit_path(config_path)
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _atomic_write_toml(path, cfg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(cfg, f)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


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
    with open(path, "rb") as f:
        return tomllib.loads(f.read().decode("utf-8"))


def _existing_override_paths():
    return [path for path in OVERRIDE_PATHS if os.path.exists(path)]


def _existing_preferences_paths():
    return [path for path in PREFERENCES_PATHS if os.path.exists(path)]


def _merge_dicts(base, override):
    from mms_command_tools import merge_dicts

    return merge_dicts(base, override)


def _pref_bool(value):
    from mms_command_tools import pref_bool

    return pref_bool(value)


def _pref_enable_disable(value):
    from mms_command_tools import pref_enable_disable

    return pref_enable_disable(value)


def _pref_reasoning_effort(value):
    from mms_command_tools import pref_reasoning_effort

    return pref_reasoning_effort(value)


def _pref_agent_pack(value):
    from mms_command_tools import pref_agent_pack

    return pref_agent_pack(value)


def _sanitize_surface_list(values):
    from mms_command_tools import sanitize_surface_list

    return sanitize_surface_list(values)


def _sanitize_disabled_session_surfaces(payload):
    from mms_command_tools import sanitize_disabled_session_surfaces

    return sanitize_disabled_session_surfaces(payload)


def _sanitize_launch_preferences(payload):
    from mms_command_tools import sanitize_launch_preferences

    return sanitize_launch_preferences(payload)


_PREFERENCE_ASSET_ROOT_KEYS = {
    "agent_browser": "agent_browser",
    "agent-browser": "agent_browser",
    "auto_github_contributor": "auto_github_contributor",
    "auto-github-contributor": "auto_github_contributor",
    "caveman": "caveman",
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


def _sanitize_asset_roots(payload):
    from mms_command_tools import sanitize_asset_roots

    return sanitize_asset_roots(payload, asset_root_keys=_PREFERENCE_ASSET_ROOT_KEYS)


def _sanitize_user_preferences(raw):
    from mms_command_tools import sanitize_user_preferences

    return sanitize_user_preferences(raw, cli_names=CLI_NAMES, asset_root_keys=_PREFERENCE_ASSET_ROOT_KEYS)


def load_user_preferences():
    merged = {}
    for path in _existing_preferences_paths():
        try:
            prefs = _load_toml_file(path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            console.print(f"[yellow]跳过无效 preferences 文件 {path}: {exc}[/yellow]")
            continue
        if isinstance(prefs, dict):
            merged = _merge_dicts(merged, prefs)
    return _sanitize_user_preferences(merged)


def preference_asset_root(asset_name):
    key = _PREFERENCE_ASSET_ROOT_KEYS.get(str(asset_name or "").strip().lower())
    if not key:
        return ""
    return str(load_user_preferences().get("assets", {}).get("roots", {}).get(key) or "").strip()


def _merge_disabled_session_surfaces(*payloads):
    from mms_command_tools import merge_disabled_session_surfaces

    return merge_disabled_session_surfaces(*payloads)


def _preference_runtime_overlay(prefs, cli_name):
    from mms_command_tools import preference_runtime_overlay

    return preference_runtime_overlay(prefs, cli_name)


def _runtime_with_launch_preferences(cfg, runtime, cli_name):
    from mms_command_tools import runtime_with_launch_preferences

    return runtime_with_launch_preferences(
        cfg,
        runtime,
        cli_name,
        load_user_preferences=load_user_preferences,
    )


def apply_local_overrides(cfg):
    merged = dict(cfg)
    for path in _existing_override_paths():
        try:
            override_cfg = _load_toml_file(path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            console.print(f"[yellow]跳过无效 override 文件 {path}: {exc}[/yellow]")
            continue
        if isinstance(override_cfg, dict):
            merged = _merge_dicts(merged, override_cfg)
    merged["_mms_preferences"] = load_user_preferences()
    return merged


def _env_file_path(cli_name):
    from mms_command_tools import env_file_path

    return env_file_path(cli_name, env_dir=ENV_DIR)


def _shell_quote(value):
    from mms_command_tools import shell_quote

    return shell_quote(value)


def _parse_shell_value(raw):
    from mms_command_tools import parse_shell_value

    return parse_shell_value(raw)


def _load_env_file(path):
    from mms_command_tools import load_env_file

    return load_env_file(path)


def _iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_now_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _load_usage_stats():
    usage_path = _active_usage_path()
    return _load_usage_stats_from_path(usage_path)


def _load_usage_stats_from_path(usage_path):
    if not os.path.exists(usage_path):
        return {"sources": {}}
    try:
        with open(usage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("sources", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sources": {}}


def _write_usage_stats_locked(usage_path, data):
    _ensure_mms_config_guard_files(_config_write_target_path())
    os.makedirs(os.path.dirname(usage_path), exist_ok=True)
    tmp_path = usage_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, usage_path)
    os.chmod(usage_path, 0o600)


def _save_usage_stats(data):
    usage_path = _active_usage_path()
    with _locked_state_file(usage_path):
        _write_usage_stats_locked(usage_path, data)
    _trigger_routes_export_after_usage_write()


def _update_usage_stats(mutator):
    usage_path = _active_usage_path()
    with _locked_state_file(usage_path):
        stats = _load_usage_stats_from_path(usage_path)
        result = mutator(stats)
        _write_usage_stats_locked(usage_path, stats)
    _trigger_routes_export_after_usage_write()
    return result


_USAGE_ROUTES_EXPORT_LOCK = threading.Lock()
_USAGE_ROUTES_EXPORT_RUNNING = False
_USAGE_ROUTES_EXPORT_LAST_STARTED_AT = 0.0
_USAGE_ROUTES_EXPORT_MIN_INTERVAL_SEC = 15.0


def _trigger_routes_export_after_usage_write():
    """Best-effort async routes export after usage changes.

    This keeps model-routes.json reasonably fresh for file readers such as Hive
    without blocking the foreground launch path on a full export.
    """
    global _USAGE_ROUTES_EXPORT_RUNNING, _USAGE_ROUTES_EXPORT_LAST_STARTED_AT

    now = time.monotonic()
    with _USAGE_ROUTES_EXPORT_LOCK:
        if _USAGE_ROUTES_EXPORT_RUNNING:
            return
        if now - _USAGE_ROUTES_EXPORT_LAST_STARTED_AT < _USAGE_ROUTES_EXPORT_MIN_INTERVAL_SEC:
            return
        _USAGE_ROUTES_EXPORT_RUNNING = True
        _USAGE_ROUTES_EXPORT_LAST_STARTED_AT = now

    def _run():
        global _USAGE_ROUTES_EXPORT_RUNNING
        try:
            _refresh_routes_export_for_hive(force=True, quiet=True)
        except Exception:
            pass
        finally:
            with _USAGE_ROUTES_EXPORT_LOCK:
                _USAGE_ROUTES_EXPORT_RUNNING = False

    threading.Thread(
        target=_run,
        daemon=True,
        name="mms-usage-routes-export",
    ).start()


def _refresh_routes_export_for_hive(cfg=None, *, force=True, quiet=False, startup_safe=False):
    """Synchronously refresh the Hive-facing routes export from current config."""
    try:
        from mms_router import export_model_routes

        current_cfg = cfg
        if current_cfg is None:
            current_cfg = load_config()
            if current_cfg is None:
                return False
            current_cfg = apply_local_overrides(current_cfg)
        export_model_routes(current_cfg, force=force, startup_safe=startup_safe)
        return True
    except Exception as exc:
        if not quiet:
            console.print(f"[yellow]⚠ Hive routes export 刷新失败: {exc}[/yellow]")
        return False


def _trigger_routes_export_after_credentials_write():
    """Best-effort routes export after provider key / URL changes."""
    _refresh_routes_export_for_hive(force=True, quiet=True)


def _backup_config_tree(label):
    backup_root = os.path.join(resolve_real_user_home(), ".config", "mms-backups")
    os.makedirs(backup_root, exist_ok=True)
    backup_dir = os.path.join(backup_root, f"{label}-{_local_now_slug()}")
    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(PRIMARY_CONFIG_DIR):
        shutil.copytree(
            PRIMARY_CONFIG_DIR,
            os.path.join(backup_dir, os.path.basename(PRIMARY_CONFIG_DIR)),
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
    return backup_dir


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


def _record_scene_usage(scene_name, cli_name, model_info):
    from mms_command_tools import record_scene_usage

    return record_scene_usage(
        scene_name,
        cli_name,
        model_info,
        update_usage_stats=_update_usage_stats,
        iso_now=_iso_now,
        resolve_model_name=_resolve_model_name,
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
    if not _trace_enabled:
        return
    _trace_overrides.append((source, {k: v for k, v in kv.items() if v is not None}))


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


def _trace_source_for(field, value):
    from mms_command_tools import trace_source_for

    return trace_source_for(field, value, _trace_overrides)


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
    runtime = _runtime_with_launch_preferences(
        {"_mms_preferences": load_user_preferences()},
        runtime,
        cli_name,
    )
    if cli_name == "claude":
        runtime = _runtime_with_vision_sidecar(load_config() or {}, runtime)
    if _trace_enabled:
        _print_trace(cli_name, model_info, runtime)
    _record_usage(runtime, cli_name, model_info)
    if runtime and runtime.get("runtime_kind") == "broker" and cli_name == "claude":
        if extra_args:
            console.print("[red]broker profile 暂不支持 CLI resume 参数[/red]")
            raise SystemExit(1)
        model_override = _resolve_model_name(model_info)
        if model_override == "official-default":
            model_override = runtime.get("remote_service_model", "")
        exit_code = run_broker_profile_interactive(
            load_config(),
            runtime.get("broker_profile_id", runtime.get("id", "")),
            model_override=model_override,
        )
        if exit_code != 0:
            raise SystemExit(exit_code)
        return
    from mms_launchers import launch_cli
    launch_cli(cli_name, model_info, runtime, once=once, extra_args=extra_args)



def load_provider_credentials(provider_id=DEFAULT_PROVIDER_ID):
    base_key = _provider_env_name(provider_id, "BASE_URL")
    openai_base_key = _provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = _provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = _provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = _provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = os.environ.get(base_key, "").strip()
    openai_base_url = os.environ.get(openai_base_key, "").strip()
    anthropic_base_url = os.environ.get(anthropic_base_key, "").strip()
    api_key = os.environ.get(api_key_name, "").strip()
    openai_api_key = os.environ.get(openai_api_key_name, "").strip()

    if provider_id == DEFAULT_PROVIDER_ID:
        base_url = base_url or os.environ.get(API_URL_ENV_NAME, "").strip()
        api_key = api_key or os.environ.get(API_KEY_ENV_NAME, "").strip()

    for credentials_path in (CREDENTIALS_PATH,):
        if not os.path.exists(credentials_path):
            continue
        file_values = _load_env_file(credentials_path)
        base_url = base_url or file_values.get(base_key, "").strip()
        openai_base_url = openai_base_url or file_values.get(openai_base_key, "").strip()
        anthropic_base_url = anthropic_base_url or file_values.get(anthropic_base_key, "").strip()
        api_key = api_key or file_values.get(api_key_name, "").strip()
        openai_api_key = openai_api_key or file_values.get(openai_api_key_name, "").strip()
        if provider_id == DEFAULT_PROVIDER_ID:
            base_url = base_url or file_values.get(API_URL_ENV_NAME, "").strip()
            api_key = api_key or file_values.get(API_KEY_ENV_NAME, "").strip()

    config_path = _active_config_path()
    if provider_id == DEFAULT_PROVIDER_ID and (not base_url or not api_key) and os.path.exists(config_path):
        with open(config_path, "rb") as f:
            legacy_cfg = tomllib.loads(f.read().decode("utf-8"))
        legacy_api = legacy_cfg.get("api", {})
        if isinstance(legacy_api, dict):
            base_url = base_url or str(legacy_api.get("base_url", "")).strip()
            api_key = api_key or str(legacy_api.get("api_key", "")).strip()

    return {
        "base_url": base_url.rstrip("/") if base_url else "",
        "openai_base_url": openai_base_url.rstrip("/") if openai_base_url else "",
        "anthropic_base_url": anthropic_base_url.rstrip("/") if anthropic_base_url else "",
        "api_key": api_key,
        "openai_api_key": openai_api_key,
    }


def save_provider_credentials(provider_id, base_url, api_key, openai_base_url="", anthropic_base_url="", openai_api_key=None):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    values = _load_env_file(CREDENTIALS_PATH) if os.path.exists(CREDENTIALS_PATH) else {}
    base_key = _provider_env_name(provider_id, "BASE_URL")
    openai_base_key = _provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = _provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = _provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = _provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = base_url.rstrip("/")
    openai_base_url = openai_base_url.rstrip("/")
    anthropic_base_url = anthropic_base_url.rstrip("/")
    values[base_key] = base_url
    if openai_base_url:
        values[openai_base_key] = openai_base_url
    else:
        values.pop(openai_base_key, None)
    if anthropic_base_url:
        values[anthropic_base_key] = anthropic_base_url
    else:
        values.pop(anthropic_base_key, None)
    values[api_key_name] = api_key
    if openai_api_key is None:
        if openai_base_url:
            values[openai_api_key_name] = api_key
        else:
            values.pop(openai_api_key_name, None)
    elif openai_api_key:
        values[openai_api_key_name] = openai_api_key
    else:
        values.pop(openai_api_key_name, None)

    if provider_id == DEFAULT_PROVIDER_ID:
        values[API_URL_ENV_NAME] = base_url
        values[API_KEY_ENV_NAME] = api_key

    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={_shell_quote(str(values[key]))}")
    lines.append("")

    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.chmod(CREDENTIALS_PATH, 0o600)
    _trigger_routes_export_after_credentials_write()


def load_api_credentials():
    provider_creds = load_provider_credentials(DEFAULT_PROVIDER_ID)
    return provider_creds["base_url"], provider_creds["api_key"]


def save_api_credentials(base_url, api_key):
    save_provider_credentials(DEFAULT_PROVIDER_ID, base_url, api_key)


def resolve_provider_context(cfg, provider_id=None):
    provider = _normalize_provider(get_provider_definition(cfg, provider_id))
    credentials = load_provider_credentials(provider["id"])
    provider["base_url"] = credentials["base_url"]
    provider["openai_base_url"] = credentials["openai_base_url"] or provider.get("default_openai_base_url", "")
    provider["anthropic_base_url"] = credentials["anthropic_base_url"] or provider.get("default_anthropic_base_url", "")
    provider["api_key"] = credentials["api_key"]
    provider["openai_api_key"] = credentials.get("openai_api_key", "")
    provider["auth_mode"] = "api_key"
    provider["runtime_kind"] = "provider"
    return provider


def resolve_account_context(cfg, account_id=None, cli_name=None):
    account = get_account_definition(cfg, account_id=account_id, cli_name=cli_name)
    if account is None:
        return None
    resolved = dict(account)
    resolved["auth_mode"] = "oauth"
    resolved["runtime_kind"] = "account"
    resolved["home_dir"] = os.path.expanduser(resolved.get("home_dir", ""))
    return resolved


def _default_config(role=MODE_ALL):
    return {
        "ui": {"language": "zh"},
        "user": {"role": normalize_user_role(role)},
        "cache": {
            "probe_async_refresh_after_sec": _PROBE_ASYNC_REFRESH_AFTER,
            "probe_async_min_interval_sec": _PROBE_ASYNC_MIN_INTERVAL,
        },
        "provider": {"default": DEFAULT_PROVIDER_ID},
        "providers": [_default_provider()],
        "account": {"defaults": {}},
        "accounts": [],
        "recommend": {"models": [
            "claude-sonnet-4-6", "qwen3-coder-plus", "gpt-4o-mini",
        ]},
        "presets": {
            "coding": {
                "cli": "claude",
                "opus": "claude-opus-4-6",
                "sonnet": "claude-sonnet-4-6",
                "haiku": "claude-haiku-4-5-20251001",
                "subagent": "claude-sonnet-4-6",
            },
            "cheap": {"cli": "claude", "model": "qwen3-coder-plus"},
            "codex-gpt": {"cli": "codex", "model": "gpt-5.4"},
        },
    }


def _migrate_legacy_api_config(cfg):
    api_cfg = cfg.get("api")
    updated_cfg = dict(cfg)

    if isinstance(api_cfg, dict):
        base_url = str(api_cfg.get("base_url", "")).strip()
        api_key = str(api_cfg.get("api_key", "")).strip()
        file_base_url, file_api_key, _ = load_api_credentials()

        if base_url and api_key and (not file_base_url or not file_api_key):
            try:
                save_api_credentials(base_url, api_key)
                console.print(f"[yellow]已将 API 凭据迁移到 {CREDENTIALS_PATH}[/yellow]")
            except OSError as exc:
                console.print(f"[yellow]无法迁移 API 凭据到 {CREDENTIALS_PATH}: {exc}[/yellow]")
                return cfg

        updated_cfg.pop("api", None)

    updated_cfg, changed = _ensure_provider_config(updated_cfg)
    updated_cfg, account_changed = _ensure_account_config(updated_cfg)
    updated_cfg, role_changed = _normalize_user_config(updated_cfg)
    if changed or account_changed or role_changed or updated_cfg != cfg:
        try:
            save_config(updated_cfg)
        except OSError as exc:
            console.print(f"[yellow]无法更新 {CONFIG_PATH}: {exc}[/yellow]")
            return cfg
    return updated_cfg


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


def _provider_id_variants(provider_id):
    from mms_command_tools import provider_id_variants

    return provider_id_variants(provider_id)


def _resolve_config_provider_id(provider_defs, provider_id):
    from mms_command_tools import resolve_config_provider_id

    return resolve_config_provider_id(provider_defs, provider_id)


def _config_truthy(value, default=False):
    from mms_command_tools import config_truthy

    return config_truthy(value, default=default)


def _vision_sidecar_model_candidates_for_provider(provider_id):
    from mms_command_tools import vision_sidecar_model_candidates_for_provider

    return vision_sidecar_model_candidates_for_provider(provider_id)


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
    return account.get("name", account.get("id", "account"))


def _account_env(account):
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
    elif cli_name == "agy":
        seed_agy_state(home_dir)
    env = os.environ.copy()
    _scrub_account_command_env(env)
    if cli_name == "gemini":
        seed_gemini_state(home_dir)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        xdg_config_home = os.path.join(home_dir, ".config")
        env["HOME"] = home_dir
        env["XDG_CONFIG_HOME"] = xdg_config_home
    proxy = str(account.get("proxy", "")).strip()
    no_proxy = str(account.get("no_proxy", "")).strip()
    timezone_name = str(account.get("timezone", "")).strip()
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = proxy
        for key in ("NO_PROXY", "no_proxy"):
            env[key] = no_proxy
    if timezone_name:
        env["TZ"] = timezone_name
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


def _account_status_command(cli_name):
    if cli_name == "claude":
        return ["claude", "auth", "status"]
    if cli_name == "codex":
        return ["codex", "login", "status"]
    if cli_name == "gemini":
        return None
    if cli_name == "agy":
        return None
    return None


def _probe_account_status(account):
    cli_name = account.get("cli")
    if cli_name == "claude":
        return {
            "state": "delegated",
            "summary": "Claude OAuth 独立入口已下线；MMS 不再探测或登录这个账号",
        }
    if cli_name == "gemini":
        home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
        gemini_dir = os.path.join(home_dir, ".gemini")
        oauth_path = os.path.join(gemini_dir, "oauth_creds.json")
        accounts_path = os.path.join(gemini_dir, "google_accounts.json")
        settings_path = os.path.join(gemini_dir, "settings.json")
        if os.path.exists(oauth_path) or os.path.exists(accounts_path):
            return {
                "state": "configured",
                "summary": "已配置 OAuth，建议直接启动 Gemini 验证",
            }
        has_state = os.path.exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，待登录" if has_state else "待登录",
        }
    if cli_name == "agy":
        home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
        agy_dir = os.path.join(home_dir, ".gemini", "antigravity-cli")
        settings_path = os.path.join(agy_dir, "settings.json")
        has_state = os.path.isdir(agy_dir) or os.path.exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，登录状态需启动 agy 验证" if has_state else "待登录",
        }
    command = _account_status_command(cli_name)
    if command is None:
        return {"state": "unsupported", "summary": "不支持状态探测"}
    try:
        result = subprocess.run(
            command,
            env=_account_env(account),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return {"state": "cli_missing", "summary": f"{cli_name} 未安装"}
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "summary": "状态探测超时"}

    output_text = (result.stdout or result.stderr or "").strip()
    output = output_text.splitlines()
    summary = output[0].strip() if output else ""
    if cli_name == "claude" and output_text.startswith("{"):
        try:
            payload = json.loads(output_text)
            email = payload.get("email", "")
            sub = payload.get("subscriptionType", "")
            summary = " / ".join(part for part in [email, sub] if part) or summary
        except json.JSONDecodeError:
            pass
    if result.returncode == 0:
        return {"state": "logged_in", "summary": summary or "已登录"}
    return {"state": "logged_out", "summary": summary or "未登录"}


def _run_account_login(account):
    cli_name = account.get("cli")
    if cli_name == "claude":
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    env = _account_env(account)
    os.makedirs(account.get("home_dir", ""), exist_ok=True)
    if cli_name == "codex":
        command = ["codex", "login"]
    elif cli_name == "gemini":
        command = ["gemini"]
    elif cli_name == "agy":
        command = ["agy"]
    else:
        console.print(f"[red]不支持的官方账号类型: {cli_name}[/red]")
        sys.exit(1)
    env_hint = f"HOME={account.get('home_dir')}"
    if cli_name == "gemini":
        env_hint = f"GEMINI_CLI_HOME={account.get('home_dir')}"
    console.print(
        f"[cyan]正在为账号档案 {_account_label(account)} 打开 {cli_name} 登录流程[/cyan]\n"
        f"[dim]{env_hint}[/dim]"
    )
    if cli_name == "gemini":
        console.print("[dim]Gemini 会在自己的 CLI 内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    if cli_name == "agy":
        console.print("[dim]Antigravity CLI 会在自己的流程内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)


def _ensure_interactive_terminal(action_hint):
    if sys.stdin.isatty():
        _ensure_rich()
        return
    console.print(
        f"[red]当前不是交互终端，无法执行 {action_hint}，请在终端里运行 {current_command()}[/red]"
    )
    sys.exit(1)


def _parse_csv_values(raw_value, allowed_values=None):
    from mms_command_tools import parse_csv_values

    return parse_csv_values(raw_value, allowed_values=allowed_values, console=console)


def _prompt_csv_values(label, default_values, allowed_values):
    _ensure_rich()
    default_text = ",".join(default_values)
    raw_value = Prompt.ask(label, default=default_text)
    values = _parse_csv_values(raw_value, allowed_values=allowed_values)
    if not values:
        console.print(f"[red]{label} 不能为空[/red]")
        sys.exit(1)
    return values


def _upsert_provider(cfg, provider):
    providers = []
    replaced = False
    for item in cfg.get("providers", []):
        if item.get("id") == provider["id"]:
            providers.append(provider)
            replaced = True
        else:
            providers.append(item)
    if not replaced:
        providers.append(provider)

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = providers
    updated_cfg, _ = _ensure_provider_config(updated_cfg)
    return updated_cfg


def _delete_provider_credentials(provider_id):
    if not os.path.exists(CREDENTIALS_PATH):
        return
    values = _load_env_file(CREDENTIALS_PATH)
    keys_to_remove = {
        _provider_env_name(provider_id, "BASE_URL"),
        _provider_env_name(provider_id, "OPENAI_BASE_URL"),
        _provider_env_name(provider_id, "ANTHROPIC_BASE_URL"),
        _provider_env_name(provider_id, "API_KEY"),
    }
    if provider_id == DEFAULT_PROVIDER_ID:
        keys_to_remove.update({API_URL_ENV_NAME, API_KEY_ENV_NAME})
    changed = False
    for key in keys_to_remove:
        if key in values:
            values.pop(key, None)
            changed = True
    if not changed:
        return
    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={_shell_quote(str(values[key]))}")
    lines.append("")
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.chmod(CREDENTIALS_PATH, 0o600)


def _prompt_provider_metadata(existing=None, preset_id=None):
    _ensure_interactive_terminal("模型源配置编辑")
    current = _normalize_provider(existing or {})
    provider_id = preset_id or current.get("id") or DEFAULT_PROVIDER_ID
    if not preset_id:
        provider_id = Prompt.ask("系统内部标识（高级）", default=provider_id).strip() or DEFAULT_PROVIDER_ID
    name = Prompt.ask("显示名称 / 列表展示名", default=current.get("name") or provider_id).strip() or provider_id
    protocols = _prompt_csv_values(
        "协议（逗号分隔）",
        current.get("protocols", list(DEFAULT_PROVIDER_PROTOCOLS)),
        list(DEFAULT_PROVIDER_PROTOCOLS),
    )
    supported_clis = _prompt_csv_values(
        "支持的 CLI（逗号分隔）",
        current.get("supported_clis", list(PROVIDER_CAPABLE_CLIS)),
        list(PROVIDER_CAPABLE_CLIS),
    )
    use_custom_models_endpoint = Confirm.ask(
        "模型列表地址与接口地址不同？（高级）",
        default=current.get("models_endpoint", "/models") != "/models",
    )
    models_endpoint = "/models"
    if use_custom_models_endpoint:
        models_endpoint = _normalize_models_endpoint(
            Prompt.ask("模型列表地址（高级；仅用于拉取模型列表，输入 manual 表示完全手工维护模型）", default=current.get("models_endpoint", "/models"))
        )
    priority = _normalize_priority(Prompt.ask("优先级（数字越大越优先）", default=str(current.get("priority", DEFAULT_PRIORITY))))
    claude_1m_mode = _normalize_claude_1m_mode(
        Prompt.ask(
            "Claude 1M 策略（auto/enable/disable）",
            choices=["auto", "enable", "disable"],
            default=current.get("claude_1m_mode", "auto"),
        )
    )
    proxy, no_proxy = _prompt_validated_proxy_fields(
        current.get("proxy", ""),
        current.get("no_proxy", ""),
        wizard=False,
    )
    timezone_name = _prompt_validated_timezone(current.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE, wizard=False)
    note = Prompt.ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = Confirm.ask("启用这个模型源？", default=bool(current.get("enabled", True)))
    return _normalize_provider({
        "id": provider_id,
        "name": name,
        "protocols": protocols,
        "supported_clis": supported_clis,
        "models_endpoint": models_endpoint,
        "priority": priority,
        "claude_1m_mode": claude_1m_mode,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "note": note,
        "enabled": enabled,
    })


def _provider_template_payload(template_key):
    template = PROVIDER_TEMPLATES.get(template_key) or PROVIDER_TEMPLATES["generic"]
    payload = {
        "id": template["id"],
        "name": template["name"],
        "protocols": list(template["protocols"]),
        "supported_clis": list(template["supported_clis"]),
        "enabled": True,
        "priority": template["priority"],
        "note": template["note"],
    }
    if "default_openai_base_url" in template:
        payload["default_openai_base_url"] = template["default_openai_base_url"]
    if "default_anthropic_base_url" in template:
        payload["default_anthropic_base_url"] = template["default_anthropic_base_url"]
    if "key_prefix" in template:
        payload["key_prefix"] = template["key_prefix"]
    if "fallback_models" in template:
        payload["fallback_models"] = list(template["fallback_models"])
    if "models_endpoint" in template:
        payload["models_endpoint"] = template["models_endpoint"]
    if "provider_profile" in template:
        payload["provider_profile"] = template["provider_profile"]
    if "extension" in template:
        payload["extension"] = template["extension"]
    if "capabilities" in template:
        payload["capabilities"] = dict(template["capabilities"])
    return payload


def _select_provider_template(preset_id=None):
    if preset_id == "openrouter":
        return "openrouter"
    if preset_id and preset_id != "generic":
        console.print("[yellow]已统一收敛为“通用兼容网关”，将直接进入通用网关配置。[/yellow]")
    return "generic"


def _prompt_account_metadata(existing=None, preset_id=None, preset_cli=None):
    _ensure_interactive_terminal("账号档案配置编辑")
    current = _normalize_account(existing or {"cli": preset_cli or "claude", "id": preset_id or ""})
    account_id = preset_id or current.get("id") or "claude-main"
    if not preset_id:
        account_id = _normalize_account_id(Prompt.ask("文件夹名（用于目录和命令）", default=account_id))
    cli_name = preset_cli or current.get("cli", "claude")
    if not preset_cli:
        if cli_name not in MMS_MANAGED_OAUTH_CLIS:
            cli_name = MMS_MANAGED_OAUTH_CLIS[0]
        cli_name = Prompt.ask("绑定的 CLI", choices=list(MMS_MANAGED_OAUTH_CLIS), default=cli_name)
    name = Prompt.ask("显示名 / 列表展示名", default=current.get("name") or account_id).strip() or account_id
    home_dir = current.get("home_dir") or _default_account_home(account_id)
    priority = _normalize_priority(Prompt.ask("优先级（数字越大越优先）", default=str(current.get("priority", DEFAULT_PRIORITY))))
    claude_1m_mode = _normalize_claude_1m_mode(
        Prompt.ask(
            "Claude 1M 策略（auto/enable/disable）",
            choices=["auto", "enable", "disable"],
            default=current.get("claude_1m_mode", "auto"),
        )
    )
    proxy, no_proxy = _prompt_validated_proxy_fields(
        current.get("proxy", ""),
        current.get("no_proxy", ""),
        wizard=False,
    )
    timezone_name = _prompt_validated_timezone(current.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE, wizard=False)
    note = Prompt.ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = Confirm.ask("启用这个账号档案？", default=bool(current.get("enabled", True)))
    return _normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "priority": priority,
        "claude_1m_mode": claude_1m_mode,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "note": note,
        "enabled": enabled,
    })


def _prompt_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    if not sys.stdin.isatty():
        console.print(
            f"[red]{_L('当前不是交互终端，无法输入 API URL / API Key，请在终端里运行', 'Not running in an interactive terminal. Please run')} {current_command()} "
            f"{_L('或执行', 'or')} {config_command_hint()}[/red]"
        )
        sys.exit(1)
    _ensure_rich()

    default_openai = provider.get("default_openai_base_url", "")
    default_anthropic = provider.get("default_anthropic_base_url", "")
    current_openai = provider.get("openai_base_url", "") or existing_base_url
    current_anthropic = provider.get("anthropic_base_url", "") or existing_base_url
    protocols = provider.get("protocols", [])
    needs_openai = "openai_chat_completions" in protocols
    needs_anthropic = "anthropic_messages" in protocols

    base_url = ""
    openai_base_url = ""
    anthropic_base_url = ""

    if needs_openai and needs_anthropic and default_openai and default_anthropic and default_openai != default_anthropic:
        openai_base_url = Prompt.ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {_provider_label(provider)}）",
            default=current_openai or default_openai,
        ).rstrip("/")
        anthropic_base_url = Prompt.ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {_provider_label(provider)}）",
            default=current_anthropic or default_anthropic,
        ).rstrip("/")
        base_url = anthropic_base_url or openai_base_url
    elif needs_openai and not needs_anthropic:
        openai_base_url = Prompt.ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {_provider_label(provider)}）",
            default=current_openai or default_openai or existing_base_url or DEFAULT_BASE_URL,
        ).rstrip("/")
        base_url = openai_base_url
    elif needs_anthropic and not needs_openai:
        anthropic_base_url = Prompt.ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {_provider_label(provider)}）",
            default=current_anthropic or default_anthropic or existing_base_url or DEFAULT_BASE_URL,
        ).rstrip("/")
        base_url = anthropic_base_url
    else:
        base_default = existing_base_url or DEFAULT_BASE_URL
        base_url = Prompt.ask(
            f"请输入接口地址 / Base URL（请求地址，通道: {_provider_label(provider)}）",
            default=base_default,
        ).rstrip("/")
        openai_base_url = base_url if needs_openai else ""
        anthropic_base_url = base_url if needs_anthropic else ""

        key_prompt = f"{_L('请输入 API Key', 'Enter API key')}（{_L('通道', 'channel')}: {_provider_label(provider)}）"
    if allow_keep and existing_api_key:
        key_prompt = f"{_L('请输入 API Key', 'Enter API key')}（{_L('通道', 'channel')}: {_provider_label(provider)}，{_L('留空保持不变', 'leave empty to keep current value')}）"

    prompt_kwargs = {"password": True}
    if allow_keep:
        prompt_kwargs["default"] = ""
    api_key = Prompt.ask(key_prompt, **prompt_kwargs)
    if allow_keep and existing_api_key and not api_key:
        api_key = existing_api_key

    if not api_key:
        console.print(f"[red]{_L('API Key 不能为空', 'API key cannot be empty')}[/red]")
        sys.exit(1)

    return base_url, api_key, openai_base_url, anthropic_base_url


def _save_provider_credentials_with_probe(provider, base_url, api_key, openai_base_url="", anthropic_base_url=""):
    provider_ctx = dict(provider)
    provider_ctx["base_url"] = base_url
    provider_ctx["openai_base_url"] = openai_base_url
    provider_ctx["anthropic_base_url"] = anthropic_base_url
    provider_ctx["api_key"] = api_key

    console.print("\n正在测试连接...", style="dim")
    probe = _probe_models(provider_ctx)
    models = probe.get("models")
    if models is None:
        console.print("[yellow]⚠ 连接失败，但配置仍会保存。请检查地址和 Key。[/yellow]")
    else:
        console.print(f"[green]✓ 连接成功！发现 {len(models)} 个可用模型[/green]")
        # Auto-fix: if probe succeeded with a different URL, update saved URL
        working_url = probe.get("working_url")
        computed_openai = _provider_openai_base_url(provider_ctx)
        if working_url and working_url != computed_openai:
            # working_url differs from what was computed → fix the stored base_url
            fixed_base = working_url  # working_url is already the correct /v1 URL
            console.print(f"[yellow]→ 自动修正地址为 {fixed_base}[/yellow]")
            openai_base_url = fixed_base
            base_url = fixed_base

    save_provider_credentials(provider["id"], base_url, api_key, openai_base_url, anthropic_base_url)
    console.print(f"[green]✓ provider '{provider['id']}' 的凭据已保存到 {CREDENTIALS_PATH}[/green]")
    console.print("[dim]API Key 在配置显示里会以掩码形式展示，不会直接回显明文。[/dim]")
    return resolve_provider_context({"providers": [provider], "provider": {"default": provider["id"]}}, provider["id"])


def _quick_connect_gateway(cfg, preset_id=None):
    _ensure_interactive_terminal(_L("网关通道接入", "gateway channel setup"))
    template_key = _select_provider_template(preset_id=preset_id)
    template = _provider_template_payload(template_key)
    console.print(Panel(
        _L(
            "[bold]网关通道[/bold]\n\n填写接口地址（请求地址 / Base URL）和 API Key，接入兼容 OpenAI / Anthropic 的服务。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续功能和外部消费引用丢失。\n"
            "如果模型列表地址和请求地址不同，再额外填写“模型列表地址（高级）”。\n"
            "默认会启用全部 CLI；后续如需精细限制，再用 provider.edit 调整。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Gateway channel[/bold]\n\nEnter the request Base URL and API key for any OpenAI- or Anthropic-compatible service.\n"
            "The display name is for you; MMS auto-generates a stable system ID so presets and external consumers do not break.\n"
            "Only fill a separate model list URL if listing models uses a different endpoint.\n"
            "All CLIs are enabled by default; use provider.edit later if you need tighter limits.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=_L("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    providers = _provider_map(cfg)
    suggested_name = template["name"]
    try:
        name = _wizard_prompt(
            _L("显示名称 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
        suggested_id = _normalize_provider_id_input(name)
        if suggested_id == DEFAULT_PROVIDER_ID:
            suggested_id = _normalize_provider_id_input(template["id"] or name)
        provider_id = _unique_runtime_id(set(providers.keys()), suggested_id)
    except WizardBack:
        console.print(f"[yellow]{_L('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print(f"[yellow]{_L('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    console.print(f"[dim]{_L('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {provider_id}[/dim]")

    provider = _normalize_provider({
        **template,
        "id": provider_id,
        "name": name,
    })
    try:
        base_url = _wizard_prompt(
            _L("接口地址 / Base URL（请求地址）", "Request Base URL"),
            default=provider.get("default_openai_base_url") or provider.get("default_anthropic_base_url") or DEFAULT_BASE_URL,
            required=True,
        ).rstrip("/")
        api_key = _wizard_prompt(
            _L("API Key（不会回显）", "API key (hidden)"),
            password=True,
            required=True,
        )
        if Confirm.ask(_L("模型列表地址与请求地址不同？（高级）", "Use a separate model list URL? (advanced)"), default=False):
            provider["models_endpoint"] = _normalize_models_endpoint(
                Prompt.ask(
                    _L(
                        "模型列表地址（高级，仅用于独立拉取模型列表；通常留默认）",
                        "Model list URL (advanced, only used for a separate model-list endpoint)",
                    ),
                    default=provider.get("models_endpoint", "/models"),
                )
            )
        provider["proxy"], provider["no_proxy"] = _prompt_validated_proxy_fields(
            provider.get("proxy", ""),
            provider.get("no_proxy", ""),
            wizard=True,
        )
        provider["timezone"] = _prompt_validated_timezone(
            provider.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE,
            wizard=True,
        )
        provider = _normalize_provider(provider)
    except WizardBack:
        console.print(f"[yellow]{_L('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print(f"[yellow]{_L('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    updated_cfg = _upsert_provider(cfg, provider)
    save_config(updated_cfg)
    _save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        base_url if "openai_chat_completions" in provider.get("protocols", []) else "",
        base_url if "anthropic_messages" in provider.get("protocols", []) else "",
    )
    console.print(f"[green]✓ {_L('已接入网关通道', 'Gateway channel added')}: {name}[/green]")
    console.print(f"[dim]{_L('内部标识', 'System ID')}: {provider_id}[/dim]")
    return load_config(), True


def _quick_connect_official(cfg, preset_cli=None):
    _ensure_interactive_terminal(_L("官方通道接入", "official channel setup"))
    console.print(Panel(
        _L(
            "[bold]官方通道[/bold]\n\n创建一个独立登录目录；创建完成后，回主界面启动该通道时再进入官方 CLI 登录。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续引用丢失。\n"
            "适合多个 ChatGPT / Claude / Antigravity 账号并行使用。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Official channel[/bold]\n\nCreate an isolated login directory first; after setup, launch this channel from the main UI to continue the official CLI login flow.\n"
            "The display name is user-facing; MMS auto-generates the stable system ID used by config and follow-up commands.\n"
            "Use this when you want multiple ChatGPT / Claude / Antigravity accounts in parallel.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=_L("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    choices = {
        "1": ("codex", "ChatGPT / Codex"),
        "2": ("agy", "Antigravity CLI"),
    }
    if preset_cli in MMC_DELEGATED_OAUTH_CLIS:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再新增 Claude 官方账号。[/yellow]")
        return cfg, False
    if preset_cli in MMS_MANAGED_OAUTH_CLIS:
        cli_name = preset_cli
    else:
        console.print("  1. ChatGPT / Codex")
        console.print("  2. Antigravity CLI")
        try:
            selected = _wizard_prompt(_L("选择官方通道类型", "Select official channel type"), default="1")
        except WizardBack:
            console.print(f"[yellow]{_L('已返回上一层', 'Returned to previous step')}[/yellow]")
            return cfg, False
        except WizardCancel:
            console.print(f"[yellow]{_L('已退出接入', 'Setup cancelled')}[/yellow]")
            return cfg, False
        if selected not in choices:
            console.print(f"[red]{_L('请输入 1-2', 'Please enter 1-2')}[/red]")
            return cfg, False
        cli_name = choices[selected][0]

    suggested_name = f"{cli_name}-main"
    try:
        name = _wizard_prompt(
            _L("显示名 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
    except WizardBack:
        console.print(f"[yellow]{_L('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print(f"[yellow]{_L('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    accounts = _account_map(cfg)
    account_id = _unique_runtime_id(set(accounts.keys()), _normalize_account_id(name))
    console.print(f"[dim]{_L('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {account_id}[/dim]")

    home_dir = _default_account_home(account_id)
    try:
        proxy, no_proxy = _prompt_validated_proxy_fields("", "", wizard=True)
        timezone_name = _prompt_validated_timezone(DEFAULT_ACCOUNT_TIMEZONE, wizard=True)
    except WizardBack:
        console.print(f"[yellow]{_L('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print(f"[yellow]{_L('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    account = _normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "enabled": True,
        "priority": DEFAULT_PRIORITY,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
    })
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = list(cfg.get("accounts", [])) + [account]
    updated_cfg, _ = _ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ {_L('已添加官方通道', 'Official channel added')}: {name}[/green]")
    console.print(f"[dim]{_L('内部标识', 'System ID')}: {account_id}[/dim]")
    console.print(f"[dim]{_L('文件夹目录', 'Directory')}: {home_dir}[/dim]")
    console.print(
        f"[dim]{_L('已跳过立即登录；请回主界面启动这个官方通道，再完成登录。', 'Immediate login skipped; launch this official channel from the main UI when you are ready to sign in.')}[/dim]"
    )
    if Confirm.ask(_L(f"设为 {cli_name} 的默认官方通道？", f"Set as the default {cli_name} official channel?"), default=True):
        updated_cfg = load_config()
        updated_cfg.setdefault("account", {}).setdefault("defaults", {})
        updated_cfg["account"]["defaults"][cli_name] = account_id
        save_config(updated_cfg)
        console.print(f"[green]✓ {_L(f'{cli_name} 默认官方通道已更新为 {account_id}', f'Default {cli_name} official channel set to {account_id}')}[/green]")
    return load_config(), True


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
    failed = str(failed_model or "").strip().lower()
    root = os.path.expanduser(str(config_dir or CONFIG_DIR))
    paths = [
        os.path.join(root, "generated", "model-routes.json"),
        os.path.join(root, "model-routes.json"),
    ]
    candidates = []
    seen = set()

    def route_is_openai_usable(route):
        if not isinstance(route, dict):
            return False
        return bool(str(route.get("openai_base_url") or "").strip() and str(route.get("api_key") or "").strip())

    for path in paths:
        try:
            payload = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        routes = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
        for model_name, entry in routes.items():
            name = str(model_name or "").strip()
            if not name or name.lower() == failed or name.lower() in seen:
                continue
            if not isinstance(entry, dict):
                continue
            leaves = [entry.get("primary")]
            if isinstance(entry.get("fallbacks"), list):
                leaves.extend(entry.get("fallbacks") or [])
            if not any(route_is_openai_usable(route) for route in leaves):
                continue
            seen.add(name.lower())
            candidates.append(name)
        if candidates:
            break
    return candidates[: max(1, int(limit or 1))]


def _rescue_fallback_model_candidates(cfg, rescue_event, *, limit=6):
    failed_model = str((rescue_event or {}).get("failed_model") or "").strip().lower()
    rows = {}

    def add(model, *, last_used_at="", source_rank=1000):
        name = str(model or "").strip()
        if not name or name.lower() == failed_model:
            return
        key = name.lower()
        existing = rows.get(key)
        candidate = {
            "model": name,
            "last_used_at": str(last_used_at or "").strip(),
            "source_rank": int(source_rank),
        }
        if existing is None:
            rows[key] = candidate
            return
        existing_key = (str(existing.get("last_used_at") or ""), -int(existing.get("source_rank") or 0))
        candidate_key = (candidate["last_used_at"], -candidate["source_rank"])
        if candidate_key > existing_key:
            rows[key] = candidate

    stats = _load_usage_stats()
    for item in (stats.get("last_by_cli") or {}).values():
        if not isinstance(item, dict):
            continue
        add(item.get("model"), last_used_at=item.get("last_used_at"), source_rank=0)
    for source in (stats.get("sources") or {}).values():
        if not isinstance(source, dict):
            continue
        model_last_used = source.get("model_last_used_at") if isinstance(source.get("model_last_used_at"), dict) else {}
        for model_name in (source.get("models") or {}).keys():
            add(model_name, last_used_at=model_last_used.get(model_name), source_rank=10)
        add(source.get("last_model"), last_used_at=source.get("last_used_at"), source_rank=5)

    rank = 100
    for provider_def in (cfg or {}).get("providers", []) or []:
        if not isinstance(provider_def, dict) or not provider_def.get("enabled", True):
            continue
        for field in ("extra_models", "fallback_models"):
            for model_name in provider_def.get(field) or []:
                add(model_name, source_rank=rank)
                rank += 1

    for model_name in _rescue_route_fallback_model_candidates(failed_model=failed_model, limit=80):
        add(model_name, source_rank=rank)
        rank += 1

    values = list(rows.values())
    recent = sorted(
        [item for item in values if item.get("last_used_at")],
        key=lambda item: (str(item.get("last_used_at") or ""), -int(item.get("source_rank") or 0)),
        reverse=True,
    )
    cold = sorted(
        [item for item in values if not item.get("last_used_at")],
        key=lambda item: (int(item.get("source_rank") or 0), str(item.get("model") or "").lower()),
    )
    ordered = recent + cold
    return [item["model"] for item in ordered[: max(int(limit or 1), 1)]]


def _rescue_default_fallback(cfg):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    return {
        "model": str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip(),
        "cli": str(rescue_cfg.get("fallback_cli") or rescue_cfg.get("default_fallback_cli") or "").strip(),
    }


def _rescue_hot_fallback_enabled_cfg(cfg):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    return bool(_pref_bool(rescue_cfg.get("hot_fallback_enabled", rescue_cfg.get("enable_hot_fallback"))))


def _set_rescue_default_fallback(cfg, *, model="", cli=""):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    model = str(model or "").strip()
    cli = str(cli or "").strip()
    for legacy_key in ("default_fallback_model", "default_fallback_cli"):
        rescue_cfg.pop(legacy_key, None)
    if model:
        rescue_cfg["fallback_model"] = model
        if cli:
            rescue_cfg["fallback_cli"] = cli
        else:
            rescue_cfg.pop("fallback_cli", None)
    else:
        rescue_cfg.pop("fallback_model", None)
        rescue_cfg.pop("fallback_cli", None)
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
    return cfg


def _set_rescue_hot_fallback_enabled(cfg, enabled=False):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    has_model = bool(str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip())
    if not has_model:
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
        return cfg, False
    rescue_cfg.pop("enable_hot_fallback", None)
    rescue_cfg["hot_fallback_enabled"] = bool(enabled)
    return cfg, bool(enabled)


def _latest_rescue_hot_fallback_event():
    try:
        from mms_events import get_recent_events

        events = get_recent_events(limit=40)
    except Exception:
        return None
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "fallback":
            continue
        if "rescue_hot_fallback" not in str(event.get("note") or ""):
            continue
        return event
    return None


def _format_rescue_hot_fallback_event(event):
    from mms_command_tools import format_rescue_hot_fallback_event

    return format_rescue_hot_fallback_event(event)


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


def _compact_tui_report_value(value, max_len=96):
    from mms_command_tools import compact_tui_report_value

    return compact_tui_report_value(value, max_len=max_len)


_SETTINGS_RESULT_RENDERED_TUI = False


def _settings_result_tui_available():
    if str(os.environ.get("MMS_DISABLE_SETTINGS_RESULT_TUI") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _settings_result_tui_payload(title, rows, note="", *, ok=True):
    from mms_command_tools import settings_result_tui_payload

    return settings_result_tui_payload(title, rows, note, ok=ok, localize=_L)


def _select_settings_result_tui(title, rows, note="", *, ok=True):
    from mms_tui import select_channel_action_tui

    tui_title, info_lines, actions = _settings_result_tui_payload(title, rows, note, ok=ok)
    return select_channel_action_tui(tui_title, info_lines, actions)


def _print_settings_result_report(title, rows, note="", *, ok=True):
    global _SETTINGS_RESULT_RENDERED_TUI
    if _settings_result_tui_available():
        try:
            _select_settings_result_tui(title, rows, note, ok=ok)
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception:
            _SETTINGS_RESULT_RENDERED_TUI = False
        else:
            _SETTINGS_RESULT_RENDERED_TUI = True
            return

    _ensure_rich()
    from mms_command_tools import display_settings_result_report

    return display_settings_result_report(title, rows, note, ok=ok, console=console)


def _print_settings_error_report(title, exc):
    _print_settings_result_report(
        title,
        [(_L("错误", "Error"), exc)],
        _L("操作未完成；没有改变 runtime defaults。", "Operation did not complete; runtime defaults unchanged."),
        ok=False,
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
    targets = _list_manage_targets(cfg)
    if not targets:
        console.print("[yellow]当前还没有可管理的通道[/yellow]")
        return None

    if _use_tui():
        try:
            from mms_tui import select_manage_target_tui
            result = select_manage_target_tui(targets)
            if result is not None:
                return result
            return None
        except (ImportError, Exception):
            pass

    from mms_command_tools import select_manage_target_fallback

    return select_manage_target_fallback(
        targets,
        ensure_rich=_ensure_rich,
        panel_cls=Panel,
        table_cls=Table,
        prompt_cls=Prompt,
        console=console,
    )


def _update_provider_model_overrides(cfg, provider_id, *, extra_models=None, hidden_models=None, models_endpoint=None):
    updated_cfg = dict(cfg)
    providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != provider_id:
            providers.append(item)
            continue
        updated = dict(item)
        if extra_models is not None:
            updated["extra_models"] = _normalize_model_id_list(extra_models)
        if hidden_models is not None:
            updated["hidden_models"] = _normalize_model_id_list(hidden_models)
        if models_endpoint is not None:
            updated["models_endpoint"] = _normalize_models_endpoint(models_endpoint)
        providers.append(_normalize_provider(updated))
    updated_cfg["providers"] = providers
    save_config(updated_cfg)
    _invalidate_probe_cache(provider_id)
    return load_config()


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
    if _SETTINGS_RESULT_RENDERED_TUI:
        _SETTINGS_RESULT_RENDERED_TUI = False
        return

    _ensure_rich()
    try:
        console.print(f"[dim]{prompt_text}[/dim]")
    except Exception:
        pass
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def _manage_provider_models(cfg, provider_id):
    _ensure_rich()
    changed = False
    current_cfg = cfg
    while True:
        provider = resolve_provider_context(current_cfg, provider_id)
        probe = _probe_models(provider, emit_output=False)
        model_count = len(probe.get("models") or [])
        extra_count = len(provider.get("extra_models", []) or [])
        hidden_count = len(provider.get("hidden_models", []) or [])

        info_lines = [
            ("通道", provider.get("name", provider_id)),
            ("模型列表地址", provider.get("models_endpoint", "/models")),
            ("来源", _model_source_label(probe.get("base_source", "remote"))),
            ("模型数", str(model_count)),
            ("补丁", f"补充 {extra_count} / 隐藏 {hidden_count}"),
        ]
        actions = [
            ("1", "查看当前模型列表"),
            ("2", "刷新远端模型列表"),
            ("3", "添加补充模型"),
            ("4", "隐藏模型"),
            ("5", "移除补充/取消隐藏"),
            ("6", "恢复默认模型补丁"),
            ("7", "编辑模型列表接口"),
            ("8", "返回"),
        ]

        choice = None
        if _use_tui():
            try:
                from mms_tui import select_channel_action_tui
                choice = select_channel_action_tui(f"模型管理 · {provider.get('name', provider_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not _use_tui():
            _ensure_rich()
            console.print(Panel(
                "\n".join(f"[bold]{l}:[/bold]  {v}" for l, v in info_lines),
                title="模型管理", border_style="cyan",
            ))
            for aid, alabel in actions:
                console.print(f"  {aid}. {alabel}")
            choice = Prompt.ask("选择操作", choices=[a[0] for a in actions], default="8")
        if choice is None:
            return current_cfg, changed
        if choice == "1":
            if _use_tui():
                try:
                    console.clear()
                except Exception:
                    pass
            _display_provider_model_table(provider, probe)
            if _use_tui():
                _pause_after_tui_report("按 Enter 返回模型管理")
            continue
        if choice == "2":
            probe = _probe_models(provider, emit_output=True, force_refresh=True)
            console.print(f"[green]✓ 已刷新远端模型列表，共 {len(probe.get('models') or [])} 个模型[/green]")
            changed = True
            continue
        if choice == "3":
            raw = Prompt.ask("输入要补充的模型 ID（逗号分隔）", default="")
            additions = _normalize_model_id_list(raw)
            if not additions:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = _normalize_model_id_list((provider.get("extra_models") or []) + additions)
            next_hidden = [item for item in provider.get("hidden_models", []) if item not in additions]
            current_cfg = _update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已补充模型: {', '.join(additions)}[/green]")
            changed = True
            continue
        if choice == "4":
            raw = Prompt.ask("输入要隐藏的模型 ID（逗号分隔）", default="")
            hidden = _normalize_model_id_list(raw)
            if not hidden:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = [item for item in provider.get("extra_models", []) if item not in hidden]
            next_hidden = _normalize_model_id_list((provider.get("hidden_models") or []) + hidden)
            current_cfg = _update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已隐藏模型: {', '.join(hidden)}[/green]")
            changed = True
            continue
        if choice == "5":
            raw = Prompt.ask("输入要移除的模型 ID（会同时从 extra/hidden 里清理，逗号分隔）", default="")
            removals = set(_normalize_model_id_list(raw))
            if not removals:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = [item for item in provider.get("extra_models", []) if item not in removals]
            next_hidden = [item for item in provider.get("hidden_models", []) if item not in removals]
            current_cfg = _update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已移除模型补丁: {', '.join(sorted(removals))}[/green]")
            changed = True
            continue
        if choice == "6":
            current_cfg = _update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=[],
                hidden_models=[],
            )
            console.print("[green]✓ 已恢复默认模型补丁[/green]")
            changed = True
            continue
        if choice == "7":
            new_endpoint = _normalize_models_endpoint(
                Prompt.ask("模型列表接口路径（输入 manual 表示仅用手工模型）", default=provider.get("models_endpoint", "/models"))
            )
            current_cfg = _update_provider_model_overrides(
                current_cfg,
                provider_id,
                models_endpoint=new_endpoint,
            )
            console.print(f"[green]✓ 已更新模型列表接口: {new_endpoint}[/green]")
            changed = True
            continue
        return current_cfg, changed


def _select_provider_for_models(cfg):
    providers = [item for item in _list_manage_targets(cfg) if item.get("kind") == "provider"]
    if not providers:
        console.print("[yellow]当前还没有可管理的网关通道[/yellow]")
        return None

    table = Table(title="模型与测速 · 选择通道", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("显示名", style="yellow")
    table.add_column("内部标识", style="green")
    table.add_column("默认", style="magenta", width=6)
    table.add_column("状态", style="white")
    for index, provider in enumerate(providers, 1):
        table.add_row(
            str(index),
            provider.get("title", ""),
            provider.get("id", ""),
            provider.get("default_label", ""),
            provider.get("status", ""),
        )
    console.print(table)

    while True:
        raw = Prompt.ask("选择要查看的通道，直接回车返回", default="")
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(providers):
                return providers[idx - 1]["id"]
        console.print(f"[red]请输入 1-{len(providers)} 的编号[/red]")


def _select_provider_for_warm(cfg):
    return _select_provider_for_models(cfg)


def _recent_models_for_provider(provider_id):
    recent = []
    seen = set()
    for item in _usage_rows_for_runtime("provider", provider_id):
        last_model = str(item.get("last_model", "")).strip()
        if last_model and last_model not in seen:
            seen.add(last_model)
            recent.append(last_model)
        for model_name, _count in sorted((item.get("models") or {}).items(), key=lambda pair: pair[1], reverse=True):
            model_name = str(model_name or "").strip()
            if model_name and model_name not in seen:
                seen.add(model_name)
                recent.append(model_name)
    return recent


def _pick_manual_models(models):
    if not models:
        return []
    table = Table(title="选择要预热的模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    for idx, model_name in enumerate(models, 1):
        table.add_row(str(idx), model_name)
    console.print(table)
    raw = Prompt.ask("输入模型编号，支持逗号分隔；直接回车取消", default="")
    if not raw.strip():
        return []
    selected = []
    seen = set()
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value.isdigit():
            continue
        idx = int(value)
        if 1 <= idx <= len(models):
            model_name = models[idx - 1]
            if model_name not in seen:
                seen.add(model_name)
                selected.append(model_name)
    return selected


def _warm_model_request(provider, model_name):
    model_name = str(model_name or "").strip()
    if not model_name:
        return False, "empty model"
    _ensure_httpx()
    if httpx is None:
        return False, "缺少 httpx"

    protocols = provider.get("protocols", [])
    api_key = provider.get("api_key", "")
    openai_api_key = provider.get("openai_api_key") or api_key
    timeout = 30
    if not api_key and not openai_api_key:
        return False, "缺少 API Key"

    use_anthropic = "anthropic_messages" in protocols and "claude" in model_name.lower()
    try:
        if use_anthropic:
            from mms_launchers import _resolve_anthropic_base_url

            base_url, _method = _resolve_anthropic_base_url(provider, probe_model=model_name)
            if not base_url:
                return False, "无法解析 Anthropic 地址"
            response = _runtime_httpx_request(
                "POST",
                f"{base_url.rstrip('/')}/v1/messages",
                runtime=provider,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "warmup"}],
                },
                timeout=timeout,
            )
        else:
            base_url = _provider_openai_base_url(provider)
            if not base_url:
                return False, "缺少 OpenAI 地址"
            response = _runtime_httpx_request(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                runtime=provider,
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "max_tokens": 1,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=timeout,
            )
        if response.status_code >= 400:
            detail = response.text.strip().replace("\n", " ")
            if len(detail) > 120:
                detail = detail[:117] + "..."
            return False, f"HTTP {response.status_code}: {detail or 'request failed'}"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


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
    provider = resolve_provider_context(cfg, provider_id)
    while True:
        default_tag = "是" if cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID) == provider_id else "否"
        extra_count = len(provider.get("extra_models", []) or [])
        hidden_count = len(provider.get("hidden_models", []) or [])

        info_lines = [
            ("名称", provider.get("name", provider_id)),
            ("标识", provider_id),
            ("默认", default_tag),
            ("OpenAI", _provider_openai_base_url(provider) or "(未设置)"),
            ("Anthropic", _provider_anthropic_base_url(provider) or "(未设置)"),
            ("模型列表地址", provider.get("models_endpoint", "/models")),
            ("模型补丁", f"补充 {extra_count} / 隐藏 {hidden_count}"),
            ("协议", ", ".join(provider.get("protocols", []))),
            ("Proxy", provider.get("proxy", "") or "-"),
            ("Timezone", provider.get("timezone", "") or "-"),
        ]
        actions = [
            ("1", "查看本地统计"),
            ("2", "模型管理"),
            ("3", "设为默认网关"),
            ("4", "重命名"),
            ("5", "编辑地址和 Key"),
            ("6", "删除通道"),
            ("7", "返回"),
        ]

        choice = None
        if _use_tui():
            try:
                from mms_tui import select_channel_action_tui
                choice = select_channel_action_tui(f"网关 · {provider.get('name', provider_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not _use_tui():
            _ensure_rich()
            console.print(Panel(
                "\n".join(f"[bold]{l}:[/bold]  {v}" for l, v in info_lines),
                title="通道详情", border_style="cyan",
            ))
            for aid, alabel in actions:
                console.print(f"  {aid}. {alabel}")
            choice = Prompt.ask("选择操作", choices=[a[0] for a in actions], default="7")
        if choice is None:
            return cfg, False
        if choice == "1":
            _display_runtime_usage("provider", provider_id, provider.get("name", provider_id))
            continue
        if choice == "2":
            return _manage_provider_models(cfg, provider_id)
        if choice == "3":
            cfg.setdefault("provider", {})["default"] = provider_id
            save_config(cfg)
            console.print(f"[green]✓ 默认网关已切换为 {provider_id}[/green]")
            return load_config(), True
        if choice == "4":
            _ensure_rich()
            new_id = _normalize_provider_id_input(Prompt.ask("新的内部标识", default=provider_id).strip())
            new_name = Prompt.ask("新的显示名", default=provider.get("name", provider_id)).strip() or new_id
            if new_id == provider_id and new_name == provider.get("name", provider_id):
                console.print("[yellow]名称和标识都未变化，已取消重命名[/yellow]")
                return cfg, False
            _handle_provider_rename_config(cfg, [provider_id, new_id, new_name])
            return load_config(), True
        if choice == "5":
            _handle_provider_credentials_config(cfg, [provider_id])
            return load_config(), True
        if choice == "6":
            before = set(_provider_map(cfg).keys())
            _handle_provider_remove_config(cfg, [provider_id])
            after_cfg = load_config()
            return after_cfg, set(_provider_map(after_cfg).keys()) != before
        return cfg, False


def _prompt_account_rename(cfg, account_id):
    _ensure_rich()
    console.print(f"[cyan]准备重命名官方通道: {account_id}[/cyan]")
    new_id = Prompt.ask("新的文件夹名", default=account_id).strip()
    if not new_id or new_id == account_id:
        console.print("[yellow]文件夹名未变化，已取消重命名[/yellow]")
        return cfg, False
    before_ids = set(_account_map(cfg).keys())
    _handle_account_rename_config(cfg, [account_id, new_id])
    updated_cfg = load_config()
    after_ids = set(_account_map(updated_cfg).keys())
    changed = new_id in after_ids and before_ids != after_ids
    return updated_cfg, changed


def _manage_account_target(cfg, account_id):
    account = resolve_account_context(cfg, account_id=account_id)
    while True:
        login_state = _probe_account_status(account)
        default_tag = "是" if cfg.get("account", {}).get("defaults", {}).get(account.get("cli")) == account_id else "否"

        info_lines = [
            ("名称", account.get("name", account_id)),
            ("文件夹", account_id),
            ("CLI", account.get("cli", "").upper()),
            ("默认", f"{default_tag}（{account.get('cli', '').upper()}）"),
            ("登录", login_state.get("summary") or login_state.get("state", "")),
            ("Proxy", account.get("proxy", "") or "-"),
            ("Timezone", account.get("timezone", "") or "-"),
        ]
        actions = [
            ("1", "查看本地统计"),
            ("2", "重新登录"),
            ("3", "设为默认官方通道"),
            ("4", "重命名"),
            ("5", "编辑通道"),
            ("6", "删除通道"),
            ("7", "返回"),
        ]

        choice = None
        if _use_tui():
            try:
                from mms_tui import select_channel_action_tui
                choice = select_channel_action_tui(f"官方 · {account.get('name', account_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not _use_tui():
            _ensure_rich()
            console.print(Panel(
                "\n".join(f"[bold]{l}:[/bold]  {v}" for l, v in info_lines),
                title="通道详情", border_style="cyan",
            ))
            for aid, alabel in actions:
                console.print(f"  {aid}. {alabel}")
            choice = Prompt.ask("选择操作", choices=[a[0] for a in actions], default="7")
        if choice is None:
            return cfg, False
        if choice == "1":
            _display_runtime_usage("account", account_id, account.get("name", account_id))
            continue
        if choice == "2":
            _run_account_login(account)
            return load_config(), True
        if choice == "3":
            cfg.setdefault("account", {}).setdefault("defaults", {})
            cfg["account"]["defaults"][account.get("cli")] = account_id
            save_config(cfg)
            console.print(f"[green]✓ {account.get('cli')} 默认官方通道已更新为 {account_id}[/green]")
            return load_config(), True
        if choice == "4":
            return _prompt_account_rename(cfg, account_id)
        if choice == "5":
            _handle_account_edit_config(cfg, [account_id])
            return load_config(), True
        if choice == "6":
            before = set(_account_map(cfg).keys())
            _handle_account_remove_config(cfg, [account_id])
            after_cfg = load_config()
            return after_cfg, set(_account_map(after_cfg).keys()) != before
        return cfg, False


def _run_account_mgmt_tui(cfg):
    """账号管理：列表选择 + 详情操作。"""
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]当前没有配置任何 OAuth 账号[/yellow]")
        return

    account_defaults = cfg.get("account", {}).get("defaults", {})
    targets = []
    for acct in accounts:
        acct_id = str(acct.get("id", "")).strip()
        if not acct_id:
            continue
        cli_name = str(acct.get("cli", "")).strip()
        is_default = account_defaults.get(cli_name) == acct_id
        launches, last_used_at = _usage_summary_for_runtime("account", acct_id)
        targets.append({
            "kind": "account",
            "id": acct_id,
            "title": acct.get("name", acct_id),
            "summary": f"官方 · {cli_name.upper()}" + (" · 默认" if is_default else ""),
            "default_label": cli_name.upper() if is_default else "备选",
            "status": "",
            "launches": launches,
            "last_used_at": last_used_at,
        })

    if not targets:
        console.print("[yellow]当前没有可管理的账号[/yellow]")
        return

    if _use_tui():
        try:
            from mms_tui import select_manage_target_tui
            target = select_manage_target_tui(targets)
            if target:
                _manage_account_target(cfg, target["id"])
        except (ImportError, Exception):
            pass


def _run_recommend_mgmt_tui(cfg):
    """推荐模型管理：查看/添加/移除。"""
    current_list = list(cfg.get("recommend", {}).get("models", []))

    if _use_tui():
        try:
            from mms_tui import select_channel_action_tui
        except ImportError:
            return cfg

        while True:
            info_lines = []
            for i, m in enumerate(current_list):
                info_lines.append((str(i + 1), m))
            if not info_lines:
                info_lines.append(("-", "(空)"))

            actions = [
                ("add", "添加模型"),
                ("remove", "移除模型"),
                ("clear", "清空列表"),
                ("back", "返回"),
            ]
            choice = select_channel_action_tui("推荐模型", info_lines, actions)

            if choice == "add":
                _ensure_rich()
                raw = Prompt.ask("输入模型名（逗号分隔）", default="")
                additions = [m.strip() for m in raw.split(",") if m.strip()]
                if additions:
                    for m in additions:
                        if m not in current_list:
                            current_list.append(m)
                    cfg.setdefault("recommend", {})["models"] = current_list
                    save_config(cfg)
                    console.print(f"[green]已添加: {', '.join(additions)}[/green]")
            elif choice == "remove":
                if not current_list:
                    continue
                _ensure_rich()
                raw = Prompt.ask("输入要移除的模型名（逗号分隔）", default="")
                removals = [m.strip() for m in raw.split(",") if m.strip()]
                if removals:
                    current_list = [m for m in current_list if m not in removals]
                    cfg.setdefault("recommend", {})["models"] = current_list
                    save_config(cfg)
                    console.print(f"[green]已移除: {', '.join(removals)}[/green]")
            elif choice == "clear":
                current_list = []
                cfg.setdefault("recommend", {})["models"] = []
                save_config(cfg)
                console.print("[green]已清空推荐列表[/green]")
            else:
                break

    return cfg


def run_manage_channels(cfg):
    _ensure_interactive_terminal("通道管理")
    changed = False
    current_cfg = cfg
    while True:
        target = _select_manage_target(current_cfg)
        if target is None:
            return current_cfg, changed
        if target.get("kind") == "provider":
            current_cfg, did_change = _manage_provider_target(current_cfg, target["id"])
        else:
            current_cfg, did_change = _manage_account_target(current_cfg, target["id"])
        changed = changed or did_change


def run_connect_wizard(cfg):
    _ensure_interactive_terminal("新通道接入")
    action_id = None
    tui_attempted = False
    if _use_tui():
        try:
            from mms_tui import select_connect_tui
        except ImportError:
            select_connect_tui = None
        if select_connect_tui is not None:
            tui_attempted = True
            action_id = select_connect_tui()
    if action_id == "fallback":
        action_id = None
    elif action_id is None and tui_attempted:
        action_id = "cancel"
    if not action_id:
        console.print("\n[bold]接入新通道[/bold]")
        console.print("  1. 添加网关通道")
        console.print("  2. 添加官方通道")
        console.print("  3. 管理现有通道")
        console.print("  4. 迁移配置到 mms")
        console.print("  5. 返回")
        action_id = Prompt.ask("选择操作", choices=["1", "2", "3", "4", "5"], default="1")
        action_id = {
            "1": "connect_gateway",
            "2": "connect_official",
            "3": "manage_channels",
            "4": "migrate_config",
            "5": "cancel",
        }[action_id]

    if action_id == "connect_gateway":
        return _quick_connect_gateway(cfg)
    if action_id == "connect_official":
        return _quick_connect_official(cfg)
    if action_id == "manage_channels":
        return run_manage_channels(cfg)
    if action_id == "migrate_config":
        _handle_config_migrate()
        return load_config() or cfg, True
    console.print("[yellow]已取消接入[/yellow]")
    return cfg, False


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
    _ensure_httpx()
    if httpx is None:
        return None
    url = configured_url.rstrip("/")
    candidates = [url[:-3], url] if url.endswith("/v1") else [url, url + "/v1"]
    for candidate in candidates:
        try:
            if body is not None:
                resp = _runtime_httpx_request(
                    "POST",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    content=body,
                    timeout=timeout,
                )
            else:
                resp = _runtime_httpx_request(
                    "GET",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    timeout=timeout,
                )
            if resp.status_code == 200:
                return candidate
        except Exception:
            continue
    return None

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
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return _normalize_positive_seconds(
                cache_cfg.get("probe_async_refresh_after_sec", _PROBE_ASYNC_REFRESH_AFTER),
                _PROBE_ASYNC_REFRESH_AFTER,
            )
    return _PROBE_ASYNC_REFRESH_AFTER


def _probe_async_min_interval(cfg=None):
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return _normalize_positive_seconds(
                cache_cfg.get("probe_async_min_interval_sec", _PROBE_ASYNC_MIN_INTERVAL),
                _PROBE_ASYNC_MIN_INTERVAL,
            )
    return _PROBE_ASYNC_MIN_INTERVAL


def _probe_file_cache_path(provider_id):
    return os.path.join(_PROBE_FILE_CACHE_DIR, f"models_{provider_id}.json")


def _invalidate_probe_cache(provider_id):
    _PROBE_CACHE.pop(provider_id, None)
    path = _probe_file_cache_path(provider_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _probe_cache_age(provider_id):
    path = _probe_file_cache_path(provider_id)
    if not os.path.exists(path):
        return None
    try:
        import time as _time
        return max(0.0, _time.time() - os.path.getmtime(path))
    except OSError:
        return None


def _load_probe_file_cache(provider_id, allow_stale=False):
    """从文件读取 probe 缓存。

    默认仅在 TTL 内返回；allow_stale=True 时，允许读取过期缓存，
    适合启动/TUI 首屏阶段先快速展示，再由后台预热异步刷新。
    """
    path = _probe_file_cache_path(provider_id)
    try:
        import time as _time
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        raw_models = _normalize_model_id_list(data.get("raw_models") or data.get("models") or [])
        error_kind = data.get("error_kind")
        ttl = _PROBE_FILE_CACHE_NEGATIVE_TTL if error_kind or not raw_models else _PROBE_FILE_CACHE_TTL
        age = _time.time() - os.path.getmtime(path)
        is_stale = age > ttl
        if is_stale and not allow_stale:
            return None
        normalized = dict(data)
        normalized["raw_models"] = raw_models
        normalized["models"] = list(raw_models)
        normalized.setdefault("base_source", "remote")
        normalized.setdefault("error", None)
        normalized.setdefault("error_kind", None)
        normalized.setdefault("details", [])
        normalized["is_stale"] = is_stale
        return normalized
    except Exception:
        pass
    return None


def _save_probe_file_cache(provider_id, result):
    """将 probe 结果写入文件缓存。

    remote 成功结果、fallback/manual 模型结果、负缓存都应落盘，
    避免模型选择页反复慢探测。
    """
    base_source = result.get("base_source")
    if base_source not in {"remote", "fallback", "manual"}:
        return
    try:
        os.makedirs(_PROBE_FILE_CACHE_DIR, exist_ok=True)
        path = _probe_file_cache_path(provider_id)
        with open(path, "w") as f:
            json.dump(
                {
                    "raw_models": result.get("raw_models") or [],
                    "working_url": result.get("working_url"),
                    "base_source": base_source or "remote",
                    "error": result.get("error"),
                    "error_kind": result.get("error_kind"),
                },
                f,
            )
    except Exception:
        pass


def _base_probe_result_from_cache(provider_id, file_cached):
    return {
        "provider_id": provider_id,
        "raw_models": list(file_cached["raw_models"]),
        "models": list(file_cached["raw_models"]),
        "error": file_cached.get("error"),
        "error_kind": file_cached.get("error_kind"),
        "working_url": file_cached.get("working_url"),
        "details": list(file_cached.get("details") or []),
        "base_source": file_cached.get("base_source", "remote"),
        "is_stale": bool(file_cached.get("is_stale")),
    }


def _ensure_probe_async_executor():
    global _PROBE_ASYNC_EXECUTOR
    if _PROBE_ASYNC_EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor
        _PROBE_ASYNC_EXECUTOR = ThreadPoolExecutor(max_workers=4)
    return _PROBE_ASYNC_EXECUTOR


def _schedule_probe_refresh(provider, cfg=None, *, reason="stale"):
    provider_id = provider.get("id", DEFAULT_PROVIDER_ID)
    import time as _time
    min_interval = _probe_async_min_interval(cfg)

    with _PROBE_ASYNC_LOCK:
        if provider_id in _PROBE_ASYNC_INFLIGHT:
            return False
        last_at = _PROBE_ASYNC_LAST.get(provider_id, 0)
        if _time.time() - last_at < min_interval:
            return False
        _PROBE_ASYNC_INFLIGHT.add(provider_id)
        _PROBE_ASYNC_LAST[provider_id] = _time.time()

    def _runner():
        try:
            _probe_models(provider, emit_output=False, skip_cache=True)
        except Exception:
            pass
        finally:
            with _PROBE_ASYNC_LOCK:
                _PROBE_ASYNC_INFLIGHT.discard(provider_id)

    _ensure_probe_async_executor().submit(_runner)
    return True


def _probe_models_for_startup(cfg, provider, emit_output=True):
    provider_id = provider.get("id", DEFAULT_PROVIDER_ID)
    import time as _time

    cached = _PROBE_CACHE.get(provider_id)
    if cached:
        cached_at, cached_result = cached
        if _time.time() - cached_at < _PROBE_CACHE_TTL:
            return _apply_provider_model_patch(provider, cached_result)

    fresh_file_cached = _load_probe_file_cache(provider_id)
    if fresh_file_cached:
        base_result = _base_probe_result_from_cache(provider_id, fresh_file_cached)
        _PROBE_CACHE[provider_id] = (_time.time(), base_result)
        return _apply_provider_model_patch(provider, base_result)

    stale_file_cached = _load_probe_file_cache(provider_id, allow_stale=True)
    if stale_file_cached:
        base_result = _base_probe_result_from_cache(provider_id, stale_file_cached)
        _PROBE_CACHE[provider_id] = (_time.time(), base_result)
        _schedule_probe_refresh(provider, cfg, reason="startup_stale")
        if emit_output:
            console.print("[dim]已使用本地模型缓存快速启动，后台正在刷新 provider 模型列表[/dim]")
        return _apply_provider_model_patch(provider, base_result)

    return _probe_models(provider, emit_output=emit_output)


def _provider_supports_mimo_anthropic_selectors(provider):
    provider = provider if isinstance(provider, dict) else {}
    identity = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("id", "name", "label", "provider_profile")
    )
    urls = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("anthropic_base_url", "openai_base_url", "base_url")
    )
    if "openrouter" in identity or "openrouter.ai" in urls:
        return False
    anthropic_base = str(provider.get("anthropic_base_url") or "").strip().lower()
    if "xiaomimimo.com" in anthropic_base:
        return True
    base_url = str(provider.get("base_url") or "").strip().lower()
    if "xiaomimimo.com" in base_url and "/anthropic" in base_url:
        return True
    return bool(anthropic_base and any(token in identity for token in ("mimo", "xiaomi")))


def _derived_model_aliases(base_models, provider=None):
    aliases = []
    if any(model_id.startswith("claude-sonnet-4-") for model_id in base_models):
        aliases.append("claude-sonnet-4-6")
    if any(model_id.startswith("claude-opus-4-") for model_id in base_models):
        aliases.append("claude-opus-4-6")
    if _provider_supports_mimo_anthropic_selectors(provider):
        model_set = set(base_models)
        for model_id in ("mimo-v2.5-pro", "mimo-v2.5"):
            selector = f"{model_id}[1m]"
            if model_id in model_set and selector not in model_set:
                aliases.append(selector)
    return aliases


def _apply_provider_model_patch(provider, base_result):
    result = dict(base_result)
    base_models = _normalize_model_id_list(result.get("raw_models") or result.get("models") or [])
    extra_models = _normalize_model_id_list(provider.get("extra_models", []))
    derived_aliases = _derived_model_aliases(base_models, provider)
    hidden_requested = set(_normalize_model_id_list(provider.get("hidden_models", [])))
    base_source = result.get("base_source") or ("fallback" if result.get("used_fallback") else "remote")

    effective_models = []
    model_sources = {}
    for model_id in base_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = base_source
        effective_models.append(model_id)

    for model_id in extra_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "extra"
        effective_models.append(model_id)

    for model_id in derived_aliases:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "derived_alias"
        effective_models.append(model_id)

    # 过滤 claude- 前缀国产别名和旧版 Claude 模型
    _DOMESTIC_KW = ("glm", "kimi", "qwen", "minimax", "deepseek", "doubao", "seed", "bailian")
    _CLAUDE_KEEP = {
        "claude-opus-4-6", "claude-opus-4-6-thinking", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    effective_models = [
        m for m in effective_models
        if not (m.startswith("claude-") and any(kw in m.lower() for kw in _DOMESTIC_KW))
        and not (m.startswith("claude-") and m not in _CLAUDE_KEEP)
    ]

    hidden_applied = [model_id for model_id in effective_models if model_id in hidden_requested]
    if hidden_requested:
        effective_models = [model_id for model_id in effective_models if model_id not in hidden_requested]
    visible_sources = {model_id: model_sources.get(model_id, base_source) for model_id in effective_models}

    result["raw_models"] = base_models
    result["models"] = effective_models
    result["model_sources"] = visible_sources
    result["extra_models"] = extra_models + [model_id for model_id in derived_aliases if model_id not in extra_models]
    result["hidden_models"] = hidden_applied
    result["base_source"] = base_source
    return result


def _probe_models(provider, emit_output=True, force_refresh=False, skip_cache=False):
    provider_id = provider.get("id", DEFAULT_PROVIDER_ID)
    if force_refresh:
        _invalidate_probe_cache(provider_id)

    import time as _time
    if not skip_cache:
        # 1. 内存缓存命中
        cached = _PROBE_CACHE.get(provider_id)
        if cached:
            cached_at, cached_result = cached
            if _time.time() - cached_at < _PROBE_CACHE_TTL:
                patched_cached = _apply_provider_model_patch(provider, cached_result)
                if emit_output and cached_result.get("error"):
                    style = "yellow" if cached_result.get("error_kind") == "protocol_unsupported" else "red"
                    console.print(f"[{style}]{cached_result['error']}[/{style}]")
                return patched_cached

        # 2. 文件缓存命中（24h TTL）
        file_cached = _load_probe_file_cache(provider_id)
        if file_cached:
            base_result = _base_probe_result_from_cache(provider_id, file_cached)
            _PROBE_CACHE[provider_id] = (_time.time(), base_result)
            return _apply_provider_model_patch(provider, base_result)

    protocols = provider.get("protocols", [])
    base_url = _provider_openai_base_url(provider)
    api_key = provider.get("api_key", "")
    result = {
        "provider_id": provider_id,
        "models": None,
        "raw_models": None,
        "error": None,
        "error_kind": None,
        "working_url": None,
        "details": [],
        "working_url": None,
        "base_source": "remote",
    }

    _ensure_httpx()
    if "openai_chat_completions" not in protocols:
        result["error_kind"] = "protocol_unsupported"
        models_endpoint = provider.get("models_endpoint", "/models")
        result["error"] = f"provider '{provider_id}' 未声明 openai_chat_completions，无法探测 {models_endpoint}"
    elif httpx is None:
        result["error_kind"] = "missing_httpx"
        result["error"] = "缺少 httpx，请执行: pip install httpx"
    elif not base_url and not api_key:
        result["error_kind"] = "missing_credentials"
        result["error"] = "当前 provider 还没有配置 API 地址和 API Key"
    elif not base_url:
        result["error_kind"] = "missing_base_url"
        result["error"] = "当前 provider 缺少 API 地址"
    elif not api_key:
        result["error_kind"] = "missing_api_key"
        result["error"] = "当前 provider 缺少 API Key"
    else:
        # 尝试 base_url 和 alt_url（/v1 互转），以第一个能返回有效 JSON 的为准
        alt_url = base_url[:-3] if base_url.endswith("/v1") else f"{base_url}/v1"
        last_exc = None
        models_endpoint = provider.get("models_endpoint", "/models")
        if models_endpoint == "manual":
            fallback = provider.get("fallback_models") or []
            result["raw_models"] = list(fallback)
            result["models"] = list(fallback)
            result["working_url"] = base_url
            result["error"] = None
            result["error_kind"] = None
            result["base_source"] = "manual"
            if emit_output:
                console.print("[dim]已跳过远端 /models 探测，直接使用手工模型列表[/dim]")
        else:
            if not models_endpoint.startswith("/"):
                models_endpoint = "/" + models_endpoint
            for try_url in [base_url, alt_url]:
                try:
                    if "{key}" in models_endpoint:
                        endpoint_url = models_endpoint.replace("{key}", api_key)
                    elif "?" in models_endpoint:
                        endpoint_url = f"{models_endpoint}&key={api_key}"
                    else:
                        endpoint_url = models_endpoint
                    full_url = f"{try_url}{endpoint_url}"
                    headers = {}
                    if "/api/models/info" not in models_endpoint:
                        headers["Authorization"] = f"Bearer {api_key}"
                    response = _runtime_httpx_request(
                        "GET",
                        full_url,
                        runtime=provider,
                        headers=headers,
                        timeout=15,
                    )
                    response.raise_for_status()
                    data = response.json()
                    models = [m["id"] for m in data.get("data", [])]
                    models.sort()
                    result["raw_models"] = models
                    result["models"] = models
                    result["working_url"] = try_url
                    if try_url != base_url and emit_output:
                        console.print(f"[yellow]⚠ 地址 {base_url} 不通，已自动用 {try_url} 连接成功[/yellow]")
                    if not models:
                        # 模型列表为空，继续尝试 alt URL 再判断
                        continue
                    break
                except Exception as exc:
                    last_exc = exc
            if result["models"] is not None and not result["models"]:
                result["error_kind"] = "empty_models"
                result["error"] = "接口返回成功，但模型列表为空"
            elif result["models"] is None and last_exc is not None:
                # 网络请求失败，尝试 fallback 到内置模型列表
                fallback = provider.get("fallback_models")
                if fallback:
                    result["raw_models"] = list(fallback)
                    result["models"] = list(fallback)
                    result["working_url"] = base_url
                    result["error"] = None
                    result["error_kind"] = None
                    result["base_source"] = "fallback"
                    if emit_output:
                        console.print(f"[dim]该来源不支持 /models 端点，使用内置模型列表 ({len(fallback)} 个模型)[/dim]")
                else:
                    result["error_kind"] = "request_failed"
                    result["error"] = f"拉取模型列表失败: {last_exc}"

    details = [
        f"provider: {_provider_label(provider)} ({provider_id})",
        f"openai_base_url: {base_url or '(未设置)'}",
        f"protocols: {', '.join(protocols) if protocols else '(未声明)'}",
    ]
    if result["error"]:
        details.append(f"error: {result['error']}")
    result["details"] = details

    if emit_output and result["error"]:
        style = "yellow" if result["error_kind"] == "protocol_unsupported" else "red"
        console.print(f"[{style}]{result['error']}[/{style}]")

    # 写入缓存（成功或失败都缓存，避免重复请求）
    _PROBE_CACHE[provider_id] = (_time.time(), result)
    _save_probe_file_cache(provider_id, result)
    return _apply_provider_model_patch(provider, result)


def _warm_probe_cache_async(cfg, default_provider):
    """后台异步刷新 provider probe 文件缓存。

    无缓存或缓存过旧的 provider 会被刷新，但不会阻塞当前启动。
    """
    default_id = default_provider.get("id")
    refresh_after = _probe_async_refresh_after(cfg)
    for provider_def in cfg.get("providers", []):
        pid = provider_def.get("id")
        if not pid or pid == default_id:
            continue
        age = _probe_cache_age(pid)
        if age is not None and age < refresh_after:
            continue
        _schedule_probe_refresh(resolve_provider_context(cfg, pid), cfg, reason="startup_warm")


def fetch_models(provider):
    return _probe_models(provider, emit_output=True).get("models")


def _model_validation_findings(provider, probe):
    from mms_command_tools import model_validation_findings

    return model_validation_findings(provider, probe, provider_label=_provider_label)


def _rank_recovery_actions(actions):
    from mms_command_tools import rank_recovery_actions

    return rank_recovery_actions(actions)


def _build_model_recovery_actions(cfg, provider, probe):
    from mms_command_tools import build_model_recovery_actions

    return build_model_recovery_actions(cfg, provider, probe, provider_map=_provider_map)


def _print_model_probe_details(probe):
    from mms_command_tools import display_model_probe_details

    return display_model_probe_details(probe, panel_cls=Panel, console=console)


def _select_provider_interactive(cfg, current_provider_id):
    providers = [
        provider for provider in cfg.get("providers", [])
        if provider.get("enabled", True) and provider.get("id") != current_provider_id
    ]
    if not providers:
        console.print("[yellow]没有可切换的其他 provider[/yellow]")
        return None

    table = Table(title="可切换的 Providers")
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("协议", style="magenta")
    for index, item in enumerate(providers, 1):
        table.add_row(
            str(index),
            item.get("id", ""),
            item.get("name", ""),
            ", ".join(item.get("protocols", [])),
        )
    console.print(table)

    while True:
        choice = Prompt.ask("切换到哪个 provider？输入编号，留空取消", default="")
        if not choice:
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(providers):
                return resolve_provider_context(cfg, providers[idx - 1]["id"])
        console.print(f"[red]请输入 1-{len(providers)} 的编号，或直接回车取消[/red]")


def _pick_recovery_actions(findings, actions):
    if _use_tui():
        try:
            from mms_tui import select_actions_tui
        except ImportError:
            select_actions_tui = None
        if select_actions_tui is not None:
            selected = select_actions_tui(findings, actions, title="处理发现")
            if selected != "fallback":
                return selected

    console.print(Panel(
        "\n".join(f"- {item['title']}: {item['summary']}" for item in findings),
        title="发现",
        border_style="yellow",
    ))
    console.print("[bold]可处理动作：[/bold]")
    for index, action in enumerate(actions, 1):
        tag = " [推荐]" if action.get("recommended") else ""
        console.print(f"  {index}. {action['title']}{tag} — {action['summary']}")
    console.print("[dim]输入编号，支持逗号分隔多选；直接回车等于取消。[/dim]")

    while True:
        raw = Prompt.ask("选择动作", default="")
        if not raw:
            return []
        try:
            indexes = []
            for chunk in raw.split(","):
                value = int(chunk.strip())
                if not 1 <= value <= len(actions):
                    raise ValueError
                if value not in indexes:
                    indexes.append(value)
            return [actions[index - 1]["id"] for index in indexes]
        except ValueError:
            console.print(f"[red]请输入 1-{len(actions)} 的编号，可用逗号分隔多选[/red]")


def _run_recovery_action(cfg, provider, probe, action_id):
    if action_id == "show_details":
        _print_model_probe_details(probe)
        return provider, False
    if action_id == "edit_credentials":
        return setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        ), False
    if action_id == "switch_provider":
        selected = _select_provider_interactive(cfg, provider.get("id"))
        return (selected or provider), False
    if action_id == "continue_without_validation":
        console.print("[yellow]已跳过模型校验。模型浏览将暂时不可用，但预设和直接 CLI 启动仍可继续。[/yellow]")
        return provider, True
    return provider, False


def setup_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    base_url, api_key, openai_base_url, anthropic_base_url = _prompt_provider_credentials(
        provider, existing_base_url, existing_api_key, allow_keep
    )
    return _save_provider_credentials_with_probe(
        provider, base_url, api_key, openai_base_url, anthropic_base_url
    )


def setup_api_credentials(existing_base_url="", existing_api_key="", allow_keep=False):
    provider = _default_provider()
    provider_ctx = setup_provider_credentials(provider, existing_base_url, existing_api_key, allow_keep)
    return provider_ctx["base_url"], provider_ctx["api_key"]


def ensure_provider_credentials(cfg, provider_id=None):
    provider = get_provider_definition(cfg, provider_id)
    credentials = load_provider_credentials(provider["id"])
    if (credentials["base_url"] or credentials["openai_base_url"] or credentials["anthropic_base_url"]) and credentials["api_key"]:
        return resolve_provider_context(cfg, provider["id"])
    existing_base = credentials["base_url"] or credentials["openai_base_url"] or credentials["anthropic_base_url"]
    return setup_provider_credentials(
        provider,
        existing_base,
        credentials["api_key"],
        allow_keep=bool(credentials["api_key"]),
    )


def ensure_api_credentials():
    provider_ctx = ensure_provider_credentials(_default_config())
    return provider_ctx["base_url"], provider_ctx["api_key"]


def setup_wizard(ui_language=None):
    ui_language = normalize_language(ui_language) or "zh"
    set_language(ui_language)
    title = display_title()
    console.print(Panel(
        f"[bold cyan]{_L(f'欢迎使用 {title} — AI Coding CLI 统一启动器', f'Welcome to {title} — unified AI coding CLI launcher')}[/bold cyan]\n\n"
        f"{_L(f'{title} 帮你一键启动 AI 编程助手', f'{title} helps you launch AI coding assistants from one entrypoint')}\n"
        f"{_L('首次使用，需要配置 API 地址和认证信息', 'First-time setup needs an API endpoint and credentials')}",
        title=f"{title} Setup",
    ))

    cfg = _default_config()
    cfg.setdefault("ui", {})["language"] = ui_language
    setup_provider_credentials(get_provider_definition(cfg))

    role = Prompt.ask(_L("模型模式", "Model mode"), choices=[MODE_ALL, MODE_RECOMMENDED], default=MODE_ALL)
    cfg = _default_config(role)
    cfg.setdefault("ui", {})["language"] = ui_language
    save_config(cfg)
    console.print(f"\n[green]✓ {_L('配置已保存到', 'Config saved to')} {CONFIG_PATH}[/green]\n")
    return cfg


# ── Model Fetching ──────────────────────────────────────

def ensure_models_ready(cfg, provider):
    probe = _probe_models_for_startup(cfg, provider, emit_output=True)
    models = probe.get("models")
    if models:
        return provider, models

    if not sys.stdin.isatty():
        console.print(f"[red]模型校验失败，请执行 {config_command_hint()} 后重试[/red]")
        sys.exit(1)

    while True:
        findings = _model_validation_findings(provider, probe)
        actions = _build_model_recovery_actions(cfg, provider, probe)
        selected_ids = _pick_recovery_actions(findings, actions)
        if not selected_ids:
            sys.exit(1)
        ordered_actions = [item for item in actions if item["id"] in selected_ids]
        for action in ordered_actions:
            provider, skip_validation = _run_recovery_action(cfg, provider, probe, action["id"])
            if skip_validation:
                return provider, []
            # recovery 后清除缓存，强制重新探测
            _PROBE_CACHE.pop(provider.get("id", DEFAULT_PROVIDER_ID), None)
            try:
                os.remove(_probe_file_cache_path(provider.get("id", DEFAULT_PROVIDER_ID)))
            except OSError:
                pass
            probe = _probe_models(provider, emit_output=True)
            models = probe.get("models")
            if models:
                return provider, models


def categorize_models(models):
    categorized = {}
    for m in _filter_visible_models(models):
        _, category = _infer_model_family(m)
        categorized.setdefault(category, []).append(m)
    return categorized


def display_models(models, role=MODE_ALL, recommend=None):
    _ensure_rich()
    categorized = categorize_models(models)
    table = Table(title="可用模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    table.add_column("分类", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")

    flat = []
    for cat, cat_models in categorized.items():
        for m in cat_models:
            flat.append((m, cat))

    if normalize_user_role(role) == MODE_RECOMMENDED and recommend:
        flat = [(m, c) for m, c in flat if m in recommend]

    for i, (m, c) in enumerate(flat, 1):
        tag = " ⭐" if recommend and m in recommend else ""
        table.add_row(
            str(i),
            m + tag,
            c,
            _model_capability_summary(m),
            _model_cli_summary(m),
        )

    console.print(table)
    return [m for m, _ in flat]


def _filter_models_for_display(models, role=MODE_ALL, recommend=None):
    categorized = categorize_models(models)
    flat = []
    for cat, cat_models in categorized.items():
        for model_name in cat_models:
            flat.append((model_name, cat))
    if normalize_user_role(role) == MODE_RECOMMENDED and recommend:
        allowed = set(recommend)
        flat = [(model_name, cat) for model_name, cat in flat if model_name in allowed]
    return flat


def _group_models_for_custom(models, role=MODE_ALL, recommend=None):
    grouped = {}
    order = []
    for model_name, _ in _filter_models_for_display(models, role, recommend):
        family, _ = _infer_model_family(model_name)
        if family not in grouped:
            grouped[family] = []
            order.append(family)
        grouped[family].append(model_name)
    return [(family, grouped[family]) for family in order]


def _group_models_by_family_and_provider(aggregated_models, role=MODE_ALL, recommend=None):
    """将聚合模型按 family → provider → models 分组。

    Args:
        aggregated_models: _aggregate_provider_models 返回的 List[dict]
        role: 角色过滤
        recommend: 推荐模型列表

    Returns:
        List[Tuple[str, Dict[str, List[str]]]]:
        [(family_name, {provider_label: [model_names]}), ...]
    """
    plain_models = [entry["model"] for entry in aggregated_models]
    allowed = set()
    for model_name, _ in _filter_models_for_display(plain_models, role, recommend):
        allowed.add(model_name)

    family_order = []
    family_providers = {}
    for entry in aggregated_models:
        model_name = entry["model"]
        if model_name not in allowed:
            continue
        family, _ = _infer_model_family(model_name)
        provider_label = entry["provider_name"]
        provider_id = entry["provider_id"]
        key = f"{provider_label}||{provider_id}"

        if family not in family_providers:
            family_providers[family] = {}
            family_order.append(family)
        providers = family_providers[family]
        if key not in providers:
            providers[key] = []
        if model_name not in providers[key]:
            providers[key].append(model_name)

    result = []
    for family in family_order:
        provider_map = {}
        for key, models in family_providers[family].items():
            provider_map[key] = models
        result.append((family, provider_map))
    return result


def _select_custom_model(models, cli_name, role=MODE_ALL, recommend=None, use_tui=False, cfg=None, default_provider=None, default_models=None):
    """三步选择：Family → Provider（多源时）→ Model。

    Args:
        models: 可以是 List[str]（旧模式）或 List[dict]（聚合模式，含 model/provider_id/provider_name）
        cfg/default_provider/default_models: 聚合模式下可选，用于构建聚合数据

    Returns:
        聚合模式: (model_name, provider_id) 或 (None, None)
        旧模式（List[str]）: model_name 或 None（兼容）
    """
    is_aggregated = models and isinstance(models[0], dict)

    if is_aggregated:
        groups = _group_models_by_family_and_provider(models, role, recommend)
    else:
        plain_groups = _group_models_for_custom(models, role, recommend)
        groups = [(family, {"_default_||_default_": items}) for family, items in plain_groups]

    if not groups:
        return (None, None) if is_aggregated else None

    # --- Step 1: 选 Family ---
    if len(groups) == 1:
        selected_family, provider_map = groups[0]
    else:
        total_per_family = []
        for family, pmap in groups:
            count = sum(len(m) for m in pmap.values())
            total_per_family.append(count)
        family_labels = [f"{family} ({total_per_family[i]})" for i, (family, _) in enumerate(groups)]
        if use_tui:
            from mms_tui import select_model_tui
            selected_label = select_model_tui(family_labels, title=f"为 {cli_name} 选择模型品牌")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            family_index = family_labels.index(selected_label)
        else:
            family_index = None
            while family_index is None:
                table = Table(title=f"{cli_name} · 选择模型品牌", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("品牌", style="green")
                table.add_column("数量", style="yellow", width=6)
                for idx, (family, _) in enumerate(groups, 1):
                    table.add_row(str(idx), family, str(total_per_family[idx - 1]))
                console.print(table)
                try:
                    picked = IntPrompt.ask("选择模型品牌编号") - 1
                except KeyboardInterrupt:
                    sys.exit(0)
                if 0 <= picked < len(groups):
                    family_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(groups)}[/red]")
        selected_family, provider_map = groups[family_index]

    # --- Step 2: 选 Provider（多源时）---
    provider_keys = list(provider_map.keys())
    if len(provider_keys) == 1:
        selected_provider_key = provider_keys[0]
    else:
        provider_labels = []
        for key in provider_keys:
            label, _ = key.split("||", 1)
            count = len(provider_map[key])
            provider_labels.append(f"{label} ({count})")
        if use_tui:
            from mms_tui import select_model_tui
            selected_label = select_model_tui(provider_labels, title=f"{selected_family} · 选择 Provider")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            provider_index = provider_labels.index(selected_label)
        else:
            provider_index = None
            while provider_index is None:
                table = Table(title=f"{cli_name} · {selected_family} · 选择 Provider", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Provider", style="green")
                table.add_column("模型数", style="yellow", width=6)
                for idx, plabel in enumerate(provider_labels, 1):
                    table.add_row(str(idx), plabel, "")
                console.print(table)
                try:
                    picked = IntPrompt.ask("选择 Provider 编号") - 1
                except KeyboardInterrupt:
                    sys.exit(0)
                if 0 <= picked < len(provider_keys):
                    provider_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(provider_keys)}[/red]")
        selected_provider_key = provider_keys[provider_index]

    family_models = provider_map[selected_provider_key]
    _, selected_provider_id = selected_provider_key.split("||", 1)

    # --- Step 3: 选 Model ---
    if use_tui:
        from mms_tui import select_model_tui
        model = select_model_tui(family_models, title=f"{selected_family} · 选择子模型")
    else:
        model = None
        while model is None:
            table = Table(title=f"{cli_name} · {selected_family}", show_lines=True)
            table.add_column("#", style="cyan", width=4)
            table.add_column("模型", style="green")
            for idx, model_name in enumerate(family_models, 1):
                table.add_row(str(idx), model_name)
            console.print(table)
            try:
                model_index = IntPrompt.ask("选择子模型编号") - 1
            except KeyboardInterrupt:
                sys.exit(0)
            if 0 <= model_index < len(family_models):
                model = family_models[model_index]
            else:
                console.print(f"[red]请输入 1-{len(family_models)}[/red]")

    if is_aggregated:
        pid = selected_provider_id if selected_provider_id != "_default_" else None
        return (model, pid) if model else (None, None)
    return model


def _ensure_models_cache_available(models_cache):
    if models_cache:
        return True
    console.print("[yellow]当前没有可用的模型列表。请先修复 provider 校验，或先使用预设 / 直接 CLI 启动。[/yellow]")
    return False


def _model_matches_cli_family(cli_name, model_name):
    hints = CLI_MODEL_FAMILY_HINTS.get(cli_name, ())
    normalized = str(model_name or "").lower()
    return any(hint in normalized for hint in hints)


def _models_for_cli_family(cli_name, models):
    if cli_name not in CLI_MODEL_FAMILY_HINTS:
        return list(models or [])
    return [model_name for model_name in (models or []) if _model_matches_cli_family(cli_name, model_name)]


def _model_matches_account_cli(cli_name, model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    if cli_name == "claude":
        return normalized.startswith("claude-")
    if cli_name == "codex":
        return normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))
    if cli_name == "gemini":
        return normalized.startswith("gemini-")
    return False


def _provider_supports_cli_name(provider, cli_name):
    provider_id = str(provider.get("id", "")).strip().lower()
    if cli_name == "agy":
        return False
    # Kimi coding endpoints currently work on Claude-compatible paths, but not in Codex runtime.
    if cli_name == "codex" and provider_id.startswith("kimi"):
        return False
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    if cli_name == "opencode" and "opencode" not in supported_clis:
        protocols = provider.get("protocols", [])
        if isinstance(protocols, str):
            protocols = [protocols]
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    return cli_name in supported_clis


def _provider_supports_model_for_cli(provider, cli_name, model_name=None):
    normalized_model = str(model_name or "").strip()
    if cli_name == "claude" and normalized_model:
        if _model_matches_account_cli("claude", normalized_model):
            return _provider_supports_cli_name(provider, "claude")
        bridge_clis = _bridge_clis_for_model(normalized_model)
        return cli_name in bridge_clis and _provider_supports_cli_name(provider, cli_name)

    if _provider_supports_cli_name(provider, cli_name):
        return True
    if not normalized_model:
        return False
    return False


def _provider_candidates(cfg, default_provider, default_models):
    candidates = [(default_provider, list(default_models or []))]
    seen_ids = {default_provider.get("id")}
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id in seen_ids:
            continue
        # 首屏/启动阶段允许使用 stale 文件缓存，避免单个慢 provider 卡住 TUI。
        file_cached = _load_probe_file_cache(provider_id, allow_stale=True)
        cached_models = None
        if file_cached is not None and not file_cached.get("is_stale"):
            cached_models = list((file_cached or {}).get("raw_models") or [])
        candidates.append((resolve_provider_context(cfg, provider_id), cached_models))
        seen_ids.add(provider_id)
    return candidates


def _provider_models_for_cli(cli_name, models):
    if cli_name in CLI_MODEL_FAMILY_HINTS:
        return _models_for_cli_family(cli_name, models)
    return list(models or [])


def _provider_effective_models(provider, cached_models, cfg=None):
    if cached_models is None:
        if provider.get("models_endpoint") == "manual":
            base_models = list(provider.get("fallback_models") or [])
            base_source = "manual"
        else:
            _schedule_probe_refresh(provider, cfg, reason="cache_miss")
            # Cold-cache startup must not hide user-configured model families while
            # the remote /models probe refreshes in the background.
            base_models = list(provider.get("fallback_models") or [])
            base_source = "fallback" if base_models else "remote"
    else:
        base_models = list(cached_models or [])
        base_source = "remote"

    patched = _apply_provider_model_patch(
        provider,
        {"raw_models": base_models, "models": base_models, "base_source": base_source},
    )
    return list(patched.get("models") or [])


def _all_provider_models_for_cli(cfg, cli_name, default_provider, default_models):
    merged = []
    seen = set()
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not _provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = _provider_effective_models(provider, cached_models, cfg)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or normalized in seen:
                continue
            if not _mms_model_visible(normalized):
                continue
            if not _provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _aggregate_provider_models(cfg, cli_name, default_provider, default_models):
    """聚合所有 provider 的模型，保留来源信息（不去重）。

    Returns:
        List[dict]: [{"model": str, "provider_id": str, "provider_name": str}, ...]
    """
    aggregated = []
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not _provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = _provider_effective_models(provider, cached_models, cfg)
        pid = provider.get("id", DEFAULT_PROVIDER_ID)
        pname = _provider_label(provider)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not _mms_model_visible(normalized):
                continue
            if not _provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            aggregated.append({
                "model": normalized,
                "provider_id": pid,
                "provider_name": pname,
            })
    return aggregated


def _resolve_best_provider(cfg, model_name, default_provider, default_models,
                           cli_name=None, protocol=None):
    """给定模型名，返回最优 (provider_ctx, provider_name) — primary > auto > fallback × priority 高到低。

    如果指定了 protocol（如 "anthropic_messages"），只考虑支持该协议的 provider。
    如果指定了 cli_name，只考虑支持该 CLI 的 provider。
    返回 None 表示没有可用 provider。
    """
    model_lower = str(model_name or "").strip().lower()
    if not model_lower:
        return None, None

    scored = []  # [(role_weight, -priority, provider_ctx, provider_name)]
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if cli_name and not _provider_supports_model_for_cli(provider, cli_name, model_name):
            continue
        if not _provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue
        if protocol:
            protocols = provider.get("protocols", [])
            if protocol not in protocols:
                continue

        models = _provider_effective_models(provider, cached_models, cfg)

        # Check if this provider has the model
        model_names_lower = [str(m or "").strip().lower() for m in models]
        if model_lower not in model_names_lower:
            continue

        role = _normalize_role(provider.get("role", "auto"))
        priority = _runtime_priority_for_model(provider, model_name)
        pname = _provider_label(provider)
        scored.append((ROLE_WEIGHTS.get(role, 1), -priority, provider, pname))

    if not scored:
        return None, None

    scored.sort(key=lambda x: (x[0], x[1]))
    return _runtime_with_priority(scored[0][2], model_name=model_name), scored[0][3]



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


def _resolve_provider_runtime(cfg, cli_name, default_provider, default_models, provider_id=None):
    from mms_command_tools import resolve_provider_runtime

    return resolve_provider_runtime(
        cfg, cli_name, default_provider, default_models, provider_id=provider_id,
        resolve_provider_context=resolve_provider_context, resolve_provider_for_cli=_resolve_provider_for_cli,
        probe_models=_probe_models,
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
    def _with_preferences(runtime, launch_cli):
        return _runtime_with_launch_preferences(cfg, runtime, launch_cli)

    if account_id or provider_id or cli_name not in MMS_MANAGED_OAUTH_CLIS:
        runtime, models = _resolve_launch_runtime(
            cfg, cli_name, default_provider, default_models, account_id=account_id, provider_id=provider_id
        )
        choice = "single runtime path"
        if provider_id:
            choice = "provider override"
        elif account_id:
            choice = "account override"
        runtime = _with_preferences(runtime, cli_name)
        _trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice=choice)
        return runtime, models, cli_name

    options, default_choice = _list_runtime_sources(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_info=model_info,
        allow_selected_model_accounts=allow_selected_model_accounts,
    )

    if not options:
        return None, [], cli_name
    if len(options) == 1:
        chosen = options[0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = _with_preferences(chosen["runtime"], launch_cli)
        _trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="single option")
        return runtime, chosen["models"], launch_cli

    if not sys.stdin.isatty():
        chosen = options[default_choice or 0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = _with_preferences(chosen["runtime"], launch_cli)
        _trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="default(no-tty)")
        return runtime, chosen["models"], launch_cli

    _ensure_rich()
    table = Table(title=f"{cli_name} 使用入口", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("来源", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("调用", style="cyan")
    table.add_column("说明", style="magenta")
    for idx, option in enumerate(options, 1):
        runtime = option["runtime"]
        source_type = _runtime_source_kind_label(runtime)
        desc = option.get("desc", "")
        if idx - 1 == default_choice:
            desc = f"{desc} / 默认"
        table.add_row(
            str(idx),
            source_type,
            runtime.get("name", runtime.get("id", "")),
            option.get("launch_cli", cli_name),
            desc,
        )
    console.print(table)

    default_num = str((default_choice or 0) + 1)
    while True:
        raw = Prompt.ask(f"为 {cli_name} 选择这次使用的入口", default=default_num)
        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(options):
                chosen = options[selected - 1]
                launch_cli = chosen.get("launch_cli", cli_name)
                runtime = _with_preferences(chosen["runtime"], launch_cli)
                _trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice=chosen.get("title"))
                return runtime, chosen["models"], launch_cli
        console.print(f"[red]请输入 1-{len(options)} 的编号[/red]")


def _resolve_visible_clis(cfg, default_provider, default_models):
    visible = []

    for cli_name in CLI_NAMES:
        if cli_name in MMS_MANAGED_OAUTH_CLIS:
            if _accounts_for_cli(cfg, cli_name):
                visible.append(cli_name)
                continue
            # Antigravity is an official OAuth-native CLI: show the tab when
            # the binary exists so users can enter the TUI connect flow first.
            if cli_name == "agy":
                try:
                    if check_cli_installed(cli_name):
                        visible.append(cli_name)
                        continue
                except Exception:
                    pass
        provider, family_models = _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)
        if provider is None:
            continue
        if cli_name in CLI_MODEL_FAMILY_HINTS and not family_models:
            continue
        visible.append(cli_name)

    return visible


def _clean_model_info(model_info):
    if not isinstance(model_info, dict):
        return model_info
    return {k: v for k, v in model_info.items() if k != "provider"}


def select_model_interactive(models_list):
    while True:
        try:
            choice = IntPrompt.ask("选择模型编号")
            if 1 <= choice <= len(models_list):
                return models_list[choice - 1]
            console.print(f"[red]请输入 1-{len(models_list)}[/red]")
        except KeyboardInterrupt:
            sys.exit(0)



# ── Confirmation ────────────────────────────────────────

def _mask_identity_value(value, *, keep=4):
    from mms_confirm_preview import mask_identity_value

    return mask_identity_value(value, keep=keep)


def _mask_email_value(value):
    from mms_confirm_preview import mask_email_value

    return mask_email_value(value)


def _runtime_network_summary_for_confirm(runtime):
    from mms_confirm_preview import runtime_network_summary_for_confirm

    return runtime_network_summary_for_confirm(
        runtime,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
        runtime_force_ipv4=_runtime_force_ipv4,
        snapshot_proxy_fingerprint=_snapshot_proxy_fingerprint,
    )


def _load_runtime_identity_preview(runtime):
    from mms_confirm_preview import load_runtime_identity_preview

    return load_runtime_identity_preview(runtime)


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
    opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
    return _opencode_profile_selection(opencode.get("default_profile") or opencode.get("profile"))


def _opencode_default_model_rank(model_name):
    return _opencode_default_model_rank_impl(
        model_name,
        default_model_preferences=_OPENCODE_DEFAULT_MODEL_PREFERENCES,
        infer_model_family=_infer_model_family,
    )


def _opencode_normalized_openai_base_url(provider):
    return _opencode_normalized_openai_base_url_impl(
        provider,
        provider_openai_base_url=_provider_openai_base_url,
    )


def _opencode_normalized_anthropic_base_url(provider):
    return _opencode_normalized_anthropic_base_url_impl(
        provider,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
    )


def _opencode_is_mimo_direct_route(provider, model_name=""):
    return _opencode_is_mimo_direct_route_impl(
        provider,
        model_name,
        provider_label=_provider_label,
    )


def _opencode_route_transport(provider, model_name):
    return _opencode_route_transport_impl(
        provider,
        model_name,
        infer_model_family=_infer_model_family,
        provider_openai_base_url=_provider_openai_base_url,
        provider_anthropic_base_url=_provider_anthropic_base_url,
        provider_label=_provider_label,
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


def _opencode_route_candidate_score(provider, model_name, sequence):
    return _opencode_route_candidate_score_impl(
        provider,
        model_name,
        sequence,
        normalize_role=_normalize_role,
        runtime_priority_for_model=_runtime_priority_for_model,
        provider_label=_provider_label,
        role_weights=ROLE_WEIGHTS,
        default_priority=DEFAULT_PRIORITY,
    )


def _opencode_provider_matches_route_policy(provider, route_policy):
    return _opencode_provider_matches_route_policy_impl(
        provider,
        route_policy,
        provider_label=_provider_label,
    )


def _opencode_route_health_allows_route(row, *, now=None):
    return _opencode_route_health_allows_route_impl(row, now=now, is_fresh=_opencode_route_health_is_fresh)


def _opencode_resolver_deps():
    return _OpenCodeResolverDeps(
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
    return _find_opencode_model_route_impl(
        cfg,
        default_provider,
        default_models,
        model_names,
        deps=_opencode_resolver_deps(),
        route_key=route_key,
        route_policy=route_policy,
        profile_id=profile_id,
        provider_id=provider_id,
    )


def _resolve_opencode_lite_pro_runtime(cfg, default_provider, default_models, profile_id=_OPENCODE_AGENT_PROFILE_ID):
    return _resolve_opencode_lite_pro_runtime_impl(
        cfg,
        default_provider,
        default_models,
        profile_id=profile_id,
        deps=_opencode_resolver_deps(),
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
    if not isinstance(runtime, dict):
        return runtime
    profile_id = runtime.get("opencode_profile")
    if not profile_id:
        profile_id = _select_opencode_profile(use_tui=use_tui)
    if not profile_id:
        return None
    return _apply_opencode_profile(runtime, profile_id)


def save_preset_interactive(cfg, cli, model_info):
    name = Prompt.ask("预设名称")
    description = Prompt.ask("预设描述（可留空）", default="").strip()
    preset = {"cli": cli}
    if isinstance(model_info, dict):
        preset.update(model_info)
    else:
        preset["model"] = model_info
    if "presets" not in cfg:
        cfg["presets"] = {}
    if description:
        preset["description"] = description
    cfg["presets"][name] = _normalize_preset_entry(name, preset)
    save_config(cfg)
    console.print(f"[green]✓ 预设 '{name}' 已保存[/green]")


def _uses_native_account_entry(runtime, cli):
    return bool(runtime and runtime.get("auth_mode") == "oauth" and cli in OAUTH_CAPABLE_CLIS)


def _uses_broker_entry(runtime, cli):
    return bool(runtime and runtime.get("runtime_kind") == "broker" and cli == "claude")


def _uses_managed_entry(runtime, cli):
    return _uses_native_account_entry(runtime, cli)


def _resolve_interactive_launch_model(cli, runtime, cli_models, models_cache, role, recommend):
    if _uses_native_account_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用账号档案登录，直接进入官方 CLI；模型选择交由官方 CLI 处理。[/cyan]")
        return True, None

    if _uses_broker_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用 broker profile；先选模型，然后直接进入 remote official Claude Code。[/cyan]")
        available_models = cli_models or models_cache
        if not _ensure_models_cache_available(available_models):
            return False, None
        models_list = display_models(available_models, role, recommend)
        return True, select_model_interactive(models_list)

    available_models = cli_models or models_cache
    if not _ensure_models_cache_available(available_models):
        return False, None
    models_list = display_models(available_models, role, recommend)
    return True, select_model_interactive(models_list)


def _preset_model_info(preset):
    if not isinstance(preset, dict):
        return {}
    return {
        key: value for key, value in preset.items()
        if key not in {"cli", "provider", "account", "description", "bridge"}
    }


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
    # 止血：TUI 暂时不再暴露 broker profile。
    return []


def _broker_enabled_by_cli(cfg, cli_names):
    return {
        cli_name: bool(_available_broker_profiles_for_cli(cfg, cli_name))
        for cli_name in (cli_names or [])
    }


def _select_broker_profile_interactive(cfg, cli_name):
    profiles = _available_broker_profiles_for_cli(cfg, cli_name)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    _ensure_rich()
    table = Table(title="Broker Experiment", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("设备/工作区", style="yellow")
    table.add_column("Broker", style="blue")
    table.add_column("Remote", style="magenta")
    for idx, profile in enumerate(profiles, 1):
        table.add_row(
            str(idx),
            str(profile.get("id", "")),
            f"{profile.get('device_id', '-')}/{profile.get('workspace_id', '-')}",
            str(profile.get("broker_base_url") or "-"),
            str(profile.get("remote_service_label") or profile.get("remote_service_base_url") or "-"),
        )
    console.print(table)

    while True:
        raw = Prompt.ask("选择 broker profile，直接回车取消", default="").strip()
        if not raw:
            return None
        if raw.isdigit():
            picked = int(raw)
            if 1 <= picked <= len(profiles):
                return profiles[picked - 1]
        console.print("[yellow]请输入有效编号[/yellow]")


def _launch_broker_experiment_interactive(cfg, cli_name):
    profile = _select_broker_profile_interactive(cfg, cli_name)
    if profile is None:
        return False

    console.print(
        f"[cyan]Broker experiment[/cyan] -> {profile['name']} "
        f"[dim]({profile['device_id']}/{profile['workspace_id']})[/dim]"
    )
    console.print("[dim]支持续最近 / 新开 / 切换旧会话；默认直接回车续最近。[/dim]")
    exit_code = run_broker_profile_interactive(cfg, profile["id"])
    if exit_code != 0:
        console.print(f"[red]broker experiment 启动失败，退出码 {exit_code}[/red]")
    return True


# ── CLI Selection (fallback) ───────────────────────────

def check_cli_installed(cli_name):
    from mms_runtime import resolve_cli_binary
    return bool(resolve_cli_binary(cli_name))


def select_cli(cli_names=None):
    from mms_installer import check_and_offer_install
    cli_names = cli_names or CLI_NAMES
    if not cli_names:
        console.print("[red]当前没有可用的 CLI。请先检查 provider 配置和模型探测结果。[/red]")
        sys.exit(1)
    table = Table(title="选择 CLI")
    table.add_column("#", style="cyan", width=4)
    table.add_column("CLI", style="green")
    table.add_column("状态", style="yellow")

    for i, name in enumerate(cli_names, 1):
        status = "[green]已安装[/green]" if check_cli_installed(name) else "[red]未安装[/red]"
        table.add_row(str(i), name, status)

    console.print(table)

    while True:
        try:
            choice = IntPrompt.ask("选择 CLI 编号")
            if 1 <= choice <= len(cli_names):
                cli = cli_names[choice - 1]
                if not check_cli_installed(cli):
                    check_and_offer_install(cli)
                return cli
            console.print(f"[red]请输入 1-{len(cli_names)}[/red]")
        except KeyboardInterrupt:
            sys.exit(0)


# ── TUI helpers ────────────────────────────────────────

def _use_tui():
    """判断是否可以使用 curses TUI"""
    if not sys.stdin.isatty():
        return False
    try:
        cols = os.get_terminal_size().columns
        return cols >= 40
    except OSError:
        return False


_CLI_DEFAULT_FAMILY_FIRST = {
    "claude": "Claude",
    "codex": "GPT",
}

_FAMILY_COLD_MAX_USE_COUNT = 3
_FAMILY_COLD_IDLE_DAYS = 21


def _parse_usage_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _usage_recency_score(value, now=None, half_life_days=14):
    parsed = _parse_usage_timestamp(value)
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (current - parsed).total_seconds()) / 86400.0
    return 0.5 ** (age_days / float(half_life_days))


def _sort_family_entries_for_tui(families, preferred_family="", now=None):
    def _key(item):
        family = str(item.get("family") or "") if isinstance(item, dict) else ""
        last_at = str(item.get("last_used_at") or "").strip() if isinstance(item, dict) else ""
        recency = _usage_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        preferred_rank = 0 if family == str(preferred_family or "").strip() else 1
        return (-has_recent, -recency, preferred_rank, family.lower())

    return sorted(list(families or []), key=_key)


def _family_is_cold_for_tui(family_name, total_use, last_used_at="", *, preferred_family=""):
    if str(family_name or "").strip() == str(preferred_family or "").strip():
        return False
    if str(family_name or "").strip() in KNOWN_MODEL_FAMILY_NAMES:
        return False
    if int(total_use or 0) > _FAMILY_COLD_MAX_USE_COUNT:
        return False
    parsed = _parse_usage_timestamp(last_used_at)
    if parsed is None:
        return True
    return parsed < (datetime.now(timezone.utc) - timedelta(days=_FAMILY_COLD_IDLE_DAYS))


def _build_provider_options_map(cfg, cli_name, default_provider, default_models, model_names):
    """为一组模型名构建运行来源替代选项映射（供 P 键使用）。

    Returns:
        dict[str, list[dict]] — model_name -> [{"provider_name", "provider_id", "provider_ctx"}]
    """
    result = {}
    for model_name in model_names:
        selected_family, _ = _infer_model_family(model_name)
        options = []
        for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
            if not provider.get("enabled", True):
                continue
            if not _provider_has_configured_base_url(provider):
                continue
            if not provider.get("api_key"):
                continue
            models = _provider_effective_models(provider, cached_models, cfg)
            model_lower = [str(m or "").strip().lower() for m in models]
            if model_name.strip().lower() not in model_lower:
                continue
            if not _provider_supports_model_for_cli(provider, cli_name, model_name):
                continue
            runtime = _runtime_with_priority(provider, model_name=model_name, family_name=selected_family)
            options.append({
                "provider_name": _provider_label(provider),
                "provider_id": provider.get("id", DEFAULT_PROVIDER_ID),
                "priority_family": selected_family,
                "provider_ctx": runtime,
            })
        account_options = _account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info={"model": model_name},
            allow_selected_model=True,
        )
        for option in account_options:
            runtime = option.get("runtime") or {}
            options.append({
                "provider_name": f"{option.get('title', runtime.get('id', 'account'))} OAuth",
                "provider_id": runtime.get("id", ""),
                "priority_family": option.get("priority_family", selected_family),
                "provider_ctx": runtime,
            })
        if len(options) > 1:
            result[model_name] = options
    return result


def _make_provider_options_loader(cfg, cli_name, default_provider, default_models):
    """按模型懒加载 provider options，避免 TUI 首屏全量预计算。"""
    cache = {}

    def _loader(model_name):
        key = str(model_name or "").strip()
        if not key:
            return []
        if key not in cache:
            cache[key] = _build_provider_options_map(
                cfg, cli_name, default_provider, default_models, [key]
            ).get(key, [])
        return cache[key]

    return _loader


def _apply_runtime_priority_changes(cfg, pri_changes):
    changed = False
    if not pri_changes:
        return changed

    for runtime_id, new_pri in pri_changes.items():
        family_name = ""
        actual_runtime_id = runtime_id
        if "||" in str(runtime_id):
            actual_runtime_id, family_name = str(runtime_id).split("||", 1)
            family_name = _canonical_model_family(family_name)
        matched = False
        for pdef in cfg.get("providers", []):
            if pdef.get("id") == actual_runtime_id:
                if family_name:
                    overrides = _normalize_family_priority_overrides(
                        pdef.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = _normalize_priority(new_pri)
                    pdef["family_priority_overrides"] = overrides
                else:
                    pdef["priority"] = _normalize_priority(new_pri)
                changed = True
                matched = True
                break
        if matched:
            continue
        for adef in cfg.get("accounts", []):
            if adef.get("id") == actual_runtime_id:
                if family_name:
                    overrides = _normalize_family_priority_overrides(
                        adef.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = _normalize_priority(new_pri)
                    adef["family_priority_overrides"] = overrides
                else:
                    adef["priority"] = _normalize_priority(new_pri)
                changed = True
                break
    return changed


def _handle_tui_launcher_selection(cfg, provider, once, cli_names, account_id=None, provider_id=None):
    """TUI 交互：品类 → 子模型 → 确认。返回 True 表示已处理，False 表示 fallback"""
    from mms_tui import select_family_tui, select_submodel_tui, confirm_tui
    import mms_tui_launcher_flow as tui_flow
    from mms_launchers import (
        _caveman_available_for_cli,
        _ecc_available_for_claude,
        _nsr_available_for_cli,
        _omc_available_for_claude,
        launch_cli,
        get_export_env,
    )

    current_cfg = cfg
    current_provider = provider
    current_cli_names = cli_names
    default_models = _probe_models(current_provider, emit_output=False).get("models")
    if account_id or provider_id:
        _trace_record("CLI flags", account=account_id, provider=provider_id)

    # 预构建品类数据（仅在配置变更时重建）
    def _rebuild_families():
        return tui_flow.build_tui_family_payloads(
            current_cfg,
            current_cli_names,
            current_provider,
            default_models,
            build_model_families_for_cli=_build_model_families_for_cli,
            cli_default_family_first=_CLI_DEFAULT_FAMILY_FIRST,
            family_is_cold_for_tui=_family_is_cold_for_tui,
            sort_family_entries_for_tui=_sort_family_entries_for_tui,
            make_provider_options_loader=_make_provider_options_loader,
        )

    def _refresh_runtime_state_after_config_change(updated_cfg):
        import shutil as _shutil

        return tui_flow.refresh_tui_runtime_state_after_config_change(
            updated_cfg,
            probe_cache=_PROBE_CACHE,
            probe_file_cache_dir=_PROBE_FILE_CACHE_DIR,
            rmtree=_shutil.rmtree,
            ensure_provider_credentials=ensure_provider_credentials,
            probe_models=_probe_models,
            resolve_visible_clis=_resolve_visible_clis,
        )

    families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = _rebuild_families()
    _families_dirty = False

    while True:
        if _families_dirty:
            families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = _rebuild_families()
            _families_dirty = False

        # 获取上次使用信息（按 CLI 分桶，TUI 内部按当前 tab 过滤）
        last_by_cli, _ = _get_scene_usage()

        result = tui_flow.safe_tui_call(
            select_family_tui,
            families_by_cli,
            current_cli_names,
            last_used=last_by_cli,
            families_detail=families_detail,
            provider_options_by_cli=provider_options_by_cli,
            provider_options_loader_by_cli=provider_options_loader_by_cli,
            broker_enabled_by_cli=_broker_enabled_by_cli(current_cfg, current_cli_names),
            profile_options_by_cli={
                "opencode": _opencode_profile_menu_options(),
                "agy": _official_account_menu_options(current_cfg, "agy"),
            },
        )

        if result == "fallback":
            return False
        if result == "__interrupt__":
            return True
        if result is None:
            return True

        action_type, cli, action_data = result

        # ── 接入通道 ──
        if action_type == "connect":
            connect_result = tui_flow.handle_tui_connect_action(
                current_cfg,
                cli,
                quick_connect_official=_quick_connect_official,
                run_connect_wizard=run_connect_wizard,
                refresh_runtime_state=_refresh_runtime_state_after_config_change,
            )
            current_cfg = connect_result["cfg"]
            if connect_result["changed"]:
                current_provider = connect_result["current_provider"]
                default_models = connect_result["default_models"]
                current_cli_names = connect_result["current_cli_names"]
                _families_dirty = connect_result["families_dirty"]
            continue

        # ── Broker experiment ──
        if action_type == "broker":
            if _launch_broker_experiment_interactive(current_cfg, cli):
                return True
            continue

        # ── OpenCode profile ──
        if action_type == "profile" and cli == "opencode":

            model_info, runtime_runtime = tui_flow.opencode_profile_launch_context(
                current_cfg,
                current_provider,
                default_models,
                action_data,
                resolve_opencode_profile_runtime=_resolve_opencode_profile_runtime,
                trace_record=_trace_record,
                trace_runtime_choice=_trace_runtime_choice,
            )
            if runtime_runtime is None:
                console.print("[yellow]OpenCode Lite/Raw 未找到安全的 OpenAI-compatible GPT provider；请用 Heavy/OMO 或先配置 GPT provider。[/yellow]")
                continue
            # fall through to confirm
        if action_type == "profile" and cli == "agy":
            if action_data == _AGY_CONNECT_PROFILE_ID:
                connect_result = tui_flow.handle_tui_connect_action(
                    current_cfg,
                    cli,
                    quick_connect_official=_quick_connect_official,
                    run_connect_wizard=run_connect_wizard,
                    refresh_runtime_state=_refresh_runtime_state_after_config_change,
                )
                current_cfg = connect_result["cfg"]
                if connect_result["changed"]:
                    current_provider = connect_result["current_provider"]
                    default_models = connect_result["default_models"]
                    current_cli_names = connect_result["current_cli_names"]
                    _families_dirty = connect_result["families_dirty"]
                continue

            model_info, runtime_runtime = tui_flow.official_account_profile_context(
                current_cfg,
                cli,
                action_data,
                resolve_account_context=resolve_account_context,
                trace_record=_trace_record,
                trace_runtime_choice=_trace_runtime_choice,
            )
            if runtime_runtime is None:
                console.print(f"[yellow]未找到 {cli} 官方账号: {action_data}[/yellow]")
                continue
            # fall through to confirm

        # ── Provider 浏览 ──
        if action_type == "provider_browse":
            from mms_tui import select_provider_browse_tui, select_provider_models_tui

            browse_result = tui_flow.handle_tui_provider_browse_action(
                current_cfg,
                cli,
                current_provider,
                default_models,
                select_provider_browse_tui=select_provider_browse_tui,
                select_provider_models_tui=select_provider_models_tui,
                provider_candidates=_provider_candidates,
                default_provider_id=DEFAULT_PROVIDER_ID,
                provider_supports_cli_name=_provider_supports_cli_name,
                provider_label=_provider_label,
                resolve_provider_context=resolve_provider_context,
                probe_models=_probe_models,
                filter_visible_models=_filter_visible_models,
                trace_record=_trace_record,
                trace_runtime_choice=_trace_runtime_choice,
            )
            if browse_result.get("message"):
                console.print(f"[yellow]{browse_result['message']}[/yellow]")
            if browse_result["status"] == "exit":
                return True
            if browse_result["status"] != "launch":
                continue
            model_info = browse_result["model_info"]
            runtime_runtime = browse_result["runtime"]
            # fall through to confirm

        # ── 设置 ──
        if action_type == "settings":
            from mms_tui import (
                select_channel_action_tui,
                select_language_tui,
                select_rescue_event_tui,
                select_settings_tui,
                select_provider_mgmt_tui,
            )
            settings_action = tui_flow.safe_tui_call(select_settings_tui)
            if settings_action == "__interrupt__":
                return True
            if settings_action is None:
                continue
            if settings_action == "provider_mgmt":
                providers_raw = current_cfg.get("providers", [])
                result_providers = tui_flow.safe_tui_call(select_provider_mgmt_tui, providers_raw)
                if result_providers == "__interrupt__":
                    return True
                if result_providers is not None:
                    # 回写 role/priority 到 config
                    for rp in result_providers:
                        pid = rp.get("id")
                        for orig in current_cfg.get("providers", []):
                            if orig.get("id") == pid:
                                orig["role"] = rp.get("role", "auto")
                                orig["priority"] = rp.get("priority", 100)
                                break
                    save_config(current_cfg)
                    _PROBE_CACHE.clear()
                    current_provider = ensure_provider_credentials(current_cfg)
                    default_models = _probe_models(current_provider, emit_output=False).get("models")
                    _families_dirty = True
                    # 自动重新生成 routes
                    try:
                        from mms_router import export_model_routes
                        export_model_routes(current_cfg, force=True)
                    except Exception:
                        pass
            elif settings_action == "language":
                chosen_lang = tui_flow.safe_tui_call(select_language_tui)
                if chosen_lang == "__interrupt__":
                    return True
                if chosen_lang in {"zh", "en"}:
                    current_cfg.setdefault("ui", {})["language"] = chosen_lang
                    save_config(current_cfg)
                    set_language(chosen_lang)
            elif settings_action == "routes_export":
                try:
                    from mms_router import MODEL_ROUTES_PATH, export_model_routes

                    export_model_routes(current_cfg, force=True)
                    console.print(f"[green]✓ 已导出 {MODEL_ROUTES_PATH}[/green]")
                except Exception as e:
                    console.print(f"[red]导出失败: {e}[/red]")
            elif settings_action == "registry":
                from mms_registry_cli import diff_openrouter_catalog, fetch_openrouter_catalog, publish_approved_bundle, refresh_source_snapshots, registry_status, scheduled_refresh, source_freshness, verify_approved_bundle

                status = registry_status()
                registry_title, registry_info, registry_actions = _registry_truth_tui_payload(status)
                registry_action = tui_flow.safe_tui_call(
                    select_channel_action_tui,
                    registry_title,
                    registry_info,
                    registry_actions,
                )
                if registry_action == "__interrupt__":
                    return True
                if registry_action == "check_staleness":
                    try:
                        summary = source_freshness()
                    except Exception as exc:
                        _print_settings_error_report(_L("检查 Source Staleness 失败", "Check Source Staleness failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_source_staleness_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action in {"refresh_sources", "refresh_due_sources"}:
                    try:
                        summary = refresh_source_snapshots(if_due=(registry_action == "refresh_due_sources"))
                    except Exception as exc:
                        _print_settings_error_report(_L("刷新 Sources 失败", "Refresh Sources failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_refresh_sources_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action in {"scheduled_dry_run", "scheduled_no_network"}:
                    try:
                        summary = scheduled_refresh(
                            dry_run=(registry_action == "scheduled_dry_run"),
                            no_network=True,
                        )
                    except Exception as exc:
                        _print_settings_error_report(_L("定时刷新失败", "Scheduled Refresh failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_scheduled_refresh_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "fetch_openrouter":
                    try:
                        summary = fetch_openrouter_catalog()
                    except Exception as exc:
                        _print_settings_error_report(_L("拉取 OpenRouter Catalog 失败", "Fetch OpenRouter Catalog failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_openrouter_fetch_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "diff_openrouter":
                    try:
                        summary = diff_openrouter_catalog(limit=12)
                    except Exception as exc:
                        _print_settings_error_report(_L("OpenRouter Candidate Diff 失败", "OpenRouter Candidate Diff failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_openrouter_diff_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "publish_approved":
                    try:
                        summary = publish_approved_bundle()
                    except Exception as exc:
                        _print_settings_error_report(_L("发布 Approved Bundle 失败", "Publish Approved Bundle failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_publish_approved_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "verify_approved":
                    try:
                        summary = verify_approved_bundle()
                    except Exception as exc:
                        _print_settings_error_report(_L("验证 Approved Bundle 失败", "Verify Approved Bundle failed"), exc)
                    else:
                        _print_settings_result_report(*_registry_verify_approved_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "doctor":
                    status = registry_status()
                    _print_settings_result_report(*_registry_doctor_report_payload(status))
                    _pause_after_tui_report("按 Enter 返回设置")
            elif settings_action == "about":
                while True:
                    about_snapshot = _about_status_snapshot(force_update=False)
                    about_title, about_lines, about_actions = _about_tui_payload(about_snapshot)
                    about_action = tui_flow.safe_tui_call(
                        select_channel_action_tui,
                        about_title,
                        about_lines,
                        about_actions,
                    )
                    if about_action == "__interrupt__":
                        return True
                    if about_action in {None, "back"}:
                        break
                    if about_action == "refresh_versions":
                        console.print("[cyan]正在刷新 MMS / Codex / Claude 版本检查...[/cyan]")
                        _about_status_snapshot(force_update=True)
                        continue
                    if about_action in {"upgrade_mms", "upgrade_codex_cli", "upgrade_claude_cli"}:
                        upgrade_target = {
                            "upgrade_mms": "mms",
                            "upgrade_codex_cli": "codex",
                            "upgrade_claude_cli": "claude",
                        }[about_action]
                        _run_about_upgrade(target=upgrade_target)
                        _pause_after_tui_report("按 Enter 返回关于")
                        continue
            elif settings_action == "guard":
                guard_title, guard_info, guard_actions = _snapshot_guard_tui_payload()
                guard_action = tui_flow.safe_tui_call(
                    select_channel_action_tui,
                    guard_title,
                    guard_info,
                    guard_actions,
                )
                if guard_action == "__interrupt__":
                    return True
                if guard_action == "status":
                    handle_guard_command(["status"], bootstrap_cfg=current_cfg)
                    _pause_after_tui_report("按 Enter 返回设置")
                elif guard_action == "accept":
                    if _confirm_guard_accept_from_tui(current_cfg):
                        handle_guard_command(["accept"], bootstrap_cfg=current_cfg)
                    else:
                        console.print("[yellow]已取消接受当前快照。[/yellow]")
                    _pause_after_tui_report("按 Enter 返回设置")
            elif settings_action == "account_mgmt":
                _run_account_mgmt_tui(current_cfg)
            elif settings_action == "rescue":
                from pathlib import Path
                from mms_rescue import list_rescue_events, write_demo_rescue_packet, write_fallback_handover

                default_fallback = _rescue_default_fallback(current_cfg)
                default_label = default_fallback.get("model") or "未设置"
                hot_fallback_enabled = _rescue_hot_fallback_enabled_cfg(current_cfg)
                route_fallback_candidates = _rescue_route_fallback_model_candidates(limit=120)
                rescue_events = list_rescue_events(repo_root=os.getcwd(), limit=20)
                landing_info, landing_actions = _rescue_landing_tui_payload(
                    default_label,
                    rescue_events,
                    _latest_rescue_hot_fallback_event(),
                    hot_fallback_enabled,
                )
                landing_action = tui_flow.safe_tui_call(
                    select_channel_action_tui,
                    "Rescue / Current-session Fallback",
                    landing_info,
                    landing_actions,
                )
                if landing_action == "__interrupt__":
                    return True
                if landing_action in {None, "back"}:
                    continue
                if str(landing_action or "").startswith("default::") or landing_action == "manual_default":
                    fallback_model = str(landing_action or "").split("::", 1)[1] if str(landing_action or "").startswith("default::") else ""
                    if not fallback_model:
                        _ensure_rich()
                        fallback_model = Prompt.ask("全局默认 fallback model", default=default_fallback.get("model") or "").strip()
                    if fallback_model:
                        current_cfg = _set_rescue_default_fallback(current_cfg, model=fallback_model)
                        save_config(current_cfg, reason="tui:rescue_default_fallback")
                        _print_settings_result_report(
                            *_rescue_default_fallback_report_payload(
                                fallback_model,
                                hot_fallback_enabled=_rescue_hot_fallback_enabled_cfg(current_cfg),
                            )
                        )
                        _pause_after_tui_report("按 Enter 返回设置")
                    continue
                if landing_action == "choose_route_default":
                    from mms_tui import select_model_tui

                    fallback_model = tui_flow.safe_tui_call(
                        select_model_tui,
                        route_fallback_candidates,
                        title="选择全局默认 fallback model",
                    )
                    if fallback_model:
                        current_cfg = _set_rescue_default_fallback(current_cfg, model=fallback_model)
                        save_config(current_cfg, reason="tui:rescue_default_fallback")
                        _print_settings_result_report(
                            *_rescue_default_fallback_report_payload(
                                fallback_model,
                                hot_fallback_enabled=_rescue_hot_fallback_enabled_cfg(current_cfg),
                            )
                        )
                        _pause_after_tui_report("按 Enter 返回设置")
                    continue
                if landing_action in {"enable_hot_fallback", "disable_hot_fallback"}:
                    enable_hot = landing_action == "enable_hot_fallback"
                    current_cfg, applied = _set_rescue_hot_fallback_enabled(current_cfg, enabled=enable_hot)
                    if applied != enable_hot:
                        _print_settings_result_report(
                            *_rescue_hot_fallback_toggle_report_payload(False, has_default=False),
                            ok=False,
                        )
                    else:
                        save_config(current_cfg, reason="tui:rescue_hot_fallback")
                        _print_settings_result_report(*_rescue_hot_fallback_toggle_report_payload(enable_hot))
                    _pause_after_tui_report("按 Enter 返回设置")
                    continue
                if landing_action == "clear_default":
                    current_cfg = _set_rescue_default_fallback(current_cfg, model="")
                    save_config(current_cfg, reason="tui:clear_rescue_default_fallback")
                    _print_settings_result_report(*_rescue_default_fallback_report_payload("", cleared=True))
                    _pause_after_tui_report("按 Enter 返回设置")
                    continue
                if landing_action == "create_demo":
                    payload = write_demo_rescue_packet(repo_root=os.getcwd())
                    _print_settings_result_report(*_rescue_demo_packet_report_payload(payload))
                    _pause_after_tui_report("按 Enter 返回设置")
                    continue
                if landing_action != "view_packets":
                    continue
                if not rescue_events:
                    _print_settings_result_report(
                        _L("没有 rescue packet", "No rescue packet"),
                        [(_L("状态", "Status"), _L("当前没有可查看记录", "No records available"))],
                        ok=False,
                    )
                    _pause_after_tui_report("按 Enter 返回设置")
                    continue
                selected_rescue = tui_flow.safe_tui_call(select_rescue_event_tui, rescue_events)
                if selected_rescue == "__interrupt__":
                    return True
                if not selected_rescue:
                    continue
                info_lines = [
                    ("时间", selected_rescue.get("created_at") or "-"),
                    ("模型", selected_rescue.get("failed_model") or "-"),
                    ("Provider", selected_rescue.get("failed_provider_id") or "-"),
                    ("状态", selected_rescue.get("status_code") or selected_rescue.get("failure_kind") or "-"),
                    ("原因", selected_rescue.get("failure_kind") or "-"),
                    ("Repo", selected_rescue.get("repo_path") or "-"),
                    ("全局默认", default_label),
                ]
                fallback_candidates = _rescue_fallback_model_candidates(current_cfg, selected_rescue, limit=8)
                route_fallback_candidates = _rescue_route_fallback_model_candidates(
                    failed_model=selected_rescue.get("failed_model") or "",
                    limit=120,
                )
                fallback_actions = [
                    (f"handover::{model}", f"生成 fallback handover -> {model}")
                    for model in fallback_candidates
                ]
                default_actions = [
                    (f"default::{model}", f"设为全局默认 fallback -> {model}")
                    for model in fallback_candidates
                ]
                rescue_action = tui_flow.safe_tui_call(
                    select_channel_action_tui,
                    "Rescue Packet",
                    info_lines,
                    fallback_actions + default_actions + [
                        ("choose_route_handover", "从 routed models 选择 handover"),
                        ("choose_route_default", "设置全局默认 fallback（routed models）"),
                        ("manual_handover", "手动输入 fallback model"),
                        ("manual_default", "手动输入全局默认 fallback"),
                        ("clear_default", "清除全局默认 fallback"),
                        ("view_md", "查看 rescue.md"),
                        ("show_paths", "显示文件路径"),
                        ("back", "返回"),
                    ],
                )
                if rescue_action == "__interrupt__":
                    return True
                if rescue_action == "view_md":
                    md_path = Path(str(selected_rescue.get("artifact_markdown") or ""))
                    try:
                        content = md_path.read_text(encoding="utf-8")
                    except OSError as exc:
                        _print_settings_error_report(_L("无法读取 rescue.md", "Cannot read rescue.md"), exc)
                    else:
                        try:
                            console.clear()
                        except Exception:
                            pass
                        console.print(content)
                    _pause_after_tui_report("按 Enter 返回设置")
                elif rescue_action == "show_paths":
                    _print_settings_result_report(*_rescue_paths_report_payload(selected_rescue))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif str(rescue_action or "").startswith("handover::") or rescue_action == "manual_handover":
                    fallback_model = str(rescue_action or "").split("::", 1)[1] if str(rescue_action or "").startswith("handover::") else ""
                    if not fallback_model:
                        _ensure_rich()
                        fallback_model = Prompt.ask("fallback model", default="").strip()
                    if fallback_model:
                        try:
                            handover = write_fallback_handover(
                                selected_rescue,
                                fallback_model=fallback_model,
                            )
                        except Exception as exc:
                            _print_settings_error_report(_L("生成 fallback handover 失败", "Create fallback handover failed"), exc)
                        else:
                            _print_settings_result_report(*_rescue_handover_report_payload(handover, fallback_model))
                        _pause_after_tui_report("按 Enter 返回设置")
                elif rescue_action == "choose_route_handover":
                    from mms_tui import select_model_tui

                    fallback_model = tui_flow.safe_tui_call(
                        select_model_tui,
                        route_fallback_candidates,
                        title="选择 fallback handover model",
                    )
                    if fallback_model:
                        try:
                            handover = write_fallback_handover(
                                selected_rescue,
                                fallback_model=fallback_model,
                            )
                        except Exception as exc:
                            _print_settings_error_report(_L("生成 fallback handover 失败", "Create fallback handover failed"), exc)
                        else:
                            _print_settings_result_report(*_rescue_handover_report_payload(handover, fallback_model))
                        _pause_after_tui_report("按 Enter 返回设置")
                elif str(rescue_action or "").startswith("default::") or rescue_action == "manual_default":
                    fallback_model = str(rescue_action or "").split("::", 1)[1] if str(rescue_action or "").startswith("default::") else ""
                    if not fallback_model:
                        _ensure_rich()
                        fallback_model = Prompt.ask("全局默认 fallback model", default=default_fallback.get("model") or "").strip()
                    if fallback_model:
                        current_cfg = _set_rescue_default_fallback(current_cfg, model=fallback_model)
                        save_config(current_cfg, reason="tui:rescue_default_fallback")
                        _print_settings_result_report(
                            *_rescue_default_fallback_report_payload(
                                fallback_model,
                                hot_fallback_enabled=_rescue_hot_fallback_enabled_cfg(current_cfg),
                            )
                        )
                        _pause_after_tui_report("按 Enter 返回设置")
                elif rescue_action == "choose_route_default":
                    from mms_tui import select_model_tui

                    fallback_model = tui_flow.safe_tui_call(
                        select_model_tui,
                        route_fallback_candidates,
                        title="选择全局默认 fallback model",
                    )
                    if fallback_model:
                        current_cfg = _set_rescue_default_fallback(current_cfg, model=fallback_model)
                        save_config(current_cfg, reason="tui:rescue_default_fallback")
                        _print_settings_result_report(
                            *_rescue_default_fallback_report_payload(
                                fallback_model,
                                hot_fallback_enabled=_rescue_hot_fallback_enabled_cfg(current_cfg),
                            )
                        )
                        _pause_after_tui_report("按 Enter 返回设置")
                elif rescue_action == "clear_default":
                    current_cfg = _set_rescue_default_fallback(current_cfg, model="")
                    save_config(current_cfg, reason="tui:clear_rescue_default_fallback")
                    _print_settings_result_report(*_rescue_default_fallback_report_payload("", cleared=True))
                    _pause_after_tui_report("按 Enter 返回设置")
            continue

        # ── 上次使用 ──
        elif action_type == "last":

            last_action = tui_flow.handle_tui_last_used_action(
                current_cfg,
                cli,
                action_data,
                current_provider,
                default_models,
                account_id=account_id,
                provider_id=provider_id,
                trace_record=_trace_record,
                resolve_last_used_runtime=_resolve_last_used_runtime,
                resolve_best_provider=_resolve_best_provider,
                choose_runtime_source=_choose_runtime_source,
                trace_runtime_choice=_trace_runtime_choice,
            )
            if last_action.get("message"):
                console.print(f"[yellow]{last_action['message']}[/yellow]")
            if last_action["status"] != "launch":
                continue
            model_info = last_action["model_info"]
            runtime_runtime = last_action["runtime"]
            cli = last_action["cli"]
            # fall through to confirm

        # ── 品类选择 → 子模型 ──
        elif action_type == "submodel":
            selected = dict(action_data or {})
            family_name = selected.pop("_family_name", "模型")

            pri_changes = selected.pop("priority_changes", None)

            if tui_flow.apply_tui_priority_changes(
                current_cfg,
                pri_changes,
                apply_runtime_priority_changes=_apply_runtime_priority_changes,
                save_config=save_config,
                export_model_routes_loader=lambda: __import__("mms_router", fromlist=["export_model_routes"]).export_model_routes,
            ):
                _families_dirty = True


            model_info, runtime_runtime = tui_flow.selected_model_launch_context(
                current_cfg,
                cli,
                selected,
                current_provider,
                default_models,
                resolve_best_provider=_resolve_best_provider,
                trace_runtime_choice=_trace_runtime_choice,
            )
            if runtime_runtime is None:
                console.print(f"[yellow]没有可用 provider 承载 {selected['model']}[/yellow]")
                continue
            _trace_record(
                f'family "{family_name}"',
                cli=cli,
                model=selected.get("model"),
                provider=(runtime_runtime or {}).get("id") if isinstance(runtime_runtime, dict) else selected.get("provider_id"),
            )
            # fall through to confirm

        elif action_type == "family":
            family_name = action_data
            models = families_detail.get(cli, {}).get(family_name, [])
            if not models:
                console.print(f"[yellow]{family_name} 下没有可用模型[/yellow]")
                continue

            provider_options = provider_options_by_cli.get(cli, {})

            selected = tui_flow.safe_tui_call(
                select_submodel_tui,
                family_name,
                models,
                provider_options=provider_options,
                last_used=last_by_cli.get(cli),
            )
            if selected == "__interrupt__":
                return True
            if selected is None:
                continue  # Esc 返回品类列表
            if selected == "__last__":
                action_data = last_by_cli.get(cli) or {}
                if not action_data.get("model"):
                    continue

                last_action = tui_flow.handle_tui_last_used_action(
                    current_cfg,
                    cli,
                    action_data,
                    current_provider,
                    default_models,
                    account_id=account_id,
                    provider_id=provider_id,
                    trace_record=_trace_record,
                    resolve_last_used_runtime=_resolve_last_used_runtime,
                    resolve_best_provider=_resolve_best_provider,
                    choose_runtime_source=_choose_runtime_source,
                    trace_runtime_choice=_trace_runtime_choice,
                )
                if last_action.get("message"):
                    console.print(f"[yellow]{last_action['message']}[/yellow]")
                if last_action["status"] != "launch":
                    continue
                model_info = last_action["model_info"]
                runtime_runtime = last_action["runtime"]
                cli = last_action["cli"]
            else:
                # 持久化 priority 变更
                pri_changes = selected.pop("priority_changes", None)

                if tui_flow.apply_tui_priority_changes(
                    current_cfg,
                    pri_changes,
                    apply_runtime_priority_changes=_apply_runtime_priority_changes,
                    save_config=save_config,
                    export_model_routes_loader=lambda: __import__("mms_router", fromlist=["export_model_routes"]).export_model_routes,
                ):
                    _families_dirty = True


                model_info, runtime_runtime = tui_flow.selected_model_launch_context(
                    current_cfg,
                    cli,
                    selected,
                    current_provider,
                    default_models,
                    resolve_best_provider=_resolve_best_provider,
                    trace_runtime_choice=_trace_runtime_choice,
                )
                if runtime_runtime is None:
                    console.print(f"[yellow]没有可用 provider 承载 {selected['model']}[/yellow]")
                    continue
                _trace_record(
                    f'family "{family_name}"',
                    cli=cli,
                    model=selected.get("model"),
                    provider=(runtime_runtime or {}).get("id") if isinstance(runtime_runtime, dict) else selected.get("provider_id"),
                )
            # fall through to confirm
        elif action_type == "profile" and cli not in {"opencode", "agy"}:
            continue
        elif action_type not in ("profile", "provider_browse", "last", "family"):
            continue

        # ── 公共：确认页 + 启动 ──
        if not check_cli_installed(cli):
            from mms_installer import check_and_offer_install
            if not check_and_offer_install(cli):
                return True

        if cli == "opencode":
            runtime_runtime = _select_and_apply_opencode_profile(runtime_runtime, use_tui=True)
            if runtime_runtime is None:
                continue
        runtime_runtime = _runtime_with_launch_preferences(current_cfg, runtime_runtime, cli)
        if cli == "claude":
            runtime_runtime = _runtime_with_vision_sidecar(current_cfg, runtime_runtime)

        clean_model_info = _clean_model_info(model_info)
        env_vars = get_export_env(cli, runtime_runtime)
        if cli == "claude" and runtime_runtime and runtime_runtime.get("auth_mode") in {"oauth", "api_key"}:
            try:
                from mms_launchers import get_claude_network_guard_preview, _claude_bypass_requires_proxy
                runtime_runtime["_network_guard"] = get_claude_network_guard_preview(
                    runtime_runtime,
                    require_proxy=bool(runtime_runtime.get("bypass")) and _claude_bypass_requires_proxy(runtime_runtime),
                )
            except Exception:
                runtime_runtime["_network_guard"] = {
                    "status": "unknown",
                    "dns_mode": "unknown",
                    "ipv4_egress": "-",
                    "ipv6_egress": "-",
                    "targets": [],
                    "no_proxy_conflicts": [],
                }

        confirm_context = tui_flow.build_confirm_capability_context(
            cli,
            runtime_runtime,
            clean_model_info,
            confirm_context_lines=_confirm_context_lines,
            caveman_available_for_cli=_caveman_available_for_cli,
            nsr_available_for_cli=_nsr_available_for_cli,
            ecc_available_for_claude=_ecc_available_for_claude,
            omc_available_for_claude=_omc_available_for_claude,
            model_info_looks_domestic=_model_info_looks_domestic,
            default_reasoning_effort_for_model_info=_default_reasoning_effort_for_model_info,
            build_confirm_preview_catalog=_build_confirm_preview_catalog,
        )
        context_lines = confirm_context["context_lines"]
        has_caveman = confirm_context["has_caveman"]
        has_nsr = confirm_context["has_nsr"]
        has_ecc = confirm_context["has_ecc"]
        has_omc = confirm_context["has_omc"]
        default_reasoning_effort = confirm_context["default_reasoning_effort"]
        preview_catalog = confirm_context["preview_catalog"]

        result = tui_flow.safe_tui_call(
            confirm_tui,
            cli,
            clean_model_info,
            **tui_flow.confirm_tui_options(
                env_vars=env_vars,
                once=once,
                context_lines=context_lines,
                has_caveman=has_caveman,
                has_nsr=has_nsr,
                has_ecc=has_ecc,
                has_omc=has_omc,
                runtime=runtime_runtime,
                default_reasoning_effort=default_reasoning_effort,
                preview_catalog=preview_catalog,
            ),
        )
        if result == "__interrupt__":
            return True

        confirm_result = tui_flow.normalize_confirm_result(result, default_reasoning_effort)
        action = confirm_result["action"]
        bypass = confirm_result["bypass"]
        claude_1m_enabled = confirm_result["claude_1m_enabled"]
        caveman_enabled = confirm_result["caveman_enabled"]
        agent_pack = confirm_result["agent_pack"]
        thinking_enabled = confirm_result["thinking_enabled"]
        reasoning_effort = confirm_result["reasoning_effort"]
        disabled_session_surfaces = confirm_result["disabled_session_surfaces"]
        nsr_enabled = confirm_result["nsr_enabled"]
        confirm_returned_surfaces = confirm_result["confirm_returned_surfaces"]
        if action == "q":
            return True
        if action == "b":
            continue

        tui_flow.apply_confirm_bypass_flag(runtime_runtime, cli, bypass)
        if bypass:
            if cli == "claude" and runtime_runtime and runtime_runtime.get("auth_mode") in {"oauth", "api_key"}:
                from mms_launchers import _enforce_claude_network_guard_or_exit, _claude_bypass_requires_proxy
                _enforce_claude_network_guard_or_exit(
                    runtime_runtime,
                    require_proxy=_claude_bypass_requires_proxy(runtime_runtime),
                )

        tui_flow.apply_confirm_runtime_preferences(
            runtime_runtime,
            cli,
            claude_1m_enabled=claude_1m_enabled,
            caveman_enabled=caveman_enabled,
            agent_pack=agent_pack,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            disabled_session_surfaces=disabled_session_surfaces,
            nsr_enabled=nsr_enabled,
            has_nsr=has_nsr,
            confirm_returned_surfaces=confirm_returned_surfaces,
            merge_disabled_session_surfaces=_merge_disabled_session_surfaces,
        )
        _launch_with_tracking(cli, clean_model_info, runtime_runtime, once=once)
        return True


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
    if not args_rest:
        _display_config(cfg)
        return

    key_path = args_rest[0]
    if key_path in {"-h", "--help", "help"}:
        _display_config_help()
        return
    if key_path == "migrate":
        _handle_config_migrate()
        return
    if key_path == "file":
        _handle_config_file()
        return
    if key_path == "validate":
        _handle_config_validate(cfg)
        return
    if key_path in {"preferences", "preferences.help", "preference.help"}:
        _display_preferences_help()
        return
    if key_path in {"preferences.path", "preference.path"}:
        _display_preferences_path()
        return
    if key_path in {"preferences.example", "preference.example"}:
        _display_preferences_example()
        return
    if key_path in {"preferences.doc", "preference.doc"}:
        console.print(PREFERENCES_DOC_PATH)
        return
    if key_path in {"web", "webui", "setup.web", "setup-web"}:
        from mms_config_web import run_config_web

        raise SystemExit(run_config_web(
            cfg,
            args_rest[1:],
            command_name=current_command(),
            config_path=_config_write_target_path(),
            preferences_path=PREFERENCES_PATHS[0],
        ))
    if key_path in {"gates", "human-gate", "humangate", "human-gates"}:
        _display_human_gate_help()
        return
    if key_path == "get":
        _handle_config_get(cfg, args_rest[1:])
        return
    if key_path == "set":
        _handle_config_set(cfg, args_rest[1:])
        return
    if key_path == "unset":
        _handle_config_unset(cfg, args_rest[1:])
        return
    if key_path == "connect":
        run_connect_wizard(cfg)
        return
    if key_path in {"extension.openrouter", "openrouter"}:
        _handle_openrouter_extension_config(cfg, args_rest[1:])
        return
    if key_path in {"adapter.registry", "source.registry", "source.top10"}:
        _display_adapter_registry()
        return
    if key_path == "provider.list":
        _display_providers(cfg)
        return
    if key_path == "provider.default":
        _handle_provider_default_config(cfg, args_rest[1:])
        return
    if key_path == "provider.add":
        _handle_provider_add_config(cfg, args_rest[1:])
        return
    if key_path == "provider.edit":
        _handle_provider_edit_config(cfg, args_rest[1:])
        return
    if key_path == "provider.rename":
        _handle_provider_rename_config(cfg, args_rest[1:])
        return
    if key_path == "provider.remove":
        _handle_provider_remove_config(cfg, args_rest[1:])
        return
    if key_path == "provider.credentials":
        _handle_provider_credentials_config(cfg, args_rest[1:])
        return
    if key_path == "account.list":
        _display_accounts(cfg)
        return
    if key_path == "account.default":
        _handle_account_default_config(cfg, args_rest[1:])
        return
    if key_path == "account.add":
        _handle_account_add_config(cfg, args_rest[1:])
        return
    if key_path == "account.edit":
        _handle_account_edit_config(cfg, args_rest[1:])
        return
    if key_path == "account.remove":
        _handle_account_remove_config(cfg, args_rest[1:])
        return
    if key_path == "account.rename":
        _handle_account_rename_config(cfg, args_rest[1:])
        return
    if key_path == "account.status":
        _handle_account_status_config(cfg, args_rest[1:])
        return
    if key_path == "account.login":
        _handle_account_login_config(cfg, args_rest[1:])
        return
    if key_path in {"usage", "stats"}:
        _display_usage_stats()
        return
    if key_path in ("api.setup", "api.edit"):
        provider = resolve_provider_context(cfg)
        setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        )
        return

    if key_path.startswith("api."):
        _handle_api_config(key_path, args_rest[1:])
        return

    parts = key_path.split(".")
    if len(args_rest) == 1:
        _handle_config_get(cfg, [key_path])
        return
    if len(args_rest) == 2:
        _handle_config_set(cfg, [key_path, args_rest[1]])
        return


def _handle_api_config(key_path, args_rest):
    base_url, api_key, _ = load_api_credentials()

    if key_path == "api.base_url":
        if not args_rest:
            display = base_url or "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            return
        save_api_credentials(args_rest[0].rstrip("/"), api_key)
        console.print(f"[green]✓ {key_path} = {args_rest[0].rstrip('/')}[/green]")
        return

    if key_path == "api.api_key":
        if not args_rest:
            display = _mask_key(api_key) if api_key else "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            console.print(f"[dim]真实值保存在 {CREDENTIALS_PATH}，这里始终只显示掩码。[/dim]")
            return
        save_api_credentials(base_url, args_rest[0])
        console.print(f"[green]✓ {key_path} = {_mask_key(args_rest[0])}[/green]")
        console.print(f"[dim]真实值已保存到 {CREDENTIALS_PATH}，这里显示为掩码。[/dim]")
        return

    console.print(f"[red]配置项 '{key_path}' 不存在[/red]")


def _validate_user_role(raw_value):
    normalized = normalize_user_role(raw_value)
    if str(raw_value).strip() not in {"dev", "ops", "all", "recommended", MODE_ALL, MODE_RECOMMENDED}:
        console.print(
            f"[red]不支持的模型模式: {raw_value}[/red]\n[dim]可用值: {MODE_ALL} / {MODE_RECOMMENDED}[/dim]"
        )
        sys.exit(1)
    return normalized


def _handle_provider_default_config(cfg, args_rest):
    default_id = cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)
    if not args_rest:
        console.print(f"[cyan]provider.default[/cyan] = {default_id}")
        console.print("[dim]当前默认模型源[/dim]")
        return

    requested_id = args_rest[0].strip()
    providers = _provider_map(cfg)
    if requested_id not in providers:
        console.print(f"[red]未找到 provider: {requested_id}[/red]")
        console.print(f"[dim]可用 provider: {', '.join(providers.keys())}[/dim]")
        return

    cfg.setdefault("provider", {})
    cfg["provider"]["default"] = requested_id
    save_config(cfg)
    _refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ provider.default = {requested_id}[/green]")
    console.print("[dim]默认模型源已更新[/dim]")


def _handle_provider_add_config(cfg, args_rest):
    preset_id = args_rest[0].strip() if args_rest else None
    _quick_connect_gateway(cfg, preset_id=preset_id)


def _handle_provider_edit_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config provider.edit <id>[/red]")
        return
    provider_id = args_rest[0].strip()
    providers = _provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    provider = _prompt_provider_metadata(existing=providers[provider_id], preset_id=provider_id)
    updated_cfg = _upsert_provider(cfg, provider)
    save_config(updated_cfg)
    _invalidate_probe_cache(provider_id)
    _refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已更新模型源: {provider_id}[/green]")


def _handle_provider_remove_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config provider.remove <id>[/red]")
        return
    _ensure_interactive_terminal("模型源删除确认")
    provider_id = args_rest[0].strip()
    providers = _provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    if len(providers) == 1:
        console.print("[red]至少需要保留一个模型源，无法删除最后一个[/red]")
        return
    if not Confirm.ask(f"确认删除模型源 '{provider_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = [
        provider for provider in cfg.get("providers", [])
        if provider.get("id") != provider_id
    ]
    default_id = cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)
    if default_id == provider_id:
        updated_cfg["provider"] = {"default": updated_cfg["providers"][0]["id"]}
    save_config(updated_cfg)
    _delete_provider_credentials(provider_id)
    _invalidate_probe_cache(provider_id)
    _refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已删除模型源: {provider_id}[/green]")


def _handle_provider_credentials_config(cfg, args_rest):
    target_id = args_rest[0].strip() if args_rest else cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)
    providers = _provider_map(cfg)
    if target_id not in providers:
        console.print(f"[red]未找到模型源: {target_id}[/red]")
        return
    provider = resolve_provider_context(cfg, target_id)
    setup_provider_credentials(
        provider,
        provider.get("base_url", ""),
        provider.get("api_key", ""),
        allow_keep=True,
    )


def _provider_looks_openrouter(provider):
    if not isinstance(provider, dict):
        return False
    fields = [
        provider.get("id"),
        provider.get("name"),
        provider.get("provider_profile"),
        provider.get("profile"),
        provider.get("extension"),
        provider.get("base_url"),
        provider.get("openai_base_url"),
        provider.get("default_openai_base_url"),
    ]
    return any("openrouter" in str(item or "").lower() for item in fields)


def _openrouter_provider_candidates(cfg):
    providers = []
    for item in cfg.get("providers", []):
        if not _provider_looks_openrouter(item):
            continue
        try:
            providers.append(resolve_provider_context(cfg, item.get("id")))
        except Exception:
            providers.append(item)
    return providers


def _parse_openrouter_extension_args(args_rest):
    args = list(args_rest or [])
    action = "status"
    provider_id = ""
    limit = 12
    assume_paid = False
    json_output = False
    if args and not args[0].startswith("-"):
        action = args.pop(0).strip().lower() or "status"
    if args and not args[0].startswith("-"):
        provider_id = args.pop(0).strip()
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {"--limit", "-n"} and idx + 1 < len(args):
            try:
                limit = max(1, int(args[idx + 1]))
            except ValueError:
                limit = 12
            idx += 2
            continue
        if token == "--assume-paid":
            assume_paid = True
        elif token == "--json":
            json_output = True
        idx += 1
    if action in {"ls", "list"}:
        action = "models"
    if action in {"-h", "--help", "help"}:
        action = "help"
    return {
        "action": action,
        "provider_id": provider_id,
        "limit": limit,
        "assume_paid": assume_paid,
        "json": json_output,
    }


def _display_openrouter_extension_help():
    from mms_command_tools import display_openrouter_extension_help

    return display_openrouter_extension_help(current_command(), console=console)


def _openrouter_extension_provider(cfg, provider_id=""):
    providers = _provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            return None, f"未找到 provider: {provider_id}"
        provider = resolve_provider_context(cfg, provider_id)
        if not _provider_looks_openrouter(provider):
            return provider, f"provider '{provider_id}' 不是 OpenRouter 模板，但仍可用其 Key 做探测"
        return provider, ""
    candidates = _openrouter_provider_candidates(cfg)
    if candidates:
        return candidates[0], ""
    return None, ""


def _display_openrouter_model_rows(title, rows, *, limit):
    from mms_command_tools import display_openrouter_model_rows

    _ensure_rich()
    return display_openrouter_model_rows(title, rows, limit=limit, table_cls=Table, console=console)


def _display_openrouter_video_rows(rows, *, limit):
    from mms_command_tools import display_openrouter_video_rows

    _ensure_rich()
    return display_openrouter_video_rows(rows, limit=limit, table_cls=Table, console=console)


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
    parsed = _parse_openrouter_extension_args(args_rest)
    action = parsed["action"]
    if action == "help":
        _display_openrouter_extension_help()
        return
    if action in {"add", "enable"}:
        _quick_connect_gateway(cfg, preset_id="openrouter")
        return

    from mms_openrouter_extension import (
        openrouter_api_key_from_env,
        probe_openrouter_extension,
    )

    provider, warning = _openrouter_extension_provider(cfg, parsed["provider_id"])
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    api_key = ""
    provider_label = ""
    if provider:
        provider_label = f"{provider.get('name') or provider.get('id')} ({provider.get('id')})"
        api_key = str(provider.get("api_key") or "").strip()
    if not api_key:
        api_key = openrouter_api_key_from_env()
        if api_key and not provider_label:
            provider_label = "OPENROUTER_API_KEY"
    summary = probe_openrouter_extension(
        api_key,
        assume_paid=bool(parsed["assume_paid"]),
    )
    if parsed["json"]:
        console.print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    _display_openrouter_extension_summary(
        summary,
        provider_label=provider_label,
        limit=int(parsed["limit"]),
        show_models=action == "models",
    )


def _handle_account_default_config(cfg, args_rest):
    defaults = cfg.get("account", {}).get("defaults", {})
    if not args_rest:
        for cli_name in MMS_MANAGED_OAUTH_CLIS:
            value = defaults.get(cli_name, "(未设置)")
            console.print(f"[cyan]account.default.{cli_name}[/cyan] = {value}")
        console.print("[dim]Claude OAuth 独立入口已下线，不再支持 account.default.claude。[/dim]")
        return
    if len(args_rest) < 2:
        console.print(f"[red]用法: {current_command()} config account.default <cli> <account_id>[/red]")
        return
    cli_name, account_id = args_rest[0].strip(), args_rest[1].strip()
    if cli_name in MMC_DELEGATED_OAUTH_CLIS:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再支持设置 account.default.claude。[/yellow]")
        return
    if cli_name not in MMS_MANAGED_OAUTH_CLIS:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        return
    accounts = _account_map(cfg)
    account = accounts.get(account_id)
    if not account:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if account.get("cli") != cli_name:
        console.print(f"[red]账号档案 '{account_id}' 绑定的是 {account.get('cli')}，不能设为 {cli_name} 默认账号[/red]")
        return
    cfg.setdefault("account", {}).setdefault("defaults", {})
    cfg["account"]["defaults"][cli_name] = account_id
    save_config(cfg)
    console.print(f"[green]✓ account.default.{cli_name} = {account_id}[/green]")


def _handle_account_add_config(cfg, args_rest):
    requested_cli = args_rest[0].strip() if args_rest and args_rest[0].strip() else None
    if requested_cli in MMC_DELEGATED_OAUTH_CLIS:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再管理 Claude 官方登录。[/yellow]")
        return
    preset_cli = requested_cli if requested_cli in MMS_MANAGED_OAUTH_CLIS else None
    _quick_connect_official(cfg, preset_cli=preset_cli)


def _handle_account_edit_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config account.edit <id>[/red]")
        return
    account_id = args_rest[0].strip()
    accounts = _account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if accounts[account_id].get("cli") in MMC_DELEGATED_OAUTH_CLIS:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再编辑 Claude 官方账号。[/yellow]")
        return
    account = _prompt_account_metadata(existing=accounts[account_id], preset_id=account_id)
    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        updated_accounts.append(account if item.get("id") == account_id else item)
    updated_cfg["accounts"] = updated_accounts
    updated_cfg, _ = _ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已更新账号档案: {account_id}[/green]")


def _handle_account_remove_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config account.remove <id>[/red]")
        return
    _ensure_interactive_terminal("账号档案删除确认")
    account_id = args_rest[0].strip()
    accounts = _account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if not Confirm.ask(f"确认删除账号档案 '{account_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = [
        item for item in cfg.get("accounts", [])
        if item.get("id") != account_id
    ]
    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in list(defaults.items()):
        if value == account_id:
            defaults.pop(cli_name, None)
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = _ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已删除账号档案: {account_id}[/green]")


def _handle_account_status_config(cfg, args_rest):
    if args_rest:
        account = resolve_account_context(cfg, account_id=args_rest[0].strip())
        status = _probe_account_status(account)
        console.print(f"[cyan]{account['id']}[/cyan] = {status['state']}")
        if status.get("summary"):
            console.print(f"[dim]{status['summary']}[/dim]")
        return
    _display_accounts(cfg)


def _handle_account_login_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config account.login <id>[/red]")
        return
    account = resolve_account_context(cfg, account_id=args_rest[0].strip())
    if account and account.get("cli") in MMC_DELEGATED_OAUTH_CLIS:
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    _run_account_login(account)


def _usage_key(runtime_kind, cli_name, runtime_id):
    return f"{runtime_kind}:{cli_name}:{runtime_id}"


def _rename_usage_account(old_id, new_id, new_name, cli_name):
    usage_path = _active_usage_path()
    if not os.path.exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        old_key = _usage_key("account", cli_name, old_id)
        entry = sources.pop(old_key, None)
        if entry is None:
            return False
        entry["id"] = new_id
        entry["name"] = new_name
        sources[_usage_key("account", cli_name, new_id)] = entry
        return True

    return bool(_update_usage_stats(_mutate))


def _rename_usage_provider(old_id, new_id, new_name):
    usage_path = _active_usage_path()
    if not os.path.exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        changed = False
        rewritten = {}
        for key, entry in list(sources.items()):
            if entry.get("runtime_kind") != "provider" or entry.get("id") != old_id:
                continue
            sources.pop(key, None)
            updated = dict(entry)
            updated["id"] = new_id
            updated["name"] = new_name
            cli_name = str(updated.get("cli", "default")).strip() or "default"
            rewritten[_usage_key("provider", cli_name, new_id)] = updated
            changed = True
        sources.update(rewritten)
        return changed

    return bool(_update_usage_stats(_mutate))


def _target_account_home(old_home, new_id):
    expanded = os.path.expanduser(str(old_home or "").strip())
    if not expanded:
        return _default_account_home(new_id)
    known_roots = {
        os.path.realpath(ACCOUNTS_DIR),
    }
    parent = os.path.realpath(os.path.dirname(expanded))
    if parent in known_roots:
        return os.path.join(ACCOUNTS_DIR, new_id)
    return os.path.join(os.path.dirname(expanded), new_id)


def _handle_provider_rename_config(cfg, args_rest):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {current_command()} config provider.rename <old_id> <new_id> [new_name][/red]")
        return
    old_id = args_rest[0].strip()
    new_id = _normalize_provider_id_input(args_rest[1].strip())
    providers = _provider_map(cfg)
    provider = providers.get(old_id)
    if not provider:
        console.print(f"[red]未找到模型源: {old_id}[/red]")
        return
    if old_id == new_id and len(args_rest) < 3:
        console.print("[yellow]名称和标识都未变化，无需重命名[/yellow]")
        return
    if new_id != old_id and new_id in providers:
        console.print(f"[red]目标模型源标识已存在: {new_id}[/red]")
        return

    new_name = args_rest[2].strip() if len(args_rest) >= 3 else new_id
    backup_dir = _backup_config_tree("provider-rename")
    updated_cfg = dict(cfg)
    updated_providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != old_id:
            updated_providers.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_name
        updated_providers.append(_normalize_provider(renamed))
    updated_cfg["providers"] = updated_providers

    provider_cfg = dict(cfg.get("provider", {}))
    if provider_cfg.get("default") == old_id:
        provider_cfg["default"] = new_id
    updated_cfg["provider"] = provider_cfg
    save_config(updated_cfg)
    _rename_usage_provider(old_id, new_id, new_name)
    _invalidate_probe_cache(old_id)
    _invalidate_probe_cache(new_id)
    _refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已重命名模型源: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]显示名: {new_name}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def _handle_account_rename_config(cfg, args_rest):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {current_command()} config account.rename <old_id> <new_id>[/red]")
        return
    old_id = args_rest[0].strip()
    new_id = _normalize_account_id(args_rest[1].strip())
    accounts = _account_map(cfg)
    account = accounts.get(old_id)
    if not account:
        console.print(f"[red]未找到账号档案: {old_id}[/red]")
        return
    if old_id == new_id:
        console.print("[yellow]新旧文件夹名相同，无需重命名[/yellow]")
        return
    if new_id in accounts:
        console.print(f"[red]目标文件夹名已存在: {new_id}[/red]")
        return

    backup_dir = _backup_config_tree("account-rename")
    old_home = os.path.expanduser(str(account.get("home_dir", "")).strip())
    new_home = _target_account_home(old_home, new_id)
    if os.path.exists(new_home):
        console.print(f"[red]目标目录已存在: {new_home}[/red]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if item.get("id") != old_id:
            updated_accounts.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_id
        renamed["home_dir"] = new_home
        updated_accounts.append(_normalize_account(renamed))
    updated_cfg["accounts"] = updated_accounts

    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in defaults.items():
        if value == old_id:
            defaults[cli_name] = new_id
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = _ensure_account_config(updated_cfg)

    if os.path.exists(old_home):
        os.makedirs(os.path.dirname(new_home), exist_ok=True)
        shutil.move(old_home, new_home)

    save_config(updated_cfg)
    _rename_usage_account(old_id, new_id, new_id, account.get("cli", ""))
    console.print(f"[green]✓ 已重命名账号档案: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]新目录: {new_home}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def _migrate_accounts_dirs(cfg):
    changed = False
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if not isinstance(item, dict):
            continue
        account = dict(item)
        home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
        target_home = _target_account_home(home_dir, account.get("id", "account"))
        if os.path.realpath(home_dir) != os.path.realpath(target_home):
            if os.path.exists(home_dir) and not os.path.exists(target_home):
                os.makedirs(os.path.dirname(target_home), exist_ok=True)
                shutil.move(home_dir, target_home)
            account["home_dir"] = target_home
            changed = True
        updated_accounts.append(_normalize_account(account))

    return updated_accounts, changed



def _handle_config_migrate():
    backup_dir = _backup_config_tree("config-migrate")
    cfg = load_config()
    if cfg is None:
        console.print("[yellow]未找到可迁移配置，当前无需执行 migrate[/yellow]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts, moved_accounts = _migrate_accounts_dirs(cfg)
    if moved_accounts:
        updated_cfg["accounts"] = updated_accounts
    save_config(updated_cfg)

    console.print("[green]✓ 配置迁移完成[/green]")
    console.print(f"[dim]config: {CONFIG_PATH}[/dim]")
    console.print(f"[dim]credentials: {_active_credentials_path()}[/dim]")
    console.print(f"[dim]usage: {_active_usage_path()}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


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
    console.print(CONFIG_PATH)


def _handle_config_validate(cfg):
    from mms_command_tools import handle_config_validate

    return handle_config_validate(cfg, validate_config=_validate_config, console=console)


# ── Main ────────────────────────────────────────────────

def _load_command_config():
    cfg = load_config()
    if cfg is None:
        cfg = _default_config()
        save_config(cfg)
    return apply_local_overrides(cfg)


def _session_status_label(item):
    from mms_command_tools import session_status_label

    return session_status_label(item)


def _session_display_id(item):
    from mms_command_tools import session_display_id

    return session_display_id(item)


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
    real_home = resolve_real_user_home()
    gateway_names = []
    if cli_name in {"all", "claude"}:
        gateway_names.append(("claude", "claude-gateway"))
    if cli_name in {"all", "codex"}:
        gateway_names.append(("codex", "codex-gateway"))
    if cli_name in {"all", "opencode"}:
        gateway_names.append(("opencode", "opencode-gateway"))
    return [
        (cli, os.path.join(real_home, ".config", "mms", gateway_name, "s"))
        for cli, gateway_name in gateway_names
    ]


def _session_dir_size_bytes(path):
    total = 0
    for root, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                if os.path.islink(file_path):
                    continue
                total += os.path.getsize(file_path)
            except OSError:
                continue
    return total


def _format_bytes(size):
    value = float(max(0, int(size or 0)))
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def _list_stale_gateway_sessions(cli_name):
    from mms_launchers import _session_home_is_active

    rows = []
    for cli, root in _session_gateway_roots(cli_name):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            session_home = os.path.join(root, name)
            if not os.path.isdir(session_home) or os.path.islink(session_home):
                continue
            if _session_home_is_active(session_home):
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(session_home)).isoformat(timespec="seconds")
            except OSError:
                mtime = "-"
            rows.append(
                {
                    "cli": cli,
                    "name": name,
                    "path": session_home,
                    "size": _session_dir_size_bytes(session_home),
                    "mtime": mtime,
                }
            )
    rows.sort(key=lambda item: (int(item.get("size") or 0), str(item.get("mtime") or "")), reverse=True)
    return rows


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
    ref = str(session_ref or "").strip()
    if ":" not in ref:
        return "", ref
    prefix, rest = ref.split(":", 1)
    prefix = prefix.strip().lower()
    rest = rest.strip()
    if prefix in {"codex", "claude"} and rest:
        return prefix, rest
    return "", ref


def _codex_resume_roots():
    roots = []

    def add(path):
        normalized = str(path or "").strip()
        if not normalized:
            return
        expanded = os.path.abspath(os.path.expanduser(normalized))
        if expanded not in roots:
            roots.append(expanded)

    for env_name in ("MMS_CODEX_RESUME_WRITEBACK_ROOT", "CODEX_HOME"):
        add(os.environ.get(env_name))
    real_home = resolve_real_user_home()
    add(os.path.join(real_home, ".config", "mms", "codex-gateway", ".codex"))
    add(os.path.join(real_home, ".codex"))
    return roots


def _iter_codex_index_records():
    seen = set()
    for root in _codex_resume_roots():
        path = os.path.join(root, "session_index.jsonl")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    session_id = str(item.get("id") or "").strip()
                    if not session_id or session_id in seen:
                        continue
                    seen.add(session_id)
                    payload = dict(item)
                    payload["_root"] = root
                    yield payload
        except OSError:
            continue


def _resolve_codex_resume_ref(session_ref, *, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    records = list(_iter_codex_index_records())
    exact = [item for item in records if str(item.get("id") or "").strip() == ref]
    if exact:
        return str(exact[0]["id"]), exact[0], None
    matches = [item for item in records if str(item.get("id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0], None
    if len(matches) > 1:
        return None, None, f"Codex session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Codex session: {ref}"


def _resolve_claude_resume_ref(session_ref, *, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    from mms_session_index import list_indexed_sessions

    sessions = [
        item for item in list_indexed_sessions(cli_name="claude")
        if str(item.get("session_id") or "").strip()
    ]
    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(sessions):
            item = sessions[index - 1]
            return str(item.get("session_id") or "").strip(), item, None
        return None, None, f"找不到第 {index} 条 Claude session"
    exact = [item for item in sessions if str(item.get("session_id") or "").strip() == ref]
    if exact:
        return str(exact[0].get("session_id") or "").strip(), exact[0], None
    matches = [item for item in sessions if str(item.get("session_id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0].get("session_id") or "").strip(), matches[0], None
    if len(matches) > 1:
        return None, None, f"Claude session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Claude session: {ref}"


def _resolve_resume_target(session_ref, cli_hint="auto"):
    prefix_cli, ref = _split_cli_prefixed_resume_ref(session_ref)
    cli_hint = prefix_cli or str(cli_hint or "auto").strip().lower()
    if cli_hint not in {"auto", "codex", "claude"}:
        return None, None, None, f"不支持的 CLI: {cli_hint}"
    if cli_hint == "codex":
        session_id, record, error = _resolve_codex_resume_ref(ref, allow_passthrough=True)
        return "codex", session_id, record, error
    if cli_hint == "claude":
        session_id, record, error = _resolve_claude_resume_ref(ref, allow_passthrough=True)
        return "claude", session_id, record, error

    codex_id, codex_record, codex_error = _resolve_codex_resume_ref(ref, allow_passthrough=False)
    claude_id, claude_record, claude_error = _resolve_claude_resume_ref(ref)
    if codex_id and not claude_id:
        return "codex", codex_id, codex_record, None
    if claude_id and not codex_id:
        return "claude", claude_id, claude_record, None
    if codex_id and claude_id:
        return None, None, None, f"session id 同时匹配 Codex 和 Claude，请使用 codex:{ref} 或 claude:{ref}"
    uuid_cli = _uuid_resume_cli_hint(ref)
    if uuid_cli == "codex":
        # Codex UUIDs are usually v7 and may not have been written back into
        # MMS' bounded index yet; pass the id through to native resume.
        return "codex", ref, {"id": ref, "_unindexed": True}, None
    if uuid_cli == "claude":
        # Claude Code prints v4 session UUIDs in "claude --resume <id>".
        return "claude", ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, None, codex_error or claude_error or f"找不到 session: {ref}"


def _uuid_resume_cli_hint(session_ref):
    ref = str(session_ref or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ref):
        return ""
    version = ref.split("-", 3)[2][:1]
    if version == "7":
        return "codex"
    if version == "4":
        return "claude"
    return ""


def _first_resume_model(cli_models, default_models, recommend=None):
    names = []
    for item in list(cli_models or []) + list(default_models or []):
        name = str(item.get("model") if isinstance(item, dict) else item or "").strip()
        if name and name not in names:
            names.append(name)
    for preferred in recommend or []:
        if preferred in names:
            return preferred
    return names[0] if names else ""


def _session_resume_model(session_record):
    if not isinstance(session_record, dict):
        return ""
    for key in ("resume_model", "selected_model", "display_model", "model"):
        value = str(session_record.get(key) or "").strip()
        if value:
            return value
    return ""


def _resolve_resume_runtime_and_model(
    cfg,
    cli,
    args,
    default_provider,
    default_models,
    session_record,
):
    requested_model = str(args.model or "").strip()
    if requested_model:
        model_info = {"model": requested_model}
    elif cli == "claude" and _session_resume_model(session_record):
        model_info = {"model": _session_resume_model(session_record)}
    else:
        last_by_cli, _scene_counts = _get_scene_usage()
        last_item = last_by_cli.get(cli)
        last_model_info = last_item.get("model_info") if isinstance(last_item, dict) else None
        model_info = last_model_info if isinstance(last_model_info, dict) else {}

    account_id = str(args.account or "").strip()
    provider_id = str(args.provider or "").strip()
    if cli == "claude" and not account_id and not provider_id and isinstance(session_record, dict):
        source_id = str(session_record.get("account_id") or "").strip()
        runtime_kind = str(session_record.get("runtime_kind") or "").strip()
        if source_id and runtime_kind == "api_key":
            provider_id = source_id
        elif source_id and runtime_kind == "oauth":
            account_id = source_id

    runtime = cli_models = launch_cli_name = None
    if not account_id and not provider_id:
        last_by_cli, _scene_counts = _get_scene_usage()
        last_item = last_by_cli.get(cli)
        runtime, cli_models, choice = _resolve_last_used_runtime(cfg, cli, last_item, default_models)
        if runtime is not None:
            launch_cli_name = cli
            _trace_runtime_choice("runtime resolve", runtime, launch_cli=cli, choice=choice)
    if runtime is None:
        runtime, cli_models, launch_cli_name = _choose_runtime_source(
            cfg,
            cli,
            default_provider,
            default_models,
            account_id=account_id or None,
            provider_id=provider_id or None,
            model_info=model_info or None,
            allow_selected_model_accounts=True,
        )

    if not isinstance(model_info, dict) or not _resolve_model_name(model_info):
        model_name = _first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        model_info = {"model": model_name} if model_name else {}
    if _resolve_model_name(model_info) == "official-default" and not _uses_managed_entry(runtime or {}, cli):
        model_name = _first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        if model_name:
            model_info = {"model": model_name}
    runtime = _runtime_with_launch_preferences(cfg, runtime, launch_cli_name or cli)
    return runtime, cli_models or [], launch_cli_name or cli, model_info


def handle_resume_command(argv, preloaded_command_cfg=None, bootstrap_cfg=None, lang_override=None):
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} resume",
        description="通过 Codex/Claude session id 一键恢复 MMS 托管会话",
    )
    parser.add_argument("session_ref", help="session id、前缀，或 codex:<id> / claude:<id>")
    parser.add_argument("prompt", nargs="*", help="恢复后追加给 CLI 的可选 prompt；若 prompt 以 -- 开头请先写 --")
    parser.add_argument("--cli", choices=["auto", "codex", "claude"], default="auto", help="强制指定恢复目标 CLI")
    parser.add_argument("--provider", help="临时指定 provider")
    parser.add_argument("--account", help="临时指定官方账号档案")
    parser.add_argument("--model", help="临时指定恢复时使用的模型")
    parser.add_argument("--once", action="store_true", help="以一次性会话模式启动底层 CLI")
    args = parser.parse_intermixed_args(argv)

    if args.account and args.provider:
        parser.error("--account 和 --provider 不能同时使用")

    cli, session_id, session_record, error = _resolve_resume_target(args.session_ref, args.cli)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    if cli not in {"codex", "claude"} or not session_id:
        console.print(f"[red]无法识别 session: {args.session_ref}[/red]")
        raise SystemExit(1)

    user_cfg = preloaded_command_cfg or bootstrap_cfg or load_config()
    if user_cfg is None:
        user_cfg = setup_wizard(_resolve_ui_language(None, lang_override))
    cfg = apply_local_overrides(user_cfg)
    set_language(_resolve_ui_language(cfg, lang_override))

    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _cli_models, launch_cli_name, model_info = _resolve_resume_runtime_and_model(
        cfg,
        cli,
        args,
        default_provider,
        models_cache,
        session_record,
    )
    if runtime is None:
        console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
        raise SystemExit(1)
    if launch_cli_name != cli:
        console.print(f"[red]resume 只支持原 CLI 恢复，当前解析为 {launch_cli_name}[/red]")
        raise SystemExit(1)
    if cli == "claude":
        project_path = str((session_record or {}).get("project_path") or (session_record or {}).get("cwd") or "").strip()
        if project_path and os.path.isdir(project_path):
            os.chdir(project_path)
        extra_args = ["--resume", session_id] + list(args.prompt or [])
    else:
        extra_args = ["resume", session_id] + list(args.prompt or [])

    source = "未写入 MMS index，交给 Codex 原生 resume 校验" if (session_record or {}).get("_unindexed") else "MMS index"
    console.print(f"[cyan]恢复 {cli} session:[/cyan] {session_id}")
    console.print(f"[dim]来源: {source}[/dim]")
    _launch_with_tracking(cli, model_info, runtime, once=bool(args.once), extra_args=extra_args)


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
    config_path = _config_write_target_path()
    current_snapshot = _build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = _config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = _config_snapshot_path("startup", "accepted.json", config_path=config_path)
    accepted_payload = _load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = _snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []
    if not diff_lines:
        console.print("[green]当前快照没有 drift，不需要 accept。[/green]")
        return False
    return _confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
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


def _is_session_prune_dry_run(argv):
    from mms_command_tools import is_session_prune_dry_run

    return is_session_prune_dry_run(argv)


def main():
    argv, lang_override = _extract_global_lang(sys.argv[1:])
    help_request = _is_help_request(argv) or _is_setup_web_request(argv)
    bootstrap_cfg = load_config()
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
        if command == "registry":
            from mms_registry_cli import handle_registry_command

            raise SystemExit(handle_registry_command(argv[1:], command_name=f"{current_command()} registry"))
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
                if not _is_config_help_request(argv[1:]):
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
                        help="CLI 名称(claude/codex/opencode/agy)")
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
        profile_to_launch = requested_opencode_profile
        entrypoint_to_launch = requested_opencode_entrypoint
        if target == "opencode" and not profile_to_launch:
            profile_to_launch, configured_entrypoint = _opencode_default_profile_from_config(cfg)
            if not entrypoint_to_launch:
                entrypoint_to_launch = configured_entrypoint

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
            runtime, cli_models, cli = _choose_runtime_source(
                cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=args.provider
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            if not check_cli_installed(cli):
                from mms_installer import check_and_offer_install
                check_and_offer_install(cli)
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
