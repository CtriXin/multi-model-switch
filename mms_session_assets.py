"""Shared session-home asset helpers for MMS launchers."""

from __future__ import annotations

import os


def link_shared_dotfiles(session_home):
    """Expose user-level Git/SSH config inside isolated HOME sessions."""
    import mms_launchers as _launchers

    real_home = _launchers._real_user_home()
    for dot_name in (".ssh", ".gitconfig", ".gitignore_global"):
        src = os.path.join(real_home, dot_name)
        dst = os.path.join(session_home, dot_name)
        if os.path.exists(src) and not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)
