import argparse
import signal
import os
import webbrowser
from pathlib import Path

from .server import WebApplication, create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description="MMS Pilot — local conversations powered by MMS and Pi")
    from mms_version import VERSION
    parser.add_argument("--version", action="version", version=f"MMS Pilot {VERSION}")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config-root", type=Path,
                        help="Explicit MMS root; omitted means no config discovery")
    parser.add_argument("--state-root", type=Path,
                        default=Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "mms-web",
                        help="Directory for Web-owned config, sessions and runtime snapshots")
    parser.add_argument("--open", action="store_true", help="Open the local Web client in your browser")
    parser.add_argument("--listen", choices=("loopback", "lan", "all"), default="loopback",
                        help="loopback (default, this machine only), lan (this machine's own "
                             "network address), or all (every interface). Anything but loopback "
                             "requires the access token printed at startup.")
    parser.add_argument("--hostname", action="append", default=[], metavar="HOST",
                        help="A public hostname this server answers to, for example one "
                             "fronted by a tunnel. Repeatable.")
    source = Path(__file__).resolve().parent.parent
    bundled = source / "mms_web_static"
    parser.add_argument("--static-root", type=Path, default=bundled if bundled.is_dir() else source / "apps/mms-web/dist")
    args = parser.parse_args(argv)
    from .install_lock import acquire_runtime_lease
    install_lease = acquire_runtime_lease(source)
    os.environ.setdefault('MMS_WEB_INSTALL_ROOT', str(source))
    from .update_activation import redirect_active, acquire_state_lock
    redirect_active(args, source)
    root = args.state_root.expanduser().resolve()
    if args.config_root and not args.config_root.expanduser().is_dir():
        parser.error("--config-root must be an existing directory")
    if not (args.static_root / "index.html").is_file():
        parser.error("Web assets are missing. Reinstall MMS v4, or run npm run build --workspace @mms/web in the source checkout.")
    lease = acquire_state_lock(root)
    config_root = args.config_root
    if config_root is None:
        from .runtime import default_config_root

        config_root = default_config_root(root)
    app = WebApplication(state_root=root, config_root=config_root,
                         listen=args.listen, hostnames=tuple(args.hostname))
    server = create_server(app, args.static_root, args.port)
    port = server.server_address[1]
    address = f"http://127.0.0.1:{port}"
    print(f"MMS Pilot: {address}", flush=True)
    if app.access.required:
        # Say plainly what is reachable and print the one link that opens it.
        # A phone gets in by following this and nothing else.
        where = {"lan": "本机局域网地址", "all": "所有网络接口"}[app.access.mode]
        print(f"  已开放：{where}。带 token 的链接才能访问，token 存在 "
              f"{root / 'remote-access-token'}", flush=True)
        print(f"  手机打开：{app.access.link(port)}", flush=True)
    else:
        print("  仅本机可访问，未监听任何对外地址。", flush=True)
    from .update_coordinator import UpdateCoordinator
    app.updates.coordinator = UpdateCoordinator(app, server, source, args.static_root)
    app.updates.start_scheduler()
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
        try:
            app.close()
        finally:
            os.close(lease)
            os.close(install_lease)
            if app.pending_handoff:
                Path(app.pending_handoff["armed"]).touch(mode=0o600)


if __name__ == "__main__":
    main()
