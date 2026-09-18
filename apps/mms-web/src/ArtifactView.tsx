import { useEffect, useRef, useState } from "react";
import { Download, FileText, RefreshCw, Quote } from "lucide-react";
import { request, isPreview } from "./api";
import { RichText } from "./components";
import type { Artifact, FileSelection, ImageRegion } from "./types";

interface Version { revision: number; sha256: string; createdAt?: string; source: string }
interface Preview extends Artifact {
  content?: string;
  dataUrl?: string;
  rows?: string[][];
  tableNote?: string;
  versions: Version[];
  diff?: string;
  diffTruncated?: boolean;
  previous?: { revision: number; dataUrl?: string; content?: string };
  downloadData: string;
  mimeType: string;
}

function ImageSelection({ src, name, select, disabled }: { src: string; name: string; select: (region: ImageRegion) => void; disabled: boolean }) {
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [region, setRegion] = useState<ImageRegion | null>(null);
  const image = useRef<HTMLImageElement>(null);
  function point(event: React.PointerEvent) {
    const rect = image.current!.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  }
  return <>
    <p className="section-note">拖选图片中的区域，再引用到输入框。</p>
    <div className="artifact-image-selection"
      onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); setStart(point(event)); setRegion(null); }}
      onPointerMove={event => { if (!start) return; const end = point(event); setRegion({ x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y) }); }}
      onPointerUp={() => setStart(null)} onPointerCancel={() => setStart(null)}>
      <img ref={image} src={src} alt={name} draggable={false} />
      {region && <span className="artifact-image-region" style={{ left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.width * 100}%`, height: `${region.height * 100}%` }} />}
    </div>
    <button type="button" disabled={disabled || !region || region.width < .005 || region.height < .005}
      onClick={() => region && select(region)}><Quote size={14} />引用选区</button>
  </>;
}

type Props = {
  artifact: Artifact; sessionId: string; onSelect: (selection: FileSelection) => void;
};
export function ArtifactView(props: Props) {
  if (isPreview) return <section className="artifact-view"><p className="section-note">示例成果，未写入工作文件夹。</p><div className="artifact-content"><RichText text={props.artifact.demoContent || ""} /></div></section>;
  return <RecordedArtifactView {...props} />;
}
function RecordedArtifactView({ artifact, sessionId, onSelect }: Props) {
  const [version, setVersion] = useState<number>();
  const [compare, setCompare] = useState<number>();
  const [mode, setMode] = useState<"preview" | "source">("preview");
  const [data, setData] = useState<Preview>();
  const [quote, setQuote] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const content = useRef<HTMLDivElement>(null);
  const requestedVersion = version ?? artifact.revision;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setQuote("");
    request<Preview>(`/sessions/${encodeURIComponent(sessionId)}/artifacts`, {
      id: artifact.id, revision: requestedVersion, ...(compare !== undefined ? { compare } : {}),
    }, controller.signal).then(setData).catch(e => {
      if (!controller.signal.aborted) { setError(e.message); setData(undefined); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [sessionId, artifact.id, artifact.sha256, artifact.status, requestedVersion, compare, revision]);
  function choose(selection: Pick<FileSelection, "quote" | "region">) {
    if (!data || data.status !== "current" || loading) return;
    onSelect({ artifactId: data.id, path: data.path, revision: data.revision, sha256: data.sha256, ...selection });
    setQuote("");
  }
  function selectText() {
    if (mode !== "source" && data?.kind !== "text") return;
    const selected = window.getSelection();
    if (!selected || !content.current?.contains(selected.anchorNode) || !content.current.contains(selected.focusNode)) return;
    const text = selected.toString().trim();
    setQuote(text.length <= 8000 ? text : "");
    if (text.length > 8000) setError("一次最多引用 8,000 个字符，请缩小选段。");
  }
  function download() {
    if (!data) return;
    const bytes = Uint8Array.from(atob(data.downloadData), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: data.mimeType }));
    const link = document.createElement("a"); link.href = url; link.download = data.name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const older = data?.versions.filter(v => v.revision !== data.revision) || [];
  return <section className="artifact-view" aria-label="成果预览">
    <div className="artifact-toolbar">
      <FileText size={15} /><strong title={artifact.path}>{artifact.name}</strong>
      <button type="button" aria-label="刷新成果" onClick={() => setRevision(r => r + 1)}><RefreshCw size={14} /></button>
      <button type="button" disabled={!data || loading} onClick={download}><Download size={14} />下载</button>
    </div>
    <p className="artifact-path">{artifact.path}</p>
    <div className="artifact-version-toolbar">
      <label>版本<select aria-label="成果版本" value={requestedVersion} onChange={event => { setVersion(Number(event.target.value)); setCompare(undefined); }}>
        <option value={0}>当前文件</option>
        {(data?.versions || []).map(v => <option key={v.revision} value={v.revision}>v{v.revision}{v.revision === artifact.revision ? " · 最近记录" : ""}</option>)}
      </select></label>
      {!!older.length && <label>比较<select aria-label="比较成果版本" value={compare ?? ""} onChange={event => setCompare(event.target.value === "" ? undefined : Number(event.target.value))}>
        <option value="">不比较</option>
        {older.map(v => <option value={v.revision} key={v.revision}>与 v{v.revision} 比较</option>)}
      </select></label>}
    </div>
    {error && <p role="alert" className="inline-error">{error}</p>}
    {loading && <p role="status" className="section-note">正在读取成果…</p>}
    {data && <>
      <div className="artifact-state" role="status">
        <span>{({ current: "与原文件一致", changed: "原文件已变化，当前显示已记录版本", missing: "原文件已删除，仍可查看已记录版本", unavailable: "原文件暂时无法访问，当前显示已记录版本" })[data.status]}</span>
        {data.status === "changed" && <button type="button" onClick={() => { setVersion(0); setCompare(data.revision || undefined); }}>查看当前文件</button>}
      </div>
      <p className="artifact-provenance">{data.source === "observed" ? "命令执行期间观察到文件变化" : data.source === "tool" ? "文件工具完成后记录" : "当前文件，未记录历史时间"} · {data.sha256.slice(0, 12)}</p>
      {compare === undefined && data.kind !== "image" && <div className="artifact-mode">
        <button type="button" className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}>预览</button>
        <button type="button" className={mode === "source" ? "active" : ""} onClick={() => setMode("source")}>原文 / 选段修改</button>
        <button type="button" disabled={!quote || data.status !== "current" || loading} onClick={() => choose({ quote })}><Quote size={14} />引用选段</button>
      </div>}
      {compare === undefined && data.kind !== "image" && <p className="section-note">在原文中选中文字，再引用到输入框提出修改。</p>}
      <div ref={content} className="artifact-content" onMouseUp={selectText} onKeyUp={selectText}>
        {compare !== undefined ? data.previous ? <div className="artifact-image-compare">
          <figure><figcaption>v{data.previous.revision}</figcaption><img src={data.previous.dataUrl} alt="较早版本" /></figure>
          <figure><figcaption>{data.revision ? `v${data.revision}` : "当前文件"}</figcaption><img src={data.dataUrl} alt="所选版本" /></figure>
        </div> : <><pre className="artifact-diff">{data.diff || "两个版本的文本内容一致。"}</pre>{data.diffTruncated && <p className="section-note">差异较长，当前显示前 200,000 字符。</p>}</>
        : data.kind === "image" ? <ImageSelection key={data.sha256} src={data.dataUrl!} name={data.name} select={region => choose({ region })} disabled={data.status !== "current" || loading} />
        : mode === "source" || data.kind === "text" ? <pre>{data.content}</pre>
        : data.kind === "markdown" ? <RichText text={data.content || ""} />
        : data.kind === "csv" ? <><div className="artifact-table"><table><tbody>{data.rows?.map((row, index) => <tr key={index}>{row.map((cell, column) => index ? <td key={column}>{cell}</td> : <th key={column}>{cell}</th>)}</tr>)}</tbody></table></div><p className="section-note">{data.tableNote}</p></>
        : <><p className="section-note">静态预览：脚本、外部资源与链接跳转均停用。</p><iframe className="artifact-html" title={`${data.name} 静态预览`} sandbox="" referrerPolicy="no-referrer"
          src={`/api/v1/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(data.id)}/preview/${data.revision}`} /></>}
      </div>
      {!!quote && compare === undefined && <blockquote className="artifact-quote">{quote.length > 180 ? quote.slice(0, 180) + "…" : quote}</blockquote>}
    </>}
  </section>;
}
