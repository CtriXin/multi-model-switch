from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services.gateway_config import GatewayContext, get_gateway_config_path, load_gateway_config, resolve_gateway_context
from services.gateway_proxy import proxy_chat_completions, proxy_models
from services.gateway_state import get_gateway_state_path

router = APIRouter(tags=["gateway"])


@router.get("/gateway/health")
async def gateway_health():
    config = load_gateway_config(required=False)
    return {
        "status": "ok" if config else "not_configured",
        "configured": bool(config),
        "configPath": str(get_gateway_config_path()),
        "statePath": str(get_gateway_state_path()),
        "providers": len(config.providers) if config else 0,
        "tokens": len(config.tokens) if config else 0,
    }


@router.get("/v1/models")
async def list_models(request: Request):
    context = _require_gateway_context(request)
    return await proxy_models(request, context)


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    context = _require_gateway_context(request)
    return await proxy_chat_completions(request, context)


def _require_gateway_context(request: Request) -> GatewayContext:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "缺少内部 Bearer token", "code": "gateway_token_missing"}},
        )

    raw_token = auth_header[7:].strip()
    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "内部 Bearer token 为空", "code": "gateway_token_missing"}},
        )

    try:
        context = resolve_gateway_context(raw_token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"message": str(exc), "code": "gateway_config_invalid"}},
        ) from exc

    if not context:
        config = load_gateway_config(required=False)
        if not config:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "message": "gateway 尚未配置。请先创建 gateway-config.json。",
                        "code": "gateway_not_configured",
                    }
                },
            )
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "内部 token 无效或已停用", "code": "gateway_token_invalid"}},
        )

    return context
