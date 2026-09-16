import { ArrowDown, ArrowUp, CornerDownRight, Trash2 } from "lucide-react";
import { moveTarget, readQueue } from "./message-control";
import type { Runtime, Session } from "./types";

/** The messages this session has accepted but not delivered yet.
 *
 *  How a message lands is decided here, on the message, after it is sent, not
 *  in a mode menu before it. Sending while the session is busy queues; if that
 *  turns out to be the wrong call, the queued message can be promoted to a
 *  steer, dropped, or reordered without retyping it.
 *
 *  Reading, clearing and ordering all come from the service, so a refresh or a
 *  restore shows the same queue without the page remembering anything. What the
 *  service cannot do, the list leaves out rather than offering a control that
 *  would do something else. */
export function MessageQueue({
  runtime,
  capabilities,
  busy,
  remove,
  move,
  steer,
  clear,
  variant = "panel",
}: {
  runtime?: Runtime;
  capabilities?: Session["capabilities"];
  busy: boolean;
  remove?: (id: string) => void;
  move?: (id: string, toIndex: number) => void;
  steer?: (id: string) => void;
  clear?: () => void;
  /** "panel" is the record of what is waiting, inside the runtime details.
   *  "dock" rides on top of the input and carries the actions, so it stays out
   *  of the way entirely when there is nothing it can do — the transcript
   *  already lists the messages, and a second read-only copy only repeats it. */
  variant?: "panel" | "dock";
}) {
  const { items, manageable, unlisted, note } = readQueue(runtime, capabilities);
  // Clearing the whole queue is the one action every service has. With a single
  // message waiting, that is exactly "drop this message", so the row can offer
  // it truthfully even where per-message control does not exist.
  const dropLast = items.length === 1 && !!clear && !manageable;
  const editable = manageable && !!remove;
  // Clearing is the one action every service has, so the dock always has
  // something to offer once a message is waiting.
  if (variant === "dock" && !editable && !dropLast && !clear) return null;
  if (!items.length && !unlisted) return null;
  const ordering = manageable && !!move && items.length > 1;
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
        {!!clear && items.length > 1 && (
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
            <div className="queue-item-actions">
              {manageable && !!steer && item.mode === "followUp" && (
                <button
                  type="button"
                  className="queue-action"
                  disabled={busy}
                  onClick={() => steer(item.id)}
                  title="改为立即引导：当前这批工具调用跑完、下一次模型请求之前送达"
                >
                  <CornerDownRight size={13} />
                  调整方向
                </button>
              )}
              {ordering && (
                <>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`上移第 ${index + 1} 条`}
                    disabled={busy || !moveTarget(items, item.id, -1)}
                    onClick={() => {
                      const target = moveTarget(items, item.id, -1);
                      if (target && move) move(target.id, target.toIndex);
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
                      if (target && move) move(target.id, target.toIndex);
                    }}
                  >
                    <ArrowDown size={13} />
                  </button>
                </>
              )}
              {(editable || dropLast) && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`删除第 ${index + 1} 条`}
                  disabled={busy}
                  onClick={() => (editable && remove ? remove(item.id) : clear?.())}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
      {!!unlisted && (
        <p className="section-note">
          另有 {unlisted} 条已在执行工具的队列里，本地服务未回报内容。
        </p>
      )}
      {!!note && variant === "panel" && <p className="section-note">{note}</p>}
    </section>
  );
}
