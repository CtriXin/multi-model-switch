# MMS Web UI Quickstart

Web UI 是 MMS 当前最适合做教程的配置入口。它比 TUI 更适合截图、录屏和逐步解释，也更适合用 Playwright 做回归截图。

## 启动

Preview root 推荐用 `mmf`。如果保存页显示的是 `保存配置`，说明你打开的是 `mms config web` stable root；要写 `预览 DB + latest-approved bundle` 必须用 `mmf`：

```bash
mmf config web
```

如果只想启动不自动打开浏览器：

```bash
mmf config web --no-open
```

## 页面怎么读

首页先看四块状态：

1. **Root**：当前是 `mms` stable root 还是 `mmf` preview root。
2. **Registry DB**：preview DB 是否存在、route/model fact 是否已写入。
3. **Latest Approved Bundle**：下游实际读取的 generated bundle 是否 verified。
4. **Promotion Plan / Human Gate**：当前是否只停在人工晋级门口，不会静默写 stable。

## 添加一个通道

1. 点通道列表里的新增通道。
2. 填内部 ID 和显示名，例如 `tokyo` / `tencent`。
3. 填 `OpenAI base URL` 和/或 `Anthropic base URL`。
4. 填 API Key；留空不会覆盖旧 key。
5. 设置 `models_endpoint`：常见是 `/models`，不探测可用 `manual`。
6. 勾选支持协议：`anthropic_messages` / `openai_chat_completions`。
7. 勾选支持 CLI：`claude` / `codex` / `opencode` / `pi` / `agy`。

## 拉取和整理模型

- 远端 `/models` 返回的模型会进入当前通道模型列表。
- 远端不返回但你确认能用的模型，放到 extra/manual 模型。
- 不想在下游显示的模型，放到 hidden policy；不要因为一次拉取缺失就直接删除本地策略。
- `reason` / reasoning 是能力 metadata，不等于启动时强制 Thinking。
- vision / cache-sensitive / reasoning 等能力应该按真实 smoke evidence 修正。

## 保存前必须看预览

Web UI 保存前先生成保存预览：

- 看 diff：哪些 provider、model policy、route bundle 会变。
- 看 risk：HTTP URL、hidden cleanup、凭据更新、route publish guard。
- 下载 redacted plan JSON：里面不应包含明文 key。
- 确认后再发布 preview bundle。

## 保存后验证

```bash
mmf config check --json
mmf config bundle --json
mmf doctor
mmf test --provider <provider-id> --cli codex
mmf test --provider <provider-id> --cli claude
```

如果要晋级 stable，仍然是 human gate：

```bash
mmf promote --json
mms migrate config-v2 --json
mms config release-readiness --json
```

## 用 Playwright 做教程截图

推荐截图对象是 Web UI，不是 TUI：

- Web UI 有稳定 DOM，适合 Playwright 选择器。
- TUI 截图受终端、字体、窗口大小影响大。
- 教程截图可以固定 demo config root，避免碰真实 `~/.config/mms/**`。

建议截图脚本只做只读页面或 demo root，不自动保存真实配置。
