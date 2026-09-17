import { useId, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { popoverPlacement, readView } from "./popover-placement";

/** Native top-layer popover: Escape, outside-click and focus return are browser-owned. */
export function Popover({
  label,
  title,
  children,
  className = "",
  wide = false,
  panelWidth,
  disabled = false,
  dataGuide,
}: {
  label: ReactNode;
  title: string;
  children: ReactNode | ((close: () => void, open: boolean) => ReactNode);
  className?: string;
  wide?: boolean;
  panelWidth?: number;
  disabled?: boolean;
  dataGuide?: string;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [style, setStyle] = useState<CSSProperties>({});
  const [open, setOpen] = useState(false);
  function place(box: DOMRect) {
    setStyle(popoverPlacement(box, readView(), { wide, panelWidth }));
  }
  return (
    <>
      <button
        type="button"
        ref={trigger}
        className={className}
        disabled={disabled}
        popoverTarget={disabled ? undefined : id}
        aria-label={title}
        aria-expanded={open}
        aria-controls={disabled ? undefined : id}
        data-guide={dataGuide}
        onClick={(event) => {
          if (disabled) return;
          place(event.currentTarget.getBoundingClientRect());
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
        onToggle={(event) => {
          const next = event.currentTarget.matches(":popover-open");
          setOpen(next);
          if (next && trigger.current) place(trigger.current.getBoundingClientRect());
        }}
      >
        {typeof children === "function"
          ? children(() => panel.current?.hidePopover(), open)
          : children}
      </div>
    </>
  );
}
