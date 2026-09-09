# MMS Web API v1

Owner: 当前 Codex。2026-09-08。状态：真实 Pi Web 集成版。

MMS 继续拥有 provider/account/model/channel、协议、优先级与隔离。Web 不建立另一路由数据库。HTTP 包装器由主导实现；外部 agent 只实现下列 Python adapter。JSON camelCase；Python 方法 snake_case。前端类型 `apps/mms-web/src/types.ts` 镜像此合同。

## 数据对象

```ts
type Harness = 'pi' | 'codex' | 'claude' | 'opencode' | 'gemini' | 'agy';
type State = 'running' | 'waiting' | 'idle' | 'completed' | 'stopped' | 'error';
interface Activity { phase: 'running'|'thinking'|'responding'|'tool'|'compacting'|'retrying'|'waiting'|'error'|'stopped'; eventId?: string; toolName?: string; method?: string; since?: string; turnStartedAt?: string }
interface Workspace { id: string; name: string; path: string }
interface Model { id: string; name: string; family: string; providerId: string; providerName: string; harnesses: Harness[]; contextLabel?: string; available: boolean; reason?: string }
interface Service { id: string; name: string; kind: string; status: 'configured'|'needs_key'|'error'; modelCount: number; detail: string }
interface Preset { id: string; name: string; description: string; harness: Harness; modelId: string; providerId: string; channel: string; available: boolean; reason?: string }
interface Session { id: string; title: string; workspaceId: string; harness: Harness; modelName: string; providerName: string; channel: string; state: State; activity?: Activity | null; updatedAt: string; owner: 'web'|'glint'|'external'; capabilities: {send: boolean; stop: boolean; approve: boolean}; summary?: string }
interface Event { id: string; sequence: number; kind: 'user'|'assistant'|'tool'|'approval'|'notice'; text: string; title?: string; status?: 'running'|'done'|'error'; approvalId?: string; decision?: 'allow'|'deny'; createdAt: string }
interface Artifact { id: string; name: string; kind: 'markdown'|'text'|'diff'; content: string; path?: string }
interface SessionDetail { session: Session; events: Event[]; artifacts: Artifact[] }
interface Diagnostic { code: string; message: string }
```

所有字段是普通文本，不渲染任意 HTML。id 必须稳定且不能包含 secret；model id 应区分同名不同 provider。available 表示当前 Web 路径可用，不是 provider 已实测连通；不能从有 Key 推导真实执行通过。Session state 来自进程/protocol，不能来自模型自述。列表可以包含非 Web owner，但不可给其伪造 send/stop 权限。

## Python adapter 接口

主导提供 `mms_web/errors.py` 中 `WebError(code, message, status=400)`，只返回可公开安全文案。不得将异常 repr、进程 env、Key、token 或完整 config 返回浏览器。

Agent A：`mms_web/catalog.py`

```python
class CatalogService:
    def __init__(self, *, config_root: Path | None, state_root: Path): ...
    def snapshot(self) -> dict:
        # models, services, presets, workspaces, diagnostics (均 list)
        ...
    def configuration_preview(self, payload: dict) -> dict:
        # {revision: str, previewId: str, changes: [{label,before,after}], warnings: [str]}
        ...
    def configuration_apply(self, payload: dict) -> dict:
        # {previewId: str, revision: str} -> {applied: bool, message: str}
        ...
    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        # INTERNAL ONLY: selected harness, modelInfo, runtime, cwd. Runtime includes a private _webConfigRoot.
        # exact MMS runtime; never serialize to HTTP.
        ...
    def capabilities(self) -> dict:
        # {catalogRead: bool, configure: bool}
        ...
```

configuration_preview 输入首版：`{revision?: string, service: {id?: string, name: string, baseUrl: string, apiKey?: string, models: string[], protocol?: 'openai'|'anthropic'|'dual'}}`。apply 只能应用服务端保存的同一 preview，不接收任意文件/命令。保留所有未知高级值，revision/CAS 拒绝陈旧配置。config_root=None 必须为空且无配置读写副作用。不得偷偷查找真实 HOME。

