import type { Bootstrap, Session, SessionDetail } from "./types";
import { previewBootstrap, previewDetails } from "./preview";
import { newRequestId } from "./request-id";

export const isPreview =
  new URLSearchParams(location.search).get("preview") === "1";
let csrfToken = "";
let uncertainMutation: { fingerprint: string; requestId: string } | null = null;
class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
  ) {
    super(message);
  }
}
const samples = structuredClone(previewDetails);
const sampleBootstrap = structuredClone(previewBootstrap);

export async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  refreshed = false,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    signal,
    headers:
      body === undefined
        ? {}
        : { "Content-Type": "application/json", "X-MMS-CSRF": csrfToken },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch((error) => {
    if (signal?.aborted) throw error;
    throw new Error("无法连接 MMS 本地服务。恢复连接后，可再次发送同一请求。");
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("本地服务未返回有效数据，请检查 MMS Pilot 服务。");
  }
  if (
    !response.ok &&
    payload.error?.code === "INVALID_CSRF" &&
    body !== undefined &&
    !refreshed
  ) {
    await bootstrap(signal);
    return request<T>(path, body, signal, true);
  }
  if (!response.ok)
    throw new ApiError(
      payload.error?.message || "操作未完成，请重试。",
      payload.error?.code || "UNKNOWN",
    );
  return payload as T;
}

export async function bootstrap(signal?: AbortSignal): Promise<Bootstrap> {
  const data = isPreview
    ? structuredClone(sampleBootstrap)
    : await request<Bootstrap>("/bootstrap", undefined, signal);
  if (
    !data ||
    data.version !== "1" ||
    ![
      "models",
      "services",
      "presets",
      "workspaces",
      "sessions",
      "diagnostics",
    ].every((key) => Array.isArray(data[key as keyof Bootstrap])) ||
    !data.capabilities ||
    typeof data.csrfToken !== "string"
  ) {
    throw new Error("本地服务的数据格式不兼容，请检查 Web 与服务版本。");
  }
  csrfToken = data.csrfToken;
  return data;
}
export async function listSessions(signal?: AbortSignal): Promise<Session[]> {
  if (isPreview) return structuredClone(sampleBootstrap.sessions);
  return (
    await request<{ sessions: Session[] }>("/sessions", undefined, signal)
  ).sessions;
}
export async function getSession(
  id: string,
  signal?: AbortSignal,
): Promise<SessionDetail> {
  if (!isPreview)
    return request(`/sessions/${encodeURIComponent(id)}`, undefined, signal);
  if (!samples[id]) throw new Error("找不到这条预览会话。");
  return structuredClone(samples[id]);
}
export async function mutate<T>(
  path: string,
  payload: Record<string, unknown>,
): Promise<T> {
  if (!isPreview) {
    const fingerprint = JSON.stringify([path, payload]);
    if (uncertainMutation?.fingerprint !== fingerprint)
      uncertainMutation = { fingerprint, requestId: newRequestId() };
    try {
      const result = await request<T>(path, {
        ...payload,
        requestId: uncertainMutation.requestId,
      });
      uncertainMutation = null;
      return result;
    } catch (error) {
      // Keep the same id after an uncertain transport failure, preventing a
      // repeated click from launching the same task twice after reconnect.
      if (
        error instanceof ApiError &&
        !["REQUEST_PENDING", "RPC_TIMEOUT"].includes(error.code)
      )
        uncertainMutation = null;
      throw error;
    }
  }
  // Preview is deliberately local. It never calls a model or makes HTTP writes.
  const time = new Date().toISOString();
  if (path === "/sessions") {
    const preset = sampleBootstrap.presets.find(
      (item) => item.id === payload.presetId,
    );
    const model = sampleBootstrap.models.find(
      (item) => item.id === preset?.modelId,
    );
    if (!preset || !model) throw new Error("请选择有效的启动组合。");
    const id = newRequestId();
    samples[id] = {
      session: {
        id,
        title: String(payload.title),
        workspaceId: String(payload.workspaceId),
        harness: preset.harness,
        modelName: model.name,
        providerName: model.providerName,
        channel: preset.channel,
        state: "idle",
        updatedAt: time,
        owner: "web",
        capabilities: { send: true, stop: false, approve: false },
      },
      events: [],
      artifacts: [],
    };
    appendPreviewMessage(samples[id], String(payload.prompt), time);
    sampleBootstrap.sessions.unshift(samples[id].session);
    return structuredClone(samples[id]) as T;
  }
  const [, , id, action] = path.split("/");
  const detail = samples[id];
  if (!detail) throw new Error("找不到这条预览会话。");
  if (action === "messages")
    appendPreviewMessage(detail, String(payload.text), time);
  else if (action === "approvals") {
    const approval = detail.events.find(
      (item) => item.approvalId === path.split("/")[4],
    );
    if (!approval || approval.decision) throw new Error("该确认已处理。");
    approval.decision = payload.decision as "allow" | "deny";
    detail.session.state = "idle";
    detail.session.capabilities.approve = false;
    detail.events.push({
      id: newRequestId(),
      sequence: detail.events.length + 1,
      kind: "notice",
      text: "已记录预览选择，未执行文件写入。",
      createdAt: time,
    });
  } else throw new Error("此操作在预览中不可用。");
  return structuredClone(detail) as T;
}
function appendPreviewMessage(
  detail: SessionDetail,
  text: string,
  time: string,
) {
  detail.events.push({
    id: newRequestId(),
    sequence: detail.events.length + 1,
    kind: "user",
    text,
    createdAt: time,
  });
  detail.events.push({
    id: newRequestId(),
    sequence: detail.events.length + 1,
    kind: "notice",
    text: "预览消息已保留在当前页面。连接 MMS 本地服务后，才能实际运行这个任务。",
    createdAt: time,
  });
}
