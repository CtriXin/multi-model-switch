import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  LoaderCircle,
  Search,
} from "lucide-react";
import type { Bootstrap, ConfigPreview } from "./types";
import { Dialog } from "./components";
import { mutate, request } from "./api";
import {
  EffortSelect,
  saveRoutePreference,
  useLaunchFacts,
} from "./ModelExplorer";

type Step = "connection" | "credentials" | "models" | "preview" | "saved";
type Saved = {
  applied: boolean;
  message: string;
  providerId: string;
  presetIds: string[];
};
const modelNames = (text: string) => [
  ...new Set(
    text
      .split(/[,\n]/)
      .map((m) => m.trim())
      .filter(Boolean),
  ),
];

export function ConnectionDialog({
  data,
  close,
  refresh,
  select,
  onboarding = false,
  complete,
}: {
  data: Bootstrap;
  close: () => void;
  refresh: () => void;
  select: (id: string) => void;
  onboarding?: boolean;
  complete?: () => void;
}) {
  const [step, setStep] = useState<Step>("connection");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [protocol, setProtocol] = useState("openai");
  const [models, setModels] = useState<string[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [manual, setManual] = useState(false);
  const [manualText, setManualText] = useState("");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<ConfigPreview | null>(null);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [listed, setListed] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const enabled = data.capabilities.configure;
  const discovered = data.capabilities.discoverModels;
  const selectedModels = manual ? modelNames(manualText) : chosen;
  const shown = models.filter((m) =>
    m.toLowerCase().includes(query.toLowerCase()),
  );
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);
  const service = () => ({
    name: name.trim() || new URL(url).hostname,
    baseUrl: url.trim().replace(/\/+$/, ""),
    apiKey: key,
    protocol,
    models: selectedModels,
  });

  async function discard() {
    if (preview)
      await request("/configuration/discard", { previewId: preview.previewId });
    setPreview(null);
  }
  async function dismiss() {
    if (busy && busy !== "discover") return;
    abort.current?.abort();
    setBusy("discard");
    try {
      await discard();
      setKey("");
      close();
    } catch (e) {
      setError((e as Error).message);
      setBusy("");
    }
  }
  async function goBack() {
    setBusy("discard");
    setError("");
    try {
      await discard();
      setStep(step === "preview" ? "models" : step === "models" ? "credentials" : "connection");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function discover() {
    setBusy("discover");
    setError("");
    const controller = new AbortController();
    abort.current = controller;
    try {
      const result = await request<{ models: string[] }>(
        "/configuration/discover",
        { service: service() },
        controller.signal,
      );
      setModels(result.models);
      const retained = chosen.filter((m) => result.models.includes(m));
      setChosen(retained.length ? retained : result.models.length === 1 ? result.models : []);
      setManual(false);
      setListed(true);
      setStep("models");
    } catch (e) {
      if (!controller.signal.aborted) {
        setError((e as Error).message);
        // A failed Key/address stays next to the fields that can fix it.
      }
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  async function prepare() {
    setBusy("preview");
    setError("");
    try {
      const result = await mutate<ConfigPreview>("/configuration/preview", {
        service: service(),
      });
      setPreview(result);
      setStep("preview");
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
      const result = await mutate<Saved>("/configuration/apply", {
        previewId: preview.previewId,
        revision: preview.revision,
      });
      if (!result.applied) throw new Error(result.message);
      setKey("");
      setPreview(null);
      setSaved(result);
      setStep("saved");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function startManual() {
    if (!manualText) setManualText(chosen.join("\n"));
    setError("");
    setManual(true);
    setStep("models");
  }
  if (!enabled)
    return (
      <Dialog title="模型配置来源" close={close}>
        <p className="dialog-intro">当前模型和通道来自你已有的 MMF 配置。</p>
        <p className="dialog-description">
          本页可以收藏通道、添加备注，查看 MMS 默认
          effort，并设置当前浏览器的通道偏好。现有通道的接入信息与全局预设继续由
          MMF Config Web 管理。
        </p>
        <p className="dialog-description">
          当前服务只读接入了这份配置，尚未开放在这里保存新通道。
        </p>
        <button type="button" className="button full" onClick={close}>
          知道了
        </button>
      </Dialog>
    );
  return (
    <Dialog
      title={onboarding ? "欢迎使用 Pilot，先连接 AI" : "连接模型服务"}
      close={() => void dismiss()}
      dismissible={!busy || busy === "discover"}
    >
      <div className="connection-flow" aria-busy={!!busy}>
        <ol className="connection-steps" aria-label="连接进度">
          {["服务地址", "连接密钥", "选择模型", "确认保存"].map((label, i) => {
            const current =
              step === "connection" ? 0 : step === "credentials" ? 1 : step === "models" ? 2 : 3;
            return (
              <li
                key={label}
                aria-current={current === i ? "step" : undefined}
                className={i < current || step === "saved" ? "done" : ""}
              >
                <span>
                  {i < current || step === "saved" ? (
                    <Check size={12} />
                  ) : (
                    i + 1
                  )}
                </span>
                {label}
              </li>
            );
          })}
        </ol>
        <h3 ref={heading} tabIndex={-1} className="connection-heading">
          {step === "connection"
            ? "先填入模型服务的地址"
            : step === "credentials"
              ? "再粘贴你的连接密钥"
            : step === "models"
              ? "选一个模型，就能开始"
              : step === "preview"
                ? "确认连接，使用 MMS 模型预设"
                : "通道已保存"}
        </h3>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        {(step === "connection" || step === "credentials") && (
          <form onSubmit={e => {
            e.preventDefault();
            if (busy) return;
            if (step === "connection") {
              if (!name.trim()) {
                const host = new URL(url).hostname;
                let candidate = host, suffix = 2;
                const slug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
                while (data.services.some(s => s.id === slug(candidate) || s.name === candidate)) candidate = `${host} ${suffix++}`;
                setName(candidate);
              }
              setError(""); setStep("credentials");
            }
            else if (protocol === "anthropic" || !discovered) startManual();
            else void discover();
          }}>
            <fieldset disabled={!!busy} className="connection-fields">
              {step === "connection" ? <>
                <p className="connection-note">Pilot 通过模型服务回答问题。把服务商提供的 API 地址粘贴到下面。</p>
                <label className="field">
                  API 地址
                  <input required type="url" value={url}
                    onChange={e => { setUrl(e.target.value.trim()); setListed(false); setModels([]); setChosen([]); }}
                    placeholder="https://api.example.com/v1" autoComplete="off" spellCheck={false} />
                  <small>使用服务商提供的完整地址，保留 /v1 等路径。</small>
                </label>
                <details className="connection-advanced">
                  <summary>服务名称与接口类型（可选）</summary>
                  <label className="field">通道名称<input maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="不填则使用服务地址的名称" autoComplete="off" /></label>
                  <label className="field">接口类型<select value={protocol} onChange={e => { setProtocol(e.target.value); setListed(false); setModels([]); setChosen([]); }}>
                    <option value="openai">OpenAI 兼容</option><option value="anthropic">Anthropic 兼容</option><option value="dual">双协议网关</option>
                  </select><small>按服务商的说明选择；没有特别要求时保留默认值。</small></label>
                  {protocol === "dual" && <p className="connection-note">适用于两种接口共用同一个地址和 Key 的网关。地址不同时，请在通道设置中分别填写。</p>}
                </details>
                <button className="button primary full" type="submit">下一步，填写密钥 <ArrowRight size={15} /></button>
                <button className="connection-text-button full" type="button" onClick={() => void dismiss()}>还没有服务信息，稍后配置</button>
              </> : <>
                <p className="connection-route"><span>{url}</span></p>
                <label className="field">API Key
                  <input required type="password" value={key} onChange={e => { setKey(e.target.value.trim()); setListed(false); setModels([]); setChosen([]); }} placeholder="粘贴服务提供的密钥" autoComplete="new-password" spellCheck={false} />
                  <small>通常可以在服务商网站的「API Key」或「密钥管理」中找到。密钥不会保存到浏览器。</small>
                </label>
                <p className="connection-note">{protocol === "anthropic" || !discovered ? "下一步填写服务商提供的模型名称。" : "下一步检查连接并读取模型列表，不发送付费对话。"}</p>
                <div className="connection-footer">
                  <button className="button" type="button" onClick={() => void goBack()}><ArrowLeft size={14} />修改地址</button>
                  <button className="button primary" type="submit">{busy === "discover" ? <><LoaderCircle size={15} className="connection-spinner" />正在读取模型…</> : <>{protocol === "anthropic" || !discovered ? "下一步，填写模型" : "连接并读取模型"}<ArrowRight size={15} /></>}</button>
                </div>
                {protocol !== "anthropic" && discovered && <button className="connection-text-button full" type="button" onClick={e => { if (e.currentTarget.form?.reportValidity()) startManual(); }}>服务不提供模型列表？手动填写</button>}
              </>}
            </fieldset>
          </form>
        )}
        {step === "models" && (
          <>
            <p className="connection-route">
              <strong>{name.trim() || new URL(url).hostname}</strong>
              <span>{url}</span>
            </p>
            {!manual && (
              <>
                {listed && (
                  <p className="connection-note">
                    已读取 {models.length}{" "}
                    个模型。先勾选一个熟悉的名字，之后随时可以添加。
                  </p>
                )}
                {listed && !models.length && <p className="inline-alert">服务返回了空列表。可以返回检查地址和 Key，或手动填写服务商提供的模型名称。</p>}
                {!!models.length && (
                  <>
                    <label className="picker-search connection-search">
                      <Search size={16} />
                      <input
                        aria-label="筛选服务模型"
                        placeholder="搜索模型名称…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <div className="connection-selection">
                      <span aria-live="polite">已选 {chosen.length} 个</span>
                      <div>
                        <button
                          type="button"
                          disabled={!shown.length}
                          onClick={() =>
                            setChosen([...new Set([...chosen, ...shown])])
                          }
                        >
                          选择{query ? "搜索结果" : "全部"}
                        </button>
                        <button
                          type="button"
                          disabled={!chosen.length}
                          onClick={() => setChosen([])}
                        >
                          清空
                        </button>
                      </div>
                    </div>
                    <div className="connection-models" aria-label="可选模型">
                      {shown.map((m) => (
                        <label key={m}>
                          <input
                            type="checkbox"
                            checked={chosen.includes(m)}
                            onChange={(e) =>
                              setChosen(
                                e.target.checked
                                  ? [...chosen, m]
                                  : chosen.filter((v) => v !== m),
                              )
                            }
                          />
                          <span>{m}</span>
                        </label>
                      ))}
                      {!shown.length && (
                        <p className="connection-note">
                          没有匹配的模型。换个关键词，或手动补充模型名。
                        </p>
                      )}
                    </div>
                  </>
                )}
                <div className="connection-methods">
                  <button
                    type="button"
                    className="connection-text-button"
                    disabled={!!busy}
                    onClick={startManual}
                  >
                    手动填写模型名
                  </button>
                  {discovered && protocol !== "anthropic" && (
                    <button
                      type="button"
                      className="connection-text-button"
                      disabled={!!busy}
                      onClick={() => void discover()}
                    >
                      {busy === "discover" ? "正在读取…" : "重新读取"}
                    </button>
                  )}
                </div>
              </>
            )}
            {manual && (
              <>
                <label className="field">
                  模型名称
                  <textarea
                    autoFocus
                    rows={5}
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    placeholder="每行一个，使用服务提供的完整模型 ID"
                    spellCheck={false}
                  />
                </label>
                <p className="connection-note">
                  已识别 {selectedModels.length} 个模型 ·
                  自动去重。保存后自动读取 MMS 预设，无需手动填写模型参数。
                </p>
                {listed && (
                  <button
                    type="button"
                    className="connection-text-button"
                    onClick={() => {
                      setManual(false);
                      setError("");
                    }}
                  >
                    返回拉取的模型列表
                  </button>
                )}
              </>
            )}
            <div className="connection-footer">
              <button
                className="button"
                disabled={!!busy}
                onClick={() => void goBack()}
              >
                <ArrowLeft size={14} />
                连接信息
              </button>
              <button
                className="button primary"
                disabled={!!busy || !selectedModels.length}
                onClick={() => void prepare()}
              >
                {busy === "preview"
                  ? "正在准备…"
                  : `下一步，确认 ${selectedModels.length} 个模型`}
                <ArrowRight size={14} />
              </button>
            </div>
          </>
        )}
        {step === "preview" && preview && (
          <>
            <p className="connection-note">保存后自动载入 MMS 随版本提供的模型预设，包括思考强度、上下文与识图能力。首次使用先保留预设即可，之后随时能调整。</p>
            <div className="config-changes">
              <div>
                <strong>接口类型</strong>
                <p>
                  {
                    {
                      openai: "OpenAI 兼容",
                      anthropic: "Anthropic 兼容",
                      dual: "双协议网关",
                    }[protocol]
                  }
                </p>
              </div>
              {preview.changes
                .filter(
                  (c) => !["Provider ID", "模型列表模式"].includes(c.label),
                )
                .map((c, i) => (
                  <div key={i}>
                    <strong>
                      {{
                        Service: "通道名称",
                        Name: "通道名称",
                        "Base URL": "API 地址",
                        Models: "启用模型",
                      }[c.label] || c.label}
                    </strong>
                    <p>
                      {c.before && (
                        <>
                          {c.before}
                          <ArrowRight size={12} />
                        </>
                      )}
                      {c.after}
                    </p>
                  </div>
                ))}
            </div>
            {preview.warnings.map((w) => (
              <p className="inline-alert" key={w}>
                {w}
              </p>
            ))}
            <p className="connection-note">
              保存本次选中的模型列表，不会自动加入其他模型。API Key
              不会写入浏览器存储。
            </p>
            <div className="connection-footer">
              <button
                className="button"
                disabled={!!busy}
                onClick={() => void goBack()}
              >
                <ArrowLeft size={14} />
                返回修改
              </button>
              <button
                className="button primary"
                disabled={!!busy}
                onClick={() => void apply()}
              >
                {busy === "apply" ? (
                  <>
                    <LoaderCircle size={15} className="connection-spinner" />
                    正在保存…
                  </>
                ) : (
                  "保存并载入预设"
                )}
              </button>
            </div>
          </>
        )}
        {step === "saved" && saved && (
          <ConnectionReady
            saved={saved}
            name={name.trim() || new URL(url).hostname}
            models={selectedModels}
            workspaceId={data.workspaces[0]?.id || "default"}
            done={(id) => {
              if (id) select(id);
              close();
              if (id) complete?.();
            }}
            onboarding={onboarding}
          />
        )}
      </div>
    </Dialog>
  );
}

function ConnectionReady({
  saved,
  name,
  models,
  workspaceId,
  done,
  onboarding,
}: {
  saved: Saved;
  name: string;
  models: string[];
  workspaceId: string;
  done: (id?: string) => void;
  onboarding: boolean;
}) {
  const [selected, setSelected] = useState(
    saved.presetIds?.find((id) => id.startsWith("web:pi:")) || "",
  );
  const [retry, setRetry] = useState(0);
  const { facts, error } = useLaunchFacts(selected, workspaceId, retry);
  const [effort, setEffort] = useState("");
  return (
    <>
      <p className="connection-note">
        {name} · {models.length}{" "}
        个模型。下一步可以开始对话，对话会在你点击发送后开始。
      </p>
      {selected ? (
        <>
          <label className="field">
            首次对话使用的模型
            <select
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setEffort("");
              }}
            >
              {models
                .map((m) => ({
                  name: m,
                  id: `web:pi:${saved.providerId}:${m}`,
                }))
                .filter((m) => saved.presetIds.includes(m.id))
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} · {name}
                  </option>
                ))}
            </select>
          </label>
          {facts ? <>
            <p className="connection-preset-ready" role="status"><Check size={17} />已载入这个模型的 MMS 预设</p>
            <p className="connection-note">现在可以直接使用。思考强度和模型能力已按当前通道读取，无需逐项填写。</p>
            <details className="connection-advanced"><summary>查看或调整模型参数</summary>
              <p className="connection-note">上下文：{facts.model.contextWindow?.toLocaleString() || "未提供"} tokens · {facts.model.input?.includes("image") ? "可直接读取图片" : "模型不直接读取图片"}</p>
              <div className="connection-effort"><span>这条通道的思考强度</span><EffortSelect facts={facts} value={effort} change={v => { setEffort(v); saveRoutePreference(selected, { effort: v }); }} /></div>
              <p className="connection-note">默认沿用 MMS 预设；这里调整后只记住当前浏览器偏好。列表读取成功不等于对话已测试。</p>
            </details>
          </> : <p className={error ? "form-error" : "connection-note"} role={error ? "alert" : "status"}>{error || "正在载入模型预设…"}{error && <button type="button" className="connection-text-button" onClick={() => setRetry(v => v + 1)}>重新载入预设</button>}</p>}
        </>
      ) : (
        <p className="inline-alert">
          配置已保存，当前还没有可启动的通道。关闭后在设置中查看具体原因；暂时不会进入聊天教程。
        </p>
      )}
      <button
        className="button primary full"
        disabled={!!selected && !facts}
        onClick={() => done(facts ? selected : undefined)}
      >
        {selected ? onboarding ? "开始使用，带我发第一条消息" : "完成，使用这条通道" : "返回设置"}
        <ArrowRight size={15} />
      </button>
    </>
  );
}
