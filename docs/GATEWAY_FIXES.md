# Gateway 修复记录（2026-03-14）

> 合并 worktree 时：涉及 `ccs_core.py` / `ccs_launchers.py` 的改动需对照本文件，避免把已修复的代码覆盖回旧版本。

---

## 问题 1：`/v1/v1/models` 404（模型拉取双重 v1）

### 根因
`_provider_openai_base_url()` 返回已带 `/v1` 的 URL，但 `_probe_models` 继续拼 `/v1/models`，
导致请求打到 `https://xxx/v1/v1/models` → 404。

### 修复位置
- `ccs_core.py` → `_probe_models()` 函数

### 修复方式
```python
# 旧代码（有 bug）：
response = httpx.get(f"{base_url}/v1/models", ...)

# 新代码：try base_url + alt_url 两个候选，自动兼容有/无 /v1 后缀
alt_url = base_url[:-3] if base_url.endswith("/v1") else f"{base_url}/v1"
for try_url in [base_url, alt_url]:
    response = httpx.get(f"{try_url}/models", ...)   # 注意：直接拼 /models，不再加 /v1
    ...
    result["working_url"] = try_url   # 记录实际通的 URL
    break
```

### 影响文件
- `ccs_core.py`（主分支 + 所有 worktree 合并时都需要应用）
- `ccs_launchers.py` → `_gateway_ping()` 同样用了 `url_with_v1`，已正确（先检查再加 `/v1`）

---

## 问题 2：安装路径与 dev 路径不同步

### 根因
`mms` 脚本通过 `sys.path.insert(0, 脚本所在目录)` 决定加载哪个 `ccs_core.py`。
运行路径不同，加载的文件不同：

| 命令 | 加载路径 |
|------|---------|
| `~/ccs/multi-model-switch/mms` | `~/ccs/multi-model-switch/ccs_core.py` |
| `~/auto-skills/.../mms` | `~/auto-skills/.../ccs_core.py` |

每次修复 `ccs_core.py` 必须同时修复两处，或确认用的是哪个路径。

---

## 问题 3：Codex gateway 模式 401（OAuth token 覆盖 API key）

### 根因
`~/.codex/auth.json` 里 `auth_mode: "chatgpt"`，Codex 读取此文件后忽略 `OPENAI_API_KEY` 环境变量，
直接用 OpenAI OAuth token 打网关 → gateway 不认 OAuth token → 401。

### 修复位置
- `ccs_launchers.py` → 新增 `_codex_gateway_env()` 函数，替换原来的 `launch_codex` api_key 分支

### 修复方式
```python
def _codex_gateway_env(runtime, base_url):
    """独立 HOME，防止 ~/.codex/auth.json chatgpt mode 覆盖 key"""
    openai_key = runtime.get("openai_api_key") or runtime["api_key"]
    gateway_home = os.path.expanduser("~/.config/mms/codex-gateway")
    codex_dir = os.path.join(gateway_home, ".codex")
    os.makedirs(codex_dir, exist_ok=True)

    # 每次启动都写入，保持 key 同步
    with open(os.path.join(codex_dir, "auth.json"), "w") as f:
        json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": openai_key}, f)

    # 首次运行时从真实 ~/.codex/config.toml 复制设置
    real_config = os.path.expanduser("~/.codex/config.toml")
    gateway_config = os.path.join(codex_dir, "config.toml")
    if os.path.exists(real_config) and not os.path.exists(gateway_config):
        shutil.copy2(real_config, gateway_config)

    env = os.environ.copy()
    env["HOME"] = gateway_home      # Codex 读 ~/.codex/ 相对于此 HOME
    env["OPENAI_API_KEY"] = openai_key
    env["OPENAI_BASE_URL"] = base_url
    return env
```

**注意**：`auth_mode` 的合法值是 `"apikey"`（不是 `"api_key"`）。

---

## 问题 4：Codex 与 Claude 用不同 Gateway Key

### 根因
某些网关对 Claude（Anthropic format）和 GPT（OpenAI format）使用不同的渠道 token。

### 修复位置
- `ccs_core.py` → `load_provider_credentials()` 新增 `openai_api_key` 字段
- `ccs_core.py` → `resolve_provider_context()` 传递 `openai_api_key`
- `~/.config/mms/credentials.sh` → 新增 `CCS_PROVIDER_<ID>_OPENAI_API_KEY`

### credentials.sh 格式
```bash
# Anthropic/Claude 渠道 key
export CCS_PROVIDER_NEWAPI_API_KEY='sk-xxx'
# OpenAI/GPT 渠道 key（可选，不配置则 fallback 到 API_KEY）
export CCS_PROVIDER_NEWAPI_OPENAI_API_KEY='sk-yyy'
```

