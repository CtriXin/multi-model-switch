# RFC: WebUI Launch Defaults 面板

**状态**: Draft — 待 committee 审核
**日期**: 2026-06-14
**作者**: Agent (claude-opus-4-6)
**影响面**: `mms_config_web.py` (preferences 流程), `mms_tui.py` (默认值来源), `docs/MMS_USER_PREFERENCES.md` (schema 扩展)

---

## 1. 问题

`preferences.toml` 已定义 `[launch.defaults]` schema（见 `docs/MMS_USER_PREFERENCES.md`），TUI `confirm_tui()` 已有完整的 session-level 交互 toggle（Thinking / Effort / Bypass / Caveman / NSR / Agent Pack / Claude 1M / Session Surface），但存在两个缺口：

1. **WebUI 完全不读取、不展示、不编辑 `[launch.defaults]`** — 用户无法通过 WebUI 管理这些默认值
2. **TUI `confirm_tui()` 的默认值全部硬编码** — 即使用户在 `preferences.toml` 配置了 `[launch.defaults]`，TUI 不会读取

当前 WebUI preferences 流程只处理 `launch.disabled_clis` 和 `session_surfaces.disabled`，`[launch.defaults]` 下的 7 个字段完全被忽略。

### 不是问题

- TUI toggle 本身是 session-level 交互覆盖，不需要搬到 WebUI
- OpenCode context window / output limit 有完整的 capability truth chain，200k/8192 是 fallback 不是主源
- ECC/OMC 等 agent pack 功能本身正常，只是默认值不可通过 WebUI 配置

---

## 2. 已有 Schema

`docs/MMS_USER_PREFERENCES.md` 已定义：

```toml
[launch.defaults]
thinking_mode = "enable"        # enable | disable
reasoning_effort = "high"       # low | medium | high | xhigh
caveman_mode = "enable"         # enable | disable
caveman_level = "light"         # light | standard | full
nsr_mode = "enable"             # enable | disable
agent_pack = "none"             # none | ecc | omc
bypass = true                   # true | false
```

Per-CLI 覆盖（已定义但同样未接入 WebUI）：

```toml
[launch.cli.codex]
bypass = true

[launch.cli.claude]
thinking_mode = "enable"

[launch.cli.agy]
reasoning_effort = "medium"
```

---

## 3. 当前代码接入点 (inspected)

| 函数 | 位置 | 当前行为 | 需要扩展 |
|------|------|----------|----------|
| `_migration_preferences_payload()` | mms_config_web.py:2797 | 读 `prefs.get("launch")` 但只取 `disabled_clis` / `session_surfaces` | 额外提取 `defaults` 子表 |
| `_normalize_asset_preferences_payload()` | mms_config_web.py:5051 | 处理 `launch.disabled_clis` / `session_surfaces.disabled` / `assets` | 新增 `launch.defaults.*` 白名单校验 |
| `_merge_asset_preferences()` | mms_config_web.py:5083 | 只合并 `launch.disabled_clis` | 新增 `launch.defaults` 合并 |
| `build_preferences_plan()` | mms_config_web.py:5105 | diff 展示 | 自动包含 launch.defaults 变更 |
| `setup_web_save_preferences()` | mms_config_web.py:~5160 | confirm + backup + atomic write + audit | 无需改动，复用 |
| `confirm_tui()` | mms_tui.py:3495 | 硬编码默认值参数 | 调用方改为从 preferences 读取 |

---

## 4. 实现方案

### Step 1: WebUI launch.defaults 读取 / 编辑 / 保存 [高优先]

**目标**: WebUI preferences 面板新增 `[launch.defaults]` 编辑区

**改动文件**: `mms_config_web.py`（受保护文件 — 仅扩展 preferences 流程内部）

**1a. 读取**: `_migration_preferences_payload()` 额外提取 `launch.defaults`

```python
# 在现有 disabled_clis 提取之后
launch_defaults = launch.get("defaults", {})
payload["launch_defaults"] = {
    "thinking_mode":     launch_defaults.get("thinking_mode"),
    "reasoning_effort":  launch_defaults.get("reasoning_effort"),
    "caveman_mode":      launch_defaults.get("caveman_mode"),
    "caveman_level":     launch_defaults.get("caveman_level"),
    "nsr_mode":          launch_defaults.get("nsr_mode"),
    "agent_pack":        launch_defaults.get("agent_pack"),
    "bypass":            launch_defaults.get("bypass"),
}
```

**1b. WebUI 面板**: preferences section 新增 launch defaults 表单

