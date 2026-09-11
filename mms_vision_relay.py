"""Lend image reading to a model that cannot do it itself.

Pi has had this for a while through its own extension: when the main model
cannot read images, a ``describe_image`` tool forwards the picture to another
model on the same channel that can, and returns text. Claude Code and OpenCode
have no extension surface, but both speak MCP, so they reach the same pool
through a small stdio server instead.

The pool is not a list of model names. It is every model the user's own channel
exposes whose resolved capability says it reads images, which is the same
single-truth chain the Pi relay uses. A channel with no such model gets no
relay at all, and the caller is told so rather than silently losing the
feature.
"""
from __future__ import annotations

import json
import os

RELAY_CONFIG_ENV = "MMS_VISION_RELAY_CONFIG"
RELAY_DIR_NAME = "vision-relay"
RELAY_SERVER_NAME = "vision"
_SERVER_SCRIPT = "mms-vision-mcp.mjs"


def _pi_support():
    import mms_pi_support

    return mms_pi_support


def relay_server_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", _SERVER_SCRIPT)


def relay_plan(runtime, model_name) -> dict:
    """``{"main_model_vision": bool, "pool": [...]}`` for this channel.

    Reuses the Pi plan so all harnesses agree on who can see images.
    """
    try:
        return _pi_support()._pi_vision_plan(runtime, model_name)
    except Exception:
        return {"main_model_vision": False, "pool": []}


def relay_needed(runtime, model_name) -> bool:
    plan = relay_plan(runtime, model_name)
    if plan.get("main_model_vision"):
        return False
    return bool(plan.get("pool"))


def relay_catalog(runtime, model_name):
    """The models.json-shaped catalog the relay server reads.

    Identical in shape to what Pi already writes, so the server discovers
    endpoints, keys and per-model ``input`` the same way for every harness.
    """
    try:
        payload, _ref = _pi_support()._pi_build_models_payload(runtime, model_name)
    except Exception:
        return None
    return payload if isinstance(payload, dict) and payload.get("providers") else None


def session_catalog_path(session_home, name="models"):
    """Where a session keeps its relay catalog."""
    return os.path.join(str(session_home), RELAY_DIR_NAME, f"{name}.json")


def write_relay_catalog(path, runtime, model_name):
    """Write the catalog at ``path`` and return it, or None.

    Returns None when the main model reads images itself, when the channel has
    no model that can, or when the catalog cannot be built. ``path`` is a file
    and must be unique per config it serves: two channels sharing one catalog
    would hand the second channel's key to the first.
    """
    if not path or not relay_needed(runtime, model_name):
        return None
    catalog = relay_catalog(runtime, model_name)
    if not catalog:
        return None
    try:
        os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        # Carries the channel key, so it is owner-readable only, like the Pi
        # export it mirrors.
        from mms_state_io import atomic_write_text

        atomic_write_text(str(path), json.dumps(catalog, indent=2) + "\n", mode=0o600)
    except Exception:
        return None
    return str(path)


def mcp_server_spec(config_path):
    """The MCP stdio server entry for a harness that speaks MCP."""
    server = relay_server_path()
    if not config_path or not os.path.isfile(server):
        return None
    return {
        "type": "stdio",
        "command": "node",
        "args": [server],
        "env": {RELAY_CONFIG_ENV: str(config_path)},
    }


def opencode_mcp_entry(config_path):
    """OpenCode spells the same server differently."""
    server = relay_server_path()
    if not config_path or not os.path.isfile(server):
        return None
    return {
        "type": "local",
        "command": ["node", server],
        "enabled": True,
        "environment": {RELAY_CONFIG_ENV: str(config_path)},
    }
