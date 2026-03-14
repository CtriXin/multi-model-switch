"""mms usage — 各账号/Provider 用量查询。

支持:
  - Claude OAuth 账号 → Anthropic /api/oauth/usage (5h/7d 利用率)
  - Codex  OAuth 账号 → JWT 解码出 plan 类型 + 有效期（OpenAI 无公开利用率 API）
  - API Key 厂商     → Kimi codingplan key 校验 / GLM·CN|EN key 校验 / Minimax·CN|EN key 校验
  - 本地 MMS 启动统计 → ~/.config/ccs/usage.json

API key 环境变量（在 shell 里 export 后运行 mms usage）:
  MMS_KIMI_KEY      Kimi — coding plan key (sk-kimi-*), endpoint: api.kimi.com/coding/v1
  MMS_GLM_KEY       智谱 GLM — key 校验，CN + EN 双端点
  MMS_MINIMAX_KEY   Minimax — key 校验，CN + EN 双端点
  MMS_BAILIAN_KEY   阿里百炼 — key 校验（无公开余额 API）
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

    # Build token pool: keychain (current active) + all cached tokens
    from ccs_account_state import load_cached_claude_tokens
    kc_token, kc_email = _keychain_claude_token()
    cached_tokens: list[dict] = load_cached_claude_tokens()
    # Deduplicate: keyed by accessToken prefix
    _seen_tokens: set[str] = set()
    _token_pool: list[dict] = []
    for oauth in ([{"accessToken": kc_token, "emailAddress": kc_email}]
                  if kc_token else []) + cached_tokens:
        tok = (oauth.get("accessToken") or "")[:20]
        if tok and tok not in _seen_tokens:
            _seen_tokens.add(tok)
            _token_pool.append(oauth)

    _pool_used: list[bool] = [False] * len(_token_pool)

    def _pick_token(acc_name: str) -> tuple[str | None, str | None, str]:
        """Return (token, email, source) for this account.
        First match by home_dir file, then first unused pool token."""
        # 1. Try account-specific file
        home = next(
            (a.get("home_dir", "") for a in accounts if a.get("id") == acc_name), ""
        )
        token, email = _file_claude_token(home)
        if token:
            return token, email, "file"
        # 2. First unused pool token
        for i, oauth in enumerate(_token_pool):
            if not _pool_used[i]:
                _pool_used[i] = True
                return oauth.get("accessToken"), oauth.get("emailAddress"), "cached"
        return None, None, "—"

    async def _row(acc) -> tuple:
        name = acc["id"] + (f" / {acc['name']}" if acc.get("name") else "")
        token, email, src = _pick_token(acc["id"])

        if not token:
            return (name, "—", "—", "—", "—", "—", "—", "[dim]无 token[/dim]")

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


# ─── Provider API-key / codingplan balance/check ─────────────────────────────
#
# check_type per endpoint:
#   "balance"   GET balance_path → show ¥ amount
#   "models"       GET /v1/models (OpenAI-compat)
#   "models_kimi"  GET /models  (Kimi coding plan — path is /models not /v1/models)
#   "glm"          GET /api/paas/v4/models  (GLM-specific path)
#   "chat_mini"    POST /v1/text/chatcompletion_v2 (Minimax — no models endpoint)
#
# Entry format: (display_name, env_var, [(region, base_url, check_type, extra_path, key_prefix)])
# key_prefix: only run this endpoint if the key starts with this prefix; None = always run
_PROVIDER_DEFS = [
    (
        "Kimi (Moonshot)",
        "MMS_KIMI_KEY",
        [
            # sk-kimi-* → Coding Plan endpoint (api.kimi.com/coding/v1)
            ("CodingPlan", "https://api.kimi.com/coding/v1", "models_kimi", None, "sk-kimi-"),
            # other keys → standard API (api.moonshot.cn), shows balance
            ("API",        "https://api.moonshot.cn",        "balance",     "/v1/users/me/balance", None),
        ],
    ),
    (
        "GLM (智谱)",
        "MMS_GLM_KEY",
        [
            ("CN", "https://open.bigmodel.cn", "glm",     None, None),
            ("EN", "https://api.bigmodel.cn",  "glm",     None, None),
        ],
    ),
    (
        "Minimax",
        "MMS_MINIMAX_KEY",
        [
            # Minimax has no /v1/models — validate via a lightweight chat probe
            ("CN", "https://api.minimax.chat",  "chat_mini", None, None),
            ("EN", "https://api.minimaxi.chat", "chat_mini", None, None),
        ],
    ),
    (
        "百炼 (DashScope)",
        "MMS_BAILIAN_KEY",
        [
            # sk-sp- coding plan keys use coding.dashscope endpoint
            # /v1/models returns 404; validate via a chat probe (400=key ok, 401=key invalid)
            ("CN", "https://coding.dashscope.aliyuncs.com", "chat_probe", None, None),
        ],
    ),
]


async def _check_provider_endpoint(
    key: str, base_url: str, check_type: str, extra_path: str | None
) -> tuple[str, str]:
    """Returns (status_label, detail)."""
    if not _httpx:
        return "N/A", "缺少 httpx"
    h = {"Authorization": f"Bearer {key}"}
    try:
        async with _httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
            if check_type == "balance":
                r = await c.get(base_url + extra_path, headers=h)
                if r.status_code == 200:
                    d = r.json()
                    data = d.get("data") or d
                    avail = (data.get("available_balance") or data.get("balance")
                             or data.get("total"))
                    if avail is not None:
                        return "余额", f"¥{float(avail):.2f}"
                    return "有效", r.text[:40]
                return "无效", f"HTTP {r.status_code}"

            elif check_type == "glm":
                r = await c.get(base_url + "/api/paas/v4/models", headers=h)
                if r.status_code == 200:
                    try:
                        n = len(r.json().get("data", []))
                        return "有效", f"{n} 个模型" if n else "有效"
                    except Exception:
                        return "有效", ""
                return "无效", f"HTTP {r.status_code}"

            elif check_type == "models":
                r = await c.get(base_url + "/v1/models", headers=h)
                if r.status_code == 200:
                    n = len((r.json()).get("data", []))
                    return "有效", f"{n} 个模型" if n else ""
                return "无效", f"HTTP {r.status_code}"

            elif check_type == "models_kimi":
                # Kimi coding plan: /models (not /v1/models)
                r = await c.get(base_url + "/models", headers=h)
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    names = [m.get("id", "") for m in models[:3]]
                    return "有效", ", ".join(names) if names else "codingplan ✓"
                if r.status_code == 401:
                    return "无效", "认证失败"
                return "无效", f"HTTP {r.status_code}"

            elif check_type == "chat_mini":
                # Minimax has no models endpoint; probe with a minimal chat call
                _MINIMAX_MODELS = "MiniMax-Text-01, MiniMax-M1, abab6.5s"
                r = await c.post(
                    base_url + "/v1/text/chatcompletion_v2",
                    headers={**h, "Content-Type": "application/json"},
                    json={"model": "MiniMax-Text-01",
                          "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 1},
                )
                if r.status_code == 200:
                    body = r.json()
                    base_resp = body.get("base_resp") or {}
                    code = base_resp.get("status_code", 0)
                    # 2049 = invalid key; 0 = ok; other errors = ok for auth
                    if code == 2049:
                        return "无效", "key 被拒"
                    return "有效", _MINIMAX_MODELS
                return "无效", f"HTTP {r.status_code}"

            elif check_type == "chat_probe":
                # Generic: send a chat request; 401 = bad key, anything else = key ok
                _BAILIAN_MODELS = "qwen-plus, qwen-turbo, qwen-max"
                r = await c.post(
                    base_url + "/v1/chat/completions",
                    headers={**h, "Content-Type": "application/json"},
                    json={"model": "_probe", "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 1},
                )
                if r.status_code == 401:
                    return "无效", "认证失败"
                if r.status_code in (400, 404, 422):
                    return "有效", _BAILIAN_MODELS
                if r.status_code == 200:
                    return "有效", _BAILIAN_MODELS
                return "无效", f"HTTP {r.status_code}"

            return "N/A", check_type

    except _httpx.TimeoutException:
        return "超时", ""
    except Exception as e:
        return "错误", str(e)[:40]


async def _section_providers_async() -> None:
    tasks: list = []
    meta: list[tuple[str, str]] = []  # (provider_name, region)

    for pname, env, endpoints in _PROVIDER_DEFS:
        key = os.environ.get(env, "").strip()
        if not key:
            continue
        for region, base_url, check_type, extra_path, key_prefix in endpoints:
            if key_prefix and not key.startswith(key_prefix):
                continue
            tasks.append(_check_provider_endpoint(key, base_url, check_type, extra_path))
            meta.append((pname, region))

    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build rows and auto-suppress failing regions when at least one region succeeds
    _VALID_STATUSES = {"余额", "有效"}
    rows: list[tuple[str, str, str, str]] = []  # (pname, region, status, detail)
    for (pname, region), res in zip(meta, results):
        if isinstance(res, Exception):
            status, detail = "错误", str(res)[:40]
        else:
            status, detail = res
        rows.append((pname, region, status, detail))

    # Per-provider: if any row is valid, hide the invalid/error ones (CN key shown as CN-only)
    valid_providers: set[str] = {pname for pname, _, status, _ in rows if status in _VALID_STATUSES}

    table = Table(title="第三方厂商账号", border_style="magenta", show_lines=False)
    table.add_column("厂商", style="bold")
    table.add_column("区域")
    table.add_column("状态")
    table.add_column("详情", style="dim")

    for pname, region, status, detail in rows:
        if pname in valid_providers and status not in _VALID_STATUSES:
            continue  # hide failing regions when another region is valid
        color = {
            "余额": "green", "有效": "green",
            "无效": "red", "超时": "yellow", "错误": "red",
        }.get(status, "dim")
        table.add_row(pname, region, f"[{color}]{status}[/{color}]", detail)

    console.print(table)


def _section_providers() -> None:
    asyncio.run(_section_providers_async())


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
    # Always cache the currently-active keychain token on each run,
    # so it's available for future runs even after account switching.
    from ccs_account_state import cache_current_claude_token
    cache_current_claude_token()

    accounts = cfg.get("accounts", [])
    asyncio.run(_section_claude(accounts))
    _section_codex(accounts)
    _section_providers()
    _section_local_stats()
