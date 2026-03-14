# Findings & Decisions

## Requirements
- 用户要求：按“公司/品牌”维度维护主要来源，而不是按具体模型维护。
- 当前先保留 10 个维护优先来源，方便后续继续扩 adapter。
- 需要把“后续新增 OAuth 默认支持 `claude bridge`”写进项目规则。

## Research Findings
- 已稳定的原生来源只有三类：
  - `Claude`
  - `Codex / GPT`
  - `Gemini`
- 已验证可桥接到 `claude` 的官方来源只有两类：
  - `codex OAuth -> claude`
  - `gemini OAuth -> claude`
- 当前更稳的 provider/API 来源包括：
  - `Qwen`
  - `Kimi`
  - `MiniMax`
  - `Z.ai`
  - `BigModel / 智谱`
  - `Volcengine / Doubao`
- Kimi 官方产品和 CLI 能力存在，但当前最稳的 MMS 接法仍然是 `provider_api`，不是直接先补 OAuth bridge。
- 个别品牌的官方资料存在重定向或路径迁移，所以 registry 参考链接优先采用：
  - 品牌官网
  - 官方文档首页
  - 已确认可访问的功能页

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| top 10 以“公司/品牌”记录，而不是以模型数记录 | 用户明确要求是公司维度 |
| registry 先以代码常量 + 文档落地，不直接驱动运行时 | 先固化维护边界，避免引入额外 UI/逻辑耦合 |
| 新增 `official OAuth` adapter 时，默认应同时评估 `claude bridge` | 当前项目已经在 `codex / gemini` 两条链路上验证可行 |
| 没有稳定 CLI / SDK / backend 的来源，默认继续按 `provider_api` 接入 | 避免做脆弱 bridge |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 现有仓库存在 unrelated local changes | 只补 registry 和文档，不去误碰用户实验改动 |
| 个别品牌官方资料路径变化较快 | registry 参考链接优先用品牌主页或文档首页 |

## Resources
- [README.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/README.md)
- [docs/OAUTH_ACCOUNTS.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/OAUTH_ACCOUNTS.md)
- [docs/ADAPTER_REGISTRY.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ADAPTER_REGISTRY.md)
- [docs/MIGRATION_AND_WORKTREE.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/MIGRATION_AND_WORKTREE.md)
- [docs/ITERATION_PLAN.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/ITERATION_PLAN.md)
- [ccs_adapter_registry.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_adapter_registry.py)

## Visual/Browser Findings
- 这轮不改 UI，只补来源公司/adapter 基线和文档入口。
