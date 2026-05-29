"""Shared runtime environment scrubbing helpers for MMS launchers.

Helpers resolve constants through ``mms_launchers`` at call time so existing
compatibility wrappers and monkeypatch-based tests keep the same behavior.
"""

from __future__ import annotations


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