| 字段 | 控件 | 可选值 | 未设置时含义 |
|------|------|--------|------------|
| `thinking_mode` | 下拉 | `enable` / `disable` | 使用硬编码默认 (`enable`) |
| `reasoning_effort` | 下拉 | `low` / `medium` / `high` / `xhigh` | 使用硬编码默认 (`high`) |
| `caveman_mode` | 下拉 | `enable` / `disable` | 使用硬编码默认 (`disable`) |
| `caveman_level` | 下拉 | `light` / `standard` / `full` | 使用硬编码默认 (`light`) |
| `nsr_mode` | 下拉 | `enable` / `disable` | 使用硬编码默认 (`enable`) |
| `agent_pack` | 下拉 | `none` / `ecc` / `omc` | 使用硬编码默认 (`none`) |
| `bypass` | 开关 | `true` / `false` | 使用硬编码默认 (`false`) |

每个字段都可留空（不写入 TOML），表示"不覆盖，使用系统默认"。

**1c. 校验**: `_normalize_asset_preferences_payload()` 新增白名单校验

```python
LAUNCH_DEFAULTS_SCHEMA = {
    "thinking_mode":    {"enable", "disable"},
    "reasoning_effort": {"low", "medium", "high", "xhigh"},
    "caveman_mode":     {"enable", "disable"},
    "caveman_level":    {"light", "standard", "full"},
    "nsr_mode":         {"enable", "disable"},
    "agent_pack":       {"none", "ecc", "omc"},
    "bypass":           {True, False},
}
# 非法值静默忽略，不 crash
```

**1d. 合并**: `_merge_asset_preferences()` 新增 `launch.defaults` 写入

- 只写白名单字段
- `None` 或空值 = 从 TOML 中删除该字段（恢复系统默认）
- 不覆盖用户手动编辑的其他 `[launch]` 子字段

**不改动**: TUI 返回结构、launcher 输入结构、runtime 决策逻辑、保存流程（confirm phrase / backup / audit 全部复用）

---

### Step 2: TUI confirm_tui() 读取 preferences.toml 默认值 [高优先]

**目标**: TUI 启动确认屏的默认值从 `preferences.toml [launch.defaults]` 读取，取代硬编码

**改动文件**: `mms_tui.py` 调用方（可能在 `mms_core.py`）— 受保护文件，仅改默认值来源

**关键约束**: **`confirm_tui()` 函数签名不变** — 它仍然接受 `thinking_enabled_default` 等参数，只是调用方传入的值从 preferences 读取而非硬编码。

**新增 helper**:

```python
def load_launch_defaults(cli=None):
    """
    从 preferences.toml 读取 [launch.defaults]，返回 dict。
    如果指定 cli，叠加 [launch.cli.<cli>] 覆盖。
    缺失键使用原硬编码兜底值。
    """
    # 1. 读 [launch.defaults]
    # 2. 如果 cli 指定，叠加 [launch.cli.<cli>]
    # 3. 缺失键填入硬编码兜底
    # 返回 dict with keys matching confirm_tui() parameter names
```

**调用方改动示例**:

```python
# Before:
action, bypass, *rest = confirm_tui(
    cli, model_info,
    thinking_enabled_default=True,
    reasoning_effort_default="high",
    ...
)

# After:
defaults = load_launch_defaults(cli=cli_name)
action, bypass, *rest = confirm_tui(
    cli, model_info,
    thinking_enabled_default=defaults["thinking_enabled"],
    reasoning_effort_default=defaults["reasoning_effort"],
    ...
)
```

**验证**:
- 不配置 `[launch.defaults]` 时行为与现在完全一致（硬编码兜底值不变）
- 配置后 TUI 确认屏默认值正确反映 preferences
- Per-CLI 覆盖正确叠加

---

### Step 3: Bypass 覆盖语义 [中优先]

**目标**: bypass 模式下支持独立的默认值覆盖

**Schema 扩展** (写入 `docs/MMS_USER_PREFERENCES.md`):

```toml
[launch.defaults]
bypass = true
thinking_mode = "enable"
reasoning_effort = "high"

# 可选：bypass 激活时的覆盖值
[launch.defaults.bypass_overrides]
thinking_mode = "disable"        # bypass 时覆盖 thinking_mode
reasoning_effort = "medium"      # bypass 时覆盖 reasoning_effort
```

**语义规则**:

| 配置状态 | bypass=false | bypass=true |
|----------|-------------|-------------|
| 无 bypass_overrides | 使用 launch.defaults | 使用 launch.defaults |
| 有 bypass_overrides | 使用 launch.defaults（忽略 overrides） | 使用 bypass_overrides 覆盖 launch.defaults |

- `bypass_overrides` 是可选子表
- 只有 bypass 激活时才读取
- 未配置的 override 字段继承普通 `launch.defaults` 的值
- `bypass_overrides` 只支持 `thinking_mode` 和 `reasoning_effort`（其他字段 bypass 时语义不变）

