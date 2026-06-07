---
name: MMS Config Center
description: Launcher-first 本地 AI Coding CLI 运行时管理器的配置表面（控制台探针，cool/green 强调，专家质感）
colors:
  # base palette
  bg: "oklch(96.5% 0.007 230)"
  surface: "oklch(100% 0 0)"
  fg: "oklch(16% 0.015 250)"
  muted: "oklch(49% 0.018 245)"
  border: "oklch(87% 0.011 235)"
  accent: "oklch(52% 0.17 154)"
  # semantic
  ok: "oklch(55% 0.14 145)"
  warn: "oklch(68% 0.11 80)"
  danger: "oklch(55% 0.18 25)"
  # derived (kept as references; live code uses color-mix())
  accent-soft: "oklch(52% 0.17 154 / 0.10)"
  accent-hover: "oklch(42% 0.17 154)"
  fg-soft: "oklch(16% 0.015 250 / 0.05)"
  fg-ghost: "oklch(16% 0.015 250 / 0.08)"
  ok-soft: "oklch(55% 0.14 145 / 0.12)"
  warn-soft: "oklch(68% 0.11 80 / 0.12)"
  danger-soft: "oklch(55% 0.18 25 / 0.12)"
typography:
  body:
    fontFamily: "'Aptos', 'Geist', 'Satoshi', 'Avenir Next', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: 1.55
    fontWeight: 400
  display:
    fontFamily: "'Aptos', 'Geist', 'Satoshi', 'Avenir Next', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "clamp(26px, 3.5vw, 42px)"
    lineHeight: 1.15
    fontWeight: 700
    letterSpacing: "-0.025em"
  mono:
    fontFamily: "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace"
    fontSize: "13px"
    lineHeight: 1.55
  mono-label:
    fontFamily: "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.08em"
    textTransform: "uppercase"
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "9px 17px"
  button-secondary:
    backgroundColor: "{colors.fg-ghost}"
    textColor: "{colors.fg}"
    rounded: "{rounded.pill}"
    padding: "9px 17px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.fg}"
    rounded: "{rounded.pill}"
    padding: "9px 17px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "9px 17px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.lg}"
    padding: "28px"
  navbtn:
    backgroundColor: "transparent"
    textColor: "{colors.fg}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
---

# Design System: MMS Config Center

## 1. Overview

**Creative North Star: "The Console Probe"**

MMS 的 Web 配置表面是控制台，不是仪表板。它面向的是一个已经知道自己在干什么的用户——他不需要被教育，不需要被哄，也不需要被一层"漂亮玻璃"挡住。设计的态度是：把诊断字段、路由参数、CLI 状态、session 摘要按密度平铺出来，绿色高亮像示波器上的脉冲，告诉用户"这里是活的"，其他地方安静地退到冷灰里。失败也要讲清楚哪个字段、什么值、为什么非法。

系统节奏是 **honest density**：信息密，但不靠装饰补偿。**冷调主导**：所有表面色都偏 cool hue (140-250)，不沾任何 warm cream / sand 系（这是 2026 划一的 AI 默认 bg，PRODUCT.md 已明确禁掉）。**键盘优先**：TUI 是主路径，Web 是等价入口，每个交互都要能 Tab/方向键走完。**诊断先于默认**：route 切换、capability 变化、save plan 都要把"为什么是这个"露出来。

这个系统明确不是：SaaS 着陆页（没有渐变 hero / 1-2-3 步骤条 / "Get started free"）；ChatGPT/Claude 官网那种聊天产品感（不是对话气泡变体）；消费类工具的向导手朴（"Next → Done"是禁忌）；AI 默认 warm-neutral 背景。营销词族（streamline / empower / supercharge / leverage / unleash / seamless / world-class / enterprise-grade / next-generation / cutting-edge / game-changer / mission-critical）整组禁用。

