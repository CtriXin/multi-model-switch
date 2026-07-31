# Pi Request Capture

诊断开关，用来抓 mmf 启动的 Pi 实际发出的请求字节。默认关闭；不设环境变量时，Pi 启动链路和生成的 `models.json` 完全不变。

对应 issue #97。

## 要解决的问题

mmf 启动的 Pi 会间歇性收到上游 400：

- `invalid character '\x00' in string literal`（New API）
- `400 "Invalid JSON"`

已确认的事实：

- 这条报错文案可以用"body 里带一个真实未转义控制字节"逐字复现
- 正常转义的控制字符（content / `tool_calls.arguments` / tool result）在 `/v1/messages` 与 `/v1/chat/completions` 上都是 200
- 抓包实测 Pi 的三条协议路径，含真实控制字符的 tool result 全部被正确转义
- 用真实 Pi 回放失败 session 的 620KB 上下文，字节干净、200 OK
- 失败字符近似覆盖整个字节空间（含 `\t`、`{`、`§`、`Û`），属于随机字节损坏

合成压测复现不出来，所以只能在真实 session 上抓现场。

## 用法

```bash
# 自动分配端口并拉起 capture proxy，随本次启动生命周期结束
MMS_PI_CAPTURE_PROXY=1 mmf

# 复用一个已经在跑的 proxy
MMS_PI_CAPTURE_PROXY=127.0.0.1:41999 mmf
MMS_PI_CAPTURE_PROXY=:41999 mmf
```

启动后会打印抓包目录，位置在 `<session_home>/pi-capture/`：

| 文件 | 内容 |
|---|---|
| `capture.jsonl` | 每个请求一行：字节数、发现的原始控制字节及其偏移和上下文、UTF-8 是否合法、上游状态码 |
| `req-NNNNN.bin` | 只有可疑请求（有原始控制字节 / 非法 UTF-8 / 上游 4xx）才落盘原始 body |
| `routes.json` | 被改写的 provider baseUrl 与原始 upstream 的对照 |
| `proxy.out` | proxy 自身的 stdout |

也可以脱离 mmf 单独跑：

```bash
python3 scripts/pi_capture_proxy.py --port 41999 --log-dir /tmp/pi-capture
```

## 判定规则

出错那一刻去看 `capture.jsonl` 里对应那条记录：

- `raw_control_bytes` 非空 → **Pi 侧**序列化或传输缺陷，可以直接拿 `req-NNNNN.bin` 给 Pi 提 issue
- `raw_control_bytes` 为空但 `status` 是 4xx → Pi 发出的字节是干净的，问题在 relay 或网络路径
- `valid_utf8` 为 false → 编码层被截断或破坏，按传输问题查

## 设计约束

- 默认零行为变化：未设开关时不读不写 `models.json`
- 上游 origin 编码在路径里（`/__mms_capture__/<base64url-origin>/...`），一个 proxy 覆盖本次启动的全部 provider
- 保留 keep-alive 与 chunked 流式转发，避免抓包本身改变要观察的传输特征
- 请求 body 原样透传，不做任何归一化
- proxy 跟随发起启动的进程退出，不留孤儿进程
- 任何一步失败都 fail-open 到"不抓包、正常启动"，不会因为诊断开关阻断 Pi

## 注意

抓包目录里的原始 body 含完整对话内容，请求 header 不落盘（避免记录 API key），但 body 本身是明文，不要外传。
