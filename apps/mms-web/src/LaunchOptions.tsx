import { useState } from "react";
import { ChevronDown, FolderOpen } from "lucide-react";
import type { Model, Preset, Workspace } from "./types";
import { Dialog } from "./components";
import { ModelExplorer } from "./ModelExplorer";
import { mutate } from "./api";

export function ModelPicker({
  presets,
  models,
  workspaceId,
  value,
  change,
  favorites,
  toggleFavorite,
  disabled = false,
}: {
  presets: Preset[];
  models: Model[];
  workspaceId: string;
  value: string;
  change: (id: string) => void;
  favorites: string[];
  toggleFavorite: (id: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [candidate, setCandidate] = useState(value);
  const selected = presets.find((p) => p.id === value);
  return (
    <>
      <button
        type="button"
        className="model-picker-trigger"
        disabled={disabled}
        onClick={() => {
          setCandidate(value);
          setOpen(true);
        }}
      >
        <span>
          <strong>{selected?.name || "选择模型"}</strong>
          <small>{selected?.channel || "选择接入通道"}</small>
        </span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <Dialog title="模型与通道" close={() => setOpen(false)}>
          <ModelExplorer
            presets={presets}
            models={models}
            workspaceId={workspaceId}
            value={candidate}
            change={setCandidate}
            favorites={favorites}
            toggleFavorite={toggleFavorite}
            choose={() => {
              change(candidate);
              setOpen(false);
            }}
          />
        </Dialog>
      )}
    </>
  );
}

export function WorkspaceDialog({
  close,
  added,
}: {
  close: () => void;
  added: (workspace: Workspace) => void;
}) {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function choose() {
    setBusy(true);
    setError("");
    try {
      const result = await mutate<{ path: string }>("/workspaces/choose", {});
      if (result.path) setPath(result.path);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      added(await mutate<Workspace>("/workspaces", { path }));
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="添加工作文件夹" close={close}>
      <p className="dialog-intro">
        把资料和生成的文件放在一起。AI 会在这个文件夹中开始工作。
      </p>
      <form className="workspace-form" onSubmit={submit}>
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => void choose()}
        >
          <FolderOpen size={16} />
          从电脑中选择文件夹
        </button>
        <label>
          也可以填写文件夹路径
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/Users/你的名字/Documents/项目"
            required
            autoComplete="off"
          />
        </label>
        {error && (
          <p role="alert" className="inline-alert">
            {error}
          </p>
        )}
        <button
          className="button primary"
          disabled={busy || !path.trim()}
          type="submit"
        >
          {busy ? "正在连接…" : "使用这个文件夹"}
        </button>
      </form>
    </Dialog>
  );
}
