# T6b · 把「运行环境」设置 tab 从 5.x 回流到 4.22.x

Date: 2026-09-16
Task: Stride 370e87ec37e741df
分支：`bot/T6b-runtime-tab-backport`，**从 4.22.x 线开**（重组后是 `main`；重组尚未完成时用 `origin/dev`，本次基准 `1f466eea` = 4.22.1，等同 tag `v4.22.1`）
建议模型：gemini3.6（前端为主）
来源：owner 2026-09-16——把 5.x 里 Pilot 设置页的「运行环境」tab 回流到 4.22.x

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件、`apps/mms-web/DESIGN.md`，然后按下面"要读的代码"逐处确认。

## 背景

「运行环境」tab 当初是被 `e4b053ef Revert "merge: Bot 工作台与 Pilot 设置更新"` 从 4.21 线上摘掉的。那个 revert（101 个文件，+58 / −15715，回退的是 merge `0d9a7ffa`）**一口气移除了四样东西**：

1. Bot 工作台（全部 `Bot*.tsx` / `bot*.css` / `mms_web/bot*.py` / `tests/test_*bot*.py` / `docs/mms-web/BOT*`）
2. **「运行环境」设置 tab**（本包要回流的）
3. `/api/v1/update/history` 发布列表
4. `browser_provider`

它们当初一起进来，只是因为在同一个 merge 里，**不是因为彼此依赖**。本包要做的就是把第 2 样单独摘回来。

**这是第一次 5.x → 4.x 回流。** 所以本包除了改代码，还要产出一份"回流流程"的实际步骤，作为以后回流的模板。

## 第一个必须回答的问题：`browser_provider` 和 `/api/v1/update/history` 是不是这个 tab 的依赖

**已经调查清楚了，结论是两个都不是。但交付里必须自己复核一遍并复述结论**——这是本包的第一个交付项。

### `browser_provider` —— 不是依赖，**不要带**

- `mms_web/browser_provider.py` 只有 **25 行**，里面是一个 `typing.Protocol` 类 `BrowserProvider`。它自己的 docstring 就写着 *"Common browser capability contract used by MMS Bots."*
- 全部消费者（`origin/dev-pre` 上逐个查过）：`mms_web/bot_computer.py:21`（import）、`:35`（`class EgoComputer(BrowserProvider)`）、`mms_web/bots.py:303`、`:308`（暴露成 Bots 能力里的 `browserProvider`）、`tests/test_mms_bot_coordinator.py:29`、以及 `docs/mms-web/BROWSER-PROVIDERS.md` / `BOT-POSITIONING.md` / `BOT-ROADMAP.md` / `CLAUDE-CONTINUATION.md`。
- **每一个消费者都是 Bot 模块。**
- tab 上那排浏览器能力 chip 走的是**完全不同的来源**：`mms_platform.py:127` 的 `browser_capabilities()` → `capability_snapshot()` → bootstrap 的 `data.browser`。`mms_platform.py` 既不 import 也不提 `browser_provider`。

**⇒ 名字撞车而已。带它进 4.22.x 会为零收益引入 Bot 语义，直接违反"4.22.x 必须保持无 Bot"。留在 5.x。**

### `/api/v1/update/history` —— 不是依赖，可选，**而且它本身是干净的**

- 它是本地发布说明列表：`mms_web/updates.py:89` 的 `release_history(root=None, limit=30)` glob `docs/mms-web/RELEASE-v*.md`，用 `version_tuple` / `upgrade_notice` 解析（**这两个 4.22 的 `updates.py` 里已经有了**），倒序返回。**不联网。**
- 路由是 `mms_web/server.py:331-333`，三行一个自包含的 `if parts == ["update", "history"]`。
- 前端调用方**只有 `HelpGuide.tsx`**（`:27` state、`:55` request、`:100` / `:115` / `:139` / `:155-166` 渲染），依赖 `release-notes.ts`、`semver-sort.ts`，CSS 在 `guide.css:88-169`。
- `grep -n "运行环境\|runtime" apps/mms-web/src/HelpGuide.tsx` → **零命中**。`SettingsPage.tsx` 从不调它。
- 会不会拖进 Bot 依赖？**不会。** `release_history` 只用 `pathlib` + 两个 4.22 已有的 helper；那三行路由自包含；`HelpGuide.tsx` / `release-notes.ts` / `semver-sort.ts` / `guide.css` 一个 Bot 符号都没有。

