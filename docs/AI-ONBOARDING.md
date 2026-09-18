# 给 AI 的项目交接

你被叫来在 MMS 上干活。这份文档是你的第一站：读完它，你应该知道这是什么产品、代码在哪、门禁怎么跑、哪些地方碰了会出事、以及这个项目已经踩过哪些坑（不要再踩一遍）。

读完这份再去读规则文件（`AGENT.md`、`docs/AGENT_GUARDRAILS.md`）。规则告诉你**不能做什么**，这份告诉你**这是什么**。

最后核对：2026-09-18。T9a 合并后的 `main` 使用 4.23.8；`dev` 当前为 5.1.10。后续状态请以各分支版本文件和 Release 为准。

---

## 一、30 秒版

MMS（Multi-Model Switch）是一个**跑在自己电脑上**的 AI coding 运行时管理器。它不是聊天客户端，也不是云服务。

三层，从下往上：

| 层 | 是什么 | 入口 |
|---|---|---|
| **MMS launcher** | 在启动 `claude` / `codex` / `opencode` / `pi` / `agy` 之前，把该想清楚的事想清楚：用哪个模型、走哪个通道、哪个账号、注入哪些能力包、用哪个隔离 HOME | `mms`（TUI）、`mms claude`、`mms codex` … |
| **MMS Pilot** | launcher 的本地 Web 客户端。开会话、加通道、拉模型、改能力、管工作文件夹都在这里。会话仍然由本机 Pi 执行，浏览器只是交互面 | `mms web --open` |
| **MMS Bot**（5.x 才有） | Pilot 的执行层升级。你交代一个目标，一个有身份、有记忆、能定时唤醒、能分发协作、能找多家模型评审的执行者去完成 | Pilot 里的 Bot 工作台 |

一句话区分 Pilot 会话和 Bot：**Pilot 是「我现在自己做这件事」，Bot 是「我交代目标，你去做完回报我」。**

技术形态：Python 后端（HTTP 服务 + launcher）+ React/TS 前端（构建产物签入仓库）+ 本机 Pi 作为 harness。没有服务端，没有账号系统，只监听 `127.0.0.1`（可显式打开局域网访问）。

---

## 二、两条发布线：先搞清楚你在哪条线上

2026-09-16 起，`main` 和 `dev` 是**两条长期并行的发布线**，不是「稳定分支和开发分支」。

| 线 | 分支 | 版本 | 安装 | 内容 |
|---|---|---|---|---|
| 稳定线 | `main` | 4.23.x | `--channel stable`（默认） | 已经坐稳的功能，只收修复和验证过的能力 |
| 预览线 | `dev` | 5.1.x | `--channel dev` | 稳定能力、Bot 工作台与其他预览改动 |
| Canary | `canary` | 停更 | `--channel canary` | 2026-06 起停更的旧实验线，不要用它承载任何东西 |

稳定线的修复应同步到 `dev`；预览线中已验证的能力可以进入 `main`。同步需要实际合并，目前没有自动同步保证。不要把 `dev` 当作 `main` 的实时超集，应逐项核对 Git 历史和 Release。

你动手前必须回答：**这个改动属于哪条线？**

- 是修 bug，或是 4.x 用户也该拿到的能力 → base `main`，合并后再进 `dev`。
- 只跟 Bot 工作台有关（`mms_web/bot_*.py`、`bots.py`、`browser_provider.py`，以及前端的 Bot 界面）→ base `dev`。
- 不确定 → 默认 `main`。往 `dev` 补容易，从 `dev` 往 `main` 摘就难。

同一个公开安装目录 `~/.mms` 一次只安装一条线。换线要重跑安装器带对应 `--channel`；配置、通道和会话历史仍在同一个 config root。隔离 worktree 可以共存，但需留意共享配置与服务端口。

**5.x 装上以后，光在 Pilot 里把通道选回 stable 不会降回 4.x。** 原因在 `mms_web/updates.py`：`available = remote > current`，`4.23.x < 5.1.x`，所以 4.x 永远不会被当成「可用更新」。降级必须重跑安装器带 `--channel stable`。这是设计，不是 bug——但**任何文案都不许说"随时可逆"**，历史上说过，害人卡住过。

### 版本号规则（owner 2026-09-17 定）

**一个合并的 PR = 一个 patch 版本。** 这样看版本号就知道做了什么。纯文档包不 bump。

