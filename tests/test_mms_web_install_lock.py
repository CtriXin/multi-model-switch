import fcntl
import os
import subprocess
from pathlib import Path
import pytest
from mms_web.install_lock import acquire_runtime_lease
from test_install_script_paths import _extract_shell_function_body

ROOT=Path(__file__).resolve().parents[1]


def guard(home, command='guard_live_pilot_install'):
    body=_extract_shell_function_body((ROOT/'install.sh').read_text(),'guard_live_pilot_install')
    script='_python_bin() { command -v python3; }\nt() { printf "%s" "$1"; }\nguard_live_pilot_install() {'+body+'\n}\n'+command
    return subprocess.run(['bash','-ec',script],env={**os.environ,'MMS_HOME':str(home)},capture_output=True,text=True)


def test_installer_refuses_live_runtime_and_allows_after_exit(tmp_path,monkeypatch):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    monkeypatch.delenv('MMS_WEB_INSTALL_ROOT',raising=False)
    fd=acquire_runtime_lease(home)
    try:
        result=guard(home)
        assert result.returncode!=0 and '没有关闭进程或清理会话' in result.stdout
    finally:os.close(fd)
    assert guard(home).returncode==0


def test_install_lease_outlives_python_and_prevents_concurrent_runtime(tmp_path):
    home=tmp_path/'installation';(home/'mms_web').mkdir(parents=True)
    (home/'mms_web/__main__.py').write_text('fixture')
    code='import os,sys; os.environ.pop("MMS_WEB_INSTALL_ROOT",None); from mms_web.install_lock import acquire_runtime_lease; acquire_runtime_lease(sys.argv[1])'
    import shlex
    command='guard_live_pilot_install\npython3 -c '+shlex.quote(code)+' "$MMS_HOME"'
    result=guard(home,command)
    assert result.returncode!=0 and '安装正在进行' in result.stderr
