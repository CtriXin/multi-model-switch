# Multi-Model Switch

Multi-Model Switch（MMS）是一个面向本地开发者的多模型 CLI launcher，用来统一启动 `claude`、`codex`、`qwen`、`kimi` 等 AI coding 工具。

这个仓库是 `MMS` 的新公开仓库。当前代码还处在从旧版 `ccs` 命名迁移到 `mms` 命名的过程中，所以你会在现有脚本和文件里看到一些旧名字。这是迁移阶段的兼容层，不代表长期品牌方向。

目前已经可以直接使用 `mms` 命令，`ccs` 继续作为兼容入口保留。

## v1 状态

当前 v1 的目标不是“一次性做完整框架”，而是先把基础能力稳定下来：

- 一个统一入口启动多个 AI coding CLI
- 保持默认“单次注入”的环境变量策略
- 允许后续演进到多 provider 配置
- 为团队/公司保留一个本地单文件 override 入口
- 把旧版 `ccs` 的逻辑迁到新的 GitHub 仓库里继续迭代

## 当前仓库说明

目前仓库里仍保留旧版文件名，例如：

- `mms`
- `ccs`
- `ccs_core.py`
- `ccs_launchers.py`
- `MMS Installer.command`
- `CCS Installer.command`

这是为了保证迁移期间不把现有使用方式一下子打断。当前已经补上：

- `mms` 新入口
- 安装脚本里的 `mms` / `ccs` 双命令链接

后续版本会继续补上：

- `mms` 配置目录
- 兼容迁移脚本
- 更清晰的 provider / credential 结构

## 设计原则

- 默认不把环境变量写进全局 shell
- 默认不把 API Key 明文写进公开配置文件
- 兼容个人使用和团队共享，但团队定制通过本地 override 文件完成
- 公开仓库不携带公司内部接入说明、公司网关地址或私有凭据

## 本地 override

v1 已支持本地单文件 override，用于团队内部下发共享默认配置，而不污染公开仓库。

支持的路径是：

```text
~/.config/ccs/override.toml
~/.config/mms/override.toml
```

加载顺序是先 `~/.config/ccs/override.toml`，再 `~/.config/mms/override.toml`，后者优先级更高。

这个文件只应该存在于本地或私有分发流程中，不应直接提交到公共仓库。override 只在运行时叠加，不会反写到用户自己的 `config.toml`。

## 现在能做什么

如果你只是想快速了解当前仓库，可以先看这些文件：

- [README.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/README.md)
- [install.sh](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/install.sh)
- [ccs_core.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_core.py)
- [ccs_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_launchers.py)

如果你要继续在这个仓库上开发，建议把它当成：

- 新品牌和新仓库已经切到 `MMS`
- 运行时仍处在兼容旧实现的过渡期
- 后续迭代会优先落地 `mms` 命名、provider 结构、凭据隔离和迁移逻辑

## License

本仓库使用根目录中的 [LICENSE](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/LICENSE)。
