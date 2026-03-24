# Claude Session 持久化方案 — Review & Deep Dive

> By Claude (Opus 4.6) — 2026-03-24
> 针对 `docs/CLAUDE_SESSION_PERSISTENCE_PLAN.md` 的审阅，以及更深层的架构思考。

---

## 一、对原方案的总体评价

方案主线 **正确且务实**：账号态 / 历史态解耦是真问题，四层架构（Account → Raw → Summary → Archive）分层合理，Phase 节奏有克制。

但有几个 **结构性盲区** 需要在动手前解决，否则 Phase 1 会做成"新增一层目录但没真正改变体验"。

---

## 二、必须先对齐的六个问题

### 2.1 与现有 gateway slot 的关系

这是最关键的一点，原方案 **完全没提**。

当前 `mms claude` 启动时的 HOME 隔离结构：

```
~/.config/mms/claude-gateway/s/<pid>/
  .claude.json          ← 合并生成，per-slot
  .claude/
    settings.json       ← 每次启动写入，per-slot
    history.jsonl  → ~/.claude/history.jsonl     ← symlink 到真实
    sessions/      → ~/.claude/sessions/         ← symlink 到真实
    transcripts/   → ~/.claude/transcripts/      ← symlink 到真实
    file-history/  → ~/.claude/file-history/     ← symlink 到真实
    ...其余全部   → ~/.claude/...               ← symlink 到真实
  .local → ~/.local
  Library → ~/Library
```

新方案要引入 `~/.config/mms/projects/<hash>/claude/raw/`。那问题是：

1. **slot 里的 symlink 改指向谁？** 从 `~/.claude/sessions/` → `~/.config/mms/projects/<hash>/claude/raw/sessions/`？
2. **真实 `~/.claude/` 里的原始文件还要不要？** 如果 Claude CLI 自身有逻辑直接读 `~/.claude/sessions/`（比如 `claude --resume`），把文件挪走会不会破坏原生 resume？
3. **slot 退出后目录被清理，但 project-scoped 目录要持久。** 两者的生命周期完全不同，需要明确谁是源、谁是影子。

**我的建议：**

```
方案 A（symlink 反转）：
  project-scoped 目录是 source of truth
  真实 ~/.claude/ 下的 history/sessions/transcripts 改为 symlink → project 目录
  slot 启动时 symlink 指向 project 目录

方案 B（copy-on-exit）：
  运行时仍然用 ~/.claude/ 作为活跃层
  slot 退出时把 delta 复制到 project-scoped 目录
  project 目录只是归档，不参与运行时

方案 C（双写 + 合并视图）：
  运行时写入 ~/.claude/（保持原生兼容）
  mms 层维护一个 project-scoped index，指向 ~/.claude/ 里的具体 session 文件
  不移动文件，只建索引
```

三种方案各有代价。但我倾向 **方案 A** 的变体——因为 Phase 1 的核心承诺是"切账号不丢历史"，这要求历史的物理位置不在全局 `~/.claude/` 里。

### 2.2 `<project-hash>` 的生成算法

原方案说"由仓库真实路径生成"，但没定义算法。这件事必须在编码前锁定，因为一旦上线就不能改（改了等于历史全丢）。

需要考虑的边界：

| 场景 | 风险 |
|------|------|
| 同一仓库被 symlink 到两个路径 | 不同 hash → 历史分裂 |
| Git worktree（不同路径，同一 .git） | 不同 hash → 历史分裂 |
| 仓库被 `mv` 到新路径 | 旧 hash 失效 → 历史"消失" |
| 非 git 目录启动 Claude | 没有 `.git`，fallback 到什么？ |

**我的建议：**

