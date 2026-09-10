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
  children: ReactNode | ((close: () => void, open: boolean) => ReactNode);
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
          // Room on each side, minus the 10px gap to the trigger and a 12px viewport margin.
          const roomBelow = window.innerHeight - box.bottom - 22;
          const roomAbove = box.top - 22;
          // Prefer below; flip when it cannot fit there and the other side has more room.
          const above = roomBelow < 360 && roomAbove > roomBelow;
          setStyle({
            width,
            left: Math.max(
              12,
              Math.min(box.right - width, window.innerWidth - width - 12),
            ),
            // Never extend past the viewport edge: the panel scrolls instead.
            maxHeight: Math.max(160, above ? roomAbove : roomBelow),
            // Lets content size its own scroll region to the room actually available.
            ["--popover-room" as string]: `${Math.max(160, above ? roomAbove : roomBelow)}px`,
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
          ? children(() => panel.current?.hidePopover(), open)
          : children}
      </div>
    </>
  );
}
