export type PreviewKind = "image" | "markdown" | "csv" | "html" | "json" | "text" | "pdf" | "audio" | "video" | "unsupported";
type FileInfo = { name: string; kind?: string; mimeType?: string | null };
const types: Record<string, [PreviewKind, string]> = {
  png: ["image", "image/png"], jpg: ["image", "image/jpeg"], jpeg: ["image", "image/jpeg"],
  gif: ["image", "image/gif"], webp: ["image", "image/webp"], svg: ["image", "image/svg+xml"],
  avif: ["image", "image/avif"], bmp: ["image", "image/bmp"], ico: ["image", "image/x-icon"],
  md: ["markdown", "text/markdown"], markdown: ["markdown", "text/markdown"],
  csv: ["csv", "text/csv"], tsv: ["csv", "text/tab-separated-values"],
  html: ["html", "text/html"], htm: ["html", "text/html"], json: ["json", "application/json"],
  pdf: ["pdf", "application/pdf"], mp3: ["audio", "audio/mpeg"], wav: ["audio", "audio/wav"],
  ogg: ["audio", "audio/ogg"], oga: ["audio", "audio/ogg"], flac: ["audio", "audio/flac"],
  m4a: ["audio", "audio/mp4"], aac: ["audio", "audio/aac"], opus: ["audio", "audio/ogg"],
  mp4: ["video", "video/mp4"], webm: ["video", "video/webm"], mov: ["video", "video/quicktime"], ogv: ["video", "video/ogg"],
};
const textExtensions = new Set("txt text log js jsx ts tsx mjs cjs py rb go rs java kt swift c h cpp hpp css scss less sh bash zsh sql xml yaml yml toml ini conf env gitignore dockerfile makefile r vue svelte patch diff jsonl ndjson".split(" "));

export function previewType(file: FileInfo): { kind: PreviewKind; mime: string } {
  const suffix = file.name.toLowerCase().split(".").at(-1) || "";
  const known = types[suffix];
  if (known) return { kind: known[0], mime: known[1] };
  const mime = (file.mimeType || "").split(";")[0].trim().toLowerCase();
  if (file.kind === "screenshot") return { kind: "image", mime: mime || "image/png" };
  if (mime.startsWith("image/")) return { kind: "image", mime };
  if (mime.startsWith("audio/")) return { kind: "audio", mime };
  if (mime.startsWith("video/")) return { kind: "video", mime };
  if (mime === "application/pdf") return { kind: "pdf", mime };
  if (mime === "application/json" || mime.endsWith("+json")) return { kind: "json", mime };
  if (textExtensions.has(suffix) || mime.startsWith("text/")) return { kind: "text", mime: "text/plain" };
  return { kind: "unsupported", mime: mime || "application/octet-stream" };
}

export function artifactContentUrl(raw: string, origin: string): string {
  try {
    const url = new URL(raw, origin);
    if (url.origin !== origin || url.username || url.password ||
        !/^\/api\/v1\/tasks\/[^/]+\/artifacts\/[^/]+\/content$/.test(url.pathname)) return "";
    return url.origin + url.pathname;
  } catch { return ""; }
}

export const PREVIEW_BYTE_LIMIT = 8 * 1024 * 1024;
export const TEXT_BYTE_LIMIT = 1024 * 1024;
export const TEXT_DISPLAY_LIMIT = 200_000;

export async function readPreviewBytes(response: Response, limit: number): Promise<Uint8Array> {
  if (Number(response.headers.get("Content-Length")) > limit) {
    await response.body?.cancel();
    throw new Error("文件超出预览大小限制，请下载查看完整内容。");
  }
  if (!response.body) return new Uint8Array();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new Error("文件超出预览大小限制，请下载查看完整内容。");
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}

export function decodePreviewText(bytes: Uint8Array): string {
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    if (/[\u0000-\u0008\u000e-\u001f]/.test(text)) throw new Error();
    return text;
  } catch { throw new Error("此文件不是可读取的 UTF-8 文本，请下载后用相应应用查看。"); }
}

// Quoted fields, escaped quotes, CRLF and embedded newlines are kept intact.
export function parseDelimited(text: string, delimiter = ",") {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false, truncated = false, fields = 0;
  const pushCell = () => { if (fields++ < 50) row.push(cell); else truncated = true; cell = ""; };
  const pushRow = () => { pushCell(); rows.push(row); row = []; fields = 0; };
  const source = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '"') {
      if (quoted && source[i + 1] === '"') { cell += '"'; i++; }
      else if (quoted || cell === "") quoted = !quoted;
      else cell += c;
    } else if (!quoted && c === delimiter) pushCell();
    else if (!quoted && (c === "\n" || c === "\r")) {
      if (c === "\r" && source[i + 1] === "\n") i++;
      pushRow();
      if (rows.length === 200) { truncated ||= i + 1 < source.length; return { rows, truncated }; }
    } else cell += c;
  }
  if (cell || row.length || fields || source.endsWith(delimiter)) pushRow();
  return { rows, truncated };
}
