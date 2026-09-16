export interface WorkIdentity {
  id: string;
  name: string;
  presetId: string;
  effort: string;
  persona: string;
}

export const IDENTITY_LIST_KEY = "mms-web-identities";
export const IDENTITY_ACTIVE_KEY = "mms-web-identity";
const MAX_IDENTITIES = 12;
const MAX_NAME = 24;
const MAX_PERSONA = 200;

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Browser storage unavailable: current choice still works. */
  }
}

export function readIdentities(): WorkIdentity[] {
  const rows = readJson<WorkIdentity[]>(IDENTITY_LIST_KEY, []);
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => row && typeof row.id === "string" && typeof row.name === "string" && typeof row.presetId === "string")
    .slice(0, MAX_IDENTITIES)
    .map((row) => ({
      id: row.id.slice(0, 80),
      name: row.name.trim().slice(0, MAX_NAME),
      presetId: row.presetId.slice(0, 500),
      effort: typeof row.effort === "string" ? row.effort.slice(0, 40) : "",
      persona: typeof row.persona === "string" ? row.persona.trim().slice(0, MAX_PERSONA) : "",
    }))
    .filter((row) => row.id && row.name && row.presetId);
}

export function saveIdentities(list: WorkIdentity[]) {
  writeJson(IDENTITY_LIST_KEY, list.slice(0, MAX_IDENTITIES));
}

export function readActiveIdentityId(): string {
  const value = readJson<string>(IDENTITY_ACTIVE_KEY, "");
  return typeof value === "string" ? value : "";
}

export function saveActiveIdentityId(id: string) {
  writeJson(IDENTITY_ACTIVE_KEY, id);
}

export function identityMatches(identity: WorkIdentity | undefined, presetId: string, effort: string) {
  if (!identity) return false;
  return identity.presetId === presetId && (identity.effort || "") === (effort || "");
}

export function applyPersona(text: string, identity: WorkIdentity | undefined) {
  const persona = identity?.persona.trim();
  if (!identity || !persona) return text;
  return `（工作身份：${identity.name}）\n${persona}\n\n${text}`;
}

export function createIdentity(input: {
  name: string;
  presetId: string;
  effort: string;
  persona: string;
}): WorkIdentity | null {
  const name = input.name.trim().slice(0, MAX_NAME);
  if (!name || !input.presetId) return null;
  return {
    id: `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    presetId: input.presetId,
    effort: (input.effort || "").slice(0, 40),
    persona: input.persona.trim().slice(0, MAX_PERSONA),
  };
}
