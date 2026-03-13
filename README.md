# Multi-Model Switch

Multi-Model Switch（MMS）是一个面向本地开发者的多模型 CLI launcher，用来统一启动 `claude`、`codex`、`qwen`、`kimi` 等 AI coding 工具。

这个仓库是 `MMS` 的新公开仓库。当前代码还处在从旧版 `ccs` 命名迁移到 `mms` 命名的过程中，所以你会在现有脚本和文件里看到一些旧名字。这是迁移阶段的兼容层，不代表长期品牌方向。

目前已经可以直接使用 `mms` 命令，`ccs` 继续作为兼容入口保留。

## v1 状态

当前 v1 的目标不是“一次性做完整框架”，而是先把基础能力稳定下来：

- 一个统一入口启动多个 AI coding CLI
- 保持默认“单次注入”的环境变量策略
- 已切到最小可用的 `providers` 配置结构
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
- `providers` 配置骨架，兼容旧的单网关用法
- 中文模型模式：`全部模型` / `推荐模型`
- 模型校验失败时的“发现后处理”交互层
- `qwen` / `kimi` 不再进入场景系统，改成直接入口

后续版本会继续补上：

- `mms` 配置目录
- 兼容迁移脚本
- 更完整的模型源选择与多平台管理

## 设计原则

- 默认不把环境变量写进全局 shell
- 默认不把 API Key 明文写进公开配置文件
- 模型源元数据和模型源凭据物理分离
- 兼容个人使用和团队共享，但团队定制通过本地 override 文件完成
- 公开仓库不携带公司内部接入说明、公司网关地址或私有凭据

## Provider 结构

当前配置已经从旧的单一 `[api]` 演进到 `[[providers]]`。

- `config.toml` 保存模型源元数据，例如 `id`、`name`、`protocols`、`supported_clis`
- `credentials.sh` 继续保存真实 `base_url` 和 `api_key`
- 默认模型源仍兼容旧的 `CCS_API_BASE_URL` / `CCS_API_KEY`
- 一个模型源可以同时声明多种协议，例如：
  - `anthropic_messages`
  - `openai_chat_completions`

这样做是为了兼容一种很常见的现实情况：同一个网关地址同时暴露 Anthropic 和 OpenAI 两种协议。

## 中文模式

用户模式已经改成中文配置：

- `全部模型`：展示全部可用模型
- `推荐模型`：只展示推荐列表里的模型

旧配置里的 `dev` / `ops` 仍会自动兼容，并在读取时迁移到中文模式。

## 本地 override

v1 已支持本地单文件 override，用于团队内部下发共享默认配置，而不污染公开仓库。

支持的路径是：

```text
~/.config/ccs/override.toml
~/.config/mms/override.toml
```

加载顺序是先 `~/.config/ccs/override.toml`，再 `~/.config/mms/override.toml`，后者优先级更高。

这个文件只应该存在于本地或私有分发流程中，不应直接提交到公共仓库。override 只在运行时叠加，不会反写到用户自己的 `config.toml`。

## Provider 命令

当前已经支持这些基础命令：

- `mms config file`：查看当前配置文件路径
- `mms config validate`：校验当前配置
- `mms config get <dot.path>`：读取配置项
- `mms config set <dot.path> <value>`：修改配置项
- `mms config unset <dot.path>`：移除配置项
- `mms config provider.list`：查看当前模型源列表
- `mms config provider.default`：查看默认模型源
- `mms config provider.default <id>`：切换默认模型源
- `mms config provider.add [id]`：新增模型源元数据
- `mms config provider.edit <id>`：编辑模型源元数据
- `mms config provider.remove <id>`：删除模型源和本地凭据
- `mms config provider.credentials [id]`：编辑指定模型源的地址和 Key
- `mms config account.list`：查看当前账号档案列表
- `mms config account.add [claude|codex]`：新增官方账号档案
- `mms config account.edit <id>`：编辑账号档案
- `mms config account.remove <id>`：删除账号档案
- `mms config account.status [id]`：查看账号档案登录状态
- `mms config account.login <id>`：进入该账号档案对应的官方登录流程
- `mms config account.default <cli> <id>`：设置 `claude` / `codex` 默认账号
- `mms config stats`：查看本地启动统计
- `mms config api.edit`：编辑默认模型源的地址和凭据
- `mms config connect`：打开统一接入向导

现在也支持从主界面直接接入：

- 进入 `mms` 后按 `O`
- 选择 `添加网关通道`、`添加官方通道` 或 `管理现有通道`
- 完成后会自动回到主界面并刷新可用通道

