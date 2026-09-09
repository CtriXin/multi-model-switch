/**
 * Vendor marks for the model lists.
 *
 * Long model ids look alike at a glance, so each family carries its vendor's
 * own mark. The files in `public/vendor/` come from @lobehub/icons-static-svg
 * (MIT), which tracks the official artwork for model vendors; the colour
 * variants are used so a vendor is recognisable by hue alone at 17px.
 * A family with no file falls back to its initials rather than an invented
 * shape, so nothing here pretends to be a logo it is not.
 */

/** Vendor key to brand tint, used for the badge plate behind the mark. */
const TINTS: Record<string, string> = {
  claude: "24 62% 48%",
  gpt: "162 52% 34%",
  gemini: "217 72% 52%",
  grok: "0 0% 24%",
  deepseek: "225 72% 56%",
  qwen: "263 78% 59%",
  kimi: "0 0% 12%",
  minimax: "0 72% 55%",
  glm: "222 78% 56%",
  stepfun: "202 92% 50%",
  doubao: "212 82% 56%",
  hunyuan: "204 72% 46%",
  ernie: "218 78% 50%",
  llama: "212 72% 52%",
  mistral: "32 88% 52%",
  nemotron: "96 58% 38%",
};

/** Extra ids that do not carry the vendor word. */
const ALIASES: [RegExp, string][] = [
  [/\bk[23](\.|\b|-)|moonshot|\bkimi/, "kimi"],
  [/\bo[134]-|codex|\bgpt/, "gpt"],
  [/\bstep-/, "stepfun"],
  [/\bxai\b/, "grok"],
  [/\bchatglm|\bzhipu/, "glm"],
  [/\bwenxin|\bernie/, "ernie"],
];

/** Map a family name, or a bare model id, onto a known vendor. */
export function vendorKey(family?: string, name?: string) {
  const direct = (family || "").trim().toLowerCase();
  if (TINTS[direct]) return direct;
  const text = `${family || ""} ${name || ""}`.toLowerCase();
  for (const key of Object.keys(TINTS)) if (text.includes(key)) return key;
  for (const [pattern, key] of ALIASES) if (pattern.test(text)) return key;
  return "";
}

export function VendorMark({
  family,
  name,
  size = 17,
}: {
  family?: string;
  name?: string;
  size?: number;
}) {
  const key = vendorKey(family, name);
  if (!key)
    // Unknown vendor: keep the initials so nothing loses its label.
    return <span className="model-monogram-text">{(family || name || "?").slice(0, 2)}</span>;
  // The family can be a catch-all like "Other" while the id names the vendor;
  // label with whichever actually identifies it.
  const label = (family || "").trim().toLowerCase() === key ? family! : key;
  return (
    <img
      className="vendor-mark"
      src={`/vendor/${key}.svg`}
      width={size}
      height={size}
      alt=""
      title={label}
      loading="lazy"
    />
  );
}

/** Background tint for the badge holding a mark. */
export function vendorTint(family?: string, name?: string) {
  const key = vendorKey(family, name);
  if (!key) return undefined;
  // Marks drawn as a dark tile carry their own ground.
  if (key === "kimi" || key === "grok") return undefined;
  return `hsl(${TINTS[key]} / 0.12)`;
}