机制上有个坑：如果每个 PR 作者自己改版本文件，N 个在飞的 PR 就会在 `lib/mms_version.py` 上 N 路冲突。所以**作者不碰版本文件，合并方在合并时盖版本号**，release note 和 bump 放在一个单独的 commit 里（别混进对方的改动，保住对方的 authorship）。

版本一致性由 `tests/test_mms_release_version.py` 守着，它要求这些地方同时对齐：`lib/mms_version.py`、根 `package.json`、`apps/mms-web/package.json`、`apps/mms-web/package-lock.json`（`version` 和 `packages[""].version` 两处）、`mms_web_static/build.json` 的 `version` 与每个文件的 sha256，以及 `docs/mms-web/RELEASE-v<版本>.md` 必须存在。

发版仍需手动执行；CI 包含 `.github/workflows/digger.yml` 和 Windows acceptance 等验证，不会自动创建 Release。手动流程：合并 PR → bump + release note 的 commit → `git push origin HEAD:<branch>` → `git tag -a` → `git push origin <tag>` → `gh release create <tag> --verify-tag [--latest|--prerelease] --notes-file docs/mms-web/RELEASE-vX.md`。

---

## 三、代码地图

### 运行时模块 `lib/`（79 个 Python 模块）

T9a 将运行时模块从根目录迁入 `lib/`。入口脚本优先把 `lib/` 加入 `sys.path`；Python import 名称保持不变。缺少 `lib/` 的旧安装需要重新运行安装器，不能靠根目录旧模块兜底。启动链的责任划分：

```
mms（入口脚本）
  └─ lib/mms_tui.py          选择界面：CLI / profile / 模型 / 使用入口
      └─ lib/mms_core.py     真值中心：模型解析、provider/account 优先级、runtime 决策、auth_mode
          └─ lib/mms_launchers.py   拼启动参数和环境变量，真正 exec 出去
              └─ lib/mms_bridge.py  协议转换：claude←codex、codex responses→chat completions
```

其它常打交道的：

| 文件 | 管什么 |
|---|---|
| `lib/mms_registry*.py` | Registry v2：配置的预览 DB、审阅、发布 |
| `lib/mms_provider_profiles.py` | provider 侧的 curated 能力数据（vision、上下文、协议） |
| `lib/mms_capability_resolver.py` | 能力解析：某个模型到底支持什么 |
| `lib/mms_pi_support.py` | Pi harness 支持，含 `_pi_model_input_types()`（识图能力真值链） |
| `lib/mms_session*.py` | 会话目录、索引、resume、能力包注入 |
| `lib/mms_account_state.py` | 账号隔离，HOME/XDG 边界 |
| `lib/mms_version.py` | 唯一的版本号真值 |
| `lib/mmc_*.py` | 旧 MMC proxy 相关，基本是维护面 |

### Pilot 后端 `mms_web/`（约 45 个模块，4.x）

| 文件 | 管什么 |
|---|---|
| `server.py` | HTTP 服务、路由分发、`mutation_lock`、监听器集合、远程访问开关 |
| `service.py` | 进程生命周期、`source_root()` |
| `sessions.py` / `session_actions.py` | 会话状态、持久化、runtime view |
| `runtime.py` | `private_json()` —— **Pilot 所有持久化的唯一入口** |
| `updates.py` / `update_install.py` / `update_*.py` | 检查更新、下载、落地安装、通道与安全 |
| `workspace_browse.py` / `workspace_search.py` / `files.py` | 文件夹浏览、搜索、预览、diff |
| `model_settings*.py` / `catalog*.py` / `connections.py` | 通道、模型列表、能力编辑 |
| `remote_access.py` / `local_addresses.py` | 手机/另一台电脑访问 |
| `artifacts*.py` / `project_materials.py` | 成果与项目资料 |

5.x 在此之上多出：`bots.py`、`bot_coordinator.py`、`bot_executor.py`、`bot_memory.py`、`bot_schedules.py`、`bot_communications.py`、`bot_retry.py`、`bot_computer.py`、`bot_client.py`、`bot_notify.py`、`browser_provider.py`。

### Pilot 前端 `apps/mms-web/`

React + TypeScript + Vite，源码在 `src/`（约 75 个文件，36 个 `.tsx`）。构建产物**签进仓库**，在 `mms_web_static/`。

**硬规则：任何 `apps/mms-web/src` 的改动，必须在同一个 PR 里重建 `mms_web_static/`。** 否则用户装到的是旧界面，而测试全绿。重建方式：

