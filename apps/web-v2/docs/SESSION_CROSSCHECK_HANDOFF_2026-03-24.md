# 2026-03-24 交叉核对文档

本文档整理了从昨晚开始到当前时点的三条并行工作线：

1. `main` / 送审主线 / 我负责收口与审核风险排查
2. `feature/wallet-lite` worktree / 独立前端支付与 Lite 模式开发线
3. `newapi` backend / Spark 钱包接口与零余额 token 放行修复线

目标是给另一个 agent 做交叉比对，不追求漂亮摘要，追求状态清晰、边界清晰、已完成与未完成清晰。

---

## 0. 总背景与产品决策

### 0.1 用户目标

- 当前版本先走上架 / 送审 / MVP。
- `main` 分支必须尽量保持送审安全，不混入未完成、易出审核风险的支付逻辑。
- 钱包、Spark 币、Lite 模式、top-up、扣点、埋点，放到独立 worktree 开发和验证。
- 后续真实产品方向：
  - 用户可以使用你提供的统一能力入口；
  - Spark 币作为站内消耗单位；
  - 一些高级能力触发扣点；
  - 未来可支持用户自带 API key，但不作为当前送审主线阻塞项。

### 0.2 已形成的关键决策

- `main` 线目标是“可提测/可送审版本”。
- wallet / 支付 / Spark 币功能不应直接混入 `main`。
- 后端必须先解决“零余额 token 无法读取 billing/wallet”的阻塞点，否则前端 Lite 模式无法可靠联调。
- 前端不应长期依赖旧的 `/dashboard/billing/subscription` 方案计算余额。
- 如果后端已有真实 wallet API，前端不应再做本地持久 mock ledger 或本地送币逻辑。

### 0.3 与审核相关的整体判断

- 送审主线应优先做：
  - HTTPS / ATS / 外链安全 / 版本号统一 / 文案和 Logo 同步 / UI 壳层稳定。
- wallet 线应独立推进，成熟后再决定合入策略。
- 对“用户自带第三方 key 解锁全部能力”这一方向，存在审核风险；当前阶段不应作为送审主线卖点。

---

## 1. `main` / 送审主线

仓库：

- `/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2`

分支：

- `main`

已知主线提交：

- `097d96c` `feat(web-v2): sync app store brand and copy refresh`

### 1.1 主线需求

- 整理 App Store 上架图、品牌文案、Logo、样式。
- 同步 `worktree-app-store-launch` 上的 copy/logo/style 结果回 `main`。
- 排查送审风险，包括：
  - ATS 例外
  - HTTP IP 访问
  - 版本号统一
  - CSP
  - 外链白名单
- 保持 `main` 可提测，不掺入未完成 wallet 功能。

### 1.2 主线目标

- 形成可直接提测/送审的前端主版本。
- 将 App Store 品牌、文案、视觉调整同步到主线。
- 记录测试清单与后端阻塞契约，便于后续并行开发。

### 1.3 已完成结果

- 已将 app-store-launch 的品牌/文案刷新同步到 `main`。
- 已追加主线 release 测试清单文档：
  - [MAIN_RELEASE_TEST_CHECKLIST_0.5.1.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/docs/MAIN_RELEASE_TEST_CHECKLIST_0.5.1.md)
- 已追加 wallet 后端阻塞契约文档：
  - [WALLET_BACKEND_BLOCKER_CONTRACT.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/docs/WALLET_BACKEND_BLOCKER_CONTRACT.md)
- 已把本轮主线收口记录写入本地 release note：
  - [.ai/agent-release-notes.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/.ai/agent-release-notes.md)

### 1.4 我确认过的主线状态

- `npm run build`：通过。
- `npm run type-check`：不完全通过，但失败主要集中在仓库历史遗留模块，不是本轮送审收口新增问题。
- 2026-03-24 后续已清掉正式路由中的 screenshot/showcase 注入链路：
  - `App.vue`
  - `ChatView.vue`
  - `DiscussView.vue`
  - `MultiLifeView.vue`
  - `CaseReconstructionView.vue`
- 与上述截图 mock 残留直接相关的 `type-check` 报错已消失；剩余失败集中在 `story-lite`、`DailyChallenge`、`StoryLive`、`multiLife` 等历史模块。

### 1.5 主线上当前仍存在的未提交工作

以下内容在我上一次审阅时处于“已修改但未提交”状态：

- [provision.ts](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/services/provision.ts)
  - `APP_VERSION` 从 `0.3.5` 调整到 `0.5.1`
