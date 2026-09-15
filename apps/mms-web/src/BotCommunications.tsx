import { useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowRight, FileText, LoaderCircle, MessageSquare, X, Zap } from "lucide-react";
import { RichText } from "./components";
import { request } from "./api";
import { PixelAvatar } from "./Bot";
import type { BotDefinition, BotTask } from "./Bot";
import "./bot-communications.css";

export type CommunicationKind = "message" | "dispatch" | "result";
export type CommunicationDeliveryStatus = "queued" | "delivered" | "processed" | "waiting" | "failed";

export interface BotCommunicationArtifact {
  id: string;
  name: string;
  kind?: string;
  url?: string;
}

export interface BotCommunication {
  id: string;
  senderBotId: string;
  recipientBotId: string;
  content: string;
  kind: CommunicationKind;
  createdAt: string;
  replyTo?: string | null;
  taskId?: string | null;
  deliveryTaskId?: string | null;
  deliveryStatus: CommunicationDeliveryStatus;
  waitReason?: string | null;
  artifacts?: BotCommunicationArtifact[];
}

export interface CommunicationTaskGroup {
  taskId: string | null;
  taskTitle: string;
  dateLabel: string;
  latestTimestamp: string;
  messages: BotCommunication[];
}

export interface BotCommunicationsProps {
  bot: BotDefinition;
  bots: BotDefinition[];
  messages: BotCommunication[];
  tasks?: BotTask[];
  peerBotId?: string;
  preview?: boolean;
  error?: string;
  onClose: () => void;
  onRefresh?: () => void;
  onWake?: (message: BotCommunication) => Promise<void> | void;
}

