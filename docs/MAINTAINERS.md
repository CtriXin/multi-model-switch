# 维护者入口

这份文档是给在这个仓库里施工的人和 agent 看的操作手册。**规则**在 [`../AGENT.md`](../AGENT.md) 和 [`AGENT_GUARDRAILS.md`](AGENT_GUARDRAILS.md)，**项目全貌和踩过的坑**在 [`AI-ONBOARDING.md`](AI-ONBOARDING.md)。

## 本机命令矩阵

```text
mms -> public installed copy   # 只用于复现公开版本的问题，不是开发入口
mmf -> dev worktree            # 日常开发
mmg -> canary worktree         # 已停更的实验线
```

这三个命令由 `scripts/link_local_channel_commands.sh` 生成到 `~/.local/bin`。`mmd` / `mmm` 已退休，这个脚本会删掉它自己写过的这两个包装器。

三个命令共用同一个 config root `~/.config/mms-next`，**不是三套配置**。普通用户不需要这些，用安装器的 `--channel` 参数就行。

启动更新提醒默认只提醒、手动确认：`mmg` 每次启动检查，`mmf` 每日检查，`mms` 每日只提示 public installed copy。手动 `mmf update` / `mmg update` 只允许 clean worktree 的 fast-forward；dirty 或分叉会拒绝。

## 开发循环

仓库**根目录**是维护者的调度入口，应该 checkout `dev` 并保持干净、最新。`.worktrees/*` 只用于具体 issue / PR 的隔离施工——**不要**把 `.worktrees/dev` 当成多人共享的默认开发入口。

1. 进根目录，确认当前分支是 `dev`。
2. `git pull --ff-only`。
3. 先开 issue，把计划写进 issue 或对应的计划文档。
4. 从最新 `dev` 创建独立 worktree / branch，例如 `.worktrees/issue-14-redline-gate`。
5. 在这个隔离 worktree 里开发、验证、commit、push。
6. 提 PR，等评审。
7. 评审通过后合并，根目录再 fast-forward 到最新。

**判断 base 分支**：修 bug 或 4.x 用户也该拿到的能力 → `main`；只跟 Bot 工作台有关 → `dev`；不确定 → `main`。`main` 上的改动默认回流 `dev`，所以往 `dev` 补容易，从 `dev` 往 `main` 摘就难。

除非人类明确要求直接在 `dev` 根入口编辑，agent 不得在共享 `dev` 入口叠加实质性改动或留下未跟踪文件。docs-only 的计划 / 报告类改动在用户要求"记录 / 提交 / 产出文档"时可以默认 commit，但**只 stage 目标文档**，不带任何无关脏文件。

### 辅助脚本

```bash
scripts/dev_doctor.sh                       # 只检查并报告，不自动改
scripts/start_issue_worktree.sh 14 redline-gate
scripts/cleanup_merged_worktree.sh <branch-or-pr>
```

`dev_doctor.sh` 报告：根目录是否在 `dev`、是否落后 `origin/dev`、共享根目录有没有脏文件、旧 `.worktrees/dev` 是否仍占用 `dev`、`mmf` 是否指向根目录 dev checkout、有没有 git 标记的 prunable worktree。**它不会自动删除或 reset。**

`start_issue_worktree.sh` 先确认根目录 dev 干净并 fast-forward，再创建 `issue/<number>-<slug>` 分支和对应 worktree。

`cleanup_merged_worktree.sh` 只删除已合入 base 且 `git status` 干净的 worktree；传 PR 编号或能被 `gh` 解析的 branch 时也支持 squash / rebase merge 的 merged 核验。遇到未合并、未 push、未提交或未跟踪文件会保留现场并报告原因。如果 agent 执行了 merge 并且能识别对应的本地 task worktree，merge 成功后应该跑这个脚本清理，除非人类明确要求保留。

## 版本号与发版

**一个合并的 PR = 一个 patch 版本。** 纯文档包不 bump。

**作者不碰版本文件，合并方在合并时盖版本号。** 否则 N 个在飞的 PR 会在 `mms_version.py` 上 N 路冲突。release note 和 bump 放在一个单独的 commit 里，别混进对方的改动，保住对方的 authorship。

