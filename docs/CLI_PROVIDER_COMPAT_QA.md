# CLI / Provider Compatibility Notes

> 更新时间：2026-05-29
> 范围：`claude` / `codex` / `qwen` / `kimi` 与公开仓库内可见的通用兼容性规则。

> 2026-04-16 stopgap：`MMS` 当前保留 `Claude CLI` 启动能力，但默认隐藏 `Claude family model` 的展示与候选选择；这是 surface 收口，不是 runtime 下线。
> 公开版口径：保留 `claude` tab 和 `mms claude`；当 route 支持时，同时展示原生 `claude-*` 与可经 `Claude CLI` bridge 的非 `claude-*` 模型；公开文档不包含 `Claude OAuth account.add/login`。

## 为什么这份文档被改成精简版

这个仓库历史上沉淀过一些仅适用于私有部署的排障记录，里面可能包含：

- 私有 provider ID
- relay / sticky-session 架构细节
- 内网或云主机地址
- 运维路径、容器名、日志追溯命令

这些内容不适合保留在公开仓库里。

因此，公开仓库只保留通用兼容性原则；部署相关的细节请保存在你自己的本地 runbook / wiki / private docs 中。

## 公开仓库内仍然有效的兼容性原则

### 1. Provider 兼容性要区分协议，不要只看名字

至少先确认 provider 实际支持哪类协议：

- `anthropic_messages`
- `openai_chat_completions`
- `responses`
- 是否需要 manual model list

厂商差异优先沉淀到 `config/provider-profiles.json`，并在 `docs/PROVIDER_PROFILES.md` 记录双格式端点、auth header、thinking/effort 字段和官方 reference；不要为单个厂商在 launcher/bridge/router 里继续堆新分支。

不要因为某个 provider “看起来像 Claude / OpenAI” 就假设它一定支持对应 CLI 的所有路径。

### 2. 模型可见性和真实可用性必须分开验证

最少要分别检查：

- 模型是否能被列出来
- 模型是否真的能被请求成功
- fallback / extra / hidden model 是否影响最终展示

Qwen / Kimi 现在是 provider model family，不再是独立 CLI launcher。删除直连
`qwen` / `kimi` CLI 不应导致 family 消失；旧配置里的 `supported_clis =
["qwen", "kimi"]` 会按 provider 协议归一到真实 CLI（通常是 `claude` /
`codex`）。如果同一个 channel/key 在新机器只显示部分 family，优先检查：

- provider 配置是否包含同样的 `fallback_models` / `extra_models`
- `credentials.sh` 是否指向同一个 provider id、base URL 和 key
- 本机是否是 cold probe cache；MMS 会先用静态模型列表显示，同时后台刷新 `/models`
- 是否被 `hidden_models` 或项目级 model policy 隐藏

### 3. Bridge / probe / fallback 是高风险区

凡是涉及下面这些点的改动，都应该视为高风险：

- `models_endpoint`
- probe cache
- fallback model logic
- header passthrough
- sticky-session key source
- `Responses` vs `Chat Completions` fallback
- same-vendor native/direct fallback

2026-05-29 implementation note: Claude Anthropic endpoint resolution may live
outside `mms_launchers.py`, but the public compatibility contract is unchanged:
`mms_launchers._resolve_anthropic_base_url` remains the compatibility wrapper,
keeps the same cache key / `/v1/messages` probe / OpenAI fallback outcomes, and
must stay monkeypatch-compatible for launcher regression tests.

2026-05-29 implementation note: Claude model-slot and context helpers may live
outside `mms_launchers.py`, but `mms_launchers._apply_claude_model_overrides`,
`_effective_context_window`, and `_runtime_supports_claude_1m` remain the
compatibility wrappers. Claude `[1m]` suffix rules, MiMo selector stripping, and
sensitive-provider 1M defaults must not change during module extraction.

2026-05-29 implementation note: Claude session settings materialization may live
outside `mms_launchers.py`, but `mms_launchers._build_claude_session_settings`,
`_write_claude_session_settings`, and `_seed_oauth_claude_session_settings`
remain the compatibility wrappers. Template loading, settings merge helpers,
settings inheritance, hook/MCP allowlists, session-local writes, and OAuth
execution-surface stripping must stay monkeypatch-compatible and
behavior-preserving during module extraction.

