/** Keep the app shell inside the visible viewport, including the iOS keyboard
 *  and in-app browser chrome. 100dvh still covers the keyboard on WebKit. */

export function keyboardInset(innerHeight: number, view: { height: number; offsetTop: number }): number {
  return Math.max(0, innerHeight - view.height - view.offsetTop);
}

export function syncVisualViewport() {
  const root = document.documentElement;
  const vv = window.visualViewport;
  if (!vv) {
    root.style.removeProperty("--vv-height");
    root.style.removeProperty("--keyboard-inset");
    return;
  }
  const inset = keyboardInset(window.innerHeight, vv);
  root.style.setProperty("--vv-height", `${vv.height}px`);
  root.style.setProperty("--keyboard-inset", `${inset}px`);
}

export function watchVisualViewport(): () => void {
  syncVisualViewport();
  const vv = window.visualViewport;
  if (!vv) return () => {};
  vv.addEventListener("resize", syncVisualViewport);
  vv.addEventListener("scroll", syncVisualViewport);
  window.addEventListener("orientationchange", syncVisualViewport);
  return () => {
    vv.removeEventListener("resize", syncVisualViewport);
    vv.removeEventListener("scroll", syncVisualViewport);
    window.removeEventListener("orientationchange", syncVisualViewport);
  };
}
