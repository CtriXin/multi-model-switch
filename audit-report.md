# Webui Audit Report — `mms_config_web_static/`

**Date:** 2026-06-07
**Scope:** `mms_config_web_static/index.html` (612L) + `config-web.css` (4010L) + `config-web.js` (588L)
**Reference:** `.worktrees/dev/DESIGN.md` + `PRODUCT.md`
**Detector:** `node .claude/skills/impeccable/scripts/detect.mjs` (side-tab pattern only — cream / gradient-text / glassmorphism 不命中)

---

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | **1** | 16+ interactive element types missing `:focus-visible`; no `prefers-reduced-motion`; 7 selectors use `transition: all`; aria-selected / aria-expanded / aria-live / aria-required 全部缺失 |
| 2 | Performance | **3** | GPU-expensive `backdrop-filter: blur()` 仅 3 处（header/sidebar/pending-bar），都在 spec 允许位；box-shadow transition 7 处（影响 hover 性能） |
| 3 | Theming | **3** | OKLCH tokens 全 `:root` 采用，color-mix 派生；7 处非 spec 硬编码色（4 白字 / 3 rgba shadow）；2 处 border-left 默认色用 `var(--fg)` 不带状态语义 |
| 4 | Responsive Design | **3** | 8 个 `@media` 块覆盖 1180/980/780/680/560 五个断点；`clamp()` 用在 header / h1 / .shell / 4 个 h3 / metric；`min-width: 1120px` 的能力表是已知 mobile 风险 |
| 5 | Anti-Patterns | **2** | 14+ `text-transform: uppercase` 全部走 mono font（OK）；**3 处非 spec 装饰侧条**（`.settings-compat-note` / `.oc-order-note` / `.session-message.is-system,is-tool`）；缺 `prefers-reduced-motion` 兜底；`transition: all` 7 处 |
| **Total** | | **12/20** | **Acceptable — P1 级问题需要在 ship 前修** |

**Rating band:** 10-13 Acceptable. 5 个 P0/P1 项直接影响 WCAG AA 合规（focus-visible 缺失 + reduced-motion 缺失 + contrast 例外 3 处 `rgba(255,255,255,.72-.82)` 在深色 active 态可能跌破 4.5:1）。

---

## Anti-Patterns Verdict

**Pass with caveats.** 这个界面不读起来像 AI 生成 —— 它读起来像"工程务实的人写的配置工具"。OKLCH + cool ink palette + tabular-nums + mono kicker + per-CLI stripe + 0-radius danger zone 这些都是项目有意识的语言。Detector 只命中 side-tab 一类（7 处），其中 3 处真违规、4 处属于 spec 内"per-state / per-role 语义例外"。

**真违规（需要修）：**
- `.settings-compat-note` 3px warn 装饰侧条（L1350）
- `.oc-order-note` 3px accent 装饰侧条（L1842）
- `.session-message.is-system, is-tool` 4px muted mix 装饰侧条（L3872-3873）—— 但与 is-user/is-assistant 4px 是同类，是对话角色编码；建议在 spec 里把"对话角色 stripe"扩展为 4 种角色统一接受

**Spec 例外（保留）：**
- `.session-card` 5px per-CLI（L3446）—— 文档已显式记录
- `.session-message.is-user` 4px right（L3857）、`.is-assistant` 4px left（L3866）—— 文档已显式记录
- `.session-message.is-system, .is-tool` 4px（L3875）—— 同上，应统一入 spec
- `.settings-route-card` 4 个状态变体（locked/ready/report/default）3px 状态色（L489-496）—— 类比 session-card per-CLI，是 per-state 状态条；spec 应新增第 5 类例外

**结构性 AI tells：**
- `transition: all` 出现在 `.navbtn` / `.provider-item` / `.tab-btn` / `.filterbar button` / `.inventory-tile strong` / `.session-inline-actions button` / `.session-resume-actions button` 7 处 —— 7 处全是为了省事不写明 transition-property，应改写具体属性列表
- 缺 `prefers-reduced-motion` 兜底，5 个 `@keyframes` 全部无条件播放
- 14+ `text-transform: uppercase` —— 但**全部**走 mono font（spec 内允许），无 eyebrow 滥用
- marketing 词族（streamline / empower / supercharge ...）在 HTML body copy 中**无命中**

---

## Executive Summary

