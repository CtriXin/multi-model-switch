export function parseSemver(v: string): [number, number, number] | null {
  const m = String(v).trim().replace(/^v/, "").match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

export function compareSemverDesc(a: string, b: string): number {
  const pa = parseSemver(a);
  const pb = parseSemver(b);
  if (!pa && !pb) return b.localeCompare(a);
  if (!pa) return 1;
  if (!pb) return -1;
  if (pa[0] !== pb[0]) return pb[0] - pa[0];
  if (pa[1] !== pb[1]) return pb[1] - pa[1];
  return pb[2] - pa[2];
}
