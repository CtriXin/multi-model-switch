# Pilot `/btw` React/UI regression

- 时间：2026-09-11（Asia/Singapore）
- 任务范围：Pilot `/btw` 旁问的 React/UI 实现。slash picker、BTW 输入状态、独立卡片、生成中展开、完成后折叠、双击展开/收起、Esc、来源/错误/取消/未完成展示、typed API boundary。
- 基线：`origin/dev` `3dd28225`，其上 cherry-pick K3 的 backend 合同 `39a31335`（`feat(web): Pilot /btw side-question backend contract`）作为对接契约。
- 变更文件（全部在 `apps/mms-web/`）：
  - 新增 `src/side-questions.ts`（类型 + 纯规则）、`src/SideQuestions.tsx`（hook + 卡片 + 浮层）、`src/side-questions.css`、`tests/side-questions.test.mjs`
  - 修改 `src/api.ts`（四个 typed BTW 调用）、`src/types.ts`（`SessionDetail.sideQuestions`、两个 capability 字段）、`src/Composer.tsx`（`/btw` 命令与输入状态）、`src/App.tsx`（接线与渲染）、`src/main.tsx`（样式注册）
- 未修改：`mms_web/**` 任何 backend 代码、Grok、launcher/bridge、真实配置、账号或 OAuth 状态、`mms_web_static/` 发布包。

## 对接的 backend 契约

以 K3 交付为准，未自行改动：

- `POST /sessions/:id/side-questions {question, idempotencyKey?, sourceHint?}`
- `GET /sessions/:id/side-questions` → `{sideQuestions: [...]}`
- `GET /sessions/:id/side-questions/:btwId`
- `POST /sessions/:id/side-questions/:btwId/cancel`
- `SessionDetail.sideQuestions` 只读回放；`capabilities.sideQuestions` / `capabilities.sidecarCompletion`
- 状态机 `prepared → accepted → running → completed|failed|cancelled|uncertain`

BTW 调用刻意不走 `mutate()`：那是主任务的单飞写路径且返回整个 `SessionDetail`。旁问必须能在主任务写入过程中发起，自带 `idempotencyKey`，只返回一行。

## 执行验证

```text
apps/mms-web $ npx tsc --noEmit
（无输出，通过）

apps/mms-web $ node --test "tests/*.test.mjs"
ℹ tests 30   ℹ pass 30   ℹ fail 0
（其中 side-questions.test.mjs 新增 14 条）

apps/mms-web $ npm run build
✓ built in 1.43s

$ python3 -m pytest tests/test_mms_web_btw_backend.py -q
18 passed in 0.66s
（确认 K3 backend 在新 dev 基线上仍然绿）
```

UI 读取的字段与真实 backend row 的对账（scratch 脚本，未提交；使用 `tests/test_mms_web_sessions_service.py` 的 in-process fakes，无子进程、无真实配置）：

```text
OK: every field the /btw UI reads is present, in both row sources
```

覆盖：`detail_view()` 带 `sideQuestions`；state 与 completion 两种来源的 row 都含 UI 解引用的 14 个字段；`routeSnapshot` 含 modelName/providerName/channel；`redactionSummary.secretsMasked` 存在；`usage.totalTokens` 可读；UUID 形状的 `idempotencyKey` 重放返回同一 `btwId`；detail 行与 list 行的 `btwId` 集合一致；主 transcript 事件数不变。

## 浏览器验证（ego-browser，preview 模式，未调用真实模型）

为了不在验证中启动真实 Pi 进程消耗用户 token，在工作树里临时给 preview 会话注入三条旁问记录，验证后已还原（`git diff src/preview.ts` 为空）。

