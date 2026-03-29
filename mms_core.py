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
from datetime import datetime, timezone

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

from mms_account_state import seed_claude_state, seed_gemini_state
from mms_adapter_registry import TOP_SOURCE_COMPANIES, DEFAULT_ADAPTER_POLICY, PROVIDER_TEMPLATES

# Provider 调试日志（写入文件，不影响 TUI 输出）
_PROBE_DEBUG_DIR = os.path.join(
    os.environ.get("MMS_CONFIG_DIR") or os.environ.get("CCS_CONFIG_DIR") or os.path.expanduser("~/.config/mms"),
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
LEGACY_COMMAND = "ccs"
PRIMARY_COMMAND = "mms"

PRIMARY_CONFIG_DIR = os.path.expanduser("~/.config/mms")
LEGACY_CONFIG_DIR = os.path.expanduser("~/.config/ccs")
CONFIG_DIR = PRIMARY_CONFIG_DIR
CONFIG_PATH = os.path.join(PRIMARY_CONFIG_DIR, "config.toml")
CREDENTIALS_PATH = os.path.join(PRIMARY_CONFIG_DIR, "credentials.sh")
ENV_DIR = os.path.join(PRIMARY_CONFIG_DIR, "env")
ACCOUNTS_DIR = os.path.join(PRIMARY_CONFIG_DIR, "accounts")
USAGE_PATH = os.path.join(PRIMARY_CONFIG_DIR, "usage.json")
LEGACY_CONFIG_PATH = os.path.join(LEGACY_CONFIG_DIR, "config.toml")
LEGACY_CREDENTIALS_PATH = os.path.join(LEGACY_CONFIG_DIR, "credentials.sh")
LEGACY_ENV_DIR = os.path.join(LEGACY_CONFIG_DIR, "env")
LEGACY_USAGE_PATH = os.path.join(LEGACY_CONFIG_DIR, "usage.json")
OVERRIDE_PATHS = [
    os.path.join(LEGACY_CONFIG_DIR, "override.toml"),
    os.path.join(PRIMARY_CONFIG_DIR, "override.toml"),
]
DEFAULT_BASE_URL = "https://your-api.example.com"
API_URL_ENV_NAME = "MMS_API_BASE_URL"
API_KEY_ENV_NAME = "MMS_API_KEY"
# Legacy fallback: 旧环境变量仍然生效
_LEGACY_API_URL_ENV = "CCS_API_BASE_URL"
_LEGACY_API_KEY_ENV = "CCS_API_KEY"
DEFAULT_PROVIDER_ID = "default"
DEFAULT_PROVIDER_PROTOCOLS = ["anthropic_messages", "openai_chat_completions"]
OAUTH_CAPABLE_CLIS = ("claude", "codex", "gemini")
DEFAULT_PRIORITY = 100
MODE_ALL = "全部模型"
MODE_RECOMMENDED = "推荐模型"
DIRECT_CLI_MODES = {"qwen", "kimi"}
DEFAULT_KIMI_MODEL = "kimi-k2.5"


class WizardBack(Exception):
    pass


class WizardCancel(Exception):
    pass

# 统一模型家族规则表（有序）。
# keywords 匹配模型名任意部分（不限前缀），支持 provider/model 格式。
# display_category 用于 Rich 表格的分类列。
MODEL_FAMILIES = [
    {"family": "Claude",  "keywords": ("claude",),                          "category": "Claude 系 ⭐"},
    {"family": "GPT",     "keywords": ("gpt-", "o1-", "o3-", "o4-", "codex-"), "category": "GPT 系"},
    {"family": "Gemini",  "keywords": ("gemini",),                          "category": "Google 系"},
    {"family": "Qwen",    "keywords": ("qwen",),                           "category": "国产系"},
    {"family": "Kimi",    "keywords": ("kimi",),                           "category": "国产系"},
    {"family": "MiniMax", "keywords": ("minimax",),                        "category": "国产系"},
    {"family": "GLM",     "keywords": ("glm",),                            "category": "国产系"},
]


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

SCENES = {
    "常规任务": {
        "emoji": "⚡",
        "desc": "简单问答、日常杂活",
        "cli": "qwen",
        "model": "qwen3-max-2026-01-23",
    },
    "主力编码": {
        "emoji": "💻",
        "desc": "日常开发、代码重构",
        "cli": "claude",
        "default_tier": "high",
        "variants": [
            {
                "tier": "med",
                "name": "GLM",
                "desc": "中杯",
                "model_info": {"model": "glm-5"},
            },
            {
                "tier": "high",
                "name": "GPT",
                "desc": "默认",
                "model_info": {"model": "gpt-5.3-codex"},
            },
            {
                "tier": "xhigh",
                "name": "Sonnet",
                "desc": "超大杯",
                "model_info": {"model": "claude-sonnet-4-6"},
            },
        ],
    },
    "深度思考": {
        "emoji": "🧠",
        "desc": "复杂推理、架构设计",
        "cli": "claude",
        "default_tier": "high",
        "variants": [
            {
                "tier": "med",
                "name": "Sonnet",
                "desc": "中杯",
                "model_info": {"model": "claude-sonnet-4-6"},
            },
            {
                "tier": "high",
                "name": "GPT",
                "desc": "默认",
                "model_info": {"model": "gpt-5.4"},
            },
            {
                "tier": "xhigh",
                "name": "Opus",
                "desc": "超大杯",
                "model_info": {"model": "claude-opus-4-6"},
            },
        ],
    },
    "中文主力": {
        "emoji": "🇨🇳",
        "desc": "中文内容、国内业务",
        "cli": "kimi",
        "model": "kimi-k2.5",
    },
    "文字产出": {
        "emoji": "🇺🇸",
        "desc": "长文撰写、内容输出",
        "cli": "codex",
        "default_tier": "med",
        "variants": [
            {
                "tier": "med",
                "name": "Gemini",
                "desc": "默认英文",
                "model_info": {"model": "gemini-3.1-pro-preview"},
            },
            {
                "tier": "high",
                "name": "GPT",
                "desc": "更稳一点",
                "model_info": {"model": "gpt-5.4"},
            },
        ],
    },
    "负载模式": {
        "emoji": "⚖️",
        "desc": "自动按任务轻重切换模型",
        "cli": "claude",
        "load_balance": True,
    },
    "视觉内容": {
        "emoji": "🎨",
        "desc": "图片理解、UI分析",
        "cli": "claude",
        "default_tier": "med",
        "variants": [
            {
                "tier": "xhigh",
                "name": "Gemini",
                "desc": "排第一",
                "model_info": {"model": "gemini-3.1-pro-preview"},
            },
            {
                "tier": "high",
                "name": "Kimi",
                "desc": "排第二",
                "model_info": {"model": "kimi-k2.5"},
            },
            {
                "tier": "med",
                "name": "MiniMax",
                "desc": "也能用",
                "model_info": {"model": "MiniMax-M2.5"},
            },
        ],
    },
}

CLI_NAMES = ["claude", "codex"]
CLI_MODEL_FAMILY_HINTS = {
    "qwen": ("qwen",),
    "kimi": ("kimi",),
}
SCENE_META_KEYS = {"emoji", "desc", "cli", "variants", "default_tier", "load_balance"}


def current_command():
    invoked = os.path.basename(sys.argv[0] or "").strip().lower()
    if invoked in {PRIMARY_COMMAND, LEGACY_COMMAND}:
        return invoked
    return PRIMARY_COMMAND


def display_title():
    return "MMS" if current_command() == PRIMARY_COMMAND else "CCS"


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


ROLE_WEIGHTS = {"primary": 0, "auto": 1, "fallback": 2}
VALID_ROLES = set(ROLE_WEIGHTS.keys())


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
        "supported_clis": list(CLI_NAMES),
        "enabled": True,
        "role": "auto",
    }


def _default_account_home(account_id):
    return os.path.join(ACCOUNTS_DIR, account_id)


def _normalize_priority(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY


def _normalize_account_id(account_id):
    value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(account_id or "").strip().lower())
    value = value.strip("-_")
    return value or "account"


