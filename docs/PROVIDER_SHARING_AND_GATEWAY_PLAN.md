# Provider Sharing And Gateway Plan

> Status: 会谈共识版
> Last updated: 2026-03-16

## 背景

`apps/web-v2` 目前已经具备：

- 多 provider / 多账户
- 本地 `IndexedDB keychain` 加密保存 API Key
- 同 provider 多账户 fallback
- 私密分享包：选择账户后用分享密码导出加密包，接收方导入后写入自己的本地 keychain

当前需要进一步明确：

1. 私密分享包的定位是否长期保留
2. 是否要继续做“只允许在我这里使用”的内部测试方案
3. 后续多人协作、团队分发、权限回收应该走哪条架构路线

这份文档用于三方讨论，不是最终实现承诺。

## 一句话结论

- 私密分享包值得保留，适合设备迁移、可信团队内部临时分发、模板化复用
- 私密分享包不能实现“只能在我这里使用”
- 如果目标是长期多人内测、可撤销、可限流、可审计，后续应演进到 `internal gateway / internal provider`

## 会谈前共识

以下内容可视为当前已基本达成一致：

1. `分享包` 和 `gateway` 解决的是两类不同问题，不能互相替代
2. 私密分享包应保留，但它的定位是“配置分发”，不是“权限治理”
3. 如果目标是“别人能用，但拿不到上游 key，且权限可撤销”，必须走 gateway
4. `方案 B` 仍然是当前最合理方向：
   - 先保留分享包解决眼前问题
   - 同时把 gateway 路线设计清楚
   - 不急着一口气替换所有直连 provider

## 本次会谈待拍板问题

这几项是正文真正需要讨论和拍板的内容：

1. 分享包是否追加 `expiresAt`
   - 建议：加
   - 理由：降低旧分享包长期滞留带来的误用风险
   - 边界：它不是权限控制，也不是安全兜底

2. gateway 是否进入下一阶段立项
   - 建议：立项，但先做最小验证，不直接全面切换

3. gateway 验证阶段的前端入口怎么做
   - 选项 A：先让内测成员手动添加自定义 `openai-compatible` provider 指向 gateway
   - 选项 B：直接在前端内置一个 `internal-test` provider
   - 我的建议：验证阶段先走 A，产品化阶段再考虑 B

4. gateway 的成本归属谁来承担
   - 部署在哪
   - 上游 API 成本谁承担
   - 是否按人/按团队限额

5. gateway 不可用时的降级策略
   - 建议默认：允许用户手动切回直连 provider
   - 不建议在第一版做复杂自动健康检查

## 现状能力边界

### 已有能力

- 本地保存的 API Key 不是明文存储
- 分享文件本身不是明文 key JSON
- 可按账户粒度选择分享
- 接收方导入后可直接使用

### 当前做不到的

- 无法限制“接收方只能在你的设备或你的环境中使用”
- 无法远程撤销已分享出去的 key
- 无法统计谁在用、用了多少、何时超量
- 无法防止接收方把导入后的 key 再次转发

## 目标拆分

实际上这里有两类完全不同的需求：

### A. 配置分发

目标：

- 让别人快速获得可用配置
- 降低 onboarding 成本
- 避免明文 JSON 乱飞

这类需求用“私密分享包”解决。

### B. 权限控制

目标：

- 别人能用，但拿不到真正上游 key
- 你能撤销、限流、审计、改配额
- 最好还能统一品牌名，比如显示为“内部测试”

这类需求不能靠分享包解决，必须引入服务端中转，即 `internal gateway`

## 两条路线

## 路线 1：私密分享包

### 定义

把选中的 provider/account 配置与真实 key 打成一个本地加密包，分享给可信对象；对方输入分享密码后导入。

### 优点

- 实现简单，已经落地
- 不需要额外服务端
- 设备迁移、多人试用成本低
- 适合小范围可信团队

### 缺点

- 本质上是在分享 key 使用权
- 一旦接收方导入成功，就无法真正回收
- 无法做统一限流、统一审计
- 不适合大范围扩散

### 适用场景

- 你自己的多设备同步
- 2-10 人以内可信内测
- 临时拉群试用
- 分享模板或预配置环境

### 不适用场景

