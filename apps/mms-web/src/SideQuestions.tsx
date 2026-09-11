/** The `/btw` surface: one card per side question, and the state behind them.
 *
 *  Side questions are shown apart from the transcript because that is what
 *  they are. Asking one does not start a turn, does not queue a message and
 *  does not enter the main context, so nothing here writes into the
 *  conversation the main task is building.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  MessageCircleQuestion,
  X,
} from "lucide-react";
import { Dialog, RichText } from "./components";
import { askSideQuestion, cancelSideQuestion, getSideQuestion } from "./api";
import { newRequestId } from "./request-id";
import { formatEventTime, formatEventTimeTitle } from "./time";
import {
  defaultExpanded,
  isInFlight,
  mergeSideQuestions,
  routeLine,
  sourceLabel,
  statusLabel,
  summaryLine,
  upsertSideQuestion,
  type SideQuestion,
} from "./side-questions";

const empty: SideQuestion[] = [];

export interface SideQuestionState {
  rows: SideQuestion[];
  ask: (question: string) => Promise<boolean>;
  cancel: (btwId: string) => Promise<void>;
  notice: string;
  clearNotice: () => void;
}

/** Side-question state for one session.
 *
 *  Rows come from two places. The session poll carries every stored row, which
 *  is what makes a refresh, a restart or a reopened session show the same
 *  history. Rows this page asked for are also kept locally, so a question is
 *  visible before the next poll and keeps updating while the main poll is
 *  paused by a write.
 */
export function useSideQuestions(
  sessionId: string | undefined,
  stored: SideQuestion[] | undefined,
): SideQuestionState {
  const [local, setLocal] = useState<SideQuestion[]>(empty);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    setLocal(empty);
    setNotice("");
  }, [sessionId]);
  const rows = useMemo(
    () => mergeSideQuestions(stored || empty, local),
    [stored, local],
  );
  // Only rows that can still change are polled, and they stop the moment the
  // server reports a final status.
  const pending = rows.filter(isInFlight).map((row) => row.btwId);
  const pendingKey = pending.join("|");
  const pendingRef = useRef<string[]>(pending);
  pendingRef.current = pending;
  useEffect(() => {
    if (!sessionId || !pendingKey) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      await Promise.all(
        pendingRef.current.map(async (btwId) => {
          try {
            const row = await getSideQuestion(
              sessionId!,
              btwId,
              controller.signal,
            );
            if (!controller.signal.aborted)
              setLocal((old) => upsertSideQuestion(old, row));
          } catch {
            // A read that failed changes nothing: the session poll carries the
            // same rows, and a stuck question still shows its real status.
          }
        }),
      );
      if (!controller.signal.aborted) timer = setTimeout(tick, 1000);
    }
    timer = setTimeout(tick, 600);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [sessionId, pendingKey]);
  const ask = useCallback(
    async (question: string) => {
      if (!sessionId) throw new Error("先打开一个会话，再发起旁问。");
      const row = await askSideQuestion(sessionId, {
        question,
        idempotencyKey: newRequestId(),
      });
      setLocal((old) => upsertSideQuestion(old, row));
      return true;
    },
    [sessionId],
  );
  const cancel = useCallback(
    async (btwId: string) => {
      if (!sessionId) return;
      try {
        const row = await cancelSideQuestion(sessionId, btwId);
        setLocal((old) => upsertSideQuestion(old, row));
      } catch (error) {
        setNotice((error as Error).message);
      }
    },
    [sessionId],
  );
  return { rows, ask, cancel, notice, clearNotice: () => setNotice("") };
}

function Facts({ row }: { row: SideQuestion }) {
  const route = routeLine(row);
  const masked = row.redactionSummary?.secretsMasked || 0;
  const tokens = row.usage?.totalTokens ?? row.usage?.total_tokens;
  return (
    <dl className="btw-facts">
      <div>
        <dt>来源</dt>
        <dd>{sourceLabel(row)}</dd>
      </div>
      {!!row.contextRevision && (
        <div>
          <dt>上下文</dt>
          <dd title="旁问只读取这一版会话状态摘要，没有主任务的全部上下文。">
            {row.contextRevision} 状态快照
          </dd>
        </div>
      )}
      {!!route && (
        <div>
          <dt>路由</dt>
          <dd>{route}</dd>
        </div>
      )}
      {typeof tokens === "number" && (
        <div>
          <dt>用量</dt>
          <dd>{tokens} tokens</dd>
        </div>
      )}
      {masked > 0 && (
        <div>
          <dt>脱敏</dt>
          <dd>已隐藏 {masked} 处密钥</dd>
        </div>
      )}
    </dl>
  );
}

