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

## Claude 回归诊断

> 如果你的核心诉求是“所有 provider 里的模型都能挂到 Claude 上使用”，优先跑这个诊断，不要只看 `/models`。

仓库内提供了一个独立诊断脚本：

```bash
scripts/doctor_claude_models.py
```

它不会改正常启动逻辑，专门用来回归这 3 件事：

- 所有 provider / OAuth 是否连得通
- 所有模型是否能正常最小 chat
- provider 里的模型是否能走 Claude 路径 `in & out`

最常用命令：

```bash
# 抽样测一个 provider，跳过真实 Claude CLI
HOME=/Users/xin python3 scripts/doctor_claude_models.py --provider anti --skip-claude-cli --max-models 5

# 全量测所有 provider 的协议层和模型 chat
HOME=/Users/xin python3 scripts/doctor_claude_models.py --skip-claude-cli

# 把 OAuth 账号状态也带上
HOME=/Users/xin python3 scripts/doctor_claude_models.py --include-oauth --skip-claude-cli

# 全量跑，包括真实 Claude CLI 冒烟
HOME=/Users/xin python3 scripts/doctor_claude_models.py
```

输出会分成 3 张表：

- `Provider / OAuth Connectivity`
- `Model Chat Availability`
- `Claude Compatibility`

常见状态包括：

- `ok`
- `auth_failed`
- `no_access`
- `agent_only`
- `model_missing`
- `endpoint_missing`
- `timeout`
- `upstream_unstable`

建议日常先跑：

```bash
HOME=/Users/xin python3 scripts/doctor_claude_models.py --skip-claude-cli
```

只有在要验真实 CLI 链路时，再去掉 `--skip-claude-cli`。

### Lessons Learned

