# MMS v1.0.0 发布说明

## 🎉  highlights

- **统一 TUI 启动器**：一个 `mms` 命令管理 Claude、Codex、Qwen、Kimi、Gemini 等所有 AI 编程 CLI
- **零污染设计**：环境变量单次注入，不修改 `.zshrc` 或 `.bashrc`
- **快速切换**：一行命令临时切换 provider 或账号，无需记住繁琐的环境变量

## ✨ 新特性

### 核心功能
- **交互式 TUI**：方向键选择模型，回车启动，支持多 CLI Tab 切换
- **Provider 管理**：`mms config provider.add/list/edit/remove` 完整 CRUD
- **账号隔离**：OAuth 账号独立目录，`--account` 临时切换不串号
- **预设系统**：`mms --preset <name>` 一键启动常用配置
- **环境导出**：`mms env <preset> --apply` 生成独立 env 文件
- **诊断工具**：`mms doctor` 全面检测 provider 健康度和模型可用性
- **Trace 模式**：`mms --trace` 查看选择链路， debug 神器

### 聊天与讨论
- `mms chat`：多模型并排流式对话
- `mms discuss`：多模型摘要 + 综合裁定
- `mms session resume`：恢复历史会话

### 其他命令
- `mms ls` / `mms models`：查看并管理模型列表
- `mms warm`：预热模型减少首 token 延迟
- `mms cache`：管理模型缓存刷新策略
- `mms test`：最小闭环 smoke 测试

## 🚀 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash

# 首次配置
mms config connect

# 启动 TUI
mms

# 临时切换 provider
mms claude --provider openrouter

# 诊断
mms doctor --skip-claude-cli
```

## 📁 配置文件

- `~/.config/mms/config.toml`：模型源元数据
- `~/.config/mms/credentials.sh`：API Key 和 Base URL（自动加密）
- `~/.config/mms/override.toml`：本地/团队覆盖配置（不提交到仓库）

## 🛡️ 安全设计

- 凭据与配置分离，config 只存元数据
- 支持系统 keychain 存储敏感信息
- API Key 默认使用 AES-256-GCM 加密
- 本地 override 机制，团队共享不泄露密钥

## 📋 系统要求

- Python 3.9+
- macOS / Linux（Windows 通过 WSL）
- 已安装目标 CLI（claude、codex、qwen-cli、kimi-cli 等）

## ⚠️ 已知限制

- 首次启动需要配置至少一个 provider
- 部分国产模型需通过 gateway bridge 使用
- Windows 原生支持仍在开发中

## 🔮 路线图

- [ ] Phase 2：负载模式（自动按任务选模型）
- [ ] GUI 配置界面
- [ ] 插件系统
- [ ] Windows 原生支持

## 🤝 贡献

欢迎 Issue 和 PR！详见 [CONTRIBUTING.md](../CONTRIBUTING.md)

## 📄 License

MIT © 2026 CtriXin
