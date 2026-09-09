import { useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

/** Native top-layer popover: Escape, outside-click and focus return are browser-owned. */
export function Popover({
  label,
  title,
  children,
  className = "",
  wide = false,
}: {
  label: ReactNode;
  title: string;
  children: ReactNode | ((close: () => void) => ReactNode);
  className?: string;
  wide?: boolean;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<CSSProperties>({});
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={className}
        popoverTarget={id}
        aria-label={title}
        aria-expanded={open}
        aria-controls={id}
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const width = Math.min(wide ? 400 : 340, window.innerWidth - 24);
          const above = window.innerHeight - box.bottom < 360 && box.top > 300;
          setStyle({
            width,
            left: Math.max(
              12,
              Math.min(box.right - width, window.innerWidth - width - 12),
            ),
            ...(above
              ? { bottom: window.innerHeight - box.top + 10, top: "auto" }
              : { top: box.bottom + 10, bottom: "auto" }),
          });
        }}
      >
        {label}
      </button>
      <div
        ref={panel}
        id={id}
        popover="auto"
        className="studio-popover"
        style={style}
        aria-label={title}
        onToggle={(event) =>
          setOpen(event.currentTarget.matches(":popover-open"))
        }
      >
        {typeof children === "function"
          ? children(() => panel.current?.hidePopover())
          : children}
      </div>
    </>
  );
}
