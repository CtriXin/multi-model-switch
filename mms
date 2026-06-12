#!/usr/bin/env python3
"""MMS — Multi-Model Switch 入口"""

import os
import sys

ROOT = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, ROOT)

if len(sys.argv) > 1 and sys.argv[1] == "review-dispatch":
    from mms_review_dispatch import handle_review_dispatch_command

    sys.exit(handle_review_dispatch_command(sys.argv[2:], command_name="mms"))


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

argv = sys.argv[1:]
if len(argv) >= 2 and argv[0] == "config" and argv[1] in {"save-plan", "save.plan", "v2-save-plan", "registry-save-plan"}:
    import json

    from mms_registry_cli import _print_registry_v2_save_plan, registry_v2_save_plan

    plan = registry_v2_save_plan(command_name="mms config save-plan")
    if "--json" in argv[2:]:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_registry_v2_save_plan(plan)
    raise SystemExit(0)

from mms_core import main

if __name__ == "__main__":
    main()
