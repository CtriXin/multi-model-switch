import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from mms_web.install_lock import acquire_runtime_lease
from test_install_script_paths import _extract_shell_function_body

ROOT=Path(__file__).resolve().parents[1]


def guard(home, command='guard_live_pilot_install', keep_running=0, port=0):
    """port=0 disables the port scan so tests never touch a real Pilot on 8765."""
    text=(ROOT/'install.sh').read_text()
    body=_extract_shell_function_body(text,'guard_live_pilot_install')
    inspect=_extract_shell_function_body(text,'inspect_live_pilot')
    script=('_python_bin() { command -v python3; }\nt() { printf "%s" "$1"; }\n'
            f'KEEP_RUNNING_PILOT={keep_running}\nSTOPPED_PILOT=0\nMMS_WEB_DEFAULT_PORT={port}\n'
            'guard_live_pilot_install() {'+body+'\n}\n'
            'inspect_live_pilot() {'+inspect+'\n}\n'+command)
    return subprocess.run(['bash','-ec',script],env={**os.environ,'MMS_HOME':str(home)},capture_output=True,text=True)


def _fake_pilot_server(home):
    """A process that looks like a Pilot server for this installation."""
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)','-m','mms_web',str(home/'source')],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    return process


def test_installer_refuses_when_only_a_lease_holder_is_found(tmp_path,monkeypatch):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    monkeypatch.delenv('MMS_WEB_INSTALL_ROOT',raising=False)
    fd=acquire_runtime_lease(home)
    try:
        result=guard(home)
        # Nothing identifiable to stop, so the install stops instead of guessing.
        assert result.returncode!=0 and '没有关闭进程或清理会话' in result.stdout
    finally:os.close(fd)
    assert guard(home).returncode==0


def test_installer_pauses_for_a_live_pilot_without_stopping_it(tmp_path):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    process=_fake_pilot_server(home)
    try:
        result=guard(home,command='guard_live_pilot_install\necho "STOPPED=$STOPPED_PILOT"')
        assert result.returncode != 0,result.stderr
        assert '没有关闭进程或清理会话' in result.stdout
        assert process.poll() is None
    finally:
        if process.poll()is None:
            process.kill();process.wait(timeout=10)


def test_keep_running_pilot_refuses_and_leaves_the_server_alone(tmp_path):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    process=_fake_pilot_server(home)
    try:
        result=guard(home,keep_running=1)
        assert result.returncode!=0 and '没有关闭进程或清理会话' in result.stdout
        assert process.poll()is None
    finally:
        process.kill();process.wait(timeout=10)


def test_install_lease_outlives_python_and_prevents_concurrent_runtime(tmp_path):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    code='import os,sys; os.environ.pop("MMS_WEB_INSTALL_ROOT",None); from mms_web.install_lock import acquire_runtime_lease; acquire_runtime_lease(sys.argv[1])'
    import shlex
    command='guard_live_pilot_install\npython3 -c '+shlex.quote(code)+' "$MMS_HOME"'
    result=guard(home,command)
    assert result.returncode!=0 and '安装正在进行' in result.stderr


def test_installer_pauses_for_a_pilot_started_with_the_mms_web_subcommand(tmp_path):
    """`mms web` serves in-process, so its argv is the CLI entry plus `web`."""
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)',str(home/'mms'),'web'],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        result=guard(home,command='guard_live_pilot_install\necho "STOPPED=$STOPPED_PILOT"')
        assert result.returncode != 0,result.stdout+result.stderr
        assert '没有关闭进程或清理会话' in result.stdout
        assert process.poll() is None
    finally:
        if process.poll()is None:
            process.kill();process.wait(timeout=10)


def test_keep_running_pilot_flag_does_not_swallow_the_next_argument():
    """The option loop shifts once per iteration; a case body must not shift again."""
    text=(ROOT/'install.sh').read_text()
    start=text.index('        --keep-running-pilot)')
    body=text[start:text.index(';;',start)]
    assert 'shift' not in body,body
    loop=text[text.index('while [[ $# -gt 0 ]]; do'):]
    assert '\n    esac\n    shift\n' in loop


def _free_port():
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        return probe.getsockname()[1]


def test_installer_pauses_for_a_pilot_from_another_install_holding_the_port(tmp_path):
    """A Pilot that updated itself, or came from another install dir, serves the
    default port with a foreign source path. It is still asked to exit so the
    fresh install does not end up as a second Pilot on the next port."""
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    port=_free_port()
    code=f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); time.sleep(60)"
    process=subprocess.Popen([sys.executable,'-c',code,'-m','mms_web',str(tmp_path/'elsewhere'/'updates'/'v9.9.9')],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        result=guard(home,command='guard_live_pilot_install\necho "STOPPED=$STOPPED_PILOT"',port=port)
        assert result.returncode != 0,result.stdout+result.stderr
        assert '没有关闭进程或清理会话' in result.stdout
        assert process.poll() is None
    finally:
        if process.poll()is None:
            process.kill();process.wait(timeout=10)


def test_port_scan_is_off_when_no_port_is_given(tmp_path):
    """The guard must not signal anything just because some Pilot listens elsewhere."""
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    port=_free_port()
    code=f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); time.sleep(60)"
    process=subprocess.Popen([sys.executable,'-c',code,'-m','mms_web',str(tmp_path/'elsewhere')],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        result=guard(home,port=0)
        assert result.returncode==0,result.stdout+result.stderr
        assert process.poll()is None
    finally:
        process.kill();process.wait(timeout=10)
