/**
 * Vendor marks for the model lists.
 *
 * Long model ids look alike at a glance, so each family gets its own hue and
 * glyph. These are original marks, not the vendors' trademarked logos: a real
 * logo set would mean shipping their artwork, and identification only needs a
 * stable colour plus a distinct shape. Drop-in brand SVGs can replace GLYPHS
 * later without touching the callers.
 */

type Vendor = { hue: string; glyph: "circle" | "ring" | "square" | "diamond" | "triangle" | "hexagon" | "bars" | "spark" };

const VENDORS: Record<string, Vendor> = {
  claude: { hue: "24 62% 48%", glyph: "spark" },
  gpt: { hue: "162 52% 34%", glyph: "ring" },
  gemini: { hue: "217 72% 52%", glyph: "diamond" },
  grok: { hue: "0 0% 24%", glyph: "triangle" },
  deepseek: { hue: "225 72% 56%", glyph: "circle" },
  qwen: { hue: "270 58% 55%", glyph: "hexagon" },
  kimi: { hue: "0 0% 12%", glyph: "circle" },
  mimo: { hue: "22 88% 52%", glyph: "square" },
  minimax: { hue: "0 68% 52%", glyph: "bars" },
  glm: { hue: "245 62% 58%", glyph: "hexagon" },
  stepfun: { hue: "192 68% 42%", glyph: "bars" },
  doubao: { hue: "212 82% 56%", glyph: "diamond" },
  hunyuan: { hue: "204 72% 46%", glyph: "circle" },
  ernie: { hue: "218 78% 50%", glyph: "triangle" },
  llama: { hue: "232 60% 56%", glyph: "circle" },
  mistral: { hue: "32 88% 52%", glyph: "bars" },
  nemotron: { hue: "96 58% 38%", glyph: "square" },
  nova: { hue: "36 74% 48%", glyph: "spark" },
  muse: { hue: "318 52% 52%", glyph: "spark" },
  inkling: { hue: "260 44% 52%", glyph: "ring" },
  spark: { hue: "180 58% 40%", glyph: "spark" },
};

/** Map a family name, or a bare model id, onto a known vendor. */
export function vendorKey(family?: string, name?: string) {
  const direct = (family || "").trim().toLowerCase();
  if (VENDORS[direct]) return direct;
  const text = `${family || ""} ${name || ""}`.toLowerCase();
  for (const key of Object.keys(VENDORS)) if (text.includes(key)) return key;
  // A few ids never carry the family word.
  if (/\bk[23](\.|\b|-)|moonshot/.test(text)) return "kimi";
  if (/\bo[134]-|codex/.test(text)) return "gpt";
  if (/\bstep-/.test(text)) return "stepfun";
  return "";
}

function Glyph({ glyph }: { glyph: Vendor["glyph"] }) {
  const fill = "currentColor";
  if (glyph === "ring")
    return <circle cx="8" cy="8" r="4.6" fill="none" stroke={fill} strokeWidth="2.2" />;
  if (glyph === "square")
    return <rect x="3.8" y="3.8" width="8.4" height="8.4" rx="2" fill={fill} />;
  if (glyph === "diamond") return <path d="M8 2.4 13.6 8 8 13.6 2.4 8Z" fill={fill} />;
  if (glyph === "triangle") return <path d="M8 3 13.4 12.6H2.6Z" fill={fill} />;
  if (glyph === "hexagon")
    return <path d="M8 2.4 13.2 5.4v5.2L8 13.6 2.8 10.6V5.4Z" fill={fill} />;
  if (glyph === "bars")
    return (
      <g fill={fill}>
        <rect x="3.2" y="6" width="2.6" height="6.8" rx="1.3" />
        <rect x="6.7" y="3.2" width="2.6" height="9.6" rx="1.3" />
        <rect x="10.2" y="7.6" width="2.6" height="5.2" rx="1.3" />
      </g>
    );
  if (glyph === "spark")
    return <path d="M8 2.2 9.7 6.3 13.8 8 9.7 9.7 8 13.8 6.3 9.7 2.2 8 6.3 6.3Z" fill={fill} />;
  return <circle cx="8" cy="8" r="4.8" fill={fill} />;
}

export function VendorMark({
  family,
  name,
  size = 16,
}: {
  family?: string;
  name?: string;
  size?: number;
}) {
  const key = vendorKey(family, name);
  const vendor = key ? VENDORS[key] : undefined;
  if (!vendor)
    // Unknown vendor: keep the initials so nothing loses its label.
    return <span className="model-monogram-text">{(family || name || "?").slice(0, 2)}</span>;
  return (
    <svg
      className="vendor-mark"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      role="img"
      aria-label={family || key}
      style={{ color: `hsl(${vendor.hue})` }}
    >
      <Glyph glyph={vendor.glyph} />
    </svg>
  );
}

/** Background tint for the badge holding a mark. */
export function vendorTint(family?: string, name?: string) {
  const key = vendorKey(family, name);
  const vendor = key ? VENDORS[key] : undefined;
  return vendor ? `hsl(${vendor.hue} / 0.12)` : undefined;
}
