"""Local read-only WebUI for MMS setup and configuration planning."""

from __future__ import annotations

import argparse
import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


_SECRET_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "gateway_key", "token", "secret"}


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _redact(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:3]}***{text[-3:]}"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _provider_summary(provider: dict[str, Any]) -> dict[str, Any]:
    provider = provider if isinstance(provider, dict) else {}
    protocols = provider.get("protocols") if isinstance(provider.get("protocols"), list) else []
    supported_clis = provider.get("supported_clis") if isinstance(provider.get("supported_clis"), list) else []
    models = []
    for key in ("models", "fallback_models", "extra_models"):
        values = provider.get(key)
        if isinstance(values, list):
            models.extend(str(item) for item in values if item)
        elif isinstance(values, dict):
            models.extend(str(item) for item in values.keys() if item)
    return {
        "id": _safe_text(provider.get("id")),
        "name": _safe_text(provider.get("name")),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": provider.get("priority", ""),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "auto"),
        "protocols": [str(item) for item in protocols if item],
        "supported_clis": [str(item) for item in supported_clis if item],
        "has_openai_base_url": bool(_safe_text(provider.get("openai_base_url") or provider.get("base_url"))),
        "has_anthropic_base_url": bool(_safe_text(provider.get("anthropic_base_url"))),
        "has_api_key": bool(_safe_text(provider.get("api_key") or provider.get("openai_api_key"))),
        "model_count": len(dict.fromkeys(models)),
    }