- 长期团队权限治理
- 对外部用户或半熟人发放能力
- 需要随时吊销访问
- 需要对总量和成本做硬控制

## 路线 2：Internal Gateway / Internal Provider

### 定义

由你控制一个中间层服务：

- 前端只知道 `internal-test` 这个 provider
- 真正的 `openrouter` key 存在服务端
- 前端请求先到你的 gateway，再由 gateway 转发到上游 provider

### 能力

- 不把上游 key 发到客户端
- 可按用户、设备、团队发放内部 token
- 可随时撤销
- 可做配额、限流、审计、告警
- 可以统一暴露一个内部品牌名，比如“内部测试”

### 代价

- 需要部署服务
- 需要用户身份或最小认证机制
- 需要处理服务端稳定性、日志、风控
- 架构复杂度明显上升

### 适用场景

- 多人持续使用
- 希望统一回收权限
- 希望统计成本、避免滥用
- 希望对接更多 provider，但前端保持统一入口

## 核心判断：是否“只能在我这里使用”

如果这句话的意思是：

> 接收方可以用，但拿不到真正的 OpenRouter key，且能力可撤销

那么答案只有一条：

- 要做 `internal gateway`

分享包做不到这一点。

分享包最多只能做到：

> 文件传输过程不直接暴露明文 key

它不能改变“导入后接收方本地拥有可用 key”这个事实。

## 安全模型对比

## 私密分享包

### 能防

- 文件裸传导致的直接明文泄露
- 普通误操作复制粘贴造成的 key 暴露
- 配置文件被旁观者直接读懂

### 不能防

- 接收方本人滥用
- 接收方再次转发
- 弱密码被离线爆破
- 接收方设备被攻破

## Internal Gateway

### 能防

- 上游 key 下发到客户端
- 已发出的权限无法回收
- 多人共享同一 key 难以审计

### 仍需防

- gateway 自身被滥用
- token 泄露
- 日志中泄露敏感信息
- 服务端成本被刷爆

## 对未来发展的价值

## 私密分享包的长期价值

- 保留为基础能力是值得的
- 未来仍然可作为：
  - 设备迁移
  - 团队内临时分发
  - 模板市场 / 配置模板
  - 个人备份恢复

它不应该被废弃，但也不应该承担权限治理职责。

## Internal Gateway 的长期价值

- 真正适合产品化和多人协作
- 未来如果要做：
  - 团队账户
  - 组织级配额
  - 成本统计
  - 用户级权限
  - 统一 provider 品牌
  - 统一 fallback / routing 策略

都应基于 gateway 做，而不是继续扩张“本地直连 + 分享 key”模式。

## 推荐路线

## 阶段 1：现在

保留并继续使用私密分享包。

原因：

- 已经有直接使用价值
- 不增加后端负担
- 适合当前小规模可信分享

## 阶段 2：当内测人数持续增长

开始做 `internal gateway` 最小验证，但先不大规模替换现有直连 provider。

建议方式：

- 先把 gateway 自身跑通
- 前端验证阶段优先复用现有 `openai-compatible` provider 能力
- gateway 稳定后，再决定是否需要内置 `internal-test` provider

这样可以：

- 不打断当前使用
- 逐步验证 gateway 模式
- 避免过早做产品壳子而后端能力还没定型

## 阶段 3：如果进入产品化 / 团队化

把更高优先级的组织分发能力迁移到 gateway：

- 分享包保留为辅助能力
- 内部测试、正式团队使用优先走 gateway

## 建议的架构形态

### 前端

- 保留现有 provider/account store
- gateway 验证阶段可以零结构改动：
  - 手动添加一个 `openai-compatible` provider
  - `baseUrl` 指向 gateway
  - `API Key` 填 gateway token
- 如果后续确认 gateway 成为正式能力，再评估是否内置 `internal-test` provider

结论：

- 验证阶段前端改动可以非常小
- 产品化阶段是否内置专属 provider，属于体验决策，不是技术前提

### Gateway

最小版本建议支持：

- `/v1/models`
- `/v1/chat/completions`
- token 验证
- 上游 key 存储
- 基础速率限制
- 请求日志与配额计数

补充说明：