- 不要只看 `/models`：`/models` 能返回，不代表模型真的能 chat，更不代表能挂到 Claude 上。
- 先抽样，再全量：日常回归优先 `--max-models 3`，先把坏掉的 provider 类型分出来，再跑全量。
- 先协议层，再 CLI 层：先用 `--skip-claude-cli` 跑协议兼容性，只有确认协议层健康后，再跑真实 Claude CLI。
- Claude 回归要看两张表：`Model Chat Availability` 看模型本身能不能聊，`Claude Compatibility` 看这批模型能不能真正走 Claude 路径。
- `agent_only` 不等于模型不可用：这通常表示它不能按普通 OpenAI chat 直连，但可能仍然能走 Claude-compatible / Coding Agent 路径。
- 诊断脚本必须独立：不要把这种高频网络探测塞进正常启动路径，否则会拖慢 TUI 和日常启动。

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
~/.config/mms/override.toml
~/.config/ccs/override.toml
```

加载顺序是先兼容读取 `~/.config/ccs/override.toml`，再读取 `~/.config/mms/override.toml`，后者优先级更高。

这个文件只应该存在于本地或私有分发流程中，不应直接提交到公共仓库。override 只在运行时叠加，不会反写到用户自己的 `config.toml`。

## Provider 命令

当前已经支持这些基础命令：

- `mms config file`：查看当前配置文件路径
- `mms config migrate`：把旧 `ccs` 配置和账号目录迁到 `mms` 路径
- `mms config validate`：校验当前配置
- `mms config get <dot.path>`：读取配置项
- `mms config set <dot.path> <value>`：修改配置项
- `mms config unset <dot.path>`：移除配置项
- `mms config provider.list`：查看当前模型源列表
- `mms config provider.default`：查看默认模型源
- `mms config provider.default <id>`：切换默认模型源
- `mms config provider.add [id]`：新增模型源元数据
- `mms config provider.edit <id>`：编辑模型源元数据
- `mms config provider.rename <old_id> <new_id> [new_name]`：重命名网关通道的内部标识和显示名
- `mms config provider.remove <id>`：删除模型源和本地凭据
- `mms config provider.credentials [id]`：编辑指定模型源的地址和 Key
- `mms config account.list`：查看当前账号档案列表
- `mms config account.add [claude|codex|gemini]`：新增官方账号档案
- `mms config account.edit <id>`：编辑账号档案
- `mms config account.rename <old_id> <new_id>`：重命名账号的文件夹名、显示名和目录
- `mms config account.remove <id>`：删除账号档案
- `mms config account.status [id]`：查看账号档案登录状态
- `mms config account.login <id>`：进入该账号档案对应的官方登录流程
- `mms config account.default <cli> <id>`：设置 `claude` / `codex` / `gemini` 默认账号
- `mms config stats`：查看本地启动统计
- `mms config api.edit`：编辑默认模型源的地址和凭据
- `mms config connect`：打开统一接入向导
- `mms config adapter.registry`：查看当前前 10 来源公司与默认 adapter 策略（别名：`source.registry`）

`provider.add` 现在也支持来源模板：

- `mms config provider.add qwen`
- `mms config provider.add kimi`
- `mms config provider.add zai-glm`
- `mms config provider.add bigmodel-glm`

现在也支持从主界面直接接入：

- 进入 `mms` 后按 `O`
- 选择 `添加网关通道`、`添加官方通道`、`管理现有通道` 或 `迁移配置到 mms`
- 接入填写页支持 `b` 返回、`q` 退出
- 完成后会自动回到主界面并刷新可用通道

通道管理里现在还支持模型管理：

- 进入 `管理现有通道` → 选择某个网关通道 → `模型管理`
- 可查看当前最终展示模型列表，并标注来源：`远端列表` / `内置回退` / `手工补充`
- 支持刷新远端模型列表、添加补充模型、隐藏模型、恢复默认补丁
- `模型列表接口路径` 也可以直接在管理页里改，不用再手写配置
- 现在也支持独立命令：`mms ls`
  - 执行后先选通道，再进入“模型列表 + 测速 + 模型管理”页
  - 也兼容 `mms models`
- 模型预热也有独立命令：`mms warm`
  - 执行后先选通道，再选择“最近使用模型 / 手动选择 / 全部模型”
  - 预热会发送真实请求，建议优先预热最近常用模型，不建议默认全量预热

模型测速会写到：

```text
~/.config/mms/speed-stats.json
```

这是 mms 自己的输出文件，外部工具如果要消费测速结果，应该来读这份文件。

现在测速按“通道作用域 + 模型”隔离：

- 同名模型如果来自不同 provider，不会再混到一条测速里
- 内部作用域 key 会优先按 endpoint 指纹生成，provider 只是改名时历史仍能接上
- 文件顶层仍保留按模型聚合的兼容视图；新消费者建议读作用域化数据

官方通道接入时有 3 个关键字段：

官方通道接入时现在只需要记两个名字：

- `显示名`：主界面里显示给你看的名字
- `文件夹名`：同时用作目录名和命令里的账号 ID，适合写成 `apple`、`work`、`personal`

对应的目录会自动生成在：

```text
~/.config/mms/accounts/<文件夹名>
```

如果你本地还在用旧版，MMS 仍会兼容读取 `~/.config/ccs/...` 下的旧配置，但新写入会优先落到 `~/.config/mms/...`。

管理现有通道时，可以直接：

- 一眼看到默认、状态、最近使用、启动次数
- 查看登录状态
- 查看本地启动统计
- 设为默认
- 重命名网关的显示名 / 内部标识，或重命名官方通道的 `文件夹名`
- 删除账号或网关

如果你之前已经在用旧版 `ccs`，建议执行一次：

```bash
./mms config migrate
```

它会把旧的 `~/.config/ccs` 配置、凭据、统计和账号目录整理到 `~/.config/mms`，并自动备份原目录。

目前 `官方真实用量 / 剩余额度` 还不支持统一查询；`mms config stats` 和管理页里展示的是本地启动统计。

## 多 OAuth 账号

MMS 现在开始支持 `claude` / `codex` / `gemini` 的多账号档案。

- `provider` 仍然表示模型源 / 网关
- `account` 表示官方 OAuth 账号档案
- 每个账号档案都绑定一个独立 `home_dir`
- `codex` 会通过隔离 `HOME` / `XDG_CONFIG_HOME` 实现登录态分离
- `codex` 账号模式下会继续隔离 `auth.json` / `config.toml`，但共享全局 `resume/history` 相关目录，避免切账号后本地会话列表消失
- `claude` / `gemini` 会保留真实系统用户上下文，只切换各自应用的本地状态目录，避免 macOS Keychain 和首次引导异常

当前优先级是先把“多绑、多选、不互相污染”做稳，所以首轮支持两种方式：

- `mms config account.default <cli> <id>`：配置默认账号
- `mms <cli> --account <id>`：本次启动临时切换账号
- `mms <cli> --provider <id>`：即使配置了默认账号，也临时强制走模型源

当前“使用入口”的规则是：

- 先检查登录态是否可用
- 启动时使用该账号的隔离目录
- 不复用 provider 的 `/v1/models` 列表
- `codex` / `claude` / `gemini` 走账号档案时，默认直接进入官方 CLI，模型选择交给官方 CLI 自己处理
- 来源选择不是只看当前 tab，而是按你已经选中的模型动态过滤
- 只会展示真正能承载当前模型的来源
- 同一个模型如果同时命中多个模型源和官方账号，TUI 会在选完模型后同屏展开“使用入口”列表
- `自定义` 现在会先按品牌分组，再选子模型，最后才按该子模型过滤可用入口
- 场景/预设里如果你选到 `Claude / GPT / Gemini` 这类官方品牌模型，仍然可以继续选择 `官方 / gateway`
- 在 `claude` 场景里，如果你选择了 `GPT` 或 `Gemini` 品牌并改走官方账号，MMS 会自动启一个本地 bridge：
  - 仍然启动 `claude`
  - 不会切去对应的官方 CLI
  - `claude` 请求会转到本地 bridge，再由 bridge 复用官方 OAuth 去请求上游
  - 启动第一刻的默认模型和底栏状态会直接显示你选中的真实模型名，不再先显示 `opus / sonnet` 这类 slot 占位名
- 这条 `官方桥接` 当前已支持：
  - `claude <- codex`
  - `claude <- gemini`
  主要解决“没有 provider，但想继续留在 Claude 里用 GPT / Gemini”的场景
- `gemini` 当前不占用主界面 tab，但支持：
  - 作为 `gemini-*` 模型的官方入口出现在来源列表
  - 直接使用 `mms gemini --account <id>` 启动
- 当前默认维护的来源公司/品牌和 adapter 策略见：
  - [docs/ADAPTER_REGISTRY.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ADAPTER_REGISTRY.md)
  - 后续新增 `official OAuth` 来源时，默认应同时评估并补上 `claude bridge`

## 本地统计

MMS 会把本地启动统计写到：

```text
~/.config/mms/usage.json
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
- [docs/MIGRATION_AND_WORKTREE.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/MIGRATION_AND_WORKTREE.md)
- [docs/ADAPTER_REGISTRY.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ADAPTER_REGISTRY.md)

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
- `glm`：不单独新增一个本地 CLI；当前按 provider 入口完成，主要在 `claude / codex / 自定义` 路径里消费 `glm-*`
- 它们不会再出现在内置场景列表里

