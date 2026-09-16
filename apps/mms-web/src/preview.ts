import type { Bootstrap, SessionDetail, SessionEvent, UpdateHistoryItem } from "./types";

const time = "2026-09-08T09:00:00Z";
// Preview turns carry plausible clocks so the timestamp and reply duration
// read the same way they do in a live session.
const at = (seconds: number) =>
  new Date(Date.parse(time) + seconds * 1000).toISOString();
const event = (
  id: string,
  kind: SessionEvent["kind"],
  text: string,
  extra = {},
): SessionEvent => ({
  id,
  sequence: Number(id),
  kind,
  text,
  createdAt: time,
  ...extra,
});
export const previewDetails: Record<string, SessionDetail> = {
  "sample-plan": {
    session: {
      id: "sample-plan",
      title: "梳理新用户的第一次使用",
      workspaceId: "product",
      harness: "pi",
      modelName: "Kimi K2.5",
      providerName: "我的模型服务",
      channel: "默认通道",
      state: "waiting",
      updatedAt: time,
      owner: "web",
      capabilities: { send: true, stop: false, approve: true },
      summary: "已有流程草案，等待确认写入文档。",
    },
    events: [
      event(
        "1",
        "user",
        "帮我梳理一下新用户第一次使用的流程。希望产品同事不用看文档，就能开始自己的第一个任务。",
      ),
      event(
        "2",
        "assistant",
        "我先看了项目里现有的使用说明和配置流程。最需要减少的，是第一次启动前连续选择工具、服务商、模型和通道的过程。",
        { createdAt: at(19), updatedAt: at(34) },
      ),
      event(
        "3",
        "tool",
        "README.md\ndocs/getting-started.md\ndocs/MODEL_CONFIG_CONTRACT.md",
        { title: "阅读了 3 份项目文档", status: "done", createdAt: at(36), updatedAt: at(88) },
      ),
      event(
        "4",
        "assistant",
        "建议把第一次使用收敛成三个步骤：\n\n1. **连接自己的模型服务**，只填写必要信息。\n2. **选择工作文件夹**，明确 AI 在哪里工作。\n3. **说出想做的事**，复用一套可用的启动组合。\n\n流程草案已经放在右侧。高级设置保留在运行详情中，需要时再展开。",
        { createdAt: at(90), updatedAt: at(133) },
      ),
      event(
        "5",
        "approval",
        "将首次使用流程保存到 docs/first-run.md，便于团队一起评审。",
        { title: "写入一份项目文档", approvalId: "sample-write", createdAt: at(135) },
      ),
    ],
    artifacts: [
      {
        id: "first-run",
        name: "首次使用流程.md",
        kind: "markdown",
        path: "docs/first-run.md",
        sha256: "", revision: 0, versionCount: 0, status: "current", source: "demo",
        demoContent:
          "# 从想法到第一个任务\n\n让第一次使用，在一个页面里完成。\n\n## 01 · 连接模型服务\n\n选择已有服务，或填入自己的 API Key。已知服务自动带出地址，只显示常用模型。\n\n## 02 · 选择工作文件夹\n\n告诉 AI 在哪里工作。解释将要访问的范围，并记住最近使用的文件夹。\n\n## 03 · 开始工作\n\n用自己的话描述任务。第一次使用推荐组合，之后记住上次的选择。\n\n---\n\n### 验收方式\n\n找一位从未使用终端的同事，观察是否能独立完成首次任务，并打开生成的文件。\n\n> 这是用于界面评审的示例文档，没有写入项目。",
      },
    ],
  },
  "sample-notes": {
    session: {
      id: "sample-notes",
      title: "整理这一周的产品反馈",
      workspaceId: "product",
      harness: "pi",
      modelName: "DeepSeek V3.2",
      providerName: "我的模型服务",
      channel: "默认通道",
      state: "completed",
      updatedAt: time,
      owner: "web",
      capabilities: { send: true, stop: false, approve: false },
      summary: "反馈已分成上手、体验和稳定性三组。",
    },
    events: [
      event("1", "user", "将产品反馈按主题整理，保留原始问题。"),
      event(
        "2",
        "assistant",
        "已按上手、体验和稳定性整理成可讨论的清单。每个问题都保留了原始描述，便于团队核对。\n\n你可以在右侧阅读示例结果。",
        { createdAt: at(14), updatedAt: at(47) },
      ),
    ],
    artifacts: [
      {
        id: "feedback",
        name: "产品反馈.md",
        kind: "markdown",
        path: "产品反馈.md", sha256: "", revision: 0, versionCount: 0, status: "current", source: "demo",
        demoContent:
          "# 本周产品反馈\n\n## 上手\n\n- 希望记住上次使用的模型组合。\n- 第一次设置不知道哪些字段必须填写。\n\n## 体验\n\n- 多个任务一起运行时，希望先看到需要确认的任务。\n\n## 稳定性\n\n- 连接失败时，需要知道下一步如何恢复。\n\n> 界面预览数据。",
      },
    ],
  },
  "sample-code": {
    session: {
      id: "sample-code",
      title: "检查登录页的表单状态",
      workspaceId: "website",
      harness: "codex",
      modelName: "GPT-5",
      providerName: "示例服务",
      channel: "默认通道",
      state: "idle",
      updatedAt: time,
      owner: "external",
      capabilities: { send: false, stop: false, approve: false },
      summary: "历史会话示例，只读展示。",
    },
    events: [
      event(
        "1",
        "notice",
        "这是外部会话的只读展示示例。接管与恢复能力尚未接入。",
      ),
    ],
    artifacts: [],
  },
};
export const previewBootstrap: Bootstrap = {
  version: "1",
  mode: "preview",
  csrfToken: "",
  platform: {
    os: "darwin",
    shell: "/bin/zsh",
    home: "/Users/preview",
    configRoot: "/Users/preview/.config/mms-next",
    stateRoot: "/Users/preview/.local/share/mms",
    tempRoot: "/tmp",
    pathStyle: "posix",
    processControl: "macOS launchd / loopback process",
    filePicker: "native",
  },
  browser: [
    { backend: "chrome", supported: true, loggedIn: true },
    { backend: "edge", supported: true, loggedIn: false, reason: "未检测到已登录的 Edge 账号" },
    { backend: "chromium", supported: false, loggedIn: "unknown", reason: "未安装 Chromium 独立运行时" },
  ],
  capabilities: { catalogRead: true, configure: false, launch: true, discoverModels: true, modelSettings: true },
  workspaces: [
    { id: "product", name: "产品工作室", path: "~/Projects/product-studio" },
    { id: "website", name: "官网", path: "~/Projects/website" },
  ],
  models: [
    {
      id: "personal/kimi",
      name: "Kimi K2.5",
      family: "Kimi",
      providerId: "personal",
      providerName: "我的模型服务",
      harnesses: ["pi"],
      contextLabel: "256K",
      available: true,
    },
    {
      id: "personal/deepseek",
      name: "DeepSeek V3.2",
      family: "DeepSeek",
      providerId: "personal",
      providerName: "我的模型服务",
      harnesses: ["pi"],
      contextLabel: "128K",
      available: true,
    },
    {
      id: "personal/gpt",
      name: "GPT-5",
      family: "OpenAI",
      providerId: "personal",
      providerName: "我的模型服务",
      harnesses: ["codex"],
      contextLabel: "400K",
      available: false,
      reason: "Codex Web adapter 尚未接入",
    },
    {
      id: "personal/sonnet",
      name: "Claude Sonnet 4",
      family: "Anthropic",
      providerId: "personal",
      providerName: "我的模型服务",
      harnesses: ["claude"],
      contextLabel: "200K",
      available: false,
      reason: "Claude Web adapter 尚未接入",
    },
  ],
  services: [
    {
      id: "personal",
      name: "我的模型服务",
      kind: "自定义服务",
      status: "configured",
      modelCount: 4,
      detail: "示例配置，未检测真实连接",
    },
  ],
  presets: [
    {
      id: "daily",
      name: "日常工作",
      description: "Pi · Kimi K2.5",
      harness: "pi",
      modelId: "personal/kimi",
      providerId: "personal",
      channel: "默认通道",
      available: true,
    },
    {
      id: "quick",
      name: "快速处理",
      description: "Pi · DeepSeek V3.2",
      harness: "pi",
      modelId: "personal/deepseek",
      providerId: "personal",
      channel: "默认通道",
      available: true,
    },
  ],
  sessions: Object.values(previewDetails).map((detail) => detail.session),
  diagnostics: [],
};

export const previewUpdateHistory: UpdateHistoryItem[] = [
  {
    version: "4.16.0",
    notes: "# v4.16.0 · 运行环境诊断与外观微调\n\n- 设置面板新增「运行环境」Tab，整合系统与浏览器能力探测。\n- 优化深色模式对比度，提供更清晰的状态指示。\n- 统一全站设置与通道配置边距，优化滚动交互体验。",
    upgradeNotice: "升级后如果遇到浏览器扩展连接异常，请在「运行环境」Tab 重新检查调试端口状态。",
    publishedAt: "2026-09-12T12:00:00Z",
  },
  {
    version: "4.15.2",
    notes: "# v4.15.2 · 稳定性修复\n\n- 优化 Pi 会话长轮次恢复逻辑。\n- 完善本地文件拖拽定位准确率。",
    publishedAt: "2026-09-10T08:30:00Z",
  },
  {
    version: "4.15.0",
    notes: "# v4.15.0 · 多通道管理与 Effort 档位支持\n\n- 通道模型支持自定义 Effort 预设。\n- 增强安全更新事务回滚保障机制。",
    publishedAt: "2026-09-05T14:00:00Z",
  },
];
