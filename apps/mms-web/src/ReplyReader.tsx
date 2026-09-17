import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { copyText } from "./clipboard";

export function replyReaderKey(
  key: string,
  composing: boolean,
  targetTag: string,
): "close" | "copy" | null {
  if (composing) return null;
  if (key === "Escape") return "close";
  if (key === "Enter" && targetTag !== "BUTTON" && targetTag !== "A")
    return "copy";
  return null;
}

export function ReplyReader({
  text,
  title,
  onClose,
  children,
}: {
  text: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  function copy() {
    void copyText(text).then((done) => {
      if (!done) return;
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <dialog
      ref={ref}
      className="reply-reader"
      aria-labelledby="reply-reader-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      onKeyDown={(event) => {
        const act = replyReaderKey(
          event.key,
          event.nativeEvent.isComposing,
          (event.target as HTMLElement).tagName,
        );
        if (act === "close") {
          event.preventDefault();
          onClose();
        }
        if (act === "copy") {
          event.preventDefault();
          copy();
        }
      }}
    >
      <header>
        <h2 id="reply-reader-title">{title}</h2>
        <button
          type="button"
          className="icon-button"
          aria-label="关闭阅读"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </header>
      <div className="reply-reader-body">{children}</div>
      <footer>
        <span>Esc 关闭</span>
        <span>·</span>
        <span>Enter {copied ? "已复制" : "复制原文"}</span>
      </footer>
    </dialog>
  );
}
