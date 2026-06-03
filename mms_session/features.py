"""Session feature mode and asset root helpers."""

from __future__ import annotations

import os


def _module_dir(module_file):
    return os.path.dirname(os.path.abspath(module_file))


def _dedupe_existing(candidates, predicate):
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if predicate(candidate):
            return candidate
    return ""


def asset_root_preference(asset_name, *, preference_asset_root_fn):
    try:
        return str(preference_asset_root_fn(asset_name) or "").strip()
    except Exception:
        return ""


def expand_candidate(value):
    return os.path.abspath(os.path.expanduser(str(value or "").strip()))


def _asset_root_candidates_from_root(root, surface, *names):
    root = str(root or "").strip()
    if not root:
        return []
    root = expand_candidate(root)
    surface = str(surface or "").strip()
    candidates = []
    for name in names:
        raw = str(name or "").strip()
        if not raw:
            continue
        variants = [raw]
        for alt in (raw.replace("_", "-"), raw.replace("-", "_")):
            if alt not in variants:
                variants.append(alt)
        for variant in variants:
            if surface:
                candidates.append(os.path.join(root, surface, variant))
            candidates.append(os.path.join(root, "packages", variant))
    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _managed_asset_root_candidates(surface, *names, managed_assets_enabled_fn=None, managed_assets_root_fn=None):
    if not callable(managed_assets_enabled_fn) or not callable(managed_assets_root_fn):
        return []
    try:
        if not managed_assets_enabled_fn():
            return []
        root = str(managed_assets_root_fn() or "").strip()
    except Exception:
        return []
    return _asset_root_candidates_from_root(root, surface, *names)


def _bundled_assets_root(module_file):
    root = os.path.join(_module_dir(module_file), "assets", "session-assets")
    return root if os.path.isdir(root) else ""


def _bundled_asset_root_candidates(module_file, surface, *names):
    return _asset_root_candidates_from_root(_bundled_assets_root(module_file), surface, *names)


def _asset_callback_kwargs(values):
    return {
        "managed_assets_enabled_fn": values.get("managed_assets_enabled_fn"),
        "managed_assets_root_fn": values.get("managed_assets_root_fn"),
    }


def resolve_nsr_root(
    *,
    module_file,
    real_user_path_fn,
    asset_root_preference_fn,
    managed_assets_enabled_fn=None,
    managed_assets_root_fn=None,
    environ=os.environ,
):
    candidates = []
    for key in ("MMS_NSR_ROOT", "NSR_ROOT"):
        explicit = str(environ.get(key) or "").strip()
        if explicit:
            candidates.append(expand_candidate(explicit))
    pref = asset_root_preference_fn("nsr")
    if pref:
        candidates.append(expand_candidate(pref))
    nsr_home = str(environ.get("NSR_HOME") or "").strip()
    if nsr_home:
        candidates.append(expand_candidate(nsr_home))
    candidates.extend(_managed_asset_root_candidates("packs", "nsr", "non-stop-run", **_asset_callback_kwargs(locals())))
    candidates.extend(_bundled_asset_root_candidates(module_file, "packs", "nsr", "non-stop-run"))
    candidates.extend([
        os.path.join(_module_dir(module_file), "vendor", "non-stop-run"),
        real_user_path_fn("auto-skills", "shared-skills", "nsr"),
        real_user_path_fn("auto-skills", "Non-Stop-Run"),
        real_user_path_fn("auto-skills", "shared-skills", "looop.deprecated"),
    ])

    def _has_nsr_hooks(candidate):
        return (
            os.path.isfile(os.path.join(candidate, "scripts", "codex_hook.py"))
            and os.path.isfile(os.path.join(candidate, "scripts", "claude_hook.py"))
        )

    return _dedupe_existing(candidates, _has_nsr_hooks)


def normalize_nsr_mode(value, default="enable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"enable", "disable"} else "enable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"enable", "disable"} else "enable"


def runtime_nsr_enabled(runtime, *, normalize_nsr_mode_fn=normalize_nsr_mode):
    return normalize_nsr_mode_fn((runtime or {}).get("nsr_mode", "enable")) == "enable"


def normalize_caveman_level(value, default="light"):
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in {"", "inherit", "default", "auto", "enable", "enabled", "on", "true", "1"}:
        return default if default in {"", "light", "standard", "full"} else "light"
    if raw in {"light", "lite", "low"}:
        return "light"
    if raw in {"standard", "normal", "medium"}:
        return "standard"
    if raw in {"full", "ultra", "high"}:
        return "full"
    return default if default in {"", "light", "standard", "full"} else "light"