**⇒ 和本 tab 无关。本包默认不带它。** 要回流它，另开一个包，它是干净的。

## 要读的代码（只读，先看完再动手）

5.x 侧（`origin/dev-pre` = `77f2fd8a`）：

| 位置 | 看什么 |
| --- | --- |
| `apps/mms-web/src/SettingsPage.tsx:2` | `Cpu` 加进 `lucide-react` 的 import |
| `apps/mms-web/src/SettingsPage.tsx:106-113` | 第 4 个 tab 按钮（`tab === "runtime"`，`<Cpu size={16} /> 运行环境`） |
| `apps/mms-web/src/SettingsPage.tsx:331-439` | **tab 正文**：`<section className="general-settings runtime-settings" aria-label="运行环境设置">`。平台能力卡（OS 名、`pathStyle · processControl`、`shell`）、浏览器能力 chip 与空状态兜底、三行 `preference-row` 状态（会话启动链路 / 配置模式 / 模型自动发现，各带一个 `.status-pill`）、条件显示的配置目录 / 状态目录、一行 `settings-footnote` |
| `apps/mms-web/src/SettingsPage.tsx:277`、`:331` | `) : tab === "usage" ? (` / `) : (` 这条链的结构。**5.x 是四路，4.22 是三路加一层额外括号**——这是主要的手工活 |
| `apps/mms-web/src/studio.css:1093-1181` | `/* Runtime environment capability card and chips … */`：`.runtime-settings`(1094)、`.platform-capability-header`(1098)、`.platform-capability strong`(1105)、`.platform-meta`(1112)、`.platform-meta code`(1116)、`.platform-browser-capabilities`(1124)、`.capability-chip`(1129)、`.capability-chip strong`(1141)、`.capability-chip .chip-indicator`(1147)、`.capability-chip.unavailable`(1154/1160)、`.status-pill`(1163)、`.status-pill.active`(1174)、`.status-pill.muted`(1178) |
| `apps/mms-web/src/studio.css:1578` | `.platform-capability` 的基础规则 |
| `mms_platform.py:18-40 / 43-60 / 127-157 / 160-164` | `PlatformDescriptor`、`BrowserCapability`、`browser_capabilities()`、`capability_snapshot()` |
| `mms_web/server.py:17`、`:125` | `from mms_platform import capability_snapshot`；bootstrap 里 `**capability_snapshot(),` |
| `apps/mms-web/tests/settings-runtime-updates.test.mjs` | 混装文件，见下面"测试怎么拆" |

4.22 侧（`origin/dev` = `1f466eea`）：

| 位置 | 看什么 |
| --- | --- |
| `apps/mms-web/src/SettingsPage.tsx:81` | `tab` state |
| `apps/mms-web/src/SettingsPage.tsx:87-88 / 94-95 / 101-102` | 现有三个 tab：模型与通道 `models` / 外观 `appearance` / 使用 `usage` |
| `apps/mms-web/src/SettingsPage.tsx` `</nav>` 与 `{tab === "models" ?` 之间 | **4.22 已经有一个常驻的 `<section className="platform-capability">`**（不在 tab 里），只显示 `os` / `pathStyle` / `processControl` + 简单 chip。**回流时要决定它和新 tab 的关系** |
| `apps/mms-web/src/studio.css:1476-1479` | 旧的 `.platform-capability` 简写规则（回流时会被 1093-1181 那批取代） |
| `apps/mms-web/src/studio.css:1012-1017` | 设置壳的布局，5.x 侧对应 `1028-1046`（滚动 / 内距行为，测试会盯） |
| `mms_web/server.py:17`、`:118` | **4.22 已经有** `from mms_platform import capability_snapshot` 和 `**capability_snapshot(),` |
| `apps/mms-web/src/types.ts:240-258` | **4.22 已经声明了** `Bootstrap.platform` 和 `Bootstrap.browser`，形状与 5.x 相同 |
| `tests/test_mms_web_windows_imports.py:1-10 / 17-22 / 48-54` | docstring、`ROOT` 与 `IMPORT_GRAPH`、`failures = {...}; assert not failures` 的写法 |