**Key Characteristics:**
- Cool neutrals only；accent 是 OKLCH 52% 0.17 154（蓝绿），不沾暖色域
- 阴影仅作状态响应（hover / active / pending），静止表面零阴影
- Backdrop-blur 只允许头部 / 侧栏 / 底部 pending bar 三处"贴边容器"，卡片表面禁用
- 颜色不是唯一信号：成功 / 失败 / 警告必搭配 mono kicker 文字或位置提示
- 字体三族封顶：sans body + mono machine labels + display（同一 sans 高权重）
- 所有数字用 `font-variant-numeric: tabular-nums`，让面板数字对齐
- 14+ 处 uppercase + letter-spacing eyebrow，但严格限于 mono font 的"机器样标签"，正文和小标题禁

## 2. Colors

OKLCH 主导，色相严格收敛在 cool 域（140-250）。Warm hue 仅 `--warn`（hue 80）作为唯一警告色；`--danger` hue 25 偏冷红。**冷调是承诺，不是默认**。

### Primary
- **Cool Ink**（`#fg` = `oklch(16% 0.015 250)`）：正文 + 标题色。偏冷近黑，不走纯黑。**任何时候正文 / 标题都用它，不允许用 muted gray 假装"优雅"**。
- **Signal Green**（`#accent` = `oklch(52% 0.17 154)`）：主品牌强调、按钮主色、active 状态、链接默认色。**蓝绿色，不是纯绿也不是 emerald**——它要和"成功"区分开（成功是 `--ok` hue 145 更深一点）。
- **Hover Signal Green**（`#accent-hover` = `oklch(42% 0.17 154)`）：主按钮 hover / 关键 focus 环。

### Semantic
- **Pass Green**（`#ok` = `oklch(55% 0.14 145)`）：成功 / 通过 / 已启用状态。**比 accent 更深更冷**。
- **Warn Amber**（`#warn` = `oklch(68% 0.11 80)`）：**唯一允许的暖色 hue**。用于警告、stale 配置、待人工确认的项。
- **Fail Red**（`#danger` = `oklch(55% 0.18 25)`）：错误、删除、不可逆操作。**偏冷红，不走纯红**。

### Neutral
- **Paper Cool**（`#bg` = `oklch(96.5% 0.007 230)`）：body 背景底色。**不是 cream / sand / paper / parchment 任何 warm-neutral 系**——OKLCH chroma 0.007 几乎为零，hue 230 是冷蓝。
- **Surface White**（`#surface` = `oklch(100% 0 0)`）：卡片 / 面板 / 弹层。
- **Slate Mute**（`#muted` = `oklch(49% 0.018 245)`）：次要文字、说明、placeholder。**placeholder 也走 4.5:1 对比度，不允许 7:1 的"为了优雅"灰**。
- **Hairline**（`#border` = `oklch(87% 0.011 235)`）：1px 分隔线和卡片描边。

### Derived
- `--accent-soft`（10% alpha）、`--ok-soft`（12%）、`--warn-soft`（12%）、`--danger-soft`（12%）：用 `color-mix(in oklch, var(--X) 12%, transparent)` 派生，作浅色背景块（标签底 / 状态条）。
- `--fg-soft`（5%）、`--fg-ghost`（8%）：用 `color-mix(in oklch, var(--fg) X%, transparent)` 派生，作按钮 secondary bg、tab 底色。

### Named Rules

**The Cool-Only Rule.** 所有自定义色相必须落在 hue 140-250。**唯一例外是 `--warn`（hue 80）**——它是警告，暖色 = 警告，这是有意的语义编码。**禁止**任何 OKLCH 染色向 hue 40-100（warm cream / sand 族）。

**The One-Aid Rule.** 主品牌强调色（Signal Green）用于 ≤15% 的可见 surface。它是探针的脉冲，不是装饰。

**The Double-Signal Rule.** 任何 ok/warn/danger 状态必须同时搭配：(a) 颜色 (b) mono kicker 文字（如 `WARN / STALE / OFF`）或位置标记（如左侧色条）。颜色永远不是唯一信号。

