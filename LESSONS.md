# MMS 经验教训

> 轻量级经验沉淀，避免同类问题重复踩坑。
> 触发时机：错误修复后、发现更优方案时、踩坑后。
> 条目成熟后可 promote 到 CLAUDE.md 成为永久规则。

---

# 🐛 错误教训

> 从 bug、故障、踩坑中提炼的经验

### 2026-03-14 | Worktree 开发：代码不生效的陷阱

- **现象**：worktree 里改了代码，`mms` 命令跑的还是旧逻辑
- **根因**：`install.sh` 把文件复制到 `~/.mms/`，全局 `mms` 命令指向那边
- **教训**：worktree 开发用 `python3 ./mms` 或 `./mms`，确认 sys.path 指向当前目录
- **关键词**：开发, worktree, install

### 2026-03-14 | TUI 返回值兼容：tuple 解包防御

- **现象**：`confirm_tui` 改返回 tuple 后，未更新的调用点 crash
- **根因**：返回类型从 `str` 变成 `(str, bool)`，解构赋值失败
- **教训**：改函数返回类型时，用 `isinstance(result, tuple)` 做防御性解包
- **关键词**：API 兼容, TUI, 返回值

---

# 💡 最佳实践

> 发现的更优方案、性能优化、架构改进

### 2026-03-14 | 启动热路径：禁止同步网络调用

- **场景**：`_source_choices_for_tui` 预计算 12 个 scene/variant 的 provider 源，串行 probe = 4s
- **方案**：
  1. 文件缓存（`~/.config/mms/cache/models_{pid}.json`，24h TTL）
  2. 惰性字典（`_LazySourceChoices`）按需计算，不预加载
  3. 后台并行预热（`ThreadPoolExecutor`）填充缓存
- **效果**：4s → 0.1s
- **规则**：启动路径上 **零同步网络调用**
- **关键词**：性能, probe, 缓存, 惰性加载

### 2026-03-14 | 及时精简不维护的路径

- **场景**：`CLI_NAMES` 包含 qwen/kimi，启动时检测浪费 3.5s
- **方案**：从默认检测列表移除，保留代码让用户手动使用
- **规则**：不再活跃维护的功能从默认路径移除，降级为可选
- **关键词**：性能, CLI_NAMES, 精简

### 2026-03-14 | Provider 模型缓存：文件 > 内存

- **场景**：`_provider_candidates` 对非 default provider 返回 `models=None`，每次触发网络 probe
- **方案**：`_provider_candidates` 优先从文件缓存读模型列表，仅首次走网络
- **规则**：可离线确定的数据优先持久化，不依赖内存缓存跨进程生效
- **关键词**：缓存, provider, 持久化

### 2026-03-14 | Claude 兼容性回归：不要只测 /models

- **现象**：provider 的 `/models` 返回正常，但真实模型 chat 或 Claude 路径仍然会报 `404 / timeout / selected model issue`
- **根因**：`/models` 只能证明模型枚举通，不等于模型可调用，更不等于可挂到 Claude CLI
- **教训**：Claude 回归至少分三层：
  1. provider / OAuth 连通性
  2. 模型最小 chat
  3. Claude 路径兼容性
- **规则**：不要再用“`/models` 正常”替代 Claude 回归
- **关键词**：Claude, 回归, /models, chat, bridge

### 2026-03-15 | Kimi CodingPlan：agent-only 不等于不可用

- **现象**：`kimi-for-coding` 走普通 OpenAI `chat/completions` 返回 403，但走 Anthropic / Claude-compatible `messages` 可以正常返回
- **根因**：上游把它限制在 Coding Agents / Claude-compatible 路径，不是完全禁用
- **教训**：诊断里要把这类情况标成 `agent_only`，不要误归类成“模型彻底不可用”
- **规则**：对 Kimi CodingPlan 这类 provider，优先验证 Claude 路径；当前不要再暴露给 codex 直连选择
- **关键词**：Kimi, agent_only, Claude-compatible, codex

### 2026-03-14 | 大规模模型回归：先抽样再全量

- **现象**：一上来全 provider、全模型、全 CLI 跑回归，耗时长，定位噪音大
- **根因**：问题往往先集中在少数 provider 的路由、权限或端点配置，不需要一开始就全量烧穿
- **教训**：先按 provider 抽样 `2-5` 个模型，把错误分成 `auth / access / endpoint / timeout / cli` 几类，再决定是否全量跑
- **规则**：日常验证默认先抽样，发布前或大改后再全量
- **关键词**：回归, 抽样, 全量, provider, 诊断

### 2026-03-14 | 诊断脚本：必须独立于启动热路径

- **现象**：如果把模型兼容性检测塞进正常启动流程，TUI 和启动体验会明显变慢
- **根因**：Claude 路径兼容性检查天然包含网络探测、bridge、甚至真实 CLI 冒烟
- **教训**：这类诊断应该做成独立脚本或独立 doctor 子命令，而不是混进 `launch` 或 `TUI` 逻辑
- **规则**：高成本验证逻辑不进入日常启动热路径
- **关键词**：诊断, 热路径, 启动, Claude, 性能
