# OpenCode / OmO 模型配置说明

这份文档是当前本机 OpenCode + OmO 配置的人类可读版；只记录模型名和用途，不记录通道名、Base URL、API Key。

- 更新时间：2026-05-10T06:01:56-04:00
- 全量 smoke：35/35 通过
- 实际配置文件：`~/.config/opencode/opencode.json`、`~/.config/opencode/oh-my-openagent.jsonc`
- repo 内只保存说明文档；真实 OpenCode 配置不进 git。

## 先说清楚：Agent 和 Category

| 名称 | 是什么 | 你怎么理解 |
|---|---|---|
| Agent | 具体执行人格/工位 | `sisyphus`、`prometheus`、`atlas` 这些是 Agent。启动某个 Agent，就用它自己的主模型和 fallback。 |
| Category | 任务类型/模型档位预设 | `ultrabrain`、`deep`、`visual-engineering` 这些是 Category，不是 Agent。它们像“任务模式”，用于把任务路由到一组模型。 |
| fallback | 备用顺序 | OmO 当前是按顺序 fallback：主模型先跑；报错、限流、超时、不可用时再换下一个。不是自动并行二选一，也不是自动比较两个答案。 |
| 二选一 | 推荐做法 | 如果一个任务确实两种模型都合适，放进 fallback 顺序即可；如果想主动选风格，就做两个 Agent/Category。 |

## 模型速览

| 模型 | 当前配置里的定位 |
|---|---|
| `gpt-5.5` | 最强 GPT 主力。适合最高难度规划、复杂架构、关键审查、长链路工程判断。 |
| `gpt-5.4` | 深度工程主力。适合实现、重构、debug、review；成本/速度比 gpt-5.5 更稳。 |
| `gpt-5.3-codex` | Codex 代码模型。适合代码生成、修复、补测试。 |
| `gpt-5.3-codex-spark` | CPA 专属轻量 Codex。适合 OpenCode-Builder / 快速代码任务备用。 |
| `deepseek-v4-pro` | 国产强推理主力。适合复杂分析、长上下文、中文技术判断；当前给 max。 |
| `deepseek-v4-pro[1m]` | DeepSeek 1M direct 版本。主要做 DeepSeek 同模型/长上下文备用。 |
| `deepseek-v4-flash` | DeepSeek 快速版。适合快速探索、低成本推理、simple fallback。 |
| `mimo-v2.5-pro` | MiMo 强版。适合发散、反例、创意/批判视角、中文综合判断。 |
| `mimo-v2.5` | MiMo 中档。适合 junior / low 档通用任务。 |
| `K2.6` | Kimi 主力代码/阅读模型。适合仓库探索、代码理解、文档检索、写作辅助。 |
| `kimi-for-coding` | Kimi coding 专用。适合代码阅读、局部实现、仓库问答备用。 |
| `kimi-k2.5` | Kimi 备用席。适合 Kimi family fallback。 |
| `qwen3.6-plus` | Qwen 通用主力。适合 quick、atlas、常规工程和中文任务。 |
| `qwen3.5-plus` | Qwen 中档快速版。适合 explore/simple/OpenCode-Builder。 |
| `qwen3-coder-plus` | Qwen coding 方向。适合代码探索和实现 fallback。 |
| `glm-5.1` | GLM 强写作/结构化推理。适合 Metis、writing、中文整理、判断。 |
| `glm-5-turbo` | GLM 快速版。适合 simple/minimal/quick fallback。 |
| `MiniMax-M2.7` | 轻量通用模型。适合 minimal、低成本简单任务；当前无自家 direct fallback。 |
| `gemini-3.1-pro-preview` | Gemini 多模态主力。适合视觉工程、图片/页面理解、设计判断。 |
| `gemini-3-flash-preview` | Gemini 快速多模态备用。 |
| `gemini-3.1-flash-lite-preview` | Gemini 轻量多模态备用。 |

## Agent 对应关系