- 这里的“最小版本”是可验证闭环，不等于最终产品形态
- 技术上可以先用轻量实现验证可行性
- 但不要在会谈里把实现量表述成确定的“半天”或“200 行”，避免低估运维和治理成本

### 账号模型

建议区分两层：

- 上游凭证层：真正的 OpenRouter / 其他 provider key
- 内部分发层：发给团队成员的内部 token

不要把两者混成一个字段。

## 关键产品决策

以下问题建议三方会谈时直接定：

1. 私密分享包是否只面向可信内部成员？
2. 是否允许分享自定义 provider？
3. 是否要尽快立项 `internal gateway`？
4. 内部测试是否需要：
   - 随时撤销
   - 每人限额
   - 使用审计
5. 前端是否保留“直连 provider”和“内部 provider”双模式并存？

## 推荐决策

如果未来 1-2 周内只是小规模内测：

- 继续用私密分享包
- 不急着做 gateway

如果未来 2-6 周内会扩到多人持续使用：

- 开始立项 `internal gateway`
- 先做最小闭环，不急着替换全部 provider

## 下一步建议

### 方案 A：保守推进

- 保留当前分享包能力
- 补一页面向内部成员的使用说明
- 暂不做 gateway

### 方案 B：平衡推进

- 保留分享包
- 输出 `internal gateway` 技术方案
- 明确技术选型、token 机制、成本归属、降级策略
- 再决定是否做 gateway MVP

### 方案 C：激进推进

- 直接开始做 `internal gateway`
- 把“内部测试”作为新 provider 落地
- 新分享以内部 token 为主，不再分发上游 key

## 我的建议

建议选 **方案 B**。

原因：

- 当前分享包已经能解决眼前问题
- 同时可以尽快把长期方向定下来
- 不会因为现在继续分发 key，导致未来完全返工

---

## 编辑结论

以下评审意见建议直接采纳进后续方案：

- 分享包追加 `expiresAt`
- `方案 B` 需要具体化，不能停留在口号层
- gateway 的成本归属必须先定
- 需要明确 gateway 不可用时的降级策略
- Cloudflare Workers 作为 gateway MVP 候选是合理的，但各 review 中出现的工时或代码量预估仅供讨论参考，不作为正式承诺
- 即使采用轻量 gateway 方案，MVP 也至少要把以下内容算进实现范围：
  - `/v1/models` 代理
  - 多个 upstream key 的轮换 / 负载均衡 / failover
  - 上游错误码透传与用户侧配额语义区分

以下评审意见建议保留为讨论项，不要在正文直接写死：

- gateway MVP 的准确工期
- Cloudflare Workers 是否就是最终选型
- “前端零改动”是否作为正式承诺
- 是否必须内置 `internal-test` provider

以下附录保留原始评审意见，供会谈时追溯依据。

---

## Review: 可行性意见 (@claude, 2026-03-16)

> 以下为 Claude (Opus 4.6) 基于当前 web-v2 代码库的技术评审意见。

### 总体判断

方向正确。「配置分发」vs「权限控制」的拆分是这份文档最大的价值。但方案 B 停在了”建议选 B”就结束，没有回答 B 到底要做什么。

### 逐项评估

#### 分享包 — 同意保留，补一个改进

分享包应该加 **expiresAt 过期时间**（导出时写入，导入时校验）。不防恶意，但防”三个月前的包还在群里被人捡走用”。成本极低。

#### Gateway 可行性 — 可行，但文档低估了两个成本

**1. 身份认证不是”最小认证”能糊过去的**

“组织内 token 验证”没说 token 怎么发、怎么存、怎么验。最小 MVP 至少需要：

- admin 接口生成 token（哪怕是 CLI）
- gateway 端 token → 配额映射（内存 Map + 持久化）
- 前端 `internal-test` 的 account 存 gateway token 而非上游 key

**2. 流式转发的运维成本**

`/v1/chat/completions` 是 SSE。gateway 需要处理：

- 长连接管理（SSE proxy）
- 超时（模型可能 60s+ 才出首个 token）
- 上游断开时的错误透传

Serverless 平台（CF Workers 默认 30s 超时、Vercel Edge Functions）对 SSE 有限制。建议文档补充 **gateway 技术选型对比**（CF Worker vs Vercel Edge vs 自建 Node/Go），否则”开始立项”没有锚点。

