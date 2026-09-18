/** Capture drop entries synchronously: browsers clear DataTransfer after the event. */
export function droppedItems(transfer: DataTransfer): { folders: FileSystemDirectoryEntry[]; files: File[] } {
  const folders: FileSystemDirectoryEntry[] = [];
  const files: File[] = [];
  if (!transfer.items.length) return { folders, files: Array.from(transfer.files) };
  for (const item of Array.from(transfer.items)) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) folders.push(entry as FileSystemDirectoryEntry);
    else {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return { folders, files };
}

/**
 * A dropped folder arrives without its location: the browser only exposes the
 * name and contents. Its entries are the fingerprint the local service uses to
 * tell one folder called "src" from another.
 */
export function folderChildren(entry: FileSystemDirectoryEntry, limit = 100): Promise<string[]> {
  return new Promise((resolve) => {
    const reader = entry.createReader?.();
    if (!reader) return resolve([]);
    const names: string[] = [];
    const done = setTimeout(() => resolve(names), 3000);
    const read = () =>
      reader.readEntries(
        (batch) => {
          for (const child of batch) names.push(child.name);
          // readEntries returns one batch at a time and an empty batch at the end.
          if (batch.length && names.length < limit) read();
          else { clearTimeout(done); resolve(names.slice(0, limit)); }
        },
        () => { clearTimeout(done); resolve(names); },
      );
    read();
  });
}
