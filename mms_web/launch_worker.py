"""One process, one original MMS launch. Stdout belongs to Pi's JSONL RPC."""
from __future__ import annotations
import contextlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from mms_web.runtime import require_private_root
    root = require_private_root(Path(os.environ["MMS_CONFIG_ROOT"]))
    payload_file = Path(sys.argv[1]).resolve()
    if payload_file.parent != root:
        raise ValueError("invalid launch payload path")
    payload = json.loads(payload_file.read_text(encoding="utf-8"))
    payload_file.unlink()
    # Redirect Python banners only. Keep OS fd 1 for the exec'ed Pi process.
    with contextlib.redirect_stdout(sys.stderr):
        import mms_launchers
        cli = str(payload.get("cli") or "pi").strip() or "pi"
        extra_args = list(payload["extraArgs"])
        if cli == "pi":
            import mms_pi_support
            btw_extension = mms_pi_support.pi_btw_extension_path(
                None, payload["runtime"], os.getcwd(), log=mms_launchers.console.print
            )
            if btw_extension:
                extra_args += ["--extension", btw_extension]
            extra_args += ["--extension", str(Path(__file__).parent / "extensions/web-controls.ts")]
        mms_launchers.launch_cli(cli, payload["modelInfo"], payload["runtime"], extra_args=extra_args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        from mms_web.runtime import private_json, require_private_root
        root = require_private_root(Path(os.environ["MMS_CONFIG_ROOT"]))
        private_json(root / "launch-error.json", {"type": type(exc).__name__, "traceback": traceback.format_exc()})
        print("MMS Pilot: 启动失败，请检查所选模型服务和本机执行工具安装。", file=sys.stderr)
        sys.exit(1)