```bash
cd apps/mms-web && npm ci --workspaces=false --ignore-scripts
cd ../.. && python3 scripts/build_mms_web_release.py --skip-install
```

**必须用 per-workspace 安装。** 在 workspace 根上跑 `npm ci` 会解析出锁文件之外的传递依赖，产出不一样的 bundle，还会把 `tsc` hoist 到别处。

`build.json` 里的 `sourceSha256` **不是**可复现性门禁——它只覆盖 src 加 5 个配置文件，不覆盖装出来的 `node_modules`。只改版本号时，`build.json` 的 `version` 和 `sourceSha256` 会变，但资源文件的 hash 不变，这是正常的。

### 其它

- `tests/` —— 171 个 pytest 文件。
- `apps/mms-web/tests/` —— node 测试，`main` 15 个 / `dev` 43 个。
- `scripts/` —— 37 个脚本，门禁和冒烟都在这里。
- `install.sh` —— macOS/Linux 安装器；Windows 走 `packages/mms-install/bin/install.ps1`。

---

## 四、4.x 能力清单（稳定线，按用户动作组织）

这些在两条线上都有。

| 用户要做的事 | 现在的行为 |
|---|---|
| 开始工作 | 选工作文件夹、模型和通道；首条消息前选真实支持的 effort（默认继承 MMS 生效偏好）；可以选执行或只读规划 |
| 对话 | 流式回复、上游真实返回的 Thinking（可展开）、工具参数与结果、工具图片、原生 confirm/select/input/editor 交互 |
| 会话管理 | 重命名、归档/恢复、整段或指定回复处分支、复制、Markdown 导出；刷新和进程重启后继续原上下文 |
| 消息控制 | 停止当前工作；工作中追加消息进 follow-up 队列，可查看和清空 |
| 运行参数 | Thinking、自动压缩、立即压缩（可附加保留要求）、失败自动重试；看模型/协议、上下文占比、Token、缓存 |
| 文件与资料 | 应用内逐级浏览目录、文本/Markdown/图片预览、Git 文本 diff、`@` 引用文件；成果预览与比较；项目资料 |
| 本地文件 | 系统选择器、粘贴绝对路径或 `file://`，直接引用原文件不复制；图片缩略预览；剪贴板截图另存为附件 |
| 通道与模型 | 填地址与 Key → 拉取或手填模型 → 勾选 → 脱敏预览 → 保存；同名模型按通道分组 |
| 模型能力 | 按模型设置默认 effort、上下文长度、能否读图；每一项标明当前值来自哪里；与 MMF 目录不一致时可一键填回目录值 |
| Skills | 按当前 workspace 搜索多选，`/skill:name` 补全，内容随消息送入 Pi |
| 工作区 | 侧栏管理文件夹排序/重命名/移除，会话按 workspace 分组折叠 |
| 命令 | `/help` `/files` `/plan` `/thinking` `/compact` `/clear-queue` `/name` `/fork` `/export`，Pi 已装扩展命令动态列出 |
| 手机访问 | 显式打开后给出地址和二维码，带 token；只在打开时才绑定额外地址 |
| 更新 | 更新中心检查、确认、落地；选 4.x 稳定版或 5.x 预览版两个通道各自缓存 |
| 外观 | 主题跟随系统、主题色、界面/等宽/中文字体和字号实时改，只列本机真装了的字体 |
| 任务模板 | 导出首条任务说明和模型偏好；接收方导入后用自己的模型服务和文件夹 |

**边界（不要误以为有）**：只监听本机地址，没有远程多用户认证；配置隔离不等于文件系统 sandbox；只读规划是 Pi extension 在 tool_call 上拦截，不是 OS sandbox；文件浏览和 diff 只读，没有编辑/提交/发布按钮；分支共用工作文件夹，不等于 git worktree 隔离；Thinking 只展示上游真给的内容，模型不给就不造；用量来自 Pi，不是供应商账单。

Pilot 当前唯一的 harness 是 **Pi**。Claude / Codex / OpenCode / agy 仍然只从 MMS CLI 启动，没进 Pilot 的统一会话。

---

## 五、5.x 增量：Bot 工作台（预览线）

5.x 相对 4.x 的**全部**区别就是 Bot 工作台。理解它需要理解这几个对象：