## 最重要的调查结论：这是一次纯前端回流

- `mms_platform.py` 在 `v4.22.1` 和 `origin/dev-pre` 上**逐字节相同**。
- 4.22 的 `mms_web/server.py` **已经有** `from mms_platform import capability_snapshot`（**17** 行）和 bootstrap 里的 `**capability_snapshot(),`（**118** 行）。
- 4.22 的 `apps/mms-web/src/types.ts` **已经声明了** `Bootstrap.platform` 和 `Bootstrap.browser`（**240-258** 行），形状一致。
- tab 本身**不发任何请求**，也**不吃任何新 props**——它只读 `data: Bootstrap`，用到 `data.platform.{os,pathStyle,processControl,shell,configRoot,stateRoot}`、`data.browser[].{backend,supported,loggedIn,reason}`、`data.capabilities.{launch,configure,discoverModels}`。

**⇒ 本包不需要改任何 Python。** 如果你发现自己在改 `mms_web/`，停下来重新确认。

### tab 是 Bot-free 的（已验证）

`grep -n "Bot\|bot" apps/mms-web/src/SettingsPage.tsx apps/mms-web/src/ModelExplorer.tsx` → **零命中**。`SettingsPage.tsx` 的全部 import：`react`、`lucide-react`、`./types`（`Bootstrap`）、`./RemoteAccess`、`./Models`、`./App`（`FONT_FAMILIES`）、`./components`（`AppVersion`、`Dialog`）、`./SkillSources`。没有 `bot.css`，没有 `bot-*` class，服务端那条路径上没有 `mms_web/bot*`。

## 本包的改动面：两个文件

**这是一次纯前端回流。**

| 文件 | 改什么 |
| --- | --- |
| `apps/mms-web/src/SettingsPage.tsx` | `Cpu` import、第 4 个 tab 按钮、tab 正文、三元链结构对齐 |
| `apps/mms-web/src/studio.css` | 搬 `1093-1181` 那块运行环境样式，删掉 4.22 被取代的旧 `.platform-capability` 简写（`1476-1479`） |

加上新增的测试文件和文档。**没有 Python 改动**——4.22 的 `server.py:17/118` 和 `types.ts:240-258` 已就绪，`mms_platform.py` 两线逐字节相同。如果你发现自己在改 `mms_web/`，停下来重新确认。

### 以下都不属于这个 tab，本包不要碰

逐个查过，它们只是当初和 tab 在同一个 merge 里进来的，彼此没有依赖：

| 文件 | 它其实是什么 |
| --- | --- |
| `apps/mms-web/src/ModelExplorer.tsx` | launch-facts 出错时的内联"重试"按钮（`RotateCcw`、`retry` state），配套 `styles.css` 的 `.inline-alert-retryable` / `.inline-retry-button` |
| `apps/mms-web/src/channel-models.css` | 设置表单布局（`.channel-models` 全宽、`.channel-save` 吸底） |
| `apps/mms-web/src/guide.css` | 全是 `.guide-updates` / `.update-history-*`，属于 `/update/history` |
| `mms_web/updates.py` | 只有 `release_history()`，属于 `/update/history` |
| `tests/test_mms_web_updates.py` | 同上 |

### ⛔ `studio.css` 的 diff 里混着两条 Bot 规则 —— 绝对不许抄

这是本包最容易踩的坑。搬 `studio.css` 的时候，**这两条不在 `1093-1181` 范围内，但会出现在你 diff 的视野里**：

- `origin/dev-pre:apps/mms-web/src/studio.css:41-51` —— 主题过渡选择器列表里的 **`.bot-workspace`**
- `origin/dev-pre:apps/mms-web/src/studio.css:448-449` —— **`.sidebar-footer.has-bots-entry`**、**`.sidebar-footer.has-bots-entry .bot-entry`**

它们和运行环境 tab 毫无关系，只是恰好在同一个文件里。**抄进 4.22.x 就直接破了"4.22.x 必须保持无 Bot"这条硬约束**，而且 CSS 不会报错，只会静悄悄地留在那里等着被 `grep -i bot` 抓到。**搬完 `studio.css` 立刻 `grep -in bot apps/mms-web/src/studio.css`，必须零命中。**

### 范围外项：`/api/v1/update/history`

