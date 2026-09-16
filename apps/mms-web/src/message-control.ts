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
 *    POST /sessions/{id}/messages   { ...,  mode: "followUp" | "steer" }
 *        `direct` is the page's word for "the session is idle, so this starts
 *        a turn". It is not a wire value and is left out of the request: the
 *        service rejects anything that is not one of the two above.
 *
 *    session.capabilities.steer   the service accepts mode: "steer"
 *    runtime.queueSteering / runtime.queueFollowUp
 *        the pending queue split by lane, in delivery order — steering goes
 *        first. Text only: Pi reports no ids for queued messages.
 *    event.status   queued | delivered | failed | interrupted | cancelled
 *
 *  That is what the service serves today. These are not served, and the page
 *  stays quiet without them rather than guessing:
 *
 *    POST /sessions/{id}/queue          { action: "remove", id }
 *                                       { action: "steer",  id }
 *                                       { action: "move",   id, toIndex }
 *        "steer" promotes a waiting follow-up into the steering lane. It is
 *        the only way the page offers to redirect work in flight, so without
 *        this route steering is unreachable from the page.
 *    session.capabilities.queueControl  the service serves /queue
 *    runtime.pending                    queued messages with stable ids
 *    event.mode                         how this user message was sent
 *    event.steeredBy                    which steers reached this answer
 *
 *  Pi has no per-item delete or reorder, so /queue has to be "clear the queue,
 *  then re-enqueue what is kept, in order" on the service side. Until it
 *  exists the page offers whole-queue clearing only. Every field above is
 *  optional and absent means "not supported": no control appears that would
 *  silently do something else, which is the anti-pattern named in
 *  `docs/AGENT_GUARDRAILS.md`.
 */
import type { PendingMessage, Runtime, SendMode, SessionEvent } from "./types";

/** What actually goes on the request. The page's `direct` has no wire form:
 *  an idle session starts a turn, which is what the service does with no mode
 *  at all, and it rejects "direct" outright. A busy session always queues; a
 *  message becomes a steer afterwards, through the queue, not on the way out. */
export function wireMode(mode: SendMode): "followUp" | "steer" | undefined {
  return mode === "direct" ? undefined : mode;
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

const LEGACY_NOTE = "本地服务只报告了队列文字，没有逐条编号，因此只能整队清空。";
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
  const lane = (texts: unknown, mode: "followUp" | "steer") =>
    (Array.isArray(texts) ? texts : []).map((text, index) => ({
      id: `${mode}:${index}`,
      text: String(text),
      mode,
    }));
  // Steering is delivered before follow-ups, so it is listed first.
  const lanes = [
    ...lane(runtime?.queueSteering, "steer"),
    ...lane(runtime?.queueFollowUp, "followUp"),
  ];
  const items = lanes.length ? lanes : lane(runtime?.queue, "followUp");
  return {
    items,
    manageable: false,
    unlisted: Math.max(0, counted - items.length),
    note: items.length ? LEGACY_NOTE : "",
  };
}

/** Where an item lands after one step, or null when it cannot move that way.
 *
 *  Every steer is delivered before every follow-up whatever the order says, so
 *  a message only moves among its own kind; at the boundary there is nowhere
 *  left to go. */
export function moveTarget(
  items: PendingMessage[],
  id: string,
  direction: -1 | 1,
): { id: string; toIndex: number } | null {
  const from = items.findIndex((item) => item.id === id);
  if (from < 0) return null;
  for (let toIndex = from + direction; toIndex >= 0 && toIndex < items.length; toIndex += direction)
    if (items[toIndex].mode === items[from].mode) return { id, toIndex };
  return null;
}

/** What happened to a message the user already sent. */
export function deliveryLabel(event: SessionEvent): string {
  if (event.status === "cancelled") return "已取消，未执行";
  if (event.status === "interrupted") return "已被停止打断，未执行";
  // "error" is what the service called a failed send before it split the
  // delivery states apart; both still mean the message never ran.
  if (event.status === "failed" || event.status === "error")
    return "发送失败，未执行";
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
    if (["cancelled", "error", "failed", "interrupted"].includes(steer.status || ""))
      continue;
    const sentAt = Date.parse(steer.createdAt);
    if (Number.isNaN(sentAt)) continue;
    // Pi delivers a steer before the next model request, so it shapes the next
    // answer, not the text already on screen when it was sent.
    const next = answers.find((answer) => {
      const started = Date.parse(answer.createdAt);
      return !Number.isNaN(started) && started > sentAt;
    });
    if (!next) continue;
    const existing = links.get(next.id);
    if (existing?.confirmed) continue;
    links.set(next.id, {
      assistantId: next.id,
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
