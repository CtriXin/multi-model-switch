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
    if mms_config_root_is_explicit():
        return ""
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
    if mms_config_root_is_explicit():
        return ""
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
    value = str(tag or "").strip()
    if not value.startswith("v"):
        return None
    parts = value[1:].split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


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
    try:
        status_code = int(str(value or "").strip())
    except (TypeError, ValueError):
        return False
    return 200 <= status_code < 300


def _load_version_meta():
    return _load_json_file(VERSION_META_PATH, {})


def _load_update_check_cache():
    return _load_json_file(UPDATE_CHECK_PATH, {})


def _save_update_check_cache(payload):
    _save_json_file(UPDATE_CHECK_PATH, payload)


def _normalize_semver_tags(raw_tags):
    if not isinstance(raw_tags, list):
        return []

    normalized = []
    seen = set()
    for item in raw_tags:
        tag = str(item or "").strip()
        parsed = _parse_semver_tag(tag)
        if parsed is None or tag in seen:
            continue
        seen.add(tag)
        normalized.append((parsed, tag))

    normalized.sort(key=lambda item: item[0], reverse=True)
    return [tag for _, tag in normalized]


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
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value or ""))
    return match.group(0) if match else ""


def _parse_semver_text(value):
    version = _extract_semver_text(value)
    if not version:
        return None
    core = re.split(r"[-+]", version, maxsplit=1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _compare_semver_text(current, latest):
    current_semver = _parse_semver_text(current)
    latest_semver = _parse_semver_text(latest)
    if current_semver is None or latest_semver is None:
        return None
    if current_semver < latest_semver:
        return -1
    if current_semver > latest_semver:
        return 1
    return 0


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
    source = str(version_meta.get("source") or "").strip()
    install_channel = str(version_meta.get("install_channel") or "").strip()
    if source:
        is_install_managed = source in UPDATE_NOTICE_SOURCES
    else:
        is_install_managed = bool(install_channel)
    if not is_install_managed:
        return None, None

    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_semver = _parse_semver_tag(installed_version)
    if installed_semver is None:
        return None, None
    return installed_version, installed_semver


def _semver_tag_gap(installed_version, known_tags, latest_tag=""):
    installed_version = str(installed_version or "").strip()
    tags = _normalize_semver_tags(known_tags)
    if not tags:
        latest_semver = _parse_semver_tag(latest_tag)
        installed_semver = _parse_semver_tag(installed_version)
        if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
            return 0
        return None

    latest_tag = tags[0]
    latest_semver = _parse_semver_tag(latest_tag)
    installed_semver = _parse_semver_tag(installed_version)
    if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
        return 0

    try:
        return tags.index(installed_version)
    except ValueError:
        return len(tags)


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
    raw = str(model_name or "").strip().lower()
    # 拆出 '/' 后面的实际模型名
    parts = raw.rsplit("/", 1)
    candidates = [raw] if len(parts) == 1 else [raw, parts[-1]]
    for entry in MODEL_FAMILIES:
        for candidate in candidates:
            if any(kw in candidate for kw in entry["keywords"]):
                return entry["family"], entry["category"]
    return "其他", "其他"


def _model_info_looks_domestic(model_info):
    values = []
    if isinstance(model_info, dict):
        primary = str(model_info.get("model") or "").strip()
        if primary:
            values.append(primary)
        values.extend(
            str(value or "").strip()
            for key, value in model_info.items()
            if key not in {"subagent", "model"} and str(value or "").strip()
        )
    else:
        values.append(str(model_info or "").strip())

    for value in values:
        lower = value.lower()
        family, _ = _infer_model_family(value)
        if family in DOMESTIC_MODEL_FAMILIES:
            return True
        if any(keyword in lower for keyword in DOMESTIC_MODEL_KEYWORDS):
            return True
    return False


_MMS_HIDDEN_MODEL_FAMILIES = set()
_MMS_HIDDEN_MODELS = set()


def _mms_model_visible(model_name):
    normalized = str(model_name or "").strip()
    if not normalized:
        return True
    if normalized.lower() in _MMS_HIDDEN_MODELS:
        return False
    family, _ = _infer_model_family(normalized)
    return family not in _MMS_HIDDEN_MODEL_FAMILIES


def _filter_visible_models(models):
    return [
        str(model_name).strip()
        for model_name in (models or [])
        if str(model_name or "").strip() and _mms_model_visible(model_name)
    ]


def _model_info_has_visible_models(model_info):
    if isinstance(model_info, str):
        return _mms_model_visible(model_info)
    if not isinstance(model_info, dict):
        return True
    model_like_keys = ("model", "opus", "sonnet", "haiku", "subagent", "lb_light", "lb_medium")
    found_model = False
    for key in model_like_keys:
        value = str(model_info.get(key) or "").strip()
        if not value:
            continue
        found_model = True
        if _mms_model_visible(value):
            return True
    return not found_model


def _preset_has_visible_model_options(preset):
    return _model_info_has_visible_models(_preset_model_info(preset))


CLI_NAMES = ["claude", "codex", "opencode", "agy"]
CLI_MODEL_FAMILY_HINTS = {}
LB_SLOT_NAMES = ("heavy", "medium", "light")


def current_command():
    explicit = str(os.environ.get("MMS_COMMAND_NAME") or "").strip()
    if explicit:
        return explicit
    invoked = os.path.basename(str(sys.argv[0] or "")).strip()
    if invoked == "mmf":
        return "mmf"
    return PRIMARY_COMMAND


def display_title():
    return "MMF" if current_command() == "mmf" else "MMS"


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
    current = str(version_info.get("installed_version") or version_info.get("release") or "").strip()
    latest = str(cache.get("latest_tag") or "").strip()
    current_semver = _parse_semver_tag(current)
    latest_semver = _parse_semver_tag(latest)
    if current_semver is None:
        status = _L("开发版/无法判断", "dev/unknown")
        outdated = False
    elif latest_semver is None:
        status = _L("未检查 latest", "latest not checked")
        outdated = False
    elif current_semver < latest_semver:
        status = _L(f"有新版 {latest}", f"update available {latest}")
        outdated = True
    else:
        status = _L("最新", "latest")
        outdated = False
    return {
        "current": current or "dev",
        "latest": latest,
        "status": status,
        "outdated": outdated,
        "last_error": str(cache.get("last_error") or "").strip(),
    }


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
    status = str(status or "").strip()
    if not status:
        return ""
    if status.startswith(_L("有新版", "update available")):
        return _L("有新版", "update available")
    if status.startswith(_L("高于 latest", "newer than latest")):
        return _L("高于 latest", "newer than latest")
    return status


def _format_cli_about_line(cli_status):
    current = str(cli_status.get("version") or cli_status.get("label") or "").strip()
    status = _short_update_status_label(cli_status.get("status"))
    status_suffix = f" · {status}" if status else ""
    return f"{current}{status_suffix}".strip() or "-"


def _format_about_latest_value(status):
    latest = str((status or {}).get("latest") or "").strip()
    return latest or _L("未检查", "not checked")


def _about_check_error_summary(error_text):
    raw = str(error_text or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if "ssl" in lower or "handshake" in lower:
        return _L("MMS latest 检查失败：SSL handshake，可稍后重试", "MMS latest check failed: SSL handshake; retry later")
    if "timed out" in lower or "timeout" in lower:
        return _L("MMS latest 检查超时，可稍后重试", "MMS latest check timed out; retry later")
    if len(raw) > 72:
        raw = raw[:69].rstrip() + "..."
    return raw


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
    title, info_lines, _actions = _about_tui_payload(about_snapshot)
    console.print(f"[cyan]{title}[/cyan]")
    for label, value in info_lines:
        console.print(f"[cyan]{label}[/cyan] {value}")


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
    role = str(value or "auto").strip().lower()
    return role if role in VALID_ROLES else "auto"


def _normalize_positive_seconds(value, default, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _default_provider():
    return {
        "id": DEFAULT_PROVIDER_ID,
        "name": "Default Gateway",
        "protocols": list(DEFAULT_PROVIDER_PROTOCOLS),
        "supported_clis": list(PROVIDER_CAPABLE_CLIS),
        "enabled": True,
        "role": "auto",
    }


def _normalize_supported_clis(value, protocols=None):
    if isinstance(value, str):
        raw_items = [value]
    else:
        raw_items = list(value or [])
    protocol_set = {str(item).strip() for item in (protocols or []) if str(item).strip()}
    normalized = []
    seen = set()

    def add(cli_name):
        if cli_name in CLI_NAMES and cli_name not in seen:
            normalized.append(cli_name)
            seen.add(cli_name)

    for item in raw_items:
        cli_name = str(item or "").strip().lower()
        if not cli_name:
            continue
        if cli_name in LEGACY_PROVIDER_CLI_ALIASES:
            if "anthropic_messages" in protocol_set:
                add("claude")
            if "openai_chat_completions" in protocol_set:
                add("codex")
            continue
        add(cli_name)
    return normalized


def _default_account_home(account_id):
    return os.path.join(ACCOUNTS_DIR, account_id)


def _normalize_priority(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY


def _canonical_model_family(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    for entry in MODEL_FAMILIES:
        family = str(entry.get("family") or "").strip()
        if family.lower() == raw:
            return family
    return ""


def _normalize_family_priority_overrides(value):
    if not isinstance(value, dict):
        return {}
    normalized = {}
    for family_name, priority in value.items():
        canonical = _canonical_model_family(family_name)
        if not canonical:
            continue
        normalized[canonical] = _normalize_priority(priority)
    return normalized


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
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in VALID_CLAUDE_1M_MODES else "auto"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in VALID_CLAUDE_1M_MODES else "auto"


def _normalize_timezone_name(value, default=DEFAULT_ACCOUNT_TIMEZONE):
    timezone_name = str(value or "").strip() or default
    if timezone_name:
        try:
            ZoneInfo(timezone_name)
        except Exception:
            timezone_name = default
    return timezone_name


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
    raw = False if not isinstance(runtime, dict) else runtime.get("force_ipv4", False)
    if isinstance(raw, bool):
        return raw
    value = str(raw or "").strip().lower()
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if value in {"1", "true", "yes", "on", "enable", "enabled", ""}:
        return True
    return False


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
    value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(account_id or "").strip().lower())
    value = value.strip("-_")
    return value or "account"


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
    cli = str(account.get("cli") or "claude").strip().lower()
    if cli not in OAUTH_CAPABLE_CLIS:
        cli = "claude"
    account_id = _normalize_account_id(account.get("id") or f"{cli}-account")
    home_dir = str(account.get("home_dir") or _default_account_home(account_id)).strip() or _default_account_home(account_id)
    proxy = str(account.get("proxy") or "").strip()
    no_proxy = str(account.get("no_proxy") or "").strip()
    timezone_name = _normalize_timezone_name(account.get("timezone"), DEFAULT_ACCOUNT_TIMEZONE)
    return {
        "id": account_id,
        "name": str(account.get("name") or account_id).strip() or account_id,
        "cli": cli,
        "auth_mode": "oauth",
        "enabled": bool(account.get("enabled", True)),
        "home_dir": os.path.expanduser(home_dir),
        "priority": _normalize_priority(account.get("priority", DEFAULT_PRIORITY)),
        "family_priority_overrides": _normalize_family_priority_overrides(
            account.get("family_priority_overrides", {})
        ),
        "claude_1m_mode": _normalize_claude_1m_mode(account.get("claude_1m_mode", "auto")),
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "force_ipv4": _runtime_force_ipv4(account),
        "note": str(account.get("note", "")).strip(),
    }


def _normalize_provider_id_input(provider_id):
    value = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(provider_id or "").strip().lower()
    )
    value = value.strip("-_")
    return value or DEFAULT_PROVIDER_ID


def _sanitize_provider_id(provider_id):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id).upper())
    cleaned = cleaned.strip("_")
    return cleaned or DEFAULT_PROVIDER_ID.upper()


def _normalize_model_id_list(values):
    if isinstance(values, str):
        values = [chunk.strip() for chunk in values.split(",")]
    normalized = []
    seen = set()
    for item in values or []:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return normalized


def _unique_runtime_id(existing_ids, base_id):
    normalized = str(base_id or "").strip()
    if not normalized:
        normalized = "default"
    if normalized not in existing_ids:
        return normalized
    suffix = 2
    while True:
        candidate = f"{normalized}-{suffix}"
        if candidate not in existing_ids:
            return candidate
        suffix += 1


def _normalize_models_endpoint(value):
    endpoint = str(value or "").strip()
    if not endpoint:
        return "/models"
    if endpoint.lower() in {"manual", "none", "off"}:
        return "manual"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def _model_source_label(source):
    mapping = {
        "remote": "远端列表",
        "fallback": "内置回退",
        "manual": "手工列表",
        "extra": "手工补充",
        "derived_alias": "本地别名",
    }
    return mapping.get(str(source or "").strip(), str(source or "-").strip() or "-")


def _ttfb_label(ttfb_ms):
    if not isinstance(ttfb_ms, (int, float)):
        return "暂无数据"
    if ttfb_ms < 1200:
        return "很快"
    if ttfb_ms < 2500:
        return "正常"
    if ttfb_ms < 4500:
        return "偏慢"
    return "很慢"


def _tps_label(tps_value):
    if not isinstance(tps_value, (int, float)):
        return "暂无数据"
    if tps_value >= 80:
        return "很快"
    if tps_value >= 40:
        return "正常"
    if tps_value >= 20:
        return "偏慢"
    return "很慢"


def _provider_env_name(provider_id, field):
    return f"MMS_PROVIDER_{_sanitize_provider_id(provider_id)}_{field}"


def _provider_env_value(provider_id, field):
    """读取 provider 环境变量。"""
    return os.environ.get(_provider_env_name(provider_id, field), "").strip()


def _normalize_provider(provider):
    merged = dict(_default_provider())
    merged.update(provider)
    merged.pop("cost_level", None)
    merged.pop("daily_budget", None)
    merged["id"] = str(merged.get("id") or DEFAULT_PROVIDER_ID).strip() or DEFAULT_PROVIDER_ID
    merged["name"] = str(merged.get("name") or merged["id"]).strip() or merged["id"]

    protocols = merged.get("protocols", DEFAULT_PROVIDER_PROTOCOLS)
    if isinstance(protocols, str):
        protocols = [protocols]
    merged["protocols"] = [str(item).strip() for item in protocols if str(item).strip()]
    if not merged["protocols"]:
        merged["protocols"] = list(DEFAULT_PROVIDER_PROTOCOLS)

    merged["supported_clis"] = _normalize_supported_clis(
        merged.get("supported_clis", PROVIDER_CAPABLE_CLIS),
        protocols=merged["protocols"],
    )
    if not merged["supported_clis"]:
        merged["supported_clis"] = list(PROVIDER_CAPABLE_CLIS)

    merged["enabled"] = bool(merged.get("enabled", True))
    merged["priority"] = _normalize_priority(merged.get("priority", DEFAULT_PRIORITY))
    merged["family_priority_overrides"] = _normalize_family_priority_overrides(
        merged.get("family_priority_overrides", {})
    )
    merged["claude_1m_mode"] = _normalize_claude_1m_mode(merged.get("claude_1m_mode", "auto"))
    merged["proxy"] = str(merged.get("proxy", "")).strip()
    merged["no_proxy"] = str(merged.get("no_proxy", "")).strip()
    merged["timezone"] = _normalize_timezone_name(merged.get("timezone"), DEFAULT_ACCOUNT_TIMEZONE)
    merged["force_ipv4"] = _runtime_force_ipv4(merged)
    merged["note"] = str(merged.get("note", "")).strip()
    merged["default_openai_base_url"] = str(merged.get("default_openai_base_url", "")).strip().rstrip("/")
    merged["default_anthropic_base_url"] = str(merged.get("default_anthropic_base_url", "")).strip().rstrip("/")
    merged["fallback_models"] = _normalize_model_id_list(merged.get("fallback_models", []))
    merged["extra_models"] = _normalize_model_id_list(merged.get("extra_models", []))
    merged["hidden_models"] = _normalize_model_id_list(merged.get("hidden_models", []))
    merged["models_endpoint"] = _normalize_models_endpoint(merged.get("models_endpoint", "/models"))
    return merged


def _ensure_provider_config(cfg):
    cfg = dict(cfg)
    raw_providers = cfg.get("providers")
    normalized = []
    seen_ids = set()

    if isinstance(raw_providers, list):
        for item in raw_providers:
            if not isinstance(item, dict):
                continue
            provider = _normalize_provider(item)
            if provider["id"] in seen_ids:
                continue
            normalized.append(provider)
            seen_ids.add(provider["id"])

    if not normalized:
        normalized = [_default_provider()]

    provider_cfg = cfg.get("provider", {})
    default_provider = DEFAULT_PROVIDER_ID
    if isinstance(provider_cfg, dict):
        default_provider = str(provider_cfg.get("default") or DEFAULT_PROVIDER_ID).strip() or DEFAULT_PROVIDER_ID
    if default_provider not in seen_ids and default_provider not in {p["id"] for p in normalized}:
        default_provider = normalized[0]["id"]

    new_cfg = dict(cfg)
    new_cfg["providers"] = normalized
    new_cfg["provider"] = {"default": default_provider}
    changed = new_cfg != cfg
    return new_cfg, changed


def _ensure_account_config(cfg):
    cfg = dict(cfg)
    raw_accounts = cfg.get("accounts")
    normalized = []
    seen_ids = set()

    if isinstance(raw_accounts, list):
        for item in raw_accounts:
            if not isinstance(item, dict):
                continue
            account = _normalize_account(item)
            if account["id"] in seen_ids:
                continue
            normalized.append(account)
            seen_ids.add(account["id"])

    raw_defaults = cfg.get("account", {})
    defaults = {}
    if isinstance(raw_defaults, dict):
        raw_cli_defaults = raw_defaults.get("defaults", raw_defaults)
        if isinstance(raw_cli_defaults, dict):
            for cli in OAUTH_CAPABLE_CLIS:
                account_id = str(raw_cli_defaults.get(cli, "")).strip()
                if account_id:
                    defaults[cli] = account_id

    defaults = {
        cli: account_id for cli, account_id in defaults.items()
        if account_id in seen_ids
    }

    new_cfg = dict(cfg)
    new_cfg["accounts"] = normalized
    new_cfg["account"] = {"defaults": defaults}
    changed = new_cfg != cfg
    return new_cfg, changed


def _normalize_preset_entry(name, preset):
    if isinstance(preset, str):
        preset = {"cli": "claude", "model": preset}
    elif not isinstance(preset, dict):
        preset = {"cli": "claude"}

    normalized = {"cli": str(preset.get("cli") or "claude").strip().lower() or "claude"}

    description = str(preset.get("description") or "").strip()
    if description:
        normalized["description"] = description

    provider = str(preset.get("provider") or "").strip()
    if provider:
        normalized["provider"] = provider

    account = str(preset.get("account") or "").strip()
    if account:
        normalized["account"] = _normalize_account_id(account)

    bridge = str(preset.get("bridge") or "").strip()
    if bridge:
        normalized["bridge"] = bridge

    model = str(preset.get("model") or "").strip()
    if not model:
        for legacy_key in ("sonnet", "opus", "haiku"):
            value = str(preset.get(legacy_key) or "").strip()
            if value:
                model = value
                break
    if model:
        normalized["model"] = model

    for key, value in preset.items():
        if key in {"cli", "description", "provider", "account", "bridge", "model", "sonnet", "opus", "haiku"}:
            continue
        normalized[key] = value

    return normalized


def _normalize_presets_config(cfg):
    raw_presets = cfg.get("presets")
    if raw_presets is None:
        return cfg, False
    if not isinstance(raw_presets, dict):
        updated = dict(cfg)
        updated["presets"] = {}
        return updated, True

    normalized = {}
    changed = False
    for name, preset in raw_presets.items():
        normalized_name = str(name).strip()
        if not normalized_name:
            changed = True
            continue
        normalized_preset = _normalize_preset_entry(normalized_name, preset)
        normalized[normalized_name] = normalized_preset
        if normalized_name != name or normalized_preset != preset:
            changed = True

    if not changed:
        return cfg, False

    updated = dict(cfg)
    updated["presets"] = normalized
    return updated, True


def _normalize_load_balance_slot(slot):
    if isinstance(slot, str):
        model = slot.strip()
        return {"model": model} if model else {}
    if not isinstance(slot, dict):
        return {}

    normalized = {}
    model = str(slot.get("model") or "").strip()
    if model:
        normalized["model"] = model
    provider = str(slot.get("provider") or "").strip()
    if provider:
        normalized["provider"] = provider
    for key, value in slot.items():
        if key in {"model", "provider"}:
            continue
        normalized[key] = value
    return normalized


def _normalize_load_balance_profile(name, profile):
    if not isinstance(profile, dict):
        profile = {}

    normalized = {}
    label = str(profile.get("label") or name).strip()
    if label:
        normalized["label"] = label

    raw_slots = profile.get("slots")
    if isinstance(raw_slots, list):
        slots = [str(item).strip() for item in raw_slots if str(item).strip()]
        normalized["slots"] = slots or list(LB_SLOT_NAMES)
    else:
        normalized["slots"] = list(LB_SLOT_NAMES)

    for slot_name in LB_SLOT_NAMES:
        slot_value = _normalize_load_balance_slot(profile.get(slot_name))
        if slot_value:
            normalized[slot_name] = slot_value

    for key, value in profile.items():
        if key in {"label", "slots", *LB_SLOT_NAMES}:
            continue
        normalized[key] = value
    return normalized


def _normalize_load_balance_config(cfg):
    raw = cfg.get("load_balance")
    if raw is None:
        return cfg, False
    if not isinstance(raw, dict):
        updated = dict(cfg)
        updated["load_balance"] = {}
        return updated, True

    normalized_profiles = {}
    raw_profiles = raw.get("profiles")
    if isinstance(raw_profiles, dict):
        for name, profile in raw_profiles.items():
            normalized_name = str(name).strip()
            if not normalized_name:
                continue
            normalized_profiles[normalized_name] = _normalize_load_balance_profile(normalized_name, profile)

    default_name = str(raw.get("default") or "").strip()
    if default_name not in normalized_profiles:
        default_name = next(iter(normalized_profiles), "")

    normalized = {k: v for k, v in raw.items() if k not in {"default", "profiles"}}
    normalized["default"] = default_name
    normalized["profiles"] = normalized_profiles

    if normalized == raw:
        return cfg, False

    updated = dict(cfg)
    updated["load_balance"] = normalized
    return updated, True


def _load_balance_profiles(cfg):
    section = cfg.get("load_balance", {})
    if not isinstance(section, dict):
        return {}
    profiles = section.get("profiles")
    return profiles if isinstance(profiles, dict) else {}


def _default_load_balance_profile_name(cfg):
    section = cfg.get("load_balance", {})
    if not isinstance(section, dict):
        return ""
    return str(section.get("default") or "").strip()


def _normalize_config_sections(cfg):
    cfg, _ = _ensure_provider_config(cfg)
    cfg, _ = _ensure_account_config(cfg)
    cfg, _ = ensure_broker_config(cfg)
    cfg, _ = _normalize_ui_config(cfg)
    cfg, _ = _normalize_presets_config(cfg)
    cfg, _ = _normalize_user_config(cfg)
    cfg, _ = _normalize_cache_config(cfg)
    cfg, _ = _normalize_load_balance_config(cfg)
    return cfg


def _format_load_balance_slot(slot):
    if isinstance(slot, str):
        return slot.strip()
    if not isinstance(slot, dict):
        return "-"
    model = str(slot.get("model") or "").strip()
    provider = str(slot.get("provider") or "").strip()
    if model and provider:
        return f"{model} @ {provider}"
    return model or "-"


def _display_load_balance_profiles(cfg):
    profiles = _load_balance_profiles(cfg)
    default_name = _default_load_balance_profile_name(cfg)
    if not profiles:
        console.print("[yellow]当前未配置 load_balance profiles[/yellow]")
        console.print(
            f"[dim]可用命令: {current_command()} config load-balance.profile.add <name> <heavy> [medium] [light][/dim]"
        )
        return

    _ensure_rich()
    table = Table(title="Load Balance Profiles", show_lines=True)
    table.add_column("名称", style="cyan")
    table.add_column("标签", style="green")
    table.add_column("默认", style="yellow", width=6)
    table.add_column("Heavy", style="magenta")
    table.add_column("Medium", style="white")
    table.add_column("Light", style="blue")
    for name, profile in profiles.items():
        table.add_row(
            name,
            str(profile.get("label") or name),
            "yes" if name == default_name else "",
            _format_load_balance_slot(profile.get("heavy")),
            _format_load_balance_slot(profile.get("medium")),
            _format_load_balance_slot(profile.get("light")),
        )
    console.print(table)


def _handle_load_balance_show_config(cfg):
    _display_load_balance_profiles(cfg)


def _handle_load_balance_default_config(cfg, args_rest):
    profiles = _load_balance_profiles(cfg)
    if not args_rest:
        default_name = _default_load_balance_profile_name(cfg)
        if not default_name:
            console.print("[yellow]当前未设置默认 load_balance profile[/yellow]")
        else:
            console.print(f"[cyan]load_balance.default[/cyan] = {default_name}")
        return

    profile_name = str(args_rest[0] or "").strip()
    if not profile_name:
        console.print(f"[red]用法: {current_command()} config load-balance.default <name>[/red]")
        return
    if profile_name not in profiles:
        console.print(f"[red]未找到 load_balance profile: {profile_name}[/red]")
        if profiles:
            console.print(f"[dim]可用 profile: {', '.join(profiles.keys())}[/dim]")
        return

    updated_cfg = dict(cfg)
    section = dict(updated_cfg.get("load_balance", {}))
    section["default"] = profile_name
    updated_cfg["load_balance"] = section
    updated_cfg = _normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ load_balance.default = {profile_name}[/green]")


def _handle_load_balance_profile_add_config(cfg, args_rest):
    if len(args_rest) < 2:
        console.print(
            f"[red]用法: {current_command()} config load-balance.profile.add <name> <heavy> [medium] [light][/red]"
        )
        return

    profile_name = str(args_rest[0] or "").strip()
    heavy = str(args_rest[1] or "").strip()
    medium = str(args_rest[2] or "").strip() if len(args_rest) >= 3 else ""
    light = str(args_rest[3] or "").strip() if len(args_rest) >= 4 else ""
    if not profile_name or not heavy:
        console.print(
            f"[red]用法: {current_command()} config load-balance.profile.add <name> <heavy> [medium] [light][/red]"
        )
        return

    updated_cfg = dict(cfg)
    section = dict(updated_cfg.get("load_balance", {}))
    profiles = dict(section.get("profiles", {}))
    existing = profiles.get(profile_name, {})
    profile = {
        "label": str(existing.get("label") or profile_name),
        "slots": list(LB_SLOT_NAMES),
        "heavy": {"model": heavy},
    }
    if medium:
        profile["medium"] = {"model": medium}
    elif isinstance(existing, dict) and existing.get("medium"):
        profile["medium"] = existing.get("medium")
    if light:
        profile["light"] = {"model": light}
    elif isinstance(existing, dict) and existing.get("light"):
        profile["light"] = existing.get("light")

    for slot_name in LB_SLOT_NAMES:
        existing_slot = existing.get(slot_name) if isinstance(existing, dict) else None
        if isinstance(existing_slot, dict) and existing_slot.get("provider") and slot_name in profile:
            slot = dict(profile[slot_name])
            slot["provider"] = existing_slot.get("provider")
            profile[slot_name] = slot

    profiles[profile_name] = profile
    section["profiles"] = profiles
    if not str(section.get("default") or "").strip():
        section["default"] = profile_name
    updated_cfg["load_balance"] = section
    updated_cfg = _normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已保存 load_balance profile: {profile_name}[/green]")


def _handle_load_balance_profile_remove_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config load-balance.profile.remove <name>[/red]")
        return

    profile_name = str(args_rest[0] or "").strip()
    profiles = _load_balance_profiles(cfg)
    if profile_name not in profiles:
        console.print(f"[red]未找到 load_balance profile: {profile_name}[/red]")
        return

    updated_cfg = dict(cfg)
    section = dict(updated_cfg.get("load_balance", {}))
    updated_profiles = dict(section.get("profiles", {}))
    updated_profiles.pop(profile_name, None)
    if updated_profiles:
        section["profiles"] = updated_profiles
        if str(section.get("default") or "").strip() == profile_name:
            section["default"] = next(iter(updated_profiles))
        updated_cfg["load_balance"] = section
    else:
        updated_cfg.pop("load_balance", None)
    updated_cfg = _normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已删除 load_balance profile: {profile_name}[/green]")


def _normalize_user_config(cfg):
    user_cfg = cfg.get("user", {})
    if not isinstance(user_cfg, dict):
        new_cfg = dict(cfg)
        new_cfg["user"] = {"role": MODE_ALL}
        return new_cfg, True

    normalized_role = normalize_user_role(user_cfg.get("role", MODE_ALL))
    if user_cfg.get("role") == normalized_role:
        return cfg, False

    new_cfg = dict(cfg)
    new_user = dict(user_cfg)
    new_user["role"] = normalized_role
    new_cfg["user"] = new_user
    return new_cfg, True


def _normalize_cache_config(cfg):
    cache_cfg = cfg.get("cache", {})
    if not isinstance(cache_cfg, dict):
        cache_cfg = {}

    normalized = {
        "probe_async_refresh_after_sec": _normalize_positive_seconds(
            cache_cfg.get("probe_async_refresh_after_sec", _PROBE_ASYNC_REFRESH_AFTER),
            _PROBE_ASYNC_REFRESH_AFTER,
        ),
        "probe_async_min_interval_sec": _normalize_positive_seconds(
            cache_cfg.get("probe_async_min_interval_sec", _PROBE_ASYNC_MIN_INTERVAL),
            _PROBE_ASYNC_MIN_INTERVAL,
        ),
    }

    if cache_cfg == normalized:
        return cfg, False

    new_cfg = dict(cfg)
    new_cfg["cache"] = normalized
    return new_cfg, True


def _provider_map(cfg):
    providers = cfg.get("providers", [])
    return {provider["id"]: provider for provider in providers if isinstance(provider, dict) and provider.get("id")}


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
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    if normalized.startswith("claude-"):
        return ["claude"]
    if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
        return ["codex"]
    return []


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
    family, _ = _infer_model_family(model_name)
    if family == "Unknown":
        return []
    native = set(_native_clis_for_model(model_name))
    bridge = []
    for cli_name in ("claude", "codex"):
        if cli_name not in native:
            bridge.append(cli_name)
    return bridge


def _model_capability_tags(model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    family, _ = _infer_model_family(model_name)
    tags = []
    if _model_supports_vision(model_name):
        tags.append("vision")
    if family in _TOOL_USE_FAMILIES:
        tags.append("tool_use")
    if any(hint in normalized for hint in _REASONING_MODEL_HINTS):
        tags.append("reasoning")
    context_window = _model_context_window(model_name)
    if context_window and context_window >= 200_000:
        tags.append("long_context")
    if "claude" in _bridge_clis_for_model(model_name):
        tags.append("bridge_required")
    return tags


def _model_supports_vision(model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    model_id = normalized.rsplit("/", 1)[-1]
    if model_id in _VISION_CAPABLE_MODEL_NAMES:
        return True
    return any(hint in model_id for hint in _VISION_CAPABLE_MODEL_HINTS)


def _model_cli_modes(model_name):
    native = set(_native_clis_for_model(model_name))
    bridge = set(_bridge_clis_for_model(model_name))
    modes = {}
    for cli_name in ("claude", "codex"):
        if cli_name in native:
            modes[cli_name] = "native"
        elif cli_name in bridge:
            modes[cli_name] = "bridge"
        else:
            modes[cli_name] = "unsupported"
    return modes


def _model_cli_summary(model_name):
    modes = _model_cli_modes(model_name)
    parts = []
    for cli_name in ("claude", "codex"):
        mode = modes.get(cli_name)
        if mode == "native":
            parts.append(f"{cli_name}:native")
        elif mode == "bridge":
            parts.append(f"{cli_name}:bridge")
    return ", ".join(parts) if parts else "-"


def _model_capability_summary(model_name):
    tags = _model_capability_tags(model_name)
    return ", ".join(tags) if tags else "-"


def _account_map(cfg):
    accounts = cfg.get("accounts", [])
    return {account["id"]: account for account in accounts if isinstance(account, dict) and account.get("id")}


def _accounts_for_cli(cfg, cli_name):
    return [
        account for account in _account_map(cfg).values()
        if account.get("cli") == cli_name and account.get("enabled", True)
    ]


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
    return """# AGENTS.md

This folder stores the real MMS user config.

## MMS Config Human Gate

- Any agent, any repo, any automation touching this folder must stop and require human confirmation before write.
- Before every write, create a timestamped backup first. Never overwrite in place without a backup.
- Applies to the whole MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and any account state under this folder.
- Agents may inspect, diff, and propose changes, but must not auto-apply user config edits without human confirmation.
- Any proposed change must show target path, affected fields/files, before/after values, and reason.
- If the process is running inside an isolated HOME or gateway session, still resolve and protect the real user config under `~/.config/mms`.
"""


def _render_mms_config_claude_guard():
    return """# CLAUDE.md

This folder stores the real MMS user config.

## Claude Hard Rule

- Claude must treat this folder as human-only config.
- Claude must never auto-write MMS user config without explicit human confirmation.
- Before every write, Claude must create a timestamped backup first.
- Claude may only inspect, explain, and generate manual diffs for changes to this folder until the human confirms.
- This applies to the full MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and account state files.
- If Claude is about to touch these files, it must stop and report the exact path, intended change, before/after values, and reason.
"""


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
    diffs = []
    previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current_snapshot = current_snapshot if isinstance(current_snapshot, dict) else {}

    previous_defaults = previous_snapshot.get("defaults") or {}
    current_defaults = current_snapshot.get("defaults") or {}
    if previous_defaults != current_defaults:
        diffs.append("default route/account changed")

    previous_accounts = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    current_accounts = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    for account_id in sorted(set(previous_accounts) | set(current_accounts)):
        previous_entry = previous_accounts.get(account_id)
        current_entry = current_accounts.get(account_id)
        if previous_entry is None:
            diffs.append(f"account added: {account_id}")
            continue
        if current_entry is None:
            diffs.append(f"account removed: {account_id}")
            continue
        field_labels = {
            "cli": "cli",
            "enabled": "enabled",
            "home_dir": "home_dir",
            "priority": "priority",
            "claude_1m_mode": "claude_1m_mode",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
            "identity_sha256": "identity",
        }
        for field_name, field_label in field_labels.items():
            if field_name == "identity_sha256":
                previous_value = previous_entry.get(field_name, "")
                current_value = current_entry.get(field_name, "")
            else:
                previous_value = previous_entry.get(field_name)
                current_value = current_entry.get(field_name)
            if field_name == "identity_sha256" and field_name not in previous_entry:
                continue
            if previous_value != current_value:
                if field_name == "proxy_sha256":
                    old_value = previous_entry.get("proxy_fingerprint")
                    new_value = current_entry.get("proxy_fingerprint")
                elif field_name == "identity_sha256":
                    old_value = previous_entry.get("identity_fingerprint")
                    new_value = current_entry.get("identity_fingerprint")
                else:
                    old_value = previous_entry.get(field_name)
                    new_value = current_entry.get(field_name)
                diffs.append(f"account {account_id} {field_label}: {old_value} -> {new_value}")

    previous_providers = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    current_providers = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    for provider_id in sorted(set(previous_providers) | set(current_providers)):
        previous_entry = previous_providers.get(provider_id)
        current_entry = current_providers.get(provider_id)
        if previous_entry is None:
            diffs.append(f"provider added: {provider_id}")
            continue
        if current_entry is None:
            diffs.append(f"provider removed: {provider_id}")
            continue
        field_labels = {
            "enabled": "enabled",
            "priority": "priority",
            "models_endpoint": "models_endpoint",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
        }
        for field_name, field_label in field_labels.items():
            if previous_entry.get(field_name) != current_entry.get(field_name):
                old_value = previous_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else previous_entry.get(field_name)
                new_value = current_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else current_entry.get(field_name)
                diffs.append(f"provider {provider_id} {field_label}: {old_value} -> {new_value}")

    previous_files = {
        str(item.get("path") or ""): item
        for item in previous_snapshot.get("files", [])
        if isinstance(item, dict) and not _is_snapshot_ignored_file(item.get("path"))
    }
    current_files = {
        str(item.get("path") or ""): item
        for item in current_snapshot.get("files", [])
        if isinstance(item, dict) and not _is_snapshot_ignored_file(item.get("path"))
    }
    for path in sorted(set(previous_files) | set(current_files)):
        if os.path.basename(str(path or "")) == ".claude.json":
            continue
        previous_entry = previous_files.get(path)
        current_entry = current_files.get(path)
        if previous_entry is None:
            diffs.append(f"file added: {path}")
            continue
        if current_entry is None:
            diffs.append(f"file removed: {path}")
            continue
        if bool(previous_entry.get("exists")) != bool(current_entry.get("exists")):
            diffs.append(f"file presence changed: {path}")
            continue
        if previous_entry.get("sha256") != current_entry.get("sha256"):
            diffs.append(f"file changed: {path}")
    return diffs


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
    cfg, lb_changed = _normalize_load_balance_config(cfg)
    changed = changed or gateway_broker_changed or account_changed or broker_changed or preset_changed or role_changed or cache_changed or lb_changed
    if changed and persist:
        save_config(cfg, reason="auto:load_config_normalize")
    return cfg


def load_runtime_config():
    cfg = _load_config_or_preview_bundle()
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
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def _pref_bool(value):
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def _pref_enable_disable(value):
    enabled = _pref_bool(value)
    if enabled is True:
        return "enable"
    if enabled is False:
        return "disable"
    raw = str(value or "").strip().lower()
    if raw in {"enable", "enabled", "disable", "disabled"}:
        return "enable" if raw.startswith("enable") else "disable"
    return ""


def _pref_reasoning_effort(value):
    raw = str(value or "").strip().lower()
    return raw if raw in {"low", "medium", "high", "xhigh"} else ""


def _pref_agent_pack(value):
    if value is None:
        return ""
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    if raw in {"none", "off", "disable", "disabled", "false", "0"}:
        return "none"
    if raw in {"ecc", "everything-claude-code"}:
        return "ecc"
    if raw in {"omc", "oh-my-claudecode", "oh-my-claude-code"}:
        return "omc"
    return ""


def _sanitize_surface_list(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    result = []
    seen = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _sanitize_disabled_session_surfaces(payload):
    payload = payload if isinstance(payload, dict) else {}
    aliases = {
        "mcp": "mcp",
        "mcps": "mcp",
        "mcp_servers": "mcp",
        "skills": "skills",
        "skill": "skills",
        "hooks": "hooks",
        "hook": "hooks",
    }
    result = {}
    for key, values in payload.items():
        normalized_key = aliases.get(str(key or "").strip().lower())
        if not normalized_key:
            continue
        cleaned = _sanitize_surface_list(values)
        if cleaned:
            result[normalized_key] = cleaned
    return result


def _sanitize_launch_preferences(payload):
    payload = payload if isinstance(payload, dict) else {}
    result = {}
    thinking_mode = _pref_enable_disable(payload.get("thinking_mode"))
    if thinking_mode:
        result["thinking_mode"] = thinking_mode
    effort = _pref_reasoning_effort(payload.get("reasoning_effort"))
    if effort:
        result["reasoning_effort"] = effort
    caveman_mode = _pref_enable_disable(payload.get("caveman_mode"))
    if caveman_mode:
        result["caveman_mode"] = caveman_mode
    nsr_mode = _pref_enable_disable(payload.get("nsr_mode"))
    if nsr_mode:
        result["nsr_mode"] = nsr_mode
    bypass = _pref_bool(payload.get("bypass"))
    if bypass is not None:
        result["bypass"] = bypass

    agent_pack = _pref_agent_pack(payload.get("agent_pack"))
    if not agent_pack and _pref_enable_disable(payload.get("omc_mode")) == "enable":
        agent_pack = "omc"
    if not agent_pack and _pref_enable_disable(payload.get("ecc_mode")) == "enable":
        agent_pack = "ecc"
    if agent_pack:
        result["agent_pack"] = agent_pack
        result["ecc_mode"] = "enable" if agent_pack == "ecc" else "disable"
        result["omc_mode"] = "enable" if agent_pack == "omc" else "disable"

    surfaces = _sanitize_disabled_session_surfaces(payload.get("disabled_session_surfaces"))
    if surfaces:
        result["disabled_session_surfaces"] = surfaces
    return result


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
    payload = payload if isinstance(payload, dict) else {}
    result = {}
    for key, value in payload.items():
        normalized_key = _PREFERENCE_ASSET_ROOT_KEYS.get(str(key or "").strip().lower())
        path = str(value or "").strip()
        if not normalized_key or not path:
            continue
        result[normalized_key] = os.path.abspath(os.path.expanduser(path))
    return result


def _sanitize_user_preferences(raw):
    raw = raw if isinstance(raw, dict) else {}
    launch = raw.get("launch") if isinstance(raw.get("launch"), dict) else {}
    session_surfaces = raw.get("session_surfaces") if isinstance(raw.get("session_surfaces"), dict) else {}
    assets = raw.get("assets") if isinstance(raw.get("assets"), dict) else {}

    result = {"launch": {"defaults": {}, "cli": {}}, "session_surfaces": {"disabled": {}}, "assets": {"roots": {}}}
    result["launch"]["defaults"] = _sanitize_launch_preferences(launch.get("defaults"))
    cli_tables = launch.get("cli") if isinstance(launch.get("cli"), dict) else {}
    for cli_name, table in cli_tables.items():
        normalized_cli = str(cli_name or "").strip().lower()
        if normalized_cli not in set(CLI_NAMES) | {"gemini"}:
            continue
        cleaned = _sanitize_launch_preferences(table)
        if cleaned:
            result["launch"]["cli"][normalized_cli] = cleaned
    global_disabled = _sanitize_disabled_session_surfaces(session_surfaces.get("disabled"))
    if global_disabled:
        result["session_surfaces"]["disabled"] = global_disabled
    roots = _sanitize_asset_roots(assets.get("roots"))
    if roots:
        result["assets"]["roots"] = roots
    return result


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
    merged = {"mcp": [], "skills": [], "hooks": []}
    seen = {key: set() for key in merged}
    for payload in payloads:
        cleaned = _sanitize_disabled_session_surfaces(payload)
        for key, values in cleaned.items():
            for value in values:
                if value in seen[key]:
                    continue
                seen[key].add(value)
                merged[key].append(value)
    return {key: values for key, values in merged.items() if values}


def _preference_runtime_overlay(prefs, cli_name):
    prefs = prefs if isinstance(prefs, dict) else {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    merged = dict(launch.get("defaults") or {})
    cli_overrides = launch.get("cli") if isinstance(launch.get("cli"), dict) else {}
    cli_specific = cli_overrides.get(str(cli_name or "").strip().lower())
    if isinstance(cli_specific, dict):
        merged = _merge_dicts(merged, cli_specific)
    global_disabled = (prefs.get("session_surfaces") or {}).get("disabled") if isinstance(prefs.get("session_surfaces"), dict) else {}
    disabled = _merge_disabled_session_surfaces(global_disabled, merged.get("disabled_session_surfaces"))
    if disabled:
        merged["disabled_session_surfaces"] = disabled
    return merged


def _runtime_with_launch_preferences(cfg, runtime, cli_name):
    if not isinstance(runtime, dict):
        return runtime
    if runtime.get("_mms_preferences_applied"):
        return runtime
    prefs = (cfg or {}).get("_mms_preferences") if isinstance(cfg, dict) else None
    if not isinstance(prefs, dict):
        prefs = load_user_preferences()
    overlay = _preference_runtime_overlay(prefs, cli_name)
    if not overlay:
        result = dict(runtime)
        result["_mms_preferences_applied"] = True
        return result
    result = dict(runtime)
    existing_disabled = result.get("disabled_session_surfaces")
    for key, value in overlay.items():
        if key == "disabled_session_surfaces":
            continue
        result[key] = value
    disabled = _merge_disabled_session_surfaces(existing_disabled, overlay.get("disabled_session_surfaces"))
    if disabled:
        result["disabled_session_surfaces"] = disabled
    result["_mms_preferences_applied"] = True
    return result


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
    return os.path.join(ENV_DIR, f"{cli_name}.sh")


def _shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _parse_shell_value(raw):
    raw = raw.strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(f"v {raw}")
    except ValueError:
        return raw.strip("\"'")
    return parts[1] if len(parts) > 1 else ""


def _load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, sep, raw_value = line.partition("=")
            if not sep:
                continue
            values[key.strip()] = _parse_shell_value(raw_value)
    return values


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
    global _USAGE_ROUTES_EXPORT_RUNNING, _USAGE_ROUTES_EXPORT_LAST_STARTED_AT

    if not _usage_routes_export_should_run():
        return

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
    """Synchronously refresh the legacy route export from current config."""
    try:
        from mms_router import export_model_routes

        if startup_safe and not _usage_routes_export_should_run():
            return True

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
            console.print(f"[yellow]⚠ Legacy routes export 刷新失败: {exc}[/yellow]")
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
    kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")
    return f"{kind}:{cli_name}:{runtime_id}"


def _resolve_model_name(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = model_info.get(key)
            if value:
                return str(value)
        return "official-default"
    return str(model_info or "official-default")


def _runtime_hint_from_runtime(runtime):
    if not isinstance(runtime, dict):
        return {}
    hint = {
        "runtime_kind": str(runtime.get("runtime_kind", "")).strip(),
        "auth_mode": str(runtime.get("auth_mode", "")).strip(),
    }
    provider_id = _trace_runtime_provider_id(runtime)
    account_id = _trace_runtime_account_id(runtime)
    runtime_id = str(runtime.get("id") or "").strip()
    if provider_id:
        hint["provider_id"] = provider_id
    if account_id:
        hint["account_id"] = account_id
    if runtime_id:
        hint["runtime_id"] = runtime_id
    return {k: v for k, v in hint.items() if v}


def _record_usage(runtime, cli_name, model_info):
    def _mutate(stats):
        sources = stats.setdefault("sources", {})
        key = _runtime_usage_key(runtime, cli_name)
        model_name = _resolve_model_name(model_info)
        now = _iso_now()
        entry = sources.setdefault(key, {
            "runtime_kind": runtime.get("runtime_kind", "provider"),
            "id": runtime.get("id", "default"),
            "name": runtime.get("name", runtime.get("id", "default")),
            "cli": cli_name,
            "launches": 0,
            "last_used_at": "",
            "last_model": "",
            "models": {},
            "model_last_used_at": {},
        })
        entry["launches"] += 1
        entry["last_used_at"] = now
        entry["last_model"] = model_name
        models = entry.setdefault("models", {})
        models[model_name] = int(models.get(model_name, 0)) + 1
        model_last_used_at = entry.setdefault("model_last_used_at", {})
        model_last_used_at[model_name] = now
        last_by_cli = stats.setdefault("last_by_cli", {})
        last_by_cli[cli_name] = {
            "cli": cli_name,
            "model": model_name,
            "model_info": model_info if isinstance(model_info, dict) else {"model": str(model_info)},
            "runtime_hint": _runtime_hint_from_runtime(runtime),
            "last_used_at": now,
        }

    _update_usage_stats(_mutate)


def _record_scene_usage(scene_name, cli_name, model_info):
    """记录 legacy 场景级启动统计，保留旧 usage.json 兼容。"""
    if not scene_name or scene_name.startswith("__"):
        return
    def _mutate(stats):
        scene_stats = stats.setdefault("scenes", {})
        model_name = _resolve_model_name(model_info)
        entry = scene_stats.setdefault(scene_name, {
            "launches": 0,
            "last_used_at": "",
            "last_cli": "",
            "last_model": "",
        })
        entry["launches"] += 1
        entry["last_used_at"] = _iso_now()
        entry["last_cli"] = cli_name
        entry["last_model"] = model_name

    _update_usage_stats(_mutate)


def _get_scene_usage():
    """获取上次使用信息（按 CLI 分桶）+ legacy scene counts。"""
    stats = _load_usage_stats()
    scene_counts = {}
    for name, entry in stats.get("scenes", {}).items():
        scene_counts[name] = entry.get("launches", 0)
    last_by_cli = {}
    for cli_name, item in (stats.get("last_by_cli", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if not isinstance(normalized.get("runtime_hint"), dict):
            model_name = _resolve_model_name(
                normalized.get("model_info") if isinstance(normalized.get("model_info"), dict) else normalized.get("model")
            )
            inferred = _infer_runtime_hint_from_usage_stats(stats, cli_name, model_name)
            if inferred:
                normalized["runtime_hint"] = inferred
        last_by_cli[cli_name] = normalized
    return last_by_cli, scene_counts


def _infer_runtime_hint_from_usage_stats(stats, cli_name, model_name):
    latest_entry = None
    latest_at = ""
    normalized_model = str(model_name or "").strip()
    for entry in (stats.get("sources", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        if str(entry.get("last_model") or "").strip() != normalized_model:
            continue
        used_at = str(entry.get("last_used_at") or "").strip()
        if used_at < latest_at:
            continue
        latest_at = used_at
        latest_entry = entry

    if not isinstance(latest_entry, dict):
        return {}

    runtime_kind = str(latest_entry.get("runtime_kind") or "").strip()
    runtime_id = str(latest_entry.get("id") or "").strip()
    if not runtime_kind or not runtime_id:
        return {}

    hint = {
        "runtime_kind": runtime_kind,
        "runtime_id": runtime_id,
    }
    if runtime_kind == "provider":
        hint["auth_mode"] = "api_key"
        hint["provider_id"] = runtime_id
    elif runtime_kind == "account":
        hint["auth_mode"] = "oauth"
        hint["account_id"] = runtime_id
    else:
        return {}
    return hint


def _resolve_last_used_runtime(cfg, cli_name, last_item, default_models):
    if not isinstance(last_item, dict):
        return None, None, None

    hint = last_item.get("runtime_hint")
    if not isinstance(hint, dict):
        return None, None, None

    model_info = last_item.get("model_info") if isinstance(last_item.get("model_info"), dict) else {
        "model": str(last_item.get("model") or "")
    }
    model_name = _resolve_model_name(model_info)

    provider_id = str(hint.get("provider_id") or "").strip()
    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            provider = None
        if provider and _provider_supports_model_for_cli(provider, cli_name, model_name):
            models = _probe_models(provider, emit_output=False).get("models")
            models = _provider_effective_models(provider, models, cfg)
            if str(model_name or "").strip().lower() in {
                str(item or "").strip().lower() for item in (models or [])
            }:
                return (
                    _runtime_with_priority(provider, model_name=model_name),
                    models,
                    f"last used provider:{provider_id}",
                )

    auth_mode = str(hint.get("auth_mode") or "").strip()
    account_id = str(hint.get("account_id") or "").strip()
    if account_id and auth_mode != "oauth_bridge":
        try:
            account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        except Exception:
            account = None
        if account and _model_matches_account_cli(cli_name, model_name):
            return (
                _runtime_with_priority(account, model_name=model_name),
                list(default_models or []),
                f"last used account:{account_id}",
            )

    return None, None, None


# ── Trace ─────────────────────────────────────────────

_trace_enabled = False
_trace_overrides = []


def _trace_record(source, **kv):
    """记录一步 override 来源。source 是 config default / preset / CLI flags 等。"""
    if not _trace_enabled:
        return
    _trace_overrides.append((source, {k: v for k, v in kv.items() if v is not None}))


def _trace_runtime_provider_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("runtime_kind") == "provider" or runtime.get("auth_mode") == "api_key":
        return str(runtime.get("id", "")).strip()
    return ""


def _trace_runtime_account_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") == "oauth_bridge":
        return str(runtime.get("bridge_account_id") or runtime.get("id") or "").strip()
    if runtime.get("auth_mode") == "oauth":
        return str(runtime.get("id") or runtime.get("account_id") or "").strip()
    return str(runtime.get("account_id") or "").strip()


def _trace_runtime_bridge(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") != "oauth_bridge":
        return ""
    return str(runtime.get("bridge_url") or runtime.get("base_url") or "").strip()


def _trace_runtime_choice(source, runtime, launch_cli=None, choice=None):
    if not _trace_enabled:
        return
    payload = {
        "cli": launch_cli,
        "provider": _trace_runtime_provider_id(runtime),
        "account": _trace_runtime_account_id(runtime),
        "bridge": _trace_runtime_bridge(runtime),
        "runtime": runtime.get("auth_mode") if isinstance(runtime, dict) else None,
        "choice": choice,
    }
    _trace_record(source, **payload)


def _trace_source_for(field, value):
    expected = str(value or "").strip()
    if not expected:
        return "(not set)"
    fallback_source = ""
    generic_match = ""
    prefer_explicit = field in {"cli", "provider", "account", "model"}
    for source, kv in reversed(_trace_overrides):
        if field not in kv:
            continue
        candidate = str(kv.get(field) or "").strip()
        if candidate == expected:
            if prefer_explicit and source == "runtime resolve":
                generic_match = source
                continue
            return source
        if not fallback_source:
            fallback_source = source
    return fallback_source or generic_match or "runtime result"


def _print_trace(cli_name, model_info, runtime):
    """打印 [MMS Trace] 到 stderr。"""
    model = ""
    if isinstance(model_info, dict):
        model = model_info.get("model", "")
    elif isinstance(model_info, str):
        model = model_info

    provider_id = _trace_runtime_provider_id(runtime)
    account_id = _trace_runtime_account_id(runtime)
    auth_mode = runtime.get("auth_mode", "") if isinstance(runtime, dict) else ""
    bridge = _trace_runtime_bridge(runtime)

    lines = [
        "",
        "[MMS Trace]",
        f"  cli:      {cli_name or '-'} <- {_trace_source_for('cli', cli_name)}",
        f"  provider: {provider_id or '-'} <- {_trace_source_for('provider', provider_id)}",
        f"  account:  {account_id or '-'} <- {_trace_source_for('account', account_id)}",
        f"  model:    {model or '-'} <- {_trace_source_for('model', model)}",
        f"  bridge:   {bridge or '-'} <- {_trace_source_for('bridge', bridge)}",
        f"  runtime:  {auth_mode or '-'} <- {_trace_source_for('runtime', auth_mode)}",
        "",
        "Override chain:",
    ]
    if _trace_overrides:
        for source, kv in _trace_overrides:
            if kv:
                parts = ", ".join(f"{k}={v}" for k, v in kv.items())
                lines.append(f"  {source:<16s}-> {parts}")
            else:
                lines.append(f"  {source:<16s}-> (none)")
    else:
        lines.append("  (no overrides recorded)")
    lines.append("")

    print("\n".join(lines), file=sys.stderr)


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
    if provider.get("_mms_bundle_runtime"):
        provider["base_url"] = credentials["base_url"] or provider.get("base_url", "")
        provider["openai_base_url"] = (
            credentials["openai_base_url"]
            or provider.get("openai_base_url", "")
            or provider.get("default_openai_base_url", "")
        )
        provider["anthropic_base_url"] = (
            credentials["anthropic_base_url"]
            or provider.get("anthropic_base_url", "")
            or provider.get("default_anthropic_base_url", "")
        )
        provider["api_key"] = credentials["api_key"] or provider.get("api_key", "")
        provider["openai_api_key"] = credentials.get("openai_api_key", "") or provider.get("openai_api_key", "")
    else:
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
        file_base_url, file_api_key = load_api_credentials()

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
    return provider.get("name", provider.get("id", DEFAULT_PROVIDER_ID))


def _provider_openai_base_url(provider):
    explicit = str(provider.get("openai_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(provider.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def _provider_anthropic_base_url(provider):
    explicit = str(provider.get("anthropic_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    if "anthropic_messages" not in protocols:
        return ""
    return str(provider.get("base_url", "")).strip().rstrip("/")


def _provider_has_configured_base_url(provider):
    return bool(
        _provider_openai_base_url(provider)
        or _provider_anthropic_base_url(provider)
        or str(provider.get("base_url", "")).strip().rstrip("/")
    )


def _provider_id_variants(provider_id):
    raw = str(provider_id or "").strip()
    if not raw:
        return []
    variants = [raw]
    for candidate in (raw.replace("_", "-"), raw.replace("-", "_")):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _resolve_config_provider_id(provider_defs, provider_id):
    provider_defs = provider_defs or {}
    for candidate in _provider_id_variants(provider_id):
        if candidate in provider_defs:
            return candidate
    return ""


def _config_truthy(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


def _vision_sidecar_model_candidates_for_provider(provider_id):
    normalized = str(provider_id or "").strip().lower()
    generic = [
        "mimo-v2.5",
        "mimo-v2-omni",
        "K2.6",
        "K2.6-code-preview",
        "kimi-k2.5",
        "qwen3.6-flash",
        "qwen3.6-plus",
    ]
    if "mimo" in normalized:
        return ["mimo-v2.5", "mimo-v2-omni"]
    if "kimi" in normalized:
        return ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    if "qwen" in normalized:
        return ["qwen3.6-plus", "qwen3.6-flash"]
    return generic


def _vision_sidecar_candidate_pairs(raw, provider_ids, *, explicit_model="", explicit_provider_id=""):
    configured = (raw.get("candidates") or raw.get("routes")) if isinstance(raw, dict) else None
    pairs = []

    def _append(provider_id, model):
        provider_id = str(provider_id or "").strip()
        model = str(model or "").strip()
        if provider_id and model and (provider_id, model) not in pairs:
            pairs.append((provider_id, model))

    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict):
                continue
            provider_id = item.get("provider_id") or item.get("provider")
            model = item.get("model") or item.get("vision_model")
            _append(provider_id, model)

    if explicit_model:
        for provider_id in provider_ids:
            _append(provider_id, explicit_model)
        return pairs

    if explicit_provider_id:
        for model in _vision_sidecar_model_candidates_for_provider(explicit_provider_id):
            _append(explicit_provider_id, model)
        return pairs

    preferred_pairs = [
        ("mimo-direct-anthropic", "mimo-v2.5"),
        ("direct-mimo", "mimo-v2.5"),
        ("direct-kimi", "K2.6"),
        ("newapi-personal-kimi", "K2.6-code-preview"),
        ("newapi-personal-kimi", "kimi-k2.5"),
        ("direct-qwen", "qwen3.6-plus"),
        ("newapi-personal-qwen", "qwen3.6-plus"),
        ("newapi-personal-tokyo", "K2.6"),
        ("xin", "K2.6"),
    ]
    for provider_id, model in preferred_pairs:
        _append(provider_id, model)
    for provider_id in provider_ids:
        for model in _vision_sidecar_model_candidates_for_provider(provider_id):
            _append(provider_id, model)
    return pairs


def _runtime_with_vision_sidecar(cfg, runtime):
    if not isinstance(runtime, dict) or runtime.get("vision_sidecar"):
        return runtime
    raw = cfg.get("vision_sidecar") if isinstance(cfg, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    if raw and not _config_truthy(raw.get("enabled"), default=True):
        return runtime

    explicit_model = str(
        os.environ.get("MMS_VISION_SIDECAR_MODEL")
        or raw.get("model")
        or raw.get("vision_model")
        or ""
    ).strip()
    explicit_provider_id = str(
        os.environ.get("MMS_VISION_SIDECAR_PROVIDER")
        or raw.get("provider_id")
        or raw.get("provider")
        or ""
    ).strip()
    preferred_ids = (
        [explicit_provider_id]
        if explicit_provider_id
        else [
            "mimo-direct-anthropic",
            "direct-mimo",
            "direct-kimi",
            "newapi-personal-kimi",
            "newapi-personal-tokyo",
            "xin",
        ]
    )
    providers = cfg.get("providers", []) if isinstance(cfg, dict) else []
    provider_defs = _provider_map(cfg) if isinstance(cfg, dict) else {}
    explicit_provider_id = _resolve_config_provider_id(provider_defs, explicit_provider_id)
    all_ids = [
        str(item.get("id") or "").strip()
        for item in providers
        if isinstance(item, dict) and item.get("id")
    ]
    candidate_ids = []
    for provider_id in preferred_ids + all_ids:
        if provider_id and provider_id not in candidate_ids:
            candidate_ids.append(provider_id)

    for provider_id, model in _vision_sidecar_candidate_pairs(
        raw,
        candidate_ids,
        explicit_model=explicit_model,
        explicit_provider_id=explicit_provider_id,
    ):
        if provider_id not in provider_defs:
            continue
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            continue
        if not provider or not provider.get("enabled", True):
            continue
        api_key = str(provider.get("api_key") or provider.get("openai_api_key") or "").strip()
        anthropic_url = _provider_anthropic_base_url(provider)
        if not api_key or not anthropic_url:
            continue
        if not explicit_provider_id:
            try:
                cached = _load_probe_file_cache(provider_id, allow_stale=True)
                cached_models = (cached or {}).get("raw_models") or (cached or {}).get("models")
                models = _provider_effective_models(provider, cached_models, cfg)
            except Exception:
                models = []
            model_l = model.lower()
            if models and model_l not in {str(item or "").strip().lower() for item in models}:
                continue
        updated = dict(runtime)
        updated["vision_sidecar"] = {
            "enabled": True,
            "provider_id": provider_id,
            "provider_profile": str(provider.get("profile") or provider.get("provider_profile") or ""),
            "model": model,
            "anthropic_base_url": anthropic_url,
            "api_key": api_key,
            "proxy_url": str(provider.get("proxy") or "").strip(),
            "no_proxy": str(provider.get("no_proxy") or "").strip(),
        }
        return updated
    return runtime


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
    values = []
    for chunk in str(raw_value or "").split(","):
        item = chunk.strip()
        if item and item not in values:
            values.append(item)
    if allowed_values is None:
        return values
    invalid = [item for item in values if item not in allowed_values]
    if invalid:
        console.print(f"[red]不支持的值: {', '.join(invalid)}[/red]")
        console.print(f"[dim]可选值: {', '.join(allowed_values)}[/dim]")
        sys.exit(1)
    return values


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
    stats = _load_usage_stats()
    rows = []
    for item in stats.get("sources", {}).values():
        if item.get("runtime_kind") == runtime_kind and item.get("id") == runtime_id:
            rows.append(item)
    rows.sort(key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)), reverse=True)
    return rows


def _usage_summary_for_runtime(runtime_kind, runtime_id):
    rows = _usage_rows_for_runtime(runtime_kind, runtime_id)
    launches = sum(int(item.get("launches", 0)) for item in rows)
    last_used_at = rows[0].get("last_used_at", "") if rows else ""
    return launches, last_used_at


def _rescue_route_fallback_model_candidates(config_dir=None, *, failed_model="", limit=80):
    failed = str(failed_model or "").strip().lower()
    root = os.path.expanduser(str(config_dir or CONFIG_DIR))
    candidates = []
    seen = set()

    def route_is_openai_usable(route):
        if not isinstance(route, dict):
            return False
        return bool(str(route.get("openai_base_url") or "").strip() and str(route.get("api_key") or "").strip())

    def add_from_router_payload(payload):
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

    manifest_path = os.path.join(root, "generated", "model-registry.latest-approved.json")
    if os.path.exists(manifest_path):
        try:
            import mms_registry

            payload = mms_registry.try_load_latest_approved_payload("router", config_dir=root, include_secret=True)
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload:
            add_from_router_payload(payload)
        return candidates[: max(1, int(limit or 1))]
    try:
        if mms_config_root_status(config_dir=root).get("mode") == "preview":
            return []
    except Exception:
        pass

    paths = [
        os.path.join(root, "generated", "model-routes.json"),
        os.path.join(root, "model-routes.json"),
    ]
    for path in paths:
        try:
            payload = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        add_from_router_payload(payload)
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
    if not isinstance(event, dict) or not event:
        return "-"
    at = str(event.get("at") or "")[:19].replace("T", " ")
    model = str(event.get("model") or "").strip()
    note = str(event.get("note") or "").strip()
    parts = [item for item in (at, model, note) if item]
    return " · ".join(parts) if parts else "-"


def _rescue_landing_tui_payload(default_label, rescue_events, latest_fallback_event=None, hot_fallback_enabled=False):
    """Build the first Rescue settings page before drilling into packet history."""
    events = list(rescue_events or [])
    latest = events[0] if events else {}
    if latest:
        latest_line = " ".join(
            item
            for item in (
                str(latest.get("created_at") or "")[:19].replace("T", " "),
                str(latest.get("failed_model") or ""),
                str(latest.get("status_code") or latest.get("failure_kind") or ""),
            )
            if item
        )
    else:
        latest_line = "-"
    packet_summary = f"{len(events)} 个 packet" if events else "没有 packet"
    has_default = bool(str(default_label or "").strip() and str(default_label or "").strip() != "未设置")
    info_lines = [
        ("全局默认", str(default_label or "未设置")),
        ("Hot fallback", "开启" if hot_fallback_enabled and has_default else "关闭"),
        ("生效范围", "MMS 全局默认；bridge 失败时读取"),
        ("触发时机", "429 / 503 / context / provider failure"),
        ("最近失败", f"{packet_summary} · {latest_line}" if latest else packet_summary),
        ("最近 fallback 尝试", _format_rescue_hot_fallback_event(latest_fallback_event)),
        ("安全边界", "只走 routed provider；不使用 global OAuth"),
    ]
    actions = [
        ("choose_route_default", "设置全局默认 fallback（routed models）"),
        ("manual_default", "手动输入 fallback model"),
        ("clear_default", "清除全局默认 fallback"),
    ]
    if has_default:
        actions.append(
            (
                "disable_hot_fallback" if hot_fallback_enabled else "enable_hot_fallback",
                "关闭 hot fallback（只记录 handoff）" if hot_fallback_enabled else "开启 hot fallback（当前会话热切）",
            )
        )
    if events:
        actions.append(("view_packets", "查看最近失败 / rescue packet"))
    actions.extend(
        [
            ("create_demo", "生成测试 rescue packet"),
            ("back", "返回"),
        ]
    )
    return info_lines, actions


def _registry_truth_tui_payload(status):
    """Build localized Registry Truth status/actions for the Settings detail page."""
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    freshness = status.get("source_freshness") if isinstance(status.get("source_freshness"), dict) else {}
    info_lines = [
        ("DB", status.get("db_path") or "-"),
        (_L("来源快照", "source snapshots"), counts.get("source_snapshot", 0)),
        (_L("模型身份", "model identities"), counts.get("model_identity", 0)),
        (_L("模型事实", "model facts"), counts.get("model_fact", 0)),
        (_L("待刷新来源", "sources due"), freshness.get("due_count", 0)),
        (_L("最新来源", "latest source"), latest.get("source_path") or "none"),
    ]
    actions = [
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
    return _L("模型真源 / Registry Truth", "Registry Truth"), info_lines, actions


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


def _model_source_status_tui_payload(summary):
    actions = [
        ("model_source_status", _L("查看 Model Source Status", "View Model Source Status")),
        ("consumer_bundle_status", _L("查看 Consumer Bundle", "View Consumer Bundle")),
        ("registry_v2_save_plan", _L("查看 v2 Save Plan", "View v2 Save Plan")),
        ("config_v2_promotion_plan", _L("查看 Promote Plan", "View Promote Plan")),
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
    text = str(value if value is not None else "-").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text or "-"
    return text[: max(1, max_len - 1)].rstrip() + "…"


_SETTINGS_RESULT_RENDERED_TUI = False


def _settings_result_tui_available():
    if str(os.environ.get("MMS_DISABLE_SETTINGS_RESULT_TUI") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _settings_result_tui_payload(title, rows, note="", *, ok=True):
    prefix = "✓ " if ok else "✗ "
    info_lines = [(_L("状态", "Status"), _L("成功", "OK") if ok else _L("失败", "Failed"))]
    info_lines.extend(
        (str(label or "-"), _compact_tui_report_value(value, max_len=120))
        for label, value in list(rows or [])
    )
    if note:
        info_lines.append((_L("说明", "Note"), _compact_tui_report_value(note, max_len=160)))
    return (
        f"{prefix}{title}",
        info_lines,
        [("back", _L("返回", "Back"))],
    )


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
    color = "green" if ok else "red"
    prefix = "✓ " if ok else "✗ "
    console.print(f"[{color}]{prefix}{title}[/{color}]")
    for label, value in rows:
        console.print(f"[cyan]{label}[/cyan] {_compact_tui_report_value(value)}")
    if note:
        console.print(f"[dim]{note}[/dim]")


def _print_settings_error_report(title, exc):
    _print_settings_result_report(
        title,
        [(_L("错误", "Error"), exc)],
        _L("操作未完成；没有改变 runtime defaults。", "Operation did not complete; runtime defaults unchanged."),
        ok=False,
    )


def _rescue_default_fallback_report_payload(model, *, cleared=False, hot_fallback_enabled=False):
    if cleared:
        return (
            _L("全局 fallback 已清除", "Global fallback cleared"),
            [
                (_L("保存位置", "saved at"), "[rescue].fallback_model"),
                (_L("安全边界", "safety"), "routed providers only; no global OAuth"),
            ],
            "",
        )
    return (
        _L("全局 fallback 已设置", "Global fallback set"),
        [
            ("Model", model or "-"),
            ("Hot fallback", _L("开启", "on") if hot_fallback_enabled else _L("关闭", "off")),
            (_L("保存位置", "saved at"), "[rescue].fallback_model"),
            (_L("生效方式", "applies"), "bridge failure -> latest-approved Router"),
            (_L("安全边界", "safety"), "no global OAuth"),
        ],
        (
            _L("真实 failure 会先写 rescue packet，再尝试该 routed model。", "Real failures write a rescue packet before trying this routed model.")
            if hot_fallback_enabled
            else _L("默认只记录 rescue / fallback handoff；开启 hot fallback 后才会自动模型调用。", "By default MMS records rescue / fallback handoff only; automatic model calls require hot fallback to be enabled.")
        ),
    )


def _rescue_hot_fallback_toggle_report_payload(enabled, *, has_default=True):
    if enabled and not has_default:
        return (
            _L("无法开启 hot fallback", "Cannot enable hot fallback"),
            [
                (_L("原因", "reason"), _L("请先设置全局 fallback model", "Set a global fallback model first")),
                (_L("安全边界", "safety"), "no global OAuth"),
            ],
            "",
        )
    return (
        _L("hot fallback 已开启", "hot fallback enabled") if enabled else _L("hot fallback 已关闭", "hot fallback disabled"),
        [
            ("Hot fallback", _L("开启", "on") if enabled else _L("关闭", "off")),
            (_L("前置条件", "requires"), "[rescue].fallback_model"),
            (_L("默认行为", "default"), _L("关闭时只记录 rescue / handoff", "off means rescue / handoff only")),
        ],
        _L("开关保存到 [rescue].hot_fallback_enabled。", "Switch is saved to [rescue].hot_fallback_enabled."),
    )


def _rescue_demo_packet_report_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    return (
        _L("测试 rescue packet 已生成", "Demo rescue packet created"),
        [
            ("rescue.md", artifacts.get("markdown") or "-"),
            ("rescue.json", artifacts.get("json") or "-"),
        ],
        "",
    )


def _rescue_paths_report_payload(selected_rescue):
    selected_rescue = selected_rescue if isinstance(selected_rescue, dict) else {}
    return (
        _L("Rescue 文件路径", "Rescue file paths"),
        [
            ("rescue.md", selected_rescue.get("artifact_markdown") or "-"),
            ("rescue.json", selected_rescue.get("artifact_json") or "-"),
        ],
        "",
    )


def _rescue_handover_report_payload(handover, fallback_model):
    handover = handover if isinstance(handover, dict) else {}
    artifacts = handover.get("artifacts") if isinstance(handover.get("artifacts"), dict) else {}
    return (
        _L("fallback handover 已生成", "fallback handover created"),
        [
            ("Model", fallback_model or "-"),
            ("handover.md", artifacts.get("markdown") or "-"),
            ("latest", artifacts.get("latest_markdown") or "-"),
        ],
        _L("handover 只写本地 rescue artifact；不切换当前 session。", "handover writes local rescue artifacts only; it does not switch the current session."),
    )


def _registry_source_staleness_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        ("DB", summary.get("db_path") or "-"),
        (_L("到期 Source", "sources due"), f"{summary.get('due_count')} / {summary.get('source_count')}"),
    ]
    for idx, item in enumerate((summary.get("sources") or [])[:5], start=1):
        due = _L("到期", "due") if item.get("due") else _L("未到期", "not due")
        rows.append(
            (
                f"Source {idx}",
                f"{due} · {item.get('reason') or '-'} · {item.get('checked_at') or '-'} · {item.get('source_path') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("sources") or []) - 5)
    if hidden:
        rows.append((_L("更多 Source", "more sources"), hidden))
    return _L("模型真源 Source Staleness", "Registry Source Staleness"), rows, ""


def _registry_refresh_sources_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    return (
        _L("刷新 Sources 完成", "Refresh Sources Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            (_L("导入", "imported"), summary.get("imported_count")),
            (_L("跳过", "skipped"), summary.get("skipped_count", 0)),
            (_L("模型", "models"), summary.get("model_count")),
            (_L("事实", "facts"), summary.get("fact_count")),
        ],
        _L("只写 source truth / candidate evidence；不改变当前 runtime defaults。", "Writes source truth / candidate evidence only; runtime defaults unchanged."),
    )


def _registry_scheduled_refresh_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    source_refresh = summary.get("source_refresh") if isinstance(summary.get("source_refresh"), dict) else {}
    openrouter_fetch = summary.get("openrouter_fetch") if isinstance(summary.get("openrouter_fetch"), dict) else {}
    return (
        _L("定时刷新结果", "Scheduled Refresh Result"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Dry Run", summary.get("dry_run")),
            (_L("到期 Source", "source due"), summary.get("source_due_count")),
            (_L("导入 Source", "source imported"), source_refresh.get("imported_count", 0)),
            (_L("OpenRouter 到期", "OpenRouter due"), summary.get("openrouter_due")),
            ("OpenRouter", openrouter_fetch.get("reason") or _L("No Network 模式未拉取", "not fetched in no-network mode")),
        ],
        _L("安全 schedule wrapper：不接入 startup，不发布 latest-approved。", "Safe schedule wrapper: no startup hook and no latest-approved publish."),
    )


def _registry_openrouter_fetch_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    return (
        _L("OpenRouter Catalog 拉取完成", "OpenRouter Catalog Fetch Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Snapshot", summary.get("snapshot_id") or "-"),
            (_L("模型", "models"), summary.get("model_count")),
        ],
        _L("只写 provider_catalog source snapshot；不改变当前 runtime defaults。", "Writes provider_catalog source snapshot only; runtime defaults unchanged."),
    )


def _registry_openrouter_diff_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        (_L("变化", "changes"), f"{summary.get('change_count')} stored={summary.get('stored_count')}"),
        (_L("缺少 reference", "missing reference"), summary.get("missing_reference_count")),
        (_L("未追踪 catalog", "untracked catalog"), summary.get("untracked_catalog_count")),
    ]
    for idx, item in enumerate((summary.get("changes") or [])[:5], start=1):
        rows.append(
            (
                f"Change {idx}",
                f"{item.get('field_key') or '-'} · {item.get('model_key') or '-'} -> {item.get('provider_model_id') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("changes") or []) - 5)
    if hidden:
        rows.append((_L("更多变化", "more changes"), hidden))
    return (
        _L("OpenRouter Candidate Diff", "OpenRouter Candidate Diff"),
        rows,
        _L("只写 candidate_change evidence；不改变当前 runtime defaults。", "Writes candidate_change evidence only; runtime defaults unchanged."),
    )


def _registry_publish_approved_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    return (
        _L("发布 Approved Bundle 完成", "Publish Approved Bundle Complete"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", summary.get("bundle_revision") or "-"),
        ],
        _L("发布 generated/latest-approved bundle；不改 root aliases，不改 runtime defaults。", "Publishes generated/latest-approved bundle; root aliases and runtime defaults unchanged."),
    )


def _registry_verify_approved_report_payload(summary):
    summary = summary if isinstance(summary, dict) else {}
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    files = summary.get("verified_files") if isinstance(summary.get("verified_files"), dict) else {}
    return (
        _L("Latest-approved hash 验证完成", "Latest-approved hash verified"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", manifest.get("bundle_revision") or "-"),
            (_L("文件", "files"), len(files)),
        ],
        "",
    )


def _registry_doctor_report_payload(status):
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    rows = [
        ("DB", status.get("db_path") or "-"),
        ("user_version", status.get("user_version") or "-"),
    ]
    for key in sorted(counts):
        rows.append((key, counts[key]))
    return _L("Registry Doctor / 状态", "Registry Doctor / Status"), rows, ""


def _about_tui_payload(about_snapshot):
    """Build localized About status/actions for the Settings detail page."""
    about_snapshot = about_snapshot if isinstance(about_snapshot, dict) else {}
    version_info = about_snapshot.get("version_info") if isinstance(about_snapshot.get("version_info"), dict) else {}
    mms_status = about_snapshot.get("mms") if isinstance(about_snapshot.get("mms"), dict) else {}
    clis = about_snapshot.get("clis") if isinstance(about_snapshot.get("clis"), dict) else {}
    codex_status = clis.get("codex") if isinstance(clis.get("codex"), dict) else {}
    claude_status = clis.get("claude") if isinstance(clis.get("claude"), dict) else {}
    info_lines = [
        ("MMS", f"{mms_status.get('current') or version_info.get('release') or 'dev'} · {mms_status.get('status') or '-'}"),
        (_L("MMS 最新", "MMS latest"), mms_status.get("latest") or _L("未检查", "not checked")),
        ("Codex", _format_cli_about_line(codex_status)),
        (_L("Codex 最新", "Codex latest"), _format_about_latest_value(codex_status)),
        ("Claude", _format_cli_about_line(claude_status)),
        (_L("Claude 最新", "Claude latest"), _format_about_latest_value(claude_status)),
        ("Git", f"{version_info.get('git_branch') or '-'} @ {version_info.get('git_commit') or '-'}"),
        (_L("安装", "Install"), f"{version_info.get('install_channel') or '-'} / {version_info.get('source') or '-'}"),
        ("Config", CONFIG_PATH),
    ]
    if mms_status.get("last_error"):
        info_lines.append((_L("检查错误", "Check error"), _about_check_error_summary(mms_status.get("last_error"))))
    actions = [("refresh_versions", _L("刷新版本检查", "Refresh Version Check"))]
    if mms_status.get("outdated"):
        actions.append(("upgrade_mms", _L("升级 MMS", "Upgrade MMS")))
    if codex_status.get("outdated"):
        actions.append(("upgrade_codex_cli", _L("升级 Codex CLI", "Upgrade Codex CLI")))
    if claude_status.get("outdated"):
        actions.append(("upgrade_claude_cli", _L("升级 Claude CLI", "Upgrade Claude CLI")))
    actions.append(("back", _L("返回", "Back")))
    return _L("关于 / About", "About"), info_lines, actions


def _snapshot_guard_tui_payload():
    """Build localized Snapshot Guard status/actions for the Settings detail page."""
    info_lines = [
        (_L("用途", "Purpose"), _L("检查/接受 MMS config drift", "Inspect / accept MMS config drift")),
        ("CLI", f"{current_command()} guard status / accept"),
    ]
    actions = [
        ("status", _L("查看当前 Snapshot 状态", "Status")),
        ("accept", _L("接受当前 Snapshot", "Accept Current Snapshot")),
        ("back", _L("返回", "Back")),
    ]
    return _L("启动快照 / Snapshot Guard", "Snapshot Guard"), info_lines, actions


def _display_runtime_usage(runtime_kind, runtime_id, title):
    if _use_tui():
        try:
            console.clear()
        except Exception:
            pass
    rows = _usage_rows_for_runtime(runtime_kind, runtime_id)
    if not rows:
        console.print(f"[yellow]{title} 还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件: {_active_usage_path()}[/dim]")
        if _use_tui():
            _pause_after_tui_report("按 Enter 返回通道详情")
        return

    table = Table(title=f"{title} · 本地统计", show_lines=True)
    table.add_column("CLI", style="cyan")
    table.add_column("启动次数", style="green")
    table.add_column("最近模型", style="yellow")
    table.add_column("最近使用", style="magenta")
    for item in rows:
        table.add_row(
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这里只是本地启动统计，不代表官方真实余额或剩余额度。[/dim]")
    if _use_tui():
        _pause_after_tui_report("按 Enter 返回通道详情")


def _list_manage_targets(cfg):
    targets = []
    default_provider_id = cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)
    account_defaults = cfg.get("account", {}).get("defaults", {})

    for provider in cfg.get("providers", []):
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id", "")).strip()
        if not provider_id:
            continue
        provider_ctx = resolve_provider_context(cfg, provider_id)
        launches, last_used_at = _usage_summary_for_runtime("provider", provider_id)
        targets.append({
            "kind": "provider",
            "id": provider_id,
            "title": provider.get("name", provider_id),
            "summary": "默认网关通道" if provider_id == default_provider_id else "网关通道",
            "is_default": provider_id == default_provider_id,
            "default_label": "网关" if provider_id == default_provider_id else "备选",
            "status": "已配置" if provider_ctx.get("base_url") and provider_ctx.get("api_key") else "未配置",
            "launches": launches,
            "last_used_at": last_used_at,
        })

    for account in cfg.get("accounts", []):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id", "")).strip()
        if not account_id:
            continue
        cli_name = str(account.get("cli", "")).strip()
        launches, last_used_at = _usage_summary_for_runtime("account", account_id)
        login_state = _probe_account_status(account)
        default_tag = " / 默认" if account_defaults.get(cli_name) == account_id else ""
        targets.append({
            "kind": "account",
            "id": account_id,
            "cli": cli_name,
            "title": account.get("name", account_id),
            "summary": f"官方通道 · {cli_name.upper()}{default_tag}",
            "is_default": account_defaults.get(cli_name) == account_id,
            "default_label": cli_name.upper() if account_defaults.get(cli_name) == account_id else "备选",
            "status": login_state.get("summary") or login_state.get("state", ""),
            "launches": launches,
            "last_used_at": last_used_at,
        })
    targets.sort(
        key=lambda item: (
            0 if item.get("is_default") else 1,
            0 if item.get("kind") == "account" else 1,
            -int(item.get("launches", 0)),
            item.get("last_used_at", ""),
            item.get("title", ""),
        )
    )
    return targets


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

    # fallback: rich 表格
    _ensure_rich()
    console.print(Panel(
        f"[bold]通道总数:[/bold] {len(targets)} 个",
        title="管理现有通道",
        border_style="cyan",
    ))
    table = Table(show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("类型", style="green")
    table.add_column("显示名", style="yellow")
    table.add_column("默认入口", style="white", width=10)
    table.add_column("状态", style="magenta")
    table.add_column("启动", style="cyan", width=6)
    for index, target in enumerate(targets, 1):
        target_type = "官方" if target.get("kind") == "account" else "网关"
        table.add_row(
            str(index), target_type, target.get("title", ""),
            target.get("default_label", ""), target.get("status", ""),
            str(target.get("launches", 0)),
        )
    console.print(table)

    while True:
        _ensure_rich()
        raw = Prompt.ask("选择要管理的通道，直接回车返回", default="")
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(targets):
                return targets[idx - 1]
        console.print(f"[red]请输入 1-{len(targets)} 的编号[/red]")


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

    _ensure_rich()
    table = Table(title=f"{provider.get('name', provider.get('id'))} · 模型列表", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("家族", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")
    table.add_column("来源", style="green")
    table.add_column("首字节延迟", style="yellow")
    table.add_column("生成速度", style="magenta")
    table.add_column("样本", style="white")
    table.add_column("最近更新", style="blue")

    for model_id in probe.get("models") or []:
        speed = get_speed_entry(model_id, provider=provider)
        ttfb = "暂无数据"
        tps = "暂无数据"
        samples = "-"
        updated = "-"
        if speed:
            ttfb_value = speed.get("ttfb_avg_ms")
            ttfb = f"{ttfb_value:.0f}ms / {_ttfb_label(ttfb_value)}" if isinstance(ttfb_value, (int, float)) else "暂无数据"
            tps_value = speed.get("tps_avg")
            tps = f"{tps_value:.1f} / {_tps_label(tps_value)}" if isinstance(tps_value, (int, float)) else "暂无数据"
            samples = str(speed.get("samples", 0))
            if speed.get("warming_up"):
                samples = f"{samples}（预热中）"
            updated = str(speed.get("last_updated") or "-")
            if speed.get("is_stale"):
                updated = f"{updated} (stale)"
        table.add_row(
            model_id,
            _infer_model_family(model_id)[0],
            _model_capability_summary(model_id),
            _model_cli_summary(model_id),
            _model_source_label((probe.get("model_sources") or {}).get(model_id, probe.get("base_source", "remote"))),
            ttfb,
            tps,
            samples,
            updated,
        )
    console.print(table)
    hidden_models = probe.get("hidden_models") or []
    extra_models = probe.get("extra_models") or []
    if extra_models:
        console.print(f"[dim]手工补充模型: {', '.join(extra_models)}[/dim]")
    if hidden_models:
        console.print(f"[dim]已隐藏模型: {', '.join(hidden_models)}[/dim]")
    raw_models = probe.get("raw_models") or []
    if raw_models and raw_models != (probe.get("models") or []):
        console.print(f"[dim]原始模型数: {len(raw_models)} | 最终展示模型数: {len(probe.get('models') or [])}[/dim]")


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
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", Text(f"{current_command()} warm [provider_id]"))
        console.print("[dim]不带参数时先选通道，再选择最近使用 / 手动选择 / 全部模型。[/dim]")
        return

    provider_id = str(argv[0]).strip() if argv else ""
    providers = _provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = _select_provider_for_warm(cfg)
        if not provider_id:
            return

    provider = resolve_provider_context(cfg, provider_id)
    probe = _probe_models(provider, emit_output=False)
    models = list(probe.get("models") or [])
    if not models:
        console.print("[yellow]当前通道没有可预热的模型[/yellow]")
        return

    recent_models = [item for item in _recent_models_for_provider(provider_id) if item in models]

    console.print(Panel(
        f"[bold]通道:[/bold] {provider.get('name', provider_id)}\n"
        f"[bold]可用模型数:[/bold] {len(models)}\n"
        f"[dim]预热会真实发请求，建议优先预热最近常用模型，不建议默认全量预热。[/dim]",
        title="模型预热",
        border_style="cyan",
    ))
    console.print("  1. 预热最近使用模型（推荐）")
    console.print("  2. 手动选择模型")
    console.print("  3. 预热全部模型（不推荐）")
    console.print("  4. 返回")
    choice = Prompt.ask("选择操作", choices=["1", "2", "3", "4"], default="1")

    selected_models = []
    if choice == "1":
        selected_models = recent_models
        if not selected_models:
            console.print("[yellow]当前没有最近使用模型，已改为手动选择[/yellow]")
            selected_models = _pick_manual_models(models)
    elif choice == "2":
        selected_models = _pick_manual_models(models)
    elif choice == "3":
        if not Confirm.ask("确认预热当前通道全部模型？这会产生真实请求成本。", default=False):
            console.print("[yellow]已取消全量预热[/yellow]")
            return
        selected_models = models
    else:
        return

    if not selected_models:
        console.print("[yellow]没有选择任何模型，已取消预热[/yellow]")
        return

    results = []
    for model_name in selected_models:
        console.print(f"[dim]正在预热 {model_name} ...[/dim]")
        ok, detail = _warm_model_request(provider, model_name)
        results.append((model_name, ok, detail))

    table = Table(title=f"{provider.get('name', provider_id)} · 预热结果", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("详情", style="yellow")
    success_count = 0
    for model_name, ok, detail in results:
        if ok:
            success_count += 1
        table.add_row(model_name, "成功" if ok else "失败", detail)
    console.print(table)
    console.print(f"[green]✓ 已完成预热：成功 {success_count} / {len(results)}[/green]")


def handle_models_command(cfg, argv):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", Text(f"{current_command()} ls [provider_id]"))
        console.print("[dim]不带参数时先选通道，再进入模型列表与测速页。[/dim]")
        return
    provider_id = str(argv[0]).strip() if argv else ""
    providers = _provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = _select_provider_for_models(cfg)
        if not provider_id:
            return

    _manage_provider_models(cfg, provider_id)


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
    if _use_tui():
        try:
            from mms_tui import select_connect_tui
        except ImportError:
            select_connect_tui = None
        if select_connect_tui is not None:
            action_id = select_connect_tui()
    if action_id == "fallback":
        action_id = None
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
    findings = []
    error_kind = probe.get("error_kind")
    provider_name = _provider_label(provider)
    if error_kind == "protocol_unsupported":
        findings.append({
            "severity": "high",
            "title": "当前 provider 不支持模型探测",
            "summary": f"{provider_name} 没有声明 openai_chat_completions，无法访问 /v1/models。",
        })
    elif error_kind in {"missing_credentials", "missing_base_url", "missing_api_key"}:
        findings.append({
            "severity": "high",
            "title": "当前 provider 凭据不完整",
            "summary": f"{provider_name} 还缺少地址或 Key，无法验证可用模型。",
        })
    elif error_kind == "empty_models":
        findings.append({
            "severity": "medium",
            "title": "接口连通，但没有拿到模型列表",
            "summary": f"{provider_name} 返回了空列表，可能是账号权限或网关映射问题。",
        })
    elif error_kind == "missing_httpx":
        findings.append({
            "severity": "high",
            "title": "本地缺少依赖",
            "summary": "当前环境缺少 httpx，暂时无法做模型探测。",
        })
    else:
        findings.append({
            "severity": "high",
            "title": "模型校验失败",
            "summary": probe.get("error") or f"{provider_name} 暂时无法拉取模型列表。",
        })
    if provider.get("id"):
        findings.append({
            "severity": "low",
            "title": "可以跳过校验继续",
            "summary": "预设和直接 CLI 启动仍然可以继续使用，但模型浏览会受限。",
        })
    return findings


def _rank_recovery_actions(actions):
    return sorted(
        actions,
        key=lambda item: (
            item.get("priority", 999),
            0 if item.get("recommended") else 1,
            item.get("title", ""),
        ),
    )


def _build_model_recovery_actions(cfg, provider, probe):
    providers = _provider_map(cfg)
    active_provider_id = provider.get("id")
    actions = [
        {
            "id": "edit_credentials",
            "title": "重新输入地址和 Key",
            "summary": "修复当前 provider 的地址或认证信息。",
            "priority": 10,
            "recommended": probe.get("error_kind") != "protocol_unsupported",
        },
        {
            "id": "show_details",
            "title": "查看详细错误",
            "summary": "展开本次校验的 provider、协议和错误明细。",
            "priority": 20,
            "recommended": False,
        },
        {
            "id": "continue_without_validation",
            "title": "跳过校验并继续",
            "summary": "继续使用预设或直接 CLI 启动，但不会有模型浏览列表。",
            "priority": 30,
            "recommended": False,
        },
    ]
    if len(providers) > 1:
        actions.insert(
            1,
            {
                "id": "switch_provider",
                "title": "切换到其他 provider",
                "summary": f"当前可切到其他已配置 provider，避免卡在 {active_provider_id}。",
                "priority": 12,
                "recommended": probe.get("error_kind") == "protocol_unsupported",
            },
        )
    return _rank_recovery_actions(actions)


def _print_model_probe_details(probe):
    lines = [f"- {line}" for line in probe.get("details", [])]
    console.print(Panel("\n".join(lines), title="校验详情", border_style="yellow"))


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
    if provider.get("_mms_bundle_runtime") and provider.get("api_key") and (
        provider.get("openai_base_url")
        or provider.get("anthropic_base_url")
        or provider.get("default_openai_base_url")
        or provider.get("default_anthropic_base_url")
    ):
        return resolve_provider_context(cfg, provider["id"])
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


def _resolve_lb_slot_provider(cfg, cli_name, model_name, provider_id):
    provider_def = _provider_map(cfg).get(provider_id)
    if not provider_def:
        return None, f"负载模式指定的 provider 不存在: {provider_id}"
    if not provider_def.get("enabled", True):
        return None, f"负载模式指定的 provider 已禁用: {provider_id}"

    provider = resolve_provider_context(cfg, provider_id)
    if not _provider_supports_cli_name(provider, cli_name):
        return None, f"provider {provider_id} 不支持 {cli_name}"
    if not provider.get("api_key"):
        return None, f"provider {provider_id} 缺少 API key"
    if not _provider_has_configured_base_url(provider):
        return None, f"provider {provider_id} 缺少可用 base_url"

    models = _probe_models(provider, emit_output=False).get("models")
    models = _provider_effective_models(provider, models, cfg)
    model_lower = str(model_name or "").strip().lower()
    if model_lower not in {str(item or "").strip().lower() for item in models}:
        return None, f"provider {provider_id} 不支持负载模式模型 {model_name}"

    return provider, None


def _build_model_families_for_cli(cfg, cli_name, default_provider, default_models):
    """聚合所有 provider 的模型，按 MODEL_FAMILIES 分组，每个模型附带最优 provider。

    Returns:
        List[dict]: [{
            "family": str,       # e.g. "Claude"
            "models": [{
                "model": str,
                "provider_id": str,
                "provider_name": str,
                "provider_ctx": dict,  # 完整 runtime context
            }],
        }]
    """
    # 聚合所有模型（去重，取最优 provider）
    model_best = {}  # model_name -> (provider_ctx, provider_name, provider_id)
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not _provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue

        models = _provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue

        role = _normalize_role(provider.get("role", "auto"))
        pid = provider.get("id", DEFAULT_PROVIDER_ID)
        pname = _provider_label(provider)

        for m in models:
            normalized = str(m or "").strip()
            if not normalized:
                continue
            if not _provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            priority = _runtime_priority_for_model(provider, normalized)
            score = (ROLE_WEIGHTS.get(role, 1), -priority)
            existing = model_best.get(normalized)
            if existing is None or score < existing[0]:
                model_best[normalized] = (
                    score,
                    _runtime_with_priority(provider, model_name=normalized),
                    pname,
                    pid,
                )

    # 注入当前 CLI 的使用信息（用于 TUI 排序）。
    use_counts = {}
    last_used_at_by_model = {}
    stats = _load_usage_stats()
    for src in stats.get("sources", {}).values():
        if str(src.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        used_at = str(src.get("last_used_at") or "").strip()
        model_last_used_at = src.get("model_last_used_at")
        if not isinstance(model_last_used_at, dict):
            model_last_used_at = {}
        for mname, cnt in src.get("models", {}).items():
            use_counts[mname] = use_counts.get(mname, 0) + cnt
            model_used_at = str(model_last_used_at.get(mname) or "").strip()
            if model_used_at and model_used_at > last_used_at_by_model.get(mname, ""):
                last_used_at_by_model[mname] = model_used_at
        last_model = str(src.get("last_model") or "").strip()
        # Legacy usage files only had source-level last_model/last_used_at.
        if (
            last_model
            and used_at
            and last_model not in model_last_used_at
            and used_at > last_used_at_by_model.get(last_model, "")
        ):
            last_used_at_by_model[last_model] = used_at

    # 按 family 分组
    family_map = {}  # family_name -> [model_entry]
    family_order = []

    for model_name, (_, provider_ctx, pname, pid) in model_best.items():
        if not _mms_model_visible(model_name):
            continue
        family, _ = _infer_model_family(model_name)
        if family not in family_map:
            family_map[family] = []
            family_order.append(family)
        family_map[family].append({
            "model": model_name,
            "family": family,
            "provider_id": pid,
            "provider_name": pname,
            "provider_ctx": provider_ctx,
            "use_count": use_counts.get(model_name, 0),
            "last_used_at": last_used_at_by_model.get(model_name, ""),
        })

    return [{"family": f, "models": family_map[f]} for f in family_order]


def _provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=None):
    selected_model = _resolve_model_name(model_info) if model_info else ""
    selected_family, _ = _infer_model_family(selected_model) if selected_model else ("", "")
    probe_debug_logger = _ensure_probe_debug_logger()
    probe_debug_logger.info("=== _provider_options_for_model(cli=%s, selected_model=%s) ===", cli_name, selected_model)
    options = []
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        pid = provider.get("id", "?")
        if not provider.get("enabled", True):
            probe_debug_logger.debug("  %s: SKIP (disabled)", pid)
            continue
        if not _provider_has_configured_base_url(provider) or not provider.get("api_key"):
            probe_debug_logger.debug(
                "  %s: SKIP (no configured base_url=%s or api_key=%s)",
                pid,
                _provider_has_configured_base_url(provider),
                bool(provider.get("api_key")),
            )
            continue

        models = cached_models
        if models is None:
            probe_debug_logger.debug("  %s: cached_models=None, schedule async refresh", pid)
            models = _provider_effective_models(provider, None, cfg)
        else:
            probe_debug_logger.debug("  %s: cached_models=%s (len=%d)", pid, type(cached_models).__name__, len(cached_models))
        models = _provider_effective_models(provider, models, cfg)
        cli_models = _provider_models_for_cli(cli_name, models)

        if selected_model:
            if not _provider_supports_model_for_cli(provider, cli_name, selected_model):
                probe_debug_logger.info("  %s: SKIP (cli/model incompatible for %s -> %s)", pid, cli_name, selected_model)
                continue
            if selected_model not in models:
                probe_debug_logger.info("  %s: SKIP (model '%s' not in %s)", pid, selected_model, models[:5])
                continue
            option_models = [selected_model]
        else:
            if not _provider_supports_cli_name(provider, cli_name):
                probe_debug_logger.debug("  %s: SKIP (cli not supported)", pid)
                continue
            option_models = cli_models

        if not option_models:
            probe_debug_logger.info("  %s: SKIP (no option models for cli=%s)", pid, cli_name)
            continue

        probe_debug_logger.info("  %s: ADDED (option_models=%s)", pid, option_models)
        options.append({
            "kind": "provider",
            "id": provider.get("id"),
            "runtime": _runtime_with_priority(provider, model_name=selected_model, family_name=selected_family),
            "models": option_models,
            "label": _runtime_choice_label(provider),
            "title": _provider_label(provider),
            "desc": "网关",
            "icon": "🌐",
            "priority": (
                _runtime_priority_for_family(provider, selected_family)
                if selected_family
                else provider.get("priority", DEFAULT_PRIORITY)
            ),
            "priority_family": selected_family,
            "is_default": provider.get("id") == default_provider.get("id"),
            "launch_cli": cli_name,
        })
    return options


def _account_options_for_model(cfg, cli_name, default_models, model_info=None, allow_selected_model=False):
    selected_model = _resolve_model_name(model_info) if model_info else ""
    selected_family, _ = _infer_model_family(selected_model) if selected_model else ("", "")
    options = []
    defaults = cfg.get("account", {}).get("defaults", {})

    for account_def in cfg.get("accounts", []):
        if not isinstance(account_def, dict) or not account_def.get("enabled", True):
            continue
        account_cli = account_def.get("cli")
        if account_cli not in OAUTH_CAPABLE_CLIS:
            continue
        # 止血：临时禁用 Gemini/Codex 官方账号经由 Claude session 的桥接入口。
        bridgeable_to_claude = False
        if account_cli != cli_name and not bridgeable_to_claude:
            continue
        if selected_model and not allow_selected_model and not bridgeable_to_claude:
            continue
        if selected_model and not _model_matches_account_cli(account_cli, selected_model):
            continue
        runtime = resolve_account_context(cfg, account_id=account_def["id"], cli_name=account_cli)
        launch_cli = account_cli
        desc = "官方"
        if bridgeable_to_claude:
            bridged = dict(runtime)
            bridged["auth_mode"] = "oauth_bridge"
            bridged["bridge_source_cli"] = account_cli
            bridged["bridge_target_cli"] = "claude"
            bridged["bridge_model"] = selected_model
            bridged["bridge_account_id"] = runtime.get("id")
            runtime = bridged
            launch_cli = "claude"
            desc = "官方桥接"
        runtime = _runtime_with_priority(runtime, model_name=selected_model, family_name=selected_family)
        options.append({
            "kind": "account",
            "id": runtime.get("id"),
            "runtime": runtime,
            "models": [selected_model] if selected_model else list(default_models or []),
            "label": _runtime_choice_label(runtime),
            "title": _account_label(runtime),
            "desc": desc,
            "icon": "🔑",
            "priority": runtime.get("priority", DEFAULT_PRIORITY),
            "priority_family": selected_family,
            "is_default": runtime.get("id") == defaults.get(account_cli),
            "launch_cli": launch_cli,
        })
    return options


def _broker_options_for_cli(cfg, cli_name, model_info=None):
    # 止血：broker 先退出默认入口，只保留显式 mms broker 命令链。
    return []


def _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models):
    options = _provider_options_for_model(cfg, cli_name, default_provider, default_models)
    for option in options:
        runtime = option["runtime"]
        models = option["models"]
        if cli_name not in CLI_MODEL_FAMILY_HINTS:
            return runtime, models
        if models:
            return runtime, models
    return None, []


def _resolve_source_default_index(options, preferred_cli):
    if not options:
        return 0
    for idx, option in enumerate(options):
        if option.get("kind") == "provider" and option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli:
            return idx
    for idx, option in enumerate(options):
        if option.get("is_default"):
            return idx
    return 0


def _resolve_launch_runtime(cfg, cli_name, default_provider, default_models, account_id=None, provider_id=None):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return _resolve_provider_for_cli(cfg, cli_name, provider, _probe_models(provider, emit_output=False).get("models"))
    if cli_name in MMS_MANAGED_OAUTH_CLIS:
        account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        if account_id and account is not None:
            return account, list(default_models or [])
        if account is not None and account.get("enabled", True):
            return account, list(default_models or [])
    return _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def _resolve_provider_runtime(cfg, cli_name, default_provider, default_models, provider_id=None):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return _resolve_provider_for_cli(cfg, cli_name, provider, _probe_models(provider, emit_output=False).get("models"))
    return _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def _runtime_choice_label(runtime):
    if runtime.get("auth_mode") == "broker_profile":
        return f"Broker / {runtime.get('name', runtime.get('id', 'broker'))}"
    if runtime.get("auth_mode") == "oauth_bridge":
        return f"官方桥接 / {_account_label(runtime)}"
    if runtime.get("auth_mode") == "oauth":
        return f"官方 / {_account_label(runtime)}"
    return f"网关 / {_provider_label(runtime)}"


def _list_runtime_sources(cfg, cli_name, default_provider, default_models, model_info=None, allow_selected_model_accounts=False):
    options = _provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=model_info)
    options.extend(
        _account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info=model_info,
            allow_selected_model=allow_selected_model_accounts,
        )
    )
    options.extend(_broker_options_for_cli(cfg, cli_name, model_info=model_info))
    options.sort(key=lambda item: (
        -int(item.get("priority", DEFAULT_PRIORITY) or DEFAULT_PRIORITY),
        0 if item.get("launch_cli") == cli_name else 1,
        0 if item["kind"] == "provider" else 1 if item["kind"] == "account" else 2,
        item.get("title", ""),
    ))
    default_choice = _resolve_source_default_index(options, cli_name)
    return options, default_choice


def _runtime_source_kind_label(runtime):
    if not runtime:
        return "网关"
    if runtime.get("runtime_kind") == "opencode_profile":
        return "OpenCode"
    auth_mode = runtime.get("auth_mode")
    if auth_mode == "broker_profile" or runtime.get("runtime_kind") == "broker":
        return "Broker"
    if auth_mode == "oauth_bridge":
        return "官方桥接"
    if auth_mode == "oauth":
        return "官方"
    return "网关"


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
    text = str(value or "").strip()
    if len(text) <= keep * 2:
        return text or "-"
    return f"{text[:keep]}***{text[-keep:]}"


def _mask_email_value(value):
    text = str(value or "").strip()
    if not text or "@" not in text:
        return _mask_identity_value(text)
    name, domain = text.split("@", 1)
    if len(name) <= 2:
        masked_name = name[:1] + "*"
    else:
        masked_name = name[:2] + "***"
    return f"{masked_name}@{domain}"


def _runtime_network_summary_for_confirm(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    proxy = str(runtime.get("proxy") or "").strip()
    timezone_name = str(runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE).strip() or DEFAULT_ACCOUNT_TIMEZONE
    force_ipv4 = bool(_runtime_force_ipv4(runtime))
    mode = _snapshot_proxy_fingerprint(proxy)
    return f"{mode} | TZ {timezone_name} | IPv4 {'on' if force_ipv4 else 'auto'}"


def _load_runtime_identity_preview(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    home_dir = os.path.expanduser(str(runtime.get("home_dir") or "").strip())
    if not home_dir:
        return {}
    target = os.path.join(home_dir, ".claude.json")
    if not os.path.exists(target):
        return {}
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    oauth_account = data.get("oauthAccount") if isinstance(data.get("oauthAccount"), dict) else {}
    return {
        "user_id": str(data.get("userID") or oauth_account.get("accountUuid") or "").strip(),
        "account_uuid": str(oauth_account.get("accountUuid") or "").strip(),
        "org_uuid": str(oauth_account.get("organizationUuid") or "").strip(),
        "email": str(oauth_account.get("emailAddress") or "").strip(),
    }


def _confirm_context_lines(cli, runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    lines = []
    if runtime:
        runtime_id = str(runtime.get("id") or runtime.get("name") or "").strip()
        if runtime_id:
            lines.append(("Source", runtime_id))
        if cli == "claude":
            sidecar = runtime.get("vision_sidecar") if isinstance(runtime.get("vision_sidecar"), dict) else {}
            if sidecar and sidecar.get("enabled", True):
                provider_id = str(sidecar.get("provider_id") or "-").strip() or "-"
                model = str(sidecar.get("model") or "-").strip() or "-"
                lines.append(("Vision", f"{provider_id}/{model}"))
    if cli == "opencode":
        profile_label = str(runtime.get("opencode_profile_label") or runtime.get("opencode_profile") or "").strip()
        if profile_label:
            lines.append(("Profile", profile_label))
    if cli == "claude" and runtime.get("auth_mode") == "oauth":
        if _fake_upstream_enabled():
            lines.append(("Fake", "ON"))
        lines.append(("Proxy", str(_snapshot_proxy_fingerprint(runtime.get("proxy")))))
        lines.append(("TZ", str(runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE)))
        lines.append(("IPv4", "on" if _runtime_force_ipv4(runtime) else "auto"))
        lines.append(("Slot", f"pid-{os.getpid()}"))
        home_dir = os.path.expanduser(str(runtime.get("home_dir") or "").strip())
        if home_dir:
            lines.append(("Session", os.path.join(home_dir, "s", str(os.getpid()))))
        identity = _load_runtime_identity_preview(runtime)
        if identity.get("email"):
            lines.append(("Email", _mask_email_value(identity.get("email"))))
        if identity.get("user_id"):
            lines.append(("UserID", _mask_identity_value(identity.get("user_id"))))
        if identity.get("org_uuid"):
            lines.append(("OrgID", _mask_identity_value(identity.get("org_uuid"))))
        network_guard = runtime.get("_network_guard") if isinstance(runtime.get("_network_guard"), dict) else {}
        if network_guard:
            lines.append(("DNS", str(network_guard.get("dns_mode") or "-")))
            proxy_validation = str(network_guard.get("proxy_validation") or "").strip()
            if proxy_validation == "skipped_fake":
                lines.append(("Check", "skipped(fake)"))
            if network_guard.get("ipv4_egress") not in {"", "-"}:
                lines.append(("IPv4Egress", str(network_guard.get("ipv4_egress") or "-")))
            if network_guard.get("ipv6_egress") not in {"", "-", "blocked"}:
                lines.append(("IPv6Egress", str(network_guard.get("ipv6_egress") or "-")))
            target_states = []
            for item in network_guard.get("targets") or []:
                label = str(item.get("label") or "?")
                target_states.append(f"{label}:{'ok' if item.get('ok') else 'fail'}")
            if target_states:
                lines.append(("Reach", " ".join(target_states[:3])))
            no_proxy_conflicts = network_guard.get("no_proxy_conflicts") or []
            if no_proxy_conflicts:
                lines.append(("Leak", ",".join(no_proxy_conflicts[:2])))
        report = runtime.get("_account_guard_report") if isinstance(runtime.get("_account_guard_report"), dict) else {}
        if report:
            lines.append(("Score", str(report.get("score", "-"))))
            lines.append(("Sessions", str(report.get("active_sessions_after", "-"))))
            drift = report.get("drift_fields") or []
            lines.append(("Profile", "stable" if not drift else ",".join(drift)))
    return lines[:12]


def _build_confirm_preview_catalog(cli, runtime, *, has_caveman=False, has_nsr=False, has_ecc=False, has_omc=False):
    runtime = runtime if isinstance(runtime, dict) else {}
    allow_execution_surfaces = not (cli == "claude" and runtime.get("auth_mode") == "oauth")
    preview = {
        "allow_execution_surfaces": allow_execution_surfaces,
        "mcp": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
        "skills": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
        "hooks": {"always": [], "caveman": [], "nsr": [], "ecc": [], "omc": []},
    }

    if cli not in {"claude", "codex", "opencode", "agy"}:
        return preview

    try:
        from mms_launchers import (
            _build_codex_session_hooks,
            _configure_claude_caveman_hooks,
            _configure_claude_nsr_hooks,
            _configure_claude_ecc_hooks,
            _configure_claude_omc_hooks,
            _agent_pack_mcp_servers,
            _default_hive_session_mcp_server,
            _default_pilot_session_mcp_server,
            _filter_claude_session_hooks,
            _load_global_claude_settings_template,
            _load_mms_claude_settings_template,
            _load_real_claude_settings,
            _merge_claude_settings,
            _merge_mms_session_hooks,
            _opencode_rtk_plugin_path,
            _opencode_xmem_plugin_path,
            _resolve_agent_browser_root,
            _resolve_auto_github_contributor_root,
            _resolve_caveman_root,
            _resolve_ecc_root,
            _resolve_nsr_root,
            _resolve_omc_root,
            _resolve_token_saver_root,
            _resolve_toon_root,
            _resolve_weber_root,
            _resolve_web_access_root,
            _resolve_xmem_root,
            _sanitize_claude_inherited_settings_payload,
            _session_managed_mcp_servers,
            _strip_agent_im_hooks,
        )
    except Exception:
        return preview

    def _append(panel_key, scope, *, title, summary="", details=None, disable_key=None):
        panel = preview.get(panel_key)
        if not isinstance(panel, dict):
            return
        bucket = panel.get(scope)
        if not isinstance(bucket, list):
            return
        title = str(title or "").strip()
        summary = str(summary or "").strip()
        normalized_details = []
        for item in details or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            label = str(item[0] or "").strip()
            value = str(item[1] or "").strip()
            if label and value:
                normalized_details.append((label, value))
        entry = {
            "title": title,
            "summary": summary,
            "details": normalized_details,
        }
        disable_key = str(disable_key or "").strip()
        if disable_key:
            entry["disable_key"] = disable_key
        if not title:
            return
        signature = (
            entry["title"],
            entry["summary"],
            tuple(entry["details"]),
        )
        for existing in bucket:
            if not isinstance(existing, dict):
                continue
            existing_signature = (
                str(existing.get("title") or "").strip(),
                str(existing.get("summary") or "").strip(),
                tuple(
                    (str(label or "").strip(), str(value or "").strip())
                    for label, value in (existing.get("details") or [])
                    if str(label or "").strip() and str(value or "").strip()
                ),
            )
            if existing_signature == signature:
                return
        bucket.append(entry)

    def _event_label(event_name, matcher=""):
        mapping = {
            "SessionStart": _L("会话启动", "SessionStart"),
            "Stop": _L("会话结束", "Stop"),
            "UserPromptSubmit": _L("提交提示", "UserPromptSubmit"),
            "PreToolUse": _L("工具前", "PreToolUse"),
            "PostToolUse": _L("工具后", "PostToolUse"),
            "PreCompact": _L("压缩前", "PreCompact"),
            "PostCompact": _L("压缩后", "PostCompact"),
        }
        label = mapping.get(str(event_name or "").strip(), str(event_name or "").strip())
        matcher_text = str(matcher or "").strip()
        return f"{label} · {matcher_text}" if matcher_text else label

    def _abbrev_path(path_text):
        path_text = str(path_text or "").strip()
        if not path_text:
            return ""
        if "://" in path_text:
            return path_text
        if os.path.isabs(path_text):
            normalized = os.path.abspath(path_text)
            real_home = os.path.abspath(resolve_real_user_home())
            cwd = os.path.abspath(_safe_getcwd())
            try:
                if os.path.commonpath([normalized, cwd]) == cwd:
                    return f".{os.sep}{os.path.relpath(normalized, cwd)}"
            except ValueError:
                pass
            try:
                if os.path.commonpath([normalized, real_home]) == real_home:
                    suffix = os.path.relpath(normalized, real_home)
                    return "~" if suffix == "." else os.path.join("~", suffix)
            except ValueError:
                pass
            return normalized
        return path_text

    def _command_target(command, args=None):
        text = str(command or "").strip()
        parts = []
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if isinstance(args, list):
            parts.extend(str(item or "").strip() for item in args if str(item or "").strip())
        generic_runners = {
            "bash", "sh", "node", "python", "python3",
            "/bin/bash", "/bin/sh", "/usr/bin/env",
        }
        for token in reversed(parts):
            token = str(token or "").strip()
            if not token or token.startswith("-") or token.startswith("--"):
                continue
            if "/" in token:
                return os.path.basename(token), token
        for token in reversed(parts):
            token = str(token or "").strip()
            if not token or token.startswith("-") or "=" in token or token in generic_runners:
                continue
            return token[:64], token
        return (_L("内联命令", "inline command"), text[:256] if text else "")

    def _skill_path(root_path):
        root_path = str(root_path or "").strip()
        if not root_path:
            return ""
        skill_md = os.path.join(root_path, "SKILL.md")
        return skill_md if os.path.isfile(skill_md) else root_path

    def _hook_descriptor(command):
        display_name, target_path = _command_target(command)
        lower_command = str(command or "").strip().lower()
        lower_target = str(target_path or "").strip().lower()
        basename = os.path.basename(target_path or display_name).lower()

        if (
            "brainkeeper-session-start-hook" in lower_target
            or "mindkeeper-session-start-hook" in lower_target
            or basename in {"brainkeeper-session-start-hook.sh", "mindkeeper-session-start-hook.sh"}
        ):
            return _L("恢复上次进度", "Resume last work"), _L("BrainKeeper 恢复提示", "BrainKeeper restore hint")
        if (
            "brainkeeper-session-end-hook" in lower_target
            or "mindkeeper-session-end-hook" in lower_target
            or basename in {"brainkeeper-session-end-hook.sh", "mindkeeper-session-end-hook.sh"}
        ):
            return _L("保存当前进度", "Save current progress"), _L("BrainKeeper 会话归档", "BrainKeeper session checkpoint")
        if (
            "brainkeeper-token-monitor-hook" in lower_target
            or "mindkeeper-token-monitor-hook" in lower_target
            or basename in {"brainkeeper-token-monitor-hook.sh", "mindkeeper-token-monitor-hook.sh"}
        ):
            return _L("监控 token 用量", "Monitor token usage"), _L("BrainKeeper token 监控", "BrainKeeper token monitor")
        if "map-auto-index" in lower_target or basename == "map-auto-index.sh":
            return _L("Map 自动索引", "Map auto-index"), _L("刷新项目结构索引", "Refresh project structure index")
        if "codegraph-auto-index" in lower_target or basename == "claude-codegraph-auto-index.sh":
            return "CodeGraph 自动索引", _L("刷新项目 CodeGraph 索引", "Refresh project CodeGraph index")
        if "xmem-session-start-hook" in lower_target or basename == "xmem-session-start-hook.sh":
            return "xmem 自动同步", _L("注册/同步当前项目 truth index", "Register/sync the current project truth index")
        if "xmem-session-end-hook" in lower_target or basename == "xmem-session-end-hook.sh":
            return "xmem 收尾同步", _L("记录会话结束，不注入知识正文", "Record session close without injecting memory body")
        if "nsr-claude-hook" in lower_target or "nsr-codex-hook" in lower_target or "nsr-builtin-hook" in lower_target:
            return "NSR 持续运行", _L("按 active NSR goal 注入继续执行提示", "Inject active NSR goal continuation hints")
        if "claude-feishu-webfetch-guard" in lower_target or basename == "claude-feishu-webfetch-guard.sh":
            return _L("飞书 WebFetch 防护", "Feishu WebFetch guard"), _L("拦截高风险飞书抓取", "Guard risky Feishu fetches")
        if "rtk-rewrite" in lower_target or basename == "rtk-rewrite.sh":
            return "RTK Bash 改写", _L("压缩高 token Bash 命令", "Rewrite token-heavy Bash commands")
        if basename == "hook.sh" and "read-once" in (lower_target or lower_command):
            return _L("Read-once 读取拦截", "Read-once read hook"), _L("避免重复全文读取", "Avoid redundant full-file rereads")
        if basename == "compact.sh" and "read-once" in (lower_target or lower_command):
            return _L("Read-once 压缩整理", "Read-once compact"), _L("编辑后优先回看 diff", "Prefer diff after edits")
        if "hive-compact-hook" in lower_target or basename == "hive-compact-hook.sh":
            return _L("Hive 压缩整理", "Hive compact"), _L("compact 前后整理上下文", "Summarize context before and after compact")
        if "caveman-activate" in lower_target or basename == "caveman-activate.js":
            return "Caveman 激活", _L("会话启动时载入 Caveman 模式", "Load Caveman mode on session start")
        if "caveman-mode-tracker" in lower_target or basename == "caveman-mode-tracker.js":
            return "Caveman 模式跟踪", _L("跟踪用户是否继续使用 Caveman", "Track whether Caveman stays enabled")
        if "plugin-hook-bootstrap" in lower_target or basename == "plugin-hook-bootstrap.js":
            return "ECC Hook 初始化", _L("载入 ECC hook 集", "Load ECC hook bundle")
        if "session-start-bootstrap" in lower_target or basename == "session-start-bootstrap.js":
            return "ECC 会话初始化", _L("会话启动时准备 ECC 运行环境", "Prepare ECC runtime on session start")
        if "run-with-flags" in lower_target or basename in {"run-with-flags.js", "run-with-flags-shell.sh"}:
            return "ECC Flag 包装", _L("为命令补充 ECC flags", "Wrap commands with ECC flags")
        if "pre-bash-dispatcher" in lower_target or basename == "pre-bash-dispatcher.js":
            return "ECC Bash 前置分发", _L("Bash 执行前做规则分发", "Dispatch ECC rules before Bash")
        if "post-bash-dispatcher" in lower_target or basename == "post-bash-dispatcher.js":
            return "ECC Bash 后置分发", _L("Bash 执行后补充检查", "Dispatch ECC checks after Bash")
        if "quality-gate" in lower_target or basename == "quality-gate.js":
            return "ECC 质量门", _L("关键阶段做质量检查", "Run ECC quality gates")
        if "stop-format-typecheck" in lower_target or basename == "stop-format-typecheck.js":
            return "ECC 停止前检查", _L("停止前做格式化与类型检查", "Run format and type checks before stop")
        if "design-quality-check" in lower_target or basename == "design-quality-check.js":
            return "ECC 设计质量检查", _L("设计相关质量检查", "Run design quality checks")
        if "post-edit-accumulator" in lower_target or basename == "post-edit-accumulator.js":
            return "ECC 编辑累积", _L("编辑后累积上下文与检查", "Accumulate edit context after changes")
        if "keyword-detector" in lower_target or basename == "keyword-detector.mjs":
            return "OMC 关键词检测", _L("识别 autopilot / ralph / team 等触发词", "Detect autopilot / ralph / team keywords")
        if "skill-injector" in lower_target or basename == "skill-injector.mjs":
            return "OMC Skill 注入", _L("按任务注入 OMC workflow skills", "Inject OMC workflow skills")
        if "session-start" in lower_target or basename == "session-start.mjs":
            return "OMC 会话初始化", _L("准备 OMC runtime 与会话状态", "Prepare OMC runtime and session state")
        if "pre-tool-enforcer" in lower_target or basename == "pre-tool-enforcer.mjs":
            return "OMC 工具前检查", _L("工具执行前做约束检查", "Run checks before tool use")
        if "permission-handler" in lower_target or basename == "permission-handler.mjs":
            return "OMC 权限处理", _L("处理 OMC permission request", "Handle OMC permission requests")
        if "post-tool-verifier" in lower_target or basename == "post-tool-verifier.mjs":
            return "OMC 工具后验证", _L("工具执行后验证交付物", "Verify outputs after tool use")
        if "subagent-tracker" in lower_target or basename == "subagent-tracker.mjs":
            return "OMC Agent 跟踪", _L("跟踪 subagent 生命周期", "Track subagent lifecycle")
        if "context-guard-stop" in lower_target or basename == "context-guard-stop.mjs":
            return "OMC 上下文防护", _L("停止前检查上下文安全", "Check context safety on stop")
        if "persistent-mode" in lower_target or basename == "persistent-mode.mjs":
            return "OMC 持续模式", _L("维持 ralph/verify loop 状态", "Maintain ralph / verify loop state")
        if "code-simplifier" in lower_target or basename == "code-simplifier.mjs":
            return "OMC 简化检查", _L("停止前触发 code simplifier", "Run code simplifier on stop")
        if "oh-my-claudecode" in lower_target or "oh-my-claudecode" in lower_command:
            return "OMC Hook", _L("OMC orchestration runtime hook", "OMC orchestration runtime hook")
        if basename:
            return os.path.splitext(os.path.basename(target_path or display_name))[0], _L("托管 hook", "Managed hook")
        return display_name, _L("托管 hook", "Managed hook")

    def _mcp_detail(spec):
        spec = spec if isinstance(spec, dict) else {}
        url = str(spec.get("url") or "").strip()
        if url:
            shortened = _abbrev_path(url)
            return {
                "summary": f"url · {shortened}",
                "details": [
                    ("URL", url),
                    (_L("类型", "Type"), str(spec.get("type") or "sse").strip() or "sse"),
                ],
            }
        command = str(spec.get("command") or "").strip()
        if command:
            type_name = str(spec.get("type") or "stdio").strip() or "stdio"
            display_name, target_path = _command_target(command, spec.get("args"))
            path_value = target_path or command
            return {
                "summary": f"{type_name} · {_abbrev_path(path_value)}",
                "details": [
                    (_L("类型", "Type"), type_name),
                    (_L("路径", "Path"), path_value),
                    (_L("命令", "Command"), command),
                ],
                "target_name": display_name,
            }
        type_name = str(spec.get("type") or "").strip()
        return {
            "summary": type_name or _L("托管", "Managed"),
            "details": [(_L("类型", "Type"), type_name or _L("托管", "Managed"))],
        }

    def _append_hooks(scope, hooks_data):
        hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
        for event_name in sorted(hooks_data):
            groups = hooks_data.get(event_name)
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                for hook in group.get("hooks") or []:
                    if not isinstance(hook, dict):
                        continue
                    if str(hook.get("type") or "").strip() != "command":
                        continue
                    command_text = str(hook.get("command") or "").strip()
                    title, hint = _hook_descriptor(command_text)
                    display_name, target_path = _command_target(command_text)
                    event_label = _event_label(event_name, matcher)
                    details = [
                        (_L("触发", "Trigger"), event_label),
                        (_L("路径", "Path"), target_path or display_name),
                    ]
                    if command_text and command_text != (target_path or display_name):
                        details.append((_L("命令", "Command"), command_text))
                    _append(
                        "hooks",
                        scope,
                        title=title,
                        summary=f"{event_label} · {hint}",
                        details=details,
                        disable_key=command_text,
                    )

    def _list_skill_entries(*parent_dirs):
        entries = []
        seen = set()
        for parent_dir in parent_dirs:
            parent_dir = str(parent_dir or "").strip()
            if not parent_dir or not os.path.isdir(parent_dir):
                continue
            try:
                child_names = sorted(os.listdir(parent_dir))
            except OSError:
                continue
            for entry_name in child_names:
                skill_dir = os.path.join(parent_dir, entry_name)
                skill_md = os.path.join(skill_dir, "SKILL.md")
                if not os.path.isdir(skill_dir) or not os.path.isfile(skill_md):
                    continue
                if entry_name in seen:
                    continue
                seen.add(entry_name)
                entries.append({"name": entry_name, "path": skill_md})
        return entries

    def _append_skill_entries(scope, entries, detail):
        for entry in entries:
            if isinstance(entry, str):
                name = str(entry).strip()
                path = ""
            else:
                name = str((entry or {}).get("name") or "").strip()
                path = str((entry or {}).get("path") or "").strip()
            if not name:
                continue
            details = [(_L("来源", "Source"), detail)]
            if path:
                details.insert(0, (_L("路径", "Path"), path))
            _append(
                "skills",
                scope,
                title=name,
                summary=detail,
                details=details,
                disable_key=name,
            )

    def _count_files(*parent_dirs):
        total = 0
        seen = set()
        for parent_dir in parent_dirs:
            parent_dir = str(parent_dir or "").strip()
            if not parent_dir or not os.path.isdir(parent_dir):
                continue
            for root_dir, _dirnames, filenames in os.walk(parent_dir):
                for filename in filenames:
                    file_path = os.path.join(root_dir, filename)
                    if file_path in seen:
                        continue
                    seen.add(file_path)
                    total += 1
        return total

    def _append_skill_collection(
        scope,
        entries,
        detail,
        *,
        bundle_title="",
        bundle_root="",
        collapse_threshold=12,
        bundle_note="",
        extra_details=None,
        bundle_disable_key="",
    ):
        entries = list(entries or [])
        if len(entries) <= max(1, int(collapse_threshold or 1)):
            _append_skill_entries(scope, entries, detail)
            return

        sample_names = ", ".join(
            str((entry or {}).get("name") or "").strip()
            for entry in entries[:5]
            if str((entry or {}).get("name") or "").strip()
        )
        details = []
        if bundle_root:
            details.append((_L("路径", "Path"), bundle_root))
        details.append((_L("数量", "Count"), str(len(entries))))
        if sample_names:
            suffix = " …" if len(entries) > 5 else ""
            details.append((_L("样例", "Samples"), f"{sample_names}{suffix}"))
        for item in extra_details or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            label = str(item[0] or "").strip()
            value = str(item[1] or "").strip()
            if label and value:
                details.append((label, value))
        details.append((_L("来源", "Source"), detail))
        if bundle_note:
            details.append((_L("说明", "Note"), bundle_note))
        _append(
            "skills",
            scope,
            title=bundle_title or detail,
            summary=_L(f"{len(entries)} 个 skill", f"{len(entries)} skills"),
            details=details,
            disable_key=bundle_disable_key or bundle_title or detail,
        )

    if cli == "claude":
        base_settings = _load_real_claude_settings()
        managed_mcp = _session_managed_mcp_servers(
            base_settings,
            allow_execution_surfaces=allow_execution_surfaces,
        )
        for name in sorted(managed_mcp):
            mcp_entry = _mcp_detail(managed_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )

        template_settings = _load_mms_claude_settings_template()
        inherited_settings = _sanitize_claude_inherited_settings_payload(
            base_settings,
            allow_execution_surfaces=allow_execution_surfaces,
        )
        merged_settings = _merge_claude_settings(
            inherited_settings,
            _load_global_claude_settings_template(),
        )
        base_hooks = _filter_claude_session_hooks(
            _merge_mms_session_hooks(
                _strip_agent_im_hooks(merged_settings.get("hooks")),
                template_settings.get("hooks"),
            ),
            allow_execution_surfaces=allow_execution_surfaces,
        )
        base_hooks = _configure_claude_nsr_hooks(base_hooks, enable_nsr=False)
        _append_hooks("always", base_hooks)
        if has_caveman and allow_execution_surfaces:
            _append_hooks(
                "caveman",
                _configure_claude_caveman_hooks({}, enable_caveman=True),
            )
        if has_nsr and allow_execution_surfaces:
            _append_hooks(
                "nsr",
                _configure_claude_nsr_hooks({}, enable_nsr=True),
            )
        if has_ecc and allow_execution_surfaces:
            _append_hooks(
                "ecc",
                _configure_claude_ecc_hooks({}, enable_ecc=True),
            )
        if has_omc and allow_execution_surfaces:
            _append_hooks(
                "omc",
                _configure_claude_omc_hooks({}, enable_omc=True),
            )
    elif cli == "codex":
        real_claude_json = os.path.join(resolve_real_user_home(), ".claude.json")
        try:
            with open(real_claude_json, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            codex_mcp = loaded.get("mcpServers", {}) if isinstance(loaded, dict) else {}
        except Exception:
            codex_mcp = {}
        codex_mcp = dict(codex_mcp) if isinstance(codex_mcp, dict) else {}
        hive_spec = _default_hive_session_mcp_server()
        if isinstance(hive_spec, dict) and str(hive_spec.get("command") or "").strip():
            codex_mcp.setdefault("hive", hive_spec)
        pilot_spec = _default_pilot_session_mcp_server()
        if isinstance(pilot_spec, dict) and str(pilot_spec.get("command") or "").strip():
            codex_mcp.setdefault("pilot", pilot_spec)
        for name in sorted(codex_mcp):
            mcp_entry = _mcp_detail(codex_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )

        real_codex_hooks = os.path.join(resolve_real_user_home(), ".codex", "hooks.json")
        try:
            with open(real_codex_hooks, "r", encoding="utf-8") as f:
                loaded_hooks = json.load(f)
            codex_hooks = _build_codex_session_hooks(loaded_hooks, enable_caveman=False)
        except Exception:
            codex_hooks = {}
        _append_hooks("always", (codex_hooks or {}).get("hooks"))
        if has_caveman:
            caveman_hooks = _build_codex_session_hooks({}, enable_caveman=True)
            _append_hooks("caveman", (caveman_hooks or {}).get("hooks"))
        if has_nsr:
            nsr_hooks = _build_codex_session_hooks({}, enable_nsr=True)
            _append_hooks("nsr", (nsr_hooks or {}).get("hooks"))
    elif cli == "opencode":
        rtk_plugin = _opencode_rtk_plugin_path(runtime)
        if rtk_plugin:
            _append(
                "hooks",
                "always",
                title="RTK OpenCode plugin",
                summary=_L("静默改写高 token Bash 命令", "Silently rewrite token-heavy Bash commands"),
                details=[
                    (_L("类型", "Type"), "OpenCode plugin"),
                    (_L("路径", "Path"), rtk_plugin),
                ],
                disable_key="opencode-rtk",
            )
        xmem_plugin = _opencode_xmem_plugin_path(runtime)
        if xmem_plugin:
            _append(
                "hooks",
                "always",
                title="xmem OpenCode plugin",
                summary=_L("会话启动/结束时轻量同步当前项目", "Lightly sync the current project on session start/end"),
                details=[
                    (_L("类型", "Type"), "OpenCode plugin"),
                    (_L("路径", "Path"), xmem_plugin),
                ],
                disable_key="opencode-xmem",
            )
    elif cli == "agy":
        agy_mcp = _session_managed_mcp_servers(
            {},
            allow_execution_surfaces=allow_execution_surfaces,
            disabled_session_surfaces=runtime.get("disabled_session_surfaces"),
        )
        for name in sorted(agy_mcp):
            mcp_entry = _mcp_detail(agy_mcp.get(name))
            _append(
                "mcp",
                "always",
                title=name,
                summary=str(mcp_entry.get("summary") or ""),
                details=mcp_entry.get("details") or [],
                disable_key=name,
            )
        agy_hooks = _merge_mms_session_hooks({})
        _append_hooks("always", agy_hooks)
        if has_caveman:
            _append_hooks(
                "caveman",
                _configure_claude_caveman_hooks({}, enable_caveman=True),
            )

    if allow_execution_surfaces:
        for pack_key, enabled in (("ecc", has_ecc), ("omc", has_omc)):
            if enabled:
                pack_mcp = _agent_pack_mcp_servers(pack_key)
                for name in sorted(pack_mcp):
                    mcp_entry = _mcp_detail(pack_mcp.get(name))
                    _append(
                        "mcp",
                        pack_key,
                        title=name,
                        summary=str(mcp_entry.get("summary") or ""),
                        details=mcp_entry.get("details") or [],
                        disable_key=name,
                    )

        if _resolve_web_access_root():
            web_access_root = _resolve_web_access_root()
            _append_skill_entries(
                "always",
                [{"name": "web-access", "path": _skill_path(web_access_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_weber_root():
            weber_root = _resolve_weber_root()
            _append_skill_entries(
                "always",
                [{"name": "weber", "path": _skill_path(weber_root)}],
                _L("会话技能", "Session skill"),
            )
        if cli in {"codex", "agy"} and _resolve_agent_browser_root():
            agent_browser_root = _resolve_agent_browser_root()
            _append_skill_entries(
                "always",
                [{"name": "agent-browser", "path": _skill_path(agent_browser_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_toon_root():
            toon_root = _resolve_toon_root()
            _append_skill_entries(
                "always",
                [{"name": "toon", "path": _skill_path(toon_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_token_saver_root():
            token_saver_root = _resolve_token_saver_root()
            _append_skill_entries(
                "always",
                [{"name": "token-saver", "path": _skill_path(token_saver_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_xmem_root():
            xmem_root = _resolve_xmem_root()
            _append_skill_entries(
                "always",
                [{"name": "xmem", "path": _skill_path(xmem_root)}],
                _L("会话技能", "Session skill"),
            )
        if _resolve_auto_github_contributor_root():
            auto_github_contributor_root = _resolve_auto_github_contributor_root()
            _append_skill_entries(
                "always",
                [
                    {
                        "name": "auto-github-contributor",
                        "path": _skill_path(auto_github_contributor_root),
                    }
                ],
                _L("会话技能", "Session skill"),
            )

        caveman_root = _resolve_caveman_root() if has_caveman else ""
        if caveman_root:
            caveman_skills = _list_skill_entries(os.path.join(caveman_root, "skills"))
            if not caveman_skills:
                caveman_skills = [{"name": "caveman", "path": _skill_path(caveman_root)}]
            _append_skill_collection(
                "caveman",
                caveman_skills,
                _L("Caveman 包", "Caveman bundle"),
                bundle_title=_L("Caveman 能力包", "Caveman bundle"),
                bundle_root=caveman_root,
                collapse_threshold=12,
                bundle_note=_L("这些是可用技能目录，不代表本次会全部执行。", "These are available skills, not all executed on launch."),
                bundle_disable_key="caveman",
            )

        nsr_root = _resolve_nsr_root() if has_nsr else ""
        if nsr_root:
            _append_skill_entries(
                "nsr",
                [{"name": "nsr", "path": _skill_path(nsr_root)}],
                _L("NSR 运行时", "NSR runtime"),
            )

        ecc_root = _resolve_ecc_root() if has_ecc else ""
        if ecc_root:
            ecc_skills = _list_skill_entries(
                os.path.join(ecc_root, ".claude", "skills"),
                os.path.join(ecc_root, ".agents", "skills"),
                os.path.join(ecc_root, "skills"),
            )
            if not ecc_skills:
                ecc_skills = [{"name": "ecc", "path": _skill_path(ecc_root)}]
            ecc_command_count = _count_files(
                os.path.join(ecc_root, ".claude", "commands"),
                os.path.join(ecc_root, "commands"),
            )
            ecc_rule_count = _count_files(
                os.path.join(ecc_root, ".claude", "rules"),
                os.path.join(ecc_root, "rules"),
            )
            _append_skill_collection(
                "ecc",
                ecc_skills,
                _L("ECC 包", "ECC bundle"),
                bundle_title=_L("ECC 能力包", "ECC bundle"),
                bundle_root=ecc_root,
                collapse_threshold=12,
                bundle_note=_L("这些是可用技能目录，不代表本次会全部执行；自动生效主要看 hooks 面板。", "These are available skills, not all executed on launch; automatic behavior mainly comes from hooks."),
                extra_details=[
                    (_L("命令", "Commands"), str(ecc_command_count)),
                    (_L("规则", "Rules"), str(ecc_rule_count)),
                ],
                bundle_disable_key="ecc",
            )

        omc_root = _resolve_omc_root() if has_omc else ""
        if omc_root:
            omc_skills = _list_skill_entries(os.path.join(omc_root, "skills"))
            if not omc_skills:
                omc_skills = [{"name": "omc", "path": _skill_path(omc_root)}]
            omc_agent_count = _count_files(os.path.join(omc_root, "agents"))
            _append_skill_collection(
                "omc",
                omc_skills,
                _L("OMC 包", "OMC bundle"),
                bundle_title=_L("OMC 能力包", "OMC bundle"),
                bundle_root=omc_root,
                collapse_threshold=12,
                bundle_note=_L("启用 orchestration runtime；可能写入 .omc/ 并使用 team/tmux/CLI worker。", "Enables orchestration runtime; may write .omc/ and use team/tmux/CLI workers."),
                extra_details=[
                    (_L("Agents", "Agents"), str(omc_agent_count)),
                ],
                bundle_disable_key="omc",
            )

    return preview


def confirm_launch(cli, model_info, once=False, runtime=None):
    if isinstance(model_info, dict):
        model_items = [f"{k}={v}" for k, v in model_info.items() if k != "subagent" and v]
        model_display = ", ".join(model_items) if model_items else "官方默认"
    else:
        model_display = model_info or "官方默认"

    mode_str = "一次性命令" if once else "交互会话"
    env_str = "临时注入，仅当前 CLI 进程可见" if cli in ("claude", "codex", "opencode", "agy") else "无需额外注入"
    source_line = ""
    if runtime:
        source_kind = _runtime_source_kind_label(runtime)
        source_label = runtime.get("name", runtime.get("id", "default"))
        source_line = f"[bold]来源:[/bold]   {source_kind} / {source_label}\n"
    profile_line = ""
    if cli == "opencode" and runtime:
        profile_label = str(runtime.get("opencode_profile_label") or runtime.get("opencode_profile") or "").strip()
        if profile_label:
            profile_line = f"[bold]Profile:[/bold] {profile_label}\n"
        entrypoint = _normalize_opencode_entrypoint(runtime.get("opencode_entrypoint")) or "tui"
        if entrypoint != "tui":
            profile_line += f"[bold]Entry:[/bold]   {entrypoint}\n"
    panel_text = (
        f"[bold]CLI:[/bold]    {cli}\n"
        f"[bold]模型:[/bold]   {model_display}\n"
        f"{source_line}"
        f"{profile_line}"
        f"[bold]启动:[/bold]   {mode_str}\n"
        f"[bold]环境:[/bold]   {env_str}\n"
        f"\n"
        f"[dim]Enter=启动  S=保存为预设  Q=取消[/dim]"
    )
    console.print(Panel(panel_text, title="确认启动", border_style="green"))

    choice = Prompt.ask("操作", choices=["", "s", "q"], default="")
    return choice


def _opencode_lite_pro_health_summary_text(repo_root=None, profile_id="agent"):
    profile_id = _normalize_opencode_profile_id(profile_id) or _OPENCODE_AGENT_PROFILE_ID
    latest = _load_opencode_route_health_latest(repo_root)
    expected_roles = {str(spec.get("key") or "").strip() for spec in _opencode_lite_pro_specs(profile_id)}
    expected = len(expected_roles)
    counts = {"live_healthy": 0, "degraded": 0, "unhealthy": 0, "blocked": 0, "untested": 0}
    role_rows = {}
    for row in latest.values():
        if not isinstance(row, dict) or row.get("profile") != profile_id:
            continue
        if (
            str(row.get("model") or "").strip().lower().startswith("mimo-")
            and str(row.get("protocol") or "").strip() == "openai_chat_completions"
            and row.get("error_class") == "cache_sensitive_wrong_protocol"
        ):
            continue
        role = str(row.get("role") or row.get("route_id") or "").strip()
        if role not in expected_roles:
            continue
        existing = role_rows.get(role)
        if existing is None or str(row.get("finished_at") or "") >= str(existing.get("finished_at") or ""):
            role_rows[role] = row
    for row in role_rows.values():
        status = str(row.get("status") or "untested")
        counts[status if status in counts else "untested"] += 1
    counts["untested"] += max(0, expected - len(role_rows))
    if counts["live_healthy"] == expected:
        return f"health: {expected}/{expected} healthy"
    parts = [f"{counts['live_healthy']}/{expected} healthy"]
    for status in ("degraded", "unhealthy", "blocked", "untested"):
        if counts[status]:
            parts.append(f"{counts[status]} {status}")
    return "health: " + ", ".join(parts)


def _opencode_profile_menu_options():
    options = []
    for option in _OPENCODE_PROFILE_OPTIONS:
        profile_id = _normalize_opencode_profile_id(option.get("profile_id") or option["id"])
        summary = option["summary"]
        if profile_id == _OPENCODE_AGENT_PROFILE_ID:
            lite_pro_health = _opencode_lite_pro_health_summary_text(profile_id=profile_id)
        else:
            lite_pro_health = ""
        if lite_pro_health:
            summary = f"{summary} {lite_pro_health}"
        options.append({
            "id": option["id"],
            "label": option["label"],
            "summary": summary,
            "badge": option.get("badge", ""),
        })
    return options


_AGY_CONNECT_PROFILE_ID = "__connect_agy_oauth__"


def _official_account_menu_options(cfg, cli_name):
    accounts = list(_accounts_for_cli(cfg, cli_name))
    defaults = cfg.get("account", {}).get("defaults", {}) if isinstance(cfg, dict) else {}

    def _sort_key(account):
        account_id = str(account.get("id") or "")
        is_default = account_id == defaults.get(cli_name)
        return (
            0 if is_default else 1,
            -int(account.get("priority", DEFAULT_PRIORITY) or DEFAULT_PRIORITY),
            _account_label(account),
            account_id,
        )

    options = []
    for account in sorted(accounts, key=_sort_key):
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            continue
        is_default = account_id == defaults.get(cli_name)
        summary_parts = [_L("官方 OAuth", "Official OAuth"), account_id]
        if is_default:
            summary_parts.append(_L("默认", "default"))
        options.append({
            "id": account_id,
            "label": _account_label(account),
            "summary": " / ".join(summary_parts),
            "badge": "*" if is_default else "OAuth",
        })

    if options or cli_name != "agy":
        return options

    legacy_gemini_count = len(_accounts_for_cli(cfg, "gemini"))
    if legacy_gemini_count:
        summary = _L(
            "检测到 Gemini CLI 旧账号；Antigravity 需要独立 agy OAuth，按 Enter 或 O 接入。",
            "Legacy Gemini CLI accounts detected; Antigravity needs a separate agy OAuth account. Press Enter or O to connect.",
        )
    else:
        summary = _L(
            "还没有 Antigravity OAuth account，按 Enter 或 O 接入。",
            "No Antigravity OAuth account yet. Press Enter or O to connect.",
        )
    return [{
        "id": _AGY_CONNECT_PROFILE_ID,
        "label": _L("接入 Antigravity OAuth", "Connect Antigravity OAuth"),
        "summary": summary,
        "badge": "O",
    }]


def _select_opencode_profile(use_tui=False):
    options = _opencode_profile_menu_options()
    if use_tui:
        try:
            from mms_tui import select_channel_action_tui
            return select_channel_action_tui(
                "OpenCode Mode",
                [(option["label"], option["summary"]) for option in options[:4]],
                [(option["id"], option["label"]) for option in options],
            )
        except Exception:
            return None

    _ensure_rich()
    table = Table(title="OpenCode Mode")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Mode", style="green")
    table.add_column("说明", style="dim")
    for idx, option in enumerate(options, 1):
        label = f"{option.get('badge')} {option['label']}".strip()
        table.add_row(str(idx), label, option["summary"])
    console.print(table)
    while True:
        try:
            choice = IntPrompt.ask("选择 OpenCode mode")
            if 1 <= choice <= len(options):
                return options[choice - 1]["id"]
            console.print(f"[red]请输入 1-{len(options)}[/red]")
        except KeyboardInterrupt:
            return None


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
    if stderr_only:
        print(message, file=sys.stderr)
    else:
        console.print(message)


def _preset_env_file_path(preset_name):
    safe_name = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(preset_name or "").strip().lower()
    ).strip("-_")
    safe_name = safe_name or "preset"
    return os.path.join(ENV_DIR, f"{safe_name}.sh")


def _resolve_named_preset(cfg, preset_name, *, stderr_only=False):
    presets = cfg.get("presets", {})
    if preset_name not in presets:
        _emit_preset_error(f"预设 '{preset_name}' 不存在", stderr_only=stderr_only)
        if presets:
            _emit_preset_error(f"可用预设: {', '.join(presets.keys())}", stderr_only=stderr_only)
        return None
    return _normalize_preset_entry(preset_name, presets[preset_name])


def _infer_preset_auth_mode(preset):
    """临时推断 preset 的 auth_mode，仅用于展示和 env/activate 解析，不落盘。"""
    if not isinstance(preset, dict):
        return None
    if preset.get("bridge"):
        return "oauth_bridge"
    if preset.get("account"):
        return "oauth"
    if preset.get("provider"):
        return "api_key"
    return None


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
    from mms_tui import select_load_balance_tui, save_lb_history
    from mms_launchers import (
        _caveman_available_for_cli,
        _ecc_available_for_claude,
        _nsr_available_for_cli,
        _omc_available_for_claude,
        launch_cli,
        get_export_env,
    )

    def _safe_tui_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            return "__interrupt__"

    current_cfg = cfg
    current_provider = provider
    current_cli_names = cli_names
    default_models = _probe_models(current_provider, emit_output=False).get("models")
    if account_id or provider_id:
        _trace_record("CLI flags", account=account_id, provider=provider_id)

    # 预构建品类数据（仅在配置变更时重建）
    def _rebuild_families():
        fbc = {}
        fd = {}
        pbc = {}
        pol = {}
        for cli_name in current_cli_names:
            raw = _build_model_families_for_cli(
                current_cfg, cli_name, current_provider, default_models
            )
            fam_list = []
            preferred_family = _CLI_DEFAULT_FAMILY_FIRST.get(cli_name)
            for f in raw:
                model_entries = [m for m in f["models"] if isinstance(m, dict)]
                total_use = sum(int(m.get("use_count", 0) or 0) for m in model_entries)
                family_last_used_at = max(
                    (str(m.get("last_used_at") or "").strip() for m in model_entries),
                    default="",
                )
                fam_list.append({
                    "family": f["family"],
                    "count": len(f["models"]),
                    "use_count": total_use,
                    "last_used_at": family_last_used_at,
                    "is_cold": _family_is_cold_for_tui(
                        f["family"],
                        total_use,
                        family_last_used_at,
                        preferred_family=preferred_family,
                    ),
                })
            # 最近使用的 family 优先；没有 recency 时再保留当前 CLI 默认主族群兜底置顶。
            fam_list = _sort_family_entries_for_tui(
                fam_list,
                preferred_family=preferred_family,
            )
            fbc[cli_name] = fam_list
            fd[cli_name] = {f["family"]: f["models"] for f in raw}
            pbc[cli_name] = {}
            pol[cli_name] = _make_provider_options_loader(
                current_cfg, cli_name, current_provider, default_models
            )
        return fbc, fd, pbc, pol

    families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = _rebuild_families()
    _families_dirty = False

    while True:
        if _families_dirty:
            families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = _rebuild_families()
            _families_dirty = False

        # 获取上次使用信息（按 CLI 分桶，TUI 内部按当前 tab 过滤）
        last_by_cli, _ = _get_scene_usage()

        result = _safe_tui_call(
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
            if cli == "agy":
                current_cfg, changed = _quick_connect_official(current_cfg, preset_cli="agy")
            else:
                current_cfg, changed = run_connect_wizard(current_cfg)
            if changed:
                _PROBE_CACHE.clear()
                import shutil as _shutil
                _shutil.rmtree(_PROBE_FILE_CACHE_DIR, ignore_errors=True)
                current_provider = ensure_provider_credentials(current_cfg)
                default_models = _probe_models(current_provider, emit_output=False).get("models")
                current_cli_names = _resolve_visible_clis(current_cfg, current_provider, default_models)
                _families_dirty = True
            continue

        # ── Broker experiment ──
        if action_type == "broker":
            if _launch_broker_experiment_interactive(current_cfg, cli):
                return True
            continue

        # ── OpenCode profile ──
        if action_type == "profile" and cli == "opencode":
            model_info, runtime_runtime = _resolve_opencode_profile_runtime(
                current_cfg,
                current_provider,
                default_models,
                action_data,
            )
            if runtime_runtime is None:
                console.print("[yellow]OpenCode Lite/Raw 未找到安全的 OpenAI-compatible GPT provider；请用 Heavy/OMO 或先配置 GPT provider。[/yellow]")
                continue
            _trace_record(
                "opencode profile",
                cli=cli,
                profile=runtime_runtime.get("opencode_profile"),
                model=model_info.get("model") if isinstance(model_info, dict) else model_info,
                provider=runtime_runtime.get("id"),
            )
            _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="opencode profile")
            # fall through to confirm
        if action_type == "profile" and cli == "agy":
            if action_data == _AGY_CONNECT_PROFILE_ID:
                current_cfg, changed = _quick_connect_official(current_cfg, preset_cli="agy")
                if changed:
                    _PROBE_CACHE.clear()
                    import shutil as _shutil
                    _shutil.rmtree(_PROBE_FILE_CACHE_DIR, ignore_errors=True)
                    current_provider = ensure_provider_credentials(current_cfg)
                    default_models = _probe_models(current_provider, emit_output=False).get("models")
                    current_cli_names = _resolve_visible_clis(current_cfg, current_provider, default_models)
                    _families_dirty = True
                continue
            runtime_runtime = resolve_account_context(current_cfg, account_id=action_data, cli_name=cli)
            if runtime_runtime is None or runtime_runtime.get("cli") != cli:
                console.print(f"[yellow]未找到 {cli} 官方账号: {action_data}[/yellow]")
                continue
            model_info = {}
            _trace_record("official account", cli=cli, account=runtime_runtime.get("id"))
            _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="official account")
            # fall through to confirm

        # ── Provider 浏览 ──
        if action_type == "provider_browse":
            from mms_tui import select_provider_browse_tui, select_provider_models_tui
            # 构建可用 provider 列表（当前 CLI 支持的、有 api_key 的）
            browse_providers = []
            seen_ids = set()
            for prov, _cached in _provider_candidates(current_cfg, current_provider, default_models):
                pid = prov.get("id", DEFAULT_PROVIDER_ID)
                if pid in seen_ids:
                    continue
                if not prov.get("enabled", True):
                    continue
                if not _provider_supports_cli_name(prov, cli):
                    continue
                if not prov.get("api_key"):
                    continue
                seen_ids.add(pid)
                browse_providers.append({
                    "id": pid,
                    "name": _provider_label(prov),
                    "role": prov.get("role", "auto"),
                    "priority": prov.get("priority", 100),
                })
            if not browse_providers:
                console.print("[yellow]没有可用的 Provider[/yellow]")
                continue
            prov_result = _safe_tui_call(select_provider_browse_tui, browse_providers)
            if prov_result is None or prov_result == "__interrupt__":
                continue
            selected_pid, selected_pname = prov_result
            # 获取该 provider 的完整上下文和模型列表
            selected_prov = resolve_provider_context(current_cfg, selected_pid)
            selected_probe = _probe_models(selected_prov, emit_output=False)
            prov_models = _filter_visible_models(selected_probe.get("models") or [])
            if not prov_models:
                console.print(f"[yellow]{selected_pname} 没有可用模型[/yellow]")
                continue
            model_result = _safe_tui_call(select_provider_models_tui, selected_pname, prov_models)
            if model_result is None:
                continue  # B 返回 provider 列表
            if model_result == "__exit__":
                return True  # Esc 完全退出
            model_info = model_result
            runtime_runtime = selected_prov
            _trace_record("provider browse", cli=cli, provider=selected_pid, model=model_info.get("model"))
            _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="provider browse")
            # fall through to confirm

        # ── 负载模式 ──
        if action_type == "load_balance":
            all_models = []
            cli_families = families_detail.get(cli, {})
            for fam_models in cli_families.values():
                all_models.extend(m["model"] for m in fam_models)
            lb_profiles = _load_balance_profiles(current_cfg)
            lb_default_profile = _default_load_balance_profile_name(current_cfg)
            lb_prov_opts = _build_provider_options_map(
                current_cfg, cli, current_provider, default_models, all_models
            ) if all_models else None
            lb_result = _safe_tui_call(
                select_load_balance_tui,
                available_models=all_models or None,
                families_detail=cli_families,
                provider_options_map=lb_prov_opts,
                profiles=lb_profiles,
                default_profile=lb_default_profile,
            )
            if lb_result == "__interrupt__":
                return True
            if lb_result is None:
                continue
            slot_provider_ids = {
                slot: provider_id
                for slot, provider_id in (lb_result.get("lb_slot_providers") or {}).items()
                if provider_id
            }
            model_info = dict(lb_result)
            _trace_record(
                "load balance",
                cli=cli,
                model=lb_result.get("model"),
                lb_medium=lb_result.get("lb_medium"),
                lb_light=lb_result.get("lb_light"),
                profile=lb_result.get("lb_profile"),
            )
            save_lb_history(
                lb_result["model"],
                lb_result.get("lb_medium", ""),
                lb_result.get("lb_light", ""),
                slot_providers=slot_provider_ids,
                label=lb_result.get("lb_label"),
            )
            # 用 heavy model 的 best provider 作为 runtime
            runtime_runtime = None
            runtime_from_best_provider = False
            heavy_provider_id = slot_provider_ids.get("heavy")
            if heavy_provider_id:
                runtime_runtime, slot_error = _resolve_lb_slot_provider(
                    current_cfg, cli, lb_result["model"], heavy_provider_id
                )
                if slot_error:
                    console.print(f"[yellow]{slot_error}[/yellow]")
                    continue
                _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice=f"profile provider:{heavy_provider_id}")
            else:
                runtime_runtime, _ = _resolve_best_provider(
                    current_cfg, lb_result["model"], current_provider, default_models, cli_name=cli
                )
                runtime_from_best_provider = runtime_runtime is not None
            if runtime_runtime is None:
                runtime_runtime, _, cli = _choose_runtime_source(
                    current_cfg, cli, current_provider, default_models,
                    account_id=account_id, provider_id=provider_id,
                    model_info=model_info, allow_selected_model_accounts=True,
                )
            if runtime_runtime is None:
                console.print(f"[yellow]{cli} 没有可用 provider 承载负载模式[/yellow]")
                continue
            if runtime_from_best_provider:
                _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="best provider")

            # 止血：暂时禁用跨 provider slot 切换，避免展示层和执行层 provider 漂移。
            # fall through to confirm below

        # ── 设置 ──
        elif action_type == "settings":
            from mms_tui import (
                select_channel_action_tui,
                select_language_tui,
                select_rescue_event_tui,
                select_settings_tui,
                select_provider_mgmt_tui,
            )
            settings_action = _safe_tui_call(select_settings_tui)
            if settings_action == "__interrupt__":
                return True
            if settings_action is None:
                continue
            if settings_action == "provider_mgmt":
                providers_raw = current_cfg.get("providers", [])
                result_providers = _safe_tui_call(select_provider_mgmt_tui, providers_raw)
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
                chosen_lang = _safe_tui_call(select_language_tui)
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
                from mms_registry_cli import config_v2_promotion_plan, consumer_bundle_status, diff_openrouter_catalog, fetch_openrouter_catalog, model_source_status, preview_doctor, publish_approved_bundle, refresh_source_snapshots, registry_status, registry_v2_save_plan, scheduled_refresh, source_freshness, verify_approved_bundle

                source_status = model_source_status(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config source")
                registry_title, registry_info, registry_actions = _model_source_status_tui_payload(source_status)
                registry_action = _safe_tui_call(
                    select_channel_action_tui,
                    registry_title,
                    registry_info,
                    registry_actions,
                )
                if registry_action == "__interrupt__":
                    return True
                if registry_action == "model_source_status":
                    _print_settings_result_report(*_model_source_status_report_payload(source_status))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "consumer_bundle_status":
                    summary = consumer_bundle_status(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config bundle")
                    _print_settings_result_report(*_consumer_bundle_status_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "registry_v2_save_plan":
                    plan = registry_v2_save_plan(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config save-plan")
                    _print_settings_result_report(*_registry_v2_save_plan_report_payload(plan))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "config_v2_promotion_plan":
                    plan = config_v2_promotion_plan(preview_config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} config promote-plan")
                    _print_settings_result_report(*_config_v2_promotion_plan_report_payload(plan))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "preview_doctor":
                    try:
                        summary = preview_doctor(config_dir=PRIMARY_CONFIG_DIR, command_name=f"{current_command()} preview doctor")
                    except Exception as exc:
                        _print_settings_error_report(_L("Preview Doctor 失败", "Preview Doctor failed"), exc)
                    else:
                        _print_settings_result_report(*_preview_doctor_report_payload(summary))
                    _pause_after_tui_report("按 Enter 返回设置")
                elif registry_action == "check_staleness":
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
                    about_action = _safe_tui_call(
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
                guard_action = _safe_tui_call(
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
                landing_action = _safe_tui_call(
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

                    fallback_model = _safe_tui_call(
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
                selected_rescue = _safe_tui_call(select_rescue_event_tui, rescue_events)
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
                rescue_action = _safe_tui_call(
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

                    fallback_model = _safe_tui_call(
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

                    fallback_model = _safe_tui_call(
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
            model_info = action_data.get("model_info") if isinstance(action_data.get("model_info"), dict) else {"model": action_data["model"]}
            _trace_record("last used", cli=cli, model=action_data.get("model"))
            runtime_runtime, _restored_models, restored_choice = _resolve_last_used_runtime(
                current_cfg, cli, action_data, default_models
            )
            runtime_from_best_provider = False
            if runtime_runtime is not None:
                _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice=restored_choice)
            else:
                runtime_runtime, _ = _resolve_best_provider(
                    current_cfg, action_data["model"], current_provider, default_models, cli_name=cli
                )
                runtime_from_best_provider = runtime_runtime is not None
            if runtime_runtime is None:
                runtime_runtime, _, cli = _choose_runtime_source(
                    current_cfg, cli, current_provider, default_models,
                    account_id=account_id, provider_id=provider_id,
                    model_info=model_info, allow_selected_model_accounts=True,
                )
            if runtime_runtime is None:
                console.print(f"[yellow]{cli} 没有可用 provider[/yellow]")
                continue
            if runtime_from_best_provider:
                _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="best provider")
            # fall through to confirm

        # ── 品类选择 → 子模型 ──
        elif action_type == "submodel":
            selected = dict(action_data or {})
            family_name = selected.pop("_family_name", "模型")

            pri_changes = selected.pop("priority_changes", None)
            if _apply_runtime_priority_changes(current_cfg, pri_changes):
                save_config(current_cfg)
                _families_dirty = True
                try:
                    from mms_router import export_model_routes
                    export_model_routes(current_cfg, force=True)
                except Exception:
                    pass

            model_info = {"model": selected["model"]}
            runtime_runtime = selected.get("provider_ctx")
            runtime_from_best_provider = runtime_runtime is not None
            if runtime_runtime is None:
                runtime_runtime, _ = _resolve_best_provider(
                    current_cfg, selected["model"], current_provider, default_models, cli_name=cli
                )
                runtime_from_best_provider = runtime_runtime is not None
            if runtime_runtime is None:
                console.print(f"[yellow]没有可用 provider 承载 {selected['model']}[/yellow]")
                continue
            _trace_record(
                f'family "{family_name}"',
                cli=cli,
                model=selected.get("model"),
                provider=(runtime_runtime or {}).get("id") if isinstance(runtime_runtime, dict) else selected.get("provider_id"),
            )
            if runtime_from_best_provider:
                _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="best provider")
            # fall through to confirm

        elif action_type == "family":
            family_name = action_data
            models = families_detail.get(cli, {}).get(family_name, [])
            if not models:
                console.print(f"[yellow]{family_name} 下没有可用模型[/yellow]")
                continue

            provider_options = provider_options_by_cli.get(cli, {})

            selected = _safe_tui_call(
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
                model_info = action_data.get("model_info") if isinstance(action_data.get("model_info"), dict) else {"model": action_data["model"]}
                _trace_record("last used", cli=cli, model=action_data.get("model"))
                runtime_runtime, _restored_models, restored_choice = _resolve_last_used_runtime(
                    current_cfg, cli, action_data, default_models
                )
                runtime_from_best_provider = False
                if runtime_runtime is not None:
                    _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice=restored_choice)
                else:
                    runtime_runtime, _ = _resolve_best_provider(
                        current_cfg, action_data["model"], current_provider, default_models, cli_name=cli
                    )
                    runtime_from_best_provider = runtime_runtime is not None
                if runtime_runtime is None:
                    runtime_runtime, _, cli = _choose_runtime_source(
                        current_cfg, cli, current_provider, default_models,
                        account_id=account_id, provider_id=provider_id,
                        model_info=model_info, allow_selected_model_accounts=True,
                    )
                if runtime_runtime is None:
                    console.print(f"[yellow]{cli} 没有可用 provider[/yellow]")
                    continue
                if runtime_from_best_provider:
                    _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="best provider")
            else:
                # 持久化 priority 变更
                pri_changes = selected.pop("priority_changes", None)
                if _apply_runtime_priority_changes(current_cfg, pri_changes):
                    save_config(current_cfg)
                    _families_dirty = True
                    # 静默重新生成 routes
                    try:
                        from mms_router import export_model_routes
                        export_model_routes(current_cfg, force=True)
                    except Exception:
                        pass

                model_info = {"model": selected["model"]}
                runtime_runtime = selected.get("provider_ctx")
                runtime_from_best_provider = runtime_runtime is not None
                if runtime_runtime is None:
                    runtime_runtime, _ = _resolve_best_provider(
                        current_cfg, selected["model"], current_provider, default_models, cli_name=cli
                    )
                    runtime_from_best_provider = runtime_runtime is not None
                if runtime_runtime is None:
                    console.print(f"[yellow]没有可用 provider 承载 {selected['model']}[/yellow]")
                    continue
                _trace_record(
                    f'family "{family_name}"',
                    cli=cli,
                    model=selected.get("model"),
                    provider=(runtime_runtime or {}).get("id") if isinstance(runtime_runtime, dict) else selected.get("provider_id"),
                )
                if runtime_from_best_provider:
                    _trace_runtime_choice("runtime resolve", runtime_runtime, launch_cli=cli, choice="best provider")
            # fall through to confirm
        elif action_type == "profile" and cli not in {"opencode", "agy"}:
            continue
        elif action_type not in ("profile", "provider_browse", "load_balance", "last", "family"):
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
        context_lines = _confirm_context_lines(cli, runtime_runtime)
        has_caveman = _caveman_available_for_cli(cli)
        has_nsr = _nsr_available_for_cli(cli)
        has_ecc = (
            cli == "claude"
            and _ecc_available_for_claude()
            and _model_info_looks_domestic(clean_model_info)
        )
        has_omc = (
            cli == "claude"
            and _omc_available_for_claude()
            and _model_info_looks_domestic(clean_model_info)
        )
        default_reasoning_effort = (
            str(runtime_runtime.get("reasoning_effort", "")).strip().lower()
            or _default_reasoning_effort_for_model_info(clean_model_info)
        )
        preview_catalog = _build_confirm_preview_catalog(
            cli,
            runtime_runtime,
            has_caveman=has_caveman,
            has_nsr=has_nsr,
            has_ecc=has_ecc,
            has_omc=has_omc,
        )
        result = _safe_tui_call(
            confirm_tui,
            cli,
            clean_model_info,
            env_vars=env_vars,
            once=once,
            context_lines=context_lines,
            has_caveman=has_caveman,
            caveman_enabled_default=str(runtime_runtime.get("caveman_mode", "enable")).strip().lower() != "disable",
            has_nsr=has_nsr,
            nsr_enabled_default=str(runtime_runtime.get("nsr_mode", "enable")).strip().lower() == "enable",
            has_ecc=has_ecc,
            ecc_enabled_default=False,
            has_omc=has_omc,
            agent_pack_default=str(runtime_runtime.get("agent_pack") or "none"),
            thinking_enabled_default=str(runtime_runtime.get("thinking_mode", "enable")).strip().lower() != "disable",
            reasoning_effort_default=default_reasoning_effort,
            preview_catalog=preview_catalog,
            runtime=runtime_runtime,
        )
        if result == "__interrupt__":
            return True
        disabled_session_surfaces = {}
        agent_pack = "none"
        nsr_enabled = False
        confirm_returned_surfaces = False

        def _confirm_agent_pack(value):
            raw = str(value or "").strip().lower()
            if raw in {"ecc", "omc", "none"}:
                return raw
            return "ecc" if bool(value) else "none"

        if isinstance(result, tuple):
            if len(result) >= 9:
                action, bypass, claude_1m_enabled, caveman_enabled, pack_value, thinking_enabled, reasoning_effort, disabled_session_surfaces, nsr_enabled = result[:9]
                agent_pack = _confirm_agent_pack(pack_value)
                confirm_returned_surfaces = True
            elif len(result) >= 8:
                action, bypass, claude_1m_enabled, caveman_enabled, pack_value, thinking_enabled, reasoning_effort, disabled_session_surfaces = result[:8]
                agent_pack = _confirm_agent_pack(pack_value)
                confirm_returned_surfaces = True
            elif len(result) >= 7:
                action, bypass, claude_1m_enabled, caveman_enabled, ecc_enabled, thinking_enabled, reasoning_effort = result[:7]
                agent_pack = _confirm_agent_pack(ecc_enabled)
            elif len(result) >= 5:
                action, bypass, claude_1m_enabled, caveman_enabled, ecc_enabled = result[:5]
                agent_pack = _confirm_agent_pack(ecc_enabled)
                thinking_enabled = True
                reasoning_effort = default_reasoning_effort
            elif len(result) >= 4:
                action, bypass, claude_1m_enabled, caveman_enabled = result[:4]
                thinking_enabled = True
                reasoning_effort = default_reasoning_effort
            elif len(result) >= 3:
                action, bypass, claude_1m_enabled = result[:3]
                caveman_enabled = False
                thinking_enabled = True
                reasoning_effort = default_reasoning_effort
            else:
                action, bypass = result[:2]
                claude_1m_enabled = False
                caveman_enabled = False
                thinking_enabled = True
                reasoning_effort = default_reasoning_effort
        else:
            action, bypass, claude_1m_enabled, caveman_enabled, thinking_enabled, reasoning_effort = result, False, False, False, True, default_reasoning_effort
            disabled_session_surfaces = {}
            nsr_enabled = False
        if action == "q":
            return True
        if action == "b":
            continue
        if cli in {"claude", "codex", "opencode", "agy"}:
            runtime_runtime["bypass"] = bool(bypass)
        if bypass:
            if cli == "claude" and runtime_runtime and runtime_runtime.get("auth_mode") in {"oauth", "api_key"}:
                from mms_launchers import _enforce_claude_network_guard_or_exit, _claude_bypass_requires_proxy
                _enforce_claude_network_guard_or_exit(
                    runtime_runtime,
                    require_proxy=_claude_bypass_requires_proxy(runtime_runtime),
                )
        if cli == "claude":
            runtime_runtime["claude_1m_mode"] = "enable" if claude_1m_enabled else "disable"
            runtime_runtime["agent_pack"] = agent_pack if agent_pack in {"ecc", "omc"} else "none"
            runtime_runtime["ecc_mode"] = "enable" if agent_pack == "ecc" else "disable"
            runtime_runtime["omc_mode"] = "enable" if agent_pack == "omc" else "disable"
        if cli in {"claude", "codex", "opencode", "agy"}:
            runtime_runtime["caveman_mode"] = "enable" if caveman_enabled else "disable"
            runtime_runtime["nsr_mode"] = "enable" if (has_nsr and nsr_enabled) else "disable"
            if confirm_returned_surfaces:
                runtime_runtime["disabled_session_surfaces"] = (
                    disabled_session_surfaces if isinstance(disabled_session_surfaces, dict) else {}
                )
            else:
                runtime_runtime["disabled_session_surfaces"] = _merge_disabled_session_surfaces(
                    runtime_runtime.get("disabled_session_surfaces"),
                    disabled_session_surfaces if isinstance(disabled_session_surfaces, dict) else {},
                )
        if cli in {"claude", "codex"}:
            runtime_runtime["thinking_mode"] = "enable" if thinking_enabled else "disable"
            runtime_runtime["reasoning_effort"] = str(reasoning_effort or "high").strip().lower() or "high"
        _launch_with_tracking(cli, clean_model_info, runtime_runtime, once=once)
        return True


# ── Export command ──────────────────────────────────────

def handle_export(cli_name, provider, apply=False):
    """输出指定 CLI 的 export 命令，或写入独立 env 文件。"""
    from mms_launchers import get_export_env

    if cli_name not in CLI_NAMES:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(CLI_NAMES)}")
        return

    exports = get_export_env(cli_name, provider)
    if not exports:
        console.print(f"[yellow]{cli_name} 无需 export；启动时会按 CLI 自己的参数或登录方式处理[/yellow]")
        return

    lines = [f"export {k}={shlex.quote(str(v))}" for k, v in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{cli_name} 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if apply:
        os.makedirs(ENV_DIR, exist_ok=True)
        env_path = _env_file_path(cli_name)
        with open(env_path, "w") as f:
            f.write(f"# Generated by {display_title()}\n")
            f.write(export_block + "\n")

        console.print(f"\n[green]✓ 已写入 {env_path}[/green]")
        console.print("[dim]这是独立 env 文件，不会自动修改 ~/.zshrc 或 ~/.bashrc[/dim]")
        console.print(f"[dim]需要时手动执行: source {env_path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {export_command_hint(cli_name)} 生成独立 env 文件[/dim]"
        )


# ── Preset env/activate ───────────────────────────────


def _resolve_preset_export_runtime(cfg, preset, provider_override=None, *, stderr_only=False):
    """解析 preset 的 export 环境变量。只支持 provider runtime (api_key 模式)。

    返回 (cli, exports_dict, runtime) 或 None（如果不可导出）。
    """
    from mms_launchers import get_export_env, validate_provider_for_cli

    cli = preset.get("cli", "claude")
    auth_mode = _infer_preset_auth_mode(preset)

    if auth_mode in ("oauth", "oauth_bridge"):
        _emit_preset_error(f"此预设使用 {auth_mode} 模式，不支持 env export", stderr_only=stderr_only)
        return None

    provider_id = provider_override or preset.get("provider") or None

    runtime = ensure_provider_credentials(cfg, provider_id)
    if runtime is None:
        _emit_preset_error(f"无法解析 provider: {provider_id or 'default'}", stderr_only=stderr_only)
        return None

    if not provider_id and sys.stderr.isatty():
        default_name = runtime.get("id", "default") if isinstance(runtime, dict) else "default"
        print(f"预设未指定 provider，使用默认: {default_name}", file=sys.stderr)

    try:
        validate_provider_for_cli(cli, runtime)
    except Exception as exc:
        _emit_preset_error(str(exc), stderr_only=stderr_only)
        return None

    exports = get_export_env(cli, runtime)
    if not exports:
        _emit_preset_error(f"{cli} 无需 export；启动时会按 CLI 自己的参数或登录方式处理", stderr_only=stderr_only)
        return None

    return cli, exports, runtime


def handle_env_command(cfg, argv):
    """处理 mms env <preset> [--apply] [--provider OVERRIDE]"""
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} env",
        description="输出预设对应的 export 环境变量",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--apply", action="store_true",
                        help="写入 ~/.config/mms/env/<preset>.sh")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = _resolve_named_preset(cfg, args.preset_name)
    if preset is None:
        return

    result = _resolve_preset_export_runtime(cfg, preset, provider_override=args.provider)
    if result is None:
        return

    cli, exports, _runtime = result
    lines = [f"export {k}={shlex.quote(str(v))}" for k, v in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{args.preset_name} ({cli}) 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if args.apply:
        os.makedirs(ENV_DIR, exist_ok=True)
        env_path = _preset_env_file_path(args.preset_name)
        with open(env_path, "w") as f:
            f.write(f"# Generated by {display_title()} — preset: {args.preset_name}\n")
            f.write(export_block + "\n")
        console.print(f"\n[green]✓ 已写入 {env_path}[/green]")
        console.print(f"[dim]需要时手动执行: source {env_path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {current_command()} env {args.preset_name} --apply 生成独立 env 文件[/dim]"
        )


def handle_activate_command(cfg, argv):
    """处理 mms activate <preset> [--provider OVERRIDE]
    输出纯 export 行到 stdout，适合 eval $(mms activate foo)。
    """
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} activate",
        description="输出可 eval 的 export 语句",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = _resolve_named_preset(cfg, args.preset_name, stderr_only=True)
    if preset is None:
        sys.exit(1)

    result = _resolve_preset_export_runtime(cfg, preset, provider_override=args.provider, stderr_only=True)
    if result is None:
        sys.exit(1)

    _cli, exports, _runtime = result
    for k, v in exports.items():
        print(f"export {k}={shlex.quote(str(v))}")

    if sys.stderr.isatty():
        print(f"# ✓ preset '{args.preset_name}' activated", file=sys.stderr)


# ── Config command ─────────────────────────────────────

def handle_config(cfg, args_rest):
    """处理 config 子命令"""
    _guard_preview_legacy_config_mutation(args_rest)
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
    if key_path in {"root", "root.status", "status.root"}:
        _display_config_root(json_output="--json" in args_rest[1:])
        return
    if key_path in {"source", "sources", "model-source", "model-sources"}:
        _display_model_source_status(json_output="--json" in args_rest[1:])
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
    if key_path == "load-balance.show":
        _handle_load_balance_show_config(cfg)
        return
    if key_path == "load-balance.default":
        _handle_load_balance_default_config(cfg, args_rest[1:])
        return
    if key_path == "load-balance.profile.add":
        _handle_load_balance_profile_add_config(cfg, args_rest[1:])
        return
    if key_path == "load-balance.profile.remove":
        _handle_load_balance_profile_remove_config(cfg, args_rest[1:])
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
    command = current_command()
    console.print(f"[bold]{command} config extension.openrouter[/bold] — OpenRouter 可选扩展")
    console.print(f"  {command} config extension.openrouter add")
    console.print(f"  {command} config extension.openrouter status [provider_id] [--limit N] [--json]")
    console.print(f"  {command} config extension.openrouter models [provider_id] [--limit N] [--json]")
    console.print("[dim]status/models 默认不写真实 MMS 配置；add 会进入交互式 provider 接入。[/dim]")


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
    _ensure_rich()
    table = Table(title=title, show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("免费", style="yellow", width=6)
    table.add_column("输入", style="magenta")
    table.add_column("输出", style="magenta")
    table.add_column("Context", justify="right")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            "yes" if item.get("is_free") else "no",
            ",".join(item.get("input_modalities") or []),
            ",".join(item.get("output_modalities") or []),
            str(item.get("context_length") or ""),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def _display_openrouter_video_rows(rows, *, limit):
    _ensure_rich()
    table = Table(title="OpenRouter Video 模型", show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("分辨率", style="yellow")
    table.add_column("时长", style="magenta")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            ",".join(str(value) for value in item.get("supported_resolutions") or []),
            ",".join(str(value) for value in item.get("supported_durations") or []),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def _display_openrouter_extension_summary(summary, *, provider_label="", limit=12, show_models=False):
    _ensure_rich()
    account = summary.get("account") or {}
    counts = summary.get("counts") or {}
    requests = summary.get("requests") or {}
    table = Table(title="OpenRouter Extension", show_lines=True)
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("provider/key", provider_label or "env/public")
    table.add_row("account tier", f"{account.get('tier')} ({account.get('reason')})")
    table.add_row("model source", str(summary.get("model_source") or "-"))
    table.add_row("visible text", str(counts.get("visible_text", 0)))
    table.add_row("image/video", f"{'on' if summary.get('image_enabled') else 'off'} / {'on' if summary.get('video_enabled') else 'off'}")
    table.add_row("requests", ", ".join(f"{key}:{value.get('status')}" for key, value in requests.items()))
    console.print(table)
    if summary.get("free_only"):
        console.print("[yellow]当前按 free-only 策略展示：只列免费文本模型，隐藏 OpenRouter Image / Video。[/yellow]")
    if not show_models:
        return
    _display_openrouter_model_rows("OpenRouter Text 模型", summary.get("text_models") or [], limit=limit)
    if summary.get("image_enabled"):
        _display_openrouter_model_rows("OpenRouter Image 模型", summary.get("image_models") or [], limit=limit)
    if summary.get("video_enabled"):
        _display_openrouter_video_rows(summary.get("video_models") or [], limit=limit)


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
    providers = cfg.get("providers", [])
    if not providers:
        console.print("[yellow]未配置模型源[/yellow]")
        return

    table = Table(title="模型源列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("协议", style="yellow")
    table.add_column("CLI", style="magenta")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="white")
    table.add_column("地址", style="blue")

    default_id = cfg.get("provider", {}).get("default", DEFAULT_PROVIDER_ID)
    for provider in providers:
        provider_ctx = resolve_provider_context(cfg, provider.get("id"))
        status = "默认" if provider.get("id") == default_id else ""
        status = f"{status} 启用" if provider.get("enabled", True) else f"{status} 禁用".strip()
        table.add_row(
            str(provider.get("id", "")),
            str(provider.get("name", "")),
            ", ".join(provider.get("protocols", [])),
            ", ".join(provider.get("supported_clis", [])),
            str(provider.get("priority", DEFAULT_PRIORITY)),
            status.strip(),
            _provider_openai_base_url(provider_ctx) or _provider_anthropic_base_url(provider_ctx) or "(未设置)",
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {current_command()} config provider.default <id> 切换默认模型源。[/dim]"
    )


def _display_accounts(cfg):
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]未配置账号档案[/yellow]")
        return

    defaults = cfg.get("account", {}).get("defaults", {})
    table = Table(title="账号档案列表", show_lines=True)
    table.add_column("文件夹名", style="cyan")
    table.add_column("显示名", style="green")
    table.add_column("CLI", style="yellow")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="magenta")
    table.add_column("登录态", style="white")
    table.add_column("文件夹目录", style="blue")

    for account in accounts:
        login_state = _probe_account_status(account)
        status = []
        if defaults.get(account.get("cli")) == account.get("id"):
            status.append("默认")
        status.append("启用" if account.get("enabled", True) else "禁用")
        table.add_row(
            str(account.get("id", "")),
            str(account.get("name", "")),
            str(account.get("cli", "")),
            str(account.get("priority", DEFAULT_PRIORITY)),
            " ".join(status).strip(),
            login_state.get("summary") or login_state.get("state", ""),
            str(account.get("home_dir", "")),
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {current_command()} config account.default <cli> <id> 设置默认账号，"
        f"{current_command()} config account.login <id> 进入官方登录。[/dim]"
    )
    console.print("[dim]注: Claude OAuth 独立入口已下线，这里仅保留旧配置只读兼容。[/dim]")


def _display_config_help():
    command = current_command()
    console.print(f"[bold]{command} config[/bold] — 配置查看与管理")
    console.print(f"[dim]用法: {command} config [子命令] [参数][/dim]")
    console.print("\n[bold]常用子命令:[/bold]")
    console.print(f"  {command} config")
    console.print(f"  {command} config file")
    console.print(f"  {command} config root [--json]")
    console.print(f"  {command} config source [--json]")
    console.print(f"  {command} config check [--json]")
    console.print(f"  {command} config bundle [--json]")
    console.print(f"  {command} config save-plan [--json]")
    console.print(f"  {command} config promote-plan [--json]")
    console.print(f"  {command} config apply-plan --plan-json <file> [--apply --confirm-preview-apply] [--json]")
    console.print(f"  {command} config doctor [--json]")
    console.print(f"  {command} config doctor --strict-exit")
    console.print(f"  {command} config validate")
    console.print(f"  {command} config get <dot.path>")
    console.print(f"  {command} config set <dot.path> <value>")
    console.print(f"  {command} config unset <dot.path>")
    console.print(f"  {command} config connect")
    console.print(f"  {command} config web [--no-open]")
    console.print(f"  {command} config preferences.help")
    console.print(f"  {command} config human-gate")
    console.print(f"  [dim]可调参数示例: cache.probe_async_refresh_after_sec / cache.probe_async_min_interval_sec[/dim]")
    console.print("\n[bold]Load Balance:[/bold]")
    console.print(f"  {command} config load-balance.show")
    console.print(f"  {command} config load-balance.default [name]")
    console.print(f"  {command} config load-balance.profile.add <name> <heavy> [medium] [light]")
    console.print(f"  {command} config load-balance.profile.remove <name>")
    console.print(f"  [dim]更细的 slot provider 可用 config set load_balance.profiles.<name>.<slot>.provider <id>[/dim]")
    console.print("\n[bold]Provider:[/bold]")
    console.print(f"  {command} config provider.list")
    console.print(f"  {command} config provider.default [id]")
    console.print(f"  {command} config provider.add [id]")
    console.print(f"  {command} config provider.edit <id>")
    console.print(f"  {command} config provider.remove <id>")
    console.print(f"  {command} config provider.credentials [id]")
    console.print(f"  {command} config extension.openrouter [add|status|models]")
    console.print("\n[bold]Account:[/bold]")
    console.print(f"  {command} config account.list")
    console.print(f"  {command} config account.add \\[codex|agy]")
    console.print(f"  {command} config account.edit <id>")
    console.print(f"  {command} config account.remove <id>")
    console.print(f"  {command} config account.status [id]")
    console.print(f"  {command} config account.login <id>")
    console.print(f"  {command} config account.default <cli> <id>")
    console.print("  [dim]Claude OAuth 独立入口已下线；MMS 不再新增/登录/设默认 Claude 官方账号。[/dim]")
    console.print("\n[bold]其他:[/bold]")
    console.print(f"  {command} config stats")
    console.print(f"  {command} config api.edit")


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


def _display_preferences_path():
    console.print("[bold]MMS preferences.toml[/bold]")
    for path in PREFERENCES_PATHS:
        marker = "active" if os.path.exists(path) else "create-if-needed"
        console.print(f"  {path}  [dim]({marker})[/dim]")
    console.print(f"[dim]文档: {PREFERENCES_DOC_PATH}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents may inspect/propose, but must not auto-write real ~/.config/mms/** without human confirmation.")


def _display_preferences_example():
    console.print(PREFERENCES_EXAMPLE_TOML.rstrip(), markup=False)


def _display_human_gate_help():
    command = current_command()
    console.print("[bold]MMS Human Gate[/bold]")
    console.print("- real config tree `~/.config/mms/**` is human-only for agents.")
    console.print("- allowed for agents: inspect, explain, generate manual diff, print examples.")
    console.print("- blocked without human confirmation: writing config.toml, preferences.toml, override.toml, credentials.sh, accounts/**, env/**, usage/account state, or Claude config.")
    console.print("- required write flow: plan -> backup -> human double check -> audited write -> post-write human double check.")
    console.print("- `preferences.toml` is safer than `override.toml`, but it is still real user config and stays behind the same human gate.")
    console.print(f"[dim]LLM entry: run `{command} config preferences.help` and read {PREFERENCES_DOC_PATH} before advising config edits.[/dim]")


def _display_preferences_help():
    command = current_command()
    console.print("[bold]MMS User Preferences[/bold]")
    console.print(f"Path: {PREFERENCES_PATHS[0]}")
    console.print("Purpose: user-owned, install-safe, allowlisted launch preference overlay.")
    console.print("\n[bold]Commands:[/bold]")
    console.print(f"  {command} config preferences.path")
    console.print(f"  {command} config preferences.example")
    console.print(f"  {command} config preferences.doc")
    console.print(f"  {command} config human-gate")
    console.print("\n[bold]Allowed keys:[/bold]")
    console.print("  launch.defaults: thinking_mode, reasoning_effort, caveman_mode, nsr_mode, agent_pack, bypass")
    console.print("  launch.cli.<claude|codex|opencode|agy>: same launch keys")
    console.print("  session_surfaces.disabled: skills, mcp, hooks")
    console.print("  assets.roots: web_access, weber, agent_browser, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor")
    console.print("\n[bold]Denied / ignored:[/bold]")
    console.print("  api_key, base_url, proxy, account identity, provider routes, OAuth tokens, credentials, Claude config, real HOME/XDG/auth state")
    console.print("\n[bold]Overlay order:[/bold]")
    console.print("  config.toml -> override.toml -> preferences.toml launch allowlist -> confirm screen changes -> launcher")
    console.print(f"[dim]Full doc: {PREFERENCES_DOC_PATH}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents can propose edits, but must not auto-write real ~/.config/mms/** without human confirmation.")



def _display_config(cfg, prefix="", depth=0):
    """递归显示配置，遮蔽敏感值"""
    if depth == 0:
        status = _config_root_status()
        console.print("[bold]配置根:[/bold]")
        console.print(f"  [cyan]command[/cyan] = {status['command']}")
        console.print(f"  [cyan]mode[/cyan] = {status['mode']}")
        console.print(f"  [cyan]root_source[/cyan] = {status['root_source']}")
        console.print(f"  [cyan]config_root[/cyan] = {status['config_root']}")
        provider = resolve_provider_context(cfg)
        console.print("[bold]模型源:[/bold]")
        console.print(f"  [cyan]default[/cyan] = {cfg.get('provider', {}).get('default', DEFAULT_PROVIDER_ID)}")
        console.print(f"  [cyan]openai_base_url[/cyan] = {_provider_openai_base_url(provider) or '(未设置)'}")
        console.print(f"  [cyan]anthropic_base_url[/cyan] = {_provider_anthropic_base_url(provider) or '(未设置)'}")
        key_display = _mask_key(provider.get("api_key", "")) if provider.get("api_key") else "(未设置)"
        console.print(f"  [cyan]api_key[/cyan] = {key_display}")
        console.print(f"  [cyan]credentials_file[/cyan] = {_active_credentials_path()}")
        console.print("  [dim]api_key 为掩码显示；真实值请查看 credentials_file。[/dim]")
        _display_providers(cfg)
        _display_accounts(cfg)
        console.print(f"  [cyan]usage_file[/cyan] = {_active_usage_path()}")
        console.print("  [dim]usage 只记录本地启动统计，不代表真实余额或官方剩余额度。[/dim]")
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            console.print(f"  [cyan]probe_async_refresh_after_sec[/cyan] = {cache_cfg.get('probe_async_refresh_after_sec', _PROBE_ASYNC_REFRESH_AFTER)}")
            console.print(f"  [cyan]probe_async_min_interval_sec[/cyan] = {cache_cfg.get('probe_async_min_interval_sec', _PROBE_ASYNC_MIN_INTERVAL)}")
            console.print("  [dim]以上窗口控制模型列表异步刷新：首屏先读 cache，后台再 refresh。[/dim]")
        active_overrides = _existing_override_paths()
        if active_overrides:
            console.print(f"  [cyan]override_files[/cyan] = {active_overrides}")
            console.print("  [dim]override 仅在运行时叠加，不会直接写回 config.toml。[/dim]")
        else:
            console.print(f"  [cyan]override_files[/cyan] = {OVERRIDE_PATHS}")
            console.print("  [dim]如需团队共享默认值，可在以上路径创建 override.toml。[/dim]")
        active_preferences = _existing_preferences_paths()
        console.print(f"  [cyan]preferences_files[/cyan] = {active_preferences or PREFERENCES_PATHS}")
        console.print(f"  [dim]用户偏好 allowlist: {current_command()} config preferences.help；真实配置仍受 human-gate 保护。[/dim]")

    for k, v in cfg.items():
        if depth == 0 and k in {"providers", "provider", "accounts", "account", "_mms_preferences"}:
            continue
        full_key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            console.print(f"{'  ' * depth}[bold]{k}:[/bold]")
            _display_config(v, full_key, depth + 1)
        elif isinstance(v, list):
            console.print(f"{'  ' * depth}[cyan]{k}[/cyan] = {v}")
        else:
            display = _mask_key(str(v)) if "key" in k.lower() else str(v)
            console.print(f"{'  ' * depth}[cyan]{k}[/cyan] = {display}")


def _display_usage_stats():
    stats = _load_usage_stats()
    sources = stats.get("sources", {})
    if not sources:
        console.print("[yellow]还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件会写入 {USAGE_PATH}[/dim]")
        return

    table = Table(title="本地启动统计", show_lines=True)
    table.add_column("来源", style="cyan")
    table.add_column("CLI", style="green")
    table.add_column("启动次数", style="yellow")
    table.add_column("最近模型", style="magenta")
    table.add_column("最近使用", style="white")

    rows = sorted(
        sources.values(),
        key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)),
        reverse=True,
    )
    for item in rows:
        table.add_row(
            f"{item.get('runtime_kind', 'source')} / {item.get('name', item.get('id', 'default'))}",
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这是本地软统计，用于排序/推荐参考；不等于真实计费数据。[/dim]")


def _display_adapter_registry():
    table = Table(title="来源公司 / Adapter Registry (Top 10)", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("公司/品牌", style="green")
    table.add_column("模型族", style="yellow")
    table.add_column("推荐 Adapter", style="magenta")
    table.add_column("当前状态", style="white")
    table.add_column("OAuth", style="white")
    table.add_column("默认 Claude Bridge", style="white")

    for idx, item in enumerate(TOP_SOURCE_COMPANIES, 1):
        table.add_row(
            str(idx),
            f"{item.get('company', '')} / {item.get('brand', '')}",
            ", ".join(item.get("families", [])),
            str(item.get("default_adapter", "")),
            str(item.get("current_support", "")),
            "yes" if item.get("oauth_native") else "no",
            "yes" if item.get("claude_bridge_default") else "no",
        )
    console.print(table)
    console.print("[bold]默认策略:[/bold]")
    for key, text in DEFAULT_ADAPTER_POLICY.items():
        console.print(f"  [cyan]{key}[/cyan]: {text}")
    console.print(
        f"[dim]详情文档: docs/ADAPTER_REGISTRY.md；命令: {current_command()} config adapter.registry[/dim]"
    )


def _mask_key(val):
    """遮蔽 API key，只显示前 4 和后 4 位"""
    if len(val) <= 8:
        return "****"
    return val[:4] + "****" + val[-4:]


def _set_nested(d, parts, val):
    """设置嵌套 dict 的值"""
    for p in parts[:-1]:
        if p not in d or not isinstance(d[p], dict):
            d[p] = {}
        d = d[p]
    d[parts[-1]] = val


def _get_nested(d, parts):
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _unset_nested(d, parts):
    current = d
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current.pop(parts[-1], None)
    return True


def _coerce_config_value(key_path, raw_value):
    if key_path == "user.role":
        return _validate_user_role(raw_value)
    if key_path == "ui.language":
        lang = normalize_language(raw_value)
        if not lang:
            raise ValueError("ui.language 只支持 zh 或 en")
        return lang
    if key_path == "provider.default":
        return str(raw_value).strip()
    if key_path in {"cache.probe_async_refresh_after_sec", "cache.probe_async_min_interval_sec"}:
        return _normalize_positive_seconds(raw_value, 1)
    if key_path.startswith("provider.") and key_path.endswith(".enabled"):
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    return raw_value


def _validate_config(cfg):
    errors = []

    def _validate_family_priority_overrides(value, label):
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(f"{label} 的 family_priority_overrides 必须是对象")
            return
        for family_name, priority in value.items():
            canonical_family = _canonical_model_family(family_name)
            if not canonical_family:
                errors.append(f"{label} 的 family_priority_overrides 存在不支持的 family: {family_name}")
                continue
            if _normalize_priority(priority) != priority:
                errors.append(f"{label} 的 family_priority_overrides.{canonical_family} 必须是正整数")

    cache_cfg = cfg.get("cache", {})
    if cache_cfg and not isinstance(cache_cfg, dict):
        errors.append("cache 必须是对象")
    elif isinstance(cache_cfg, dict):
        for key in ("probe_async_refresh_after_sec", "probe_async_min_interval_sec"):
            value = cache_cfg.get(key)
            if value is None:
                continue
            try:
                if int(value) <= 0:
                    errors.append(f"{key} 必须是正整数")
            except (TypeError, ValueError):
                errors.append(f"{key} 必须是正整数")
    providers = cfg.get("providers", [])
    if not isinstance(providers, list) or not providers:
        errors.append("providers 不能为空")
    else:
        seen_ids = set()
        for item in providers:
            if not isinstance(item, dict):
                errors.append("providers 中存在非对象条目")
                continue
            provider_id = str(item.get("id", "")).strip()
            if not provider_id:
                errors.append("存在缺少 id 的模型源")
                continue
            if provider_id in seen_ids:
                errors.append(f"模型源 ID 重复: {provider_id}")
            seen_ids.add(provider_id)

            protocols = item.get("protocols", [])
            if isinstance(protocols, str):
                protocols = [protocols]
            invalid_protocols = [value for value in protocols if value not in DEFAULT_PROVIDER_PROTOCOLS]
            if invalid_protocols:
                errors.append(f"模型源 {provider_id} 存在不支持的协议: {', '.join(invalid_protocols)}")

            supported_clis = item.get("supported_clis", [])
            if isinstance(supported_clis, str):
                supported_clis = [supported_clis]
            invalid_clis = [
                value for value in supported_clis
                if value not in CLI_NAMES and value not in LEGACY_PROVIDER_CLI_ALIASES
            ]
            if invalid_clis:
                errors.append(f"模型源 {provider_id} 存在不支持的 CLI: {', '.join(invalid_clis)}")
            if _normalize_priority(item.get("priority", DEFAULT_PRIORITY)) != item.get("priority", DEFAULT_PRIORITY):
                errors.append(f"模型源 {provider_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"模型源 {provider_id}",
            )
            if _normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"模型源 {provider_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    default_id = cfg.get("provider", {}).get("default")
    provider_ids = {item.get("id") for item in providers if isinstance(item, dict)}
    if default_id and default_id not in provider_ids:
        errors.append(f"默认模型源不存在: {default_id}")

    accounts = cfg.get("accounts", [])
    seen_account_ids = set()
    if not isinstance(accounts, list):
        errors.append("accounts 必须是列表")
    else:
        for item in accounts:
            if not isinstance(item, dict):
                errors.append("accounts 中存在非对象条目")
                continue
            account_id = str(item.get("id", "")).strip()
            if not account_id:
                errors.append("存在缺少 id 的账号档案")
                continue
            if account_id in seen_account_ids:
                errors.append(f"账号档案 ID 重复: {account_id}")
            seen_account_ids.add(account_id)
            cli_name = str(item.get("cli", "")).strip()
            if cli_name not in OAUTH_CAPABLE_CLIS:
                errors.append(f"账号档案 {account_id} 绑定了不支持的 CLI: {cli_name}")
            auth_mode = str(item.get("auth_mode", "oauth")).strip()
            if auth_mode != "oauth":
                errors.append(f"账号档案 {account_id} 目前只支持 oauth 模式")
            if not str(item.get("home_dir", "")).strip():
                errors.append(f"账号档案 {account_id} 缺少 home_dir")
            if _normalize_priority(item.get("priority", DEFAULT_PRIORITY)) != item.get("priority", DEFAULT_PRIORITY):
                errors.append(f"账号档案 {account_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"账号档案 {account_id}",
            )
            if _normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"账号档案 {account_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    account_defaults = cfg.get("account", {}).get("defaults", {})
    if isinstance(account_defaults, dict):
        for cli_name, account_id in account_defaults.items():
            if cli_name not in OAUTH_CAPABLE_CLIS:
                errors.append(f"存在不支持的默认账号 CLI: {cli_name}")
            elif account_id not in seen_account_ids:
                errors.append(f"{cli_name} 的默认账号不存在: {account_id}")

    role = cfg.get("user", {}).get("role", MODE_ALL)
    if normalize_user_role(role) not in {MODE_ALL, MODE_RECOMMENDED}:
        errors.append(f"不支持的模型模式: {role}")

    load_balance = cfg.get("load_balance")
    if load_balance is not None:
        if not isinstance(load_balance, dict):
            errors.append("load_balance 必须是对象")
        else:
            profiles = load_balance.get("profiles")
            if profiles is not None and not isinstance(profiles, dict):
                errors.append("load_balance.profiles 必须是对象")
            elif isinstance(profiles, dict):
                for profile_name, profile in profiles.items():
                    if not isinstance(profile, dict):
                        errors.append(f"load_balance profile {profile_name} 必须是对象")
                        continue
                    for slot_name in LB_SLOT_NAMES:
                        slot = profile.get(slot_name)
                        if slot is not None and not isinstance(slot, (dict, str)):
                            errors.append(f"load_balance profile {profile_name}.{slot_name} 必须是对象或字符串")

    return errors


def _handle_config_get(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config get <dot.path>[/red]")
        return
    key_path = args_rest[0]
    value, found = _get_nested(cfg, key_path.split("."))
    if not found:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    display = _mask_key(str(value)) if "key" in key_path.lower() else str(value)
    console.print(f"[cyan]{key_path}[/cyan] = {display}")


def _handle_config_set(cfg, args_rest):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {current_command()} config set <dot.path> <value>[/red]")
        return
    key_path = args_rest[0]
    raw_value = args_rest[1]
    new_val = _coerce_config_value(key_path, raw_value)
    updated_cfg = dict(cfg)
    _set_nested(updated_cfg, key_path.split("."), new_val)
    updated_cfg = _normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    display = _mask_key(str(new_val)) if "key" in key_path.lower() else str(new_val)
    console.print(f"[green]✓ {key_path} = {display}[/green]")


def _handle_config_unset(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config unset <dot.path>[/red]")
        return
    key_path = args_rest[0]
    updated_cfg = dict(cfg)
    removed = _unset_nested(updated_cfg, key_path.split("."))
    if not removed:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    updated_cfg = _normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已移除 {key_path}[/green]")


def _handle_config_file():
    console.print(CONFIG_PATH)


def _handle_config_validate(cfg):
    errors = _validate_config(cfg)
    if errors:
        console.print("[red]配置校验失败:[/red]")
        for item in errors:
            console.print(f"  - {item}")
        sys.exit(1)
    console.print("[green]✓ 配置校验通过[/green]")


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
                    "name": provider_id if unique_id == provider_id else f"{provider_id} ({unique_id})",
                    "enabled": True,
                    "role": "primary" if leaf_kind == "primary" else "fallback",
                    "priority": max(1, 1000 - route_index),
                    "protocols": protocols,
                    "supported_clis": _bundle_runtime_supported_clis(protocols),
                    "models_endpoint": "manual",
                    "fallback_models": [],
                    "extra_models": [],
                    "hidden_models": [],
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
            elif leaf_kind == "primary":
                provider["role"] = "primary"
            for field in ("fallback_models", "extra_models"):
                if model_name not in provider[field]:
                    provider[field].append(model_name)

    if not providers:
        return None
    return {
        "ui": {"language": "zh"},
        "user": {"role": MODE_ALL},
        "cache": {
            "probe_async_refresh_after_sec": _PROBE_ASYNC_REFRESH_AFTER,
            "probe_async_min_interval_sec": _PROBE_ASYNC_MIN_INTERVAL,
        },
        "provider": {"default": providers[0]["id"]},
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


def _session_status_label(item):
    session_id = str(item.get("session_id") or "").strip()
    if not session_id:
        return "active"
    if item.get("stale_cleanup"):
        return "stale-finalized"
    if item.get("exit_code") is None:
        return "active"
    return f"exit:{item.get('exit_code')}"


def _session_display_id(item):
    session_id = str(item.get("session_id") or "").strip()
    if session_id:
        return session_id
    pid = item.get("pid")
    return f"pid-{pid}" if pid is not None else "-"


def _handle_session_ls(cli_name):
    from mms_session_index import list_indexed_sessions

    rows = list_indexed_sessions(cli_name=cli_name)
    if not rows:
        console.print(f"[yellow]当前没有已索引的 {cli_name} session[/yellow]")
        return

    table = Table(title=f"{cli_name} session 列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("项目", style="green")
    table.add_column("来源", style="magenta")
    table.add_column("状态", style="yellow")
    table.add_column("最近活动", style="blue")
    for item in rows:
        project_name = os.path.basename(str(item.get("project_path", "")).rstrip(os.sep)) or "-"
        source_label = str(item.get("account_id") or item.get("runtime_kind") or "-")
        last_active = str(item.get("last_active_at") or item.get("started_at") or "-")
        table.add_row(
            _session_display_id(item),
            project_name,
            source_label,
            _session_status_label(item),
            last_active,
        )
    console.print(table)


def _handle_session_info(session_id, cli_name):
    from mms_session_index import get_indexed_session

    item = get_indexed_session(session_id, cli_name=cli_name)
    if item is None:
        console.print(f"[red]找不到 session: {session_id}[/red]")
        sys.exit(1)

    table = Table(title=f"{cli_name} session 详情")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    ordered_keys = [
        "session_id",
        "project_key",
        "project_path",
        "account_id",
        "runtime_kind",
        "pid",
        "cwd",
        "started_at",
        "last_active_at",
        "exit_code",
        "stale_cleanup",
        "slot_home",
        "_path",
    ]
    seen = set()
    for key in ordered_keys:
        seen.add(key)
        table.add_row(key, str(item.get(key, "")))
    for key in sorted(item):
        if key in seen:
            continue
        table.add_row(str(key), str(item.get(key, "")))
    console.print(table)


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

    rows = _list_stale_gateway_sessions(cli_name)
    if not rows:
        console.print("[green]没有可清理的 stale MMS session[/green]")
        return

    table = Table(title="Stale MMS session dry-run" if not apply else "Stale MMS session prune")
    table.add_column("CLI", style="cyan")
    table.add_column("Session", style="green")
    table.add_column("Size", style="yellow")
    table.add_column("Modified", style="blue")
    table.add_column("Path", style="white")
    for item in rows:
        table.add_row(
            str(item["cli"]),
            str(item["name"]),
            _format_bytes(item["size"]),
            str(item["mtime"]),
            str(item["path"]),
        )
    console.print(table)

    if not apply:
        console.print(f"[dim]dry-run only：加 --apply --yes 才会删除 {len(rows)} 个 stale session[/dim]")
        return
    if not yes:
        console.print("[red]拒绝删除：需要显式传 --yes[/red]")
        return

    removed = 0
    for item in rows:
        session_home = str(item.get("path") or "")
        root = os.path.dirname(session_home)
        try:
            if os.path.commonpath([os.path.abspath(session_home), os.path.abspath(root)]) != os.path.abspath(root):
                continue
        except ValueError:
            continue
        if item.get("cli") == "claude":
            try:
                _finalize_claude_slot(session_home, stale_cleanup=True)
            except Exception:
                pass
        shutil.rmtree(session_home, ignore_errors=True)
        removed += 1
    console.print(f"[green]已删除 {removed} 个 stale MMS session[/green]")


def handle_session_command(argv):
    _ensure_rich()
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} session",
        description="查看 MMS 托管 session，或恢复 legacy chat session",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    ls_parser = subparsers.add_parser("ls", help="列出已索引 session")
    ls_parser.add_argument("--cli", default="claude", choices=["claude"])

    info_parser = subparsers.add_parser("info", help="查看单个 session 详情")
    info_parser.add_argument("session_id", help="session_id 或 pid-<pid>")
    info_parser.add_argument("--cli", default="claude", choices=["claude"])

    resume_parser = subparsers.add_parser("resume", help="恢复 legacy chat session")
    resume_parser.add_argument("session_ref", help="session id / 前缀 / 最近列表序号")
    resume_parser.add_argument("--provider", help="临时指定 provider")

    prune_parser = subparsers.add_parser("prune", help="列出或删除 stale MMS gateway session")
    prune_parser.add_argument("--cli", default="all", choices=["claude", "codex", "opencode", "all"])
    prune_parser.add_argument("--dry-run", action="store_true", help="只列出候选项；默认行为")
    prune_parser.add_argument("--apply", action="store_true", help="实际删除 stale session；默认只 dry-run")
    prune_parser.add_argument("--yes", action="store_true", help="配合 --apply，确认删除")

    args = parser.parse_args(argv)
    if args.subcommand == "ls":
        _handle_session_ls(args.cli)
        return
    if args.subcommand == "info":
        _handle_session_info(args.session_id, args.cli)
        return
    if args.subcommand == "prune":
        _handle_session_prune(args.cli, apply=bool(args.apply), yes=bool(args.yes))
        return
    if args.subcommand == "resume":
        from mms_chat import chat_main
        from mms_session import resolve_session_ref

        resolved_id, error = resolve_session_ref(args.session_ref, cwd=_safe_getcwd())
        if not resolved_id:
            console.print(f"[red]{error or f'找不到 session: {args.session_ref}'}[/red]")
            return

        chat_argv = ["--resume", resolved_id]
        if args.provider:
            chat_argv.extend(["--provider", args.provider])
        chat_main(_load_command_config(), chat_argv)
        return

    parser.print_help()


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


def _save_cache_config_value(cfg, key, value):
    updated_cfg = dict(cfg)
    cache_cfg = dict(updated_cfg.get("cache", {}) if isinstance(updated_cfg.get("cache"), dict) else {})
    cache_cfg[key] = _normalize_positive_seconds(value, 1)
    updated_cfg["cache"] = cache_cfg
    updated_cfg, _ = _ensure_provider_config(updated_cfg)
    updated_cfg, _ = _ensure_account_config(updated_cfg)
    updated_cfg, _ = _normalize_user_config(updated_cfg)
    updated_cfg, _ = _normalize_cache_config(updated_cfg)
    save_config(updated_cfg)
    return updated_cfg


def _display_cache_settings(cfg):
    cache_cfg = cfg.get("cache", {}) if isinstance(cfg.get("cache"), dict) else {}
    refresh_after = cache_cfg.get("probe_async_refresh_after_sec", _PROBE_ASYNC_REFRESH_AFTER)
    min_interval = cache_cfg.get("probe_async_min_interval_sec", _PROBE_ASYNC_MIN_INTERVAL)
    table = Table(title="MMS Cache Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Meaning", style="white")
    table.add_row("probe_async_refresh_after_sec", str(refresh_after), "cache 超过多久后，启动时后台刷新")
    table.add_row("probe_async_min_interval_sec", str(min_interval), "同一 provider 两次异步刷新最小间隔")
    console.print(table)
    console.print(f"[dim]命令示例: {current_command()} cache refresh-after 1800[/dim]")
    console.print(f"[dim]命令示例: {current_command()} cache min-interval 300[/dim]")
    console.print(f"[dim]命令示例: {current_command()} cache reset[/dim]")


def handle_cache_command(argv):
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} cache",
        description="查看或调整启动期 provider model cache 的异步刷新窗口",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("show", help="显示当前 cache 异步刷新参数")

    refresh_parser = subparsers.add_parser("refresh-after", help="设置 cache 多久后触发后台刷新")
    refresh_parser.add_argument("seconds", type=int, help="正整数秒数")

    interval_parser = subparsers.add_parser("min-interval", help="设置同一 provider 最小异步刷新间隔")
    interval_parser.add_argument("seconds", type=int, help="正整数秒数")

    subparsers.add_parser("reset", help="恢复默认异步刷新参数")

    args = parser.parse_args(argv)
    cfg = _load_command_config()

    if args.subcommand in {None, "show"}:
        _display_cache_settings(cfg)
        return
    if args.subcommand == "refresh-after":
        _save_cache_config_value(cfg, "probe_async_refresh_after_sec", args.seconds)
        console.print(f"[green]✓ cache.probe_async_refresh_after_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "min-interval":
        _save_cache_config_value(cfg, "probe_async_min_interval_sec", args.seconds)
        console.print(f"[green]✓ cache.probe_async_min_interval_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "reset":
        updated_cfg = dict(cfg)
        updated_cfg["cache"] = {
            "probe_async_refresh_after_sec": _PROBE_ASYNC_REFRESH_AFTER,
            "probe_async_min_interval_sec": _PROBE_ASYNC_MIN_INTERVAL,
        }
        updated_cfg, _ = _normalize_cache_config(updated_cfg)
        save_config(updated_cfg)
        console.print("[green]✓ 已恢复默认 cache 异步刷新参数[/green]")
        _display_cache_settings(updated_cfg)
        return

    parser.print_help()


def handle_guard_command(argv, bootstrap_cfg=None):
    _ensure_rich()
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} guard",
        description="查看或接受 MMS 配置/关键文件快照",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看当前快照状态")
    subparsers.add_parser("accept", help="把当前状态设为新的已确认快照")

    args = parser.parse_args(argv)
    config_path = _config_write_target_path()
    cfg = bootstrap_cfg if isinstance(bootstrap_cfg, dict) else (load_config() or _default_config())
    current_snapshot = _build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = _config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = _config_snapshot_path("startup", "accepted.json", config_path=config_path)
    pending_path = _config_snapshot_path("startup", "pending.json", config_path=config_path)
    accepted_payload = _load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = _snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []

    if args.subcommand == "accept":
        payload = {
            "kind": "startup",
            "captured_at": _iso_now(),
            "digest": _snapshot_digest(current_snapshot),
            "snapshot": current_snapshot,
        }
        _write_json_snapshot(latest_path, payload)
        _write_json_snapshot(accepted_path, payload)
        if os.path.exists(pending_path):
            try:
                os.remove(pending_path)
            except OSError:
                pass
        console.print(f"[green]✓ 已接受当前快照[/green]\n[dim]{accepted_path}[/dim]")
        return

    status = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
    table = Table(title="MMS Snapshot Guard")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("status", status)
    table.add_row("accepted", accepted_path)
    table.add_row("latest", latest_path)
    table.add_row("pending", pending_path if os.path.exists(pending_path) else "-")
    table.add_row("real_home", current_snapshot.get("real_home", "-"))
    table.add_row("config_path", current_snapshot.get("config_path", "-"))
    table.add_row("accounts", str(len(current_snapshot.get("accounts", []))))
    table.add_row("providers", str(len(current_snapshot.get("providers", []))))
    console.print(table)
    if diff_lines:
        console.print("[red]检测到漂移：[/red]")
        for item in diff_lines[:20]:
            console.print(f"  - {item}")
        if len(diff_lines) > 20:
            console.print(f"[dim]... 还有 {len(diff_lines) - 20} 项[/dim]")


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
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} fake-upstream",
        description="开发期 fake upstream：不访问真实上游，并把请求写入日志",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看 fake upstream 状态")
    subparsers.add_parser("on", help="开启 fake upstream")
    subparsers.add_parser("off", help="关闭 fake upstream")
    log_parser = subparsers.add_parser("log", help="查看 fake upstream 日志")
    log_parser.add_argument("--tail", type=int, default=20, help="最后 N 条")

    args = parser.parse_args(argv)

    if args.subcommand == "on":
        _set_fake_upstream_enabled(True)
        payload = _fake_upstream_status_payload()
        console.print(f"[green]✓ fake upstream 已开启[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        console.print(f"[dim]log:   {payload['log_path']}[/dim]")
        return
    if args.subcommand == "off":
        _set_fake_upstream_enabled(False)
        payload = _fake_upstream_status_payload()
        console.print(f"[green]✓ fake upstream 已关闭[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        return
    if args.subcommand == "log":
        rows = _fake_upstream_tail_log(args.tail)
        if not rows:
            console.print("[yellow]暂无 fake upstream 日志[/yellow]")
            return
        table = Table(title="Fake Upstream Log")
        table.add_column("Time", style="cyan")
        table.add_column("Kind", style="green")
        table.add_column("Target", style="magenta")
        table.add_column("Detail", style="white")
        for row in rows:
            target = str(row.get("url") or row.get("host") or "-")
            if str(row.get("kind") or "") == "upstream":
                detail = row.get("request_body_preview") or row.get("path") or "-"
            else:
                detail = (
                    row.get("path")
                    or row.get("request_body_preview")
                    or row.get("body")
                    or row.get("proxy")
                    or row.get("listen")
                    or "-"
                )
            table.add_row(str(row.get("ts") or "-"), str(row.get("kind") or "-"), target, str(detail))
        console.print(table)
        return

    payload = _fake_upstream_status_payload()
    table = Table(title="Fake Upstream")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("enabled", "yes" if payload.get("enabled") else "no")
    table.add_row("state_path", str(payload.get("state_path") or "-"))
    table.add_row("log_path", str(payload.get("log_path") or "-"))
    table.add_row("proxy_url", str(payload.get("proxy_url") or "-"))
    table.add_row("ca_cert_path", str(payload.get("ca_cert_path") or "-"))
    table.add_row("proxy_pid", str(payload.get("proxy_pid") or "-"))
    table.add_row("proxy_started_at", str(payload.get("proxy_started_at") or "-"))
    table.add_row("updated_at", str(payload.get("updated_at") or "-"))
    console.print(table)


def handle_logs_command(argv):
    _ensure_rich()
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} logs",
        description="显示 MMS 常用日志路径与可直接复制的查看命令",
    )
    parser.add_argument("--tail", type=int, default=20, help="默认 tail 行数")
    args = parser.parse_args(argv)

    fake_payload = _fake_upstream_status_payload()
    config_root = _config_guard_root_dir(_config_write_target_path())
    fake_log_path = str(fake_payload.get("log_path") or "-")
    fake_status_cmd = f"{current_command()} fake-upstream status"
    fake_log_cmd = f"{current_command()} fake-upstream log --tail {args.tail}"
    raw_tail_cmd = f"tail -n {args.tail} {shlex.quote(fake_log_path)}" if fake_log_path not in {"", "-"} else "-"
    guard_status_cmd = f"{current_command()} guard status"

    table = Table(title="MMS Logs")
    table.add_column("项", style="cyan", no_wrap=True)
    table.add_column("值", style="green")
    table.add_row("config_root", config_root)
    table.add_row("fake_upstream", "on" if fake_payload.get("enabled") else "off")
    table.add_row("fake_log_path", fake_log_path)
    table.add_row("cmd.status", fake_status_cmd)
    table.add_row("cmd.fake_log", fake_log_cmd)
    table.add_row("cmd.raw_tail", raw_tail_cmd)
    table.add_row("cmd.guard", guard_status_cmd)
    console.print(table)


def _run_script_subcommand(script_name, argv, subcommand_name):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", script_name)
    if not os.path.exists(script_path):
        console.print(f"[red]找不到脚本: {script_path}[/red]")
        return 1
    env = os.environ.copy()
    env["MMS_SUBCOMMAND_PROG"] = f"{current_command()} {subcommand_name}"
    try:
        completed = subprocess.run([sys.executable, script_path, *argv], env=env)
        return int(completed.returncode or 0)
    except KeyboardInterrupt:
        return 130


def handle_doctor_command(argv):
    return _run_script_subcommand("doctor_claude_models.py", argv, "doctor")


def handle_exposure_command(argv):
    _ensure_rich()
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} exposure",
        description="审计当前 runtime 会向 CLI 暴露哪些 env / settings / HOME 信息",
    )
    parser.add_argument("cli", nargs="?", default="claude", choices=CLI_NAMES, help="目标 CLI")
    parser.add_argument("--account", help="指定账号 id")
    parser.add_argument("--provider", help="指定 provider id")
    args = parser.parse_args(argv)

    from mms_launchers import inspect_runtime_exposure

    cfg = _load_command_config()
    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _models, launch_cli = _choose_runtime_source(
        cfg,
        args.cli,
        default_provider,
        models_cache,
        account_id=args.account,
        provider_id=args.provider,
    )
    if runtime is None:
        console.print(f"[red]{args.cli} 当前没有可用运行来源[/red]")
        return

    payload = inspect_runtime_exposure(launch_cli, runtime)

    summary = Table(title="MMS Exposure Audit")
    summary.add_column("字段", style="cyan")
    summary.add_column("值", style="green")
    summary.add_row("cli", str(payload.get("cli") or "-"))
    summary.add_row("runtime", str(payload.get("runtime_name") or payload.get("runtime_id") or "-"))
    summary.add_row("auth_mode", str(payload.get("auth_mode") or "-"))
    network = payload.get("network") or {}
    summary.add_row("net", str(network.get("proxy_mode") or "-"))
    summary.add_row("dns", str(network.get("dns_mode") or "-"))
    summary.add_row("proxy", str(network.get("proxy_fingerprint") or "-"))
    summary.add_row("timezone", str(network.get("timezone") or "-"))
    summary.add_row("locale", str(network.get("locale") or "-"))
    summary.add_row("fake_upstream", "on" if network.get("fake_upstream") else "off")
    summary.add_row("ipv4", "on" if network.get("force_ipv4") else "off")
    console.print(summary)

    home = payload.get("home") or {}
    home_table = Table(title="Session Home / Settings")
    home_table.add_column("字段", style="cyan")
    home_table.add_column("值", style="green")
    home_table.add_row("real_home", str(home.get("real_home") or "-"))
    home_table.add_row("account_home", str(home.get("account_home") or "-"))
    home_table.add_row("session_home", str(home.get("session_home") or "-"))
    home_table.add_row("settings_path", str(home.get("settings_path") or "-"))
    console.print(home_table)

    env_table = Table(title="Process Env Exposed To CLI")
    env_table.add_column("Key", style="cyan")
    env_table.add_column("Value", style="green")
    for item in payload.get("process_env") or []:
        env_table.add_row(str(item.get("key") or "-"), str(item.get("value") or "-"))
    console.print(env_table)

    settings = payload.get("settings") or {}
    settings_table = Table(title="Session Settings Exposure")
    settings_table.add_column("字段", style="cyan")
    settings_table.add_column("值", style="green")
    settings_table.add_row("statusLine", "on" if settings.get("statusline") else "off")
    settings_table.add_row("hook_events", ", ".join(settings.get("hook_events") or []) or "-")
    settings_table.add_row("env_keys", ", ".join(settings.get("env_keys") or []) or "-")
    console.print(settings_table)

    notes = payload.get("notes") or []
    if notes:
        console.print("[yellow]可观察性说明：[/yellow]")
        for note in notes:
            console.print(f"  - {note}")


def handle_test_command(argv, subcommand_name="test"):
    return _run_script_subcommand("smoke_cli_channels.py", argv, subcommand_name)


def handle_opencode_smoke_command(argv):
    return _run_script_subcommand("smoke_opencode_profile.py", argv, "opencode-smoke")


def _is_help_request(argv):
    if not argv:
        return False
    if argv[0] == "help":
        return True
    if argv[0] == "config" and _is_config_help_request(argv[1:]):
        return True
    return any(str(arg).strip() in {"-h", "--help"} for arg in argv)


def _is_setup_web_request(argv):
    if not argv:
        return False
    command = str(argv[0] or "").strip()
    if command in {"setup", "setup-web", "web-setup"}:
        return True
    if command != "config" or len(argv) < 2:
        return False
    return str(argv[1] or "").strip() in {"web", "webui", "setup.web", "setup-web"}


def _is_config_help_request(args_rest):
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    return key_path in {
        "-h",
        "--help",
        "help",
        "preferences",
        "preferences.help",
        "preference.help",
        "preferences.path",
        "preference.path",
        "preferences.example",
        "preference.example",
        "preferences.doc",
        "preference.doc",
        "root",
        "root.status",
        "status.root",
        "check",
        "preview-check",
        "preview.check",
        "v2-check",
        "bundle",
        "consumer-bundle",
        "manifest",
        "save-plan",
        "save.plan",
        "v2-save-plan",
        "apply-plan",
        "apply.plan",
        "preview-apply",
        "apply-preview",
        "registry-apply-plan",
        "doctor",
        "preview-doctor",
        "preview.doctor",
        "v2-doctor",
        "web",
        "webui",
        "setup.web",
        "setup-web",
        "gates",
        "human-gate",
        "humangate",
        "human-gates",
    }


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
    if len(argv) < 2:
        return False
    if argv[0] != "session" or argv[1] != "prune":
        return False
    return "--apply" not in argv


def _legacy_chat_discuss_enabled():
    value = str(os.environ.get("MMS_ENABLE_LEGACY_CHAT_DISCUSS") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _handle_disabled_legacy_chat_discuss(command):
    command = str(command or "").strip()
    if command not in {"chat", "discuss"}:
        return False
    if _legacy_chat_discuss_enabled():
        return False
    _ensure_rich()
    console.print(f"[yellow]`{current_command()} {command}` 已从默认入口下线。[/yellow]")
    console.print("[cyan]新会话请直接运行 `mms` / `mmd`，通过 TUI 选择 CLI、模型、fallback 与设置。[/cyan]")
    console.print("[dim]兼容模块暂时保留给内部依赖；如确需一次性旧入口，可设置 MMS_ENABLE_LEGACY_CHAT_DISCUSS=1。[/dim]")
    return True


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

    if len(argv) >= 1 and _handle_disabled_legacy_chat_discuss(argv[0]):
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
        if command == "chat":
            from mms_chat import chat_main

            chat_main(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
        if command == "discuss":
            from mms_discuss import discuss_main

            discuss_main(preloaded_command_cfg if preloaded_command_cfg is not None else _load_command_config(), argv[1:])
            return
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

    if len(argv) >= 1 and argv[0] == "discuss":
        from mms_discuss import discuss_main

        cfg = bootstrap_cfg
        if cfg is None:
            cfg = _default_config()
            save_config(cfg)
        cfg = apply_local_overrides(cfg)
        discuss_main(cfg, argv[1:])
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
            f"  {current_command()} usage ...       查看 usage 统计\n\n"
            "Legacy / emergency-only 模块（默认入口已下线）:\n"
            f"  {current_command()} chat/discuss    默认拒绝直接启动；新会话请用 TUI launcher\n"
            "  MMS_ENABLE_LEGACY_CHAT_DISCUSS=1 可临时打开旧入口"
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
        presets = cfg.get("presets", {})
        visible_presets = {
            name: p for name, p in presets.items()
            if _preset_has_visible_model_options(p)
        }
        if visible_presets:
            table = Table(title="已保存预设")
            table.add_column("名称", style="cyan")
            table.add_column("CLI", style="green")
            table.add_column("Provider", style="magenta")
            table.add_column("模型", style="yellow")
            table.add_column("描述", style="dim")
            table.add_column("模式", style="blue")
            for name, p in visible_presets.items():
                model_str = p.get("model", f"opus={p.get('opus','')}, sonnet={p.get('sonnet','')}")
                desc = p.get("description", "")
                auth = _infer_preset_auth_mode(p) or "—"
                table.add_row(name, p.get("cli", "?"), p.get("provider", DEFAULT_PROVIDER_ID), str(model_str), desc, auth)
            console.print(table)
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
