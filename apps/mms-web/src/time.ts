// Message time and turn duration, shown in the transcript.
// Durations climb through 秒 / 分 / 小时 / 天 so a long turn never reads as a
// bare second count.

const CLOCK: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hour12: false };

function parse(value?: string): Date | null {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? null : at;
}

/** Local clock time; older messages keep their date so the day stays clear. */
export function formatEventTime(value?: string): string {
  const at = parse(value);
  if (!at) return "";
  const now = new Date();
  const clock = at.toLocaleTimeString("zh-CN", CLOCK);
  if (at.toDateString() === now.toDateString()) return clock;
  const date = at.toLocaleDateString("zh-CN", at.getFullYear() === now.getFullYear()
    ? { month: "2-digit", day: "2-digit" }
    : { year: "numeric", month: "2-digit", day: "2-digit" });
  return `${date} ${clock}`;
}

/** Full timestamp for the hover title, so the short label stays short. */
export function formatEventTimeTitle(value?: string): string {
  const at = parse(value);
  return at ? at.toLocaleString("zh-CN") : "";
}

/** Round a millisecond span to at most two units: 3 天 4 小时, 2 分 13 秒. */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  const total = Math.max(1, Math.round(ms / 1000));
  const day = Math.floor(total / 86400);
  const hour = Math.floor((total % 86400) / 3600);
  const minute = Math.floor((total % 3600) / 60);
  const second = total % 60;
  if (day) return hour ? `${day} 天 ${hour} 小时` : `${day} 天`;
  if (hour) return minute ? `${hour} 小时 ${minute} 分` : `${hour} 小时`;
  if (minute) return second ? `${minute} 分 ${second} 秒` : `${minute} 分`;
  return `${second} 秒`;
}

/** Time from the turn's start to the last update of the reply. */
export function turnDuration(startedAt?: string, endedAt?: string): string {
  const start = parse(startedAt);
  const end = parse(endedAt);
  if (!start || !end) return "";
  return formatDuration(end.getTime() - start.getTime());
}