## 3. Typography

**Display Font:** Aptos / Geist / Satoshi（与 body 同族，靠 weight 700 + clamp + 负字距拉开）
**Body Font:** Aptos / Geist / Satoshi / Avenir Next（系统 fallback 到 SF / Segoe UI / system-ui）
**Label/Mono Font:** JetBrains Mono / IBM Plex Mono（mono 全包，monospace number 走 `tabular-nums`）

**Character:** 三族封顶、零竞争。所有"显示感"都靠 weight 700 + letter-spacing -0.025em ~ -0.06em 拉出来，而不是换字体。Mono 严格只用于：(a) 命令行、API key、capability key；(b) uppercase kicker 标签；(c) 数字。**正文里不出现 mono**。

### Hierarchy
- **Display**（700, clamp(26px, 3.5vw, 42px), line-height 1.15, letter-spacing -0.025em）：h1，页面标题，**只用 1 个**。`text-wrap: balance`。
- **Headline**（700, 18px, line-height ~1.2）：panel 标题。
- **Title**（600, 15px ~ 16px）：卡片 / 子段标题。
- **Body**（400, 14px, line-height 1.55）：正文，行长 ≤75ch，**placeholder 走 4.5:1**，`text-wrap: pretty`。
- **Label**（600, 12px, letter-spacing 0.01em, muted 色）：form label。
- **Mono Label / Kicker**（600, 11px, letter-spacing 0.08em-0.14em, uppercase, mono font）：**唯一允许 uppercase 出现的位置**——CLI 标签、状态机读数、`.settings-kicker`、`.settings-stamp`、`.gate-risk`、`.inventory-tile span`、`.asset-cli-label`、`.session-cli`、`<th>`。
- **Mono Code**（400, 12-13px, line-height 1.45-1.55）：`code`、`textarea`、`.gate-command-row code`、`.result/.diff` 块。

### Named Rules

**The Uppercase-Mono Rule.** uppercase + letter-spacing 只允许出现在 mono font 标签上。正文 / 小标题 / 卡片标题**禁** uppercase。Mono kicker 起到"机器读出"的作用，不是装饰。

**The Three-Family Ceiling.** 不超过 3 族字体：sans body、mono label/code、display = sans body 加权重。**不引入衬线、不引入 humanist 副体**。同一 sans 不同 weight 比引入新字体更稳。

**The Tabular-Numbers Rule.** 任何面板级数字（库存数、metric、capability 计数、usage 数字）必须 `font-variant-numeric: tabular-nums`。让数字纵向对齐，不让变量宽度让表格乱。

## 4. Elevation

**默认零阴影。** Surfaces at rest 是平的（白底卡 + 1px hairline）。**阴影只作为状态响应出现**：hover lift、active focus、pending bar、modal 浮层。**不接受 "ambient shadow for depth" 装饰用法**。

### Shadow Vocabulary
- **State Hover**（`--shadow-sm` = `0 1px 2px oklch(0% 0 0 / 0.04)`）：`button:hover`、`.card:hover`、`.tab-btn:hover` 的最轻描边。**这是 shadow 默认值**。
- **State Active**（`--shadow` = `0 1px 3px oklch(0% 0 0 / 0.06), 0 1px 2px oklch(0% 0 0 / 0.04)`）：`.panel:hover`、`.navbtn.active`、`.session-card:hover`。**只用于明确的"选中 / 浮起"**。
- **Modal Lift**（`--shadow-md` = `0 4px 6px -1px oklch(0% 0 0 / 0.05), 0 2px 4px -2px oklch(0% 0 0 / 0.04)`）：dialog、popover、`.asset-pending-inner` 级别。
- **Hero Lift**（`--shadow-lg` = `0 10px 15px -3px oklch(0% 0 0 / 0.05), 0 4px 6px -4px oklch(0% 0 0 / 0.03)`）：reserved（当前未使用，预留大浮层如 onboarding overlay）。