官方通道接入时有 3 个关键字段：

- `账号备注`：主界面里显示给你看的名字
- `账号标识`：内部区分用，适合写成 `apple`、`work`、`personal`
- `登录目录`：这个账号独立保存官方登录态的位置

管理现有通道时，可以直接：

- 一眼看到默认、状态、最近使用、启动次数
- 查看登录状态
- 查看本地启动统计
- 设为默认
- 删除账号或网关

目前 `官方真实用量 / 剩余额度` 还不支持统一查询；`mms config stats` 和管理页里展示的是本地启动统计。

## 多 OAuth 账号

MMS 现在开始支持 `claude` / `codex` 的多账号档案。

- `provider` 仍然表示模型源 / 网关
- `account` 表示官方 OAuth 账号档案
- 每个账号档案都绑定一个独立 `home_dir`
- 启动时会把 `HOME` / `XDG_CONFIG_HOME` 切到对应目录，实现不同账号的登录态隔离

当前优先级是先把“多绑、多选、不互相污染”做稳，所以首轮支持两种方式：

- `mms config account.default <cli> <id>`：配置默认账号
- `mms <cli> --account <id>`：本次启动临时切换账号
- `mms <cli> --provider <id>`：即使配置了默认账号，也临时强制走模型源

当前执行通道的规则是：

- 先检查登录态是否可用
- 启动时使用该账号的隔离目录
- 不复用 provider 的 `/v1/models` 列表
- `codex` / `claude` 走账号档案时，默认直接进入官方 CLI，模型选择交给官方 CLI 自己处理
- 来源选择不是只看当前 tab，而是按你已经选中的模型动态过滤
- 只会展示真正能承载当前模型的来源
- 同一个模型如果同时命中多个模型源和官方账号，TUI 会在选完模型后同屏展开“执行通道”列表

## 元数据与本地统计

`provider` / `account` 现在都支持这些手工元数据：

- `priority`
- `cost_level`
- `daily_budget`
- `note`

同时，MMS 会把本地启动统计写到：

```text
~/.config/ccs/usage.json
```

当前记录的是软统计：

- 启动次数
- 最近使用时间
- 最近模型

它们适合做排序和推荐参考，但**不等于真实余额或官方剩余额度**。

更完整的后续计划见：

- [docs/USAGE_AND_QUOTA_PLAN.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/USAGE_AND_QUOTA_PLAN.md)

最小试验：

```bash
./mms config account.add claude
./mms config account.login <id>
./mms config account.status <id>
./mms config account.default claude <id>
./mms claude --account <id>
```

更完整的落地说明和四象限 todo 见：

- [docs/OAUTH_ACCOUNTS.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/OAUTH_ACCOUNTS.md)

## 失败恢复交互

当默认模型源的模型校验失败时，MMS 会进入一个“发现后处理”交互层。

- TUI 环境下可用 `Space` 勾选处理动作，`Enter` 执行
- 当前支持的动作包括：
  - 重新输入地址和 Key
  - 切换到其他已配置模型源
  - 查看详细错误
  - 跳过校验并继续

“跳过校验并继续”只影响当前启动流程，不会自动改写你的配置；但在这次运行里，模型浏览列表会暂时不可用。

## Qwen / Kimi 入口

`qwen` 和 `kimi` 现在不再使用“常规任务 / 中文主力”这类场景交互。

- `qwen`：直接进入当前可用模型源的全部 `qwen*` 模型列表
- `kimi`：直接使用默认模型 `kimi-k2.5`
- 它们不会再出现在内置场景列表里

## CLI 可见性

MMS 启动时会先读取已配置模型源，并用可拉取到的模型列表做一次轻量筛选。

- `qwen`：只有当模型源里明确探测到 `qwen*` 模型时才显示
- `kimi`：只有当模型源里明确探测到 `kimi*` 模型时才显示
- `claude` / `codex`：仍按模型源的 `supported_clis` 决定是否显示

这层筛选会同时作用到顶部 CLI 入口和内置场景可见性，不会只隐藏 tab 留下失效入口。

## Codex 说明

`codex` 当前按它自己的 CLI 能力启动：使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`，再通过 `-m/--model` 指定单个模型。

它没有类似 Claude Code 的多 slot 默认模型环境变量机制，所以这里不会伪装成 `opus / sonnet / haiku` 那种多模型注入。

但在交互层里，`codex` 不会再被强制绑定到固定的两档场景预设；你仍然可以走全量模型选择路径。

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
