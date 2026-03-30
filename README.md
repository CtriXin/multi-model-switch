# Multi-Model Switch (MMS)

> 一个让 `claude`、`codex`、`qwen`、`kimi` 等 AI 编程 CLI 统一接入的本地 launcher。

![MMS TUI - Claude Tab](assets/mms-tui.png)
*MMS TUI 界面：方向键选择模型，回车启动*

---

## 一句话

MMS = 一个入口管理你多个 CLI 的模型源、账号和启动参数。需要切模型或换 provider 时，不用改一堆环境变量。

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

## 3 个高频场景

### 1. 统一启动（支持 TUI 选模型）
```bash
mms              # 进入 TUI：选择模型 → 确认启动
```

### 2. 快速切换 provider / 账号
```bash
mms claude --provider my-openrouter   # 本次临时走 OpenRouter
mms codex --account work              # 本次临时切 Codex 工作号
```

### 3. 为外部工具导出环境变量
```bash
mms env my-preset --apply             # 写 .sh 文件，方便脚本复用
```

## Quick Start

```bash
mms config connect          # 首次配置向导
mms config migrate          # 从旧版 ccs 迁移
mms doctor --skip-claude-cli # 快速诊断 provider 健康度
mms --trace --preset coding  # 启动前看选择链路
```

## 核心设计

- **单次注入**：环境变量只在本次启动生效，不写 `.zshrc` / `.bashrc`
- **凭据隔离**：`config.toml` 只存元数据，`credentials.sh` 或系统 keychain 存真实 key
- **本地 override**：支持 `~/.config/mms/override.toml`，方便团队内共享默认配置
- **多账号隔离**：`claude` / `codex` / `gemini` 官方 OAuth 账号独立目录，互不污染

## 已支持的 CLI

| CLI | 说明 |
|-----|------|
| `claude` | Claude Code，可直连或走本地 bridge 挂 GPT/Gemini 模型 |
| `codex` | OpenAI Codex CLI |
| `qwen` | 通义千问 |
| `kimi` | Kimi |
| `gemini` | Gemini CLI |

![MMS TUI - Codex Tab](assets/mms-tui-codex.png)
*按 `←/→` 切换 CLI Tab，同一套 TUI 管理所有模型*

## 相关命令

```bash
mms config provider.list          # 查看已配置 provider
mms config provider.add qwen      # 一键添加 provider 模板
mms ls                            # 列出可用模型并测速
mms warm                          # 预热模型（减少首 token 延迟）
mms chat "解释递归"              # 多模型并排对话
mms discuss "设计 proto"         # 多模型摘要 + 综合裁定
mms session resume 1              # 恢复上一次的 chat session
```

## 文档

- [docs/ADAPTER_REGISTRY.md](docs/ADAPTER_REGISTRY.md) — 模型来源与别名策略

## License

[LICENSE](LICENSE)
