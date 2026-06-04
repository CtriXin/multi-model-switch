# Agent Guardrails

这份文档约束所有在本仓库内操作的 agent，目标是减少“顺手改一点”却扰动主功能的情况。默认原则不是禁止改动，而是限制高风险改动必须先收窄范围、明确影响面、做最小验证。

## 目标

- 保护 MMS 的主启动链路稳定：`CLI/profile 选择 -> 模型选择 -> 使用入口选择 -> runtime 决策 -> launcher -> bridge/env 注入 -> 实际 CLI 启动`
- 保护现有兼容承诺：`mms` 主入口、provider / account 双来源、单次注入策略、本地隔离目录策略
- `ccs` 已全面退休；只允许保留 stale cleanup / reset 清理逻辑，不允许重新引入 `ccs` 入口、`~/.config/ccs` fallback 或 `CCS_*` 环境变量兼容。
- 避免 UI 展示、配置状态、启动参数、bridge 实际路由彼此脱节

## 受保护的稳定面

以下能力默认视为主功能，除非用户明确要求，否则 agent 不应改变其行为语义：

- CLI tab / profile / 模型选择、自定义选择、最近使用与默认来源逻辑
- `provider` / `account` 的优先级、过滤逻辑、默认来源选择逻辑
- `runtime` 决策和 `auth_mode` 语义，包括 `api_key`、`oauth`、`oauth_bridge`
- `claude` / `codex` / `opencode` / `agy` 的启动参数与环境变量注入
- bridge 行为，包括 `claude <- codex`、`codex responses -> chat completions`
- 配置文件结构、迁移逻辑、override 读取规则、账号目录隔离规则
- 本地统计、最近使用、历史启动记录的写入语义

## 高风险文件

对下列文件的改动默认视为高风险改动：

- `mms_core.py`
- `mms_launchers.py`
- `mms_display/tui.py`
- `mms_runtime/bridge.py`
- `mms_runtime/account_state.py`
- `mms_session/index.py`
- `mms_registry/adapter_registry.py`
- `mms`
- retired `ccs` 入口和 deleted legacy `mms_session.py` 相关清理逻辑

如果任务涉及这些文件，agent 必须先说明改动边界，再动手。

## 保险窗口：private relay / sticky relay / upstream

以下链路现在进入“保险窗口”，默认按受保护集成面处理：

- `MMS -> sensitive Claude relay -> upstream`
- `MMS -> sensitive OpenAI-compatible relay -> upstream`
- `MMS -> sticky-session relay -> upstream`

## Anthropic-First / Cache Guardrail

这条规则专门针对 dual-protocol provider 与 cache 命中问题：

- `Anthropic Messages` 和 `OpenAI chat/completions` 不是等价 transport
- 同一个 vendor、同一个 model、同一个 key，在 `/v1/messages` 和 `/v1/chat/completions` 上的 cache 表现可能完全不同
- 如果 route 支持 `anthropic_messages`，默认应优先 `Anthropic /v1/messages`
- `chat/completions` 只能作为 fallback，不应该是静默默认值

当前已知稳定经验：

- `shared-root gateway`：如果 `openai_base_url=/v1` 且已知支持 `anthropic_messages`，优先验证裁 root 后的 `/v1/messages`
- `separate-path vendor`：例如 `.../v1` 与 `.../apps/anthropic`，必须显式配置两条 URL；不要靠猜
- `Qwen plus/max`：`qwen-plus`、`qwen3.5-plus`、`qwen3.6-plus`、`qwen3-max` 在 `Anthropic /v1/messages` 路径上需要保留 `cache_control`，不要按“非 Claude 模型”统一剥离
- 低 cache 先区分 `route/protocol` 问题和 `model-level` 问题，不要一上来就怀疑 sticky failure

相关事实 runbook：

- `docs/SERVER_CLAUDE_CACHE_RUNBOOK.md`

只要改动会碰到下面任一项，就不能只看“本地代码改得小不小”，必须先回答“会不会影响这条链路”：

- provider 的 `models_endpoint`
- `extra_models` / `hidden_models`
- model probe / probe cache / fallback model logic
- `Codex` / `Claude` header 透传
- `channel_affinity` / sticky key source
- `/claude`、`/openai`、`/responses`、`/models` 的协议假设