- **Audit Health Score: 12/20 (Acceptable)**
- **Total issues:** 2 P0 · 7 P1 · 12 P2 · 6 P3
- **Top 5 关键项：**
  1. **P0** 16+ interactive 元素缺 `:focus-visible` —— WCAG 2.4.7 必修
  2. **P0** 缺 `prefers-reduced-motion: reduce` 兜底 —— WCAG 2.3.3 必修
  3. **P1** 3 处 `rgba(255,255,255,.72-.82)` 文字在 active 态深色 bg 上可能跌破 4.5:1 对比度
  4. **P1** 5 个触摸目标 < 36px（.chip / .pill / .cap-pill / .tag / .ui-mode-toggle button / .asset-mini-action）—— WCAG 2.5.5 (AAA 44px / AA 24px)
  5. **P1** `.session-card` 5px + 4 处 3-4px 侧条 / stripe 缺 spec 一致性 —— 3 处真违规要修，4 处要进 spec
- **Recommended next steps:** 修 P0/P1 后再 re-audit；如果只是评估当前状态，本报告就足够决策

---

## Detailed Findings by Severity

### P0 — Blocking (WCAG AA 必修)

#### [P0] Focus indicators missing on 16+ interactive selectors
- **Location:** 全文件
- **Category:** Accessibility
- **Impact:** 键盘用户（power user 流程、screen reader 用户、TUI 习惯者）无法判断当前焦点位置。MMS 目标用户群（多 CLI / 多 provider 开发者）很多人就是键盘流。
- **WCAG:** 2.4.7 Focus Visible (AA)
- **Evidence:** `config-web.css` 唯一 `:focus` 规则在 L794-798（仅覆盖 `input, select, textarea`）。其余全部缺：`.button` / `.navbtn` / `.tab-btn` / `.chip` / `.cap-pill` / `.pill` / `.tag` / `.check` / `.settings-tab` / `.provider-form-tab` / `.ui-mode-toggle button` / `.session-card` / `.asset-card` / `.provider-item` / `.filterbar button` / `.asset-mini-action` / `details > summary` / `<a>` (当前无 `<a>`，但 0 命中也代表缺)
- **Recommendation:** 全局加 `:focus-visible` 规则，复用 input 现有 ring（`box-shadow: 0 0 0 3px var(--accent-soft); border-color: var(--accent);`），可加一条通配 selector 兜底
- **Suggested command:** `/impeccable polish`（focus 状态属于 micro-details 修整）

#### [P0] `prefers-reduced-motion: reduce` missing
- **Location:** 全文件
- **Category:** Accessibility / Performance
- **Impact:** 前庭功能障碍用户在 `loadingSweep` / `bootPulse` / `buttonSpin` / `assetBarIn` / `panelSettle` / `fadeIn` 下会眩晕；系统级 reduce-motion 开关被忽略。
- **WCAG:** 2.3.3 Animation from Interactions (AAA)
- **Evidence:** `grep "@media (prefers-reduced-motion" config-web.css` 返回 0 命中。6 个 `@keyframes` 全部无条件。
- **Recommendation:** 文末加 `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; } }`
- **Suggested command:** `/impeccable polish`

### P1 — Major

#### [P1] 3 处非 spec 装饰侧条（border-left 3-4px 在 callout / 普通卡片上）
- **Location:** `.settings-compat-note` L1350（3px warn）/ `.oc-order-note` L1842（3px accent）/ `.session-message.is-system, is-tool` L3872-3873（4px muted mix）
- **Category:** Anti-Pattern / Theming
- **Impact:** 违反 spec 核心禁令；3 处都是普通信息块/告警块的彩色装饰边，正是 AI slop 典型 tell。`.session-message.is-system, is-tool` 这条有辩解空间（与 is-user / is-assistant 4px 是同类对话角色编码），但当前 spec 只接受 2 种角色，需扩展。
- **Recommendation:** 三个选项任选——
  - A. 改用 mono kicker 文字 + `--warn-soft` / `--accent-soft` 浅色背景块（推荐）
  - B. 降到 1px hairline（弱化但保留语义）
  - C. 进 spec（只在对话角色 4 种 + settings-route-card 状态 4 种保留）
- **Suggested command:** `/impeccable polish`（选 A 后可以批量改）

