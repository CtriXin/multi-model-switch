# v4.14.0 · 管理本机 Pilot 服务；DeepSeek v4.1 / GLM / Qwen 档位

- **`mms web status / url / start / stop / restart`**（#189）：安装后在后台跑的 Pilot 不再是「不知道在哪」的进程。`status` 列出本机所有在监听的 Pilot（地址、版本、pid、state-root、config-root、来源目录）并标出当前实例；`url` 只打印地址；`start` 已在跑就返回地址，没跑就后台启动并打印地址（日志在 `<state-root>/logs/mms-web.log`）；`stop` 只发 SIGTERM，`--all` 停本机全部 Pilot；`restart` 先停再起。`mmf web ...` 同样可用；`mms web --open` 前台启动不变。
- **DeepSeek v4 全家按 v4.1 能力**（#185）：v4-pro / v4-flash / vision-exp 的旧档位钉扎移除，上下文 1048576、最大输出 393216，`xhigh` 成为独立档位（不再映射到 `max`）；v4-flash / chat / reasoner / vision-exp 识图，v4-pro 仅文本。GLM 5.2/5.3 与 coding-effort 开放 none..max 七档，默认仍为 `max`；Qwen 3.7/3.6 六档，Qwen 3.8 含 `max`。证据记录在 `docs/reference/model-capability-calibration/2026-09-10-deepseek-v41-glm-qwen-tiers.json`。

已设 `reasoning_effort: xhigh` 的 DeepSeek 用户会按真实 xhigh 档发送，不再被抬到 max。版本源、Web package metadata 和静态 Web bundle 同步为 `4.14.0`。
