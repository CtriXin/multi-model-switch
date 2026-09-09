import argparse
import signal
import os
import webbrowser
from pathlib import Path

from .server import WebApplication, create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description="MMS Web — local conversations powered by MMS and Pi")
    from mms_version import VERSION
    parser.add_argument("--version", action="version", version=f"MMS Web {VERSION}")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config-root", type=Path,
                        help="Explicit MMS root; omitted means no config discovery")
    parser.add_argument("--state-root", type=Path,
                        default=Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "mms-web",
                        help="Directory for Web-owned config, sessions and runtime snapshots")
    parser.add_argument("--open", action="store_true", help="Open the local Web client in your browser")
    source = Path(__file__).resolve().parent.parent
    bundled = source / "mms_web_static"
    parser.add_argument("--static-root", type=Path, default=bundled if bundled.is_dir() else source / "apps/mms-web/dist")
    args = parser.parse_args(argv)
    root = args.state_root.expanduser().resolve()
    if args.config_root and not args.config_root.expanduser().is_dir():
        parser.error("--config-root must be an existing directory")
    if not (args.static_root / "index.html").is_file():
        parser.error("Web assets are missing. Reinstall MMS v4, or run npm run build --workspace @mms/web in the source checkout.")
    app = WebApplication(state_root=root, config_root=args.config_root)
    server = create_server(app, args.static_root, args.port)
    address = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"MMS Web: {address}", flush=True)
    if args.open:
        webbrowser.open(address)
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()


if __name__ == "__main__":
    main()
