# Task Plan: chat + discuss 交互升级与产品化

## Goal
在 `feature-chat-discuss` worktree 中沉淀一份可开源分享级别的产品方案，明确 `mms chat` 交互式续聊、`mms discuss` 执行导向、session 生命周期、context 压缩与 branch continuation 的设计方向，并为后续实现准备 todo。

## Current Phase
Phase 2

## Phases

### Phase 1: Requirements & Discovery
- [x] 确认用户目标：把当前方向提升为可独立开源分享的功能
- [x] 确认工作目标 worktree：`feature-chat-discuss`
- [x] 收集已有结论：chat 侧重结果选择与续聊，discuss 侧重结论转执行
- [x] 记录第一次外部讨论（Codex）结论
- **Status:** complete

### Phase 2: Planning & Product Framing
- [x] 建立文件化 planning 文档
- [x] 明确产品边界、交互主路径与核心风险
- [x] 形成可执行的 v1 / v2 范围划分
- [x] 明确 session 清理与保留规则
- **Status:** complete

### Phase 3: Research & Pattern Review
- [x] 再做一轮垂直研究：branching chat、context compression、execution handoff
- [x] 提炼适合当前需求的分类框架，而不是泛泛的“AI chat”
- [ ] 记录同类/近似产品模式与差异点
- **Status:** in_progress

### Phase 4: Documentation
- [x] 在 `docs/` 中落地产品方案文档
- [x] 补充键位、状态机、session 结构、清理策略
- [x] 写清楚为何它值得独立开源分享
- **Status:** in_progress

### Phase 5: Delivery
- [x] 向用户汇报 worktree 状态、计划、todo、研究结论
- [x] 给出推荐的下一步实现顺序（已转为 agent-discuss 讨论 + 确认 plan）
- **Status:** complete

### Phase 6: Implementation — Chat+Discuss 状态机闭环 v1
优先级标注：🔴 P0（阻塞后续）/ 🟡 P1（核心路径）/ 🟢 P2（增强）

- [x] 🔴 **P0-A** `ccs_session.py` — 新建：4 层 envelope + extract_brief_footer + build_continuation_prompt
- [x] 🔴 **P0-B** `ccs_chat.py` — run_compare 返回 buffers（1 行改动）
- [x] 🔴 **P0-C** `ccs_chat.py` — _stream_compare_model 加 hidden JSON footer 指令（with_footer 参数）
- [x] 🟡 **P1-D** `ccs_action_bar.py` — 新建：post_action_bar curses + event reducer + run_chat_loop
- [x] 🟡 **P1-E** `ccs_chat.py` — chat_main 接入 run_chat_loop
- [x] 🟡 **P1-F** `ccs_discuss.py` — 新增 REFINE_SYSTEM_PROMPT + ACTION_BRIEF_SYSTEM_PROMPT
- [x] 🟢 **P2-G** `ccs_action_bar.py` — CONVERGE single/multi-branch 路径（_handle_converge）
- **Status:** complete

## Key Questions
1. `chat` 的后操作栏应该如何做到高效、直觉、低 token 成本？
2. `discuss` 如何默认导向执行层，同时保留少量回退到 chat 的能力？
3. session 应保存哪些内容、保留多久、何时自动清理？
4. 如何把“从某一列继续”压缩成 state-first，而不是 transcript-first？
5. 这个功能在开源定位上最适合归入哪个更垂直的产品分类？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 工作文档写入 `feature-chat-discuss` worktree | 用户明确要求在该 worktree 里落地记录，不污染当前 `feature-discuss` 会话工作区 |
| `chat` 和 `discuss` 作为两种不同产品模式设计 | 用户需求已明确区分：chat 用于选答案继续，discuss 用于收敛并转执行 |
| 继续逻辑采用 state-first，不采用 transcript-first | 控制 context 膨胀，符合 Codex 讨论结论，也更适合 CLI 产品 |
| `R` 纳入 chat 后操作栏 | 用户明确要求对结果不满意时可快速重开，不复用脏上下文 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `planning-with-files` 的 catchup 脚本路径依赖 `CLAUDE_PLUGIN_ROOT`，当前为空，导致 `/scripts/session-catchup.py` 不存在 | 1 | 直接读取技能模板并手工初始化 planning 文档；后续如需可改用显式绝对路径 |

## Notes
- 当前 Claude 会话所在 cwd 仍是 `feature-discuss`，但本次规划与文档已明确写到 `feature-chat-discuss`
- 需要把”更垂的分类”研究成产品定位，而不只是功能列表
- 后续若开始实现，先读本文件和 `docs/CHAT_DISCUSS_PRODUCT_SPEC.md`

## Future TODOs (v2+)

### TODO-1: OAuth Plan 用量查询
- 接口：`GET https://api.anthropic.com/api/oauth/usage`
  - Header: `Authorization: Bearer <oauth_token>`, `anthropic-beta: oauth-2025-04-20`
  - 返回: 5h/7d 利用率百分比
- 目标：在 `mms config stats`（或新命令）展示当前 plan 用量
- 适用范围：OAuth 账号（plan mode）；gateway 账号不适用
- 同步接入已有 oauth 基础设施（`feature-oauth` 分支已完成 oauth 登录/token 缓存）
- 后续可在 Phase 3 综合前查询用量，动态影响 synthesizer 档位选择

### TODO-2: Model Pricing Database 维护与自动更新
- 当前 `_MODEL_PRICE_DB` 在 `ccs_discuss.py` 中硬编码（前缀 → tier, $/1M tokens）
- 问题：新模型出来后需手动更新，价格随时变
- 目标：
  1. 将 DB 提取到独立配置文件（如 `~/.mms/model_prices.json`）
  2. 触发时机：`mms discuss` 首次运行 / 用户执行 `mms update-prices`
  3. 数据源候选：OpenRouter `/api/v1/models`（含 pricing）、各厂商官方 API
  4. fallback：内置静态 DB（当前版本作为 seed）
- 关联：可与 OAuth 用量查询联动，低用量时自动选更高质量档位
