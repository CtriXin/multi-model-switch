"""Shared runtime model-name helpers."""

from __future__ import annotations


def resolve_model(model_info):
    """Extract the selected model name from a runtime model payload."""
    if isinstance(model_info, str):
        return model_info
    return model_info.get("model", model_info.get("sonnet", ""))


def normalized_model_name(model_name):
    if not isinstance(model_name, str):
        return ""
    return model_name.strip()
