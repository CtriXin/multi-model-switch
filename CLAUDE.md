# CLAUDE.md

这份文件只针对 `Claude` 生效，用来把它在本仓库内的默认行为收紧。

## 默认模式

在这个仓库里，`Claude` 默认是保守执行模式，不是默认激进实现模式。

- 优先诊断、解释、补文档、补清单、补测试
- 不要因为“看起来应该这样”就直接改核心启动逻辑
- 只在用户明确要求改代码，且范围清楚时，才改代码
- 每完成一个可独立交付的迭代，先问用户是否需要 `commit`

## 禁止直接改动的区域

没有用户明确授权时，`Claude` 不要直接修改这些文件：

- `mms_core.py`
- `mms_launchers.py`
- `mms_tui.py`
- `mms_bridge.py`
- `mms_account_state.py`
- `mms_session.py`
- `mms_adapter_registry.py`
- `mms`
- `ccs`

如果问题落在这些文件，默认先输出：

1. 现象
2. 可能影响面
3. 最小修复点
4. 需要用户确认的范围

然后再继续。

## 对 Claude 的硬性规则

- 不要私自改变默认模型、默认来源、默认 bridge、默认 fallback
- 不要私自改变 `model_info`、`runtime`、`provider`、`account` 的字段语义
- 不要把展示层状态和执行层参数混用
- 不要为了“统一风格”重写 TUI 选择返回结构
- 不要为了“更智能”加入隐式自动切换，除非用户明确要求
- 不要覆盖未提交改动里已经存在的核心链路修改
- 不要在一个未确认是否提交的迭代上继续叠加下一轮实质性改动

## 用户请求的解释规则

以下说法都不等于“可以直接改核心逻辑”：

- “看下这个问题”
- “怎么又坏了”
- “帮我定位”
- “帮我约束一下”
- “先分析一下”

只有当用户明确要求“改代码 / 修复 / 落地实现”，并且范围足够清楚时，才进入代码修改。

## 必须先确认的情况

遇到下面任一情况，`Claude` 应先停下来，不要继续扩大改动：

- 需要改上面列出的受保护文件
- 需要改变启动默认行为
- 需要改变 TUI 选择结果结构
- 需要改变 provider/account 优先级
- 需要改变 bridge 的路由、模型覆盖、URL 拼接或鉴权方式
- 发现修复一个 CLI 会波及另一个 CLI

## 允许做的低风险事项

下面这些在未额外确认时通常是允许的：

- 新增或修改文档
- 补充回归清单
- 增加注释
- 增加不改变行为的日志
- 增加测试
- 修正纯文案或纯展示问题

## 如果必须改核心文件

当用户明确要求修改核心文件时，`Claude` 仍需遵守：

- 只做最小补丁
- 不顺手做重构
- 不顺手改 unrelated 逻辑
- 改完后说明选择值如何从 `TUI -> core -> launcher -> bridge` 传递
- 至少做语法检查和一条与问题相关的链路验证
- 完成该迭代后先询问用户是否要提交当前改动，再进入下一轮

## 开源准备：必须 gitignore 的内容

本仓库计划开源，以下目录/文件**绝不能**进入 git 历史：

| 路径 | 原因 |
|------|------|
| `.ai/cache/` | AI 工具运行缓存，含临时上下文 |
| `.sparkring/` | Sparkring 本地配置/缓存 |
| `.worktrees/` | Git worktree 临时工作区 |
| `.claude/` | Claude Code 项目配置（含 memory） |
| `findings.md` / `progress.md` / `task_plan.md` | 本地 planning / handoff 文件，不应作为公开仓库内容 |
| `DESIGN_V3_SPEC.md` | 本地 UI 设计草案，不作为开源仓库事实来源 |
| `apps/runtime-api/gateway-config.json` | 网关配置，可能含 API 端点 |
| `apps/runtime-api/gateway-state.db` | 运行时状态数据库 |
| `apps/*/.ai/` | app 级 AI 本地计划、release note 与运行上下文 |
| `apps/*/findings.md` / `progress.md` / `task_plan.md` | app 级本地规划文件，不属于产品源码或公开文档 |
| `apps/web-v2/GEMINI.md` | 本地 AI 协作上下文，不应作为公开发布内容 |
| `apps/web-v2/*-worktree/` | 本地临时 worktree，可能包含未整理改动或重复仓库副本 |
| `apps/web-v2/src-tauri/*.provisionprofile` | Apple 签名证书 |
| `apps/web-v2/ios/build/` | Xcode 构建产物 |
| `apps/web-v2/src-tauri/target/` | Rust 构建产物 |

开源前还需额外检查：
- 所有 `.env` / API Key 引用不能硬编码
- `docs/` 内文档不含内部链接或私有服务地址
- commit 历史中无泄漏的 key（需要时用 `git filter-repo` 清理）

## 一句话

在这个仓库里，`Claude` 先当审计员，再当实现者。
