"""Session overlay helpers for MMS-managed CLI homes."""

from __future__ import annotations

import os
import shutil


def _launchers():
    import mms_launchers as _module

    return _module


def _normalize_session_surface_disabled(disabled_session_surfaces):
    return _launchers()._normalize_session_surface_disabled(disabled_session_surfaces)


def _session_skill_disabled(disabled_session_surfaces, skill_name):
    return _launchers()._session_skill_disabled(disabled_session_surfaces, skill_name)


def _resolve_caveman_root():
    return _launchers()._resolve_caveman_root()


def _resolve_ecc_root():
    return _launchers()._resolve_ecc_root()


def _resolve_omc_root():
    return _launchers()._resolve_omc_root()


def _resolve_web_access_root():
    return _launchers()._resolve_web_access_root()


def _resolve_weber_root():
    return _launchers()._resolve_weber_root()


def _resolve_agent_browser_root():
    return _launchers()._resolve_agent_browser_root()


def _resolve_toon_root():
    return _launchers()._resolve_toon_root()


def _resolve_xmem_root():
    return _launchers()._resolve_xmem_root()


def _resolve_token_saver_root():
    return _launchers()._resolve_token_saver_root()


def _resolve_auto_github_contributor_root():
    return _launchers()._resolve_auto_github_contributor_root()


def _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, extra_source_root, *, exclude_names=None):
    extra_source_root = str(extra_source_root or "").strip()
    if not extra_source_root:
        return False
    extra_dir = os.path.join(extra_source_root, entry_name)
    if not os.path.isdir(extra_dir):
        return False
    exclude_names = set(str(item or "").strip() for item in (exclude_names or []) if str(item or "").strip())

    dst = os.path.join(parent_dir, entry_name)
    merged_dir = os.path.join(overlay_root, entry_name)
    os.makedirs(merged_dir, exist_ok=True)

    def _merge_dir(src_dir):
        src_dir = str(src_dir or "").strip()
        if not src_dir or not os.path.isdir(src_dir):
            return
        try:
            if os.path.samefile(src_dir, merged_dir):
                return
        except Exception:
            pass
        for item in os.listdir(src_dir):
            if item in exclude_names:
                continue
            src = os.path.join(src_dir, item)
            link = os.path.join(merged_dir, item)
            if os.path.exists(link) or os.path.islink(link):
                continue
            os.symlink(src, link)

    if os.path.exists(dst) or os.path.islink(dst):
        _merge_dir(os.path.realpath(dst))
    _merge_dir(extra_dir)
    if not os.listdir(merged_dir):
        return False
    if os.path.islink(dst):
        os.unlink(dst)
    elif os.path.isdir(dst):
        shutil.rmtree(dst)
    elif os.path.exists(dst):
        os.unlink(dst)
    os.symlink(merged_dir, dst)
    return True


def _overlay_session_skill_dir(parent_dir, overlay_root, skill_name, skill_root, *, disabled_session_surfaces=None):
    skill_name = str(skill_name or "").strip()
    skill_root = str(skill_root or "").strip()
    if not skill_name or not skill_root:
        return False

    os.makedirs(parent_dir, exist_ok=True)
    skills_dir = os.path.join(parent_dir, "skills")
    merged_dir = os.path.join(overlay_root, "skills")
    os.makedirs(merged_dir, exist_ok=True)

    def _merge_dir(src_dir, *, exclude_names=None):
        src_dir = str(src_dir or "").strip()
        if not src_dir or not os.path.isdir(src_dir):
            return
        exclude_names = set(str(item or "").strip() for item in (exclude_names or []) if str(item or "").strip())
        try:
            if os.path.samefile(src_dir, merged_dir):
                return
        except Exception:
            pass
        for item in os.listdir(src_dir):
            if item in exclude_names:
                continue
            src = os.path.join(src_dir, item)
            link = os.path.join(merged_dir, item)
            if os.path.exists(link) or os.path.islink(link):
                continue
            os.symlink(src, link)

    disabled = _session_skill_disabled(disabled_session_surfaces, skill_name)
    if os.path.exists(skills_dir) or os.path.islink(skills_dir):
        _merge_dir(os.path.realpath(skills_dir), exclude_names={skill_name} if disabled else None)

    if disabled:
        if os.path.islink(skills_dir):
            os.unlink(skills_dir)
        elif os.path.isdir(skills_dir):
            shutil.rmtree(skills_dir)
        elif os.path.exists(skills_dir):
            os.unlink(skills_dir)
        if os.listdir(merged_dir):
            os.symlink(merged_dir, skills_dir)
        return False

    if not os.path.isfile(os.path.join(skill_root, "SKILL.md")):
        return False

    skill_link = os.path.join(merged_dir, skill_name)
    if not os.path.exists(skill_link) and not os.path.islink(skill_link):
        os.symlink(skill_root, skill_link)

    if not os.listdir(merged_dir):
        return False
    if os.path.islink(skills_dir):
        os.unlink(skills_dir)
    elif os.path.isdir(skills_dir):
        shutil.rmtree(skills_dir)
    elif os.path.exists(skills_dir):
        os.unlink(skills_dir)
    os.symlink(merged_dir, skills_dir)
    return True


