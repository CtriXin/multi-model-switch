/**
 * Vendor marks for the model lists.
 *
 * Long model ids look alike at a glance, so each family carries its vendor's
 * mark. The official artwork below is reused from the runtimia provider-logo
 * set, which recorded where each path came from; those notes are kept.
 * Families with no sourced asset get a plain tinted glyph that is clearly not
 * claiming to be a logo, rather than an invented one.
 */

type Vendor = {
  hue: string;
  glyph?: "circle" | "ring" | "square" | "diamond" | "triangle" | "hexagon" | "bars" | "spark";
  mark?: (size: number) => React.ReactElement;
};

// Claude (Anthropic) — official mark, sourced from Bootstrap Icons (bi-claude)
const claudeMark = (size: number) => (
  <svg viewBox="0 0 16 16" fill="#D97757" width={size} height={size} aria-hidden>
    <path d="m3.127 10.604 3.135-1.76.053-.153-.053-.085H6.11l-.525-.032-1.791-.048-1.554-.065-1.505-.08-.38-.081L0 7.832l.036-.234.32-.214.455.04 1.009.069 1.513.105 1.097.064 1.626.17h.259l.036-.105-.089-.065-.068-.064-1.566-1.062-1.695-1.121-.887-.646-.48-.327-.243-.306-.104-.67.435-.48.585.04.15.04.593.456 1.267.981 1.654 1.218.242.202.097-.068.012-.049-.109-.181-.9-1.626-.96-1.655-.428-.686-.113-.411a2 2 0 0 1-.068-.484l.496-.674L4.446 0l.662.089.279.242.411.94.666 1.48 1.033 2.014.302.597.162.553.06.17h.105v-.097l.085-1.134.157-1.392.154-1.792.052-.504.25-.605.497-.327.387.186.319.456-.045.294-.19 1.23-.37 1.93-.243 1.29h.142l.161-.16.654-.868 1.097-1.372.484-.545.565-.601.363-.287h.686l.505.751-.226.775-.707.895-.585.759-.839 1.13-.524.904.048.072.125-.012 1.897-.403 1.024-.186 1.223-.21.553.258.06.263-.218.536-1.307.323-1.533.307-2.284.54-.028.02.032.04 1.029.098.44.024h1.077l2.005.15.525.346.315.424-.053.323-.807.411-3.631-.863-.872-.218h-.12v.073l.726.71 1.331 1.202 1.667 1.55.084.383-.214.302-.226-.032-1.464-1.101-.565-.497-1.28-1.077h-.084v.113l.295.432 1.557 2.34.08.718-.112.234-.404.141-.444-.08-.911-1.28-.94-1.44-.759-1.291-.093.053-.448 4.821-.21.246-.484.186-.403-.307-.214-.496.214-.98.258-1.28.21-1.016.19-1.263.112-.42-.008-.028-.092.012-.953 1.307-1.448 1.957-1.146 1.227-.274.109-.477-.247.045-.44.266-.39 1.586-2.018.956-1.25.617-.723-.004-.105h-.036l-4.212 2.736-.75.096-.324-.302.04-.496.154-.162 1.267-.871z" />
  </svg>
);

