/** What to hand the agent when someone asks it to set up outside access.
 *
 *  A task, not a page of instructions, because the right answer depends on
 *  what the person already has, and most people have nothing. So it starts by
 *  asking, and the branch for "nothing at all" is a real one: a quick tunnel
 *  needs no account and no domain, and Pilot polls rather than streaming, so
 *  the one thing quick tunnels cannot do does not matter here. */
export function tunnelTask(port: number) {
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