**Bot** —— 有独立身份、头像、名字（用户自己起）、职责描述、默认模型（`presetId` 可以留空，执行时解析当前可用默认 preset）和**独立持久记忆**的执行者。所有 Bot 默认用共享电脑的全局 `default` workspace，不要求用户管目录。聊天窗口按 Bot 聚合历史任务，是连续对话感，不是控制台 Board。

**Task** —— 一次执行。状态 `queued` / `starting` / `running` / `waiting` / `completed` / `failed` / `interrupted` / `cancelled`。主聊天只呈现用户消息、Bot 回复、成果和等待提示；`bash`、`exit`、内部 `list`/`wait` 这类 CLI 诊断留在事件数据里不进主聊天。取消要等 Pi 确认，15 秒不停才结束该 Bot 自有进程，**只有实际停止才记 cancelled**。

**Plan（计划层）** —— 计划从提示词里拿出来，变成落库、可见、可执行的对象。普通 `direct-first` 请求直接进持久会话，不起 planner；只有明确协作意图或显式 `plan-approve` 才调一次短 planner（20 秒预算，用完即弃）。触发前有一道纯函数形状检查 `looks_multi_goal`（编号列表 ≥2 项、"分别/同时/各自"、`@Bot名`、提到 ≥2 个花名册 Bot 名）。计划有完整状态机（`proposed`/`auto`/`approved` → `running` → `merging` → `done`，外加 `failed`/`rejected`/`cancelled`），步骤级 `pending → ready → running → done|failed|skipped`，每步带 `onFailure`（`retry`/`skip`/`abort`）。分发链最多五层，同一条链不能再次调用同一个 Bot。

**Fleet（同一个 Bot 的多模型评审）** —— 关键定位：**多模型评审是同一个 Bot 换几颗脑子，不是让用户再雇一排永久同事。** 界面上关掉时输入框只留「寻求场外帮助」。默认开、强度「听意见」、2 家便宜对照。Fleet worker 只能由 coordinator 内部创建，是指定模型的一次性**只读** Pi session（只开 read/grep/find/ls，禁用自动扩展、skills、上下文文件加载），不改主 Bot 的模型/会话，不把各家意见写进共享长期记忆。自动选择不足两家时走 direct 并**明确说明不是多方评审**；显式选的家族或型号失效时停止并提示重选，**不换家族不换同名型号**。家族判定优先用 catalog 的 `family`，兜底只走 `mms_core.MODEL_FAMILIES`，**不许再写第二份前缀表**。

**Memory（记忆）** —— 每个 Bot 独立，在 `state_root/bots/memory/<botId>/memory.json`，与 Pi 会话和 workspace 分开。最多 100 条事实 + 200 条任务摘要，每条 2000 字。新任务按关键词检索相关内容注入，**当前用户指令优先，记忆内容不增加权限**。整理阈值是软触发：Pi 回报的 context usage 到阈值后，下一轮在安全 idle boundary 调 Pi 原生 `compact`。Pi 不回报 usage 时界面显示「未知」，**不伪造硬上限**。

**Schedule（定时）** —— 独立实体，不是 task 上的字段。带 `rule`（`once`/`interval`/`daily`/`weekly`）、必填 IANA `timezone`、单条 `enabled`、`overlapPolicy`（`skip`/`queue`）。到点**新建一个 task**，所以每次运行有独立 transcript 和成果。几条容易做错的语义：
- 周期任务**不补课**：停机错过超过一个周期就只把 `nextRunAt` 推到下一个未来时刻，记 `lastSkip`，不把积压全补跑；恰好错过一次才立即补。
- `interval` 的下一次从**本该触发的时刻**算（`previous + everySeconds`），不被每次触发的延迟带偏。
- 「每天 9 点」在夏令时切换日仍是本地 9:00。
- **`once` 只有一次机会，没跑就不消耗它**：到点不能触发时这条 schedule 停在一旁（parked），`nextRunAt` 保留那个过去的时间，重新可用后的下一个 tick 补触发一次并在新 task 上写 system 消息说明是延后补触发。
- `wakeEnabled` 是 Bot 级总开关，与单条 `enabled` 是两层，任一 false 就不触发。

**Mailbox（Bot 间通信）** —— `dispatch` 用于有依赖的分工，`message`/`reply` 用于通知、澄清、追问，**不伪装成用户消息**。每条消息有 `queued`/`delivered`/`processed`/`waiting`/`failed` 回执；`reply` 只能回复发给当前 Bot 的消息；连续自动往返超过 8 跳暂停，避免 Bot 互相空转。