// OpenAI — the knot mark shipped with the Codex CLI brand assets.
const openaiMark = (size: number) => (
  <svg viewBox="0 0 16 16" fill="currentColor" width={size} height={size} aria-hidden>
    <path d="M14.949 6.547a3.94 3.94 0 0 0-.348-3.273 4.11 4.11 0 0 0-4.4-1.934A4.1 4.1 0 0 0 8.423.2 4.15 4.15 0 0 0 6.305.086a4.1 4.1 0 0 0-1.891.948 4.04 4.04 0 0 0-1.158 1.753 4.1 4.1 0 0 0-1.563.679A4 4 0 0 0 .554 4.72a3.99 3.99 0 0 0 .502 4.731 3.94 3.94 0 0 0 .346 3.274 4.11 4.11 0 0 0 4.402 1.933c.382.425.852.764 1.377.995.526.231 1.095.35 1.67.346 1.78.002 3.358-1.132 3.901-2.804a4.1 4.1 0 0 0 1.563-.68 4 4 0 0 0 1.14-1.253 3.99 3.99 0 0 0-.506-4.716m-6.097 8.406a3.05 3.05 0 0 1-1.945-.694l.096-.054 3.23-1.838a.53.53 0 0 0 .265-.455v-4.49l1.366.778q.02.011.025.035v3.722c-.003 1.653-1.361 2.992-3.037 2.996m-6.53-2.75a2.95 2.95 0 0 1-.36-2.01l.095.057L5.29 12.09a.53.53 0 0 0 .527 0l3.949-2.246v1.555a.05.05 0 0 1-.022.041L6.473 13.3c-1.454.826-3.311.335-4.15-1.098m-.85-6.94A3.02 3.02 0 0 1 3.07 3.949v3.785a.51.51 0 0 0 .262.451l3.93 2.237-1.366.779a.05.05 0 0 1-.048 0L2.585 9.342a2.98 2.98 0 0 1-1.113-4.094zm11.216 2.571L8.747 5.576l1.362-.776a.05.05 0 0 1 .048 0l3.265 1.86a3 3 0 0 1 1.173 1.207 2.96 2.96 0 0 1-.27 3.2 3.05 3.05 0 0 1-1.36.997V8.279a.52.52 0 0 0-.276-.445m1.36-2.015-.097-.057-3.226-1.855a.53.53 0 0 0-.53 0L6.249 6.153V4.598a.04.04 0 0 1 .019-.04L9.533 2.7a3.07 3.07 0 0 1 3.257.139c.474.325.843.778 1.066 1.303.223.526.289 1.103.191 1.664zM5.503 8.575 4.139 7.8a.05.05 0 0 1-.026-.037V4.049c0-.57.166-1.127.476-1.607s.752-.864 1.275-1.105a3.08 3.08 0 0 1 3.234.41l-.096.054-3.23 1.838a.53.53 0 0 0-.265.455zm.742-1.577 1.758-1 1.762 1v2l-1.755 1-1.762-1z" />
  </svg>
);

// Kimi (Moonshot) — the mark used by the Kimi CLI brand assets.
const kimiMark = (size: number) => (
  <svg viewBox="0 0 24 24" fill="none" width={size} height={size} aria-hidden>
    <rect width="24" height="24" rx="5" fill="#1F1147" />
    <path d="M7.2 6h2.4v5.1l4.3-5.1h2.9l-4.4 5.1L17 18h-2.9l-3.2-5.2-1.3 1.5V18H7.2V6z" fill="#FFF" />
  </svg>
);

