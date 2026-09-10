import { useCallback, useEffect, useRef, useState } from "react";
import {
  Archive,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Copy,
  Download,
  GitBranch,
  CircleAlert,
  Command,
  FileText,
  FolderOpen,
  Inbox,
  Menu,
  MessageSquarePlus,
  Moon,
  MoreHorizontal,
  PanelRight,
  Pencil,
  Plus,
  Search,
  Trash2,
  Settings2,
  SlidersHorizontal,
  Sun,
  ChevronDown,
  X,
} from "lucide-react";
import type { Bootstrap, Page, SessionDetail, FileSelection } from "./types";
import { bootstrap, getSession, includeCliSessions, listSessions, isPreview, mutate, request } from "./api";
import {
  Composer,
  Dialog,
  Logo,
  AppVersion,
  Status,
  WorkspacePicker,
  harnessNames,
} from "./components";
import { HelpGuide } from "./HelpGuide";
import { UpdateCenter } from "./UpdateCenter";
import { ConnectionDialog } from "./ConnectionDialog";
import { GuidedTour } from "./GuidedTour";
import type { TourStep } from "./GuidedTour";
import type { GuideAction } from "./guide-content";
import { ArtifactView } from "./ArtifactView";
import { ProjectMaterials } from "./ProjectMaterials";
import { Transcript } from "./Transcript";
import { ConversationOutline } from "./ConversationOutline";
import { CurrentActivity, sessionStatus } from "./SessionStatus";
import { useSessionAttention } from "./SessionAttention";
import { FilesPanel } from "./FilesPanel";
import { RuntimePanel, SessionMenu, exportConversation } from "./SessionTools";
import { RecipeImport, readRecipeDraft, saveRecipeDraft } from "./Recipe";
import { modelRequirementIssues, requiredSkillMatches } from "./recipe-core";
import type { Skill } from "./SkillPicker";
import type { LaunchFacts } from "./ModelExplorer";
import { VendorMark, vendorTint } from "./VendorMark";
import type { RecipeDraft } from "./Recipe";
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
// Appearance fonts. Families mirror Glint's catalogue so the two products
// offer the same names. Everything is a locally installed face: a webfont
// would put a network request in the path of a tool that runs offline, and
// leave the page swapping type whenever that request is slow.
type FontEntry = { label: string; css: string[]; mono?: boolean; cjk?: boolean };

export const FONT_FAMILIES: Record<string, FontEntry> = {
  inter: { label: "Inter", css: ['"Inter"'] },
  helvetica: { label: "Helvetica Neue", css: ['"Helvetica Neue"', "Helvetica"] },
  jetbrains: { label: "JetBrains Mono", css: ['"JetBrains Mono"'], mono: true },
  fira: { label: "Fira Code", css: ['"Fira Code"'], mono: true },
  plex: { label: "IBM Plex Mono", css: ['"IBM Plex Mono"'], mono: true },
  menlo: { label: "Menlo", css: ["Menlo"], mono: true },
  monaco: { label: "Monaco", css: ["Monaco"], mono: true },
  pingfang: { label: "苹方", css: ['"PingFang SC"'], cjk: true },
  hiragino: { label: "冬青黑体", css: ['"Hiragino Sans GB"'], cjk: true },
  hansans: {
    label: "思源黑体",
    css: ['"Source Han Sans CN"', '"Noto Sans CJK SC"'],
    cjk: true,
  },
  heiti: { label: "黑体", css: ['"Heiti SC"'], cjk: true },
  yahei: { label: "微软雅黑", css: ['"Microsoft YaHei"'], cjk: true },
};

const SYSTEM_SANS = [
  "-apple-system",
  "BlinkMacSystemFont",
  '"SF Pro Text"',
];
const SYSTEM_MONO = ['"SF Mono"', "Menlo"];

/** The family name to probe for, so the picker never offers an absent face. */
const PROBE_NAME: Record<string, string> = {
  inter: "Inter",
  helvetica: "Helvetica Neue",
  jetbrains: "JetBrains Mono",
  fira: "Fira Code",
  plex: "IBM Plex Mono",
  menlo: "Menlo",
  monaco: "Monaco",
  pingfang: "PingFang SC",
  hiragino: "Hiragino Sans GB",
  hansans: "Source Han Sans CN",
  heiti: "Heiti SC",
  yahei: "Microsoft YaHei",
};

/** Width-probe font detection: a missing family falls back and measures the
 *  same as the generic it was paired with. Glint filters its list the same
 *  way, because a silently substituted font looks like a broken setting. */
export function detectInstalledFonts(): Record<string, boolean> {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const found: Record<string, boolean> = {};
  if (!context) return found;
  const sample = "MMS 多模型 0123 mmmiiilll";
  const baselines: Record<string, number> = {};
  for (const generic of ["monospace", "sans-serif", "serif"]) {
    context.font = `72px ${generic}`;
    baselines[generic] = context.measureText(sample).width;
  }
  for (const [key, family] of Object.entries(PROBE_NAME)) {
    found[key] = Object.entries(baselines).some(([generic, width]) => {
      context.font = `72px "${family}", ${generic}`;
      return Math.abs(context.measureText(sample).width - width) > 0.5;
    });
  }
  return found;
}

