"""Read-only quiescence checks and durable, non-destructive state snapshots."""
from __future__ import annotations
import hashlib
import os
import shutil
from pathlib import Path
from .runtime import private_json


def session_safety(service, *, native=True):
    if service is None:
        return {'sessions': 0, 'live': 0, 'resumable': 0, 'blockers': []}
    with service._lock:
        sessions = list(service._sessions.values())
    result = {'sessions': len(sessions), 'live': 0, 'resumable': 0, 'blockers': []}
    for session in sessions:
        with session.lock:
            alive = session.alive()
            result['live'] += int(alive)
            result['resumable'] += int(session.can_resume())
            blocked = bool(session.approvals or session.pending_prompts or (alive and session.state in {'running', 'waiting'}))
            # An unacknowledged prompt/control request must not be cut over.
            driver = session.driver
        if alive and native and not blocked:
            try:
                response = driver.request({'type': 'get_state'}, timeout=2)
                state = response.get('data')
                if response.get('success') is not True or not isinstance(state, dict):
                    blocked = True
                else:
                    blocked = not (state.get('isStreaming') is False and state.get('isCompacting') is False and type(state.get('pendingMessageCount')) is int and state['pendingMessageCount'] == 0)
            except Exception:
                blocked = True  # Missing live evidence is not permission to restart.
        if blocked:
            result['blockers'].append(session.meta['id'])
    with service._lock:
        if any(item.get('pending') for item in service._requests.values()):
            result['blockers'].append('request-in-flight')
    return result


def file_manifest(root: Path):
    entries = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        relative = Path(directory).relative_to(root)
        if relative == Path('.'):
            dirs[:] = [name for name in dirs if name != 'updates']
        for name in [*dirs, *files]:
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            if path.is_symlink():
                entries[key] = {'link': os.readlink(path)}
            elif path.is_file():
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                entries[key] = {'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}
    return entries


def close_idle_sessions(service):
    """Caller holds the mutation lock and has explicit idle-restart consent."""
    if service is None:
        return
    safety = session_safety(service)
    if safety['blockers']:
        raise ValueError('session became busy before idle restart')
    with service._lock:
        sessions = list(service._sessions.values())
    # Validate every live session before stopping any of them.
    for session in sessions:
        with session.lock:
            if session.alive() and not session.can_resume():
                raise ValueError('live session has no recoverable native history')
    for session in sessions:
        with session.lock:
            if not session.alive():
                continue
            driver = session.driver
            session.stop_requested = True
        if not driver.close_for_update():
            with session.lock:
                session.stop_requested = False
            raise ValueError('idle Pi did not exit; no force kill attempted')
        with session.lock:
            session.persist(service._state_dir)


def backup_state(state: Path, destination: Path):
    before = file_manifest(state)
    required = sum(item.get('bytes', 0) for item in before.values()) + 16 * 1024 * 1024
    if shutil.disk_usage(state).free < required:
        raise ValueError('not enough space for a verified session backup')
    destination.mkdir(parents=True, mode=0o700)
    for item in state.iterdir():
        if item.name == 'updates':
            continue
        target = destination / item.name
        if item.is_symlink():
            target.symlink_to(os.readlink(item))
        elif item.is_dir():
            shutil.copytree(item, target, symlinks=True)
        else:
            shutil.copy2(item, target)
    if before != file_manifest(destination) or before != file_manifest(state):
        raise ValueError('state changed while backing up; update cancelled')
    private_json(destination.parent / (destination.name + '.manifest.json'), before)
    return before
