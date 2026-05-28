"""
Bootstrap API - App initialization config
"""
from fastapi import APIRouter
from models import MOCK_PROVIDERS, MOCK_ACCOUNTS, MOCK_PRESETS

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap")
async def get_bootstrap():
    """Get app bootstrap configuration"""
    return {
        "version": "0.1.0",
        "features": [
            "launcher-runtime",
            "model-routing",
            "gateway-proxy",
            "model-presets",
        ],
        "providers": [p.model_dump() for p in MOCK_PROVIDERS],
        "accounts": [a.model_dump() for a in MOCK_ACCOUNTS],
        "presets": [p.model_dump() for p in MOCK_PRESETS],
        "limits": {
            "maxModels": 5,
        },
    }
