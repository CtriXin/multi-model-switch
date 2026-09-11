import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Download,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { request } from "./api";
import { Dialog } from "./components";
import { effortLabels } from "./ModelExplorer";
import "./channel-models.css";

type ModelSetting = {
  id: string;
  visible: boolean;
  effort: string;
  effectiveEffort: string;
  legacyEffort?: string;
  launchOverride?: string;
  effortLevels: string[];
  contextWindow?: number;
  vision: boolean;
  visionSource?: string;
  contextSource?: string;
  capabilitiesEditable?: boolean;
  catalogVision?: boolean;
  catalogContextWindow?: number;
};
type Provider = {
  id: string;
  name: string;
  canDiscover: boolean;
  models: ModelSetting[];
  connection: {
    openaiBaseUrl: string;
    anthropicBaseUrl: string;
    hasApiKey: boolean;
    protocols: string[];
  };
};
type Snapshot = {
  revision: string;
  fingerprint: string;
  configRoot: string;
  configScope?: "standalone" | "mmf";
  providers: Provider[];
};
type Change = {
  kind: "add" | "remove" | "effort" | "vision" | "context" | "connection" | "channel-remove";
  model: string;
  before?: string;
  after?: string;
  channels?: string[];
};
type RefreshField = {
  field: "vision" | "context" | "effort";
  value: boolean | number | string;
  before: string;
  after: string;
  source: string;
  /** The current value is the user's own setting, so replacing it is not a
   *  correction and must not happen without them saying so. */
  userSet: boolean;
};
type Refresh = {
  modelCount: number;
  proposals: { model: string; fields: RefreshField[] }[];
  skipped: { model: string; reason: string }[];
  sourceLabels: Record<string, string>;
  reports: {
    source: string;
    label: string;
    ok: boolean;
    matched: number;
    unmatched: number;
    warnings: string[];
  }[];
};
type Preview = {
  previewId: string;
  changes: Change[];
  configRoot: string;
  confirmPhrase?: string;
  writeSummary: string;
};

const fieldLabels: Record<string, string> = {
  vision: "识图",
  context: "上下文",
  effort: "默认 effort",
};

/** A row is proposed by default unless taking it would overwrite the user's
 *  own setting, or the only source saying so is the provider catalogue. */
function proposedByDefault(field: RefreshField) {
  return !field.userSet && field.source !== "catalog";
}

function fieldKey(model: string, field: RefreshField) {
  return `${model}:${field.field}`;
}


const capabilityOriginLabels: Record<string, string> = {
  manual_override: "本机覆盖",
  model_policy: "你设置的",
  approved_facts: "MMF 目录",
  provider_profile: "通道预设",
  conservative_fallback: "未声明，按保守值",
};

function capabilityOrigin(model: ModelSetting) {
  const parts = [
    model.vision ? "可读取图片" : "不可读取图片",
    model.contextWindow
      ? `${Math.round(model.contextWindow / 1000)}K 上下文`
      : "",
  ].filter(Boolean);
  const origin =
    capabilityOriginLabels[model.visionSource || ""] ||
    capabilityOriginLabels[model.contextSource || ""];
  return origin ? `${parts.join(" · ")} · 来源 ${origin}` : parts.join(" · ");
}