#### [P1] Active 态白字在彩色 bg 上可能跌破 4.5:1
- **Location:** `.navbtn.active small` L224 (`rgba(255,255,255,0.82)`) / `.provider-form-tab.active .muted` L1052 (`rgba(255,255,255,.72)`) / `.settings-tab.active span` L1272 (`rgba(255,255,255,.74)`) / 同 L3261 (`rgba(255,255,255,.72)`)
- **Category:** Accessibility
- **Impact:** muted white 在 accent / fg 浅色 active 态上对比度可能 < 4.5:1；`.72` 透明度尤其危险。需要逐 selector 实测。
- **WCAG:** 1.4.3 Contrast Minimum (AA)
- **Recommendation:** 移除透明度，用 `oklch` 直接定 `--muted-active` token，亮度按 active 底色算；或者把透明度提到 `.88` 起
- **Suggested command:** `/impeccable audit` 之后再修（需要重新计算）

#### [P1] 5 个触摸目标 < 36px
- **Location:** `.ui-mode-toggle button` L109 `min-height: 28px` / `.cap-pill` L1606 `min-height: 28px` / `.asset-mini-action` L2604 `min-height: 28px` / `.chip` L1679 计算 ~28.6px / `.pill` L1383 计算 ~28.6px / `.tag` L1406 计算 ~23px
- **Category:** Accessibility / Responsive
- **Impact:** 触屏用户（iPad 调试 / 触屏笔电）点不准。`.tag` 是 inline 显示文本，理论上非交互；但 `.chip` / `.pill` 多数带 data-* 操作，是真交互。
- **WCAG:** 2.5.5 Target Size (AAA 44px / AA 24px)
- **Recommendation:** 交互型 chip / pill / cap-pill 升到 `min-height: 32px`；`.ui-mode-toggle button` 升到 36px（保持 segmented control 紧凑感）。`.asset-mini-action` 升到 36px。`.tag` 可不修
- **Suggested command:** `/impeccable adapt`（响应式 / 触屏适配）

#### [P1] ARIA states 缺失（aria-selected / aria-expanded / aria-current / aria-live）
- **Location:** 全文件
- **Category:** Accessibility
- **Impact:** Screen reader 用户无法知道当前 tab / 展开的 details / 切换的 UI mode。MMS 标"键盘优先"，ARIA 不能只靠视觉。
- **WCAG:** 4.1.2 Name, Role, Value (AA)
- **Evidence:** `grep -E "aria-(selected|expanded|current|controls|describedby|invalid|required|live)" index.html` 返回 0 命中。只有 `aria-label` / `aria-busy` / `aria-hidden` / `role="tablist"` 用了。
- **Recommendation:** JS 在切换 tab / navbtn / settings-tab / provider-form-tab 时同步设 `aria-selected="true"`；`<details>` 默认带 `aria-expanded` 但可显式管理；UI mode toggle 改用 `role="radiogroup"` + `aria-checked`
- **Suggested command:** `/impeccable harden`（生产就绪 a11y）

#### [P1] `transition: all` 7 处 — 反模式
- **Location:** L204 `.navbtn` / L916 `.provider-item` / L986 `.tab-btn` / L1861 `.filterbar` / L2789 `.inventory-tile strong` / L3490 `.session-inline-actions button` / L3631 `.session-resume-actions button`
- **Category:** Performance / Anti-Pattern
- **Impact:** `transition: all` 会导致"所有"可继承属性都参与过渡（color / font / line-height 等等），触发不必要的 paint / layout；浏览器不能优化。
- **Recommendation:** 全部改写为具体属性列表（参考已有 `.button` L853 写法：`background .15s ease, transform .06s ease, box-shadow .15s ease`）
- **Suggested command:** `/impeccable polish`

#### [P1] `<input>`/`<select>` 缺 `aria-required` / `aria-invalid` / 缺 form 错误状态
- **Location:** 全文件表单
- **Category:** Accessibility
- **Impact:** 必填项 / 校验失败对 screen reader 静默。
- **WCAG:** 1.3.1 Info and Relationships (AA)
- **Evidence:** `grep -E "(required|aria-required|aria-invalid)"` HTML 命中 0。
- **Recommendation:** 必填项加 `aria-required="true"`；JS 校验失败时 `aria-invalid="true"` + 错误 mono kicker 文字（spec 已要求 mono kicker 文字，颜色不是唯一信号）
- **Suggested command:** `/impeccable harden`

### P2 — Minor