**浏览器能力** —— 由外部 `BrowserProvider` 提供，不自研。macOS 装了 Ego 就交给 Ego；Windows/Linux 可由 Web Access 连用户明确授权的 Chrome/Edge CDP。Provider 不可用时显示明确的 capability unavailable，**不降级成一套自研的假浏览器**。

**明确不在范围**：操作系统级 Computer Use、桌面窗口控制、通用 Connector 平台、云端 VM。

---

## 六、配置和状态放在哪

这一段记错会写坏用户的机器。

| 路径 | 是什么 |
|---|---|
| `~/.config/mms-next` | **唯一的 config root。** `mms` / `mmf` / `mmg` 和 Pilot 网页都落在它上面 |
| `~/.config/mms-next/version.json` | 安装元数据：`installed_version`、`install_channel`、`release_track*`、`installed_at`、`source`，外加**用户偏好 `preferred_language`** |
| `~/.local/share/mms-web` | Pilot 的 state root：会话、更新缓存、Bot 数据、成果 |
| `<state>/updates/settings.json` | `channel` —— 「我想检查哪条线」 |
| `~/.mms` | 安装目录（代码副本），`~/.mms/.venv` 是它自己的 Python |
| `~/.config/mms` | **legacy，已退出配置来源。** 不自动导入、不回退。只剩 `*-gateway/` 这类运行时会话目录还在那里 |

两个容易混的东西：`updates/settings.json` 的 `channel` 是「我想检查哪条线」，`version.json` 的 `install_channel` 是「我实际装的是哪条线」。**它们不是一回事**，不要合并。用户切到 preview、检查了、但没确认升级——此时 channel 是 preview 而实际安装还是 stable，这个状态是合法的。

`version.json` 混着两类东西：安装元数据和**用户偏好**（`preferred_language`）。要改它就读出现有 JSON、只覆盖安装元数据那几个 key、其余原样保留、再原子写回。整份重写会静默吃掉用户的语言选择。

配置的写入路径只有一条：**写入预览 DB + 发布**。本地修改优先走 Registry v2，TUI / `mms config` / WebUI 先创建 DB candidate，审阅通过后发布成 `generated/model-registry.latest-approved.json`，它引用的 generated Profile 就是 runtime boundary。没有第二条绕开审阅的写入路径。

`~/.config/mms-next/preferences.toml` 是用户偏好 allowlist 覆盖层，**agent 不能自动写真实文件**。可以读、解释、生成 TOML snippet 给用户，写入走 human gate。

---

## 七、门禁：怎么跑，哪几条命令有坑

跑之前先隔离环境，否则可能写穿机主真实配置：

```bash
env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME <你的命令>
```

**这不是谨慎，是事故后加的。** 2026-09-17 有一个测试 fixture 只清了 `HOME` 没清配置根变量，写穿到机主真实 config root，把 capability bundle 冲成空壳，Pilot 当场瞎掉。

| 门禁 | 命令 | 坑 |
|---|---|---|
| Python 回归 | `python3 scripts/ci_pytest_regression.py --base origin/main` | 报「base 红、head 绿」不等于修好了，见下 |
| 新用户视角 | `python3 scripts/regression_fresh_user_gate.py` | **对并发敏感，串行跑一次**；红了单独复跑确认并如实写明 |
| 前端类型 | `apps/mms-web/node_modules/.bin/tsc --noEmit -p apps/mms-web` | **不要用 `npx tsc`**：从仓库根解析会命中一个 decoy 包，假失败 |
| 前端测试 | `node --test apps/mms-web/tests/*.test.mjs` | **glob 是必须的**，漏了等于没跑 |
| 版本一致性 | `python3 -m pytest tests/test_mms_release_version.py` | 见第二节的对齐清单 |
| bundle 新鲜度 | 改了 `apps/mms-web/src` 就必须重建 `mms_web_static/` | 见第三节 |

`.github/workflows/digger.yml` 是仓库唯一的 CI。**它曾经完全没有跑过前端**——240 个 web 测试和 typecheck 从来没进过 CI，这就是「一整块 UI 被删掉而套件全绿」反复靠手工发现的原因。

---

## 八、这个项目已经踩过的坑（重点段，别再踩）

### 1. 读源码字符串的测试什么都不证明

这是本项目最反复出现的一类问题，连续四个 PR 都犯过。

