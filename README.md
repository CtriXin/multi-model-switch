# Multi-Model Switch (MMS)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 一个让 `claude`、`codex` 等 AI 编程 CLI 统一接入的本地 launcher。

![MMS - Before vs After](assets/cover.svg)

**MMS** 是一个面向本地开发者的多模型 CLI 启动器。它让你用**一个入口**管理所有 AI 编程工具，告别繁琐的环境变量配置。

---

## ✨ 核心特性

- 🎯 **统一 TUI**：方向键选模型，回车启动，无需记忆命令
- ⚡ **快速切换**：一行命令临时切换 provider 或账号
- 🔧 **环境导出**：一键生成 env 文件供脚本使用
- 🩺 **健康诊断**：内置 `doctor` 命令检测所有 provider 状态
- 🔍 **链路追踪**：`--trace` 模式查看选择逻辑
- 🏠 **账号隔离**：多 OAuth 账号独立目录，互不串号
- 📝 **预设系统**：保存常用配置，一键启动

---

## 📦 安装

### 一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

### 手动安装

```bash
git clone https://github.com/CtriXin/multi-model-switch.git
cd multi-model-switch
pip install -r requirements.txt
ln -s $(pwd)/mms /usr/local/bin/mms
```

---

## 🚀 快速开始

### 1. 首次配置

```bash
mms config connect    # 进入配置向导，添加第一个 provider
```

### 2. 启动 TUI

```bash
mms                   # 进入交互界面，选择模型启动
```

### 3. 快速启动（免交互）

```bash
mms --preset coding                    # 使用预设启动
mms claude --provider openrouter       # 临时指定 provider
mms codex --account work               # 临时切换账号
```

---

## 📸 界面预览

### Claude Tab
![Claude Tab](assets/mms-tui.png)

### Codex Tab
![Codex Tab](assets/mms-tui-codex.png)

### 启动确认页
![Launch Confirm](assets/mms-launch-confirm.png)
*启动前确认配置：模型、Provider、模式一目了然*

**操作说明**：
- `←/→`：切换 CLI Tab（claude / codex / qwen / kimi）
- `↑/↓`：选择模型族群 / 模型
- `Enter`：确认启动
- `P`：从 Provider 角度浏览
- `O`：接入新通道
- `Q/Esc`：退出

---

## 🎯 使用场景

### 场景 1：日常开发

每天需要切换不同模型对比效果：

```bash
mms                              # 进入 TUI，方向键选择
# 或者直接用预设
mms --preset sonnet-for-coding   # 启动 Claude Sonnet
mms --preset gpt-for-review      # 启动 GPT 做 Code Review
```

### 场景 2：多账号管理

公司和个人的 AI 账号需要分开：

```bash
# 配置多个账号
mms config account.add claude    # 添加个人号
mms config account.add claude    # 添加工作号

# 启动时切换
mms claude --account personal    # 个人项目
mms claude --account work        # 工作项目
```

### 场景 3：团队协作

团队共享配置，但密钥各自保管：

```bash
# 团队 leader 创建 override.toml
# 包含推荐的 provider 配置（不含密钥）
# 分发给团队成员

# 成员只需要填自己的 API Key
mms config provider.credentials my-provider
```

### 场景 4：CI/CD 集成

为脚本导出环境变量：

```bash
# 生成独立 env 文件
mms env my-preset --apply

# 在脚本中使用
source ~/.config/mms/env/my-preset.sh
claude
```

### 场景 5：问题诊断

Provider 连不上或模型异常：

```bash
# 快速诊断所有 provider
mms doctor --skip-claude-cli

# 测试特定 provider
mms test --provider openrouter --cli claude

# 查看详细选择链路
mms --trace --preset coding
```

---

## 🛠️ 完整命令列表

### 配置管理