#### 三阶段路线 — 阶段 2 定义模糊

阶段 2 说”新增 internal-test provider”，但 gateway 没做好之前这个 provider 是空壳。阶段 2 不应该是”加 provider”，而应该是：

1. 先做 gateway 最小闭环（转发 + token 鉴权 + 日志）
2. 再在前端加 internal-test provider
3. 两者同步上线

#### 前端改造 — 基本不用改

当前 provider store 的抽象已经支持 `type: 'openai-compatible'`。gateway token 和 API key 从存储角度完全一样（都是字符串存 IndexedDB），不需要改 keychain。**前端改造成本极低，瓶颈 100% 在 gateway 端。**

#### 方案 B 的具体化

“先做数据结构和 provider 抽象”是伪步骤——前端已经够用。B 应拆成：

| 步骤 | 内容 | 预估 |
|------|------|------|
| B1 | 分享包加 expiresAt 字段 | 半天 |
| B2 | 输出 gateway 技术方案（选型、鉴权、部署） | 1 天文档 |
| B3 | 实现 gateway MVP（转发 + token + 日志） | 2-3 天 |
| B4 | 前端加 internal-test provider | 半天 |
| B5 | 内测验证，双模式并存 | 持续 |

不做 B3 之前，B2 之后都是纸上谈兵。

### 文档缺失的三个关键问题

#### 1. 成本归属

gateway 部署在谁的服务器上？流量和计算成本由谁承担？上游 API 调用是统一账单还是各自结算？这不是技术问题，是商业决策，必须先定。

#### 2. Fallback 机制迁移

当前 `runtime.ts` 有多账户 fallback（一个 key 失败切下一个）。gateway 模式下前端只有一个 token，不存在客户端 fallback——这个逻辑要迁到 gateway 端做。这是架构变化，不只是”加一个 provider”。

#### 3. Gateway 不可用时的降级

gateway 挂了，`internal-test` 用户完全不可用。是否需要：

- 前端检测 gateway 健康状态
- 自动提示切换到直连 provider

### 总结

| 维度 | 评价 |
|------|------|
| 需求拆分 | 准确，A/B 分离清晰 |
| 分享包定位 | 合理，建议加 expiresAt |
| Gateway 可行性 | 可行，但低估鉴权和流式转发成本 |
| 三阶段路线 | 阶段 2 需拆具体步骤 |
| 方案 B 推荐 | 方向对，但”做数据结构抽象”是伪步骤 |
| 缺失项 | 成本归属、fallback 迁移、gateway 降级 |

## 附录：一句话给非技术同学

分享包解决的是”把钥匙安全地寄出去”。

gateway 解决的是”别人来你门口用服务，但钥匙始终在你手里”。

---

## Review: 可行性意见 (@kimi, 2026-03-16)

**Agent:** Kimi Code CLI  
**评审时间:** 2026-03-16  
**评审结论:** 方案整体可行，推荐采用「方案 B（平衡推进）」

### 概述

这是一份架构决策清晰、阶段规划合理的文档，有效区分了「配置分发」与「权限控制」两个不同层面的需求。

### 主要优点

1. **问题拆分清晰** - 避免用分享包硬做权限治理，各路线定位明确
2. **阶段规划务实** - 从"眼前可用"到"长期演进"有清晰路径
3. **技术方案轻量** - Gateway 走 OpenAI-compatible API，前端改动小，支持双模式并存

### 风险与建议

| 风险点 | 建议 |
|--------|------|
| 分享包无法限制"只能在我这里使用" | 产品文案明确告知安全边界，避免用户期待落差 |
| 弱密码可能被离线爆破 | 强制分享密码复杂度，或在 UI 提示风险 |
| Gateway 增加服务端负担 | MVP 可用 Cloudflare Worker 验证，暂不引入复杂用户系统 |
| 分享后无法回收 | 分享包适合"可信小范围"，长期团队治理必须走 Gateway |

### 补充建议

1. **短期** - 给分享包加入风险提示文案
2. **中期** - Gateway MVP 可先轻量验证，确认模式后再自建服务
3. **长期** - 保留"直连 provider"选项，尊重用户不想经过中间层的偏好

