import { useEffect, useState } from "react";
import { ChevronDown, FolderOpen, Search, ArrowUpRight } from "lucide-react";
import type { Model, Preset, Workspace } from "./types";
import { Dialog } from "./components";
import { ModelExplorer } from "./ModelExplorer";
import { mutate, request } from "./api";

export function ModelPicker({
  presets,
  models,
  workspaceId,
  value,
  change,
  favorites,
  toggleFavorite,
  disabled = false,
}: {
  presets: Preset[];
  models: Model[];
  workspaceId: string;
  value: string;
  change: (id: string) => void;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [candidate, setCandidate] = useState(value);
  const selected = presets.find((p) => p.id === value);
  return (
    <>
      <button
        type="button"
        className="model-picker-trigger"
        disabled={disabled}
        onClick={() => {
          setCandidate(value);
          setOpen(true);
        }}
      >
        <span>
          <strong>{selected?.name || "选择模型"}</strong>
          <small>{selected?.channel || "选择接入通道"}</small>
        </span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <Dialog title="模型与通道" close={() => setOpen(false)}>
          <ModelExplorer
            presets={presets}
            models={models}
            workspaceId={workspaceId}
            value={candidate}
            change={setCandidate}
            favorites={favorites}
            toggleFavorite={toggleFavorite}
            choose={() => {
              change(candidate);
              setOpen(false);
            }}
          />
        </Dialog>
      )}
    </>
  );
}

export function WorkspaceDialog({ close, added, reference, initialQuery = "", suggestions = [] }: {
  close: () => void;
  added?: (workspace: Workspace) => void;
  reference?: (path: string) => Promise<void>;
  initialQuery?: string;
  /** Folders the service already matched to a drop; shown until the user types. */
  suggestions?: Workspace[];
}) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<Workspace[]>([]);
  const [choice, setChoice] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    document.getElementById(`workspace-match-${choice}`)?.scrollIntoView({block: "nearest"});
  }, [choice]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      request<{workspaces: Workspace[]}>("/workspaces/search", {query}, controller.signal)
        .then(data => { if (!controller.signal.aborted) { setResults(data.workspaces); setChoice(0); setError(""); } })
        .catch(e => { if (!controller.signal.aborted) setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 120);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query]);
  // Located folders lead while the query is untouched; typing takes over.
  const shown = (query === initialQuery ? [...suggestions, ...results] : results)
    .filter((item, index, all) => all.findIndex(other => other.path === item.path) === index);
  async function select(workspace: Workspace) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (reference) await reference(workspace.path);
      else added?.(workspace.id ? workspace : await mutate<Workspace>("/workspaces", {path: workspace.path}));
      close();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function choose() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await mutate<{path: string}>("/workspaces/choose", {});
      if (result.path) {
        if (reference) await reference(result.path);
        else added?.(await mutate<Workspace>("/workspaces", {path: result.path}));
        close();
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <Dialog title={reference ? "引用文件夹" : "找到你的项目"} close={() => { if (!busy) close(); }}>
      <p className="dialog-intro">{reference
        ? `已识别文件夹${initialQuery ? `「${initialQuery}」` : ""}。选择对应的本地目录，把路径插入正文；不会复制内容或切换工作目录。`
        : "输入项目名，就能找到常用的工作文件夹。选好后会记住，下次可以直接开始。"}</p>
      <form className="workspace-form" onSubmit={e => { e.preventDefault(); if (shown[choice]) void select(shown[choice]); }}>
        <label className="workspace-search-input">
          <Search size={18} />
          <input autoFocus value={query} onChange={e => { setQuery(e.target.value); setResults([]); setChoice(0); }}
            placeholder="输入项目名，如 runtimia 或 multi" autoComplete="off" aria-label="搜索项目文件夹"
            role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="workspace-matches"
            aria-activedescendant={shown[choice] ? `workspace-match-${choice}` : undefined}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (shown[choice]) void select(shown[choice]);
              }
              if ((e.key === "ArrowDown" || e.key === "ArrowUp") && shown.length) {
                e.preventDefault(); setChoice(old => (old + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length);
              }
            }} />
        </label>
        <p className="muted" role="status">{loading && !shown.length ? "正在查找…" : query ? `找到 ${shown.length} 个文件夹` : "最近和常用的文件夹"}</p>
        <div id="workspace-matches" className="workspace-matches" role="listbox" aria-label="匹配的项目">
          {shown.map((item, index) => <button type="button" id={`workspace-match-${index}`} key={item.path}
            role="option" aria-selected={choice === index} disabled={busy}
            onMouseEnter={() => setChoice(index)} onClick={() => void select(item)}>
            <FolderOpen size={18} /><span><strong>{item.name}</strong><small>{item.path}</small></span><ArrowUpRight size={15} />
          </button>)}
          {!loading && !shown.length && <p className="muted">还没找到，可以换个关键词、粘贴完整路径，或浏览文件夹。</p>}
        </div>
        {error && <p role="alert" className="inline-alert">{error}</p>}
        <button type="button" className="text-button" disabled={busy} onClick={() => void choose()}><FolderOpen size={16} />浏览其他文件夹…</button>
      </form>
    </Dialog>
  );
}