- [App.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/App.vue)
  - 修了 sidebar 本地状态
  - 去掉错误挂载的 `IOSModelSheet`
- [AdvisorsV2View.vue](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/src/views/AdvisorsV2View.vue)
  - 修了头像 `@error` 的类型安全 fallback

### 1.6 主线结论

- `main` 的定位仍然应该是送审与提测主线。
- wallet、支付、Lite、top-up 不应直接在当前状态下合入 `main`。
- 如果要继续推进提测，应优先按 [MAIN_RELEASE_TEST_CHECKLIST_0.5.1.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2/docs/MAIN_RELEASE_TEST_CHECKLIST_0.5.1.md) 跑完整确认。

---

## 2. `feature/wallet-lite` worktree / 前端支付线

worktree 路径：

- `/private/tmp/mms-wallet-lite-worktree/apps/web-v2`

分支：

- `feature/wallet-lite`

已知 worktree 提交：

- `dfb7bfb` `feat: add wallet sync and lite mode gating`

### 2.1 worktree 的原始需求

- 做 Spark 钱包、余额展示、Lite 模式、top-up、扣点、埋点。
- 先打通前端链路，后端接口不完整的部分先留口子。
- 重要扣点场景：
  - 聊天深度模式
  - 锦囊 / Advisors
  - 创意实验室（第 5 次后）
- 余额不足时触发 top-up。
- 未来支持分享，但当前只需先留口子。

### 2.2 worktree 的中期目标

- 基于 Sparkring provider 显示钱包余额。
- 零余额时自动进入 Lite 模式，仅允许基础免费模型。
- 支持 mock top-up 流程。
- 对关键付费点埋点，便于观察真实使用场景和转化漏斗。

### 2.3 我审过的 worktree 文件范围

- [wallet.ts](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/services/wallet.ts)
- [app.ts](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/stores/app.ts)
- [constants/wallet.ts](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/constants/wallet.ts)
- [TopupSheet.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/components/shared/TopupSheet.vue)
- [analytics.ts](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/services/analytics.ts)
- [ChatView.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/views/ChatView.vue)
- [DiscussView.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/views/DiscussView.vue)
- [InteractiveLabView.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/views/InteractiveLabView.vue)
- [AdvisorsV2View.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/views/AdvisorsV2View.vue)
- [IOSModelSheet.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/components/shared/IOSModelSheet.vue)
- [ModelChipBar.vue](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/components/chat/ModelChipBar.vue)
- [chat.ts](/private/tmp/mms-wallet-lite-worktree/apps/web-v2/src/stores/chat.ts)

### 2.4 我实际做过的验证

- 在 `/private/tmp/mms-wallet-lite-worktree/apps/web-v2` 执行：
  - `npm run build`：通过
  - `npm run type-check`：失败

### 2.5 我给出的主要 review 结论

#### 2.5.1 初版结论：该 worktree 不能直接作为可联调基线

当时的主要问题如下：

- 钱包余额仍直接打旧接口 `/dashboard/billing/subscription`。
- `balance` 计算逻辑与真实后端契约不一致。
- `deduct()` 与 `mockTopupSuccess()` 只是改本地状态，再刷新会被后端余额覆盖。
- `Discuss` 的深度模式没有真正接入扣点。
- `App.vue` 仍然落后于 `main`，导致 type-check 中有明显壳层集成错误。
- `trackDeductTriggered()` 虽已定义，但没有被实际调用。
- `INITIAL_GIFT_BALANCE = 10000` 只定义了常量，没有真正落地。

#### 2.5.2 我明确反对的后续方案

另一个方案提出过：

- 用 `localSparkDelta` + `localStorage` 做本地持久 mock ledger
- 前端本地发 10000 初始赠送
- 余额 = 服务端余额 + 本地 delta

我明确反对，理由如下：

- 后端既然已经补了真实 wallet API，前端再做本地账本会造成双账本分叉。
- localStorage 送币不可控，清缓存即可重领，跨设备不一致。
- 这种做法会让联调和后续真实支付接入非常混乱。

### 2.6 我给出的 worktree 正确方向

我后面给 worktree agent 的正确修复方向是：

1. 前端停止依赖旧 billing 余额方案。
2. 直接切到新后端 wallet API：
   - `GET /v1/wallet/balance`
   - `GET /v1/wallet/usage`
   - `POST /v1/wallet/preview-consume`
   - `POST /v1/wallet/consume`
   - `GET /v1/wallet/topup/packages`
   - `POST /v1/wallet/topup/create-order`
   - `POST /v1/wallet/topup/mock-success`
