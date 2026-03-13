"""MMS/CCS 核心逻辑：交互选择、模型拉取、分类、预设管理"""

import sys
import os
import argparse
import shlex

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None

try:
    import httpx
except ImportError:
    httpx = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, IntPrompt, Confirm
    from rich.text import Text
except ImportError:
    print("缺少依赖，请执行: pip install rich httpx tomli-w")
    sys.exit(1)

console = Console()

APP_NAME = "Multi-Model Switch"
LEGACY_COMMAND = "ccs"
PRIMARY_COMMAND = "mms"

CONFIG_DIR = os.path.expanduser("~/.config/ccs")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
CREDENTIALS_PATH = os.path.join(CONFIG_DIR, "credentials.sh")
ENV_DIR = os.path.join(CONFIG_DIR, "env")
OVERRIDE_PATHS = [
    os.path.join(CONFIG_DIR, "override.toml"),
    os.path.expanduser("~/.config/mms/override.toml"),
]
DEFAULT_BASE_URL = "https://your-api.example.com"
API_URL_ENV_NAME = "CCS_API_BASE_URL"
API_KEY_ENV_NAME = "CCS_API_KEY"
DEFAULT_PROVIDER_ID = "default"
DEFAULT_PROVIDER_PROTOCOLS = ["anthropic_messages", "openai_chat_completions"]
MODE_ALL = "全部模型"
MODE_RECOMMENDED = "推荐模型"

CATEGORIES = {
    "Claude 系 ⭐": ["claude-"],
    "GPT 系": ["gpt-", "o1-", "o3-", "o4-", "codex-"],
    "国产系": ["qwen", "glm-", "deepseek-", "kimi-", "minimax", "MiniMax"],
    "Google 系": ["gemini-"],
}

SCENES = {
    "常规任务": {
        "emoji": "⚡",
        "desc": "简单问答、日常杂活",
        "cli": "qwen",
        "default_tier": "high",
        "variants": [
            {
                "tier": "med",
                "name": "Qwen",
                "desc": "轻量",
                "model_info": {"model": "qwen3.5-plus"},
            },
            {
                "tier": "high",
                "name": "Qwen Max",
                "desc": "默认",
                "model_info": {"model": "qwen3-max-2026-01-23"},
            },
            {
                "tier": "xhigh",
                "name": "GLM",
                "desc": "备用",
                "model_info": {"model": "glm-5"},
            },
        ],
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
        "default_tier": "med",
        "variants": [
            {
                "tier": "med",
                "name": "Kimi",
                "desc": "默认中文",
                "model_info": {"model": "kimi-k2.5"},
            },
            {
                "tier": "high",
                "name": "MiniMax",
                "desc": "更稳一点",
                "model_info": {"model": "MiniMax-M2.5"},
            },
        ],
    },
    "英文主力": {
        "emoji": "🇺🇸",
        "desc": "英文内容、海外业务",
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

CLI_NAMES = ["claude", "codex", "qwen", "kimi"]
SCENE_META_KEYS = {"emoji", "desc", "cli", "variants", "default_tier"}


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


def _default_provider():
    return {
        "id": DEFAULT_PROVIDER_ID,
        "name": "Default Gateway",
        "protocols": list(DEFAULT_PROVIDER_PROTOCOLS),
        "supported_clis": list(CLI_NAMES),
        "enabled": True,
    }


def _sanitize_provider_id(provider_id):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id).upper())
    cleaned = cleaned.strip("_")
    return cleaned or DEFAULT_PROVIDER_ID.upper()


def _provider_env_name(provider_id, field):
    return f"CCS_PROVIDER_{_sanitize_provider_id(provider_id)}_{field}"


def _normalize_provider(provider):
    merged = dict(_default_provider())
    merged.update(provider)
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


def _provider_map(cfg):
    providers = cfg.get("providers", [])
    return {provider["id"]: provider for provider in providers if isinstance(provider, dict) and provider.get("id")}


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


