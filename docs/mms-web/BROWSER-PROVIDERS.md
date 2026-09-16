# Browser Provider 路线

浏览器不是 MMS Bot 自己实现的核心能力。Bot 只依赖统一的 `BrowserProvider` 能力合同，由平台选择当前系统可用的执行器。

## Provider 选择

| 平台 / 条件 | Provider | 负责范围 |
|---|---|---|
| macOS 且已安装 Ego | Ego | 持久 TaskSpace、登录态、导航、读取、点击、输入、截图、用户接管 |
| Windows / Linux，已有授权 Chrome 或 Edge CDP | Web Access | 通过 CDP 操作授权浏览器页面，读取、导航、交互、截图 |
| 没有可用 Provider | none | 明确显示浏览器能力不可用，不模拟成功 |

Provider 选择是显式能力探测，不做静默的跨浏览器降级。用户正在使用的登录态、浏览器权限和是否允许接管，都必须由 Provider 自己确认；MMS 不复制 profile、cookie 数据库或凭据。

## Windows 版本的现实边界

Web Access 可以连接 Chrome、Edge 或 Chromium 的 CDP，但它解决的是“浏览器内的 Computer Use”，不是任意 Windows 桌面控制。Windows 桌面应用、系统对话框、资源管理器、原生客户端仍然需要单独的 Desktop Provider，不能假装已经支持。

Windows 的第一版应支持：

1. 发现用户明确授权的 Chrome / Edge 调试实例。
2. 由 Web Access 执行网页导航、DOM / 页面读取、点击、输入、上传和截图。
3. 在 Bot 聊天中展示 Provider、权限、当前页面和结果。
4. Provider 不可用时，让 Bot 解释“需要打开并授权浏览器”，而不是启动另一套浏览器或伪造结果。

## 三种状态的产品定义

| 状态 | 运行载体 | 用户体感 | 生命周期 |
|---|---|---|---|
| CLI Harness | Terminal 中的一次 Pi / Harness 进程 | 自己盯着做，控制最直接 | 通常是一次会话 |
| Pilot Web Chat | Web UI 驱动的 Pi Harness session | 像 ChatGPT 一样直接对话 | 会话级，可继续和恢复 |
| MMS Bot | 持久 Bot 记录 + 一个或多个 Harness session | 像给员工交代目标，员工会执行、分工、等待和回报 | Bot 级；session 可以重启或替换 |

Bot 不是“更长的 Chat session”。它拥有独立身份、角色、模型偏好、Skill 组合、memory、调度、协作收件箱和结果记录。当前实现仍然使用 Pi session 作为执行载体，但 session 只是员工的运行实例，不是员工本身。

## 实现顺序

1. 已把当前 `EgoComputer` 收敛到 `BrowserProvider` 合同，保留 Ego adapter；能力探测会返回 provider、scope 和支持的 semantic operations。
2. 增加 `WebAccessProvider` 的 Windows / Chrome / Edge 适配和显式能力状态。
3. 让 Bot prompt 只看到统一的 browser tool contract，不看到平台分支。
4. 最后再评估 Windows Desktop Provider；没有成熟复用项目前不自研。