调查结论是它**自包含且 Bot-free**（`updates.py:89` 的本地 glob + `server.py` 三行自包含路由 + 只被 `HelpGuide.tsx` 调用，依赖 `release-notes.ts` / `semver-sort.ts` / `guide.css`，一个 Bot 符号都没有）。

**但本包不做。** 它不是运行环境 tab 的依赖，**可以另开一个包独立回流**。本包的实现者不要顺手把它带上。

## 硬约束：只回流 tab 本身，不带 Bot 工作台任何部分

**4.22.x 必须保持无 Bot。这是本包的第一硬约束。**

`git ls-tree -r --name-only origin/dev | grep -i bot` 今天返回**零条**。本包做完必须仍然是零条。

**交付时要逐文件说明：动了哪些文件，为什么每一处都与 Bot 无关。** 不接受"我看了一眼没问题"。

## 要做成什么

### A. 把 tab 搬过去

1. `SettingsPage.tsx:2` 加 `Cpu` 到 lucide import。
2. 在现有三个 tab 按钮后面加第 4 个（照 `origin/dev-pre:106-113`）。`tab` state（4.22 的 `:81`）的联合类型加 `"runtime"`。
3. 把 `origin/dev-pre:331-439` 那个 `<section className="general-settings runtime-settings">` 整段搬过来。
4. **处理三元链的结构差异**：5.x 是 `models / appearance / usage / runtime` 四路，4.22 是三路加一层额外括号包裹。**这是本包唯一需要动脑的手工活**，不要机械 `git cherry-pick`，改完先跑 `tsc`。
5. `studio.css` 把 `origin/dev-pre:1093-1181` 那一整块搬过来，**并删掉 4.22 的 `studio.css:1476-1479` 那批被取代的旧 `.platform-capability` 简写**，避免两套规则打架。
6. **决定 4.22 那个常驻的 `<section className="platform-capability">` 怎么办。** 它现在在 `</nav>` 和 tab 内容之间，永远显示，内容是新 tab 的子集。**本包默认：把它移进新 tab，页面上不留重复。** 如果保留会造成"同一份信息显示两遍"，那是回归。这条要在交付里说明实际处置。

### B. 测试怎么拆

`origin/dev-pre:apps/mms-web/tests/settings-runtime-updates.test.mjs` 是一个混装文件：

| 行 | 属于 |
| --- | --- |
| 7 | `import ../src/semver-sort.ts` —— **4.22 上不存在这个文件** |
| 12-36 | semver 块 |
| **38-51 / 53-67 / 69-80 / 82-93 / 95-109** | **运行环境 tab —— 这些才是本包要的** |
| 111-116 | WhatsNew |
| 118-134 | `/update/history` |
| **136-178** | **Bot —— 必须整段删掉** |
| 180-188 | ModelExplorer 重试按钮 |

**本包只搬 38-51 / 53-67 / 69-80 / 82-93 / 95-109 这五段**，去掉第 7 行的 `semver-sort` import 和 12-36 块（除非你连 `semver-sort.ts` 一起回流，本包默认不）。文件名建议改成能反映实际内容的（例如 `settings-runtime.test.mjs`），别沿用那个混装名字。

### C. 加一条"4.22.x 上不存在任何 Bot 模块"的断言

**这条断言仓库里还不存在，本包从零写。** 不要去 `tests/test_mms_web_windows_imports.py` 里找一条现成的"no Bot modules"断言——**那里面没有**。那个文件钉的是 fcntl 契约（65 行，两条线逐字节相同），它和 Bot 唯一的关系是 commit `92df3582` 把 docstring 里提到的 Bot 文件名删掉了，因为 4.21 线上那些文件不存在。**那是一次 docstring 清理，不是断言。**

可复用的只是**写法**，就在那个文件里：`ROOT` 和 `IMPORT_GRAPH` 的构造在 **17-22** 行，`failures = {…}; assert not failures, f"…: {failures}"` 的断言惯例在 **48-54** 行。照这个形状写你自己的新断言。

断言至少覆盖：

```python
list((ROOT / "mms_web").glob("bot*.py")) == []
list((ROOT / "apps/mms-web/src").glob("Bot*.tsx")) == []
list((ROOT / "apps/mms-web/src").glob("bot*.css")) == []
list((ROOT / "tests").glob("test_*bot*.py")) == []
# 再加一条：SettingsPage.tsx 的源码里不含 "bot" 子串（大小写不敏感）
```

