# MMS 智能路由系统 — 技术综述

> 版本：tui-refactor-v2 worktree
> 日期：2026-03-25
> 状态：核心已实现，待合并 main

---

## 1. 整体架构

```
用户输入
  │
  ▼
Claude CLI / Codex CLI
  │  POST /v1/messages
  ▼
┌──────────────────────────────────┐
│         mms_bridge.py            │
│  (本地 HTTP 代理，拦截所有请求)    │
│                                  │
│  1. 提取用户文本                  │
│  2. 调用 classify_task() 分类     │
│  3. 按 tier 选模型名              │
│  4. 按 tier 选 provider endpoint  │
│  5. 转发到上游                    │
└─────────┬────────────────────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
Provider A   Provider B     （跨 provider 负载）
(heavy)      (light/medium)
```

### 涉及文件

| 文件 | 职责 |
|------|------|
| `mms_router.py` | 分类引擎：关键词 → LLM → 默认值；model-routes.json 导出 |
| `mms_bridge.py` | 本地代理：请求拦截、tier→模型映射、跨 provider 转发 |
| `mms_core.py` | Provider role/priority 体系、`_resolve_best_provider()` |
| `mms_tui.py` | 负载模式 TUI：slot 编辑、provider 切换 |

---

## 2. Provider Role + Priority 体系

### 2.1 config.toml 配置

每个 `[[providers]]` 支持 `role` 和 `priority` 字段：

```toml
[[providers]]
id = "bailian-codingplan"
name = "百炼 CodingPlan"
role = "primary"        # primary | auto | fallback
priority = 75           # 正整数，数值越小越优先
enabled = true
```

### 2.2 Role 权重

```python
ROLE_WEIGHTS = {"primary": 0, "auto": 1, "fallback": 2}
```

| Role | 权重 | 含义 |
|------|------|------|
| `primary` | 0 | 首选，同等 priority 下优先于 auto |
| `auto` | 1 | 默认，按 priority 参与路由 |
| `fallback` | 2 | 备用，仅当 primary/auto 都无法覆盖该模型时使用 |

### 2.3 Provider 自动选择算法

`_resolve_best_provider(cfg, model_name, ...)`:

```
1. 遍历所有 enabled provider
2. 过滤：支持目标 CLI + 支持目标协议 + 有 API key + 有 base_url
3. 检查该 provider 是否有目标模型（probe 缓存 or fallback_models）
4. 打分：(ROLE_WEIGHTS[role], -priority)
5. 升序排序，取第一个 → 最优 provider
```

排序效果：`primary:P75` > `primary:P100` > `auto:P75` > `auto:P100` > `fallback:*`

---

## 3. 智能路由分类引擎 (`mms_router.py`)

### 3.1 四层分类流程

```
classify_task(text) → (tier, reason)
  │
  ├─ Layer 0: 系统请求 fast-path
  │   text.startswith("[SUGGESTION MODE") → light, "system_prompt"
  │
  ├─ Layer 1: Guardrail 文件名检测
  │   text 中包含 ccs_core / ccs_bridge / auth / security 等 → heavy
  │
  ├─ Layer 2: 关键词 fast-path（零延迟）
  │   Heavy 关键词：refactor multi-file / 架构 / 安全 / 迁移 / 并发 ...
  │   Light 关键词：fix typo / 改注释 / 你好啊 / hi / hello ...
  │   来源：内置默认 + 用户配置 + 自动学习（三层合并去重）
  │
  ├─ Layer 3: LLM 异步分类（非阻塞）
  │   后台线程调用 light 模型做二分类 + 置信度
  │   当前请求用上次缓存结果（5分钟有效）
  │   高置信 → 采用；低置信 → fallback medium
  │
  └─ Layer 4: 默认 medium（安全中间档）
      reason = "no_match→medium"
```

### 3.2 LLM 分类优化

```python
_llm_classify(text, api_url, api_key, model):
  - max_tokens: 128（只需 2 个词：LIGHT/HEAVY + HIGH/LOW）
  - temperature: 0
  - thinking: {"type": "disabled"}   # 禁用 thinking，避免 token 浪费
  - timeout: 5s
  - 协议回退：Anthropic messages → OpenAI chat/completions
  - token 异常检测：input > 500 → 日志告警
```

### 3.3 Sticky Escalation

```
进入 HEAVY 后保持 N 轮（STICKY_DECAY_TURNS = 5）不降级
除非：高置信 LIGHT 信号（关键词命中 or LLM high confidence）→ override
```

### 3.4 自动学习

