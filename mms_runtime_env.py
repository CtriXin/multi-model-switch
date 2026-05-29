"""Shared runtime environment scrubbing helpers for MMS launchers.

Helpers resolve constants through ``mms_launchers`` at call time so existing
compatibility wrappers and monkeypatch-based tests keep the same behavior.
"""

from __future__ import annotations

import os


def runtime_locale_env(runtime=None, *, normalize_language_fn):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw_locale = (
        str(runtime.get("locale") or "").strip()
        or str(os.environ.get("MMS_LOCALE") or "").strip()
        or str(os.environ.get("LC_ALL") or "").strip()
        or str(os.environ.get("LANG") or "").strip()
    )
    normalized_lang = normalize_language_fn(
        str(runtime.get("language") or "").strip()
        or str(os.environ.get("MMS_LANG") or "").strip()
        or raw_locale
    )
    if raw_locale and "." in raw_locale and "_" in raw_locale:
        locale_value = raw_locale
    elif normalized_lang == "zh":
        locale_value = "zh_CN.UTF-8"
    else:
        locale_value = "en_US.UTF-8"
    return {
        "LANG": locale_value,
        "LC_ALL": locale_value,
        "LC_CTYPE": locale_value,
        "LC_MESSAGES": locale_value,
    }


def apply_runtime_locale_profile(env, runtime=None, *, runtime_locale_env_fn):
    env = env if isinstance(env, dict) else {}
    env.update(runtime_locale_env_fn(runtime))
    return env


def scrub_claude_oauth_env(env):
    import mms_launchers as _launchers

    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if any(normalized.startswith(prefix) for prefix in _launchers._CLAUDE_OAUTH_ENV_PREFIX_BLOCKLIST):
            env.pop(key, None)
    return env


def scrub_inherited_runtime_env(env, *, strip_openai=False, strip_proxy=False):
    import mms_launchers as _launchers

    env = _launchers._scrub_claude_oauth_env(env)
    if strip_openai:
        for key in list(env.keys()):
            normalized = str(key or "").strip()
            if any(normalized.startswith(prefix) for prefix in _launchers._OPENAI_ENV_PREFIX_BLOCKLIST):
                env.pop(key, None)
    if strip_proxy:
        for key in (
            *_launchers._RUNTIME_PROXY_ENV_KEYS,
            *_launchers._RUNTIME_FAKE_ENV_KEYS,
            *_launchers._RUNTIME_CA_ENV_KEYS,
        ):
            env.pop(key, None)
    return env