function withFallback(head: string[], cjk: string, generic: string) {
  const tail = FONT_FAMILIES[cjk]?.css || [];
  return [...head, ...tail, generic].join(", ");
}

export function fontStack(family: string, cjk: string) {
  if (family === "system_ui") return withFallback(["system-ui"], cjk, "sans-serif");
  const entry = FONT_FAMILIES[family];
  const head = entry ? [...entry.css, ...SYSTEM_SANS] : SYSTEM_SANS;
  return withFallback(head, cjk, "sans-serif");
}

export function monoStack(mono: string, cjk: string) {
  const entry = FONT_FAMILIES[mono];
  const head = entry ? [...entry.css, ...SYSTEM_MONO] : SYSTEM_MONO;
  return withFallback(head, cjk, "monospace");
}

export function clampFontSize(value: unknown) {
  const size = Math.round(Number(value));
  return Number.isFinite(size) ? Math.min(20, Math.max(12, size)) : 14;
}

/** Resolve the "follow system" theme choice against the OS setting. */
export function resolveTheme(choice: string): "light" | "dark" {
  if (choice === "light" || choice === "dark") return choice;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function App() {
  const [data, setData] = useState<Bootstrap>(empty);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [statusesStale, setStatusesStale] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState<Page>("new");
  const [guideOpen, setGuideOpen] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<{ available: boolean; active: boolean }>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const setupPrompted = useRef(false);
  const modelReady = data.presets.some(p => p.available);
  const [guideStep, setGuideStep] = useState<TourStep | null>(null);
  const [guideSettingsKey, setGuideSettingsKey] = useState(0);
  const [guideRequest, setGuideRequest] = useState<{ nonce: string; text: string }>();
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [workspaceId, setWorkspaceId] = useState(() =>
    readSetting("mms-web-workspace", ""),
  );
  const [recipe, setRecipe] = useState<RecipeDraft | null>(readRecipeDraft);
  const [recipeConfirmed, setRecipeConfirmed] = useState("");
  const recipeContext = useRef({ key: "", revision: 0 });
  useEffect(() => { saveRecipeDraft(recipe); }, [recipe]);
  const [planMode, setPlanMode] = useState(!!recipe?.recipe.planning);
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
  const [workspaceSort, setWorkspaceSort] = useState<"recent" | "manual">(() =>
    readSetting<string>("mms-web-workspace-sort", "recent") === "manual"
      ? "manual"
      : "recent",
  );
  const [workspaceOrder, setWorkspaceOrder] = useState<string[]>(() => {
    const value = readSetting<unknown>("mms-web-workspace-order", []);
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string")
      : [];
  });
  const [workspaceNotice, setWorkspaceNotice] = useState("");
  const [renameSession, setRenameSession] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [shownPerWorkspace, setShownPerWorkspace] = useState<
    Record<string, number>
  >({});
  const [renameWorkspace, setRenameWorkspace] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [removeWorkspace, setRemoveWorkspace] = useState<{
    id: string;
    name: string;
    sessions: number;
  } | null>(null);
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
  const [processForced, setProcessForced] = useState<{
    collapsed: boolean;
    revision: number;
  } | null>(null);
  const [processTurns, setProcessTurns] = useState<Record<string, boolean>>({});
  const reportProcessTurn = useCallback((id: string, collapsed: boolean) => {
    setProcessTurns((old) => (old[id] === collapsed ? old : { ...old, [id]: collapsed }));
  }, []);
  const [accent, setAccent] = useState(() => {
    const stored = readSetting<string>("mms-web-accent", "indigo");
    const migrated = stored === "blue" ? "cyan" : stored === "rose" ? "pink" : stored;
    return ["indigo", "cyan", "pink", "orange", "green"].includes(migrated) ? migrated : "indigo";
  });
  const [themeChoice, setThemeChoice] = useState<"light" | "dark" | "system">(
    () => {
      const stored = readSetting<string>("mms-web-theme", "light");
      return stored === "dark" || stored === "system" ? stored : "light";
    },
  );
  const [systemDark, setSystemDark] = useState(
    () => matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const theme =
    themeChoice === "system" ? (systemDark ? "dark" : "light") : themeChoice;
  const [fontFamily, setFontFamily] = useState(() =>
    readSetting("mms-web-font-family", "system"),
  );
  const [monoFont, setMonoFont] = useState(() =>
    readSetting("mms-web-mono-font", "system"),
  );
  const [cjkFont, setCjkFont] = useState(() =>
    readSetting("mms-web-cjk-font", "system"),
  );
  const [installedFonts] = useState(detectInstalledFonts);
  const [fontSize, setFontSize] = useState(() =>
    readSetting("mms-web-font-size", 14),
  );
  const [boldText, setBoldText] = useState(() =>
    readSetting("mms-web-bold-text", false),
  );
  const [selectToCopy, setSelectToCopy] = useState(() =>
    readSetting("mms-web-select-to-copy", false),
  );
  const [showCliSessions, setShowCliSessions] = useState(() =>
    readSetting("mms-web-cli-sessions", false),
  );
  const [favorites, setFavorites] = useState<string[]>(() => {
    const value = readSetting<unknown>("mms-web-favorites", []);
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string")
      : [];
  });
  // Told to the API layer before anything reads a list, and reloaded right
  // after, so turning it off empties the list immediately.
  useEffect(() => {
    saveSetting("mms-web-cli-sessions", showCliSessions);
    includeCliSessions(showCliSessions);
    void load();
  }, [showCliSessions]);
  useEffect(() => { saveSetting("mms-web-auto-collapse-process", autoCollapseProcess); }, [autoCollapseProcess]);
  useEffect(() => { saveSetting("mms-web-workspace-sort", workspaceSort); }, [workspaceSort]);
  useEffect(() => { saveSetting("mms-web-workspace-order", workspaceOrder); }, [workspaceOrder]);
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
    if (loading || !connected || setupPrompted.current) return;
    setupPrompted.current = true;
    if (data.presets.some(p => p.available)) return;
    // Empty installs go straight to the actionable form. Existing/broken
    // channels keep their settings, rather than asking for a duplicate account.
    if (!data.services.length && data.capabilities.configure) setSetupOpen(true);
    else setSettingsOpen(true);
  }, [loading, connected, data]);
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
    saveSetting("mms-web-select-to-copy", selectToCopy);
    if (!selectToCopy) return;
    // Copy on mouseup: that event is a user gesture, which is what the
    // clipboard write needs. Selections made inside a field are left alone,
    // because there the user is usually editing rather than quoting.
    const copy = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) return;
      const endpoints = [selection.anchorNode, selection.focusNode].map((node) =>
        node instanceof Element ? node : (node?.parentElement ?? null),
      );
      const conversation = endpoints[0]?.closest(".conversation-content");
      if (!conversation || endpoints.some((element) =>
        element?.closest(".conversation-content") !== conversation ||
        element?.closest("input, textarea, [contenteditable='true']"),
      )) return;
      const text = selection.toString();
      if (!text.trim()) return;
      void navigator.clipboard?.writeText(text).catch(() => {
        // A browser that refuses the write should not break selecting text.
      });
    };
    document.addEventListener("mouseup", copy);
    return () => document.removeEventListener("mouseup", copy);
  }, [selectToCopy]);
  useEffect(() => {
    // Turn ids are per session; carrying them over would make the toggle lie.
    setProcessForced(null);
    setProcessTurns({});
  }, [selectedId]);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => setSystemDark(media.matches);
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveSetting("mms-web-theme", themeChoice);
  }, [theme, themeChoice]);
  useEffect(() => {
    document.documentElement.dataset.accent = accent;
    saveSetting("mms-web-accent", accent);
  }, [accent]);
  useEffect(() => {
    // The tab icon is the same three-bar mark as the sidebar, drawn in the
    // accent the user picked. A static file would keep showing the old colour.
    const ink = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim();
    if (!ink) return;
    const bar = (x: number, y: number, h: number) =>
      `<rect x="${x}" y="${y}" width="4.5" height="${h}" rx="2.25"/>`;
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
      `<g fill="${ink}" transform="translate(3.7 0) skewX(-13)">` +
      bar(6.25, 4, 24) +
      bar(13.75, 8, 16) +
      bar(21.25, 4, 24) +
      `</g></svg>`;
    let link = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.type = "image/svg+xml";
    link.href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }, [accent, theme]);
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--app-font", fontStack(fontFamily, cjkFont));
    root.style.setProperty("--font-mono", monoStack(monoFont, cjkFont));
    root.style.setProperty("--app-font-size", `${clampFontSize(fontSize)}px`);
    root.style.setProperty("--app-font-weight", boldText ? "600" : "400");
    saveSetting("mms-web-font-family", fontFamily);
    saveSetting("mms-web-mono-font", monoFont);
    saveSetting("mms-web-cjk-font", cjkFont);
    saveSetting("mms-web-font-size", clampFontSize(fontSize));
    saveSetting("mms-web-bold-text", boldText);
  }, [fontFamily, monoFont, cjkFont, fontSize, boldText]);
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
  function navigate(next: Page, after?: () => void) {
    requestNavigation(() => {
    setGuideStep(null);
    setSettingsOpen(next === "models");
    if (next === "models") { setNavOpen(false); after?.(); return; }
    setPage(next);
    if (next !== "session")
      history.replaceState(null, "", location.pathname + location.search);
    setNavOpen(false);
    if (next !== "session") {
      setSelectedId("");
      setDetail(null);
      currentSelection.current = "";
    }
    after?.();
    });
  }
  function beginGuideStep(step: TourStep) {
    requestNavigation(() => {
      setGuideOpen(false);
      if (step !== "artifacts" && step !== "runtime") setPanel(false);
      if (step !== "model" && step !== "effort") {
        document.querySelectorAll<HTMLElement>('.studio-popover:popover-open').forEach(el => el.hidePopover());
      }
      const inSettings = step === "connection" || step === "settings";
      setSettingsOpen(inSettings);
      if (inSettings) setGuideSettingsKey(old => old + 1);
      if (step === "workspace" || step === "compose") {
        setPage("new"); setSelectedId(""); setDetail(null); currentSelection.current = "";
        history.replaceState(null, "", location.pathname + location.search);
      }
      if (step === "artifacts" || step === "runtime") {
        setPanel(true); setPanelTab(step === "artifacts" ? "artifacts" : "runtime");
      }
      setNavOpen(step === "sessions");
      setGuideStep(step);
    });
  }
  function startIntroduction() {
    if (modelReady) { beginGuideStep("welcome"); return; }
    requestNavigation(() => {
      setGuideOpen(false); setGuideStep(null);
      if (!data.services.length && data.capabilities.configure) { setSettingsOpen(false); setSetupOpen(true); }
      else setSettingsOpen(true);
    });
  }
  function connectionCompleted() {
    void load().then(() => beginGuideStep("welcome"));
  }
  function guideNavigate(action: GuideAction) {
    const steps: Record<GuideAction, TourStep> = { settings: "settings", workspace: "workspace", model: "model", compose: "compose", materials: "materials", artifacts: "artifacts", runtime: "runtime" };
    beginGuideStep(steps[action]);
  }
  function guideExample(text: string) {
    navigate("new", () => {
      setGuideRequest({ nonce: crypto.randomUUID(), text });
      setGuideStep("compose");
    });
  }
  useEffect(() => {
    if (guideStep === "send" && page === "session" && detail) setGuideStep("reply");
  }, [guideStep, page, detail?.session.id]);
  function openSession(id: string) {
    requestNavigation(() => {
    setGuideStep(null);
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
    targetId?: string,
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
        if (guideStep === "send") setGuideStep("reply");
        setDetail(result);
      } else if (
      currentSelection.current === originId &&
      (!targetId || targetId === originId)
    )
      setDetail(result);
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
  const recipeKey = recipe ? [recipe.key, workspaceId, presetId, JSON.stringify(launchFacts.facts?.model)].join("|") : "";
  if (recipeContext.current.key !== recipeKey) recipeContext.current = { key: recipeKey, revision: recipeContext.current.revision + 1 };
  const recipeToken = `${recipeKey}|${recipeContext.current.revision}`;
  const recipeIssues = recipe ? modelRequirementIssues(recipe.recipe, launchFacts.facts?.model) : [];
  const recipeReady = !recipe || (!recipeIssues.length && recipeConfirmed === recipeToken);
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
  const lastEdited = new Map<string, string>();
  for (const session of data.sessions) {
    const seen = lastEdited.get(session.workspaceId) || "";
    if (session.updatedAt > seen)
      lastEdited.set(session.workspaceId, session.updatedAt);
  }
  navWorkspaces.sort((a, b) => {
    if (workspaceSort === "manual") {
      // Unordered folders keep their registration order behind ordered ones.
      const ai = workspaceOrder.indexOf(a.id);
      const bi = workspaceOrder.indexOf(b.id);
      if (ai !== bi) return (ai < 0 ? Infinity : ai) - (bi < 0 ? Infinity : bi);
      return 0;
    }
    return (lastEdited.get(b.id) || "").localeCompare(lastEdited.get(a.id) || "");
  });
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
  function setAllCollapsed(next: boolean) {
    const ids = next ? navWorkspaces.map((w) => w.id) : [];
    setCollapsed(ids);
    saveSetting("mms-web-collapsed", ids);
  }
  function moveWorkspace(id: string, delta: number) {
    // Manual order is per-browser, like the collapse state. Seed it from what
    // is on screen so the first move does not reshuffle everything else.
    const order = navWorkspaces.map((w) => w.id);
    const from = order.indexOf(id);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= order.length) return;
    order.splice(to, 0, ...order.splice(from, 1));
    setWorkspaceOrder(order);
    setWorkspaceSort("manual");
  }
  async function copyWorkspacePath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      setWorkspaceNotice("已复制路径");
    } catch {
      setWorkspaceNotice("浏览器拒绝了复制，请手动选择路径");
    }
  }
  async function copySessionId(id: string) {
    try {
      await navigator.clipboard.writeText(id);
      setWorkspaceNotice("已复制 Session ID");
    } catch {
      setWorkspaceNotice("浏览器拒绝了复制，请手动选择 ID");
    }
  }
  async function exportSession(id: string) {
    // The sidebar only holds summaries; the export needs the full transcript.
    try {
      exportConversation(await getSession(id));
    } catch (error) {
      setWorkspaceNotice(
        error instanceof Error ? error.message : "导出失败，请打开会话后重试",
      );
    }
  }
  async function submitSessionRename() {
    if (!renameSession) return;
    const title = renameSession.title.trim();
    if (!title) return;
    if (
      await runAction(
        `/sessions/${renameSession.id}/manage`,
        { title },
        false,
        renameSession.id,
      )
    )
      setRenameSession(null);
  }
  async function submitWorkspaceRename() {
    if (!renameWorkspace) return;
    const name = renameWorkspace.name.trim();
    if (!name) return;
    try {
      await mutate("/workspaces/rename", { id: renameWorkspace.id, name });
      setRenameWorkspace(null);
      await load();
    } catch (error) {
      setWorkspaceNotice(error instanceof Error ? error.message : "重命名失败");
    }
  }
  async function submitWorkspaceRemove() {
    if (!removeWorkspace) return;
    try {
      await mutate("/workspaces/remove", { id: removeWorkspace.id });
      setRemoveWorkspace(null);
      await load();
    } catch (error) {
      setWorkspaceNotice(error instanceof Error ? error.message : "移除失败");
    }
  }
  const signals = useSessionAttention(
    data.sessions,
    detail,
    page === "session" && atBottom && !sessionError,
    connected && !statusesStale,
  );
  const tour = guideStep && modelReady && !setupOpen ? <GuidedTour step={guideStep} move={beginGuideStep} close={() => setGuideStep(null)} help={() => requestNavigation(() => { setSettingsOpen(false); setGuideStep(null); setGuideOpen(true); })} example={guideExample} modelReady={data.presets.some(p => p.available)} configure={!!data.capabilities.configure} hasSession={page === "session" && !!detail} /> : null;
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
          aria-label="MMS Pilot 首页"
        >
          <Logo />
          <div className="brand-wordmark">
            <span className="brand-mms">MMS</span>
            <span className="brand-pilot">PILOT</span>
          </div>
          <AppVersion version={data.appVersion} />
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
            <div className="workspace-tools">
              <button
                type="button"
                className="icon-button"
                aria-label={
                  collapsed.length >= navWorkspaces.length
                    ? "展开全部工作区"
                    : "收起全部工作区"
                }
                title={
                  collapsed.length >= navWorkspaces.length
                    ? "展开全部"
                    : "收起全部"
                }
                onClick={() =>
                  setAllCollapsed(collapsed.length < navWorkspaces.length)
                }
              >
                {collapsed.length >= navWorkspaces.length ? (
                  <ChevronsUpDown size={14} />
                ) : (
                  <ChevronsDownUp size={14} />
                )}
              </button>
              <Popover
                title="工作区排序"
                className="icon-button"
                label={<MoreHorizontal size={15} />}
              >
                {(close) => (
                  <>
                    <header>
                      <strong>工作区排序</strong>
                    </header>
                    {(
                      [
                        ["manual", "手动排序", "在文件夹菜单里用上移下移调整"],
                        ["recent", "按最后编辑时间", "最近有新消息的排在前面"],
                      ] as const
                    ).map(([mode, label, description]) => (
                      <button
                        type="button"
                        key={mode}
                        className={
                          "filter-option " +
                          (workspaceSort === mode ? "selected" : "")
                        }
                        onClick={() => {
                          setWorkspaceSort(mode);
                          close();
                        }}
                      >
                        <span>
                          <strong>{label}</strong>
                          <small>{description}</small>
                        </span>
                        {workspaceSort === mode && <Check size={14} />}
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
          </div>
          {workspaceNotice && (
            <p className="workspace-notice" role="status">
              {workspaceNotice}
            </p>
          )}
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
                  <div className="workspace-row-actions">
                    <Popover
                      title={`${w.name} 的操作`}
                      className="icon-button"
                      label={<MoreHorizontal size={14} />}
                    >
                      {(close) => (
                        <>
                          <header>
                            <strong>{w.id === "default" ? "启动目录" : w.name}</strong>
                          </header>
                          <button
                            type="button"
                            className="filter-option"
                            disabled={!w.path}
                            onClick={() => {
                              copyWorkspacePath(w.path);
                              close();
                            }}
                          >
                            <Copy size={14} />
                            <span>
                              <strong>复制路径</strong>
                              <small>{w.path || "这些会话的目录已不在记录里"}</small>
                            </span>
                          </button>
                          {workspaceSort === "manual" && (
                            <>
                              <button
                                type="button"
                                className="filter-option"
                                onClick={() => {
                                  moveWorkspace(w.id, -1);
                                  close();
                                }}
                              >
                                <ArrowUp size={14} />
                                <span>
                                  <strong>上移</strong>
                                </span>
                              </button>
                              <button
                                type="button"
                                className="filter-option"
                                onClick={() => {
                                  moveWorkspace(w.id, 1);
                                  close();
                                }}
                              >
                                <ArrowDown size={14} />
                                <span>
                                  <strong>下移</strong>
                                </span>
                              </button>
                            </>
                          )}
                          <button
                            type="button"
                            className="filter-option"
                            disabled={w.id === "default" || !w.path}
                            onClick={() => {
                              setRenameWorkspace({ id: w.id, name: w.name });
                              close();
                            }}
                          >
                            <Pencil size={14} />
                            <span>
                              <strong>重命名</strong>
                              <small>只改这里显示的名称，不动文件夹</small>
                            </span>
                          </button>
                          <button
                            type="button"
                            className="filter-option danger"
                            disabled={w.id === "default" || !w.path}
                            onClick={() => {
                              setRemoveWorkspace({
                                id: w.id,
                                name: w.name,
                                sessions: sessions.length,
                              });
                              close();
                            }}
                          >
                            <Trash2 size={14} />
                            <span>
                              <strong>移除工作区</strong>
                              <small>
                                {w.id === "default"
                                  ? "启动目录不能移除"
                                  : "只从侧栏移除，文件和会话都保留"}
                              </small>
                            </span>
                          </button>
                        </>
                      )}
                    </Popover>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`在 ${w.name} 新建会话`}
                      title="在这个目录新建会话"
                      disabled={!w.path}
                      onClick={() => {
                        setWorkspaceId(w.id);
                        navigate("new");
                      }}
                    >
                      <MessageSquarePlus size={14} />
                    </button>
                  </div>
                  {!collapsed.includes(w.id) &&
                    sessions.slice(0, shownPerWorkspace[w.id] ?? 8).map((s) => (
                      <div className="session-row" key={s.id}>
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
                            {s.owner === "cli" && <span>终端 ·</span>}
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
                      <Popover
                        title={`${s.title} 的操作`}
                        className="icon-button session-row-menu"
                        label={<MoreHorizontal size={14} />}
                      >
                        {(close) => (
                          <>
                            <button
                              type="button"
                              className="filter-option"
                              onClick={() => {
                                void copySessionId(s.id);
                                close();
                              }}
                            >
                              <Copy size={14} />
                              <span>
                                <strong>复制 Session ID</strong>
                              </span>
                            </button>
                            <button
                              type="button"
                              className="filter-option"
                              onClick={() => {
                                setRenameSession({ id: s.id, title: s.title });
                                close();
                              }}
                            >
                              <Pencil size={14} />
                              <span>
                                <strong>重命名</strong>
                              </span>
                            </button>
                            <button
                              type="button"
                              className="filter-option"
                              disabled={
                                busy ||
                                ["running", "waiting"].includes(s.state)
                              }
                              onClick={() => {
                                void runAction(
                                  `/sessions/${s.id}/fork`,
                                  {},
                                  true,
                                );
                                close();
                              }}
                            >
                              <GitBranch size={14} />
                              <span>
                                <strong>分叉会话</strong>
                                <small>
                                  {["running", "waiting"].includes(s.state)
                                    ? "执行中不能分叉"
                                    : "复制到新会话继续，原会话不变"}
                                </small>
                              </span>
                            </button>
                            <button
                              type="button"
                              className="filter-option"
                              onClick={() => {
                                void exportSession(s.id);
                                close();
                              }}
                            >
                              <Download size={14} />
                              <span>
                                <strong>导出会话</strong>
                              </span>
                            </button>
                            <button
                              type="button"
                              className="filter-option danger"
                              disabled={
                                busy ||
                                ["running", "waiting"].includes(s.state)
                              }
                              onClick={() => {
                                void runAction(
                                  `/sessions/${s.id}/manage`,
                                  { archived: !s.archived },
                                  false,
                                  s.id,
                                );
                                close();
                              }}
                            >
                              <Archive size={14} />
                              <span>
                                <strong>
                                  {s.archived ? "恢复到列表" : "归档"}
                                </strong>
                                <small>
                                  {["running", "waiting"].includes(s.state)
                                    ? "执行中不能归档"
                                    : "从列表收起，内容保留"}
                                </small>
                              </span>
                            </button>
                            <p className="session-row-time">
                              {new Date(s.updatedAt).toLocaleString()}
                            </p>
                          </>
                        )}
                      </Popover>
                      </div>
                    ))}
                  {!collapsed.includes(w.id) &&
                    sessions.length > (shownPerWorkspace[w.id] ?? 8) && (
                      <button
                        type="button"
                        className="load-more-sessions"
                        onClick={() =>
                          setShownPerWorkspace((old) => ({
                            ...old,
                            [w.id]: (old[w.id] ?? 8) + 20,
                          }))
                        }
                      >
                        加载更多 {sessions.length - (shownPerWorkspace[w.id] ?? 8)} 个对话
                      </button>
                    )}
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
          <button
            className={
              "settings-entry" + (updateStatus?.available ? " has-update" : "")
            }
            title={updateStatus?.available ? "设置 · 有新版可用" : "设置"}
            onClick={() => navigate("models")}
          >
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
            <UpdateCenter ready={!loading && connected} open={updateOpen} setOpen={setUpdateOpen} onStatus={setUpdateStatus} />
            <HelpGuide ready={!loading && connected && modelReady && !setupOpen && !settingsOpen} modelReady={modelReady} open={guideOpen} setOpen={(open) => { if (open) setGuideStep(null); setGuideOpen(open); }} hasSession={page === "session" && !!detail} navigate={guideNavigate} startTour={startIntroduction} startConnection={data.capabilities.configure ? () => requestNavigation(() => { setGuideOpen(false); setGuideStep(null); setSettingsOpen(false); setSetupOpen(true); }) : undefined} />
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
        {!settingsOpen && tour}
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
                {!isPreview && workspaceId && <ProjectMaterials key={workspaceId} workspaceId={workspaceId} />}
                <RecipeImport
                  loaded={(item) => {
                    setRecipe(item); setRecipeConfirmed("");
                    setPlanMode(item.recipe.planning);
                  }}
                />
              </div>
              {recipe && <section className="recipe-loaded">
                <strong>已载入「{recipe.recipe.title}」</strong>
                <p>模板模型偏好：{recipe.recipe.preferredModel || "未指定"}。当前使用 {preset?.name || "尚未选择"} · {preset?.channel || ""}；确认后再发送。</p>
                <p>必需 Skills：{recipe.recipe.requiredSkills.join("、") || "无"}。文件与变量由本次草稿提供。</p>
                {recipeIssues.map(issue => <p role="status" key={issue}>{issue}</p>)}
                {recipeReady ? <p role="status">已确认当前模型与工作文件夹。</p> : <button type="button" disabled={!!recipeIssues.length || !preset?.available || !connected} onClick={() => setRecipeConfirmed(recipeToken)}>确认使用当前模型</button>}
                <button type="button" onClick={() => { setRecipe(null); setRecipeConfirmed(""); }}>退出模板草稿</button>
              </section>}
              <Composer
                key={`new:${workspaceId}:${recipe?.key || ""}`}
                draftKey={`new:${workspaceId}:${recipe?.key || ""}`}
                initialText={recipe?.draftPrompt}
                requiredSkillNames={recipe?.recipe.requiredSkills}
                guideRequest={guideRequest}
                guideHandled={() => setGuideRequest(undefined)}
                workspaceId={workspaceId}
                disabled={
                  !connected ||
                  !recipeReady ||
                  !data.capabilities.launch ||
                  !launchFacts.facts ||
                  !presetId ||
                  !workspaceId
                }
                reason={
                  !connected
                    ? "连接 MMS 本地服务后即可开始。"
                    : !recipeReady ? "请先核对模板需求并确认当前模型。" : "请选择可用模型和工作文件夹后开始。"
                }
                busy={busy}
                placeholder="想做什么？"
                send={async (text, extras) => {
                  if (!recipeReady) return false;
                  const revision = recipeContext.current.revision;
                  if (recipe) {
                    const [facts, found] = await Promise.all([
                      request<LaunchFacts>("/launch-options", { presetId, workspaceId }),
                      request<{ skills: Skill[] }>("/skills", { workspaceId }),
                    ]);
                    if (recipeContext.current.revision !== revision) throw new Error("工作文件夹或模型已经变化，请重新检查后发送。");
                    const issues = [...modelRequirementIssues(recipe.recipe, facts.model), ...requiredSkillMatches(recipe.recipe.requiredSkills, found.skills, extras.skills).issues];
                    if (issues.length) throw new Error(issues.join(" "));
                  }
                  const ok = await runAction("/sessions", {
                    workspaceId, presetId, title: text.length > 42 ? text.slice(0, 42) + "…" : text, prompt: text,
                    planMode, thinkingLevel: effort || undefined, ...extras,
                    ...(recipe ? { recipeRequirements: { ...recipe.recipe.modelRequirements, skills: recipe.recipe.requiredSkills } } : {}),
                  }, true);
                  if (ok && recipe) { setRecipe(null); setRecipeConfirmed(""); }
                  return ok;
                }}
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
              {!modelReady && (
                <div className="setup-inline">
                  <Settings2 size={19} />
                  <div>
                    <strong>{data.services.length ? "检查模型连接" : "先连接一个模型服务"}</strong>
                    <p>{data.services.length ? "已有通道暂时不可用，可以在设置中查看原因。" : "填入服务地址和密钥，我们会带你完成其余步骤。"}</p>
                  </div>
                  <button className="button primary" onClick={startIntroduction}>
                    {data.services.length ? "检查设置" : "开始配置"}
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
                        <span
                          className="recent-icon"
                          style={{ background: vendorTint(undefined, s.modelName) }}
                        >
                          {s.state === "waiting" ? (
                            <CircleAlert size={19} />
                          ) : (
                            <VendorMark name={s.modelName} size={19} />
                          )}
                        </span>
                        <span className="recent-copy">
                          <strong>{s.title}</strong>
                          <small>
                            {s.summary ||
                              (s.owner === "cli" ? "终端 · " : "") +
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
        {setupOpen && <ConnectionDialog data={data} onboarding
          close={() => setSetupOpen(false)} refresh={() => void load()} select={selectTaskPreset}
          complete={connectionCompleted} />}
        {settingsOpen && (
          <SettingsPage
            key={guideSettingsKey}
            openUpdates={() => setUpdateOpen(true)}
            showCliSessions={showCliSessions}
            setShowCliSessions={setShowCliSessions}
            updateAvailable={!!updateStatus?.available}
            connectionCompleted={connectionCompleted}
            tour={tour}
            requestNavigation={requestNavigation}
            editStateChanged={setSettingsEdit}
            autoCollapseProcess={autoCollapseProcess}
            setAutoCollapseProcess={setAutoCollapseProcess}
            fontFamily={fontFamily}
            setFontFamily={setFontFamily}
            monoFont={monoFont}
            setMonoFont={setMonoFont}
            cjkFont={cjkFont}
            setCjkFont={setCjkFont}
            installedFonts={installedFonts}
            fontSize={clampFontSize(fontSize)}
            setFontSize={setFontSize}
            boldText={boldText}
            setBoldText={setBoldText}
            selectToCopy={selectToCopy}
            setSelectToCopy={setSelectToCopy}
            presetId={presetId}
            selectPreset={selectTaskPreset}
            workspaceId={workspaceId}
            effortChanged={(id) => {
              if (id === presetId) setEffortChoice({ id: "", level: "" });
            }}
            themeChoice={themeChoice}
            setThemeChoice={setThemeChoice}
            accent={accent}
            setAccent={setAccent}
            back={() => { setSettingsOpen(false); setGuideStep(null); }}
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
                      {detail.session.owner === "cli" && (
                        // Say it before the transcript, not after: someone
                        // scrolling a long session should not have to reach
                        // the composer to find out it cannot be used.
                        <p className="session-readonly" role="status">
                          这个会话是在终端里用 <code>mmf</code> 开始的，这里只读。
                          要继续，请回到那个终端。
                        </p>
                      )}
                      <Transcript
                        key={detail.session.id}
                        forced={processForced}
                        report={reportProcessTurn}
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
                      className="workbar-folder"
                      title={`浏览文件和 Git 变更：${detail.session.cwd || "当前工作文件夹"}`}
                      aria-label={`浏览 ${detail.session.cwd?.split("/").pop() || "当前项目"} 的文件和变更`}
                      aria-haspopup="dialog"
                      onClick={() => setFilesOpen(true)}
                    >
                      <FolderOpen size={14} />
                      <span>文件</span>
                      <span className="workbar-folder-name">{detail.session.cwd?.split("/").pop() || "当前项目"}</span>
                    </button>
                    {!isPreview && <ProjectMaterials key={detail.session.workspaceId} workspaceId={detail.session.workspaceId} />}
                    {detail.events.some((e) => e.kind === "tool" || e.thinking) &&
                      (() => {
                        // Anything still open means the useful action is to close it.
                        const collapseNext = Object.values(processTurns).some(
                          (collapsed) => !collapsed,
                        );
                        return (
                          <button
                            className="process-toggle-all"
                            aria-expanded={collapseNext}
                            onClick={() =>
                              setProcessForced({
                                collapsed: collapseNext,
                                revision: (processForced?.revision || 0) + 1,
                              })
                            }
                          >
                            {collapseNext ? (
                              <ChevronsDownUp size={14} />
                            ) : (
                              <ChevronsUpDown size={14} />
                            )}
                            {collapseNext ? "收起全部过程" : "展开全部过程"}
                          </button>
                        );
                      })()}
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
      {renameSession && (
        <Dialog title="重命名会话" close={() => setRenameSession(null)}>
          <form
            className="workspace-form"
            onSubmit={(e) => {
              e.preventDefault();
              void submitSessionRename();
            }}
          >
            <label>
              会话名称
              <input
                autoFocus
                aria-label="会话名称"
                value={renameSession.title}
                maxLength={100}
                autoComplete="off"
                onChange={(e) =>
                  setRenameSession({
                    ...renameSession,
                    title: e.target.value,
                  })
                }
              />
            </label>
            <button
              type="submit"
              className="button primary"
              disabled={busy || !renameSession.title.trim()}
            >
              保存
            </button>
          </form>
        </Dialog>
      )}
      {renameWorkspace && (
        <Dialog title="重命名工作区" close={() => setRenameWorkspace(null)}>
          <p className="dialog-intro">
            只改侧栏显示的名称，电脑上的文件夹不变。
          </p>
          <form
            className="workspace-form"
            onSubmit={(e) => {
              e.preventDefault();
              void submitWorkspaceRename();
            }}
          >
            <label>
              工作区名称
              <input
                autoFocus
                aria-label="工作区名称"
                value={renameWorkspace.name}
                maxLength={120}
                autoComplete="off"
                onChange={(e) =>
                  setRenameWorkspace({
                    ...renameWorkspace,
                    name: e.target.value,
                  })
                }
              />
            </label>
            <button
              type="submit"
              className="button primary"
              disabled={!renameWorkspace.name.trim()}
            >
              保存
            </button>
          </form>
        </Dialog>
      )}
      {removeWorkspace && (
        <Dialog title="移除工作区" close={() => setRemoveWorkspace(null)}>
          <p className="dialog-intro">
            把「{removeWorkspace.name}」从侧栏移除。文件夹和里面的文件都不会被删除。
          </p>
          {removeWorkspace.sessions > 0 && (
            <p className="muted">
              这里的 {removeWorkspace.sessions} 个会话会移到「其他工作空间」分组，
              仍然可以打开和搜索。
            </p>
          )}
          <div className="workspace-form">
            <button
              type="button"
              className="button primary"
              onClick={() => void submitWorkspaceRemove()}
            >
              移除
            </button>
            <button
              type="button"
              className="button"
              onClick={() => setRemoveWorkspace(null)}
            >
              取消
            </button>
          </div>
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
                    {s.owner === "cli" ? "终端 · " : ""}
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
