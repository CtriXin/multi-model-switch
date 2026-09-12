import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import { Download, FileText, X } from "lucide-react";
import { RichText } from "./components";
import type { BotArtifact } from "./Bot";
import { artifactContentUrl, decodePreviewText, parseDelimited, PREVIEW_BYTE_LIMIT, previewType, TEXT_BYTE_LIMIT, TEXT_DISPLAY_LIMIT, readPreviewBytes } from "./bot-artifact-preview";

type Props = { artifact: BotArtifact; onClose: () => void };

export function BotArtifactPreview({ artifact, onClose }: Props) {
  const [state, setState] = useState<{ status: "loading" | "ready" | "error"; text?: string; url?: string; message?: string }>({ status: "loading" });
  const type = previewType(artifact);
  const contentUrl = artifactContentUrl(artifact.url, window.location.origin);
  useEffect(() => {
    let objectUrl = "";
    const controller = new AbortController();
    if (!contentUrl || type.kind === "html" || type.kind === "unsupported") {
      setState({ status: "ready" });
      return () => controller.abort();
    }
    void fetch(contentUrl, { credentials: "same-origin", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("文件暂时无法读取，请稍后重试。");
        return readPreviewBytes(response, type.kind === "text" || type.kind === "markdown" || type.kind === "csv" || type.kind === "json" ? TEXT_BYTE_LIMIT : PREVIEW_BYTE_LIMIT);
      })
      .then((bytes) => {
        if (type.kind === "text" || type.kind === "markdown" || type.kind === "csv" || type.kind === "json") {
          const text = decodePreviewText(bytes);
          setState({ status: "ready", text: text.slice(0, TEXT_DISPLAY_LIMIT) });
        } else {
          const buffer = new ArrayBuffer(bytes.byteLength);
          new Uint8Array(buffer).set(bytes);
          objectUrl = URL.createObjectURL(new Blob([buffer], { type: type.mime }));
          setState({ status: "ready", url: objectUrl });
        }
      })
      .catch((error) => { if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "文件预览失败。" }); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [contentUrl, type.kind, type.mime]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  const closeOnBackdrop = (event: MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) onClose(); };
  const htmlUrl = contentUrl.replace(/\/content$/, "/preview");
  const title = artifact.name;
  return (
    <div className="bot-artifact-lightbox" role="dialog" aria-modal="true" aria-label={`预览 ${title}`} onMouseDown={closeOnBackdrop}>
      <div className={`bot-artifact-lightbox-card bot-preview-${type.kind}`}>
        <header className="bot-artifact-lightbox-toolbar">
          <span><FileText size={15} />{title}</span>
          <div>
            <a className="bot-preview-download" href={artifact.url} download={artifact.name} title="下载文件"><Download size={15} />下载</a>
            <button type="button" className="bot-icon-button" onClick={onClose} aria-label="关闭预览"><X size={17} /></button>
          </div>
        </header>
        <div className="bot-artifact-preview-body">
          {state.status === "loading" && <p className="bot-preview-state">正在读取文件…</p>}
          {state.status === "error" && <p className="bot-preview-state bot-preview-error">{state.message}</p>}
          {state.status === "ready" && type.kind === "unsupported" && <div className="bot-preview-state"><strong>这个文件没有适合的内置预览</strong><span>可以下载后用本地应用打开。</span></div>}
          {state.status === "ready" && type.kind === "html" && <iframe className="bot-artifact-preview-frame" title={`${title} 预览`} sandbox="" referrerPolicy="no-referrer" src={htmlUrl} />}
          {state.status === "ready" && type.kind === "image" && state.url && <img className="bot-artifact-preview-media" src={state.url} alt={title} />}
          {state.status === "ready" && type.kind === "pdf" && state.url && <iframe className="bot-artifact-preview-frame" title={`${title} PDF 预览`} src={state.url} />}
          {state.status === "ready" && (type.kind === "audio" || type.kind === "video") && state.url && (type.kind === "audio" ? <audio className="bot-artifact-preview-audio" controls src={state.url} /> : <video className="bot-artifact-preview-video" controls src={state.url} />)}
          {state.status === "ready" && (type.kind === "text" || type.kind === "json") && <pre className="bot-artifact-preview-text">{type.kind === "json" ? (() => { try { return JSON.stringify(JSON.parse(state.text || ""), null, 2); } catch { return state.text; } })() : state.text}</pre>}
          {state.status === "ready" && type.kind === "markdown" && <div className="bot-artifact-preview-markdown"><RichText text={state.text || ""} /></div>}
          {state.status === "ready" && type.kind === "csv" && <div className="bot-artifact-preview-table"><table><tbody>{parseDelimited(state.text || "", artifact.name.toLowerCase().endsWith(".tsv") ? "\t" : ",").rows.map((row, i) => <tr key={i}>{row.map((cell, j) => j === 0 ? <th key={j}>{cell}</th> : <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>}
        </div>
      </div>
    </div>
  );
}