3. 不做本地持久 mock ledger。
4. `Discuss full depth` 真正接入扣点与 top-up。
5. `Chat` / `Advisors` / `Lab` 继续统一走 preview/consume。
6. `TopupSheet` 改为以后端 package 列表为准。
7. `App.vue` 对齐 `main`，解决陈旧壳层错误。
8. 补齐 `deduct_triggered` 漏斗埋点。

### 2.7 我对 worktree 当前状态的结论

- 该线有价值，但当前不应直接 merge 到 `main`。
- 旧版本实现是“可 build，但不可作为真实钱包联调基线”。
- 正确路径是：接新 wallet backend，放弃前端本地账本方案。

---

## 3. `newapi` backend / 钱包接口线

后端仓库路径：

- `/Users/xin/auto-skills/CtriXin-repo/newapi`

### 3.1 后端最初阻塞点

我和你确认过的关键阻塞点是：

- `ValidateUserToken()` 在 `RemainQuota <= 0` 时直接报错。
- 这导致：
  - 零余额 token 查 billing 返回 401
  - 前端无法区分“余额为 0”与“token 无效”
  - Lite 模式与 wallet 引导无法可靠实现

### 3.2 我定位过的关键后端文件

- [model/token.go](/Users/xin/auto-skills/CtriXin-repo/newapi/model/token.go)
- [middleware/auth.go](/Users/xin/auto-skills/CtriXin-repo/newapi/middleware/auth.go)
- [router/dashboard.go](/Users/xin/auto-skills/CtriXin-repo/newapi/router/dashboard.go)
- [controller/billing.go](/Users/xin/auto-skills/CtriXin-repo/newapi/controller/billing.go)

### 3.3 我要求后端 agent 完成的目标

1. 让 billing 对零余额 token 可读。
2. 新增统一 wallet API。
3. 提供 preview/consume/top-up/mock-topup 链路。
4. 给出测试用例和测试结果。

### 3.4 当前我确认后端本地仓库里已落地的内容

#### 已存在的实现

- `TokenAuthReadOnly()` 已存在：
  - [auth.go](/Users/xin/auto-skills/CtriXin-repo/newapi/middleware/auth.go)
- dashboard billing 路由已改为 `TokenAuthReadOnly()`：
  - [dashboard.go](/Users/xin/auto-skills/CtriXin-repo/newapi/router/dashboard.go)
- wallet 路由已注册：
  - [relay-router.go](/Users/xin/auto-skills/CtriXin-repo/newapi/router/relay-router.go)
- `GetTokenUsedQuotaSince()` 已新增：
  - [log.go](/Users/xin/auto-skills/CtriXin-repo/newapi/model/log.go)
- wallet controller 已存在：
  - [wallet.go](/Users/xin/auto-skills/CtriXin-repo/newapi/controller/wallet.go)

### 3.5 后端 agent 声称的测试完成情况

后端 agent 报告了 12 个测试场景通过，包括：

- 正余额 token 可读 wallet balance
- 零余额 token 可读 wallet balance
- 零余额 token 可读 billing
- consume 在余额不足时返回 `402 quota_depleted`
- topup packages 可返回 5 档位
- create-order 可返回 `order_id`
- mock top-up 后余额更新

并声称已部署到：

- `82.156.121.141:4001`
- 容器：`new-api-custom`

### 3.6 我对后端代码的复审结论

我没有盲信“12 个测试通过”，而是继续对本地后端代码做了 review。

#### 我确认成立的正向结果

- 零余额 token 查询 billing 的核心阻塞点已解开。
- wallet API 路由与基础 handler 确实落库。

#### 我发现的关键问题

##### CRITICAL 1：`create-order -> mock-success` 链路在本地代码里是断的

文件：

- [wallet.go](/Users/xin/auto-skills/CtriXin-repo/newapi/controller/wallet.go)

问题：

- `create-order` 返回的是随机 `order_id`
- `mock-success` 却用 `req.OrderID` 去查 `topupPackageMap`
- `topupPackageMap` 的 key 是 package id：`p1/p6/p18/p68/p99`
- 不是随机订单号

结论：

- 如果前端按真实流程：
  - 先 `create-order`
  - 再拿返回的 `order_id` 调 `mock-success`
- 本地代码会直接“无效的订单号”

因此我判断：

- “测试通过”很可能不是按真实订单链路测的
- 或者部署实例与本地仓库代码并不完全一致

