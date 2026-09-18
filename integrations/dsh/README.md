# MMS DSH（独立扩展预览）

让原版 DSH 使用 MMS approved model bundle，并用 DSH 的公开 command / request hook 执行 MMS Recipe。没有 fork 或修改 DSH 内核。

当前固定 DSH `0.1.6-alpha.2`，`package-lock.json` 固定完整依赖；Node 需 >=24.2。安装后源码、依赖、会话都在独立目录，不依赖任务 worktree 继续存在。它是本机可用的集成预览，不是替代整个 Pilot 的发布版。

## 已接入

- 只读加载 MMS latest-approved manifest，验证 canonical paths、所有文件 hash、revision 和非 secret 文件的边界。
- 保留逻辑模型名、wire model ID、provider、主/备用顺序、可见性、上下文及 capability 来源。DSH 模型列表明确展示 provider；备用通道由用户显式选择，没有跨账号静默回退。
- 非 OpenAI 双协议通道优先 Anthropic Messages；OpenAI 系列使用 Responses。URL 沿用 MMS SDK root 语义，不把裸 root 错发到 `/responses`。
- MMS 明确声明的 effort 与默认偏好映射到 DSH selector。仅有偏好而无完整支持列表时，只暴露该偏好；approved/policy 缺少的能力字段用当前 MMS 版本随附的非 secret profile metadata 补齐，记录来源和文件 hash；仍未知的字段保守处理。
- 独立 HOME / XDG / DSH_HOME；启动环境不继承 API keys、OAuth paths、NODE_OPTIONS 或真实 MMS HOME aliases。MMS key 仅写入本实例 0600 credential store，不写入 shareable config、Git 或 shell env。重启仅更新 `MMS_DSH_*`，保留用户自己添加的 DSH credentials。
- `/recipe list`、`/recipe import <绝对路径>`、`/recipe use <id> {"变量":"值"}`、`/recipe clear`。复用 Pilot 的 Recipe parser/render，支持 v1/v2 导入、变量和示例。图片、推理、Skills 在每次实际请求前验证；中途切模型和重启不会解除约束。
- 浏览器内工作目录选择，独立后台进程，可停止、再启动并续接会话。
- `cache_transport_evidence.v1` 记录真实 URL/path、模型、协议、effort/budget、HTTP 状态和 bundle revisions；不记录 key、headers 或 prompt。

## 本机入口

本次安装路径：`~/.local/share/mms-dsh`。启动入口：`~/Applications/MMS DSH.command`（指向独立安装）。双击会启动或复用本实例，并打开当前认证 URL。默认监听 `127.0.0.1:3091`。

`MMS DSH.command start|stop|status|open` 管理自己的进程。它不注册开机自动启动，不操作 Pilot 服务。停止保留会话；再次启动重新读取最新 approved MMS bundle。运行期间模型表是启动快照，修改 MMS 通道后重启此实例刷新。

## 安装/开发

```bash
python3 integrations/dsh/install.py \
  --destination /path/to/mms-dsh \
  --mms-root /path/to/mms-next \
  --node /absolute/path/to/node
```

安装器从本目录 lockfile 执行 `npm ci --ignore-scripts`；可用 `--runtime-from` 复用版本与 lock 完全相同的已安装 runtime。目标目录已存在时拒绝覆盖。仓库现有 mms launchers、MMS config 和 DSH 原版安装均不作为写入目标。

## 当前边界

- 已实测的模型/协议列在本任务 regression report；68 条配置路由不是 68 条真实调用验收。
- 缺少 approved API key 的 OAuth 路由不自动导入；image generation endpoint 不作为聊天模型导入。整体 bundle readiness 为 false 时保留诊断，逐条筛掉不可启动的 leaf，而不掩盖缺 key。
- 暂无 MMS 自动 provider failover、账号登录导入、Recipe 图形模板库或 `planning=true` 模板的等价行为；规划模板明确拒绝，仍用 Pilot 执行。Skills 用 DSH 当前会话的真实可用 catalog，未自动复制全局 skill packs。
- 手机公网/LAN、电脑重启后自启、原 Pilot 会话迁移、Fleet/Bot 产品层未包含在这一版配置中。会话保存与进程自启是不同能力。
- 固定版本升级需重跑适配与实际交互验证；不自动追踪 alpha。

扩展首先放在独立插件/profile。只有后续必需功能缺少公开扩展点，并经实际验证后，才考虑有明确 diff 边界的 fork。
