"""Runtime network and proxy helpers for MMS launchers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit


CLAUDE_PROXY_GUARD_TARGETS = [
    ("api", "https://api.anthropic.com"),
    ("site", "https://claude.ai"),
    ("auth", "https://anthropic.auth0.com"),
]
CLAUDE_NO_PROXY_TOKENS = (
    "*",
    "anthropic.com",
    "api.anthropic.com",
    "claude.ai",
    "claude.com",
    "clau.de",
    "anthropic.auth0.com",
)
PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
NO_PROXY_KEYS = ("NO_PROXY", "no_proxy")
FAKE_STATE_KEYS = (
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)
CA_KEYS = ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def mask_secret(value, *, keep=2):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * max(2, len(text) - keep)


def mask_proxy_url(proxy_url, *, mask_secret_fn=mask_secret):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return ""
    try:
        parsed = urlsplit(proxy_url)
    except Exception:
        return proxy_url
    try:
        parsed_port = parsed.port
    except ValueError:
        return proxy_url
    username = parsed.username or ""
    password = parsed.password or ""
    host = parsed.hostname or ""
    port = f":{parsed_port}" if parsed_port else ""
    auth = ""
    if username:
        auth = mask_secret_fn(username)
        if password:
            auth += ":****"
        auth += "@"
    netloc = f"{auth}{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", parsed.query or "", parsed.fragment or ""))


def runtime_network_summary(
    runtime,
    *,
    mask_proxy_url_fn,
    runtime_force_ipv4_fn,
    fake_upstream_enabled_fn,
    proxy_dns_mode_fn,
    runtime_locale_env_fn,
    default_account_timezone,
):
    proxy_url = mask_proxy_url_fn(runtime.get("proxy", ""))
    timezone_name = str(runtime.get("timezone") or default_account_timezone).strip() or default_account_timezone
    ipv4_label = "on" if runtime_force_ipv4_fn(runtime) else "off"
    dns_mode = "fake-local" if fake_upstream_enabled_fn() else proxy_dns_mode_fn(runtime.get("proxy", ""))
    locale_value = runtime_locale_env_fn(runtime).get("LANG", "en_US.UTF-8")
    parts = [f"DNS {dns_mode}", f"TZ {timezone_name}", f"LANG {locale_value}", f"IPv4 {ipv4_label}"]
    if proxy_url:
        parts.insert(0, f"Proxy {proxy_url}")
    else:
        parts.insert(0, "Proxy direct")
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if no_proxy:
        parts.append("NO_PROXY set")
    return " | ".join(parts)


def apply_runtime_ip_stack_profile(env, runtime, *, runtime_force_ipv4_fn):
    if not runtime_force_ipv4_fn(runtime):
        return env
    env["MMS_FORCE_IPV4"] = "1"
    existing = str(env.get("NODE_OPTIONS") or "").strip()
    token = "--dns-result-order=ipv4first"
    if token not in existing.split():
        env["NODE_OPTIONS"] = f"{existing} {token}".strip()
    return env


def apply_proxy_env(env, proxy_url, no_proxy=""):
    proxy_url = str(proxy_url or "").strip()
    no_proxy = str(no_proxy or "").strip()
    if not proxy_url:
        return env
    for key in PROXY_KEYS:
        env[key] = proxy_url
    for key in NO_PROXY_KEYS:
        env[key] = no_proxy
    return env


def proxy_dns_mode(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        scheme = (urlsplit(proxy_url).scheme or "").lower()
    except Exception:
        scheme = ""
    if scheme == "socks5h":
        return "remote"
    if scheme == "socks5":
        return "local-risk"
    if scheme in {"http", "https"}:
        return "proxy-likely"
    return scheme or "proxy"


def split_no_proxy_values(no_proxy):
    raw = str(no_proxy or "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def claude_no_proxy_conflicts(no_proxy, *, no_proxy_tokens=CLAUDE_NO_PROXY_TOKENS):
    values = split_no_proxy_values(no_proxy)
    conflicts = []
    for item in values:
        normalized = item.lstrip(".")
        if normalized in no_proxy_tokens:
            conflicts.append(item)
            continue
        for token in no_proxy_tokens:
            if token == "*":
                continue
            if normalized == token or normalized.endswith(f".{token}"):
                conflicts.append(item)
                break
    return sorted(set(conflicts))


def run_proxy_probe(
    proxy_url,
    target_url,
    *,
    no_proxy="",
    force_ipv4=True,
    resolve_ip=False,
    fake_upstream_enabled_fn,
    fake_proxy_probe_fn,
    which_fn=shutil.which,
    subprocess_run=subprocess.run,
):
    proxy_url = str(proxy_url or "").strip()
    if fake_upstream_enabled_fn():
        return fake_proxy_probe_fn(
            target_url,
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=resolve_ip,
        )
    curl_bin = which_fn("curl")
    if not curl_bin:
        return {"ok": False, "detail": "curl missing", "http_code": "", "body": ""}
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        "8",
        "--proxy",
        proxy_url,
        target_url,
    ]
    if resolve_ip:
        cmd.extend(["--output", "-"])
    else:
        cmd.extend(["--head", "--output", "/dev/null", "--write-out", "%{http_code}"])
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess_run(cmd, capture_output=True, text=True)
    body = str(result.stdout or "").strip()
    http_code = body if not resolve_ip else ""
    detail = str(result.stderr or "").strip()
    ok = result.returncode == 0
    if not resolve_ip:
        ok = ok and bool(http_code) and http_code not in {"000", "407"}
        if http_code and http_code not in {"000"}:
            detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    return {
        "ok": ok,
        "detail": detail[:200] + ("..." if len(detail) > 200 else ""),
        "http_code": http_code,
        "body": body[:200],
    }


def base_claude_network_guard(
    runtime,
    *,
    require_proxy=False,
    runtime_force_ipv4_fn,
    fake_upstream_enabled_fn,
    proxy_fingerprint_fn,
    proxy_dns_mode_fn,
    claude_no_proxy_conflicts_fn,
):
    runtime = dict(runtime or {})
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    force_ipv4 = bool(runtime_force_ipv4_fn(runtime))
    dns_mode = proxy_dns_mode_fn(proxy_url)
    fake_enabled = bool(fake_upstream_enabled_fn())
    return {
        "proxy_required": bool(require_proxy),
        "proxy_present": bool(proxy_url),
        "proxy_fingerprint": proxy_fingerprint_fn(proxy_url),
        "dns_mode": "fake-local" if fake_enabled else dns_mode,
        "force_ipv4": force_ipv4,
        "no_proxy": no_proxy,
        "no_proxy_conflicts": claude_no_proxy_conflicts_fn(no_proxy),
        "targets": [],
        "ipv4_egress": "-",
        "ipv6_egress": "blocked" if force_ipv4 else "unknown",
        "status": "ok",
        "block_reason": "",
        "fake_upstream": fake_enabled,
        "proxy_validation": "skipped_fake" if fake_enabled else "pending",
    }


def claude_network_guard_cache_key(runtime, require_proxy, *, runtime_force_ipv4_fn, fake_upstream_enabled_fn):
    runtime = dict(runtime or {})
    return (
        str(runtime.get("id") or runtime.get("name") or "").strip(),
        str(runtime.get("proxy") or "").strip(),
        str(runtime.get("no_proxy") or "").strip(),
        bool(runtime_force_ipv4_fn(runtime)),
        bool(require_proxy),
        bool(fake_upstream_enabled_fn()),
    )


def get_claude_network_guard_preview(
    runtime,
    *,
    require_proxy=False,
    cache,
    ttl_sec,
    perf_counter_fn,
    cache_key_fn,
    base_guard_fn,
):
    cache_key = cache_key_fn(runtime, require_proxy)
    cached = cache.get(cache_key)
    now = perf_counter_fn()
    if cached and now - float(cached.get("ts", 0.0) or 0.0) < ttl_sec:
        return dict(cached.get("guard") or {})
    return base_guard_fn(runtime, require_proxy=require_proxy)


def build_claude_network_guard(
    runtime,
    *,
    require_proxy=False,
    cache,
    ttl_sec,
    perf_counter_fn,
    cache_key_fn,
    base_guard_fn,
    runtime_force_ipv4_fn,
    fake_upstream_enabled_fn,
    run_proxy_probe_fn,
    guard_targets=CLAUDE_PROXY_GUARD_TARGETS,
):
    runtime = dict(runtime or {})
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    force_ipv4 = bool(runtime_force_ipv4_fn(runtime))
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    cache_key = cache_key_fn(runtime, require_proxy)
    cached = cache.get(cache_key)
    now = perf_counter_fn()
    if cached and now - float(cached.get("ts", 0.0) or 0.0) < ttl_sec:
        return dict(cached.get("guard") or {})
    guard = base_guard_fn(runtime, require_proxy=require_proxy)
    if require_proxy and not proxy_url:
        guard["status"] = "blocked"
        if auth_mode == "oauth":
            guard["block_reason"] = "BYPASS 启动要求当前 Claude 官方账号必须配置 proxy"
        else:
            guard["block_reason"] = "敏感 Claude provider 的 BYPASS 启动要求当前通道配置 proxy"
        cache[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if guard["no_proxy_conflicts"]:
        guard["status"] = "blocked"
        guard["block_reason"] = "NO_PROXY 命中了 Claude 域名，存在直连泄漏风险"
        cache[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if not proxy_url:
        cache[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if fake_upstream_enabled_fn():
        guard["proxy_validation"] = "skipped_fake"
        guard["block_reason"] = "fake upstream 模式下已跳过真实 proxy / egress 校验"
        cache[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard

    failed_targets = []
    for label, url in guard_targets:
        probe = run_proxy_probe_fn(
            proxy_url or "http://127.0.0.1:0",
            url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
        )
        guard["targets"].append(
            {
                "label": label,
                "url": url,
                "ok": bool(probe.get("ok")),
                "detail": probe.get("detail", ""),
            }
        )
        if not probe.get("ok"):
            failed_targets.append(label)

    ipv4_probe = run_proxy_probe_fn(
        proxy_url or "http://127.0.0.1:0",
        "https://api4.ipify.org",
        no_proxy=no_proxy,
        force_ipv4=True,
        resolve_ip=True,
    )
    if ipv4_probe.get("ok") and ipv4_probe.get("body"):
        guard["ipv4_egress"] = ipv4_probe["body"]
    if not force_ipv4:
        ipv6_probe = run_proxy_probe_fn(
            proxy_url or "http://127.0.0.1:0",
            "https://api6.ipify.org",
            no_proxy=no_proxy,
            force_ipv4=False,
            resolve_ip=True,
        )
        if ipv6_probe.get("ok") and ipv6_probe.get("body"):
            guard["ipv6_egress"] = ipv6_probe["body"]

    if failed_targets:
        guard["status"] = "blocked"
        guard["block_reason"] = f"Claude 关键域名代理检测失败: {', '.join(failed_targets)}"
    elif guard.get("dns_mode") == "local-risk":
        guard["status"] = "watch"
        guard["block_reason"] = "当前 proxy 为 socks5，本地 DNS 解析有风险"
    else:
        guard["proxy_validation"] = "validated"
    cache[cache_key] = {"ts": now, "guard": dict(guard)}
    return guard


def enforce_claude_network_guard_or_exit(
    runtime,
    *,
    require_proxy=False,
    build_network_guard_fn,
    console,
    exit_fn=sys.exit,
):
    guard = build_network_guard_fn(runtime, require_proxy=require_proxy)
    runtime["_network_guard"] = guard
    if guard.get("status") != "blocked":
        return guard
    detail_lines = []
    if guard.get("block_reason"):
        detail_lines.append(str(guard["block_reason"]))
    for item in guard.get("targets") or []:
        if item.get("ok"):
            continue
        detail = str(item.get("detail") or "").strip()
        detail_lines.append(
            f"{item.get('label')}: {detail}" if detail else str(item.get("label") or "target")
        )
    console.print(
        f"[red]{runtime.get('id') or runtime.get('name') or 'Claude runtime'} 网络保护阻止启动[/red]"
        + (f"\n[dim]{' | '.join(detail_lines)}[/dim]" if detail_lines else "")
    )
    exit_fn(1)


def check_proxy_connectivity_or_exit(
    proxy_url,
    no_proxy="",
    *,
    label="account",
    force_ipv4=True,
    fake_upstream_enabled_fn,
    fake_proxy_probe_fn,
    console,
    which_fn=shutil.which,
    subprocess_run=subprocess.run,
    exit_fn=sys.exit,
):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return
    if fake_upstream_enabled_fn():
        probe = fake_proxy_probe_fn(
            "https://api.anthropic.com",
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=False,
        )
        if probe.get("ok"):
            return
        detail = str(probe.get("detail") or probe.get("http_code") or "fake upstream")
        console.print(
            f"[red]{label} 配置的 proxy 不可用，已阻止启动[/red]"
            + (f"\n[dim]{detail}[/dim]" if detail else "")
        )
        exit_fn(1)
    curl_bin = which_fn("curl")
    if not curl_bin:
        console.print(f"[red]{label} 要求强制 proxy，但当前系统没有 curl，无法做启动前连通性检查[/red]")
        exit_fn(1)
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        proxy_url,
        "https://api.anthropic.com",
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess_run(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode != 0 or not http_code or http_code in {"000", "407"}:
        detail = (result.stderr or "").strip()
        if http_code and http_code not in {"000"}:
            detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
        if len(detail) > 200:
            detail = detail[:200] + "..."
        console.print(
            f"[red]{label} 配置的 proxy 不可用，已阻止启动[/red]"
            + (f"\n[dim]{detail}[/dim]" if detail else "")
        )
        exit_fn(1)


def apply_runtime_network_profile(
    env,
    runtime,
    *,
    validate_proxy=True,
    validate_timezone_or_exit_fn,
    apply_runtime_locale_profile_fn,
    apply_runtime_ip_stack_profile_fn,
    check_proxy_connectivity_or_exit_fn,
    fake_upstream_enabled_fn,
    fake_upstream_status_payload_fn,
    proxy_fingerprint_fn,
    runtime_force_ipv4_fn,
    default_account_timezone,
):
    env = env if isinstance(env, dict) else {}
    runtime = runtime if isinstance(runtime, dict) else {}

    timezone_name = validate_timezone_or_exit_fn(
        runtime.get("timezone") or default_account_timezone,
        label=str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "runtime"),
    )
    if timezone_name:
        env["TZ"] = timezone_name
    else:
        env.pop("TZ", None)

    apply_runtime_locale_profile_fn(env, runtime)
    apply_runtime_ip_stack_profile_fn(env, runtime)

    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    runtime_label = str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "runtime")

    if proxy_url and validate_proxy:
        check_proxy_connectivity_or_exit_fn(
            proxy_url,
            no_proxy,
            label=runtime_label,
            force_ipv4=bool(runtime_force_ipv4_fn(runtime)),
        )

    if fake_upstream_enabled_fn():
        fake_payload = fake_upstream_status_payload_fn()
        fake_proxy_url = str(fake_payload.get("proxy_url") or "").strip()
        if fake_proxy_url:
            for key in PROXY_KEYS:
                env[key] = fake_proxy_url
            env["MMS_FAKE_UPSTREAM_PROXY"] = fake_proxy_url
        else:
            for key in PROXY_KEYS:
                env.pop(key, None)
            env.pop("MMS_FAKE_UPSTREAM_PROXY", None)
        env["MMS_FAKE_UPSTREAM_MODE"] = "upstream-proxy"
        for key in NO_PROXY_KEYS:
            env[key] = "127.0.0.1,localhost,::1"
        if proxy_url:
            env["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] = proxy_fingerprint_fn(proxy_url)
        else:
            env.pop("MMS_FAKE_UPSTREAM_ORIGINAL_PROXY", None)
        if no_proxy:
            env["MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY"] = no_proxy
        else:
            env.pop("MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY", None)
        ca_cert_path = str(fake_payload.get("ca_cert_path") or "").strip()
        for key in CA_KEYS:
            if ca_cert_path:
                env[key] = ca_cert_path
            else:
                env.pop(key, None)
        return env

    for key in FAKE_STATE_KEYS:
        env.pop(key, None)
    for key in CA_KEYS:
        env.pop(key, None)

    if proxy_url:
        for key in PROXY_KEYS:
            env[key] = proxy_url
    else:
        for key in PROXY_KEYS:
            env.pop(key, None)

    if no_proxy:
        for key in NO_PROXY_KEYS:
            env[key] = no_proxy
    else:
        for key in NO_PROXY_KEYS:
            env.pop(key, None)

    return env