**改动文件**:
- `docs/MMS_USER_PREFERENCES.md`: 扩展 schema
- `mms_config_web.py`: WebUI 条件性展示 bypass override 字段
- `load_launch_defaults()` helper: 支持 bypass 参数

**验证** (3 条路径单元测试):
1. `bypass=false` → 忽略 `bypass_overrides`
2. `bypass=true` + 无 `bypass_overrides` → 继承普通 defaults
3. `bypass=true` + 有 `bypass_overrides` → 覆盖生效

---

### Step 4: Context / Output 显式覆盖入口 [低优先]

**目标**: WebUI 添加 `max_output_tokens` 显式覆盖入口

**背景**: OpenCode context / output 有完整 capability truth chain:

```
latest-approved capabilities
  → model-policy
    → WebUI capabilities
      → provider-profiles
        → per-runtime explicit
          → hardcoded fallback (200k / 8192)
```

200k / 8192 是 fallback，不是主源。这步只添加 WebUI 覆盖入口，不引入新 hardcode。

**改动**:
- WebUI OpenCode 配置区域添加可选 `max_output_tokens` 覆盖字段
- 明确标注"留空则使用 capability chain 默认值"
- 值写入 override 层（不影响 capability chain 优先级）

**不改动**: `OPENCODE_DEFAULT_OUTPUT_LIMIT` / `OPENCODE_DEFAULT_CONTEXT_WINDOW` 常量、profile 解析逻辑、capability truth chain

---

## 5. 改动边界声明

### 会改动
- `mms_config_web.py`: preferences 读取/校验/合并/展示流程（4 个函数扩展 + 1 个面板新增）
- `mms_core.py` 或 `confirm_tui()` 调用方: 默认值传递来源
- `docs/MMS_USER_PREFERENCES.md`: bypass_overrides schema

### 不会改动
- TUI `confirm_tui()` 的交互逻辑和返回结构
- launcher 输入结构和启动参数
- runtime 决策逻辑
- bridge 行为
- provider / account 优先级
- 任何已有字段语义
- `OPENCODE_DEFAULT_*` 常量
- 配置文件结构（`config.toml` / `override.toml` 不变）
- 保存流程（confirm phrase / backup / audit trail 全部复用）

---

## 6. 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 受保护文件改动 (`mms_config_web.py`, `mms_tui.py`) | 中 | 仅扩展 preferences 流程，不触及启动链路 |
| 新字段引入隐式耦合 | 低 | 白名单 + 枚举校验，非法值静默忽略 |
| TUI 默认值读取失败 | 低 | 硬编码兜底值不变，preferences 缺失 = 原行为 |
| bypass_overrides 语义歧义 | 低 | 只支持 thinking_mode / reasoning_effort 两个字段 |
| WebUI 保存破坏现有 preferences | 低 | 复用已有 atomic write + backup 流程 |

---

## 7. 验证计划

### Step 1 完成后
- [ ] `python3 -m py_compile mms_config_web.py`
- [ ] WebUI preferences 面板正确展示 7 个 launch.defaults 字段
- [ ] 保存后 `preferences.toml` 结构正确（`[launch.defaults]` 下的字段）
- [ ] 留空字段不写入 TOML
- [ ] 非法值被静默忽略

### Step 2 完成后
- [ ] 不配置 `[launch.defaults]` → TUI 行为与当前完全一致
- [ ] 配置 `thinking_mode = "disable"` → TUI 确认屏 Thinking 默认关闭
- [ ] 配置 `[launch.cli.codex].bypass = true` → 仅 Codex 启动时 bypass 默认开启
- [ ] per-CLI 覆盖正确叠加在 launch.defaults 之上

### Step 3 完成后
- [ ] 3 条路径单元测试全部通过
- [ ] WebUI 中 bypass=false 时 bypass_overrides 区域隐藏
- [ ] bypass=true 时 bypass_overrides 区域可见并可编辑

### Step 4 完成后
- [ ] max_output_tokens 留空 → capability chain 正常工作
- [ ] max_output_tokens 设置值 → override 生效
- [ ] `OPENCODE_DEFAULT_*` 常量未被改动

### 全部完成后
- [ ] `python3 scripts/regression_fresh_user_gate.py --quick`
- [ ] 主启动链路 smoke: 选择的模型/来源 = 实际启动使用的模型/来源

---

## 8. 实施顺序建议

```
Step 1 → Step 2 → (可独立) Step 3 → (可独立) Step 4
         ↑ 共享 load_launch_defaults() helper
```

Step 1 和 Step 2 有依赖关系（Step 2 的 `load_launch_defaults()` 需要 Step 1 的 schema 校验逻辑）。Step 3 和 Step 4 可独立实施。

建议每个 Step 独立提交，不混合。
