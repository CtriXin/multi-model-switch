import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Model, Preset, Workspace } from "./types";
import { Dialog } from "./components";
import { ModelExplorer } from "./ModelExplorer";
import { availableRoutesForModel, channelLabel } from "./modelSelection";
import { mutate, request } from "./api";
import {
  applyTreeKey,
  busyNotice,
  dismissWorkspaceDialog,
  parentRowIndex,
  scheduleWorkspaceSearchFocus,
  toggleExpanded,
  visibleRows,
  WorkspaceDialogBody,
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
  scope = "web",
}: {
  presets: Preset[];
  models: Model[];
  workspaceId: string;
  value: string;
  change: (id: string) => void | Promise<void | boolean>;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  disabled?: boolean;
  scope?: "web" | "bot";
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [candidate, setCandidate] = useState(value);
  const selected = presets.find((p) => p.id === value);
  const extraChannels = availableRoutesForModel(presets, selected).length > 1;
  return (
    <>
      <button
        type="button"
        className="model-picker-trigger"
        disabled={disabled}
        onClick={() => {
          setError("");
          setCandidate(value);
          setOpen(true);
        }}
      >
        <span>
          <strong>{selected?.name || "选择模型"}</strong>
          {extraChannels && selected && (
            <small>{channelLabel(selected, models)}</small>
          )}
        </span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <Dialog title="模型与通道" close={() => setOpen(false)} dismissible={!pending}>
          {error && <p role="alert" className="inline-alert">{error}</p>}
          {pending && <p role="status">正在切换模型…</p>}
          <fieldset disabled={pending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <ModelExplorer
            scope={scope}
            presets={presets}
            models={models}
            workspaceId={workspaceId}
            value={candidate}
            change={setCandidate}
            favorites={favorites}
            toggleFavorite={toggleFavorite}
            choose={async () => {
              if (pending) return;
              setPending(true); setError("");
              try {
                if (await change(candidate) === false) setError("切换未完成，请重试。");
                else setOpen(false);
              } catch (cause) {
                setError(cause instanceof Error ? cause.message : "切换未完成，请重试。");
              } finally { setPending(false); }
            }}
          />
          </fieldset>
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
  const [truncatedAt, setTruncatedAt] = useState<Record<string, boolean>>({});
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
    if (busy) return;
    return scheduleWorkspaceSearchFocus(inputRef.current);
  }, [browsing, busy]);
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
  async function loadListing(path: string, controller: AbortController): Promise<BrowseResponse> {
    return request<BrowseResponse>("/workspaces/browse", {path}, controller.signal);
  }
  async function openBrowser() {
    if (busy) return;
    const controller = startAction();
    setBusy("browse"); setError("");
    try {
      const data = await loadListing("", controller);
      if (controller.signal.aborted) return;
      setTreeRoots(data.entries);
      setTreeChildren({});
      setExpanded([]);
      setActiveIndex(0);
      setTruncatedAt({ "": data.truncated });
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
        const data = await loadListing(path, controller);
        if (controller.signal.aborted) return;
        kids = data.entries;
        setTreeChildren((current) => ({ ...current, [path]: kids }));
        setTruncatedAt((current) => ({ ...current, [path]: data.truncated }));
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
  function onTreeKey(event: { key: string; preventDefault: () => void }): boolean {
    const result = applyTreeKey(event.key, activeIndex, rows.length);
    if (result === null) return false;
    event.preventDefault();
    if (typeof result === "number") setActiveIndex(result);
    else if (result === "expand" && rows[activeIndex]) {
      if (event.key === "Enter" || !rows[activeIndex].expanded) void toggle(rows[activeIndex].path);
    }
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
  const truncated = Object.values(truncatedAt).some(Boolean);
  return (
    <Dialog title={reference ? "引用文件夹" : "找到你的项目"} close={() => dismissWorkspaceDialog(close, abortAction)}>
      <p className="dialog-intro">{reference
        ? `已识别文件夹${initialQuery ? `「${initialQuery}」` : ""}。选择对应的本地目录，把路径插入正文；不会复制内容或切换工作目录。`
        : "输入项目名，就能找到常用的工作文件夹。选好后会记住，下次可以直接开始。"}</p>
      <WorkspaceDialogBody
        query={query}
        onQueryChange={(value) => { setQuery(value); setResults([]); setChoice(0); setBrowsing(false); }}
        onQueryKeyDown={(e) => {
          if (browsing && onTreeKey(e)) return;
          if (e.key === "Enter" && !e.nativeEvent?.isComposing) {
            e.preventDefault();
            if (shown[choice]) void select(shown[choice]);
          }
          if ((e.key === "ArrowDown" || e.key === "ArrowUp") && shown.length) {
            e.preventDefault(); setChoice(old => (old + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length);
          }
        }}
        inputRef={inputRef}
        browsing={browsing}
        busy={busy}
        status={status}
        error={error}
        shown={shown}
        choice={choice}
        onHighlightShown={setChoice}
        onSelectShown={(item) => void select({ id: item.id || "", name: item.name, path: item.path })}
        rows={rows}
        activeIndex={activeIndex}
        truncated={truncated}
        onHighlightRow={setActiveIndex}
        onToggleRow={(path) => void toggle(path)}
        onTreeKeyDown={(e) => { onTreeKey(e); }}
        onUseFolder={() => activeFolder && void select({ id: "", name: activeFolder.name, path: activeFolder.path })}
        onOpenBrowser={() => void openBrowser()}
      />
    </Dialog>
  );
}
