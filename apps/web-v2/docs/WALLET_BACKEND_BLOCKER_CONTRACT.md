# Wallet Backend Blocker Contract

## Decision

这个点必须现在修。

原因不是“体验优化”，而是前端无法正确区分：

- `余额耗尽`
- `token 无效`

如果不修，wallet / Lite / top-up 这条功能线只能做半成品演示，不能进入稳定测试。

## Required Backend Change

### Problem

当前 `ValidateUserToken()` 在 `RemainQuota <= 0` 时直接返回 error。

结果：

- auth middleware 直接 401
- billing API 无法读取零余额 token 的余额信息
- 前端只能拿到“无效令牌”，无法判定是否该进入 Lite mode 或弹充值

### Required Behavior

对 billing 只读接口，允许 `exhausted token` 通过认证。

最小要求：

- token 合法
- token 归属合法
- token 可读取
- 即使 `RemainQuota <= 0`，也允许访问 billing 查询接口

不允许：

- exhausted token 继续发起消费型 relay 请求

## Recommended Backend Options

### Option A

给 `ValidateUserToken()` 增加参数：

- `allowExhausted bool`

规则：

- 普通 relay / consume 路由：`allowExhausted = false`
- billing / dashboard 只读路由：`allowExhausted = true`

这是推荐方案，语义最清楚。

### Option B

给 billing 路由挂单独 auth middleware：

- 校验 token 有效性
- 不校验 `RemainQuota > 0`

这也能做，但后续权限语义容易分散。

## Required API Contract For Frontend

### 1. Billing Read

billing 路由在零余额 token 下必须返回 200，而不是 401。

前端依赖字段：

- `soft_limit_usd`
- `total_usage`

前端余额换算：

- `QuotaPerUnit = 500000`
- `SparkCoins = remain_quota / 500000`
- 若 billing 返回的是 `soft_limit_usd` + `total_usage`
  - 前端按：
  - `remain = soft_limit_usd - total_usage`

### 2. Error Semantics

消费型请求要保证下面的区分成立：

- `401 invalid_token`
  - 真正的 token 无效 / 不存在 / 鉴权失败
- `quota_depleted`
  - 合法 token，但余额耗尽
- `daily_quota_exceeded`
  - 风控日限额
- `rate_limited`
  - 限流

如果暂时不能在 relay 层返回标准 `quota_depleted`，至少 billing 查询必须可读，这样前端仍能通过余额=0 进入 Lite mode。

## Frontend Dependency

前端在以下功能上依赖此修复：

- Spark 币余额展示
- 零余额自动进入 Lite mode
- premium capability 拦截
- top-up trigger
- `余额不足` 与 `token 无效` 的差异化提示

## Test Cases Backend Must Pass

- [ ] normal token + positive balance => billing 200
- [ ] valid token + zero balance => billing 200
- [ ] invalid token => billing 401
- [ ] valid token + zero balance => relay consume returns `quota_depleted` or equivalent blocked result
- [ ] valid token + daily limit exceeded => stable `daily_quota_exceeded`
- [ ] valid token + rate limit => stable `rate_limited`