版本一致性由 `tests/test_mms_release_version.py` 守着，要求同时对齐：

- `mms_version.py`
- 根 `package.json`
- `apps/mms-web/package.json`
- `apps/mms-web/package-lock.json` 的 `version` 和 `packages[""].version`
- `mms_web_static/build.json` 的 `version` 与每个文件的 sha256
- `docs/mms-web/RELEASE-v<版本>.md` 必须存在

发版没有自动化，手动流程：

```bash
# 1. 合并 PR
# 2. bump + release note，单独一个 commit
# 3. 推分支
git push origin HEAD:<branch>
# 4. 打 tag 并推
git tag -a v<版本> -m "..."
git push origin v<版本>
# 5. 建 release
gh release create v<版本> --verify-tag \
  --notes-file docs/mms-web/RELEASE-v<版本>.md \
  --latest              # 4.x 稳定线用 --latest
# gh release create ... --prerelease    # 5.x 预览线用 --prerelease
```

`/releases/latest` 永远不返回 prerelease，这是 4.x 用户不会被推到 5.x 的原因。

## 前端构建

**任何 `apps/mms-web/src` 的改动必须在同一个 PR 里重建 `mms_web_static/`。**

```bash
cd apps/mms-web && npm ci --workspaces=false --ignore-scripts
cd ../.. && python3 scripts/build_mms_web_release.py --skip-install
```

**必须 per-workspace 安装。** 在 workspace 根上跑 `npm ci` 会解析出锁文件之外的传递依赖，产出不一样的 bundle，还会把 `tsc` hoist 到别处。

`build.json` 的 `sourceSha256` **不是**可复现性门禁：它只覆盖 src 加 5 个配置文件，不覆盖装出来的 `node_modules`。只改版本号时 `version` 和 `sourceSha256` 会变但资源 hash 不变，这是正常的。

## 门禁

跑任何测试之前先隔离环境，否则可能写穿真实配置根：

```bash
env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME <命令>
```

| 门禁 | 命令 | 注意 |
|---|---|---|
| Python 回归 | `python3 scripts/ci_pytest_regression.py --base origin/main` | 会单独列出"base 红且此处已不存在"的测试，别把删掉的红测试当成修好了 |
| 新用户视角 | `python3 scripts/regression_fresh_user_gate.py` | 对并发敏感，串行跑一次；`--quick` 只用于紧急小修，push 前要补全 |
| 前端类型 | `apps/mms-web/node_modules/.bin/tsc --noEmit -p apps/mms-web` | **不要用 `npx tsc`**，从仓库根解析会命中 decoy 包导致假失败 |
| 前端测试 | `node --test apps/mms-web/tests/*.test.mjs` | glob 是必须的 |
| 语法 | `python3 -m py_compile <改动的文件>` | 碰高风险文件时必跑 |

改动触及 `mms_core.py`、`mms_launchers.py`、installer、session index、config root、resume、HOME/XDG 隔离、wrapper 或 release channel 时，交付里**必须**写明 fresh-user gate 的实际结果。

`.github/workflows/digger.yml` 是仓库唯一的 CI。

## 发布门槛

Stable（`main`）候选至少需要：

- `bash install.sh --check`
- `python3 -m py_compile` 覆盖改动的 Python 文件
- launcher / Pilot / model route 的定向测试
- `mms doctor` 或 `mmf doctor` 冒烟
- 涉及配置时跑一次 Pilot 的 save-plan / bundle verify 冒烟
- release note 写明升级影响、回滚方式和 channel

Dev（`dev`）候选至少需要：小步 commit、定向测试通过、回归报告写明未测范围。

## 多台工作机

如果两台机器要保持一致，装同一条 channel，必要时用 `--ref <commit-or-tag>` 固定到同一版本。MMS 默认装在 `~/.mms`，**不要**让两条 channel 同时覆盖同一个 `~/.mms`；真要并存多个代码 channel，用 VM、独立用户或明确的安装前缀。
