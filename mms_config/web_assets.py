# -*- coding: utf-8 -*-
"""Static asset loader for the MMS config WebUI.

Edit files under ``mms_config_web_static/`` for UI markup, styles, and browser
logic. This module only resolves those files for the Python HTTP server.
"""

from __future__ import annotations

from pathlib import Path


_STATIC_DIR = Path(__file__).resolve().parents[1] / "mms_config_web_static"
_ASSET_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "config-web.css": "text/css; charset=utf-8",
    "config-web-reports.css": "text/css; charset=utf-8",
    "config-web-reports.js": "application/javascript; charset=utf-8",
    "config-web.js": "application/javascript; charset=utf-8",
}


def _static_path(name: str) -> Path:
    if name not in _ASSET_TYPES:
        raise FileNotFoundError(name)
    return _STATIC_DIR / name


def _read_static_text(name: str) -> str:
    return _static_path(name).read_text(encoding="utf-8")


def read_static_asset(name: str) -> tuple[bytes, str]:
    """Return a known config-WebUI static asset and its content type."""

    return _static_path(name).read_bytes(), _ASSET_TYPES[name]


def read_index_html() -> str:
    """Read the editable WebUI HTML file from disk."""

    return _read_static_text("index.html")


_HTML_PAGE = _read_static_text("index.html")
