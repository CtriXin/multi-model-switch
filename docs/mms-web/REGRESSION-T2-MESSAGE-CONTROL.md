# T2 消息控制 UI · 回归报告

- 分支：`claude/t2-message-control`，基于 `origin/dev` `a1348e3c`
- 日期：2026-09-11
- 范围：`apps/mms-web/src` 与 `apps/mms-web/tests`；未改 backend、BTW、Grok、`mms_web_static/` 打包产物或任何真实配置

## 1. 先确认的事实：Pi 真实 API

以本机 `@earendil-works/pi-coding-agent` **0.85.1** 的 `docs/rpc.md` 为准：

| 原生命令 | 语义 |
|---|---|
| `follow_up` / `prompt` + `streamingBehavior: "followUp"` | 当前 run settle 后送达 |
| `steer` / `prompt` + `streamingBehavior: "steer"` | 当前 assistant turn 的 tool calls 跑完、下一次 LLM 请求之前送达 |
| `clear_queue` | 整队清空，返回被清掉的 `steering` 与 `followUp` 文本 |
| `abort` | 真正结束当前一轮 |
| `queue_update` 事件 | 回报 `steering[]` 与 `followUp[]`，只有文本 |

**Pi 没有按条删除，也没有重排。** 官方给的做法是 `clear_queue` 之后由客户端把要保留的按顺序重新入队，这只能在服务端做。

## 2. 当前 backend 的缺口

`dev` 上的 `mms_web`：

- `drivers/pi_rpc.py:211` 把 `streamingBehavior` 写死成 `followUp`，没有 steer 通路。
- `sessions.py:541` 的 `send` 只读取 `text/skills/attachments/references/fileSelections`，没有 mode。
- `session_actions.py:143` 的 `control` 只有 `clearQueue` 全清。
- `runtime.queue` 是拼接后的 `string[]`，没有 id，也分不出 steer 和 followUp。

所以「立即引导 / 按条删除 / 顺序管理」在纯前端无法真实交付。本次不造假按钮，改为按能力位降级——这条正是 `docs/AGENT_GUARDRAILS.md` 里点名要避免的反例（界面选中值与实际执行值不一致）。

## 3. 本次消费的契约

契约原文写在 `apps/mms-web/src/message-control.ts` 顶部。backend 侧需要提供：

```text
POST /sessions/{id}/messages   { ..., mode: "direct" | "followUp" | "steer" }
POST /sessions/{id}/queue      { action: "remove", id }
                               { action: "move",   id, toIndex }   → SessionDetail

session.capabilities.steer         服务接受 mode: "steer"
session.capabilities.queueControl  服务提供 /queue
runtime.pending: [{ id, text, mode, createdAt? }]   有 id、可区分 mode 的队列
SessionEvent.mode                  这条用户消息当时以什么方式发出
SessionEvent.steeredBy: string[]   这条回答被哪几条引导改变（assistant 事件上）
```

`mode` 一律发送。三个 capability 与两个事件字段都是可选，缺失即视为不支持。与 `MESSAGE-CONTROL-SPEC.md` §5 的 API 草案一致，`/queue` 是草案没写、但 T2 的「删除/顺序管理」必须有的一条。

## 4. 交付的界面

| 范围项 | 落点 | 无 backend 时 |
|---|---|---|
| 发送方式选择 | composer 发送按钮旁的「发送方式」菜单：排队补充 / 立即引导 / 停止当前执行 | 菜单仍在，立即引导不出现，并写明「本地服务尚未提供立即引导」 |
| 送达状态与失败提示 | transcript 未执行消息区按 mode 给出「引导已排队 · 当前这批工具调用结束后送达」「排队中 · 本轮结束后送达」；取消、失败、结果待确认各自独立 | 退回原有「排队中，尚未执行」 |
| 被 steer 改变的回答标记 | 回答下方一行提示 | 不显示 |
| queue 查看 / 删除 / 顺序管理 | composer 上方「待发送队列 · 按送达顺序」，逐条带 mode 徽标与上移/下移/删除；运行详情面板复用同一组件 | 控制条整块不出现；运行详情面板保持原有只读列表与整队清空 |
| 刷新 / 恢复后的状态展示 | 队列、mode、送达状态全部来自服务端 `runtime` 与 events，页面不存本地状态 | 同上 |

两处刻意的取舍：

- 选了引导发送一次后自动回到排队补充。引导是一次性动作，不该粘住。
- 服务端没给 `steeredBy` 时，只按事件时间线推断「生成过程中收到你的引导」，绝不说成「被改变」。服务端给了才说「按你的引导调整过」。

## 5. 实际执行的验证

| 项目 | 结果 |
|---|---|
| `npx tsc --noEmit` | 通过 |
| `node --test` 逐个文件 | 5 个文件 35 项全过，其中新增 `message-control.test.mjs` 19 项 |
| `npm run build` | 通过 |
| 隔离 Pilot 实例 + ego-browser | 见下 |

浏览器验证在端口 8817 的隔离实例上进行，state root 在临时目录，`--static-root` 指向新构建的 `dist`，未碰用户自己的实例，未发送任何真实消息。

用临时 preview fixture（已还原，未提交）造出「运行中 + 队列两条 + 服务端确认的 steer」状态，实测：

- 队列控制条显示两条，mode 徽标分别是补充与引导，上移/下移/删除按钮在边界正确禁用。
- transcript 两条未执行消息分别显示「引导已排队 · 当前这批工具调用结束后送达」与「排队中 · 本轮结束后送达」。
- 回答下方显示「按你的引导调整过」。
- 发送方式菜单三项齐全，文案说明 steer 不截断已生成内容。
- 400px 宽度不产生横向滚动；配色只用现有 token，深色值均已定义。

用真实 fixture（等同今天的 backend）实测降级：队列控制条 0 个、引导入口 0 个、回答标记 0 个，发送按钮文案不变；运行中时菜单只给排队补充与停止，并写明引导不可用。

## 6. 没有做的事

- 没有重建 `mms_web_static/` 打包产物。这套 UI 在 backend 落地前不会产生任何可见变化，打包应留给真正发版的那个 commit。
- 没有跑 `scripts/regression_fresh_user_gate.py` 与 `scripts/ci_pytest_regression.py`。本次改动完全在前端 TypeScript 内，未触及 installer、config root、session、resume、HOME/XDG 隔离或任何 Python 路径。
- 没有用真实模型跑一次真正的 steer。backend 还没有这条通路，跑不了。

## 7. 残余风险

- **契约要对齐。** backend 由另一个会话实现。如果它选了不同的字段名或路径，这些界面会静默保持不可用（不会报错，也不会假装可用），但需要改前端对齐。`/queue` 尤其是本文件新增的，`MESSAGE-CONTROL-SPEC.md` §5 没写。
- **推断出的 steer 标记是启发式的。** 只在服务端不给 `steeredBy` 时生效，措辞已收敛成「生成过程中收到你的引导」，但仍可能在时间戳粒度粗的历史会话上落到相邻的那条回答。服务端补上 `steeredBy` 后这条路径就不再使用。
- **运行中会话的发送按钮 aria-label 从「加入队列」变成当前发送方式名。** 属于文案变化，没有改变任何发送行为。
