# private / privateopenai / newapi / CRS Smoke Test Runbook

> 更新时间：2026-03-29
> 目标：为 `MMS -> private(/claude) -> CRS`、`MMS -> privateopenai(/openai) -> CRS`、`MMS -> xin/newapi(4001) -> CRS` 提供一套可追溯、可复现的最小验证步骤

## 适用场景

当下面任一项发生变更时，优先跑本文档：

- provider `models_endpoint`
- `extra_models` / `hidden_models`
- model probe / cache / fallback
- `Codex` / `Claude` header 透传
- `channel_affinity`
- `/claude`、`/openai`、`/responses`、`/models` 相关兼容逻辑

## 现网基线

截至 2026-03-25，本轮确认的现网事实：

- `private(/claude)`：
  - `GET /claude/v1/models` 返回 `200`
  - `POST /claude/v1/messages?beta=true` 返回 `200`
  - 上游模型列表主要是 dated model id
- `privateopenai(/openai)`：
  - `GET /openai/v1/models` 返回 `404`
  - 在 MMS 里建议使用 `models_endpoint = "manual"`
  - 手工补充模型示例：`gpt-5.4`
- `xin/newapi(4001)`：
  - 背后是 `new-api-custom`
  - 默认 `channel_affinity` 规则已启用
  - `Claude` 规则默认从 `gjson:metadata.user_id` 取 sticky key

## 服务器信息

当前已验证的示例环境：

- 机器：`root@82.156.121.141`
- `CRS`：`http://82.156.121.141:3000`
- `newapi-custom`：`http://82.156.121.141:4001`

容器：

- `claude-relay-service-claude-relay-1`
- `new-api-custom`
- `postgres`

## 预备命令

```bash
ssh root@82.156.121.141
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

## 0. 本地最小闭环 Smoke 入口

如果你只是想快速确认“这个 channel 的 `URL + key + bridge` 现在还能不能给对应 CLI 用”，优先跑本地脚本，不必先手工 curl：

```bash
HOME=/Users/xin mms test --provider private --cli claude
HOME=/Users/xin mms test --provider privateopenai --cli codex
HOME=/Users/xin mms test --provider xin --cli codex
```

注意：

- 如果你是在 `MMS` 隔离 session 里二次启动工具，表面看到的 `HOME` 可能是 `~/.config/mms/.../s/<pid>`
- 当前 launcher 已补真实 home 回源提示：
  - `MMS_REAL_HOME`
  - `ORIGINAL_HOME`
  - `REAL_HOME`
  - `GH_CONFIG_DIR`
  - gateway 路径下的真实 `XDG_CONFIG_HOME`
- 但做 smoke 时，仍建议显式用 `HOME=/Users/xin` 运行，避免把问题混到隔离 session 语义里

一次扫当前启用 provider 的 `claude + codex`：

```bash
HOME=/Users/xin mms test
```

JSON 输出，适合合版校验或定时巡检：

```bash
HOME=/Users/xin mms test --json
```

这套脚本的验证边界是：

- `claude`
  - 直连 `Anthropic Messages`
  - 或走本地 `gateway_claude_bridge`
- `codex`
  - GPT 模型走 `codex_responses_bridge`
  - 非 GPT 模型走 `codex_chatcompletions_bridge`

所以它验证的不是“模型全量兼容性”，而是：

- 这个 provider 的 `URL + key` 是否还活着
- MMS 当前 `launcher -> bridge` 主链路是否还活着
- 本地 `models` advertisement 是否还在

额外注意：

- 对 `fishcrs` / `trcrs` 这类 direct CRS key，smoke 后必须去 `CRS` 日志核对：
  - `Using proxy for Claude request: <expected_proxy>`
- 如果看不到这行日志，不算验证通过
- 对 `xin` / `fishcrs` 这类敏感 provider，默认不要用 `1M context` 做第一条验证

## 一、验证 `private(/claude)` 正常

### 1. 验证模型列表

```bash
curl -sS -D - \
  http://82.156.121.141:3000/claude/v1/models \
  -H 'Authorization: Bearer <CRS_KEY>'
```

预期：

- `HTTP/1.1 200 OK`
- body 里能看到 dated model id，例如：
  - `claude-sonnet-4-20250514`
  - `claude-opus-4-5-20251101`

### 2. 验证最小消息可聊

```bash
curl -sS \
  -X POST 'http://82.156.121.141:3000/claude/v1/messages?beta=true' \
  -H 'Authorization: Bearer <CRS_KEY>' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: claude-cli/2.1.81 (external, sdk-cli)' \
  -H 'x-app: cli' \
  -H 'anthropic-version: 2023-06-01' \
  -H 'anthropic-beta: fine-grained-tool-streaming-2025-05-14' \
  --data-binary @- <<'EOF'
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 32,
  "stream": false,
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "hi"}]}
  ],
  "metadata": {
    "user_id": "{\"device_id\":\"smoke-dev\",\"account_uuid\":\"smoke-acct\",\"session_id\":\"smoke-private-001\"}"
  }
}
EOF
```

预期：

- 返回 `200`
- `usage.input_tokens` 很小
- `metadata.user_id` 必须是 string，不是 object

## 二、验证 `privateopenai(/openai)` 的 manual model-list 模式

### 1. 验证上游本来就没有 `/models`

```bash
curl -sS -D - \
  http://82.156.121.141:3000/openai/v1/models \
  -H 'Authorization: Bearer <CRS_KEY>'
