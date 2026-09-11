import type { SideQuestion } from "./side-questions";

export type Harness = "pi" | "codex" | "claude" | "opencode" | "gemini" | "agy";
/** How a message reaches the session. `direct` starts a turn, `followUp` waits
 *  for the current one to settle, `steer` lands in it. See message-control.ts
 *  for the service contract behind these. */
export type SendMode = "direct" | "followUp" | "steer";
/** One message the session has accepted but not yet delivered. */
export interface PendingMessage {
  id: string;
  text: string;
  mode: "followUp" | "steer";
  createdAt?: string;
}
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
  capabilities: {
    send: boolean;
    stop: boolean;
    approve: boolean;
    /** The service accepts `mode: "steer"` on a message. Absent means every
     *  message queues as a follow-up, so the page offers no steer. */
    steer?: boolean;
    /** The service serves `/sessions/{id}/queue`, so single queued messages can
     *  be removed or reordered. Absent leaves only clearing the whole queue. */
    queueControl?: boolean;
  };
  summary?: string;
  archived?: boolean;
  cwd?: string;
  forkedFrom?: string;
}
export interface SessionEvent {
  modelName?: string;
  /** How this user message was sent. Absent on messages recorded before the
   *  service reported delivery modes. */
  mode?: SendMode;
  /** On an assistant event: the user messages the service says steered it. */
  steeredBy?: string[];
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
  /** `/btw` records. They live beside the transcript, never inside `events`. */
  sideQuestions?: SideQuestion[];
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
  /** Queue text only, in delivery order, with no ids: readable, not editable. */
  queue?: string[];
  /** The same queue with stable ids and per-message mode, when the service
   *  reports it. Preferred over `queue` whenever present. */
  pending?: PendingMessage[];
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
    /** `/btw` is answerable at all. State answers need no model. */
    sideQuestions?: boolean;
    /** A read-only sidecar model is available, so questions that need
     *  judgement can be answered too. Without it those fail closed. */
    sidecarCompletion?: boolean;
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
export type Page = "new" | "models" | "session";