```
LLM 连续 N 次（_LEARN_THRESHOLD = 3）对相似 pattern 给出相同高置信 LIGHT
→ 自动 promote 为 learned keyword
→ 存入 ~/.config/mms/route_learned.json
→ 后续零延迟命中，不再调 LLM
```

安全策略：只自动学习 light（误判代价低），heavy 不自动学习。

### 3.5 关键词配置

| 来源 | 路径 | 优先级 |
|------|------|--------|
| 用户配置 | `~/.config/mms/route_keywords.json` | 最高 |
| 自动学习 | `~/.config/mms/route_learned.json` | 中 |
| 内置默认 | 代码硬编码 | 最低 |

文件变化时热重载（mtime 检查）。

---

## 4. Bridge 路由集成 (`mms_bridge.py`)

### 4.1 请求处理流程

```
POST /v1/messages → bridge handler
  │
  ├─ 提取用户文本（回退查找，跳过 tool_result）
  │   reversed(user_msgs) → _extract_user_text() → 找到第一个有文本的
  │
  ├─ 短时去重（3 秒窗口）
  │   同一文本 + 3s 内 → 复用上次分类结果，reason="dedup(...)"
  │
  ├─ classify_task() 分类
  │
  ├─ Sticky escalation 处理
  │
  ├─ 按 tier 选模型名
  │   light → light_model
  │   medium → medium_model
  │   heavy → heavy_model（保持原值）
  │
  ├─ 按 tier 选 provider endpoint（跨 provider）
  │   slot_configs[current_level] → {url, key}
  │
  └─ 转发到上游 provider
```

### 4.2 Tool-Use 续接处理

```
问题：Claude CLI 的 tool_use 续接请求，last user message 是 tool_result（无文本）
旧行为：默认 HEAVY → 浪费
新行为：沿用上次 _last_level → 同一 turn 保持一致 tier
        日志标记 reason="tool_continue"
```

### 4.3 跨 Provider 负载

`slot_configs` 支持每个 tier 独立的 `(url, key)`：

```python
slot_configs = {
    "medium": {"url": "https://api.kimi.com/...", "key": "sk-kimi-xxx"},
    "light":  {"url": "https://api.minimax.com/...", "key": "sk-xxx"},
}
# heavy 用默认 gateway_url / gateway_key
```

TUI 选完 3 个 slot 的模型后，`_resolve_best_provider()` 自动为每个 slot 匹配最优 provider。

---

## 5. 负载模式 TUI (`mms_tui.py`)

### 5.1 入口

品类选择页 → "⚖ 负载模式" → 负载 TUI

### 5.2 流程

```
┌─────────────────────────────┐
│  ⚖ 负载模式                 │
│                             │
│  最近 3 条历史记录           │
│  ▸ MiniMax-M2.7 / M2.5 / k2│
│    kimi-for-coding / glm / M│
│    ...                      │
│  ✏ 自定义...                │
│                             │
│  ↑↓ 选择  Enter 确认  Esc   │
└─────────────────────────────┘
        │ Enter on 自定义
        ▼
┌─────────────────────────────┐
│  ✏ 自定义负载               │
│                             │
│  heavy:   MiniMax-M2.7  百炼│  ← Enter 进入全屏选模型
│  medium:  MiniMax-M2.5  xin │  ← +/- 切 provider
│  light:   kimi-k2.5    kimi │
│  ─────────────────────────  │
│  ▶ 启动                     │  ← heavy 选好后才能点
│                             │
│  Enter 编辑  +/- Provider   │
└─────────────────────────────┘
        │ Enter on slot
        ▼
    全屏品类选择 → 子模型选择 → 回到 slot 编辑
```

### 5.3 历史持久化

`~/.config/mms/lb_history.json`:

```json
{
  "recent": [
    {"heavy": "MiniMax-M2.7", "medium": "MiniMax-M2.5", "light": "kimi-k2.5",
     "label": "MiniMax-M2.7 / MiniMax-M2.5 / kimi-k2.5"},
    ...
  ]
}
```

保留最近 3 条，去重。

---

## 6. model-routes.json 导出

### 6.1 命令

```bash
mms routes          # 显示当前路由表
mms routes export   # 强制重新生成
```

### 6.2 输出格式

`~/.config/mms/model-routes.json`（权限 0o600）：

```json
{
  "_meta": {
    "generated_at": "2026-03-25T14:30:00Z",
    "generator": "mms"
  },
  "routes": {
    "kimi-k2.5": {
      "anthropic_base_url": "https://api.kimi.com/coding/",
      "api_key": "sk-kimi-xxx",
      "provider_id": "kimi-codingplan",
      "priority": 75,
      "role": "auto"
    },
    "claude-sonnet-4-6": {
      "anthropic_base_url": "https://...",
      "api_key": "sk-xxx",
      "provider_id": "bailian-codingplan",
      "priority": 75,
      "role": "primary"
    }
  }
}
```

