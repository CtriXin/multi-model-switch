import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Check,
  CircleAlert,
  ChevronDown,
  FileText,
  FolderOpen,
  LockKeyhole,
  X,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkReadable } from "./remarkReadable";
import { ToolEvent } from "./ToolEvent";
import { messageAnchor } from "./ConversationOutline";
import { MessageActions } from "./SessionTools";
import { AttachmentView } from "./MessageMedia";
import type {
  Artifact,
  Preset,
  SessionDetail,
  SessionEvent,
  Workspace,
} from "./types";

export const harnessNames: Record<string, string> = {
  pi: "Pi",
  codex: "Codex",
  claude: "Claude Code",
  opencode: "OpenCode",
  gemini: "Gemini",
  agy: "Antigravity",
};
export { Status } from "./SessionStatus";
export function AppVersion({ version }: { version?: string }) {
  return version ? <span className="app-version" title="当前服务版本" aria-label={`MMS 版本 ${version}`}>v{version}</span> : null;
}

export function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={"mms-mark " + (small ? "small" : "")} aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
}
function CodeBlock({ children }: { children?: ReactNode }) {
  const ref = useRef<HTMLPreElement>(null);
  const [state, setState] = useState("复制代码");
  return (
    <div className="code-block">
      <button
        onClick={() => {
          void navigator.clipboard
            .writeText(ref.current?.textContent || "")
            .then(() => {
              setState("已复制");
              setTimeout(() => setState("复制代码"), 1500);
            })
            .catch(() => setState("请选中文字复制"));
        }}
      >
        {state}
      </button>
      <pre ref={ref}>{children}</pre>
    </div>
  );
}
// Stable renderers preserve code-copy feedback during streaming/session polls.
const markdownComponents: Components = {
  pre: CodeBlock,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  img: ({ alt }) => <span className="muted">[图片：{alt || "未加载"}]</span>,
};
const standardMarkdown = [remarkGfm];
const readableMarkdown = [remarkGfm, remarkReadable];
export function RichText({
  text,
  repair = false,
}: {
  text: string;
  repair?: boolean;
}) {
  return (
    <div className="markdown">
      <Markdown
        skipHtml
        remarkPlugins={repair ? readableMarkdown : standardMarkdown}
        components={markdownComponents}
      >
        {text}
      </Markdown>
    </div>
  );
}
export function Dialog({
  title,
  children,
  close,
  dismissible = true,
  size = "default",
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  dismissible?: boolean;
  /** "wide" for lists that read badly in a narrow column, "sheet" for the
   *  settings surface, which holds a full channel table. */
  size?: "default" | "wide" | "sheet";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (dismissible) close();
      }}
      onClick={(e) => {
        if (dismissible && e.target === ref.current) close();
      }}
    >
      <section className={"dialog-body" + (size === "default" ? "" : " " + size)}>
        <header>
          <h2>{title}</h2>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭窗口"
            disabled={!dismissible}
            onClick={close}
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </dialog>
  );
}
export { Composer } from "./Composer";
export function WorkspacePicker({
  workspaces,
  value,
  change,
  allowAdd = false,
}: {
  workspaces: Workspace[];
  allowAdd?: boolean;
  value: string;
  change: (id: string) => void;
}) {
  return (
    <label className="workspace-picker">
      <FolderOpen size={15} />
      <span className="sr-only">工作文件夹</span>
      <select
        value={value}
        onChange={(e) => change(e.target.value)}
        disabled={!workspaces.length && !allowAdd}
      >
        {!workspaces.length && <option value="">尚未连接工作文件夹</option>}
        {workspaces.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
        {allowAdd && <option value="__add__">＋ 添加工作文件夹</option>}
      </select>
      <ChevronDown size={13} />
    </label>
  );
}
export function PresetPicker({
  presets,
  value,
  change,
}: {
  presets: Preset[];
  value: string;
  change: (id: string) => void;
}) {
  return (
    <div className="preset-list" role="radiogroup" aria-label="常用启动组合">
      {presets.map((item) => (
        <button
          key={item.id}
          role="radio"
          aria-checked={value === item.id}
          className={"preset " + (value === item.id ? "selected" : "")}
          onClick={() => change(item.id)}
          disabled={!item.available}
          title={item.reason}
        >
          <span className="radio-dot">
            {value === item.id && <Check size={10} />}
          </span>
          <span>
            <strong>{item.name}</strong>
            <small>{item.description}</small>
          </span>
        </button>
      ))}
    </div>
  );
}
export function EventView({
  event,
  detail,
  busy,
  approve,
  action,
  disconnected = false,
  continuation = false,
  intermediate = false,
}: {
  continuation?: boolean;
  intermediate?: boolean;
  disconnected?: boolean;
  event: SessionEvent;
  action?: (
    path: string,
    payload: Record<string, unknown>,
    open?: boolean,
  ) => Promise<boolean>;
  detail: SessionDetail;
  busy: boolean;
  approve: (id: string, decision: "allow" | "deny", value?: string) => void;
}) {
  const thinking =
    !disconnected &&
    detail.session.state === "running" &&
    detail.session.activity?.phase === "thinking" &&
    detail.session.activity.eventId === event.id;
  if (event.id === "n-web-mode") return null;
  if (event.kind === "tool")
    return (
      <ToolEvent event={event} detail={detail} disconnected={disconnected} />
    );
  if (event.kind === "notice")
    return <p className="notice-event">{event.text}</p>;
  if (event.kind === "approval")
    return (
      <Interaction
        event={event}
        busy={busy || !detail.session.capabilities.approve}
        approve={approve}
      />
    );
  if (
    event.kind === "assistant" &&
    !event.text.trim() &&
    !event.thinking?.trim()
  )
    return null;
  return (
    <article
      id={messageAnchor(event.id)}
      tabIndex={-1}
      data-event-id={event.id}
      className={`message ${event.kind}${continuation ? " continuation" : ""}${intermediate ? " intermediate" : ""}`}
    >
      <div className="message-avatar">
        {event.kind === "user" ? "你" : <Logo small />}
      </div>
      <div className="message-body">
        <div className="message-author">
          {event.kind === "user" ? "你" : harnessNames[detail.session.harness]}
          {event.kind === "assistant" && (
            <span>{event.modelName || detail.session.modelName}</span>
          )}
        </div>
        {event.thinking && (
          <details className="thinking-block">
            <summary>
              <span
                className={thinking ? "thinking-dot working" : "thinking-dot"}
              />
              {thinking ? "正在思考" : "思考过程"}
              <ChevronDown size={13} />
            </summary>
            <RichText text={event.thinking} repair />
          </details>
        )}
        {event.attachments?.map((a) => (
          <AttachmentView key={a.id} attachment={a} />
        ))}
        {!!event.skills?.length && (
          <div className="message-references">
            {event.skills.map((s) => (
              <span key={s.id}>Skill · {s.name}</span>
            ))}
          </div>
        )}
        {!!event.references?.length && (
          <div className="message-references">
            {event.references.map((p) => (
              <span key={p}>@ {p}</span>
            ))}
          </div>
        )}
        <RichText text={event.text} repair={event.kind === "assistant"} />
        {event.text && (
          <MessageActions
            detail={detail}
            eventId={event.id}
            text={event.text}
            action={event.kind === "assistant" ? action : undefined}
          />
        )}
      </div>
    </article>
  );
}
function Interaction({
  event,
  busy,
  approve,
}: {
  event: SessionEvent;
  busy: boolean;
  approve: (id: string, decision: "allow" | "deny", value?: string) => void;
}) {
  const [value, setValue] = useState(event.prefill || "");
  const method = event.method || "confirm";
  return (
    <section className="approval-event">
      <div className="approval-heading">
        <LockKeyhole size={18} />
        <strong>{event.title || "需要你的回答"}</strong>
      </div>
      <p>{event.text}</p>
      {event.decision ? (
        <span className="approval-result">
          <Check size={14} />
          {event.decision === "deny" ? "已取消" : event.answer || "已确认"}
        </span>
      ) : (
        <>
          {method === "select" && (
            <div className="interaction-options">
              {event.options?.map((option) => (
                <button
                  key={option}
                  className="button"
                  disabled={busy}
                  onClick={() =>
                    event.approvalId &&
                    approve(event.approvalId, "allow", option)
                  }
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          {(method === "input" || method === "editor") && (
            <textarea
              className="interaction-input"
              aria-label="回答"
              value={value}
              placeholder={event.placeholder}
              onChange={(e) => setValue(e.target.value)}
              rows={method === "editor" ? 6 : 2}
            />
          )}
          <div className="approval-actions">
            {method !== "select" && (
              <button
                className="button primary"
                disabled={busy}
                onClick={() =>
                  event.approvalId &&
                  approve(
                    event.approvalId,
                    "allow",
                    method === "confirm" ? undefined : value,
                  )
                }
              >
                {method === "confirm" ? "确认" : "提交回答"}
              </button>
            )}
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                event.approvalId && approve(event.approvalId, "deny")
              }
            >
              取消
            </button>
          </div>
        </>
      )}
    </section>
  );
}

export function ArtifactView({ artifact }: { artifact: Artifact }) {
  function download() {
    const url = URL.createObjectURL(
      new Blob([artifact.content], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = artifact.name.split(/[\\/]/).pop() || "result.txt";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <div className="artifact-toolbar">
        <FileText size={15} />
        <span>{artifact.name}</span>
        <button className="text-button" onClick={download}>
          下载
        </button>
      </div>
      <div className="artifact-content">
        {artifact.kind === "markdown" ? (
          <RichText text={artifact.content} />
        ) : (
          <pre className={artifact.kind}>{artifact.content}</pre>
        )}
      </div>
    </>
  );
}
