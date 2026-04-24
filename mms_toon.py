from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any


_SAFE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_NUMBER_LIKE_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")


@dataclass(frozen=True)
class LlmDataFormat:
    format: str
    text: str
    json_chars: int
    toon_chars: int | None
    savings_chars: int
    savings_ratio: float


def json_for_llm(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def choose_llm_data_format(
    value: Any,
    *,
    allow_toon: bool = True,
    min_savings_chars: int = 24,
    min_savings_ratio: float = 0.05,
) -> LlmDataFormat:
    json_text = json_for_llm(value)
    json_chars = len(json_text)
    if not allow_toon:
        return LlmDataFormat("json", json_text, json_chars, None, 0, 0.0)

    try:
        toon_text = "TOON:\n" + encode_toon(value)
    except (TypeError, ValueError):
        return LlmDataFormat("json", json_text, json_chars, None, 0, 0.0)

    savings_chars = json_chars - len(toon_text)
    savings_ratio = savings_chars / json_chars if json_chars else 0.0
    if savings_chars >= min_savings_chars and savings_ratio >= min_savings_ratio:
        return LlmDataFormat("toon", toon_text, json_chars, len(toon_text), savings_chars, savings_ratio)
    return LlmDataFormat("json", json_text, json_chars, len(toon_text), savings_chars, savings_ratio)


def format_llm_data(value: Any, **kwargs: Any) -> str:
    return choose_llm_data_format(value, **kwargs).text


def encode_toon(value: Any) -> str:
    if not _is_supported(value):
        raise TypeError("value shape is not supported by the minimal TOON encoder")
    lines = _encode_value(None, value, 0)
    return "\n".join(lines).rstrip()


def _is_supported(value: Any) -> bool:
    if _is_primitive(value):
        return True
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_supported(item) for key, item in value.items())
    if isinstance(value, list):
        return _is_primitive_list(value) or _is_table_list(value)
    return False


def _is_primitive(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _is_primitive_list(value: list[Any]) -> bool:
    return all(_is_primitive(item) for item in value)


def _is_table_list(value: list[Any]) -> bool:
    if not value or not all(isinstance(item, dict) for item in value):
        return False
    fields = list(value[0].keys())
    if not fields or not all(isinstance(field, str) for field in fields):
        return False
    field_set = set(fields)
    for row in value:
        if set(row.keys()) != field_set:
            return False
        if not all(_is_primitive(row[field]) for field in fields):
            return False
    return True


def _encode_value(key: str | None, value: Any, indent: int) -> list[str]:
    prefix = "  " * indent
    label = _format_key(key) if key is not None else ""

    if _is_primitive(value):
        if key is None:
            return [prefix + _format_scalar(value)]
        return [f"{prefix}{label}: {_format_scalar(value)}"]

    if isinstance(value, dict):
        lines = []
        if key is not None:
            lines.append(f"{prefix}{label}:")
            child_indent = indent + 1
        else:
            child_indent = indent
        for child_key, child_value in value.items():
            lines.extend(_encode_value(child_key, child_value, child_indent))
        return lines

    if _is_primitive_list(value):
        suffix = ",".join(_format_scalar(item) for item in value)
        if key is None:
            return [f"{prefix}[{len(value)}]: {suffix}"]
        return [f"{prefix}{label}[{len(value)}]: {suffix}"]

    if _is_table_list(value):
        fields = list(value[0].keys())
        header_fields = ",".join(_format_key(field) for field in fields)
        if key is None:
            header = f"{prefix}[{len(value)}]{{{header_fields}}}:"
        else:
            header = f"{prefix}{label}[{len(value)}]{{{header_fields}}}:"
        rows = [
            "  " * (indent + 1) + ",".join(_format_scalar(row[field]) for field in fields)
            for row in value
        ]
        return [header, *rows]

    raise TypeError("value shape is not supported by the minimal TOON encoder")


def _format_key(key: str | None) -> str:
    if key is None:
        return ""
    if _SAFE_KEY_RE.fullmatch(key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        raise TypeError(f"unsupported scalar type: {type(value).__name__}")
    if _needs_quoted_string(value):
        return json.dumps(value, ensure_ascii=False)
    return value


def _needs_quoted_string(value: str) -> bool:
    if value == "":
        return True
    if value != value.strip():
        return True
    if value.lower() in {"true", "false", "null"}:
        return True
    if _NUMBER_LIKE_RE.fullmatch(value):
        return True
    if any(ch in value for ch in [",", "\n", "\r", '"', "[", "]", "{", "}"]):
        return True
    if value.startswith(("-", ":", "#")):
        return True
    return False
