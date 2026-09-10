"""Persist the active managed release while leaving installed/git sources intact."""
from __future__ import annotations
import fcntl
import os
import sys
from pathlib import Path
from mms_version import VERSION
from .runtime import require_private_root
from .updates import read_json, version_tuple
from .update_stage import candidate_environment, validate_bundle


def active_source(state, source):
    marker = read_json(state/'updates/active.json')
    target_version = version_tuple(marker.get('version'))
    if not target_version or target_version <= version_tuple(VERSION):
        return None
    target = Path(str(marker.get('source') or '')).resolve()
    if target == source.resolve() or not target.is_relative_to((state/'updates/versions').resolve()):
        return None
    try:
        validate_bundle(target, marker['version'])
    except (OSError, ValueError, TypeError):
        return None  # Fall back to the intact installed source.
    return target


def redirect_active(args, source):
    state = require_private_root(args.state_root.expanduser().resolve())
    if os.environ.get('MMS_WEB_SKIP_ACTIVE') == '1' or args.static_root.resolve() != source/'mms_web_static':
        return
    target = active_source(state, source)
    if not target:
        return
    cmd = [sys.executable, '-P', '-m', 'mms_web', '--state-root', str(state), '--port', str(args.port)]
    if args.config_root:
        cmd += ['--config-root', str(args.config_root.expanduser().resolve())]
    if args.open:
        cmd += ['--open']
    env = candidate_environment(target)
    env['MMS_WEB_UPDATE_CHECK'] = os.environ.get('MMS_WEB_UPDATE_CHECK', '')
    os.execve(sys.executable, cmd, env)


def acquire_state_lock(state):
    root = require_private_root(state)/'updates'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root/'service.lock', os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(descriptor)
        raise RuntimeError('这个会话目录已有 Pilot 服务运行。请使用已有服务。') from None
    return descriptor
