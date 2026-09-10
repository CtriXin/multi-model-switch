"""Bounded release checks. Only Web-owned state is written; no provider calls."""
from __future__ import annotations
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from mms_version import VERSION
from .errors import WebError
from .runtime import private_json

REPO = 'CtriXin/multi-model-switch'
RELEASE_API = f'https://api.github.com/repos/{REPO}/releases/latest'
CHECK_INTERVAL = 6 * 60 * 60
TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')


def version_tuple(value):
    match = TAG.fullmatch('v' + str(value).removeprefix('v'))
    return tuple(map(int, match.groups())) if match else None


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def checked_at(cache):
    value = cache.get('checkedAt', 0)
    return value if isinstance(value, (int, float)) and 0 <= value < 10**12 else 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WebError('UPDATE_DOWNLOAD_FAILED', '更新来源发生了意外跳转，请稍后重试。', 502)


def fetch_release():
    request = urllib.request.Request(RELEASE_API, headers={'User-Agent': 'MMS-Pilot', 'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
        content = response.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError('release response too large')
    value = json.loads(content)
    tag = value.get('tag_name')
    if not isinstance(tag, str) or not TAG.fullmatch(tag) or value.get('draft') or value.get('prerelease'):
        raise ValueError('invalid stable release')
    return {'tag': tag, 'notes': str(value.get('body') or '')[:16000],
            'publishedAt': str(value.get('published_at') or '')[:80],
            'url': f'https://github.com/{REPO}/releases/tag/{tag}'}


class UpdateService:
    def __init__(self, app, *, fetcher=fetch_release, clock=time.time):
        self.app, self.fetcher, self.clock = app, fetcher, clock
        self.root = app.state_root / 'updates'
        self._check_lock = threading.Lock()
        self._stop = threading.Event()
        self._checking = False
        self._scheduler = None
        self.coordinator = None

    def enabled(self):
        if os.environ.get('MMS_WEB_UPDATE_CHECK', '').lower() in {'0', 'false', 'off'}:
            return False
        return read_json(self.root / 'settings.json').get('enabled', True) is not False

    def status(self):
        cache = read_json(self.root / 'check.json')
        latest = cache.get('latest') if isinstance(cache.get('latest'), dict) else {}
        remote, current = version_tuple(latest.get('tag')), version_tuple(VERSION)
        available = bool(remote and current and remote > current)
        operation = self.coordinator.status() if self.coordinator else {'phase': 'idle'}
        return {'currentVersion': VERSION, 'latest': latest, 'updateAvailable': available,
                'enabled': self.enabled(), 'checking': self._checking,
                'checkedAt': checked_at(cache), 'checkInterval': CHECK_INTERVAL,
                'error': str(cache.get('error') or ''), 'operation': operation,
                'canUpgrade': bool(available and self.coordinator and self.coordinator.available())}

    def check(self, *, manual=False):
        if not manual and not self.enabled():
            return self.status()
        if not self._check_lock.acquire(blocking=False):
            return self.status()
        try:
            cache = read_json(self.root / 'check.json')
            interval = 60 if manual else (1800 if cache.get('error') else CHECK_INTERVAL)
            age = self.clock() - checked_at(cache)
            if checked_at(cache) and 0 <= age < interval:
                return self.status()
            self._checking = True
            try:
                latest = self.fetcher()
                private_json(self.root / 'check.json', {'checkedAt': self.clock(), 'latest': latest, 'error': ''})
            except Exception:
                private_json(self.root / 'check.json', {**cache, 'checkedAt': self.clock(), 'error': '暂时无法检查更新，稍后可以重试。现有会话不受影响。'})
        finally:
            self._checking = False
            self._check_lock.release()
        return self.status()

    def request_check(self):
        threading.Thread(target=self.check, kwargs={'manual': True}, name='pilot-update-check', daemon=True).start()
        return self.status()

    def preferences(self, payload):
        if not isinstance(payload.get('enabled'), bool):
            raise WebError('INVALID_REQUEST', '更新检查设置无效。', 400)
        private_json(self.root / 'settings.json', {'enabled': payload['enabled']})
        return self.status()

    def start_scheduler(self):
        if self._scheduler:
            return
        def loop():
            while not self._stop.is_set():
                try:
                    self.check()
                except OSError:
                    pass  # Unwritable update cache must not stop the Web service.
                self._stop.wait(60)
        self._scheduler = threading.Thread(target=loop, name='pilot-release-scheduler', daemon=True)
        self._scheduler.start()

    def close(self):
        self._stop.set()
