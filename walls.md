# walls · bot/T8e-no-reverse-dns

## 2026-09-17 18:15 SGT · glm-4.7 · T8e packet (bot-work, origin/main)

需求: 按 `docs/mms-web/bot-work/T8e-reverse-dns-blocks-the-remote-access-switch.md`，修「打开手机访问会卡住整个 Pilot 30 秒」：`ThreadingHTTPServer` 构造时标准库 `server_bind` 里的 `socket.getfqdn()` 做反向 DNS，在不回 PTR 的家用网络（本机 192.168.23.16 实测 30.00s）阻塞 30 秒，且 `set_remote_access` 持有 `mutation_lock`，期间所有 POST 排队、前端健康轮询超时报断开、开关停在 pending 变灰。

包：T8e
分支 / worktree / base ref（含实际 commit）:
- 分支: `bot/T8e-no-reverse-dns`
- worktree: `/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/wt-T8e`
- base ref: `origin/main` = `8a52a2da`（4.22.4；T8e 包文档 commit 是 `69bc57ba`，base 判定为 origin/main 当前 HEAD，两 commit 间只有 T8f 包文档差异，与 `mms_web/server.py` 无关）

改动文件（git diff --stat）:
```
 mms_web/server.py | 27 +++++++++++++++++++++++++--
 1 file changed, 25 insertions(+), 2 deletions(-)
```
新增: `tests/test_mms_web_listener_bind.py`（4 测试）、`docs/mms-web/design/t8e/`（2 张真机截图）、`.ai/regression-reports/2026-09-17-t8e-no-reverse-dns-bind.md`、本文件。

### 处置

主修（包第三节，唯一改法）: 新增 `NoReverseDNSHTTPServer(ThreadingHTTPServer)` 子类，覆盖 `server_bind` —— 直接调 `socketserver.TCPServer.server_bind(self)`（跳过 `HTTPServer.server_bind` 里的 `getfqdn`），`server_name` 设为 host 字符串、`server_port` 设为 port。docstring 写明原因（反向 DNS 在不回 PTR 的网络上阻塞实测 30s，且 `server_name` 只被标准库 CGI 管线消费、本服务从不使用），防止后人"顺手清理"。
- 替换了 `mms_web/server.py` 里全部两处 `ThreadingHTTPServer` 构造点: `create_server` 内的主 server（原 `:690`）与 `RemoteListeners.sync` 内的每地址监听器（原 `:728`）。
- 新增 `import socketserver`（覆盖里显式调 `socketserver.TCPServer.server_bind`）。
- `RemoteListeners._servers` 的类型注解 `dict[str, ThreadingHTTPServer]` 保持不变（子类是该类型的子类型，零语义变化）。

不做的（包明令禁止）:
- **没有**把 `set_remote_access` 移出 `mutation_lock`（v4.18.0 的解法，这次不适用——真写操作应持锁；修掉阻塞后绑定毫秒级）。
- 没有动 `mms_web/remote_access.py`、4.22.2 的凭据修复（`_switch_cookie`）、`_gate()`、关闭开关路径、保护文件。
- 前端一行未改 → **未重建 bundle**（门禁第六节的豁免条件成立；`apps/mms-web/dist` 为 gitignored，仅为本地起验证实例构建，不进 commit）。

### 验证

