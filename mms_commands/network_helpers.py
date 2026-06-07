"""Network, proxy, and timezone prompt helpers for command flows."""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import urlparse

from mms_commands.provider_config import runtime_force_ipv4


def url_matches_host_suffix(url, host_suffixes):
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    for suffix in host_suffixes:
        normalized = str(suffix or "").strip().lower().lstrip(".")
        if not normalized:
            continue
        if host == normalized or host.endswith("." + normalized):
            return True
    return False


def runtime_should_disable_ambient_env(
    runtime,
    *,
    target_url="",
    official_hosts,
    url_matches_host_suffix=url_matches_host_suffix,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    if str(runtime.get("proxy") or "").strip():
        return True
    return url_matches_host_suffix(target_url, official_hosts)


def runtime_httpx_kwargs(
    runtime,
    *,
    target_url="",
    official_hosts,
    runtime_force_ipv4=runtime_force_ipv4,
    runtime_should_disable_ambient_env=runtime_should_disable_ambient_env,
):
    transport_kwargs = {}
    proxy_url = str((runtime or {}).get("proxy") or "").strip()
    if proxy_url:
        transport_kwargs["proxy"] = proxy_url
    if runtime_should_disable_ambient_env(runtime, target_url=target_url, official_hosts=official_hosts):
        transport_kwargs["trust_env"] = False
    if runtime_force_ipv4(runtime):
        transport_kwargs["local_address"] = "0.0.0.0"
    return transport_kwargs


def detect_working_base_url(
    configured_url,
    path,
    headers,
    body=None,
    timeout=5,
    runtime=None,
    *,
    ensure_httpx,
    get_httpx,
    runtime_httpx_request,
):
    ensure_httpx()
    if get_httpx() is None:
        return None
    url = configured_url.rstrip("/")
    candidates = [url[:-3], url] if url.endswith("/v1") else [url, url + "/v1"]
    for candidate in candidates:
        try:
            if body is not None:
                resp = runtime_httpx_request(
                    "POST",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    content=body,
                    timeout=timeout,
                )
            else:
                resp = runtime_httpx_request(
                    "GET",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    timeout=timeout,
                )
            if resp.status_code == 200:
                return candidate
        except Exception:
            continue
    return None


def validate_proxy_url(proxy_url, *, supported_proxy_schemes):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return None
    try:
        parsed = urlparse(proxy_url)
    except Exception:
        return "代理地址解析失败"
    if parsed.scheme.lower() not in supported_proxy_schemes:
        return "代理协议仅支持 http / https / socks5 / socks5h"
    if not parsed.hostname:
        return "代理地址缺少 host"
    if parsed.port is None:
        return "代理地址缺少 port"
    return None


def test_proxy_connectivity(
    proxy_url,
    no_proxy="",
    target_url="https://api.anthropic.com",
    force_ipv4=True,
    *,
    http_status_is_success,
    which=shutil.which,
    run_command=subprocess.run,
):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return True, "未配置代理，跳过检测"
    curl_bin = which("curl")
    if not curl_bin:
        return False, "当前系统没有 curl，无法测试代理连通性"
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
        target_url,
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = run_command(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode == 0 and http_status_is_success(http_code):
        return True, f"代理连通性测试通过：{target_url} (HTTP {http_code})"
    detail = (result.stderr or "").strip()
    if http_code and http_code not in {"000"}:
        detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return False, detail or f"代理连通性测试失败：{target_url}"


def prompt_validated_proxy_fields(
    current_proxy="",
    current_no_proxy="",
    *,
    wizard=False,
    target_url="https://api.anthropic.com",
    wizard_prompt,
    prompt_ask,
    localize,
    validate_proxy_url,
    test_proxy_connectivity,
    confirm_ask,
    console,
):
    prompt_fn = wizard_prompt if wizard else prompt_ask
    proxy_label = "代理地址（可选，直接回车跳过；例 http://127.0.0.1:7890 / socks5h://127.0.0.1:7890）"
    no_proxy_label = "NO_PROXY（可选，直接回车跳过）"
    while True:
        proxy = prompt_fn(
            localize(proxy_label, "Proxy URL (optional, press Enter to skip; e.g. http://127.0.0.1:7890 / socks5h://127.0.0.1:7890)"),
            default=current_proxy or "",
        ).strip()
        error = validate_proxy_url(proxy)
        if error:
            console.print(f"[red]{error}[/red]")
            continue
        if not proxy:
            return "", ""
        no_proxy = prompt_fn(localize(no_proxy_label, "NO_PROXY (optional, press Enter to skip)"), default=current_no_proxy or "").strip()
        if proxy:
            console.print(f"[dim]正在测试代理连通性: {target_url}[/dim]")
            ok, detail = test_proxy_connectivity(
                proxy,
                no_proxy=no_proxy,
                target_url=target_url,
                force_ipv4=True,
            )
            if ok:
                console.print(f"[green]✓ {detail}[/green]")
                return proxy, no_proxy
            console.print(
                f"[yellow]代理测试未通过[/yellow]\n"
                f"[dim]{detail}[/dim]\n"
                f"[dim]这可能是 proxy 不通，也可能是当前代理策略不放行 {target_url}。[/dim]"
            )
            if confirm_ask("仍然保存这个代理配置？", default=False):
                return proxy, no_proxy
            current_proxy = proxy
            current_no_proxy = no_proxy
            continue
        return proxy, no_proxy


def prompt_validated_timezone(
    current_timezone="",
    *,
    wizard=False,
    default_account_timezone,
    wizard_prompt,
    prompt_ask,
    localize,
    zone_info_cls,
    console,
):
    prompt_fn = wizard_prompt if wizard else prompt_ask
    label = localize(
        f"启动时区（默认 {default_account_timezone}）",
        f"Launch timezone (default {default_account_timezone})",
    )
    while True:
        timezone_name = prompt_fn(label, default=current_timezone or default_account_timezone).strip()
        try:
            zone_info_cls(timezone_name)
            return timezone_name
        except Exception:
            console.print(f"[red]无效时区: {timezone_name}[/red]")
