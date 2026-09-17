import { createElement as h, type MouseEvent } from "react";
import { ChevronDown, ChevronRight, FolderOpen } from "lucide-react";

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
  onHighlight,
  onToggle,
}: {
  rows: VisibleRow[];
  activeIndex: number;
  onHighlight: (index: number) => void;
  onToggle: (path: string) => void;
}) {
  if (!rows.length) {
    return h("p", { className: "muted" }, "这里没有可打开的文件夹。");
  }
  return h(
    "div",
    {
      id: FOLDER_TREE_CLASS,
      className: `workspace-matches ${FOLDER_TREE_CLASS}`,
      role: "tree",
      "aria-label": "这台电脑上的文件夹",
    },
    rows.map((row, index) => {
      const selected = index === activeIndex;
      const Chevron = row.expanded ? ChevronDown : ChevronRight;
      return h(
        "button",
        {
          type: "button",
          key: row.path,
          id: `workspace-folder-${index}`,
          role: "treeitem",
          "aria-selected": selected,
          "aria-expanded": row.expanded,
          "aria-level": row.depth + 1,
          className: "workspace-folder-row",
          style: { paddingLeft: `${11 + row.depth * 16}px` },
          onClick: () => onHighlight(index),
          onDoubleClick: (event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
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
    }),
  );
}