## 这条链路的额外禁止事项

没有用户明确要求时，不要做下面这些事：

- 把敏感 relay 从 manual model-list 模式改回默认 `/models` 探测
- 改动 Claude alias / model patch 行为，却不验证公开默认模型是否仍可用
- 改动 `Codex` / `Claude` 上游识别头，却不验证 sticky / client identity 行为
- 改动 sticky-session 规则或 body/header 映射，却不验证 `metadata.user_id` / `prompt_cache_key`

## 这条链路的最小确认问题

任何人或 agent 在动手前，至少要先确认这 4 个问题：

1. 这次会不会改变模型列表的来源：`remote` / `fallback` / `manual` / alias patch？
2. 这次会不会改变任一敏感 relay 链的 `/models`、`/responses`、`/messages` 行为？
3. 这次会不会改变 sticky-session 的 key source、header 透传，或上游对客户端类型的识别？
4. 如果线上坏了，能不能立刻用现有 smoke 文档复现并回溯？
5. 这次会不会把原本应走 `Anthropic /v1/messages` 的流量重新打回 `chat/completions`，从而影响 cache？

## 这条链路的最低验证

除了通用验证外，这条链路至少补一条对应 smoke：

- Claude relay：
  - 对应的 `models` / `messages` smoke
- OpenAI-compatible relay：
  - manual model-list / fallback / extra model smoke
- sticky-session relay：
  - sticky-session 命中与关键 header 识别 smoke
- dual-protocol / cache-sensitive route：
  - 实际 `request_path` 是否仍是 `/v1/messages`
  - 是否意外退回 `/v1/chat/completions`
  - 如果 cache 异常，是否已区分 `route-level` vs `model-level`

统一追溯入口：

- 当前仓库内的公开兼容性说明
- 你自己的本地 smoke runbook（如果不适合进 git）

## Claude 额外限制

`Claude` 在本仓库内默认采用更保守模式：

- 没有用户明确要求时，不要直接修改任何高风险文件
- 用户只说“修一下”“看看问题”“为什么错了”时，默认先做诊断和定位，不直接改主启动链路
- 如果需求同时能通过文档、注释、测试、回归清单、辅助脚本解决，优先这些低风险路径
- 若必须改高风险文件，只允许做最小修复；禁止顺手重构、顺手统一抽象、顺手重排选择流程
- 若发现 TUI、runtime、launcher、bridge 之间存在结构性问题，先提交影响面说明，再等待用户确认是否继续
- 改完后必须明确说明“用户选择的数据从哪里来、如何传递、在哪里生效”，避免再次出现选中值和实际启动值不一致

## 禁止事项

没有用户明确要求时，agent 不得做下面这些事：

- 顺带重构主启动链路，只因为“代码看起来可以更优雅”
- 私自改变默认模型、默认 provider、默认 account、默认 bridge 策略
- 私自改变已有字段语义，尤其是 `model_info`、`runtime`、`provider`、`account` 相关字段
- 把显示层需要的数据和启动层需要的数据混在一起，导致 UI 选项和实际执行不一致
- 重新引入已退休的 legacy `ccs` shim、`~/.config/ccs` 旧配置 fallback、`CCS_*` 环境变量兼容，或已删除的 legacy chat session module
- 在未验证的情况下改动 HOME/XDG/状态目录隔离逻辑
- 为了实现新功能，直接覆盖已有选择流程、确认流程或 bridge 路由
- 把一次性的实验逻辑直接变成默认行为，且没有显式开关或任务上下文说明

## Global OAuth Hard Cut

这条规则高于一般“方便复用”的实现倾向：

- `real HOME` / global OAuth / global account state 不是 runtime fallback pool
- model / provider / account 失败时，必须留在当前 runtime 里 fail-closed；不允许静默切到 global/default OAuth
- 不允许把 real-home 的 auth-bearing state 当作重试、恢复、自动补救来源，包括但不限于：
  - `~/.claude.json`
  - macOS Keychain 里的 OAuth state
  - `~/.codex/auth.json`
  - `~/.gemini`
  - 其他真实用户 home 下的 token / account / owner identity cache
