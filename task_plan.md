# Task Plan: Adapter Registry 与来源 Top 10 基线

## Goal
把当前默认维护的前 10 个来源公司/品牌落成 registry，并把“后续新增 OAuth 默认支持 claude bridge”的规则写入项目文档和代码常量，方便多个 worktree 继续扩展。

## Current Phase
Phase 3

## Phases

### Phase 1: Requirements & Discovery
- [x] 确认用户要的是“按公司/品牌维护来源”，不是按单个模型维护
- [x] 盘点当前已经稳定的来源：Claude / Codex / Gemini
- [x] 盘点当前更适合按 provider 落地的来源：Qwen / Kimi / MiniMax / Z.ai / BigModel / Volcengine
- **Status:** complete

### Phase 2: Design & Scope
- [x] 确定前 10 以“公司/品牌”为单位，而不是按模型数排名
- [x] 确定 registry 只记录维护优先级和默认 adapter，不直接驱动运行时
- [x] 确定新增 `official OAuth` 的默认规则：稳定后默认补 `claude bridge`
- **Status:** complete

### Phase 3: Implementation
- [x] 新增 `ccs_adapter_registry.py`
- [x] 新增 `docs/ADAPTER_REGISTRY.md`
- [x] 更新 README / OAuth 文档 / planning files
- **Status:** complete

## Key Questions
1. 哪 10 个来源最值得作为默认维护清单？
2. 哪些来源已经适合做原生 OAuth，哪些还应按 provider 落地？
3. 新增来源时，默认 adapter 规则要怎么固化？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 前 10 来源按“公司/品牌”维护，而不是按模型数量维护 | 用户明确要求是公司维度 |
| registry 先落成代码常量 + 文档，不直接驱动运行时 | 先固化规则，避免过早把 UI/运行时绑死 |
| 新增 `official OAuth` adapter 时，默认也要评估并补 `claude bridge` | 这是当前项目已经验证有效的扩展方向 |
| 没有稳定原生路径的来源，继续按 `provider_api` 落地 | 避免做脆弱 bridge |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 官方资料分布在不同站点，单个搜索页不稳定 | 1 | 使用品牌官网 / 官方文档首页 / 已确认可访问的入口做 registry 参考 |

## Notes
- 当前 worktree 仍有用户本地未提交改动：`.gitignore`、`README.md`、`ccs_core.py`、未跟踪 `.ai/` / `.claude/` / `ccs_discuss.py` 等，不能误提交。
- `codex / gemini -> claude` 已验证成立，因此被写入“新增 OAuth 默认评估 bridge”的规则。