Agent B：`mms_web/sessions.py` 与 `mms_web/drivers/`

```python
class SessionService:
    def __init__(self, *, config_root: Path | None, state_root: Path, catalog): ...
    def capabilities(self) -> dict: ...  # {launch: bool}
    def list_sessions(self) -> list[dict]: ...
    def get_session(self, session_id: str) -> dict: ...  # SessionDetail
    def launch(self, payload: dict) -> dict: ...        # SessionDetail
    def send(self, session_id: str, payload: dict) -> dict: ...
    def stop(self, session_id: str, payload: dict) -> dict: ...
    def approve(self, session_id: str, approval_id: str, payload: dict) -> dict: ...
    def close(self) -> None: ...
```

launch `{requestId,workspaceId,presetId,title,prompt}`；send `{requestId,text}`；stop `{requestId}`；approve `{requestId,decision:'allow'|'deny',value?:string}`。mutation 成功返回最新 SessionDetail。requestId 必须幂等，重复请求不可二次启动/执行/审批；相同 requestId 内容不符要拒绝。能力不足返回 409 `CAPABILITY_UNAVAILABLE`，不要静默模拟成功。原终端会话未知 owner 不接管；恢复不能用裸 CLI 丢掉 MMS 选中路由。

主导负责浏览器每 1.2s 取 session snapshot，按稳定 id/sequence 渲染（第一阶段 polling，后续可换 SSE）。adapter 内部仍持续消费 RPC，snapshot 应线程安全，不因轮询丢失增量。首个 rich driver 选择已受 MMS 支持的 Pi RPC；验证原 launcher 实际如何交出 stdin/stdout，不能只 get_export_env 后拼裸 CLI 绕过隔离。若需改 protected surface，先给最小兼容扩展方案，不自行改 shared 默认行为。

## HTTP（主导所有）

- `GET /api/v1/bootstrap`：`{version:'1',mode:'live',capabilities:{catalogRead,configure,launch},models,services,presets,workspaces,diagnostics,sessions,csrfToken}`。
- `GET /api/v1/sessions/:id`：SessionDetail。
- `POST /api/v1/sessions`：launch。
- `POST /api/v1/sessions/:id/messages`、`/stop`、`/approvals/:approvalId`：上述方法。
- `POST /api/v1/configuration/preview`、`/apply`：上述方法。
- 错误 envelope：`{error:{code,message}}`，设置对应 HTTP status。禁止 traceback/secret。

服务只绑 127.0.0.1，严格 Host/Origin，无泛化 CORS；POST 需要 bootstrap 提供的 X-MMS-CSRF，同源 cookie/session 方案可后续升级。API 一旦不可用前端显示错误，不自动退回预览数据。预览显式 `?preview=1`，只运行前端 fixture，不访问模型或 HTTP mutation。

## 集成边界

主导的目录缺 adapter 时返回明确空数据与 capability=false；不复制旧 runtime-api mock。导入报错不能被吞为缺 adapter。state_root 为独立 Web 状态目录；CLI 默认使用 ~/.local/share/mms-web，开发验证显式传任务目录；真实 `~/.config/mms*` 开发写入仍受 human-only gate。测试一律临时 HOME/config，真实账号与收费模型验证由主导安排。


## 已集成扩展