- 显式 human 动作（例如 `login`、`import-auth`、手动重选 runtime）是唯一允许进入 OAuth 的路径；普通 launch / probe / retry / bridge / resume 逻辑不得自动这样做
- 如果确实要继承 global 的非认证状态，必须走 schema/allowlist，并明确排除 token、account identity、owner fingerprint、account 选择提示和请求 credential
- 任何可能把隔离 session auth state 回写到 real/global HOME 的设计都默认禁止；除非任务明确要求一次性人工导入，而且边界和验证都写清楚

## Codex Hook Trust No-Popup Contract

MMS-managed Codex launch must not repeatedly stop on `Hooks need review` in isolated sessions.

- Gateway Codex `CODEX_HOME` must stay stable at `~/.config/mms/codex-gateway/.codex`; per-PID `MMS_SESSION_HOME` is allowed only for wrappers/tmp/session packet state.
- Do not revert Codex gateway back to `CODEX_HOME=$MMS_SESSION_HOME/.codex`.
- Runtime `bypass` mode must pass both `--dangerously-bypass-approvals-and-sandbox` and `--dangerously-bypass-hook-trust`.
- Real `~/.codex/hooks.json` trust wins over stale sibling sessions. Sibling `codex-gateway/s/<pid>/.codex/config.toml` trust can backfill missing entries, but cannot overwrite matching real-home trust.
- Codex upgrade/hash drift must be repaired from the current Codex `app-server` `hooks/list` `currentHash` before launch; do not rely only on stale copied `trusted_hash` values.
- Real `~/.codex/config.toml` refresh is allowed only for MMS-managed hook trust hashes; do not auto-trust arbitrary project/user hooks there.
- If an isolated MMS/Codex session approves hook trust once, that trust must be written back to stable gateway trust and reused by later sessions. Asking the user to approve the same MMS-managed hooks again is a bug.
- On recurrence, immediately inspect actual active `CODEX_HOME`, `MMS_SESSION_HOME`, launch flags, Codex version, and Codex `app-server` `hooks/list` statuses for gateway and real Codex homes before changing code.
- Expected healthy state after any repair: gateway `hooks/list` has `0` `untrusted`/`modified` hooks; real `~/.codex` may only be auto-refreshed for MMS-managed hook hashes.
- Any change to Codex hook generation, hook order, `CODEX_HOME`, or hook trust copy/write-back must run `tests/test_codex_hook_trust_contract.py` plus the targeted Codex hook trust tests.

## User Preferences And Human Gate

`~/.config/mms/preferences.toml` 是用户偏好 allowlist 覆盖层，不是 agent 可随手写的配置文件。

- 日常偏好优先建议写 `preferences.toml`，例如 `thinking_mode`、`reasoning_effort`、`bypass`、`caveman_mode`、`nsr_mode`、`agent_pack`、`session_surfaces.disabled`、`assets.roots`
- LLM / agent 需要先看 `docs/MMS_USER_PREFERENCES.md`，或让用户执行 `mms config preferences.help`
- agents 可以读取、解释、生成 TOML snippet / manual diff，但不能自动写入真实 `~/.config/mms/**`
- `preferences.toml` 会忽略 credentials、provider routes、account identity、proxy、OAuth、real HOME/XDG、Claude config 等非 allowlist 字段
- 如必须写真实配置，仍走 human gate：`plan -> backup -> human double check -> audited write -> post-write human double check`

## 必须先停下来确认的情况

遇到以下情况，agent 应先停止扩散改动范围，必要时直接向用户确认：

- 需要修改上面“受保护的稳定面”里的行为语义
- 需要新增、删除、重命名配置字段，或者改变已有字段含义
- 需要改变 TUI 选择结果的返回结构，或改变 launcher 依赖的输入结构
- 需要改变 provider / account 的决策优先级
- 需要改动 bridge 请求翻译格式、鉴权头、默认 URL 拼接方式
- 发现已有未提交改动正好落在同一高风险文件，且当前任务与其存在真实冲突

## 允许的改动方式

高风险任务应优先使用下面的收敛策略：

