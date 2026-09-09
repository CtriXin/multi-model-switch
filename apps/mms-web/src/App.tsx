import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  Command,
  FileText,
  FolderOpen,
  Inbox,
  Menu,
  Moon,
  PanelRight,
  Plus,
  Search,
  Settings2,
  SlidersHorizontal,
  Sun,
  ChevronDown,
  X,
} from "lucide-react";
import type { Bootstrap, Page, SessionDetail, FileSelection } from "./types";
import { bootstrap, getSession, listSessions, isPreview, mutate } from "./api";
import {
  Composer,
  Dialog,
  Logo,
  Status,
  WorkspacePicker,
  harnessNames,
} from "./components";
import { ArtifactView } from "./ArtifactView";
import { Transcript } from "./Transcript";
import { ConversationOutline } from "./ConversationOutline";
import { CurrentActivity, sessionStatus } from "./SessionStatus";
import { useSessionAttention } from "./SessionAttention";
import { FilesPanel } from "./FilesPanel";
import { RuntimePanel, SessionMenu, exportConversation } from "./SessionTools";
import { RecipeImport } from "./Recipe";
import type { Recipe } from "./Recipe";
import { SettingsPage } from "./SettingsPage";
import { TaskSettings, SessionSettings } from "./TaskSettings";
import { Popover } from "./Popover";
import { useLaunchFacts, readRoutePreferences } from "./ModelExplorer";
import { WorkspaceDialog } from "./LaunchOptions";