## CLI 可见性

MMS 启动时会先读取已配置模型源，并用可拉取到的模型列表做一次轻量筛选。

- `qwen`：只有当模型源里明确探测到 `qwen*` 模型时才显示
- `kimi`：只有当模型源里明确探测到 `kimi*` 模型时才显示
- `claude` / `codex`：仍按模型源的 `supported_clis` 决定是否显示
- `glm`：当前通过 `zai-glm` / `bigmodel-glm` 这类 provider 模板接入，不单独占用主界面 tab

这层筛选会同时作用到顶部 CLI 入口和内置场景可见性，不会只隐藏 tab 留下失效入口。

## Codex 说明

`codex` 当前按它自己的 CLI 能力启动：使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`，再通过 `-m/--model` 指定单个模型。

它没有类似 Claude Code 的多 slot 默认模型环境变量机制，所以这里不会伪装成 `opus / sonnet / haiku` 那种多模型注入。

但在交互层里，`codex` 不会再被强制绑定到固定的两档场景预设；你仍然可以走全量模型选择路径。

`mms --export codex` 只导出直连 `Responses API` 所需的环境变量；如果目标模型需要本地 `Chat Completions bridge` 才能跑，仍应通过 `mms` 直接启动，而不是只靠 export。

通过 `mms` 直接启动 `codex` 时，`api_key` 路径会按模型能力分流：

- `gpt-*` / `o*` / `codex-*` 优先走本地 `Responses bridge`
- 其余模型走本地 `Chat Completions bridge`
- 如果上游 `Responses API` 返回错误、空体或已知不兼容，MMS 会自动回退到 `chat/completions`
- 如果 provider 的 `openai_base_url` 已经带 path 前缀（例如 `/openai`、`/api/paas/v4`），bridge 会直接拼接目标 endpoint，不再额外强补 `/v1`

当 `codex` 走 `--account <id>` 时，MMS 会继续隔离账号登录态和项目级配置，但把 `history.jsonl`、`sessions/`、`session_index.jsonl`、`shell_snapshots/` 这类 `resume/history` 数据切回共享层。这样切换不同 `codex` 账号后，本地 `resume` 列表仍然可见，不会因为账号目录分裂而“像丢历史”。

## `mms chat` / `mms discuss`

`mms chat` 和 `mms discuss` 都建立在同一套 provider / model 选择能力上：

- 两者都会先选择 provider（可用 `--provider` 临时指定）
- 两者都复用同一套模型多选 TUI
- 两者都走相同的流式请求与 SSE 解析逻辑
- 两者都适合拿来做“先选多个模型，再处理一个任务”的交互入口

差异是：

- `mms chat`：让多个模型并排实时输出，适合快速看不同模型的原始回答
- `mms discuss`：先让多个模型输出压缩摘要，再做综合裁定，适合设计讨论、方案对比、review

## `mms chat`

`mms chat` 用来把同一个 prompt 同时发给多个模型，并在终端里并排流式展示结果。流式结束后进入一个可交互的 action bar，支持续聊、切模型、收敛和交付。

```bash
mms chat
mms chat "解释 Python GIL"
mms chat --provider foo "为这个 CLI 设计配置结构"
```

**流式阶段**：模型数 ≤3 时横向并排，>3 时纵向堆叠。流式过程中：

- `←` / `→`：切换当前焦点列（Tab 模式）
- `Ctrl+C`：中断并进入结果页（已输出内容不丢失）

**action bar 键位**（流式结束后出现）：

| 键 | 动作 |
|----|------|
| `←` / `→` | 切换模型 |
| `↑` / `↓` | 滚动内容 |
| `Enter` | 选择此回答，继续提问 |
| `M` | 选择此回答 + 换模型继续 |
| `E` | 收敛：多模型综合裁定 |
| `H` | 交付：打印选中方案 + 可复用命令 |
| `P` | 并排查看所有模型输出 |
| `R` | 重新提问（清除上轮上下文） |
| `Q` | 退出 |

**输入框支持**：

- `←` / `→` 光标移动，`Ctrl+A/E` 行首/行尾，`Ctrl+K` 清到行尾
- `ESC`：第一次提示确认，第二次清空全部内容
- `Ctrl+V`：粘贴剪贴板图片（Pillow），插入为 `@image1`
- `Cmd+V`（iTerm2 bracketed paste）：图片优先；长文本（>60 字符）显示为 `[Pasted N chars]`，Backspace 整块删除
- `@/path/to/image.png`：手动引用图片路径

**session 机制**：续聊时携带已选方案的 brief + 最近 3 条决策记录，不携带完整历史 transcript，token 成本可控。

## `mms discuss`

`mms discuss` 用来让多个模型围绕同一个任务先独立压缩思考，再统一做一次对抗式综合，目标是比简单并排回答更有碰撞感，但又不引入多轮群聊带来的上下文膨胀。

默认是 **模式 B：摘要发散 + 对抗收敛**：

- 多个模型并行输出短 JSON 摘要
- 汇总表里快速对比核心方案、风险和下一步
- 再由一个 synthesizer 基于所有摘要生成最终裁定

如果加 `--cross`，会升级到 **模式 C：环形交叉审查 + 对抗收敛**：

- 每个模型会额外审查下一个模型的摘要
- 交叉阶段只看短摘要，不看完整长文，成本可控
- 最终综合会同时吸收摘要和交叉质疑

当前支持的用法：

```bash
mms discuss
mms discuss "重构 auth 模块"
mms discuss --cross "解释 Python GIL"
mms discuss --provider foo "为这个 CLI 设计配置结构"
```

交互流程是：

1. 选择 provider
2. 单选或多选 1-5 个模型
3. 输入任务（或直接从 CLI 读取）
4. 查看 Phase 1 摘要发散
5. 可选查看 Phase 2 环形交叉审查
6. 查看最终综合结论

## 现在能做什么

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
