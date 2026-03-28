# MMS Claude Session Phase 1 决策稿

> 状态：已完成方案合并，可作为后续实现依据  
> 来源文档：
> - `docs/CLAUDE_SESSION_PERSISTENCE_PLAN.md`
> - `docs/CLAUDE_SESSION_PERSISTENCE_REVIEW.md`
>  
> 目标：把“为什么做”和“怎么落到现有架构里”收敛成一份能直接开工的 Phase 1 决策稿。  
> 后续实现 owner：`Codex`

---

## 一、结论先行

三方已经基本对齐：

- 原方案的主方向成立：
  - `账号态` / `历史态` 解耦
  - `project-scoped` 历史仓
  - 在“不丢”之后再做“好找”和“可治理”
- Claude review 提出的补充是必要的：
  - 必须正面接入现有 `_claude_gateway_env()` / gateway slot 架构
  - 必须在动手前锁定 `project_key()` 算法
  - Phase 1 不能只建目录，还要带最小 `metadata` 与最小 `session ls`
- 但有一个点本轮不直接采纳为默认实现：
  - 不默认执行“把全局 `~/.claude` 反向 symlink 到 project 目录”这类高 blast radius 方案

一句话版本：

**Phase 1 先让 `mms` 自己启动的 Claude session 在项目维度稳定持久，并可被识别；不试图一步改造全局 `Claude CLI` 的所有历史语义。**

---

## 二、已达成一致的目标

Phase 1 只解决下面三件事：

1. `mms` 启动的 `Claude` session 不再因全局账号切换而“像丢了一样”
2. session 至少有一层可辨认的被动 metadata，而不是只剩原生 `resume` 的最后一句
3. 方案必须接入现有 `gateway slot` 启动架构，而不是另起一套旁路

Phase 1 明确不做：

- AI 生成 summary
- archive / prune
- 跨 CLI 统一索引
- handoff / timeline / search / export
- 修改官方 `Claude CLI` 本体

---

## 三、现有架构与新方案的关系

这是本轮最关键的对齐点。

### 当前架构

当前 `mms claude` 的核心启动结构在 [mms_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_launchers.py)：

- `_claude_gateway_env()` 负责创建 `~/.config/mms/claude-gateway/s/<pid>/`
- 该 slot 目录里：
  - `.claude.json` 是 per-slot 生成
  - `.claude/settings.json` 是 per-slot 覆写
  - `.claude` 其余内容大多 symlink 到真实 `~/.claude`
- `_cleanup_stale_sessions()` 负责清理死掉 PID 对应的 slot 目录

也就是说，**现在真正需要下刀的地方不是“Claude 有没有历史目录”，而是“slot 里的 `.claude/*` 到底指向哪一层”**。

### 新架构在现有体系里的位置

Phase 1 不是额外再搞一个并列系统，而是要把现有 slot 的一部分 symlink 目标从全局 `~/.claude` 收敛到 project-scoped 历史仓。

新的关系应该是：

```text
account state
  -> 仍来自 account.home_dir / .claude.json

gateway slot (per PID)
  -> 仍存在，继续作为运行时 HOME

project-scoped raw store
  -> 变成 Claude 原始 session/history 的持久化来源
```

---

## 四、Phase 1 的架构决策

## 4.1 历史仓位置

采用 project-scoped 全局目录：

```text
~/.config/mms/projects/<project_key>/claude/
  raw/
    history.jsonl
    sessions/
    transcripts/
    file-history/
  state/
    metadata.json
    sessions/
      <session-id>.json
```

说明：

- 不放仓库根目录，避免污染工作树
- 但按项目隔离，而不是继续混在全局 `~/.claude/`
- Phase 1 只做 `raw/` 和 `state/`，不做 `summary/`、`archive/`

## 4.2 `project_key()` 算法

采用 Claude review 提议的方向，并直接锁定为 Phase 1 规范：

优先级：

1. `git rev-parse --show-toplevel`
2. 若失败，fallback 到当前 `cwd`
3. 对 `realpath` 结果做 `sha256(...).hexdigest()[:16]`

同时在 `metadata.json` 中保留：

- `project_key`
- `canonical_path`
- `display_name`
- `created_at`

这样做是为了覆盖：

- symlink 路径
- git worktree
- 仓库挪路径后的人工排查

## 4.3 历史态与账号态拆分

Phase 1 明确拆分为：

### 继续按账号隔离

- `.claude.json`
- `.credentials.json`
- 账号偏好 / onboarding / 认证相关状态

