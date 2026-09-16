# v4.19.1 · 安装、能力与配置根修复

本版是 v4.19.0 之后的修复版，重点是让安装升级提示、模型识图能力和单一配置根保持一致。

## 修复

- 安装器遇到正在运行的 Pilot 时，明确提示从 Pilot 的更新入口或 `mms web stop` 处理；`--keep-running-pilot` 保留兼容但不再暗示会自动停止或重开 Pilot。
- 恢复 `k3[1m]` 与 `mimo-v2.5[1m]` 的识图兜底，并用 profile 到 Pi 的完整链路测试固定这条真值链。
- 修复 bridge 在 `mms-next` gateway HOME 下写入 `lb_debug.log` 的路径，避免出现重复的 `.config/mms-next/.config/mms-next`。
- 修正 Pilot 模型拉取后未返回模型的提示文案，并重建静态 bundle。
- 让 session catalog、prune、resume 使用与 launcher 相同的显式配置根解析器。
- 同步 English README 中已经退休的 Caveman、token-saver 和旧版能力包说明。

## 升级须知

- 会话历史、运行状态、通道、账号和 API key 不由本次版本 bump 改写。
- `k3[1m]` 保持能力解析支持，但不重新加入产品展示 roster；用户仍通过已有模型入口使用它。
- 配置根继续是 `~/.config/mms-next`，不恢复 legacy `~/.config/mms` 回退。

## 验证

- PR #226、#227、#228 已按顺序合入 `dev`，三项 CI 均通过。
- 发布 worktree 通过 real-home marker、安装路径、Web、单配置根和相关回归测试。
- Pilot frontend type-check/build、Python compileall 和 `git diff --check` 通过。