export function ChannelModels({
  initialProvider,
  back,
  saved,
  editStateChanged,
  onCreateChannel,
}: {
  initialProvider: string;
  back: () => void;
  saved: () => void;
  editStateChanged: (state: {dirty: boolean; busy: boolean}) => void;
  onCreateChannel?: () => void;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [providerId, setProviderId] = useState(initialProvider);
  const [chosen, setChosen] = useState<string[]>([]);
  const [efforts, setEfforts] = useState<Record<string, string>>({});
  const [visions, setVisions] = useState<Record<string, boolean>>({});
  const [contextWindows, setContextWindows] = useState<Record<string, number>>(
    {},
  );
  const [connection, setConnection] = useState<Record<string, string>>({});
  const [showConnection, setShowConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState("");
  const [remote, setRemote] = useState<string[] | null>(null);
  const [manual, setManual] = useState<string[]>([]);
  const [newModel, setNewModel] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("load");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState<Refresh>();
  const [refreshPicks, setRefreshPicks] = useState<Record<string, boolean>>({});
  const [preview, setPreview] = useState<Preview>();
  const [leave, setLeave] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);
  const refreshFields = refresh?.proposals.flatMap((item) =>
    item.fields.map((field) => ({ key: fieldKey(item.model, field), field })),
  ) || [];
  const selectedFields = refreshFields.filter(({ key }) => refreshPicks[key]);
  const selectedOverrides = selectedFields.filter(({ field }) => field.userSet).length;
  const allRefreshSelected = refreshFields.length > 0 && selectedFields.length === refreshFields.length;
  const provider = snapshot?.providers.find((p) => p.id === providerId);
  const original =
    provider?.models.filter((m) => m.visible).map((m) => m.id) || [];
  const dirty =
    chosen.length !== original.length ||
    chosen.some((id) => !original.includes(id)) ||
    Object.keys(efforts).length > 0 ||
    Object.keys(visions).length > 0 ||
    Object.keys(contextWindows).length > 0 ||
    Object.keys(connection).length > 0;
  useEffect(() => {
    editStateChanged({dirty, busy: busy === "apply"});
    return () => editStateChanged({dirty: false, busy: false});
  }, [dirty, busy, editStateChanged]);
  const ids = [
    ...new Set([
      ...(provider?.models.map((m) => m.id) || []),
      ...(remote || []),
      ...manual,
    ]),
  ];
  const shown = ids.filter((id) =>
    id.toLowerCase().includes(query.toLowerCase()),
  );

  function reset(p: Provider | undefined) {
    setProviderId(p?.id || "");
    setChosen(p?.models.filter((m) => m.visible).map((m) => m.id) || []);
    setEfforts({});
    setVisions({});
    setContextWindows({});
    setConnection({});
    setShowConnection(false);
    setConnectionResult("");
    setRemote(null);
    setManual([]);
    setNewModel("");
    setQuery("");
    setError("");
  }
  async function load() {
    setBusy("load");
    setError("");
    try {
      const next = await request<Snapshot>("/model-settings");
      setSnapshot(next);
      reset(
        next.providers.find((p) => p.id === providerId) || next.providers[0],
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const draft = () => ({
    providerId,
    revision: snapshot?.revision,
    fingerprint: snapshot?.fingerprint,
    models: chosen,
    efforts,
    visions,
    contextWindows,
    connection,
  });
  function editConnection(field: string, value: string) {
    setConnection((old) => {
      const next = { ...old };
      const original =
        field === "apiKey"
          ? ""
          : provider?.connection[field as "openaiBaseUrl" | "anthropicBaseUrl"];
      if (value === original) delete next[field];
      else next[field] = value;
      return next;
    });
    setConnectionResult("");
  }
  async function checkConnection() {
    setBusy("check");
    setConnectionResult("");
    setError("");
    try {
      const result = await request<{
        message: string;
        latencyMs: number;
        modelCount: number;
      }>("/model-settings/check", draft());
      setConnectionResult(
        `${result.message} ${result.latencyMs} ms · ${result.modelCount} 个模型`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function discover() {
    setBusy("discover");
    setError("");
    setNotice("");
    try {
      const result = await request<{ models: string[] }>(
        "/model-settings/discover",
        draft(),
      );
      setRemote(result.models);
      // Remote discovery is authoritative for this channel. Replace the
      // visible selection so removed upstream models leave the local route.
      setChosen(result.models);
      setManual([]);
      setNotice(`已用远端模型列表覆盖当前通道，共 ${result.models.length} 个模型。取消勾选后保存即可继续精简。`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function checkCapabilities(sources?: string[]) {
    setBusy(sources ? "refresh:catalog" : "refresh");
    setError("");
    setNotice("");
    try {
      const result = await request<Refresh>("/model-settings/refresh", {
        ...draft(),
        ...(sources ? { sources } : {}),
      });
      setRefresh(result);
      const picks: Record<string, boolean> = {};
      for (const item of result.proposals)
        for (const field of item.fields) {
          const key = fieldKey(item.model, field);
          const previous = refresh?.proposals.find(row => row.model === item.model)?.fields.find(row => row.field === field.field);
          const unchanged = sources && previous?.value === field.value && previous?.source === field.source && previous?.before === field.before;
          picks[key] = unchanged && key in refreshPicks ? refreshPicks[key] : proposedByDefault(field);
        }
      setRefreshPicks(picks);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function chooseRefresh(mode: "all" | "none" | "default") {
    setRefreshPicks(Object.fromEntries(refreshFields.map(({ key, field }) => [
      key, mode === "default" ? proposedByDefault(field) : mode === "all",
    ])));
  }
  function applyChecked() {
    if (!refresh) return;
    const nextVisions: Record<string, boolean> = {};
    const nextContexts: Record<string, number> = {};
    const nextEfforts: Record<string, string> = {};
    for (const item of refresh.proposals)
      for (const field of item.fields) {
        if (!refreshPicks[fieldKey(item.model, field)]) continue;
        if (field.field === "vision")
          nextVisions[item.model] = field.value as boolean;
        if (field.field === "context")
          nextContexts[item.model] = field.value as number;
        if (field.field === "effort")
          nextEfforts[item.model] = field.value as string;
      }
    const count =
      Object.keys(nextVisions).length +
      Object.keys(nextContexts).length +
      Object.keys(nextEfforts).length;
    // The worker only reports values that differ from what is saved, so
    // merging cannot leave a pending edit equal to the stored value.
    setVisions((old) => ({ ...old, ...nextVisions }));
    setContextWindows((old) => ({ ...old, ...nextContexts }));
    setEfforts((old) => ({ ...old, ...nextEfforts }));
    setRefresh(undefined);
    setNotice(
      count
        ? `已填入 ${count} 处改动，还没有保存。检查后点“检查并保存”。`
        : "没有选中任何一项，配置没有改变。",
    );
  }
  async function review() {
    setBusy("preview");
    setError("");
    try {
      setPreview(await request<Preview>("/model-settings/preview", draft()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function apply() {
    if (!preview) return;
    setBusy("apply");
    setError("");
    try {
      const result = await request<{ applied: boolean; runtimeReady: boolean }>(
        "/model-settings/apply",
        { previewId: preview.previewId, confirmed: true },
      );
      setPreview(undefined);
      saved();
      await load();
      setNotice(
        result.runtimeReady
          ? "设置已保存。新会话会读取新配置；单独设置的会话 effort 优先于模型默认值。"
          : "设置已保存。部分通道仍缺少连接信息；已就绪的通道可以继续使用。",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function askDelete(id: string, name: string) {
    setMenuOpen(false);
    if (dirty) {
      setError("请先保存或放弃当前通道的修改，再删除通道。");
      return;
    }
    setError("");
    setConfirmDelete({ id, name });
  }
  async function deleteChannel(id: string) {
    setBusy("apply");
    setError("");
    try {
      const preview = await request<Preview>("/model-settings/preview", {
        providerId: id,
        removeProviderId: id,
        revision: snapshot?.revision,
        fingerprint: snapshot?.fingerprint,
      });
      await request<{ applied: boolean }>("/model-settings/apply", {
        previewId: preview.previewId,
        confirmed: true,
      });
      setConfirmDelete(null);
      saved();
      await load();
      setNotice("通道已删除。新会话不再使用它；其他通道和已有会话不受影响。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function navigate(id: string) {
    if (dirty) {
      setLeave(id);
      return;
    }
    if (id === "back") back();
    else {
      reset(snapshot?.providers.find((p) => p.id === id));
      setNotice("");
    }
  }
  function toggle(id: string) {
    setChosen((old) =>
      old.includes(id) ? old.filter((m) => m !== id) : [...old, id],
    );
  }
  function addModel() {
    const id = newModel.trim();
    if (!id || id.length > 200 || /[\x00-\x1f]/.test(id)) return;
    setManual((old) => [...new Set([...old, id])]);
    setChosen((old) => [...new Set([...old, id])]);
    setNewModel("");
    setQuery("");
  }
  return (
    <section className="channel-models" aria-label="通道模型管理">
      <div className="channel-models-heading">
        <button
          className="button subtle"
          onClick={() => navigate("back")}
          disabled={!!busy}
        >
          <ArrowLeft size={16} />
          返回模型选择
        </button>
        <button
          className="button subtle"
          onClick={() => (dirty ? setLeave(providerId) : void load())}
          disabled={!!busy}
        >
          <RefreshCw size={15} />
          重新加载配置
        </button>
      </div>
      <h2>通道设置</h2>
      <p className="muted">连接服务、选择模型，设置默认 effort。</p>
      {error && !preview && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="channel-notice" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      {busy === "load" && (
        <p role="status" className="muted">
          正在读取已保存的模型配置…
        </p>
      )}
      {snapshot && (
        <>
          <div className="channel-toolbar">
            <div className="channel-select-field">
              <span className="channel-select-caption">通道</span>
              <div className="channel-select" ref={menuRef}>
                <button
                  type="button"
                  className="channel-select-trigger"
                  aria-haspopup="listbox"
                  aria-expanded={menuOpen}
                  disabled={!!busy}
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  <span className="channel-select-value">
                    {provider ? (
                      <>
                        <strong>{provider.name}</strong>
                        <small>{provider.id}</small>
                      </>
                    ) : (
                      "选择通道"
                    )}
                  </span>
                  <ChevronDown size={16} />
                </button>
                {menuOpen && (
                  <div className="channel-select-menu" role="listbox" aria-label="通道列表">
                    {snapshot.providers.map((p) => (
                      <div
                        key={p.id}
                        className={
                          "channel-select-option" +
                          (p.id === providerId ? " active" : "")
                        }
                      >
                        <button
                          type="button"
                          role="option"
                          aria-selected={p.id === providerId}
                          className="channel-select-option-main"
                          onClick={() => {
                            setMenuOpen(false);
                            navigate(p.id);
                          }}
                        >
                          {p.id === providerId ? (
                            <Check size={15} />
                          ) : (
                            <span className="channel-select-dot" aria-hidden="true" />
                          )}
                          <span className="channel-select-labels">
                            <strong>{p.name}</strong>
                            <small>{p.id}</small>
                          </span>
                        </button>
                        {snapshot.providers.length > 1 && (
                          <button
                            type="button"
                            className="channel-select-delete"
                            aria-label={`删除通道 ${p.name}`}
                            title="删除通道"
                            disabled={!!busy}
                            onClick={() => askDelete(p.id, p.name)}
                          >
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    ))}
                    {onCreateChannel && (
                      <button
                        type="button"
                        className="channel-select-create"
                        onClick={() => {
                          setMenuOpen(false);
                          onCreateChannel();
                        }}
                      >
                        <Plus size={15} />
                        新建通道
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
            <button
              className="button"
              disabled={!!busy || !provider?.canDiscover}
              onClick={() => void discover()}
              title={
                provider?.canDiscover
                  ? "使用该通道现有地址和 Key 拉取模型"
                  : "通道使用手工模型目录，可在下方添加模型 ID"
              }
            >
              <Download size={16} />
              {busy === "discover" ? "正在拉取模型…" : "拉取模型"}
            </button>
          </div>
          <section className="channel-connection" aria-label="通道连接">
            <button
              className="channel-connection-toggle"
              aria-expanded={showConnection}
              onClick={() => setShowConnection(!showConnection)}
            >
              <span>连接地址与 API Key</span>
              <span className="muted">{showConnection ? "收起" : "编辑"}</span>
            </button>
            {showConnection && (
              <div className="channel-connection-fields">
                {(
                  [
                    ["openaiBaseUrl", "OpenAI 地址", "openai_chat_completions"],
                    [
                      "anthropicBaseUrl",
                      "Anthropic 地址",
                      "anthropic_messages",
                    ],
                  ] as const
                )
                  .filter(
                    ([field, , protocol]) =>
                      provider?.connection.protocols.includes(protocol) ||
                      provider?.connection[field],
                  )
                  .map(([field, label]) => (
                    <label key={field}>
                      {label}
                      <input
                        aria-label={label}
                        type="url"
                        autoComplete="off"
                        value={
                          connection[field] ?? provider?.connection[field] ?? ""
                        }
                        disabled={!!busy}
                        onChange={(e) => editConnection(field, e.target.value)}
                        placeholder="https://…"
                      />
                    </label>
                  ))}
                <label>
                  API Key
                  <input
                    type="password"
                    aria-label="替换通道 API Key"
                    autoComplete="new-password"
                    spellCheck={false}
                    value={connection.apiKey || ""}
                    disabled={!!busy}
                    placeholder={
                      provider?.connection.hasApiKey
                        ? "已保存，留空保留原 Key"
                        : "粘贴 API Key"
                    }
                    onChange={(e) => editConnection("apiKey", e.target.value)}
                  />
                </label>
                <div className="channel-connection-check">
                  <button
                    className="button"
                    disabled={!!busy || !provider?.canDiscover}
                    onClick={() => void checkConnection()}
                  >
                    {busy === "check" ? "正在检查连接…" : "检查模型接口"}
                  </button>
                  <span className="muted">
                    使用当前填写的地址和 Key，不保存配置。
                  </span>
                </div>
                {!provider?.canDiscover && (
                  <p className="muted">
                    手工目录通道不自动探测；保存后可用新会话验证模型。
                  </p>
                )}
                {connectionResult && (
                  <p className="channel-notice" role="status">
                    <Check size={16} />
                    {connectionResult}
                  </p>
                )}
              </div>
            )}
          </section>
          {!provider?.canDiscover && (
            <p className="muted">
              这个通道采用手工模型目录，可直接添加模型 ID。
            </p>
          )}
          <div className="channel-list-toolbar">
            <label className="channel-search">
              <Search size={16} />
              <input
                aria-label="搜索通道模型"
                placeholder="搜索模型"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <span>
              {chosen.length} 个已选 / {ids.length} 个模型
            </span>
          </div>
          <div className="channel-capability-refresh">
            <button
              type="button"
              className="button primary capability-refresh"
              disabled={!!busy}
              aria-busy={busy === "refresh"}
              title="对比 MMF 官方数据和本地已知快照，列出与当前配置不一致的地方"
              onClick={() => void checkCapabilities()}
            >
              <RefreshCw size={16} aria-hidden="true" />
              {busy === "refresh" ? "正在对比…" : "检查最新能力"}
            </button>
            <span className="muted">
              先看差异再决定填哪些，不会直接改配置
            </span>
          </div>
          <div className="channel-model-table">
            <div className="channel-model-table-head">
              <span>在该通道中使用</span>
              <span>能力</span>
              <span>默认 effort</span>
            </div>
            <div className="channel-model-rows">
              {shown.map((id) => {
                const model = provider?.models.find((m) => m.id === id);
                const newRemote = !model && remote?.includes(id);
                return (
                  <div className="channel-model-row" key={id}>
                    <label className="channel-model-name">
                      <input
                        type="checkbox"
                        aria-label={`使用 ${id}`}
                        checked={chosen.includes(id)}
                        disabled={!!busy}
                        onChange={() => toggle(id)}
                      />
                      <span>
                        <strong>{id}</strong>
                        <small>
                          {newRemote
                            ? "新发现"
                            : !model
                              ? "手工添加，保存后可配置默认值"
                              : remote && !remote.includes(id)
                                ? "本次拉取未返回，已保留原选择"
                                : capabilityOrigin(model)}
                        </small>
                      </span>
                    </label>
                    {model?.capabilitiesEditable ? (
                      <div className="channel-model-capability">
                        <label>
                          <input
                            type="checkbox"
                            aria-label={`${id} 可读取图片`}
                            checked={visions[id] ?? model.vision}
                            disabled={!!busy}
                            onChange={(e) =>
                              setVisions((old) => {
                                const next = { ...old };
                                if (e.target.checked === model.vision)
                                  delete next[id];
                                else next[id] = e.target.checked;
                                return next;
                              })
                            }
                          />
                          <span>可读取图片</span>
                        </label>
                        <label>
                          <span>上下文</span>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={1024}
                            max={10000000}
                            step={1024}
                            aria-label={`${id} 上下文长度`}
                            placeholder="自动"
                            value={
                              contextWindows[id] ?? model.contextWindow ?? ""
                            }
                            disabled={!!busy}
                            onChange={(e) =>
                              setContextWindows((old) => {
                                const next = { ...old };
                                const value = Number(e.target.value);
                                if (
                                  !e.target.value ||
                                  !Number.isFinite(value) ||
                                  value === model.contextWindow
                                )
                                  delete next[id];
                                else next[id] = Math.trunc(value);
                                return next;
                              })
                            }
                          />
                        </label>
                        {(() => {
                          const vision = visions[id] ?? model.vision;
                          const context = contextWindows[id] ?? model.contextWindow;
                          const off =
                            (model.catalogVision !== undefined &&
                              vision !== model.catalogVision) ||
                            (model.catalogContextWindow !== undefined &&
                              context !== model.catalogContextWindow);
                          if (!off) return null;
                          return (
                            <button
                              type="button"
                              className="capability-reset"
                              disabled={!!busy}
                              title="按 MMF 目录里这个模型的已知能力填回"
                              onClick={() => {
                                setVisions((old) => {
                                  const next = { ...old };
                                  if (model.catalogVision === undefined) return next;
                                  if (model.catalogVision === model.vision)
                                    delete next[id];
                                  else next[id] = model.catalogVision;
                                  return next;
                                });
                                setContextWindows((old) => {
                                  const next = { ...old };
                                  if (model.catalogContextWindow === undefined)
                                    return next;
                                  if (model.catalogContextWindow === model.contextWindow)
                                    delete next[id];
                                  else next[id] = model.catalogContextWindow;
                                  return next;
                                });
                              }}
                            >
                              用 MMF 默认
                            </button>
                          );
                        })()}
                      </div>
                    ) : (
                      <span className="muted">
                        {model ? "保存后可编辑" : ""}
                      </span>
                    )}
                    {model?.effortLevels.length ? (
                      <select
                        aria-label={`${id} MMF 默认 effort`}
                        value={efforts[id] ?? model.effort}
                        disabled={!!busy}
                        onChange={(e) =>
                          setEfforts((old) => {
                            const next = { ...old };
                            if (e.target.value === model.effort)
                              delete next[id];
                            else next[id] = e.target.value;
                            return next;
                          })
                        }
                      >
                        <option value="">
                          {model.effort
                            ? "恢复自动"
                            : `自动 · ${model.effectiveEffort}`}
                        </option>
                        {model.effort &&
                          !model.effortLevels.includes(model.effort) && (
                            <option value={model.effort} disabled>
                              {model.effort}（实际 {model.effectiveEffort}）
                            </option>
                          )}
                        {model.effortLevels.map((level) => (
                          <option value={level} key={level}>
                            {level}
                            {effortLabels[level]
                              ? ` · ${effortLabels[level]}`
                              : ""}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="muted effort-unavailable">
                        {model?.legacyEffort
                          ? `用户覆盖 · ${model.legacyEffort}`
                          : model
                            ? "未声明可调档位"
                            : "保存后读取"}
                      </span>
                    )}
                  </div>
                );
              })}
              {!shown.length && (
                <p className="muted">
                  {query
                    ? "没有匹配的模型。"
                    : "还没有模型，可以拉取或手工添加。"}
                </p>
              )}
            </div>
          </div>
          <form
            className="channel-manual"
            onSubmit={(e) => {
              e.preventDefault();
              addModel();
            }}
          >
            <input
              aria-label="手工添加模型 ID"
              placeholder="列表没有？输入完整模型 ID"
              value={newModel}
              onChange={(e) => setNewModel(e.target.value)}
              disabled={!!busy}
            />
            <button className="button" disabled={!!busy || !newModel.trim()}>
              <Plus size={16} />
              添加模型
            </button>
          </form>
          <p className="channel-scope-note">
            模型勾选只影响当前通道。默认 effort 按模型 ID
            保存，会影响其他通道的同名模型；下拉框按当前 Pi
            通道的可用档位展示；其他 harness 按各自能力处理。
          </p>
          <footer className="channel-save">
            <span>{dirty ? "有未保存的修改" : "与已保存的配置一致"}</span>
            <button
              className="button primary"
              disabled={!dirty || !!busy}
              onClick={() => void review()}
            >
              {busy === "preview" ? "正在检查变更…" : "检查并保存"}
            </button>
          </footer>
        </>
      )}
      {refresh && (
        <Dialog title="最新能力对比" size="wide" dismissible={!busy} close={() => { if (!busy) setRefresh(undefined); }}>
          <div className="capability-review">
            {refresh.proposals.length === 0 ? (
              <p className="muted">
                这条通道的 {refresh.modelCount} 个模型和已知数据一致，没有需要改的地方。
              </p>
            ) : (
              <>
                <p className="muted" id="capability-selection-help">
                  默认选中不会覆盖手动设置的更新；你自己设过的值、仅来自 OpenRouter 的建议默认不选。
                  全选会包含这些项，填入后仍需“检查并保存”才生效。
                </p>
                <div className="capability-review-selection">
                  <div className="capability-review-actions">
                    <button
                      type="button"
                      className="button"
                      disabled={!!busy}
                      aria-describedby="capability-selection-help"
                      onClick={() => chooseRefresh(allRefreshSelected ? "none" : "all")}
                    >
                      {allRefreshSelected ? "取消全选" : "全选"}
                    </button>
                    <button
                      type="button"
                      className="button subtle"
                      disabled={!!busy}
                      onClick={() => chooseRefresh("default")}
                    >
                      恢复默认选择
                    </button>
                  </div>
                  <span className="muted" role="status">
                    已选 {selectedFields.length} / {refreshFields.length} 项
                    {selectedOverrides > 0 && (
                      <span className="capability-selection-warning">
                        ，其中 {selectedOverrides} 项会覆盖手动设置
                      </span>
                    )}
                  </span>
                </div>
                <div className="capability-review-rows">
                  {refresh.proposals.map((item) =>
                    item.fields.map((field) => {
                      const key = fieldKey(item.model, field);
                      return (
                        <label className="capability-review-row" key={key}>
                          <input
                            type="checkbox"
                            checked={!!refreshPicks[key]}
                            disabled={!!busy}
                            onChange={(e) =>
                              setRefreshPicks((old) => ({
                                ...old,
                                [key]: e.target.checked,
                              }))
                            }
                          />
                          <span className="capability-review-model">
                            <strong>{item.model}</strong>
                            <small>{fieldLabels[field.field]}</small>
                          </span>
                          <span className="capability-review-change">
                            <span className="muted">{field.before}</span>
                            <span aria-hidden="true">→</span>
                            <span>{field.after}</span>
                          </span>
                          <span className="capability-review-source">
                            <span className={`source-chip source-${field.source}`}>
                              {refresh.sourceLabels[field.source] || field.source}
                            </span>
                            {field.userSet && (
                              <span className="source-chip source-user">
                                会覆盖你设置的值
                              </span>
                            )}
                          </span>
                        </label>
                      );
                    }),
                  )}
                </div>
              </>
            )}
            {refresh.skipped.length > 0 && (
              <p className="muted">{refresh.skipped[0].reason}</p>
            )}
            <ul className="capability-review-reports">
              {refresh.reports.map((report) => (
                <li key={report.source}>
                  {report.label}：
                  {report.ok
                    ? `匹配 ${report.matched} 个，${report.unmatched} 个没有记录`
                    : "读取失败"}
                  {report.warnings[0] ? ` · ${report.warnings[0]}` : ""}
                </li>
              ))}
            </ul>
            <footer>
              {!refresh.reports.some((r) => r.source === "catalog") && (
                <button
                  className="button"
                  disabled={!!busy}
                  title="联网读取 OpenRouter。它报的是它选中的上游的限额，不是厂商口径，所以查到的项默认不勾"
                  onClick={() =>
                    void checkCapabilities(["official", "approved", "catalog"])
                  }
                >
                  {busy === "refresh:catalog" ? "正在读取…" : "也查 OpenRouter"}
                </button>
              )}
              <button className="button" disabled={!!busy} onClick={() => setRefresh(undefined)}>
                取消
              </button>
              <button
                className="button primary"
                disabled={
                  !selectedFields.length || !!busy
                }
                onClick={applyChecked}
              >
                填入选中项{selectedFields.length > 0 ? `（${selectedFields.length}）` : ""}
              </button>
            </footer>
          </div>
        </Dialog>
      )}
      {confirmDelete && (
        <Dialog
          title="删除通道"
          close={() => { if (busy !== "apply") setConfirmDelete(null); }}
          dismissible={busy !== "apply"}
        >
          <div className="channel-confirm">
            <p>
              删除通道 <strong>{confirmDelete.name}</strong> 后，新会话不再使用它。其他通道和已有会话不受影响。
            </p>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <footer>
              <button
                className="button"
                disabled={busy === "apply"}
                onClick={() => setConfirmDelete(null)}
              >
                取消
              </button>
              <button
                className="button danger"
                disabled={busy === "apply"}
                onClick={() => void deleteChannel(confirmDelete.id)}
              >
                {busy === "apply" ? "正在删除…" : "删除通道"}
              </button>
            </footer>
          </div>
        </Dialog>
      )}
      {preview && (
        <Dialog
          title={snapshot?.configScope === "standalone" ? "确认保存设置" : "确认保存到 MMF"}
          close={() => setPreview(undefined)}
          dismissible={busy !== "apply"}
        >
          <div className="channel-review">
            <p>{preview.writeSummary}</p>
            <code className="channel-config-path">{preview.configRoot}</code>
            <ul>
              {preview.changes.map((c, i) => (
                <li key={i}>
                  <strong>
                    {c.kind === "channel-remove"
                      ? "删除通道"
                      : c.kind === "add"
                        ? "加入通道"
                        : c.kind === "remove"
                          ? "从通道移除"
                          : c.kind === "connection"
                            ? "修改连接"
                            : c.kind === "vision"
                              ? "修改识图能力"
                              : c.kind === "context"
                                ? "修改上下文长度"
                                : "修改默认 effort"}
                  </strong>
                  <span>
                    {c.model}
                    {(c.kind === "effort" ||
                      c.kind === "connection" ||
                      c.kind === "vision" ||
                      c.kind === "context") &&
                      `：${c.before} → ${c.after || "自动（移除覆盖）"}`}
                  </span>
                  {c.channels && (
                    <small>同时影响：{c.channels.join("、")}</small>
                  )}
                </li>
              ))}
            </ul>
            <p className="form-hint">
              确认后将写入当前配置并刷新已发布模型目录。
            </p>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <footer>
              <button
                className="button"
                disabled={!!busy}
                onClick={() => setPreview(undefined)}
              >
                继续修改
              </button>
              <button
                className="button primary"
                disabled={!!busy}
                onClick={() => {
                  if (window.confirm("确认写入当前配置并刷新已发布模型目录？")) void apply();
                }}
              >
                {busy === "apply" ? "正在保存并校验…" : snapshot?.configScope === "standalone" ? "保存设置" : "保存到 MMF"}
              </button>
            </footer>
          </div>
        </Dialog>
      )}
      {leave !== null && (
        <Dialog title="有尚未保存的修改" close={() => setLeave(null)}>
          <p>离开后将丢弃本页修改。已保存的配置不会改变。</p>
          <div className="channel-leave">
            <button className="button" onClick={() => setLeave(null)}>
              继续编辑
            </button>
            <button
              className="button"
              onClick={() => {
                const destination = leave;
                setLeave(null);
                if (destination === "back") back();
                else if (destination === providerId) void load();
                else {
                  reset(snapshot?.providers.find((p) => p.id === destination));
                  setNotice("");
                }
              }}
            >
              放弃修改并离开
            </button>
          </div>
        </Dialog>
      )}
    </section>
  );
}
