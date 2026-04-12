# CLI / Provider Compatibility Notes

> 更新时间：2026-04-12
> 范围：`claude` / `codex` / `qwen` / `kimi` 与公开仓库内可见的通用兼容性规则。

## 为什么这份文档被改成精简版

这个仓库历史上沉淀过一些仅适用于私有部署的排障记录，里面可能包含：

- 私有 provider ID
- relay / sticky-session 架构细节
- 内网或云主机地址
- 运维路径、容器名、日志追溯命令

这些内容不适合保留在公开仓库里。

因此，公开仓库只保留通用兼容性原则；部署相关的细节请保存在你自己的本地 runbook / wiki / private docs 中。

## 公开仓库内仍然有效的兼容性原则

### 1. Provider 兼容性要区分协议，不要只看名字

至少先确认 provider 实际支持哪类协议：

- `anthropic_messages`
- `openai_chat_completions`
- `responses`
- 是否需要 manual model list

不要因为某个 provider “看起来像 Claude / OpenAI” 就假设它一定支持对应 CLI 的所有路径。

### 2. 模型可见性和真实可用性必须分开验证

最少要分别检查：

- 模型是否能被列出来
- 模型是否真的能被请求成功
- fallback / extra / hidden model 是否影响最终展示

### 3. Bridge / probe / fallback 是高风险区

凡是涉及下面这些点的改动，都应该视为高风险：

- `models_endpoint`
- probe cache
- fallback model logic
- header passthrough
- sticky-session key source
- `Responses` vs `Chat Completions` fallback

### 4. OAuth 隔离语义优先于“方便复用”

对于官方账号入口，默认目标应是：

- 跨账号完全隔离
- 同账号可 resume
- 不从真实 global 目录偷偷 seed 私有状态
- 不因 launcher 混用状态目录而串号

### 5. Proxy / timezone / IPv4-first 现在是 runtime profile 的一部分

对于 MMS 启动出来的 runtime，应该明确区分：

- `proxy`
- `NO_PROXY`
- `timezone`
- `force_ipv4`

不要把这些网络/环境参数混进展示层状态，也不要让它们只在最终子进程生效、但前置 probe 漂移到别的网络路径。

## 最小验证清单

如果你改了 provider / launcher / bridge / account isolation，至少做下面这些验证：

1. `python3 -m py_compile` 覆盖改动文件
2. 相关回归测试通过
3. 模型列表和真实启动链路一致
4. OAuth 账号隔离不串号
5. 配置了 proxy 时，坏 proxy 会被拦截
6. 启动环境里的 timezone / IPv4-first 符合预期

## 本地私有文档建议

如果你有部署相关内容，建议放到不进 git 的本地文件，例如：

- `docs/CLI_PROVIDER_COMPAT_QA.local.md`
- `docs/private-relay-smoketest.local.md`
- 你自己的 wiki / ops runbook

## 一句话

公开仓库保留通用兼容性原则；任何带真实部署标识、主机、容器、账号池、粘滞策略的内容，都应该留在本地私有文档中。