**放哪里**：本包默认新开一个 `tests/test_mms_4_22_no_bot.py`，因为 `test_mms_web_windows_imports.py` 钉的是 fcntl 契约，和这条正交。如果 owner 更希望塞进那个文件，写进"需要 Fable 确认"。

### D. 产出「回流流程」模板（本包的第二个交付项）

**这是第一次 5.x → 4.x 回流，以后还会有。** 交付里要记录一份实际走过的步骤，至少包含：

1. 怎么确定改动边界（本包的做法：从当初那个 revert 的 diff 里按"关注点"分类，再逐个 grep 验证依赖方向）
2. 怎么证明不带进不该带的东西（本包的做法：import 清单 + `grep -i bot` + `git ls-tree | grep -i bot` 前后对比）
3. 混装测试文件怎么拆
4. 两条线结构不同的地方怎么手工对齐（本包的三元链）
5. 门禁跑哪些、基线数字在哪里取
6. 踩到的坑

写成 `docs/mms-web/BACKPORT-5X-TO-4X.md` 或追加到现有文档，位置在交付里说明。

## 关于 base 分支：为什么是 4.x 侧

**base = 4.22.x 线**（重组后是 `main`；今天是 `origin/dev` / `v4.22.1`）。回流的目标就是 4.22.x，改动只能落在那里。

owner 定的流向是"4.x 的所有改动默认进入 5.x"，所以这次回流之后 4.22.x 上的 `SettingsPage.tsx` 会再往 5.x 流一次。**5.x 上已经有这个 tab 了**，所以合的时候大概率是一次 no-op 或小冲突——**要在交付里提醒下一个做合流的人注意这一点**，别把 4.22 那份（可能被你改过结构的）盖掉 5.x 那份。

## 只许改

**只有两个产品文件**（其余是新增的测试与文档）：

- `apps/mms-web/src/SettingsPage.tsx`
- `apps/mms-web/src/studio.css`
- 新增 `apps/mms-web/tests/settings-runtime.test.mjs`（从混装文件里摘出来的五段）
- 新增 `tests/test_mms_4_22_no_bot.py`
- 新增或追加回流流程文档
- `apps/mms-web/DESIGN.md`：如果 tab 带进了新的 token / class 约定，补写进去

## 不许改

- **任何 `mms_web/**` Python**（本包是纯前端；后端在 4.22 上已经就绪。发现缺口写进"需要 Fable 确认"，不要自己补后端）
- **任何会把 Bot 带进 4.22.x 的东西**。包括但不限于 `mms_web/browser_provider.py`、任何 `Bot*.tsx`、任何 `bot*.css`、`studio.css` 里那两条 Bot 规则（41-51 的 `.bot-workspace`、448-449 的 `.sidebar-footer.has-bots-entry`）
- `mms_web/updates.py` 的 `release_history` 与 `/api/v1/update/history`（另开包）
- `apps/mms-web/src/ModelExplorer.tsx`、`channel-models.css`、`guide.css`、`HelpGuide.tsx`、`release-notes.ts`、`semver-sort.ts`
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`、`install.sh`
- 真实 `~/.config/mms*`
- 不加依赖（`Cpu` 已在 lucide-react 里）
- **不要重启 60824，不要动 8767**（owner 在用的实例）

## 门禁

```bash
# 1. 后端定向
python3 -m pytest tests/test_mms_web_updates.py tests/test_mms_release_version.py -q

# 2. 类型
npx tsc --noEmit -p apps/mms-web

