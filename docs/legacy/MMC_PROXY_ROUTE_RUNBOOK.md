# MMC Loopback Proxy Route v1 (Retired)

> Retired: the public `mmc` entrypoint is no longer installed by MMS. This document is kept only as historical context for the old isolated Claude OAuth experiment. Do not use it as current setup guidance.


## 结论

这套方案的目标很窄：`mmc / mms` 只看见本地 `127.0.0.1:31xxx`，背后的 tunnel / server / static IP proxy 全部藏在网络层；route 不通就 fail-closed，不做自动切换，不做同账户 load-balance。

## 适用范围

- 适合：`OAuth Claude -> mmc`
- 适合：你已经有现成的 private tunnel / reverse tunnel / local agent，可以把远端服务映射成本地 `127.0.0.1:<port>`
- 不适合：同一个 OAuth account 想在多个 proxy 之间轮询、随机切换、动态调度
- 不适合：把 `mmc` 做成通用本地代理编排器或 Clash 替代品

## 为什么它能降低本地网络不稳定影响

- `mmc / mms` 只连本地 loopback，CLI 侧不再直接依赖外部 proxy URL / IP / credential
- 本地只维护一条到 tunnel 的短链路；真正的 static IP proxy 和上游访问都放在服务器侧
- `mmc doctor` 和运行时 guard 都会验证本地 route 的 reachability、upstream health 和 exit IP
- route 失效、出口漂移、关键域名探测失败时，`mmc` 会直接拒绝启动或终止 session，不会 silent fallback 到直连
- 运行中的 fail-closed 现在会终止整个 `Claude` process group，不只杀主进程，降低 MCP / tool 子进程残留的旁路风险
- `XDG_RUNTIME_DIR`、`NPM_CONFIG_CACHE`、`NODE_GYP_DIR` 都会被重定向到 session 隔离目录，不再落到宿主全局缓存

## 目标链路

```text
mmc / mms
  -> 127.0.0.1:31001
  -> existing tunnel / local agent
  -> server 127.0.0.1:41001
  -> static IP proxy
  -> upstream
```

## 最小 route schema

字段：

- `id`: route id，供 `mmc --route-id` 使用
- `purpose`: 当前 v1 主要用 `oauth_claude`
- `local_proxy_url`: 本地 loopback proxy，仅允许 `127.0.0.1 / localhost / ::1`
- `sticky_account_binding`: 绑定当前 OAuth account，至少填一个稳定标识
- `expected_exit_ip`: doctor 和运行时 pin 的预期出口 IP
- `health_targets`: 通过该 route 检测的上游目标

示例文件：

- `config/mmc-proxy-routes.example.json`

约束：

- 不允许非 loopback `local_proxy_url`
- 不允许在 `local_proxy_url` 里写 credential
- 不允许同一个 OAuth account 绑定到多个 route
- `oauth_claude` route 必须有 `sticky_account_binding`

## 启动方式

推荐：route file + route id

```bash
python3 mmc run \
  --route-id claude-route-a \
  --routes-file config/mmc-proxy-routes.example.json
```

手工调试：直接给本地 loopback URL

```bash
python3 mmc run --proxy http://127.0.0.1:31001
```

说明：

- `--route-id` 会先查 `--routes-file`
- 未传 `--routes-file` 时，默认读取 `~/.config/mmc/proxy-routes.json`
- 也可以设置 `MMC_PROXY_ROUTES_FILE`
- 直接 `--proxy` 只接受 loopback URL；外部 proxy URL 会被拒绝

## doctor 检查项

```bash
python3 mmc doctor --route-id claude-route-a --routes-file ~/.config/mmc/proxy-routes.json
python3 mmc doctor --proxy http://127.0.0.1:31001
python3 mmc doctor --strict --route-id claude-route-a --routes-file ~/.config/mmc/proxy-routes.json
```

`doctor` 会检查：

