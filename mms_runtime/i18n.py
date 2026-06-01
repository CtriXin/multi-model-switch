"""Minimal UI language helpers for MMS."""

import os

SUPPORTED_LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"

_CURRENT_LANGUAGE = DEFAULT_LANGUAGE


def normalize_language(value):
    raw = str(value or "").strip().lower()
    if raw.startswith("zh"):
        return "zh"
    if raw.startswith("en"):
        return "en"
    return ""


def set_language(value):
    global _CURRENT_LANGUAGE
    normalized = normalize_language(value) or DEFAULT_LANGUAGE
    _CURRENT_LANGUAGE = normalized
    return _CURRENT_LANGUAGE


def get_language():
    env_lang = normalize_language(os.environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    return _CURRENT_LANGUAGE


def pick(zh_text, en_text=None):
    if get_language() == "en":
        return en_text if en_text is not None else zh_text
    return zh_text
