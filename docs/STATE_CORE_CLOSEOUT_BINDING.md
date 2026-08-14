# MMS × state-core Closeout Reference Binding (TB-46)

> Owner: MMS hook-parity / runner adapters.
> Contract source (read-only): `/Users/xin/auto-skills/CtriXin-repo/state-core/docs/runner-adapter-hooks.md`(ratified amendment `2026-06-14-runner-adapter-hooks-contract`)。
> state-core 仍唯一拥有 canonical state、done-gate 与 `completion_ref`;本 binding 不改 state-core 任何 schema/gate。

## 这是什么

把已 ratify 的 runner-adapter consume contract 接到第一个 MMS-managed reference binding:

- **Adapter** = `mms_state_core_closeout.py`(runner-neutral、stdlib-only)。调 `python3 <state-core>/src/cli.py closeout --task-id <id> --root <root>`,成功后用 `verify-completion` read-back `completion_ref`;非零退出保留原 phase 并输出 compact blockers。不直接读写 `task-state.json`,不调 `set --next-action/--runner/--owner`。
- **Reference binding** = `mms closeout` 子命令(`mms_core.main` 单一显式 dispatch 分支)。只在被显式调用时存在;不给任何 session 静默安装 global hard hook。

## 何时触发

**只有一种触发方式:显式调用。**

```
mms closeout --task-id <id> --root <repo-root> [--actor <name>] [--at <iso8601>]
# 或 standalone: python3 mms_state_core_closeout.py --task-id <id> --root <root>
```

由正式的 finish 入口(work-done / 显式 human 指令)在 agent 明确宣布任务结束时调用。调用即表示"请求进入 state-core done-gate",不表示任务已经 done——done 由 state-core done-gate 唯一裁决。

### root 可以是 launch / business root

`--root` 传的可以是真实 state root,也可以是只持有 `DIRECT_TO`/`MOVED_TO` 指针的 launch / business root(state-core `read` 会自动跟随指针)。这是合法用法——pickup.root 常是 launch repo。但当指针缺失、target 不存在、或显式 root 指错时,adapter 报 `status=error`(`reason=task_or_root_unresolved`,exit 4),**不**报 `blocked`(host-review P1-2)。

### task_id / root 解析优先级(fail closed)

1. 显式 argv(`--task-id` / `--root`)
2. env(`STATE_CORE_TASK_ID` / `STATE_CORE_ROOT`)
3. handover pickup pointer(`.agent.local/continuity/pickup.json` 的 `active.task_id` → `checkpoint.task_id`,及顶层 `root`)
4. 都找不到 → **fail closed**(exit 2),绝不从聊天文本猜。

state-core CLI 本身的定位:`--state-core-root` argv(authoritative,指向不存在的路径即 fail closed)> `STATE_CORE_ROOT` env > 祖先遍历(兼容主 checkout 与 `.worktrees/<slug>` 两种布局)。

## 何时绝不触发

- **普通 `Stop` / 回合结束 / 回答结束 / 进程退出 / `SessionEnd`** —— 一律不是任务完成。本 binding 不挂在任何事件 hook 上(`tests/test_state_core_closeout_binding.py::test_no_stop_or_sessionend_hook_is_wired_to_closeout` 静态断言 hooks/ 目录零引用)。
- **NSR 的 `Stop` 循环语义** —— NSR 是否继续循环与任务是否 canonical done 是两件事,不复用。
- **error / abort / timeout** —— adapter 返回 `status=error`(exit 4),不推断 `done` 也不推断 `blocked`,不改 canonical phase。
- **聊天里出现"完成/上线/验证"字样** —— 不构成 finish 信号(红线:auto-advance 已判死,不按字面判断)。

## 失败语义(确定性 exit code)

| status | exit | 含义 |
|---|---|---|
| `done` | 0 | closeout 成功且 `completion_ref` read-back 通过（verify 是强制的，无 escape hatch） |
| `blocked` | 1 | done-gate / phase 拒绝(`reason=phase_not_verifying` 或 `done_gate_blockers`),phase 不变,blockers 原样带出 |
| `verify_failed` | 1 | closeout 本身成功但 `completion_ref` read-back 失败(视为未完成,不得宣称 done) |
| `missing_task_id` / `missing_root` | 2 | 解析失败,fail closed,未触碰任何 state |
| `cli_unavailable` | 3 | state-core CLI 找不到(含显式 override 指向不存在路径) |
| `error` | 4 | task-state.json 缺失 / root 指错 / DIRECT_TO 指针缺或坏 / subprocess crash / timeout / stdout 异常 / exit-0 伴随 stderr——**不是** done-gate blocker，不推断任何 phase |

