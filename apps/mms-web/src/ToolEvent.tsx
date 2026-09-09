import {
  Check,
  ChevronRight,
  CircleAlert,
  FileText,
  ListChecks,
  LoaderCircle,
  Pencil,
  Square,
  Terminal,
} from "lucide-react";
import { AttachmentView } from "./MessageMedia";
import type { SessionDetail, SessionEvent } from "./types";

export function toolSummary(event: SessionEvent) {
  const args = event.arguments || {};
  const name = event.title || "Tool";
  const lower = name.toLowerCase();
  const candidate = [
    args.command,
    args.cmd,
    args.path,
    args.file_path,
    args.filePath,
    args.query,
    args.pattern,
    args.url,
    args.description,
  ].find((v) => typeof v === "string" && v.trim());
  const items = args.todos || args.items;
  const fullSummary =
    typeof candidate === "string"
      ? candidate.replace(/\s+/g, " ").trim()
      : Array.isArray(items)
        ? `${items.length} 项`
        : Object.keys(args).length
          ? Object.entries(args)
              .map(
                ([k, v]) =>
                  `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`,
              )
              .join(" · ")
          : "";
  // Show the operation before a repeated working-directory prefix. This is
  // display-only: never parse/execute or rewrite the command sent to the tool.
  const command = args.command ?? args.cmd;
  const summary =
    typeof command === "string" && candidate === command
      ? command
          .replace(
            /^cd[ \t]+(?:"[^"$`\r\n]+"|'[^'\r\n]+'|[^;&|$`()\r\n]+?)[ \t]*&&[ \t]*/,
            "",
          )
          .replace(/\s+/g, " ")
          .trim() || fullSummary
      : fullSummary;
  const Icon = /bash|shell|exec|terminal/.test(lower)
    ? Terminal
    : /todo|plan/.test(lower)
      ? ListChecks
      : /edit|write|patch/.test(lower)
        ? Pencil
        : FileText;
  return { name, summary, fullSummary, Icon };
}

export function ToolEvent({
  event,
  detail,
  disconnected = false,
}: {
  event: SessionEvent;
  detail: SessionDetail;
  disconnected?: boolean;
}) {
  const { name, summary, fullSummary, Icon } = toolSummary(event);
  const running =
    !disconnected &&
    detail.session.state === "running" &&
    event.status === "running";
  const status = running
    ? "执行中"
    : event.status === "running"
      ? "状态未同步"
      : event.status === "error"
        ? "失败或已停止"
        : event.status === "done"
          ? "已完成"
          : "状态未知";
  return (
    <details
      className={`tool-event ${event.status || "unknown"}`}
      data-event-id={event.id}
    >
      <summary title={`${name}${fullSummary ? " · " + fullSummary : ""}`}>
        <Icon size={15} className="tool-kind" />
        <strong className="tool-name">{name}</strong>
        <span className="tool-summary">{summary || "查看参数与结果"}</span>
        <span className="tool-result" aria-label={status} title={status}>
          {running ? (
            <LoaderCircle size={14} className="spin" />
          ) : event.status === "running" ? (
            <Square size={12} />
          ) : event.status === "error" ? (
            <CircleAlert size={14} />
          ) : event.status === "done" ? (
            <Check size={15} />
          ) : (
            <span>—</span>
          )}
        </span>
        <ChevronRight size={14} className="tool-chevron" />
      </summary>
      <div className="tool-expanded">
        {event.arguments && (
          <details className="tool-input">
            <summary>完整参数</summary>
            <pre>{JSON.stringify(event.arguments, null, 2)}</pre>
          </details>
        )}
        <div className="tool-output-label">{status} · 输出</div>
        {event.text ? (
          <pre tabIndex={0} aria-label={`${name} 输出`}>
            {event.text}
          </pre>
        ) : (
          <p className="tool-empty">
            {running ? "等待工具输出…" : "工具没有返回文本。"}
          </p>
        )}
        {event.attachments?.map((a) => (
          <AttachmentView key={a.id} attachment={a} />
        ))}
      </div>
    </details>
  );
}

export function ToolGroup({
  events,
  detail,
  disconnected,
}: {
  events: SessionEvent[];
  detail: SessionDetail;
  disconnected: boolean;
}) {
  const running =
    !disconnected &&
    detail.session.state === "running" &&
    events.some((e) => e.status === "running");
  const failed = events.some((e) => e.status === "error");
  const done = events.filter((e) => e.status === "done").length;
  const label = running
    ? `执行中 · ${done}/${events.length}`
    : failed
      ? "有操作失败或停止"
      : done === events.length
        ? "已完成"
        : "状态未同步";
  return (
    <details
      className="tool-group"
      open
      data-status={
        running
          ? "running"
          : failed
            ? "error"
            : done === events.length
              ? "done"
              : "unknown"
      }
    >
      <summary className="tool-group-heading">
        <span className="tool-group-dot" />
        <ListChecks size={15} />
        <strong>{events.length} 项操作</strong>
        <span className="tool-group-status">{label}</span>
        <ChevronRight size={14} />
      </summary>
      <div className="tool-group-items">
        {events.map((event) => (
          <ToolEvent
            key={event.id}
            event={event}
            detail={detail}
            disconnected={disconnected}
          />
        ))}
      </div>
    </details>
  );
}