def normalize_caveman_mode(value, default="disable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "disable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    if normalize_caveman_level(raw, default=""):
        return "enable"
    return default if default in {"auto", "enable", "disable"} else "disable"


def runtime_caveman_enabled(runtime, *, normalize_caveman_mode_fn=normalize_caveman_mode):
    return normalize_caveman_mode_fn((runtime or {}).get("caveman_mode", "disable")) == "enable"


def runtime_caveman_level(runtime, *, normalize_caveman_level_fn=normalize_caveman_level):
    runtime = runtime or {}
    level = runtime.get("caveman_level")
    if level is None:
        level = runtime.get("caveman_mode")
    return normalize_caveman_level_fn(level, default="light")


def normalize_thinking_mode(value, default="enable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "enable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "enable"


def runtime_thinking_enabled(runtime, *, normalize_thinking_mode_fn=normalize_thinking_mode):
    return normalize_thinking_mode_fn((runtime or {}).get("thinking_mode", "enable")) == "enable"


def normalize_reasoning_effort(value, default="high"):
    raw = str(value or "").strip().lower()
    if raw in {"low", "medium", "high", "xhigh"}:
        return raw
    return default if default in {"low", "medium", "high", "xhigh"} else "high"


def runtime_reasoning_effort(runtime, default="high", *, normalize_reasoning_effort_fn=normalize_reasoning_effort):
    return normalize_reasoning_effort_fn((runtime or {}).get("reasoning_effort", default), default=default)


def runtime_vision_sidecar(runtime):
    sidecar = (runtime or {}).get("vision_sidecar")
    if not isinstance(sidecar, dict):
        return {}
    if not sidecar.get("enabled", True):
        return {}
    return dict(sidecar)


def is_installed_mms_layout(*, module_path, real_user_path_fn):
    current_path = os.path.abspath(module_path)
    installed_root = os.path.abspath(real_user_path_fn(".mms"))
    try:
        return os.path.commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def default_gpt_reasoning_effort(*, module_path, is_installed_mms_layout_fn):
    return "high" if is_installed_mms_layout_fn(module_path=module_path) else "xhigh"


def resolve_caveman_root(
    *,
    module_file,
    real_user_path_fn,
    asset_root_preference_fn,
    managed_assets_enabled_fn=None,
    managed_assets_root_fn=None,
    environ=os.environ,
):
    candidates = []
    explicit = str(environ.get("MMS_CAVEMAN_ROOT") or "").strip()
    if explicit:
        candidates.append(expand_candidate(explicit))
    pref = asset_root_preference_fn("caveman")
    if pref:
        candidates.append(expand_candidate(pref))
    candidates.extend(_managed_asset_root_candidates("packs", "caveman", **_asset_callback_kwargs(locals())))
    candidates.extend(_bundled_asset_root_candidates(module_file, "packs", "caveman"))
    candidates.extend([
        os.path.join(_module_dir(module_file), "vendor", "caveman"),
        real_user_path_fn("auto-skills", "vendor", "caveman"),
        real_user_path_fn("vendor", "caveman"),
        real_user_path_fn("caveman"),
    ])

    def _has_caveman(candidate):
        return (
            os.path.isfile(os.path.join(candidate, "hooks", "caveman-activate.js"))
            and os.path.isfile(os.path.join(candidate, "hooks", "caveman-mode-tracker.js"))
        )

    return _dedupe_existing(candidates, _has_caveman)


def normalize_ecc_mode(value, default="disable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "disable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "disable"


def normalize_agent_pack(value, default="none"):
    raw = str(value or "").strip().lower()
    fallback = default if default in {"none", "ecc", "omc"} else "none"
    if raw in {"", "inherit", "default", "auto"}:
        return fallback
    if raw in {"0", "false", "no", "off", "disable", "disabled", "none", "null"}:
        return "none"
    if raw in {"ecc", "everything-claude-code", "everything_claude_code"}:
        return "ecc"
    if raw in {"omc", "oh-my-claudecode", "oh_my_claudecode", "oh-my-claude-code"}:
        return "omc"
    return fallback


def runtime_agent_pack(runtime, *, normalize_agent_pack_fn=normalize_agent_pack, normalize_ecc_mode_fn=normalize_ecc_mode):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "agent_pack" in runtime and str(runtime.get("agent_pack") or "").strip():
        return normalize_agent_pack_fn(runtime.get("agent_pack"), default="none")
    if normalize_ecc_mode_fn(runtime.get("ecc_mode", "disable")) == "enable":
        return "ecc"
    if normalize_ecc_mode_fn(runtime.get("omc_mode", "disable")) == "enable":
        return "omc"
    return "none"


def runtime_ecc_enabled(runtime, *, runtime_agent_pack_fn=runtime_agent_pack):
    return runtime_agent_pack_fn(runtime) == "ecc"


def runtime_omc_enabled(runtime, *, runtime_agent_pack_fn=runtime_agent_pack):
    return runtime_agent_pack_fn(runtime) == "omc"


def resolve_ecc_root(
    *,
    module_file,
    real_user_path_fn,
    asset_root_preference_fn,
    managed_assets_enabled_fn=None,
    managed_assets_root_fn=None,
    environ=os.environ,
):
    candidates = []
    explicit = str(environ.get("MMS_ECC_ROOT") or "").strip()
    if explicit:
        candidates.append(expand_candidate(explicit))
    pref = asset_root_preference_fn("ecc")
    if pref:
        candidates.append(expand_candidate(pref))
    candidates.extend(_managed_asset_root_candidates("packs", "ecc", "everything-claude-code", **_asset_callback_kwargs(locals())))
    candidates.extend(_bundled_asset_root_candidates(module_file, "packs", "ecc", "everything-claude-code"))
    candidates.extend([
        os.path.join(_module_dir(module_file), "agent-packs", "everything-claude-code"),
        os.path.join(_module_dir(module_file), "vendor", "everything-claude-code"),
        real_user_path_fn("auto-skills", "vendor", "everything-claude-code"),
        real_user_path_fn("vendor", "everything-claude-code"),
        real_user_path_fn("everything-claude-code"),
    ])

    def _has_ecc(candidate):
        return (
            os.path.isfile(os.path.join(candidate, "hooks", "hooks.json"))
            and os.path.isdir(os.path.join(candidate, "commands"))
            and os.path.isdir(os.path.join(candidate, "skills"))
        )

    return _dedupe_existing(candidates, _has_ecc)


def resolve_omc_root(
    *,
    module_file,
    real_user_path_fn,
    asset_root_preference_fn,
    managed_assets_enabled_fn=None,
    managed_assets_root_fn=None,
    environ=os.environ,
):
    candidates = []
    explicit = str(environ.get("MMS_OMC_ROOT") or "").strip()
    if explicit:
        candidates.append(expand_candidate(explicit))
    pref = asset_root_preference_fn("omc")
    if pref:
        candidates.append(expand_candidate(pref))
    candidates.extend(_managed_asset_root_candidates("packs", "omc", "oh-my-claudecode", **_asset_callback_kwargs(locals())))
    candidates.extend(_bundled_asset_root_candidates(module_file, "packs", "omc", "oh-my-claudecode"))
    candidates.extend([
        os.path.join(_module_dir(module_file), "agent-packs", "oh-my-claudecode"),
        os.path.join(_module_dir(module_file), "vendor", "oh-my-claudecode"),
        real_user_path_fn("auto-skills", "installed-skills", "oh-my-claudecode"),
        real_user_path_fn("auto-skills", "vendor", "oh-my-claudecode"),
        real_user_path_fn("vendor", "oh-my-claudecode"),
        real_user_path_fn("oh-my-claudecode"),
    ])

    def _has_omc(candidate):
        return (
            os.path.isfile(os.path.join(candidate, "hooks", "hooks.json"))
            and os.path.isdir(os.path.join(candidate, "skills"))
            and os.path.isfile(os.path.join(candidate, ".claude-plugin", "plugin.json"))
        )

    return _dedupe_existing(candidates, _has_omc)


def resolve_skill_root(
    *,
    env_key,
    preference_key,
    default_parts,
    real_user_path_fn,
    asset_root_preference_fn,
    module_file,
    managed_assets_enabled_fn=None,
    managed_assets_root_fn=None,
    environ=os.environ,
):
    candidates = []
    explicit = str(environ.get(env_key) or "").strip()
    if explicit:
        candidates.append(expand_candidate(explicit))
    pref = asset_root_preference_fn(preference_key)
    if pref:
        candidates.append(expand_candidate(pref))
    module_dir = _module_dir(module_file)
    candidates.extend(
        _managed_asset_root_candidates(
            "skills",
            preference_key,
            preference_key.replace("_", "-"),
            **_asset_callback_kwargs(locals()),
        )
    )
    candidates.extend(_bundled_asset_root_candidates(module_file, "skills", preference_key, preference_key.replace("_", "-")))
    for origin, parts in default_parts:
        if origin == "module":
            candidates.append(os.path.join(module_dir, *parts))
        elif origin == "real_home":
            candidates.append(real_user_path_fn(*parts))

    return _dedupe_existing(candidates, lambda candidate: os.path.isfile(os.path.join(candidate, "SKILL.md")))


def resolve_web_access_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_WEB_ACCESS_ROOT",
        preference_key="web_access",
        default_parts=(
            ("module", ("vendor", "web-access")),
            ("real_home", ("auto-skills", "vendor", "web-access")),
            ("real_home", ("vendor", "web-access")),
        ),
        **kwargs,
    )


def resolve_weber_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_WEBER_ROOT",
        preference_key="weber",
        default_parts=(
            ("module", ("vendor", "weber")),
            ("real_home", ("auto-skills", "shared-skills", "weber")),
            ("real_home", ("auto-skills", "vendor", "weber")),
            ("real_home", ("vendor", "weber")),
        ),
        **kwargs,
    )


def resolve_agent_browser_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_AGENT_BROWSER_ROOT",
        preference_key="agent_browser",
        default_parts=(
            ("module", ("vendor", "agent-browser")),
            ("real_home", ("auto-skills", "installed-skills", "agent-browser")),
            ("real_home", ("auto-skills", "vendor", "agent-browser")),
            ("real_home", ("vendor", "agent-browser")),
        ),
        **kwargs,
    )


