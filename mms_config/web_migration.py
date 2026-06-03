# -*- coding: utf-8 -*-
"""Migration/import helpers for the MMS config WebUI."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
from datetime import datetime, timezone
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any


MIGRATION_BUNDLE_SCHEMA = "mms.config_migration_bundle.v1"
MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA = "mms.config_migration_credentials.aesgcm.v1"
MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA = "mms.config_migration_credentials.openssl-cbc-hmac.v1"


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _sanitize_for_output(value: Any) -> Any:
    return _call_backend("_sanitize_for_output", value)


def _normalize_priority(value: Any) -> int:
    return _call_backend("_normalize_priority", value)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _call_backend("_normalize_family_priority_overrides", value)


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _load_preferences_raw(path: str) -> dict[str, Any]:
    from mms_config.web_apply import _load_preferences_raw as load_preferences_raw_impl

    return load_preferences_raw_impl(path)


def _preferences_target_path(*, config_path: str = "", preferences_path: str = "") -> str:
    from mms_config.web_apply import _preferences_target_path as preferences_target_path_impl

    return preferences_target_path_impl(config_path=config_path, preferences_path=preferences_path)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend("_policy_path_for_config", config_path)


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _call_backend("_config_root_for_snapshot", config_path)


def _version_info_for_snapshot(command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_version_info_for_snapshot", command_name)


def _now_iso() -> str:
    return _call_backend("_now_iso")


def _backend_web_wrapper(name: str) -> bool:
    func = getattr(_backend(), name, None)
    return callable(func) and getattr(func, "__module__", "") == "mms_config.web" and getattr(func, "__name__", "") == name


def _call_backend_override(name: str, default: Any, *args: Any, **kwargs: Any) -> Any:
    func = getattr(_backend(), name, None)
    if callable(func) and not _backend_web_wrapper(name):
        return func(*args, **kwargs)
    return default(*args, **kwargs)


def _migration_cryptography_available() -> bool:
    return _call_backend_override("_migration_cryptography_available", _migration_cryptography_available_impl)


def _migration_openssl_available() -> bool:
    return _call_backend_override("_migration_openssl_available", _migration_openssl_available_impl)


def _migration_secret_crypto_backend() -> str:
    return _call_backend_override("_migration_secret_crypto_backend", _migration_secret_crypto_backend_impl)


def _migration_crypto_available() -> bool:
    return _call_backend_override("_migration_crypto_available", _migration_crypto_available_impl)


def _migration_derive_key(password: str, salt: bytes, *, iterations: int) -> bytes:
    return _call_backend_override("_migration_derive_key", _migration_derive_key_impl, password, salt, iterations=iterations)


def _migration_encrypt_json_aesgcm(payload: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_encrypt_json_aesgcm", _migration_encrypt_json_aesgcm_impl, payload, password)


def _migration_decrypt_json_aesgcm(box: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_decrypt_json_aesgcm", _migration_decrypt_json_aesgcm_impl, box, password)


def _migration_openssl_passfile(password: str) -> str:
    return _call_backend_override("_migration_openssl_passfile", _migration_openssl_passfile_impl, password)


def _migration_run_openssl_enc(data: bytes, password: str, *, decrypt: bool, iterations: int) -> bytes:
    return _call_backend_override("_migration_run_openssl_enc", _migration_run_openssl_enc_impl, data, password, decrypt=decrypt, iterations=iterations)


def _migration_openssl_mac_payload(box: dict[str, Any]) -> bytes:
    return _call_backend_override("_migration_openssl_mac_payload", _migration_openssl_mac_payload_impl, box)


def _migration_encrypt_json_openssl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_encrypt_json_openssl", _migration_encrypt_json_openssl_impl, payload, password)


def _migration_decrypt_json_openssl(box: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_decrypt_json_openssl", _migration_decrypt_json_openssl_impl, box, password)


def _migration_encrypt_json(payload: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_encrypt_json", _migration_encrypt_json_impl, payload, password)


def _migration_decrypt_json(box: dict[str, Any], password: str) -> dict[str, Any]:
    return _call_backend_override("_migration_decrypt_json", _migration_decrypt_json_impl, box, password)


def _migration_cryptography_available_impl() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

        return True
    except Exception:
        return False


def _migration_openssl_available_impl() -> bool:
    return bool(shutil.which("openssl"))


def _migration_secret_crypto_backend_impl() -> str:
    if _migration_cryptography_available():
        return "cryptography"
    if _migration_openssl_available():
        return "openssl"
    return "none"


def _migration_crypto_available_impl() -> bool:
    return _migration_secret_crypto_backend() != "none"


def _migration_derive_key_impl(password: str, salt: bytes, *, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def _migration_encrypt_json_aesgcm_impl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iterations = 220_000
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _migration_derive_key(password, salt, iterations=iterations)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, MIGRATION_BUNDLE_SCHEMA.encode("utf-8"))
    return {
        "schema": MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": iterations,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_schema": "mms.config_migration_credentials_payload.v1",
    }


def _migration_decrypt_json_aesgcm_impl(box: dict[str, Any], password: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iterations = int(box.get("iterations") or 0)
    if iterations < 100_000:
        raise ValueError("迁移包凭据 KDF 强度过低，已拒绝导入。")
    salt = base64.b64decode(str(box.get("salt_b64") or ""))
    nonce = base64.b64decode(str(box.get("nonce_b64") or ""))
    ciphertext = base64.b64decode(str(box.get("ciphertext_b64") or ""))
    key = _migration_derive_key(password, salt, iterations=iterations)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, MIGRATION_BUNDLE_SCHEMA.encode("utf-8"))
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("迁移包凭据解密后不是对象。")
    return payload


def _migration_openssl_passfile_impl(password: str) -> str:
    fd, path = tempfile.mkstemp(prefix="mms-migration-pass-", text=False)
    try:
        os.chmod(path, 0o600)
        os.write(fd, password.encode("utf-8"))
        os.close(fd)
        fd = -1
        return path
    except Exception:
        try:
            if fd >= 0:
                os.close(fd)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def _migration_run_openssl_enc_impl(data: bytes, password: str, *, decrypt: bool, iterations: int) -> bytes:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("当前 Python 环境缺少 cryptography，且找不到 openssl，不能处理加密 API Key。")
    passfile = _migration_openssl_passfile(password)
    try:
        cmd = [
            openssl,
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            str(iterations),
            "-md",
            "sha256",
            "-salt",
            "-pass",
            f"file:{passfile}",
        ]
        if decrypt:
            cmd.insert(2, "-d")
        proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    finally:
        try:
            os.unlink(passfile)
        except OSError:
            pass
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        message = detail[-1] if detail else "openssl enc failed"
        raise ValueError(f"OpenSSL 加密后备失败：{message}")
    return proc.stdout


def _migration_openssl_mac_payload_impl(box: dict[str, Any]) -> bytes:
    fields = {
        "schema": _safe_text(box.get("schema")),
        "algorithm": _safe_text(box.get("algorithm")),
        "kdf": _safe_text(box.get("kdf")),
        "iterations": int(box.get("iterations") or 0),
        "mac_salt_b64": _safe_text(box.get("mac_salt_b64")),
        "ciphertext_b64": _safe_text(box.get("ciphertext_b64")),
        "plaintext_schema": _safe_text(box.get("plaintext_schema")),
        "aad": MIGRATION_BUNDLE_SCHEMA,
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _migration_encrypt_json_openssl_impl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    iterations = 220_000
    mac_salt = os.urandom(16)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = _migration_run_openssl_enc(plaintext, password, decrypt=False, iterations=iterations)
    box = {
        "schema": MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA,
        "algorithm": "AES-256-CBC+HMAC-SHA256",
        "kdf": "OpenSSL-PBKDF2-HMAC-SHA256 + PBKDF2-HMAC-SHA256-MAC",
        "iterations": iterations,
        "mac_salt_b64": base64.b64encode(mac_salt).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_schema": "mms.config_migration_credentials_payload.v1",
    }
    mac_key = _migration_derive_key(password, mac_salt, iterations=iterations)
    box["hmac_b64"] = base64.b64encode(
        hmac.new(mac_key, _migration_openssl_mac_payload(box), hashlib.sha256).digest()
    ).decode("ascii")
    return box


def _migration_decrypt_json_openssl_impl(box: dict[str, Any], password: str) -> dict[str, Any]:
    iterations = int(box.get("iterations") or 0)
    if iterations < 100_000:
        raise ValueError("迁移包凭据 KDF 强度过低，已拒绝导入。")
    mac_salt = base64.b64decode(str(box.get("mac_salt_b64") or ""))
    ciphertext = base64.b64decode(str(box.get("ciphertext_b64") or ""))
    expected = base64.b64decode(str(box.get("hmac_b64") or ""))
    mac_key = _migration_derive_key(password, mac_salt, iterations=iterations)
    actual = hmac.new(mac_key, _migration_openssl_mac_payload(box), hashlib.sha256).digest()
    if not expected or not hmac.compare_digest(actual, expected):
        raise ValueError("迁移密码错误或凭据已损坏。")
    plaintext = _migration_run_openssl_enc(ciphertext, password, decrypt=True, iterations=iterations)
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("迁移包凭据解密后不是对象。")
    return payload


def _migration_encrypt_json_impl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    backend = _migration_secret_crypto_backend()
    if backend == "cryptography":
        return _migration_encrypt_json_aesgcm(payload, password)
    if backend == "openssl":
        return _migration_encrypt_json_openssl(payload, password)
    raise ValueError("当前 Python 环境缺少 cryptography，且找不到 openssl，不能导出包含 API Key 的加密迁移包。")


def _migration_decrypt_json_impl(box: dict[str, Any], password: str) -> dict[str, Any]:
    if not isinstance(box, dict):
        raise ValueError("迁移包凭据格式不受支持。")
    schema = box.get("schema")
    if schema == MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA:
        if not _migration_cryptography_available():
            raise ValueError("这个迁移包使用 AES-GCM，需要当前 Python 环境安装 cryptography 才能解密。")
        return _migration_decrypt_json_aesgcm(box, password)
    if schema == MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA:
        if not _migration_openssl_available():
            raise ValueError("这个迁移包使用 OpenSSL 后备加密；当前环境找不到 openssl，不能解密。")
        return _migration_decrypt_json_openssl(box, password)
    raise ValueError("迁移包凭据格式不受支持。")


def _hydrate_preview_config_from_latest_bundle(current_cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_hydrate_preview_config_from_latest_bundle", current_cfg, config_path=config_path, command_name=command_name)


def _is_preview_config_root(config_path: str = "", *, command_name: str = "mms") -> bool:
    return _call_backend("_is_preview_config_root", config_path, command_name=command_name)


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_model_source_status_for_snapshot", config_path, command_name=command_name)


def build_config_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend("build_config_snapshot", *args, **kwargs)


def build_config_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_plan import build_config_plan as build_config_plan_impl

    return build_config_plan_impl(*args, **kwargs)


def build_preferences_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_apply import build_preferences_plan as build_preferences_plan_impl

    return build_preferences_plan_impl(*args, **kwargs)


def apply_preferences_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_apply import apply_preferences_plan as apply_preferences_plan_impl

    return apply_preferences_plan_impl(*args, **kwargs)


def apply_config_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_apply import apply_config_plan as apply_config_plan_impl

    return apply_config_plan_impl(*args, **kwargs)


def apply_registry_v2_preview_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_apply import apply_registry_v2_preview_plan as apply_registry_v2_preview_plan_impl

    return apply_registry_v2_preview_plan_impl(*args, **kwargs)


def _provider_summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend("_provider_summary", *args, **kwargs)


def _mapping_digest(payload: Any) -> str:
    return _call_backend("_mapping_digest", payload)


def _MIGRATION_BUNDLE_SCHEMA() -> str:
    return str(getattr(_backend(), "_MIGRATION_BUNDLE_SCHEMA"))


def _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA() -> str:
    return str(getattr(_backend(), "_MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA"))


def _migration_config_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    provider_rows = snapshot.get("providers") if isinstance(snapshot.get("providers"), list) else []
    providers: list[dict[str, Any]] = []
    for row in provider_rows:
        if not isinstance(row, dict):
            continue
        provider_id = _safe_text(row.get("id"))
        if not provider_id:
            continue
        provider = {
            "id": provider_id,
            "name": _safe_text(row.get("name") or provider_id),
            "enabled": row.get("enabled", True) is not False,
            "role": _safe_text(row.get("role") or "auto"),
            "priority": _normalize_priority(row.get("priority", 100)),
            "family_priority_overrides": _normalize_family_priority_overrides(row.get("family_priority_overrides")),
            "claude_1m_mode": _safe_text(row.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(row.get("timezone")),
            "note": _safe_text(row.get("note")),
            "models_endpoint": _safe_text(row.get("models_endpoint") or "/models"),
            "protocols": [str(item) for item in (row.get("protocols") or []) if item],
            "supported_clis": [str(item) for item in (row.get("supported_clis") or []) if item],
            "openai_base_url": _safe_text(row.get("openai_base_url") or row.get("effective_openai_base_url")),
            "anthropic_base_url": _safe_text(row.get("anthropic_base_url") or row.get("effective_anthropic_base_url")),
            "fallback_models": _normalize_model_list(row.get("approved_route_models") or row.get("fallback_models")),
            "extra_models": _normalize_model_list(row.get("extra_models")),
            "hidden_models": _normalize_model_list(row.get("hidden_models")),
            "models": [],
        }
        model_rows = []
        for model_row in row.get("models") if isinstance(row.get("models"), list) else []:
            if not isinstance(model_row, dict):
                continue
            model_id = _safe_text(model_row.get("id") or model_row.get("model"))
            if not model_id or _safe_text(model_row.get("source")) == "derived_alias":
                continue
            model_rows.append(
                {
                    "id": model_id,
                    "source": _safe_text(model_row.get("source") or "migration"),
                    "visible": model_row.get("visible", True) is not False,
                    "favorite": model_row.get("favorite") is True,
                }
            )
        if model_rows:
            provider["models"] = model_rows
        else:
            provider.pop("models", None)
        providers.append({key: value for key, value in provider.items() if value not in ("", {}, [])})

    raw_config: dict[str, Any] = {}
    if providers:
        raw_config["providers"] = providers
    provider_default = _safe_text(snapshot.get("provider_default"))
    if provider_default:
        raw_config["provider"] = {"default": provider_default}
    for key in ("rescue", "vision_sidecar", "ui", "opencode"):
        value = snapshot.get(key)
        if isinstance(value, dict) and value:
            raw_config[key] = _sanitize_for_output(value)
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    if runtime:
        coding: dict[str, Any] = {}
        preferred_cli = _safe_text(runtime.get("preferred_cli"))
        coding_model = _safe_text(runtime.get("coding_preset_model"))
        if preferred_cli:
            coding["cli"] = preferred_cli
        if coding_model:
            coding["model"] = coding_model
        if coding:
            raw_config["presets"] = {"coding": coding}
    return raw_config


def _migration_payload_config_from_cfg(cfg: dict[str, Any], *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    snapshot = build_config_snapshot(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    exported = _migration_config_from_snapshot(snapshot)
    for key in ("load_balance",):
        value = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
        if value:
            exported[key] = _sanitize_for_output(value)
    return exported


def _migration_preferences_payload(config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    target_path = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    prefs = _load_preferences_raw(target_path)
    payload: dict[str, Any] = {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    disabled_clis = _normalize_model_list(launch.get("disabled_clis"))
    if disabled_clis:
        payload.setdefault("launch", {})["disabled_clis"] = disabled_clis
    session_surfaces = prefs.get("session_surfaces") if isinstance(prefs.get("session_surfaces"), dict) else {}
    disabled = session_surfaces.get("disabled") if isinstance(session_surfaces.get("disabled"), dict) else {}
    normalized_disabled: dict[str, list[str]] = {}
    for key in ("skills", "mcp", "hooks"):
        values = _normalize_model_list(disabled.get(key))
        if values:
            normalized_disabled[key] = values
    if normalized_disabled:
        payload["session_surfaces"] = {"disabled": normalized_disabled}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    managed_root = _safe_text(assets.get("managed_root"))
    if managed_root:
        payload["assets"] = {"managed_root": managed_root}
    return payload


def _migration_collect_credentials(cfg: dict[str, Any]) -> list[dict[str, str]]:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    mms_core = _load_mms_core()
    credentials: list[dict[str, str]] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = _safe_text(provider.get("id"))
        if not provider_id:
            continue
        try:
            raw = mms_core.load_provider_credentials(provider_id)
        except Exception:
            raw = {}
        api_key = _safe_text(raw.get("api_key") or provider.get("api_key"))
        openai_api_key = _safe_text(raw.get("openai_api_key") or provider.get("openai_api_key"))
        if not api_key and not openai_api_key:
            continue
        openai_base = _safe_text(raw.get("openai_base_url") or raw.get("base_url") or provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url"))
        anthropic_base = _safe_text(raw.get("anthropic_base_url") or provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
        credentials.append(
            {
                "provider_id": provider_id,
                "base_url": (openai_base or anthropic_base).rstrip("/"),
                "openai_base_url": openai_base.rstrip("/"),
                "anthropic_base_url": anthropic_base.rstrip("/"),
                "api_key": api_key or openai_api_key,
                "openai_api_key": openai_api_key,
            }
        )
    return credentials

def build_migration_export(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    cfg = _hydrate_preview_config_from_latest_bundle(cfg, config_path=config_path, command_name=command_name)
    include_credentials = _truthy(payload.get("include_credentials") or payload.get("include_secrets"), False)
    password = _safe_text(payload.get("password") or payload.get("passphrase"))
    warnings = [
        "OAuth / Claude / Codex 原生登录态不会进入迁移包；另一台机器仍需人工登录原生 CLI。",
        "Claude account、proxy/no_proxy、home_dir 等 human-only 配置不会被自动迁移。",
    ]
    policy_path = _policy_path_for_config(config_path)
    bundle: dict[str, Any] = {
        "schema": _MIGRATION_BUNDLE_SCHEMA(),
        "created_at": _now_iso(),
        "source": {
            "command": command_name,
            "version": _version_info_for_snapshot(command_name),
            "config_root": _config_root_for_snapshot(config_path),
            "config_path": os.path.abspath(os.path.expanduser(config_path)) if config_path else "",
            "preferences_path": os.path.abspath(os.path.expanduser(preferences_path)) if preferences_path else "",
        },
        "security": {
            "contains_credentials": False,
            "credential_box": "none",
            "oauth_state": "excluded",
            "native_cli_auth": "excluded",
            "redaction": "api_key/password/token fields are never stored in payload",
        },
        "payload": {
            "config": _migration_payload_config_from_cfg(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name),
            "model_policy": _load_json_file(policy_path),
            "preferences": _migration_preferences_payload(config_path=config_path, preferences_path=preferences_path),
        },
        "warnings": warnings,
    }
    credential_count = 0
    if include_credentials:
        crypto_backend = _migration_secret_crypto_backend()
        if len(password) < 8:
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": ["包含 API Key 的迁移包必须输入至少 8 位迁移密码。"],
                "crypto_available": _migration_crypto_available(),
                "crypto_backend": crypto_backend,
            }
        if crypto_backend == "none":
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": ["当前 Python 环境缺少 cryptography，且找不到 openssl，不能导出包含 API Key 的加密迁移包。"],
                "crypto_available": False,
                "crypto_backend": crypto_backend,
            }
        credentials = _migration_collect_credentials(cfg)
        credential_count = len(credentials)
        credential_payload = {
            "schema": "mms.config_migration_credentials_payload.v1",
            "created_at": _now_iso(),
            "credentials": credentials,
        }
        try:
            encrypted_credentials = _migration_encrypt_json(credential_payload, password)
        except Exception as exc:
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": [f"API Key 加密失败：{type(exc).__name__}: {exc}"],
                "crypto_available": _migration_crypto_available(),
                "crypto_backend": crypto_backend,
            }
        bundle["encrypted_credentials"] = encrypted_credentials
        bundle["security"]["contains_credentials"] = bool(credentials)
        bundle["security"]["credential_box"] = (
            "encrypted-aesgcm"
            if encrypted_credentials.get("schema") == _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA()
            else "encrypted-openssl-cbc-hmac"
        )
        bundle["security"]["credential_crypto_backend"] = crypto_backend
    model_policy = (bundle.get("payload") or {}).get("model_policy") if isinstance(bundle.get("payload"), dict) else {}
    summary = {
        "providers": len((bundle.get("payload", {}).get("config", {}).get("providers") if isinstance(bundle.get("payload"), dict) else []) or []),
        "policy_models": len((model_policy.get("models") if isinstance(model_policy, dict) else {}) or {}),
        "preferences": bool((bundle.get("payload") or {}).get("preferences")),
        "credentials": credential_count,
        "encrypted_credentials": include_credentials,
    }
    bundle["summary"] = summary
    return {
        "ok": True,
        "schema": "mms.config_migration_export_result.v1",
        "status": "ready",
        "bundle": bundle,
        "summary": summary,
        "crypto_available": _migration_crypto_available(),
        "crypto_backend": _migration_secret_crypto_backend(),
        "filename": f"mms-config-migration-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    }


def _parse_migration_bundle(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw = payload.get("bundle") or payload.get("migration_bundle") or payload.get("text") or payload.get("raw")
    errors: list[str] = []
    bundle: Any = {}
    if isinstance(raw, dict):
        bundle = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            errors.append("请先粘贴或上传迁移包 JSON。")
        else:
            try:
                bundle = json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"迁移包 JSON 解析失败：{exc}")
    else:
        errors.append("请提供迁移包 JSON。")
    if not isinstance(bundle, dict):
        errors.append("迁移包必须是 JSON 对象。")
        bundle = {}
    if bundle and bundle.get("schema") != _MIGRATION_BUNDLE_SCHEMA():
        errors.append(f"迁移包 schema 不支持：{bundle.get('schema') or '-'}")
    return bundle, errors


def _migration_decrypted_credentials(bundle: dict[str, Any], password: str) -> tuple[list[dict[str, str]], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    box = bundle.get("encrypted_credentials") if isinstance(bundle.get("encrypted_credentials"), dict) else {}
    if not box:
        return [], warnings, errors
    if not password:
        errors.append("这个迁移包包含加密 API Key；请输入迁移密码后再预览或导入。")
        return [], warnings, errors
    try:
        payload = _migration_decrypt_json(box, password)
    except Exception as exc:
        errors.append(f"迁移密码错误或凭据已损坏：{type(exc).__name__}: {exc}")
        return [], warnings, errors
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), list) else []
    result: list[dict[str, str]] = []
    for item in credentials:
        if not isinstance(item, dict):
            continue
        provider_id = _safe_text(item.get("provider_id"))
        api_key = _safe_text(item.get("api_key"))
        openai_api_key = _safe_text(item.get("openai_api_key"))
        if not provider_id or (not api_key and not openai_api_key):
            continue
        result.append(
            {
                "provider_id": provider_id,
                "base_url": _safe_text(item.get("base_url")).rstrip("/"),
                "openai_base_url": _safe_text(item.get("openai_base_url")).rstrip("/"),
                "anthropic_base_url": _safe_text(item.get("anthropic_base_url")).rstrip("/"),
                "api_key": api_key or openai_api_key,
                "openai_api_key": openai_api_key,
            }
        )
    if not result:
        warnings.append("迁移包声明了加密凭据，但没有可导入的 provider API Key。")
    return result, warnings, errors


def _safe_local_command_name(command_name: str = "mms") -> str:
    command = _safe_text(command_name or "mms") or "mms"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", command):
        return "mms"
    return command


def _migration_start_status_from_snapshot(snapshot: dict[str, Any], *, command_name: str = "mms", disabled_clis_override: list[str] | None = None) -> dict[str, Any]:
    command = _safe_local_command_name(command_name)
    providers = [item for item in (snapshot.get("providers") if isinstance(snapshot.get("providers"), list) else []) if isinstance(item, dict)]
    enabled = [item for item in providers if item.get("enabled", True) is not False]
    missing_key = [_safe_text(item.get("id")) for item in enabled if not item.get("has_api_key")]
    missing_url = [
        _safe_text(item.get("id"))
        for item in enabled
        if not _safe_text(item.get("openai_base_url") or item.get("anthropic_base_url") or item.get("effective_openai_base_url") or item.get("effective_anthropic_base_url"))
    ]
    missing_models = [_safe_text(item.get("id")) for item in enabled if int(item.get("model_count") or 0) <= 0]
    ready_providers = [
        _safe_text(item.get("id"))
        for item in enabled
        if item.get("has_api_key")
        and int(item.get("model_count") or 0) > 0
        and _safe_text(item.get("openai_base_url") or item.get("anthropic_base_url") or item.get("effective_openai_base_url") or item.get("effective_anthropic_base_url"))
    ]
    source_status = snapshot.get("model_source_status") if isinstance(snapshot.get("model_source_status"), dict) else {}
    root = source_status.get("root") if isinstance(source_status.get("root"), dict) else {}
    bundle = source_status.get("generated_bundle") if isinstance(source_status.get("generated_bundle"), dict) else {}
    preview_root = root.get("mode") == "preview"
    bundle_verified = bool(bundle.get("verified"))
    bundle_runtime_ready = bundle.get("runtime_ready") is True
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    preferred_cli = _safe_text(runtime.get("preferred_cli") or "opencode")
    coding_model = _safe_text(runtime.get("coding_preset_model"))
    disabled_clis = list(disabled_clis_override or [])
    if not disabled_clis:
        session_assets = snapshot.get("session_assets") if isinstance(snapshot.get("session_assets"), dict) else {}
        cli_visibility = session_assets.get("cli_visibility") if isinstance(session_assets.get("cli_visibility"), dict) else {}
        disabled_clis = _normalize_model_list(cli_visibility.get("disabled"))
    blockers: list[dict[str, Any]] = []
    if not enabled:
        blockers.append({"id": "no_enabled_provider", "label": "没有启用通道", "detail": "请先导入或启用至少一个 provider。"})
    if missing_key:
        blockers.append({"id": "missing_api_key", "label": "缺少 API Key", "detail": "这些通道没有 Key，无法直接开始工作。", "providers": missing_key})
    if missing_url:
        blockers.append({"id": "missing_base_url", "label": "缺少 Base URL", "detail": "这些通道没有 OpenAI/Anthropic Base URL。", "providers": missing_url})
    if missing_models:
        blockers.append({"id": "missing_models", "label": "缺少模型", "detail": "这些通道没有可用模型，请拉取或手动添加模型。", "providers": missing_models})
    if preview_root and not bundle_verified:
        blockers.append({"id": "bundle_not_verified", "label": "预览 Bundle 未验证", "detail": "preview root 需要 latest-approved bundle 验证通过后更稳。"})
    if preferred_cli in disabled_clis:
        blockers.append({"id": "preferred_cli_disabled", "label": "首选 CLI 已默认关闭", "detail": f"{preferred_cli} 在 preferences 中被关闭；启动后请换 CLI 或先打开。"})
    provider_ready = bool(bundle_runtime_ready if preview_root else ready_providers)
    ready_to_work = provider_ready and preferred_cli not in disabled_clis
    start_command = command
    return {
        "schema": "mms.config_migration_start_status.v1",
        "ready_to_work": ready_to_work,
        "start_command": start_command,
        "copy_command": start_command,
        "preferred_cli": preferred_cli,
        "coding_model": coding_model,
        "command_name": command,
        "target_mode": _safe_text(root.get("mode") or ("preview" if preview_root else "stable")),
        "config_root": _safe_text(root.get("config_root") or source_status.get("config_root") or _config_root_for_snapshot(snapshot.get("paths", {}).get("config") if isinstance(snapshot.get("paths"), dict) else "")),
        "terminal_launch_available": sys.platform == "darwin",
        "provider_count": len(providers),
        "enabled_provider_count": len(enabled),
        "ready_provider_ids": ready_providers,
        "missing_api_key_provider_ids": missing_key,
        "missing_base_url_provider_ids": missing_url,
        "missing_model_provider_ids": missing_models,
        "preview_bundle": {
            "verified": bundle_verified,
            "runtime_ready": bundle_runtime_ready,
            "status": _safe_text(bundle.get("status")),
            "missing_api_key_count": int(bundle.get("router_missing_api_key_count") or 0),
            "missing_base_url_count": int(bundle.get("router_missing_base_url_count") or 0),
        },
        "blockers": blockers,
        "notes": [
            "按钮只启动当前 MMS 命令，不会迁移 OAuth / Claude / Codex 原生登录态。",
            "如果 API Key 已随加密迁移包导入，通常可以直接打开终端运行。",
        ],
    }

def build_migration_start_status(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    del payload
    snapshot = build_config_snapshot(current_cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    prefs = _load_preferences_raw(_preferences_target_path(config_path=config_path, preferences_path=preferences_path))
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    disabled_clis = _normalize_model_list(launch.get("disabled_clis"))
    return _migration_start_status_from_snapshot(snapshot, command_name=command_name, disabled_clis_override=disabled_clis)

def start_migration_work_session(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    status = build_migration_start_status(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    command = _safe_text(status.get("start_command") or _safe_local_command_name(command_name))
    cwd = os.getcwd()
    shell_command = f"cd {shlex.quote(cwd)} && {command}"
    if sys.platform != "darwin":
        return {
            "ok": False,
            "schema": "mms.config_migration_start_result.v1",
            "status": "unsupported_platform",
            "errors": ["当前系统不支持从 WebUI 自动打开终端；可以复制启动命令手动运行。"],
            "command": command,
            "shell_command": shell_command,
            "start_status": status,
        }
    script = f'tell application "Terminal" to activate\ntell application "Terminal" to do script {json.dumps(shell_command)}'
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.config_migration_start_result.v1",
            "status": "failed",
            "errors": [f"打开终端失败：{type(exc).__name__}: {exc}"],
            "command": command,
            "shell_command": shell_command,
            "start_status": status,
        }
    return {
        "ok": True,
        "schema": "mms.config_migration_start_result.v1",
        "status": "started",
        "command": command,
        "shell_command": shell_command,
        "cwd": cwd,
        "start_status": status,
    }


def _migration_provider_payload(provider: dict[str, Any]) -> dict[str, Any]:
    provider_id = _safe_text(provider.get("id"))
    result = {
        "id": provider_id,
        "original_id": provider_id,
        "name": _safe_text(provider.get("name") or provider_id),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": _normalize_priority(provider.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(provider.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(provider.get("claude_1m_mode") or "auto") or "auto",
        "timezone": _safe_text(provider.get("timezone")),
        "note": _safe_text(provider.get("note")),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "/models"),
        "protocols": [str(item) for item in (provider.get("protocols") or []) if item],
        "supported_clis": [str(item) for item in (provider.get("supported_clis") or []) if item],
        "openai_base_url": _safe_text(provider.get("openai_base_url") or provider.get("default_openai_base_url") or provider.get("base_url")),
        "anthropic_base_url": _safe_text(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url")),
        "fallback_models": _normalize_model_list(provider.get("fallback_models") or provider.get("approved_route_models")),
        "extra_models": _normalize_model_list(provider.get("extra_models")),
        "hidden_models": _normalize_model_list(provider.get("hidden_models")),
    }
    models = []
    for row in provider.get("models") if isinstance(provider.get("models"), list) else []:
        if isinstance(row, dict):
            model_id = _safe_text(row.get("id") or row.get("model"))
            if model_id:
                models.append({"id": model_id, "visible": row.get("visible", True) is not False})
        else:
            model_id = _safe_text(row)
            if model_id:
                models.append({"id": model_id, "visible": True})
    if models:
        result["models"] = models
    return {key: value for key, value in result.items() if value not in ("", {}, [])}


def _migration_preferences_apply_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    prefs = ((bundle.get("payload") or {}).get("preferences") if isinstance(bundle.get("payload"), dict) else {}) or {}
    prefs = prefs if isinstance(prefs, dict) else {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    session_surfaces = prefs.get("session_surfaces") if isinstance(prefs.get("session_surfaces"), dict) else {}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    return {
        "disabled_clis": _normalize_model_list(launch.get("disabled_clis")),
        "disabled": (session_surfaces.get("disabled") if isinstance(session_surfaces.get("disabled"), dict) else {}) or {},
        "assets": {
            "managed_enabled": bool(_safe_text(assets.get("managed_root"))),
            "managed_root": _safe_text(assets.get("managed_root")),
        },
    }


def _migration_draft_from_bundle(current_cfg: dict[str, Any], bundle: dict[str, Any], credentials: list[dict[str, str]], *, config_path: str = "") -> dict[str, Any]:
    policy_payload = _load_json_file(_policy_path_for_config(config_path))
    current_providers = {
        _safe_text(row.get("id")): _migration_provider_payload(row)
        for row in [_provider_summary(item, policy_payload=policy_payload) for item in current_cfg.get("providers", []) if isinstance(item, dict)]
        if _safe_text(row.get("id"))
    }
    payload = bundle.get("payload") if isinstance(bundle.get("payload"), dict) else {}
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    incoming_providers = config.get("providers") if isinstance(config.get("providers"), list) else []
    for provider in incoming_providers:
        if not isinstance(provider, dict):
            continue
        normalized = _migration_provider_payload(provider)
        provider_id = _safe_text(normalized.get("id"))
        if provider_id:
            current_providers[provider_id] = normalized
    for update in credentials:
        provider_id = _safe_text(update.get("provider_id"))
        if not provider_id:
            continue
        provider = current_providers.setdefault(provider_id, {"id": provider_id, "name": provider_id, "enabled": True})
        provider["update_credentials"] = True
        provider["api_key"] = _safe_text(update.get("api_key"))
        provider["openai_api_key"] = _safe_text(update.get("openai_api_key"))
        if _safe_text(update.get("openai_base_url")):
            provider["openai_base_url"] = _safe_text(update.get("openai_base_url"))
        if _safe_text(update.get("anthropic_base_url")):
            provider["anthropic_base_url"] = _safe_text(update.get("anthropic_base_url"))
        if not _safe_text(provider.get("openai_base_url")) and not _safe_text(provider.get("anthropic_base_url")) and _safe_text(update.get("base_url")):
            provider["openai_base_url"] = _safe_text(update.get("base_url"))

    draft: dict[str, Any] = {"providers": list(current_providers.values())}
    provider_default = _safe_text((config.get("provider") if isinstance(config.get("provider"), dict) else {}).get("default"))
    if provider_default:
        draft["provider_default"] = provider_default
    for key in ("rescue", "vision_sidecar", "ui", "opencode", "load_balance"):
        value = config.get(key) if isinstance(config.get(key), dict) else {}
        if value:
            draft[key] = value
    presets = config.get("presets") if isinstance(config.get("presets"), dict) else {}
    coding = presets.get("coding") if isinstance(presets.get("coding"), dict) else {}
    runtime: dict[str, Any] = {}
    if _safe_text(coding.get("cli")):
        runtime["preferred_cli"] = _safe_text(coding.get("cli"))
    if _safe_text(coding.get("model")):
        runtime["coding_preset_model"] = _safe_text(coding.get("model"))
    if runtime:
        draft["runtime"] = runtime
    model_policy = payload.get("model_policy") if isinstance(payload.get("model_policy"), dict) else {}
    if model_policy:
        draft["model_policy_import"] = model_policy
    return draft


def _merge_model_policy_import(policy_before: dict[str, Any], incoming: Any) -> dict[str, Any]:
    if not isinstance(incoming, dict) or not incoming:
        return policy_before
    original = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy.setdefault("version", incoming.get("version") if isinstance(incoming.get("version"), int) else 1)
    policy.setdefault("description", "User-maintained model visibility and preference policy. MMS never stores provider secrets here.")
    for section in ("models", "projects"):
        src = incoming.get(section) if isinstance(incoming.get(section), dict) else {}
        if not src:
            continue
        dst = policy.setdefault(section, {})
        if not isinstance(dst, dict):
            dst = {}
            policy[section] = dst
        for key, value in src.items():
            key_text = _safe_text(key)
            if not key_text:
                continue
            dst[key_text] = _sanitize_for_output(value)
    if _mapping_digest(policy) != _mapping_digest(original):
        policy["updated_at"] = _now_iso()
    elif isinstance(original, dict) and "updated_at" in original:
        policy["updated_at"] = original["updated_at"]
    return policy


def _build_migration_import_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    current_cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    current_cfg = _hydrate_preview_config_from_latest_bundle(current_cfg, config_path=config_path, command_name=command_name)
    bundle, parse_errors = _parse_migration_bundle(payload)
    warnings = [
        "导入不会迁移 OAuth / Claude / Codex 原生登录态；只处理 WebUI 可审计配置、model-policy、preferences 和可选加密 API Key。",
        "导入采用 merge 策略：同 ID provider 覆盖，当前机器独有 provider 默认保留。",
    ]
    credentials: list[dict[str, str]] = []
    if not parse_errors:
        credentials, cred_warnings, cred_errors = _migration_decrypted_credentials(bundle, _safe_text(payload.get("password") or payload.get("passphrase")))
        warnings.extend(cred_warnings)
        parse_errors.extend(cred_errors)
    if parse_errors:
        return {
            "ok": False,
            "schema": "mms.config_migration_import_plan.v1",
            "status": "blocked",
            "errors": parse_errors,
            "warnings": warnings,
        }
    draft = _migration_draft_from_bundle(current_cfg, bundle, credentials, config_path=config_path)
    config_plan = build_config_plan(current_cfg, {"draft": draft}, config_path=config_path, preferences_path=preferences_path, include_secrets=True, command_name=command_name)
    pref_payload = _migration_preferences_apply_payload(bundle)
    pref_plan = build_preferences_plan(pref_payload, config_path=config_path, preferences_path=preferences_path)
    ok = bool(config_plan.get("ok") and pref_plan.get("ok"))
    errors = list(config_plan.get("errors") or [])
    summary = {
        "providers": (config_plan.get("summary") or {}).get("providers", 0),
        "credential_updates": len(credentials),
        "policy_models": (config_plan.get("summary") or {}).get("policy_models", 0),
        "preferences_will_write": bool(pref_plan.get("will_write")),
        "target_root": _config_root_for_snapshot(config_path),
        "target_mode": (_model_source_status_for_snapshot(config_path, command_name=command_name).get("root") or {}).get("mode", ""),
    }
    return {
        "ok": ok,
        "schema": "mms.config_migration_import_plan.v1",
        "status": "planned" if ok else "blocked",
        "errors": errors,
        "warnings": [*warnings, *(config_plan.get("warnings") or [])],
        "bundle_summary": bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {},
        "summary": summary,
        "draft": draft,
        "config_plan": config_plan,
        "preferences_payload": pref_payload,
        "preferences_plan": pref_plan,
        "diffs": {
            "config_toml": (config_plan.get("diffs") or {}).get("config_toml", ""),
            "model_policy_json": (config_plan.get("diffs") or {}).get("model_policy_json", ""),
            "credentials": (config_plan.get("diffs") or {}).get("credentials", ""),
            "preferences_toml": pref_plan.get("diff", ""),
        },
    }

def build_migration_import_preview(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    plan = _build_migration_import_plan(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    return _sanitize_for_output(plan)

def apply_migration_import(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_migration"), False):
        return {"ok": False, "schema": "mms.config_migration_import_result.v1", "status": "blocked", "errors": ["导入前必须勾选确认导入。"]}
    if _safe_text(payload.get("confirm_phrase")) != "导入配置":
        return {"ok": False, "schema": "mms.config_migration_import_result.v1", "status": "blocked", "errors": ["确认文字必须输入：导入配置"]}
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:migration-import"
    plan = _build_migration_import_plan(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "schema": "mms.config_migration_import_result.v1",
            "status": "blocked",
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "plan": _sanitize_for_output(plan),
        }
    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    if _is_preview_config_root(config_path, command_name=command_name):
        config_result = apply_registry_v2_preview_plan(
            current_cfg,
            {
                "draft": draft,
                "confirm_v2_preview": True,
                "confirm_phrase": "写入预览DB",
                "reason": reason,
            },
            config_path=config_path,
            preferences_path=preferences_path,
        )
    else:
        config_result = apply_config_plan(
            current_cfg,
            {
                "draft": draft,
                "confirm_save": True,
                "confirm_phrase": "保存配置",
                "reason": reason,
            },
            config_path=config_path,
            preferences_path=preferences_path,
        )
    preferences_result: dict[str, Any] = {"ok": True, "status": "no_change"}
    pref_plan = plan.get("preferences_plan") if isinstance(plan.get("preferences_plan"), dict) else {}
    if config_result.get("ok") and pref_plan.get("will_write"):
        pref_payload = dict(plan.get("preferences_payload") if isinstance(plan.get("preferences_payload"), dict) else {})
        pref_payload.update(
            {
                "confirm_preferences": True,
                "confirm_phrase": "保存偏好",
                "reason": f"{reason}:preferences",
            }
        )
        preferences_result = apply_preferences_plan(pref_payload, config_path=config_path, preferences_path=preferences_path)
    ok = bool(config_result.get("ok") and preferences_result.get("ok"))
    applied_cfg = ((plan.get("config_plan") or {}).get("config") if isinstance(plan.get("config_plan"), dict) else {}) or current_cfg
    start_status = build_migration_start_status(
        applied_cfg if isinstance(applied_cfg, dict) else current_cfg,
        {},
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    return _sanitize_for_output(
        {
            "ok": ok,
            "schema": "mms.config_migration_import_result.v1",
            "status": "imported" if ok else "failed",
            "summary": plan.get("summary") or {},
            "warnings": plan.get("warnings") or [],
            "config_result": config_result,
            "preferences_result": preferences_result,
            "start_status": start_status,
        }
    )
