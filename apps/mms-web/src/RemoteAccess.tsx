import { useCallback, useEffect, useState } from "react";
import { Copy, RefreshCw, Wand2, X } from "lucide-react";
import { mutate, request } from "./api";
import { copyText } from "./clipboard";
import { QrCode } from "./QrCode";

interface Way {
  host: string;
  url: string;
  kind: "hostname" | "address";
  detail: string;
  removable?: boolean;
}
interface State {
  mode: "loopback" | "lan" | "all";
  enabled: boolean;
  token: string;
  hostnames: string[];
  savedHostnames: string[];
  links: Way[];
  listening: string[];
  unavailable: Record<string, string>;
  port: number;
}

/** What to hand the agent when someone asks it to set up outside access.
 *
 *  A task, not a page of instructions, because the right answer depends on
 *  what the person already has, and most people have nothing. So it starts by
 *  asking, and the branch for "nothing at all" is a real one: a quick tunnel
 *  needs no account and no domain, and Pilot polls rather than streaming, so
 *  the one thing quick tunnels cannot do does not matter here. */
function tunnelTask(port: number) {
  return [
    "【第一步只做一件事：问我下面两个问题，然后停下等我回答。",
    "不要执行任何命令，不要安装任何东西，不要读取或修改任何配置。】",
    "",
    "问题：",
    "1. 我有没有域名？托管在哪里（Cloudflare / 其他 / 没有）",
    "2. 我有没有自己的服务器？有没有装 Tailscale 之类的虚拟网？",
    "",
    "———— 以下是背景，等我回答完再用 ————",
    "",
    "目标：配好从外网访问这台电脑上的 MMS Pilot。",
    `Pilot 现在跑在 127.0.0.1:${port}，只有同一个网络里的设备能连。`,
    "要的是一条从公网到这台电脑的反向通道：这台机器主动往外建长连接，",
    "外面的请求顺着它回来。所以不需要公网 IP，也不用在路由器上开端口。",
    "",
    "按我的回答挑一条，并且告诉我为什么挑它：",
    "",
    "A. 什么都没有 —— Cloudflare 快速隧道",
    "   `cloudflared tunnel --url http://127.0.0.1:" + port + "`",
    "   不需要账号、不需要域名，跑起来就给一个 https://xxx.trycloudflare.com。",
    "   代价：每次重启地址都会变；官方定位是调试用途，不保证可用性。",
    "",
    "B. 有 Tailscale 或愿意装 —— 免费、不需要域名、跨网络可用",
    "   两台设备装同一个账号即可，Pilot 的设置页里已经会列出这个地址。",
    "",
    "C. 有域名且托管在 Cloudflare —— 具名隧道，地址固定",
    "   建隧道、指 DNS、装成开机自启的服务。",
    "",
    "D. 有自己的服务器 —— 反向隧道到你的机器",
    "",
    "不管走哪条，配好之后：",
    "- 把隧道给出的地址填进 Pilot 设置页的「隧道域名」，立即生效，不用重启",
    "- 告诉我怎么验证，以及带 token 的链接从哪里拿",
    "",
    "规矩：",
    "- 注册域名、改 DNS、建账号、装系统服务，每一步都要先问我",
    "- 能装成开机自启就装，不要只在终端里前台跑，我关了终端就断",
    "",
    "再说一次：现在只问那两个问题，不要动手。",
  ].join("\n");
}

/** Turning this on is the one setting here that reaches past this machine, so
 *  the row says what that means before the switch rather than after. */