| Agent | 用途 | 主模型 | 主 effort | fallback（只写模型名，按顺序） |
|---|---|---|---|---|
| `sisyphus` | 最高强度通用执行者；重工程、长任务、难题推进。 | `gpt-5.5` | `xhigh, T=0.3` | gpt-5.5（同模型备用） [xhigh, T=0.3]<br>gpt-5.4 [xhigh]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>gemini-3.1-pro-preview [high, thinking] |
| `hephaestus` | 深度工程实现者；构建、修复、重构。 | `gpt-5.4` | `xhigh, T=0.2` | gpt-5.4（同模型备用） [xhigh, T=0.2]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>mimo-v2.5-pro [high, thinking]<br>qwen3.6-plus [high] |
| `prometheus` | 高阶规划/审查；架构判断、风险发现。 | `gpt-5.5` | `xhigh, T=0.2` | gpt-5.5（同模型备用） [xhigh, T=0.2]<br>gemini-3.1-pro-preview [high, thinking]<br>glm-5.1 [max, thinking]<br>K2.6 [high, T=1.0] |
| `atlas` | 广域探索/方案汇总；多模型中文工程判断。 | `qwen3.6-plus` | `high, T=0.4` | qwen3.6-plus（同模型备用） [high]<br>K2.6 [high, T=1.0]<br>kimi-for-coding [high, T=1.0]<br>glm-5.1 [max, thinking]<br>gpt-5.4 [high] |
| `oracle` | 强推理裁判；复杂问题最终判断。 | `deepseek-v4-pro` | `max, thinking` | deepseek-v4-pro[1m] [max, thinking]<br>gpt-5.5 [xhigh]<br>gemini-3.1-pro-preview [high, thinking]<br>mimo-v2.5-pro [high, thinking]<br>glm-5.1 [max, thinking] |
| `momus` | 反例/批判/发散视角；MiMo 主席位。 | `mimo-v2.5-pro` | `high, thinking, T=0.3` | mimo-v2.5-pro（同模型备用） [high, thinking]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>glm-5.1 [max, thinking]<br>gpt-5.5 [xhigh] |
| `metis` | 结构化判断和写作；GLM 主席位。 | `glm-5.1` | `max, thinking` | glm-5.1（同模型备用） [max, thinking]<br>K2.6 [high, T=1.0]<br>mimo-v2.5-pro [high, thinking]<br>qwen3.6-plus [high]<br>gpt-5.4 [high] |
| `librarian` | 资料/仓库阅读；Kimi 主席位。 | `K2.6` | `high, T=1.0` | K2.6（同模型备用） [high, T=1.0]<br>kimi-for-coding [high, T=1.0]<br>qwen3.6-plus [high]<br>glm-5.1 [max, thinking]<br>mimo-v2.5 [medium, thinking] |
| `explore` | 轻量探索；快速扫代码、找线索。 | `qwen3.5-plus` | `medium, T=0.3` | qwen3.5-plus（同模型备用） [medium]<br>qwen3-coder-plus [high]<br>deepseek-v4-flash [medium, thinking]<br>MiniMax-M2.7 [medium, maxTokens=8192] |
| `sisyphus-junior` | 低成本小执行者；简单实现/辅助。 | `mimo-v2.5` | `medium, thinking, T=0.3` | mimo-v2.5（同模型备用） [medium, thinking]<br>qwen3.5-plus [medium]<br>deepseek-v4-flash [medium, thinking]<br>MiniMax-M2.7 [medium, maxTokens=8192] |
| `multimodal-looker` | 视觉/多模态观察者；页面、截图、设计。 | `gemini-3.1-pro-preview` | `high, thinking, T=0.2` | gemini-3-flash-preview [high, thinking]<br>gemini-3.1-flash-lite-preview [medium, thinking]<br>gpt-5.4 [high] |
| `plan` | 计划专用；拆任务、定路线。 | `gpt-5.5` | `xhigh, T=0.2` | gpt-5.5（同模型备用） [xhigh, T=0.2]<br>gpt-5.4 [xhigh]<br>gemini-3.1-pro-preview [high, thinking]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking] |
| `build` | 构建专用；落地实现。 | `gpt-5.4` | `high, T=0.2` | gpt-5.4（同模型备用） [high, T=0.2]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>mimo-v2.5-pro [high, thinking]<br>qwen3.6-plus [high] |
| `OpenCode-Builder` | OpenCode 轻量构建位；简单代码任务。 | `qwen3.5-plus` | `medium, T=0.2` | MiniMax-M2.7 [medium, maxTokens=8192]<br>qwen3.5-plus（同模型备用） [medium]<br>glm-5-turbo [medium, thinking] |

## Category 对应关系

