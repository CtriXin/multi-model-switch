import { useMemo } from "react";
import qrcode from "qrcode-generator";

/** A scannable code for one link, drawn as SVG so it stays sharp at any size.
 *
 *  Generated here, never fetched: the link carries the access token, and
 *  handing that to an image service would hand away the key to this machine.
 *  Error correction is the lowest level, which keeps the code coarse enough
 *  for a phone to read off a laptop screen; the link is short-lived and read
 *  from a few inches away, not printed on a poster. */
export function QrCode({ value, size = 168 }: { value: string; size?: number }) {
  const path = useMemo(() => {
    // Type 0 lets the encoder pick the smallest version that fits.
    const code = qrcode(0, "L");
    code.addData(value);
    code.make();
    const count = code.getModuleCount();
    const parts: string[] = [];
    for (let row = 0; row < count; row += 1) {
      for (let column = 0; column < count; column += 1) {
        if (code.isDark(row, column)) parts.push(`M${column} ${row}h1v1h-1z`);
      }
    }
    return { d: parts.join(""), count };
  }, [value]);
  return (
    <svg
      className="qr-code"
      width={size}
      height={size}
      // One unit per module, so the browser scales the whole code cleanly.
      viewBox={`-1 -1 ${path.count + 2} ${path.count + 2}`}
      role="img"
      aria-label="扫描这个码在手机上打开"
    >
      <rect
        x={-1}
        y={-1}
        width={path.count + 2}
        height={path.count + 2}
        fill="#fff"
      />
      <path d={path.d} fill="#000" />
    </svg>
  );
}
