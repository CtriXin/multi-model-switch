# MMS vNext Phase 1: Preset Schema + activate/env 最小闭环

> worktree: `preset-schema` | branch: `feat/preset-schema-phase1`
> 日期: 2026-03-30

## Context

MMS 当前的 preset 系统只有 save + `--preset` launch。用户要复用 preset 中的 provider 配置（API key、base URL）给外部工具，只能走 `mms --export claude --apply`，这条路跟 preset 是脱节的。

目标：让 preset 成为「命名的完整环境配置」，并通过 `mms activate` / `mms env` 两个子命令把 preset 和 env export 串起来，实现最小闭环。

**本轮只做 direct provider (auth_mode=api_key) 场景**，不碰 oauth / oauth_bridge。

## 约束

- 先只支持 direct provider export 场景
- 不承诺 oauth / oauth_bridge 一步到位
- 不改默认启动路径语义
- CLI flags 优先级必须高于 override/preset
- 尽量复用现有 `--export` / `get_export_env()` 逻辑

## 现有代码状态（worktree 已有未提交改动）

mms_core.py +96 行：
- `_normalize_preset_entry()` — 单 preset 规范化
- `_normalize_presets_config()` — 全 preset 批量规范化，挂进 `load_config()`
- `_preset_model_info()` — 从 preset 提取 model_info（过滤 cli/provider/account/description/bridge）
- `_resolve_named_preset()` — 按名查 preset，带报错
- `save_preset_interactive()` — 新增 description 字段，保存时走 normalize

## 实现步骤

### Step 1: auth_mode 临时推断函数（不落盘）

**位置**: mms_core.py，`_resolve_named_preset()` 附近新增

auth_mode 是 runtime 解析结果，不是稳定配置语义。如果存进 preset，后面容易出现「preset 标了 api_key，但实际因 CLI/account/provider 组合走成别的路径」的错觉。

做法：新增 `_infer_preset_auth_mode(preset)` 纯函数，临时推断，只用于展示和 env/activate 解析，**不写回 preset dict、不落盘**。

```python
def _infer_preset_auth_mode(preset):
    if preset.get("bridge"):
        return "oauth_bridge"
    if preset.get("account"):
        return "oauth"
    if preset.get("provider"):
        return "api_key"
    return None  # 未知，由 runtime resolution 决定
```

`_normalize_preset_entry()` 不改。

### Step 2: `mms env <preset>` 子命令

**位置**: main() 子命令分发 (mms_core.py:6037+) + 新 handler

```
mms env <preset-name> [--apply] [--provider OVERRIDE]
```

实现：
1. 在 main() 的子命令分发区增加 `if command == "env"` 分支
2. 新增 `handle_env_command(cfg, argv)`:
   - 用 argparse 解析 `preset_name`, `--apply`, `--provider`
   - 调用 `_resolve_named_preset()` 查 preset
   - 新增内部函数 `_resolve_preset_export_runtime(cfg, preset, provider_override=None)`:
     - 明确只支持 provider runtime（api_key 模式），不做 oauth/account 解析
     - `provider_id = provider_override or preset.get("provider") or None`
     - 如果 provider_id 缺失 → 回落 config default，**stderr 提示**（仅 TTY）: "预设未指定 provider，使用默认: {id}"
     - `cli = preset.get("cli", "claude")`
     - 用 `_infer_preset_auth_mode(preset)` 判断：oauth/oauth_bridge → 提示"此预设使用 OAuth 模式，不支持 env export"并 return None
     - `runtime = ensure_provider_credentials(cfg, provider_id)`
     - 复用 `validate_provider_for_cli(cli, runtime)` 校验 cli/provider 组合可用性（失败走现有报错路径）
     - `exports = get_export_env(cli, runtime)` — 如果返回空 → 提示"{cli} 无需 export" 并 return None
     - return `(cli, exports, runtime)` 三元组
   - 输出 export 语句（复用 handle_export 的格式）
   - `--apply` 时写到 `~/.config/mms/env/<preset-name>.sh`

### Step 3: `mms activate <preset>` 子命令

**位置**: main() 子命令分发 + 新 handler

```
mms activate <preset-name> [--provider OVERRIDE]
```

实现：
1. 复用 `_resolve_preset_export_runtime()` 拿到 (cli, exports, runtime)
2. 输出纯 export 行到 stdout（无 Rich 格式化，适合 `eval $(mms activate foo)`）
3. **不默认写文件** — activate 语义是「纯 stdout for eval」，写文件属于副作用，交给 `mms env --apply`
4. 如果 `sys.stdout.isatty()` → stderr 打印一行 dim 提示（不干扰 eval 管道）

### Step 4: --presets 列表增加 description/auth_mode 列

**位置**: `args.presets` 分支 (mms_core.py:~6156)

在 Table 里增加两列：
- `description` — 显示 preset 的 description 字段
- `auth_mode` — 临时推断显示（`_infer_preset_auth_mode()`，api_key/oauth/oauth_bridge/—）

### Step 5: --preset launch 路径复用 helper

**位置**: `args.preset` 分支 (mms_core.py:~6191)

将现有 inline 逻辑替换为：
```python
p = _resolve_named_preset(cfg, args.preset)
if p is None:
    return
cli = p["cli"]
model_info = _preset_model_info(p)
```

行为完全不变，只是复用已有 helper 减少重复。

## 优先级链路

```
CLI flags (--provider) > preset.provider > config default
```

在 `_resolve_preset_export_runtime()` 中：
```python
provider_id = cli_provider_override or preset.get("provider") or None
runtime = ensure_provider_credentials(cfg, provider_id)
validate_provider_for_cli(cli, runtime)  # 复用现有校验路径
exports = get_export_env(cli, runtime)
```

## 数据流

```
mms env <preset> --provider foo
  → _resolve_named_preset(cfg, name)     # 查 preset
  → _resolve_preset_export_runtime(cfg, preset, "foo")
    → _infer_preset_auth_mode(preset)        # 临时推断，不落盘
    → ensure_provider_credentials(cfg, "foo")  # 拿 runtime（foo 覆盖 preset.provider）
    → validate_provider_for_cli("claude", runtime)  # 校验 cli/provider 组合
    → get_export_env("claude", runtime)        # 拿 env dict
  → 格式化 + 输出
```

## 涉及文件

| 文件 | 改动性质 |
|------|----------|
| `mms_core.py` | 核心改动（用户已授权） |
| `mms_launchers.py` | **不改**（复用 `get_export_env`） |

## 不做的事

- 不碰 oauth / oauth_bridge export（直接 early return + 提示）
- 不改默认启动路径（`mms` 无参数行为完全不变）
- 不改 TUI 选择结果结构
- 不加隐式自动切换
- 不改 mms_launchers.py
- 不改 mms_bridge.py

## 验证方法

1. `python3 -m py_compile mms_core.py` — 语法检查
2. `python3 mms --presets` — 确认 description / auth_mode 列正确显示
3. `python3 mms env <preset>` — 确认输出正确的 export 语句
4. `python3 mms env <preset> --apply` — 确认写入文件
5. `python3 mms activate <preset>` — 确认纯文本输出可 `eval`
6. `python3 mms --preset <name>` — 确认 launch 行为不变（回归）
7. `python3 mms activate <oauth-preset>` — 确认 graceful 提示
