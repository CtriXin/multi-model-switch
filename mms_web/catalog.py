"""MMS Web catalog adapter (Agent A).

Provides the model/service/preset/workspace catalog and a preview->apply
configuration flow for the MMS Web frontend, per docs/mms-web/API.md.

Design boundaries:
- Catalog reads come from the verified latest-approved bundle
  (``generated/model-registry.latest-approved.json``) through
  ``mms_registry.load_latest_approved_bundle(config_dir=...)`` and a raw
  ``tomllib`` read of ``config.toml``. Provider ordering, protocol fallback and
  account selection logic are NOT re-implemented here.
- Heavy MMS reuse (launch env assembly, audited config writes) happens inside
  an isolated subprocess worker (``catalog_worker.py``) with a dedicated
  ``MMS_CONFIG_ROOT`` and isolated HOME, so host-process module state and the
  real ``~/.config/mms*`` roots stay untouched.
- ``config_root=None`` means "no catalog": no reads of the real HOME, empty
  results plus diagnostics. Applying to real MMS config roots is rejected
  fail-closed (human-only gate).
- No provider/network probes are issued from this module. Secrets never leave
  through snapshot/preview/apply responses; API keys are always masked.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from .errors import WebError

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKER_PATH = Path(__file__).resolve().parent / "catalog_worker.py"

PREVIEW_TTL_SECONDS = 30 * 60
_PROVIDER_LAUNCHABLE_HARNESSES = ("claude", "codex", "opencode", "pi")
_KNOWN_HARNESSES = ("pi", "codex", "claude", "opencode", "gemini", "agy")
# Project identity for model-policy project overlays (docs/MODEL_CONFIG_CONTRACT.md).
PROJECT_ID = "mms-web"
_PROTECTED_ROOT_NAMES = (".config/mms", ".config/mms-next")

# Display-layer family heuristics only; launch truth stays inside MMS.
_FAMILY_RULES = (
    ("claude", "Claude"),
    ("gpt", "GPT"),
    ("codex", "GPT"),
    ("o1", "GPT"),
    ("o3", "GPT"),
    ("o4", "GPT"),
    ("gemini", "Gemini"),
    ("qwen", "Qwen"),
    ("kimi", "Kimi"),
    ("k2", "Kimi"),
    ("k3", "Kimi"),
    ("glm", "GLM"),
    ("minimax", "MiniMax"),
    ("deepseek", "DeepSeek"),
    ("mimo", "MiMo"),
    ("doubao", "Doubao"),
)


def _ensure_repo_on_path() -> None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 12:
        return "••••"
    return f"{text[:4]}…{text[-4:]}"


def _mask_url(value: str) -> str:
    """Mask userinfo and query secrets in a URL for display."""
    text = str(value or "").strip()
    if not text:
        return ""
    masked = re.sub(r"//[^/@]+@", "//***@", text)
    masked = re.sub(r"\?.*$", "?***", masked)
    return masked


def _context_label(tokens) -> str:
    try:
        value = int(tokens)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000}M"
    if value >= 1_000_000:
        return f"{round(value / 1_000_000, 1)}M"
    if value >= 1_000:
        return f"{round(value / 1_000)}K"
    return str(value)


def _model_family(model_name: str) -> str:
    lowered = str(model_name or "").lower()
    for prefix, family in _FAMILY_RULES:
        if lowered.startswith(prefix):
            return family
    return "Other"


def _parse_env_file(text: str) -> dict:
    """Parse MMS credentials.sh KEY=value pairs (read-only display heuristics)."""
    values = {}
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        raw = raw.strip()
        try:
            parsed = shlex.split(raw)
        except ValueError:
            parsed = [raw.strip("'\"")]
        values[key.strip()] = parsed[0] if parsed else ""
    return values


def _slug_provider_id(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug or "gateway"


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class CatalogService:
    """Catalog + preview/apply configuration adapter. See module docstring."""

    def __init__(self, *, config_root: Path | None, state_root: Path):
        self._config_root = (
            Path(os.path.expanduser(str(config_root))).resolve()
            if config_root is not None
            else None
        )
        self._state_root = Path(os.path.expanduser(str(state_root))).resolve()
        self._previews_dir = self._state_root / "previews"

    # ── internals ─────────────────────────────────────────────────────────

    @property
    def config_root(self) -> Path | None:
        return self._config_root

    def _real_home(self) -> Path:
        """Resolve the human's real home without importing MMS core."""
        for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
            raw = str(os.environ.get(key) or "").strip()
            if raw:
                return Path(os.path.expanduser(raw)).resolve()
        return Path(os.path.expanduser("~")).resolve()

    def _protected_roots(self) -> list[Path]:
        home = self._real_home()
        roots = []
        for name in _PROTECTED_ROOT_NAMES:
            try:
                roots.append((home / name).resolve())
            except OSError:
                continue
        return roots

    @staticmethod
    def _overlaps_protected(root: Path, protected: list[Path]) -> bool:
        """True when root is inside a protected subtree, contains one, or equals one.

        Symlinks are collapsed via resolve() on both sides before comparison.
        """
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

    def _is_protected_real_root(self) -> bool:
        if self._config_root is None:
            return False
        return self._overlaps_protected(self._config_root, self._protected_roots())

    def _state_root_protected(self) -> bool:
        return self._overlaps_protected(self._state_root, self._protected_roots())

    def _require_config_root(self) -> Path:
        if self._config_root is None:
            raise WebError("CONFIG_ROOT_DISABLED", "目录服务未配置 config root，无法执行此操作", status=409)
        return self._config_root

    def _require_safe_state_root(self) -> None:
        if self._state_root_protected():
            raise WebError(
                "STATE_ROOT_PROTECTED",
                "state_root 落在真实 MMS 配置保护区内，拒绝写入",
                status=409,
            )

    def _raw_config(self) -> dict:
        root = self._require_config_root()
        config_path = root / "config.toml"
        if not config_path.exists():
            return {}
        try:
            with open(config_path, "rb") as handle:
                cfg = tomllib.loads(handle.read().decode("utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def _credentials_values(self) -> dict:
        root = self._require_config_root()
        credentials_path = root / "credentials.sh"
        if not credentials_path.exists():
            return {}
        try:
            return _parse_env_file(credentials_path.read_text(encoding="utf-8"))
        except OSError:
            return {}

    def _local_setup(self) -> bool:
        return bool(self._config_root and self._config_root.resolve() == (self._state_root / "config").resolve())

    def _load_bundle(self, diagnostics: list) -> dict:
        """Load the verified latest-approved bundle; secrets stay in-process."""
        root = self._require_config_root()
        _ensure_repo_on_path()
        try:
            import mms_registry

            bundle = mms_registry.load_latest_approved_bundle(config_dir=root, include_secret=True)
        except FileNotFoundError:
            if self._local_setup():
                return {}
            diagnostics.append(
                {
                    "code": "BUNDLE_MISSING",
                    "message": "未找到已批准的模型目录 bundle（generated/model-registry.latest-approved.json），模型列表为空",
                }
            )
            return {}
        except Exception:
            diagnostics.append(
                {
                    "code": "BUNDLE_INVALID",
                    "message": "已批准模型目录 bundle 校验失败（hash 或格式异常），模型列表为空",
                }
            )
            return {}
        return bundle

    def _config_revision(self) -> str:
        if self._config_root is None:
            return ""
        digest = hashlib.sha256()
        for name in ("config.toml", "credentials.sh", "generated/model-registry.latest-approved.json"):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            try:
                digest.update((self._config_root / name).read_bytes())
            except OSError:
                digest.update(b"")
        return digest.hexdigest()[:16]

    def _secure_write_json(self, path: Path, payload: dict) -> None:
        """Atomic 0600 JSON write with no permission window."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _cleanup_expired_previews(self) -> None:
        if not self._previews_dir.exists():
            return
        now = time.time()
        for record_path in self._previews_dir.glob("*.json"):
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
                if float(record.get("expiresAt") or 0) < now:
                    record_path.unlink()
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    def _run_worker(self, payload: dict, *, timeout: float = 60.0) -> dict:
        root = self._require_config_root()
        if payload.get("command") == "resolve-launch":
            from .runtime import snapshot_config
            root = snapshot_config(root, self._state_root, published_credentials_only=self._local_setup())
            payload = {**payload, "config_root": str(root)}
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "MMS_CONFIG_ROOT": str(root),
            "HOME": str(self._state_root / "launch-home"),
            "MMS_WEB_WORKER": "1",
        }
        # Pass the real-home guard explicitly: the worker HOME is isolated, so
        # env-based real-home discovery would otherwise be blind there.
        payload = dict(payload)
        payload["realHome"] = str(self._real_home())
        for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "LANG", "LC_ALL", "TMPDIR"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        (self._state_root / "launch-home").mkdir(parents=True, exist_ok=True)
        process = subprocess.run(
            [sys.executable, str(_WORKER_PATH)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(_REPO_ROOT),
            timeout=timeout,
        )
        stdout = (process.stdout or "").strip()
        if not stdout:
            raise WebError(
                "WORKER_FAILED",
                "目录 worker 执行失败，请重试或查看服务端日志",
                status=500,
            )
        try:
            result = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            raise WebError("WORKER_FAILED", "目录 worker 返回了无法解析的结果", status=500)
        if not result.get("ok"):
            raise WebError(
                str(result.get("code") or "WORKER_FAILED"),
                str(result.get("message") or "目录 worker 执行失败"),
                status=400,
            )
        if payload.get("command") == "resolve-launch":
            result.setdefault("runtime", {})["_webConfigRoot"] = str(root)
        return result

    # ── contract surface ──────────────────────────────────────────────────

    def capabilities(self) -> dict:
        if self._config_root is None:
            return {"catalogRead": False, "configure": False}
        read = (self._config_root / "config.toml").exists() or (self._config_root / "generated").exists()
        if self._is_protected_real_root() or self._state_root_protected():
            # Real MMS roots may be displayed but never written by the web UI;
            # a state root inside the protected subtree is equally fail-closed.
            return {"catalogRead": read, "configure": False}
        return {"catalogRead": read, "configure": True}

    def snapshot(self) -> dict:
        diagnostics: list[dict] = []
        if self._config_root is None:
            return {
                "models": [],
                "services": [],
                "presets": [],
                "workspaces": [],
                "diagnostics": [
                    {
                        "code": "CONFIG_ROOT_DISABLED",
                        "message": "未配置 config root，目录返回空数据",
                    }
                ],
            }

        cfg = self._raw_config()
        if not cfg and not self._local_setup():
            diagnostics.append(
                {"code": "CONFIG_MISSING", "message": "config root 下缺少 config.toml 或文件不可读"}
            )
        bundle = self._load_bundle(diagnostics)
        cfg = self._published_config(cfg, bundle)
        payloads = bundle.get("payloads") or {}
        router_routes = (payloads.get("router") or {}).get("routes") or {}
        lineup_routes = (payloads.get("lineup") or {}).get("routes") or {}
        policy_payload = payloads.get("policy") or {}
        policy_models = policy_payload.get("models") or {}
        policy_projects = policy_payload.get("projects") or {}
        project_policy = policy_projects.get(PROJECT_ID) if isinstance(policy_projects, dict) else None
        project_policy = project_policy if isinstance(project_policy, dict) else {}
        if project_policy:
            diagnostics.append(
                {
                    "code": "POLICY_PROJECT_OVERLAY_APPLIED",
                    "message": f"已应用 model-policy 的 project overlay（project: {PROJECT_ID}）",
                }
            )

        def _project_lists(field: str) -> set[str]:
            values = project_policy.get(field)
            if not isinstance(values, list):
                return set()
            return {str(item).strip() for item in values if str(item).strip()}

        project_allowed = _project_lists("allowed_models")
        project_hidden = _project_lists("hidden_models") | _project_lists("disabled_models")
        project_favorite = _project_lists("favorite_models")
        whitelist_mode = project_policy.get("default_visible") is False

        def _apply_project_overlay(model_name: str, policy_entry: dict) -> tuple[bool, bool, str]:
            """Apply documented project-overlay semantics for PROJECT_ID.

            Returns (visible, favorite, hidden_reason). Base visibility from the
            model-level policy entry is evaluated by the caller.
            """
            if model_name in project_hidden:
                return False, False, f"被 project overlay 隐藏（{PROJECT_ID}）"
            show_in = policy_entry.get("show_in")
            if isinstance(show_in, list) and show_in and PROJECT_ID not in {str(v) for v in show_in}:
                return False, False, f"不在 show_in 列表中（{PROJECT_ID}）"
            hide_in = policy_entry.get("hide_in")
            if isinstance(hide_in, list) and PROJECT_ID in {str(v) for v in hide_in}:
                return False, False, f"被 hide_in 隐藏（{PROJECT_ID}）"
            if whitelist_mode and model_name not in project_allowed and model_name not in project_favorite:
                return False, False, f"project overlay 为白名单模式，模型不在允许列表（{PROJECT_ID}）"
            favorite = bool(policy_entry.get("favorite")) or model_name in project_favorite
            return True, favorite, ""

        providers_cfg = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
        providers_by_id = {
            str(item.get("id") or "").strip(): item
            for item in providers_cfg
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        default_provider_id = str((cfg.get("provider") or {}).get("default") or "").strip()
        credentials = self._credentials_values()

        def _provider_name(provider_id: str) -> str:
            entry = providers_by_id.get(provider_id) or {}
            return str(entry.get("name") or provider_id)

        def _provider_leaves(provider_id: str) -> list[dict]:
            leaves = []
            for route in router_routes.values():
                if not isinstance(route, dict):
                    continue
                for leaf in [route.get("primary"), *(route.get("fallbacks") or [])]:
                    if isinstance(leaf, dict) and leaf.get("provider_id") == provider_id:
                        leaves.append(leaf)
            return leaves

        def _provider_has_key(provider_id: str) -> bool:
            if self._local_setup() and bundle:
                return any(leaf.get("api_key") for leaf in _provider_leaves(provider_id))
            prefix = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).upper().strip("_") or "DEFAULT"
            return bool(credentials.get(f"MMS_PROVIDER_{prefix}_API_KEY")
                        or any(leaf.get("api_key") for leaf in _provider_leaves(provider_id)))

        def _provider_base_url(provider_id: str) -> str:
            prefix = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).upper().strip("_") or "DEFAULT"
            configured = (credentials.get(f"MMS_PROVIDER_{prefix}_BASE_URL")
                          or credentials.get(f"MMS_PROVIDER_{prefix}_OPENAI_BASE_URL")
                          or credentials.get(f"MMS_PROVIDER_{prefix}_ANTHROPIC_BASE_URL"))
            if configured and not (self._local_setup() and bundle):
                return configured
            return next((leaf.get("openai_base_url") or leaf.get("anthropic_base_url")
                         for leaf in _provider_leaves(provider_id)
                         if leaf.get("openai_base_url") or leaf.get("anthropic_base_url")), "")

        def _harnesses_for(provider_id: str, model_name: str) -> list[str]:
            """Display-layer harness mapping; launch truth is validated in the worker."""
            entry = providers_by_id.get(provider_id) or {}
            supported = entry.get("supported_clis")
            if isinstance(supported, str):
                supported = [supported]
            supported = {str(item).strip().lower() for item in (supported or []) if str(item).strip()}
            if not supported:
                supported = {"claude", "codex", "opencode"}
            protocols = entry.get("protocols")
            if isinstance(protocols, str):
                protocols = [protocols]
            protocols = {str(item).strip() for item in (protocols or []) if str(item).strip()} or {
                "openai_chat_completions",
                "anthropic_messages",
            }
            harnesses = []
            for cli in _PROVIDER_LAUNCHABLE_HARNESSES:
                if cli in supported:
                    harnesses.append(cli)
                    continue
                # Mirror MMS protocol-compat relaxation for pi/opencode only.
                if cli == "pi" and "openai_chat_completions" in protocols and supported & {"codex", "opencode", "claude"}:
                    harnesses.append(cli)
                elif cli == "pi" and "anthropic_messages" in protocols and "claude" in supported:
                    harnesses.append(cli)
                elif cli == "opencode" and "openai_chat_completions" in protocols and supported & {"codex", "claude"}:
                    harnesses.append(cli)
                elif cli == "opencode" and "anthropic_messages" in protocols and "claude" in supported:
                    harnesses.append(cli)
            return harnesses

        # Models: every provider leaf (primary + fallbacks) yields its own
        # provider-qualified entry, so the same model name served by different
        # providers stays distinguishable and joinable from presets.
        models: list[dict] = []
        seen_model_ids: set[str] = set()
        bundle_model_names: set[str] = set()

        def _append_model_entry(model_name: str, provider_id: str, *, leaf: dict, lineup_leaf: dict, policy_entry: dict, route_role: str) -> None:
            nonlocal seen_model_ids
            model_id = f"{provider_id}:{model_name}"
            bundle_model_names.add(model_name)
            if model_id in seen_model_ids or not provider_id:
                return
            seen_model_ids.add(model_id)

            capabilities_entry = policy_entry.get("capabilities") or {}
            capabilities_entry = capabilities_entry if isinstance(capabilities_entry, dict) else {}
            visible = policy_entry.get("visible", True) is not False
            text_capable = capabilities_entry.get("text", True) is not False
            overlay_visible, overlay_favorite, overlay_reason = _apply_project_overlay(model_name, policy_entry)

            provider_entry = providers_by_id.get(provider_id) or {}
            provider_enabled = provider_entry.get("enabled", True) is not False

            available = True
            reason = ""
            if not visible:
                available, reason = False, "被模型策略隐藏（visible=false）"
            elif not text_capable:
                available, reason = False, "模型策略关闭了文本能力（text=false）"
            elif not overlay_visible:
                available, reason = False, overlay_reason
            elif not provider_enabled:
                available, reason = False, "所属模型服务已禁用"
            elif not (leaf.get("api_key") and (leaf.get("anthropic_base_url") or leaf.get("openai_base_url"))):
                available, reason = False, "路由信息不完整（缺少 Key 或接入地址）"
            else:
                harnesses = _harnesses_for(provider_id, model_name)
                if not harnesses:
                    available, reason = False, "没有可由 Web 启动的 harness 支持该服务"

            display_name = (
                policy_entry.get("display_name")
                or (lineup_leaf.get("display_name") if lineup_leaf else "")
                or model_name
            )
            entry = {
                "id": model_id,
                "name": str(display_name),
                "family": _model_family(model_name),
                "providerId": provider_id,
                "providerName": _provider_name(provider_id),
                "harnesses": _harnesses_for(provider_id, model_name) if available else [],
                "contextLabel": _context_label(
                    capabilities_entry.get("context_window_tokens")
                    or lineup_leaf.get("max_context_tokens")
                ),
                "available": available,
                "favorite": overlay_favorite,
                # Registry approval verifies saved configuration, not a
                # generation request or this service's model capabilities.
                "verified": not self._local_setup(),
            }
            if route_role:
                entry["routeRole"] = route_role
            if reason:
                entry["reason"] = reason
            models.append(entry)

        for model_name, route in router_routes.items():
            route_entry = route if isinstance(route, dict) else {}
            primary = route_entry.get("primary")
            if isinstance(primary, dict):
                policy_entry = policy_models.get(model_name) if isinstance(policy_models, dict) else {}
                policy_entry = policy_entry if isinstance(policy_entry, dict) else {}
                lineup_entry = lineup_routes.get(model_name)
                lineup_leaf = lineup_entry.get("primary") if isinstance(lineup_entry, dict) and isinstance(lineup_entry.get("primary"), dict) else {}
                _append_model_entry(
                    model_name,
                    str(primary.get("provider_id") or "").strip(),
                    leaf=primary,
                    lineup_leaf=lineup_leaf,
                    policy_entry=policy_entry,
                    route_role="primary",
                )
            fallbacks = route_entry.get("fallbacks")
            for fallback in fallbacks if isinstance(fallbacks, list) else []:
                if not isinstance(fallback, dict):
                    continue
                policy_entry = policy_models.get(model_name) if isinstance(policy_models, dict) else {}
                policy_entry = policy_entry if isinstance(policy_entry, dict) else {}
                lineup_entry = lineup_routes.get(model_name)
                lineup_fallbacks = lineup_entry.get("fallbacks") if isinstance(lineup_entry, dict) and isinstance(lineup_entry.get("fallbacks"), list) else []
                lineup_leaf = next(
                    (item for item in lineup_fallbacks if isinstance(item, dict) and item.get("provider_id") == fallback.get("provider_id")),
                    {},
                )
                _append_model_entry(
                    model_name,
                    str(fallback.get("provider_id") or "").strip(),
                    leaf=fallback,
                    lineup_leaf=lineup_leaf,
                    policy_entry=policy_entry,
                    route_role="fallback",
                )

        # Pending/unverified models: manual providers whose hand-entered model
        # lists have not entered the approved bundle yet. They are listed for
        # visibility but stay launch-unavailable until the bundle is refreshed
        # by MMS itself (no probing from here).
        pending_provider_ids: set[str] = set()
        for provider_id, entry in providers_by_id.items():
            if str(entry.get("models_endpoint") or "") != "manual":
                continue
            manual_models = entry.get("fallback_models")
            if not isinstance(manual_models, list):
                continue
            for raw_name in manual_models:
                model_name = str(raw_name or "").strip()
                if not model_name or f"{provider_id}:{model_name}" in seen_model_ids:
                    continue
                pending_provider_ids.add(provider_id)
                model_id = f"{provider_id}:{model_name}"
                if model_id in seen_model_ids:
                    continue
                seen_model_ids.add(model_id)
                can_try = bool(self._local_setup() and not bundle
                               and not (self._config_root / "generated/model-registry.latest-approved.json").exists()
                               and entry.get("enabled", True)
                               and _provider_has_key(provider_id) and _provider_base_url(provider_id))
                models.append(
                    {
                        "id": model_id,
                        "name": model_name,
                        "family": _model_family(model_name),
                        "providerId": provider_id,
                        "providerName": _provider_name(provider_id),
                        "harnesses": _harnesses_for(provider_id, model_name) if can_try else [],
                        "contextLabel": "",
                        "available": can_try,
                        "favorite": False,
                        "verified": False,
                        "reason": "" if can_try else "等待验证：服务尚未进入已批准模型目录，请先在 MMS 内完成验证/导出后再从 Web 启动",
                    }
                )
        if pending_provider_ids and not self._local_setup():
            diagnostics.append(
                {
                    "code": "PENDING_UNVERIFIED_PROVIDERS",
                    "message": "存在仅手工维护模型列表、尚未进入已批准目录的服务（"
                    + ", ".join(sorted(pending_provider_ids))
                    + "）；配置保存不等于连通，需在 MMS 内验证后目录才会更新",
                }
            )

        # Services: provider entries from real config.
        services: list[dict] = []
        provider_model_counts: dict[str, int] = {}
        for model in models:
            pid = model.get("providerId")
            if pid:
                provider_model_counts[pid] = provider_model_counts.get(pid, 0) + 1
        for provider_id, entry in providers_by_id.items():
            enabled = entry.get("enabled", True) is not False
            has_key = _provider_has_key(provider_id)
            has_url = bool(_provider_base_url(provider_id))
            if has_key and has_url:
                status = "configured"
            elif not has_key:
                status = "needs_key"
            else:
                status = "error"
            detail_parts = []
            if not enabled:
                detail_parts.append("已禁用")
            if not has_url:
                detail_parts.append("缺少接入地址")
            if provider_id in pending_provider_ids:
                detail_parts.append("已填写模型，发送第一条消息即可开始验证连接" if self._local_setup() else "模型列表未验证（手工维护）")
            services.append(
                {
                    "id": provider_id,
                    "name": _provider_name(provider_id),
                    "kind": "gateway",
                    "status": status,
                    "modelCount": provider_model_counts.get(provider_id, 0),
                    "detail": "; ".join(detail_parts) if detail_parts else "正常",
                }
            )
        if not providers_by_id and cfg:
            diagnostics.append(
                {"code": "NO_PROVIDERS", "message": "config.toml 中没有任何模型服务（provider）条目"}
            )

        # Presets from real config. modelId is the provider-qualified catalog
        # id (joinable with models[].id); modelName keeps the bare MMS model
        # name; channel reflects the real MMS channel concept (provider gateway
        # or official account), never a guessed provider for account presets.
        presets_cfg = cfg.get("presets") if isinstance(cfg.get("presets"), dict) else {}
        catalog_models_by_id = {model["id"]: model for model in models}
        presets: list[dict] = []
        for name, preset in presets_cfg.items():
            preset = preset if isinstance(preset, dict) else {}
            cli = str(preset.get("cli") or "claude").strip()
            account_id = str(preset.get("account") or "").strip()
            provider_ref = str(preset.get("provider") or "").strip()
            provider_id = (
                providers_by_id.get(provider_ref, {}).get("id")
                if provider_ref and provider_ref in providers_by_id
                else (default_provider_id if not provider_ref or provider_ref == "default" else provider_ref)
            )
            model_name = (
                preset.get("model")
                or preset.get("sonnet")
                or preset.get("opus")
                or preset.get("haiku")
                or preset.get("subagent")
                or ""
            )
            model_name = str(model_name).strip()
            if account_id:
                channel, channel_kind = account_id, "account"
            else:
                channel, channel_kind = provider_id, "provider"
            model_id = f"{provider_id}:{model_name}" if model_name and provider_id and not account_id else ""

            available = True
            reason = ""
            if cli not in _KNOWN_HARNESSES:
                available, reason = False, f"未知 harness：{cli}"
            elif account_id:
                available, reason = False, "该预设使用官方账号通道，Web 首版暂不支持启动"
            elif cli not in _PROVIDER_LAUNCHABLE_HARNESSES:
                available, reason = False, "官方账号 harness 暂不支持从 Web 启动"
            elif provider_id not in providers_by_id:
                available, reason = False, f"模型服务未配置：{provider_id}"
            elif providers_by_id[provider_id].get("enabled", True) is False:
                available, reason = False, "所属模型服务已禁用"
            elif not _provider_has_key(provider_id):
                available, reason = False, "所属模型服务缺少 API Key"
            elif model_name:
                catalog_model = catalog_models_by_id.get(model_id)
                if catalog_model is None:
                    available, reason = False, f"模型不在当前目录中：{model_name}"
                elif not catalog_model.get("available"):
                    available = False
                    reason = str(catalog_model.get("reason") or "模型当前不可用")

            preset_payload = {
                "id": str(name),
                "name": str(name),
                "description": str(preset.get("description") or ""),
                "harness": cli,
                "modelId": model_id or model_name,
                "modelName": model_name,
                "providerId": "" if account_id else provider_id,
                "channel": channel,
                "channelKind": channel_kind,
                "available": available,
            }
            if reason:
                preset_payload["reason"] = reason
            presets.append(preset_payload)

        for model in models:
            if "pi" not in model.get("harnesses", []):
                continue
            presets.append({
                "id": "web:pi:" + model["id"], "name": model["name"],
                "description": model["providerName"] + " · Pi",
                "harness": "pi", "modelId": model["id"],
                "providerId": model["providerId"], "channel": model["providerId"],
                "available": model["available"], "reason": model.get("reason", ""),
            })
        return {
            "models": models,
            "services": services,
            "presets": presets,
            "workspaces": self._workspaces(),
            "diagnostics": diagnostics,
            "revision": self._config_revision(),
        }

    def _workspaces(self) -> list[dict]:
        workspaces: list[dict] = []
        registry_path = self._state_root / "workspaces.json"
        if registry_path.exists():
            try:
                registered = json.loads(registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                registered = []
            for item in registered if isinstance(registered, list) else []:
                if isinstance(item, dict) and item.get("path"):
                    workspaces.append(
                        {
                            "id": str(item.get("id") or ""),
                            "name": str(item.get("name") or Path(item["path"]).name),
                            "path": str(item["path"]),
                        }
                    )
        if not any(item["id"] == "default" for item in workspaces):
            try:
                cwd = os.getcwd()
            except OSError:
                cwd = str(self._state_root)
            workspaces.insert(
                0,
                {
                    "id": "default",
                    "name": Path(cwd).name or "workspace",
                    "path": cwd,
                },
            )
        return workspaces

    # ── configuration preview / apply ─────────────────────────────────────

    def _require_configure(self) -> None:
        capabilities = self.capabilities()
        if not capabilities.get("configure"):
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                "当前 config root 不允许通过 Web 写入配置（真实 MMS 配置仅限人工写入）",
                status=409,
            )

    def _published_config(self, cfg: dict, bundle: dict) -> dict:
        if not self._local_setup() or not bundle:
            return cfg
        payloads = bundle.get("payloads") or {}
        profiles = (payloads.get("profile") or {}).get("profiles") or {}
        providers = []
        for pid, profile in profiles.items():
            models = []
            for name, route in (payloads.get("router") or {}).get("routes", {}).items():
                if any(leaf and leaf.get("provider_id") == pid for leaf in [route.get("primary"), *route.get("fallbacks", [])]):
                    models.append(name)
            providers.append({**profile, "id": pid, "fallback_models": models})
        return {**cfg, "providers": providers}

    def _validate_service_payload(self, payload: dict) -> tuple[str, str, str, list[str], list[str]]:
        service = payload.get("service")
        if not isinstance(payload, dict) or not isinstance(service, dict):
            raise WebError("INVALID_PAYLOAD", "payload.service 必须是对象")
        name = str(service.get("name") or "").strip()
        base_url = str(service.get("baseUrl") or "").strip()
        api_key = str(service.get("apiKey") or "").strip()
        models_raw = service.get("models")
        if not name:
            raise WebError("INVALID_PAYLOAD", "缺少服务名称（service.name）")
        if not base_url:
            raise WebError("INVALID_PAYLOAD", "缺少接入地址（service.baseUrl）")
        from .connections import connection_url
        base_url = connection_url(base_url, allow_query=True)
        if len(api_key) > 8192 or any(ord(c) < 32 for c in api_key):
            raise WebError("INVALID_SERVICE_KEY", "请填写有效的 API Key。")
        models = []
        if models_raw is not None:
            if not isinstance(models_raw, list):
                raise WebError("INVALID_PAYLOAD", "service.models 必须是模型名列表")
            if len(models_raw) > 5000 or any(
                not isinstance(item, str) or len(item.strip()) > 200
                or any(ord(c) < 32 for c in item) for item in models_raw
            ):
                raise WebError("INVALID_MODEL_LIST", "模型列表格式不正确，请每行填写一个完整的模型 ID。")
            models = list(dict.fromkeys(item.strip() for item in models_raw if item.strip()))
        warnings = []
        if not api_key:
            warnings.append("未提供 API Key；应用后该服务将处于“需要 Key”状态，直到补充 Key。")
        if not models:
            warnings.append("未提供模型列表；该服务在目录中将不会展示任何模型。")
        return name, base_url, api_key, models, warnings

    def configuration_preview(self, payload: dict) -> dict:
        self._require_configure()
        self._require_safe_state_root()
        root = self._require_config_root()
        if not isinstance(payload, dict) or not isinstance(payload.get("service"), dict):
            raise WebError("INVALID_PAYLOAD", "payload.service 缺失")
        service = payload["service"]
        protocol = str(service.get("protocol") or "dual")
        if protocol not in {"openai", "anthropic", "dual"}:
            raise WebError("INVALID_PROTOCOL", "请选择支持的服务类型。", 400)
        name, base_url, api_key, models, warnings = self._validate_service_payload(payload)

        bundle = self._load_bundle([])
        published = self._local_setup() and bool(bundle)
        cfg = self._published_config(self._raw_config(), bundle)
        providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
        providers_by_id = {
            str(item.get("id") or "").strip(): item
            for item in providers
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        service_id = str(service.get("id") or "").strip()
        mode = "update" if service_id and service_id in providers_by_id else "create"
        if mode == "create":
            provider_id = service_id or _slug_provider_id(name)
            base = provider_id
            suffix = 2
            while provider_id in providers_by_id:
                provider_id = f"{base}-{suffix}"
                suffix += 1
        else:
            provider_id = service_id

        credentials = self._credentials_values()

        def _current_credential(field: str) -> str:
            if published:
                for route in (bundle.get("payloads", {}).get("router", {}).get("routes", {})).values():
                    for leaf in [route.get("primary"), *route.get("fallbacks", [])]:
                        if leaf and leaf.get("provider_id") == provider_id:
                            return str(leaf.get(field.lower()) or "")
                return ""
            prefix = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).upper().strip("_") or "DEFAULT"
            return credentials.get(f"MMS_PROVIDER_{prefix}_{field}", "")

        changes: list[dict] = []
        if mode == "create":
            changes.append({"label": "Service", "before": "", "after": name})
            changes.append({"label": "Provider ID", "before": "", "after": provider_id})
            changes.append({"label": "Base URL", "before": "", "after": _mask_url(base_url)})
            changes.append({"label": "API Key", "before": "", "after": _mask_secret(api_key)})
            changes.append({"label": "Models", "before": "", "after": ", ".join(models)})
            changes.append(
                {
                    "label": "模型列表模式",
                    "before": "",
                    "after": "manual（由这份列表手工维护）",
                }
            )
        else:
            entry = providers_by_id[provider_id]
            if name and entry.get("name") != name:
                changes.append({"label": "Name", "before": str(entry.get("name") or ""), "after": name})
            if base_url and not published:
                current_url = _current_credential("BASE_URL")
                if current_url != base_url:
                    changes.append({"label": "Base URL", "before": _mask_url(current_url), "after": _mask_url(base_url)})
            if api_key:
                changes.append(
                    {
                        "label": "API Key",
                        "before": _mask_secret(_current_credential("API_KEY")),
                        "after": _mask_secret(api_key),
                    }
                )
            if models:
                if str(entry.get("models_endpoint") or "") == "manual":
                    current_models = ", ".join(str(m) for m in (entry.get("fallback_models") or []))
                    if current_models != ", ".join(models):
                        changes.append({"label": "Models", "before": current_models, "after": ", ".join(models)})
                else:
                    warnings.append(
                        "该服务使用远端模型列表（高级设置）；表单提供的模型列表不会覆盖这个设置，也不会写入模型清单。"
                    )
            # Advanced protocol-specific values are never touched by this form.
            for field, label in (
                ("OPENAI_BASE_URL", "OpenAI 专属地址"),
                ("ANTHROPIC_BASE_URL", "Anthropic 专属地址"),
                ("OPENAI_API_KEY", "OpenAI 专属 Key"),
            ):
                if _current_credential(field):
                    warnings.append(f"将保留已配置的{label}（高级设置，表单不会修改）。")
            if not changes:
                warnings.append("本次提交对该服务没有产生任何变更。")

        revision = self._config_revision()
        preview_id = secrets.token_hex(16)
        record = {
            "previewId": preview_id,
            "revision": revision,
            "requestedRevision": str(payload.get("revision") or ""),
            "mode": mode,
            "providerId": provider_id,
            "service": {"id": service_id or provider_id, "name": name, "baseUrl": base_url, "apiKey": api_key, "models": models, "protocol": protocol},
            "createdAt": time.time(),
            "expiresAt": time.time() + PREVIEW_TTL_SECONDS,
            "consumed": False,
        }
        self._cleanup_expired_previews()
        self._secure_write_json(self._previews_dir / f"{preview_id}.json", record)

        return {
            "revision": revision,
            "previewId": preview_id,
            "changes": changes,
            "warnings": warnings,
        }

    def configuration_apply(self, payload: dict) -> dict:
        self._require_configure()
        self._require_safe_state_root()
        root = self._require_config_root()
        if not isinstance(payload, dict):
            raise WebError("INVALID_PAYLOAD", "payload 必须是对象")
        preview_id = str(payload.get("previewId") or "").strip()
        if not preview_id or not re.fullmatch(r"[0-9a-f]{32}", preview_id):
            raise WebError("PREVIEW_NOT_FOUND", "previewId 缺失或格式非法", status=404)
        record_path = self._previews_dir / f"{preview_id}.json"
        if not record_path.exists():
            raise WebError("PREVIEW_NOT_FOUND", "预览不存在或已被清理，请重新生成预览", status=404)

        provided_revision = str(payload.get("revision") or "").strip()

        def _load_record() -> dict:
            if not record_path.exists():
                raise WebError("PREVIEW_NOT_FOUND", "预览不存在或已被清理，请重新生成预览", status=404)
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise WebError("PREVIEW_NOT_FOUND", "预览记录无法读取", status=404)
            if record.get("consumed"):
                raise WebError("PREVIEW_ALREADY_APPLIED", "该预览已被应用过，不能重复应用", status=409)
            if float(record.get("expiresAt") or 0) < time.time():
                # Expired: drop the record (and its stored key) immediately.
                try:
                    record_path.unlink()
                except OSError:
                    pass
                raise WebError("PREVIEW_EXPIRED", "预览已过期（并已清除保存的 Key），请重新生成预览", status=409)
            if provided_revision and provided_revision != record.get("revision"):
                raise WebError(
                    "CONFIG_STALE",
                    "配置在预览生成后已发生变化，请刷新后重新预览",
                    status=409,
                )
            return record

        _load_record()

        self._state_root.mkdir(parents=True, exist_ok=True)
        lock_path = self._state_root / "apply.lock"
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                # Re-read and re-validate the preview inside the apply lock.
                record = _load_record()
                current_revision = self._config_revision()
                if current_revision != record.get("revision"):
                    raise WebError(
                        "CONFIG_STALE",
                        "配置在预览生成后已发生变化，请刷新后重新预览",
                        status=409,
                    )
                try:
                    result = self._run_worker(
                        {
                            "command": "apply-config",
                            "config_root": str(root),
                            "mode": record.get("mode"),
                            "providerId": record.get("providerId"),
                            "service": record.get("service"),
                            "expectedRevision": record.get("revision"),
                            "standalone": self._local_setup(),
                        }
                    )
                except WebError as exc:
                    if exc.code == "CONFIG_STALE":
                        raise WebError(
                            "CONFIG_STALE",
                            "配置在应用时被其他进程修改，已中止；请刷新后重新预览",
                            status=409,
                        )
                    raise
                # Clear the stored key once applied; keep only audit fields.
                consumed_record = dict(record)
                consumed_record["service"] = {
                    **record.get("service", {}),
                    "apiKey": "",
                }
                consumed_record["consumed"] = True
                consumed_record["appliedAt"] = _utc_now_iso()
                consumed_record["resultRevision"] = self._config_revision()
                self._secure_write_json(record_path, consumed_record)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        provider_id = record.get("providerId")
        try:
            presets = [p["id"] for p in self.snapshot()["presets"]
                       if p.get("providerId") == provider_id and p.get("available")]
        except WebError:
            # The write is already committed. A failed catalog read must not
            # invite a second save or claim that no configuration was written.
            presets = []
        return {"applied": True, "message": "配置已应用", "providerId": provider_id,
                "presetIds": presets}

    def configuration_discard(self, payload: dict) -> dict:
        """Drop an abandoned preview, including its temporary key, under the apply lock."""
        self._require_configure()
        self._require_safe_state_root()
        preview_id = str(payload.get("previewId") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", preview_id):
            raise WebError("PREVIEW_NOT_FOUND", "预览标识无效。", status=404)
        self._state_root.mkdir(parents=True, exist_ok=True)
        with open(self._state_root / "apply.lock", "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                path = self._previews_dir / f"{preview_id}.json"
                if path.exists():
                    record = json.loads(path.read_text(encoding="utf-8"))
                    # Applied records contain audit metadata, not credentials.
                    if not record.get("consumed"):
                        path.unlink()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return {"discarded": True}

    # ── launch resolution (INTERNAL ONLY) ─────────────────────────────────

    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        """Resolve the exact MMS runtime for a preset + workspace.

        INTERNAL ONLY: the returned dict contains secrets (export env, runtime
        api_key). It must never be serialized to an HTTP response; the server
        owner passes it straight into the session launcher.
        """
        capabilities = self.capabilities()
        if not capabilities.get("catalogRead"):
            raise WebError("CAPABILITY_UNAVAILABLE", "catalog is unavailable", status=409)
        root = self._require_config_root()

        cfg = self._raw_config()
        presets = cfg.get("presets") if isinstance(cfg.get("presets"), dict) else {}
        preset = presets.get(str(preset_id)) if isinstance(presets, dict) else None
        if str(preset_id).startswith("web:pi:"):
            model_id = str(preset_id).removeprefix("web:pi:")
            item = next((m for m in self.snapshot()["models"] if m["id"] == model_id), None)
            if not item or not item["available"] or "pi" not in item["harnesses"]:
                raise WebError("MODEL_UNAVAILABLE", "所选模型当前不可用。", 409)
            preset = {"cli": "pi", "provider": item["providerId"],
                      "model": model_id.removeprefix(item["providerId"] + ":")}
        if not isinstance(preset, dict):
            raise WebError("PRESET_NOT_FOUND", f"预设不存在：{preset_id}", status=404)
        cli = str(preset.get("cli") or "claude").strip()
        account_id = str(preset.get("account") or "").strip()
        if account_id:
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                f"预设 {preset_id} 绑定官方账号通道（{account_id}），Web 首版不支持启动官方账号会话",
                status=409,
            )
        if cli not in _PROVIDER_LAUNCHABLE_HARNESSES:
            raise WebError(
                "CAPABILITY_UNAVAILABLE",
                f"harness “{cli}”需要官方账号，暂不支持从 Web 启动",
                status=409,
            )
        visible_preset = next((p for p in self.snapshot()["presets"] if p["id"] == str(preset_id)), None)
        if visible_preset is not None and not visible_preset.get("available"):
            raise WebError("CAPABILITY_UNAVAILABLE", str(visible_preset.get("reason") or "该模型组合不可用。"), 409)
        provider_ref = str(preset.get("provider") or "").strip()
        default_provider_id = str((cfg.get("provider") or {}).get("default") or "").strip()
        provider_id = provider_ref if provider_ref and provider_ref != "default" else default_provider_id
        model = str(
            preset.get("model")
            or preset.get("sonnet")
            or preset.get("opus")
            or preset.get("haiku")
            or preset.get("subagent")
            or ""
        ).strip()

        workspace = next((item for item in self._workspaces() if item["id"] == workspace_id), None)
        if workspace is None:
            raise WebError("WORKSPACE_NOT_FOUND", f"工作区不存在：{workspace_id}", status=404)
        cwd = workspace.get("path") or str(root)
        if not Path(cwd).is_dir():
            raise WebError("WORKSPACE_MISSING", "工作文件夹不存在，请重新选择。", 409)

        result = self._run_worker(
            {
                "command": "resolve-launch",
                "config_root": str(root),
                "cli": cli,
                "providerId": provider_id or None,
                "model": model,
            }
        )
        resolved_provider_id = result.get("providerId") or provider_id
        return {
            "launchOptions": result.get("launchOptions", {}),
            "piModel": result.get("piModel", {}),
            "harness": result.get("harness"),
            "modelInfo": result.get("modelInfo") or {},
            "runtime": result.get("runtime") or {},
            "exportEnv": result.get("exportEnv") or {},
            "providerId": resolved_provider_id,
            "channel": resolved_provider_id,
            "channelKind": "provider",
            "providerModelId": f"{resolved_provider_id}:{model}" if model else "",
            "cwd": cwd,
            "presetId": str(preset_id),
        }

    def add_workspace(self, payload: dict) -> dict:
        self._require_safe_state_root()
        raw = str(payload.get("path") or "").strip()
        if not raw:
            raise WebError("INVALID_WORKSPACE", "请选择一个工作文件夹。", 400)
        folder = Path(raw).expanduser().resolve()
        if not folder.is_dir():
            raise WebError("INVALID_WORKSPACE", "这个文件夹不存在。", 400)
        from .runtime import private_json
        workspace = {"id": "w-" + hashlib.sha256(str(folder).encode()).hexdigest()[:16],
                     "name": folder.name or str(folder), "path": str(folder)}
        registry = self._state_root / "workspaces.json"
        self._state_root.mkdir(parents=True, exist_ok=True)
        with open(self._state_root / "workspaces.lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            items = self._workspaces()
            items = [w for w in items if w["id"] not in ("default", workspace["id"])]
            private_json(registry, [*items, workspace])
        return workspace
