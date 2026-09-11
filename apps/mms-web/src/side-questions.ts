/** `/btw` side questions: the shapes the server returns, and the pure rules the
 *  UI applies to them.
 *
 *  A side question is not a turn. It is stored beside the transcript, carries
 *  its own id and lifecycle, and never enters the main context. Everything in
 *  this file is data and decisions only, so it can be read and tested without
 *  a browser; the HTTP calls live in `api.ts` and the views in
 *  `SideQuestions.tsx`.
 */

export type SideQuestionStatus =
  | "prepared"
  | "accepted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "uncertain";

/** Where the answer came from. `state` is the session snapshot the server can
 *  always read; `completion` is the read-only sidecar model. */
export type SideQuestionSource = "state" | "completion";

export interface SideQuestionRoute {
  modelName?: string;
  providerName?: string;
  channel?: string;
  thinking?: string;
}

export interface SideQuestion {
  btwId: string;
  mainSessionId: string;
  owner?: string;
  question: string;
  status: SideQuestionStatus;
  answer: string | null;
  source: SideQuestionSource;
  contextRevision?: string;
  routeSnapshot?: SideQuestionRoute;
  usage?: Record<string, unknown> | null;
  redactionSummary?: { secretsMasked?: number };
  error: string | null;
  createdAt: string;
  acceptedAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface AskSideQuestion {
  question: string;
  idempotencyKey?: string;
  sourceHint?: SideQuestionSource;
}

/** Statuses the server will never move away from. */
export const SIDE_QUESTION_SETTLED: readonly SideQuestionStatus[] = [
  "completed",
  "failed",
  "cancelled",
  "uncertain",
];

export function isSettled(row: SideQuestion): boolean {
  return SIDE_QUESTION_SETTLED.includes(row.status);
}

export function isInFlight(row: SideQuestion): boolean {
  return !isSettled(row);
}

/** How far along the lifecycle a row is, used to pick between two copies of
 *  the same question. A settled row is never replaced by an in-flight one. */
function progress(status: SideQuestionStatus): number {
  if (SIDE_QUESTION_SETTLED.includes(status)) return 3;
  if (status === "running") return 2;
  if (status === "accepted") return 1;
  return 0;
}

/** Merge the rows the session detail carries with the rows this page has seen
 *  directly.
 *
 *  The two disagree for a second at a time in both directions: a question just
 *  posted is not in the session detail yet, and a locally cached row goes stale
 *  while the sidecar keeps working. Whichever copy is further along wins, and
 *  the server breaks a tie, so neither poll can walk a finished answer back to
 *  "generating".
 */
export function mergeSideQuestions(
  server: SideQuestion[],
  local: SideQuestion[],
): SideQuestion[] {
  const byId = new Map<string, SideQuestion>();
  for (const row of local) if (row?.btwId) byId.set(row.btwId, row);
  for (const row of server) {
    if (!row?.btwId) continue;
    const seen = byId.get(row.btwId);
    if (!seen || progress(row.status) >= progress(seen.status))
      byId.set(row.btwId, row);
  }
  return [...byId.values()].sort(
    (a, b) =>
      (a.createdAt || "").localeCompare(b.createdAt || "") ||
      a.btwId.localeCompare(b.btwId),
  );
}

/** Replace one row in a list, or append it when it is new. */
export function upsertSideQuestion(
  rows: SideQuestion[],
  row: SideQuestion,
): SideQuestion[] {
  if (!rows.some((old) => old.btwId === row.btwId)) return [...rows, row];
  return rows.map((old) =>
    old.btwId !== row.btwId || progress(row.status) < progress(old.status)
      ? old
      : row,
  );
}

/** Open while the answer is still arriving, folded once it has settled.
 *  A card the reader has toggled keeps their choice instead of this. */
export function defaultExpanded(row: SideQuestion): boolean {
  return isInFlight(row);
}

export function sourceLabel(row: SideQuestion): string {
  return row.source === "state" ? "Pilot 状态" : "只读旁问模型";
}

export type SideQuestionTone =
  | "running"
  | "done"
  | "error"
  | "cancelled"
  | "unknown";

/** The short status word on the folded row, and the tone that colours it. */
export function statusLabel(row: SideQuestion): {
  text: string;
  tone: SideQuestionTone;
} {
  if (row.status === "completed") return { text: "已回答", tone: "done" };
  if (row.status === "failed") return { text: "未回答", tone: "error" };
  if (row.status === "cancelled") return { text: "已取消", tone: "cancelled" };
  if (row.status === "uncertain") return { text: "结果未知", tone: "unknown" };
  if (row.status === "running") return { text: "生成中", tone: "running" };
  return { text: "已受理", tone: "running" };
}

/** One line of the answer for the folded row: never the error text alone,
 *  because the status word already says something went wrong. */
export function summaryLine(row: SideQuestion, limit = 120): string {
  const text = (row.answer || row.error || "").trim().replace(/\s+/g, " ");
  if (!text) return isInFlight(row) ? "正在旁路回答，主任务继续运行…" : "";
  return text.length > limit ? text.slice(0, limit) + "…" : text;
}

/** What typing `/btw` should do with whatever followed it. Bare `/btw` opens
 *  the side-question input rather than sending anything. */
export function readBtwCommand(
  args: string,
): { kind: "ask"; question: string } | { kind: "compose" } {
  const question = (args || "").trim();
  return question ? { kind: "ask", question } : { kind: "compose" };
}

/** The route the answer was produced against, as one readable line.
 *
 *  Empty when nothing was sent. A question answered from the session snapshot
 *  never reached a model, and one that failed closed never reached the
 *  network, so printing a model name beside either would read as a claim that
 *  it answered.
 */
export function routeLine(row: SideQuestion): string {
  if (row.source !== "completion" || !row.startedAt || row.answer === null)
    return "";
  const route = row.routeSnapshot || {};
  return [route.modelName, route.providerName, route.channel]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(" · ");
}
