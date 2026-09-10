import { appendGuidePrompt } from "./guide-content";
import { readDraft, saveDraft, discardDraft } from "./drafts";
import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, RefObject } from "react";
import {
  CircleAlert,
  ArrowUp,
  BookOpen,
  AtSign,
  ImagePlus,
  LoaderCircle,
  Paperclip,
  Plus,
  Square,
  Terminal,
  X,
} from "lucide-react";
import { Popover } from "./Popover";
import { SkillPicker } from "./SkillPicker";
import type { Skill } from "./SkillPicker";
import { request } from "./api";
import { SKILL_PREFERENCES_EVENT } from "./SkillSources";
import type { Attachment, FileSelection } from "./types";
import { FilesPanel } from "./FilesPanel";
import { localFilePaths } from "./local-file-paths";
import { requiredSkillMatches } from "./recipe-core";
const noRequiredSkills: string[] = [];
import { droppedItems } from "./dropped-items";
import { WorkspaceDialog } from "./LaunchOptions";

export interface MessageExtras {
  skillInvocation?: string;
  skills: string[];
  attachments: string[];
  references: string[];
  fileSelections: FileSelection[];
}
interface CommandItem {
  name: string;
  description: string;
  source?: string;
}
const commands: CommandItem[] = [
  { name: "help", description: "查看使用方式与快捷键" },
  { name: "files", description: "浏览工作文件，添加 @ 引用" },
  { name: "plan", description: "切换只读规划：/plan on 或 /plan off" },
  { name: "thinking", description: "调整思考等级，例如 /thinking high" },
  { name: "compact", description: "压缩上下文；可在命令后补充保留要求" },
  { name: "clear-queue", description: "清空尚未执行的补充消息" },
  { name: "name", description: "重命名会话，例如 /name 产品方案" },
  { name: "fork", description: "从当前进度创建独立会话分支" },
  { name: "export", description: "下载这段对话的 Markdown" },
];

