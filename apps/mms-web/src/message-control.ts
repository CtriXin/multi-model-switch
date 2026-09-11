/** T2 message control: how a message reaches a running session, what is still
 *  queued, and which answer a steer landed in.
 *
 *  ## The contract this file consumes
 *
 *  Pi 0.85.1 (`docs/rpc.md`) offers three delivery primitives and nothing else:
 *  `follow_up` (delivered once the run settles), `steer` (delivered after the
 *  current assistant turn finishes its tool calls, before the next LLM call)
 *  and `clear_queue` (empties the whole queue and returns the texts). There is
 *  no native per-item delete and no native reorder: both are "clear, then
 *  re-enqueue what you keep, in order", which only the server can do.
 *
 *  So the page can only offer what the local service exposes:
 *
 *    POST /sessions/{id}/messages   { ...,  mode: "direct" | "followUp" | "steer" }
 *        `mode` is always sent. A service that ignores it still behaves the way
 *        the page describes, because "steer" is offered only under the
 *        capability below.
 *    POST /sessions/{id}/queue      { action: "remove", id }
 *                                   { action: "move",   id, toIndex }
 *        Returns the session detail, like every other mutation.
 *
 *    session.capabilities.steer         the service accepts mode: "steer"
 *    session.capabilities.queueControl  the service serves /queue
 *    runtime.pending                    queued messages with stable ids and mode
 *
 *  Every one of those is optional and absent means "not supported". Until the
 *  service grows them the page keeps the honest subset — queue reading, whole
 *  queue clearing, delivery state — and never shows a control that would
 *  silently do something else. Fake buttons are the documented anti-pattern in
 *  `docs/AGENT_GUARDRAILS.md`.
 */
import type { PendingMessage, Runtime, SendMode, SessionEvent } from "./types";

export interface SendModeOption {
  mode: SendMode;
  label: string;
  /** What the user is promising the session, in delivery terms. */
  description: string;
}

const DIRECT: SendModeOption = {
  mode: "direct",
  label: "发送",
  description: "会话空闲，这条消息直接开始新一轮。",
};
const FOLLOW_UP: SendModeOption = {
  mode: "followUp",
  label: "排队补充",
  description: "等当前这一轮完全结束后再送达，不改变正在进行的工作。",
};
const STEER: SendModeOption = {
  mode: "steer",
  label: "立即引导",
  description:
    "当前这批工具调用跑完、下一次模型请求之前送达。它不会中途截断已经生成的内容；要真正结束这一轮请用停止。",
};

/** The delivery choices this session can actually honour right now. */
export function availableSendModes(
  running: boolean,
  capabilities?: { steer?: boolean },
): SendModeOption[] {
  if (!running) return [DIRECT];
  return capabilities?.steer ? [FOLLOW_UP, STEER] : [FOLLOW_UP];
}

/** Keeps a remembered choice legal: a session that stopped running sends
 *  directly, and a steer the service cannot deliver falls back to the queue. */
export function resolveSendMode(
  chosen: SendMode | undefined,
  running: boolean,
  capabilities?: { steer?: boolean },
): SendMode {
  const options = availableSendModes(running, capabilities);
  return options.some((option) => option.mode === chosen)
    ? (chosen as SendMode)
    : options[0].mode;
}

export interface QueueView {
  items: PendingMessage[];
  /** Whether single items can be removed or reordered, rather than only the
   *  whole queue cleared. */
  manageable: boolean;
  /** Queued messages the service counted but did not list. */
  unlisted: number;
  /** Why management is unavailable, when it is. Empty when it is available. */
  note: string;
}

const LEGACY_NOTE = "当前本地服务只报告了队列文字，没有逐条编号，只能整队清空。";
const UNMANAGEABLE_NOTE = "当前本地服务不支持逐条删除或调整顺序，只能整队清空。";

