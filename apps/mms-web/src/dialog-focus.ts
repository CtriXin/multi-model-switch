/** Native <dialog>.showModal() focuses the first control, usually Close.
 *  React 19 also does not put `autofocus` in the DOM, so `autoFocus` alone
 *  never wins. After showModal, put the caret where typing should start. */

export function scheduleDialogAutofocus(root: ParentNode | null): () => void {
  const run = () => {
    const node = pickAutofocus(root);
    if (!node) return;
    node.focus();
    if (isSelectableField(node) && node.value) node.select();
  };
  run();
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame(run) : 0;
  const timer = setTimeout(run, 50);
  return () => {
    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(raf);
    clearTimeout(timer);
  };
}

export function pickAutofocus(root: ParentNode | null): HTMLElement | null {
  if (!root) return null;
  const marked = root.querySelector<HTMLElement>("[data-autofocus], [autofocus]");
  if (marked) return marked;
  const list = typeof root.querySelectorAll === "function"
    ? [...root.querySelectorAll<HTMLElement>("input, textarea")]
    : [];
  const fields = list.filter((el) => isSelectableField(el) && !(el as HTMLInputElement).disabled);
  return fields.length === 1 ? fields[0] : null;
}

function isSelectableField(
  node: HTMLElement,
): node is HTMLInputElement | HTMLTextAreaElement {
  const tag = node.tagName;
  if (tag === "TEXTAREA") return true;
  if (tag !== "INPUT") return false;
  const type = (node as HTMLInputElement).type || "text";
  return type !== "checkbox" && type !== "radio" && type !== "button" && type !== "submit";
}