| 验收项 | 结果 |
|---|---|
| slash picker 出现 `/btw` | `['/btw — 旁问，不打断当前任务']` |
| 空参数 `/btw` 进入旁问输入 | 横幅、placeholder `问一个问题，不打断当前任务…`、发送按钮 `发送旁问`；主任务 turn 数不变 |
| 生成中默认展开 | `running` 卡片 `aria-expanded=true`，含问题/来源/「主任务继续运行」说明 |
| 完成后默认折叠 | `completed` 与 `failed` 卡片 `aria-expanded=false`，折叠行显示回答或失败原因摘要 |
| 双击展开 | 双击已回答卡片后 `aria-expanded=true`，展开区显示来源 `Pilot 状态`、上下文 `r-6 状态快照`、路由 |
| 键盘可达 | 卡片行 focus 后 Enter 展开、Space 收起 |
| Esc 关闭输入并保留记录 | 横幅消失、回到普通 placeholder、三张卡片仍在、主任务 turn 数不变、已输入文字保留 |
| Esc 关闭浮层并保留记录 | `dialog[open]` 关闭后卡片数仍为 3 |
| 错误可见 | preview 下发起旁问显示 `预览不会调用本地服务。连接 MMS Pilot 后才能发起旁问。`，文字保留，未产生主任务消息 |
| 取消入口 | `取消旁问` 只出现在未完结卡片上 |
| 窄屏 390px | 无横向溢出（`documentElement.scrollWidth === innerWidth === 390`） |
| 深色模式 | 语义色正常，失败卡片红色左边界 |

## 未验证

- **真实 Pi 会话下的端到端旁问未跑**：需要创建真实会话并启动真实 Pi 进程。按 `AGENT.md` 与用户既有约束，未在验证中发送真实主任务消息。长任务运行 1 小时期间连发 3 条 BTW、审批等待下的 BTW、刷新/重启/升级后的状态保留，都只由 K3 的 backend 测试覆盖，没有经过真实浏览器端到端。
- **只读 sidecar 的成功路径没有真实模型验证**：当前 `sidecar_runner` 未注入，`capabilities.sidecarCompletion` 为 false，completion 类问题会 fail closed。UI 的成功渲染只用 fake runner 和 preview 数据验证过。
- **`mms_web_static/` 发布包未重建**。仓库约定要求 `apps/mms-web/src` 的改动与 `python3 scripts/build_mms_web_release.py --skip-install` 在同一个 commit 里；本次按任务边界「只修改 `apps/mms-web/src`」执行，所以 **合并前必须由集成方重建发布包，否则安装版 Pilot 不会带上这个功能**。
- fresh-user gate 未跑：本次没有改动任何 `.py` / `.sh`，该 gate 无法被本改动影响。
- `npm ci` 在 `apps/mms-web` 下报 EUSAGE（既有环境问题），本次用 `npm install` 装依赖；`package-lock.json` 未改动。

## 已知边界与残余风险

- **旁问卡片集中显示在 transcript 之后，而不是按时间插进 turn 之间。** 这是为了不改动 `Transcript.tsx` 的 turn 分组逻辑（受保护的阅读链路）。新旁问出现在输入框上方，符合「最新在下」的阅读习惯；但同一会话里较早的旁问也会排在全部主消息之后。
- **单击只负责聚焦，不打开浮层。** 规范允许「聚焦或打开轻量查看」，选聚焦是为了彻底避免 click/dblclick 竞态。浮层由卡片上的「查看」按钮打开。
- **`Composer` 的 `disabled` 门没有为旁问放宽。** 主会话 `capabilities.send` 为 false（例如只读的终端会话）时，输入框整体禁用，旁问也发不出去。running / waiting 状态下 `send` 为 true，主用例不受影响。改这个门要动既有发送门控，超出本次边界。
- 旁问的本地副本与 session 轮询结果按「谁更靠后」合并，服务端在同级时胜出，因此两条轮询都不会把已完成的回答退回「生成中」。这条规则有单测覆盖。
- Esc 退出旁问输入会保留已输入文字，此时它变成主任务草稿。横幅消失、placeholder 变回普通文案是唯一提示。
