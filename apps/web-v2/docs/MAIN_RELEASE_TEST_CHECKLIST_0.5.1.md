# Main Release Test Checklist v0.5.1

## Scope

- Branch: `main`
- Goal: current App Store / TestFlight candidate
- Excluded from this release:
  - Spark 币真实充值
  - 支付 SDK
  - 扣点闭环
  - 分享闭环

## Build Gate

- [ ] `npm run build` passes
- [ ] `npm run type-check` passes, or failures are confirmed as historical and unrelated
- [ ] iOS package installs successfully on simulator / device

## Smoke Flow

### First Launch

- [ ] cold start without white screen
- [ ] no immediate crash
- [ ] lands on expected first screen
- [ ] drawer / sidebar opens normally

### Setup

- [ ] [SetupGuide.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/SetupGuide.vue) opens
- [ ] “先试试看” path works
- [ ] “连接 API” path works
- [ ] brand header renders correctly
- [ ] no broken icon or missing asset

### Chat

- [ ] [ChatView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/ChatView.vue) opens
- [ ] model picker opens
- [ ] select at least one model
- [ ] send one message successfully
- [ ] response cards render
- [ ] retry / replace model entry does not break
- [ ] empty state copy and header copy render correctly

### Discuss

- [ ] [DiscussView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/DiscussView.vue) opens
- [ ] discussion flow can start
- [ ] no dead button in primary action path

### Advisors V2

- [ ] [AdvisorsV2View.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/AdvisorsV2View.vue) opens
- [ ] step 1 can select mode / scene
- [ ] step 2 can open model selection
- [ ] step 3 can select personas and submit
- [ ] committee result page renders

### Creative Lab

- [ ] [InteractiveLabView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/InteractiveLabView.vue) opens
- [ ] all visible lab cards can enter corresponding route
- [ ] no empty / broken page for visible entries

### Settings

- [ ] [SettingsView.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/SettingsView.vue) opens
- [ ] theme toggle works
- [ ] prefer free toggle works
- [ ] show home toggle works
- [ ] provider list expands / collapses
- [ ] no broken external link

## Navigation

- [ ] Sidebar brand area renders correctly
- [ ] mobile drawer brand area renders correctly
- [ ] labels are consistent:
  - 首页
  - 多问几家
  - 深度对质
  - 锦囊参谋
  - 创意实验室
  - 模型库
  - 设置

## Review Risk Sweep

- [ ] no production business URL uses raw HTTP
- [ ] no production business URL points to bare IP
- [ ] no visible unfinished “支付 / 充值 / 扣点”入口暴露到主路径
- [ ] no dead-end share入口暴露到主路径
- [ ] no screenshot / showcase query path can inject mock data into production routes
- [ ] no debug wording or mock-only wording in user-facing core path

## Known Current Release Position

- This release is positioned as a usable multi-model AI app with experience / BYOK entry.
- Wallet / Spark 币 capability is intentionally deferred to feature worktree and should not block this test round.

## Release Decision

Ready to submit when all items below are true:

- [ ] build passes
- [ ] install passes
- [ ] smoke flow passes
- [ ] no App Store obvious review blocker remains
