# MMS Launcher Tree

## 一句话结论
MMS 是一个 launcher-first 的本地运行时：先做显式入口与路由决策，再启动隔离 Claude/Codex session，并把 resume、provider profile、session pack 控制在 MMS 管理边界内。

## 结构拆解
- Entry surfaces: TUI、direct CLI、export/preset。
- Decision layer: provider profiles、priority、diagnostics。
- Runtime isolation: Claude/Codex isolated home、bridge、resume state。
- Session packs: token/web/agent capabilities injected per session.

## 关键关系
- Entry -> Decision: 用户选择先解析成 runtime 和 model source。
- Decision -> Runtime: 只有明确 route/provider/account 进入 launcher。
- Runtime -> Resume: Claude/Codex resume 数据被限制在可审计的 session/store 里。
- Packs -> Runtime: optional capabilities are session-scoped, not global fallbacks.

## 备注
- README 使用 SVG，Mermaid 源文件用于后续维护。
