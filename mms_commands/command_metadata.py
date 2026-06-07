"""Command name and UI language helpers."""

from __future__ import annotations

import os
import sys


def resolve_ui_language(
    cfg=None,
    cli_override=None,
    *,
    normalize_language,
    load_version_meta,
    environ=None,
    default_language="zh",
):
    environ = os.environ if environ is None else environ
    cli_lang = normalize_language(cli_override)
    if cli_lang:
        return cli_lang
    env_lang = normalize_language(environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    if isinstance(cfg, dict):
        ui_lang = normalize_language((cfg.get("ui") or {}).get("language", ""))
        if ui_lang:
            return ui_lang
    locale_lang = normalize_language(environ.get("LC_ALL", "") or environ.get("LANG", ""))
    if locale_lang:
        return locale_lang
    version_meta = load_version_meta()
    version_lang = normalize_language(
        version_meta.get("preferred_language", "") if isinstance(version_meta, dict) else ""
    )
    if version_lang:
        return version_lang
    return default_language


def extract_global_lang(argv, *, normalize_language):
    cleaned = []
    lang = ""
    idx = 0
    while idx < len(argv):
        item = argv[idx]
        if item == "--lang" and idx + 1 < len(argv):
            candidate = normalize_language(argv[idx + 1])
            if candidate:
                lang = candidate
                idx += 2
                continue
        cleaned.append(item)
        idx += 1
    return cleaned, lang


def current_command(*, primary_command, environ=None, argv0=None):
    environ = {} if environ is None else environ
    explicit = str(environ.get("MMS_COMMAND_NAME") or "").strip()
    invoked = os.path.basename(str(argv0 if argv0 is not None else (sys.argv[0] if sys.argv else ""))).strip()
    known_entrypoints = {"mms", "mmd", "mmf", "mmg", "mmm"}
    if explicit and (explicit in known_entrypoints or invoked == explicit):
        return explicit
    if invoked in known_entrypoints:
        return invoked
    return primary_command


def display_title(title="MMS", *, current_command_fn=None):
    if current_command_fn is not None and current_command_fn() == "mmf":
        return "MMF"
    return title
