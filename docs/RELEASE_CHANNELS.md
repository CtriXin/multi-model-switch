# MMS Release Channels

MMS 采用 Stable / Dev / Canary 三通道。目标是把“普通用户能放心装”和“作者每天快速迭代”分开。

## 固定通道契约

除非人类明确要求修改 release/channel contract，否则 LLM / agent 不要重命名、重映射或混用以下关系：

- `Stable == main == MMD/mmd`：纯稳定上线版本；等待 stable 追到当前能力后，`main` 就是默认稳定分支。
- `Dev == dev branch == MMF/mmf`：日常开发通道；给作者工作机常用，但仍要保持“开发中稳定”。
- `Canary == canary branch == MMG/mmg`：每天测试的实验通道；小步迭代、频繁 commit，方便随时回滚。

当前实现注意：

- 本机维护者命令由 `scripts/link_local_channel_commands.sh` 生成到 `~/.local/bin`。
- `mms` 固定为 public installed copy：`/Users/xin/.mms/mms`，默认 root `/Users/xin/.config/mms`，只用于公开版本复现。
- `mmd` 指向 stable worktree：`.worktrees/stable-v3.3-no-db/mms`，默认 root `/Users/xin/.config/mms`。
- `mmf` 指向 dev worktree：`.worktrees/dev/mmf`，强制 root `/Users/xin/.config/mms-next`。
- `mmg` 指向 canary worktree：`.worktrees/canary/mms`，强制 root `/Users/xin/.config/mms-next`。
- `mmm` 指向当前 main worktree 的 `mms`，默认 root `/Users/xin/.config/mms`。

## 通道定义

| Channel | 固定关系 | Git source | Config root | 安装参数 | 用户 | 规则 |
|---|---|---|---|---|---|---|
| Stable | Stable == `main` == `mmd` | `main` / GitHub Release / `release/stable-*` | `~/.config/mms` | `--channel stable` / `--stable` | 普通用户、生产环境 | 纯稳定上线版本，只收验证过的修复和兼容功能 |
| Main / pinned branch | Stable 对照入口 | explicit `--ref main` | `~/.config/mms` | `--ref main` | 兼容旧入口 / 主线对照 | 不默认启用 preview DB |
| Dev | Dev == `dev` == `mmf` | `dev` | `~/.config/mms-next` preview DB | `--channel dev` / `--dev` | 作者日常工作机、需要最新修复的人 | 开发中稳定，小步提交，targeted tests 通过 |
| Canary | Canary == `canary` == `mmg` | `canary` | `~/.config/mms-next` preview DB | `--channel canary` / `--canary` | 测试机、夜间试验 | 最快实验分支，小步高频 commit，必须方便回滚 |

## 当前过渡策略

- `main` 暂时不停止迭代，会和 `dev` 同步一段时间，避免已有安装入口突然断档；但 `main` / pinned `--ref main` 仍读 stable root `~/.config/mms`。
- `dev` 和 `canary` 已从当前 main 切出；后续新功能优先进入 `dev` / `canary`，并默认使用 `~/.config/mms-next` preview DB / latest-approved bundle，再按验证结果进入 Stable。
- `release/stable-v3.3-no-db` 继续作为 stable 维护线，逐步 cherry-pick 已验证的 Web UI / Thinking / model route 修复。
- 开发过程中发现的 bug 必须先修复，再进入 Stable；Stable 不接收“已知会破坏主流程”的变更。
- 等 stable 追上当前主功能后，目标语义是 `main == Stable/default == mmd`；日常开发不要继续直接把 `main` 当 Dev。

## 本机命令矩阵

这段是给 LLM / agent 的长期产品约定，避免把 branch channel 和 config root 混在一起：

| Command | 语义 | 当前目标 | Config root | 用途 |
|---|---|---|---|---|
| `mms` | Public installed MMS | `/Users/xin/.mms/mms` | `/Users/xin/.config/mms` | 只用于公开版本问题复现 |
| `mmd` | Stable | `.worktrees/stable-v3.3-no-db/mms` | `/Users/xin/.config/mms` | stable 线验证 |
| `mmf` | Dev | `.worktrees/dev/mmf` | `/Users/xin/.config/mms-next` | 日常开发 / DB preview |
| `mmg` | Canary | `.worktrees/canary/mms` | `/Users/xin/.config/mms-next` | 每日实验 / 快速回滚 |
| `mmm` | Main | 当前 main worktree 的 `mms` | `/Users/xin/.config/mms` | main 过渡观察入口 |

- `main`：未来等同 Stable/default branch；当前用 `mmm` 明确区分 main 过渡入口。
- `dev`：作者平时常用的开发通道；固定对应 `MMF/mmf`。
- `canary`：最激进的金丝雀通道；固定对应 `MMG/mmg`。
- 后续 Canary 迭代默认自动吸收 `main` 和 `dev` 的新内容，再继续 Canary 自身小步提交。
- 重新生成本机命令时运行：`scripts/link_local_channel_commands.sh`。
- 不要把 `mms` 当本地开发入口；`mms` 后续只代表 public installed copy。

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
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v3.3.1
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

如果一台白天用、一台晚上用，建议两台都装 `Dev`，并尽量保持同一个 commit / channel。Dev / Canary 的 primary `mms` 入口默认读取 `~/.config/mms-next` preview DB；Stable / pinned `main` 默认读取 `~/.config/mms`。

需要真正并存多个代码 channel 时，先用 VM、独立用户或明确的安装前缀方案；不要让两个 channel 同时覆盖同一个 `~/.mms`。
