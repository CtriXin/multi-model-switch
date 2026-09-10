# v4.10.1 · 安装提示与 Claude 安全规则

- **安装命令提示对齐**：裸 `curl` 和解析到最新稳定版的 npm wrapper 都显示一行简洁提示；只有旧版本 pin、`dev` 或 `canary` 才显示完整版本概览。
- **Claude deny rule 修正**：修正新版 Claude Code 会忽略的危险命令匹配格式，避免每次启动重复出现设置修复提示。

本版本不改变会话存储、运行中任务或模型配置。Web 静态资源与 `mms_version.py` 均为 `4.10.1`。
