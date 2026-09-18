import { createElement as h, type MouseEvent } from "react";
import { ChevronDown, ChevronRight, FolderOpen, Search } from "lucide-react";

export type FolderKind = "home" | "drive" | "volume" | "folder";

export type FolderEntry = {
  name: string;
  path: string;
  kind?: FolderKind;
};

export type BrowseResponse = {
  path: string;
  name: string;
  parent: string | null;
  selectable: boolean;
  truncated: boolean;
  entries: FolderEntry[];
};

export type VisibleRow = {
  path: string;
  name: string;
  depth: number;
  expanded: boolean;
  kind: FolderKind;
};

export const WORKSPACE_SEARCH_AUTOFOCUS = true;
export const BUSY_SELECT = "正在打开这个文件夹…";
export const BUSY_BROWSE = "正在列出文件夹…";
export const FOLDER_TREE_CLASS = "workspace-folder-tree";
export const TREE_TRUNCATED_HINT = "这一层文件夹太多，当前只显示前 400 项。";
export const USE_FOLDER_LABEL = "使用这个文件夹";

export function scheduleWorkspaceSearchFocus(input: { focus: () => void } | null): () => void {
  if (!input) return () => {};
  const focus = () => input.focus();
  focus();
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame(focus) : 0;
  const timer = setTimeout(focus, 50);
  return () => {
    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf);
    clearTimeout(timer);
  };
}

export function busyNotice(busy: string): string {
  if (busy === "select") return BUSY_SELECT;
  if (busy === "browse") return BUSY_BROWSE;
  return "";
}

export function dismissWorkspaceDialog(close: () => void, abort?: () => void): void {
  abort?.();
  close();
}

export function toggleExpanded(expanded: string[], path: string): string[] {
  return expanded.includes(path) ? expanded.filter((item) => item !== path) : [...expanded, path];
}

export function visibleRows(
  roots: FolderEntry[],
  expanded: string[],
  children: Record<string, FolderEntry[]>,
): VisibleRow[] {
  const rows: VisibleRow[] = [];
  const walk = (entries: FolderEntry[], depth: number) => {
    for (const entry of entries) {
      const isExpanded = expanded.includes(entry.path);
      rows.push({
        path: entry.path,
        name: entry.name,
        depth,
        expanded: isExpanded,
        kind: entry.kind || "folder",
      });
      if (isExpanded && children[entry.path]) walk(children[entry.path], depth + 1);
    }
  };
  walk(roots, 0);
  return rows;
}

export function applyTreeKey(
  key: string,
  activeIndex: number,
  rowCount: number,
): number | "expand" | "collapse" | null {
  if (!rowCount) return null;
  if (key === "ArrowDown") return Math.min(rowCount - 1, activeIndex + 1);
  if (key === "ArrowUp") return Math.max(0, activeIndex - 1);
  if (key === "ArrowRight" || key === "Enter") return "expand";
  if (key === "ArrowLeft") return "collapse";
  return null;
}

export function parentRowIndex(rows: VisibleRow[], activeIndex: number): number {
  const current = rows[activeIndex];
  if (!current) return activeIndex;
  for (let index = activeIndex - 1; index >= 0; index -= 1) {
    if (rows[index].depth < current.depth) return index;
  }
  return activeIndex;
}

export function BusyNotice({ busy }: { busy: string }) {
  const text = busyNotice(busy);
  if (!text) return null;
  return h("p", { className: "workspace-busy", role: "status" }, text);
}

export function FolderTree({
  rows,
  activeIndex,
  truncated = false,
  truncatedPaths,
  onHighlight,
  onToggle,
  onKeyDown,
}: {
  rows: VisibleRow[];
  activeIndex: number;
  truncated?: boolean;
  truncatedPaths?: string[];
  onHighlight: (index: number) => void;
  onToggle: (path: string) => void;
  onKeyDown?: (event: { key: string; preventDefault: () => void }) => void;
}) {
  if (!rows.length) {
    return h("p", { className: "muted" }, "这里没有可打开的文件夹。");
  }
  // Each truncated level gets its own hint, placed at the end of that level's
  // visible subtree. The root listing is tracked under the empty path.
  const hintIndexes = new Set<number>();
  for (const path of truncatedPaths ?? []) {
    if (!path) {
      hintIndexes.add(rows.length - 1);
      continue;
    }
    const start = rows.findIndex((row) => row.path === path);
    if (start < 0) continue;
    let end = start;
    for (let index = start + 1; index < rows.length; index += 1) {
      if (rows[index].depth <= rows[start].depth) break;
      end = index;
    }
    hintIndexes.add(end);
  }
  const truncatedHint = (key: string) =>
    h("p", { key, className: "muted workspace-folder-truncated", role: "status" }, TREE_TRUNCATED_HINT);
  return h(
    "div",
    {
      id: FOLDER_TREE_CLASS,
      className: `workspace-matches ${FOLDER_TREE_CLASS}`,
      role: "tree",
      tabIndex: 0,
      "aria-label": "这台电脑上的文件夹",
      onKeyDown,
    },
    [
      ...rows.flatMap((row, index) => {
        const selected = index === activeIndex;
        const Chevron = row.expanded ? ChevronDown : ChevronRight;
        const button = h(
          "button",
          {
            type: "button",
            key: row.path,
            id: `workspace-folder-${index}`,
            role: "treeitem",
            tabIndex: selected ? 0 : -1,
            "aria-selected": selected,
            "aria-expanded": row.expanded,
            "aria-level": row.depth + 1,
            className: "workspace-folder-row",
            style: { paddingLeft: `${11 + row.depth * 16}px` },
            onClick: () => {
              onHighlight(index);
              onToggle(row.path);
            },
          },
          h(
            "span",
            {
              className: "workspace-folder-chevron",
              onClick: (event: MouseEvent<HTMLSpanElement>) => {
                event.preventDefault();
                event.stopPropagation();
                onHighlight(index);
                onToggle(row.path);
              },
            },
            h(Chevron, { size: 14, "aria-hidden": true }),
          ),
          h(FolderOpen, { size: 18, "aria-hidden": true }),
          h("span", { className: "workspace-folder-label" }, h("strong", null, row.name), h("small", null, row.path)),
        );
        return hintIndexes.has(index) ? [button, truncatedHint(`truncated-${index}`)] : [button];
      }),
      truncated && !truncatedPaths?.length ? truncatedHint("truncated") : null,
    ],
  );
}