### ccs_core.py 变更摘要
```python
# load_provider_credentials 新增：
openai_api_key_name = _provider_env_name(provider_id, "OPENAI_API_KEY")
openai_api_key = ...  # 从 env / credentials.sh 读取
return { ..., "openai_api_key": openai_api_key }

# resolve_provider_context 新增：
provider["openai_api_key"] = credentials.get("openai_api_key", "")
```

---

## 问题 5：Claude gateway 模式 `claude-sonnet-4-6[1m]` 找不到

### 根因
`~/.claude.json` 里有 `sonnet1m45MigrationComplete: true`，Claude Code 启动时自动把
`claude-sonnet-4-6` 升级为 `claude-sonnet-4-6[1m]`（1M context 变体）。
gateway 只有 `claude-sonnet-4-6`，没有 `[1m]` 变体 → 模型 not found。

OAuth 模式不受影响（Anthropic 官方后端有 `[1m]`）。

### 修复位置
- `ccs_launchers.py` → 新增 `_claude_gateway_env()` 函数，替换 `launch_claude` api_key 分支

### 修复方式
```python
def _claude_gateway_env(runtime):
    """独立 HOME，剥离 migration 标记，防止 [1m] 自动升级"""
    gateway_home = os.path.expanduser("~/.config/mms/claude-gateway")
    os.makedirs(gateway_home, exist_ok=True)

    # 每次写入，移除 migration flags
    real_json = os.path.expanduser("~/.claude.json")
    data = json.load(open(real_json)) if os.path.exists(real_json) else {}
    data.pop("sonnet1m45MigrationComplete", None)
    data.pop("opusProMigrationComplete", None)
    with open(os.path.join(gateway_home, ".claude.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 软链真实 ~/.claude 目录（保留 settings/MCP/projects）
    gw_claude = os.path.join(gateway_home, ".claude")
    if os.path.exists(os.path.expanduser("~/.claude")) and not os.path.exists(gw_claude):
        os.symlink(os.path.expanduser("~/.claude"), gw_claude)

    env = os.environ.copy()
    env["HOME"] = gateway_home
    env["ANTHROPIC_BASE_URL"] = _anthropic_base_url(runtime)
    env["ANTHROPIC_AUTH_TOKEN"] = runtime["api_key"]
    return env
```

### launch_claude api_key 分支改为
```python
else:
    gateway_health_check(runtime)
    env = _claude_gateway_env(runtime)  # isolated HOME strips migration flags
    state_home = None
    cleanup_ctx = None
```

---

## 问题 6：Claude gateway 模式 "model not found"（双重 /v1）

### 根因
Claude Code 的 Anthropic TypeScript SDK 使用路径 `/v1/messages`（已含 `/v1`）。
若 `ANTHROPIC_BASE_URL=https://xxx/v1`，SDK 拼出 `https://xxx/v1/v1/messages` → 404 →
Claude Code 报 "There's an issue with the selected model"。

### 修复位置
- `ccs_launchers.py` → `_claude_gateway_env()` 函数尾部

### 修复方式
```python
# 设置 ANTHROPIC_BASE_URL 前，剥离 /v1 后缀
base_url = _anthropic_base_url(runtime)   # 可能是 https://xxx/v1
if base_url.endswith("/v1"):
    base_url = base_url[:-3]              # 变成 https://xxx
env["ANTHROPIC_BASE_URL"] = base_url
# SDK 会自动拼 /v1/messages → https://xxx/v1/messages ✓
```

### 验证
```bash
# 错误（404）：
curl -X POST https://xxx/v1/v1/messages ...

# 正确（200）：
curl -X POST https://xxx/v1/messages ...
```

---

## 合并 checklist

合并任意 worktree 到 main 前，确认以下 5 点：

- [ ] `_probe_models` 用的是 `f"{try_url}/models"`，**不是** `f"{base_url}/v1/models"`
- [ ] `load_provider_credentials` 返回 dict 包含 `openai_api_key` 字段
- [ ] `resolve_provider_context` 有 `provider["openai_api_key"] = ...` 这行
- [ ] `launch_codex` api_key 分支调用的是 `_codex_gateway_env(runtime, ...)`，**不是** 直接设 `env["OPENAI_API_KEY"]`
- [ ] `launch_claude` api_key 分支调用的是 `_claude_gateway_env(runtime)`，**不是** 直接设 `env["ANTHROPIC_AUTH_TOKEN"]`（防 `[1m]` 自动升级）
- [ ] `_claude_gateway_env` 里 `ANTHROPIC_BASE_URL` 设置前去掉 `/v1` 后缀（防双重 `/v1/v1/messages`）