def _sanitized_mapping(payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if normalized.lower() in _SECRET_KEYS:
            result[normalized] = _redact(value)
        elif isinstance(value, dict):
            result[normalized] = _sanitized_mapping(value)
        elif isinstance(value, list):
            result[normalized] = [
                _sanitized_mapping(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[normalized] = value
    return result


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return a redacted, UI-friendly config snapshot; never mutates config."""
    cfg = cfg if isinstance(cfg, dict) else {}
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    provider_rows = [_provider_summary(item) for item in providers if isinstance(item, dict)]
    vision_sidecar = cfg.get("vision_sidecar") if isinstance(cfg.get("vision_sidecar"), dict) else {}
    rescue = cfg.get("rescue") if isinstance(cfg.get("rescue"), dict) else {}
    opencode = {
        "recommended_profile": "lite_pro_orchestrated",
        "vision_agents": ["mobius-vision-mimo", "mobius-vision-kimi", "mobius-vision-qwen"],
        "executor": "mobius-executor-gpt54",
        "release_gate": "mobius-reviewer-gpt55",
    }
    recommendations = []
    if not provider_rows:
        recommendations.append("Add at least one provider before configuring model and fallback policy.")
    if not vision_sidecar:
        recommendations.append("Configure vision_sidecar if text-only Claude bridge models should handle screenshots/images.")
    if not _safe_text(rescue.get("fallback_model")):
        recommendations.append("Configure rescue.fallback_model before enabling rescue hot fallback.")
    if not any(row.get("has_anthropic_base_url") for row in provider_rows):
        recommendations.append("Add an Anthropic /v1/messages route for cache-sensitive domestic models.")
    return {
        "schema": "mms.setup_web.snapshot.v1",
        "mode": "read_only",
        "command": command_name,
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
        },
        "providers": provider_rows,
        "vision_sidecar": _sanitized_mapping(vision_sidecar),
        "rescue": _sanitized_mapping(rescue),
        "opencode": opencode,
        "recommendations": recommendations,
        "snippets": build_config_snippets(),
    }


def build_config_snippets() -> dict[str, str]:
    """Manual snippets shown in WebUI; callers choose whether to apply."""
    vision = """# Manual config.toml snippet: vision sidecar
[vision_sidecar]
enabled = true
provider_id = \"mimo-direct-anthropic\"
model = \"mimo-v2.5\"

# Optional ordered fallbacks
[[vision_sidecar.candidates]]
provider_id = \"mimo-direct-anthropic\"
model = \"mimo-v2.5\"

[[vision_sidecar.candidates]]
provider_id = \"direct-kimi\"
model = \"K2.6\"

[[vision_sidecar.candidates]]
provider_id = \"direct-qwen\"
model = \"qwen3.6-plus\"
""".strip()
    rescue = """# Manual config.toml snippet: rescue fallback
[rescue]
fallback_model = \"deepseek-v4-flash\"
fallback_cli = \"codex\"
hot_fallback_enabled = false
""".strip()
    opencode = """# Launch examples
mms opencode --profile lite_pro_orchestrated
mms opencode --profile lite_pro_orchestrated_backend
mms opencode-smoke --profile lite_pro_orchestrated --health-summary
""".strip()
    return {"vision_sidecar": vision, "rescue": rescue, "opencode": opencode}


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    providers = snapshot.get("providers") or []
    lines = [
        "# MMS Setup Plan",
        "",
        f"- mode: `{snapshot.get('mode')}`",
        f"- config: `{snapshot.get('paths', {}).get('config') or '-'}`",
        f"- preferences: `{snapshot.get('paths', {}).get('preferences') or '-'}`",
        "",
        "## Providers",
    ]
    if providers:
        for item in providers:
            lines.append(
                "- `{id}` enabled={enabled} protocols={protocols} clis={clis} models={models}".format(
                    id=item.get("id") or "-",
                    enabled=item.get("enabled"),
                    protocols=",".join(item.get("protocols") or []) or "-",
                    clis=",".join(item.get("supported_clis") or []) or "-",
                    models=item.get("model_count", 0),
                )
            )
    else:
        lines.append("- No providers found.")
    lines.extend(["", "## Vision Sidecar", "", "```toml", snapshot.get("snippets", {}).get("vision_sidecar", ""), "```"])
    lines.extend(["", "## Rescue Fallback", "", "```toml", snapshot.get("snippets", {}).get("rescue", ""), "```"])
    lines.extend(["", "## OpenCode", "", "```bash", snapshot.get("snippets", {}).get("opencode", ""), "```"])
    recommendations = snapshot.get("recommendations") or []
    if recommendations:
        lines.extend(["", "## Recommendations"])
        lines.extend(f"- {item}" for item in recommendations)
    lines.extend([
        "",
        "## Safety",
        "- This WebUI is read-only in the current slice.",
        "- Do not auto-write real `~/.config/mms/**`; use backup + diff + human confirmation before applying changes.",
    ])
    return "\n".join(lines).strip() + "\n"


def _html_page(snapshot: dict[str, Any]) -> bytes:
    data = json.dumps(snapshot, ensure_ascii=False, indent=2)
    providers = snapshot.get("providers") or []
    provider_cards = []
    for item in providers:
        provider_cards.append(
            f"""
            <article class=\"card\">
              <h3>{html.escape(str(item.get('id') or '-'))}</h3>
              <p>{html.escape(str(item.get('name') or ''))}</p>
              <dl>
                <dt>Status</dt><dd>{'enabled' if item.get('enabled') else 'disabled'}</dd>
                <dt>Protocols</dt><dd>{html.escape(', '.join(item.get('protocols') or []) or '-')}</dd>
                <dt>CLIs</dt><dd>{html.escape(', '.join(item.get('supported_clis') or []) or '-')}</dd>
                <dt>Models</dt><dd>{int(item.get('model_count') or 0)}</dd>
              </dl>
            </article>
            """
        )
    if not provider_cards:
        provider_cards.append("<article class=\"card muted\">No providers detected yet.</article>")
    recommendations = "".join(f"<li>{html.escape(str(item))}</li>" for item in snapshot.get("recommendations") or [])
    if not recommendations:
        recommendations = "<li>No blocking recommendations.</li>"
    snippets = snapshot.get("snippets") or {}
    page = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>MMS Setup</title>
  <style>
    :root {{ --ink:#18211f; --muted:#66736f; --paper:#fbf7ef; --card:#fffdfa; --line:#ded5c5; --accent:#1f7a5a; --accent2:#d97706; }}
    body {{ margin:0; font-family: ui-serif, Georgia, 'Times New Roman', serif; color:var(--ink); background:radial-gradient(circle at 20% 0%, #e0f2df, transparent 32rem), linear-gradient(135deg, #fbf7ef, #edf5ee); }}
    header {{ padding:48px 6vw 24px; }}
    h1 {{ margin:0; font-size:clamp(36px, 7vw, 76px); line-height:.9; letter-spacing:-0.05em; }}
    header p {{ max-width:760px; color:var(--muted); font-size:18px; }}
    main {{ padding:0 6vw 56px; display:grid; gap:24px; }}
    section {{ background:rgba(255,253,250,.82); border:1px solid var(--line); border-radius:24px; padding:24px; box-shadow:0 18px 55px rgba(61,50,35,.08); }}
    h2 {{ margin:0 0 16px; font-size:24px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:16px; }}
    .card {{ border:1px solid var(--line); border-radius:18px; padding:16px; background:var(--card); }}
    .muted {{ color:var(--muted); }}
    dl {{ display:grid; grid-template-columns:90px 1fr; gap:6px 12px; margin:0; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; }}
    pre {{ overflow:auto; background:#17211d; color:#e8f5e9; border-radius:18px; padding:18px; }}
    a.button {{ display:inline-block; background:var(--accent); color:white; text-decoration:none; border-radius:999px; padding:10px 16px; margin-right:8px; }}
    .pill {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:6px 10px; color:var(--muted); }}
  </style>
</head>
<body>
  <header>
    <span class=\"pill\">read-only setup preview</span>
    <h1>MMS Setup</h1>
    <p>Inspect providers, vision sidecar, rescue fallback, and OpenCode presets. This first slice generates a plan only; it does not write real ~/.config/mms files.</p>
    <a class=\"button\" href=\"/setup.md\">Download setup.md</a>
    <a class=\"button\" href=\"/api/snapshot\">View JSON</a>
  </header>
  <main>
    <section><h2>Providers</h2><div class=\"grid\">{''.join(provider_cards)}</div></section>
    <section><h2>Recommendations</h2><ul>{recommendations}</ul></section>
    <section><h2>Vision Sidecar</h2><pre>{html.escape(snippets.get('vision_sidecar', ''))}</pre></section>
    <section><h2>Rescue Fallback</h2><pre>{html.escape(snippets.get('rescue', ''))}</pre></section>
    <section><h2>OpenCode Presets</h2><pre>{html.escape(snippets.get('opencode', ''))}</pre></section>
    <section><h2>Redacted Snapshot</h2><pre>{html.escape(data)}</pre></section>
  </main>
</body>
</html>"""
    return page.encode("utf-8")


class _SetupWebHandler(BaseHTTPRequestHandler):
    snapshot: dict[str, Any] = {}

    def log_message(self, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            self._send(200, _html_page(self.snapshot), "text/html; charset=utf-8")
            return
        if path == "/api/snapshot":
            body = json.dumps(self.snapshot, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/setup.md":
            self._send(200, build_setup_markdown(self.snapshot).encode("utf-8"), "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")


def serve_config_web(snapshot: dict[str, Any], *, host: str, port: int, open_browser: bool = True) -> str:
    handler = type("MMSSetupWebHandler", (_SetupWebHandler,), {"snapshot": snapshot})
    server = ThreadingHTTPServer((host, int(port)), handler)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mms-setup-web")
    thread.start()
    print(f"MMS setup WebUI: {url}")
    print("Read-only preview. Press Ctrl-C to stop.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping MMS setup WebUI.")
    finally:
        server.shutdown()
        server.server_close()
    return url


def run_config_web(
    cfg: dict[str, Any] | None,
    argv: list[str] | None = None,
    *,
    command_name: str = "mms",
    config_path: str = "",
    preferences_path: str = "",
) -> int:
    parser = argparse.ArgumentParser(prog=f"{command_name} config web", description="Start the local read-only MMS setup WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; default 127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Bind port; default 0 chooses a free port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--print-summary", action="store_true", help="Print redacted setup JSON and exit")
    parser.add_argument("--print-markdown", action="store_true", help="Print setup markdown and exit")
    args = parser.parse_args(argv or [])
    snapshot = build_config_snapshot(
        cfg,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    if args.print_summary:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.print_markdown:
        print(build_setup_markdown(snapshot), end="")
        return 0
    serve_config_web(snapshot, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0