/** Reads the queue out of whatever shape the service reports. */
export function readQueue(
  runtime: Runtime | undefined,
  capabilities?: { queueControl?: boolean },
): QueueView {
  const pending = runtime?.pending;
  const counted = runtime?.pendingMessageCount || 0;
  if (Array.isArray(pending)) {
    const items = pending.flatMap((item) =>
      item && typeof item.id === "string" && typeof item.text === "string"
        ? [
            {
              id: item.id,
              text: item.text,
              mode: item.mode === "steer" ? ("steer" as const) : ("followUp" as const),
              createdAt: item.createdAt,
            },
          ]
        : [],
    );
    const manageable = !!capabilities?.queueControl && items.length > 0;
    return {
      items,
      manageable,
      unlisted: Math.max(0, counted - items.length),
      note: manageable || !items.length ? "" : UNMANAGEABLE_NOTE,
    };
  }
  const texts = Array.isArray(runtime?.queue) ? runtime.queue : [];
  return {
    items: texts.map((text, index) => ({
      id: `legacy:${index}`,
      text: String(text),
      mode: "followUp" as const,
    })),
    manageable: false,
    unlisted: Math.max(0, counted - texts.length),
    note: texts.length ? LEGACY_NOTE : "",
  };
}

/** Where an item lands after one step, or null when it cannot move that way. */
export function moveTarget(
  items: PendingMessage[],
  id: string,
  direction: -1 | 1,
): { id: string; toIndex: number } | null {
  const from = items.findIndex((item) => item.id === id);
  if (from < 0) return null;
  const toIndex = from + direction;
  if (toIndex < 0 || toIndex >= items.length) return null;
  return { id, toIndex };
}

/** What happened to a message the user already sent. */
export function deliveryLabel(event: SessionEvent): string {
  if (event.status === "cancelled") return "已取消，未执行";
  if (event.status === "error") return "发送失败，未执行";
  if (event.contextUsage?.state === "uncertain") return "发送结果待确认";
  if (event.status !== "queued") return "";
  if (event.mode === "steer")
    return "引导已排队 · 当前这批工具调用结束后送达";
  if (event.mode === "followUp") return "排队中 · 本轮结束后送达";
  return "排队中，尚未执行";
}

export interface SteerLink {
  /** The answer the steer reached. */
  assistantId: string;
  /** The user messages that steered it. */
  steerIds: string[];
  /** True when the service said so, false when the page inferred it from the
   *  timing of the events it already has. */
  confirmed: boolean;
}

/** Links steering messages to the answer they landed in.
 *
 *  The service is the authority: an assistant event carrying `steeredBy` is
 *  reported as confirmed. Without it the page falls back to what the event
 *  timeline proves on its own — a steer sent while an answer was already being
 *  written — and says only that, never that the answer changed. */
export function steerLinks(events: SessionEvent[]): SteerLink[] {
  const links = new Map<string, SteerLink>();
  for (const event of events) {
    if (event.kind !== "assistant") continue;
    const reported = event.steeredBy?.filter((id) => typeof id === "string");
    if (reported?.length)
      links.set(event.id, {
        assistantId: event.id,
        steerIds: [...reported],
        confirmed: true,
      });
  }
  const answers = events.filter((event) => event.kind === "assistant");
  for (const steer of events) {
    if (steer.kind !== "user" || steer.mode !== "steer") continue;
    if (steer.status === "cancelled" || steer.status === "error") continue;
    const sentAt = Date.parse(steer.createdAt);
    if (Number.isNaN(sentAt)) continue;
    // The answer that was already being written when the steer was queued: Pi
    // delivers it into that same run, before the next model request.
    const inFlight = [...answers]
      .reverse()
      .find((answer) => {
        const started = Date.parse(answer.createdAt);
        if (Number.isNaN(started) || started > sentAt) return false;
        const ended = Date.parse(answer.updatedAt || "");
        return answer.status === "running" || Number.isNaN(ended) || ended > sentAt;
      });
    if (!inFlight) continue;
    const existing = links.get(inFlight.id);
    if (existing?.confirmed) continue;
    links.set(inFlight.id, {
      assistantId: inFlight.id,
      steerIds: [...(existing?.steerIds || []), steer.id],
      confirmed: false,
    });
  }
  return [...links.values()];
}

/** The badge an answer carries, or empty when it carries none. */
export function steerBadge(link: SteerLink | undefined): string {
  if (!link) return "";
  const count = link.steerIds.length > 1 ? ` · ${link.steerIds.length} 条` : "";
  return link.confirmed
    ? `按你的引导调整过${count}`
    : `生成过程中收到你的引导${count}`;
}