- route/schema 是否合法
- local loopback proxy 是否可达
- 通过该 route 访问 `health_targets` 是否成功
- 当前出口 IP 是否能测出
- 如果配置了 `expected_exit_ip`，是否与预期一致
- inherited env 里是否有高风险代理变量
- 当前 shell 是否已经在 MMC session 内
- 当前是否通过 `sudo/root` 运行，是否存在把 `~/.config/mmc` 写成 root 所有的风险
- `launcher/account` 关键 state 文件是否可写
- 当前终端是否是 TTY；若不是，Claude 交互能力可能退化

补充：

- `--strict` 会把 warning 也当成失败，适合真正启动前做“必须干净”的检查
- 默认 `doctor` 仍然允许带 warning 通过，适合日常排查

## Session Janitor

清理 stale slot 与 orphan tmp：

```bash
python3 mmc session prune
```

说明：

- 这个命令不会动真实 Claude/MMS 配置
- 只清理 MMC 自己的 `accounts/default/s/*` stale slot 和 `tmp/*` orphan runtime
- 适合在崩过、强杀过、或者怀疑有残留时手动跑一次

## MMS 最小接入点

这轮不改 `mms` 主 routing 语义，只保留现有最小接入：

- `OAuth Claude -> mmc`
- `mms` 侧如果 human 手工把 `runtime.proxy` / `provider.proxy` 指到 `http://127.0.0.1:31xxx`，现有委托链就能工作
- 这轮没有新增 `mms -> mmc --route-id` 透传，避免扩大 protected surface

换句话说，v1 先把 `mmc` 路线跑通；`mms` 继续只把 local loopback proxy 当成普通本地 proxy endpoint 使用。

## 最小 tunnel 启动模板

客户端模板：

- `scripts/mmc-loopback-tunnel-template.sh`

用法：

```bash
SSH_TARGET=ubuntu@example-host LOCAL_PORT=31001 REMOTE_PORT=41001 \
  ./scripts/mmc-loopback-tunnel-template.sh
```

服务端最小契约：

- 只监听 `127.0.0.1:41001`
- 不要求开放新的公网业务端口
- 由你现有的 tunnel / reverse tunnel / agent 把它映射回本地 `127.0.0.1:31001`

## 承载机建议

优先原则：

- 选你可长期控制、可观测、可复用的固定承载机
- server 侧 route service 只监听 loopback，不直接暴露公网业务端口
- 每个 OAuth account 固定绑定一条 route，不做同账户多出口漂移
- 先在一台机器上把第一条 route 跑稳，再扩第二承载点

## 端口号段建议

客户端本地保留：

- `127.0.0.1:31001-31032`

服务端 loopback 保留：

- `127.0.0.1:41001-41032`

建议固定映射：

- `31001 -> 41001 -> route A`
- `31002 -> 41002 -> route B`
- `31003 -> 41003 -> route C`

这样后面继续加 route 时，不需要改现有 route 的端口和 account pinning。

## 为什么同一个 OAuth account 不能做 load-balance

- OAuth session 本身有明显的 account identity 和风控语义
- 同一 account 在多个出口间漂移，最容易触发“不稳定 / 异常来源”类问题
- route pinning 可以把“哪个 account 走哪个出口”固定下来，排障和追责也更直接

## 怎么加第二个 / 第三个 route

1. 在 server 上新增一个只监听 `127.0.0.1:4100x` 的 route service
2. 在本地把它映射成 `127.0.0.1:3100x`
3. 在 `proxy-routes.json` 新增一个 route 条目
4. 给新 route 绑定独立 OAuth account
5. 先跑 `mmc doctor --route-id <new-route>`
6. doctor 通过后，再把对应 account 固定到这个 route

## 不做的事

- 不做自动 route 切换
- 不做 route 轮询
- 不做同账户多出口漂移
- 不把真实 server 地址、external proxy URL、credential 写进 git