def resolve_codegraph_root(**kwargs):
    environ = kwargs.get("environ", os.environ)
    candidates = []
    explicit = str(environ.get("MMS_CODEGRAPH_ROOT") or environ.get("MMS_CODEGRAPH_SKILL_ROOT") or "").strip()
    if explicit:
        candidates.append(expand_candidate(explicit))
    pref = kwargs["asset_root_preference_fn"]("codegraph")
    if pref:
        candidates.append(expand_candidate(pref))
    module_dir = _module_dir(kwargs["module_file"])
    real_user_path_fn = kwargs["real_user_path_fn"]
    candidates.extend(
        _managed_asset_root_candidates(
            "skills",
            "codegraph",
            managed_assets_enabled_fn=kwargs.get("managed_assets_enabled_fn"),
            managed_assets_root_fn=kwargs.get("managed_assets_root_fn"),
        )
    )
    candidates.extend(_bundled_asset_root_candidates(kwargs["module_file"], "skills", "codegraph"))
    candidates.extend(
        [
            os.path.join(module_dir, "vendor", "codegraph"),
            real_user_path_fn("auto-skills", "shared-skills", "codegraph"),
            real_user_path_fn("auto-skills", "vendor", "codegraph"),
            real_user_path_fn("vendor", "codegraph"),
        ]
    )
    return _dedupe_existing(candidates, lambda candidate: os.path.isfile(os.path.join(candidate, "SKILL.md")))


