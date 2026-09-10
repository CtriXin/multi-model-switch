/** Which Enter presses send the draft instead of typing a newline.
 *
 * With `enterToSend` on, Enter sends and Shift + Enter types a newline. Turning
 * it off swaps the two: Enter types, and the modifier sends. ⌘/Ctrl + Enter
 * sends either way, so that habit survives the setting.
 */
export function sendsOnEnter(
  event: { key: string; shiftKey: boolean; metaKey: boolean; ctrlKey: boolean },
  enterToSend: boolean,
): boolean {
  if (event.key !== "Enter") return false;
  return enterToSend ? !event.shiftKey : event.metaKey || event.ctrlKey;
}