```js
// 这种测试：只能发现"被整段删掉"，发现不了"被改成不干活"
const src = fs.readFileSync('src/Thing.tsx', 'utf8');
assert.match(src, /scrollTo\(\{ top: 0 \}\)/);
```

正确写法是用 esbuild 把 JSX 抽出来**真的执行**，断言算出来的行为。仓库里的正面样板：`apps/mms-web/tests/bot-model-chip.test.mjs`、`reply-reader.test.mjs`、`bot-wait-controls.test.mjs`、`session-attention.test.mjs`。

**推论，同样重要：一个写对的纯函数测试，配上一个没人测的调用点，保护力是零。**

真实案例：`popover-placement.test.mjs` 写得完全正确——import 真函数、断言算出来的数字。但把 `Popover.tsx` 里那一行调用换回旧的右对齐写法，手机上面板甩出屏幕的 bug 就回来了，而 265 条测试全绿。同一个错误我自己也犯过：给「绑定时不做反向 DNS」写的测试直接实例化了那个类，把调用点改回裸的标准库 server 照样绿。解法是把绑定抽成一个工厂函数（`create_setup_server()`），让测试必须走真实路径。

**验收标准：每个包都必须做 mutation testing。** 把修复反向改回去，对应的测试必须变红。自己跑，逐条记录红/绿。「测试通过」不是证据，「把修复破坏掉测试就红」才是。

### 2. 门禁本身会说谎

`scripts/ci_pytest_regression.py` 原来把「base 红、head 不红」算成修好了。但一个**被删掉的**红测试也满足这个条件。PR #315 报告的 62 个「修复」里有 4 个已经不存在了，其中一个（`startup_safe`）让一个真实行为在 400 个测试里零覆盖。

现在它会单独打印「base 红且此处已不存在」的清单。它**不会**让门禁失败（改名和删功能是合法的），但不能再隐形。

教训是通用的：**门禁报告的绿，要先问它测的东西还在不在。**

### 3. 启动热路径上零同步网络调用

历史事故：`_source_choices_for_tui` 预计算 12 个 scene/variant 的 provider 源，串行 probe = 4 秒启动。解法是文件缓存（24h TTL）+ 惰性字典 + 后台并行预热，4s → 0.1s。

同型的还有：`CLI_NAMES` 里塞了不再维护的 qwen/kimi，启动时检测浪费 3.5 秒。

**规则：高成本验证逻辑不进日常启动路径，做成独立脚本或 doctor 子命令。**

### 4. 写锁里不要做慢操作

同一个病犯过三次：

- v4.18.0：文件夹搜索跑在全局写锁里，一次拖拽让发消息、停会话、确认更新一起排队几秒。解法是把这三条**只读**路由移出锁。
- 4.22.4：打开手机访问卡 30 秒。根因是标准库 `HTTPServer.server_bind` 里的 `socket.getfqdn(host)` 做反向 DNS，在不回 PTR 的家用网络上卡满 30 秒；而 `set_remote_access` 持有 `mutation_lock`，那 30 秒里所有 POST 排队，前端健康轮询超时报断开。解法是子类覆盖 `server_bind` 跳过 `getfqdn`（`server_name` 只被标准库的 CGI 管道读，Pilot 从不 emit），**不是**把写操作移出锁。
- v4.23.1：`configuration/discover` 在锁内做同步 httpx（15s timeout），`model-settings` 的 discover/check/refresh 在锁内做 `subprocess.run`（90s timeout）。解法同第一条，只把**真只读**的路由放进 `_UNLOCKED_POSTS`。

**分辨标准：真的在改服务器状态就该持锁，修掉里面的阻塞；只读就移出去。不要用「移出写锁」去解决一个写操作的延迟问题——那是拿正确性换延迟。**

`mms_web/server.py` 的 `_UNLOCKED_POSTS` 是精确路径列表，**绝不要改成前缀匹配**：`model-settings/preview` 和 `apply` 确实会写，必须留在锁里。

### 5. Windows 上 `os.replace` 会被杀毒软件短暂挡住

`mms_web/runtime.py` 的 `private_json()` 是 Pilot **所有**持久化的唯一入口。POSIX 上 rename 能覆盖正被打开的文件，Windows 不行：Defender 实时扫描那个刚 close 的临时文件会短暂持有句柄，`os.replace` 拿到 `WinError 5`。原来一次都不重试，而且 `finally` 会把刚写好的临时文件删掉——**会话数据静默丢失**。