### Named Rules

**The Flat-At-Rest Rule.** 静止 surface 永远零阴影。需要层级感用 1px hairline border + 0.005-0.015 chroma 的 surface tint 区分，不靠阴影。

**The State-Only-Shadow Rule.** 阴影四档（`--shadow-sm` 到 `--shadow-lg`）只服务于交互态：hover、active、focus、浮层。**禁止用阴影做"卡片更亮"或"模块更突出"的装饰用途**——那种深度交给 border + bg tint 解决。

## 5. Components

### Buttons
- **Shape:** 永远 pill（`border-radius: 999px`）。**不接受方形或大圆角按钮**。
- **Padding:** 主按钮 `9px 17px`；tab 按钮 `10px 16px`；ui-mode-toggle `5px 12px`（小尺寸 segmented）。
- **Primary:** Signal Green bg + 白字 + 14px 600；hover 用 `--accent-hover`，加 `transform: translateY(-1px)` 60ms。
- **Secondary:** `--fg-ghost` bg + fg 色字。Tab group、filter 用。
- **Ghost:** 透明 bg + 1px border（border 色）+ fg 字。危险度低但需要可点。
- **Danger:** `--danger` bg + 白字。**只用于不可逆操作**（删除 provider、删除 account、删除 session）。
- **Loading:** `.is-loading` 加 `::after` 旋转 spinner，无文字变化。
- **Focus:** `:focus` 加 `box-shadow: 0 0 0 3px var(--accent-soft)`，**目前 `button` 缺 focus 规则**——见 Don'ts。

### Chips / Pills / Tags / Badges
- **Style:** pill 或 5-7px 圆角。`--tag` 用 3-5px 圆角更紧。
- **Pill (.pill):** 5px 11px padding、12px 字。`ok` 用 `--ok-soft` bg + `--ok` 字，`warn` 同理。
- **Tag (.tag):** 3px 9px padding、11px 600。off 状态用 `--fg-ghost` bg + muted 字。
- **Chip (.chip):** 7px 13px padding、12px。filter 用，点击切换 active。
- **Cap Pill (.cap-pill):** 5px 10px padding、12px 650。模型能力标签。active 状态用 accent。
- **State (active / off):** 颜色 + 文字（"ACTIVE" / "OFF"）双信号，永远 mono font。

### Cards / Panels
- **Corner Style:** panel 用 `--radius-lg`（14px），card 用 `--radius`（10px），sub-card 用 6-8px。
- **Background:** `--surface` 白底，**不**用阴影立层级。
- **Border:** 1px `--border` hairline。
- **Internal Padding:** panel `28px`、card `18px`、tight card `15px`（如 `.setting-edit-card`）。
- **Hover:** panel 加 `--shadow` 抬一档 + border 略暗，transform 不动。card hover 加 `--shadow-sm`。
- **Special:** `.settings-command` 故意 0 圆角 + 1.5px 顶部分隔线 + 大号 mono h3，作为"控制台命令"语义。**不破坏 pill 体系**——它是有意的语义断点。

### Inputs / Fields
- **Style:** `--surface` bg + 1px `--border` + `--radius`（10px） + `10px 12px` padding。
- **Focus:** `border-color: var(--accent)` + `box-shadow: 0 0 0 3px var(--accent-soft)`。**这是 input 当前唯一 focus 规则**。
- **Mono Input:** `input[type="password"]` 和 `textarea` 用 `--font-mono`。
- **Error:** 红边 + 错误 mono kicker 文字（"INVALID JSON" / "MISSING API KEY"），**颜色不是唯一信号**。
- **Disabled:** 50% opacity + `cursor: not-allowed` + 不响应 hover。

