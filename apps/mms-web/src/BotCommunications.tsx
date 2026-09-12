import { useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowRight, FileText, LoaderCircle, MessageSquare, X, Zap } from "lucide-react";
import { RichText } from "./components";
import type { BotDefinition } from "./Bot";
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

interface BotCommunicationsProps {
  bot: BotDefinition;
  bots: BotDefinition[];
  messages: BotCommunication[];
  peerBotId?: string;
  preview?: boolean;
  error?: string;
  onClose: () => void;
  onRefresh?: () => void;
  onWake?: (message: BotCommunication) => Promise<void> | void;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function deliveryLabel(status: CommunicationDeliveryStatus) {
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

function kindLabel(kind: CommunicationKind) {
  return kind === "dispatch" ? "任务" : kind === "result" ? "结果" : "消息";
}

export function BotCommunications({
  bot,
  bots,
  messages,
  peerBotId,
  preview = false,
  error,
  onClose,
  onRefresh,
  onWake,
}: BotCommunicationsProps) {
  const [selectedPeerId, setSelectedPeerId] = useState<string>();
  const [wakingId, setWakingId] = useState<string | null>(null);
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
  const conversation = selectedPeer
    ? messages
        .filter(
          (message) =>
            (message.senderBotId === bot.id && message.recipientBotId === selectedPeer.id) ||
            (message.senderBotId === selectedPeer.id && message.recipientBotId === bot.id),
        )
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    : [];

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
          <span className="bot-communications-icon" aria-hidden="true"><MessageSquare size={17} /></span>
          <div>
            <h2>协作</h2>
            <p>{bot.name} 与其他 Bot 的消息往来</p>
          </div>
        </div>
        <button className="bot-communications-close" type="button" onClick={onClose} aria-label="关闭协作面板" title="关闭"><X size={17} /></button>
      </div>
      <div className="bot-communications-body">
        {preview && <p className="bot-communications-preview">预览模式：这里展示协作记录，真实读写已禁用。</p>}
        {error && <p className="bot-communications-error" role="alert"><AlertCircle size={15} />{error}</p>}
        {!messages.length && !error && <div className="bot-communications-empty"><MessageSquare size={22} /><p>还没有协作消息。</p></div>}
        {peers.length > 0 && (
          <nav className="bot-communications-peers" aria-label="协作对象">
            {peers.map((peer) => {
              const count = messages.filter((message) => message.senderBotId === peer.id || message.recipientBotId === peer.id).length;
              return <button key={peer.id} type="button" className={peer.id === selectedPeerId ? "is-selected" : ""} onClick={() => setSelectedPeerId(peer.id)}><span className="bot-communications-peer-avatar"><MessageSquare size={13} /></span><span>{peer.name}</span><small>{count}条</small></button>;
            })}
          </nav>
        )}
        {selectedPeer && conversation.length > 0 && (
          <section className="bot-communications-conversation" aria-label={`${bot.name} 与 ${selectedPeer.name} 的完整会话`}>
            <div className="bot-communications-conversation-heading"><strong>{bot.name} <ArrowRight size={12} /> {selectedPeer.name}</strong><span>{conversation.length} 条消息往来</span></div>
            {conversation.map((message) => {
              const fromCurrent = message.senderBotId === bot.id;
              const sender = bots.find((item) => item.id === message.senderBotId);
              const canWake = !fromCurrent && message.deliveryStatus === "waiting" && message.recipientBotId === bot.id;
              return (
                <article className={`bot-communication-message ${fromCurrent ? "from-current" : "from-peer"}`} key={message.id}>
                  <div className="bot-communication-meta">
                    <strong>{fromCurrent ? bot.name : sender?.name || "Bot"}</strong>
                    <span className="bot-communication-meta-sep">·</span>
                    <span>{kindLabel(message.kind)}</span>
                    <span className="bot-communication-meta-sep">·</span>
                    <time dateTime={message.createdAt}>{formatDate(message.createdAt)}</time>
                  </div>
                  <div className="bot-communication-content">
                    <RichText text={message.content} repair />
                  </div>
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
          </section>
        )}
      </div>
    </aside>
  );
}