```python
def project_key(cwd: str) -> str:
    """
    优先级：
    1. git rev-parse --show-toplevel 的 realpath
    2. 如果不是 git 仓库，用 cwd 的 realpath
    3. 对结果取 SHA-256 前 16 位
    """
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, text=True
        ).strip()
        canonical = os.path.realpath(root)
    except subprocess.CalledProcessError:
        canonical = os.path.realpath(cwd)

    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

同时在 `metadata.json` 里记录原始路径，方便人工排查：

```json
{
  "project_hash": "a1b2c3d4e5f67890",
  "canonical_path": "/Users/xin/auto-skills/CtriXin-repo/multi-model-switch",
  "display_name": "multi-model-switch",
  "created_at": "2026-03-24T10:00:00Z"
}
```

### 2.3 并发写入

如果两个 `mms claude` 窗口同时指向同一个 project，`history.jsonl` 会被并发 append。

Claude CLI 自己在单进程场景下大概率用的是 append-only + 行级写入，这在 POSIX 下对小写入是原子的（< PIPE_BUF = 4096 bytes）。但如果一行 JSON 超过 4KB（长对话的 transcript 引用），就不安全了。

**建议：** Phase 1 不解决，但在文档里标记为已知限制。Phase 2 如果要做 summary index，index 文件的写入必须用 fcntl 锁或原子 rename。

### 2.4 Summary 的最小可行版本应该进 Phase 1

原方案把 Summary 放 Phase 2，但这会导致 Phase 1 的用户体验改善 **不可感知**。

"历史不丢"在技术上是进步，但用户的痛点是"找不到"——找不到和丢了，体感一样。

**建议：** Phase 1 带一个 **passive metadata**，不需要 AI 生成，纯机械记录：

```json
{
  "session_id": "90b690b2-...",
  "project_hash": "a1b2c3d4e5f67890",
  "project_path": "/Users/xin/.../multi-model-switch",
  "account_id": "claude-pro-1",
  "started_at": "2026-03-24T10:00:00Z",
  "last_active_at": "2026-03-24T12:30:00Z",
  "cwd": "/Users/xin/.../multi-model-switch",
  "pid": 66398,
  "cli_version": "1.0.25"
}
```

Phase 2 再叠加 AI 生成的 `title` / `task_summary` / `next_step`。

### 2.5 与 OAuth 账号的 `home_dir` 的关系

`ccs_account_state.py` 的 `activated_claude_account_state()` 会临时把 `~/.claude.json` 替换成对应账号的版本。这和 gateway slot 的 HOME 隔离是 **两套独立机制**。

新方案需要明确：当 `mms claude --account pro-2` 启动时——

- 账号态 → 用 `accounts/pro-2/` 下的 `.claude.json`（已有）
- 历史态 → 用 `projects/<hash>/claude/raw/`（新增）
- 两者在 slot 构建时如何组装？

如果不理清这个，最终会出现三层叠加（account home + gateway slot + project scope），调试时没人能说清某个 session 文件到底从哪来。

### 2.6 `ccs_session.py` 的定位

当前 `ccs_session.py` 管理的是 mms 自己的 `chat/discuss` session（存在 `~/.mms/sessions/`），和 Claude CLI 的 session 是 **完全不同的东西**。

新方案应该明确：project-scoped 历史仓只管 Claude CLI 的原始 session，不要和 mms 的 chat/discuss session 混在一起。两者未来可以在 Phase 4 做统一视图，但存储层必须隔离。

---

## 三、更远的思考

### 3.1 统一 Session Envelope：Claude + Codex + Gemini

原方案只讨论了 Claude。但 mms 的价值恰恰在于多 CLI 统一管理。如果只给 Claude 做持久化，Codex 和 Gemini 的历史仍然是各自为政。

建议从 Phase 1 开始就设计一个 **CLI-agnostic 的 session envelope**：

```
~/.config/mms/projects/<hash>/
  claude/
    raw/
    summary/
  codex/
    raw/
    summary/
  gemini/
    raw/
    summary/
  unified/
    session_index.json    ← 跨 CLI 的统一索引
```

这样 `mms session ls` 可以一次列出所有 CLI 在这个项目下的活动，而不只是 Claude 的。

### 3.2 Session Identity：谁定义 "session"？

Claude CLI 的 session ID 是它自己生成的 UUID。mms 无法提前知道这个 ID，只能在启动后从 `sessions/<pid>.json` 里读取。

这意味着 mms 的 session metadata **必须是事后追踪型**，而不是事前分配型。流程应该是：

```
mms 启动 claude → claude 生成 session_id →
mms 在 slot 退出回调里读取 session_id → 写入 project-scoped metadata
```

如果 mms 要在 Phase 2 做 `mms session resume <id>`，需要：
1. 从 metadata 查到 session_id
2. 用 `claude --resume --session-id <id>` 启动（如果 Claude CLI 支持的话）
3. 确保 raw session 文件仍在正确位置

### 3.3 Session 生命周期钩子

当前 `_cleanup_stale_sessions()` 只做了"PID 死了就删 slot 目录"。新方案需要一个更完整的生命周期：

```
on_slot_create(pid, project_hash, account_id):
    # 创建 project-scoped 目录（如果不存在）
    # 设置 symlink / bind
    # 写入初始 metadata

on_slot_active(pid):
    # 可选：定期快照 metadata
    # 可选：监控 session 文件变化