测试（全部 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`）:

1. 新增 `tests/test_mms_web_listener_bind.py`（4 passed）:
   - `test_main_server_bind_does_no_reverse_dns` —— patch `socket.getfqdn` 为记录调用+sleep 的桩，走 `create_server` 构造主 server，断言桩零调用、`server.server_name == "127.0.0.1"`。
   - `test_remote_listener_bind_does_no_reverse_dns` —— 同桩走 `RemoteListeners.sync(["127.0.0.1"])`，断言零调用、地址进入 `active`。
   - `test_sync_stays_fast_when_reverse_dns_would_stall` —— 桩 sleep 1.5s，`sync` 全程耗时 < 1.0s（未修时必然 ≥ 1.5s）。
   - `test_close_actually_releases_the_port` —— 持有 server 引用防 GC 误关 socket、spy `server_close`，断言 `close()` 真正调用 `server_close()` 且 `connect_ex` 被拒绝。
2. 定向回归 11 文件（listener_bind + remote_access + remote_access_cookie + lan_switch + server + status + integration + connections + interactions + artifact_flow + configuration_flow）: **109 passed, 4 subtests passed**。4.22.2 的 cookie/切换测试全绿，未放宽任何一条。
3. `python3 scripts/ci_pytest_regression.py --base origin/main`: base 72 failing / head 71 failing（既有失败，与本包无关），**"No test that passes on the base commit fails here"**，另 head 多修复 1 条（`test_wire_duplicate_steer_request_writes_one_command`，base 上也是 flaky 红）。
4. `python3 scripts/regression_fresh_user_gate.py`（完整、串行、env 隔离）: **既有失败，与本包无关** —— `channel-switch-round-trip` 场景在 `task["runAt"]` 处 `KeyError`。按包要求单独复跑 2 次稳定同点红；另在干净的 `origin/main`（`8a52a2da`，detached 临时 worktree）上复跑**同样红在同一处**，证明是 gate 脚本内嵌脚本与 `BotRuntime.create_task` 返回形状脱节，非本包引入。本包改动（server_bind 子类）与 `BotRuntime` 无交集。

mutation（每条实测，改后恢复并确认 `server.py` 与验证状态逐字节一致）:
| mutation | 结果 |
| --- | --- |
| 删掉 `server_bind` 覆盖（回到标准库） | 3 failed（主 server + listener 两条 getfqdn 断言、时长断言）→ 红 |
| `:728` 换回裸 `ThreadingHTTPServer` | 2 failed（listener getfqdn 断言、时长断言）→ 红 |
| `RemoteListeners._close` 去掉 `extra.server_close()` | 1 failed（close 释放断言；初版测试被 CPython 引用计数回收 socket 救绿，已改为持有引用 + spy 后按预期红） | 
| 恢复后 | 4 passed 全绿 |

真机验证（本机即机主报障网络: `socket.getfqdn("192.168.23.16")` 实测 **30.00s**、`getfqdn("127.0.0.1")` 0.01s，具备真实慢反向 DNS 条件，非 patch 模拟）:
- **脚本级对照**（同脚本两环境，直接调 `app.post(["remote-access"], {"enabled": True})`，即 UI 开关走的同一条持锁路径）:
  - BASE（`origin/main` detached worktree）: **30.03s**，`listening=['100.120.8.98','192.168.23.16']` —— 完整复现机主"等一会才打开"
  - HEAD（本 worktree）: **0.03s**，同一 listening 集合；关闭开关 0.49s/0.98s
- **ego-browser 真实 UI**（task space 130，实例 `--port 61742 --state-root /tmp/t8e-verify/state --config-root /tmp/t8e-verify/config`，worktree 代码 + 本地构建 dist）:
  - 设置 →「使用」→ 打开「让手机或另一台电脑访问」: **99ms** 内状态变"已开启 —— 正在监听 100.120.8.98、192.168.23.16"、地址选择器与二维码全部渲染；页面无「正在重连/服务离线/操作未完成」。截图 `docs/mms-web/design/t8e/switch-on-instant.png`
  - `lsof` 实测 3 个 LISTEN: `127.0.0.1:61742`、`192.168.23.16:61742`、`100.120.8.98:61742`
  - 关闭开关: 1039ms 回"已关闭 —— 未监听任何网络端口"，`lsof` 只剩 `127.0.0.1:61742` —— 端口真实释放。截图 `switch-off-released.png`
  - 验证实例已按 PID 关闭（不碰 8767/60824，未 pkill，未按端口批量 grep kill）；task space 已 finish
- 插曲（如实记录）: 第一次浏览器会话中开关曾被意外触发一次（疑似 ego-browser click 重试期间焦点事件触发 POST），前端报「操作未完成」+ 开关 disabled、刷新 401 —— 该实例被整体重置（清 state 重启）后未再复现；重置后全程一次通过。base 上此形态本就对应"请求慢→前端放弃→后端成功"的真实症状，与本包改动无关，且最终验证流程里 UI 状态与后端完全一致。

### 锁内网络调用扫描（包第三节顺带检查，只列不改）

`post()` 的 `mutation_lock` 内路径逐分支扫过，两个同型候选（锁内同步网络/子进程），交 owner 定优先级:
1. `["configuration","discover"]` → `connections.discover_models()`: 锁内同步 `httpx.Client`（`timeout=15, connect=5`，`trust_env=False`）拉远端模型列表。慢/无响应 provider 最坏卡 15s，全部 POST 排队 —— 与本包 getfqdn 同型。
2. `model-settings` 的 `discover`/`check`/`refresh` → `ModelSettings.worker()`: 锁内 `subprocess.run(..., timeout=90)`，子进程（`model_settings_worker.py`）自身会探测 provider endpoints，最坏 90s 持锁。

已确认不在锁内阻塞的: `updates.request_check()`（后台线程）、`update_coordinator.start()`（下载在 `pilot-safe-update` 线程，锁内只有 session_safety 短临界区）、三条 workspace 只读路由（`_UNLOCKED_POSTS`，v4.18.0 已移出）。

### 耗时

约 2.5 小时（含 npm 环境搭建、gate 既有失败排查与 base 对照、浏览器重置重跑）。
