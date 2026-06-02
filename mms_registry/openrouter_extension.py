"""OpenRouter optional extension helpers.

This module is intentionally side-effect free except for explicit API probes.
It keeps OpenRouter text/image/video account gating out of the launcher path.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from mms_registry.provider_profiles import ensure_default_user_agent
from decimal import Decimal, InvalidOperation
from typing import Any


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://github.com/CtriXin/multi-model-switch"
OPENROUTER_TITLE = "MMS OpenRouter Extension"
FREE_ONLY_TIERS = {"free", "unknown", "invalid", "missing_key"}
ACCOUNT_TIERS = {"paid", "free", "unknown", "invalid", "missing_key"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("data")
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _positive(value: Any) -> bool:
    parsed = _decimal(value)
    return parsed is not None and parsed > 0


def _zeroish(value: Any) -> bool:
    parsed = _decimal(value)
    return parsed is not None and parsed == 0


def _origin_from_model_id(model_id: str) -> str:
    if "/" not in model_id:
        return "openrouter"
    origin = model_id.split("/", 1)[0].strip()
    return origin or "openrouter"


def _modalities(record: dict[str, Any]) -> tuple[list[str], list[str], str]:
    arch = record.get("architecture") if isinstance(record.get("architecture"), dict) else {}
    inputs = [_lower(item) for item in (arch.get("input_modalities") or []) if _lower(item)]
    outputs = [_lower(item) for item in (arch.get("output_modalities") or []) if _lower(item)]
    modality = _lower(arch.get("modality"))
    if "->" in modality:
        left, right = modality.split("->", 1)
        inputs = inputs or [part.strip() for part in left.split("+") if part.strip()]
        outputs = outputs or [part.strip() for part in right.split("+") if part.strip()]
    return inputs, outputs, modality


def openrouter_model_is_free(record: dict[str, Any]) -> bool:
    """Return True for OpenRouter free-tier model records.

    OpenRouter marks many free models with the ':free' suffix. A few public
    router/preview records expose zero pricing without that suffix, so zero
    prompt+completion/request pricing is also treated as free for display.
    """
    model_id = _lower(record.get("id"))
    if model_id.endswith(":free") or ":free" in model_id:
        return True
    pricing = record.get("pricing") if isinstance(record.get("pricing"), dict) else {}
    relevant = [
        pricing.get("prompt"),
        pricing.get("completion"),
        pricing.get("request"),
    ]
    present = [value for value in relevant if value is not None]
    return bool(present) and all(_zeroish(value) for value in present)


def normalize_openrouter_model(record: dict[str, Any]) -> dict[str, Any]:
    model_id = _clean(record.get("id"))
    inputs, outputs, modality = _modalities(record)
    pricing = record.get("pricing") if isinstance(record.get("pricing"), dict) else {}
    text_output = "text" in outputs or (not outputs and not model_id.startswith("openrouter/auto"))
    image_output = "image" in outputs
    video_output = "video" in outputs
    return {
        "id": model_id,
        "name": _clean(record.get("name")) or model_id,
        "origin": _origin_from_model_id(model_id),
        "input_modalities": inputs,
        "output_modalities": outputs,
        "modality": modality,
        "is_free": openrouter_model_is_free(record),
        "text": bool(text_output),
        "image": bool(image_output),
        "video": bool(video_output),
        "pricing": dict(pricing),
        "context_length": record.get("context_length"),
    }


def normalize_openrouter_video_model(record: dict[str, Any]) -> dict[str, Any]:
    model_id = _clean(record.get("id"))
    pricing = record.get("pricing_skus") if isinstance(record.get("pricing_skus"), dict) else {}
    return {
        "id": model_id,
        "name": _clean(record.get("name")) or model_id,
        "origin": _origin_from_model_id(model_id),
        "input_modalities": ["text", "image"] if record.get("supported_frame_images") else ["text"],
        "output_modalities": ["video"],
        "video": True,
        "pricing_skus": dict(pricing),
        "supported_resolutions": list(record.get("supported_resolutions") or []),
        "supported_durations": list(record.get("supported_durations") or []),
    }


def _credits_payload_balance(credits_payload: Any) -> Decimal | None:
    if not isinstance(credits_payload, dict):
        return None
    data = credits_payload.get("data") if isinstance(credits_payload.get("data"), dict) else credits_payload
    candidates = (
        data.get("total_credits"),
        data.get("credits"),
        data.get("balance"),
        data.get("credit_balance"),
        data.get("limit_remaining"),
    )
    positives = [_decimal(value) for value in candidates if value is not None]
    positives = [value for value in positives if value is not None]
    if not positives:
        return None
    return max(positives)


def detect_openrouter_account_tier(
    key_payload: Any = None,
    credits_payload: Any = None,
    *,
    has_api_key: bool = False,
    key_error_status: int | None = None,
    assume_paid: bool = False,
) -> dict[str, Any]:
    if assume_paid:
        return {"tier": "paid", "reason": "assume_paid"}
    if key_error_status in {401, 403}:
        return {"tier": "invalid", "reason": f"key_http_{key_error_status}"}
    if not has_api_key:
        return {"tier": "missing_key", "reason": "no_api_key"}

    key_data = key_payload.get("data") if isinstance(key_payload, dict) and isinstance(key_payload.get("data"), dict) else key_payload
    if isinstance(key_data, dict):
        for field in ("is_free_tier", "free_tier", "is_free"):
            if isinstance(key_data.get(field), bool):
                return {
                    "tier": "free" if key_data.get(field) else "paid",
                    "reason": field,
                }
        if any(_positive(key_data.get(field)) for field in ("limit", "limit_remaining", "credit_limit")):
            return {"tier": "paid", "reason": "key_limit"}
        if _lower(key_data.get("tier")) in ACCOUNT_TIERS:
            tier = _lower(key_data.get("tier"))
            return {"tier": tier, "reason": "key_tier"}

    balance = _credits_payload_balance(credits_payload)
    if balance is not None:
        return {"tier": "paid" if balance > 0 else "free", "reason": "credits_balance"}
    return {"tier": "unknown", "reason": "no_plan_signal"}


def classify_openrouter_extension(
    models_payload: Any,
    *,
    key_payload: Any = None,
    credits_payload: Any = None,
    user_models_payload: Any = None,
    video_models_payload: Any = None,
    has_api_key: bool = False,
    key_error_status: int | None = None,
    assume_paid: bool = False,
) -> dict[str, Any]:
    account = detect_openrouter_account_tier(
        key_payload,
        credits_payload,
        has_api_key=has_api_key,
        key_error_status=key_error_status,
        assume_paid=assume_paid,
    )
    free_only = account["tier"] in FREE_ONLY_TIERS
    source_payload = user_models_payload if _as_list(user_models_payload) and not free_only else models_payload
    source = "user" if source_payload is user_models_payload else "public"

    models = [normalize_openrouter_model(item) for item in _as_list(source_payload)]
    models = [item for item in models if item["id"]]
    free_text_models = [item for item in models if item["text"] and item["is_free"]]
    paid_text_models = [item for item in models if item["text"] and not item["is_free"]]
    visible_text_models = free_text_models if free_only else [item for item in models if item["text"]]
    image_models = [] if free_only else [item for item in models if item["image"]]
    video_models = [] if free_only else [
        normalize_openrouter_video_model(item)
        for item in _as_list(video_models_payload)
        if _clean(item.get("id"))
    ]

    return {
        "account": account,
        "model_source": source,
        "free_only": free_only,
        "text_models": visible_text_models,
        "free_text_models": free_text_models,
        "paid_text_models": paid_text_models,
        "image_models": image_models,
        "video_models": video_models,
        "image_enabled": bool(image_models) and not free_only,
        "video_enabled": bool(video_models) and not free_only,
        "counts": {
            "all_source_models": len(models),
            "visible_text": len(visible_text_models),
            "free_text": len(free_text_models),
            "paid_text": len(paid_text_models),
            "image": len(image_models),
            "video": len(video_models),
        },
    }


def openrouter_headers(api_key: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return ensure_default_user_agent(headers)


def openrouter_get_json(
    path: str,
    *,
    api_key: str = "",
    base_url: str = OPENROUTER_BASE_URL,
    timeout: int = 20,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/" + path.strip("/")
    request = urllib.request.Request(url, headers=openrouter_headers(api_key))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "status": int(response.status),
                "payload": json.loads(response.read().decode("utf-8")),
                "url": url,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            payload = {"error": {"message": body[:300]}}
        return {"ok": False, "status": int(exc.code), "payload": payload, "url": url}
    except Exception as exc:
        return {"ok": False, "status": 0, "payload": {"error": {"message": str(exc)}}, "url": url}


def probe_openrouter_extension(api_key: str = "", *, assume_paid: bool = False) -> dict[str, Any]:
    # /models is public; avoid letting an invalid key hide the free fallback list.
    models = openrouter_get_json("models")
    key = openrouter_get_json("key", api_key=api_key) if api_key else {"ok": False, "status": 0, "payload": {}}
    credits = openrouter_get_json("credits", api_key=api_key) if api_key else {"ok": False, "status": 0, "payload": {}}
    user_models = openrouter_get_json("models/user", api_key=api_key) if api_key else {"ok": False, "status": 0, "payload": {}}

    key_status = key.get("status") if not key.get("ok") else None
    preliminary = detect_openrouter_account_tier(
        key.get("payload"),
        credits.get("payload"),
        has_api_key=bool(api_key),
        key_error_status=key_status,
        assume_paid=assume_paid,
    )
    videos = (
        openrouter_get_json("videos/models", api_key=api_key)
        if preliminary["tier"] not in FREE_ONLY_TIERS
        else {"ok": False, "status": 0, "payload": {}}
    )
    summary = classify_openrouter_extension(
        models.get("payload") if models.get("ok") else {},
        key_payload=key.get("payload") if key.get("ok") else {},
        credits_payload=credits.get("payload") if credits.get("ok") else {},
        user_models_payload=user_models.get("payload") if user_models.get("ok") else {},
        video_models_payload=videos.get("payload") if videos.get("ok") else {},
        has_api_key=bool(api_key),
        key_error_status=key_status,
        assume_paid=assume_paid,
    )
    summary["requests"] = {
        "models": {"ok": bool(models.get("ok")), "status": models.get("status")},
        "key": {"ok": bool(key.get("ok")), "status": key.get("status")},
        "credits": {"ok": bool(credits.get("ok")), "status": credits.get("status")},
        "user_models": {"ok": bool(user_models.get("ok")), "status": user_models.get("status")},
        "video_models": {"ok": bool(videos.get("ok")), "status": videos.get("status")},
    }
    return summary


def openrouter_api_key_from_env() -> str:
    for name in ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY", "MMS_OPENROUTER_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""