现在是短退避重试，重试期间不删临时文件，全部失败后明确抛出。**不要**为了绕过它改成直接写目标文件：那是用数据损坏换数据丢失，原子替换的语义必须保留。

配套教训：`threading.Thread(daemon=True)` 里抛出的异常 Python 会静默丢弃。后台线程必须有顶层捕获 + 日志，否则用户只看到「点了没反应」。

### 6. Claude 兼容性不能只测 `/models`

`/models` 返回正常只证明模型枚举通，不等于模型可调用，更不等于能挂到 Claude CLI。回归至少分三层：provider/OAuth 连通性 → 模型最小 chat → Claude 路径兼容性。

相关：`Anthropic /v1/messages` 和 `OpenAI /v1/chat/completions` **不是等价 transport**，同一个 vendor、同一个模型、同一个 key，在两条路径上的 cache 表现可能完全不同。route 支持 `anthropic_messages` 时默认优先走 `/v1/messages`，`chat/completions` 只能是显式 fallback。`kimi-for-coding` 这类在 `chat/completions` 上返回 403 但在 Anthropic 路径正常的，要标成 `agent_only`，不要误判成「模型彻底不可用」。

### 7. 识图能力只有一条真值链

`_pi_model_input_types()`（`lib/mms_pi_support.py`）的优先级：用户设置（`manual_override`、`model_policy`）> Pi 实测硬编码 hints > curated 数据（provider profile、approved facts）> 名称匹配兜底。

**不许**在 `_pi_model_input_types` 里绕过 `caps` 直接查表（那会让用户在 Web 里的设置对 Pi 失效），**不许**把 `conservative_fallback` 当成「这个模型不支持图片」（它的含义是「没有任何来源声明过」），**不许**新增第五份硬编码 vision 名单。

### 8. 真实 HOME 和全局 OAuth 不是 fallback 池

模型/provider/account 失败时必须留在当前 runtime 里 fail-closed。**不允许**静默切到 global/default OAuth，不允许把 `~/.claude.json`、Keychain 里的 OAuth state、`~/.codex/auth.json`、`~/.gemini` 当成重试或自动补救来源。只有显式的人类动作（login、import-auth、手动重选 runtime）才能进入 OAuth。

### 9. 大规模回归先抽样

不要一上来全 provider、全模型、全 CLI 跑。先按 provider 抽 2-5 个模型，把错误分成 `auth / access / endpoint / timeout / cli` 几类，再决定要不要全量。

### 10. 已经查过、不是 bug 的东西

省下重复推导：`workspace_browse.py` 里 `child.is_symlink()` 看着像多余的冗余检查，因为 `child.is_dir(follow_symlinks=False)` 已经排除了 symlink——它是冗余，不是漏洞，**不要"顺手清理"也不要当成 bug 报**。

---

## 九、安全边界（碰之前先说清楚）

**受保护文件。** 改它们之前必须先说明改动边界：`lib/mms_core.py`、`lib/mms_launchers.py`、`lib/mms_tui.py`、`lib/mms_bridge.py`、`lib/mms_account_state.py`、`lib/mms_session.py`、`lib/mms_adapter_registry.py`、`mms`、`ccs`。用户只说"修一下"、"看看问题"时默认先诊断定位，不直接改主启动链路。能用文档、注释、测试、辅助脚本解决的优先走低风险路径。

**端口。** 绝不碰 8767 / 60824 / 8765 / 8766——那是机主在跑的实例。要起验证实例用 61000-62000 的随机端口。**只 kill 自己启动的 PID，按精确 PID。绝不 `pkill`，绝不按端口 grep 完批量 kill。** 有过一次 verifier 用这种方式杀掉机主两个进程。

**别人的工作树。** 仓库根目录可能有其它会话正在编辑的脏文件。在 scratchpad 下用独立 worktree 干活，**绝不** stage / stash / reset / clean 别人的改动。`git stash` 列表里有其它会话 2026-09-10 及更早保存的工作，**绝不要 drop 它们**。注意 `git stash -q -u` 会同时吃掉已 staged 和未 staged 的改动——`git reset --soft` 之后再 stash 会把作者的工作整个卷走（发生过，靠 `stash pop` 救回）。

**force-push 前必须先告诉用户。** 往别人的分支 force-push 会覆盖对方的工作，默认不做。要在别人的 PR 上做改动，用 `git merge --no-commit --no-ff` 到自己的 worktree，对方分支不动，PR 依然会被标成 merged。

