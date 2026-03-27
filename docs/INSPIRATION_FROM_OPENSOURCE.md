# MMS 可借鉴的开源项目

> 2026-03-25 调研笔记

---

## 10x (1.4k⭐)

**Smart Model Routing** — 自动选最快的模型处理任务

| Tier | Model | Speed | Best For |
|------|-------|-------|----------|
| ⚡⚡ Superfast | GPT OSS 20B | 20x | 简单查询 |
| ⚡ Fast | Kimi K2 1T | 4x | 代码生成 |
| ◆ Smart | Claude Opus 4 | 1x | 复杂推理 |

**MMS 融合思路**:
- `preferFree` + `tier` 已有类似逻辑
- 可以增加 `task complexity` 自动检测 → 选模型
- Superpowers workflow 可以用 mms 的多模型切换实现

---

## BMAD-METHOD (42k⭐)

**Multi-Agent Orchestration** — 12+ 专业化 agent

**MMS 融合思路**:
- mms 的 bridge 可以为不同 agent 类型路由到不同模型
- 比如：PM agent → Claude（擅长结构化）、Coder agent → Codex（擅长执行）

---

## Vibe Kanban (24k⭐)

**支持 10+ coding agents** — Claude Code, Codex, Gemini CLI, Amp, Cursor...

**MMS 融合思路**:
- mms 已经支持多 provider，可以考虑适配更多 CLI
- 统一的 adapter 接口可以让切换更丝滑

---

## 总结

mms 的定位是**模型路由基础设施**，这些项目的思路可以融入：

1. **Task-aware routing** — 根据任务复杂度自动选模型
2. **Agent-type routing** — 不同角色用不同模型
3. **Workflow orchestration** — 多步骤流水线，每步不同模型

不需要重新造轮子，只需要让 mms 的路由更智能。
