import { ArrowDown, ArrowUp, X } from "lucide-react";
import { moveTarget, readQueue } from "./message-control";
import type { Runtime, Session } from "./types";

/** The messages this session has accepted but not delivered yet.
 *
 *  Reading, clearing and ordering all come from the service, so a refresh or a
 *  restore shows the same queue without the page remembering anything. What the
 *  service cannot do, the list says plainly instead of offering a control that
 *  would do something else. */
export function MessageQueue({
  runtime,
  capabilities,
  busy,
  remove,
  move,
  clear,
  variant = "panel",
}: {
  runtime?: Runtime;
  capabilities?: Session["capabilities"];
  busy: boolean;
  remove?: (id: string) => void;
  move?: (id: string, toIndex: number) => void;
  clear?: () => void;
  /** "panel" is the record of what is waiting. "controls" sits above the input
   *  and exists to act on the queue, so it stays out of the way entirely when
   *  the service cannot act on single messages — the transcript already lists
   *  them, and a second read-only copy would only repeat it. */
  variant?: "panel" | "controls";
}) {
  const { items, manageable, unlisted, note } = readQueue(runtime, capabilities);
  const editable = manageable && !!remove && !!move;
  if (variant === "controls" && !editable) return null;
  if (!items.length && !unlisted) return null;
  return (
    <section className={`message-queue message-queue-${variant}`} aria-label="待发送消息">
      <div className="message-queue-head">
        <h3>
          待发送队列 · {items.length + unlisted}
          {/* The transcript lists these where they were typed; this list is
              ordered the way the session will actually deliver them, and
              steering goes before follow-ups. Saying so keeps the two orders
              from reading as a contradiction. */}
          <span>按送达顺序</span>
        </h3>
        {!!clear && (
          <button
            type="button"
            className="message-queue-clear"
            disabled={busy}
            onClick={clear}
          >
            清空队列
          </button>
        )}
      </div>
      <ol className="message-queue-items">
        {items.map((item, index) => (
          <li key={item.id}>
            <span className={`queue-mode queue-mode-${item.mode}`}>
              {item.mode === "steer" ? "引导" : "补充"}
            </span>
            <p>{item.text.slice(0, 500)}</p>
            {editable && (
              <div className="queue-item-actions">
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`上移第 ${index + 1} 条`}
                  disabled={busy || !moveTarget(items, item.id, -1)}
                  onClick={() => {
                    const target = moveTarget(items, item.id, -1);
                    if (target) move(target.id, target.toIndex);
                  }}
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`下移第 ${index + 1} 条`}
                  disabled={busy || !moveTarget(items, item.id, 1)}
                  onClick={() => {
                    const target = moveTarget(items, item.id, 1);
                    if (target) move(target.id, target.toIndex);
                  }}
                >
                  <ArrowDown size={13} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`删除第 ${index + 1} 条`}
                  disabled={busy}
                  onClick={() => remove(item.id)}
                >
                  <X size={13} />
                </button>
              </div>
            )}
          </li>
        ))}
      </ol>
      {!!unlisted && (
        <p className="section-note">
          另有 {unlisted} 条已在执行工具的队列里，本地服务未回报内容。
        </p>
      )}
      {!!note && <p className="section-note">{note}</p>}
    </section>
  );
}