### 改为 project-scoped 持久化

- `history.jsonl`
- `sessions/`
- `transcripts/`
- `file-history/`

### 保持真实系统上下文

- `.local`
- `Library`

这意味着：

- “你是谁”仍由账号决定
- “你在这个项目里做过什么”由 project 历史仓决定

## 4.4 不默认采纳“全局 ~/.claude 反转 symlink”

这是本轮唯一一个明确保守处理的点。

### 本轮不做

- 不把全局 `~/.claude/history.jsonl`
- 不把全局 `~/.claude/sessions/`
- 不把全局 `~/.claude/transcripts/`

直接反向改成指向 `~/.config/mms/projects/...`

### 原因

- blast radius 太大
- 会影响你直接运行全局 `claude`
- 会让 `mms` 与原生全局行为深度耦合
- 一旦路径语义不对，排查成本会非常高

### 本轮改法

只修改 **slot 内部** 的 `.claude/*` 目标，让 `mms` 自己启动的会话先稳定落到 project store。  
这能解决大部分“通过 mms 启动不丢”的问题，同时不立刻接管全局 `claude` 的默认物理存储。

### 4.4.1 slot 内 `.claude/*` 映射对照表

| 路径 | 现在 | Phase 1 后 |
|------|------|------------|
| `slot/.claude/history.jsonl` | `~/.claude/history.jsonl` | `~/.config/mms/projects/<key>/claude/raw/history.jsonl` |
| `slot/.claude/sessions/` | `~/.claude/sessions/` | `~/.config/mms/projects/<key>/claude/raw/sessions/` |
| `slot/.claude/transcripts/` | `~/.claude/transcripts/` | `~/.config/mms/projects/<key>/claude/raw/transcripts/` |
| `slot/.claude/file-history/` | `~/.claude/file-history/` | `~/.config/mms/projects/<key>/claude/raw/file-history/` |
| `slot/.claude/settings.json` | per-slot 生成 | 仍然 per-slot 生成，不 symlink |
| `slot/.claude/projects/` | `~/.claude/projects/` | 保持 `~/.claude/projects/` |
| `slot/.claude/cache/` 等其余项 | `~/.claude/<entry>` | 保持 `~/.claude/<entry>` |

补充说明：

- `projects/` 保持指向全局 `~/.claude/projects/`，因为它更像 Claude Code 的 project memory / settings，不纳入本轮 project store
- Phase 1 只改 `mms` 自己 slot 内部的指向，不回写、不反向污染全局 `~/.claude`

---

## 五、Phase 1 最小可见能力

Claude review 的一个关键提醒是对的：

如果 Phase 1 只做“历史不丢”，用户未必感知得到。  
所以本轮要带一个 **passive metadata 层**，但不做 AI summary。

### 5.1 每个 session 记录的最小 metadata

建议字段：

```json
{
  "session_id": "uuid-or-filename",
  "project_key": "a1b2c3d4e5f67890",
  "project_path": "/Users/xin/.../multi-model-switch",
  "account_id": "boss2-claude",
  "started_at": "2026-03-24T10:00:00Z",
  "last_active_at": "2026-03-24T12:30:00Z",
  "cwd": "/Users/xin/.../multi-model-switch",
  "pid": 66398,
  "cli": "claude",
  "cli_version": "unknown"
}
```

### 5.2 最小命令能力

Phase 1 只承诺：

- `mms session ls`
- `mms session info <id>`

不承诺：

- `resume`
- `search`
- `handoff`
- `summarize`
- `archive`

这样既能让用户感知到“这条 session 还在”，又不会把 scope 拉得太大。

---

## 六、生命周期决策

Phase 1 采用最小生命周期钩子，而不是继续只有“PID 死了就删 slot”。

### 6.1 需要的钩子

- `on_slot_create(pid, project_key, account_id, cwd)`
  - 确保 project-scoped 目录存在
  - 准备 slot 内部的 `.claude/*` 映射
  - 写入初始 metadata

- `on_slot_exit(pid, exit_code)`
  - 从 raw/session 文件里尽量解析真实 `session_id`
  - 更新 `last_active_at`
  - 写入退出状态
  - 再清理 slot 目录

### 6.2 本轮不做

- 周期性心跳
- 长时间运行中的增量快照
- 并发锁
- 自动 summary 生成

### 6.3 `_cleanup_stale_sessions()` 的新语义

当前它只是 `rmtree` 死掉的 slot。  
Phase 1 之后，它仍然可以负责清理 slot，但**不能再承担“历史清理”语义**。

