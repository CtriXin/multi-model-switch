export type Rect = { top: number; bottom: number; right: number };
export type View = { width: number; height: number; keyboardInset?: number };

const MARGIN = 12;
const GAP = 10;
const SHEET_MAX = 640;

export function popoverPlacement(
  box: Rect,
  view: View,
  opts: { wide?: boolean; panelWidth?: number } = {},
): {
  width: number;
  left: number;
  maxHeight: number;
  top?: number | string;
  bottom?: number | string;
  ["--popover-room"]?: string;
} {
  const keyboard = view.keyboardInset || 0;
  const targetWidth = opts.wide ? 400 : opts.panelWidth || 340;
  if (view.width < SHEET_MAX) {
    const bottom = MARGIN + keyboard;
    const maxHeight = Math.max(160, view.height - bottom - MARGIN);
    return {
      width: view.width - MARGIN * 2,
      left: MARGIN,
      bottom,
      top: "auto",
      maxHeight,
      ["--popover-room"]: `${maxHeight}px`,
    };
  }
  const width = Math.min(targetWidth, view.width - MARGIN * 2);
  const roomBelow = view.height - box.bottom - MARGIN - GAP;
  const roomAbove = box.top - MARGIN - GAP;
  const above = roomBelow < 360 && roomAbove > roomBelow;
  const maxHeight = Math.max(160, above ? roomAbove : roomBelow);
  const left = Math.max(
    MARGIN,
    Math.min(box.right - width, view.width - width - MARGIN),
  );
  return {
    width,
    left,
    maxHeight,
    ["--popover-room"]: `${maxHeight}px`,
    ...(above
      ? { bottom: view.height - box.top + GAP, top: "auto" as const }
      : { top: box.bottom + GAP, bottom: "auto" as const }),
  };
}

export function readView(): View {
  const vv = window.visualViewport;
  const height = vv?.height || window.innerHeight;
  const width = vv?.width || window.innerWidth;
  const offsetTop = vv?.offsetTop || 0;
  return {
    width,
    height,
    keyboardInset: Math.max(0, window.innerHeight - height - offsetTop),
  };
}
