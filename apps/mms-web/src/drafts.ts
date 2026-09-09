import type { Attachment } from "./types";
export interface Draft {
  text: string;
  skills: string[];
  attachments: Attachment[];
  references: string[];
  thumbnails: Record<string, string>;
}
const key = "mms-web-drafts-v1";
const ttl = 7 * 24 * 60 * 60 * 1000;
const memory = new Map<string, Draft>();
type Saved = Omit<Draft, "thumbnails"> & { savedAt: number };
function stored(): Record<string, Saved> {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "{}");
    const valid: Record<string, Saved> = {};
    for (const [id, raw] of Object.entries(value)) {
      const d = raw as Saved;
      if (
        d &&
        typeof d.text === "string" &&
        typeof d.savedAt === "number" &&
        Date.now() - d.savedAt < ttl &&
        Array.isArray(d.skills) &&
        d.skills.every((x) => typeof x === "string") &&
        Array.isArray(d.references) &&
        d.references.every((x) => typeof x === "string") &&
        Array.isArray(d.attachments) &&
        d.attachments.every(
          (a) =>
            a &&
            typeof a.id === "string" &&
            typeof a.name === "string" &&
            typeof a.mimeType === "string",
        )
      )
        valid[id] = d;
    }
    return valid;
  } catch {
    return {};
  }
}
export function readDraft(id: string): Draft | undefined {
  if (memory.has(id)) return memory.get(id);
  const saved = stored()[id];
  return saved ? { ...saved, thumbnails: {} } : undefined;
}
export function saveDraft(id: string, draft: Draft): boolean {
  memory.set(id, draft);
  if (memory.size > 30) memory.delete(memory.keys().next().value!);
  try {
    const data = stored();
    if (
      !draft.text &&
      !draft.skills.length &&
      !draft.attachments.length &&
      !draft.references.length
    )
      delete data[id];
    else {
      const { thumbnails: _thumbnails, ...metadata } = draft;
      data[id] = { ...metadata, savedAt: Date.now() };
    }
    const entries = Object.entries(data)
      .sort((a, b) => b[1].savedAt - a[1].savedAt)
      .slice(0, 30);
    localStorage.setItem(key, JSON.stringify(Object.fromEntries(entries)));
    return true;
  } catch {
    return false;
  }
}
export function discardDraft(id: string) {
  memory.delete(id);
  try {
    const data = stored();
    delete data[id];
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    /* keep current page usable */
  }
}