def _overlay_caveman_session_entries(parent_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None):
    if not enable_caveman:
        return
    if _session_skill_disabled(disabled_session_surfaces, "caveman"):
        return
    caveman_root = _resolve_caveman_root()
    if not caveman_root:
        return
    overlay_root = os.path.join(session_home, ".mms-caveman-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    disabled_names = _normalize_session_surface_disabled(disabled_session_surfaces).get("skills", set())
    for entry_name in ("commands", "skills"):
        _overlay_session_entry_dir(
            parent_dir,
            overlay_root,
            entry_name,
            caveman_root,
            exclude_names=disabled_names,
        )


def _overlay_ecc_session_entries(parent_dir, session_home, *, enable_ecc=False, disabled_session_surfaces=None):
    if not enable_ecc:
        return
    if _session_skill_disabled(disabled_session_surfaces, "ecc") or _session_skill_disabled(disabled_session_surfaces, "__bundle__:ecc"):
        return
    ecc_root = _resolve_ecc_root()
    if not ecc_root:
        return
    overlay_root = os.path.join(session_home, ".mms-ecc-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    disabled_names = _normalize_session_surface_disabled(disabled_session_surfaces).get("skills", set())
    for source_root, entry_name in (
        (os.path.join(ecc_root, ".claude"), "commands"),
        (ecc_root, "commands"),
        (os.path.join(ecc_root, ".claude"), "skills"),
        (os.path.join(ecc_root, ".agents"), "skills"),
        (ecc_root, "skills"),
        (os.path.join(ecc_root, ".claude"), "rules"),
        (ecc_root, "rules"),
    ):
        _overlay_session_entry_dir(
            parent_dir,
            overlay_root,
            entry_name,
            source_root,
            exclude_names=disabled_names,
        )


def _overlay_omc_session_entries(parent_dir, session_home, *, enable_omc=False, disabled_session_surfaces=None):
    if not enable_omc:
        return
    if _session_skill_disabled(disabled_session_surfaces, "omc") or _session_skill_disabled(disabled_session_surfaces, "__bundle__:omc"):
        return
    omc_root = _resolve_omc_root()
    if not omc_root:
        return
    overlay_root = os.path.join(session_home, ".mms-omc-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    disabled_names = _normalize_session_surface_disabled(disabled_session_surfaces).get("skills", set())
    for entry_name in ("agents", "skills", "commands"):
        _overlay_session_entry_dir(
            parent_dir,
            overlay_root,
            entry_name,
            omc_root,
            exclude_names=disabled_names,
        )


def _overlay_web_access_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    web_access_root = _resolve_web_access_root()
    if not web_access_root:
        return
    overlay_root = os.path.join(session_home, ".mms-web-access-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "web-access", web_access_root, disabled_session_surfaces=disabled_session_surfaces)


def _overlay_weber_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    weber_root = _resolve_weber_root()
    if not weber_root:
        return
    overlay_root = os.path.join(session_home, ".mms-weber-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "weber", weber_root, disabled_session_surfaces=disabled_session_surfaces)


def _overlay_agent_browser_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    agent_browser_root = _resolve_agent_browser_root()
    if not agent_browser_root:
        return
    overlay_root = os.path.join(session_home, ".mms-agent-browser-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "agent-browser", agent_browser_root, disabled_session_surfaces=disabled_session_surfaces)


def _overlay_toon_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    toon_root = _resolve_toon_root()
    if not toon_root:
        return
    overlay_root = os.path.join(session_home, ".mms-toon-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "toon", toon_root, disabled_session_surfaces=disabled_session_surfaces)


def _overlay_xmem_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    xmem_root = _resolve_xmem_root()
    if not xmem_root:
        return
    overlay_root = os.path.join(session_home, ".mms-xmem-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "xmem", xmem_root, disabled_session_surfaces=disabled_session_surfaces)


def _overlay_token_saver_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    token_saver_root = _resolve_token_saver_root()
    if not token_saver_root:
        return
    overlay_root = os.path.join(session_home, ".mms-token-saver-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    if _session_skill_disabled(disabled_session_surfaces, "token-saver"):
        _overlay_session_skill_dir(
            parent_dir,
            overlay_root,
            "token-saver",
            token_saver_root,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _overlay_session_entry_dir(
            parent_dir,
            overlay_root,
            "commands",
            token_saver_root,
            exclude_names={"token-saver", "token-saver.toml"},
        )
        return
    _overlay_session_skill_dir(parent_dir, overlay_root, "token-saver", token_saver_root, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_session_entry_dir(parent_dir, overlay_root, "commands", token_saver_root)


def _overlay_auto_github_contributor_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    auto_gh_root = _resolve_auto_github_contributor_root()
    if not auto_gh_root:
        return
    overlay_root = os.path.join(session_home, ".mms-auto-github-contributor-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "auto-github-contributor", auto_gh_root, disabled_session_surfaces=disabled_session_surfaces)
    vendor_root = os.path.normpath(os.path.join(os.path.realpath(auto_gh_root), "..", ".."))
    if _session_skill_disabled(disabled_session_surfaces, "auto-github-contributor"):
        if os.path.isdir(os.path.join(vendor_root, "commands")):
            _overlay_session_entry_dir(
                parent_dir,
                overlay_root,
                "commands",
                vendor_root,
                exclude_names={"auto-contribute.md"},
            )
        return
    if os.path.isdir(os.path.join(vendor_root, "commands")):
        _overlay_session_entry_dir(parent_dir, overlay_root, "commands", vendor_root)