// Grok (xAI) — the mark used by the Grok CLI brand assets.
const grokMark = (size: number) => (
  <svg viewBox="0 0 24 24" fill="none" width={size} height={size} aria-hidden>
    <rect width="24" height="24" rx="5" fill="#0A0A0A" />
    <path
      d="M7.2 7.2h4.1c2.7 0 4.5 1.7 4.5 4.2 0 2.5-1.8 4.2-4.5 4.2H9.4v1.2H7.2V7.2zm2.2 2v4.2h1.8c1.5 0 2.4-.9 2.4-2.1 0-1.2-.9-2.1-2.4-2.1H9.4z"
      fill="#FFF"
    />
    <path d="M16.8 16.8 14.2 14.1" stroke="#FFF" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

// Qwen — official SVG from QwenLM/qwen-code's desktop brand assets
// (packages/desktop/apps/electron/resources/brands/qwen-code/icon.svg).
const qwenMark = (size: number) => (
  <svg viewBox="0 0 141.38 140" width={size} height={size} aria-hidden>
    <path
      fill="#6D44E8"
      d="m140.93 85-16.35-28.33-1.93-3.34 8.66-15a3.323 3.323 0 0 0 0-3.34l-9.62-16.67c-.3-.51-.72-.93-1.22-1.22s-1.07-.45-1.67-.45H82.23l-8.66-15a3.33 3.33 0 0 0-2.89-1.67H51.43c-.59 0-1.17.16-1.66.45-.5.29-.92.71-1.22 1.22L32.19 29.98l-1.92 3.33H12.96c-.59 0-1.17.16-1.66.45-.5.29-.93.71-1.22 1.22L.45 51.66a3.323 3.323 0 0 0 0 3.34l18.28 31.67-8.66 15a3.32 3.32 0 0 0 0 3.34l9.62 16.67c.3.51.72.93 1.22 1.22s1.07.45 1.67.45h36.56l8.66 15a3.35 3.35 0 0 0 2.89 1.67h19.25a3.34 3.34 0 0 0 2.89-1.67l18.28-31.67h17.32c.6 0 1.17-.16 1.67-.45s.92-.71 1.22-1.22l9.62-16.67a3.323 3.323 0 0 0 0-3.34ZM51.44 3.33 61.07 20l-9.63 16.66h76.98l-9.62 16.66H45.67l-11.54-20zM57.21 120H22.58l9.63-16.67h19.25l-38.5-66.67h19.25l9.62 16.67L68.78 100l-11.55 20Zm61.59-33.34-9.62-16.67-38.49 66.67-9.63-16.67 9.63-16.66 26.94-46.67h23.1l17.32 30z"
    />
  </svg>
);

// MiniMax — official mark from the MiniMax Code docs logo. Upstream ships
// separate #171717 and white variants; currentColor gives both from one path.
const minimaxMark = (size: number) => (
  <svg viewBox="2.1 2 27.9 28" fill="currentColor" width={size} height={size} aria-hidden>
    <path d="M27.0157 5.80436C27.867 5.80448 28.5567 6.49502 28.5567 7.34635V20.7487C28.5567 21.2424 28.3347 21.7099 27.9522 22.0221L23.4102 25.7311C23.1167 25.9708 22.7491 26.1021 22.3702 26.1022H5.12508C4.27367 26.1022 3.58308 25.4116 3.58308 24.5602V11.5592C3.58308 11.0643 3.80649 10.5951 4.19051 10.2829L9.24519 6.17253C9.53831 5.93433 9.90459 5.80436 10.2823 5.80436H27.0157ZM11.0587 8.88053C10.8705 8.88052 10.6884 8.94584 10.5421 9.06413L6.99519 11.9313C6.80216 12.0874 6.69051 12.3227 6.69051 12.571V22.4987C6.69073 22.7823 6.92051 23.0124 7.20418 23.0124H9.7491V17.6745C9.74924 17.2206 10.1175 16.8524 10.5714 16.8522H12.5245C12.9784 16.8523 13.3466 17.2206 13.3468 17.6745V23.0124H15.1964V17.6745C15.1965 17.2205 15.5647 16.8522 16.0186 16.8522H17.9718C18.4256 16.8524 18.7939 17.2206 18.794 17.6745V23.0124H21.5587C21.7476 23.0124 21.9306 22.947 22.0772 22.8278L25.17 20.3112C25.3618 20.1551 25.4736 19.9208 25.4737 19.6735V9.40104C25.4736 9.11741 25.2437 8.8875 24.96 8.88737L11.0587 8.88053Z" />
  </svg>
);

// DeepSeek — official mark from deepseek-ai/deepseek-harness
// (apps/web/public/favicon.svg, MIT — Copyright 2026 DeepSeek).
const deepseekMark = (size: number) => (
  <svg viewBox="0 0 50 50" fill="#4D6BFE" width={size} height={size} aria-hidden>
    <path
      fillRule="nonzero"
      d="M48.8354 10.0479C48.3232 9.79199 48.1025 10.2798 47.8032 10.5278C47.7007 10.6079 47.6143 10.7119 47.5273 10.8076C46.7793 11.624 45.9048 12.1597 44.7622 12.0957C43.0923 12 41.666 12.5356 40.4058 13.8398C40.1377 12.2319 39.2476 11.272 37.8926 10.6558C37.1836 10.3359 36.4668 10.0156 35.9702 9.31982C35.6235 8.82373 35.5293 8.27197 35.356 7.72754C35.2456 7.3999 35.1353 7.06396 34.7651 7.00781C34.3633 6.94385 34.2056 7.2876 34.0479 7.57568C33.418 8.75195 33.1733 10.0479 33.1973 11.3599C33.2524 14.312 34.4736 16.6641 36.8999 18.3359C37.1758 18.5278 37.2466 18.7197 37.1597 19C36.9946 19.5757 36.7974 20.1357 36.624 20.7119C36.5137 21.0801 36.3486 21.1597 35.9624 21C34.6309 20.4321 33.481 19.5918 32.4644 18.5757C30.7393 16.8721 29.1792 14.9917 27.2334 13.52C26.7764 13.1758 26.3193 12.856 25.8467 12.5518C23.8618 10.584 26.1069 8.96777 26.627 8.77588C27.1704 8.57568 26.8159 7.8877 25.0591 7.896C23.3022 7.90381 21.6953 8.50391 19.647 9.30371C19.3477 9.42383 19.0322 9.51172 18.7095 9.58398C16.8501 9.22363 14.9199 9.14355 12.9033 9.37598C9.10596 9.80762 6.07275 11.6396 3.84326 14.7681C1.16455 18.5278 0.53418 22.7998 1.30664 27.2559C2.11768 31.9521 4.46582 35.8398 8.07373 38.8799C11.8159 42.0322 16.1255 43.5762 21.041 43.2803C24.0269 43.104 27.3516 42.6963 31.1016 39.4561C32.0469 39.936 33.0396 40.1279 34.686 40.272C35.9546 40.3921 37.1758 40.208 38.1211 40.0078C39.6021 39.688 39.4995 38.2881 38.9639 38.0322C34.623 35.9678 35.5762 36.8081 34.71 36.1279C36.9155 33.4639 40.2402 30.6958 41.54 21.728C41.6426 21.0161 41.5557 20.5679 41.54 19.9917C41.5322 19.6396 41.6108 19.5039 42.0049 19.4639C43.0923 19.3359 44.1479 19.0317 45.1167 18.4878C47.9292 16.9199 49.064 14.3438 49.3315 11.2559C49.3711 10.7837 49.3237 10.2959 48.8354 10.0479ZM24.3262 37.8398C20.1196 34.4639 18.0791 33.3521 17.2358 33.3999C16.4482 33.4482 16.5898 34.3682 16.7632 34.9678C16.9443 35.5601 17.1812 35.9683 17.5117 36.4878C17.7402 36.832 17.8979 37.3442 17.2832 37.728C15.9282 38.584 13.5728 37.4399 13.4624 37.3838C10.7207 35.7358 8.42822 33.5601 6.81348 30.584C5.25342 27.7197 4.34766 24.6479 4.19775 21.3677C4.1582 20.5757 4.38672 20.2959 5.15869 20.1519C6.17529 19.96 7.22314 19.9199 8.23926 20.0718C12.5327 20.7119 16.1885 22.6719 19.2529 25.7759C21.002 27.5439 22.3252 29.6558 23.6885 31.7202C25.1377 33.9121 26.6978 36 28.6831 37.7119C29.3843 38.312 29.9434 38.7681 30.479 39.104C28.8643 39.2881 26.1699 39.3281 24.3262 37.8398ZM26.3433 24.6001C26.3433 24.248 26.6191 23.9678 26.9658 23.9678C27.0444 23.9678 27.1152 23.9839 27.1782 24.0078C27.2651 24.04 27.3438 24.0879 27.4067 24.1602C27.5171 24.272 27.5801 24.4321 27.5801 24.6001C27.5801 24.9521 27.3042 25.2319 26.9575 25.2319C26.6108 25.2319 26.3433 24.9521 26.3433 24.6001ZM32.6064 27.8799C32.2046 28.0479 31.8027 28.1919 31.4165 28.208C30.8179 28.2397 30.1641 27.9922 29.8096 27.688C29.2583 27.2158 28.8643 26.9521 28.6987 26.1279C28.6279 25.7759 28.6675 25.2319 28.7305 24.9199C28.8721 24.248 28.7144 23.8159 28.2495 23.4238C27.8716 23.104 27.3911 23.0161 26.8633 23.0161C26.666 23.0161 26.4849 22.9277 26.3511 22.856C26.1304 22.7441 25.9492 22.4639 26.1226 22.1201C26.1777 22.0078 26.4458 21.7358 26.5088 21.688C27.2256 21.272 28.0527 21.4077 28.8169 21.7197C29.5259 22.0161 30.0615 22.5601 30.834 23.3281C31.6216 24.2559 31.7632 24.5117 32.2124 25.208C32.5669 25.752 32.8901 26.312 33.1104 26.9521C33.2446 27.3521 33.0713 27.6802 32.6064 27.8799Z"
    />
  </svg>
);

// Gemini — no official asset has been sourced, so this is the four-point star
// silhouette the product is known by, not a claimed copy of the brand file.
const geminiMark = (size: number) => (
  <svg viewBox="0 0 24 24" fill="#4285F4" width={size} height={size} aria-hidden>
    <path d="M12 1.6c.6 4.4 3.4 7.2 7.8 7.8v.4c-4.4.6-7.2 3.4-7.8 7.8h-.4c-.6-4.4-3.4-7.2-7.8-7.8v-.4c4.4-.6 7.2-3.4 7.8-7.8h.4Z" />
  </svg>
);

const VENDORS: Record<string, Vendor> = {
  claude: { hue: "24 62% 48%", mark: claudeMark },
  gpt: { hue: "162 52% 34%", mark: openaiMark },
  gemini: { hue: "217 72% 52%", mark: geminiMark },
  grok: { hue: "0 0% 24%", mark: grokMark },
  deepseek: { hue: "225 72% 56%", mark: deepseekMark },
  qwen: { hue: "263 78% 59%", mark: qwenMark },
  kimi: { hue: "255 62% 18%", mark: kimiMark },
  minimax: { hue: "0 0% 12%", mark: minimaxMark },
  // No sourced artwork yet: a tinted glyph, deliberately not a claimed logo.
  mimo: { hue: "22 88% 52%", glyph: "square" },
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

function Glyph({ glyph }: { glyph: NonNullable<Vendor["glyph"]> }) {
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
  size = 17,
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
  // The family can be a catch-all like "Other" while the id still names the
  // vendor; label with whichever actually identifies it.
  const label = (family || "").trim().toLowerCase() === key ? family! : key;
  if (vendor.mark)
    return (
      <span className="vendor-mark" style={{ color: `hsl(${vendor.hue})` }} title={label}>
        {vendor.mark(size)}
      </span>
    );
  return (
    <svg
      className="vendor-mark"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      role="img"
      aria-label={label}
      style={{ color: `hsl(${vendor.hue})` }}
    >
      <Glyph glyph={vendor.glyph!} />
    </svg>
  );
}

/** Background tint for the badge holding a mark. */
export function vendorTint(family?: string, name?: string) {
  const key = vendorKey(family, name);
  const vendor = key ? VENDORS[key] : undefined;
  // Marks that carry their own tile need no plate behind them.
  if (!vendor || (vendor.mark && (key === "kimi" || key === "grok"))) return undefined;
  return `hsl(${vendor.hue} / 0.12)`;
}
