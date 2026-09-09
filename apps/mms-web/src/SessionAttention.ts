import { useEffect, useRef, useState } from "react";
import { getSession } from "./api";
import type { Session, SessionDetail } from "./types";

const storageKey = "mms-web-read-results-v1";
function readReceipts(): Record<string, string> {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || "{}");
    const clean: Record<string, string> = {};
    for (const [id, token] of Object.entries(value))
      if (id.length < 160 && typeof token === "string" && token.length < 160)
        clean[id] = token;
    return clean;
  } catch {
    return {};
  }
}
function completed(session: Session) {
  return (
    session.state === "idle" &&
    !["error", "stopped", "compacting", "retrying"].includes(
      session.activity?.phase || "",
    )
  );
}
export function resultToken(detail: SessionDetail): string {
  if (!completed(detail.session)) return "";
  const output = [...detail.events]
    .reverse()
    .find((e) => e.kind === "assistant" && (e.text || e.thinking));
  if (!output) return "";
  // A fingerprint of actual output, never a rename/runtime/usage timestamp.
  const content = `${output.nativeTimestamp || output.id}:${output.text}:${output.thinking || ""}`;
  let hash = 2166136261;
  for (let i = 0; i < content.length; i++)
    hash = Math.imul(hash ^ content.charCodeAt(i), 16777619);
  return `${output.nativeTimestamp || output.id}:${hash >>> 0}`;
}

export function useSessionAttention(
  sessions: Session[],
  detail: SessionDetail | null,
  viewingBottom: boolean,
  connected: boolean,
) {
  const receipts = useRef(readReceipts());
  const revisions = useRef(new Map<string, string>());
  const busy = useRef(new Set<string>());
  const baseline = useRef<Set<string> | null>(null);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [unread, setUnread] = useState<Record<string, string>>({});
  const [flashes, setFlashes] = useState<Record<string, string>>({});
  const [retry, setRetry] = useState(0);
  const [visible, setVisible] = useState(
    document.visibilityState === "visible",
  );
  function save() {
    const entries = Object.entries(receipts.current).slice(-1000);
    receipts.current = Object.fromEntries(entries);
    try {
      localStorage.setItem(storageKey, JSON.stringify(receipts.current));
    } catch {
      /* best effort */
    }
  }
  useEffect(() => {
    const change = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", change);
    const sync = (e: StorageEvent) => {
      if (e.key !== storageKey) return;
      receipts.current = readReceipts();
      setUnread((old) =>
        Object.fromEntries(
          Object.entries(old).filter(
            ([id, token]) => receipts.current[id] !== token,
          ),
        ),
      );
    };
    window.addEventListener("storage", sync);
    return () => {
      document.removeEventListener("visibilitychange", change);
      window.removeEventListener("storage", sync);
      timers.current.forEach(clearTimeout);
    };
  }, []);
  const signature = JSON.stringify(
    sessions.map((s) => [s.id, s.state, s.activity?.phase, s.updatedAt]),
  );
  useEffect(() => {
    if (!connected || !sessions.length) return;
    if (!baseline.current)
      baseline.current = new Set(sessions.filter(completed).map((s) => s.id));
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const pending: Session[] = [];
    for (const s of sessions) {
      if (s.state === "running" || s.state === "waiting") {
        busy.current.add(s.id);
        if (!(s.id in receipts.current)) receipts.current[s.id] = "";
        setUnread((old) =>
          old[s.id]
            ? Object.fromEntries(
                Object.entries(old).filter(([id]) => id !== s.id),
              )
            : old,
        );
      }
      if (completed(s) && revisions.current.get(s.id) !== s.updatedAt)
        pending.push(s);
    }
    save();
    async function worker() {
      while (pending.length && !controller.signal.aborted) {
        const s = pending.shift()!;
        try {
          const latest = await getSession(s.id, controller.signal);
          if (controller.signal.aborted) return;
          const token = resultToken(latest);
          if (!token) continue;
          revisions.current.set(s.id, s.updatedAt);
          if (
            baseline.current?.has(s.id) &&
            !(s.id in receipts.current) &&
            !busy.current.has(s.id)
          ) {
            receipts.current[s.id] = token;
            save();
          }
          if (receipts.current[s.id] !== token)
            setUnread((old) => ({ ...old, [s.id]: token }));
          if (busy.current.delete(s.id)) {
            setFlashes((old) => ({ ...old, [s.id]: token }));
            clearTimeout(timers.current.get(s.id));
            timers.current.set(
              s.id,
              setTimeout(() => {
                setFlashes((old) =>
                  Object.fromEntries(
                    Object.entries(old).filter(([id]) => id !== s.id),
                  ),
                );
                timers.current.delete(s.id);
              }, 2200),
            );
          }
        } catch {
          if (!controller.signal.aborted && !retryTimer)
            retryTimer = setTimeout(() => setRetry((n) => n + 1), 2500);
        }
      }
    }
    void Promise.all([worker(), worker()]);
    return () => {
      controller.abort();
      clearTimeout(retryTimer);
    };
  }, [signature, connected, retry]);
  const token = detail ? resultToken(detail) : "";
  useEffect(() => {
    if (!detail || !token || !viewingBottom || !visible || !connected) return;
    const id = detail.session.id;
    // A selected row is not a read receipt. Wait until its actual output is rendered.
    const frame = requestAnimationFrame(() => {
      receipts.current[id] = token;
      save();
      setUnread((old) =>
        old[id] === token
          ? Object.fromEntries(
              Object.entries(old).filter(([key]) => key !== id),
            )
          : old,
      );
    });
    return () => cancelAnimationFrame(frame);
  }, [
    detail?.session.id,
    token,
    viewingBottom,
    visible,
    connected,
    unread[detail?.session.id || ""],
  ]);
  return { unread, flashes };
}
