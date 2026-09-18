#!/usr/bin/env python3
"""Manage only this installation's foreground-independent DSH process."""
import argparse
import fcntl
import http.cookiejar
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def identity(pid, config):
    try:
        command = subprocess.check_output(['/bin/ps','-p',str(pid),'-o','command='],text=True).strip()
        return str(Path(config['runtime'])/'node_modules/@deepseek-ai/dsh/lib/bin.js') in command and str(Path(config['instance'])/'mms.patch.yml') in command
    except subprocess.CalledProcessError:
        return False


def ready_url(log):
    if not log.exists():
        return None
    matches = re.findall(r'dsh web: (http://127\.0\.0\.1:\d+/\?token=[\w-]+)', log.read_text(errors='replace'))
    return matches[-1] if matches else None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['start','stop','status','open'],nargs='?',default='open')
    parser.add_argument('--installation',type=Path,required=True)
    args=parser.parse_args()
    root=args.installation.resolve();config=json.loads((root/'installation.json').read_text())
    log=root/'service.log';pidfile=root/'service.pid'
    with (root/'service.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        pid=int(pidfile.read_text()) if pidfile.exists() else 0
        running=bool(pid and identity(pid,config))
        if args.action=='status':
            print(json.dumps({'running':running,'pid':pid if running else None,'url':ready_url(log) if running else None},ensure_ascii=False));return
        if args.action=='stop':
            if running:
                os.kill(pid,signal.SIGTERM)
                for _ in range(100):
                    if not identity(pid,config):break
                    time.sleep(.1)
                if identity(pid,config):raise SystemExit('DSH is still stopping; process was not force-killed')
            pidfile.unlink(missing_ok=True);print('MMS DSH 已停止；会话和配置已保留。');return
        if not running:
            if log.exists():log.rename(root/'service.previous.log')
            command=[config['python'],str(root/'source/integrations/dsh/run.py')]
            for key in ['instance','mms_root','node','runtime','workspace','model','port']:
                command.extend(['--'+key.replace('_','-'),str(config[key])])
            fd=os.open(log,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as stream:
                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True)
            pid=process.pid;pidfile.write_text(str(pid))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        for _ in range(200):
            url=ready_url(log)
            if url and identity(pid,config):
                try:
                    with opener.open(url,timeout=1) as response:
                        if response.status==200:
                            if args.action=='open':webbrowser.open(url)
                            print(url);return
                except OSError:pass
            time.sleep(.1)
        raise SystemExit('DSH 未就绪，请检查 '+str(log))

if __name__=='__main__':main()