##### CRITICAL 2：写操作也挂在 `TokenAuthReadOnly()` 下

文件：

- [relay-router.go](/Users/xin/auto-skills/CtriXin-repo/newapi/router/relay-router.go)
- [auth.go](/Users/xin/auto-skills/CtriXin-repo/newapi/middleware/auth.go)

问题：

- `/v1/wallet/*` 整组使用 `TokenAuthReadOnly()`
- 这意味着：
  - `consume`
  - `create-order`
  - `mock-success`
  这些写操作也走宽松认证

`TokenAuthReadOnly()` 的注释写得很明确：

- 不检查状态
- 不检查过期
- 不检查额度

这适合只读接口，不适合写接口。

##### HIGH：`mock-success` 返回的 `balance_before` 不可信

文件：

- [wallet.go](/Users/xin/auto-skills/CtriXin-repo/newapi/controller/wallet.go)

问题：

- `BalanceBefore` 被硬编码成了 `0`

结果：

- 前端支付成功页 / 埋点 / 对账会拿到错误值

### 3.7 我无法独立复跑 Go 测试的原因

我尝试本地跑 Go 侧验证时，被两个环境问题阻断：

1. 当前本机 `go version` 是 `go1.20`
2. 后端仓库 [go.mod](/Users/xin/auto-skills/CtriXin-repo/newapi/go.mod) 要求 `go 1.22`
3. sandbox 还拦了 `~/Library/Caches/go-build` 写入

因此我对后端的判断是：

- 基于本地代码 review 的结论
- 不是“我在本机完整复测通过”的结论

### 3.8 我给后端 agent 的进一步修复方向

我给出的二次修复 prompt 目标是：

1. 修复真实 `order_id` 与 `mock-success` 的关联
2. 将 wallet 路由拆成：
   - 只读接口：可用 `TokenAuthReadOnly()`
   - 写接口：必须严格 auth
3. 修正 `mock-success` 的 `balance_before`
4. 保持“零余额 token 可读 billing/wallet”这一核心能力不回退

---

## 4. 我、worktree、backend 三条线的关系判断

### 4.1 当前最可靠的事实

- `main` 是送审主线，应保持相对干净。
- worktree 旧实现不能直接做真实钱包联调。
- 后端基础 wallet API 已经出现，但本地代码里还有明显逻辑缺陷。

### 4.2 当前正确的推进顺序

1. 先把 backend wallet API 修到真正可串单、写操作 auth 合理。
2. 再让 worktree 前端切到新 wallet API。
3. 在 worktree 完成：
   - 深度模式扣点
   - top-up
   - Lite 模式
   - package 同步
   - 埋点
4. 最后再评估是否、何时合入 `main`。

### 4.3 当前不建议做的事

- 不建议在前端做本地持久 mock ledger。
- 不建议把“初始赠送 10000”放前端 localStorage。
- 不建议当前就把 wallet 功能混入 `main` 送审主线。

---

## 5. 给 Claude 做交叉比对时，建议重点核对的点

### 5.1 主线核对点

- `main` 是否仍保持送审定位，没有混入钱包逻辑
- `097d96c` 之后是否还有未记录的关键改动
- `App.vue` / `provision.ts` / `AdvisorsV2View.vue` 的未提交状态是否仍存在

### 5.2 worktree 核对点

- 当前 `feature/wallet-lite` 是否仍在用旧 billing 接口
- 是否仍存在本地 mock 账本方案
- `Discuss full depth` 是否已经真实接入扣点
- `TopupSheet` 是否已以后端 packages 为准
- `type-check` 是否解决了 `App.vue` 壳层错误

### 5.3 backend 核对点

- `create-order -> mock-success` 是否已经真正按 `order_id` 串通
- wallet 写接口是否已从 `TokenAuthReadOnly()` 中拆出
- `balance_before` 是否已修正
- 部署实例代码是否与本地仓库一致

---

## 6. 当前一页结论

- `main`：定位正确，适合作为送审与提测主线，但仍需按 checklist 做完整人工确认。
- `worktree`：方向有价值，但旧实现不能直接作为真实 wallet 联调基线；必须改接新后端 wallet API。
- `backend`：核心阻塞点已被部分解决，但本地代码仍有两个重大缺陷：
  - `order_id` 链路不闭环
  - 写接口 auth 过宽

如果只用一句话概括当前状态：

> 主线可继续朝送审推进；钱包线不能直接合并；后端有基础但还没到“我愿意让前端直接压上去联调”的程度。
