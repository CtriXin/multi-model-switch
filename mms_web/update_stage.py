"""Prepare an immutable Web release without running install.sh or touching config."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from .updates import NoRedirect, REPO, TAG, read_json

MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024


def download_release(tag: str, destination: Path):
    if not TAG.fullmatch(tag):
        raise ValueError('invalid release tag')
    url = f'https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}'
    req = urllib.request.Request(url, headers={'User-Agent': 'MMS-Pilot'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response, destination.open('xb') as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError('release download too large')
            output.write(chunk)


def unpack_release(archive: Path, destination: Path):
    total, prefix, count = 0, None, 0
    with tarfile.open(archive, 'r:gz') as bundle:
        for item in bundle:
            count += 1
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('unsafe archive path')
            if prefix is None:
                prefix = path.parts[0]
            if path.parts[0] != prefix or count > 100000:
                raise ValueError('invalid archive layout')
            relative = Path(*path.parts[1:])
            # Optional shared agent governance link is not a runtime dependency.
            if item.issym() and relative.as_posix() == 'agent-rules':
                continue
            if not (item.isdir() or item.isfile()):
                raise ValueError('release contains an unsafe archive entry')
            total += item.size
            if total > MAX_UNPACKED:
                raise ValueError('release expands beyond size limit')
            target = destination / relative
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with bundle.extractfile(item) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o700 if item.mode & 0o111 else 0o600)


def validate_bundle(source: Path, tag: str):
    public = source / 'mms_web_static'
    manifest = read_json(public / 'build.json')
    files = manifest.get('files')
    if manifest.get('version') != tag.removeprefix('v') or not isinstance(files, dict) or 'index.html' not in files:
        raise ValueError('release Web bundle version mismatch')
    for name, digest in files.items():
        path = public / name
        if not path.resolve().is_relative_to(public.resolve()) or not path.is_file() or path.is_symlink():
            raise ValueError('invalid Web bundle file')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Web bundle integrity check failed')
    if not (source / 'mms_web/update_handoff.py').is_file():
        raise ValueError('release does not support safe update protocol')
    return manifest


def candidate_environment(source: Path):
    env = os.environ.copy()
    env['PYTHONPATH'] = str(source)
    env['MMS_WEB_UPDATE_CHECK'] = '0'
    env['MMS_WEB_SKIP_ACTIVE'] = '1'
    return env


def probe_release(source: Path, tag: str):
    # The candidate only sees a disposable config/state root during its probe.
    with tempfile.TemporaryDirectory(prefix='pilot-probe-', dir=source.parent) as temporary:
        root = Path(temporary)
        env = candidate_environment(source)
        env.update(HOME=str(root), MMS_REAL_HOME=str(root), MMS_CONFIG_ROOT=str(root / 'config'))
        code = "from mms_version import VERSION; from mms_web.server import WebApplication; from mms_web.update_handoff import PROTOCOL; from pathlib import Path; import sys; assert VERSION == sys.argv[1] and PROTOCOL == 1; app=WebApplication(state_root=Path(sys.argv[2])); app.close()"
        result = subprocess.run([sys.executable, '-P', '-c', code, tag.removeprefix('v'), str(root / 'state')], cwd=source, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45)
        if result.returncode:
            raise ValueError('candidate runtime probe failed; original service retained')


def stage_release(root: Path, tag: str, *, downloader=download_release, probe=probe_release):
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise ValueError('invalid release tag')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Every attempt gets its own directory; never overwrite an executing release.
    destination = Path(tempfile.mkdtemp(prefix=tag + '-', dir=root))
    archive, source = destination / 'source.tar.gz', destination / 'source'
    downloader(tag, archive)
    source.mkdir(mode=0o700)
    unpack_release(archive, source)
    validate_bundle(source, tag)
    probe(source, tag)
    return source
