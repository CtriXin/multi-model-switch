# -*- coding: utf-8 -*-
"""Compatibility facade for Settings/report helpers in the MMS config WebUI."""

from __future__ import annotations

from mms_config.web_settings_catalog import (
    _settings_action_cards,
    _settings_gate_catalog,
    _settings_gate_report,
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
    _webui_capability_coverage,
)
from mms_config.web_settings_reports import (
    _config_root_for_snapshot,
    _load_mms_core,
    _safe_text,
    _sanitize_for_output,
    _snapshot_guard_status_report,
    build_config_snapshot,
    build_settings_report,
)
