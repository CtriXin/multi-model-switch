import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, FolderOpen, Search, ArrowUpRight } from "lucide-react";
import type { Model, Preset, Workspace } from "./types";
import { Dialog } from "./components";
import { ModelExplorer } from "./ModelExplorer";
import { mutate, request } from "./api";
import {
  applyTreeKey,
  BusyNotice,
  busyNotice,
  dismissWorkspaceDialog,
  FolderTree,
  parentRowIndex,
  toggleExpanded,
  visibleRows,
  FOLDER_TREE_CLASS,
  WORKSPACE_SEARCH_AUTOFOCUS,
  type BrowseResponse,
  type FolderEntry,
} from "./folder-tree";

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
  const [busy, setBusy] = useState<"" | "select" | "browse">("");
  const [error, setError] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [treeRoots, setTreeRoots] = useState<FolderEntry[]>([]);
  const [treeChildren, setTreeChildren] = useState<Record<string, FolderEntry[]>>({});
  const [expanded, setExpanded] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const actionRef = useRef<AbortController | null>(null);
  const rows = visibleRows(treeRoots, expanded, treeChildren);
  const abortAction = () => { actionRef.current?.abort(); };
  const startAction = () => {
    abortAction();
    const controller = new AbortController();
    actionRef.current = controller;
    return controller;
  };

  useEffect(() => {
    const focus = () => inputRef.current?.focus();
    focus();
    const raf = requestAnimationFrame(focus);
    const timer = setTimeout(focus, 50);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
  }, []);
  useEffect(() => {
    const target = browsing
      ? `workspace-folder-${activeIndex}`
      : `workspace-match-${choice}`;
    document.getElementById(target)?.scrollIntoView({block: "nearest"});
  }, [choice, activeIndex, browsing]);
  useEffect(() => {
    if (browsing) return;
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      request<{workspaces: Workspace[]}>("/workspaces/search", {query}, controller.signal)
        .then(data => { if (!controller.signal.aborted) { setResults(data.workspaces); setChoice(0); setError(""); } })
        .catch(e => { if (!controller.signal.aborted) setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 120);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, browsing]);
  // Located folders lead while the query is untouched; typing takes over.
  const shown = (query === initialQuery ? [...suggestions, ...results] : results)
    .filter((item, index, all) => all.findIndex(other => other.path === item.path) === index);
  async function select(workspace: Workspace) {
    if (busy) return;
    const controller = startAction();
    setBusy("select"); setError("");
    try {
      if (reference) await reference(workspace.path);
      else added?.(workspace.id ? workspace : await mutate<Workspace>("/workspaces", {path: workspace.path}, controller.signal));
      if (!controller.signal.aborted) close();
    } catch (e) {
      if (controller.signal.aborted) return;
      setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  async function loadEntries(path: string, controller: AbortController): Promise<FolderEntry[]> {
    const data = await request<BrowseResponse>("/workspaces/browse", {path}, controller.signal);
    return data.entries;
  }
  async function openBrowser() {
    if (busy) return;
    const controller = startAction();
    setBusy("browse"); setError("");
    try {
      const entries = await loadEntries("", controller);
      if (controller.signal.aborted) return;
      setTreeRoots(entries);
      setTreeChildren({});
      setExpanded([]);
      setActiveIndex(0);
      setBrowsing(true);
    } catch (e) {
      if (controller.signal.aborted) return;
      setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  async function toggle(path: string) {
    if (expanded.includes(path)) {
      setExpanded(toggleExpanded(expanded, path));
      return;
    }
    const controller = startAction();
    setBusy("browse"); setError("");
    try {
      let kids = treeChildren[path];
      if (!kids) {
        kids = await loadEntries(path, controller);
        if (controller.signal.aborted) return;
        setTreeChildren((current) => ({ ...current, [path]: kids }));
      }
      if (controller.signal.aborted) return;
      setExpanded((current) => toggleExpanded(current, path));
    } catch (e) {
      if (controller.signal.aborted) return;
      setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  function onTreeKey(event: KeyboardEvent<HTMLInputElement>): boolean {
    const result = applyTreeKey(event.key, activeIndex, rows.length);
    if (result === null) return false;
    event.preventDefault();
    if (typeof result === "number") setActiveIndex(result);
    else if (result === "expand" && rows[activeIndex]) void toggle(rows[activeIndex].path);
    else if (result === "collapse" && rows[activeIndex]) {
      if (rows[activeIndex].expanded) setExpanded(toggleExpanded(expanded, rows[activeIndex].path));
      else setActiveIndex(parentRowIndex(rows, activeIndex));
    }
    return true;
  }
  const status = busy
    ? busyNotice(busy)
    : browsing
      ? "从这台电脑逐层打开"
      : loading && !shown.length ? "正在查找…" : query ? `找到 ${shown.length} 个文件夹` : "最近和常用的文件夹";
  const activeFolder = rows[activeIndex];
  return (
    <Dialog title={reference ? "引用文件夹" : "找到你的项目"} close={() => dismissWorkspaceDialog(close, abortAction)}>
      <p className="dialog-intro">{reference
        ? `已识别文件夹${initialQuery ? `「${initialQuery}」` : ""}。选择对应的本地目录，把路径插入正文；不会复制内容或切换工作目录。`
        : "输入项目名，就能找到常用的工作文件夹。选好后会记住，下次可以直接开始。"}</p>
      <form className="workspace-form" onSubmit={e => {
        e.preventDefault();
        if (browsing) return;
        if (shown[choice]) void select(shown[choice]);
      }}>
        <label className="workspace-search-input">
          <Search size={18} />
          <input ref={inputRef} autoFocus={WORKSPACE_SEARCH_AUTOFOCUS} value={query}
            onChange={e => { setQuery(e.target.value); setResults([]); setChoice(0); setBrowsing(false); }}
            placeholder="输入项目名，如 runtimia 或 multi" autoComplete="off" aria-label="搜索项目文件夹"
            role="combobox" aria-autocomplete="list" aria-expanded="true"
            aria-controls={browsing ? FOLDER_TREE_CLASS : "workspace-matches"}
            aria-activedescendant={browsing
              ? (activeFolder ? `workspace-folder-${activeIndex}` : undefined)
              : (shown[choice] ? `workspace-match-${choice}` : undefined)}
            onKeyDown={e => {
              if (browsing && onTreeKey(e)) return;
              if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (shown[choice]) void select(shown[choice]);
              }
              if ((e.key === "ArrowDown" || e.key === "ArrowUp") && shown.length) {
                e.preventDefault(); setChoice(old => (old + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length);
              }
            }} />
        </label>
        {busy ? <BusyNotice busy={busy} /> : <p className="muted" role="status">{status}</p>}
        {browsing ? (
          <>
            <FolderTree rows={rows} activeIndex={activeIndex} onHighlight={setActiveIndex} onToggle={(path) => void toggle(path)} />
            <button type="button" className="button" disabled={!!busy || !activeFolder}
              onClick={() => activeFolder && void select({ id: "", name: activeFolder.name, path: activeFolder.path })}>
              使用这个文件夹
            </button>
          </>
        ) : (
          <div id="workspace-matches" className="workspace-matches" role="listbox" aria-label="匹配的项目">
            {shown.map((item, index) => <button type="button" id={`workspace-match-${index}`} key={item.path}
              role="option" aria-selected={choice === index} disabled={!!busy}
              onMouseEnter={() => setChoice(index)} onClick={() => void select(item)}>
              <FolderOpen size={18} /><span><strong>{item.name}</strong><small>{item.path}</small></span><ArrowUpRight size={15} />
            </button>)}
            {!loading && !shown.length && <p className="muted">还没找到，可以换个关键词、粘贴完整路径，或浏览文件夹。</p>}
          </div>
        )}
        {error && <p role="alert" className="inline-alert">{error}</p>}
        <button type="button" className="text-button" disabled={!!busy} onClick={() => void openBrowser()}><FolderOpen size={16} />浏览其他文件夹…</button>
      </form>
    </Dialog>
  );
}