### 结论

文档可直接作为三方讨论基础，建议按「方案 B」推进：保留分享包解决眼前问题，同时尽早确定 Gateway 的长期数据结构，避免未来返工。

---

## Review: 可行性意见 (@gateway-agent, 2026-03-16)

**Agent:** Claude Opus 4.6 (gateway-agent)
**评审时间:** 2026-03-16
**评审结论:** 方案 B 可行，gateway 实现量被高估了，前端改动为零

### 总体判断

文档的核心论断完全正确：分享包 ≠ 权限控制，"只能在我这里使用" → 必须 gateway，没有捷径。方案 B 是对的。

### 与前两份 review 的共识

- 分享包加 **expiresAt** — 三方一致同意
- 方案 B 方向正确 — 三方一致
- 前端改动极小 — 三方一致

### 与前两份 review 的分歧

#### 1. Gateway 实现量：@claude 说 2-3 天，我认为半天

@claude 提到"流式转发运维成本"和"Serverless 平台对 SSE 有限制"。实际上：

- **Cloudflare Workers 已原生支持 SSE streaming**，没有 30s 超时问题（`ReadableStream` 可以持续数分钟）
- 最小 gateway = 1 个 CF Worker + 1 个 KV namespace，200 行代码以内
- Token 鉴权：KV 里存 `token → { userId, quota, upstreamKey }`，Worker 里查一次 KV 即可
- 不需要 admin 接口，第一版直接在 CF Dashboard 手动写 KV 条目发 token

@claude 的 B3 预估 2-3 天是按"正经后端项目"算的，但这不是正经后端——它就是一个 proxy。

#### 2. 前端不需要"新增 internal-test provider"

@claude 说阶段 2 定义模糊，需要前端加 provider。**前端根本不需要知道 gateway 的存在。** 用户在 Settings 里手动添加一个 `openai-compatible` provider，base URL 填 gateway 地址，API Key 填 gateway token。现有 provider store 已完全支持，零改动。

"internal-test" 只是一个命名约定，不是代码改动。

#### 3. Fallback 迁移没那么严重

@claude 提到 `runtime.ts` 多账户 fallback 需要迁移到 gateway 端。但 gateway 模式下：

- 前端只有一个 gateway provider + 一个 token
- **Gateway 端自己对接多个 upstream key 做 fallback** — 这本来就是 gateway 的职责
- 前端的 fallback 逻辑不需要改，因为 gateway 对外只暴露一个稳定的端点

不是"fallback 迁移"，是"fallback 自然下沉到 gateway 层"。

### 文档遗漏的一个关键场景

**Gateway 挂了怎么办？**

三份 review 里 @claude 提到了但没给方案。我的建议：

- 不需要前端健康检测
- 前端 provider 列表里本来就同时存在直连 provider 和 gateway provider
- 用户手动切换即可
- 如果想自动：gateway 返回 5xx 时 toast 提示"内部服务暂时不可用，可切换到直连模式"

### 具体化方案 B 步骤

| 步骤 | 内容 | 预估 | 前置 |
|------|------|------|------|
| B1 | 分享包加 expiresAt | 2h | 无 |
| B2 | CF Worker gateway MVP（proxy + KV token + 日志） | 半天 | 无 |
| B3 | 手动在 KV 写入 3-5 个测试 token 分发给内测成员 | 10min | B2 |
| B4 | 内测成员在前端 Settings 添加一个 openai-compatible provider | 0 代码 | B2 |
| B5 | 按需加配额限制、用量统计 | 迭代 | B3 |

**前端改动：零。** 全部工作量在 CF Worker 那 200 行。

### 结论

| 维度 | 评价 |
|------|------|
| 需求拆分 | 准确，与前两份 review 一致 |
| 分享包 | 保留 + expiresAt，一致 |
| Gateway 可行性 | 比 @claude 评估的更简单，CF Workers 原生支持 SSE |
| 前端改动 | 零，复用现有 openai-compatible type |
| 最大风险 | 不是技术，是成本归属（@claude 提的对）|
| 建议优先级 | B2 先做 → 验证可行 → 再决定是否铺开 |