另外，对带 `thinking` 的非 Claude upstream 不要只验证“首轮能回字”：

- 像 `DeepSeek` 这类 `tool_use + thinking` 路径，后续 continuation 可能要求把上一轮 assistant reasoning 原样 round-trip 回去
- 如果你在 `Anthropic Messages` bridge 里消费、裁剪、重排了 `thinking` block，要额外验证后续 `tool_result` 轮不会因为缺少 `reasoning_content` 等等价字段而报 `400`

### 4. OAuth 隔离语义优先于“方便复用”

对于官方账号入口，默认目标应是：

- 跨账号完全隔离
- 同账号可 resume
- 不从真实 global 目录偷偷 seed 私有状态
- 不因 launcher 混用状态目录而串号
- `.claude.json` 在 copy-in / sync-back 时都应剥离 `projects`、`lastSessionId`、`lastCost` 这类 restore-state 噪声，避免“第一窗口正常、第二窗口继承旧恢复状态”
- OAuth `.claude.json` 不应继续走 blacklist strip；应改成 allowlist，只保留 account-scoped OAuth 持久态（如 `userID` / `oauthAccount` / `claudeAiOauth` 的明确字段）
- OAuth 启动前要清理父进程残留的 `ANTHROPIC_*` / `CLAUDE_CODE_*` 覆盖环境，避免 gateway/api_key session 把认证和模型槽位带进官方账号路径
- 非 Claude CLI 与 gateway/bridge 路径也要清理 inherited `OPENAI_* / proxy / fake-upstream / CA env`，避免上一条 session 或全局 shell 环境把 data plane 静默带偏

### 5. Proxy / timezone / IPv4-first 现在是 runtime profile 的一部分

对于 MMS 启动出来的 runtime，应该明确区分：

- `proxy`
- `NO_PROXY`
- `timezone`
- `force_ipv4`

不要把这些网络/环境参数混进展示层状态，也不要让它们只在最终子进程生效、但前置 probe 漂移到别的网络路径。

另外，`accept-only` 只解决 config/state 继承问题，不等于 data plane 已经隔离。对于本地 bridge / gateway 上游请求，默认还应满足：

- bridge 上游 `httpx` 请求默认 `trust_env=False`
- 只有 MMS 显式传入的 `runtime.proxy / runtime.no_proxy` 可以影响 bridge 实际出口
- 不能让 ambient/global proxy（例如系统 proxy、其他工具注入的 `HTTP_PROXY`、本机 `cc-switch`）静默覆盖掉用户在 MMS 里选中的 channel / provider
- 官方 Anthropic control-plane 请求（例如 usage / warmup / direct probe）也应优先忽略 ambient proxy；需要代理时只认账号或 runtime 显式配置

### 6. Claude hardening 默认要走 allowlist + fail-closed

当前公开仓库的基线应至少满足：

- `settings.json` 只继承 `hooks` / `statusLine` / `permissions`；不要从真实 global state 宽拷贝 `env`、主题或未知字段
- gateway `.claude.json` 只按 schema-based allowlist 写当前 session 需要的字段；未知 global 字段默认丢弃
- `gateway/provider/api_key` 新 session 若要支持 shared resume，只能回填当前 `project + runtime/account + launch model` 的安全 resume pointer（如 `projects[project].lastSessionId`）；不同窗口切换 `claude/gpt/qwen/kimi` 时不能复用上一个模型的 `sessionId`
- Claude session `~/.claude/` 不再大面积继承真实目录；默认只保留 project-scoped 持久项，再额外 allowlist 静态 tooling surface（如 `skills` / `.mcp.json` / `CLAUDE.md` / `RTK.md` / `commands` / `hooks`）
- Claude session `~/Library/` 只暴露 `Keychains` 这类最小必要依赖；不要把整个 `Library` symlink 进去
- Claude session 只暴露真实 `~/.local/bin`，不要把整棵 `~/.local` symlink 进去
- Claude bypass 应区分路径：
  - 官方 `Claude` account 的 bypass 继续要求 proxy 并 fail-closed
  - 显式 sensitive Claude provider 的 bypass 也要求 proxy 并 fail-closed
  - 普通 `api_key/gateway provider` 仍应走 network guard，但不应因为“没配 proxy”被一刀切误拦