export function RemoteAccessSection({ startTask }: { startTask: (text: string) => void }) {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [chosen, setChosen] = useState("");

  const load = useCallback(async () => {
    try {
      setState(await request<State>("/remote-access"));
      setError("");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "读取失败");
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function change(payload: Record<string, unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setState(await mutate<State>("/remote-access", payload));
      setChosen("");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  const ways = state?.links || [];
  const active = ways.find((way) => way.host === chosen) || ways[0];
  return (
    <>
      <label className="preference-row">
        <div>
          <h2>让手机或另一台电脑访问</h2>
          {/* Where things stand, not what the feature is. The caveat that
              only matters while it is on is said below, where it applies. */}
          <p>
            {state?.enabled
              ? `已开启 —— 正在监听 ${state.listening.join("、") || "（暂无地址）"}。`
              : "已关闭 —— 未监听任何网络端口。"}
          </p>
        </div>
        <input
          type="checkbox"
          role="switch"
          aria-label="让手机或另一台电脑访问"
          disabled={busy || !state || state.mode === "all"}
          checked={!!state?.enabled}
          onChange={(event) => void change({ enabled: event.target.checked })}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {state?.mode === "all" && (
        <p className="section-note">
          这次启动用了 <code>--listen all</code>，监听范围由命令行决定。
        </p>
      )}
      {state?.enabled && (
        <div className="remote-access">
          {ways.length === 0 ? (
            <p className="section-note">现在没有可用的网络地址，连上 Wi-Fi 后回来看。</p>
          ) : (
            <>
              <p className="section-note">
                带 token 的链接才能打开。共用网络里，同网段的人也能碰到这个入口。
              </p>
              <div className="remote-ways" role="radiogroup" aria-label="选择一个地址">
                {ways.map((way) => (
                  <button
                    key={way.host}
                    type="button"
                    role="radio"
                    aria-checked={active?.host === way.host}
                    className={"remote-way " + (active?.host === way.host ? "selected" : "")}
                    onClick={() => setChosen(way.host)}
                  >
                    <strong>{way.host}</strong>
                    <small>{way.detail}</small>
                  </button>
                ))}
              </div>
              {active && (
                <div className="remote-share">
                  <QrCode value={active.url} />
                  <div className="remote-share-copy">
                    <p>用手机相机扫码打开。</p>
                    <code className="remote-url">{active.url}</code>
                    <div className="remote-actions">
                      <button
                        type="button"
                        className="button"
                        onClick={async () =>
                          setNotice(
                            (await copyText(active.url))
                              ? "链接已复制"
                              : "这个浏览器不允许复制，请手动选择链接",
                          )
                        }
                      >
                        <Copy size={14} />
                        复制链接
                      </button>
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        title="之前发出去的链接和已打开的页面都会失效"
                        onClick={() => void change({ regenerate: true })}
                      >
                        <RefreshCw size={14} />
                        换一个 token
                      </button>
                    </div>
                    <p className="section-note" role="status">
                      {notice || "换 token 会让之前发出去的链接全部失效。"}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
          <TunnelHostnames state={state} busy={busy} change={change} />
          {Object.keys(state.unavailable).length > 0 && (
            <p className="section-note">
              这些地址没能开出入口：{Object.keys(state.unavailable).join("、")}
            </p>
          )}
        </div>
      )}
      <div className="preference-row">
        <div>
          <h2>出门也要用</h2>
          <p>需要你自己的域名和一条公网通道。我们不提供支持。</p>
        </div>
        <button
          type="button"
          className="button"
          disabled={!state}
          onClick={() => startTask(tunnelTask(state?.port || 8765))}
        >
          <Wand2 size={14} />
          交给 Pilot 配
        </button>
      </div>
    </>
  );
}

/** The hostname a tunnel hands out, which it only knows once it is running.
 *
 *  Pilot answers to names it was told about and nothing else, and a quick
 *  tunnel's name is random per start, so requiring a restart to accept it
 *  would make the no-domain path useless. */
function TunnelHostnames({
  state,
  busy,
  change,
}: {
  state: State;
  busy: boolean;
  change: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  return (
    <form
      className="tunnel-hostnames"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!draft.trim()) return;
        await change({ hostname: draft });
        setDraft("");
      }}
    >
      <label>
        <span>隧道域名</span>
        <input
          value={draft}
          disabled={busy}
          placeholder="粘贴隧道给你的地址，例如 https://xxx.trycloudflare.com"
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
      <button type="submit" className="button" disabled={busy || !draft.trim()}>
        添加
      </button>
      {state.savedHostnames.length > 0 && (
        <ul className="tunnel-list">
          {state.savedHostnames.map((name) => (
            <li key={name}>
              <code>{name}</code>
              <button
                type="button"
                disabled={busy}
                aria-label={`不再接受 ${name}`}
                onClick={() => void change({ removeHostname: name })}
              >
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
