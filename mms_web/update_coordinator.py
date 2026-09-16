"""One update at a time. Preparation never interrupts the serving runtime."""
from __future__ import annotations
import os
import secrets
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from mms_version import VERSION
from .errors import WebError
from .runtime import private_json
from .updates import read_json
from .update_stage import stage_release, candidate_environment
from .update_safety import backup_state, session_safety, close_idle_sessions
from .update_handoff import session_inventory


class UpdateCoordinator:
    def __init__(self, app, server, source, static_root, *, stager=stage_release):
        self.app, self.server, self.source = app, server, Path(source).resolve()
        self.static_root = Path(static_root).resolve()
        self.root = app.state_root/'updates'
        self.stager = stager
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._operation = read_json(self.root/'operation.json')
        if self._operation.get('phase') in {'preparing', 'waiting', 'backing-up'}:
            self._operation = {'phase':'interrupted', 'message':'上次更新未完成，当前版本和会话已保留，可以重试。'}

    def available(self):
        return os.name == 'posix' and self.static_root == self.source/'mms_web_static'

    def status(self):
        # The guardian finishes the operation after this server has exited.
        if not self._thread or not self._thread.is_alive():
            stored = read_json(self.root/'operation.json')
            if stored.get('phase') in {'complete', 'rolled-back', 'error'}:
                return stored
        return dict(self._operation) or {'phase':'idle'}

    def _status(self, phase, message, *, cancellable=False):
        self._operation.update(phase=phase, message=message, cancellable=cancellable)
        private_json(self.root/'operation.json', self._operation)

    def start(self, payload):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.app.updates.status()
            latest = self.app.updates.status()
            target = payload.get('target')
            if (latest.get('upgradeGuidance') or {}).get('required'):
                raise WebError(
                    'UPDATE_REQUIRES_MANUAL_STEP',
                    latest['upgradeGuidance'].get('reason') or '请先按页面提示运行安装命令。',
                    409,
                )
            if not self.available() or not latest['updateAvailable'] or target != latest['latest'].get('tag'):
                raise WebError('UPDATE_UNAVAILABLE', '请先检查更新，并选择可用的稳定版本。', 409)
            self._cancel.clear()
            self._operation = {'id':uuid.uuid4().hex, 'target':target,
                               'allowIdleRestart':payload.get('allowIdleRestart') is True}
            self._status('preparing', '正在下载并检查新版，当前对话可以继续。', cancellable=True)
            self._thread = threading.Thread(target=self._run, args=(target,), name='pilot-safe-update', daemon=True)
            self._thread.start()
        return self.app.updates.status()

    def cancel(self):
        with self._lock:
            if not self._operation.get('cancellable'):
                raise WebError('UPDATE_COMMITTING', '更新已开始切换，请等待本次检查完成。', 409)
            self._cancel.set()
        return self.app.updates.status()

    def _run(self, target):
        try:
            candidate = self.stager(self.root/'versions', target)
            while not self._cancel.is_set():
                with self.app.mutation_lock:
                    safety = session_safety(self.app.sessions)
                    if safety['blockers']:
                        self._status('waiting', '还有任务执行、等待确认或排队消息，完成后再更新。你可以继续工作或取消更新。', cancellable=True)
                    elif safety['live'] and not self._operation['allowIdleRestart']:
                        self._status('waiting', '还有空闲 Pi 进程保持连接。若希望现在更新，可取消后勾选“允许重启空闲会话”；历史会保留，续聊时恢复。', cancellable=True)
                    else:
                        if self._cancel.is_set():
                            break
                        self.app.maintenance = True
                        if safety['live']:
                            self._status('backing-up', '正在备份会话；随后按你的选择重启空闲会话。')
                            backup_state(self.app.state_root, self.root/'operations'/self._operation['id']/'before-idle-restart')
                            close_idle_sessions(self.app.sessions)
                        self._status('backing-up', '正在备份会话、恢复目录和附件，即将切换版本。')
                        self._cutover(candidate, target)
                        return
                self._cancel.wait(3)
            self._status('cancelled', '本次更新已取消，当前版本和会话保持原状。')
        except Exception as exc:
            self.app.maintenance = False
            try:
                private_json(self.root/"last-error.json", {"type":type(exc).__name__, "phase":self._operation.get("phase"), "message":str(exc)[:1000]})
            except OSError:
                pass
            self._status('error', '新版准备或安全检查未完成，当前服务继续运行；会话未清理。可以稍后重试。')

    def port(self):
        """The port the update keeps: the handoff re-launches on this one.

        Reporting it must never be the reason the update status fails to load,
        so an unreadable address is 0 rather than an exception.
        """
        try:
            return int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError, ValueError):
            return 0

    def _cutover(self, candidate, target):
        operation_root = self.root/'operations'/self._operation['id']
        backup = operation_root/'backup'
        backup_state(self.app.state_root, backup)
        spec = {'id':self._operation['id'], 'target':target, 'source':str(candidate),
                'oldSource':str(self.source), 'oldVersion':VERSION, 'python':sys.executable,
                'state':str(self.app.state_root), 'config':str(self.app.config_root.resolve()),
                'cwd':os.getcwd(), 'port':self.server.server_address[1],
                'sessions':session_inventory(self.app.sessions), 'token':secrets.token_urlsafe(32),
                'backup':str(backup), 'operation':str(self.root/'operation.json'),
                'armed':str(operation_root/'armed'), 'log':str(operation_root/'service.log'),
                'updateCheck':os.environ.get('MMS_WEB_UPDATE_CHECK', '')}
        spec_path = operation_root/'handoff.json'
        private_json(spec_path, spec)
        with (operation_root/'guardian.log').open('ab') as log:
            subprocess.Popen([sys.executable, '-P', '-m', 'mms_web.update_handoff', str(spec_path)],
                             cwd=self.source, env=candidate_environment(self.source), stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
        self.app.pending_handoff = spec
        self._status('restarting', '备份完成，正在切换并验证新版本。')
        # shutdown must run outside serve_forever's thread.
        self.server.shutdown()