# ── Config ──────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)
    cfg = _migrate_legacy_api_config(cfg)
    cfg, changed = _ensure_provider_config(cfg)
    cfg, role_changed = _normalize_user_config(cfg)
    changed = changed or role_changed
    if changed:
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


def load_provider_credentials(provider_id=DEFAULT_PROVIDER_ID):
    base_key = _provider_env_name(provider_id, "BASE_URL")
    api_key_name = _provider_env_name(provider_id, "API_KEY")
    base_url = os.environ.get(base_key, "").strip()
    api_key = os.environ.get(api_key_name, "").strip()

    if provider_id == DEFAULT_PROVIDER_ID:
        base_url = base_url or os.environ.get(API_URL_ENV_NAME, "").strip()
        api_key = api_key or os.environ.get(API_KEY_ENV_NAME, "").strip()

    if os.path.exists(CREDENTIALS_PATH):
        file_values = _load_env_file(CREDENTIALS_PATH)
        base_url = base_url or file_values.get(base_key, "").strip()
        api_key = api_key or file_values.get(api_key_name, "").strip()
        if provider_id == DEFAULT_PROVIDER_ID:
            base_url = base_url or file_values.get(API_URL_ENV_NAME, "").strip()
            api_key = api_key or file_values.get(API_KEY_ENV_NAME, "").strip()

    if provider_id == DEFAULT_PROVIDER_ID and (not base_url or not api_key) and os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "rb") as f:
            legacy_cfg = tomllib.load(f)
        legacy_api = legacy_cfg.get("api", {})
        if isinstance(legacy_api, dict):
            base_url = base_url or str(legacy_api.get("base_url", "")).strip()
            api_key = api_key or str(legacy_api.get("api_key", "")).strip()

    return (base_url.rstrip("/") if base_url else "", api_key)


def save_provider_credentials(provider_id, base_url, api_key):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    values = _load_env_file(CREDENTIALS_PATH) if os.path.exists(CREDENTIALS_PATH) else {}
    base_url = base_url.rstrip("/")
    values[_provider_env_name(provider_id, "BASE_URL")] = base_url
    values[_provider_env_name(provider_id, "API_KEY")] = api_key

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
    return load_provider_credentials(DEFAULT_PROVIDER_ID)


def save_api_credentials(base_url, api_key):
    save_provider_credentials(DEFAULT_PROVIDER_ID, base_url, api_key)


def resolve_provider_context(cfg, provider_id=None):
    provider = dict(get_provider_definition(cfg, provider_id))
    base_url, api_key = load_provider_credentials(provider["id"])
    provider["base_url"] = base_url
    provider["api_key"] = api_key
    return provider