每次调用在 stdout 输出 compact JSON（machine-readable，含 `verified` 布尔），人读的 hint/blockers 在 stderr。
成功收据只把互相绑定的 `task_id` / `revision_sha256` / `completion_ref` 当作可信证据：
adapter 会独立重算 `completion_ref=sha256(task_id:revision_sha256)`，再调
`verify-completion` read-back。state-core 输出的 `state_path` 可能经 DIRECT_TO/MOVED_TO 跨 root，
adapter 不复制指针解析，因此不把 `state_path` 带进最终可信 compact receipt。

**success envelope 硬规则**：`closeout` 或 `verify-completion` 在 exit 0 时只要 stderr 非空就
fail closed；closeout JSON 必须恰好是 canonical 五字段，多出 `errors` 等矛盾字段也拒绝。

**error vs blocked 的硬规则**（host-review P1-2）：只有 state-core 明确拒绝 phase 或 done-gate 内容时才报 `blocked`；路径 / 指针 / CLI / 文件异常一律报 `error`。理由：把“任务不存在 / root 指错”伪装成“业务 gate blocker”会误导下游以为是任务未过门，而其实是查不到任务。
done-gate blockers 仅接受 state-core 当前输出的 canonical Python `list[str]` repr；注释、尾逗号、
隐式字符串拼接或 JSON 双引号等“可解析但非 canonical”的 suffix 一律当 wrapper/CLI 异常。

### 关于 `--no-verify`

**不存在。** 正式 `mms closeout` 没有跳过 read-back 的 escape：成功声明必须引用本 `closeout` 返回并 verify 过的 `completion_ref`（host-review P1-1）。

## fresh session 生效边界

- 本 binding 是**纯显式命令**,不改任何 hook/config/环境注入,因此:
  - **新 session**:安装(merge)后立即可用,无投影延迟。
  - **旧 session**:已启动的 session 不受影响——它本来就只能通过显式敲 `mms closeout` 触发,不存在"旧 session 被静默更新/未更新"的问题面。
- 若未来把本 adapter 接进某个 harness 的事件面(新增 binding),按 HANDBOOK 惯例:**变更只对新 session 生效**,旧 session 的旧 hook 配置会重放,需在变更记录中写明。

## 如何手工复核 completion_ref

```bash
# 1) closeout 成功后拿到 ref(也存在 state 里)
mms closeout --task-id <id> --root <repo>            # stdout JSON: completion_ref

# 2) 独立 read-back(不依赖 adapter,直接用 state-core CLI)
python3 <state-core>/src/cli.py verify-completion \
  --task-id <id> --root <repo> --completion-ref <ref>
# → {"status": "passed"} 且 exit 0;ref 与 task/revision 绑定,任何 state 后续变更都会使其失效

# 3) 直接看 canonical state
python3 <state-core>/src/cli.py read --task-id <id> --root <repo>
# → phase=done 且 completion.completion_ref 与 1) 一致
```

注意:`completion_ref` 是 task/revision-bound 的(`completion:sha256:<hash>`,hash = task_id + 证据 revision)。done 之后任何 slot/evidence 变更都会让旧 ref verify 失败——这是特性不是 bug,防的是拿旧收据给新状态背书。

## Cross-runner compliance suite

`tests/test_state_core_closeout_binding.py` 冻结以下 contract cases,后续新 harness binding(Claude / Codex / OpenCode)**必须跑同一组 cases** 通过后才可标 parity-complete:

1. explicit finish → closeout 成功 → `completion_ref` verified(read-back)。
2. phase≠verifying → 非零退出 → phase 不变、无 completion。
3. done-gate content blocker → 非零退出 → blockers 可见 → `task-state.json` 逐字节不变。
4. 普通 Stop/turn end → 不触发 closeout(hooks/ 零引用静态断言)。
5. task id / root 缺失 → fail closed(exit 2),不猜状态。
6. cli unavailable → exit 3。
7. 静态:adapter 无文件写原语(`open(`/`.write_text(`/`.write_bytes(`/`json.dump(`)、无 `set --next-action/--runner/--owner`、无聊天文本解析面。
8. exit-0 payload 字段互绑、stderr 为空；非 canonical blocker literal 不能升格为 business `blocked`。

## 非目标(红线重申)

- 不做 auto-advance;不按聊天字样判断完成。
- 不把 state-core 变成 hook daemon;不把 runner-specific 依赖塞进 state-core。
- 不修改其他既有 Map/Caveman/NSR hook 的顺序或默认启用状态。
- adapter 不直接读写 `task-state.json`;唯一 state 写路径是 state-core CLI 自己的 `closeout`。
