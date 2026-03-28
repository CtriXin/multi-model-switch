# MMS 多 OAuth 账号落地说明

## 当前已落地

- 新增 `accounts` / `account.defaults` 配置层，用来管理官方 CLI 的账号档案
- 当前覆盖 `claude`、`codex` 和 `gemini`
- 支持的命令：
  - `mms config migrate`
  - `mms config account.list`
  - `mms config account.add`
  - `mms config account.edit <id>`
  - `mms config account.rename <old_id> <new_id>`
  - `mms config account.remove <id>`
  - `mms config account.status [id]`
  - `mms config account.login <id>`
  - `mms config account.default <cli> <id>`
- 启动时支持 `--account <id>` 临时切换账号档案
- 不托管 OAuth token 明文；账号隔离依赖每个账号独立的 `home_dir`
- 已支持统一接入向导：
  - `mms config connect`
  - 主界面按 `O`
  - 可继续进入“管理现有通道”
  - 也可直接选择“迁移配置到 mms”
  - 接入填写页支持 `b` 返回、`q` 退出
- 官方通道接入时只需要两个核心字段：
  - `显示名`：主界面里看到的名字
  - `文件夹名`：同时用作目录名和命令里的账号 ID
- 新账号默认会写到 `~/.config/mms/accounts/<文件夹名>`
- 旧版 `~/.config/ccs/accounts/...` 仍可兼容读取

## 运行模型

- `provider` 继续表示网关/模型源，走 `base_url + api_key`
- `account` 表示官方账号档案，走本机官方 CLI 登录态
- 另外增加了一条特殊运行路径：`官方桥接`
  - 当前支持：
    - `codex OAuth -> claude`
    - `gemini OAuth -> claude`
  - 目标是让你在 `claude` 里继续工作，但模型能力来自官方账号
- 对用户来说，两者都会进入同一个“使用入口”选择层
- `claude` / `codex` / `gemini` 启动时：
  - 指定了 `--account` 就优先走账号档案
  - 没指定但配置了默认账号时，走默认账号
  - 否则回退到原有模型源路径
- `OAuth account` 路径当前不复用 provider 的 `/v1/models` 列表
- `codex --account <id>` / `claude --account <id>` / `gemini --account <id>` 默认直接进入官方 CLI，模型选择交给官方 CLI 自己处理
- 来源选择会按“当前已选模型”动态过滤，不再只看当前 CLI
- 如果某个模型同时命中多个来源，MMS 的 TUI 会在选完模型后同屏展开使用入口列表
- `自定义` 模式会先展示品牌，再进入子模型，最后按选中的模型过滤来源
- 场景/预设里如果选到官方品牌模型，会继续保留 `官方 / gateway` 的入口选择
- 如果你在 `claude` 场景里选到 `GPT` 或 `Gemini` 品牌，再选择某个官方账号，MMS 不会切去对应官方 CLI
  - 它会启动 `claude`
  - 同时在本地临时起一个 Anthropic-compatible bridge
  - `claude` 的请求会被转给 bridge，bridge 再复用对应官方 OAuth 去访问上游
- 这条桥接路径已经做过最小真实联调：
  - `alex-codex` 可返回正常文本结果
  - 也能透传 function call / tool call 事件
- `gemini-alex-father` 可通过 `CodeAssistServer` 路径返回正常文本结果
- `apple-codex` 当前真实上游会返回 `usage_limit_reached`，不适合作桥接联调账号

## 账号隔离方式

- 每个账号档案都绑定一个独立 `home_dir`
- `codex` 启动时会为当前进程注入：
  - `HOME=<home_dir>`
  - `XDG_CONFIG_HOME=<home_dir>/.config`
- `codex` / `claude` 的隔离 session 会额外 symlink 真实用户的：
  - `~/.ssh`
  - `~/.gitconfig`
  - `~/.gitignore_global`
  这样在独立 `HOME` 里跑 Git / SSH 时，不会因为找不到用户级配置而异常
- `gemini` 启动时会注入：
  - `GEMINI_CLI_HOME=<home_dir>`
  - 保留真实系统 `HOME`，让 macOS Keychain 和 Gemini 自己的重启流程保持正常
- `claude` 启动时会使用 per-session 隔离 `HOME`，并把账号态与项目级 session 历史拆开托管
- 这样可以把不同 Plan / 不同官方登录态分开，不互相覆盖，同时保留 Git/SSH 与 macOS Keychain 等系统级依赖
- 官方通道的 `文件夹名` 也可以在“管理现有通道”里直接重命名，不必记 `config account.rename`

## 最小试验

### 1. 新建账号档案

```bash
./mms config account.add claude
./mms config account.list
```

也可以直接：

```bash
./mms config connect
```

然后选：

- `添加官方通道`
- 或 `管理现有通道`

### 2. 进入官方登录

```bash
./mms config account.login <id>
./mms config account.status <id>
```

### 3. 设为默认账号

```bash
./mms config account.default claude <id>
./mms config account.default
```