- 隔离 session 里会修改 global state 或触发 GUI/Keychain 的命令（如 `open`、`security`、`git/ssh/gh`、`pm2`、`npm/pnpm/yarn/corepack`）应通过 wrapper 强制回到 real `HOME/XDG/PM2_HOME`；找不到 real binary 时宁可 fail-closed，也不要掉回隔离态安装/更新
- 需要打开用户 Chrome 时使用 session 内置 `mms-chrome-host` / `BROWSER` wrapper；不要在隔离 HOME 下直接启动 Chrome binary
- statusline / background helper 默认不得读取 macOS Keychain；如确需 Claude OAuth usage，必须由用户显式设置 `MMS_STATUSLINE_KEYCHAIN_USAGE=1` 或运行 `mms usage --keychain` / 设置 `MMS_ALLOW_KEYCHAIN_READ=1`
- stale OAuth session cleanup 不应把旧 session state 再回写到账户目录
- gateway / proxy 健康检查应按 provider scope 独立记录，并且只把真实成功的 `2xx` 当作可用；`401/403/404/5xx` 不应被当成“线路健康”
- 本地 bridge 不应先探测空闲端口再二次 bind；应直接 `bind(127.0.0.1, 0)` 取内核分配端口，并在 yield 前完成 ready wait，避免首请求 `connection refused`
- `Responses -> Chat Completions fallback` 只在明确“不支持 Responses API”时才写 cache；`empty body / empty stream / content-length=0` 这类模糊失败不能持久化成 fallback 结论
- Anthropic-facing probe / classify / bridge fallback 遇到 `429` 时应优先 respect `Retry-After` 并对同一目标做最小 backoff，不要立刻横扫其它 candidate URL
- same-vendor native/direct fallback 只能作为显式诊断 fallback：同厂商、同 profile、API-key runtime、有明确 native/direct provider 与模型元数据；不得写 config、不得同步 probe、不得切到 global OAuth、不得在 client response 已经开始后切 route
- probe metadata 不应带固定可识别前缀，也不应带 runtime/account identity；如果必须带 session identity，默认使用中性/随机值
- `load_config()` 这类 read path 不应在仅做 normalize/migrate 时自动落盘真实 config；显式写配置必须保持为单独动作
- stale probe cache 可以用于“提示后台刷新”，但不能静默主导 provider 选择；缓存里的 `error / error_kind` 也不应被洗白

## 最小验证清单

如果你改了 provider / launcher / bridge / account isolation，至少做下面这些验证：

1. `python3 -m py_compile` 覆盖改动文件
2. 相关回归测试通过
3. 模型列表和真实启动链路一致
4. OAuth 账号隔离不串号
5. 配置了 proxy 时，坏 proxy 会被拦截
6. 启动环境里的 timezone / IPv4-first 符合预期
7. Claude settings / `.claude.json` / `.claude` / `Library` 的继承面符合 allowlist 预期
8. stale cache / fallback cache 不会把错误结论跨 provider、跨 URL、跨 session 固化下来
9. 隔离 session 内执行 `open/security/git/ssh/gh/pm2/npm/pnpm/npx/yarn/corepack/node` 时，会明确落到 real `HOME`，不会把 global 安装/更新写进 session HOME；`claude/codex/opencode` 本体不能被 wrapper 截走
10. Anthropic `429` 时不会继续 fanout 到其它 candidate URL，OAuth 路径也不会继承父进程里的 `ANTHROPIC_*` 认证环境
11. gateway/proxy 健康检查不会把 `401/403/404` 误判成“线路可用”，多 provider 之间也不会共享同一条 health 记录
12. local bridge 在 yield 前已经 listen，首请求不会因为端口竞争或未 ready 而偶发 `connection refused`
13. same-vendor native/direct fallback 只在首个 client response 前发生，并且能在日志/route status 里看到 fallback source、target、request path 与 reason

## 本地私有文档建议

如果你有部署相关内容，建议放到不进 git 的本地文件，例如：

- `docs/CLI_PROVIDER_COMPAT_QA.local.md`
- `docs/private-relay-smoketest.local.md`
- 你自己的 wiki / ops runbook

## 一句话

公开仓库保留通用兼容性原则；任何带真实部署标识、主机、容器、账号池、粘滞策略的内容，都应该留在本地私有文档中。