也就是说：

- `slot/` 是临时运行层，可以删
- `projects/<key>/claude/raw/` 是持久层，不能因为 PID 结束就删

### 6.4 `on_slot_exit` 触发位置

实现时机固定为：

1. `launch_claude()` 最终进入 `_exec_or_run()`
2. `claude` 子进程退出后，先执行 `on_slot_exit`
3. 然后再释放 bridge cleanup context / 返回上层
4. slot 目录本身仍按现有策略保留，等下一次 `_cleanup_stale_sessions()` 发现死 PID 时再清

`Ctrl-C` 采用保守方案 A：

- 不额外引入 `signal handler` / `atexit` 复杂逻辑
- 若这次来不及完整写 metadata，接受下一次启动时由 stale cleanup 补写

---

## 七、文件与函数改动边界

Phase 1 只建议触碰这些位置：

### 必改

- [mms_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_launchers.py)
  - `_claude_gateway_env()`
  - `_cleanup_stale_sessions()`
  - 以及 `launch_claude()` 周边用于补生命周期回调的最小接线

### 新增

- `mms_project_store.py`
  - `project_key()`
  - project metadata 路径计算
  - Claude raw store 目录确保逻辑

- `mms_session_index.py`
  - session metadata 读写
  - `mms session ls/info` 所需的读层

### 本轮不改

- `mms_session.py`
  - 它仍然只管 `mms chat/discuss`
- `mms_bridge.py`
  - Phase 1 无需动 bridge 协议层
- `mms_tui.py`
  - 最多后面接一个简单入口，不作为第一刀阻塞项

---

## 八、迁移策略

Phase 1 只做保守迁移，不承诺历史无损归因。

### 迁移原则

- 如果 project store 为空，就初始化目录
- 如果 slot 要用的 raw 目录为空，但全局 `~/.claude/` 对应文件存在，可做一次**保守 copy**
- 不尝试自动把全局历史精确拆分回不同账号

### 为什么不用“智能迁移归类”

因为缺少稳定事实源：

- 全局历史已经可能混过多个账号
- 单靠文件名和时间戳无法 100% 还原归属

所以本轮目标是：

- 从现在开始不再继续污染
- 不是回溯性地完美重建过去

---

## 九、并发与风险说明

### 9.1 并发写入

Phase 1 记为已知限制，不做阻塞项。

风险点：

- 两个 `mms claude` 窗口同时对同一项目写 `history.jsonl`
- 原始 session 文件可能被并发 append

处理策略：

- 本轮在文档中标记为已知风险
- 后续 Phase 2/3 若写 index，再为 index 引入文件锁或原子 rename

### 9.2 原生 CLI 兼容性

本轮的设计原则是：

- 不改官方 CLI 本体
- 不接管全局 `~/.claude` 默认位置
- 只让 `mms` 自己的 slot 指向 project store

这样可以把兼容风险收敛在 `mms` 自己的启动路径内。

---

## 十、后续阶段边界

## Phase 1

- project-scoped raw store
- passive metadata
- `mms session ls/info`

## Phase 2

- AI summary index
- 更强的 session 可辨识性
- 可能增加简单标签/状态

## Phase 3

- archive / prune
- retention policy
- 目录体积治理

## Phase 4

- 跨 CLI unified session envelope
- handoff
- timeline / search / export

说明：

结构上可以从一开始预留：

```text
~/.config/mms/projects/<key>/
  claude/
  codex/
  gemini/
```

但功能上 **只实现 Claude**，不把统一 envelope 反向变成 Phase 1 的阻塞项。

---

## 十一、最终决策表

## 直接采纳

- account/history 解耦
- project-scoped 历史仓
- `project_key()` 锁定
- `_claude_gateway_env()` 作为主接入点
- Phase 1 带 passive metadata
- Phase 1 带 `mms session ls/info`
- 新增 `mms_project_store.py` / `mms_session_index.py`

## 暂缓到后续阶段

- AI summary
- archive / prune
- unified cross-CLI index
- handoff / timeline / search / export
- 并发写入保护

## 本轮明确不默认采用

- 全局 `~/.claude` 反向 symlink 到 project store

---

## 十二、实现前最后一句话

Phase 1 不是“再加一层目录”，而是：

**把 `mms` 的 Claude gateway slot 从“临时借用全局 `~/.claude` 历史”切换为“显式写入 project-scoped 持久层”，并补上一层最小可见 metadata。**

这一步做对了，后面的 summary、archive、handoff 才有稳定地基。
