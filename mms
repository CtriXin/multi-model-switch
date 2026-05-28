#!/usr/bin/env python3
"""MMS — Multi-Model Switch 入口"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