const empty: Bootstrap = {
  version: "1",
  mode: "live",
  csrfToken: "",
  capabilities: { catalogRead: false, configure: false, launch: false },
  workspaces: [],
  models: [],
  services: [],
  presets: [],
  sessions: [],
  diagnostics: [],
};
function readSetting<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}
function saveSetting(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
}
export function App() {
  const [data, setData] = useState<Bootstrap>(empty);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [statusesStale, setStatusesStale] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState<Page>("new");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [workspaceId, setWorkspaceId] = useState(() =>
    readSetting("mms-web-workspace", ""),
  );
  const [recipe, setRecipe] = useState<(Recipe & { key: number }) | null>(null);
  const [planMode, setPlanMode] = useState(false);
  const [addFolder, setAddFolder] = useState(false);
  const [presetId, setPresetId] = useState(() =>
    readSetting("mms-web-preset", ""),
  );
  const [settingsEdit, setSettingsEdit] = useState({dirty: false, busy: false});
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  const [search, setSearch] = useState(false);
  const [query, setQuery] = useState("");
  const [attention, setAttention] = useState<
    "all" | "waiting" | "error" | "archived"
  >("all");
  const [collapsed, setCollapsed] = useState<string[]>(() =>
    readSetting("mms-web-collapsed", []),
  );
  const [filesOpen, setFilesOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [panel, setPanel] = useState(false);
  const [panelTab, setPanelTab] = useState<"artifacts" | "runtime">(
    "artifacts",
  );
  const [artifactId, setArtifactId] = useState("");
  const [selectionRequest, setSelectionRequest] = useState<{ nonce: string; sessionId: string; selection: FileSelection }>();
  const [atBottom, setAtBottom] = useState(true);
  const [autoCollapseProcess, setAutoCollapseProcess] = useState(() => readSetting("mms-web-auto-collapse-process", true));
  const [accent, setAccent] = useState(() =>
    readSetting("mms-web-accent", "indigo"),
  );
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    readSetting("mms-web-theme", "light"),
  );
  const [favorites, setFavorites] = useState<string[]>(() => {
    const value = readSetting<unknown>("mms-web-favorites", []);
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string")
      : [];
  });
  useEffect(() => { saveSetting("mms-web-auto-collapse-process", autoCollapseProcess); }, [autoCollapseProcess]);
  const currentSelection = useRef("");
  const mutation = useRef(false);
  const generation = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const followOutput = useRef(true);
  const holdPosition = useRef(false);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await bootstrap(signal);
      if (signal?.aborted) return;
      setData(result);
      setConnected(true);
      setError("");
      setWorkspaceId((old) =>
        result.workspaces.some((w) => w.id === old)
          ? old
          : result.workspaces.find((w) => w.id !== "default")?.id ||
            result.workspaces[0]?.id ||
            "",
      );
      setPresetId((old) =>
        result.presets.some((p) => p.id === old && p.available)
          ? old
          : result.presets.find((p) => p.available)?.id || "",
      );
    } catch (e) {
      if (!signal?.aborted) {
        setConnected(false);
        setError((e as Error).message || "无法连接 MMS 本地服务。");
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  useEffect(() => {
    if (presetId) saveSetting("mms-web-preset", presetId);
  }, [presetId]);
  useEffect(() => {
    if (workspaceId) saveSetting("mms-web-workspace", workspaceId);
  }, [workspaceId]);
  useEffect(() => {
    const id = new URLSearchParams(location.hash.slice(1)).get("session");
    if (id) openSession(id);
    // Recover the same conversation on a browser refresh.
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveSetting("mms-web-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.dataset.accent = accent;
    saveSetting("mms-web-accent", accent);
  }, [accent]);
  useEffect(() => {
    const media = matchMedia("(max-width: 1200px)");
    const collapse = () => {
      if (media.matches) setPanel(false);
    };
    media.addEventListener("change", collapse);
    return () => media.removeEventListener("change", collapse);
  }, []);
  const latestEvent = detail?.events.at(-1);
  useEffect(() => {
    if (followOutput.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [selectedId, latestEvent?.id, latestEvent?.text, latestEvent?.thinking]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch((v) => !v);
      }
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    currentSelection.current = selectedId;
    if (!selectedId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function update() {
      if (mutation.current) {
        timer = setTimeout(update, 1200);
        return;
      }
      const startedGeneration = generation.current;
      try {
        const result = await getSession(selectedId, controller.signal);
        if (
          !controller.signal.aborted &&
          !mutation.current &&
          generation.current === startedGeneration
        ) {
          setDetail(result);
          setSessionError("");
          setData((old) => ({
            ...old,
            sessions: old.sessions.map((s) =>
              s.id === result.session.id ? result.session : s,
            ),
          }));
        }
      } catch (e) {
        if (!controller.signal.aborted) setSessionError((e as Error).message);
      }
      if (!controller.signal.aborted) timer = setTimeout(update, 1200);
    }
    void update();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [selectedId]);
  useEffect(() => {
    if (isPreview) return;
    const timer = setInterval(() => {
      if (!mutation.current) void load();
    }, 8000);
    return () => clearInterval(timer);
  }, [load]);
  useEffect(() => {
    if (isPreview) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function update() {
      const startedGeneration = generation.current;
      {
        try {
          const sessions = await listSessions(controller.signal);
          if (
            !controller.signal.aborted &&
            generation.current === startedGeneration
          ) {
            setData((old) => ({
              ...old,
              sessions: sessions.map((session) => {
                const previous = old.sessions.find((s) => s.id === session.id);
                return previous && previous.updatedAt > session.updatedAt
                  ? previous
                  : session;
              }),
            }));
            setDetail((old) => {
              const session = sessions.find((s) => s.id === old?.session.id);
              return old &&
                session &&
                session.updatedAt >= old.session.updatedAt
                ? { ...old, session }
                : old;
            });
            setStatusesStale(false);
          }
        } catch {
          if (!controller.signal.aborted) setStatusesStale(true);
        }
      }
      if (!controller.signal.aborted)
        timer = setTimeout(update, document.hidden ? 4000 : 1000);
    }
    void update();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);
  function requestNavigation(action: () => void) {
    if (settingsEdit.busy) {
      setError("配置正在保存，请等待保存结束后离开。");
      return;
    }
    if (settingsEdit.dirty) {
      setPendingNavigation(() => action);
      return;
    }
    action();
  }
  function navigate(next: Page) {
    requestNavigation(() => {
    setPage(next);
    if (next !== "session")
      history.replaceState(null, "", location.pathname + location.search);
    setNavOpen(false);
    if (next !== "session") {
      setSelectedId("");
      setDetail(null);
      currentSelection.current = "";
    }
    });
  }
  function openSession(id: string) {
    requestNavigation(() => {
    history.replaceState(null, "", "#session=" + encodeURIComponent(id));
    followOutput.current = true;
    holdPosition.current = false;
    setAtBottom(true);
    currentSelection.current = id;
    setSelectedId(id);
    setDetail(null);
    setSessionError("");
    setPage("session");
    setNavOpen(false);
    setSearch(false);
    setArtifactId("");
    });
  }
  async function runAction(
    path: string,
    body: Record<string, unknown>,
    create = false,
  ): Promise<boolean> {
    if (mutation.current) return false;
    generation.current += 1;
    mutation.current = true;
    setBusy(true);
    setError("");
    const originId = currentSelection.current;
    try {
      const result = await mutate<SessionDetail>(path, body);
      if (create) {
        openSession(result.session.id);
        setDetail(result);
      } else if (currentSelection.current === originId) setDetail(result);
      setData((old) => ({
        ...old,
        sessions: [
          result.session,
          ...old.sessions.filter((s) => s.id !== result.session.id),
        ],
      }));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      mutation.current = false;
      setBusy(false);
    }
  }
  const waiting = data.sessions.filter(
    (s) => s.state === "waiting" && !s.archived,
  );
  const workspace = data.workspaces.find((w) => w.id === workspaceId);
  const preset = data.presets.find((p) => p.id === presetId);
  const launchFacts = useLaunchFacts(presetId, workspaceId);
  const [effortChoice, setEffortChoice] = useState<{
    id: string;
    level: string;
  }>({ id: "", level: "" });
  const effort =
    effortChoice.id === presetId
      ? effortChoice.level
      : readRoutePreferences()[presetId]?.effort || "";
  function selectTaskPreset(id: string) {
    if (id !== presetId) {
      setPresetId(id);
      setEffortChoice({ id: "", level: "" });
    }
  }

  const artifact =
    detail?.artifacts.find((a) => a.id === artifactId) || detail?.artifacts[0];
  const filtered = data.sessions.filter((s) =>
    attention === "archived"
      ? !!s.archived
      : !s.archived &&
        (attention === "all" ||
          s.state === attention ||
          (attention === "error" && s.activity?.phase === "error")),
  );
  const navWorkspaces = [...data.workspaces];
  for (const session of data.sessions) {
    if (!navWorkspaces.some((w) => w.id === session.workspaceId))
      navWorkspaces.push({
        id: session.workspaceId,
        name: "其他工作空间",
        path: "",
      });
  }
  const searchResults = data.sessions.filter((s) =>
    (s.title + " " + s.modelName + " " + s.harness + " " + s.cwd)
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  function favorite(id: string) {
    setFavorites((old) => {
      const next = old.includes(id)
        ? old.filter((x) => x !== id)
        : [...old, id];
      saveSetting("mms-web-favorites", next);
      return next;
    });
  }
  const signals = useSessionAttention(
    data.sessions,
    detail,
    page === "session" && atBottom && !sessionError,
    connected && !statusesStale,
  );
  return (
    <div className="app-shell" data-page={page}>
      {navOpen && (
        <button
          className="nav-scrim"
          aria-label="关闭导航"
          onClick={() => setNavOpen(false)}
        />
      )}
      <aside
        className={"sidebar " + (navOpen ? "open" : "")}
        aria-label="工作区与会话"
      >
        <button
          className="brand"
          onClick={() => navigate("new")}
          aria-label="MMS 首页"
        >
          <Logo />
          <span>mms</span>
        </button>
        <div className="sidebar-actions">
          <button className="new-task" onClick={() => navigate("new")}>
            <Plus size={17} />
            新会话
          </button>
          <button className="search-trigger" onClick={() => setSearch(true)}>
            <Search size={16} />
            搜索会话<kbd>⌘ K</kbd>
          </button>
        </div>
        {waiting.length > 0 && (
          <button
            className="attention-banner"
            onClick={() => setAttention("waiting")}
          >
            <Inbox size={16} />
            <span>{waiting.length} 条会话需要你回答</span>
            <ChevronRight size={14} />
          </button>
        )}
        <div className="session-nav">
          <div className="sidebar-section-label">
            <Popover
              title="筛选会话"
              className="session-filter"
              label={
                <>
                  <span>
                    {
                      {
                        all: "所有会话",
                        waiting: "等待回答",
                        error: "执行出错",
                        archived: "已归档",
                      }[attention]
                    }
                  </span>
                  <ChevronDown size={12} />
                </>
              }
            >
              {(close) => (
                <>
                  <header>
                    <strong>筛选会话</strong>
                  </header>
                  {(
                    [
                      ["all", "所有会话", "按工作空间浏览正在使用的会话"],
                      ["waiting", "等待回答", "AI 提出问题，需要你作出选择"],
                      ["error", "执行出错", "查看失败原因，然后继续工作"],
                      ["archived", "已归档", "收起的历史会话，可以恢复"],
                    ] as const
                  ).map(([id, label, description]) => (
                    <button
                      type="button"
                      key={id}
                      className={
                        "filter-option " + (attention === id ? "selected" : "")
                      }
                      onClick={() => {
                        setAttention(id);
                        close();
                      }}
                    >
                      <span>
                        <strong>{label}</strong>
                        <small>{description}</small>
                      </span>
                      {attention === id && <Check size={14} />}
                    </button>
                  ))}
                </>
              )}
            </Popover>
            <button
              type="button"
              className="icon-button add-workspace"
              aria-label="添加工作空间"
              onClick={() => setAddFolder(true)}
            >
              <Plus size={15} />
            </button>
          </div>
          {loading ? (
            <div className="nav-skeleton">
              <i />
              <i />
              <i />
            </div>
          ) : (
            navWorkspaces.map((w) => {
              const sessions = filtered.filter((s) => s.workspaceId === w.id);
              return (
                <section className="workspace-group" key={w.id}>
                  <button
                    className="workspace-heading"
                    title={w.path}
                    aria-expanded={!collapsed.includes(w.id)}
                    onClick={() =>
                      setCollapsed((old) => {
                        const next = old.includes(w.id)
                          ? old.filter((id) => id !== w.id)
                          : [...old, w.id];
                        saveSetting("mms-web-collapsed", next);
                        return next;
                      })
                    }
                  >
                    <ChevronRight
                      className={collapsed.includes(w.id) ? "" : "expanded"}
                      size={13}
                    />
                    <FolderOpen size={14} />
                    <span>{w.id === "default" ? "启动目录" : w.name}</span>
                    <span>{sessions.length}</span>
                  </button>
                  {!collapsed.includes(w.id) &&
                    sessions.map((s) => (
                      <button
                        className={
                          "session-link " +
                          (selectedId === s.id ? "selected " : "") +
                          (signals.unread[s.id] ? "has-unread " : "") +
                          (signals.flashes[s.id] ? "just-completed" : "")
                        }
                        data-phase={
                          sessionStatus(s, !connected || statusesStale).phase
                        }
                        aria-current={selectedId === s.id ? "page" : undefined}
                        key={s.id}
                        onClick={() => openSession(s.id)}
                      >
                        <Status
                          session={s}
                          compact
                          disconnected={!connected || statusesStale}
                        />
                        <span className="session-link-copy">
                          <span className="session-title-row">
                            <strong>{s.title}</strong>
                            {signals.unread[s.id] && (
                              <span className="new-reply-badge">新回复</span>
                            )}
                          </span>
                          <small>
                            <span
                              className={
                                "session-phase " +
                                sessionStatus(s, !connected || statusesStale)
                                  .phase
                              }
                            >
                              {
                                sessionStatus(s, !connected || statusesStale)
                                  .label
                              }
                            </span>
                            <span>·</span>
                            {s.modelName}
                          </small>
                        </span>
                        {s.state === "waiting" && (
                          <span
                            className="attention-dot"
                            aria-label="需要确认"
                          />
                        )}
                      </button>
                    ))}
                </section>
              );
            })
          )}
          {!loading && !filtered.length && (
            <p className="sidebar-empty">
              {attention !== "all"
                ? "这个分类中没有会话。"
                : "开始第一个任务后，会话会保存在这里。"}
            </p>
          )}
        </div>
        <div className="sidebar-footer">
          <button className="settings-entry" onClick={() => navigate("models")}>
            <Settings2 size={17} />
            <span>设置</span>
          </button>
          <span
            className={
              "connection-dot " + (connected && !statusesStale ? "online" : "")
            }
            title={
              connected && !statusesStale
                ? "本地服务已连接"
                : "等待连接本地服务"
            }
            aria-label={
              connected && !statusesStale
                ? "本地服务已连接"
                : "等待连接本地服务"
            }
          />
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <button
            className="icon-button mobile-nav"
            aria-label="展开会话导航"
            onClick={() => setNavOpen(true)}
          >
            <Menu size={19} />
          </button>
          <div className="breadcrumb">
            <span>
              {page === "models"
                ? "设置"
                : detail
                  ? data.workspaces.find(
                      (w) => w.id === detail.session.workspaceId,
                    )?.name || "工作空间"
                  : workspace?.name || "工作空间"}
            </span>
            <ChevronRight size={14} />
            <strong>
              {page === "new"
                ? "新建任务"
                : page === "models"
                  ? "设置"
                  : detail?.session.title || "加载会话"}
            </strong>
          </div>
          <div className="topbar-actions">
            {detail && (
              <Status
                session={detail.session}
                disconnected={!connected || statusesStale || !!sessionError}
              />
            )}
            {page === "session" && (
              <button
                className={"icon-button " + (panel ? "active" : "")}
                aria-label="切换成果侧栏"
                aria-pressed={panel}
                onClick={() => setPanel(!panel)}
              >
                <PanelRight size={18} />
              </button>
            )}
          </div>
        </header>
        {isPreview && (
          <div className="preview-banner">
            <span>
              界面预览 <span>·</span> 所有内容均为示例，不调用模型或修改文件
            </span>
            <a href={location.pathname}>
              连接真实服务
              <ArrowUpRight size={13} />
            </a>
          </div>
        )}
        {error && (
          <div className="error-banner" role="alert">
            <CircleAlert size={17} />
            <span>{error}</span>
            {!connected && (
              <button className="text-button" onClick={() => void load()}>
                重新连接
              </button>
            )}
            <button
              className="icon-button"
              aria-label="关闭错误提示"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {page === "new" && (
          <div className="home-scroll">
            <div className="home-content">
              <div className="home-intro">
                <WorkspacePicker
                  workspaces={data.workspaces}
                  value={workspaceId}
                  change={(id) =>
                    id === "__add__" ? setAddFolder(true) : setWorkspaceId(id)
                  }
                  allowAdd={!isPreview}
                />
                <h1>从一个想法开始</h1>
                <p>写下想法，或引用电脑上的文件。</p>
              </div>
              <div className="recipe-access">
                <RecipeImport
                  loaded={(item) => {
                    setRecipe({ ...item, key: Date.now() });
                    setPlanMode(item.planning);
                    const match = data.presets.find(
                      (p) => p.available && p.name === item.preferredModel,
                    );
                    setPresetId(match?.id || "");
                  }}
                />
              </div>
              {recipe && (
                <p className="recipe-loaded" role="status">
                  已载入「{recipe.title}
                  」。任务说明已填入草稿，检查内容、工作文件夹和模型后发送。模板不会自动附带附件或连接凭据。
                </p>
              )}
              <Composer
                key={`new:${workspaceId}:${recipe?.key || ""}`}
                draftKey={`new:${workspaceId}:${recipe?.key || ""}`}
                initialText={recipe?.prompt}
                workspaceId={workspaceId}
                disabled={
                  !connected ||
                  !data.capabilities.launch ||
                  !launchFacts.facts ||
                  !presetId ||
                  !workspaceId
                }
                reason={
                  !connected
                    ? "连接 MMS 本地服务后即可开始。"
                    : "请选择可用模型和工作文件夹后开始。"
                }
                busy={busy}
                placeholder="想做什么？"
                send={(text, extras) =>
                  runAction(
                    "/sessions",
                    {
                      workspaceId,
                      presetId,
                      title: text.slice(0, 42),
                      prompt: text,
                      planMode,
                      thinkingLevel: effort || undefined,
                      ...extras,
                    },
                    true,
                  )
                }
              >
                <TaskSettings
                  presets={data.presets}
                  models={data.models}
                  workspaceId={workspaceId}
                  value={presetId}
                  change={selectTaskPreset}
                  favorites={favorites}
                  toggleFavorite={favorite}
                  facts={launchFacts.facts}
                  effort={effort}
                  setEffort={(level) =>
                    setEffortChoice({ id: presetId, level })
                  }
                  planning={planMode}
                  setPlanning={setPlanMode}
                  settings={() => navigate("models")}
                />
              </Composer>
              {launchFacts.error && (
                <p className="inline-alert" role="alert">
                  {launchFacts.error}
                </p>
              )}
              <div className="input-hint">
                <span>Enter 发送 · Shift + Enter 换行</span>
              </div>
              {!data.presets.length && (
                <div className="setup-inline">
                  <Settings2 size={19} />
                  <div>
                    <strong>连接你的第一个模型</strong>
                    <p>有了模型服务，就可以开始工作。</p>
                  </div>
                  <button className="button" onClick={() => navigate("models")}>
                    前往设置
                    <ArrowRight size={14} />
                  </button>
                </div>
              )}
              {data.sessions.length > 0 && (
                <section className="recent-section">
                  <div className="section-heading">
                    <h2>最近在做</h2>
                    <span className="muted">{data.sessions.length} 个会话</span>
                  </div>
                  {data.sessions
                    .filter((s) => !s.archived)
                    .slice(0, 3)
                    .map((s) => (
                      <button
                        className="recent-row"
                        key={s.id}
                        onClick={() => openSession(s.id)}
                      >
                        <span className="recent-icon">
                          {s.state === "waiting" ? (
                            <CircleAlert size={19} />
                          ) : (
                            <FileText size={19} />
                          )}
                        </span>
                        <span className="recent-copy">
                          <strong>{s.title}</strong>
                          <small>
                            {s.summary ||
                              harnessNames[s.harness] + " · " + s.modelName}
                          </small>
                        </span>
                        <Status
                          session={s}
                          disconnected={!connected || statusesStale}
                        />
                        <ChevronRight size={16} />
                      </button>
                    ))}
                </section>
              )}
              {data.diagnostics.length > 0 && (
                <div className="diagnostics">
                  {data.diagnostics.map((d, i) => (
                    <p key={d.code + i}>
                      <CircleAlert size={15} />
                      {d.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        {page === "models" && (
          <SettingsPage
            requestNavigation={requestNavigation}
            editStateChanged={setSettingsEdit}
            autoCollapseProcess={autoCollapseProcess}
            setAutoCollapseProcess={setAutoCollapseProcess}
            presetId={presetId}
            selectPreset={selectTaskPreset}
            workspaceId={workspaceId}
            effortChanged={(id) => {
              if (id === presetId) setEffortChoice({ id: "", level: "" });
            }}
            theme={theme}
            setTheme={setTheme}
            accent={accent}
            setAccent={setAccent}
            back={() => navigate("new")}
            data={data}
            favorites={favorites}
            toggleFavorite={favorite}
            refresh={() => void load()}
          />
        )}
        {page === "session" && (
          <div className={"session-layout " + (panel ? "with-panel" : "")}>
            <div className="conversation">
              <div className="conversation-scroll-shell">
                <div
                  className="conversation-scroll"
                  ref={scroll}
                  onWheelCapture={() => {
                    holdPosition.current = false;
                  }}
                  onTouchMoveCapture={() => {
                    holdPosition.current = false;
                  }}
                  onPointerDownCapture={() => {
                    holdPosition.current = false;
                  }}
                  onKeyDownCapture={(e) => {
                    if (
                      [
                        "PageDown",
                        "PageUp",
                        "End",
                        "Home",
                        "ArrowDown",
                        "ArrowUp",
                      ].includes(e.key)
                    )
                      holdPosition.current = false;
                  }}
                  onScroll={() => {
                    const el = scroll.current;
                    if (el) {
                      followOutput.current =
                        !holdPosition.current &&
                        el.scrollHeight - el.scrollTop - el.clientHeight < 100;
                      setAtBottom(followOutput.current);
                    }
                  }}
                >
                  {sessionError && (
                    <p className="inline-alert" role="alert">
                      {sessionError} 已保留最近一次会话内容。
                    </p>
                  )}
                  {!detail && !sessionError && (
                    <div className="message-skeleton">
                      <i />
                      <i />
                      <i />
                    </div>
                  )}
                  {detail && (
                    <div className="conversation-content">
                      <Transcript
                        key={detail.session.id}
                        autoCollapseProcess={autoCollapseProcess}
                        disconnected={
                          !connected || statusesStale || !!sessionError
                        }
                        action={runAction}
                        detail={detail}
                        busy={busy}
                        approve={(id, decision, value) =>
                          void runAction(
                            "/sessions/" +
                              encodeURIComponent(detail.session.id) +
                              "/approvals/" +
                              encodeURIComponent(id),
                            {
                              decision,
                              ...(value === undefined ? {} : { value }),
                            },
                          )
                        }
                      />
                      {!detail.events.length && (
                        <p className="empty-results">
                          会话已建立。发送第一条消息开始工作。
                        </p>
                      )}
                    </div>
                  )}
                </div>
                {detail && (
                  <ConversationOutline
                    key={detail.session.id}
                    events={detail.events}
                    scroll={scroll}
                    beforeJump={() => {
                      holdPosition.current = true;
                      followOutput.current = false;
                      setAtBottom(false);
                    }}
                  />
                )}
                {detail && !atBottom && (
                  <button
                    className="return-latest"
                    onClick={() => {
                      holdPosition.current = false;
                      followOutput.current = true;
                      scroll.current?.scrollTo({
                        top: scroll.current.scrollHeight,
                        behavior: "instant",
                      });
                      setAtBottom(true);
                    }}
                  >
                    <ArrowDown size={15} />
                    回到最新消息
                  </button>
                )}
              </div>
              {detail && (
                <div className="session-composer">
                  <CurrentActivity
                    session={detail.session}
                    disconnected={!connected || statusesStale || !!sessionError}
                  />
                  <div className="session-workbar">
                    <button
                      title={detail.session.cwd}
                      onClick={() => setFilesOpen(true)}
                    >
                      <FolderOpen size={14} />
                      {detail.session.cwd?.split("/").pop() || "工作文件"}
                    </button>
                    <SessionMenu
                      detail={detail}
                      action={runAction}
                      busy={busy}
                    />
                  </div>
                  <Composer
                    key={detail.session.id}
                    selectionRequest={selectionRequest?.sessionId === detail.session.id ? selectionRequest : undefined}
                    selectionHandled={() => setSelectionRequest(undefined)}
                    workspaceId={detail.session.workspaceId}
                    sessionId={detail.session.id}
                    sessionAlive={!!detail.runtime?.alive}
                    onCommand={async (command, args) => {
                      if (command === "export") {
                        exportConversation(detail);
                        return true;
                      }
                      if (command === "fork")
                        return runAction(
                          `/sessions/${detail.session.id}/fork`,
                          {},
                          true,
                        );
                      if (command === "name")
                        return runAction(
                          `/sessions/${detail.session.id}/manage`,
                          { title: args },
                        );
                      if (command === "plan") {
                        if (!args) {
                          setPanel(true);
                          setPanelTab("runtime");
                          return true;
                        }
                        if (!["on", "off"].includes(args))
                          throw new Error(
                            "用 /plan on 进入只读规划，/plan off 切回执行。",
                          );
                        return runAction(
                          `/sessions/${detail.session.id}/control`,
                          { action: "plan", value: args === "on" },
                        );
                      }
                      if (command === "thinking" && !args) {
                        setPanel(true);
                        setPanelTab("runtime");
                        return true;
                      }
                      return runAction(
                        `/sessions/${detail.session.id}/control`,
                        {
                          action:
                            command === "clear-queue" ? "clearQueue" : command,
                          value: args,
                        },
                      );
                    }}
                    disabled={
                      !detail.session.capabilities.send ||
                      !!sessionError ||
                      !connected ||
                      statusesStale
                    }
                    reason={
                      sessionError || !connected || statusesStale
                        ? "恢复会话连接后即可发送。"
                        : "该会话目前只支持查看。"
                    }
                    busy={busy}
                    running={detail.session.state === "running"}
                    send={(text, extras) =>
                      runAction(
                        "/sessions/" +
                          encodeURIComponent(detail.session.id) +
                          "/messages",
                        { text, ...extras },
                      )
                    }
                    stop={
                      detail.session.capabilities.stop
                        ? () =>
                            void runAction(
                              "/sessions/" +
                                encodeURIComponent(detail.session.id) +
                                "/stop",
                              {},
                            )
                        : undefined
                    }
                  >
                    <SessionSettings
                      presets={data.presets} models={data.models}
                      favorites={favorites} toggleFavorite={favorite}
                      detail={detail}
                      busy={busy}
                      action={runAction}
                      more={() => {
                        setPanel(true);
                        setPanelTab("runtime");
                      }}
                    />
                  </Composer>
                </div>
              )}
            </div>
            {panel && (
              <aside className="result-panel">
                <div className="panel-tabs">
                  <button
                    className={panelTab === "artifacts" ? "active" : ""}
                    onClick={() => setPanelTab("artifacts")}
                  >
                    成果<span>{detail?.artifacts.length || 0}</span>
                  </button>
                  <button
                    className={panelTab === "runtime" ? "active" : ""}
                    onClick={() => setPanelTab("runtime")}
                  >
                    运行详情
                  </button>
                  <button
                    className="icon-button"
                    aria-label="关闭成果侧栏"
                    onClick={() => setPanel(false)}
                  >
                    <X size={16} />
                  </button>
                </div>
                {panelTab === "artifacts" ? (
                  artifact ? (
                    <>
                      {detail!.artifacts.length > 1 && (
                        <select
                          aria-label="选择成果"
                          className="artifact-select"
                          value={artifact.id}
                          onChange={(e) => setArtifactId(e.target.value)}
                        >
                          {detail!.artifacts.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.name}
                            </option>
                          ))}
                        </select>
                      )}
                      <ArtifactView key={`${detail!.session.id}:${artifact.id}`} artifact={artifact} sessionId={detail!.session.id}
                        onSelect={selection => {
                          setSelectionRequest({ nonce: crypto.randomUUID(), sessionId: detail!.session.id, selection });
                          if (window.matchMedia("(max-width: 1200px)").matches) setPanel(false);
                        }} />
                      {detail?.artifactNotice && <p className="section-note">{detail.artifactNotice}</p>}
                    </>
                  ) : (
                    <div className="panel-empty">
                      <FileText size={28} />
                      <h3>成果会出现在这里</h3>
                      <p>
                        会话生成的文档与变更，
                        <br />
                        可以一边讨论，一边查看。
                      </p>
                      {detail?.artifactNotice && <p>{detail.artifactNotice}</p>}
                    </div>
                  )
                ) : (
                  detail && (
                    <RuntimePanel
                      detail={detail}
                      action={runAction}
                      busy={busy}
                    />
                  )
                )}
              </aside>
            )}
          </div>
        )}
      </main>
      {filesOpen && (
        <Dialog close={() => setFilesOpen(false)} title="工作文件与变更">
          {detail && (
            <FilesPanel
              key={detail.session.workspaceId}
              workspaceId={detail.session.workspaceId}
            />
          )}
        </Dialog>
      )}
      {addFolder && (
        <WorkspaceDialog
          close={() => setAddFolder(false)}
          added={(w) => {
            setData((old) => ({
              ...old,
              workspaces: [...old.workspaces.filter((x) => x.id !== w.id), w],
            }));
            setWorkspaceId(w.id);
            void load();
          }}
        />
      )}
      {search && (
        <Dialog
          title="搜索会话"
          close={() => {
            setSearch(false);
            setQuery("");
          }}
        >
          <label className="dialog-search">
            <Search size={19} />
            <input
              autoFocus
              aria-label="搜索全部会话"
              placeholder="输入任务、模型或工具名称…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="search-results">
            {searchResults.map((s) => (
              <button key={s.id} onClick={() => openSession(s.id)}>
                <FileText size={17} />
                <span>
                  <strong>{s.title}</strong>
                  <small>
                    {harnessNames[s.harness]} · {s.modelName}
                  </small>
                </span>
                <ArrowUpRight size={15} />
              </button>
            ))}
            {!searchResults.length && (
              <p className="empty-results">没有找到匹配的会话。</p>
            )}
          </div>
          <div className="search-footer">
            <Command size={12} /> K 打开搜索 <span>Esc 关闭</span>
          </div>
        </Dialog>
      )}
      {pendingNavigation && <Dialog title="保留未保存的修改？" close={() => setPendingNavigation(null)}>
        <p>通道地址、Key、模型或 effort 还有未保存的修改。可以继续编辑，或放弃本次修改后离开。</p>
        <div className="dialog-actions">
          <button className="button" onClick={() => setPendingNavigation(null)}>继续编辑</button>
          <button className="button primary" onClick={() => { const action = pendingNavigation; setPendingNavigation(null); setSettingsEdit({dirty:false,busy:false}); action(); }}>放弃修改并离开</button>
        </div>
      </Dialog>}
    </div>
  );
}
