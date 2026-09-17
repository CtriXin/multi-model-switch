import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

/** Radio menus focus the current value; native popovers own dismissal/focus return. */
export function RadioMenu({ label, className, children, active = true }: { active?: boolean; label: string; className?: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    const selected = root.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"][aria-checked="true"]:not(:disabled)');
    (selected || root.current?.querySelector<HTMLButtonElement>('button:not(:disabled)'))?.focus();
  }, [active]);
  function move(event: KeyboardEvent<HTMLDivElement>) {
    if (event.nativeEvent.isComposing || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)')];
    if (!items.length) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 :
      index < 0 ? (event.key === "ArrowUp" ? items.length - 1 : 0) :
      (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next].focus();
  }
  return <div ref={root} role="menu" aria-label={label} className={className} onKeyDown={move}>{children}</div>;
}
