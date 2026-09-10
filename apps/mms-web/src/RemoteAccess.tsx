import { useCallback, useEffect, useState } from "react";
import { ChevronDown, Copy, RefreshCw } from "lucide-react";
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

/** Turning this on is the one thing that makes Pilot reachable from another
 *  device, so the section says what that means before the switch, not after. */
export function RemoteAccessSection() {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [chosen, setChosen] = useState("");
  const [geek, setGeek] = useState(false);

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
      const next = await mutate<State>("/remote-access", payload);
      setState(next);
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
          <p>
            打开后，这台电脑会在自己的网络地址上多开一个入口，同一个 Wi-Fi
            下的手机和电脑就能打开 Pilot。链接里带一串 token，没有它打不开。
          </p>
          <p className="preference-caution">
            在公司、学校或咖啡馆这类共用网络里打开，同网段的人都能碰到这个入口。
            token 挡得住，但要不要开由你决定。关掉后端口立刻关闭，网络上再也看不到。
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
          这次启动用了 <code>--listen all</code>，监听范围由命令行决定，开关不改它。
        </p>
      )}
      {state?.enabled && (
        <div className="remote-access">
          {ways.length === 0 ? (
            <p className="section-note">
              这台电脑现在没有可用的网络地址。连上 Wi-Fi 或网线后回来刷新。
            </p>
          ) : (
            <>
              <div className="remote-ways" role="radiogroup" aria-label="选择一个地址">
                {ways.map((way) => (
                  <button
                    key={way.host}
                    type="button"
                    role="radio"
                    aria-checked={active?.host === way.host}
                    className={
                      "remote-way " + (active?.host === way.host ? "selected" : "")
                    }
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
                    <p>用手机相机扫这个码，就会打开这个地址。</p>
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
                        onClick={() => void change({ regenerate: true })}
                      >
                        <RefreshCw size={14} />
                        换一个 token
                      </button>
                    </div>
                    {notice && <p className="section-note" role="status">{notice}</p>}
                    <p className="section-note">
                      换 token 之后，之前发出去的链接和已经打开的页面都会失效，需要重新扫码。
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
          {Object.keys(state.unavailable).length > 0 && (
            <p className="section-note">
              这些地址没能打开入口，已经不再列出：
              {Object.keys(state.unavailable).join("、")}
            </p>
          )}
        </div>
      )}
      <div className="preference-row geek-row">
        <div>
          <button
            type="button"
            className="geek-toggle"
            aria-expanded={geek}
            onClick={() => setGeek((open) => !open)}
          >
            <ChevronDown size={14} className={geek ? "open" : ""} />
            <h2>出门也要用（需要自己动手）</h2>
          </button>
          <p>
            上面那个开关只在同一个网络里有效。要在外面用流量访问，需要一条从公网到这台
            电脑的通道。这部分我们不提供支持，下面是自己配的思路。
          </p>
          {geek && (
            <div className="geek-body">
              <p>
                思路是反向连接：这台电脑上跑一个客户端，主动向外建一条长连接，外面的请求
                顺着这条连接回来。所以不需要公网 IP，也不用在路由器上开端口。
              </p>
              <p>
                以 Cloudflare Tunnel 为例，你需要一个接在 Cloudflare 上的域名和一个免费
                账号，然后大致三步：
              </p>
              <ol>
                <li>装 <code>cloudflared</code> 并登录你的 Cloudflare 账号。</li>
                <li>
                  建一条隧道并把域名指向它，让它转发到本机的 Pilot 端口
                  <code>{` 127.0.0.1:${state?.port || 8765}`}</code>。
                </li>
                <li>
                  用这个域名启动 Pilot，让它接受这个 Host：
                  <code>{` mms-web --listen lan --hostname 你的域名`}</code>
                </li>
              </ol>
              <p>
                之后设置页里会多出一条带域名的入口，扫码方式一样。走域名是 HTTPS，所以
                能装主屏幕图标、能用相机，局域网那条不行。
              </p>
              <p className="preference-caution">
                域名不是秘密：证书一签发就会进公开的 Certificate Transparency 日志，几分钟
                内就能被扫到。所以 token 依然是唯一的门禁，别把带 token 的链接贴到公开地方。
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
