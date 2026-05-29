"""Session-scoped environment helpers for MMS launchers."""

from __future__ import annotations


def _launchers():
    import mms_launchers as _module

    return _module


def configure_ecc_session_env(env_data, *, enable_ecc=False):
    merged = dict(env_data) if isinstance(env_data, dict) else {}
    for key in (
        "CLAUDE_PLUGIN_ROOT",
        "ECC_PLUGIN_ROOT",
        "ECC_HOOK_PROFILE",
        "ECC_DISABLED_HOOKS",
        "OMC_PLUGIN_ROOT",
    ):
        merged.pop(key, None)
    if not enable_ecc:
        return merged
    ecc_root = _launchers()._resolve_ecc_root()
    if not ecc_root:
        return merged
    merged["CLAUDE_PLUGIN_ROOT"] = ecc_root
    merged["ECC_PLUGIN_ROOT"] = ecc_root
    merged.setdefault("ECC_HOOK_PROFILE", "standard")
    return merged


def configure_agent_pack_session_env(env_data, *, agent_pack="none"):
    merged = _launchers()._configure_ecc_session_env(env_data, enable_ecc=False)
    pack = _launchers()._normalize_agent_pack(agent_pack, default="none")
    if pack == "ecc":
        return _launchers()._configure_ecc_session_env(merged, enable_ecc=True)
    if pack == "omc":
        omc_root = _launchers()._resolve_omc_root()
        if not omc_root:
            return merged
        merged["CLAUDE_PLUGIN_ROOT"] = omc_root
        merged["OMC_PLUGIN_ROOT"] = omc_root
    return merged


def session_required_env_from_runtime_env(env):
    env = env if isinstance(env, dict) else {}
    required = {}
    for key in _launchers()._CLAUDE_SESSION_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            required[key] = value
    return required