### 4. 临时切换启动

```bash
./mms claude --account <id>
./mms codex --account <id>
./mms gemini --account <id>
./mms claude --provider default
```

### 5. 交互式选择使用入口

当某个 CLI 同时存在：

- 一个或多个账号档案
- 以及一个可用模型源

直接执行：

```bash
./mms codex
```

或

```bash
./mms claude
```

会在当前 TUI 里展开“使用入口”列表，让你决定这次走：

- 某个账号档案
- 还是模型源

如果你先选中了具体模型，例如 `gpt-5.4`，这里不会再把所有来源一股脑列出来，而是只显示真正能承载 `gpt-5.4` 的来源。

## 四象限 Todo

| 象限 | 项目 | 状态 |
| --- | --- | --- |
| 高价值 / 低成本 | `account` 配置层、默认账号、`--account` 临时切换 | 已完成 |
| 高价值 / 高成本 | 启动前交互式账号选择、按额度/权重自动切换 | 待做 |
| 低价值 / 低成本 | 账号列表里显示更丰富的登录摘要、示例配置片段 | 待做 |
| 低价值 / 高成本 | 把 `qwen` / `kimi` / `glm` / `minimax` 也抽进统一 OAuth 账号体系 | 暂不做 |

## 当前边界

- 还没做“启动前交互选账号”，首轮先用 `account.default` + `--account`
- 还没做自动配额切换
- 已经有统一接入向导，但真正的登录动作仍然调用官方 CLI 自己的登录命令
- Claude 官方通道启动前会自动同步主账号的本地 onboarding / 偏好状态，避免隔离目录反复出现首次欢迎页
- Gemini 官方通道会复用真实系统用户环境，并把账号专属状态写到 `<home_dir>/.gemini`，避免 Keychain 弹窗和登录后重启卡住
- OAuth 账号当前只做两类检查：
  - 登录态是否可用
  - 官方 CLI 是否能正常启动
- `官方桥接` 当前覆盖：
  - `claude <- codex`
  - `claude <- gemini`
  - 还没有泛化成 `claude <- 其他官方 CLI` 或反向的 `codex <- claude`
  - 如果你明确选了某个具体模型的 `自定义` 路径，MMS 仍会优先把它当成“provider-only” 模型，不把所有官方账号一股脑混进来
- 当前不做 provider 式 model list；后续如果某个官方 CLI 能稳定枚举模型，再单独加
- 当前不支持统一显示官方真实用量 / 剩余额度；管理页和 `mms config stats` 展示的是本地启动统计
- `gemini` 当前作为官方账号源接入，不单独占用主界面 tab；它会在你选中 `gemini-*` 模型后，出现在“使用入口”列表里
- `qwen` / `kimi` 继续保持当前直达路径，不进入这个抽象层
- `glm` 当前按 provider 模板接入，不单独新增本地 CLI
- 后续如果新增新的 `official OAuth` adapter，默认规则是：
  - 先补原生账号接入
  - 只要原生路径稳定，再默认评估并补上 `claude bridge`
  - 如果没有稳定 CLI / SDK / backend，就继续按 `provider_api` 落地

## Q&A

### Q: GPT-on-Claude (Claude 里用 GPT-5) 为什么每次对话都发送全量历史，不能增量？

**A:** 这是上游 CRS (Claude Relay Service) 的限制，不是 MMS 的问题。

**背景**
- MMS 的 `privateopenai` provider 指向 CRS (`crs.adsconflux.xyz/openai`)
- CRS 的 OpenAI 账户是 **ChatGPT OAuth** 类型，走 `chatgpt.com/backend-api/codex/responses`
- 不是标准 OpenAI API (`api.openai.com/v1/responses`)

**关键差异**

| 特性 | ChatGPT OAuth (CRS) | 标准 OpenAI API |
|------|---------------------|-----------------|
| 上游 URL | `chatgpt.com/backend-api/codex/responses` | `api.openai.com/v1/responses` |
| `previous_response_id` | ❌ 不支持 | ✅ 支持 |
| 存储 Response | ❌ 不存储 | ✅ 存储 |
| Prompt Cache 可见性 | ❌ `cached_tokens: 0` | ✅ 正常统计 |
| Stream | ✅ 支持 | ✅ 支持 |
| `/responses/compact` | ✅ 支持但不存 | N/A |

**结论**
- 使用 CRS 的 OpenAI 账户时，GPT-on-Claude 只能以全量 history 模式工作
- 如需增量优化（`previous_response_id`），需要标准 OpenAI API key
- MMS 代码已移除 `previous_response_id` 参数（commit `fb30485`），避免发送到不支持的 endpoint

**参考**
- MindKeeper Recipe: `crs-openai-oauth-limitation`
- 恢复口令: `dst-20260327-u0crvi`

---

更完整的来源公司/adapter 基线见：

- [docs/ADAPTER_REGISTRY.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ADAPTER_REGISTRY.md)
