# -*- coding: utf-8 -*-
"""Human-gate catalog for Settings actions in the MMS config WebUI."""

from __future__ import annotations

from typing import Any

from mms_config.web_common import _safe_text


def _load_mms_core():
    from mms_config import web

    return web._load_mms_core()


def _about_upgrade_gate_commands() -> list[str]:
    try:
        mms_core = _load_mms_core()
        commands = [
            mms_core._mms_upgrade_shell_command(include_clis=False),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("codex"),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("claude"),  # noqa: SLF001 - display only
        ]
        return [item for item in commands if _safe_text(item)]
    except Exception:
        return [
            "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --latest-tag",
            "npm install -g @openai/codex@latest",
            "npm install -g @anthropic-ai/claude-code@latest",
        ]


def _settings_gate_catalog(command_name: str = "mms") -> dict[str, dict[str, Any]]:
    command = _safe_text(command_name) or "mms"
    registry = f"{command} registry"
    webui = f"{command} config web"
    interactive = command
    account_writes = [
        "~/.config/mms/config.toml accounts/account.defaults",
        "~/.config/mms/accounts/** OAuth/account state",
        "可能涉及外部浏览器或 CLI login side effects",
    ]
    registry_writes = [
        "<MMS_CONFIG_ROOT>/registry/model-registry.sqlite",
        "<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json",
        "<MMS_CONFIG_ROOT>/generated/model-capabilities.approved.json",
    ]
    return {
        "guard_status": {
            "title": "Snapshot 快照状态 / accept",
            "risk_level": "medium",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status 查看 accepted/latest/pending snapshot 和 drift。",
                "只有确认当前 config drift 是你要保留的状态后，再手动运行 accept。",
                "WebUI 只展示 gate，不会替你接受 baseline。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "只点 guard_status 查看状态；不要运行 accept。",
        },
        "guard_accept_gate": {
            "title": "接受当前 Snapshot baseline",
            "risk_level": "high",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status，确认 drift 来自你刚刚认可的配置变化。",
                "再运行 accept；这会把当前 snapshot 设为新的已确认 baseline。",
                "如果 drift 涉及 Claude account/proxy/home_dir，按 human-only 规则停下人工确认。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "保留 pending drift，只在 WebUI/CLI 里查看 status。",
        },
        "connect_official_gate": {
            "title": "OAuth / AGY 官方登录已下线",
            "risk_level": "low",
            "commands": [],
            "manual_steps": [
                "不再新增 WebUI OAuth / AGY 官方登录能力。",
                "已有 account 只保留默认值、priority、note 等兼容配置。",
                "新配置走 API Key provider，并通过保存预览写入。",
            ],
            "writes": [],
            "safe_alternative": "网关 API Key 通道使用 WebUI Add provider + 保存预览，不走 OAuth。",
        },
        "migrate_config_gate": {
            "title": "迁移旧配置 / v2 promotion 人工确认",
            "risk_level": "high",
            "commands": [f"{command} migrate config-v2 --json", f"{command} config migrate", f"{command} config root --json"],
            "manual_steps": [
                "先用只读 migration/promotion plan 看 preview root 与 stable root 的差异。",
                "确认 backup、目标 root、secret 处理和 human-only config 边界。",
                "只有人工确认后才运行实际迁移命令。",
            ],
            "writes": ["~/.config/mms/** stable config tree", "<MMS_CONFIG_ROOT>/registry/** preview DB/root artifacts", "config backups / audit logs"],
            "safe_alternative": "在 WebUI 保存页生成 preview plan，不直接迁移 stable。",
        },
        "family_autosort_gate": {
            "title": "按速度统计批量排序 family priority",
            "risk_level": "medium",
            "commands": [webui, interactive],
            "manual_steps": [
                "先在 WebUI 通道页查看/编辑 provider priority 与 family_priority_overrides。",
                "生成保存预览，确认每个 family 的排序变化。",
                "如要使用 TUI speed stats autosort，只能人工打开主 TUI 并逐项确认，不从 WebUI 自动批量改。",
            ],
            "writes": ["provider.priority", "provider.family_priority_overrides", "account.family_priority_overrides"],
            "safe_alternative": "WebUI 已提供手工 family priority 草稿 + diff review，替代自动批量排序。",
        },
        "account_login_gate": {
            "title": "账号登录",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.login <account-id>", f"{command} config account.status <account-id>"],
            "manual_steps": [
                "确认 account id 不是 Claude human-only account。",
                "手动执行 login，并完成外部 OAuth/CLI 交互。",
                "回到 WebUI 刷新 accounts report，检查默认账号和状态。",
            ],
            "writes": account_writes,
            "safe_alternative": "非 OAuth API Key 通道使用 WebUI provider credentials draft。",
        },
        "account_remove_gate": {
            "title": "删除账号",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.status <account-id>", f"{command} config account.remove <account-id>"],
            "manual_steps": [
                "确认该 account 没有作为默认账号或专属 key 绑定使用。",
                "Claude account/remove 必须停在 human-only gate。",
                "手动 remove 后回 WebUI accounts report 和保存预览核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<account-id>/**"],
            "safe_alternative": "先在 WebUI 将非 Claude account disabled/default 草稿调整并 review。",
        },
        "account_rename_gate": {
            "title": "重命名账号 / 移动账号 home",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.rename <old-account-id> <new-account-id>"],
            "manual_steps": [
                "先确认 old/new account id、默认账号引用和账号 home_dir。",
                "该动作可能移动 account home 目录并重写 usage/defaults；必须人工确认备份和目标目录不存在。",
                "完成后回 WebUI accounts report，核对 id/default/usage 是否一致。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<old-id>/** -> <new-id>/**", "~/.config/mms/usage.json account usage keys"],
            "safe_alternative": "WebUI 已支持非 Claude account 显示名、启用状态、priority、family、timezone、note 的草稿/保存预览。",
        },
        "account_network_gate": {
            "title": "编辑账号 proxy / no_proxy / home_dir",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.edit <account-id>"],
            "manual_steps": [
                "不要在 WebUI 中回显或复制 proxy/no_proxy 明文；这些字段可能包含凭据或影响 OAuth/Claude 网络边界。",
                "Claude account config 是 human-only；任何 Claude proxy/home_dir/no_proxy 变化都必须停止并人工确认。",
                "非 Claude 账号如需改 proxy/no_proxy，请在终端人工运行 account.edit 并随后回 WebUI 做只读核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts[*].proxy/no_proxy/home_dir/timezone", "~/.config/mms/accounts/** account state can be affected by launch/login"],
            "safe_alternative": "WebUI 只显示 proxy/no_proxy 是否已配置；非敏感 timezone/note 可在账号表中走保存预览。",
        },
        "provider_network_gate": {
            "title": "编辑通道 proxy / no_proxy",
            "risk_level": "high",
            "commands": [f"{command} config provider.edit <provider-id>"],
            "manual_steps": [
                "proxy/no_proxy 可能包含凭据，也可能改变 Claude/provider 的网络隔离策略；WebUI 不回显明文。",
                "修改前先确认目标 provider、expected proxy、no_proxy 不会命中 Claude/OpenAI 域名造成直连泄漏。",
                "人工执行 provider.edit 后回到 WebUI 生成保存预览或 provider_usage_summary 核对非敏感字段。",
            ],
            "writes": ["~/.config/mms/config.toml providers[*].proxy/no_proxy", "provider network policy for future launches"],
            "safe_alternative": "WebUI 支持通道 URL/API Key/protocol/CLI/timezone/note/Claude 1M 的草稿/保存预览；只把 proxy/no_proxy 留给人工确认。",
        },
        "refresh_due_sources_gate": {
            "title": "刷新到期 registry source",
            "risk_level": "medium",
            "commands": [f"{registry} check-staleness", f"{registry} refresh-sources --if-due"],
            "manual_steps": [
                "先运行 check-staleness，只读确认哪些 source 到期。",
                "确认可写 preview registry root 后，再运行 --if-due refresh。",
                "刷新后运行 source-status/preview-doctor 核对。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "WebUI 点击过期检查报告只读查看。",
        },
        "scheduled_refresh_gate": {
            "title": "定时 registry 刷新",
            "risk_level": "medium",
            "commands": [f"{registry} scheduled-refresh --dry-run --no-network", f"{registry} scheduled-refresh --no-network", f"{registry} scheduled-refresh"],
            "manual_steps": [
                "先 dry-run/no-network，确认 due state 和不会访问外网。",
                "需要联网 OpenRouter refresh 时，由人工明确运行不带 --no-network 的命令。",
                "执行后查看 scheduled output、source-status 和 preview doctor。",
            ],
            "writes": registry_writes,
            "safe_alternative": "保留 WebUI 只读报告；不要执行联网/写入刷新。",
        },
        "refresh_sources_gate": {
            "title": "刷新全部 registry source",
            "risk_level": "high",
            "commands": [f"{registry} refresh-sources", f"{registry} source-status --json"],
            "manual_steps": [
                "确认当前 root 是预期 preview/stable root。",
                "运行 refresh-sources 前先确认 reference snapshots 和写入范围。",
                "完成后用 source-status/preview-doctor 验证。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "只运行 check-staleness 或 source-status。",
        },
        "fetch_openrouter_gate": {
            "title": "拉取 OpenRouter catalog",
            "risk_level": "medium",
            "commands": [f"{registry} fetch-openrouter-catalog", f"{registry} fetch-openrouter-catalog --from-file <models.json>"],
            "manual_steps": [
                "联网拉取前确认网络可用和 OpenRouter source 仍可信。",
                "如已有离线 catalog，优先使用 --from-file。",
                "完成后再运行 diff-openrouter-catalog 查看候选变化。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "用 --from-file 导入人工下载的 catalog，避免 WebUI 自动联网。",
        },
        "diff_openrouter_gate": {
            "title": "对比 OpenRouter candidate 变化",
            "risk_level": "medium",
            "commands": [f"{registry} diff-openrouter-catalog --limit 50", f"{registry} diff-openrouter-catalog --no-store --limit 50"],
            "manual_steps": [
                "先用 --no-store 只读查看 diff。",
                "确认 candidate changes 合理后，再允许 store candidate_change rows。",
                "后续 publish 前必须走 approved bundle 验证。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/registry/model-registry.sqlite candidate_change rows"],
            "safe_alternative": "只运行 --no-store diff。",
        },
        "publish_approved_gate": {
            "title": "发布已批准 Bundle",
            "risk_level": "high",
            "commands": [f"{registry} publish-approved", f"{registry} verify --json"],
            "manual_steps": [
                "先确认 candidate/bundle revision 和 route shrink guard。",
                "人工运行 publish-approved 后立刻运行 verify。",
                "verify 未通过时不要继续把结果交给 launcher/runtime。",
            ],
            "writes": registry_writes[1:],
            "safe_alternative": "WebUI 保存页 preview apply 会在明确 confirm 后 publish/verify preview bundle。",
        },
        "verify_approved_gate": {
            "title": "验证已批准 Bundle",
            "risk_level": "low",
            "commands": [f"{registry} verify --json", f"{registry} consumer-bundle --json --no-strict-exit"],
            "manual_steps": [
                "运行 verify 检查 latest-approved manifest/hash。",
                "再运行 consumer-bundle 查看下游可读状态。",
                "此 gate 保留 CLI/manual path，WebUI 不替你执行外部命令。",
            ],
            "writes": [],
            "safe_alternative": "WebUI 点击消费端 Bundle 报告读取当前状态。",
        },
        "rescue_create_demo_gate": {
            "title": "生成 demo rescue packet",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> Rescue -> 生成测试 rescue packet。",
                "确认写入 repo-local .mms/rescue demo artifacts。",
                "完成后在 WebUI 点击 rescue_events 查看 artifact path。",
            ],
            "writes": ["<repo>/.mms/rescue/**", "~/.config/mms/rescue/index.jsonl metadata"],
            "safe_alternative": "WebUI 只读 rescue_events；不生成 demo artifact。",
        },
        "rescue_handover_gate": {
            "title": "生成 fallback 交接",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "先在 WebUI rescue_events 找到要处理的 rescue packet。",
                "打开主 TUI：Settings -> Rescue -> 选择 packet -> handover/manual_handover。",
                "确认 fallback model 和 artifact path 后再生成。",
            ],
            "writes": ["<repo>/.mms/rescue/latest-fallback-handover.json", "<repo>/.mms/rescue/latest-fallback-handover.md"],
            "safe_alternative": "WebUI 已支持 fallback/hot fallback 持久配置草稿，handover artifact 仍人工生成。",
        },
        "about_refresh_gate": {
            "title": "刷新版本检查",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> About -> 刷新版本检查。",
                "该动作可能访问 GitHub/npm 并更新本地 version cache。",
                "WebUI about report 默认只读 cached 状态，不自动联网刷新。",
            ],
            "writes": ["~/.config/mms/version.json update cache"],
            "safe_alternative": "WebUI 点击关于状态读取缓存版本状态。",
        },
        "about_upgrade_gate": {
            "title": "升级 MMS / Codex / Claude CLI",
            "risk_level": "critical",
            "commands": _about_upgrade_gate_commands(),
            "manual_steps": [
                "先看当前版本和 latest 版本，确认升级目标。",
                "手动复制并运行对应升级命令；这会联网并修改本机安装。",
                "升级后重新打开 WebUI，运行 summary/py_compile/smoke 确认入口可用。",
            ],
            "writes": ["MMS install location", "global npm packages for Codex/Claude CLI"],
            "safe_alternative": "只查看 about cached status，不执行升级。",
        },
        "provider_remove_gate": {
            "title": "删除通道 legacy 人工确认",
            "risk_level": "medium",
            "commands": [webui, f"{command} config provider.remove <provider-id>"],
            "manual_steps": [
                "WebUI 当前已提供 typed confirm 草稿删除；优先使用 WebUI 保存预览。",
                "CLI remove 属于 legacy mutating path，执行前先确认 provider 不再被默认/route/fallback 使用。",
            ],
            "writes": ["~/.config/mms/config.toml providers/provider.default", "credentials/model-policy related entries"],
            "safe_alternative": "WebUI typed confirm -> 生成保存预览 -> confirm save。",
        },
    }
