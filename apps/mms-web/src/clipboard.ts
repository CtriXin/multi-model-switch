/** Copy text without throwing when there is no clipboard to copy to.
 *
 * `navigator.clipboard` is undefined outside a secure context, so on a plain
 * http LAN address reading `.writeText` off it throws synchronously. A promise
 * `.catch()` never sees that, which turned three copy buttons into uncaught
 * errors on a phone. Callers get false instead and can say so.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
