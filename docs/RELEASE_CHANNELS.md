# MMS Release Channels

MMS 采用 Stable / Dev / Canary 三通道。目标是把“普通用户能放心装”和“作者每天快速迭代”分开。

## 通道定义

| Channel | Git source | 安装参数 | 用户 | 规则 |
|---|---|---|---|---|
| Stable | GitHub Release / `release/stable-*` | `--channel stable` / `--stable` | 普通用户、生产环境 | 慢更新，只收验证过的修复和兼容功能 |
| Dev | `dev` | `--channel dev` / `--dev` | 作者日常工作机、需要最新修复的人 | 小步提交，targeted tests 通过即可推进 |
| Canary | `canary` | `--channel canary` / `--canary` | 测试机、夜间试验 | 最快，可破，但必须可回滚 |

## 当前过渡策略

- `main` 暂时不停止迭代，会和 `dev` 同步一段时间，避免已有安装入口突然断档。
- `dev` 和 `canary` 已从当前 main 切出；后续新功能优先进入 `dev` / `canary`。
- `release/stable-v3.3-no-db` 继续作为 stable 维护线，逐步 cherry-pick 已验证的 Web UI / Thinking / model route 修复。
- 等 stable 追上当前主功能后，再把 GitHub default branch 是否继续叫 `main` 单独决策。

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
- 记录破坏面，不假装稳定

## 两台个人工作机

如果一台白天用、一台晚上用，建议两台都装 `Dev`，并尽量保持同一个 commit / channel。MMS 默认安装目录是 `~/.mms`，`mms` / `mmf` 是同一套安装里的两个 config root，不是两套代码版本。

需要真正并存多个代码 channel 时，先用 VM、独立用户或明确的安装前缀方案；不要让两个 channel 同时覆盖同一个 `~/.mms`。