def _wizard_prompt(label, default="", password=False, required=False):
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
    return {
        "id": account_id,
        "name": str(account.get("name") or account_id).strip() or account_id,
        "cli": cli,
        "auth_mode": "oauth",
        "enabled": bool(account.get("enabled", True)),
        "home_dir": os.path.expanduser(home_dir),
        "priority": _normalize_priority(account.get("priority", DEFAULT_PRIORITY)),
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
    """读取 provider 环境变量，MMS_PROVIDER_* 优先，fallback 到 CCS_PROVIDER_*。"""
    sanitized = _sanitize_provider_id(provider_id)
    return (os.environ.get(f"MMS_PROVIDER_{sanitized}_{field}", "").strip()
            or os.environ.get(f"CCS_PROVIDER_{sanitized}_{field}", "").strip())


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

    supported_clis = merged.get("supported_clis", CLI_NAMES)
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    merged["supported_clis"] = [str(item).strip() for item in supported_clis if str(item).strip()]
    if not merged["supported_clis"]:
        merged["supported_clis"] = list(CLI_NAMES)

    merged["enabled"] = bool(merged.get("enabled", True))
    merged["priority"] = _normalize_priority(merged.get("priority", DEFAULT_PRIORITY))
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

def _first_existing_path(*paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return paths[0] if paths else ""


def _active_config_path():
    return _first_existing_path(CONFIG_PATH, LEGACY_CONFIG_PATH)


def _active_credentials_path():
    return _first_existing_path(CREDENTIALS_PATH, LEGACY_CREDENTIALS_PATH)


def _active_usage_path():
    return _first_existing_path(USAGE_PATH, LEGACY_USAGE_PATH)

def load_config():
    config_path = _active_config_path()
    if not os.path.exists(config_path):
        return None
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)
    cfg = _migrate_legacy_api_config(cfg)
    cfg, changed = _ensure_provider_config(cfg)
    cfg, account_changed = _ensure_account_config(cfg)
    cfg, role_changed = _normalize_user_config(cfg)
    cfg, cache_changed = _normalize_cache_config(cfg)
    changed = changed or account_changed or role_changed or cache_changed
    if changed or config_path != CONFIG_PATH:
        save_config(cfg)
    return cfg


def load_runtime_config():
    cfg = load_config()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


def save_config(cfg):
    if tomli_w is None:
        console.print("[red]缺少 tomli-w，请执行: pip install tomli-w[/red]")
        sys.exit(1)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def _load_toml_file(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _existing_override_paths():
    return [path for path in OVERRIDE_PATHS if os.path.exists(path)]


def _merge_dicts(base, override):
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


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


def _save_usage_stats(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(USAGE_PATH, 0o600)


def _backup_config_tree(label):
    backup_root = os.path.expanduser("~/.config/mms-backups")
    os.makedirs(backup_root, exist_ok=True)
    backup_dir = os.path.join(backup_root, f"{label}-{_local_now_slug()}")
    os.makedirs(backup_dir, exist_ok=True)
    for source in {PRIMARY_CONFIG_DIR, LEGACY_CONFIG_DIR}:
        if os.path.exists(source):
            shutil.copytree(
                source,
                os.path.join(backup_dir, os.path.basename(source)),
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


def _record_usage(runtime, cli_name, model_info):
    stats = _load_usage_stats()
    sources = stats.setdefault("sources", {})
    key = _runtime_usage_key(runtime, cli_name)
    model_name = _resolve_model_name(model_info)
    entry = sources.setdefault(key, {
        "runtime_kind": runtime.get("runtime_kind", "provider"),
        "id": runtime.get("id", "default"),
        "name": runtime.get("name", runtime.get("id", "default")),
        "cli": cli_name,
        "launches": 0,
        "last_used_at": "",
        "last_model": "",
        "models": {},
    })
    entry["launches"] += 1
    entry["last_used_at"] = _iso_now()
    entry["last_model"] = model_name
    models = entry.setdefault("models", {})
    models[model_name] = int(models.get(model_name, 0)) + 1
    # 全局最后一次使用（按 CLI 分桶，供 TUI "上次使用" 展示）
    last_by_cli = stats.setdefault("last_by_cli", {})
    last_by_cli[cli_name] = {
        "cli": cli_name,
        "model": model_name,
        "model_info": model_info if isinstance(model_info, dict) else {"model": str(model_info)},
        "last_used_at": _iso_now(),
    }
    _save_usage_stats(stats)


def _record_scene_usage(scene_name, cli_name, model_info):
    """记录场景级启动统计（用于 TUI 启动次数排名）"""
    if not scene_name or scene_name.startswith("__"):
        return
    stats = _load_usage_stats()
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
    # 全局 last_* 已由 _record_usage 写入，此处不再重复
    _save_usage_stats(stats)


def _get_scene_usage():
    """获取上次使用信息（按 CLI 分桶）+ 场景启动次数，返回 (last_by_cli, scene_counts)"""
    stats = _load_usage_stats()
    scene_counts = {}
    for name, entry in stats.get("scenes", {}).items():
        scene_counts[name] = entry.get("launches", 0)
    return stats.get("last_by_cli", {}), scene_counts


def _launch_with_tracking(cli_name, model_info, runtime, once=False):
    _record_usage(runtime, cli_name, model_info)
    from mms_launchers import launch_cli
    launch_cli(cli_name, model_info, runtime, once=once)


def _legacy_provider_env_name(provider_id, field):
    """旧版 CCS_PROVIDER_* 环境变量名，用于 credentials.sh fallback。"""
    return f"CCS_PROVIDER_{_sanitize_provider_id(provider_id)}_{field}"


def load_provider_credentials(provider_id=DEFAULT_PROVIDER_ID):
    base_key = _provider_env_name(provider_id, "BASE_URL")
    openai_base_key = _provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = _provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = _provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = _provider_env_name(provider_id, "OPENAI_API_KEY")
    # Legacy CCS_PROVIDER_* fallback keys
    legacy_base_key = _legacy_provider_env_name(provider_id, "BASE_URL")
    legacy_openai_base_key = _legacy_provider_env_name(provider_id, "OPENAI_BASE_URL")
    legacy_anthropic_base_key = _legacy_provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    legacy_api_key_name = _legacy_provider_env_name(provider_id, "API_KEY")
    legacy_openai_api_key_name = _legacy_provider_env_name(provider_id, "OPENAI_API_KEY")

    base_url = os.environ.get(base_key, "").strip() or os.environ.get(legacy_base_key, "").strip()
    openai_base_url = os.environ.get(openai_base_key, "").strip() or os.environ.get(legacy_openai_base_key, "").strip()
    anthropic_base_url = os.environ.get(anthropic_base_key, "").strip() or os.environ.get(legacy_anthropic_base_key, "").strip()
    api_key = os.environ.get(api_key_name, "").strip() or os.environ.get(legacy_api_key_name, "").strip()
    openai_api_key = os.environ.get(openai_api_key_name, "").strip() or os.environ.get(legacy_openai_api_key_name, "").strip()

    if provider_id == DEFAULT_PROVIDER_ID:
        base_url = base_url or os.environ.get(API_URL_ENV_NAME, "").strip() or os.environ.get(_LEGACY_API_URL_ENV, "").strip()
        api_key = api_key or os.environ.get(API_KEY_ENV_NAME, "").strip() or os.environ.get(_LEGACY_API_KEY_ENV, "").strip()

    for credentials_path in (CREDENTIALS_PATH, LEGACY_CREDENTIALS_PATH):
        if not os.path.exists(credentials_path):
            continue
        file_values = _load_env_file(credentials_path)
        # 先查 MMS_PROVIDER_* 再 fallback 到 CCS_PROVIDER_*
        base_url = base_url or file_values.get(base_key, "").strip() or file_values.get(legacy_base_key, "").strip()
        openai_base_url = openai_base_url or file_values.get(openai_base_key, "").strip() or file_values.get(legacy_openai_base_key, "").strip()
        anthropic_base_url = anthropic_base_url or file_values.get(anthropic_base_key, "").strip() or file_values.get(legacy_anthropic_base_key, "").strip()
        api_key = api_key or file_values.get(api_key_name, "").strip() or file_values.get(legacy_api_key_name, "").strip()
        openai_api_key = openai_api_key or file_values.get(openai_api_key_name, "").strip() or file_values.get(legacy_openai_api_key_name, "").strip()
        if provider_id == DEFAULT_PROVIDER_ID:
            base_url = base_url or file_values.get(API_URL_ENV_NAME, "").strip() or file_values.get(_LEGACY_API_URL_ENV, "").strip()
            api_key = api_key or file_values.get(API_KEY_ENV_NAME, "").strip() or file_values.get(_LEGACY_API_KEY_ENV, "").strip()

    config_path = _active_config_path()
    if provider_id == DEFAULT_PROVIDER_ID and (not base_url or not api_key) and os.path.exists(config_path):
        with open(config_path, "rb") as f:
            legacy_cfg = tomllib.load(f)
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


def load_api_credentials():
    provider_creds = load_provider_credentials(DEFAULT_PROVIDER_ID)
    return provider_creds["base_url"], provider_creds["api_key"]


def save_api_credentials(base_url, api_key):
    save_provider_credentials(DEFAULT_PROVIDER_ID, base_url, api_key)


def resolve_provider_context(cfg, provider_id=None):
    provider = dict(get_provider_definition(cfg, provider_id))
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
            "cheap": {"cli": "qwen", "model": "qwen3-coder-plus"},
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


def _account_label(account):
    return account.get("name", account.get("id", "account"))


def _account_env(account):
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
    env = os.environ.copy()
    if cli_name == "gemini":
        seed_gemini_state(home_dir)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        xdg_config_home = os.path.join(home_dir, ".config")
        env["HOME"] = home_dir
        env["XDG_CONFIG_HOME"] = xdg_config_home
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


def _account_status_command(cli_name):
    if cli_name == "claude":
        return ["claude", "auth", "status"]
    if cli_name == "codex":
        return ["codex", "login", "status"]
    if cli_name == "gemini":
        return None
    return None


def _probe_account_status(account):
    cli_name = account.get("cli")
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
    env = _account_env(account)
    os.makedirs(account.get("home_dir", ""), exist_ok=True)
    if cli_name == "claude":
        command = ["claude", "auth", "login"]
    elif cli_name == "codex":
        command = ["codex", "login"]
    elif cli_name == "gemini":
        command = ["gemini"]
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
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)


def _ensure_interactive_terminal(action_hint):
    if sys.stdin.isatty():
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
        provider_id = Prompt.ask("模型源 ID", default=provider_id).strip() or DEFAULT_PROVIDER_ID
    name = Prompt.ask("模型源名称", default=current.get("name") or provider_id).strip() or provider_id
    protocols = _prompt_csv_values(
        "协议（逗号分隔）",
        current.get("protocols", list(DEFAULT_PROVIDER_PROTOCOLS)),
        list(DEFAULT_PROVIDER_PROTOCOLS),
    )
    supported_clis = _prompt_csv_values(
        "支持的 CLI（逗号分隔）",
        current.get("supported_clis", list(CLI_NAMES)),
        list(CLI_NAMES),
    )
    use_custom_models_endpoint = Confirm.ask(
        "模型拉取使用自定义 endpoint？",
        default=current.get("models_endpoint", "/models") != "/models",
    )
    models_endpoint = "/models"
    if use_custom_models_endpoint:
        models_endpoint = _normalize_models_endpoint(
            Prompt.ask("模型列表接口路径（输入 manual 表示仅用手工模型）", default=current.get("models_endpoint", "/models"))
        )
    priority = _normalize_priority(Prompt.ask("优先级（数字越小越优先）", default=str(current.get("priority", DEFAULT_PRIORITY))))
    note = Prompt.ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = Confirm.ask("启用这个模型源？", default=bool(current.get("enabled", True)))
    return _normalize_provider({
        "id": provider_id,
        "name": name,
        "protocols": protocols,
        "supported_clis": supported_clis,
        "models_endpoint": models_endpoint,
        "priority": priority,
        "note": note,
        "enabled": enabled,
    })


def _provider_template_names():
    return {
        "1": "generic",
        "2": "qwen",
        "3": "bailian-codingplan",
        "4": "kimi",
        "5": "kimi-codingplan",
        "6": "glm-cn",
        "7": "glm-en",
        "8": "minimax-cn",
        "9": "minimax-codingplan",
        "10": "minimax-en",
    }


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
    return payload


def _select_provider_template(preset_id=None):
    if preset_id in PROVIDER_TEMPLATES:
        return preset_id
    console.print("  1. 通用兼容网关")
    console.print("  2. Qwen")
    console.print("  3. 百炼 CodingPlan (sk-sp-*)")
    console.print("  4. Kimi")
    console.print("  5. Kimi CodingPlan (sk-kimi-*)")
    console.print("  6. GLM CN (智谱 BigModel)")
    console.print("  7. GLM EN (Z.ai)")
    console.print("  8. MiniMax CN")
    console.print("  9. MiniMax CodingPlan")
    console.print("  10. MiniMax EN")
    selected = Prompt.ask("选择网关通道类型", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], default="1")
    return _provider_template_names()[selected]


def _prompt_account_metadata(existing=None, preset_id=None, preset_cli=None):
    _ensure_interactive_terminal("账号档案配置编辑")
    current = _normalize_account(existing or {"cli": preset_cli or "claude", "id": preset_id or ""})
    account_id = preset_id or current.get("id") or "claude-main"
    if not preset_id:
        account_id = _normalize_account_id(Prompt.ask("文件夹名（用于目录和命令）", default=account_id))
    cli_name = preset_cli or current.get("cli", "claude")
    if not preset_cli:
        cli_name = Prompt.ask("绑定的 CLI", choices=list(OAUTH_CAPABLE_CLIS), default=cli_name)
    name = Prompt.ask("显示名", default=current.get("name") or account_id).strip() or account_id
    home_dir = current.get("home_dir") or _default_account_home(account_id)
    priority = _normalize_priority(Prompt.ask("优先级（数字越小越优先）", default=str(current.get("priority", DEFAULT_PRIORITY))))
    note = Prompt.ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = Confirm.ask("启用这个账号档案？", default=bool(current.get("enabled", True)))
    return _normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "priority": priority,
        "note": note,
        "enabled": enabled,
    })


