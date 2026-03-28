# MMS Iteration Handoff

最后更新：2026-03-13

## 目标

这份文档用于给下一次迭代快速对齐上下文，避免重新读完整仓库和聊天记录。

当前仓库定位：

- 公共仓库名：`Multi-Model Switch (MMS)`
- 当前主命令：`mms`
- 兼容命令：`ccs`
- 旧公司版基线仍保留在 `/Users/xin/ccs`
- 新仓库只继续做公开版和兼容层演进

## 已完成

### 1. 公开基线

- 已重写公开 README
- 已移除新仓库里的公司接入文档
- 已保留本地 override 机制，避免公司内部共享默认值时污染公开仓库

相关文件：

- `README.md`
- `ccs_core.py`

### 2. 命名兼容

- 已新增 `mms` 入口
- `ccs` 继续保留为兼容入口
- 安装脚本会同时安装 `mms` 和 `ccs`
- 已补 `MMS Installer.command`
- 旧 `CCS Installer.command` 继续保留

相关文件：

- `mms`
- `ccs`
- `install.sh`
- `MMS Installer.command`
- `CCS Installer.command`

### 3. Provider 最小骨架

- 已从旧 `[api]` 结构演进到 `[[providers]]`
- 已支持 `provider.default`
- 已支持 `protocols`
- 已支持 `supported_clis`
- 已支持 provider 级别 fail-fast 校验
- 默认 provider 支持同时声明：
  - `anthropic_messages`
  - `openai_chat_completions`

这一步是为了兼容“同一个网关地址同时暴露多种协议”的现实场景。

相关文件：

- `ccs_core.py`
- `ccs_launchers.py`
- `config.example.toml`

### 4. 凭据分离

- provider 元数据继续放在 `config.toml`
- 真实凭据继续放在 `credentials.sh`
- 默认 provider 仍兼容旧环境变量：
  - `CCS_API_BASE_URL`
  - `CCS_API_KEY`
- 凭据读写已升级成 per-provider 形式

### 5. 中文模式

- 用户模式已改为：
  - `全部模型`
  - `推荐模型`
- 旧 `dev / ops` 仍自动兼容
- README 和示例配置已同步成中文模式

### 6. Provider 可见操作

当前已经支持：

- `mms config provider.list`
- `mms config provider.default`
- `mms config provider.default <id>`
- `mms config api.edit`

### 7. 按模型 Context Window 自动配置 Claude Code（2026-03-28）

Claude Code 的 auto-compact 和 blocking limit 由内部 `NM()` 函数决定 context window，
但 NM() 只认识 Claude 模型——对国产模型一律返回 200k 默认值，导致频繁触发 compact。

**解决方案**：三层联动——

1. **壳名机制**：非 Claude 模型的 env slot 统一用 `claude-sonnet-4-6[1m]`（NM() 返回 1M 上限），
   bridge 层在 API 请求时替换成真实模型名。
2. **`CLAUDE_CODE_AUTO_COMPACT_WINDOW`**：按真实模型的 context window 往下 cap。
   Claude Code 内部 `Math.min(NM(), env)` 生效为实际值。
3. **`CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`**：同步设为 `context_window - 3000`。

**各模型 context window**（来源：各厂商官方 API 文档，2026-03 更新）：

| 模型 | Context |
|------|---------|
| Claude Opus/Sonnet 4.6 (`[1m]`) | 1,000,000 |
| Claude Haiku 4.5 | 200,000 |
| kimi-for-coding / kimi-k2.5 | 262,144 |
| qwen3.5-plus / qwen3-coder-plus | 1,000,000 |
| qwen3-max | 262,144 |
| glm-5 / glm-5-turbo / glm-5.1 / glm-4.7 | 200,000 |
| MiniMax-M2.5 | 196,608 |
| MiniMax-M2.7 | 200,000 |

**智能路由场景**：取所有活跃模型（heavy/medium/light）中最小的 context window。

相关文件：

- `ccs_launchers.py` — `_MODEL_CONTEXT_WINDOWS` 映射表、`_effective_context_window()`、`_with_1m_suffix()`
- `~/.claude/statusline-command.sh` — 读取 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 显示真实 context

## 已验证

- `./mms --help` 正常
- `./ccs --help` 正常
- Python 语法检查通过
- `dev / ops` 到中文模式映射通过
- `provider.default` 读写逻辑通过
- 当前仓库工作区干净

最近几次关键提交：

- `404bbdd` `feat: localize user modes and expose provider config`
- `493dba3` `feat: add minimal provider-based runtime`
- `f8cc8f8` `feat: add mms entrypoint with ccs compatibility`
- `e76f9e9` `feat: bootstrap public mms baseline`

## 还没做

### 1. 真正的迁移链路

还没做这些：

- `~/.ccs` -> `~/.mms` 自动迁移
- `~/.config/ccs` -> `~/.config/mms` 自动迁移
- 旧 env 文件迁移
- 旧安装产物迁移
- 迁移脚本和 dry-run

### 2. Provider 管理能力

现在只支持“看”和“切默认值”，还不支持：

- 新增 provider
- 编辑 provider 元数据
- 删除 provider
- 逐个 provider 配置凭据
- 交互式选择 provider

### 3. 公司 overlay

还没做：

- `editions/company/`
- overlay merge 规则
- overlay 应用脚本
- overlay 回滚

### 4. 自动探测

还没做：

- 根据 URL 猜协议
- 根据 URL 猜认证方式
- provider 连通性非阻塞探测

### 5. 环境变量导出增强

还没做：

- provider-scoped 全局导出
- shell/profile 写入与回滚
- 切换 provider 时清理旧变量

### 6. 排序和推荐增强

还没做：

- 显式排序编辑
- 主推 / 备选链路
- 场景绑定不同 provider
- 更细的推荐管理

## 明天建议从这里开始

优先级建议按这个顺序：

1. 先补 provider 的最小增改能力
2. 再补 preset 绑定 provider 的可见编辑体验
3. 再决定先做迁移脚本还是 company overlay

### 明天最建议先做的具体项

建议先做 provider 管理的最小闭环：

- `mms config provider.add`
- `mms config provider.edit <id>`
- `mms config provider.remove <id>`
- `mms config provider.credentials <id>`

原因：

- 现在底层 provider 结构已经有了
- 但用户还只能手改 TOML
- 不先补这个，后面无论是多平台接入还是 company overlay 都不好验证

## 设计约束

明天继续改时要保持这些约束不被破坏：

- 不删除旧的 `/Users/xin/ccs`
- 新仓库继续公开化，不放公司内部接入文档
- 公司仍可通过本地单文件 override 使用
- 凭据不能回写到公开 `config.toml`
- 默认仍以单次注入为主，不直接改全局 shell

## 快速命令

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git status --short
./mms --help
./ccs --help
```

查看当前 provider：

```bash
./mms config provider.list
./mms config provider.default
```

## 收尾结论

当前状态适合暂停，已经不是“方向性重构草稿”，而是“有公开基线、有兼容入口、有 provider 底座”的可持续迭代状态。
