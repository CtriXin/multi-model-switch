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

type Step = "connection" | "models" | "preview" | "saved";
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
}: {
  data: Bootstrap;
  close: () => void;
  refresh: () => void;
  select: (id: string) => void;
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
    name,
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
      setStep(step === "preview" ? "models" : "connection");
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
      setChosen(chosen.filter((m) => result.models.includes(m)));
      setManual(false);
      setListed(true);
      setStep("models");
    } catch (e) {
      if (!controller.signal.aborted) {
        setError((e as Error).message);
        setStep("models");
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
      title="连接模型服务"
      close={() => void dismiss()}
      dismissible={!busy || busy === "discover"}
    >
      <div className="connection-flow" aria-busy={!!busy}>
        <ol className="connection-steps" aria-label="连接进度">
          {["连接服务", "选择模型", "确认保存"].map((label, i) => {
            const current =
              step === "connection" ? 0 : step === "models" ? 1 : 2;
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
            ? "用你已经在用的服务"
            : step === "models"
              ? "只留下你会用的模型"
              : step === "preview"
                ? "这些内容将被保存"
                : "通道已保存"}
        </h3>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        {step === "connection" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (protocol === "anthropic" || !discovered) startManual();
              else void discover();
            }}
          >
            <fieldset disabled={!!busy} className="connection-fields">
              <label className="field">
                通道名称
                <input
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：个人账号、公司网关"
                  autoComplete="off"
                />
                <small>同一个模型通过不同服务连接时，用这个名称区分。</small>
              </label>
              <label className="field">
                接口类型
                <select
                  value={protocol}
                  onChange={(e) => {
                    setProtocol(e.target.value);
                    setListed(false);
                    setModels([]);
                    setChosen([]);
                  }}
                >
                  <option value="openai">OpenAI 兼容</option>
                  <option value="anthropic">Anthropic 兼容</option>
                  <option value="dual">双协议网关</option>
                </select>
              </label>
              <label className="field">
                API 地址
                <input
                  required
                  type="url"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setListed(false);
                    setModels([]);
                    setChosen([]);
                  }}
                  placeholder="https://api.example.com/v1"
                  autoComplete="off"
                  spellCheck={false}
                />
                <small>按服务提供的地址填写，包括它要求的 /v1 等路径。</small>
              </label>
              <label className="field">
                API Key
                <input
                  required
                  type="password"
                  value={key}
                  onChange={(e) => {
                    setKey(e.target.value);
                    setListed(false);
                    setModels([]);
                    setChosen([]);
                  }}
                  placeholder="粘贴服务提供的密钥"
                  autoComplete="new-password"
                  spellCheck={false}
                />
              </label>
              {protocol === "dual" && (
                <p className="connection-note">
                  此入口适用于两种协议共用同一个 API 地址与 Key
                  的网关；不同地址的通道请在 MMF Config Web 中设置。
                </p>
              )}
              {protocol !== "anthropic" && discovered && (
                <p className="connection-endpoint">
                  将读取{" "}
                  <code>
                    {url.trim().replace(/\/+$/, "") || "API 地址"}/models
                  </code>
                </p>
              )}
              <button className="button primary full" type="submit">
                {busy === "discover" ? (
                  <>
                    <LoaderCircle size={15} className="connection-spinner" />
                    正在读取模型…
                  </>
                ) : (
                  <>
                    {protocol === "anthropic" || !discovered
                      ? "填写模型名称"
                      : "读取可用模型"}
                    <ArrowRight size={15} />
                  </>
                )}
              </button>
              {protocol !== "anthropic" && discovered && (
                <button
                  className="connection-text-button full"
                  type="button"
                  onClick={(e) => {
                    if (e.currentTarget.form?.reportValidity()) startManual();
                  }}
                >
                  我知道模型名称，手动填写
                </button>
              )}
            </fieldset>
          </form>
        )}
        {step === "models" && (
          <>
            <p className="connection-route">
              <strong>{name}</strong>
              <span>{url}</span>
            </p>
            {!manual && (
              <>
                {listed && (
                  <p className="connection-note">
                    已读取 {models.length}{" "}
                    个模型。读取列表不代表已验证对话、图片或 Thinking 能力。
                  </p>
                )}
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
                  自动去重。模型能力会在保存后按 MMS 的启动设置读取。
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
                  : `预览 ${selectedModels.length} 个模型`}
                <ArrowRight size={14} />
              </button>
            </div>
          </>
        )}
        {step === "preview" && preview && (
          <>
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
                  "保存通道"
                )}
              </button>
            </div>
          </>
        )}
        {step === "saved" && saved && (
          <ConnectionReady
            saved={saved}
            name={name}
            models={selectedModels}
            workspaceId={data.workspaces[0]?.id || "default"}
            done={(id) => {
              if (id) select(id);
              close();
            }}
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
}: {
  saved: Saved;
  name: string;
  models: string[];
  workspaceId: string;
  done: (id?: string) => void;
}) {
  const [selected, setSelected] = useState(
    saved.presetIds?.find((id) => id.startsWith("web:pi:")) || "",
  );
  const { facts, error } = useLaunchFacts(selected, workspaceId);
  const [effort, setEffort] = useState("");
  return (
    <>
      <p className="connection-note">
        {name} · {models.length}{" "}
        个模型。现在可以检查默认参数，对话在你发送任务时开始。
      </p>
      {selected ? (
        <>
          <label className="field">
            查看模型
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
          <div className="connection-effort">
            <span>默认思考强度</span>
            {facts ? (
              <EffortSelect
                facts={facts}
                value={effort}
                change={(v) => {
                  setEffort(v);
                  saveRoutePreference(selected, { effort: v });
                }}
              />
            ) : (
              <span className="muted" role="status">
                {error || "正在读取启动参数…"}
              </span>
            )}
          </div>
          <p className="connection-note">
            默认沿用 MMS
            的设置。在这里调整会记住当前浏览器对这条模型通道的偏好；其他通道和
            MMF 全局预设不变。
          </p>
          {facts && (
            <p className="connection-note">
              当前有效值：{effort || facts.defaultThinkingLevel}
              {facts.configuredThinkingLevel !== facts.defaultThinkingLevel &&
                `（MMS 配置为 ${facts.configuredThinkingLevel}，适配器调整为受支持的等级）`}
            </p>
          )}
        </>
      ) : (
        <p className="inline-alert">
          配置已保存，但当前模型目录还没有可启动的通道。请在 MMF Config Web
          中完成目录更新，再刷新本页。
        </p>
      )}
      <button
        className="button primary full"
        onClick={() => done(selected || undefined)}
      >
        {selected ? "完成，查看这条通道" : "完成"}
        <ArrowRight size={15} />
      </button>
    </>
  );
}
