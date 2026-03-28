# 通道与模型管理 TODO Review — Deep Dive

> By Claude (Opus 4.6) — 2026-03-24
> 针对 `.ai/plan/TODO.md` 中通道/模型管理相关条目的审阅。

---

## 一、总体评价

TODO 条目的拆分粒度和优先级排序 **基本合理**。但有几个结构性问题如果不在编码前对齐，很容易做成"CLI 加了一套、Web 加了另一套、两边语义对不上"的局面。

---

## 二、逐条审阅

### ✅ 没问题的条目

| 条目 | 评价 |
|------|------|
| "为 companycrs 支持手工补充模型" | 真实痛点，优先级正确 |
| "特殊通道文档" | 该写，不急 |
| "模型别名/展示名" | 确实不急，放 Neither 合理 |

### ⚠️ 需要澄清或调整的条目

#### 1. "明确 provider 模型展示层语义：远端 / 缓存 / 最终展示"

方向对，但定义不够锐利。当前实际已经有 **四层**：

```
Layer 1: Remote  — HTTP GET /models 返回的原始列表
Layer 2: Cache   — ~/.config/mms/cache/models_{provider_id}.json (24h TTL)
Layer 3: Fallback — config.toml 里的 fallback_models（Remote 和 Cache 都失败时）
Layer 4: Display  — 经过 CLI family filter + role filter + recommend filter 后的最终列表
```

新增 `extra_models` / `hidden_models` 实际上是在 Layer 3 和 Layer 4 之间插入一个 **Layer 3.5: Patch**：

```
Layer 3.5: Patch — extra_models 补入 + hidden_models 剔除
```

**建议：** 把这五层画成一个明确的 pipeline，每层的输入输出类型一致（都是 `list[str]` 或 `list[ModelInfo]`），这样后面无论在 CLI 还是 Web 端都能复用同一套语义。

#### 2. "为 provider 配置增加 extra_models / hidden_models 持久化"

关键问题：**存在哪里？**

选项 A：`config.toml` 的 `[[providers]]` 里加字段
```toml
[[providers]]
id = "companycrs"
extra_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
hidden_models = ["gpt-4o-mini-2024-07-18"]
```

选项 B：独立文件 `~/.config/mms/provider_overrides/<provider_id>.toml`
```toml
extra_models = ["claude-opus-4-6"]
hidden_models = ["gpt-4o-mini-2024-07-18"]
```

选项 C：在现有 cache 文件旁加一个 `models_{provider_id}.overrides.json`

**我的建议：选项 A。**

理由：
- `config.toml` 是 mms 配置的单一事实源（single source of truth）
- 用户已经在 `config.toml` 里管理 provider，加两个字段最直觉
- 独立文件会增加"配置散落在多处"的认知负担
- `config.toml` 已经有 `fallback_models` 先例，加 `extra_models` / `hidden_models` 语义自洽

但需要注意：`config.toml` 目前是手工编辑 + TUI 写入混合的。如果 TUI 要写回 `extra_models`，需要确保不破坏用户手工写的注释和格式。用 `tomlkit`（保留格式）而不是 `tomli` + `tomli_w`（会丢格式）。

#### 3. "在通道管理 TUI 中增加模型管理入口"

`mms_tui.py` 已经很重了。建议 **不要** 在现有 `select_connect_tui()` 里继续膨胀，而是：

```
select_connect_tui() 菜单：
  > 添加网关通道
  > 添加官方账号
  > 管理已有通道      ← 进入后再展开
  > 迁移旧配置

管理已有通道 → select_channel_detail_tui(provider_id):
  > 编辑基本信息
  > 模型管理           ← 新增入口
  > 测试连接
  > 删除通道

模型管理 → select_model_management_tui(provider_id):
  > 查看当前模型列表（标注来源：remote / extra / fallback）
  > 刷新远端列表
  > 添加补充模型
  > 隐藏模型
  > 恢复默认
```

**重点：** 模型管理的 TUI 应该放在 **新函数** 里，不要塞进现有函数。`mms_tui.py` 已经 800+ 行，按照代码红线（单文件 ≤ 800 行），可能需要考虑拆文件了。

#### 4. "model_list_mode 设计评估（remote / hybrid / manual）"

**这条我建议直接砍掉。**

理由：
- `remote` 就是现状（只靠 /models）
- `manual` 是一个极端 case（谁会完全手写模型列表？）
- 真正需要的只有 `hybrid`：remote + extra - hidden
- 引入 mode 概念会增加配置复杂度，用户需要理解三种模式的区别
- 不如直接默认 hybrid 行为：有 remote 就用 remote，extra 永远追加，hidden 永远剔除

如果非要保留一个 escape hatch，可以加一个 `skip_remote_models = true` 的布尔开关，而不是一个三值 enum。

#### 5. "自定义 models endpoint 选项"

当前 `config.toml` 已经有 `models_endpoint` 字段，`_probe_models()` 也已经支持。这条 TODO 实际上是 **TUI 暴露已有能力**，不是新功能。

建议降级为"在编辑通道 TUI 中展示 models_endpoint 字段"，实现成本很低。

#### 6. "provider 模型管理页交互设计"

这条和第 3 条（TUI 模型管理入口）有大量重叠。建议合并，不要分成两个 TODO。

---

## 三、被遗漏的问题

### 3.1 CLI 与 Web-v2 的模型管理语义正在分裂

Web-v2 **已经有** 一套模型管理机制：

| 能力 | Web-v2 | CLI (计划中) |
|------|--------|-------------|
| 模型白名单 | `provider.models` | 无 |
| 手工添加模型 | `provider.customModels` | `extra_models` |
| 隐藏模型 | `suppressModelForToday()` (临时) | `hidden_models` (持久) |
| 模型来源标注 | 无 | 计划中 |