def _prompt_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    if not sys.stdin.isatty():
        console.print(
            f"[red]当前不是交互终端，无法输入 API URL / API Key，请在终端里运行 {current_command()} "
            f"或执行 {config_command_hint()}[/red]"
        )
        sys.exit(1)

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
            f"请输入 OpenAI API 地址（模型源: {_provider_label(provider)}）",
            default=current_openai or default_openai,
        ).rstrip("/")
        anthropic_base_url = Prompt.ask(
            f"请输入 Anthropic API 地址（模型源: {_provider_label(provider)}）",
            default=current_anthropic or default_anthropic,
        ).rstrip("/")
        base_url = anthropic_base_url or openai_base_url
    elif needs_openai and not needs_anthropic:
        openai_base_url = Prompt.ask(
            f"请输入 OpenAI API 地址（模型源: {_provider_label(provider)}）",
            default=current_openai or default_openai or existing_base_url or DEFAULT_BASE_URL,
        ).rstrip("/")
        base_url = openai_base_url
    elif needs_anthropic and not needs_openai:
        anthropic_base_url = Prompt.ask(
            f"请输入 Anthropic API 地址（模型源: {_provider_label(provider)}）",
            default=current_anthropic or default_anthropic or existing_base_url or DEFAULT_BASE_URL,
        ).rstrip("/")
        base_url = anthropic_base_url
    else:
        base_default = existing_base_url or DEFAULT_BASE_URL
        base_url = Prompt.ask(
            f"请输入 API 地址（模型源: {_provider_label(provider)}）",
            default=base_default,
        ).rstrip("/")
        openai_base_url = base_url if needs_openai else ""
        anthropic_base_url = base_url if needs_anthropic else ""

    key_prompt = f"请输入 API Key（模型源: {_provider_label(provider)}）"
    if allow_keep and existing_api_key:
        key_prompt = f"请输入 API Key（模型源: {_provider_label(provider)}，留空保持不变）"

    prompt_kwargs = {"password": True}
    if allow_keep:
        prompt_kwargs["default"] = ""
    api_key = Prompt.ask(key_prompt, **prompt_kwargs)
    if allow_keep and existing_api_key and not api_key:
        api_key = existing_api_key

    if not api_key:
        console.print("[red]API Key 不能为空[/red]")
        sys.exit(1)

    return base_url, api_key, openai_base_url, anthropic_base_url


def _quick_connect_gateway(cfg, preset_id=None):
    _ensure_interactive_terminal("网关通道接入")
    template_key = _select_provider_template(preset_id=preset_id)
    template = _provider_template_payload(template_key)
    console.print(Panel(
        "[bold]网关通道[/bold]\n\n输入一个兼容 OpenAI / Anthropic 的 API 地址和 Key。\n"
        "默认会启用全部 CLI；后续如需精细限制，再用 provider.edit 调整。\n"
        "[dim]输入 b 返回，q 退出。[/dim]",
        title="快速接入",
        border_style="cyan",
    ))
    providers = _provider_map(cfg)
    suggested_name = template["name"]
    try:
        name = _wizard_prompt("显示名称（主界面里看到的名字）", default=suggested_name).strip() or suggested_name
        suggested_id = _normalize_provider_id_input(name)
        provider_id = _normalize_provider_id_input(
            _wizard_prompt("内部标识（用于配置和命令）", default=template["id"] or suggested_id).strip() or suggested_id
        )
    except WizardBack:
        console.print("[yellow]已返回上一层[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print("[yellow]已退出接入[/yellow]")
        return cfg, False
    if provider_id in providers:
        console.print(f"[red]通道 ID '{provider_id}' 已存在，请换一个，或使用 {current_command()} config provider.edit {provider_id}[/red]")
        return cfg, False

    provider = _normalize_provider({
        **template,
        "id": provider_id,
        "name": name,
    })
    if Confirm.ask("模型拉取使用自定义 endpoint？", default=False):
        provider["models_endpoint"] = _normalize_models_endpoint(
            Prompt.ask("模型列表接口路径", default=provider.get("models_endpoint", "/models"))
        )
    updated_cfg = _upsert_provider(cfg, provider)
    save_config(updated_cfg)
    setup_provider_credentials(provider)
    console.print(f"[green]✓ 已接入网关通道: {provider_id}[/green]")
    return load_config(), True


def _quick_connect_official(cfg, preset_cli=None):
    _ensure_interactive_terminal("官方通道接入")
    console.print(Panel(
        "[bold]官方通道[/bold]\n\n创建一个独立登录目录，然后进入官方 CLI 登录。\n"
        "适合多个 ChatGPT / Claude / Gemini 账号并行使用。\n"
        "[dim]输入 b 返回，q 退出。[/dim]",
        title="快速接入",
        border_style="cyan",
    ))
    choices = {
        "1": ("codex", "ChatGPT / Codex"),
        "2": ("claude", "Claude"),
        "3": ("gemini", "Gemini"),
    }
    if preset_cli in OAUTH_CAPABLE_CLIS:
        cli_name = preset_cli
    else:
        console.print("  1. ChatGPT / Codex")
        console.print("  2. Claude")
        console.print("  3. Gemini")
        try:
            selected = _wizard_prompt("选择官方通道类型", default="1")
        except WizardBack:
            console.print("[yellow]已返回上一层[/yellow]")
            return cfg, False
        except WizardCancel:
            console.print("[yellow]已退出接入[/yellow]")
            return cfg, False
        if selected not in choices:
            console.print("[red]请输入 1-3[/red]")
            return cfg, False
        cli_name = choices[selected][0]

    suggested_name = f"{cli_name}-main"
    try:
        name = _wizard_prompt("显示名（主界面里看到的名字）", default=suggested_name).strip() or suggested_name
        account_id = _normalize_account_id(
            _wizard_prompt(
                "文件夹名（用于目录和命令，例如 apple / work / personal）",
                default=_normalize_account_id(name),
            ).strip()
        )
    except WizardBack:
        console.print("[yellow]已返回上一层[/yellow]")
        return cfg, False
    except WizardCancel:
        console.print("[yellow]已退出接入[/yellow]")
        return cfg, False
    accounts = _account_map(cfg)
    if account_id in accounts:
        console.print(f"[red]文件夹名 '{account_id}' 已存在，请换一个，或使用 {current_command()} config account.edit {account_id}[/red]")
        return cfg, False

    home_dir = _default_account_home(account_id)
    account = _normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "enabled": True,
        "priority": DEFAULT_PRIORITY,
    })
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = list(cfg.get("accounts", [])) + [account]
    updated_cfg, _ = _ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已添加官方通道: {account_id}[/green]")
    console.print(f"[dim]文件夹目录: {home_dir}[/dim]")
    if Confirm.ask("现在去登录这个官方通道？", default=True):
        _run_account_login(account)
    if Confirm.ask(f"设为 {cli_name} 的默认官方通道？", default=True):
        updated_cfg = load_config()
        updated_cfg.setdefault("account", {}).setdefault("defaults", {})
        updated_cfg["account"]["defaults"][cli_name] = account_id
        save_config(updated_cfg)
        console.print(f"[green]✓ {cli_name} 默认官方通道已更新为 {account_id}[/green]")
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


def _display_runtime_usage(runtime_kind, runtime_id, title):
    rows = _usage_rows_for_runtime(runtime_kind, runtime_id)
    if not rows:
        console.print(f"[yellow]{title} 还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件: {_active_usage_path()}[/dim]")
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

    table = Table(title=f"{provider.get('name', provider.get('id'))} · 模型列表", show_lines=True)
    table.add_column("模型", style="cyan")
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


