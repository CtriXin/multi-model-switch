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


def upgrade_guidance(current, latest, *, installation=None, config_root=None):
    reason = ''
    legacy_default = Path(real_home(), '.config', LEGACY_CONFIG_ROOT_NAME).resolve()
    if config_root is not None and Path(config_root).expanduser().resolve() == legacy_default:
        reason = '当前 Pilot 仍指向旧配置目录。请重新安装并从统一配置入口启动，确认通道可用后再继续。'
    elif (installation or {}).get('manualInstallRequired'):
        reason = installation['reason']
    else:
        policy = latest.get('upgradePolicy') or {}
        minimum = version_tuple(policy.get('manualBelow'))
        installed, target = version_tuple(current), version_tuple(latest.get('tag'))
        if minimum and installed and target and installed < minimum <= target:
            reason = policy.get('reason') or '目标版本要求先运行安装器。'
    if not reason:
        return None
    return {
        'required': True,
        'title': '请先用安装器更新',
        'reason': reason,
        'command': INSTALL_COMMAND,
        'steps': [
            '先等执行中、待确认和排队的任务全部结束，再停止 Pilot 服务。关闭浏览器标签页不会停止服务。',
            '可用 mms web stop 停止后台服务；很旧的前台版本请回到启动它的终端按 Ctrl+C。',
            '执行下面的安装命令，完成后重新打开 Pilot。使用自定义会话目录时，继续指定原来的 --state-root。',
            '如果以前只在旧终端配置过通道，请在 Pilot 设置中重新连接并确认模型可用。',
        ],
    }