#### [P2] Spacing scale 部分值不在 5 步 token 内
- **Location:** 大量 padding/gap 出现 9 / 11 / 13 / 14 / 15 / 16 / 17 / 18 / 22 px
- **Category:** Theming
- **Impact:** 视觉密度看似"差不多"，但和 5 步 token (6/10/16/24/32) 不齐，让 polish 时难批量改。
- **Recommendation:** 把 5 步 token 扩到 6 步（加 8 / 12），或承认"padding 不是 5 步的硬约束"，spec 把这两套都接受。**注意**：原 spec 已说 padding 不在 5 步里，所以 P2 而非 P1
- **Suggested command:** `/impeccable layout`（节奏统一）

#### [P2] Radius 出现 8 / 12 / 13 / 16 / 20 / 22 等非常规值
- **Location:** L700 `8px` / L1659 `10px` / L2384 `12px` / L1035 `13px` / L1191 `16px` / L3383 `20px` / L2126 `22px` 等
- **Category:** Theming
- **Impact:** 14 个非 token radius 值（不含 0/4/999px/pill 与 var 引用），让设计系统"看上去有 radius 系统但实际有 14 个特例"。
- **Recommendation:** 把 `.cli-toggle` / `.session-card` / `.session-resume-hints` / `.settings-actionbar` / `.settings-tab-panel` 等统一到 14px（`--radius-lg`）或 18px（`--radius-xl`），看具体上下文
- **Suggested command:** `/impeccable layout`

#### [P2] `box-shadow` 7 处参与 transition（hover 时 reflow）
- **Location:** `.panel` L233 / `.card` L293 / `input/select/textarea` L789 / `button, .button` L853 / `.oc-metric` L1803 / `.session-card` L3453 / 还有 `.asset-card` 派生
- **Category:** Performance
- **Impact:** 阴影在 hover 时重绘，移动端掉帧可能。
- **Recommendation:** 用 `transform: translateY(-1px)` + 不变 shadow（已部分实现于 `.button`）替代单纯改 shadow；或用 `::after` pseudo 做半透明阴影层
- **Suggested command:** `/impeccable optimize`

#### [P2] 能力表 `min-width: 1120px` 在 < 1180px 视口会撑破布局
- **Location:** L1468 `.model-capability-table` `min-width: 1120px` / L1429 `table` `min-width: 860px`
- **Category:** Responsive
- **Impact:** 移动端 / 平板竖屏会触发水平滚动。
- **Recommendation:** `.table-wrap` 已有 `overflow: auto`（OK），但要测 iPad 竖屏 1024px；如真有 1024-1180 之间视口卡死，把 min-width 降到 980 或改成 `width: 100%` + 内部 table 用更小列宽
- **Suggested command:** `/impeccable adapt`

#### [P2] `padding: 9px 17px` button 在 mono label 文本下视觉水平 padding 不对称
- **Location:** L843 `button, .button`
- **Category:** Theming
- **Impact:** 9+17=26 / 9+17=26 但 mono label 字宽不对称（"STOP" vs "RUN"），实际看着偏左
- **Recommendation:** 改 `padding: 9px 18px`（保持 9 + 18 = 27，对称）
- **Suggested command:** `/impeccable polish`

#### [P2] `transition: all` 在 `.provider-item` 上让整卡片参与过渡（包括 box-shadow 已写定）
- **Location:** L916
- **Category:** Performance
- **Impact:** 同 [P1] `transition: all`，但 `.provider-item` 数量在 fallback / channel 页面大
- **Suggested command:** `/impeccable polish`

#### [P2] 0.5px 字体相关 / fractional value 未发现，但 `font-weight: 650` / `750` 是 OKLCH 黑体之间过渡值
- **Location:** L114 `.cap-pill` `font-weight: 650` / L2567 `.asset-title` `font-weight: 750` / L2554 `.asset-cli-label` `font-weight: 750` / L1930 `.asset-count` `font-weight: 750` / L2104 `.session-card` `font-weight: 750`
- **Category:** Theming
- **Impact:** variable font 大量铺开（OK），但不同 selector 用了 650 / 700 / 750，需要让 spec 收敛到 4-5 个 weight
- **Recommendation:** spec 接受 4 个 weight：500（body label） / 600（button / strong） / 700（h1 / h2） / 750（display 强调）。650 改 600 或 700
- **Suggested command:** `/impeccable typeset`

#### [P2] `<details>` 缺 `aria-expanded` 显式管理
- **Location:** 多个 `details`（如 `.session-folder` / `.session-resume-details` / `.gate-raw` / `.asset-source-diagnostic` / `.asset-config-card details`）
- **Category:** Accessibility
- **Impact:** HTML `<details>` 浏览器会管 `open` attr，但 screen reader 对动态切换的体验在某些浏览器上不一致
- **Recommendation:** JS 显式同步 `aria-expanded` 到 `details.open`
- **Suggested command:** `/impeccable harden`

