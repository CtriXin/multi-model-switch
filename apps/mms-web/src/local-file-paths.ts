/** Recognize pasted Finder/terminal paths without guessing a File object's origin. */
export function localFilePaths(value: string): string[] {
  const paths = value
    .trim()
    .split(/\r?\n/)
    .map((line) => {
      let path = line.trim();
      if (
        (path.startsWith("'") && path.endsWith("'")) ||
        (path.startsWith('"') && path.endsWith('"'))
      )
        path = path.slice(1, -1);
      if (path.startsWith("file://")) {
        try {
          const url = new URL(path);
          if (url.hostname && url.hostname !== "localhost") return "";
          path = decodeURIComponent(url.pathname);
        } catch {
          return "";
        }
      }
      // A pasted /help or /thinking high remains a command, not a file reference.
      return path.startsWith("~/") ||
        /^\/.*\/[^/]+$/.test(path) ||
        /^\/[^/]+\.[^/]+$/.test(path)
        ? path
        : "";
    });
  return paths.length && paths.every(Boolean) ? paths : [];
}
