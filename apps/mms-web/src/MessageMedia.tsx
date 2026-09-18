import { useEffect, useState } from "react";
import { Paperclip } from "lucide-react";
import { request } from "./api";
import type { Attachment } from "./types";

export function AttachmentView({ attachment }: { attachment: Attachment }) {
  const [url, setUrl] = useState("");
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!attachment.mimeType.startsWith("image/")) return;
    const c = new AbortController();
    request<{ dataUrl: string }>(
      "/attachments/" + attachment.id,
      undefined,
      c.signal,
    )
      .then((d) => setUrl(d.dataUrl))
      .catch(() => {});
    return () => c.abort();
  }, [attachment.id, attachment.mimeType]);
  return url ? (
    <button
      className={"message-image " + (expanded ? "expanded" : "")}
      onClick={() => setExpanded(!expanded)}
      title={expanded ? "缩小图片" : "放大图片"}
    >
      <img src={url} alt={attachment.name} />
      <span>{attachment.name}</span>
    </button>
  ) : (
    <span className="message-file">
      <Paperclip size={14} />
      {attachment.name}
    </span>
  );
}
