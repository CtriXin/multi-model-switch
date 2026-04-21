        # multi-model-switch / architecture-mainline outline

        - Conclusion: MMS 的主流程是“加载配置并做显式路由决策”，然后再生成隔离会话、gateway 或导出 route artifacts。
        - Timestamp: 2026-04-20 22:15:13 +0800
        - Agent: Codex

        ## Entry Surfaces
- Installer and optional packs- TUI & CLI- Web / runtime API## Core Runtime / Workflow
- Load config & state- Resolve adapters- Route & classify- Launch or bridge- Export & diagnose## Artifacts / Operator Surfaces
- Config tree- Routing artifacts- Operator surfaces## Out of Scope

        - 所有 protected core file 的内部实现细节
- 尚未落到 mainline 的 proposal UI
- 具体某个 provider 的私有 endpoint