```

预期：

- `HTTP/1.1 404 Not Found`

### 2. 验证 MMS 配置已切到 manual

```bash
HOME=/Users/xin python3 - <<'PY'
from mms_core import load_config
cfg = load_config()
for p in cfg.get('providers', []):
    if p.get('id') == 'privateopenai':
        print(p.get('models_endpoint'))
        print(p.get('extra_models'))
        break
PY
```

预期：

- `models_endpoint = manual`
- `extra_models` 至少包含你手工添加的模型，例如 `gpt-5.4`

### 3. 验证 probe 不再空等 `/models`

```bash
HOME=/Users/xin python3 - <<'PY'
from mms_core import load_config, resolve_provider_context, _probe_models
cfg = load_config()
provider = resolve_provider_context(cfg, 'privateopenai')
res = _probe_models(provider, emit_output=False, force_refresh=True)
print('base_source =', res.get('base_source'))
print('models =', res.get('models'))
print('error =', res.get('error'))
print('model_sources =', res.get('model_sources'))
PY
```

预期：

- `base_source = manual`
- `models = ['gpt-5.4', ...]`
- `error = None`

## 三、验证 `xin/newapi(4001)` 的 sticky 与识别头

### 1. 验证 `Claude` sticky

```bash
for i in 1 2 3; do
  curl -sS \
    -X POST 'http://82.156.121.141:4001/v1/messages?beta=true' \
    -H 'Authorization: Bearer <NEWAPI_TOKEN>' \
    -H 'Content-Type: application/json' \
    -H 'User-Agent: claude-cli/2.1.81 (external, sdk-cli)' \
    -H 'x-app: cli' \
    -H 'anthropic-version: 2023-06-01' \
    -H 'anthropic-beta: fine-grained-tool-streaming-2025-05-14' \
    --data-binary @- <<'EOF'
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 64,
  "stream": false,
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "hi"}]}
  ],
  "metadata": {
    "user_id": "{\"device_id\":\"dev-codex-test\",\"account_uuid\":\"acct-coding-1\",\"session_id\":\"sess-sticky-claude-001\"}"
  }
}
EOF
done
```

然后查 CRS 日志：

```bash
docker exec claude-relay-service-claude-relay-1 sh -lc \
  "grep -n 'sess-sticky-claude-001' /app/logs/claude-relay-$(date +%F).log* | tail -40"
```

预期：

- 首次出现 `Created new sticky session mapping`
- 后续出现 `Using sticky session account from group`
- 三次都落到同一账号

### 2. 验证 `Codex` / `Claude` 识别头未丢

```bash
docker exec claude-relay-service-claude-relay-1 sh -lc \
  "grep -n 'codex_cli_rs\\|claude-cli/2.1.81\\|x-app\\|anthropic-version' /app/logs/claude-relay-$(date +%F).log* | tail -60"
```

预期：

- `Codex` 请求能看到 `ua = codex_cli_rs/...`
- `Claude` 请求能看到 `ua = claude-cli/...`
- 不应退化成 `python-httpx/...` 或 `Go-http-client/1.1`

## 四、快速定位日志

### CRS

```bash
docker exec claude-relay-service-claude-relay-1 sh -lc \
  "ls -1 /app/logs | tail -20"
```

常用 grep：

```bash
docker exec claude-relay-service-claude-relay-1 sh -lc \
  "grep -n 'privateopenai\\|private(/claude)\\|/openai/v1/models\\|/claude/v1/messages\\|sess-sticky' /app/logs/claude-relay-$(date +%F).log* | tail -80"
```

### newapi

```bash
docker exec postgres psql -U root -d 'new-api' -At -F '|' -c \
  \"select id,name,base_url,models,setting from channels order by id;\"
```

## 五、遇到异常时先判断什么

1. `/claude/v1/models` 正常、`/openai/v1/models` 404：优先考虑接口本来不对称，不要误判成 MMS 坏了。
2. `metadata.user_id` 不是 string：先修 payload，再看 sticky，不要先怀疑 `channel_affinity`。
3. `privateopenai` 已设 `manual` 但还是空等：先确认是不是用真实 `HOME=/Users/xin` 跑的配置，而不是隔离 session home。
4. CRS 日志里 `ua` 退化成 `python-httpx` 或 `Go-http-client`：优先回查 header passthrough。
5. provider 列表里不见 `claude-sonnet-4-6` / `claude-opus-4-6`：先查 `private(/claude)` 的 dated model id，再查 MMS alias patch。

## 六、与哪些文档联动

- `docs/CLI_PROVIDER_COMPAT_QA.md`
- `docs/NEWAPI_CRS_STICKY_SESSION_GUIDE.md`
- `docs/AGENT_GUARDRAILS.md`