- 优先在局部函数修复 bug，不扩大为跨模块重写
- 优先新增显式字段，不复用一个旧字段承载新的不同语义
- 优先保留原默认行为，把实验能力放在明确入口、开关或新分支里
- 优先把“显示用状态”和“执行用参数”分开保存、分开传递
- 优先让 fallback 保守，不要让失败路径自动切到语义明显不同的默认值

## 改动前检查

动手前至少要明确这几件事：

- 这次改动影响的是显示层、选择层、runtime 决策层、launcher 层，还是 bridge 层
- 当前任务是否会影响 `mms` 主入口的默认路径
- 当前任务是否会影响任何已有预设、provider、account 的兼容行为
- 当前数据结构有没有被多个模块共享，如果有，是否会引入隐式耦合
- 当前改动会不会让失败路径读到 real HOME / global OAuth，并把它当成 fallback 或恢复来源

## 改动后最低验证

只要碰到高风险文件，至少完成与改动相符的最小验证，并在交付时写清结果：

- 语法级验证：`python3 -m py_compile` 覆盖改动到的 Python 文件
- 启动链路验证：确认“选择到的模型/来源”和“实际启动使用的模型/来源”一致
- 回归验证：确认未改动的默认路径仍可继续工作
- 如果涉及 bridge：确认请求目标协议、模型名和鉴权信息没有被静默改写错位
- 如果涉及配置或账号隔离：确认不会误写真实用户全局目录或破坏现有登录态
- 如果涉及 fallback / resume / auth 恢复：确认失败路径不会静默切到 global OAuth，也不会把 global auth-bearing state 当作自动补救输入

## Push 前 Fresh User Gate

每个功能迭代准备 push 前，必须跑一次安装版/新用户视角的回归 gate，不能只依赖当前开发者机器的真实状态。

- 默认命令：`python3 scripts/regression_fresh_user_gate.py`
- 紧急小修可先跑：`python3 scripts/regression_fresh_user_gate.py --quick`，但 push 前仍要补全默认 gate，或在交付里明确说明未补全原因。
- gate 必须清掉当前 session 注入的 `MMS_CONFIG_ROOT` / `REAL_HOME` / `ORIGINAL_HOME` / `MMS_REAL_HOME` / `XDG_CONFIG_HOME` 等环境变量，用临时 `HOME` 模拟 fresh installed user。
- gate 至少覆盖：
  - `mmf` fresh preview root 是否落到临时 `~/.config/mms-next`
  - Claude 新启动不会消费项目旧 `lastSessionId`
  - 显式 `mms resume <id>` 仍传递原生 resume 参数
  - installer/path smoke 不依赖开发者 worktree 私有状态
- 若改动触及 `mms_core.py`、`mms_launchers.py`、installer、session index、config root、resume、HOME/XDG 隔离、wrapper 或 release channel，最终 handoff 必须写明 fresh-user gate 的实际结果。

## 迭代与提交隔离

为了降低多 agent 共用工作树时的污染风险：

- 一个迭代完成后，agent 必须先询问用户是否提交当前改动
- 在用户没有明确回复前，不应默认进入下一轮实质性改动
- 如果用户选择暂不提交，agent 在继续前应把“当前仍未提交”视为显式风险写明
- 不要把第二个独立问题直接叠加到第一个未确认提交的迭代上

## 交付要求

在最终说明里，agent 至少要写清楚：

- 改动边界是什么，哪些主功能没有动
- 实际做了哪些验证，哪些没有做
- 是否存在残余风险，尤其是跨 `TUI -> core -> launcher -> bridge` 的链路风险

## 反例

以下属于本仓库要避免再次发生的问题：

- 界面里选中了某个模型，但 launcher 最终启动时使用了另一个默认模型
- 为了支持新路由，在 bridge 或 env 注入阶段静默覆盖用户明确选择
- 为了省事复用已有字段，导致 `recent`、`preset`、`custom` 三条路径行为不一致
- 改动一个 CLI 的分支时，意外破坏另一个 CLI 的 runtime 选择或确认流程

## 一句话规则

主启动链路可以修，但不能在没有明示、没有边界、没有验证的情况下“顺手改”。