# 3. 前端单测（必须带 glob）
node --test apps/mms-web/tests/*.test.mjs

# 4. 构建
npm run build --workspace @mms/web

# 5. 完整版新用户 gate
python3 scripts/regression_fresh_user_gate.py

# 6. 专门的无 Bot 断言
PYTHONPATH=. python3 -m pytest -q tests/test_mms_4_22_no_bot.py

# 7. 手工复核（两条都应当返回零命中）
git ls-tree -r --name-only HEAD | grep -i bot
grep -in bot apps/mms-web/src/studio.css
```

**4.22.x 侧的基线（2026-09-16 核对，跑之前先 `npm install`）：**

- `apps/mms-web/tests/*.test.mjs` 在 4.22 上只有 **7 个文件**：`composer-keys`、`markdown-reading`、`message-control`、`model-selection`、`side-questions`、`time`、`whats-new`。**通过数以你在 base ref 上实测的为准，不要照抄 5.x 的 121**（那是 19 个文件的数）。开工第一件事就是在 base 上跑一遍拿到基线数字，写进交付。
- `apps/mms-web/tsconfig.json` 的 `include` 只有 `["src"]`，**所以 `npx tsc --noEmit -p apps/mms-web` 不会检查 `apps/mms-web/tests/*.mjs`**。别指望 tsc 帮你抓测试文件的问题。
- `tests/test_mms_release_version.py` 会断言 `package.json` / `apps/mms-web/package.json` / `apps/mms-web/package-lock.json` 三处版本都等于 `VERSION`，并且 `docs/mms-web/RELEASE-v{VERSION}.md` 存在。**本包不改版本号**，这条只是确认你没碰坏。
- `scripts/regression_fresh_user_gate.py` 的 `_PYTEST_TARGETS`（57-83 行）已经包含 `tests/test_mms_release_version.py`（:57）和 `tests/test_mms_web_updates.py`（:60）。
- gate 在这台机器上本来就有既存失败项，**用与既存失败集的 diff 判断，不看绝对值**。第 5 条必须跑完整版，不许只跑 `--quick`。

## 真实验证（不是可选项）

用 ego-browser 在**隔离实例**上验证，**不要重启 60824，不要动 8767**：

```bash
cd .worktrees/wt-T6b
npm install
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61755 \
  --state-root /tmp/bot-verify-t6b \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

截图全部存到 `docs/mms-web/design/t6b/`。

## 验收清单（逐条可勾）

调查（**第一个交付项**）：

- [ ] 独立复核并复述结论：`browser_provider` 不是运行环境 tab 的依赖，不带；给出证据（消费者清单 + tab 的实际数据来源）。
- [ ] 独立复核并复述结论：`/api/v1/update/history` 不是运行环境 tab 的依赖，不带；给出证据（调用方清单）。
- [ ] 回答：带上这两个会不会把 Bot 依赖拖进来。逐个给 yes/no 加证据。
- [ ] 确认这是一次纯前端回流（4.22 的 `server.py:17/118` 和 `types.ts:240-258` 已就绪，`mms_platform.py` 两线逐字节相同）。如果你的复核与此不符，**停下来报告**。

实现：

- [ ] 「运行环境」tab 出现在设置页，与现有三个 tab 并列。截图。
- [ ] tab 内容显示平台能力卡（OS、`pathStyle · processControl`、shell）。截图。
- [ ] 浏览器能力 chip 正常显示，且**空状态有兜底**（造一次没有浏览器能力的情况）。截图两张。
- [ ] 三行状态（会话启动链路 / 配置模式 / 模型自动发现）各自的 `.status-pill` 显示正确。截图。
- [ ] 配置目录 / 状态目录的条件显示正确。截图。
- [ ] 4.22 原来那个常驻 `<section className="platform-capability">` 已处置，**页面上没有同一份信息显示两遍**。截图 + 说明实际处置。
- [ ] `studio.css` 里旧的 `.platform-capability` 简写（4.22 的 1476-1479）已删，没有两套规则打架。
- [ ] 三元链结构改对了，`tsc` 0 错。

硬约束（**逐条说明**）：

- [ ] **逐文件说明：动了哪些文件，为什么每一处都与 Bot 无关。** 不接受概括性结论。
- [ ] `studio.css` 里那两条 Bot 规则（dev-pre 的 41-51 的 `.bot-workspace`、448-449 的 `.sidebar-footer.has-bots-entry`）**没有**被抄过来。逐条确认。
- [ ] `grep -in bot apps/mms-web/src/studio.css` **零命中**。
- [ ] `git ls-tree -r --name-only HEAD | grep -i bot` 返回零条。
- [ ] `mms_web/browser_provider.py` 不存在于本分支。
- [ ] `tests/test_mms_4_22_no_bot.py` 存在且通过，覆盖 `mms_web/bot*.py` / `Bot*.tsx` / `bot*.css` / `test_*bot*.py` 四类 glob 加 `SettingsPage.tsx` 不含 `bot` 子串。
- [ ] 没有改任何 `mms_web/**` Python。

测试：

- [ ] 混装测试文件只摘了运行环境那五段（38-51 / 53-67 / 69-80 / 82-93 / 95-109），**Bot 那段（136-178）没有被带进来**。
- [ ] 没有引入 `semver-sort.ts`（或：引入了并说明理由）。
- [ ] 新测试文件名反映实际内容，不是 `settings-runtime-updates`。

门禁：

- [ ] 先在 base ref 上跑一遍拿到基线，**基线数字写进交付**（node test 通过数、pytest 通过数）。
- [ ] `python3 -m pytest tests/test_mms_web_updates.py tests/test_mms_release_version.py -q` 全过。
- [ ] `npx tsc --noEmit -p apps/mms-web` → 0。
- [ ] `node --test apps/mms-web/tests/*.test.mjs` → 全过，数量 ≥ 基线 + 你新增。
- [ ] `npm run build --workspace @mms/web` 通过。
- [ ] `python3 scripts/regression_fresh_user_gate.py` **完整版**通过（与既存失败集 diff 为空）。
- [ ] 截图全部在 `docs/mms-web/design/t6b/`。
- [ ] 没有重启 60824，没有动 8767。

回流流程模板（**第二个交付项**）：

- [ ] 产出一份"回流流程"文档，覆盖上面 D 的六点，位置在交付里说明。
- [ ] 提醒下一个做 4.x → 5.x 合流的人：5.x 上已有这个 tab，合的时候别用 4.22 这份盖掉 5.x 那份。

## 并行规则

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git fetch origin
git worktree add .worktrees/wt-T6b -b bot/T6b-runtime-tab-backport origin/dev   # 重组完成后用 origin/main
cd .worktrees/wt-T6b && npm install
```

端口 61755。不碰 60824 和 8767。**不提交、不 push、不 merge。**

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T6b
分支 / worktree / base ref（含实际 commit）：
改动文件：git diff --stat 输出
调查结论：browser_provider 与 /update/history 的依赖判定，逐条证据
Bot 隔离说明：逐文件说明为什么每一处都与 Bot 无关；git ls-tree | grep -i bot 的输出
基线数字：base ref 上实测的 node test / pytest 通过数
测试：tsc、node --test（对比基线）、pytest、build、fresh-user gate（与既存失败集 diff）、无 Bot 断言
真实验证：端口、验收清单逐条结果、截图路径
回流流程模板：文档位置 + 六点是否齐全
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

## 需要 Fable 确认

1. **`origin/main` 还不是 4.22 线**（现在是 4.10.0，HEAD `ca6c09eb`）。本包 base 写成"4.22.x 线（重组后是 `main`）"，今天实际用 `origin/dev` / `v4.22.1`。重组时点由 owner 决定。
2. **4.22 那个常驻的 `platform-capability` section 怎么处置。** 本包默认移进新 tab（避免重复显示）。如果 owner 希望保留常驻卡片、tab 只做扩展，那是另一种形状，请确认。
3. **无 Bot 断言放哪里。** 本包默认新开 `tests/test_mms_4_22_no_bot.py`，理由是 `test_mms_web_windows_imports.py` 钉的是 fcntl 契约，两者正交。如果 owner 希望合并进去，请确认。
4. **`ModelExplorer.tsx` 的内联重试按钮要不要顺带回流。** 它不是 tab 的一部分，但当初是同一个 merge 进来的，配套 `styles.css` 的 `.inline-alert-retryable` / `.inline-retry-button`。本包默认**不带**。
5. **`channel-models.css` 的设置表单布局改进要不要顺带回流。** 同上，默认不带。
6. **`/api/v1/update/history` 已定为本包范围外。** 调查结论是它干净、可独立、Bot-free，可以另开一个包回流。这里只是提醒排期，本包不做。
7. **`studio.css` 的设置壳布局重写（4.22 的 1012-1017 → 5.x 的 1028-1046）要不要一起带。** 5.x 的测试会盯这段的滚动 / 内距行为。本包默认只带 tab 必需的 1093-1181，如果摘出来的测试要求那段布局，会在实现时暴露——到时按实际情况处置并在交付里说明。