问题：
- Web-v2 的 `customModels` 存在 `ProviderConfig`（前端 JSON），CLI 的 `extra_models` 存在 `config.toml`（后端）
- Web-v2 的 suppress 是临时的（localStorage + expiry），CLI 的 hidden 是持久的
- 两边的模型列表可能不一致

**建议：** 至少在设计文档里明确 —— CLI 的 `config.toml` 是 source of truth，Web-v2 要么读同一份配置（通过 runtime-api），要么自己维护但不与 CLI 互通。不要两边都是 source of truth。

### 3.2 `extra_models` 的类型问题

`extra_models` 是 `list[str]`（纯 model ID）还是 `list[ModelInfo]`（带 metadata）？

如果是纯 string：
```toml
extra_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
```

如果是 ModelInfo：
```toml
[[providers.extra_models]]
id = "claude-opus-4-6"
display_name = "Claude Opus 4.6"
protocols = ["anthropic_messages"]
```

**建议：** Phase 1 用纯 string，足够覆盖 companycrs 的需求。ModelInfo 结构留给"模型别名"那个 Neither 条目。

### 3.3 `hidden_models` 的粒度

隐藏是 provider 级别还是全局级别？

- Provider 级别：`companycrs` 隐藏 `gpt-4o-mini`，不影响 `newapi` 的 `gpt-4o-mini`
- 全局级别：所有 provider 都不显示 `gpt-4o-mini`

**建议：** Provider 级别。全局隐藏的需求不明确，而且可以通过在每个 provider 里都加来实现。

### 3.4 通道增删改的"删"

TODO 里只提了模型的增删改，但通道本身的 **删除** 流程也需要设计：

- 删除 `config.toml` 里的 `[[providers]]` 条目
- 清理 `credentials.toml` 里对应的 key
- 清理 `~/.config/mms/cache/models_{provider_id}.json`
- 如果有 bridge 正在用这个 provider，需要提示而不是静默删除

### 3.5 通道增删改的"增"

现有 `connect_gateway` 流程是：TUI 引导输入 URL + Key → 写入 config.toml。但缺少：

- **模板选择**：`mms_adapter_registry.py` 里有 `PROVIDER_TEMPLATES`，TUI 应该让用户从模板开始，而不是每次从空白填起
- **连接测试**：添加后自动 `GET /models` 验证 URL 和 Key 是否有效
- **协议探测**：自动判断是 OpenAI 兼容还是 Anthropic 兼容（通过试探 `/v1/models` vs `/v1/messages`）

### 3.6 bridge 对模型列表的影响

`mms_bridge.py` 自己会暴露一个 `/v1/models` endpoint 给 Codex 等 CLI。bridge 返回的模型列表来自上游 provider 的 probe 结果。

如果用户在 provider 上配了 `extra_models`，bridge 的 `/v1/models` 是否也应该返回这些模型？**应该。** 否则 Codex 侧看不到手工补充的模型。

这意味着 `extra_models` / `hidden_models` 的 patch 逻辑需要在 `_probe_models()` 里统一做，而不是在 TUI 展示层做。

---

## 四、建议的实现顺序

原 TODO 把所有条目平铺在四象限里，但缺少 **依赖关系**。我建议按这个顺序：

```
Step 1: 数据模型
  - 在 config.toml 的 provider schema 里加 extra_models / hidden_models
  - 定义 model pipeline 五层语义（文档）
  - 确保 tomlkit 读写不丢格式

Step 2: 核心逻辑
  - 在 _probe_models() 出口处加 patch 逻辑（extra 追加 + hidden 剔除）
  - bridge 的 /v1/models 自动继承 patch 结果
  - 验证：companycrs 补充 claude-opus-4-6 后，claude CLI 能看到并使用

Step 3: TUI 入口
  - 通道详情页加"模型管理"入口
  - 模型管理页：查看列表（标注来源）+ 添加 + 隐藏 + 刷新远端
  - 写回 config.toml

Step 4: 润色
  - 模型来源标注（remote / extra / fallback / hidden）
  - models_endpoint 在 TUI 中可编辑
  - 特殊通道文档
```

Step 1 → 2 → 3 是严格依赖链。Step 4 可以随时穿插。

---

## 五、需要改动的文件预估

| 文件 | 改动 | 是否受保护 |
|------|------|-----------|
| `config.toml` schema | 加 `extra_models` / `hidden_models` 字段 | — (配置) |
| `mms_core.py` | `_probe_models()` 出口加 patch 逻辑 | ✅ 受保护 |
| `mms_tui.py` | 新增模型管理 TUI 函数 | ✅ 受保护 |
| `mms_bridge.py` | 验证 `/v1/models` 已继承 patch | ✅ 受保护 |
| `mms_adapter_registry.py` | PROVIDER_TEMPLATES 加新字段 | ✅ 受保护 |
| 新文件（可选） | `ccs_model_management.py` — TUI 拆分 | 无 |

四个受保护文件都要改，意味着 **每一步都需要用户明确授权**。建议分 PR 提交，不要一把做完。

---

## 六、一句话总结

TODO 的 **"做什么"** 列对了，但缺少三个关键决策：① `extra_models` 存哪里（建议 config.toml）；② patch 逻辑在哪层生效（建议 `_probe_models()` 出口，而非 TUI 展示层）；③ CLI 和 Web-v2 的模型管理语义如何统一（至少要明确不统一也行，但要写下来）。`model_list_mode` 三值 enum 建议砍掉，默认 hybrid 就够了。
