# Pilot `/btw` handoff（2026-09-14 独立复核）

状态：`/btw` 已在 `origin/dev`（PR #209、#221 合入）。本次复核与最小补充在分支 `claude/pilot-btw-closeout-dev`（基于 `origin/dev` 065cf856），未发布、未合并、未 push。

## 关于分支 `codex/pilot-btw-closeout`

- 该分支落后 `origin/dev` 278 个提交。它的 `/btw` 代码（`mms_web/side_questions.py`、`mms_web/side_question_model.py`、`apps/mms-web/src/SideQuestions.tsx`、`side-questions.ts`、四个测试文件、fixture）与 `origin/dev` 逐字相同；`session_actions.py`、`api.ts`、`API.md`、回归报告则是 dev 更新（dev 多了真实并发 smoke「补充三」）。
- 分支的 `mms_web/server.py` 是 K3 cherry-pick 时整文件带入的，import 了本分支不存在的 `remote_access` / `cli_sessions` / `ui_preferences`。`python3 -c "import mms_web.server"` 直接 ImportError，三个 HTTP 层测试失败。该分支本身启动不了 Pilot，不应再作为交付载体。
- 它的 `build(web): ship the /btw bundle` 提交只新增了 `mms_web_static/assets/index-CjtuiNVv.js`，没有改 `index.html`，安装版仍指向不含 `/btw` 的旧 bundle。`origin/dev` 的 bundle（`index-DY6M0OD5.js`）已含 `/btw`。
- 分支独有内容只有 heartbeat 七行（b236f397）和本文档，两者都在新分支重做，见下。

## 与 Claude Code 官方 `/btw` 的差距

| 维度 | Claude Code `/btw` | Pilot `/btw`（dev + 本次） | 判断 |
|---|---|---|---|
| 主任务不中断、不排队 | 是 | 是：不进 transcript、follow-up queue，不调 driver，不改 model/provider/channel/thinking；有真实并发 smoke | 接近 |
| 用同一模型与凭据 | 是 | 是：从 session 私有 `resume.json` 读回路由，Anthropic-first，不探测 endpoint | 接近 |
| 上下文 | 当前对话全文 | 状态快照 + 最近至多 6 轮 user/assistant 文本摘录（每轮 ≤1200 字、合计 ≤5000 字）；无工具输出正文、无文件、无 thinking | 主要短板 |
| 运行时原生性 | 宿主内置 | Pilot host 旁路请求，Pi 无内置 side-request | 缺口 |
| 历史、取消、幂等、脱敏、重启 | 是 | 是 | 接近 |

## 1. 上下文能安全增加到哪里

- 本次新增 `recentTurns`：只读 `session.events`（driver 已镜像、按 session secrets 脱敏后的事件），取最近 user/assistant 文本；不读 `~/.config/mms*`、Claude 配置、API key，也不读 Pi 的 `conversation.jsonl`。
- 旁问行新增 `contextScope {recentTurns, totalTurns, truncated}`，写明摘录覆盖了几轮、是否截断；system prompt 同步告知模型「摘录可能截断，材料里没有的就说不知道」。
- 仍不安全的：整段 transcript（可能极大、含工具输出与文件内容）；Pi compaction 后的真实上下文（只能通过 RPC `get_messages` 或 extension 取得，见下）。

## 2. Pi 是否有独立 side-request 能力

依据本机安装的 `@earendil-works/pi-coding-agent` 0.85.1 的 `docs/rpc.md`、`docs/extensions.md`、`examples/extensions/summarize.ts`：

- RPC 没有 side-completion 命令。`prompt` / `steer` / `follow_up` 都进入主 agent loop；`get_messages`、`get_entries`、`get_state`、`get_session_stats` 只读。
- Extension API 有一条可行但非内置的路径：RPC `prompt` 发 `/命令` 时，extension command「executes immediately even during streaming」；handler 内可用 `ctx.modelRegistry.complete(model, {messages}, options)` 发一次独立 completion（`summarize.ts` 正是这样做），`ctx.sessionManager.buildContextEntries()` 能拿到压缩后的完整上下文；只要不调 `sendMessage` 就不进 transcript。
- 这条路径的 host API 缺口：结果只能经 `extension_ui_request`（notify / custom UI）回传，没有结构化 RPC 响应；没有 RPC 级取消；与主任务共用 stdin 通道、进程和 auth；extension 需由 MMS 打包注入。因此 `/btw` 目前仍由 Pilot host 执行，没有伪造原生支持。

## 3. 主任务并发隔离

- `ask_side_question` 只在 `session.lock` 内写 `side_questions` / `btw_idem` 并 persist；不碰 driver、`pending_prompts`、`meta.queue`、model/channel/thinking；completion 在独立线程。
- backend 测试断言 `last_sequence` 与 driver `prompts` 不变；真实并发 smoke 见回归报告「补充三」。
- 唯一共享点：HTTP POST 走 server 的 `mutation_lock`，与其他 POST 串行（毫秒级），这不是 follow-up queue。

## 4. `heartbeatAt` / `lastEventAt`

- 分支版本两者是同一个值，只在 transcript 写入时刷新（含宿主 notice 与用户消息），而 Pi 的 activity / state / approval 回调不刷新，名不副实。
- 本次改为：`lastEventAt` = 最近一次 transcript 写入；`heartbeatAt` = 最近一次 driver 从 Pi 进程送达的回调（event、activity、proto state、approval、exit），没有收到过回调时为 `null`。两者随 session 持久化并在重启后按记录恢复；没有百分比或推测进度。前端尚未消费这两个字段。

## 5. 仍有遗漏的地方

- 前端：只读 `cli:` 会话的 Composer 整体禁用，旁问也发不出（既有边界）；`heartbeatAt`、`contextScope` 未展示，卡片仍写「状态快照」。本次未改前端，避免重建 bundle。
- 取消只丢弃迟到答案，不会中断已发出的 HTTP 请求，token 仍会消耗。
- 未做真实 Pi 会话的 runtime 回归；OpenAI-only 路由仍只有 stub 覆盖。

## 验证（本次实际执行）

- `tests/test_mms_web_btw_context.py`（新，4 条）、`tests/test_mms_web_session_heartbeat.py`（新，2 条）通过。
- `tests/test_mms_web_btw_backend.py`、`..._route_model.py`、`..._contract.py`、`tests/test_mms_web_sessions_service.py`：75 passed。
- `python3 -m pytest tests/ -k mms_web`：570 passed, 2 xfailed（修正断言前仅本次新测试失败一次）。
- `python3 scripts/regression_fresh_user_gate.py --quick`：PASS（139 passed）。默认完整 gate 未跑。
- `node --test apps/mms-web/tests/side-questions.test.mjs`：16 passed（在旧分支 worktree 执行，前端源码与 dev 相同）。

## 下一步

- 若要展示 `contextScope` 与 `heartbeatAt`，改 `apps/mms-web/src` 后必须重建 `mms_web_static/`。
- 若要接 Pi 原生上下文，先在 MMS 注入的 extension 里实现 `btw` command + `ctx.modelRegistry.complete`，并为结果设计结构化回传与取消，再替换 host runner；隔离合同不变。