function Body({
  row,
  question = false,
}: {
  row: SideQuestion;
  /** The folded row already carries the question, so the card body repeats it
   *  only where that row is absent: the overlay. */
  question?: boolean;
}) {
  return (
    <div className="btw-body">
      {question && <p className="btw-full-question">{row.question}</p>}
      {isInFlight(row) && (
        <p className="btw-progress" role="status">
          正在旁路回答，主任务继续运行，不会因为这条旁问停止或改变。
        </p>
      )}
      {!!row.answer && <RichText text={row.answer} />}
      {!!row.error && (
        <p className="btw-error" role="status">
          {row.error}
        </p>
      )}
      {row.status === "uncertain" && !row.error && (
        <p className="btw-error" role="status">
          服务停止时这条旁问仍在进行，结果没有记录下来。
        </p>
      )}
      <Facts row={row} />
    </div>
  );
}

function Card({
  row,
  expanded,
  toggle,
  view,
  cancel,
}: {
  row: SideQuestion;
  expanded: boolean;
  toggle: () => void;
  view: () => void;
  cancel: () => void;
}) {
  const status = statusLabel(row);
  const summary = summaryLine(row);
  return (
    <article className="btw-card" data-tone={status.tone}>
      <div
        className="btw-row"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        // Double-click is the pointer gesture the product asks for; a single
        // click only focuses, so the two never race. Enter and Space are the
        // same toggle for a keyboard or a screen reader.
        onDoubleClick={toggle}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        }}
      >
        <button
          type="button"
          className="btw-fold"
          aria-label={expanded ? "收起这条旁问" : "展开这条旁问"}
          onClick={toggle}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <span className="btw-mark">
          <MessageCircleQuestion size={13} />
          BTW
        </span>
        <span className="btw-aside">不影响主任务</span>
        <span className="btw-question">{row.question}</span>
        {!expanded && !!summary && (
          <span className="btw-summary">{summary}</span>
        )}
        <span className="btw-state">{status.text}</span>
        <time
          dateTime={row.createdAt}
          title={formatEventTimeTitle(row.createdAt)}
        >
          {formatEventTime(row.createdAt)}
        </time>
      </div>
      {expanded && <Body row={row} />}
      <div className="btw-actions">
        <button type="button" onClick={view}>
          查看
        </button>
        {isInFlight(row) && (
          <button type="button" onClick={cancel}>
            取消旁问
          </button>
        )}
      </div>
    </article>
  );
}

function Detail({ row, close }: { row: SideQuestion; close: () => void }) {
  // Dialog answers Escape itself, and closing it only hides this view: the
  // card and its record stay in the conversation.
  return (
    <Dialog title="BTW 旁问" close={close} dismissible>
      <p className="dialog-intro">
        旁问独立于主任务：它不进入主任务的上下文，也不会改变主任务的模型、
        思考等级或执行顺序。关闭这个浮层不会删除记录。
      </p>
      <Body row={row} question />
    </Dialog>
  );
}

/** Every side question of one session, oldest first. */
export function SideQuestions({
  state,
  sidecarAvailable,
}: {
  state: SideQuestionState;
  sidecarAvailable?: boolean;
}) {
  const [choice, setChoice] = useState<Record<string, boolean>>({});
  const [opened, setOpened] = useState("");
  const { rows, notice, clearNotice, cancel } = state;
  const open = rows.find((row) => row.btwId === opened);
  useEffect(() => {
    if (opened && !open) setOpened("");
  }, [opened, open]);
  if (!rows.length && !notice) return null;
  return (
    <section className="btw-stack" aria-label="旁问记录">
      {!!notice && (
        <p className="btw-notice" role="status">
          {notice}
          <button type="button" aria-label="关闭提示" onClick={clearNotice}>
            <X size={13} />
          </button>
        </p>
      )}
      {rows.map((row) => {
        const fallback = defaultExpanded(row);
        const expanded = choice[row.btwId] ?? fallback;
        return (
          <Card
            key={row.btwId}
            row={row}
            expanded={expanded}
            toggle={() =>
              setChoice((old) => ({ ...old, [row.btwId]: !expanded }))
            }
            view={() => setOpened(row.btwId)}
            cancel={() => void cancel(row.btwId)}
          />
        );
      })}
      {sidecarAvailable === false &&
        rows.some((row) => row.source === "completion") && (
          <p className="btw-notice" role="status">
            这台机器没有配置只读旁问模型，需要判断的问题无法回答。状态问题
            （进度、耗时、最近工具、审批、队列）仍然可以问。
          </p>
        )}
      {open && <Detail row={open} close={() => setOpened("")} />}
    </section>
  );
}
