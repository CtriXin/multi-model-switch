#!/usr/bin/env python3
"""MMS — Multi-Model Switch 入口"""

import os
import sys

ROOT = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, ROOT)


def _resolve_real_home_for_venv():
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    home = os.path.expanduser("~")
    for marker in ("/.config/mms-next", "/.config/mms"):
        if marker in home:
            return home.split(marker, 1)[0]
    return home


def _reexec_with_mms_venv_if_available():
    if os.environ.get("MMS_SKIP_VENV_REEXEC") == "1" or os.environ.get("MMS_VENV_REEXECED") == "1":
        return
    venv_python = os.path.join(_resolve_real_home_for_venv(), ".mms", ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        return
    if os.path.realpath(sys.executable) == os.path.realpath(venv_python):
        return
    os.environ["MMS_VENV_REEXECED"] = "1"
    os.execv(venv_python, [venv_python, os.path.realpath(__file__), *sys.argv[1:]])


_reexec_with_mms_venv_if_available()

from mms_runtime import ensure_supported_python

ensure_supported_python("MMS")

from mms_core import main

if __name__ == "__main__":
    main()
