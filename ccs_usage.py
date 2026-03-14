"""mms usage — 各账号/Provider 用量查询。

支持:
  - Claude OAuth 账号 → Anthropic /api/oauth/usage (5h/7d 利用率)
  - Codex  OAuth 账号 → JWT 解码出 plan 类型 + 有效期（OpenAI 无公开利用率 API）
  - 本地 MMS 启动统计 → ~/.config/ccs/usage.json
"""
import asyncio
import base64
import json
import os
import subprocess
from datetime import datetime, timezone

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
except ImportError:
    raise SystemExit("缺少 rich，请执行: pip install rich")

console = Console()

_CONFIG_DIRS = [
    os.path.expanduser("~/.config/mms"),
    os.path.expanduser("~/.config/ccs"),
]


def _active_usage_path() -> str | None:
    for d in _CONFIG_DIRS:
        p = os.path.join(d, "usage.json")
        if os.path.exists(p):
            return p
    return None


# ─── Token helpers ────────────────────────────────────────────────────────────

def _keychain_claude_token() -> tuple[str | None, str | None]:
    """Returns (access_token, email) from macOS Keychain 'Claude Code-credentials'."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None, None
        data = json.loads(r.stdout.strip())
        oauth = data.get("claudeAiOauth") or {}
        return oauth.get("accessToken"), oauth.get("emailAddress")
    except Exception:
        return None, None


def _file_claude_token(home_dir: str) -> tuple[str | None, str | None]:
    """Read Claude token from <home_dir>/.claude.json. Returns (token, email)."""
    if not home_dir:
        return None, None
    path = os.path.join(os.path.expanduser(home_dir), ".claude.json")
    try:
        data = json.loads(open(path).read())
        oauth = data.get("claudeAiOauth") or {}
        return oauth.get("accessToken"), oauth.get("emailAddress")
    except Exception:
        return None, None


def _decode_jwt(token: str) -> dict:
    """JWT payload decode (no verification)."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def _codex_auth_data(home_dir: str | None) -> dict | None:
    """Read Codex auth.json from home_dir or ~/.codex."""
    candidates = []
    if home_dir:
        candidates.append(os.path.join(os.path.expanduser(home_dir), ".codex", "auth.json"))
    candidates.append(os.path.expanduser("~/.codex/auth.json"))
    for p in candidates:
        if os.path.exists(p):
            try:
                return json.loads(open(p).read())
            except Exception:
                pass
    return None


# ─── API calls ────────────────────────────────────────────────────────────────

async def _anthropic_usage(token: str) -> dict | None:
    if not _httpx:
        return None
    try:
        async with _httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.anthropic.com/api/oauth/usage",
                headers={"Authorization": f"Bearer {token}",
                         "anthropic-beta": "oauth-2025-04-20"},
            )
            if r.status_code == 200:
                return r.json()
            console.print(f"[dim]Anthropic usage API → HTTP {r.status_code}[/dim]")
    except Exception as e:
        console.print(f"[dim]Anthropic usage API 异常: {e}[/dim]")
    return None


# ─── Formatters ───────────────────────────────────────────────────────────────

def _pct(v) -> str:
    if v is None:
        return "—"
    f = float(v)
    s = f"{f:.0f}%"
    if f >= 90:
        return f"[red]{s}[/red]"
    if f >= 70:
        return f"[yellow]{s}[/yellow]"
    return f"[green]{s}[/green]"


