export type Harness = "pi" | "codex" | "claude" | "opencode" | "gemini" | "agy";
export type SessionState =
  | "running"
  | "waiting"
  | "idle"
  | "completed"
  | "stopped"
  | "error";
export interface Workspace {
  id: string;
  name: string;
  path: string;
  /** A folder the sidebar shows because sessions ran there, not one the user
   *  registered. It can be read and copied, but not renamed or removed. */
  unregistered?: boolean;
}
export interface Model {
  id: string;
  name: string;
  family: string;
  providerId: string;
  providerName: string;
  harnesses: Harness[];
  contextLabel?: string;
  available: boolean;
  reason?: string;
}
export interface Service {
  id: string;
  name: string;
  kind: string;
  status: "configured" | "needs_key" | "error";
  modelCount: number;
  detail: string;
}
export interface Preset {
  id: string;
  name: string;
  description: string;
  harness: Harness;
  modelId: string;
  providerId: string;
  channel: string;
  available: boolean;
  reason?: string;
}
export interface Session {
  presetId?: string;
  id: string;
  title: string;
  workspaceId: string;
  harness: Harness;
  modelName: string;
  providerName: string;
  channel: string;
  state: SessionState;
  activity?: {
    phase:
      | "running"
      | "thinking"
      | "responding"
      | "tool"
      | "compacting"
      | "retrying"
      | "waiting"
      | "error"
      | "stopped";
    eventId?: string;
    toolName?: string;
    method?: string;
    since?: string;
    turnStartedAt?: string;
  } | null;
  updatedAt: string;
  owner: "web" | "cli" | "glint" | "external";
  capabilities: { send: boolean; stop: boolean; approve: boolean };
  summary?: string;
  archived?: boolean;
  cwd?: string;
  forkedFrom?: string;
}
export interface SessionEvent {
  modelName?: string;
  id: string;
  sequence: number;
  kind: "user" | "assistant" | "tool" | "approval" | "notice";
  text: string;
  title?: string;
  status?: "running" | "done" | "error" | "queued" | "cancelled";
  approvalId?: string;
  decision?: "allow" | "deny";
  method?: "confirm" | "select" | "input" | "editor";
  options?: string[];
  placeholder?: string;
  prefill?: string;
  answer?: string;
  arguments?: Record<string, unknown>;
  createdAt: string;
  updatedAt?: string;
  thinking?: string;
  skills?: { id: string; name: string; source: string }[];
  nativeEntryId?: string;
  nativeTimestamp?: number;
  attachments?: Attachment[];
  references?: string[];
  fileSelections?: { path: string; revision: number; quote?: string; region?: ImageRegion }[];
  contextUsage?: import("./ContextUsage").ContextRecord;
  usage?: Record<string, unknown>;
}
export interface Artifact {
  id: string;
  name: string;
  kind: "markdown" | "text" | "csv" | "html" | "image";
  path: string;
  sha256: string;
  revision: number;
  versionCount: number;
  status: "current" | "changed" | "missing" | "unavailable";
  source: string;
  demoContent?: string;
}
export interface ImageRegion { x: number; y: number; width: number; height: number }
export interface FileSelection {
  artifactId: string;
  path: string;
  revision: number;
  sha256: string;
  quote?: string;
  region?: ImageRegion;
}
export interface SessionDetail {
  session: Session;
  events: SessionEvent[];
  artifacts: Artifact[];
  artifactNotice?: string;
  runtime?: Runtime;
}
export interface Attachment {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  source?: "local";
  localPath?: string;
}
export interface Runtime {
  planning?: boolean;
  alive?: boolean;
  cached?: boolean;
  stale?: boolean;
  cwd?: string;
  thinkingLevel?: string;
  supportedThinkingLevels?: string[];
  autoCompactionEnabled?: boolean;
  autoRetryEnabled?: boolean;
  isCompacting?: boolean;
  pendingMessageCount?: number;
  queue?: string[];
  model?: {
    id?: string;
    provider?: string;
    api?: string;
    reasoning?: boolean;
    input?: string[];
    contextWindow?: number;
    maxTokens?: number;
  };
  stats?: {
    tokens?: {
      input: number;
      output: number;
      cacheRead: number;
      cacheWrite: number;
      total: number;
    };
    cost?: number;
    toolCalls?: number;
    contextUsage?: {
      tokens: number | null;
      percent: number | null;
      contextWindow: number;
    };
  };
}
export interface Bootstrap {
  version: "1";
  appVersion?: string;
  mode: "live" | "preview";
  csrfToken: string;
  capabilities: {
    catalogRead: boolean;
    configure: boolean;
    modelSettings?: boolean;
    launch: boolean;
    discoverModels?: boolean;
  };
  workspaces: Workspace[];
  models: Model[];
  services: Service[];
  presets: Preset[];
  sessions: Session[];
  diagnostics: { code: string; message: string }[];
}
export interface ConfigPreview {
  revision: string;
  previewId: string;
  changes: { label: string; before: string; after: string }[];
  warnings: string[];
}
export type Page = "new" | "models" | "bots" | "session";

// Bot 结果送达（T3）：页面通知与 webhook 共用同一事件形状。
export type BotNotificationType =
  | "task.completed"
  | "task.failed"
  | "task.waiting"
  | "task.retrying";
export interface BotNotification {
  id: string;
  at: string;
  type: BotNotificationType;
  botId: string;
  botName: string;
  taskId: string;
  title: string;
  summary: string;
  waitReason?: "approval" | "input" | null;
  link: string;
}
export interface BotNotifyWebhook {
  url: string;
  events: BotNotificationType[];
  secret: string;
}
export interface BotNotifyConfig {
  webhooks: BotNotifyWebhook[];
  events: BotNotificationType[];
  timeoutSeconds?: number;
}

/** Coordinator plan attached to a Bot task (T2). */
export type BotPlanStepStatus = "pending" | "dispatched" | "done" | "failed" | "blocked";
export interface BotPlanStep {
  id: string;
  kind: "execute" | "delegate" | string;
  botId: string;
  goal?: string;
  dependsOn?: string[];
  presetId?: string | null;
  status: BotPlanStepStatus | string;
  taskId?: string | null;
  error?: string;
}
export type BotPlanStatus = "proposed" | "auto" | "approved" | "rejected";
export interface BotTaskPlan {
  version?: number;
  mode: "direct" | "delegate";
  reason?: string;
  steps?: BotPlanStep[];
  candidates?: Array<{ id: string; name: string; description?: string }>;
  merge?: string;
  source?: "model" | "keywords" | "fallback" | "off" | "user";
  status?: BotPlanStatus;
  modelDecision?: boolean;
}