- WebApplication 未提供 config_root 时，使用 state_root/config 完成新用户设置。CatalogService 自身的 config_root=None 仍表示禁用目录，不偷偷发现 HOME。
- POST /workspaces 接收 {path}，返回 Workspace；POST /workspaces/choose 在 macOS 打开本机文件夹选择器，返回 {path}，取消返回空 path。只由用户点击触发。
- 自动模型组合 id 为 web:pi:<providerId>:<modelId>，由当前可用目录派生，不写回 MMS presets。
- Event 增加 arguments、method、options、placeholder、prefill、answer。method 为 confirm/select/input/editor；select 回答必须是服务端收到的原始选项。任何问题都不自动代答。
- send capability 包含可从私有原生 history 恢复的会话。恢复沿用该会话快照中的模型/通道，不自动换路由或使用全局 OAuth。
- requestId 复用不同 payload 返回 409；启动准备中返回 425 REQUEST_PENDING；不确定的 RPC timeout 保留 requestId，重试不得重复执行。
- 内部启动链：只读 source config → 私有 runtime snapshot → MMS runtime resolver → 独立 Python worker → 原 mms_launchers.launch_cli("pi", ..., --mode rpc --session ...) → Pi JSONL。
- 新用户手工配置只有明确选中的单一路由。私有 runtime bundle 标注 manual-configuration/capabilities_verified=false，空能力事实由 MMS 原有保守默认值解析，不修改源目录的已批准 bundle。
- 事件与私有 resume 凭据不使用公开文件权限；HTTP 不序列化 runtime/meta 内部字段。发生启动失败时，详情仅保存到该会话私有运行目录。

## 2026-09-08 交互扩展

- `SessionDetail.runtime` 为 Pi RPC 白名单状态：alive/cached/stale、model display/输入能力、thinkingLevel、autoCompactionEnabled、已确认的 autoRetryEnabled、planning、stats/contextUsage、pendingMessageCount/queue、cwd。服务端短缓存，停止后明确 cached；不序列化密钥或环境变量。
- `POST /attachments {name,data}` 接收 base64；实际文件签名决定图片类型，文本验证 UTF-8，私有保存。`GET /attachments/:id` 返回 text 或 image dataUrl。launch/messages 的 `attachments` 是已上传 ID 数组，`references` 是相对 workspace 路径数组；所有路径在使用时再次检查边界。
- `POST /files/tree|read|git {workspaceId,path?}`：逐层目录、文件预览、Git status/diff。Git 不执行外部 diff/textconv，也不改变仓库状态。
- `GET /sessions/:id/runtime|commands|diagnostics`：原生状态、可见扩展命令、脱敏进程信息。
- `POST /sessions/:id/control {requestId,action,value?}`：thinking、plan、autoCompaction、autoRetry、compact、clearQueue；除清空队列外执行中拒绝调整。参数由 Pi 验证。plan 预检 Web extension 存在，命令缺失时 fail closed，不把内部命令发送给模型。
- `POST /sessions/:id/manage {title?,archived?}`：幂等赋值；执行中不可归档。`POST /sessions/:id/fork {requestId,eventId?}`：从完整历史或指定 assistant 原生 entry 复制独立私有运行目录，原会话不变，cwd 共用。
- launch 可指定 `planMode: boolean`；默认 false，普通 MMS CLI 完全不注入此 Web extension。
- Event 增加 thinking、usage、nativeTimestamp、attachments、references。Thinking 在 text_delta/thinking_delta 和 message_end 中同步；旧会话按匹配的原生 assistant 历史补齐。
- 图片能力拒绝在记录新消息前完成。CSRF 明确拒绝后前端只刷新 token 并重试一次，不对未知网络失败盲目重发。上传内容不打印到日志。
- 工作配方是前端导出/导入的 `mms-work-recipe-v1` 文件，只白名单读取 title/prompt/preferredModel/planning，不自动提交、启动或写入配置。

## Prelaunch selection (2026-09-08)