on_slot_exit(pid, exit_code):
    # 从 slot 里提取 session_id
    # 更新 metadata（last_active_at, duration, exit_code）
    # Phase 2+: 触发 summary 生成
    # 清理 slot 目录（但不清理 project-scoped 目录）
```

这比现在的"PID 死了就 rmtree"要精细得多，但也是持久化的必要基础。

### 3.4 `mms session` 子命令族

原方案提了几个命令，我建议扩展为一个完整的子命令族：

```bash
# Phase 1
mms session ls [--cli claude|codex|gemini] [--project <path>]
mms session info <session-id>

# Phase 2
mms session resume <session-id>          # 自动找到对应 CLI 并 resume
mms session summarize [--recent 7d]      # AI 生成摘要
mms session tag <session-id> <tag>       # 手动打标签
mms session search <keyword>             # 全文搜索

# Phase 3
mms session archive [--older-than 30d]
mms session prune [--older-than 90d] [--dry-run]
mms session export <session-id> [--format md|json]

# Phase 4
mms session timeline [--project <path>]  # 按时间线展示跨 CLI 活动
mms session handoff <session-id> --to codex  # 跨 CLI 接力
```

其中 `handoff` 是一个有想象力的方向——把 Claude session 的 context 摘要传给 Codex 继续，或反过来。这在 mms 的多模型协作定位下是自然延伸。

### 3.5 长期记忆 vs Session 历史

Session 历史是"发生过什么"，长期记忆是"学到了什么"。两者不应该混在一起。

当前 Claude Code 已经有 `CLAUDE.md` 和 memory 机制。mms 不应该试图替代这些，而应该做好 **session 层的桥接**：

- Session 历史：mms 托管，project-scoped，可归档可清理
- 长期记忆：各 CLI 自己管理（Claude 用 memory/，Codex 用 AGENTS.md，等）
- mms 的价值：跨 CLI 的 session 索引 + 生命周期管理

不要试图做一个"mms 统一知识库"——那会变成一个永远做不完的系统。

### 3.6 隐私与安全

Session 历史包含用户的完整对话，可能涉及：
- API keys（虽然不应该，但用户会在对话里粘贴）
- 内部代码片段
- 业务逻辑讨论

Archive 和 Summary 层应该考虑：
- Summary 不应包含原文中的敏感 token
- Archive 目录的权限应为 `700`
- `mms session export` 输出前应有 warning
- 如果未来做远程同步，必须端到端加密

---

## 四、Phase 1 的最小实现清单

基于以上分析，我认为 Phase 1 的真正 scope 应该是：

### 必须做

1. **定义 `project_key()` 算法** — 基于 git toplevel realpath 的 SHA-256[:16]
2. **创建 project-scoped 目录结构** — `~/.config/mms/projects/<hash>/claude/raw/` + `metadata.json`
3. **修改 `_claude_gateway_env()` 的 symlink 目标** — 从 `~/.claude/` → `project-scoped/raw/`
4. **首次启动时的迁移** — 如果 project 目录为空但 `~/.claude/` 里有对应 session，copy 过来
5. **写入 passive metadata** — session_id, project, account, timestamps（on_slot_exit 回调）
6. **`mms session ls` 最小版本** — 读 metadata，列表展示

### 不做

- AI 生成的 summary
- Archive / prune
- 跨 CLI 统一索引
- 并发写入保护
- 远程同步

### 需要改动的受保护文件

| 文件 | 改动范围 | 风险 |
|------|----------|------|
| `ccs_launchers.py` | `_claude_gateway_env()` 的 symlink 逻辑 | 中 — 这是启动核心链路 |
| `ccs_launchers.py` | `_cleanup_stale_sessions()` 增加 on_exit 回调 | 低 — 只是增加逻辑 |
| `ccs_session.py` | 可能不需要改，新逻辑放新文件 | — |
| 新文件：`ccs_project_store.py` | project_key / metadata / 目录管理 | 无 — 新文件 |
| 新文件：`ccs_session_index.py` | session metadata 读写 / ls 命令 | 无 — 新文件 |

---

## 五、一句话总结

Codex 的方案把 **"为什么要做"** 说清楚了，但 **"怎么接入现有架构"** 还是空白。Phase 1 的关键不是"新建目录结构"，而是 **把 `_claude_gateway_env()` 里的 symlink 目标从全局 `~/.claude/` 切到 project-scoped 目录，同时不破坏 Claude CLI 的原生 resume**。这一刀切准了，后面的 Phase 自然能长出来。
