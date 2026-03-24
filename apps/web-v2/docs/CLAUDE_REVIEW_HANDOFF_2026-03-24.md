# Claude Review Handoff - 2026-03-24

## 当前目标

`main` 现在只服务于 iOS 送审 / 提测主线。

本轮边界：

- 保留“免费限额可直接体验”的主路径
- 不暴露 `好友模式` 概念
- 不把 `wallet / top-up / Spark 币支付` 前端主路径混入 `main`
- 继续让首装用户能拿到可用通道和模型

## 本轮已完成

### 1. 清掉正式路由中的 screenshot / showcase 注入

已移除以下文件中通过 query 灌 mock 场景的逻辑：

- [App.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/App.vue)
- [ChatView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/ChatView.vue)
- [DiscussView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/DiscussView.vue)
- [MultiLifeView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/MultiLifeView.vue)
- [CaseReconstructionView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/CaseReconstructionView.vue)

目标是让 production route 不再接受 screenshot/showcase query 注入 mock 数据。

### 2. 修回 SparkRing 通道可见性回归

中间一度误把“不要露出好友模式”处理成“把 SparkRing 通道一起藏掉”，这会让主线没有模型可用。

现已修正：

- [src/stores/provider.ts](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/stores/provider.ts)
  - `sparkring` 不再依赖 `mms-show-friends` 才进入 provider 列表
- [src/stores/app.ts](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/stores/app.ts)
  - `refreshModels()` 不再因 `showFriendsMode` 过滤掉 `sparkring`
- [src/views/SettingsView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/SettingsView.vue)
  - 设置页 provider 列表不再硬过滤 `sparkring`

当前正确语义：

- 不展示“好友模式”这个审核风险概念
- 但 `SparkRing` 作为送审版内建体验通道保留

## 额度语义

这个点请按下面理解，不要和 wallet worktree 混掉：

### 送审版当前语义

- 首装用户会自动走 [src/services/provision.ts](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/services/provision.ts)
- `POST /api/provision`
- 服务端按安装实例返回一个独立的初始化 key
- 注释里当前写的是：
  - default tier: `50 RMB quota`
  - max tier: `500 RMB quota`

也就是说，现在主线不是“共享公共通道”，而是“每个安装实例各自拿一个初始化额度”。

### 额度不足时当前前端表现

[src/services/api.ts](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/services/api.ts) 已对 NewAPI 的额度错误做映射：

- `daily_quota_exceeded` -> `今日额度已用完，明天 UTC 0 点重置`
- `pre_consume_token_quota_failed` / `quota_not_enough` -> `账户额度已耗尽，请联系支持申请更多额度`

当前主线表现是：

- 聊天/辩论里会出现“额度已用完/已耗尽”的错误提示
- `quota_not_enough` 不再是纯死胡同文案，而是会提示用户联系支持申请更多额度
- 但 `main` 不包含 wallet/top-up UI 主路径
- 真正的余额展示、Lite mode、top-up、consume gating 仍在独立 `wallet-lite` 线，不在这次送审主线里
- 上述文案成立的前提是后端继续稳定区分 `daily_quota_exceeded` 与 `quota_not_enough` / `pre_consume_token_quota_failed`

## 当前验证状态

- `npm run build` ✅
- `npm run type-check` ✅

本轮额外清掉了原先会影响可达实验室页面的类型错误：

- `src/features/play-modes/story-lite/mock.ts`
- `src/stores/dailyChallenge.ts`
- `src/stores/multiLife.ts`
- `src/stores/storyLiteV2.ts`
- `src/views/DailyChallengeView.vue`
- `src/views/StoryLiveView.vue`

这些页面当前都还在主路由 / 实验室入口中可达：

- `/challenge`
- `/story-lite`
- `/story-live`
- `/multi-life`

所以这轮把它们清绿是必要动作，不只是“顺手修类型”。

## 送审前必检补充

- 审核 / 演示安装实例要预置足够额度，避免审核员在首轮体验里直接撞到 `quota_not_enough`
- 后端必须继续稳定返回不同错误码：`daily_quota_exceeded` vs `quota_not_enough` / `pre_consume_token_quota_failed`
- `POST /api/provision` 至少要有设备 / IP 级基础限频，避免安装实例 provisioning 被刷穿
- visible lab entries 至少要做到“可进入、不白屏、不报明显 runtime 错误”，不要再把 type risk 当成不可达模块忽略

## 关于 Wallet Contract 文档

暂不建议归档 [WALLET_BACKEND_BLOCKER_CONTRACT.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/docs/WALLET_BACKEND_BLOCKER_CONTRACT.md)。

原因不是要把 wallet 合回 `main`，而是其中的错误码契约

- `daily_quota_exceeded`
- `quota_depleted` / `quota_not_enough`

仍然直接影响送审版当前的前端提示语义。

## 建议 Claude Review 重点

请优先 review 下面几类风险：

1. `main` 首装后是否一定能拿到可用通道和模型
2. 去掉 `好友模式` 概念后，是否还有任何地方错误地把 `sparkring` 隐藏掉
3. 正式路由是否还存在 screenshot/mock/showcase 可达注入点
4. “额度不足”是否已经能在主路径里给出可理解提示，而不是表现成坏掉或无模型
5. `provision` 的后端限频 / 防刷是否已经具备基本可上线约束

## 不要误做的事

- 不要把 wallet/top-up 直接合回 `main`
- 不要为了做余额提示而引入本地 mock ledger
- 不要重新把 `sparkring` 绑定回 `好友模式`