- `POST /launch-options {presetId, workspaceId}`: read-only resolution through the original MMS provider/preferences/model-policy path using a disposable private configuration snapshot. Public fields: `model` (id/name/input/contextWindow/maxTokens/reasoning), `protocol`, `configuredThinkingLevel`, `defaultThinkingLevel`, `supportedThinkingLevels`, `thinkingLevelMap`. No credentials or endpoint URLs.
- `POST /skills {workspaceId}`: Pi-native metadata parser over the same effective MMS global/project overlay. Returns `skills[{id,name,description,filePath,baseDir,source,manualOnly}]`, diagnostics. No provider call.
- Session launch optionally takes `thinkingLevel`, `skills:[id]`. Omitted effort inherits MMS; supplied effort is validated against the actual launched Pi model and confirmed through RPC before publishing a prompt. Resume restores the last confirmed level.
- Session messages optionally take `skills:[id]`. Server re-resolves IDs against the workspace catalog; selected skill content and base-directory context join the native prompt; Web user events keep the short text and selected skill labels. Unknown IDs, invalid effort or excessive skills fail before sending.
- Favorites, notes and per-route Web effort/channel defaults are browser preferences; they never mutate MMS source preferences or provider priority.

## 当前运行状态

`GET /sessions` 返回 `{sessions: Session[]}`，只读取会话快照，不重建模型 catalog，也不请求 provider。前台每秒更新，后台页每四秒；当前会话事件仍由原 detail API 更新。

生命周期 `state` 保持不变。`activity` 来自 Pi RPC 的真实事件：agent_start 为 running；thinking/text 的 start 或 delta 分别为 thinking/responding；工具执行为 tool；压缩与重试独立展示。未返回思考事件时不会把运行阶段标成 thinking。`eventId` 只指向本次消息/工具，历史 Thinking 不跟随新轮动画。

等待原生交互时 waiting 优先于工具/模型阶段，并依据 confirm 或 input/select/editor 区分确认和回答。`agent_end` 不代表空闲，`agent_settled` 才清除忙碌状态；失败/中止的模型轮次保留 error/stopped activity，同时 idle 生命周期允许继续发送。压缩也可以由用户在空闲时触发。

activity 是瞬时数据，进程退出/重启后不会恢复为忙碌；未正常结束的工具记录标为未收到完成回报。断连显示“状态未同步”，暂停动画，保留上次内容；减少动态效果的系统偏好使用静态标记。


## 独立配置连接向导

`POST /configuration/discover` 接收 `service: {baseUrl, apiKey, protocol}`。仅在用户明确读取时对指定 API 基址追加 `/models`，使用单次 GET；不猜 `/v1`、不跟随跳转、不读代理环境、不生成内容、不写配置或缓存。仅支持 OpenAI/dual 的列表；Anthropic 使用手填。返回 `models: string[]`、`requestUrl`、`latencyMs`、`generationVerified: false`。认证、限流、空列表及超时提供明确错误；读取列表不等于模型能力验证。

`configuration/preview` 保留原 revision/previewId 合同。Key 仅保存于权限受限的临时 preview，HTTP 返回脱敏字段。手动配置继续兼容原有 query URL 并在输出中脱敏；discovery 不接受 query URL。模型 ID 去重并限制数量/长度，不接受控制字符。

`configuration/apply` 在原结果上追加 `providerId` 和当前可启动的 `presetIds`。配置已写入但目录暂不可读时仍返回 `applied: true, presetIds: []`，避免把目录失败伪装成保存失败；UI 提示完成 MMF 目录更新。

`POST /configuration/discard` 接收 `{previewId}`，在 apply 同一把锁内移除未应用的预览及其 Key；重复取消幂等。已应用的脱敏 audit 不删除。取消、返回编辑使用这个入口；写入中禁止再次保存或关闭。所有配置 mutation 继续检查真实配置根保护、Origin 与 CSRF。

保存后的 effort 使用 `/launch-options` 读取模型适配器真实支持值。MMS 默认、当前浏览器的单通道偏好、当前任务覆盖分别保持原语义；不在拉取列表时猜测能力或覆盖全局默认。

