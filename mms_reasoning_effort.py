"""Shared model-specific reasoning effort capability helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


CODEX_MAX_EFFORT_MODEL_PREFIXES = ("gpt-5.6", "gpt-6")


def _model_tokens(model_info: Any) -> list[str]:
    if isinstance(model_info, Mapping):
        values = model_info.values()
    elif isinstance(model_info, Iterable) and not isinstance(model_info, (str, bytes)):
        values = model_info
    else:
        values = [model_info]
    tokens: list[str] = []
    for value in values:
        token = str(value or "").strip().lower()
        if "/" in token:
            token = token.rsplit("/", 1)[-1]
        if token:
            tokens.append(token)
    return tokens


def model_supports_max_reasoning_effort(model_info: Any) -> bool:
    return any(
        token.startswith(CODEX_MAX_EFFORT_MODEL_PREFIXES)
        for token in _model_tokens(model_info)
    )