export function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function formatDateOnly(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatCompactTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const now = new Date();
  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  if (isSameDay) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function deliveryLabel(status: CommunicationDeliveryStatus) {
  return status === "queued"
    ? "待投递"
    : status === "delivered"
      ? "已送达"
      : status === "processed"
        ? "已处理"
        : status === "waiting"
          ? "等待继续"
          : "投递失败";
}

export function kindLabel(kind: CommunicationKind) {
  return kind === "dispatch" ? "任务" : kind === "result" ? "结果" : "消息";
}

export function isLongResult(content: string) {
  const lines = content.split(/\r?\n/);
  return lines.length > 6 || content.length > 240;
}

export function groupCommunicationsByDate<T extends { createdAt: string }>(
  items: T[],
): Array<{ date: string; items: T[] }> {
  const groups: Array<{ date: string; items: T[] }> = [];
  const map = new Map<string, T[]>();

  for (const item of items) {
    const date = formatDateOnly(item.createdAt);
    let list = map.get(date);
    if (!list) {
      list = [];
      map.set(date, list);
      groups.push({ date, items: list });
    }
    list.push(item);
  }
  return groups;
}

export function groupCommunicationsByTask(
  messages: BotCommunication[],
  tasks: BotTask[] = [],
  currentBotId?: string,
): CommunicationTaskGroup[] {
  if (!messages || messages.length === 0) return [];

  const taskMap = new Map<string, BotTask>();
  for (const task of tasks) {
    taskMap.set(task.id, task);
  }

  const commMap = new Map<string, BotCommunication>();
  for (const msg of messages) {
    commMap.set(msg.id, msg);
  }

  function getRootComm(msg: BotCommunication): BotCommunication {
    let curr = msg;
    const visited = new Set<string>([curr.id]);
    while (curr.replyTo && commMap.has(curr.replyTo)) {
      if (visited.has(curr.replyTo)) break;
      visited.add(curr.replyTo);
      curr = commMap.get(curr.replyTo)!;
    }
    return curr;
  }

  function resolveRootTask(taskId: string): BotTask | undefined {
    let curr = taskMap.get(taskId);
    if (!curr) return undefined;
    const visited = new Set<string>([curr.id]);
    while (curr.parentTaskId && taskMap.has(curr.parentTaskId)) {
      if (visited.has(curr.parentTaskId)) break;
      visited.add(curr.parentTaskId);
      curr = taskMap.get(curr.parentTaskId)!;
    }
    return curr;
  }

  function getEffectiveTaskId(msg: BotCommunication): string | null {
    const rootComm = getRootComm(msg);
    const candidateTaskIds: string[] = [];
    if (rootComm.taskId) candidateTaskIds.push(rootComm.taskId);
    if (rootComm.deliveryTaskId) candidateTaskIds.push(rootComm.deliveryTaskId);
    if (msg.taskId) candidateTaskIds.push(msg.taskId);
    if (msg.deliveryTaskId) candidateTaskIds.push(msg.deliveryTaskId);

    // Prefer a task belonging to currentBotId and with a prompt
    for (const tid of candidateTaskIds) {
      const t = resolveRootTask(tid);
      if (t && (!currentBotId || t.botId === currentBotId)) return t.id;
    }
    for (const tid of candidateTaskIds) {
      const t = resolveRootTask(tid);
      if (t) return t.id;
    }
    return candidateTaskIds[0] || null;
  }

  const groupMap = new Map<string | null, CommunicationTaskGroup>();

  for (const msg of messages) {
    const effId = getEffectiveTaskId(msg);
    let group = groupMap.get(effId);
    if (!group) {
      let taskTitle = "未关联任务";
      let dateLabel = "";
      let refTime = msg.createdAt;

      if (effId) {
        const task = taskMap.get(effId);
        if (task) {
          const cleanPrompt = (task.prompt || "").trim();
          taskTitle = cleanPrompt ? cleanPrompt.slice(0, 60) : task.id;
          dateLabel = formatDateOnly(task.createdAt || msg.createdAt);
          refTime = task.createdAt || msg.createdAt;
        } else {
          taskTitle = effId;
          dateLabel = formatDateOnly(msg.createdAt);
        }
      } else {
        dateLabel = formatDateOnly(msg.createdAt);
      }

      group = {
        taskId: effId,
        taskTitle,
        dateLabel,
        latestTimestamp: refTime,
        messages: [],
      };
      groupMap.set(effId, group);
    }

    group.messages.push(msg);
    if (msg.createdAt > group.latestTimestamp) {
      group.latestTimestamp = msg.createdAt;
    }
  }

  const groups = Array.from(groupMap.values());
  for (const g of groups) {
    g.messages.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }
  // 最新任务在最上
  groups.sort((a, b) => b.latestTimestamp.localeCompare(a.latestTimestamp));
  return groups;
}

export function BotCommunications({
  bot,
  bots,
  messages,
  tasks: tasksProp,
  peerBotId,
  preview = false,
  error,
  onClose,
  onRefresh,
  onWake,
}: BotCommunicationsProps) {
  const [selectedPeerId, setSelectedPeerId] = useState<string>();
  const [wakingId, setWakingId] = useState<string | null>(null);
  const [expandedResultIds, setExpandedResultIds] = useState<Set<string>>(() => new Set());
  const [loadedTasks, setLoadedTasks] = useState<BotTask[]>(tasksProp || []);

  useEffect(() => {
    if (tasksProp && tasksProp.length > 0) {
      setLoadedTasks(tasksProp);
      return;
    }
    if (preview) return;
    let cancelled = false;
    request<{ tasks: BotTask[] }>("/tasks")
      .then((res) => {
        if (!cancelled && res.tasks) {
          setLoadedTasks(res.tasks);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [tasksProp, preview]);

  const peers = useMemo(() => {
    const ids = new Set<string>();
    for (const message of messages) {
      const peerId = message.senderBotId === bot.id ? message.recipientBotId : message.senderBotId;
      if (peerId && peerId !== bot.id) ids.add(peerId);
    }
    return [...ids]
      .map((id) => bots.find((peer) => peer.id === id))
      .filter((peer): peer is BotDefinition => Boolean(peer));
  }, [bot.id, bots, messages]);

  useEffect(() => {
    if (!peers.length) {
      setSelectedPeerId(undefined);
      return;
    }
    if (peerBotId && peers.some((peer) => peer.id === peerBotId)) {
      setSelectedPeerId(peerBotId);
    } else if (!selectedPeerId || !peers.some((peer) => peer.id === selectedPeerId)) {
      setSelectedPeerId(peers[0].id);
    }
  }, [peerBotId, peers, selectedPeerId]);

  const selectedPeer = peers.find((peer) => peer.id === selectedPeerId);
  const conversation = useMemo(() => {
    if (!selectedPeer) return [];
    return messages
      .filter(
        (message) =>
          (message.senderBotId === bot.id && message.recipientBotId === selectedPeer.id) ||
          (message.senderBotId === selectedPeer.id && message.recipientBotId === bot.id),
      )
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }, [bot.id, messages, selectedPeer]);

  const taskGroups = useMemo(
    () => groupCommunicationsByTask(conversation, loadedTasks, bot.id),
    [conversation, loadedTasks, bot.id],
  );

  function toggleResultExpand(id: string) {
    setExpandedResultIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function wake(message: BotCommunication) {
    if (!onWake || preview || wakingId) return;
    setWakingId(message.id);
    try {
      await onWake(message);
    } finally {
      setWakingId(null);
    }
  }

  return (
    <aside className="bot-communications-panel" aria-label={`${bot.name} 的协作`}>
      <div className="bot-communications-heading">
        <div className="bot-communications-title">
          <span className="bot-communications-icon" aria-hidden="true">
            <MessageSquare size={17} />
          </span>
          <div>
            <h2>协作</h2>
            <p>{bot.name} 与 {selectedPeer ? selectedPeer.name : "其他 Bot 的消息往来"}</p>
          </div>
        </div>
        <button
          className="bot-communications-close"
          type="button"
          onClick={onClose}
          aria-label="关闭协作面板"
          title="关闭"
        >
          <X size={17} />
        </button>
      </div>
      <div className="bot-communications-body">
        {preview && <p className="bot-communications-preview">预览模式：这里展示协作记录，真实读写已禁用。</p>}
        {error && <p className="bot-communications-error" role="alert"><AlertCircle size={15} />{error}</p>}
        {!messages.length && !error && (
          <div className="bot-communications-empty">
            <MessageSquare size={22} />
            <p>还没有协作消息。</p>
          </div>
        )}
        {peers.length > 0 && (
          <nav className="bot-communications-peers" aria-label="协作对象">
            {peers.map((peer) => {
              const peerMessages = messages
                .filter(
                  (m) =>
                    (m.senderBotId === peer.id && m.recipientBotId === bot.id) ||
                    (m.senderBotId === bot.id && m.recipientBotId === peer.id),
                )
                .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
              const latestMsg = peerMessages[peerMessages.length - 1];
              const isSelected = peer.id === selectedPeerId;
              return (
                <button
                  key={peer.id}
                  type="button"
                  className={`bot-communications-peer-btn ${isSelected ? "is-selected" : ""}`}
                  onClick={() => setSelectedPeerId(peer.id)}
                >
                  <PixelAvatar
                    className="bot-communications-peer-avatar"
                    avatarId={peer.avatarId}
                    color={peer.avatarColor}
                    seed={peer.id}
                  />
                  <span className="bot-communications-peer-name">{peer.name}</span>
                  {latestMsg && (
                    <time className="bot-communications-peer-time" dateTime={latestMsg.createdAt}>
                      {formatCompactTime(latestMsg.createdAt)}
                    </time>
                  )}
                </button>
              );
            })}
          </nav>
        )}
        {selectedPeer && conversation.length > 0 && (
          <section
            className="bot-communications-conversation"
            aria-label={`${bot.name} 与 ${selectedPeer.name} 的完整会话`}
          >
            <div className="bot-communications-conversation-heading">
              <strong>{bot.name} <ArrowRight size={12} /> {selectedPeer.name}</strong>
              <span>{conversation.length} 条消息往来</span>
            </div>

            {taskGroups.map((group, groupIdx) => {
              const showDateDivider =
                groupIdx === 0 || group.dateLabel !== taskGroups[groupIdx - 1].dateLabel;
              return (
                <div className="bot-communication-task-group" key={group.taskId || `unlinked-${groupIdx}`}>
                  {showDateDivider && (
                    <div className="bot-communication-date-divider" role="separator">
                      <span>{group.dateLabel}</span>
                    </div>
                  )}
                  <div className="bot-communication-task-header">
                    <span className="bot-communication-task-title">{group.taskTitle}</span>
                    <time className="bot-communication-task-date">{group.dateLabel}</time>
                  </div>
                  <div className="bot-communication-task-messages">
                    {group.messages.map((message) => {
                      const fromCurrent = message.senderBotId === bot.id;
                      const sender = bots.find((item) => item.id === message.senderBotId);
                      const canWake =
                        !fromCurrent &&
                        message.deliveryStatus === "waiting" &&
                        message.recipientBotId === bot.id;
                      const isResult = message.kind === "result";
                      const isCollapsible = isResult && isLongResult(message.content);
                      const isExpanded = expandedResultIds.has(message.id);

                      return (
                        <article
                          className={`bot-communication-message ${fromCurrent ? "from-current" : "from-peer"}`}
                          key={message.id}
                        >
                          <div className="bot-communication-meta">
                            <PixelAvatar
                              className="bot-communication-avatar"
                              avatarId={fromCurrent ? bot.avatarId : sender?.avatarId}
                              color={fromCurrent ? bot.avatarColor : sender?.avatarColor}
                              seed={fromCurrent ? bot.id : sender?.id}
                            />
                            <strong>{fromCurrent ? bot.name : sender?.name || "Bot"}</strong>
                            <span className="bot-communication-meta-sep">·</span>
                            <span className={`bot-communication-kind-tag is-${message.kind}`}>
                              {kindLabel(message.kind)}
                            </span>
                            <span className="bot-communication-meta-sep">·</span>
                            <time dateTime={message.createdAt}>{formatDate(message.createdAt)}</time>
                          </div>
                          <div
                            className={`bot-communication-content ${isCollapsible && !isExpanded ? "is-collapsed" : ""}`}
                          >
                            <RichText text={message.content} repair />
                          </div>
                          {isCollapsible && (
                            <button
                              type="button"
                              className="bot-communication-expand-btn"
                              onClick={() => toggleResultExpand(message.id)}
                            >
                              {isExpanded ? "收起" : "展开全文"}
                            </button>
                          )}
                          {message.artifacts && message.artifacts.length > 0 && (
                            <div className="bot-communication-artifacts">
                              {message.artifacts.map((artifact) =>
                                artifact.url ? (
                                  <a
                                    className="bot-file-preview-trigger"
                                    key={artifact.id}
                                    href={artifact.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    title={artifact.name}
                                  >
                                    <FileText size={15} />
                                    <span>{artifact.name}</span>
                                  </a>
                                ) : (
                                  <div
                                    className="bot-file-preview-trigger"
                                    key={artifact.id}
                                    title={artifact.name}
                                  >
                                    <FileText size={15} />
                                    <span>{artifact.name}</span>
                                  </div>
                                ),
                              )}
                            </div>
                          )}
                          <div className="bot-communication-status">
                            <span className={`bot-communication-delivery is-${message.deliveryStatus}`}>
                              {deliveryLabel(message.deliveryStatus)}
                            </span>
                            {message.waitReason && <span>{message.waitReason}</span>}
                            {canWake && (
                              <button
                                type="button"
                                onClick={() => void wake(message)}
                                disabled={wakingId === message.id || preview}
                              >
                                <Zap size={12} />
                                {wakingId === message.id ? "唤醒中…" : "继续投递"}
                              </button>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        )}
      </div>
    </aside>
  );
}
