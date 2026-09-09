/** Capture drop entries synchronously: browsers clear DataTransfer after the event. */
export function droppedItems(transfer: DataTransfer): { folders: string[]; files: File[] } {
  const folders: string[] = [];
  const files: File[] = [];
  if (!transfer.items.length) return { folders, files: Array.from(transfer.files) };
  for (const item of Array.from(transfer.items)) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) folders.push(entry.name);
    else {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return { folders, files };
}
