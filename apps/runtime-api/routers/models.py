"""
Models API - Model management
"""
from fastapi import APIRouter, Query
from typing import Optional
from models import MOCK_MODELS

router = APIRouter(tags=["models"])


@router.get("/models")
async def get_models(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """Get available models with optional filters"""
    models = MOCK_MODELS

    if provider:
        models = [m for m in models if m.provider == provider]
    if category:
        models = [m for m in models if m.category == category]

    return {
        "models": [m.model_dump() for m in models],
        "total": len(models),
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """Get specific model details"""
    for model in MOCK_MODELS:
        if model.id == model_id:
            return model.model_dump()
    return {"error": "Model not found"}, 404
