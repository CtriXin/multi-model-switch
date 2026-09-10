import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { SessionEvent } from "./types";

export const messageAnchor = (id: string) => `message-${id}`;
function questionText(event: SessionEvent) {
  const text = event.text
    .replace(/<image\b[^>]*>\s*(?:<\/image>)?/gi, "[图片]")
    .replace(/\s+/g, " ")
    .trim();
  return text || event.attachments?.map((a) => a.name).join("、") || "附件消息";
}
export function ConversationOutline({
  events,
  scroll,
  beforeJump,
}: {
  events: SessionEvent[];
  scroll: RefObject<HTMLDivElement | null>;
  beforeJump: () => void;
}) {
  const questions = events.filter((e) => e.kind === "user");
  const signature = questions.map((e) => e.id).join("\n");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(questions[0]?.id || "");
  const nav = useRef<HTMLElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const highlight = useRef<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const root = scroll.current;
    if (!root) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const top = root.getBoundingClientRect().top + 80;
        let id = questions[0]?.id || "";
        if (root.scrollHeight - root.scrollTop - root.clientHeight < 24)
          id = questions.at(-1)?.id || id;
        else
          for (const q of questions) {
            const el = document.getElementById(messageAnchor(q.id));
            if (el && el.getBoundingClientRect().top <= top) id = q.id;
          }
        setActive(id);
      });
    };
    root.addEventListener("scroll", update, { passive: true });
    const resize = new ResizeObserver(update);
    resize.observe(root);
    const content = root.querySelector(".conversation-content");
    if (content) resize.observe(content);
    update();
    return () => {
      root.removeEventListener("scroll", update);
      resize.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [signature, scroll]);
  useEffect(() => {
    if (open || !list.current) return;
    const item = list.current.querySelector<HTMLElement>(
      '[aria-current="location"]',
    );
    if (item)
      list.current.scrollTop =
        item.offsetTop - list.current.clientHeight / 2 + item.clientHeight / 2;
  }, [active, open]);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      highlight.current?.classList.remove("message-located");
    },
    [],
  );

  if (questions.length < 2) return null;
  const jump = (id: string) => {
    const target = document.getElementById(messageAnchor(id));
    const root = scroll.current;
    if (!target || !root) return;
    beforeJump();
    setActive(id);
    setOpen(false);
    target.focus({ preventScroll: true });
    root.scrollTo({
      top:
        root.scrollTop +
        target.getBoundingClientRect().top -
        root.getBoundingClientRect().top -
        28,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    clearTimeout(timer.current);
    highlight.current?.classList.remove("message-located");
    target.classList.add("message-located");
    highlight.current = target;
    timer.current = setTimeout(
      () => target.classList.remove("message-located"),
      1800,
    );
  };
  return (
    <nav
      ref={nav}
      className={`question-outline${open ? " open" : ""}`}
      aria-label="我的提问"
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") setOpen(true);
      }}
      onPointerLeave={() => {
        if (!nav.current?.contains(document.activeElement)) setOpen(false);
      }}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          trigger.current?.focus();
          setOpen(false);
        }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          setOpen(true);
          const buttons = Array.from(
            list.current?.querySelectorAll<HTMLButtonElement>("button") || [],
          );
          const i = buttons.indexOf(
            document.activeElement as HTMLButtonElement,
          );
          const next =
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? buttons.length - 1
                : e.key === "ArrowDown"
                  ? Math.min(i + 1, buttons.length - 1)
                  : Math.max(i - 1, 0);
          buttons[next]?.focus();
        }
      }}
    >
      <button
        ref={trigger}
        className="outline-trigger"
        aria-label={`定位我的提问，共 ${questions.length} 条`}
        aria-expanded={open}
        aria-controls="question-outline-list"
        tabIndex={open ? -1 : 0}
        onClick={() => setOpen(true)}
      />
      <div ref={list} className="outline-list" id="question-outline-list">
        {questions.map((q, i) => (
          <button
            key={q.id}
            type="button"
            tabIndex={open ? 0 : -1}
            aria-current={active === q.id ? "location" : undefined}
            aria-label={`第 ${i + 1} 条提问：${questionText(q)}`}
            title={questionText(q)}
            onClick={() => jump(q.id)}
          >
            <span className="outline-mark" aria-hidden="true" />
            <span className="outline-text">{questionText(q)}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}
