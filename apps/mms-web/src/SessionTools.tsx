import { useRef, useState } from "react";
import {
  Archive,
  Copy,
  Download,
  GitBranch,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { request } from "./api";
import { RecipeExport } from "./Recipe";
import type { SessionDetail } from "./types";

type Action = (
  path: string,
  payload: Record<string, unknown>,
  open?: boolean,
) => Promise<boolean>;
export function exportConversation(detail: SessionDetail) {
  const text =
    `# ${detail.session.title}\n\n` +
    detail.events
      .map(
        (e) =>
          `## ${e.kind === "user" ? "你" : e.kind === "assistant" ? detail.session.harness : e.title || e.kind}\n\n${e.thinking ? `<details><summary>Thinking</summary>\n\n${e.thinking}\n\n</details>\n\n` : ""}${e.text}\n`,
      )
      .join("\n");
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/markdown;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download =
    (detail.session.title.replace(/[\\/:*?"<>|]/g, "-").slice(0, 80) ||
      "conversation") + ".md";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function SessionMenu({
  detail,
  action,
  busy,
}: {
  detail: SessionDetail;
  action: Action;
  busy: boolean;
}) {
  const menuRef = useRef<HTMLDetailsElement>(null);
  const [rename, setRename] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [name, setName] = useState("");
  const path = "/sessions/" + detail.session.id;
  const active = ["running", "waiting"].includes(detail.session.state);
  const lastUser = [...detail.events].reverse().find((e) => e.kind === "user");
  return (
    <div className="session-menu-wrap">
      {sharing && <RecipeExport detail={detail} close={() => setSharing(false)} />}
      {rename && (
        <form
          className="rename-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await action(path + "/manage", { title: name }))
              setRename(false);
          }}
        >
          <input
            autoFocus
            aria-label="会话名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
          />
          <button disabled={busy}>保存</button>
          <button type="button" onClick={() => setRename(false)}>
            取消
          </button>
        </form>
      )}
      <details
        className="session-menu"
        ref={menuRef}
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("button") && menuRef.current)
            menuRef.current.open = false;
        }}
      >
        <summary aria-label="会话操作">
          <MoreHorizontal size={18} />
        </summary>
        <div>
          <button
            onClick={() => {
              setName(detail.session.title);
              setRename(true);
            }}
          >
            <Pencil size={14} />
            重命名
          </button>
          <button
            disabled={active || busy}
            onClick={() => void action(path + "/fork", {}, true)}
          >
            <GitBranch size={14} />
            创建会话分支
          </button>
          {detail.session.state === "error" && lastUser && (
            <button
              disabled={busy || !detail.session.capabilities.send}
              onClick={() =>
                void action(path + "/messages", {
                  text: lastUser.text,
                  attachments: (lastUser.attachments || []).map((a) => a.id),
                  references: lastUser.references || [],
                })
              }
            >
              <RefreshCw size={14} />
              重试最后一条消息
            </button>
          )}
          <button
            onClick={() => setSharing(true)}
            title="编辑目标、示例和需求，检查导出内容后下载模板。"
          >
            <Copy size={14} />
            保存为任务模板
          </button>
          <button onClick={() => exportConversation(detail)}>
            <Download size={14} />
            导出对话
          </button>
          <button
            disabled={active || busy}
            onClick={() =>
              void action(path + "/manage", {
                archived: !detail.session.archived,
              })
            }
          >
            <Archive size={14} />
            {detail.session.archived ? "恢复到列表" : "归档会话"}
          </button>
        </div>
      </details>
    </div>
  );
}
export function RuntimeStrip({
  detail,
  show,
}: {
  detail: SessionDetail;
  show: () => void;
}) {
  const r = detail.runtime;
  const usage = r?.stats?.contextUsage;
  return (
    <div className="runtime-strip">
      {r?.planning && (
        <button className="planning-label" onClick={show}>
          只读规划中
        </button>
      )}
      <button onClick={show} title="查看模型、Thinking、上下文与运行参数">
        <Settings2 size={13} />
        {r?.thinkingLevel ? `Thinking · ${r.thinkingLevel}` : "运行参数"}
      </button>
      {usage && (
        <button onClick={show}>
          上下文{" "}
          {usage.percent == null ? "待更新" : usage.percent.toFixed(1) + "%"}
          <span className="usage-meter">
            <i
              style={{
                width: Math.max(0, Math.min(100, usage.percent || 0)) + "%",
              }}
            />
          </span>
        </button>
      )}
      {!!r?.pendingMessageCount && (
        <button onClick={show}>排队 {r.pendingMessageCount}</button>
      )}
      {r?.isCompacting && <span role="status">正在压缩上下文…</span>}
    </div>
  );
}
export function RuntimePanel({
  detail,
  action,
  busy,
}: {
  detail: SessionDetail;
  action: Action;
  busy: boolean;
}) {
  const r = detail.runtime || {};
  const [diagnostic, setDiagnostic] = useState("");
  const stats = r.stats;
  const tokens = stats?.tokens;
  const locked = busy || ["running", "waiting"].includes(detail.session.state);
  const control = (name: string, value?: unknown) =>
    action(`/sessions/${detail.session.id}/control`, { action: name, value });
  const levels = r.supportedThinkingLevels || [
    "off",
    "minimal",
    "low",
    "medium",
    "high",
  ];
  return (
    <div className="runtime-details">
      <h3>当前运行</h3>
      <p className="section-note">
        {r.alive ? "执行进程已连接" : "进程未运行，发送消息时恢复原上下文"}
        {r.cached ? " · 以下用量为上次记录" : ""}
        {r.stale ? " · 运行信息暂未更新" : ""}
      </p>
      <dl>
        {[
          ["执行工具", detail.session.harness],
          ["模型", detail.session.modelName],
          ["模型服务", detail.session.providerName],
          ["通道", detail.session.channel],
          ["请求协议", r.model?.api || "尚未读取"],
          ["工作文件夹", detail.session.cwd || r.cwd],
          ["会话 ID", detail.session.id],
        ].map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <h3>运行参数</h3>
      <p className="section-note">
        只改变当前会话，由 Pi 验证参数。MMS 的路由和账号配置保持原值。
      </p>
      <label className="runtime-setting">
        工作模式
        <select
          aria-label="工作模式"
          value={r.planning ? "plan" : "execute"}
          disabled={locked}
          onChange={(e) => void control("plan", e.target.value === "plan")}
        >
          <option value="execute">执行任务</option>
          <option value="plan">只读规划</option>
        </select>
      </label>
      <p className="section-note">
        只读规划允许阅读、查找资料，阻止写入和命令执行。切回执行后才能修改文件。
      </p>
      <label className="runtime-setting">
        Thinking{" "}
        <select
          aria-label="Thinking 等级"
          value={r.thinkingLevel || ""}
          disabled={locked || !r.model?.reasoning}
          onChange={(e) => void control("thinking", e.target.value)}
        >
          <option value="" disabled>
            尚未读取
          </option>
          {[
            ...new Set([
              ...levels,
              ...(r.thinkingLevel ? [r.thinkingLevel] : []),
            ]),
          ].map((level) => (
            <option key={level}>{level}</option>
          ))}
        </select>
      </label>
      {!r.model?.reasoning && (
        <p className="section-note">当前模型没有声明可调 Thinking 能力。</p>
      )}
      <label className="runtime-setting">
        自动压缩上下文
        <input
          aria-label="自动压缩上下文"
          type="checkbox"
          checked={!!r.autoCompactionEnabled}
          disabled={locked || r.autoCompactionEnabled === undefined}
          onChange={(e) => void control("autoCompaction", e.target.checked)}
        />
      </label>
      <label className="runtime-setting">
        失败后自动重试
        <select
          aria-label="失败后自动重试"
          value={
            r.autoRetryEnabled === undefined ? "" : String(r.autoRetryEnabled)
          }
          disabled={locked}
          onChange={(e) => void control("autoRetry", e.target.value === "true")}
        >
          <option value="" disabled>
            使用执行工具原值
          </option>
          <option value="true">开启</option>
          <option value="false">关闭</option>
        </select>
      </label>
      <button
        className="secondary-button"
        disabled={locked}
        onClick={() => void control("compact")}
      >
        <RefreshCw size={14} />
        现在压缩上下文
      </button>
      {locked && (
        <p className="section-note">当前任务结束后可以调整这些参数。</p>
      )}
      <h3>用量与缓存</h3>
      {tokens ? (
        <dl>
          {[
            ["输入 Token", tokens.input],
            ["输出 Token", tokens.output],
            ["缓存读取", tokens.cacheRead],
            ["缓存写入", tokens.cacheWrite],
            ["累计 Token", tokens.total],
            ["工具调用", stats?.toolCalls],
          ].map(([key, value]) => (
            <div key={String(key)}>
              <dt>{key}</dt>
              <dd>
                {typeof value === "number" ? value.toLocaleString() : "未报告"}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="section-note">执行工具尚未报告用量。</p>
      )}
      {stats?.contextUsage && (
        <p className="section-note">
          当前上下文：
          {stats.contextUsage.tokens?.toLocaleString() || "压缩后待更新"} /{" "}
          {stats.contextUsage.contextWindow.toLocaleString()} Token
        </p>
      )}
      {stats?.cost != null && (
        <p className="section-note">
          Pi 报告费用：${stats.cost.toFixed(5)}。以模型服务的实际账单为准。
        </p>
      )}
      {!!r.pendingMessageCount && (
        <>
          <h3>待发送消息 · {r.pendingMessageCount}</h3>
          <ol className="queued-messages">
            {r.queue?.map((message, i) => (
              <li key={i}>{message.slice(0, 500)}</li>
            ))}
          </ol>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void control("clearQueue")}
          >
            清空待发送队列
          </button>
        </>
      )}
      <details className="diagnostic-details">
        <summary
          onClick={() => {
            void request<Record<string, unknown>>(
              `/sessions/${detail.session.id}/diagnostics`,
            )
              .then((data) => setDiagnostic(JSON.stringify(data, null, 2)))
              .catch((e) => setDiagnostic(e.message));
          }}
        >
          进程与诊断信息
        </summary>
        <pre>{diagnostic || "正在读取…"}</pre>
        <p className="section-note">
          仅展示当前会话的状态和脱敏日志，不显示 API Key 或完整环境变量。
        </p>
      </details>
    </div>
  );
}
export function MessageActions({
  detail,
  eventId,
  text,
  action,
}: {
  detail: SessionDetail;
  eventId: string;
  text: string;
  action?: Action;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  return (
    <div className="message-action-slot">
      <div className="message-actions">
        <button
          title="复制 Markdown 原文"
          aria-label={copied ? "已复制" : "复制"}
          onClick={() => {
            setError("");
            void navigator.clipboard
              .writeText(text)
              .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              })
              .catch(() => setError("复制失败，请选择文字后复制。"));
          }}
        >
          <Copy size={13} />
          <span role="status">{copied ? "已复制" : "复制"}</span>
        </button>
        {action && (
          <button
            disabled={["running", "waiting"].includes(detail.session.state)}
            onClick={() =>
              void action(
                `/sessions/${detail.session.id}/fork`,
                { eventId },
                true,
              )
            }
          >
            <GitBranch size={13} />
            从这里分支
          </button>
        )}
        {error && <small role="alert">{error}</small>}
      </div>
    </div>
  );
}
