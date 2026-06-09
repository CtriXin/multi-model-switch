# MMS Release Channels

MMS 采用 Stable / Dev / Canary 三通道。目标是把“普通用户能放心装”和“作者每天快速迭代”分开。

## 固定通道契约

除非人类明确要求修改 release/channel contract，否则 LLM / agent 不要重命名、重映射或混用以下关系：

- `Stable == main == MMD/mmd`：纯稳定上线版本；等待 stable 追到当前能力后，`main` 就是默认稳定分支。
- `Dev == dev branch == MMF/mmf`：日常开发通道；给作者工作机常用，但仍要保持“开发中稳定”。
- `Canary == canary branch == MMG/mmg`：每天测试的实验通道；小步迭代、频繁 commit，方便随时回滚。

当前实现注意：

- 本机维护者命令由 `scripts/link_local_channel_commands.sh` 生成到 `~/.local/bin`。
- `mms` 固定为 public installed copy，只用于公开版本复现，不作为日常本地开发入口。
- `mmd` 指向 stable worktree；`mmf` 指向 dev worktree；`mmg` 指向 canary worktree；`mmm` 指向 main worktree。
- `mmf` / `mmg` 都强制使用 `~/.config/mms-next` preview DB root；`mms` / `mmd` / `mmm` 使用默认 stable root。

## 通道定义

| Channel | 固定关系 | Git source | 安装参数 | 用户 | 规则 |
|---|---|---|---|---|---|
| Stable | Stable == `main` == `mmd` | `main` / GitHub Release / `release/stable-*` | `--channel stable` / `--stable` | 普通用户、生产环境 | 纯稳定上线版本，只收验证过的修复和兼容功能 |
| Dev | Dev == `dev` == `mmf` | `dev` | `--channel dev` / `--dev` | 作者日常工作机、需要最新修复的人 | 开发中稳定，小步提交，targeted tests 通过 |
| Canary | Canary == `canary` == `mmg` | `canary` | `--channel canary` / `--canary` | 测试机、夜间试验 | 最快实验分支，小步高频 commit，必须方便回滚 |

## 版本轨道

当前版本语义按 channel track 表达。正式 tag/release 使用固定分支轨道：

| Channel | Version track | 说明 |
|---|---|---|
| Stable / Main | `3.4.z` | 公开稳定安装线；继续用正式 `v3.4.z` tag / release 表达可安装版本。 |
| Dev / `mmf` | `3.5.z` | 开发中稳定线；承载 WebUI-first、preview DB/config v2、launcher 瘦身等能力。 |
| Canary / `mmg` | `3.6.z` | 金丝雀实验线；比 Dev 更激进，仍以小 commit + git hash 支持回滚。 |

`z` 是每个 channel 自己的 release 计数：如果 release 只覆盖一个 commit，就按该 commit `z+1`；如果 release 覆盖一组已验证 commits，就作为一次复合 release 只 `z+1` 一次。未 tag 的日常小步 commit 仍用 git hash 追踪，不单独占用正式 release 号。

不要把当前 Canary 叫 `5.0`。`5.0` 留给未来真正的大破坏边界，例如 3.6 金丝雀线验证完成后再重构 launcher/runtime 公共 API。

## 当前过渡策略

- `main` 暂时不停止迭代，会和 `dev` 同步一段时间，避免已有安装入口突然断档；同步窗口结束后 `main` 固定为 Stable/default。
- `dev` 和 `canary` 已从当前 main 切出；后续新功能优先进入 `dev` / `canary`，再按验证结果进入 Stable。
- `release/stable-v3.3-no-db` 继续作为 stable 维护线，逐步 cherry-pick 已验证的 Web UI / Thinking / model route 修复。
- 开发过程中发现的 bug 必须先修复，再进入 Stable；Stable 不接收“已知会破坏主流程”的变更。
- 等 stable 追上当前主功能后，目标语义是 `main == Stable/default == mmd`；日常开发不要继续直接把 `main` 当 Dev。