### Navigation
- **Sidebar (.side):** 260px 宽，sticky，`backdrop-filter: blur(10px)` + 半透明白。**blur 是允许的"贴边容器"用法**。
- **Nav Button (.navbtn):** 全宽，左对齐，title 14px 500 + sub 11.5px 400 muted。active 状态加 `--fg-ghost` bg + `--shadow`。
- **Tab Group:** 横向 `.provider-tabs`、`.settings-tabs`、`.provider-form-tabs`。pill 圆角 999px + 内 padding 一致。
- **UI Mode Toggle:** segmented control（`.ui-mode-toggle`），三个按钮平铺，`5px 12px` 小 padding，active 状态 mono kicker 文字 + accent 描边。
- **Sticky Header:** `<header>` 用 `backdrop-filter: blur(12px)` + 半透明白，**blur 第二处允许用法**。

### Session Card
- **Shape:** `--radius`（10px），与普通 card 一致。
- **Per-CLI Color:** `--session-cli-color` 由 `.is-codex`（`#183a68` 深蓝）或 `.is-claude`（`#bd3f35` 深红）覆盖。
- **Left Border:** **5px solid** `--session-cli-color`——这是 CLI 标识信号。**属于有意的语义断点**（多色左条用于 per-CLI 区分），不属"装饰侧条"。Audit 时作为已知例外记录。
- **Body:** CLI 名 + 时间戳 + 状态 pill + 模型名。

### Settings Route Card
- **Shape:** `--radius`（10px），与普通 card 一致。
- **Per-State Color:** 3px 左边按状态变体（locked=`--danger` / ready=`--accent` / report=`--warn` / 默认=`--fg`），4 状态色 + 默认态 = 5 类。
- **Left Border:** **3px solid** 状态色——这是 route 状态编码信号。**属于有意的语义断点**（per-state identifier），与 `.session-card` 5px per-CLI 同类。
- **Body:** 状态名 + 路径 + 小描述。

### Session Message
- **User:** 4px **右**边（不是左边）`#15895e`（深绿）+ mono kicker "USER"。
- **Assistant:** 4px **左**边 `#2563c8`（深蓝）+ mono kicker "ASSISTANT"。
- **System / Tool:** 4px 左边 `color-mix(in oklch, var(--muted) 75%, var(--border))`（柔灰）+ mono kicker "SYSTEM" / "TOOL"。
- **Border 规则例外**：4 种对话角色统一接受 4px 侧条作为角色编码（per-role semantic stripe），不属"装饰侧条"。

### Pending / Toast
- **Toast:** 右下，固定位，pill 圆角，`box-shadow: --shadow-md`，`opacity/transform 350ms cubic-bezier(.4,0,.2,1)` 入场。
- **Asset Pending Bar:** 底部 fixed 居中 pill，`backdrop-filter: blur(14px)` + 半透明白。**blur 第三处允许用法**。

### Code / Command Blocks
- **Inline Code (`code`):** mono 12px / line-height 1.45。
- **Block (`.result`, `.diff`):** mono + inset box-shadow + `max-height` 滚动 + 内部 padding。
- **Command Row (`.gate-command-row`):** mono command + 右侧 copy 按钮 + hint 文字。

### Signature Component: Settings Command Panel
- **意义**：故意打破 pill 体系的"控制台命令"语义块。0 圆角、1.5px 顶部分隔、26px×26px 网格底纹、mono kicker（红色 `--danger`）"DANGER"、h3 巨大 uppercase `clamp(28px, 4.5vw, 56px)`。
- **用途**：danger zone、recovery 步骤、运行时控制。
- **规则**：仅用于强调"这里能破坏系统"——其他场景**不用**这个模式。

## 6. Do's and Don'ts

每条都直接对应 PRODUCT.md 战略语言 + 当前代码证据。"Don't" 里出现的项目就是未来 audit / polish 要对账的 backlog。

