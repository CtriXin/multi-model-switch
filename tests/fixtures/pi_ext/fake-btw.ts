/**
 * fake-btw — contract fixture extension for MMS T2a/T2b end-to-end tests.
 *
 * Implements the §4.3 data contract of docs/btw-plugin/00-PLAN.md without
 * any real model call: `/btw <question>` answers with a fixed echo split
 * into streamed deltas, emits every state as a `BTW_EVENT:` notify (the
 * channel MMS Pilot parses), and appends the matching `custom/btw` entry
 * on completion so `get_entries` can prove isolation from the LLM context.
 *
 * Load like any extension:  pi --extension tests/fixtures/pi_ext/fake-btw.ts
 * In RPC mode (`pi --mode rpc`) notifies surface as extension_ui_request
 * messages, which is exactly the seam the host driver listens on.
 *
 * This is a test fixture, NOT the real fork: the answer content is fake,
 * there is no context window logic beyond counting entries, and deltas are
 * throttled to the contract's ≤4/s rather than to any model cadence.
 */

export default function (pi: any) {
  const live = new Map<string, { question: string; startedAt: string; abort: AbortController }>();
  const order: string[] = [];

  const nowIso = () => new Date().toISOString();
  const newId = () => "btw-" + Array.from({ length: 12 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const emit = (ctx: any, payload: Record<string, unknown>) => {
    // Fire-and-forget in both TUI and RPC modes; never awaits a consumer.
    ctx.ui.notify("BTW_EVENT:" + JSON.stringify({ v: 1, ...payload }), "info");
  };

  const contextOf = (ctx: any) => {
    // The real fork reports the branch it fed the model; the fixture only
    // reports the shape so the host can be tested against it.
    try {
      const entries = ctx.sessionManager.getBranch();
      const chars = entries.reduce(
        (sum: number, entry: any) => sum + JSON.stringify(entry).length, 0);
      return { mode: "branch", entries: entries.length, chars, truncated: false };
    } catch {
      return { mode: "none", entries: 0, chars: 0, truncated: false };
    }
  };

  const hostOf = (ctx: any) => (ctx.mode && ctx.mode !== "tui" ? "rpc" : "tui");

  const finish = (ctx: any, id: string, status: string, extra: Record<string, unknown>) => {
    const meta = live.get(id);
    live.delete(id);
    const at = nowIso();
    const payload = { event: status, id, at, ...extra };
    emit(ctx, payload);
    if (meta) {
      pi.appendEntry("btw", {
        v: 1,
        id,
        question: meta.question,
        status,
        answer: status === "completed" ? extra.text ?? null : null,
        error: status === "failed" || status === "cancelled" ? extra.error ?? null : null,
        model: { provider: "fake", id: "fake-btw-model" },
        thinkingLevel: "medium",
        usage: extra.usage ?? { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: null },
        context: contextOf(ctx),
        createdAt: meta.startedAt,
        completedAt: at,
        host: hostOf(ctx),
      });
    }
  };

  pi.registerCommand("btw", {
    description: "旁问（fixture）：主任务继续运行的同时回答一个临时问题",
    handler: async (args: string, ctx: any) => {
      const question = String(args ?? "").trim();
      if (!question) {
        emit(ctx, { event: "failed", id: newId(), at: nowIso(), error: "question_required: /btw 需要一个问题参数。" });
        return;
      }
      const id = newId();
      const startedAt = nowIso();
      const abort = new AbortController();
      live.set(id, { question, startedAt, abort });
      order.push(id);
      emit(ctx, { event: "accepted", id, question, at: startedAt, context: contextOf(ctx), model: { provider: "fake", id: "fake-btw-model" } });
      emit(ctx, { event: "running", id, at: nowIso() });
      const answer = `[fake-btw] 旁问（${question}）：这是 fixture 的固定回答，用于验证 BTW_EVENT 事件流与 custom entry 持久化，不调用任何真实模型。`;
      const chunks = answer.match(/.{1,24}/g) ?? [answer];
      for (const chunk of chunks) {
        if (abort.signal.aborted) return; // cancelled: the cancel command emits the terminal event
        emit(ctx, { event: "delta", id, text: chunk, at: nowIso() });
        await sleep(250); // contract cap: ≤4 deltas per second
      }
      if (abort.signal.aborted) return;
      finish(ctx, id, "completed", { text: answer, usage: { input: 0, output: chunks.length, cacheRead: 0, cacheWrite: 0, cost: null } });
    },
  });

  pi.registerCommand("btw:cancel", {
    description: "取消指定或最新进行中的旁问（fixture）",
    handler: async (args: string, ctx: any) => {
      const wanted = String(args ?? "").trim();
      let id = wanted || order[order.length - 1];
      if (!id || !live.has(id)) {
        id = [...live.keys()].pop() ?? "";
      }
      if (!id || !live.has(id)) {
        emit(ctx, { event: "failed", id: wanted || "btw-unknown", at: nowIso(), error: "not_running: 没有进行中的旁问可取消。" });
        return;
      }
      live.get(id)!.abort.abort();
      finish(ctx, id, "cancelled", { error: "旁问已取消。" });
    },
  });

  pi.on("session_shutdown", async () => {
    // Abort in-flight questions; terminal events are best-effort here since
    // the process is going down. The host marks rows cancelled on restart.
    for (const meta of live.values()) meta.abort.abort();
    live.clear();
  });
}