def _reset(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta_h = (dt - now).total_seconds() / 3600
        if delta_h < 0:
            return "已过期"
        if delta_h < 24:
            return f"{delta_h:.1f}h 后"
        return f"{delta_h/24:.1f}d 后"
    except Exception:
        return ts[:16]


def _short_date(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ts[:10]


# ─── Sections ─────────────────────────────────────────────────────────────────

async def _section_claude(accounts: list[dict]) -> None:
    claude_accs = [a for a in accounts
                   if a.get("cli") == "claude" and a.get("auth_mode") == "oauth"
                   and a.get("enabled", True)]
    if not claude_accs:
        return

    table = Table(title="Claude Plan Usage  (Anthropic OAuth)", border_style="cyan",
                  show_lines=False)
    table.add_column("账号", style="bold", no_wrap=True)
    table.add_column("Email", style="dim")
    table.add_column("5h 利用", justify="right")
    table.add_column("5h 重置")
    table.add_column("7d 利用", justify="right")
    table.add_column("7d Sonnet", justify="right")
    table.add_column("7d 重置")
    table.add_column("状态", style="dim")

    # keychain token (current active)
    kc_token, kc_email = _keychain_claude_token()
    kc_used = False

    async def _row(acc) -> tuple:
        nonlocal kc_used
        name = acc["id"] + (f" / {acc['name']}" if acc.get("name") else "")
        token, email = _file_claude_token(acc.get("home_dir", ""))
        src = "file"
        if not token and not kc_used:
            token, email = kc_token, kc_email
            src = "keychain"
            kc_used = True

        if not token:
            return (name, "—", "—", "—", "—", "—", "—", "无 token")

        usage = await _anthropic_usage(token)
        if usage is None:
            return (name, email or "—", "—", "—", "—", "—", "—", "[red]API 失败[/red]")

        fh = usage.get("five_hour") or {}
        sd = usage.get("seven_day") or {}
        ss = usage.get("seven_day_sonnet") or {}
        return (
            name,
            email or "—",
            _pct(fh.get("utilization")),
            _reset(fh.get("resets_at")),
            _pct(sd.get("utilization")),
            _pct(ss.get("utilization")),
            _reset(sd.get("resets_at")),
            src,
        )

    rows = await asyncio.gather(*[_row(a) for a in claude_accs])
    for r in rows:
        table.add_row(*r)
    console.print(table)


def _section_codex(accounts: list[dict]) -> None:
    codex_accs = [a for a in accounts
                  if a.get("cli") == "codex" and a.get("auth_mode") == "oauth"
                  and a.get("enabled", True)]
    if not codex_accs:
        return

    table = Table(title="Codex Plan Info  (OpenAI OAuth — 无利用率 API)", border_style="blue",
                  show_lines=False)
    table.add_column("账号", style="bold", no_wrap=True)
    table.add_column("Email", style="dim")
    table.add_column("Plan")
    table.add_column("到期日")
    table.add_column("状态")

    seen_default = False
    for acc in codex_accs:
        name = acc["id"] + (f" / {acc['name']}" if acc.get("name") else "")
        home = acc.get("home_dir", "")
        auth = _codex_auth_data(home)

        # fallback: try ~/.codex/auth.json once
        if auth is None and not seen_default:
            auth = _codex_auth_data(None)
            seen_default = True

        if not auth:
            table.add_row(name, "—", "—", "—", "[dim]无 auth.json[/dim]")
            continue

        tokens = auth.get("tokens") or {}
        raw = tokens.get("access_token") or tokens.get("id_token", "")
        if not raw:
            table.add_row(name, "—", "—", "—", "[dim]无 token[/dim]")
            continue

        payload = _decode_jwt(raw)
        oai = payload.get("https://api.openai.com/auth") or {}
        profile = payload.get("https://api.openai.com/profile") or {}

        plan = oai.get("chatgpt_plan_type", "—")
        email = profile.get("email", "—")
        active_until = oai.get("chatgpt_subscription_active_until", "")

        # check expiry
        exp = payload.get("exp")
        if exp and exp < datetime.now(timezone.utc).timestamp():
            status = "[red]token 已过期[/red]"
        else:
            status = "[green]有效[/green]"

        table.add_row(name, email, plan, _short_date(active_until), status)

    console.print(table)


def _section_local_stats() -> None:
    path = _active_usage_path()
    if not path:
        return

    try:
        stats = json.loads(open(path).read()).get("sources", {})
    except Exception:
        return

    if not stats:
        return

    table = Table(title="MMS 本地启动统计", border_style="dim", show_lines=False)
    table.add_column("来源", style="bold")
    table.add_column("CLI", style="dim")
    table.add_column("启动", justify="right")
    table.add_column("最后使用")
    table.add_column("最后模型", style="dim")

    for _, s in sorted(stats.items(),
                       key=lambda kv: kv[1].get("last_used_at", ""),
                       reverse=True):
        label = s.get("id", "?")
        if s.get("name") and s["name"] != label:
            label += f" / {s['name']}"
        last = (s.get("last_used_at") or "")[:10]
        model = (s.get("last_model") or "—")[:35]
        table.add_row(label, s.get("cli", "?"), str(s.get("launches", 0)), last, model)

    console.print(table)


# ─── Public entry ─────────────────────────────────────────────────────────────

def usage_main(cfg: dict) -> None:
    accounts = cfg.get("accounts", [])
    asyncio.run(_section_claude(accounts))
    _section_codex(accounts)
    _section_local_stats()