### Do:
- **Do** use OKLCH throughout. No HSL, no RGB-as-design-token, no #hex 散落（除了 `--session-cli-color` per-CLI 标识和 `.session-message` 的 4 个对话角色色）。
- **Do** pair color with mono kicker text. `WARN: stale config` 比单独 amber 圆点更清楚。
- **Do** use `font-variant-numeric: tabular-nums` on any panel-level number.
- **Do** use `text-wrap: balance` on h1-h3 and `text-wrap: pretty` on long prose.
- **Do** keep body line length ≤75ch, padding above 16px on body paragraphs.
- **Do** keep h1 to one per page; if you need a second hero, you've already failed.
- **Do** use 1px hairline borders for separation, not 2-3px colored stripes on neutral cards.
- **Do** use `--shadow-sm` and `--shadow` for hover/active state response, not for ambient depth.
- **Do** cap body font-size at 14px and section title at 18px. Display sizes use `clamp(26px, 3.5vw, 42px)` ceiling, never above 56px except in `.settings-command` semantic block.
- **Do** reference PRODUCT.md's "diagnose before default" by exposing route / provider / protocol / cache in the default state, not behind a "Show details" toggle.

### Don't:
- **Don't** use `border-left` / `border-right` greater than 1px as a colored accent on neutral cards, list items, callouts, or alerts. **Four known exceptions** in current code:
  - `.session-card` (5px) — per-CLI identifier stripe (codex / claude / others)
  - `.session-message` (4px) — per-role chat stripe (4 roles: user / assistant / system / tool)
  - `.settings-route-card` (3px) — per-state status stripe (locked / ready / report / default)
  - All four are semantic stripes, not decoration; they stay. **New violations** in any other context are a hard fail.
- **Don't** use `background-clip: text` + gradient background for emphasis. Use single solid color or weight.
- **Don't** use `backdrop-filter: blur()` decoratively on cards. **Three known exceptions**: `<header>`, `<aside class="side">`, `.asset-pending-inner` (sticky top, sticky sidebar, fixed-bottom pending bar). **New uses on regular cards/panels are a hard fail.**
- **Don't** use uppercase + letter-spacing on body text, headlines, or card titles. The mono-kicker uppercase pattern is the only allowed location.
- **Don't** add `01 · About / 02 · Process / 03 · Pricing`-style numbered section markers above sections. If a section is genuinely a sequence (a 3-step install), use the sequence; do not reflex-number every section.
- **Don't** add a SaaS-style kicker (`ABOUT / PROCESS / PRICING` all-caps, wide tracking) above every section. `.settings-kicker` is mono-machine, not decorative eyebrow; that is its only legitimate form.
- **Don't** ship animations without a `prefers-reduced-motion: reduce` fallback. Current code has `loadingSweep`, `bootPulse`, `buttonSpin`, `assetBarIn`, `panelSettle` and **no reduced-motion override** — see audit backlog.
- **Don't** ship interactive elements without `:focus-visible` styles. **Current state**: only `input / select / textarea` have `:focus` styles. `button / .button / .navbtn / .chip / .tab-btn / .cap-pill` are all missing focus rules. This is a P1 audit item.
- **Don't** use `box-shadow` for ambient depth on resting cards. Use border + bg tint.
- **Don't** use warm cream / sand / paper / parchment / bone / linen / wheat / biscuit / ivory / flour background hues (OKLCH L 0.84-0.97, C < 0.06, hue 40-100). Cool-only or true neutral.
- **Don't** use any of the marketing-buzzword family: streamline / empower / supercharge / leverage / unleash / seamless / world-class / enterprise-grade / next-generation / cutting-edge / game-changer / mission-critical. Pick a specific noun and a verb.
- **Don't** use em dashes (`—`) or `--` in body copy. Use commas, colons, semicolons, periods, or parentheses.
- **Don't** use the "big number, small label, gradient accent" hero-metric template. Numbers stand on `tabular-nums` + mono kicker label, no decorative chrome.
- **Don't** repeat the section title in the section body. The heading is the heading; the body says something the heading doesn't.
- **Don't** use the "default to dark mode" reflex; the cool-light baseline is the spec.