真实 `~/.config/mms*` 的 `configure` 仍为 false；开发验证只在 task-private configuration 中进行。这些 API 不是绕过旧 Config Web 的 Registry 发布入口。

## Existing MMF channel settings

`capabilities.modelSettings` indicates a verified preview Registry can be edited through the existing Config Web publisher. It is separate from `configure`, which controls new connections in Web-owned configuration roots.

- `GET /api/v1/model-settings`: current approved providers/model rows, actual Pi-compatible policy effort levels, bundle revision, source fingerprint, config root. No credentials are returned.
- `POST /api/v1/model-settings/discover`: providerId + revision + fingerprint. Calls the selected provider's existing model probe against a private snapshot. Manual providers stay manual; failed/fallback discovery is not reported as a successful remote fetch.
- `POST /api/v1/model-settings/preview`: providerId, selected model IDs, changed effort values, revision and fingerprint. Returns a 15-minute preview token and human-readable changes. Does not write the source configuration.
- `POST /api/v1/model-settings/apply`: previewId + confirmPhrase (`写入预览DB`). The exact server-held draft is applied; caller replacement fields are ignored. Successful replay returns the recorded result. Uncertain writes require a fresh read, not blind replay.

CSRF and loopback origin checks apply to these endpoints. Source edits remain human-only. The adapter reuses Config Web's audited v2 writer and route scope preservation. Stable real MMS roots are excluded. Browser route preferences continue to live in localStorage; they are not model-policy writes.

### Existing channel connection settings

`model-settings` provider rows include `connection` (`openaiBaseUrl`, `anthropicBaseUrl`, `hasApiKey`, `protocols`). Saved secrets are never returned. Preview accepts an optional `connection` patch with changed URL fields and an optional new `apiKey`. Empty API Key means the UI omits the patch and retains the saved key; an explicitly empty key is rejected. URL fields must be HTTP(S) without embedded credentials, query or fragment.

`POST /api/v1/model-settings/check` uses the same revision/fingerprint and optional connection draft to check the provider's existing model-list endpoint. It does not publish, run generation or convert manual providers to probe mode. Result: `connected`, `modelCount`, `latencyMs`, `message`; success only proves the model-list endpoint.

`efforts: {"model-id": ""}` explicitly removes that model's policy effort override. Capability facts and other policy fields are preserved. Legacy real-root overrides remain read-only in this editor.

A secret-bearing preview stores the key only in process memory for the pending preview; apply is allowed only within the preview lifetime; Web draft files and responses exclude it. A server restart invalidates that preview. Only explicit human apply passes it to the native audited MMF writer. No actual user configuration was applied by the development agent during validation.


## v4 会话切换与执行轮次

`POST /api/v1/sessions/{id}/model` 接受 `{requestId, presetId}`。拒绝 running/waiting 会话；native Pi set_model 或通过原 MMS launch 创建候选 runtime。成功后返回原 Web session ID 的详情，包含真实 runtime model/thinking；同通道保留原PID，跨通道保留 native history并换私有进程。目标失败/最终保存失败回退原选择，不调用全局 auth。

Session 增加 `presetId`，assistant event 增加 `modelName`。已有回答保持生成时模型标签。用户事件 `status: queued` 表示还未被Pi消费，不作为新执行轮次；收到真实 user message_start后把该事件移至当前执行位置，清空队列/停止/恢复失效队列时标记 `cancelled`。event ID保持稳定；sequence在实际消费时重新排序。

过程折叠是客户端偏好，不删除后端事件。`mms-web-auto-collapse-process` 保存在 localStorage。工具错误、审批/通知在折叠时仍可见；展开后保持事件顺序。GET 返回的是快照，不能把旧快照event数组当作永不变的append-only日志。

`GET /bootstrap` 的 `version: "1"` 是 API 版本；`appVersion` 来自当前运行服务的 `mms_version.VERSION`，用于 Logo 和设置页显示产品版本。缺失时不猜测产品版本。
