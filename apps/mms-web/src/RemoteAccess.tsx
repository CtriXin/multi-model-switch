import { useCallback, useEffect, useState } from "react";
import { Copy, RefreshCw, Wand2 } from "lucide-react";
import { mutate, request } from "./api";
import { copyText } from "./clipboard";
import { QrCode } from "./QrCode";

interface Way {
  host: string;
  url: string;
  kind: "hostname" | "address";
  detail: string;
}
interface State {
  mode: "loopback" | "lan" | "all";
  enabled: boolean;
  token: string;
  hostnames: string[];
  links: Way[];
  listening: string[];
  unavailable: Record<string, string>;
  port: number;
}

/** What to hand the agent when someone asks it to set the tunnel up.
 *
 *  Written as a task rather than a page of instructions: the steps depend on
 *  whose domain it is and where it is hosted, which the agent can ask and this
 *  page cannot. It is told to ask before touching DNS or accounts. */
function tunnelTask(port: number) {
  return [
    "帮我把这台电脑上的 MMS Pilot 配好，让我出门用流量也能访问。",
    "",
    `现在 Pilot 跑在 127.0.0.1:${port}，只有同一个网络里的设备能连。`,
    "我要的是一条从公网到这台电脑的反向通道：这台机器主动往外建长连接，",
    "外面的请求顺着它回来，所以不需要公网 IP，也不用在路由器上开端口。",
    "",
    "动手之前先问我这几件事，确认了再做：",
    "1. 我有没有可用的域名，托管在哪里",
    "2. 用 Cloudflare Tunnel 还是别的方案",
    "",
    "要求：",
    "- 注册域名、改 DNS、建账号这类动作，每一步都要先让我确认",
    "- 通道装成开机自启的服务，不要只在终端里前台跑",
    "- 配好后用 --hostname <域名> 重启 Pilot，它的 Host 白名单只认它知道的名字",
    "- 最后告诉我怎么验证，以及带 token 的链接从哪里拿",
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