| Category | 用途 | 主模型 | 主 effort | fallback（只写模型名，按顺序） |
|---|---|---|---|---|
| `ultrabrain` | 最高脑力档；难规划、难判断。 | `gpt-5.5` | `xhigh` | gpt-5.5（同模型备用） [xhigh]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>gemini-3.1-pro-preview [high, thinking]<br>glm-5.1 [max, thinking] |
| `deep` | 深度工程档；复杂实现/修复。 | `gpt-5.4` | `xhigh` | gpt-5.4（同模型备用） [xhigh]<br>deepseek-v4-pro [max, thinking]<br>deepseek-v4-pro[1m] [max, thinking]<br>mimo-v2.5-pro [high, thinking]<br>qwen3.6-plus [high] |
| `unspecified-high` | 未指定但需要强模型。 | `deepseek-v4-pro` | `max, thinking` | deepseek-v4-pro[1m] [max, thinking]<br>gpt-5.4 [xhigh]<br>glm-5.1 [max, thinking]<br>K2.6 [high, T=1.0] |
| `visual-engineering` | 视觉/前端/多模态工程。 | `gemini-3.1-pro-preview` | `high, thinking` | gemini-3-flash-preview [high, thinking]<br>gpt-5.4 [high]<br>glm-5.1 [max, thinking]<br>mimo-v2.5-pro [high, thinking] |
| `artistry` | 创意、视觉、文案审美。 | `gemini-3.1-pro-preview` | `high, thinking` | mimo-v2.5-pro [high, thinking]<br>K2.6 [high, T=1.0]<br>gemini-3-flash-preview [high, thinking]<br>gpt-5.5 [high] |
| `quick` | 快速通用任务。 | `qwen3.6-plus` | `high, T=0.5` | qwen3.6-plus（同模型备用） [high]<br>qwen3.5-plus [medium]<br>deepseek-v4-flash [medium, thinking]<br>glm-5-turbo [medium, thinking] |
| `unspecified-low` | 未指定且低成本任务。 | `mimo-v2.5` | `medium, thinking, T=0.3` | mimo-v2.5（同模型备用） [medium, thinking]<br>qwen3.5-plus [medium]<br>MiniMax-M2.7 [medium, maxTokens=8192]<br>deepseek-v4-flash [medium, thinking] |
| `writing` | 写作、整理、中文表达。 | `glm-5.1` | `max, thinking` | glm-5.1（同模型备用） [max, thinking]<br>K2.6 [high, T=1.0]<br>mimo-v2.5 [medium, thinking]<br>MiniMax-M2.7 [medium, maxTokens=8192] |
| `code-exploration` | 代码库探索、读代码。 | `K2.6` | `high, T=1.0` | K2.6（同模型备用） [high, T=1.0]<br>kimi-for-coding [high, T=1.0]<br>qwen3.6-plus [high]<br>qwen3-coder-plus [high]<br>deepseek-v4-flash [medium, thinking] |
| `minimal` | 最小成本任务。 | `MiniMax-M2.7` | `medium, maxTokens=8192` | qwen3.5-plus [medium]<br>glm-5-turbo [medium, thinking] |
| `simple` | 简单任务。 | `qwen3.5-plus` | `medium, T=0.4` | qwen3.5-plus（同模型备用） [medium]<br>glm-5-turbo [medium, thinking]<br>MiniMax-M2.7 [medium, maxTokens=8192]<br>deepseek-v4-flash [medium, thinking] |
| `cn-deepseek` | DeepSeek family 专用位。 | `deepseek-v4-pro` | `max, thinking` | deepseek-v4-pro[1m] [max, thinking]<br>deepseek-v4-flash [medium, thinking] |
| `cn-mimo` | MiMo family 专用位。 | `mimo-v2.5-pro` | `high, thinking` | mimo-v2.5-pro（同模型备用） [high, thinking]<br>mimo-v2.5 [medium, thinking] |
| `cn-kimi` | Kimi family 专用位。 | `K2.6` | `high, T=1.0` | K2.6（同模型备用） [high, T=1.0]<br>kimi-for-coding [high, T=1.0]<br>kimi-k2.5 [high, T=1.0] |
| `cn-qwen` | Qwen family 专用位。 | `qwen3.6-plus` | `high` | qwen3.6-plus（同模型备用） [high]<br>qwen3.5-plus [medium]<br>qwen3-coder-plus [high] |
| `cn-glm` | GLM family 专用位。 | `glm-5.1` | `max, thinking` | glm-5.1（同模型备用） [max, thinking]<br>glm-5-turbo [medium, thinking] |
| `cn-minimax` | MiniMax family 专用位。 | `MiniMax-M2.7` | `medium, maxTokens=8192` | - |

## 当前使用建议

| 场景 | 优先用 | 说明 |
|---|---|---|
| 超难规划/审查 | `sisyphus` / `plan` / `ultrabrain` | GPT 5.5 主，CPA 同模型备用，再 DeepSeek/Gemini。 |
| 深度实现/debug | `hephaestus` / `build` / `deep` | GPT 5.4 主，DeepSeek/MiMo/Qwen 备用。 |
| 快速代码探索 | `explore` / `code-exploration` / `librarian` | Qwen/Kimi 体系优先。 |
| 复杂中文推理 | `oracle` / `cn-deepseek` | DeepSeek v4 pro max 主。 |
| 发散/反例/创意 | `momus` / `cn-mimo` | MiMo pro 主。 |
| 写作/整理 | `metis` / `writing` / `cn-glm` | GLM 5.1 max 主。 |
| 视觉/前端/截图 | `multimodal-looker` / `visual-engineering` | Gemini 3.1 pro preview 主。 |
| 低成本简单任务 | `OpenCode-Builder` / `simple` / `minimal` | Qwen/MiniMax/GLM turbo。 |