#### [P2] `.provider-form-tab.active` 用 `box-shadow: 0 8px 20px rgba(15, 23, 42, .12)` 含硬编码 rgba
- **Location:** L1050
- **Category:** Theming
- **Impact:** 用了硬编码 rgba shadow（不是 OKLCH），且是 spec 内允许的 `--shadow` 之外的手工值
- **Recommendation:** 改用 `--shadow-md` token
- **Suggested command:** `/impeccable polish`

#### [P2] `rgba(17, 24, 39, 0.08)` 在 `.model-capability-table` L1536
- **Category:** Theming
- **Impact:** 硬编码 shadow
- **Recommendation:** 改用 `--shadow-sm` 或派生 token
- **Suggested command:** `/impeccable polish`

#### [P2] `<input type="password">` 与 textarea 共用 font-family 但密码应走 letter-spacing
- **Location:** L786
- **Category:** Accessibility
- **Impact:** mono password 让用户更难数位数
- **Recommendation:** password input 单独 `font-family: var(--font-mono); letter-spacing: 0.1em;`
- **Suggested command:** `/impeccable polish`

#### [P2] heading 层级缺 h4（0 命中），h5 定义但未用
- **Location:** 全文件
- **Category:** Accessibility
- **Impact:** 大量 h3 在 panel 内堆叠 6+ 层时层级不清
- **Recommendation:** 在 panel 内嵌套层级 > 3 时升级到 h4；h5 删除
- **Suggested command:** `/impeccable typeset`

### P3 — Polish

#### [P3] `width: 12px; height: 12px` 硬编码在 `.button.is-loading::after` spinner
- **Location:** L891
- **Category:** Theming
- **Recommendation:** 抽到 `--spinner-size: 12px`

#### [P3] `font-feature-settings: "tnum"` 在 5 处用了 `font-variant-numeric: tabular-nums` —— 行为一致，不算问题
- **Recommendation:** 留

#### [P3] `header padding` clamp 下限 18px、上限 56px — 中间断点是否合适需实测
- **Location:** L65, L153
- **Category:** Responsive
- **Recommendation:** 实测 1180/980/780/560 四档断点下 header padding 表现；如 980 视口 4vw = 39.2px 不够紧凑，调低 4vw → 3vw

#### [P3] `.gate-risk` padding 有 3 个值（6px 11px / 6px 10px / 6px 8px），3 个变体
- **Location:** L663
- **Category:** Theming
- **Recommendation:** 统一到一个值

#### [P3] `loading-lines` max-width 680px 在 desktop 太窄
- **Location:** L269
- **Category:** Responsive
- **Recommendation:** 提到 720-820 区间

#### [P3] `<h5>` 在 CSS L678 定义但 HTML 0 命中
- **Location:** L678
- **Category:** Theming
- **Recommendation:** 删除未用样式

---

## Patterns & Systemic Issues

### 1. "side-tab stripe" 在 4 个不同位置以 3 种不同 size 出现
- `.session-card` 5px per-CLI
- `.session-message` 4px per-role（4 种角色）
- `.settings-route-card` 3px per-state（4 种状态）
- `.settings-compat-note` / `.oc-order-note` 3px 普通 callout

**根因**：作者在用"侧条颜色"作为状态编码工具，但 spec 没把这套说清楚。**修法**：spec 显式分两类（"per-state / per-role / per-CLI 标识"允许 / "普通 callout 装饰"禁止），现有 7 处中 3 处归到禁止类。

### 2. focus-visible 缺失是单点失败不是设计缺陷
- 1 处输入框 focus 写得很好（accent 3px ring），但作者没把它推广到 button / navbtn / chip。
- **修法**：加全局 `:focus-visible` 兜底 + 组件级 override。

### 3. `transition: all` 是"省事税"
- 7 处全是为了少打几个属性名。
- **修法**：在 spec 的"Components"段写"所有 transition 必须显式列属性，禁止 `all`"。