def _manage_provider_models(cfg, provider_id):
    changed = False
    current_cfg = cfg
    while True:
        provider = resolve_provider_context(current_cfg, provider_id)
        probe = _probe_models(provider, emit_output=True)
        console.print(Panel(
            f"[bold]Provider:[/bold] {provider.get('name', provider_id)}\n"
            f"[bold]模型列表接口:[/bold] {provider.get('models_endpoint', '/models')}\n"
            f"[bold]基础来源:[/bold] {_model_source_label(probe.get('base_source', 'remote'))}\n"
            f"[bold]最终展示模型数:[/bold] {len(probe.get('models') or [])}",
            title="模型管理",
            border_style="cyan",
        ))
        console.print("  1. 查看当前模型列表")
        console.print("  2. 刷新远端模型列表")
        console.print("  3. 添加补充模型")
        console.print("  4. 隐藏模型")
        console.print("  5. 移除补充/取消隐藏")
        console.print("  6. 恢复默认模型补丁")
        console.print("  7. 编辑模型列表接口")
        console.print("  8. 返回")
        choice = Prompt.ask("选择操作", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="8")
        if choice == "1":
            _display_provider_model_table(provider, probe)
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
            response = httpx.post(
                f"{base_url.rstrip('/')}/v1/messages",
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
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
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
            ("模型接口", provider.get("models_endpoint", "/models")),
            ("模型补丁", f"补充 {extra_count} / 隐藏 {hidden_count}"),
            ("协议", ", ".join(provider.get("protocols", []))),
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


def detect_working_base_url(configured_url, path, headers, body=None, timeout=5):
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
                resp = httpx.post(f"{candidate}{path}", headers=headers, content=body, timeout=timeout)
            else:
                resp = httpx.get(f"{candidate}{path}", headers=headers, timeout=timeout)
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
        if age > ttl and not allow_stale:
            return None
        normalized = dict(data)
        normalized["raw_models"] = raw_models
        normalized["models"] = list(raw_models)
        normalized.setdefault("base_source", "remote")
        normalized.setdefault("error", None)
        normalized.setdefault("error_kind", None)
        normalized.setdefault("details", [])
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
        "error": None,
        "error_kind": None,
        "working_url": file_cached.get("working_url"),
        "details": [],
        "base_source": file_cached.get("base_source", "remote"),
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


def _derived_model_aliases(base_models):
    aliases = []
    if any(model_id.startswith("claude-sonnet-4-") for model_id in base_models):
        aliases.append("claude-sonnet-4-6")
    if any(model_id.startswith("claude-opus-4-") for model_id in base_models):
        aliases.append("claude-opus-4-6")
    return aliases


def _apply_provider_model_patch(provider, base_result):
    result = dict(base_result)
    base_models = _normalize_model_id_list(result.get("raw_models") or result.get("models") or [])
    extra_models = _normalize_model_id_list(provider.get("extra_models", []))
    derived_aliases = _derived_model_aliases(base_models)
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
        "claude-opus-4-6", "claude-sonnet-4-6",
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
                    response = httpx.get(full_url, headers=headers, timeout=15)
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
            "summary": "场景和预设仍然可以继续使用，但模型浏览会受限。",
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
            "summary": "继续使用场景或预设，但不会有模型浏览列表。",
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
        console.print("[yellow]已跳过模型校验。模型浏览将暂时不可用，但场景和预设仍可继续。[/yellow]")
        return provider, True
    return provider, False


def setup_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    base_url, api_key, openai_base_url, anthropic_base_url = _prompt_provider_credentials(
        provider, existing_base_url, existing_api_key, allow_keep
    )
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


def setup_wizard():
    title = display_title()
    console.print(Panel(
        f"[bold cyan]欢迎使用 {title} — AI Coding CLI 统一启动器[/bold cyan]\n\n"
        f"{title} 帮你一键启动 AI 编程助手\n"
        "首次使用，需要配置 API 地址和认证信息",
        title=f"{title} Setup",
    ))

    cfg = _default_config()
    setup_provider_credentials(get_provider_definition(cfg))

    role = Prompt.ask("模型模式", choices=[MODE_ALL, MODE_RECOMMENDED], default=MODE_ALL)
    cfg = _default_config(role)
    save_config(cfg)
    console.print(f"\n[green]✓ 配置已保存到 {CONFIG_PATH}[/green]\n")
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
    for m in models:
        _, category = _infer_model_family(m)
        categorized.setdefault(category, []).append(m)
    return categorized


def display_models(models, role=MODE_ALL, recommend=None):
    categorized = categorize_models(models)
    table = Table(title="可用模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    table.add_column("分类", style="yellow")

    flat = []
    for cat, cat_models in categorized.items():
        for m in cat_models:
            flat.append((m, cat))

    if normalize_user_role(role) == MODE_RECOMMENDED and recommend:
        flat = [(m, c) for m, c in flat if m in recommend]

    for i, (m, c) in enumerate(flat, 1):
        tag = " ⭐" if recommend and m in recommend else ""
        table.add_row(str(i), m + tag, c)

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
    console.print("[yellow]当前没有可用的模型列表。请先修复 provider 校验，或先使用场景 / 预设启动。[/yellow]")
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
    # Kimi coding endpoints currently work on Claude-compatible paths, but not in Codex runtime.
    if cli_name == "codex" and provider_id.startswith("kimi"):
        return False
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    return cli_name in supported_clis


def _provider_candidates(cfg, default_provider, default_models):
    candidates = [(default_provider, list(default_models or []))]
    seen_ids = {default_provider.get("id")}
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id in seen_ids:
            continue
        # 首屏/启动阶段允许使用 stale 文件缓存，避免单个慢 provider 卡住 TUI。
        file_cached = _load_probe_file_cache(provider_id, allow_stale=True)
        cached_models = None if file_cached is None else list((file_cached or {}).get("raw_models") or [])
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
            base_models = []
            base_source = "remote"
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
        if not _provider_supports_cli_name(provider, cli_name):
            continue
        if not provider.get("base_url") or not provider.get("api_key"):
            continue
        models = _provider_effective_models(provider, cached_models, cfg)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or normalized in seen:
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
        if not _provider_supports_cli_name(provider, cli_name):
            continue
        if not provider.get("base_url") or not provider.get("api_key"):
            continue
        models = _provider_effective_models(provider, cached_models, cfg)
        pid = provider.get("id", DEFAULT_PROVIDER_ID)
        pname = _provider_label(provider)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            aggregated.append({
                "model": normalized,
                "provider_id": pid,
                "provider_name": pname,
            })
    return aggregated


def _resolve_best_provider(cfg, model_name, default_provider, default_models,
                           cli_name=None, protocol=None):
    """给定模型名，返回最优 (provider_ctx, provider_name) — primary > auto > fallback × priority desc。

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
        if cli_name and not _provider_supports_cli_name(provider, cli_name):
            continue
        if not provider.get("base_url") and not provider.get("openai_base_url") and not provider.get("anthropic_base_url"):
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
        priority = _normalize_priority(provider.get("priority", DEFAULT_PRIORITY))
        pname = _provider_label(provider)
        scored.append((ROLE_WEIGHTS.get(role, 1), -priority, provider, pname))

    if not scored:
        return None, None

    scored.sort(key=lambda x: (x[0], x[1]))
    return scored[0][2], scored[0][3]


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
        if not _provider_supports_cli_name(provider, cli_name):
            continue
        if not provider.get("base_url") and not provider.get("openai_base_url") and not provider.get("anthropic_base_url"):
            continue
        if not provider.get("api_key"):
            continue

        models = _provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue

        role = _normalize_role(provider.get("role", "auto"))
        priority = _normalize_priority(provider.get("priority", DEFAULT_PRIORITY))
        score = (ROLE_WEIGHTS.get(role, 1), -priority)
        pid = provider.get("id", DEFAULT_PROVIDER_ID)
        pname = _provider_label(provider)

        for m in models:
            normalized = str(m or "").strip()
            if not normalized:
                continue
            existing = model_best.get(normalized)
            if existing is None or score < existing[0]:
                model_best[normalized] = (score, provider, pname, pid)

    # 注入 use_count（用于 TUI 排序）
    use_counts = {}
    stats = _load_usage_stats()
    for src in stats.get("sources", {}).values():
        for mname, cnt in src.get("models", {}).items():
            use_counts[mname] = use_counts.get(mname, 0) + cnt

    # 按 family 分组
    family_map = {}  # family_name -> [model_entry]
    family_order = []

    for model_name, (_, provider_ctx, pname, pid) in model_best.items():
        family, _ = _infer_model_family(model_name)
        if family not in family_map:
            family_map[family] = []
            family_order.append(family)
        family_map[family].append({
            "model": model_name,
            "provider_id": pid,
            "provider_name": pname,
            "provider_ctx": provider_ctx,
            "use_count": use_counts.get(model_name, 0),
        })

    return [{"family": f, "models": family_map[f]} for f in family_order]


def _provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=None):
    selected_model = _resolve_model_name(model_info) if model_info else ""
    _probe_debug_logger.info("=== _provider_options_for_model(cli=%s, selected_model=%s) ===", cli_name, selected_model)
    options = []
    for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
        pid = provider.get("id", "?")
        if not provider.get("enabled", True):
            _probe_debug_logger.debug("  %s: SKIP (disabled)", pid)
            continue
        if not _provider_supports_cli_name(provider, cli_name):
            _probe_debug_logger.debug("  %s: SKIP (cli not supported)", pid)
            continue
        if not provider.get("base_url") or not provider.get("api_key"):
            _probe_debug_logger.debug("  %s: SKIP (no base_url=%s or api_key=%s)", pid, bool(provider.get("base_url")), bool(provider.get("api_key")))
            continue

        models = cached_models
        if models is None:
            _probe_debug_logger.debug("  %s: cached_models=None, schedule async refresh", pid)
            models = _provider_effective_models(provider, None, cfg)
        else:
            _probe_debug_logger.debug("  %s: cached_models=%s (len=%d)", pid, type(cached_models).__name__, len(cached_models))
        models = _provider_effective_models(provider, models, cfg)
        cli_models = _provider_models_for_cli(cli_name, models)

        if selected_model:
            if selected_model not in models:
                _probe_debug_logger.info("  %s: SKIP (model '%s' not in %s)", pid, selected_model, models[:5])
                continue
            option_models = [selected_model]
        else:
            option_models = cli_models

        if not option_models:
            _probe_debug_logger.info("  %s: SKIP (no option models for cli=%s)", pid, cli_name)
            continue

        _probe_debug_logger.info("  %s: ADDED (option_models=%s)", pid, option_models)
        options.append({
            "kind": "provider",
            "id": provider.get("id"),
            "runtime": provider,
            "models": option_models,
            "label": _runtime_choice_label(provider),
            "title": _provider_label(provider),
            "desc": "网关",
            "icon": "🌐",
            "priority": provider.get("priority", DEFAULT_PRIORITY),
            "is_default": provider.get("id") == default_provider.get("id"),
            "launch_cli": cli_name,
        })
    return options


def _account_options_for_model(cfg, cli_name, default_models, model_info=None, allow_selected_model=False):
    selected_model = _resolve_model_name(model_info) if model_info else ""
    options = []
    defaults = cfg.get("account", {}).get("defaults", {})

    for account_def in cfg.get("accounts", []):
        if not isinstance(account_def, dict) or not account_def.get("enabled", True):
            continue
        account_cli = account_def.get("cli")
        if account_cli not in OAUTH_CAPABLE_CLIS:
            continue
        bridgeable_to_claude = (
            bool(selected_model)
            and cli_name == "claude"
            and account_cli in {"codex", "gemini"}
        )
        if selected_model and not allow_selected_model and not bridgeable_to_claude:
            continue
        if selected_model and not _model_matches_account_cli(account_cli, selected_model):
            continue
        if not selected_model and account_cli != cli_name:
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
            "is_default": runtime.get("id") == defaults.get(account_cli),
            "launch_cli": launch_cli,
        })
    return options


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
    if cli_name in OAUTH_CAPABLE_CLIS:
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
    options.sort(key=lambda item: (
        item.get("priority", DEFAULT_PRIORITY),
        0 if item.get("launch_cli") == cli_name else 1,
        0 if item["kind"] == "provider" else 1,
        item.get("title", ""),
    ))
    default_choice = _resolve_source_default_index(options, cli_name)
    return options, default_choice


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
    if account_id or provider_id or cli_name not in OAUTH_CAPABLE_CLIS:
        runtime, models = _resolve_launch_runtime(
            cfg, cli_name, default_provider, default_models, account_id=account_id, provider_id=provider_id
        )
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
        return options[0]["runtime"], options[0]["models"], options[0].get("launch_cli", cli_name)

    if not sys.stdin.isatty():
        chosen = options[default_choice or 0]
        return chosen["runtime"], chosen["models"], chosen.get("launch_cli", cli_name)

    table = Table(title=f"{cli_name} 使用入口", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("来源", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("调用", style="cyan")
    table.add_column("说明", style="magenta")
    for idx, option in enumerate(options, 1):
        runtime = option["runtime"]
        source_type = "官方" if option["kind"] == "account" else "网关"
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
                return chosen["runtime"], chosen["models"], chosen.get("launch_cli", cli_name)
        console.print(f"[red]请输入 1-{len(options)} 的编号[/red]")


class _LazySourceChoices(dict):
    """惰性 source choices：key 首次被访问时才计算，避免预计算所有 scene/variant 的 provider 源。"""

    def __init__(self, cfg, scenes, cli_names, default_provider, default_models):
        super().__init__()
        self._cfg = cfg
        self._scenes = scenes
        self._cli_names = cli_names
        self._default_provider = default_provider
        self._default_models = default_models

    def _compute(self, key):
        # 解析 key = "cli_name|model_or___default__"
        parts = key.split("|", 1)
        cli_name = parts[0]
        model_key = parts[1] if len(parts) > 1 else "__default__"

        if model_key == "__default__":
            options, default_index = _list_runtime_sources(
                self._cfg, cli_name, self._default_provider, self._default_models)
        else:
            # 从 scenes 中找到对应的 model_info
            model_info = self._find_model_info(cli_name, key)
            options, default_index = _list_runtime_sources(
                self._cfg, cli_name, self._default_provider, self._default_models,
                model_info=model_info, allow_selected_model_accounts=True)
        result = {"options": options, "default_index": default_index or 0}
        self[key] = result
        return result

    def _find_model_info(self, cli_name, key):
        for scene in self._scenes.values():
            if scene.get("cli") != cli_name:
                continue
            if scene.get("variants"):
                for variant in scene["variants"]:
                    mi = dict(variant.get("model_info", {}))
                    if _source_choice_key(cli_name, mi) == key:
                        return mi
            else:
                mi = _scene_model_info(scene)
                if _source_choice_key(cli_name, mi) == key:
                    return mi
        return {}

    def get(self, key, default=None):
        if key in self:
            return super().__getitem__(key)
        try:
            return self._compute(key)
        except Exception:
            return default

    def __getitem__(self, key):
        if key not in self:
            return self._compute(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        return super().__contains__(key)


def _source_choices_for_tui(cfg, scenes, cli_names, default_provider, default_models):
    return _LazySourceChoices(cfg, scenes, cli_names, default_provider, default_models)


def _resolve_visible_clis(cfg, default_provider, default_models):
    visible = []

    for cli_name in CLI_NAMES:
        if cli_name in OAUTH_CAPABLE_CLIS and _accounts_for_cli(cfg, cli_name):
            visible.append(cli_name)
            continue
        provider, family_models = _resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)
        if provider is None:
            continue
        if cli_name in CLI_MODEL_FAMILY_HINTS and not family_models:
            continue
        visible.append(cli_name)

    return visible


def _filter_scenes_by_visible_clis(cli_names):
    visible = set(cli_names)
    return {
        name: scene for name, scene in SCENES.items()
        if scene.get("cli") in visible and scene.get("cli") not in DIRECT_CLI_MODES
    }


def _builtin_scene_catalog():
    return {
        name: scene for name, scene in SCENES.items()
        if scene.get("cli") not in DIRECT_CLI_MODES
    }


def select_model_interactive(models_list):
    while True:
        try:
            choice = IntPrompt.ask("选择模型编号")
            if 1 <= choice <= len(models_list):
                return models_list[choice - 1]
            console.print(f"[red]请输入 1-{len(models_list)}[/red]")
        except KeyboardInterrupt:
            sys.exit(0)


def _scene_model_info(scene):
    return {k: v for k, v in scene.items() if k not in SCENE_META_KEYS}


def _clean_model_info(model_info):
    if not isinstance(model_info, dict):
        return model_info
    return {k: v for k, v in model_info.items() if k != "provider"}


def _source_choice_key(cli_name, model_info=None):
    if not model_info:
        return f"{cli_name}|__default__"
    if isinstance(model_info, dict):
        cleaned = _clean_model_info(model_info)
        if not cleaned:
            return f"{cli_name}|__default__"
        payload = json.dumps(cleaned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return f"{cli_name}|{payload}"
    return f"{cli_name}|{str(model_info).strip()}"


def _tier_label(tier):
    return {
        "med": "中杯",
        "high": "大杯",
        "xhigh": "超大杯",
    }.get(tier, tier)


def _variant_line(variant):
    model = variant.get("model_info", {}).get("model", "")
    tier = _tier_label(variant.get("tier", ""))
    return f"{tier:<6}  {model}"


def _select_scene_model_info(scene_name, scene, use_tui=False):
    variants = scene.get("variants")
    if not variants:
        return _scene_model_info(scene)

    option_lines = [_variant_line(variant) for variant in variants]
    if use_tui:
        from mms_tui import select_model_tui
        selected = select_model_tui(option_lines, title=f"{scene_name}：选择档位")
        if selected is None:
            return None
        return dict(variants[option_lines.index(selected)]["model_info"])

    console.print(f"\n[bold]{scene_name}：选择档位[/bold]")
    for i, line in enumerate(option_lines, 1):
        console.print(f"  {i}. {line}")

    while True:
        try:
            choice = IntPrompt.ask("选择档位编号")
            if 1 <= choice <= len(variants):
                return dict(variants[choice - 1]["model_info"])
            console.print(f"[red]请输入 1-{len(variants)}[/red]")
        except KeyboardInterrupt:
            sys.exit(0)


# ── Scene Selection (fallback for non-TTY) ─────────────

def show_scenes(scenes):
    scene_list = list(scenes.keys())
    lines = []
    for i, name in enumerate(scene_list, 1):
        s = scenes[name]
        lines.append(f"  {i}. {s['emoji']} {name}  {s['desc']}")
    lines.append("  ─" * 20)
    lines.append(f"  {len(scene_list) + 1}. 🔧 自定义    手动选 CLI + 模型")

    console.print(Panel("\n".join(lines), title=f"{display_title()} — 选择场景"))
    return scene_list


def select_scene_fallback(scenes):
    """非 TTY 环境的 fallback：数字选择"""
    scene_list = show_scenes(scenes)
    total = len(scene_list) + 1
    while True:
        try:
            choice = IntPrompt.ask("选择场景编号")
            if 1 <= choice <= total:
                if choice == total:
                    return None  # custom
                return scene_list[choice - 1]
            console.print(f"[red]请输入 1-{total}[/red]")
        except KeyboardInterrupt:
            sys.exit(0)


# ── Confirmation ────────────────────────────────────────

def confirm_launch(cli, model_info, once=False, runtime=None):
    if isinstance(model_info, dict):
        model_items = [f"{k}={v}" for k, v in model_info.items() if k != "subagent" and v]
        model_display = ", ".join(model_items) if model_items else "官方默认"
    else:
        model_display = model_info or "官方默认"

    mode_str = "一次性命令" if once else "交互会话"
    env_str = "临时注入，仅当前 CLI 进程可见" if cli in ("claude", "codex", "kimi") else "无需额外注入"
    source_line = ""
    if runtime:
        source_kind = "官方" if runtime.get("auth_mode") == "oauth" else "网关"
        source_label = runtime.get("name", runtime.get("id", "default"))
        source_line = f"[bold]来源:[/bold]   {source_kind} / {source_label}\n"
    panel_text = (
        f"[bold]CLI:[/bold]    {cli}\n"
        f"[bold]模型:[/bold]   {model_display}\n"
        f"{source_line}"
        f"[bold]启动:[/bold]   {mode_str}\n"
        f"[bold]环境:[/bold]   {env_str}\n"
        f"\n"
        f"[dim]Enter=启动  S=保存为预设  Q=取消[/dim]"
    )
    console.print(Panel(panel_text, title="确认启动", border_style="green"))

    choice = Prompt.ask("操作", choices=["", "s", "q"], default="")
    return choice


def save_preset_interactive(cfg, cli, model_info):
    name = Prompt.ask("预设名称")
    preset = {"cli": cli}
    if isinstance(model_info, dict):
        preset.update(model_info)
    else:
        preset["model"] = model_info
    if "presets" not in cfg:
        cfg["presets"] = {}
    cfg["presets"][name] = preset
    save_config(cfg)
    console.print(f"[green]✓ 预设 '{name}' 已保存[/green]")


def _uses_native_account_entry(runtime, cli):
    return bool(runtime and runtime.get("auth_mode") == "oauth" and cli in OAUTH_CAPABLE_CLIS)


# ── CLI Selection (fallback) ───────────────────────────

def check_cli_installed(cli_name):
    from shutil import which
    return which(cli_name) is not None


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


def _build_provider_options_map(cfg, cli_name, default_provider, default_models, model_names):
    """为一组模型名构建 provider 替代选项映射（供 P 键使用）。

    Returns:
        dict[str, list[dict]] — model_name -> [{"provider_name", "provider_id", "provider_ctx"}]
    """
    result = {}
    for model_name in model_names:
        options = []
        for provider, cached_models in _provider_candidates(cfg, default_provider, default_models):
            if not provider.get("enabled", True):
                continue
            if not _provider_supports_cli_name(provider, cli_name):
                continue
            if not provider.get("base_url") and not provider.get("openai_base_url") and not provider.get("anthropic_base_url"):
                continue
            if not provider.get("api_key"):
                continue
            models = _provider_effective_models(provider, cached_models, cfg)
            model_lower = [str(m or "").strip().lower() for m in models]
            if model_name.strip().lower() not in model_lower:
                continue
            options.append({
                "provider_name": _provider_label(provider),
                "provider_id": provider.get("id", DEFAULT_PROVIDER_ID),
                "provider_ctx": provider,
            })
        if len(options) > 1:
            result[model_name] = options
    return result


def _handle_tui_scene_selection(cfg, scenes, provider, once, cli_names, account_id=None, provider_id=None):
    """TUI 交互：品类 → 子模型 → 确认。返回 True 表示已处理，False 表示 fallback"""
    from mms_tui import select_family_tui, select_submodel_tui, confirm_tui
    from mms_tui import select_load_balance_tui, save_lb_history
    from mms_launchers import launch_cli, get_export_env

    def _safe_tui_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            return "__interrupt__"

    current_cfg = cfg
    current_provider = provider
    current_cli_names = cli_names
    default_models = _probe_models(current_provider, emit_output=False).get("models")

    # 预构建品类数据（仅在配置变更时重建）
    def _rebuild_families():
        fbc = {}
        fd = {}
        for cli_name in current_cli_names:
            raw = _build_model_families_for_cli(
                current_cfg, cli_name, current_provider, default_models
            )
            fam_list = []
            for f in raw:
                total_use = sum(m.get("use_count", 0) for m in f["models"] if isinstance(m, dict))
                fam_list.append({"family": f["family"], "count": len(f["models"]), "use_count": total_use})
            # 按使用量降序排列（用的多的在前）
            fam_list.sort(key=lambda x: x.get("use_count", 0), reverse=True)
            fbc[cli_name] = fam_list
            fd[cli_name] = {f["family"]: f["models"] for f in raw}
        return fbc, fd

    families_by_cli, families_detail = _rebuild_families()
    _families_dirty = False

    while True:
        if _families_dirty:
            families_by_cli, families_detail = _rebuild_families()
            _families_dirty = False

        # 获取上次使用信息（按 CLI 分桶，TUI 内部按当前 tab 过滤）
        last_by_cli, _ = _get_scene_usage()

        result = _safe_tui_call(select_family_tui, families_by_cli, current_cli_names, last_used=last_by_cli, families_detail=families_detail)

        if result == "fallback":
            return False
        if result == "__interrupt__":
            return True
        if result is None:
            return True

        action_type, cli, action_data = result

        # ── 接入通道 ──
        if action_type == "connect":
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
            file_cached = _load_probe_file_cache(selected_pid, allow_stale=True)
            cached_models = None if file_cached is None else list((file_cached or {}).get("raw_models") or [])
            prov_models = _provider_effective_models(selected_prov, cached_models, current_cfg)
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
            # fall through to confirm

        # ── 负载模式 ──
        if action_type == "load_balance":
            all_models = []
            cli_families = families_detail.get(cli, {})
            for fam_models in cli_families.values():
                all_models.extend(m["model"] for m in fam_models)
            lb_prov_opts = _build_provider_options_map(
                current_cfg, cli, current_provider, default_models, all_models
            ) if all_models else None
            lb_result = _safe_tui_call(
                select_load_balance_tui,
                available_models=all_models or None,
                families_detail=cli_families,
                provider_options_map=lb_prov_opts,
            )
            if lb_result == "__interrupt__":
                return True
            if lb_result is None:
                continue
            model_info = dict(lb_result)
            save_lb_history(lb_result["model"], lb_result.get("lb_medium", ""), lb_result.get("lb_light", ""))
            # 用 heavy model 的 best provider 作为 runtime
            runtime_runtime, _ = _resolve_best_provider(
                current_cfg, lb_result["model"], current_provider, default_models, cli_name=cli
            )
            if runtime_runtime is None:
                runtime_runtime, _, cli = _choose_runtime_source(
                    current_cfg, cli, current_provider, default_models,
                    account_id=account_id, provider_id=provider_id,
                    model_info=model_info, allow_selected_model_accounts=True,
                )
            if runtime_runtime is None:
                console.print(f"[yellow]{cli} 没有可用 provider 承载负载模式[/yellow]")
                continue

            # 构建跨 provider slot_configs：为 medium/light 找各自的最优 provider
            slot_configs = {}
            for slot_name, slot_model in [("medium", lb_result.get("lb_medium")),
                                          ("light", lb_result.get("lb_light"))]:
                if not slot_model or not slot_model.strip():
                    continue
                slot_prov, _ = _resolve_best_provider(
                    current_cfg, slot_model, current_provider, default_models, cli_name=cli
                )
                if slot_prov and slot_prov.get("id") != runtime_runtime.get("id"):
                    # 不同 provider：记录独立 url/key
                    slot_url = (slot_prov.get("anthropic_base_url") or
                                slot_prov.get("base_url") or
                                slot_prov.get("openai_base_url") or "")
                    if slot_url:
                        slot_url = slot_url.rstrip("/")
                        if not slot_url.endswith("/v1"):
                            slot_url += "/v1"
                        slot_configs[slot_name] = {
                            "url": slot_url,
                            "key": slot_prov.get("api_key", ""),
                        }
            if slot_configs:
                model_info["lb_slot_configs"] = slot_configs
            # fall through to confirm below

        # ── 设置 ──
        elif action_type == "settings":
            from mms_tui import select_settings_tui, select_provider_mgmt_tui
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
            elif settings_action == "routes_export":
                try:
                    from mms_router import export_model_routes
                    path = export_model_routes(current_cfg, force=True)
                    if path:
                        console.print(f"[green]✓ 已导出 {path}[/green]")
                except Exception as e:
                    console.print(f"[red]导出失败: {e}[/red]")
            elif settings_action == "about":
                console.print(f"[cyan]{display_title()}[/cyan]")
                console.print(f"[dim]Config: {CONFIG_PATH}[/dim]")
            elif settings_action == "account_mgmt":
                console.print("[dim]账号管理尚未完全实现[/dim]")
            elif settings_action == "recommend":
                console.print("[dim]推荐模型管理尚未完全实现[/dim]")
            continue

        # ── 上次使用 ──
        elif action_type == "last":
            model_info = {"model": action_data["model"]}
            runtime_runtime, _ = _resolve_best_provider(
                current_cfg, action_data["model"], current_provider, default_models, cli_name=cli
            )
            if runtime_runtime is None:
                runtime_runtime, _, cli = _choose_runtime_source(
                    current_cfg, cli, current_provider, default_models,
                    account_id=account_id, provider_id=provider_id,
                    model_info=model_info, allow_selected_model_accounts=True,
                )
            if runtime_runtime is None:
                console.print(f"[yellow]{cli} 没有可用 provider[/yellow]")
                continue
            # fall through to confirm

        # ── 品类选择 → 子模型 ──
        elif action_type == "family":
            family_name = action_data
            models = families_detail.get(cli, {}).get(family_name, [])
            if not models:
                console.print(f"[yellow]{family_name} 下没有可用模型[/yellow]")
                continue

            # 构建 P 键 provider 替代选项
            model_names = [m["model"] for m in models]
            provider_options = _build_provider_options_map(
                current_cfg, cli, current_provider, default_models, model_names
            )

            selected = _safe_tui_call(select_submodel_tui, family_name, models, provider_options=provider_options)
            if selected == "__interrupt__":
                return True
            if selected is None:
                continue  # Esc 返回品类列表

            # 持久化 priority 变更
            pri_changes = selected.pop("priority_changes", None)
            if pri_changes:
                for pid, new_pri in pri_changes.items():
                    for pdef in current_cfg.get("providers", []):
                        if pdef.get("id") == pid:
                            pdef["priority"] = new_pri
                            break
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
            if runtime_runtime is None:
                runtime_runtime, _ = _resolve_best_provider(
                    current_cfg, selected["model"], current_provider, default_models, cli_name=cli
                )
            if runtime_runtime is None:
                console.print(f"[yellow]没有可用 provider 承载 {selected['model']}[/yellow]")
                continue
            # fall through to confirm
        elif action_type not in ("provider_browse", "load_balance", "last", "family"):
            continue

        # ── 公共：确认页 + 启动 ──
        if not check_cli_installed(cli):
            from mms_installer import check_and_offer_install
            if not check_and_offer_install(cli):
                return True

        clean_model_info = _clean_model_info(model_info)
        env_vars = get_export_env(cli, runtime_runtime)
        result = _safe_tui_call(confirm_tui, cli, clean_model_info, env_vars=env_vars, once=once)
        if result == "__interrupt__":
            return True
        action, bypass = result if isinstance(result, tuple) else (result, False)
        if action == "q":
            return True
        if action == "b":
            continue
        if bypass:
            runtime_runtime["bypass"] = True
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

    lines = [f'export {k}="{v}"' for k, v in exports.items()]
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
    console.print(f"[green]✓ 已更新模型源: {provider_id}[/green]")


def _handle_provider_remove_config(cfg, args_rest):
    if not args_rest:
        console.print(f"[red]用法: {current_command()} config provider.remove <id>[/red]")
        return
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


def _handle_account_default_config(cfg, args_rest):
    defaults = cfg.get("account", {}).get("defaults", {})
    if not args_rest:
        for cli_name in OAUTH_CAPABLE_CLIS:
            value = defaults.get(cli_name, "(未设置)")
            console.print(f"[cyan]account.default.{cli_name}[/cyan] = {value}")
        return
    if len(args_rest) < 2:
        console.print(f"[red]用法: {current_command()} config account.default <cli> <account_id>[/red]")
        return
    cli_name, account_id = args_rest[0].strip(), args_rest[1].strip()
    if cli_name not in OAUTH_CAPABLE_CLIS:
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
    preset_cli = args_rest[0].strip() if args_rest and args_rest[0].strip() in OAUTH_CAPABLE_CLIS else None
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
    _run_account_login(account)


def _usage_key(runtime_kind, cli_name, runtime_id):
    return f"{runtime_kind}:{cli_name}:{runtime_id}"


def _rename_usage_account(old_id, new_id, new_name, cli_name):
    usage_path = _active_usage_path()
    if not os.path.exists(usage_path):
        return False
    stats = _load_usage_stats()
    sources = stats.get("sources", {})
    old_key = _usage_key("account", cli_name, old_id)
    entry = sources.pop(old_key, None)
    if entry is None:
        return False
    entry["id"] = new_id
    entry["name"] = new_name
    sources[_usage_key("account", cli_name, new_id)] = entry
    _save_usage_stats(stats)
    return True


def _rename_usage_provider(old_id, new_id, new_name):
    usage_path = _active_usage_path()
    if not os.path.exists(usage_path):
        return False
    stats = _load_usage_stats()
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
    if not changed:
        return False
    _save_usage_stats(stats)
    return True


def _target_account_home(old_home, new_id):
    expanded = os.path.expanduser(str(old_home or "").strip())
    if not expanded:
        return _default_account_home(new_id)
    known_roots = {
        os.path.realpath(ACCOUNTS_DIR),
        os.path.realpath(os.path.join(LEGACY_CONFIG_DIR, "accounts")),
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
    legacy_accounts_dir = os.path.join(LEGACY_CONFIG_DIR, "accounts")
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

    if os.path.isdir(legacy_accounts_dir):
        for leftover in os.listdir(legacy_accounts_dir):
            source = os.path.join(legacy_accounts_dir, leftover)
            target = os.path.join(ACCOUNTS_DIR, leftover)
            if os.path.isdir(source) and not os.path.exists(target):
                os.makedirs(ACCOUNTS_DIR, exist_ok=True)
                shutil.move(source, target)
                changed = True
    return updated_accounts, changed


def _copy_if_missing(source, target):
    if not os.path.exists(source) or os.path.exists(target):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    return True


def _handle_config_migrate():
    backup_dir = _backup_config_tree("config-migrate")
    copied = []
    if _copy_if_missing(LEGACY_CREDENTIALS_PATH, CREDENTIALS_PATH):
        copied.append(CREDENTIALS_PATH)
    if _copy_if_missing(LEGACY_USAGE_PATH, USAGE_PATH):
        copied.append(USAGE_PATH)

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
    if copied:
        console.print(f"[dim]复制的文件: {copied}[/dim]")
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


def _display_config_help():
    command = current_command()
    console.print(f"[bold]{command} config[/bold] — 配置查看与管理")
    console.print(f"[dim]用法: {command} config [子命令] [参数][/dim]")
    console.print("\n[bold]常用子命令:[/bold]")
    console.print(f"  {command} config")
    console.print(f"  {command} config file")
    console.print(f"  {command} config validate")
    console.print(f"  {command} config get <dot.path>")
    console.print(f"  {command} config set <dot.path> <value>")
    console.print(f"  {command} config unset <dot.path>")
    console.print(f"  {command} config connect")
    console.print(f"  [dim]可调参数示例: cache.probe_async_refresh_after_sec / cache.probe_async_min_interval_sec[/dim]")
    console.print("\n[bold]Provider:[/bold]")
    console.print(f"  {command} config provider.list")
    console.print(f"  {command} config provider.default [id]")
    console.print(f"  {command} config provider.add [id]")
    console.print(f"  {command} config provider.edit <id>")
    console.print(f"  {command} config provider.remove <id>")
    console.print(f"  {command} config provider.credentials [id]")
    console.print("\n[bold]Account:[/bold]")
    console.print(f"  {command} config account.list")
    console.print(f"  {command} config account.add [claude|codex]")
    console.print(f"  {command} config account.edit <id>")
    console.print(f"  {command} config account.remove <id>")
    console.print(f"  {command} config account.status [id]")
    console.print(f"  {command} config account.login <id>")
    console.print(f"  {command} config account.default <cli> <id>")
    console.print("\n[bold]其他:[/bold]")
    console.print(f"  {command} config stats")
    console.print(f"  {command} config api.edit")



def _display_config(cfg, prefix="", depth=0):
    """递归显示配置，遮蔽敏感值"""
    if depth == 0:
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

    for k, v in cfg.items():
        if depth == 0 and k in {"providers", "provider", "accounts", "account"}:
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
    if key_path == "provider.default":
        return str(raw_value).strip()
    if key_path in {"cache.probe_async_refresh_after_sec", "cache.probe_async_min_interval_sec"}:
        return _normalize_positive_seconds(raw_value, 1)
    if key_path.startswith("provider.") and key_path.endswith(".enabled"):
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    return raw_value


def _validate_config(cfg):
    errors = []
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
            invalid_clis = [value for value in supported_clis if value not in CLI_NAMES]
            if invalid_clis:
                errors.append(f"模型源 {provider_id} 存在不支持的 CLI: {', '.join(invalid_clis)}")
            if _normalize_priority(item.get("priority", DEFAULT_PRIORITY)) != item.get("priority", DEFAULT_PRIORITY):
                errors.append(f"模型源 {provider_id} 的 priority 必须是正整数")
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
    updated_cfg, _ = _ensure_provider_config(updated_cfg)
    updated_cfg, _ = _ensure_account_config(updated_cfg)
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
    updated_cfg, _ = _ensure_provider_config(updated_cfg)
    updated_cfg, _ = _ensure_account_config(updated_cfg)
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

def _load_command_config():
    cfg = load_config()
    if cfg is None:
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


def handle_session_command(argv):
    parser = argparse.ArgumentParser(
        prog=f"{current_command()} session",
        description="查看 MMS 托管的 CLI session 元数据",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    ls_parser = subparsers.add_parser("ls", help="列出已索引 session")
    ls_parser.add_argument("--cli", default="claude", choices=["claude"])

    info_parser = subparsers.add_parser("info", help="查看单个 session 详情")
    info_parser.add_argument("session_id", help="session_id 或 pid-<pid>")
    info_parser.add_argument("--cli", default="claude", choices=["claude"])

    args = parser.parse_args(argv)
    if args.subcommand == "ls":
        _handle_session_ls(args.cli)
        return
    if args.subcommand == "info":
        _handle_session_info(args.session_id, args.cli)
        return

    parser.print_help()


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


def handle_test_command(argv, subcommand_name="test"):
    return _run_script_subcommand("smoke_cli_channels.py", argv, subcommand_name)


def main():
    if len(sys.argv) >= 2:
        command = sys.argv[1]
        if command == "config":
            cfg = load_config()
            if cfg is None:
                cfg = _default_config()
                save_config(cfg)
            handle_config(cfg, sys.argv[2:])
            return
        if command == "chat":
            from mms_chat import chat_main

            chat_main(_load_command_config(), sys.argv[2:])
            return
        if command == "discuss":
            from mms_discuss import discuss_main

            discuss_main(_load_command_config(), sys.argv[2:])
            return
        if command == "usage":
            from mms_usage import usage_main

            usage_main(_load_command_config(), sys.argv[2:])
            return
        if command in {"models", "ls"}:
            handle_models_command(_load_command_config(), sys.argv[2:])
            return
        if command == "warm":
            handle_warm_command(_load_command_config(), sys.argv[2:])
            return
        if command == "session":
            handle_session_command(sys.argv[2:])
            return
        if command == "cache":
            handle_cache_command(sys.argv[2:])
            return
        if command == "routes":
            from mms_router import routes_main

            routes_main(_load_command_config(), sys.argv[2:])
            return
        if command == "doctor":
            raise SystemExit(handle_doctor_command(sys.argv[2:]))
        if command in {"test", "smoke"}:
            raise SystemExit(handle_test_command(sys.argv[2:], subcommand_name=command))

    if len(sys.argv) >= 2 and sys.argv[1] == "discuss":
        from mms_discuss import discuss_main

        cfg = load_config()
        if cfg is None:
            cfg = _default_config()
            save_config(cfg)
        cfg = apply_local_overrides(cfg)
        discuss_main(cfg, sys.argv[2:])
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
            f"  {current_command()} routes ...      查看路由配置\n"
            f"  {current_command()} doctor ...      诊断 provider / model / Claude 兼容性\n"
            f"  {current_command()} test ...        最小闭环 smoke 测试 channel URL + key + bridge\n"
            f"  {current_command()} smoke ...       等同于 test\n"
            f"  {current_command()} chat ...        进入 chat 子命令\n"
            f"  {current_command()} discuss ...     进入 discuss 子命令\n"
            f"  {current_command()} usage ...       查看 usage 统计"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="场景编号(1-6) 或 CLI 名称(claude/codex/qwen/kimi/gemini)")
    parser.add_argument("--preset", help="使用指定预设直接启动")
    parser.add_argument("--once", nargs="?", const=True, default=False,
                        help="一次性会话模式（可附带场景编号）")
    parser.add_argument("--list", action="store_true", help="列出 API 可用模型")
    parser.add_argument("--presets", action="store_true", help="列出已保存预设和场景")
    parser.add_argument("--install", metavar="CLI", help="安装指定 CLI")
    parser.add_argument("--custom", action="store_true", help="强制手动选 CLI + 模型模式")
    parser.add_argument("--export", nargs="?", const="claude", metavar="CLI",
                        help="输出指定 CLI 的 export 环境变量命令")
    parser.add_argument("--apply", action="store_true",
                        help="配合 --export 使用，写入 ~/.config/mms/env/<cli>.sh")
    parser.add_argument("--account", help="临时使用指定官方账号档案启动")
    parser.add_argument("--provider", help="临时使用指定模型源启动")

    args = parser.parse_args()

    if args.account and args.provider:
        console.print("[red]--account 和 --provider 不能同时使用[/red]")
        sys.exit(1)

    # --install
    if args.install:
        from mms_installer import install_cli
        install_cli(args.install)
        return

    # Load or create config
    user_cfg = load_config()
    if user_cfg is None:
        user_cfg = setup_wizard()

    cfg = apply_local_overrides(user_cfg)

    default_provider = ensure_provider_credentials(cfg)
    role = normalize_user_role(cfg.get("user", {}).get("role", MODE_ALL))
    recommend = cfg.get("recommend", {}).get("models", [])

    from mms_launchers import launch_cli

    # --presets
    if args.presets:
        presets = cfg.get("presets", {})
        if presets:
            table = Table(title="已保存预设")
            table.add_column("名称", style="cyan")
            table.add_column("CLI", style="green")
            table.add_column("Provider", style="magenta")
            table.add_column("模型", style="yellow")
            for name, p in presets.items():
                model_str = p.get("model", f"opus={p.get('opus','')}, sonnet={p.get('sonnet','')}")
                table.add_row(name, p.get("cli", "?"), p.get("provider", DEFAULT_PROVIDER_ID), str(model_str))
            console.print(table)
        console.print("\n[bold]内置场景:[/bold]")
        for i, (name, s) in enumerate(_builtin_scene_catalog().items(), 1):
            console.print(f"  {i}. {s['emoji']} {name} — {s['desc']}")
        return

    # --export
    if args.export is not None:
        handle_export(args.export, default_provider, apply=args.apply)
        return

    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    _warm_probe_cache_async(cfg, default_provider)
    visible_clis = _resolve_visible_clis(cfg, default_provider, models_cache)
    visible_scenes = _filter_scenes_by_visible_clis(visible_clis)

    # --list
    if args.list:
        if not _ensure_models_cache_available(models_cache):
            return
        display_models(models_cache, role, recommend)
        return

    # --preset
    if args.preset:
        presets = cfg.get("presets", {})
        if args.preset not in presets:
            console.print(f"[red]预设 '{args.preset}' 不存在[/red]")
            console.print(f"可用预设: {', '.join(presets.keys())}")
            return
        p = presets[args.preset]
        cli = p["cli"]
        model_info = {k: v for k, v in p.items() if k not in {"cli", "provider"}}
        runtime, _, cli = _choose_runtime_source(
            cfg,
            cli,
            ensure_provider_credentials(cfg, p.get("provider")),
            models_cache,
            account_id=args.account,
            provider_id=args.provider,
            model_info=model_info,
            allow_selected_model_accounts=True,
        )
        once = bool(args.once)
        if runtime is None:
            console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
            return
        _launch_with_tracking(cli, model_info, runtime, once=once)
        return

    # Determine once mode
    once = bool(args.once)
    once_target = args.once if isinstance(args.once, str) and args.once is not True else None

    # Direct target
    target = once_target or args.target

    if target:
        # Is it a scene number?
        scene_list = list(visible_scenes.keys())
        try:
            idx = int(target)
            if 1 <= idx <= len(scene_list):
                scene_name = scene_list[idx - 1]
                scene = visible_scenes[scene_name]
                cli = scene["cli"]
                model_info = _select_scene_model_info(scene_name, scene, use_tui=False)
                runtime, _, cli = _choose_runtime_source(
                    cfg,
                    cli,
                    default_provider,
                    models_cache,
                    account_id=args.account,
                    provider_id=args.provider,
                    model_info=model_info,
                    allow_selected_model_accounts=True,
                )
                if runtime is None:
                    console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                    return
                if not check_cli_installed(cli):
                    from mms_installer import check_and_offer_install
                    if not check_and_offer_install(cli):
                        return
                console.print(f"[cyan]场景: {scene['emoji']} {scene_name}[/cyan]")
                action = confirm_launch(cli, model_info, once, runtime=runtime)
                if action == "q":
                    return
                if action == "s":
                    save_preset_interactive(user_cfg, cli, model_info)
                _launch_with_tracking(cli, _clean_model_info(model_info), runtime, once=once)
                return
        except ValueError:
            pass

        # Is it a CLI name?
        if target in visible_clis:
            cli = target
            runtime, cli_models, cli = _choose_runtime_source(
                cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=args.provider
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            if not check_cli_installed(cli):
                from mms_installer import check_and_offer_install
                check_and_offer_install(cli)
            if _uses_native_account_entry(runtime, cli):
                console.print(f"[cyan]{cli} 当前使用账号档案登录，直接进入官方 CLI；模型选择交由官方 CLI 处理。[/cyan]")
                model = None
            elif cli == "kimi":
                model = DEFAULT_KIMI_MODEL
            else:
                if not _ensure_models_cache_available(cli_models or models_cache):
                    return
                base_models = cli_models if cli == "qwen" else (cli_models or models_cache)
                models_list = display_models(base_models, role, recommend if cli != "qwen" else None)
                model = select_model_interactive(models_list)
            model_info = {} if _uses_native_account_entry(runtime, cli) else model
            action = confirm_launch(cli, model_info, once, runtime=runtime)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model_info)
            _launch_with_tracking(cli, {} if _uses_native_account_entry(runtime, cli) else {"model": model}, runtime, once=once)
            return
        if target in OAUTH_CAPABLE_CLIS and _accounts_for_cli(cfg, target):
            cli = target
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
            if _uses_native_account_entry(runtime, cli):
                console.print(f"[cyan]{cli} 当前使用账号档案登录，直接进入官方 CLI；模型选择交由官方 CLI 自己处理。[/cyan]")
                model = None
            else:
                if not _ensure_models_cache_available(cli_models or models_cache):
                    return
                models_list = display_models(cli_models or models_cache, role, recommend)
                model = select_model_interactive(models_list)
            model_info = {} if _uses_native_account_entry(runtime, cli) else model
            action = confirm_launch(cli, model_info, once, runtime=runtime)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model_info)
            _launch_with_tracking(cli, {} if _uses_native_account_entry(runtime, cli) else {"model": model}, runtime, once=once)
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
        if cli == "kimi":
            runtime, cli_models, cli = _choose_runtime_source(
                cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=args.provider
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            model = DEFAULT_KIMI_MODEL
        else:
            aggregated = _aggregate_provider_models(cfg, cli, default_provider, models_cache)
            if not _ensure_models_cache_available(aggregated):
                return
            model, custom_provider_id = _select_custom_model(
                aggregated,
                cli,
                role=role,
                recommend=recommend if cli != "qwen" else None,
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
        model_info = model
        action = confirm_launch(cli, model_info, once, runtime=runtime)
        if action == "q":
            return
        if action == "s":
            save_preset_interactive(user_cfg, cli, model_info)
        _launch_with_tracking(cli, {"model": model}, runtime, once=once)
        return

    # Default: TUI scene selection (with fallback)
    if _use_tui():
        handled = _handle_tui_scene_selection(
            cfg, visible_scenes, default_provider, once, visible_clis, account_id=args.account, provider_id=args.provider
        )
        if handled:
            return
        # fallback if curses failed

    # Fallback: number-based selection
    scene_name = select_scene_fallback(visible_scenes)

    if scene_name is None:
        # Custom mode
        cli = select_cli(visible_clis)
        if cli == "kimi":
            runtime, cli_models, cli = _choose_runtime_source(
                cfg, cli, default_provider, models_cache, account_id=args.account, provider_id=args.provider
            )
            if runtime is None:
                console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
                return
            model = DEFAULT_KIMI_MODEL
        else:
            aggregated = _aggregate_provider_models(cfg, cli, default_provider, models_cache)
            if not _ensure_models_cache_available(aggregated):
                return
            model, custom_provider_id = _select_custom_model(
                aggregated,
                cli,
                role=role,
                recommend=recommend if cli != "qwen" else None,
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
        model_info = model
        action = confirm_launch(cli, model_info, once, runtime=runtime)
        if action == "q":
            return
        if action == "s":
            save_preset_interactive(user_cfg, cli, model_info)
        _launch_with_tracking(cli, {"model": model}, runtime, once=once)
        return

    scene = visible_scenes[scene_name]
    cli = scene["cli"]
    model_info = _select_scene_model_info(scene_name, scene, use_tui=False)
    runtime, _, cli = _choose_runtime_source(
        cfg,
        cli,
        default_provider,
        models_cache,
        account_id=args.account,
        provider_id=args.provider,
        model_info=model_info,
        allow_selected_model_accounts=True,
    )
    if runtime is None:
        console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
        return

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
