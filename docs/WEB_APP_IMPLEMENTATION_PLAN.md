# MMS Web App 实施计划

## 1. 目标与产品姿态

这条线不是给现有 CLI 随便包一层页面，而是新建一条长期产品主线：

- `apps/web`：用户可直接使用的 web 前端
- `apps/runtime-api`：web 与未来 Tauri app 共用的本地服务层
- `packages/contracts`：前后端共享契约

产品姿态明确为：

- MMS 自己是主 app
- Claude Code / Codex / Gemini / gateway 是 execution targets 或 runtime adapters
- 不把第三方 CLI 当作 UI 宿主，也不做“另一个聊天壳”

## 2. 这次规划相比旧方案的补充与修正

相对仓库里旧的 `feature/app` 路线，这次有 5 个明确升级：

1. 现在就开始在独立 worktree 中落地，而不是继续停留在“merge 后再说”
2. 先建立 `web + runtime-api + contracts` 三层边界，再考虑 Tauri 包装
3. 首页不是纯 landing page，也不是纯聊天页，而是“承载页 + 工作台入口”混合结构
4. UI 目标是高效率多模型决策台，不照搬参考图，也不保留 Kimi 原型的暗色控制台风格
5. 把后续开发入口写进 `.ai/plan/current.md`，让新会话直接有 source of truth

## 3. 设计原则

### 3.1 选择更快

- 模型、provider、account、模式切换必须是就近操作，不藏到深层弹窗
- `Chat / Discuss / Handoff / Session` 是一级动作，不做长路径跳转
- 已选模型和当前来源状态要在输入区附近直接可见

### 3.2 展示更快

- 关键信息首屏可见，不把核心结果藏进 tab
- `Chat` 直接展示多列对比
- `Discuss` 直接 phase 化展示
- 右侧辅助面板只放高价值内容：preview、files、task、execution result、context assets

### 3.3 操作更快

- 首页进入后可直接开始
- 空配置时优先引导接入 provider/account，而不是让用户先理解一堆设置
- 继续、改模型、收敛、交付，都应是一跳动作

### 3.4 视觉更清楚

- 白底桌面工作台，不保留现有暗色主题
- 以浅灰层级、细边框、轻阴影为主
- 深色文字保证对比度，避免“浅灰字在白底不可见”
- 重点状态和主 CTA 用有限品牌色，不堆满渐变

## 4. 信息架构

主导航固定为：

- 首页
- Chat
- Discuss
- Sessions
- Models
- Settings

推荐工作台骨架：

- 左栏：workspace / recent sessions / pinned sessions / quick entry
- 中栏：当前主模式内容
- 右栏：可切换的 context panel（Preview / Files / Task / Git / Execution）

但不照抄参考图。MMS 的核心布局应围绕“多模型比较和讨论”展开，而不是普通单线程聊天。

## 5. 路由与页面定义

### `/`

- 产品定位与一句话价值
- 快速开始卡片：Chat / Discuss
- 最近会话
- 推荐模型组
- 当前 provider/account 状态
- 示例任务

### `/chat`

- 顶部：模式、provider/account、已选模型、快速预设
- 主区：多模型并排结果 lanes
- 底部：输入框与附件入口
- 次级动作：continue、change models、converge、handoff、restart、save

### `/discuss`

- 顶部：任务、已选模型、cost/tier 提示
- 主区：Phase 1 / Phase 2 / Phase 3
- 强调 synthesizer final 和 handoff brief
- 次级动作：followup、handoff、convert to chat、restart、save

### `/sessions`

- recent / pinned / ephemeral 分类
- session detail
- 恢复、删除、pin、导出

### `/models`

- provider / account / model 分层视图
- 快速接入入口
- 模型可用性、来源、支持模式、推荐预设

### `/settings`

- app 偏好
- UI 偏好
- runtime 状态与诊断入口

## 6. 目录结构

```text
apps/
  web/
  runtime-api/
packages/
  contracts/
docs/
  WEB_APP_IMPLEMENTATION_PLAN.md
```

各目录职责：

- `apps/web`
  - Vue 3 + TypeScript + Vite + Pinia + Vue Router
  - 只依赖 `contracts` 和 HTTP/SSE client
- `apps/runtime-api`
  - FastAPI
  - 提供 bootstrap / models / sessions / chat / discuss / providers / accounts
  - 后续逐步封装现有 Python 逻辑
- `packages/contracts`
  - endpoint contracts
  - TypeScript/Python 共享数据模型说明
  - mock adapter 与 real adapter 的统一返回结构

## 7. Runtime API 边界

首批接口固定为：

- `GET /api/bootstrap`
- `GET /api/models`
- `GET /api/sessions`
- `GET /api/sessions/:id`
- `POST /api/chat/start`
- `POST /api/chat/continue`
- `POST /api/chat/converge`
- `POST /api/chat/handoff`
- `POST /api/discuss/start`
- `POST /api/discuss/followup`
- `POST /api/discuss/handoff`
- `POST /api/providers/connect`
- `POST /api/accounts/connect`
- `GET /api/config/status`

统一 session schema 至少包含：

- `id`
- `mode`
- `status`
- `originalTask`
- `selectedModels`
- `round`
- `branches`
- `activeBranchId`
- `chatLanes`
- `discussPhases`
- `finalSummary`
- `handoffBrief`
- `lifecycle`

## 8. Kimi 原型迁移策略

### 保留

- Vue 3 + Vite + Pinia 技术基线
- `chat / discuss / models / shared` 这组组件分类方式
- 一部分 arena 思路和输入区组织方式

### 重写

- 整体视觉体系：改为白底桌面工作台
- 首页：加入承载层与快速开始层
- 顶部导航：从纯模式切换改为产品级导航
- 模型选择：从深层 picker 改成高频快速切换
- 右侧上下文面板：补 Preview / Files / Task / Execution 价值
- session/sources/account 视图：按产品化方式重构

### 废弃

- 现有暗色主题 token
- 过于通用的 AI 控制台视觉表达
- 只适合纯原型的 mock-only 空状态文案

## 9. 开发阶段

### Phase 0：骨架

- 建目录
- 写当前任务 source of truth
- 固化实施计划
- 写 README 占位

### Phase 1：contracts + bootstrap

- 定义 contracts
- `apps/web` 起路由与 shell
- `apps/runtime-api` 起基础 server
- 前端先打通 bootstrap/models/sessions 读接口

### Phase 2：Chat v1

- lanes UI
- 输入区
- model quick select
- continue / change models / converge / handoff 动作

### Phase 3：Discuss v1

- phase timeline
- synthesis card
- followup / handoff
- discuss -> chat 回退链路

### Phase 4：Sources + Sessions

- provider/account 接入页
- 最近会话与 pin
- 导出/恢复

### Phase 5：Desktop readiness

- Tauri 适配边界
- 本地 runtime 发现与健康检查
- 文件/执行面板能力补齐

## 10. 新会话启动顺序

后续任何新会话进入本 worktree 后，先读：

1. `.ai/plan/current.md`
2. `docs/WEB_APP_IMPLEMENTATION_PLAN.md`
3. `docs/AGENT_GUARDRAILS.md`
4. `docs/APP_ROADMAP.md`

然后再开始实际代码实现。

## 11. 验收标准

- 有明确的 `apps/web`、`apps/runtime-api`、`packages/contracts`
- 新会话无需再补产品决策即可开始做代码
- 文档清楚说明：不内嵌 Claude Code/Codex 做宿主
- 文档清楚说明：UI 参考桌面工作台气质，但不照抄参考图
- 文档清楚说明：优先级是多模型工作流 > 模型接入体验 > 会话与素材管理
