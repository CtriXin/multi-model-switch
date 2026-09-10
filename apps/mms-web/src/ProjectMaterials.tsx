import { useEffect, useState } from "react";
import { BookOpen, Plus, RefreshCw } from "lucide-react";
import { request } from "./api";
import { Dialog } from "./components";

interface Material {
  id: string; title: string; content: string; enabled: boolean; revision: number;
  sha256: string; updatedAt: string; confirmedAt: string;
}
interface Snapshot { workspace: string; revision: number; items: Material[] }
const emptyDraft = { title: "", content: "", enabled: true };

export function ProjectMaterials({ workspaceId }: { workspaceId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Snapshot>();
  const [draft, setDraft] = useState({ ...emptyDraft, id: "" });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleteId, setDeleteId] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    request<Snapshot>("/project-materials", { workspaceId }, controller.signal).then(setData).catch(e => {
      if (!controller.signal.aborted) setError(e.message);
    });
    return () => controller.abort();
  }, [workspaceId]);
  async function refresh() {
    setBusy(true); setError("");
    try { setData(await request<Snapshot>("/project-materials", { workspaceId })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function change(action: "save" | "delete", value: Partial<Material>) {
    if (!data || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await request<Snapshot>("/project-materials/change", {
        workspaceId, revision: data.revision, action, confirmed: true, ...value,
      });
      setData(saved); setDeleteId("");
      if (action === "delete" || !value.id || value.id === draft.id) setEditing(false);
      setNotice(action === "delete" ? "资料已删除，后续消息不会再次加入。" : "已保存，从下一条消息开始使用当前启用的资料。");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const enabled = data?.items.filter(item => item.enabled).length;
  return <>
    <button type="button" className="materials-access" onClick={() => { setOpen(true); void refresh(); }}>
      <BookOpen size={14} />项目资料{enabled ? <span>{enabled} 条启用</span> : null}
    </button>
    {open && <Dialog title="项目资料" close={() => setOpen(false)} dismissible={!busy}>
      <section className="project-materials">
        <p className="section-note">保存项目背景、写作要求或常用约定。启用后会加入这个工作文件夹的每条新消息。</p>
        <p className="materials-workspace">{data?.workspace}</p>
        <p className="section-note">停用或删除只影响后续消息；已经发送的内容仍在原会话历史中。</p>
        <div className="materials-toolbar">
          <button type="button" disabled={busy || !data} onClick={() => { setDraft({ ...emptyDraft, id: "" }); setEditing(true); setNotice(""); }}><Plus size={14} />添加资料</button>
          <button type="button" disabled={busy} onClick={() => void refresh()}><RefreshCw size={14} />刷新列表</button>
          <span>{data?.items.length || 0} / 20 条</span>
        </div>
        {error && <p className="inline-error" role="alert">{error}</p>}
        {notice && <p className="section-note" role="status">{notice}</p>}
        <div className={`materials-layout${editing ? " editing" : ""}`}>
          <div className="materials-list">
            {data && !data.items.length && <p className="section-note">还没有保存项目资料。只有你明确保存的内容才会加入后续消息。</p>}
            {data?.items.map(item => <article key={item.id} className={draft.id === item.id && editing ? "active" : ""}>
              <strong>{item.title}</strong><span className="material-enabled">{item.enabled ? "已启用" : "已停用"}</span>
              <p>{item.content.slice(0, 110)}{item.content.length > 110 ? "…" : ""}</p>
              <small>手动保存 · v{item.revision} · {new Date(item.updatedAt).toLocaleString()}</small>
              <div>
                <button type="button" disabled={busy} aria-label={`编辑资料 ${item.title}`} onClick={() => { setDraft({ id: item.id, title: item.title, content: item.content, enabled: item.enabled }); setEditing(true); setNotice(""); }}>编辑</button>
                <button type="button" disabled={busy} aria-label={`${item.enabled ? "停用" : "启用"}资料 ${item.title}`} onClick={() => void change("save", { id: item.id, title: item.title, content: item.content, enabled: !item.enabled })}>{item.enabled ? "停用" : "启用"}</button>
                <button type="button" disabled={busy} aria-label={`删除资料 ${item.title}`} onClick={() => setDeleteId(item.id)}>删除</button>
              </div>
              {deleteId === item.id && <div className="material-delete-confirm" role="group" aria-label={`确认删除资料 ${item.title}`}>
                <p>删除后不再加入新消息，已发送内容仍保留在会话历史中。</p>
                <button type="button" disabled={busy} onClick={() => setDeleteId("")}>保留资料</button>
                <button type="button" disabled={busy} onClick={() => void change("delete", { id: item.id })}>确认删除</button>
              </div>}
            </article>)}
          </div>
          {editing && <form className="material-editor" onSubmit={event => { event.preventDefault(); void change("save", { ...draft, ...(draft.id ? {} : { id: undefined }) }); }}>
            <label>标题<input aria-label="资料标题" maxLength={80} value={draft.title} disabled={busy} onChange={event => setDraft({ ...draft, title: event.target.value })} placeholder="例如：项目背景" /></label>
            <label>正文<textarea aria-label="资料正文" value={draft.content} disabled={busy} onChange={event => setDraft({ ...draft, content: event.target.value })} placeholder="只填写希望在这个项目中持续使用的资料或要求。" /></label>
            <label className="material-toggle">保存后在新消息中使用<input type="checkbox" role="switch" aria-label="保存后在新消息中使用" checked={draft.enabled} disabled={busy} onChange={event => setDraft({ ...draft, enabled: event.target.checked })} /></label>
            <p className="section-note">单条最多 20 KB，总量最多 80 KB；大文件请直接引用原路径。</p>
            <div className="material-editor-actions"><button type="button" disabled={busy} onClick={() => setEditing(false)}>取消编辑</button><button type="submit" disabled={busy || !draft.title.trim() || !draft.content.trim()}>{busy ? "正在保存…" : "保存资料"}</button></div>
          </form>}
        </div>
      </section>
    </Dialog>}
  </>;
}
