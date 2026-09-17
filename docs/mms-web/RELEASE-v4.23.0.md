# v4.23.0 · 目录浏览与稳定性收敛

本次按明确授权，将近期改动集中校验后提升 minor 版本；后续单个迭代仍沿用 patch 规则。

- 工作目录在 Pilot 内逐层浏览和选择，支持键盘展开、收起，重复按右方向键保持展开；窄屏可用。
- OpenRouter 目录差异检查使用所有已知模型的最新参考值，空的新快照不再让旧参考失效，保留变更来源。
- committee 传递已选模型的明确 protocol，保持 Anthropic Messages / OpenAI Responses 路由边界。
- 更新通道收到错误 JSON 类型时返回可处理的请求错误。
- 首次 OpenCode bootstrap、批准 bundle 校验和 config export 增加隔离回归；缺失或损坏的 bundle 继续 fail closed。

升级保持原有 config root、账号和历史记录。仍是 4.x stable 线；5.x Bot 工作台通过 Preview 通道获取。

验证覆盖本地隔离 Python/Web 测试、实际目录选择及 390px 页面操作。没有改动真实账号配置；不把本地测试视作真实 provider 或 Windows 原生安装验收。
