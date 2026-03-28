# MMS App 化路线图（索引）

详细规划见 `feature/app` 分支的 `APP_PLAN.md`。

## 快速摘要

**目标**：把以下功能提取为可独立运行的 app 层（不依赖 CLI 工具安装）：
- Gateway 绑定（provider 配置）
- OAuth 登录（claude / codex 账号）
- Chat（多模型并排比较）
- Discuss（多模型审议 → 综合结论）

**不纳入 app 的部分**：CLI 子进程启动（claude/codex/qwen/kimi）、scene 选择——这些继续与 CLI 结合。

## 执行时机

**当前阶段不开始**。等所有 feature 分支合入 main 后再启动。

当前待合并的分支：
- `feature/chat`
- `feature/chat-discuss`
- `feature/claude-first-launcher`

## 关键技术决策（待定）

merge 完成后，先做：
1. 从 `mms_core.py` 提取 `mms_api.py`（portable layer，约 150 行）
2. 在此基础上起 FastAPI server，兼顾手机 bridge

App 技术方案暂定：**FastAPI + Web UI → 后续 Tauri wrap**。

## 手机 Bridge

本机跑 FastAPI，手机通过局域网或 Tailscale 连接，SSE 流式输出，纯 HTML 页面，无需安装 app。
