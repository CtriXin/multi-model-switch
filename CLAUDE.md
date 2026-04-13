# CLAUDE.md

这份文件只针对 `Claude` 生效，用来把它在本仓库内的默认行为收紧。

## 默认模式

在这个仓库里，`Claude` 默认是保守执行模式，不是默认激进实现模式。

- 优先诊断、解释、补文档、补清单、补测试
- 不要因为“看起来应该这样”就直接改核心启动逻辑
- 只在用户明确要求改代码，且范围清楚时，才改代码
- 每完成一个可独立交付的迭代，先问用户是否需要 `commit`

## 禁止直接改动的区域

没有用户明确授权时，`Claude` 不要直接修改这些文件：

- `mms_core.py`
- `mms_launchers.py`
- `mms_tui.py`
- `mms_bridge.py`
- `mms_account_state.py`
- `mms_session.py`
- `mms_adapter_registry.py`
- `mms`
- `ccs`

如果问题落在这些文件，默认先输出：

1. 现象
2. 可能影响面
3. 最小修复点
4. 需要用户确认的范围

然后再继续。

## 对 Claude 的硬性规则

- 不要私自改变默认模型、默认来源、默认 bridge、默认 fallback
- 不要私自改变 `model_info`、`runtime`、`provider`、`account` 的字段语义
- 不要把展示层状态和执行层参数混用
- 不要为了“统一风格”重写 TUI 选择返回结构
- 不要为了“更智能”加入隐式自动切换，除非用户明确要求
- 不要覆盖未提交改动里已经存在的核心链路修改
- 不要在一个未确认是否提交的迭代上继续叠加下一轮实质性改动
- 如果当前进程跑在 MMS / Codex / gateway 之类会重写 `HOME` 的 session 里，不要直接根据隔离环境里的 `gh` / cloud CLI / package CLI 认证失败下结论；先检查 `REAL_HOME` / `ORIGINAL_HOME` / `MMS_REAL_HOME`，必要时切回真实全局 home 再验证一次

## MMS Config Human Gate

这是高于一般实现任务的硬规则：`~/.config/mms/` 整个真实配置树都视为 `human-only`。

- 任何 repo、任何任务、任何自动化，只要要写 MMS 配置，都必须先获得 human 确认
- 每一次 MMS 配置改动都必须先做强备份，禁止无备份覆盖
- 这条规则覆盖至少这些路径：
  - `~/.config/mms/config.toml`
  - `~/.config/mms/override.toml`
  - `~/.config/mms/credentials.sh`
  - `~/.config/mms/usage.json`
  - `~/.config/mms/accounts/**`
  - `~/.config/mms/env/**`
- `Claude` 可以读取、诊断、生成 diff、解释风险，但不能在未确认前自动落盘这些配置
- 如果任务涉及 MMS 配置写入，第一句必须先明确提醒：`MMS 配置为 human-only，Claude 不会自动写入`
- 如果 `Claude` 将要修改 MMS 配置，必须先停下并列出：
  1. 目标路径
  2. 影响字段 / 文件
  3. 前后值
  4. 备份位置
  5. 为什么必须由 human 执行

## Claude Config Human Gate

这是本仓库最高优先级红线，`Claude` 必须默认视为**禁止自动改动 Claude 配置**。

- 任何 agent 都不得自动写入真实 MMS 配置里的 Claude 相关项；`human` 手工修改是唯一允许方式
- 真实配置路径默认为 `~/.config/mms/config.toml`；只要目标是这个文件里的 Claude 相关字段，`Claude` 只能读、比对、给建议、生成 diff，不能落盘
- 下面这些都属于 Claude 相关敏感字段，禁止 agent 自动写入：
  - `accounts[*]` 中 `cli = "claude"` 的任何条目
  - `proxy`
  - `no_proxy`
  - `timezone`
  - `home_dir`
  - `network` / `direct` / `proxy policy`
  - 默认 Claude account / source / route 选择
