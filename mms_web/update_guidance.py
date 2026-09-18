"""Read-only upgrade advice: verified release policies and actual install drift.

Old clients can read the prose in release notes, but cannot acquire these
guards remotely. Only a client shipping this module enforces the policy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mms_state_io import LEGACY_CONFIG_ROOT_NAME
from .updates import version_tuple
from .runtime import real_home

INSTALL_COMMAND = 'curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash'
POLICY = re.compile(r'<!--\s*mms-upgrade-policy\s*:\s*(\{.{1,2000}?\})\s*-->', re.DOTALL)
# The stable line stops at 4.x. A newer major means the install came from the
# preview line, and pilot's own updater only ever moves forward.
STABLE_LINE = 4
STEPS = [
    '先等执行中、待确认和排队的任务全部结束，再停止 Pilot 服务。关闭浏览器标签页不会停止服务。',
    '可用 mms web stop 停止后台服务；很旧的前台版本请回到启动它的终端按 Ctrl+C。',
    '执行下面的安装命令，完成后重新打开 Pilot。使用自定义会话目录时，继续指定原来的 --state-root。',
    '如果以前只在旧终端配置过通道，请在 Pilot 设置中重新连接并确认模型可用。',
]
BACKUP_STEP = ('先备份 5.x 数据：~/.local/share/mms-web 里的 Bot 工作台、定时任务和记忆不会被 4.x 读取；'
               '降级前自己留一份。')
BACK_TO_STABLE_TITLE = '回到 4.x 稳定线要用安装器'
BACK_TO_STABLE_REASON = ('当前运行的是 5.x 预览线。Pilot 内的更新只会安装更高的版本，4.x 稳定版不会以「有更新」'
                         '的形式出现；回到稳定线要用安装器重新安装。')


def release_policy(notes):
    """Optional release-authored cutoff; never accept an executable command."""
    match = POLICY.search(str(notes or '')[:16000])
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return {}
    if not isinstance(value, dict) or not version_tuple(value.get('manualBelow')):
        return {}
    reason = value.get('reason')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        return {}
    return {'manualBelow': value['manualBelow'], 'reason': reason.strip()}


def upgrade_guidance(current, latest, *, installation=None, config_root=None, channel=None):
    """Where the user has to go next, or None when the updater can do it alone.

    ``channel`` is the update channel the user selected. A 5.x install that
    checks the stable channel finds a 4.x release; that is not an update the
    updater can install, and the page must say so instead of calling the
    install up to date.
    """
    reason, title, steps = '', '请先用安装器更新', list(STEPS)
    installed = version_tuple(current)
    legacy_default = Path(real_home(), '.config', LEGACY_CONFIG_ROOT_NAME).resolve()
    if config_root is not None and Path(config_root).expanduser().resolve() == legacy_default:
        reason = '当前 Pilot 仍指向旧配置目录。请重新安装并从统一配置入口启动，确认通道可用后再继续。'
    elif (installation or {}).get('manualInstallRequired'):
        reason = installation['reason']
    elif channel == 'stable' and installed and installed[0] > STABLE_LINE:
        title, reason = BACK_TO_STABLE_TITLE, BACK_TO_STABLE_REASON
        steps = [BACKUP_STEP, *steps]
    else:
        policy = latest.get('upgradePolicy') or {}
        minimum = version_tuple(policy.get('manualBelow'))
        target = version_tuple(latest.get('tag'))
        if minimum and installed and target and installed < minimum <= target:
            reason = policy.get('reason') or '目标版本要求先运行安装器。'
    if not reason:
        return None
    return {
        'required': True,
        'title': title,
        'reason': reason,
        'command': INSTALL_COMMAND,
        'steps': steps,
    }
