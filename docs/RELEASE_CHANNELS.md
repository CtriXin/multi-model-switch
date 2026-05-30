# MMS Release Channels

MMS 采用 Stable / Dev / Canary 三通道。目标是把“普通用户能放心装”和“作者每天快速迭代”分开。

## 固定通道契约

除非人类明确要求修改 release/channel contract，否则 LLM / agent 不要重命名、重映射或混用以下关系：

- `Stable == main == MMD/mmd`：纯稳定上线版本；等待 stable 追到当前能力后，`main` 就是默认稳定分支。
- `Dev == dev branch == MMF/mmf`：日常开发通道；给作者工作机常用，但仍要保持“开发中稳定”。
- `Canary == canary branch == MMG/mmg`：每天测试的实验通道；小步迭代、频繁 commit，方便随时回滚。

当前实现注意：

- 已发布安装器仍主要提供 `mms` / `mmf` / `mmslogs`；`mmd` / `mmg` 作为目标入口名记录在这里。
- 在 `mmd` / `mmg` 安装链接真正落地前，不要在用户文档或回复里暗示它们已经可执行。
- `mms` 是现有 stable/current launcher 入口；后续若新增 `mmd`，它应继承 Stable/main 语义，而不是另起一套规则。

## 通道定义

| Channel | 固定关系 | Git source | 安装参数 | 用户 | 规则 |
|---|---|---|---|---|---|
| Stable | Stable == `main` == `mmd` | `main` / GitHub Release / `release/stable-*` | `--channel stable` / `--stable` | 普通用户、生产环境 | 纯稳定上线版本，只收验证过的修复和兼容功能 |
| Dev | Dev == `dev` == `mmf` | `dev` | `--channel dev` / `--dev` | 作者日常工作机、需要最新修复的人 | 开发中稳定，小步提交，targeted tests 通过 |
| Canary | Canary == `canary` == `mmg` | `canary` | `--channel canary` / `--canary` | 测试机、夜间试验 | 最快实验分支，小步高频 commit，必须方便回滚 |

## 当前过渡策略

- `main` 暂时不停止迭代，会和 `dev` 同步一段时间，避免已有安装入口突然断档；同步窗口结束后 `main` 固定为 Stable/default。
- `dev` 和 `canary` 已从当前 main 切出；后续新功能优先进入 `dev` / `canary`，再按验证结果进入 Stable。
- `release/stable-v3.3-no-db` 继续作为 stable 维护线，逐步 cherry-pick 已验证的 Web UI / Thinking / model route 修复。
- 开发过程中发现的 bug 必须先修复，再进入 Stable；Stable 不接收“已知会破坏主流程”的变更。
- 等 stable 追上当前主功能后，目标语义是 `main == Stable/default == mmd`；日常开发不要继续直接把 `main` 当 Dev。

## 未来 CLI / root 目标语义

这段是给 LLM / agent 的长期产品约定，避免把 branch channel 和 config root 混在一起：

- `main`：未来等同 Stable/default branch；固定对应 `MMD/mmd` 目标入口，等待 stable 追到当前能力后切换完成。
- `dev`：作者平时常用的开发通道；固定对应 `MMF/mmf`。
- `canary`：最激进的金丝雀通道；固定对应 `MMG/mmg` 目标入口。
- 当前已经实现的入口仍然是 `mms` / `mmf`：
  - `mms -> ~/.config/mms`，stable/current config root。
  - `mmf -> ~/.config/mms-next`，preview config root。
- `mmd` / `mmg` 是目标命名；实现前不要在代码、文档或用户回复里暗示它们已可用。
- 新逻辑上 `Dev channel` 与 `mmf` 语义绑定；实现细节仍要避免把 branch checkout 和 config root 误写成互相覆盖的同一件事。

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

如果一台白天用、一台晚上用，建议两台都装 `Dev`，并尽量保持同一个 commit / channel。MMS 默认安装目录是 `~/.mms`，`mms` / `mmf` 是同一套安装里的两个 config root，不是两套代码版本。

需要真正并存多个代码 channel 时，先用 VM、独立用户或明确的安装前缀方案；不要让两个 channel 同时覆盖同一个 `~/.mms`。
