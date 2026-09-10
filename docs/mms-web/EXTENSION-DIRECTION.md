# MMF Web：配置、过程与扩展方向

> v4 更新：Pi 会话内模型/通道切换与过程折叠现已实现。本文保留原调研背景；最新能力与下一步以 [NEXT-PHASE.md](NEXT-PHASE.md) 为准。


2026-09-08。依据当前 Web/Pi 源码、DeepSeek Harness 官方源码 c389f96bf3a9b6807cb71ed6bdad5849be0df6d8、本地 Runtimia d4a712abf3880dfbd3daeac5daac1bd4bfb39b6f。以下区分已实现、参考与后续方案。

## 产品判断

常用通道接入、模型拉取、模型/通道预设和默认 effort 应进入同一个 Web。保留 Config Web 作为高级配置入口，最终共用 MMF 的配置读取、变更预览、校验和应用逻辑；不能长期维护两套真实模型配置。

目前 Web 连接既有 MMF 配置时只读。收藏、通道备注、Web 首选和 effort 偏好保存在浏览器，修改前清楚说明作用范围。当前独立 Web 配置已有 preview/apply，但尚不是完整 MMF 配置链的替代。接入真实写入前必须评估既有 route、priority、protocol、隔离环境以及 human-only 授权边界。

推荐设置分层：

| 入口 | 放什么 | 原因 |
| --- | --- | --- |
| 输入框的本次任务 | 模型、明确的通道、effort、执行/只读规划 | 频繁变动，不能藏进全局配置 |
| 设置 → 模型与通道 | 连接服务、拉取模型、显示/隐藏、收藏、默认值、检测连接 | 用户以服务和模型理解，不要求认识内部配置字段 |
| 设置 → 能力（后续） | Skills、工具与扩展的来源、开关、作用范围 | 与任务内容区分，方便诊断缺少的能力 |
| 高级配置 | 协议映射、路由优先级、headers、细粒度运行参数 | 保留现有能力，但不成为第一次使用的门槛 |

新用户流程建议：粘贴服务地址/API Key → 预览模型列表与拉取错误 → 选择常用模型和默认值 → 一次可解释的连接检测 → 保存。拉取/检测是明确的操作；不暗中扫描全部 provider，不静默跨通道 fallback。执行中会话固定自己的模型和通道，新默认只影响后续启动。

## DeepSeek：可以借，但不是直接装插件

官方架构将 model adapter、工具、session、agent loop 组织为 Cordis plugins。Web 有插件设置与只读 inventory；配置卡片由注册的 settings slot 提供。其 Web profile 支持配置 patch 的运行时处理，不代表任何第三方插件在任意版本都可无风险热加载。

我们当前运行的是 MMF 启动的 Pi，不能把 DeepSeek plugin 名字填入后就当作可用。需要适配能力发现、权限/配置范围、生命周期及 Web 展示。优先复用 Pi 已有 Skills/extensions 与事件，避免再造一个 agent loop。

用户截图的上下文注入、Skill、Think、Tool call 是不同类型的过程条目。当前 Web 已显示 Thinking、工具参数/输出、显式选择的 Skills、附件/引用与交互问题；尚未完整记录自动加载上下文、plugin 装载/变更、所有子任务轨迹。不能把模型文本推测当作真实加载事件。

如果 Customize 指通过自然语言为界面增加组件（截图中的 cordis-plugin-development/cordis_inspect），这是开发并挂载插件的能力，并非思考强度。当前 MMF Web 尚未提供。未来可以提供“描述改动 → 隔离预览 → 应用/撤回”，不应直接允许任意生成代码修改主界面。

来源：
- https://github.com/deepseek-ai/deepseek-harness/blob/c389f96bf3a9b6807cb71ed6bdad5849be0df6d8/docs/architecture.md
- https://github.com/deepseek-ai/deepseek-harness/blob/c389f96bf3a9b6807cb71ed6bdad5849be0df6d8/packages/client/ui-settings-plugins/src/client/ConfigurablePluginsTab.tsx
- https://github.com/deepseek-ai/deepseek-harness/blob/c389f96bf3a9b6807cb71ed6bdad5849be0df6d8/packages/client/ui-settings-plugin-inventory/src/client/PluginInventorySettingsTab.tsx
- https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/config/agent-presets/cordis/skills/cordis-plugin-development/SKILL.md

## Runtimia：优先取这三点

已检查本地源文件，不代表已移植：

1. 引导式 setup 与上下文持续性：`packages/views/agents/create/builder-setup-panel.tsx`、`ai-builder-session-page.tsx`。借鉴“先选运行位置、再完成设置”的交互及草稿持续性，映射成 MMF 的服务/模型/工作空间设置。
2. 可解释的执行过程：`packages/views/common/task-transcript/run-timeline.tsx`。模型与工具分段、耗时、定位和缩放。MMF 后续需真实时间戳，再展示“时间花在哪”，不要估造耗时。
3. Skills 来源和冲突预览：`packages/views/skills/components/runtime-local-skill-import-panel.tsx`。帮助普通用户理解共享/项目 Skills、同名覆盖、导入进度和失败恢复。

团队权限、企业看板、多设备编排暂不进入核心对话界面。此次未复制 Runtimia 代码，也未改动其仓库。

## 建议顺序

1. 当前 Web 的统一任务设置、设置页和交互质量。
2. MMF 配置链贯通：通道接入 → 拉取模型 → 检测 → 常用预设；完整回读和隔离测试。
3. 明确的能力管理、上下文/Skills/工具/子任务过程与成果预览。
4. 可分享的无密钥配置配方/能力组合与引导导入。
5. 最后评估 Customize 和其他 harness 适配。以用户能完成任务为判断，不以扩展数量为目标。
