# Runtime Gateway MVP

这个目录现在支持一个最小可用的 OpenAI-compatible gateway，用来把内部成员的请求先打到 `apps/runtime-api`，再由它转发到上游 provider。

## 本轮能力

- `GET /gateway/health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- Bearer token 鉴权
- OpenRouter 上游 key 池轮换与 failover
- SQLite 请求日志与按 token 的日额度限制

## 配置方式

1. 复制 `gateway-config.example.json` 为 `gateway-config.json`
2. 用环境变量填真实上游 key，例如 `OPENROUTER_API_KEY_A`
3. 运行：

```bash
python3 scripts/gateway_token.py --id internal-test-a --name "内部测试 A"
```

4. 把输出里的 `tokenHash` 填回 `gateway-config.json`
5. 启动服务：

```bash
uvicorn main:app --reload --port 8000
```

## 前端接法

第一版不需要内置新 provider。直接在 `web-v2` 设置页手动新增一个 `openai-compatible provider`：

- `Base URL`：`http://<gateway-host>:8000/v1`
- `API Key`：上一步生成的原始 token

这样现有 `fetchModels` 和 `chat/completions` 调用就会直接走 gateway。
