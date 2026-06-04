"""About/update/version command helpers with dependencies injected by core."""

from __future__ import annotations

import os
import re
import shlex
import subprocess


def short_update_status_label(status, *, localize):
    status = str(status or "").strip()
    if not status:
        return ""
    if status.startswith(localize("有新版", "update available")):
        return localize("有新版", "update available")
    if status.startswith(localize("高于 latest", "newer than latest")):
        return localize("高于 latest", "newer than latest")
    return status


def format_cli_about_line(cli_status, *, localize):
    current = str(cli_status.get("version") or cli_status.get("label") or "").strip()
    status = short_update_status_label(cli_status.get("status"), localize=localize)
    status_suffix = f" · {status}" if status else ""
    return f"{current}{status_suffix}".strip() or "-"


def format_about_latest_value(status, *, localize):
    latest = str((status or {}).get("latest") or "").strip()
    return latest or localize("未检查", "not checked")


def about_check_error_summary(error_text, *, localize):
    raw = str(error_text or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if "ssl" in lower or "handshake" in lower:
        return localize("MMS latest 检查失败：SSL handshake，可稍后重试", "MMS latest check failed: SSL handshake; retry later")
    if "timed out" in lower or "timeout" in lower:
        return localize("MMS latest 检查超时，可稍后重试", "MMS latest check timed out; retry later")
    if len(raw) > 72:
        raw = raw[:69].rstrip() + "..."
    return raw


def mms_upgrade_shell_command(*, include_clis=False, preferred_language="", normalize_language):
    args = ["--latest-tag", "--lang", normalize_language(preferred_language) or "zh"]
    if include_clis:
        args.extend(["--install-cli", "claude,codex"])
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    return f"curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- {quoted_args}"


def cli_upgrade_shell_command(cli_name, *, cli_version_packages):
    cli = str(cli_name or "").strip().lower()
    package = cli_version_packages.get(cli)
    if not package:
        return ""
    return "npm install -g " + shlex.quote(f"{package}@latest")


def run_about_upgrade(
    *,
    target="mms",
    include_clis=False,
    ensure_rich,
    cli_upgrade_shell_command,
    mms_upgrade_shell_command,
    confirm_ask,
    subprocess_run,
    console,
    localize,
):
    ensure_rich()
    target = str(target or "mms").strip().lower()
    if target in {"codex", "claude"}:
        command = cli_upgrade_shell_command(target)
        label = "Codex CLI" if target == "codex" else "Claude CLI"
    else:
        command = mms_upgrade_shell_command(include_clis=include_clis)
        label = localize("MMS + Codex/Claude CLI", "MMS + Codex/Claude CLI") if include_clis else "MMS"
    if not command:
        console.print(f"[red]{localize('没有可执行的升级命令。', 'No upgrade command available.')}[/red]")
        return False
    console.print(f"[yellow]{localize(f'即将升级 {label}', f'About to upgrade {label}')}[/yellow]")
    console.print(f"[dim]{command}[/dim]")
    if not confirm_ask(localize("确认执行升级？", "Run upgrade now?"), default=False):
        console.print(f"[yellow]{localize('已取消升级。', 'Upgrade cancelled.')}[/yellow]")
        return False
    result = subprocess_run(
        ["bash", "-lc", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        console.print(result.stdout)
    if result.returncode == 0:
        console.print(f"[green]✓ {localize('升级命令完成。重新打开终端或重新启动 mms 后生效。', 'Upgrade command completed. Restart the terminal or MMS to apply.')}[/green]")
        return True
    console.print(f"[red]{localize('升级命令失败', 'Upgrade command failed')} (exit {result.returncode})[/red]")
    return False


def about_tui_payload(about_snapshot, *, config_path, localize):
    about_snapshot = about_snapshot if isinstance(about_snapshot, dict) else {}
    version_info = about_snapshot.get("version_info") if isinstance(about_snapshot.get("version_info"), dict) else {}
    mms_status = about_snapshot.get("mms") if isinstance(about_snapshot.get("mms"), dict) else {}
    clis = about_snapshot.get("clis") if isinstance(about_snapshot.get("clis"), dict) else {}
    codex_status = clis.get("codex") if isinstance(clis.get("codex"), dict) else {}
    claude_status = clis.get("claude") if isinstance(clis.get("claude"), dict) else {}
    info_lines = [
        ("MMS", f"{mms_status.get('current') or version_info.get('release') or 'dev'} · {mms_status.get('status') or '-'}"),
        (localize("版本轨道", "Version track"), version_info.get("release_track_label") or version_info.get("release_track_version") or "-"),
        (localize("MMS 最新", "MMS latest"), mms_status.get("latest") or localize("未检查", "not checked")),
        ("Codex", format_cli_about_line(codex_status, localize=localize)),
        (localize("Codex 最新", "Codex latest"), format_about_latest_value(codex_status, localize=localize)),
        ("Claude", format_cli_about_line(claude_status, localize=localize)),
        (localize("Claude 最新", "Claude latest"), format_about_latest_value(claude_status, localize=localize)),
        ("Git", f"{version_info.get('git_branch') or '-'} @ {version_info.get('git_commit') or '-'}"),
        (localize("安装", "Install"), f"{version_info.get('install_channel') or '-'} / {version_info.get('source') or '-'}"),
        ("Config", config_path),
    ]
    if mms_status.get("last_error"):
        info_lines.append((localize("检查错误", "Check error"), about_check_error_summary(mms_status.get("last_error"), localize=localize)))
    actions = [("refresh_versions", localize("刷新版本检查", "Refresh Version Check"))]
    if mms_status.get("outdated"):
        actions.append(("upgrade_mms", localize("升级 MMS", "Upgrade MMS")))
    if codex_status.get("outdated"):
        actions.append(("upgrade_codex_cli", localize("升级 Codex CLI", "Upgrade Codex CLI")))
    if claude_status.get("outdated"):
        actions.append(("upgrade_claude_cli", localize("升级 Claude CLI", "Upgrade Claude CLI")))
    actions.append(("back", localize("返回", "Back")))
    return localize("关于 / About", "About"), info_lines, actions


def snapshot_guard_tui_payload(*, command_name, localize):
    info_lines = [
        (localize("用途", "Purpose"), localize("检查/接受 MMS config drift", "Inspect / accept MMS config drift")),
        ("CLI", f"{command_name} guard status / accept"),
    ]
    actions = [
        ("status", localize("查看当前 Snapshot 状态", "Status")),
        ("accept", localize("接受当前 Snapshot", "Accept Current Snapshot")),
        ("back", localize("返回", "Back")),
    ]
    return localize("启动快照 / Snapshot Guard", "Snapshot Guard"), info_lines, actions


def display_about_version_summary(about_snapshot, *, payload_builder, console):
    title, info_lines, _actions = payload_builder(about_snapshot)
    console.print(f"[cyan]{title}[/cyan]")
    for label, value in info_lines:
        console.print(f"[cyan]{label}[/cyan] {value}")

def parse_semver_tag(tag):
    value = str(tag or "").strip()
    if not value.startswith("v"):
        return None
    parts = value[1:].split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def normalize_semver_tags(raw_tags):
    if not isinstance(raw_tags, list):
        return []

    normalized = []
    seen = set()
    for item in raw_tags:
        tag = str(item or "").strip()
        parsed = parse_semver_tag(tag)
        if parsed is None or tag in seen:
            continue
        seen.add(tag)
        normalized.append((parsed, tag))

    normalized.sort(key=lambda item: item[0], reverse=True)
    return [tag for _, tag in normalized]


def fetch_latest_semver_tags(*, limit, request_cls, urlopen_func, json_load, normalize_semver_tags):
    req = request_cls(
        f"https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page={int(limit)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mms-update-check",
        },
    )
    with urlopen_func(req, timeout=3) as resp:
        data = json_load(resp)

    if not isinstance(data, list):
        return ""

    semver_tags = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("name") or "").strip()
        semver_tags.append(tag)
    return normalize_semver_tags(semver_tags)


def fetch_latest_semver_tag(*, fetch_latest_semver_tags):
    semver_tags = fetch_latest_semver_tags()
    return semver_tags[0] if semver_tags else ""


def extract_semver_text(value):
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?", str(value or ""))
    return match.group(0) if match else ""

def parse_semver_text(value):
    version = extract_semver_text(value)
    if not version:
        return None
    core = re.split(r"[-+]", version, maxsplit=1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def compare_semver_text(current, latest):
    current_semver = parse_semver_text(current)
    latest_semver = parse_semver_text(latest)
    if current_semver is None or latest_semver is None:
        return None
    if current_semver < latest_semver:
        return -1
    if current_semver > latest_semver:
        return 1
    return 0


def detect_cli_version(command_name, *, which, subprocess_run, extract_semver_text, localize):
    command = str(command_name or "").strip()
    if not command:
        return {"installed": False, "label": localize("未安装", "not installed"), "version": "", "path": ""}
    path = which(command)
    if not path:
        return {"installed": False, "label": localize("未安装", "not installed"), "version": "", "path": ""}
    try:
        result = subprocess_run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return {
            "installed": True,
            "label": localize(f"读取失败: {exc}", f"version failed: {exc}"),
            "version": "",
            "path": path,
        }
    raw = str(result.stdout or "").strip().splitlines()
    label = raw[0].strip() if raw else (path if result.returncode == 0 else localize("读取失败", "version failed"))
    return {
        "installed": True,
        "label": label,
        "version": extract_semver_text(label),
        "path": path,
    }


def fetch_npm_package_latest_version(package_name, *, which, subprocess_run, extract_semver_text):
    package = str(package_name or "").strip()
    if not package:
        return ""
    npm_bin = which("npm")
    if not npm_bin:
        return ""
    try:
        result = subprocess_run(
            [npm_bin, "view", package, "version", "--silent"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=6,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return extract_semver_text(str(result.stdout or "").strip())


def git_output(args, *, subprocess_run, file_path):
    try:
        result = subprocess_run(
            ["git", "-C", os.path.dirname(os.path.abspath(file_path)), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def semver_tag_gap(installed_version, known_tags, latest_tag=""):
    installed_version = str(installed_version or "").strip()
    tags = normalize_semver_tags(known_tags)
    if not tags:
        latest_semver = parse_semver_tag(latest_tag)
        installed_semver = parse_semver_tag(installed_version)
        if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
            return 0
        return None

    latest_tag = tags[0]
    latest_semver = parse_semver_tag(latest_tag)
    installed_semver = parse_semver_tag(installed_version)
    if latest_semver is None or installed_semver is None or latest_semver <= installed_semver:
        return 0

    try:
        return tags.index(installed_version)
    except ValueError:
        return len(tags)


def installed_update_semver(version_meta, *, update_notice_sources):
    source = str(version_meta.get("source") or "").strip()
    install_channel = str(version_meta.get("install_channel") or "").strip()
    if source:
        is_install_managed = source in update_notice_sources
    else:
        is_install_managed = bool(install_channel)
    if not is_install_managed:
        return None, None

    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_semver = parse_semver_tag(installed_version)
    if installed_semver is None:
        return None, None
    return installed_version, installed_semver


def update_notice(
    *,
    stdin,
    stdout,
    load_version_meta,
    installed_update_semver,
    load_update_check_cache,
    parse_semver_tag,
    semver_tag_gap,
    save_update_check_cache,
    now,
    version_gap,
    prompt_interval_sec,
):
    if not (stdin.isatty() and stdout.isatty()):
        return None

    version_meta = load_version_meta()
    installed_version, installed_semver = installed_update_semver(version_meta)
    if installed_semver is None:
        return None

    cache = load_update_check_cache()
    latest_tag = str(cache.get("latest_tag") or "").strip()
    latest_semver = parse_semver_tag(latest_tag)
    if latest_semver is None or latest_semver <= installed_semver:
        return None

    gap_count = semver_tag_gap(installed_version, cache.get("semver_tags"), latest_tag)
    is_major_upgrade = latest_semver[0] > installed_semver[0]
    if not is_major_upgrade and (gap_count is None or gap_count < version_gap):
        return None

    now_value = now()
    last_prompted_for = str(cache.get("last_prompted_for") or "").strip()
    last_prompted_at = float(cache.get("last_prompted_at") or 0)
    if last_prompted_for == latest_tag and now_value - last_prompted_at < prompt_interval_sec:
        return None

    cache["last_prompted_for"] = latest_tag
    cache["last_prompted_at"] = now_value
    save_update_check_cache(cache)
    return {
        "installed_version": installed_version,
        "latest_tag": latest_tag,
        "gap_count": gap_count,
        "upgrade_command": "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash",
    }


def major_update_notice(*, update_notice):
    return update_notice()


def start_async_update_check(
    *,
    load_version_meta,
    installed_update_semver,
    load_update_check_cache,
    fetch_latest_semver_tags,
    save_update_check_cache,
    lock,
    get_running,
    set_running,
    thread_cls,
    now,
    interval_sec,
):
    version_meta = load_version_meta()
    _installed_version, installed_semver = installed_update_semver(version_meta)
    if installed_semver is None:
        return

    cache = load_update_check_cache()
    last_checked_at = float(cache.get("checked_at") or 0)
    if now() - last_checked_at < interval_sec:
        return

    with lock:
        if get_running():
            return
        set_running(True)

    def _run():
        try:
            semver_tags = fetch_latest_semver_tags()
            payload = load_update_check_cache()
            payload["checked_at"] = now()
            if semver_tags:
                payload["latest_tag"] = semver_tags[0]
                payload["semver_tags"] = semver_tags
            save_update_check_cache(payload)
        except Exception:
            pass
        finally:
            with lock:
                set_running(False)

    thread_cls(
        target=_run,
        daemon=True,
        name="mms-update-check",
    ).start()


def mms_update_status(version_info, cache, *, localize):
    current = str(version_info.get("installed_version") or version_info.get("release") or "").strip()
    latest = str(cache.get("latest_tag") or "").strip()
    current_semver = parse_semver_tag(current)
    latest_semver = parse_semver_tag(latest)
    if current_semver is None:
        status = localize("开发版/无法判断", "dev/unknown")
        outdated = False
    elif latest_semver is None:
        status = localize("未检查 latest", "latest not checked")
        outdated = False
    elif current_semver < latest_semver:
        status = localize(f"有新版 {latest}", f"update available {latest}")
        outdated = True
    else:
        status = localize("最新", "latest")
        outdated = False
    return {
        "current": current or "dev",
        "latest": latest,
        "status": status,
        "outdated": outdated,
        "last_error": str(cache.get("last_error") or "").strip(),
    }


def release_track_for_channel(version_meta, *, git_branch="", environ=None):
    """Return the product track without treating preview channels as stable semver."""
    version_meta = version_meta if isinstance(version_meta, dict) else {}
    environ = os.environ if environ is None else environ
    install_channel = str(version_meta.get("install_channel") or "").strip().lower()
    installed_ref = str(version_meta.get("installed_ref") or "").strip().lower()
    preview_mode = str(environ.get("MMS_PREVIEW_MODE") or "").strip().lower()
    command_name = str(environ.get("MMS_COMMAND_NAME") or "").strip().lower()
    branch = str(git_branch or "").strip().lower()

    canary_markers = {"canary", "mmg", "mms-canary"}
    dev_markers = {"dev", "mmf", "mms-dev"}
    if preview_mode in canary_markers or command_name == "mmg":
        return {
            "release_track": "canary",
            "release_track_series": "4.0",
            "release_track_version": "4.0.0-canary",
            "release_track_label": "4.0 Canary Preview",
        }
    if preview_mode in dev_markers or command_name == "mmf":
        return {
            "release_track": "dev",
            "release_track_series": "4.0",
            "release_track_version": "4.0.0-dev",
            "release_track_label": "4.0 Dev Preview",
        }
    if install_channel == "canary" or installed_ref == "canary" or branch == "canary":
        return {
            "release_track": "canary",
            "release_track_series": "4.0",
            "release_track_version": "4.0.0-canary",
            "release_track_label": "4.0 Canary Preview",
        }
    if install_channel == "dev" or installed_ref == "dev" or branch == "dev":
        return {
            "release_track": "dev",
            "release_track_series": "4.0",
            "release_track_version": "4.0.0-dev",
            "release_track_label": "4.0 Dev Preview",
        }
    return {
        "release_track": "stable",
        "release_track_series": "3.x",
        "release_track_version": "3.x-stable",
        "release_track_label": "3.x Stable",
    }


def release_version_info(*, load_version_meta, git_output):
    version_meta = load_version_meta()
    installed_version = str(version_meta.get("installed_version") or "").strip()
    installed_ref = str(version_meta.get("installed_ref") or "").strip()
    git_describe = git_output(["describe", "--tags", "--always", "--dirty"])
    git_branch = git_output(["branch", "--show-current"])
    git_commit = git_output(["rev-parse", "--short", "HEAD"])
    release = installed_version or git_describe or git_commit or "dev"
    info = {
        "release": release,
        "installed_version": installed_version,
        "installed_ref": installed_ref,
        "git_describe": git_describe,
        "git_branch": git_branch,
        "git_commit": git_commit,
        "install_channel": str(version_meta.get("install_channel") or "").strip(),
        "source": str(version_meta.get("source") or "").strip(),
    }
    info.update(release_track_for_channel(version_meta, git_branch=git_branch))
    return info


def cli_version_status(
    *,
    force_update=False,
    load_update_check_cache,
    save_update_check_cache,
    cli_version_packages,
    detect_cli_version,
    fetch_npm_package_latest_version,
    compare_semver_text,
    localize,
    now,
):
    cache = load_update_check_cache()
    cached_latest = cache.get("cli_latest_versions") if isinstance(cache.get("cli_latest_versions"), dict) else {}
    latest_versions = dict(cached_latest)
    if force_update:
        latest_versions = {}
        for cli_name, package_name in cli_version_packages.items():
            latest_versions[cli_name] = fetch_npm_package_latest_version(package_name)
        cache["cli_latest_versions"] = latest_versions
        cache["cli_latest_checked_at"] = now()
        save_update_check_cache(cache)

    status = {}
    for cli_name in ("codex", "claude"):
        current = detect_cli_version(cli_name)
        latest = str(latest_versions.get(cli_name) or "").strip()
        comparison = compare_semver_text(current.get("version"), latest)
        if not current.get("installed"):
            label = localize("未安装", "not installed")
            outdated = False
        elif comparison == -1:
            label = localize(f"有新版 {latest}", f"update available {latest}")
            outdated = True
        elif comparison == 0:
            label = localize("最新", "latest")
            outdated = False
        elif latest:
            label = localize(f"高于 latest {latest}", f"newer than latest {latest}")
            outdated = False
        else:
            label = localize("未检查 latest", "latest not checked")
            outdated = False
        status[cli_name] = {
            **current,
            "latest": latest,
            "status": label,
            "outdated": outdated,
            "package": cli_version_packages.get(cli_name, ""),
        }
    return status


def refresh_update_cache_for_about(*, force_update=False, load_update_check_cache, fetch_latest_semver_tags, save_update_check_cache, now):
    cache = load_update_check_cache()
    if not force_update:
        return cache
    try:
        semver_tags = fetch_latest_semver_tags()
    except Exception as exc:
        cache["last_error"] = str(exc)
        cache["checked_at"] = now()
        save_update_check_cache(cache)
        return cache
    cache["checked_at"] = now()
    cache["last_error"] = ""
    if semver_tags:
        cache["latest_tag"] = semver_tags[0]
        cache["semver_tags"] = semver_tags
    save_update_check_cache(cache)
    return cache


def about_status_snapshot(*, force_update=False, release_version_info, refresh_update_cache_for_about, cli_version_status, mms_update_status):
    version_info = release_version_info()
    cache = refresh_update_cache_for_about(force_update=force_update)
    cli_status = cli_version_status(force_update=force_update)
    return {
        "version_info": version_info,
        "mms": mms_update_status(version_info, cache),
        "clis": cli_status,
        "checked_at": cache.get("checked_at"),
    }
