/** Idempotency keys that also work over a plain-http LAN address.
 *
 * `crypto.randomUUID` exists only in a secure context, which `localhost` and
 * HTTPS are and `http://192.168.x.x` is not. A phone reaching this machine by
 * its network address therefore had every write throw before it reached the
 * network: reads are GETs and carried no id, so the page looked fine until
 * someone pressed send.
 *
 * `crypto.getRandomValues` is not gated that way, so it is what the fallback
 * is built from. The value only has to be unique per request, which is what
 * 128 random bits gives; it is never used as a secret.
 */
export function newRequestId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  // RFC 4122 version 4 layout, so the id is shaped like the other one and the
  // server's requestId pattern accepts it unchanged.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return (
    hex.slice(0, 8) +
    "-" +
    hex.slice(8, 12) +
    "-" +
    hex.slice(12, 16) +
    "-" +
    hex.slice(16, 20) +
    "-" +
    hex.slice(20)
  );
}