```bash
mms config connect                    # 统一接入向导
mms config migrate                    # 从旧版 ccs 迁移
mms config file                       # 查看配置文件路径

mms config provider.list              # 查看 provider 列表
mms config provider.add [template]    # 添加 provider（支持模板）
mms config provider.edit <id>         # 编辑 provider
mms config provider.remove <id>       # 删除 provider
mms config provider.credentials [id]  # 编辑密钥

mms config account.add <cli>          # 添加 OAuth 账号
mms config account.login <id>         # 登录账号
mms config account.status [id]        # 查看登录状态
```

### 模型管理

```bash
mms ls                                # 列出所有模型（支持测速）
mms warm                              # 预热模型
mms cache                             # 查看/调整缓存策略
```

### 诊断工具

```bash
mms doctor                            # 全面诊断
mms doctor --provider <id>            # 诊断指定 provider
mms doctor --skip-claude-cli          # 跳过 CLI 层，只测协议
mms test --provider <id> --cli <name> # 最小闭环测试
```

### 聊天与讨论

```bash
mms chat "解释递归"                   # 多模型并排对话
mms discuss "设计 proto"              # 多模型摘要 + 综合裁定
mms session resume <id>               # 恢复会话
```

---

## 🏗️ 架构设计

### 核心原则

1. **单次注入**：环境变量只在本次启动生效，不写全局 shell 配置
2. **凭据隔离**：`config.toml` 只存元数据，密钥存 `credentials.sh` 或系统 keychain
3. **本地覆盖**：支持 `~/.config/mms/override.toml`，团队共享不泄露密钥
4. **账号隔离**：每个 OAuth 账号独立目录，登录态互不干扰

### 数据流

```
用户输入 → mms → 解析配置 → 选择 provider/account →
注入环境变量 → 启动目标 CLI → 清理环境
```

### 支持的 CLI

| CLI | 协议 | 特性 |
|-----|------|------|
| `claude` | Anthropic Messages | 支持 bridge 模式挂 GPT/Gemini |
| `codex` | OpenAI Responses | 自动降级到 Chat Completions |
| `qwen` | OpenAI compatible | 直接启动 |
| `kimi` | OpenAI compatible | 默认 kimi-k2.5 |
| `gemini` | Google AI | OAuth 账号支持 |

---

## 📁 配置文件

### 目录结构

```
~/.config/mms/
├── config.toml          # 模型源元数据
├── credentials.sh       # API Key（加密存储）
├── override.toml        # 本地/团队覆盖配置
├── usage.json           # 本地启动统计
├── speed-stats.json     # 模型测速结果
└── accounts/            # OAuth 账号目录
    ├── personal/
    └── work/
```

### config.toml 示例

```toml
[provider]
default = "openrouter"

[[providers]]
id = "openrouter"
name = "OpenRouter"
protocols = ["anthropic_messages", "openai_chat_completions"]
supported_clis = ["claude", "codex"]

[[accounts]]
id = "personal"
cli = "claude"
home_dir = "~/.config/mms/accounts/personal"
```

---

## 🚧 已知限制

- 首次启动需要配置至少一个 provider
- 部分国产模型需通过 gateway bridge 使用
- Windows 原生支持正在开发中（目前可用 WSL）

---

## 🗺️ 路线图

- [ ] **Phase 2**：负载模式（自动按任务复杂度选模型）
- [ ] GUI 配置界面
- [ ] 插件系统
- [ ] Windows 原生支持
- [ ] 云端配置同步

---

## 🤝 贡献

欢迎 Issue 和 PR！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing`)
5. 创建 Pull Request

---

## 📄 License

MIT © 2026 [CtriXin](https://github.com/CtriXin)

---

## 🙏 致谢

感谢所有测试和反馈的用户。特别感谢以下开源项目：
- [Claude Code](https://github.com/anthropics/claude-code)
- [Codex CLI](https://github.com/openai/codex)
- [Rich](https://github.com/Textualize/rich) - Python TUI 库
