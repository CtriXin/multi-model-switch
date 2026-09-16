# v4.16.0 · K3 的 1M 落到每个 harness，配置 Web UI 降级，CI 开始跑测试

## K3 现在在四个 harness 上都是 1M

- **profile 的 context 不再来回改**（#209）：`k3` 的窗口两天内被两个 agent 改了三轮，每轮都漏掉一个 alias，结果 dev 上 profile 说 1M、测试说 256K，四个测试是红的。现在 `k3` / `k3[1m]` / `kimi-k3` 一起锁在 1048576，由 `tests/test_provider_profiles.py::test_kimi_k3_aliases_agree_on_one_million_context` 守住。
- **恢复 `k3-256k`**（#209）：它是 Moonshot 自己的 256K 变体，不是被降级的 k3。上一版把它的 profile 条目删掉后，它被静默解析成 1048576，用它跑长会话会直接撞上下文超限。
- **`k3` 的输出上限改回 131072**（#209）：上一版把它抬到 1048576，没有来源支撑；官方标定记录里输出上限是空的。输出上限报大不会被截断，而是请求被拒。
- **Codex 终于知道模型有多大**（#213）：Claude Code、Pi、OpenCode 一直都被告知 context window，Codex 什么都没收到，只能用它自己对未知模型的默认值。现在选中的模型解析到 1M 以上时，会写进 Codex gateway 的 `model_context_window`。只放大不缩小，OpenAI 自己的模型跳过，换模型时会把这个值取走。

## 配置 Web UI 降级

- **`mms config web` 不再是配置入口**（#212）：Pilot 和终端写同一个配置根，Pilot 里保存的通道就是 `mms claude` 启动时用的那份。命令仍然可用，启动时会说明它只剩账号、偏好、Skill / MCP、迁移和人工确认这些 Pilot 还没覆盖的部分。
- **人工确认页不再写错要改的文件**（#212）：那些卡片仍然写着 `~/.config/mms/config.toml`、`usage.json`、`version.json`、`accounts/**`，但配置早就搬到了 `~/.config/mms-next`，等于在请你批准一个不会被写的路径。现在按实际位置显示。

## CI 开始跑测试

- **PR 会因为它改红的测试而失败**（#210）：之前 CI 只有两个 AI reviewer，没有任何一步执行测试，所以上一版顶着两个 SUCCESS 合进来同时改红了四个测试。
- 做法是比较而不是断言：在 PR 的 base commit 上跑一遍套件，在 head 上再跑一遍，只有在 base 通过、在 head 失败的测试才让检查失败。不需要维护豁免名单。
- 这个检查不需要 secret，所以**从 fork 提的 PR 也会跑**；原有的两个 reviewer 对 fork PR 是跳过的。
- 本地同样可用：`python3 scripts/ci_pytest_regression.py --base origin/dev`

## 其他

- **拉取模型覆盖而不是合并**（#211）：通道里已经删掉的模型，拉取后保存会从本地路由里消失，不再只是取消勾选。行为在上一版已经修好，这次补上覆盖完整用户路径的回归测试。
- **第二次 Ctrl-C 不再抛栈**（#208）：`mms config web` 停止时连按两次 Ctrl-C 会打印一段 traceback。清理路径在主线程留了一个可被中断的等待，现在进入清理前先忽略 SIGINT。

## 升级须知

- 本次会替换安装目录里的 `mms`、`mmf` 和 Pilot。如果同机有 `mms` 会话在跑，建议等它结束再更新。
- 更新过程中 Pilot 会重启，页面会自动刷新；重启期间已在跑的网页会话会短暂断开。
- 如果你之前把 `k3` 的 context 手动改过，你自己的设置仍然优先，profile 只在你没设的时候生效。
- `mms config web` 仍然可用，只是启动时会多打印一段降级说明。如果你的脚本用 `--print-summary` 取 JSON，那段说明走 stderr，stdout 不受影响。