def _default_config(role=MODE_ALL):
    return {
        "user": {"role": normalize_user_role(role)},
        "provider": {"default": DEFAULT_PROVIDER_ID},
        "providers": [_default_provider()],
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
    updated_cfg, role_changed = _normalize_user_config(updated_cfg)
    if changed or role_changed or updated_cfg != cfg:
        try:
            save_config(updated_cfg)
        except OSError as exc:
            console.print(f"[yellow]无法更新 {CONFIG_PATH}: {exc}[/yellow]")
            return cfg
    return updated_cfg


def _provider_label(provider):
    return provider.get("name", provider.get("id", DEFAULT_PROVIDER_ID))


def _prompt_provider_credentials(provider, existing_base_url="", existing_api_key="", allow_keep=False):
    if not sys.stdin.isatty():
        console.print(
            f"[red]当前不是交互终端，无法输入 API URL / API Key，请在终端里运行 {current_command()} "
            f"或执行 {config_command_hint()}[/red]"
        )
        sys.exit(1)

    base_default = existing_base_url or DEFAULT_BASE_URL
    base_url = Prompt.ask(f"请输入 API 地址（provider: {_provider_label(provider)}）", default=base_default).rstrip("/")

    key_prompt = f"请输入 API Key（provider: {_provider_label(provider)}）"
    if allow_keep and existing_api_key:
        key_prompt = f"请输入 API Key（provider: {_provider_label(provider)}，留空保持不变）"

    prompt_kwargs = {"password": True}
    if allow_keep:
        prompt_kwargs["default"] = ""
    api_key = Prompt.ask(key_prompt, **prompt_kwargs)
    if allow_keep and existing_api_key and not api_key:
        api_key = existing_api_key

    if not api_key:
        console.print("[red]API Key 不能为空[/red]")
        sys.exit(1)

    return base_url, api_key


def _probe_models(provider, emit_output=True):
    provider_id = provider.get("id", DEFAULT_PROVIDER_ID)
    protocols = provider.get("protocols", [])
    base_url = provider.get("base_url", "").rstrip("/")
    api_key = provider.get("api_key", "")
    result = {
        "provider_id": provider_id,
        "models": None,
        "error": None,
        "error_kind": None,
        "details": [],
    }

    if "openai_chat_completions" not in protocols:
        result["error_kind"] = "protocol_unsupported"
        result["error"] = f"provider '{provider_id}' 未声明 openai_chat_completions，无法探测 /v1/models"
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
        try:
            response = httpx.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            models.sort()
            result["models"] = models
            if not models:
                result["error_kind"] = "empty_models"
                result["error"] = "接口返回成功，但模型列表为空"
        except Exception as exc:
            result["error_kind"] = "request_failed"
            result["error"] = f"拉取模型列表失败: {exc}"

    details = [
        f"provider: {_provider_label(provider)} ({provider_id})",
        f"base_url: {base_url or '(未设置)'}",
        f"protocols: {', '.join(protocols) if protocols else '(未声明)'}",
    ]
    if result["error"]:
        details.append(f"error: {result['error']}")
    result["details"] = details

    if emit_output and result["error"]:
        style = "yellow" if result["error_kind"] == "protocol_unsupported" else "red"
        console.print(f"[{style}]{result['error']}[/{style}]")
    return result


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
            from ccs_tui import select_actions_tui
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
    base_url, api_key = _prompt_provider_credentials(provider, existing_base_url, existing_api_key, allow_keep)
    provider_ctx = dict(provider)
    provider_ctx["base_url"] = base_url
    provider_ctx["api_key"] = api_key

    console.print("\n正在测试连接...", style="dim")
    models = fetch_models(provider_ctx)
    if models is None:
        console.print("[yellow]⚠ 连接失败，但配置仍会保存。请检查地址和 Key。[/yellow]")
    else:
        console.print(f"[green]✓ 连接成功！发现 {len(models)} 个可用模型[/green]")

    save_provider_credentials(provider["id"], base_url, api_key)
    console.print(f"[green]✓ provider '{provider['id']}' 的凭据已保存到 {CREDENTIALS_PATH}[/green]")
    console.print("[dim]API Key 在配置显示里会以掩码形式展示，不会直接回显明文。[/dim]")
    return resolve_provider_context({"providers": [provider], "provider": {"default": provider["id"]}}, provider["id"])


def setup_api_credentials(existing_base_url="", existing_api_key="", allow_keep=False):
    provider = _default_provider()
    provider_ctx = setup_provider_credentials(provider, existing_base_url, existing_api_key, allow_keep)
    return provider_ctx["base_url"], provider_ctx["api_key"]


def ensure_provider_credentials(cfg, provider_id=None):
    provider = get_provider_definition(cfg, provider_id)
    base_url, api_key = load_provider_credentials(provider["id"])
    if base_url and api_key:
        return resolve_provider_context(cfg, provider["id"])
    return setup_provider_credentials(provider, base_url, api_key, allow_keep=bool(api_key))


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
    probe = _probe_models(provider, emit_output=True)
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
            probe = _probe_models(provider, emit_output=True)
            models = probe.get("models")
            if models:
                return provider, models


def categorize_models(models):
    categorized = {cat: [] for cat in CATEGORIES}
    categorized["其他"] = []
    for m in models:
        placed = False
        for cat, prefixes in CATEGORIES.items():
            if any(m.lower().startswith(p.lower()) for p in prefixes):
                categorized[cat].append(m)
                placed = True
                break
        if not placed:
            categorized["其他"].append(m)
    return {k: v for k, v in categorized.items() if v}


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


def _ensure_models_cache_available(models_cache):
    if models_cache:
        return True
    console.print("[yellow]当前没有可用的模型列表。请先修复 provider 校验，或先使用场景 / 预设启动。[/yellow]")
    return False


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
        from ccs_tui import select_model_tui
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

def show_scenes():
    scene_list = list(SCENES.keys())
    lines = []
    for i, name in enumerate(scene_list, 1):
        s = SCENES[name]
        lines.append(f"  {i}. {s['emoji']} {name}  {s['desc']}")
    lines.append("  ─" * 20)
    lines.append(f"  {len(scene_list) + 1}. 🔧 自定义    手动选 CLI + 模型")

    console.print(Panel("\n".join(lines), title=f"{display_title()} — 选择场景"))
    return scene_list


def select_scene_fallback():
    """非 TTY 环境的 fallback：数字选择"""
    scene_list = show_scenes()
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

def confirm_launch(cli, model_info, once=False):
    if isinstance(model_info, dict):
        model_display = ", ".join(f"{k}={v}" for k, v in model_info.items() if k != "subagent")
    else:
        model_display = model_info

    mode_str = "一次性命令" if once else "交互会话"
    env_str = "临时注入，仅当前 CLI 进程可见" if cli in ("claude", "codex", "kimi") else "无需额外注入"
    panel_text = (
        f"[bold]CLI:[/bold]    {cli}\n"
        f"[bold]模型:[/bold]   {model_display}\n"
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


# ── CLI Selection (fallback) ───────────────────────────

def check_cli_installed(cli_name):
    from shutil import which
    return which(cli_name) is not None


def select_cli():
    from ccs_installer import check_and_offer_install
    table = Table(title="选择 CLI")
    table.add_column("#", style="cyan", width=4)
    table.add_column("CLI", style="green")
    table.add_column("状态", style="yellow")

    for i, name in enumerate(CLI_NAMES, 1):
        status = "[green]已安装[/green]" if check_cli_installed(name) else "[red]未安装[/red]"
        table.add_row(str(i), name, status)

    console.print(table)

    while True:
        try:
            choice = IntPrompt.ask("选择 CLI 编号")
            if 1 <= choice <= len(CLI_NAMES):
                cli = CLI_NAMES[choice - 1]
                if not check_cli_installed(cli):
                    check_and_offer_install(cli)
                return cli
            console.print(f"[red]请输入 1-{len(CLI_NAMES)}[/red]")
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


def _handle_tui_scene_selection(cfg, provider, once):
    """TUI 交互选择场景，返回 True 表示已处理（launch 或退出），False 表示 fallback"""
    from ccs_tui import select_scene_tui, select_model_tui, confirm_tui
    from ccs_launchers import launch_cli, get_export_env

    while True:
        result = select_scene_tui(SCENES, CLI_NAMES)

        # curses 失败，fallback
        if result == "fallback":
            return False

        # 用户取消
        if result is None:
            return True

        scene_name, cli, model_info = result

        if scene_name is None:
            # 自定义模式：用 TUI 选模型
            models = fetch_models(provider)
            if not models:
                return True
            model = select_model_tui(models, title=f"为 {cli} 选择模型")
            if model is None:
                return True
            model_info = {"model": model}
        if not check_cli_installed(cli):
            console.print(f"[yellow]{cli} 未安装，使用 claude 代替[/yellow]")
            cli = "claude"

        clean_model_info = _clean_model_info(model_info)
        env_vars = get_export_env(cli, provider)
        action = confirm_tui(cli, clean_model_info, env_vars=env_vars, once=once)
        if action == "q":
            return True
        if action == "b":
            continue
        launch_cli(cli, clean_model_info, provider, once=once)
        return True


# ── Export command ──────────────────────────────────────

def handle_export(cli_name, provider, apply=False):
    """输出指定 CLI 的 export 命令，或写入独立 env 文件。"""
    from ccs_launchers import get_export_env

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
    if key_path == "provider.list":
        _display_providers(cfg)
        return
    if key_path == "provider.default":
        _handle_provider_default_config(cfg, args_rest[1:])
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
        val = cfg
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
                return
        if "key" in key_path.lower():
            display = _mask_key(str(val))
        else:
            display = str(val)
        console.print(f"[cyan]{key_path}[/cyan] = {display}")
    elif len(args_rest) == 2:
        # 修改某个值
        new_val = args_rest[1]
        if key_path == "user.role":
            new_val = _validate_user_role(new_val)
        _set_nested(cfg, parts, new_val)
        save_config(cfg)
        if "key" in key_path.lower():
            display = _mask_key(new_val)
        else:
            display = new_val
        console.print(f"[green]✓ {key_path} = {display}[/green]")


def _handle_api_config(key_path, args_rest):
    base_url, api_key = load_api_credentials()

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


def _display_providers(cfg):
    providers = cfg.get("providers", [])
    if not providers:
        console.print("[yellow]未配置 provider[/yellow]")
        return

    table = Table(title="Providers", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("协议", style="yellow")
    table.add_column("CLI", style="magenta")
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
            status.strip(),
            provider_ctx.get("base_url") or "(未设置)",
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {current_command()} config provider.default <id> 切换默认 provider。[/dim]"
    )


def _display_config(cfg, prefix="", depth=0):
    """递归显示配置，遮蔽敏感值"""
    if depth == 0:
        provider = resolve_provider_context(cfg)
        console.print("[bold]provider:[/bold]")
        console.print(f"  [cyan]default[/cyan] = {cfg.get('provider', {}).get('default', DEFAULT_PROVIDER_ID)}")
        console.print(f"  [cyan]base_url[/cyan] = {provider.get('base_url') or '(未设置)'}")
        key_display = _mask_key(provider.get("api_key", "")) if provider.get("api_key") else "(未设置)"
        console.print(f"  [cyan]api_key[/cyan] = {key_display}")
        console.print(f"  [cyan]credentials_file[/cyan] = {CREDENTIALS_PATH}")
        console.print("  [dim]api_key 为掩码显示；真实值请查看 credentials_file。[/dim]")
        _display_providers(cfg)
        active_overrides = _existing_override_paths()
        if active_overrides:
            console.print(f"  [cyan]override_files[/cyan] = {active_overrides}")
            console.print("  [dim]override 仅在运行时叠加，不会直接写回 config.toml。[/dim]")
        else:
            console.print(f"  [cyan]override_files[/cyan] = {OVERRIDE_PATHS}")
            console.print("  [dim]如需团队共享默认值，可在以上路径创建 override.toml。[/dim]")

    for k, v in cfg.items():
        if depth == 0 and k in {"providers", "provider"}:
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


# ── Main ────────────────────────────────────────────────

def main():
    # 先检查是否是 config 子命令（argparse 前拦截）
    if len(sys.argv) >= 2 and sys.argv[1] == "config":
        cfg = load_config()
        if cfg is None:
            cfg = _default_config()
            save_config(cfg)
        handle_config(cfg, sys.argv[2:])
        return

    parser = argparse.ArgumentParser(
        prog=current_command(),
        description=f"{display_title()} — AI Coding CLI 统一启动器",
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="场景编号(1-6) 或 CLI 名称(claude/codex/qwen/kimi)")
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
                        help="配合 --export 使用，写入 ~/.config/ccs/env/<cli>.sh")

    args = parser.parse_args()

    # --install
    if args.install:
        from ccs_installer import install_cli
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

    from ccs_launchers import launch_cli

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
        for i, (name, s) in enumerate(SCENES.items(), 1):
            console.print(f"  {i}. {s['emoji']} {name} — {s['desc']}")
        return

    # --export
    if args.export is not None:
        handle_export(args.export, default_provider, apply=args.apply)
        return

    default_provider, models_cache = ensure_models_ready(cfg, default_provider)

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
        provider = ensure_provider_credentials(cfg, p.get("provider"))
        model_info = {k: v for k, v in p.items() if k not in {"cli", "provider"}}
        once = bool(args.once)
        launch_cli(cli, model_info, provider, once=once)
        return

    # Determine once mode
    once = bool(args.once)
    once_target = args.once if isinstance(args.once, str) and args.once is not True else None

    # Direct target
    target = once_target or args.target

    if target:
        # Is it a scene number?
        scene_list = list(SCENES.keys())
        try:
            idx = int(target)
            if 1 <= idx <= len(scene_list):
                scene_name = scene_list[idx - 1]
                scene = SCENES[scene_name]
                cli = scene["cli"]
                model_info = _select_scene_model_info(scene_name, scene, use_tui=False)
                if not check_cli_installed(cli):
                    console.print(f"[yellow]{cli} 未安装，使用 claude 代替[/yellow]")
                    cli = "claude"
                console.print(f"[cyan]场景: {scene['emoji']} {scene_name}[/cyan]")
                action = confirm_launch(cli, model_info, once)
                if action == "q":
                    return
                if action == "s":
                    save_preset_interactive(user_cfg, cli, model_info)
                launch_cli(cli, _clean_model_info(model_info), default_provider, once=once)
                return
        except ValueError:
            pass

        # Is it a CLI name?
        if target in CLI_NAMES:
            cli = target
            if not check_cli_installed(cli):
                from ccs_installer import check_and_offer_install
                check_and_offer_install(cli)
            if not _ensure_models_cache_available(models_cache):
                return
            models_list = display_models(models_cache, role, recommend)
            model = select_model_interactive(models_list)
            action = confirm_launch(cli, model, once)
            if action == "q":
                return
            if action == "s":
                save_preset_interactive(user_cfg, cli, model)
            launch_cli(cli, {"model": model}, default_provider, once=once)
            return

        console.print(f"[red]未知目标: {target}[/red]")
        return

    # --custom: manual CLI + model selection
    if args.custom:
        cli = select_cli()
        if not _ensure_models_cache_available(models_cache):
            return
        models_list = display_models(models_cache, role, recommend)
        model = select_model_interactive(models_list)
        action = confirm_launch(cli, model, once)
        if action == "q":
            return
        if action == "s":
            save_preset_interactive(user_cfg, cli, model)
        launch_cli(cli, {"model": model}, default_provider, once=once)
        return

    # Default: TUI scene selection (with fallback)
    if _use_tui():
        handled = _handle_tui_scene_selection(cfg, default_provider, once)
        if handled:
            return
        # fallback if curses failed

    # Fallback: number-based selection
    scene_name = select_scene_fallback()

    if scene_name is None:
        # Custom mode
        cli = select_cli()
        if not _ensure_models_cache_available(models_cache):
            return
        models_list = display_models(models_cache, role, recommend)
        model = select_model_interactive(models_list)
        action = confirm_launch(cli, model, once)
        if action == "q":
            return
        if action == "s":
            save_preset_interactive(user_cfg, cli, model)
        launch_cli(cli, {"model": model}, default_provider, once=once)
        return

    scene = SCENES[scene_name]
    cli = scene["cli"]
    model_info = _select_scene_model_info(scene_name, scene, use_tui=False)

    if not check_cli_installed(cli):
        fallback = scene.get("fallback_cli", "claude")
        console.print(f"[yellow]{cli} 未安装，使用 {fallback} 代替[/yellow]")
        cli = fallback

    action = confirm_launch(cli, model_info, once)
    if action == "q":
        return
    if action == "s":
        save_preset_interactive(user_cfg, cli, model_info)
    launch_cli(cli, _clean_model_info(model_info), default_provider, once=once)
