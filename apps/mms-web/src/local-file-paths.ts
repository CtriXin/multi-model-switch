/** Recognize pasted Finder/terminal paths without guessing a File object's origin. */
export function localFilePaths(value: string): string[] {
  const paths = value
    .trim()
    .split(/\r?\n/)
    .map((line) => {
      let path = line.trim();
      if (path.startsWith('"') && path.endsWith('"')) {
        try { path = JSON.parse(path); }
        catch { path = path.slice(1, -1); }
      } else if (path.startsWith("'") && path.endsWith("'"))
        path = path.slice(1, -1);
      if (path.toLowerCase().startsWith("file://")) {
        try {
          // URL() treats file://C:/... as a hostname. Normalize Windows drive
          // and UNC file URLs explicitly before applying the local-path check.
          const raw = path.slice(7); // after "file://"
          if (/^[A-Za-z]:[\\/]/.test(raw) || /^\/[A-Za-z]:[\\/]/.test(raw)) {
            path = decodeURIComponent(raw.replace(/^\//, ""));
          } else {
            const url = new URL(path);
            if (url.hostname && url.hostname !== "localhost") {
              // file://server/share/... is the URL form of the UNC path
              // \\server\share\... — not a foreign host to reject.
              path = "\\\\" + decodeURIComponent(url.hostname + url.pathname).replaceAll("/", "\\");
            } else {
              path = decodeURIComponent(url.pathname);
              // file://localhost/C:/... still carries a leading slash; restore
              // the drive form so the Windows path check below can match it.
              const drive = /^\/([A-Za-z]:[\\/].*)$/.exec(path);
              if (drive) path = drive[1];
            }
          }
        } catch {
          return "";
        }
      }
      // A pasted /help or /thinking high remains a command, not a file reference.
      return path.startsWith("~/") ||
        /^\/.*\/[^/]*$/.test(path) ||
        /^\/[^/]+\.[^/]+$/.test(path) ||
        /^[A-Za-z]:[\\/]/.test(path) ||
        /^\\\\[^\\]+\\[^\\]+/.test(path)
        ? path
        : "";
    });
  return paths.length && paths.every(Boolean) ? paths : [];
}
