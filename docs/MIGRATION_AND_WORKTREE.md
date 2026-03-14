# 配置迁移与 Worktree 迭代说明

## 当前目标

把旧版 `ccs` 的全局配置逐步迁到 `mms`，并把账号目录重命名产品化，避免后续在多个 worktree 里继续手工改：

- `~/.config/ccs/config.toml`
- `~/.config/ccs/credentials.sh`
- `~/.config/ccs/usage.json`
- `~/.config/ccs/accounts/*`

## 正式命令

### 1. 一键迁移

```bash
./mms config migrate
```

也可以在主界面里：

1. 进入 `./mms`
2. 按 `O`
3. 选择 `迁移配置到 mms`

行为：

- 优先把旧的 `credentials.sh` / `usage.json` 复制到 `~/.config/mms/`
- 将账号目录迁到 `~/.config/mms/accounts/`
- 规范化 `config.toml` 中账号的 `home_dir`
- 自动生成备份到 `~/.config/mms-backups/`
- 备份阶段会保留账号目录中的 symlink；即使存在断链 symlink，也不会在第一步直接报错中断

### 2. 重命名账号目录

```bash
./mms config account.rename <old_id> <new_id>
```

也可以在主界面里：

1. 进入 `./mms`
2. 按 `O`
3. 选择 `管理现有通道`
4. 进入对应官方通道
5. 选择 `重命名这个通道`

### 3. 重命名网关通道

```bash
./mms config provider.rename <old_id> <new_id> [new_name]
```

也可以在主界面里：

1. 进入 `./mms`
2. 按 `O`
3. 选择 `管理现有通道`
4. 进入对应网关通道
5. 选择 `重命名这个通道`

行为：

- 更新账号 `id`
- 默认把 `显示名` 也改成 `new_id`
- 更新 `home_dir`
- 同步 `account.defaults`
- 同步 `usage.json` 里的本地统计键
- 自动生成备份到 `~/.config/mms-backups/`

说明：

- 这里的 `id` 就是主界面里的 `文件夹名`
- 如果只想改单独的显示名，用 `./mms config account.edit <id>`

## 建议工作流

### 单人继续迭代

1. 先执行 `./mms config migrate`
2. 再执行若干次 `./mms config account.rename`
3. 用 `./mms config account.list` 确认结果

### 多 worktree 并行

建议把“全局配置目录”和“仓库代码改动”分开看：

- 仓库代码：
  - 走 Git 正常提交
  - 在各自 worktree 内独立开发
- 全局配置：
  - 只在一个工作分支里集中整理一次
  - 整理前先备份
  - 整理后用文档记录最终命名方案

不建议：

- 在两个 worktree 里同时改 `~/.config/mms/`
- 手工 `mv` 账号目录但不改 `config.toml`
- 手工改 `usage.json` 键名

## 当前命名约定

官方账号统一用两层概念：

- `显示名`
  - 给你看的名字
- `文件夹名`
  - 目录名
  - 命令里的账号 ID
  - 例如 `apple-codex`、`boss2-claude`

## 回滚

每次正式迁移或重命名都会先备份：

```text
~/.config/mms-backups/<action>-<timestamp>/
```

如果这轮结果不满意，可以从备份目录恢复。

## 交接提示

后续如果在其他 worktree 继续这条线，先看：

- [task_plan.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/task_plan.md)
- [findings.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/findings.md)
- [progress.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/progress.md)
- [docs/ADAPTER_REGISTRY.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ADAPTER_REGISTRY.md)
- [docs/ITERATION_PLAN.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ITERATION_PLAN.md)