export function Composer({
  disabled,
  reason,
  busy,
  running,
  send,
  stop,
  children,
  workspaceId,
  sessionId,
  sessionAlive,
  onCommand,
  initialText = "",
  requiredSkillNames = noRequiredSkills,
  selectionRequest,
  selectionHandled,
  guideRequest,
  guideHandled,
  draftKey: providedDraftKey,
  placeholder = "继续补充你的想法…",
  scroll,
}: {
  initialText?: string;
  requiredSkillNames?: string[];
  guideRequest?: { nonce: string; text: string };
  guideHandled?: () => void;
  selectionRequest?: { nonce: string; selection: FileSelection };
  selectionHandled?: () => void;
  draftKey?: string;
  disabled: boolean;
  reason?: string;
  busy: boolean;
  running?: boolean;
  send: (value: string, extras: MessageExtras) => Promise<boolean>;
  stop?: () => void;
  children?: ReactNode;
  placeholder?: string;
  workspaceId?: string;
  sessionId?: string;
  sessionAlive?: boolean;
  /** Transcript scroller; enables the scroll-aware fold when provided. */
  scroll?: RefObject<HTMLDivElement | null>;
  onCommand?: (command: string, args: string) => Promise<boolean>;
}) {
  const draftKey =
    providedDraftKey ||
    (sessionId ? `session:${sessionId}` : `new:${workspaceId}`);
  const draft = readDraft(draftKey);
  const [draftLocalOnly, setDraftLocalOnly] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>(
    draft?.skills || [],
  );
  const [skillError, setSkillError] = useState("");
  const [skillsReady, setSkillsReady] = useState(false);
  const requiredSkillKey = requiredSkillNames.join("|");
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [folderDrops, setFolderDrops] = useState<string[]>([]);
  function toggleSkill(id: string) {
    if (lock.current) return;
    setSelectedSkills((old) =>
      old.includes(id)
        ? old.filter((i) => i !== id)
        : [...old, id].slice(0, 20),
    );
  }
  const [skillsRevision, setSkillsRevision] = useState(0);
  useEffect(() => {
    const bump = () => setSkillsRevision(n => n + 1);
    window.addEventListener(SKILL_PREFERENCES_EVENT, bump);
    return () => window.removeEventListener(SKILL_PREFERENCES_EVENT, bump);
  }, []);
  useEffect(() => {
    let cancelled = false;
    setSkills([]);
    setSkillsReady(false);
    setSkillError("");
    if (workspaceId)
      request<{ skills: Skill[] }>("/skills", { workspaceId })
        .then((d) => {
          if (!cancelled) {
            setSkills(d.skills); setSkillsReady(true);
            setSelectedSkills(ids => {
              const kept = ids.filter(id => d.skills.some(s => s.id === id));
              const defaults = draft ? [] : requiredSkillMatches(requiredSkillNames, d.skills).ids;
              return [...new Set([...kept, ...defaults])].slice(0, 20);
            });
          }
        })
        .catch((e) => {
          if (!cancelled) setSkillError(e.message);
        });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, requiredSkillKey, skillsRevision]);
  const requirementIssues = requiredSkillNames.length ? (skillsReady ? requiredSkillMatches(requiredSkillNames, skills, selectedSkills).issues : [skillError || "正在核对模板所需的 Skills。"]) : [];
  const [text, setText] = useState(() => {
    const original = draft?.text ?? initialText;
    const paths = (draft?.attachments || []).flatMap(a => a.localPath && !original.includes(a.localPath) && !original.includes(JSON.stringify(a.localPath)) ? [JSON.stringify(a.localPath)] : []);
    return paths.length ? [original, ...paths].filter(Boolean).join("\n") : original;
  });
  const [fileSelections, setFileSelections] = useState<FileSelection[]>(draft?.fileSelections || []);
  const [submitting, setSubmitting] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>(
    draft?.attachments || [],
  );
  const [references, setReferences] = useState<string[]>(
    draft?.references || [],
  );
  const [thumbnails, setThumbnails] = useState<Record<string, string>>(
    draft?.thumbnails || {},
  );
  useEffect(() => {
    setDraftLocalOnly(
      !saveDraft(draftKey, {
        text,
        skills: selectedSkills,
        attachments: attachments.filter(a => referencedInText(a)),
        references,
        thumbnails,
        fileSelections,
      }),
    );
  }, [draftKey, text, selectedSkills, attachments, references, thumbnails, fileSelections]);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [localFilesBusy, setLocalFilesBusy] = useState(false);
  const [filePathHint, setFilePathHint] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    for (const attachment of attachments) {
      if (draft?.thumbnails[attachment.id]) continue;
      if (!attachment.mimeType.startsWith("image/")) continue;
      request<{ dataUrl?: string }>(
        "/attachments/" + encodeURIComponent(attachment.id),
        undefined,
        controller.signal,
      )
        .then((result) => {
          if (!controller.signal.aborted && result.dataUrl)
            setThumbnails((old) => ({
              ...old,
              [attachment.id]: result.dataUrl!,
            }));
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError(
              `草稿附件“${attachment.name}”无法恢复，请移除后重新添加。`,
            );
        });
    }
    return () => controller.abort();
  }, [draftKey, attachments]);
  // Recipe variables and restored drafts can already contain absolute paths.
  // Resolve those lines once so the composer can show the same removable
  // preview cards as a direct file drop.
  useEffect(() => {
    if (draft?.attachments?.length || !initialText) return;
    const paths = initialText.split(/\r?\n/).flatMap((line) => localFilePaths(line));
    if (!paths.length || !workspaceId) return;
    const controller = new AbortController();
    request<{ attachments: Attachment[] }>("/files/reference-local", { paths }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setAttachments((old) => {
          const known = new Set(old.map((item) => item.localPath));
          return [...old, ...result.attachments.filter((item) => !known.has(item.localPath))].slice(0, 8);
        });
      })
      .catch(() => {});
    return () => controller.abort();
  }, [draftKey]);
  const [help, setHelp] = useState(false);
  const [files, setFiles] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [nativeCommands, setNativeCommands] = useState<CommandItem[]>([]);
  const [choice, setChoice] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  // Scroll-aware fold: a deliberate upward scroll in the transcript means
  // "I am reading", so the composer folds to one line. Scrolling back down,
  // reaching the latest message, focusing or clicking the box restores it.
  const [collapsed, setCollapsed] = useState(false);
  const [focused, setFocused] = useState(false);
  const collapsedRef = useRef(false);
  collapsedRef.current = collapsed;
  const canCollapseRef = useRef((): boolean => false);
  function setCollapsedState(next: boolean) {
    if (next) {
      // Native top-layer popovers would stay floating over the transcript
      // with their anchor folded away; dismiss them instead.
      formRef.current
        ?.querySelectorAll<HTMLElement>("[popover]")
        .forEach((p) => {
          try {
            if (p.matches(":popover-open")) p.hidePopover();
          } catch {
            /* engines without the popover API */
          }
        });
    }
    setCollapsed(next);
  }
  // The box grew with neither the text nor the window: three rows with an
  // inner scrollbar while the page below it sat empty. It now follows the
  // content up to a share of the viewport, and stops following as soon as the
  // person drags the corner, so a chosen height is not overwritten on typing.
  const dragged = useRef(false);
  function fitToContent() {
    const el = input.current;
    if (!el || dragged.current || collapsedRef.current) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, Math.round(window.innerHeight * 0.4))}px`;
  }
  // Keyed on the text rather than the change handler, so a restored draft, an
  // imported template and an inserted file path all size the box too.
  useEffect(fitToContent, [text]);
  useEffect(() => {
    const refit = () => fitToContent();
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
  }, []);
  const consumedSelection = useRef("");
  const consumedGuide = useRef("");
  useEffect(() => {
    if (!guideRequest || consumedGuide.current === guideRequest.nonce) return;
    consumedGuide.current = guideRequest.nonce;
    setText(old => appendGuidePrompt(old, guideRequest.text));
    input.current?.focus();
    guideHandled?.();
  }, [guideRequest?.nonce]);
  useEffect(() => {
    if (!selectionRequest || consumedSelection.current === selectionRequest.nonce) return;
    consumedSelection.current = selectionRequest.nonce;
    if (fileSelections.length >= 4) setError("最多引用 4 个选段，请先移除已有选段。");
    else {
      setFileSelections(old => [...old, selectionRequest.selection]);
      input.current?.focus();
    }
    selectionHandled?.();
  }, [selectionRequest?.nonce]);
  const dialog = useRef<HTMLDialogElement>(null);
  const lock = useRef(false);
  const uploadLock = useRef(false);
  const dragDepth = useRef(0);
  useEffect(() => {
    if (!sessionId) return;
    const c = new AbortController();
    request<{ commands: CommandItem[] }>(
      `/sessions/${sessionId}/commands`,
      undefined,
      c.signal,
    )
      .then((d) => setNativeCommands(d.commands))
      .catch(() => {});
    return () => c.abort();
  }, [sessionId, sessionAlive]);
  useEffect(() => {
    if (files && !dialog.current?.open) dialog.current?.showModal();
    else if (!files) dialog.current?.close();
  }, [files]);
  const menu = !dismissed && /^\/[\w:-]*$/.test(text);
  // Anything that needs the reader's attention or holds an open surface
  // vetoes the fold; evaluated lazily so the scroll listener never sees
  // stale state.
  canCollapseRef.current = () =>
    !focused &&
    !menu &&
    !skillsOpen &&
    !files &&
    !help &&
    !submitting &&
    !uploading &&
    !localFilesBusy &&
    !error &&
    !uploadErrors.length &&
    !requirementIssues.length &&
    !(disabled && reason);
  useEffect(() => {
    const el = scroll?.current;
    if (!el) return;
    let last = el.scrollTop;
    let up = 0;
    let down = 0;
    const onScroll = () => {
      const top = el.scrollTop;
      const delta = top - last;
      last = top;
      const gap = el.scrollHeight - top - el.clientHeight;
      // Hysteresis: fold only after a real upward intent, unfold eagerly.
      if (delta < 0) {
        up += -delta;
        down = 0;
      } else if (delta > 0) {
        down += delta;
        up = 0;
      }
      // The fold itself shrinks the composer and grows the scroller's
      // clientHeight, moving the gap by ~100px. Gating every transition on
      // the scroll direction — unfold only on a real downward delta, fold
      // only when the gap clearly exceeds the layout shift — keeps that
      // self-inflicted movement from bouncing the state back and forth.
      if (delta > 0 && gap < 48) {
        up = down = 0;
        setCollapsedState(false);
        return;
      }
      if (up > 48 && gap > 240 && canCollapseRef.current()) {
        setCollapsedState(true);
        up = 0;
      } else if (down > 24) {
        setCollapsedState(false);
        down = 0;
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scroll]);
  // A guard flipping on (error, picker, upload…) cancels the fold at once.
  useEffect(() => {
    if (collapsed && !canCollapseRef.current()) setCollapsedState(false);
  });
  useEffect(() => {
    if (!collapsed) fitToContent();
  }, [collapsed]);
  const items = [
    ...commands.filter((c) => sessionId || ["help", "files"].includes(c.name)),
    ...nativeCommands.filter(
      (c) =>
        !commands.some((b) => b.name === c.name) &&
        !c.name.startsWith("skill:"),
    ),
    ...skills.map((s) => ({
      name: "skill:" + s.name,
      description: s.description,
      source: s.source,
    })),
  ]
    .filter((c) => c.name.toLowerCase().includes(text.slice(1).toLowerCase()))
    .slice(0, 10);
  function insertCommand(item: CommandItem) {
    if (item.name.startsWith("skill:")) {
      const skill = skills.find((s) => "skill:" + s.name === item.name);
      if (skill && !selectedSkills.includes(skill.id)) toggleSkill(skill.id);
      setText("");
      setDismissed(true);
      input.current?.focus();
      return;
    }
    setText("/" + item.name + " ");
    setDismissed(true);
    input.current?.focus();
  }
  function reference(path: string) {
    setReferences((old) => [...new Set([...old, path])].slice(0, 20));
    setFiles(false);
    setText((old) => old.replace(/(^|\s)@[^\s]*$/, "$1"));
    input.current?.focus();
  }
  function referencedInText(item: Attachment, value = text) {
    return !item.localPath || value.includes(item.localPath) || value.includes(JSON.stringify(item.localPath));
  }
  function insertPaths(paths: string[]) {
    if (!paths.length) return;
    const element = input.current;
    const current = element?.value ?? text;
    const start = element?.selectionStart ?? current.length;
    const end = element?.selectionEnd ?? start;
    const before = current.slice(0, start);
    const after = current.slice(end);
    const inserted = (before && !/\s$/.test(before) ? "\n" : "") + paths.map(path => JSON.stringify(path)).join("\n") + "\n";
    setText(before + inserted + after);
    setDismissed(true);
    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(before.length + inserted.length, before.length + inserted.length);
    });
  }
  async function addLocalFiles(paths?: string[]) {
    if (uploadLock.current) return;
    uploadLock.current = true;
    setLocalFilesBusy(true);
    setError("");
    setFilePathHint("");
    try {
      const result = await request<{ attachments: Attachment[]; directories?: string[] }>(
        paths ? "/files/reference-local" : "/files/choose-local",
        paths ? { paths } : {},
      );
      const fresh = result.attachments.filter(
        (item) => !attachments.some((old) => referencedInText(old) && old.localPath === item.localPath),
      );
      if (attachments.filter(a => referencedInText(a)).length + fresh.length > 8)
        throw new Error("每条消息最多引用 8 个文件，请减少选择。");
      setAttachments((old) => [...old.filter(a => referencedInText(a)), ...fresh]);
      insertPaths([...result.attachments.flatMap(item => item.localPath ? [item.localPath] : []), ...(result.directories || [])]);
      for (const item of fresh.filter((item) =>
        item.mimeType.startsWith("image/"),
      )) {
        request<{ dataUrl?: string }>("/attachments/" + item.id)
          .then((preview) => {
            if (preview.dataUrl)
              setThumbnails((old) => ({ ...old, [item.id]: preview.dataUrl! }));
          })
          .catch(() => {});
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      uploadLock.current = false;
      setLocalFilesBusy(false);
    }
  }
  async function upload(list: File[]) {
    if (uploadLock.current || !list.length) return;
    uploadLock.current = true;
    setUploading(true);
    setError("");
    setUploadErrors([]);
    const failures: string[] = [];
    try {
      if (attachments.filter(a => referencedInText(a)).length + list.length > 8)
        throw new Error("每条消息最多 8 个附件。");
      if (!workspaceId) throw new Error("先选一个工作文件夹，拖入的文件会保存在里面。");
      const imported: Attachment[] = [];
      for (const file of list) {
        try {
          if (file.size > 8 * 1024 * 1024)
            throw new Error("文件超过 8 MB，可直接粘贴原文件路径引用。");
          const dataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result));
            reader.onerror = () => reject(new Error("无法读取 " + file.name));
            reader.readAsDataURL(file);
          });
          const item = await request<Attachment>("/files/import", {
            workspaceId,
            name: file.name,
            data: dataUrl.split(",")[1],
          });
          imported.push(item);
        } catch (e) {
          failures.push(`${file.name}：${(e as Error).message}`);
        }
      }
      setAttachments((old) => [...old.filter(a => referencedInText(a)), ...imported]);
      insertPaths(imported.flatMap(item => item.localPath ? [item.localPath] : []));
      if (imported.length) setFilePathHint("文件已保存到项目的 .pilot/attachments，路径已插入正文，可在其他会话继续引用。30 天内没有任何会话引用的副本会自动清理。");
    } catch (e) {
      failures.push((e as Error).message);
    } finally {
      setUploadErrors(failures);
      uploadLock.current = false;
      setUploading(false);
    }
  }
  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (
      (!text.trim() && !attachments.some(a => referencedInText(a))) ||
      disabled ||
      requirementIssues.length > 0 ||
      busy ||
      uploading ||
      localFilesBusy ||
      lock.current
    )
      return;
    lock.current = true;
    setSubmitting(true);
    setError("");
    try {
      let outgoing = text.trim();
      let outgoingSkills = selectedSkills;
      let skillInvocation: string | undefined;
      const skillMatch = outgoing.match(/^\/skill:([^\s]+)(?:\s+([\s\S]*))?$/);
      if (skillMatch) {
        const skill = skills.find((s) => s.name === skillMatch[1]);
        if (!skill) throw new Error("当前 workspace 没有这个 skill。");
        outgoingSkills = [...new Set([...outgoingSkills, skill.id])];
        skillInvocation = skill.id;
        outgoing = skillMatch[2] || `请使用 ${skill.name} 协助我。`;
      }
      const startsWithFile = localFilePaths(outgoing.split("\n")[0]).length > 0;
      const match = startsWithFile
        ? null
        : outgoing.match(/^\/(\S+)(?:\s+([\s\S]*))?$/);
      let ok = false;
      if (match && commands.some((c) => c.name === match[1])) {
        if (match[1] === "help") {
          setHelp(true);
          ok = true;
        } else if (match[1] === "files") {
          setFiles(true);
          ok = true;
        } else if (onCommand) ok = await onCommand(match[1], match[2] || "");
        else throw new Error("先开始一个会话，再使用这个命令。");
        if (ok) setText("");
      } else {
        if (match && !nativeCommands.some((c) => c.name === match[1]))
          throw new Error(
            "当前执行工具未提供这个命令。输入 / 查看可用命令，普通路径可用 @ 引用。",
          );
        ok = await send(outgoing || "请查看附件。", {
          attachments: attachments.filter(a => referencedInText(a, outgoing)).map((a) => a.id),
          references,
          skills: outgoingSkills,
          ...(skillInvocation ? { skillInvocation } : {}),
          fileSelections,
        });
        if (ok) {
          discardDraft(draftKey);
          setText("");
          setSelectedSkills([]);
          setAttachments([]);
          setReferences([]);
          setFileSelections([]);
          setThumbnails({});
          setUploadErrors([]);
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }
  return (
    <>
      {!!folderDrops.length && <WorkspaceDialog key={folderDrops.length}
        initialQuery={folderDrops[0]} reference={async path => { await addLocalFiles([path]); }}
        close={() => setFolderDrops(old => old.slice(1))} />}
      {skillsOpen && (
        <SkillPicker
          skills={skills}
          selected={selectedSkills}
          locked={submitting || busy}
          toggle={toggleSkill}
          close={() => setSkillsOpen(false)}
          error={skillError}
          example={(skill) => {
            setSelectedSkills(old => [...new Set([...old, skill.id])]);
            setText(old => appendGuidePrompt(old, skill.example || ""));
            setSkillsOpen(false);
            requestAnimationFrame(() => input.current?.focus());
          }}
        />
      )}
      <form
        ref={formRef}
        className={
          "composer " +
          (collapsed ? "collapsed " : "") +
          (disabled ? "unavailable " : "") +
          (dragging ? "dragging" : "")
        }
        onMouseDownCapture={(e) => {
          if (!collapsed) return;
          // Buttons (send/stop) keep working in the folded state.
          if ((e.target as HTMLElement).closest("button")) return;
          e.preventDefault();
          setCollapsedState(false);
          requestAnimationFrame(() => input.current?.focus());
        }}
        onSubmit={submit}
        onDragEnter={(e) => {
          if (e.dataTransfer.types.some(type => type === "Files" || type === "text/uri-list")) {
            e.preventDefault();
            dragDepth.current++;
            setDragging(true);
          }
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          if (--dragDepth.current <= 0) setDragging(false);
        }}
        onDragOver={(e) => {
          if (e.dataTransfer.types.some(type => type === "Files" || type === "text/uri-list")) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
          }
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          const paths = localFilePaths(
            e.dataTransfer.getData("text/uri-list") ||
              e.dataTransfer.getData("text/plain"),
          );
          if (paths.length) void addLocalFiles(paths);
          else {
            const dropped = droppedItems(e.dataTransfer);
            // Finish ordinary imports before opening a directory picker, so its
            // input cannot race an upload or overwrite the current draft.
            void upload(dropped.files).then(() => setFolderDrops(dropped.folders.slice(0, 8)));
          }
        }}
      >
        {dragging && (
          <div className="drop-overlay">
            <ImagePlus size={28} />
            引用文件或文件夹
          </div>
        )}
        {(attachments.filter(a => referencedInText(a)).length > 0 || references.length > 0) && (
          <div className="attachment-list">
            {attachments.filter(a => referencedInText(a)).map((a) => (
              <div className="attachment-chip" key={a.id}>
                {thumbnails[a.id] ? (
                  <img src={thumbnails[a.id]} alt={a.name} />
                ) : (
                  <FileIcon />
                )}
                <span title={a.localPath}>
                  {a.name}
                  <small>
                    {a.source === "local" ? "本地文件 · " : ""}
                    {a.size >= 1024 * 1024
                      ? `${(a.size / 1024 / 1024).toFixed(1)} MB`
                      : `${Math.ceil(a.size / 1024)} KB`}
                  </small>
                </span>
                <button
                  type="button"
                  aria-label={"移除附件 " + a.name}
                  onClick={() => {
                    if (a.localPath) {
                      const quoted = JSON.stringify(a.localPath);
                      setText((old) => old.split(/\r?\n/).filter((line) => {
                        const value = line.trim();
                        return value !== a.localPath && value !== quoted;
                      }).join("\n").replace(/\n{3,}/g, "\n\n").trim());
                    }
                    setAttachments((old) => old.filter((x) => x.id !== a.id));
                    setThumbnails((old) => { const next = { ...old }; delete next[a.id]; return next; });
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
            {references.map((path) => (
              <div className="attachment-chip reference" key={path}>
                <AtSign size={14} />
                <span title={path}>{path}</span>
                <button
                  type="button"
                  aria-label={"移除引用 " + path}
                  onClick={() =>
                    setReferences((old) => old.filter((p) => p !== path))
                  }
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
        {!!selectedSkills.length && (
          <div className="selected-skills">
            {skills
              .filter((s) => selectedSkills.includes(s.id))
              .map((s) => (
                <button
                  type="button"
                  key={s.id}
                  onClick={() => toggleSkill(s.id)}
                  disabled={submitting || busy}
                  aria-label={"移除 skill " + s.name}
                >
                  <BookOpen size={13} />
                  {s.title || s.name}
                  <X size={12} />
                </button>
              ))}
          </div>
        )}
        {collapsed &&
          (running ||
            !!text.trim() ||
            attachments.some((a) => referencedInText(a)) ||
            !!references.length ||
            !!fileSelections.length ||
            !!selectedSkills.length) && (
            <div className="composer-summary">
              {running && (
                <span className="chip live">
                  <LoaderCircle size={11} className="spin" />
                  执行中…
                </span>
              )}
              {!!text.trim() && (
                <span className="chip">草稿 {text.trim().length} 字</span>
              )}
              {attachments.filter((a) => referencedInText(a)).length +
                references.length >
                0 && (
                <span className="chip">
                  <Paperclip size={11} />
                  {attachments.filter((a) => referencedInText(a)).length +
                    references.length}{" "}
                  个附件
                </span>
              )}
              {!!fileSelections.length && (
                <span className="chip">
                  <AtSign size={11} />
                  {fileSelections.length} 个选段
                </span>
              )}
              {!!selectedSkills.length && (
                <span className="chip">
                  <BookOpen size={11} />
                  {selectedSkills.length} 个 Skills
                </span>
              )}
            </div>
          )}
        <div className="composer-editor">
          {menu && (
            <div className="command-menu" role="listbox" aria-label="可用命令">
              {items.length ? (
                items.map((c, i) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={choice === i}
                    key={c.name}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertCommand(c)}
                  >
                    <code>/{c.name}</code>
                    <span>{c.description || "执行工具提供的命令"}</span>
                  </button>
                ))
              ) : (
                <p>没有匹配的命令</p>
              )}
            </div>
          )}
          <textarea
            ref={input}
            aria-label="任务内容"
            value={text}
            readOnly={submitting}
            onChange={(e) => {
              setText(e.target.value);
              setChoice(0);
              setDismissed(false);
              if (/(^|\s)@$/.test(e.target.value) && workspaceId)
                setFiles(true);
            }}
            onMouseDown={(e) => {
              // The only pointer target inside a textarea that is not text is
              // the resize corner, so a press there means a manual height.
              const el = e.currentTarget;
              const box = el.getBoundingClientRect();
              if (box.right - e.clientX < 18 && box.bottom - e.clientY < 18)
                dragged.current = true;
            }}
            onFocus={() => {
              setFocused(true);
              setCollapsedState(false);
            }}
            onBlur={() => setFocused(false)}
            placeholder={
              running ? "补充一条消息，将在当前执行完成后处理…" : placeholder
            }
            rows={2}
            maxLength={50000}
            onPaste={(e) => {
              const paths = localFilePaths(
                e.clipboardData.getData("text/plain"),
              );
              if (paths.length) {
                e.preventDefault();
                void addLocalFiles(paths);
                return;
              }
              const images = Array.from(e.clipboardData.files);
              if (images.length) {
                e.preventDefault();
                void upload(images);
              }
            }}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing || e.keyCode === 229) return;
              if (
                menu &&
                items.length &&
                ["ArrowDown", "ArrowUp", "Tab", "Enter", "Escape"].includes(
                  e.key,
                )
              ) {
                e.preventDefault();
                if (e.key === "Escape") setDismissed(true);
                else if (e.key === "ArrowDown")
                  setChoice((c) => (c + 1) % items.length);
                else if (e.key === "ArrowUp")
                  setChoice((c) => (c + items.length - 1) % items.length);
                else insertCommand(items[Math.min(choice, items.length - 1)]);
              } else if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submit();
              } else if (e.key === "Escape") {
                // The fold only engages while unfocused; Escape explicitly
                // hands focus back to the transcript.
                e.currentTarget.blur();
              }
            }}
          />
        </div>
        <div className="composer-bottom">
          <div className="composer-tools">
            <Popover
              title="添加内容"
              className="add-content"
              label={
                uploading || localFilesBusy ? (
                  <LoaderCircle size={19} className="spin" />
                ) : (
                  <Plus size={20} />
                )
              }
            >
              {(close) => (
                <>
                  <header>
                    <strong>添加到对话</strong>
                  </header>
                  <button
                    type="button"
                    className="content-option"
                    aria-label="选择本地文件"
                    disabled={uploading || localFilesBusy}
                    onClick={() => {
                      close();
                      void addLocalFiles();
                    }}
                  >
                    <Paperclip size={17} />
                    <span>
                      本地文件
                      <small>直接引用原文件，不复制、无上传大小限制</small>
                      <small>也可以粘贴完整路径；图片可预览</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="content-option"
                    disabled={!workspaceId}
                    onClick={() => {
                      close();
                      setFiles(true);
                    }}
                  >
                    <AtSign size={17} />
                    <span>
                      引用工作文件<small>从当前工作空间中选择</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="content-option"
                    onClick={() => {
                      close();
                      if (!text.trim()) {
                        setText("/");
                        setDismissed(false);
                      } else setHelp(true);
                      input.current?.focus();
                    }}
                  >
                    <Terminal size={17} />
                    <span>
                      命令与快捷操作<small>输入 / 选择命令，支持参数</small>
                    </span>
                  </button>
                </>
              )}
            </Popover>
            <button
              type="button"
              disabled={!workspaceId}
              data-guide="skills"
              onClick={() => setSkillsOpen(true)}
            >
              <BookOpen size={15} />
              Skills{selectedSkills.length ? ` · ${selectedSkills.length}` : ""}
            </button>
          </div>
          <div className="composer-context">{children}</div>
          <div className="composer-actions">
            {running && stop && (
              <button
                type="button"
                className="send-button stop"
                disabled={busy}
                onClick={stop}
                aria-label="停止执行"
              >
                <Square size={14} fill="currentColor" />
              </button>
            )}
            <button
              className="send-button"
              type="submit"
              disabled={
                disabled ||
      requirementIssues.length > 0 ||
                busy ||
                submitting ||
                uploading ||
                localFilesBusy ||
                (!text.trim() && !attachments.some(a => referencedInText(a)))
              }
              title={running ? "加入待发送队列" : "发送任务"}
              aria-label={running ? "加入队列" : "发送任务"}
            >
              {busy || submitting ? (
                <LoaderCircle size={18} className="spin" />
              ) : (
                <ArrowUp size={20} />
              )}
            </button>
          </div>
        </div>
        {disabled && reason && <p className="composer-reason">{reason}</p>}
        {requirementIssues.map(issue => <p className="composer-reason" role="status" key={issue}>{issue}</p>)}
        {localFilesBusy && (
          <p className="composer-reason" role="status">
            正在选择本地文件…
          </p>
        )}
        {filePathHint && (
          <div className="composer-file-hint" role="status">
            <span>{filePathHint}</span>
            <button
              type="button"
              onClick={() => setFilePathHint("")}
              aria-label="关闭文件引用提示"
            >
              <X size={14} />
            </button>
          </div>
        )}
        {!!fileSelections.length && <div className="composer-selections" aria-label="引用的成果选段">
          {fileSelections.map((selection, index) => <div className="composer-selection" key={index}>
            <div><strong>{selection.path} · {selection.revision ? `v${selection.revision}` : "当前文件"}</strong>
              <p>{selection.quote ? selection.quote.slice(0, 180) + (selection.quote.length > 180 ? "…" : "") : "图片中的选定区域"}</p></div>
            <button type="button" aria-label={`移除选段 ${index + 1}`} onClick={() => setFileSelections(old => old.filter((_, i) => i !== index))}><X size={14} /></button>
          </div>)}
          <p className="section-note">写下修改要求，发送后开始处理。文件变化时需要重新选择。</p>
        </div>}
        {draftLocalOnly && (
          <p className="form-error" role="status">
            浏览器暂时无法保存草稿，刷新前请先复制文字。
          </p>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {uploadErrors.length > 0 && (
          <div className="composer-upload-error inline-error" role="alert">
            <CircleAlert size={18} aria-hidden="true" />
            <div>
              <strong>上传失败</strong>
              {uploadErrors.map((message, index) => (
                <p key={index}>{message}</p>
              ))}
              <button type="button" onClick={() => void addLocalFiles()}>
                改为引用本地图片
              </button>
            </div>
            <button
              type="button"
              className="upload-error-dismiss"
              aria-label="关闭上传错误提示"
              onClick={() => setUploadErrors([])}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {help && (
          <p className="composer-help">
            Enter 发送，Shift + Enter 换行。粘贴文件路径或截图，@
            引用工作文件；输入 / 后可用方向键与 Enter
            选择命令。运行中可以补充消息或停止。
            <button
              type="button"
              onClick={() => setHelp(false)}
              aria-label="关闭使用帮助"
            >
              <X size={12} />
            </button>
          </p>
        )}
      </form>
      <dialog
        className="dialog files-dialog"
        ref={dialog}
        onCancel={() => setFiles(false)}
      >
        <div className="dialog-heading">
          <h2>选择工作文件</h2>
          <button
            className="icon-button"
            onClick={() => setFiles(false)}
            aria-label="关闭文件选择"
          >
            <X size={18} />
          </button>
        </div>
        {files && workspaceId ? (
          <FilesPanel
            key={workspaceId}
            workspaceId={workspaceId}
            onReference={reference}
          />
        ) : (
          <p>先选择工作文件夹。</p>
        )}
      </dialog>
    </>
  );
}
function FileIcon() {
  return <Paperclip size={16} />;
}