**不要碰机主真实配置。** 不写 `~/.config/mms*`、不写 `~/.local/share/mms-web`。

---

## 十、协作方式

这个项目是**多个模型并行**在做。你不是唯一一个在动这个仓库的 agent。

- **改动通过 issue → PR → 评审 → 合并。** agent 不自行 merge，也不绕过评审门禁。除非人类在当轮明确说了合并。
- **谁审谁的：** 自己的 PR 留给别人审，你去审别人的。
- **提交要人类同意。** 例外：docs-only 的计划/报告/交接文档，用户说"记录/提交/产出文档"时可以直接 commit，但只 stage 目标文档，不带任何无关脏文件。
- **包（packet）制。** 复杂工作会被写成一份 `docs/mms-web/bot-work/T*.md` 的工作包：症状、证据、根因、要做什么、**不要做什么**、测试要求、mutation 清单、门禁、边界、交付要求。你拿到一个包就按它做，包里明说"只列不改"的东西就不要改。
- **验收看 mutation，不看交付报告。** 见第八节第 1 条。
- **commit 身份**（每个 commit 单独设，不改全局 config）：

```bash
TZ=Asia/Singapore git -c user.name="<AgentName>" -c user.email="<model>@<family>.com" commit ...
```

trailers：`Agent-Model`、`Agent-Family`、`Agent-Session`、`Agent-Step: x.y.z`。**时间戳一律 Asia/Singapore (+0800)**，不管你自己的会话在哪个时区——同一个仓库里曾经并存 `-0700` / `+0800` / `+0900` 的 commit，`git log` 的排序和任何跨 agent 的耗时判断都不可靠了。

- 合别人的活时**保住对方的 authorship**（`GIT_AUTHOR_NAME/EMAIL/DATE`），自己的版本 stamp 放在**另一个** commit。

---

## 十一、文档地图，以及哪些已经过期

先读：

| 文档 | 内容 |
|---|---|
| 这份 | 项目全貌、能力清单、坑 |
| `AGENT.md` | 共享规则（语言、提交、worktree、受保护面） |
| `docs/AGENT_GUARDRAILS.md` | 高风险面的详细约束：启动链、cache、vision、Codex hook trust、single config root |
| `docs/mms-web/GETTING-STARTED.md` | Pilot 安装与使用 |
| `docs/mms-web/API.md` | Pilot 本地 API v1 |
| `docs/RELEASE_CHANNELS.md` | 通道契约 |
| `docs/mms-web/CHANGELOG.md` + `RELEASE-v*.md` | 每个版本实际做了什么，比任何总结都准 |

5.x 专属：`docs/mms-web/BOTS.md`（最详细的 Bot 行为说明）、`BOT-POSITIONING.md`（定位与复用边界）、`BOT-ROADMAP.md`、`docs/mms-web/bot-work/`（工作包）。

**已知过期，读的时候要打折：**

- `docs/mms-web/FEATURES.md` 顶部还写着「2026-09-08，尚未公开发布」，最后几节是按日期追加的增量日志。功能清单本身基本可信，"尚未发布"那句早就不成立。
- `docs/RELEASE_CHANNELS.md` 的「版本轨道」表还是 `3.4.z / 3.5.z / 3.6.z`，「4.21.x 稳定线与 5.0 预发线」那节描述的 `dev-pre` 分支方案**已经作废**（5.x 现在直接在 `dev` 上）。通道定义和安装命令仍然有效。
- `docs/legacy/` 下的东西只用于追溯。
- `README.md` 里 3.x 轨道那段是历史记录，不是当前状态。

写代码前请核对：**任何文档里的版本号、分支关系和"当前状态"，都以 `lib/mms_version.py`、`git log` 和最近的 `RELEASE-v*.md` 为准。**

---

## 十二、交付的时候要写清什么

- 改动边界是什么，哪些主功能**没有**动。
- 实际做了哪些验证，哪些**没有**做。mutation 逐条红/绿。门禁写实测绝对数（base / head）。
- 用户选择的数据从哪来、怎么传、在哪生效——这是本仓库反复出问题的地方（界面选了一个模型、launcher 启动了另一个）。
- 残余风险，特别是跨 `TUI → core → launcher → bridge` 的链路风险。
- 没验证的就写"没验证"。不要含糊。
