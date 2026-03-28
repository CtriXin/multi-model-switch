# Web App Handoff

## Context

当前工作目录：

- `feature/web-app`
- 路径：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.claude/worktrees/feature-web-app`

这条线的目标是给 MMS 新增一条独立的 web/macOS 产品线，而不是给现有 CLI 随便包一层页面。

## What Has Been Decided

- 主产品形态是独立 web/macOS app
- 不内嵌 Claude Code 或 Codex 作为宿主 UI
- Claude Code / Codex / Gemini / gateway 是 execution/runtime targets
- 首版采用三层结构：
  - `apps/web`
  - `apps/runtime-api`
  - `packages/contracts`
- UI 方向是白色桌面工作台
- 只参考外部产品的“气质”，不照搬版式或交互路径
- 设计优先级固定为：
  - 多模型工作流
  - 模型接入体验
  - 会话与素材管理

## Source Of Truth

开发前先读这 3 份文件：

1. `.ai/plan/current.md`
2. `docs/WEB_APP_IMPLEMENTATION_PLAN.md`
3. `docs/AGENT_GUARDRAILS.md`

补充参考：

- `docs/APP_ROADMAP.md`
- `.ai/plan/TODO.md`

## Current Repo State

本 worktree 当前已经有这些与 web 线直接相关的落点：

- `.ai/plan/current.md`
  - 当前任务 source of truth
- `docs/WEB_APP_IMPLEMENTATION_PLAN.md`
  - 完整实施计划
- `.ai/plan/TODO.md`
  - 下一步任务列表

注意：

- `docs/APP_ROADMAP.md` 仍是旧索引文档，还没切到这条新 web 线的表述
- 当前还没有正式的前端/服务端代码骨架提交

## First Implementation Order

### Step 1: contracts

先固化基础契约，不要先写散的 mock：

- bootstrap schema
- session schema
- chat lane schema
- discuss phase schema
- provider/account schema

### Step 2: runtime-api

在 `apps/runtime-api` 起 FastAPI 骨架，先打这几个接口：

- `GET /api/bootstrap`
- `GET /api/models`
- `GET /api/sessions`

要求：

- 先保证接口形状稳定
- 真实底层逻辑可以阶段性 mock
- 不要一开始就重构 `mms_core.py`

### Step 3: web shell

在 `apps/web` 起 Vue/Vite/Pinia/Router 骨架，先建这几个页面：

- `/`
- `/chat`
- `/discuss`
- `/sessions`
- `/models`
- `/settings`

要求：

- 首页是“承载页 + 工作台入口”混合结构
- Chat 必须直接体现多模型 compare
- Discuss 必须直接体现 phase 和 synthesis

### Step 4: adapter boundary

前端只依赖 contracts + runtime-api，不直接碰 CLI 子进程。

## UI Rules

- 白底，不保留 Kimi 原型暗色主题
- 高对比度文字，避免浅灰不可读
- 模型、provider、account、模式切换要高频可见
- 核心动作一跳完成：continue / change models / converge / handoff
- 不做普通聊天软件式单线程信息流

## Protected Surfaces

开始实现前必须意识到这几块不是当前首选改动面：

- `mms_core.py`
- `mms_launchers.py`
- `mms_tui.py`
- `mms_bridge.py`
- `mms_account_state.py`
- `mms_session.py`
- `mms_adapter_registry.py`
- `mms`
- `ccs`

如果要改这些文件，先读 `docs/AGENT_GUARDRAILS.md`，并明确说明为什么 web 线必须改到这里。

## Recommended Immediate Task For Next Session

新会话建议直接做这一组最小可执行动作：

1. 初始化 `apps/web`
2. 初始化 `apps/runtime-api`
3. 初始化 `packages/contracts`
4. 写 bootstrap/models/sessions 的最小契约
5. 在 web 里先把首页 + Chat/Discuss 路由壳跑起来

## Deliverable Standard

下一个阶段完成时，至少应满足：

- 新会话不需要再补产品决策
- `apps/web` 可以启动
- `apps/runtime-api` 可以启动
- web 能请求到一个稳定的 bootstrap 响应
- UI 已经明显脱离旧 Kimi 暗色原型