### 4. OKLCH 教义执行彻底，但 7 处硬编码色泄漏
- 4 个 per-CLI / per-role 例外（spec 允许） + 3 个 active 态白字 rgba + 2 个 shadow rgba + 1 个 L490 border 默认色 `var(--fg)`。
- **修法**：3 个白字 rgba 进 token（`--fg-on-accent` / `--fg-on-warn`）；2 个 shadow rgba 改 OKLCH；L490 `var(--fg)` 是 `.settings-route-card` 默认态，进 spec 例外。

### 5. `prefers-reduced-motion` 缺失是 P0
- 一个 `@media` 块就能修，但当前 0 命中。

---

## Positive Findings

值得保留的（不要在 polish 里改坏）：

1. **OKLCH 教义彻底执行** — `:root` 0 处硬编码颜色，所有非 per-CLI / per-role 色都走 `var(--*)` + `color-mix(in oklch, ...)`。这是项目最强的设计资产。
2. **input focus ring** 写得专业（3px accent-soft box-shadow + accent border），是 P0 focus 修复的"原型"
3. **`text-wrap: balance` / `text-wrap: pretty`** 在 L59-60 全局启用 —— 不常见，值得保留
4. **`font-variant-numeric: tabular-nums`** 5 处使用（库存 / 指标 / progress / mono），对齐数字面板
5. **`<button>` 80 个 + `<div onclick>` 0 + `<a>` 0** — 语义 HTML 干净
6. **`<details>` + `summary`** 用于折叠组，符合 spec"键盘优先"路线
7. **`.table-wrap` 已有 `overflow: auto`** 兜底能力表水平滚动
8. **`.asset-pending-bar` 用 `env(safe-area-inset-*)`** 处理 iPhone 横屏 home indicator
9. **5 档 `@media` 断点**（1180/980/780/680/560）覆盖 tablet + 触屏
10. **`<h5>` 在 CSS 定义但 HTML 不用** —— 反而是好事，说明作者节制；P3 建议删
11. **`reset: box-sizing: border-box`** 全局
12. **15 处 `overflow-wrap: anywhere`** 防长字符串撑破布局
13. **`.navbtn` 在 mobile sidebar 是 58px** —— 主交互路径 100% 满足 44px 要求
14. **per-CLI stripe**（`.session-card.is-codex` / `.is-claude`）是诊断增强，不是装饰 —— spec 例外应保留

---

## Recommended Actions

按 P0 → P1 → P2 优先级：

1. **[P0] `/impeccable polish`** —— focus-visible 兜底 + prefers-reduced-motion + `transition: all` 7 处改具体属性（一次能解决 3 个 P0/P1）
2. **[P1] `/impeccable harden`** —— aria-selected / aria-expanded / aria-required / aria-invalid 全面补齐（MMS 走 keyboard-first，aria 是基础设施）
3. **[P1] `/impeccable polish`** —— 3 处装饰侧条（.settings-compat-note / .oc-order-note / .session-message.is-system,is-tool）改 mono kicker 文字 + soft bg 块；4 处真 per-state / per-role 例外进 spec
4. **[P1] `/impeccable audit`** —— 4 处 active 态白字 contrast 实际测算，确定 token 值
5. **[P2] `/impeccable adapt`** —— 触屏触摸目标升级 + 能力表 min-width 收窄
6. **[P2] `/impeccable layout`** —— radius 14 个非常规值收敛到 var token
7. **[P2] `/impeccable optimize`** —— 7 处 box-shadow transition 改 transform-based hover
8. **[P2] `/impeccable typeset`** —— font-weight 650/700/750 收敛到 4 档；heading 层级补 h4
9. **[P3] `/impeccable polish`** —— 收尾：小数 padding 统一、loading spinner token 化、未用 h5 删除

> 修完后重跑 `/impeccable audit` 验证分数上升。

---

## Score Recap

| 维度 | 现状 | 修完预期 |
|------|------|----------|
| Accessibility | 1 | 3（focus-visible + reduced-motion + ARIA states 修完） |
| Performance | 3 | 4（transition: all 改完 + shadow 优化） |
| Theming | 3 | 4（3 处真违规侧条 + 7 处硬编码色全部 token 化） |
| Responsive | 3 | 3-4（触屏 / 能力表 min-width 看是否再调） |
| Anti-Patterns | 2 | 4（spec 例外定义清楚，violation 全部修完） |
| **Total** | **12/20** | **18-19/20 (Excellent)** |

---

## Re-audit Command

```bash
node .claude/skills/impeccable/scripts/detect.mjs --json mms_config_web_static/index.html mms_config_web_static/config-web.css mms_config_web_static/config-web.js
```