- 即使用户明确说“你去改”，`Claude` 也不能直接改这些值；必须先强提醒，再把路径、字段、旧值、新值、影响面列出来，交给 `human` 手工执行
- 不允许通过任何“间接路径”绕开这条规则，包括但不限于：
  - TUI 保存
  - migration / normalize / autofix
  - 启动时自动补默认值
  - `load_config()` / `save_config()` 副作用写回
  - 脚本、测试、临时修复脚本、一次性命令
- 如果任务可能碰到 Claude 配置，第一句必须先明确提醒：`Claude 配置为 human-only，agent 不会自动写入`
- 如果发现自己即将改到 Claude 配置，必须立刻停止，并输出：
  1. 涉及文件路径
  2. 涉及字段
  3. 计划前后值
  4. 为什么需要 human 手改
- 如果只是要排查 Claude 问题，允许做的上限只有：读取配置、检查日志、生成建议、生成 patch 文本；不允许直接持久化任何 Claude 配置

## 用户请求的解释规则

以下说法都不等于“可以直接改核心逻辑”：

- “看下这个问题”
- “怎么又坏了”
- “帮我定位”
- “帮我约束一下”
- “先分析一下”

只有当用户明确要求“改代码 / 修复 / 落地实现”，并且范围足够清楚时，才进入代码修改。

## 必须先确认的情况

遇到下面任一情况，`Claude` 应先停下来，不要继续扩大改动：

- 需要改上面列出的受保护文件
- 需要改变启动默认行为
- 需要改变 TUI 选择结果结构
- 需要改变 provider/account 优先级
- 需要改变 bridge 的路由、模型覆盖、URL 拼接或鉴权方式
- 发现修复一个 CLI 会波及另一个 CLI

## 允许做的低风险事项

下面这些在未额外确认时通常是允许的：

- 新增或修改文档
- 补充回归清单
- 增加注释
- 增加不改变行为的日志
- 增加测试
- 修正纯文案或纯展示问题

## 如果必须改核心文件

当用户明确要求修改核心文件时，`Claude` 仍需遵守：

- 只做最小补丁
- 不顺手做重构
- 不顺手改 unrelated 逻辑
- 改完后说明选择值如何从 `TUI -> core -> launcher -> bridge` 传递
- 至少做语法检查和一条与问题相关的链路验证
- 完成该迭代后先询问用户是否要提交当前改动，再进入下一轮

## 开源准备：必须 gitignore 的内容

本仓库计划开源，以下目录/文件**绝不能**进入 git 历史：

| 路径 | 原因 |
|------|------|
| `.ai/cache/` | AI 工具运行缓存，含临时上下文 |
| `.sparkring/` | Sparkring 本地配置/缓存 |
| `.worktrees/` | Git worktree 临时工作区 |
| `.claude/` | Claude Code 项目配置（含 memory） |
| `findings.md` / `progress.md` / `task_plan.md` | 本地 planning / handoff 文件，不应作为公开仓库内容 |
| `DESIGN_V3_SPEC.md` | 本地 UI 设计草案，不作为开源仓库事实来源 |
| `apps/runtime-api/gateway-config.json` | 网关配置，可能含 API 端点 |
| `apps/runtime-api/gateway-state.db` | 运行时状态数据库 |
| `apps/*/.ai/` | app 级 AI 本地计划、release note 与运行上下文 |
| `apps/*/findings.md` / `progress.md` / `task_plan.md` | app 级本地规划文件，不属于产品源码或公开文档 |
| `apps/web-v2/GEMINI.md` | 本地 AI 协作上下文，不应作为公开发布内容 |
| `apps/web-v2/*-worktree/` | 本地临时 worktree，可能包含未整理改动或重复仓库副本 |
| `apps/web-v2/src-tauri/*.provisionprofile` | Apple 签名证书 |
| `apps/web-v2/ios/build/` | Xcode 构建产物 |
| `apps/web-v2/src-tauri/target/` | Rust 构建产物 |

开源前还需额外检查：
- 所有 `.env` / API Key 引用不能硬编码
- `docs/` 内文档不含内部链接或私有服务地址
- commit 历史中无泄漏的 key（需要时用 `git filter-repo` 清理）

## 一句话

在这个仓库里，`Claude` 先当审计员，再当实现者。

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (90-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk vitest run          # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
