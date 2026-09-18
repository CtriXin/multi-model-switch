import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  Folder,
  GitBranch,
  RefreshCw,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { request } from "./api";

interface Entry {
  name: string;
  path: string;
  directory: boolean;
  size: number;
}
interface Preview {
  name: string;
  path?: string;
  kind: string;
  content?: string;
  dataUrl?: string;
}
export function FilePreview({ file }: { file: Preview }) {
  return (
    <div className="file-preview">
      {file.kind === "image" ? (
        <img src={file.dataUrl} alt={file.name} />
      ) : file.kind === "markdown" ? (
        <Markdown remarkPlugins={[remarkGfm]} skipHtml>
          {file.content}
        </Markdown>
      ) : (
        <pre>{file.content}</pre>
      )}
    </div>
  );
}
export function FilesPanel({
  workspaceId,
  onReference,
}: {
  workspaceId: string;
  onReference?: (path: string) => void;
}) {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [root, setRoot] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"files" | "git">("files");
  const [changes, setChanges] = useState<{ path: string; status: string }[]>(
    [],
  );
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setPath("");
    setPreview(null);
  }, [workspaceId]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPreview(null);
    const payload = { workspaceId, path };
    if (tab === "files")
      request<{ root: string; entries: Entry[] }>(
        "/files/tree",
        payload,
        controller.signal,
      )
        .then((d) => {
          setEntries(d.entries);
          setRoot(d.root);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    else
      request<{
        available: boolean;
        changes: typeof changes;
        message?: string;
      }>("/files/git", { workspaceId }, controller.signal)
        .then((d) => {
          setChanges(d.changes);
          if (!d.available) setError(d.message || "没有 Git 仓库");
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    return () => controller.abort();
  }, [workspaceId, path, tab, revision]);
  async function openFile(relative: string) {
    setError("");
    setLoading(true);
    try {
      if (tab === "git") {
        const data = await request<{ diff: string; truncated?: boolean }>(
          "/files/git",
          { workspaceId, path: relative },
        );
        setPreview({
          name: relative,
          path: relative,
          kind: "diff",
          content: data.diff || "此文件没有可显示的文本差异。",
        });
        if (data.truncated) setError("差异较长，当前显示前 200,000 字符。");
      } else
        setPreview(
          await request<Preview>("/files/read", {
            workspaceId,
            path: relative,
          }),
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="files-panel" aria-label="工作文件">
      <div className="files-toolbar">
        <button
          className={tab === "files" ? "active" : ""}
          onClick={() => setTab("files")}
        >
          <Folder size={14} />
          文件
        </button>
        <button
          className={tab === "git" ? "active" : ""}
          onClick={() => setTab("git")}
        >
          <GitBranch size={14} />
          变更
        </button>
        <button
          title="刷新文件"
          aria-label="刷新文件"
          onClick={() => setRevision((r) => r + 1)}
        >
          <RefreshCw size={14} />
        </button>
      </div>
      <p className="folder-path" title={root}>
        {root}
      </p>
      {preview ? (
        <>
          <div className="file-preview-heading">
            <button onClick={() => setPreview(null)}>
              <ArrowLeft size={14} />
              返回
            </button>
            <strong>{preview.name}</strong>
            {onReference && preview.path && (
              <button onClick={() => onReference(preview.path!)}>
                引用文件
              </button>
            )}
          </div>
          <FilePreview file={preview} />
        </>
      ) : (
        <>
          {tab === "files" && path && (
            <button
              className="file-row"
              onClick={() => setPath(path.split("/").slice(0, -1).join("/"))}
            >
              <ArrowLeft size={15} />
              上一级 <small>{path}</small>
            </button>
          )}
          {loading ? (
            <p className="section-note" role="status">
              正在读取文件…
            </p>
          ) : tab === "files" ? (
            entries.map((entry) => (
              <div className="file-row-wrap" key={entry.path}>
                <button
                  className="file-row"
                  onClick={() =>
                    entry.directory
                      ? setPath(entry.path)
                      : void openFile(entry.path)
                  }
                >
                  {entry.directory ? (
                    <Folder size={15} />
                  ) : (
                    <FileText size={15} />
                  )}
                  <span>{entry.name}</span>
                  {entry.directory && <ChevronRight size={14} />}
                </button>
                {!entry.directory && onReference && (
                  <button
                    className="reference-file"
                    title={"引用 " + entry.name}
                    onClick={() => onReference(entry.path)}
                  >
                    @
                  </button>
                )}
              </div>
            ))
          ) : (
            changes.map((change) => (
              <button
                className="file-row"
                key={change.path}
                onClick={() => void openFile(change.path)}
              >
                <span className="git-status">{change.status}</span>
                <span>{change.path}</span>
              </button>
            ))
          )}
          {!loading &&
            !error &&
            !(tab === "files" ? entries : changes).length && (
              <p className="section-note">
                {tab === "files"
                  ? "这个文件夹没有可显示的文件。"
                  : "工作目录没有 Git 变更。"}
              </p>
            )}
        </>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <p className="section-note">
        隐藏文件、凭据和依赖目录不显示。这里只查看文件，不修改 Git 状态。
      </p>
    </section>
  );
}