def resolve_toon_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_TOON_ROOT",
        preference_key="toon",
        default_parts=(
            ("module", ("vendor", "toon")),
            ("real_home", ("auto-skills", "vendor", "toon")),
            ("real_home", ("vendor", "toon")),
        ),
        **kwargs,
    )


def resolve_token_saver_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_TOKEN_SAVER_ROOT",
        preference_key="token_saver",
        default_parts=(
            ("module", ("vendor", "token-saver")),
            ("real_home", ("auto-skills", "shared-skills", "token-saver")),
            ("real_home", ("auto-skills", "vendor", "token-saver")),
            ("real_home", ("vendor", "token-saver")),
        ),
        **kwargs,
    )


def resolve_xmem_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_XMEM_ROOT",
        preference_key="xmem",
        default_parts=(
            ("module", ("vendor", "xmem")),
            ("real_home", ("auto-skills", "shared-skills", "xmem")),
            ("real_home", ("auto-skills", "CtriXin-repo", "xmem", "skills", "xmem")),
            ("real_home", (".codex", "skills", "xmem")),
            ("real_home", (".agents", "skills", "xmem")),
        ),
        **kwargs,
    )


def resolve_auto_github_contributor_root(**kwargs):
    return resolve_skill_root(
        env_key="MMS_AUTO_GITHUB_CONTRIBUTOR_ROOT",
        preference_key="auto_github_contributor",
        default_parts=(
            ("real_home", ("auto-skills", "installed-skills", "auto-github-contributor")),
            ("real_home", ("auto-skills", "vendor", "auto-github-contributor", "skills", "auto-github-contributor")),
            ("real_home", ("vendor", "auto-github-contributor", "skills", "auto-github-contributor")),
        ),
        **kwargs,
    )
