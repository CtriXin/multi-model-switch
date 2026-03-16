from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
_CONFIG_CACHE: tuple[Path, float, "GatewayConfig"] | None = None


class GatewayUpstreamKey(BaseModel):
    id: str
    apiKey: str
    enabled: bool = True


class GatewayProvider(BaseModel):
    id: str
    label: str
    baseUrl: str
    apiType: str = "openai-compatible"
    httpReferer: str | None = None
    xTitle: str | None = None
    timeoutSeconds: float = 90.0
    modelAllowlist: list[str] = Field(default_factory=lambda: ["*"])
    apiKeys: list[GatewayUpstreamKey]


class GatewayToken(BaseModel):
    id: str
    name: str
    tokenHash: str
    providerId: str
    enabled: bool = True
    allowedModels: list[str] = Field(default_factory=lambda: ["*"])
    upstreamKeyIds: list[str] = Field(default_factory=list)
    dailyRequestLimit: int | None = None


class GatewayConfig(BaseModel):
    providers: list[GatewayProvider]
    tokens: list[GatewayToken]


@dataclass(frozen=True)
class GatewayContext:
    config: GatewayConfig
    provider: GatewayProvider
    token: GatewayToken
    rawToken: str


def get_gateway_config_path() -> Path:
    env_path = os.getenv("MMS_GATEWAY_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "gateway-config.json"


def hash_gateway_token(raw_token: str) -> str:
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def generate_gateway_token(prefix: str = "mms_tk") -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def model_matches(patterns: list[str], model_id: str) -> bool:
    if not patterns:
        return False
    if "*" in patterns:
        return True

    for pattern in patterns:
        if pattern.endswith("*") and model_id.startswith(pattern[:-1]):
            return True
        if pattern == model_id:
            return True
    return False


def load_gateway_config(required: bool = False) -> GatewayConfig | None:
    path = get_gateway_config_path()
    if not path.exists():
        if required:
            raise RuntimeError(
                f"未找到 gateway 配置文件：{path}。"
                "请基于 gateway-config.example.json 复制一份 gateway-config.json 后再启动。"
            )
        return None

    mtime = path.stat().st_mtime
    global _CONFIG_CACHE
    if _CONFIG_CACHE and _CONFIG_CACHE[0] == path and _CONFIG_CACHE[1] == mtime:
        return _CONFIG_CACHE[2]

    raw = path.read_text(encoding="utf-8")
    data = json.loads(_expand_env_placeholders(raw))
    config = GatewayConfig.model_validate(data)
    _CONFIG_CACHE = (path, mtime, config)
    return config


def resolve_gateway_context(raw_token: str) -> GatewayContext | None:
    config = load_gateway_config(required=False)
    if not config:
        return None

    token_hash = hash_gateway_token(raw_token)
    for token in config.tokens:
        if not token.enabled or not secrets.compare_digest(token.tokenHash, token_hash):
            continue

        provider = next((item for item in config.providers if item.id == token.providerId), None)
        if not provider:
            raise RuntimeError(f"gateway token {token.id} 引用了不存在的 provider: {token.providerId}")
        return GatewayContext(config=config, provider=provider, token=token, rawToken=raw_token)

    return None


def _expand_env_placeholders(raw: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.getenv(name, "")

    return _ENV_PATTERN.sub(replace, raw)