export type WorkspaceMatch = { id?: string; name: string; path: string };

export function WorkspaceDialogBody({
  query,
  onQueryChange,
  onQueryKeyDown,
  inputRef,
  browsing,
  busy,
  status,
  error,
  shown,
  choice,
  onHighlightShown,
  onSelectShown,
  rows,
  activeIndex,
  truncated,
  truncatedPaths,
  onHighlightRow,
  onToggleRow,
  onTreeKeyDown,
  onUseFolder,
  onOpenBrowser,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onQueryKeyDown: (event: { key: string; preventDefault: () => void; nativeEvent?: { isComposing?: boolean } }) => void;
  inputRef?: { current: HTMLInputElement | null };
  browsing: boolean;
  busy: string;
  status: string;
  error: string;
  shown: WorkspaceMatch[];
  choice: number;
  onHighlightShown: (index: number) => void;
  onSelectShown: (item: WorkspaceMatch) => void;
  rows: VisibleRow[];
  activeIndex: number;
  truncated?: boolean;
  truncatedPaths?: string[];
  onHighlightRow: (index: number) => void;
  onToggleRow: (path: string) => void;
  onTreeKeyDown: (event: { key: string; preventDefault: () => void }) => void;
  onUseFolder: () => void;
  onOpenBrowser: () => void;
}) {
  const activeFolder = rows[activeIndex];
  return h(
    "form",
    {
      className: "workspace-form",
      onSubmit: (event: { preventDefault: () => void }) => event.preventDefault(),
    },
    h(
      "label",
      { className: "workspace-search-input" },
      h(Search, { size: 18 }),
      h("input", {
        ref: inputRef,
        autoFocus: WORKSPACE_SEARCH_AUTOFOCUS,
        value: query,
        onChange: (event: { target: { value: string } }) => onQueryChange(event.target.value),
        onKeyDown: onQueryKeyDown,
        placeholder: "输入项目名，如 runtimia 或 multi",
        autoComplete: "off",
        "aria-label": "搜索项目文件夹",
        role: "combobox",
        "aria-autocomplete": "list",
        "aria-expanded": "true",
        "aria-controls": browsing ? FOLDER_TREE_CLASS : "workspace-matches",
        "aria-activedescendant": browsing
          ? (activeFolder ? `workspace-folder-${activeIndex}` : undefined)
          : (shown[choice] ? `workspace-match-${choice}` : undefined),
      }),
    ),
    busy ? h(BusyNotice, { busy }) : h("p", { className: "muted", role: "status" }, status),
    browsing
      ? [
          h(FolderTree, {
            key: "tree",
            rows,
            activeIndex,
            truncated,
            truncatedPaths,
            onHighlight: onHighlightRow,
            onToggle: onToggleRow,
            onKeyDown: onTreeKeyDown,
          }),
          h(
            "button",
            {
              key: "use",
              type: "button",
              className: "button",
              disabled: !!busy || !activeFolder,
              onClick: onUseFolder,
            },
            USE_FOLDER_LABEL,
          ),
        ]
      : h(
          "div",
          { id: "workspace-matches", className: "workspace-matches", role: "listbox", "aria-label": "匹配的项目" },
          shown.length
            ? shown.map((item, index) =>
                h(
                  "button",
                  {
                    type: "button",
                    id: `workspace-match-${index}`,
                    key: item.path,
                    role: "option",
                    "aria-selected": choice === index,
                    disabled: !!busy,
                    onMouseEnter: () => onHighlightShown(index),
                    onClick: () => onSelectShown(item),
                  },
                  h(FolderOpen, { size: 18 }),
                  h("span", null, h("strong", null, item.name), h("small", null, item.path)),
                ),
              )
            : h("p", { className: "muted" }, "还没找到，可以换个关键词、粘贴完整路径，或浏览文件夹。"),
        ),
    error ? h("p", { role: "alert", className: "inline-alert" }, error) : null,
    h(
      "button",
      {
        type: "button",
        className: "text-button",
        disabled: !!busy,
        onClick: onOpenBrowser,
      },
      h(FolderOpen, { size: 16 }),
      "浏览其他文件夹…",
    ),
  );
}
