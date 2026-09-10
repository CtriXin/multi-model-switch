"""Isolated worker for mms_web.catalog heavy MMS reuse.

Runs as a subprocess with a dedicated ``MMS_CONFIG_ROOT`` (and isolated HOME),
so MMS module-level path constants bind to the catalog-owned config root
instead of the host process environment. All stdout chatter from MMS helpers
(rich console, prints) is redirected to stderr; the JSON result is written on a
dup'ed copy of the original stdout fd.

Commands (stdin JSON):
- ``resolve-launch``: pin provider/model/cli explicitly, reuse the real MMS
  assembly chain (``resolve_provider_context`` -> ``validate_provider_for_cli``
  -> launch preferences). The session worker calls the original launcher.
  No TUI selection, global fallback or wizard.
- ``apply-config``: CAS-guarded narrow-patch write. The CAS check and the write
  both happen inside an flock on the same ``config.toml.lock`` file that
  ``mms_core.save_config`` uses, so MMS-side writes cannot be lost to a stale
  web apply. The config write itself reuses the real MMS writer components
  (backup + atomic TOML write + audit trail). credentials.sh gets a narrow,
  probe-free write that keeps the on-disk format of
  ``mms_core.save_provider_credentials`` without triggering its routes-export
  network probe. Update mode touches only form-owned fields (name, generic
  BASE_URL, primary API_KEY, manual model list); protocol-specific URLs/keys
  and every unknown advanced field are preserved byte-for-byte.

INTERNAL ONLY: results may contain secrets (export env / runtime api_key).
They must never be serialized to HTTP responses by the server owner.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import tempfile
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_PROVIDER_LAUNCHABLE_CLIS = ("claude", "codex", "opencode", "pi")
_PROTECTED_ROOT_NAMES = (".config/mms", ".config/mms-next")


def _result_stream():
    """Keep a private handle on the original stdout; redirect fd 1 to stderr."""
    stream = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    return stream


def _emit(stream, payload):
    stream.write(json.dumps(payload, ensure_ascii=False))
    stream.flush()


def _fail(stream, code, message):
    _emit(stream, {"ok": False, "code": code, "message": str(message)[:500]})


def _read_raw_config(config_root: Path) -> dict:
    config_path = config_root / "config.toml"
    if not config_path.exists():
        raise FileNotFoundError(str(config_path))
    with open(config_path, "rb") as handle:
        return tomllib.loads(handle.read().decode("utf-8"))


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _revision_of(config_root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("config.toml", "credentials.sh", "generated/model-registry.latest-approved.json"):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_read_bytes(config_root / name))
    return digest.hexdigest()[:16]


def _protected_roots(real_home: Path) -> list[Path]:
    roots = []
    for name in _PROTECTED_ROOT_NAMES:
        try:
            roots.append((real_home / name).resolve())
        except OSError:
            continue
    return roots


def _overlaps_protected(root: Path, protected: list[Path]) -> bool:
    try:
        resolved = Path(root).resolve()
    except OSError:
        return False
    for guard in protected:
        if resolved == guard:
            return True
        if resolved.is_relative_to(guard) or guard.is_relative_to(resolved):
            return True
    return False


def _real_home_from_payload(payload: dict) -> Path:
    """Real home comes from the parent process; worker HOME is isolated."""
    raw = str(payload.get("realHome") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        raw = str(os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return Path("~").expanduser().resolve()


def _cmd_resolve_launch(stream, payload):
    import mms_core
    import mms_launchers

    config_root = Path(payload["config_root"])
    cli = str(payload.get("cli") or "").strip()
    provider_id = str(payload.get("providerId") or "").strip() or None
    model = str(payload.get("model") or "").strip()

    if cli not in _PROVIDER_LAUNCHABLE_CLIS:
        _fail(stream, "HARNESS_UNSUPPORTED", f"harness “{cli}”无法从模型服务预设启动")
        return

    try:
        if (config_root / "generated/model-registry.latest-approved.json").is_file():
            cfg = mms_core._load_preview_runtime_config_from_latest_bundle()
            if not cfg:
                _fail(stream, "INVALID_BUNDLE", "MMS 无法读取已批准的模型目录。")
                return
            cfg = mms_core._merge_preview_local_launch_preferences(cfg)
        else:
            cfg = mms_core.load_config(persist=False)
        cfg = mms_core.apply_local_overrides(cfg or {})
    except FileNotFoundError:
        _fail(stream, "CONFIG_MISSING", "config root 下缺少 config.toml")
        return

    # Resolve provider definition; get_provider_definition sys.exit(1)s when an
    # explicit provider id is unknown, which we translate to a public error.
    try:
        provider_def = mms_core.get_provider_definition(cfg, provider_id)
    except SystemExit:
        _fail(stream, "PROVIDER_NOT_FOUND", f"未找到模型服务：{provider_id or 'default'}")
        return
    resolved_provider_id = provider_def.get("id") or provider_id

    runtime = mms_core.resolve_provider_context(cfg, resolved_provider_id)
    credentials = runtime
    has_url = bool(
        credentials.get("base_url")
        or credentials.get("openai_base_url")
        or credentials.get("anthropic_base_url")
    )
    if not has_url:
        _fail(stream, "PROVIDER_NO_BASE_URL", f"模型服务 “{resolved_provider_id}” 未配置接入地址")
        return
    if not credentials.get("api_key"):
        _fail(stream, "PROVIDER_NEEDS_KEY", f"模型服务 “{resolved_provider_id}” 未配置 API Key")
        return

    runtime = mms_core._runtime_with_launch_preferences(cfg, runtime, cli)
    try:
        mms_launchers.validate_provider_for_cli(cli, runtime)
    except SystemExit:
        _fail(
            stream,
            "HARNESS_UNSUPPORTED",
            f"模型服务 “{resolved_provider_id}” 无法驱动 harness “{cli}”（兼容性校验未通过）",
        )
        return

    model_info = {"model": model} if model else {}
    if not (config_root / "generated/model-registry.latest-approved.json").is_file():
        from mms_web.manual_bundle import materialize_manual_runtime_bundle
        materialize_manual_runtime_bundle(config_root, runtime, model)
    options = {}
    pi_model = {}
    if cli == "pi":
        from mms_web.launch_options import public_options
        options = public_options(runtime, model)
        runtime["reasoning_effort"] = options["defaultThinkingLevel"]
        import mms_pi_support
        _, provider_ref = mms_pi_support._pi_build_models_payload(runtime, mms_pi_support._pi_effective_selected_model(runtime, model))
        pi_model = {"provider": provider_ref, "modelId": options["model"]["id"]}
    _emit(
        stream,
        {
            "ok": True,
            "launchOptions": options,
            "piModel": pi_model,
            "harness": cli,
            "providerId": resolved_provider_id,
            "modelInfo": model_info,
            "runtime": runtime,
        },
    )


def _cmd_apply_config(stream, payload):
    config_root = Path(payload["config_root"])
    real_home = _real_home_from_payload(payload)
    protected = _protected_roots(real_home)

    # Gate every actual write target BEFORE importing any MMS module: the
    # config root itself and the lock/credential paths all live inside it.
    # The Registry publish path is the one exemption: it writes through the
    # same reviewed plan MMS itself applies, never by hand-editing config.toml
    # or credentials.sh, so a shared v2 root stays consistent for both
    # entrances. Legacy hand-writes into a real root remain refused.
    registry_publish = payload.get("standalone") is True
    if _overlaps_protected(config_root, protected) and not registry_publish:
        _fail(stream, "CONFIG_ROOT_PROTECTED", "真实 MMS 配置区仅限人工写入，Web 应用已拒绝")
        return

    import mms_core

    service = payload.get("service") or {}
    provider_id = str(payload.get("providerId") or "").strip()
    provider_name = str(service.get("name") or "").strip()
    base_url = str(service.get("baseUrl") or "").strip().rstrip("/")
    api_key = str(service.get("apiKey") or "").strip()
    models = [str(item).strip() for item in (service.get("models") or []) if str(item).strip()]
    expected_revision = str(payload.get("expectedRevision") or "").strip()

    config_path = config_root / "config.toml"
    credentials_path = config_root / "credentials.sh"
    # Same lock file (and flock) that mms_core.save_config takes, so MMS-side
    # writes and web applies serialize against each other across processes.
    lock_path = config_root / "config.toml.lock"
    config_root.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # CAS re-verified inside the writer critical section.
            if expected_revision and _revision_of(config_root) != expected_revision:
                _fail(stream, "CONFIG_STALE", "配置在应用时被其他进程修改，已中止")
                return

            if payload.get("standalone") is True:
                from mms_web.standalone_config import apply_connection
                _emit(stream, apply_connection(config_root, payload))
                return

            if config_path.exists():
                try:
                    cfg = _read_raw_config(config_root)
                except (OSError, tomllib.TOMLDecodeError):
                    _fail(stream, "CONFIG_INVALID", "config.toml 无法解析，已中止")
                    return
            else:
                cfg = {"provider": {"default": ""}, "providers": []}
            providers = cfg.setdefault("providers", [])
            if not isinstance(providers, list):
                _fail(stream, "CONFIG_INVALID", "config.toml 的 providers 不是列表，已中止")
                return

            existing_index = next(
                (idx for idx, item in enumerate(providers) if isinstance(item, dict) and item.get("id") == provider_id),
                None,
            )

            if existing_index is None:
                # Create: mirror the MMS quick-connect gateway template shape
                # and run it through the real MMS provider normalizer.
                entry = mms_core._normalize_provider(
                    {
                        "id": provider_id,
                        "name": provider_name or provider_id,
                        "protocols": {"openai": ["openai_chat_completions"],
                                      "anthropic": ["anthropic_messages"]}.get(
                                          service.get("protocol"), ["openai_chat_completions", "anthropic_messages"]),
                        "supported_clis": list(mms_core.PROVIDER_CAPABLE_CLIS),
                        "models_endpoint": "manual",
                        "fallback_models": models,
                        "enabled": True,
                    }
                )
                providers.append(entry)
                provider_entry = entry
            else:
                # Update: narrow patch of form-owned fields only. Name when
                # provided; the manual model list when (and only when) the
                # provider is already in manual mode, matching the preview.
                provider_entry = dict(providers[existing_index])
                if provider_name and provider_entry.get("name") != provider_name:
                    provider_entry["name"] = provider_name
                if models and str(provider_entry.get("models_endpoint") or "") == "manual":
                    provider_entry["fallback_models"] = models
                providers[existing_index] = provider_entry

            # Reuse the real MMS writer components under our lock: backup,
            # atomic TOML write, and the config audit trail.
            try:
                mms_core._ensure_mms_config_guard_files(str(config_path))
                backup_path = mms_core._backup_config_file(str(config_path))
                mms_core._atomic_write_toml(str(config_path), cfg)
                mms_core._append_config_audit_entry(
                    {
                        "timestamp": mms_core._iso_now(),
                        "reason": "mms-web:configuration_apply",
                        "target_path": os.path.abspath(str(config_path)),
                        "backup_path": backup_path,
                        "caller_path": str(Path(__file__)),
                        "caller_line": 0,
                        "caller_function": "mms_web_catalog_apply",
                        "pid": os.getpid(),
                        "before_sha1": "",
                        "after_sha1": mms_core._sha1_file(str(config_path)),
                    },
                    config_path=str(config_path),
                )
            except SystemExit:
                _fail(stream, "CONFIG_WRITE_FAILED", "MMS 写入器拒绝了本次配置写入")
                return
            except Exception:
                _fail(stream, "CONFIG_WRITE_FAILED", "配置写入失败（详情见服务端日志）")
                return

            # Credentials narrow write: reuse MMS helpers for env naming/
            # quoting/file parsing. Create mode owns the full set; update mode
            # touches only the generic BASE_URL and the primary API_KEY, never
            # protocol-specific URLs/keys or other providers' entries. No
            # routes-export probe is triggered from here.
            credentials_touched = False
            if base_url or api_key:
                values = mms_core._load_env_file(str(credentials_path)) if credentials_path.exists() else {}
                env_name = mms_core._provider_env_name
                if base_url:
                    values[env_name(provider_id, "BASE_URL")] = base_url
                if api_key:
                    values[env_name(provider_id, "API_KEY")] = api_key
                if existing_index is None:
                    # Fresh provider: the form owns protocol-specific URLs too.
                    protocols = {str(p) for p in (provider_entry.get("protocols") or [])}
                    if base_url:
                        if "openai_chat_completions" in protocols:
                            values[env_name(provider_id, "OPENAI_BASE_URL")] = base_url
                        if "anthropic_messages" in protocols:
                            values[env_name(provider_id, "ANTHROPIC_BASE_URL")] = base_url
                    if api_key and base_url and "openai_chat_completions" in protocols:
                        values[env_name(provider_id, "OPENAI_API_KEY")] = api_key
                lines = ["# Generated by MMS"]
                for key in sorted(values):
                    lines.append(f"export {key}={mms_core._shell_quote(str(values[key]))}")
                lines.append("")
                fd, temp_path = tempfile.mkstemp(
                    prefix=credentials_path.name + ".", suffix=".tmp", dir=str(config_root)
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write("\n".join(lines))
                    os.chmod(temp_path, 0o600)
                    os.replace(temp_path, credentials_path)
                    credentials_touched = True
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    _emit(
        stream,
        {
            "ok": True,
            "applied": True,
            "providerId": provider_id,
            "changed": ["providers"] + (["credentials.sh"] if credentials_touched else []),
        },
    )


def main() -> int:
    stream = _result_stream()
    try:
        payload = json.loads(sys.stdin.read())
        command = str(payload.get("command") or "").strip()
        if command == "resolve-launch":
            _cmd_resolve_launch(stream, payload)
        elif command == "apply-config":
            _cmd_apply_config(stream, payload)
        else:
            _fail(stream, "WORKER_UNKNOWN_COMMAND", f"未知 worker 命令：{command}")
    except Exception:
        # Controlled message only: exception text could echo secrets/paths.
        _fail(stream, "WORKER_ERROR", "worker 内部错误（详情见服务端日志）")
    finally:
        stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
