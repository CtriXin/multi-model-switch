# MMS / CRS / Relay 命名规范

## 目标

这份文档用于统一以下几层的命名：

- `MMS provider`
- `CRS account`
- `CRS api key`
- `newapi / relay` 入口

目标不是一次性重建链路，而是在**不影响现有运行**的前提下，把显示名、说明和职责表达收干净。

## 核心原则

### 1. 先改显示层，不改稳定标识

本轮默认只允许修改：

- `provider.name`
- `provider.note`
- `CRS account name`
- `CRS api key name`
- `description / tags`
- `enabled / disabled` 状态

本轮默认不改：

- `provider.id`
- `CRS api key secret`
- `group id`
- `route` 语义
- `sticky` / session key 语义

原因：

- `MMS`、`model-routes.json`、统计文件、部分脚本和默认入口都稳定引用 `provider.id`
- `CRS` 调用链实际依赖的是 `api key secret`，不是 key 的显示名

### 2. 语义优先，别名最少

名字应该表达：

- 它是什么平台
- 是 direct 还是 relay
- 来源是 company 还是 xin
- 是 dedicated 还是 group
- 是否属于 legacy / 实验

不要把历史昵称、测试痕迹、模型名、服务器名都堆进一个名字。

### 3. 同一概念跨层尽量同名

如果一条链路本质上是“主 relay 入口”，那么：

- `newapi token`
- `CRS key`
- `MMS provider.name`
- 文档里的口径

应该尽量共享同一主名字，而不是每层都重新起一个别名。

## 命名前缀

### 平台前缀

- `cl` = Claude
- `op` = OpenAI / Codex
- `gm` = Gemini

### 路径前缀

- `direct` = 直连目标服务
- `crs` = 直连 CRS
- `relay` = 经由 newapi / relay 再到 CRS
- `legacy` = 历史入口、待下线、默认不使用

### 归属前缀

- `company` = 公司资源
- `xin` = 你自己的资源

### 账号类型后缀

- `oauth` = 官方 OAuth 账号
- `dedicated` = 独享
- `group` = 账号池

## 推荐命名格式

### MMS provider.name

格式：

`<path>-<platform>-<owner>`

示例：

- `relay-main-xin`
- `crs-op-company`
- `crs-cl-company`
- `crs-cl-b2-xin`
- `crs-cl-fish-xin`
- `crs-op-group-xin`
- `relay-op-company`
- `legacy-op-company-svip`
- `kimi-direct`
- `minimax-direct`
- `glm-direct`
- `bailian-direct`

说明：

- `main` 只用于默认主入口
- `company54` 这类模型版本不建议放进主名字，优先写在 `note`

### CRS account name

格式：

`<platform>-<scope>-<owner>`

示例：

- `cl-dedicated-b2`
- `cl-group-fish`
- `op-dedicated-apple`
- `op-group-turkey`
- `op-group-christopher`
- `op-group-paul`
- `op-group-julie`
- `op-group-ethan-pro`

说明：

- `owner` 优先取稳定识别名，不要直接依赖邮箱全称
- 若邮箱就是唯一识别，也可以保留邮箱，但风格要统一

### CRS api key name

格式：

`<path>-<platform>-<scope>`

示例：

- `relay-main`
- `crs-cl-b2`
- `crs-cl-fish`
- `crs-op-turkey`
- `legacy-test-disabled`
- `legacy-gateway-disabled`

说明：

- key 名字表达“用途”，不要表达 secret 内容
- 如果后续要 rotate secret，新 key 也应沿用同一命名语义

### 本地 OAuth 账户名

格式：

`<platform>-<owner>-oauth`

示例：

- `claude-b2-oauth`
- `claude-fish-oauth`
- `codex-apple-oauth`

失效账号可以直接删除，不建议长期保留历史废名。

## 当前建议映射

### MMS provider.name

- `newapi` -> `legacy-relay-company`
- `kimi-codingplan` -> `kimi-direct`
- `glm-en` -> `glm-direct`
- `bailian-codingplan` -> `bailian-direct`
- `minimax-cn` -> `minimax-direct`
- `xin` -> `relay-main-xin`
- `private` -> `crs-cl-b2-xin`
- `companycrs` -> `crs-cl-company`
- `companycrsopenai` -> `crs-op-company`
- `privateopenai` -> `crs-op-group-xin`
- `newapi5-4` -> `relay-op-company`
- `newapi5-4-svip` -> `legacy-op-company-svip`
- `fishcrs` -> `crs-cl-fish-xin`

### CRS api key name

- `new-api-relay` -> `relay-main`
- `独享` -> `crs-cl-b2`
- `fish-direct` -> `crs-cl-fish`
- `turkey-openai-direct` -> `crs-op-turkey`
- `test` -> `legacy-test-disabled`
- `new-api-gateway` -> `legacy-gateway-disabled`

## 对 hive / MindKeeper / Sparkring 的影响边界

### 不会受影响的前提

如果本轮只做下面这些修改，则默认不会影响：

- `hive`
- `MindKeeper`
- `MMS` 现有路由
- `Sparkring` 已经接入的接口

安全前提是：

- 不改 `provider.id`
- 不改 `model-routes.json` 里的 `provider_id`
- 不改 `api key secret`
- 不改 `base_url`
- 不改 `route` 协议
- 不改 `newapi / CRS` 的真实绑定关系

### 会触发影响的动作

下面这些属于高风险动作，必须单独评估：

- 改 `provider.id`
- rotate 现有 `CRS api key secret`
- 删除仍被引用的 key
- 修改 `model-routes.json` 中正在使用的 `api_key`
- 替换 `newapi` 的 upstream 域名 / 端口
- 删除 `legacy` 入口但未完成切流

## 推荐落地顺序

### Phase 1

只改名字和说明：

- `MMS provider.name`
- `MMS provider.note`
- `CRS account name`
- `CRS api key name`

### Phase 2

只做状态整理：

- disable 历史 provider
- disable 历史 key
- 删除明确失效的本地 OAuth 账号

### Phase 3

最后才做切流：

- 更新 `model-routes.json`
- 更新 `credentials.sh`
- 更新 `newapi` upstream
- 替换 `company` 链路为 `xin` 或新机器链路

## 当前建议

就当前环境而言，推荐先执行“安全版重整”：

- 只改 `name`
- 只补 `note / description / tags`
- 不碰 `provider.id`
- 不换 `secret`
- 不删仍可能被引用的 key

这样可以先把界面、文档、排障口径收干净，再决定下一轮是否要真正切流。
