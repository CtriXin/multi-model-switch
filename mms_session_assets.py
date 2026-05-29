"""Shared session-home asset helpers for MMS launchers."""

from __future__ import annotations

import os


def resolve_local_hooks_dir(module_file):
    module_dir = os.path.dirname(os.path.abspath(module_file))
    parts = module_dir.split(os.sep)
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        canonical_root = os.sep.join(parts[:idx]) or os.sep
        canonical_hooks = os.path.join(canonical_root, "hooks")
        required_hooks = (
            "nsr-codex-hook.sh",
            "xmem-session-start-hook.sh",
            "xmem-session-end-hook.sh",
            "xmem-gateway-hook.sh",
        )
        if all(os.path.isfile(os.path.join(canonical_hooks, name)) for name in required_hooks):
            return canonical_hooks
    return os.path.join(module_dir, "hooks")


def link_shared_dotfiles(session_home):
    """Expose user-level Git/SSH config inside isolated HOME sessions."""
    import mms_launchers as _launchers

    real_home = _launchers._real_user_home()
    for dot_name in (".ssh", ".gitconfig", ".gitignore_global"):
        src = os.path.join(real_home, dot_name)
        dst = os.path.join(session_home, dot_name)
        if os.path.exists(src) and not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)