## 本机命令矩阵

这段是给 LLM / agent 的长期产品约定，避免把 branch channel 和 config root 混在一起：

| Command | 语义 | 当前目标 | Config root | 用途 |
|---|---|---|---|---|
| `mms` | Public installed MMS | `~/.mms/mms` | 默认 `~/.config/mms` | 只用于公开版本问题复现 |
| `mmd` | Stable | `.worktrees/stable-v3.3-no-db/mms` | 默认 `~/.config/mms` | stable 线验证 |
| `mmf` | Dev | `.worktrees/dev/mmf` | 强制 `~/.config/mms-next` | 日常开发 / DB preview |
| `mmg` | Canary | `.worktrees/canary/mms` | 强制 `~/.config/mms-next` | 每日实验 / 快速回滚 |
| `mmm` | Main | 当前 main worktree `mms` | 默认 `~/.config/mms` | main 过渡观察入口 |

- `main`：未来等同 Stable/default branch；当前用 `mmm` 明确区分 main 过渡入口。
- `dev`：作者平时常用的开发通道；固定对应 `MMF/mmf`。
- `canary`：最激进的金丝雀通道；固定对应 `MMG/mmg`。
- 重新生成本机命令时运行：`scripts/link_local_channel_commands.sh`。
- 不要把 `mms` 当本地开发入口；`mms` 后续只代表 public installed copy。

### 启动更新提醒策略

本机 wrapper 会先调用 `scripts/local_channel_update.py` 做轻量提醒；默认只提醒/手动更新，不自动 pull：

| Command | 检查频率 | 默认动作 | 手动更新 |
|---|---|---|---|
| `mms` | daily | 只提示 public installed copy，不自动更新 | `mms update` 只说明走 installer/release 更新 |
| `mmd` | weekly | fetch 后提示；stable 不自动更新 | `mmd update` 仅允许 clean worktree fast-forward |
| `mmf` | daily | fetch 后提示 dev 更新 | `mmf update` 仅允许 clean worktree fast-forward |
| `mmg` | every launch | 每次 fetch 并提示 canary ahead/behind/diverged | `mmg update` 仅允许 clean worktree fast-forward |
| `mmm` | daily | fetch 后提示 main 更新 | `mmm update` 仅允许 clean worktree fast-forward |

安全规则：dirty worktree 拒绝更新；只允许 `git merge --ff-only`；分叉时只提示，不自动 merge/reset；检查状态写到 `~/.local/state/mms/channel-updates.json`，不写 `~/.config/mms/**`。

## 安装命令

Stable：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel stable --write-shell-rc
```

Dev：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev --write-shell-rc
```

Canary：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel canary --write-shell-rc
```

精确 pin：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v3.4.0
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref dev
```

## 发布门槛

Stable 候选至少需要：

- `bash install.sh --check`
- `python3.13 -m py_compile` 覆盖改动 Python 文件
- launcher / Web UI / model route 的 targeted tests
- `mms doctor` 或 `mmf doctor` smoke
- Web UI save-plan / bundle verify smoke（涉及配置时）
- release note 明确升级影响、回滚方式和 channel

Dev 候选至少需要：

- 小步 commit
- 针对性 tests 通过
- 本地 regression report 写明未测范围

Canary 候选至少需要：

- 能启动或能回滚
- 小步迭代 commit
- 高频 commit，保证随时能按 commit 回滚
- 记录破坏面，不假装稳定

## 两台个人工作机

如果一台白天用、一台晚上用，建议两台都装 `Dev`，并尽量保持同一个 commit / channel。MMS 默认安装目录是 `~/.mms`，`mms` / `mmf` 是同一套安装里的两个 config root，不是两套代码版本。

需要真正并存多个代码 channel 时，先用 VM、独立用户或明确的安装前缀方案；不要让两个 channel 同时覆盖同一个 `~/.mms`。