### 6.3 生成规则

1. 只收录支持 `anthropic_messages` 协议且有 `anthropic_base_url` 的 provider
2. 每个模型被最高优先级 provider claim（primary > auto > fallback × priority desc）
3. 同一模型不重复，先 claim 先得
4. mtime 缓存：config.toml 未变时直接读缓存

### 6.4 Hive MCP 消费方式

Hive 读取 `~/.config/mms/model-routes.json`，按 model name 查找对应的 `anthropic_base_url` + `api_key`，直接发 Anthropic Messages API 请求。无需关心 provider 选择逻辑。

---

## 7. 日志与诊断

### 7.1 路由日志

```bash
tail -f ~/.config/mms/lb_route.log
```

```
[09:34:14] ⬇ LIGHT  model=kimi-k2.5      reason=keyword: greeting  prompt=你好啊
[09:34:28]   MEDIUM  model=MiniMax-M2.5   reason=no_match→medium    prompt=我有什么todo
[09:34:30]   MEDIUM  model=MiniMax-M2.5   reason=tool_continue      prompt=(tool_result)
[09:34:32]   MEDIUM  model=MiniMax-M2.5   reason=dedup(no_match→medium)  prompt=我有什么todo
```

### 7.2 Reason 含义速查

| reason | 含义 |
|--------|------|
| `keyword: xxx` | 内置/用户/学习关键词命中 |
| `guardrail: xxx` | 提到受保护文件名 |
| `system_prompt` | 系统请求（SUGGESTION MODE 等） |
| `llm_async:tier+high_confidence` | LLM 异步分类结果（上次缓存） |
| `no_match→medium` | 无关键词命中 + 无 LLM 结果 → 默认中档 |
| `tool_continue` | tool_result 续接，沿用上次 tier |
| `dedup(...)` | 3 秒内重复请求，复用上次分类 |
| `sticky(N)` | Sticky escalation，剩余 N 轮 |
| `sticky_override(...)` | 高置信 LIGHT 打破 sticky |
| `learned:xxx` | 自动学习的关键词 |

### 7.3 LLM 错误日志

同文件，`LLM_ERR` 标签：

```
[09:41:58]   LLM_ERR  exception: timed out model=kimi-k2.5 elapsed=5001ms
[09:42:00]   LLM_ERR  token_waste model=kimi-k2.5 tokens(in=27086,cache=1280,out=44) — consider disabling thinking
```

---

## 8. 已修复的问题

| 问题 | 根因 | 修复 |
|------|------|------|
| tool_result 续接默认走 HEAVY | bridge 无法从 tool_result 提取文本 → 默认 heavy | 回退查找有文本的 user message + 沿用 `_last_level` |
| 同一请求被分类两次 | Claude CLI 对同一 turn 发 2 次请求 | 3 秒去重窗口 |
| Provider priority 联动 bug | TUI 的 +/- 操作修改全局 `priority_changes` dict | +/- 只改 `provider_overrides`（per-model），priority 调整只在 Enter 确认时 |
| Thinking token 浪费 | LLM 分类时 Kimi 自动开 thinking（27k input） | 显式 `"thinking": {"type": "disabled"}` + max_tokens=128 |
| SUGGESTION MODE 浪费 | Claude CLI 每轮发 autocomplete 请求（~9k tokens） | `promptSuggestionEnabled: false` + router fast-path |
| 负缓存未持久化 | probe 失败的 provider 每次重新 timeout 10s+ | 负缓存 2 小时 TTL，存入 probe_cache |

---

## 9. 待补充/讨论

1. **LLM 分类模型选择** — 当前用 light_model（负载里的 light slot 模型）做分类。是否需要独立配置一个 classify 专用模型？
2. **分类结果跨 session 持久化** — 当前 LLM 异步结果只在内存中缓存（5 分钟），是否需要持久化到磁盘？
3. **Hive 消费 model-routes.json 的刷新机制** — 当前只在 `mms` 启动时检查 mtime 自动重新生成。Hive 是否需要 watch 机制或 webhook？
4. **负载模式的 provider 一致性** — 当前 heavy/medium/light 各自独立选 provider。是否需要策略约束（如同一 provider 优先）？
5. **路由日志分析** — 是否需要定期统计 tier 分布、LLM 命中率、关键词覆盖率？
