# T7a · 连接横幅与真实连接状态脱节

Date: 2026-09-16
Task: Stride 370e87ec37e741df
建议模型：gemini3.6（纯前端）
来源：owner 2026-09-16——"怎么总有这个报错啊 好烦"（顶部红条反复出现，底下对话正常工作）

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件，然后按下面"要读的代码"逐处确认。

**本包与 T7b 互相独立，可以并行**，两个包都建议给 gemini。两者改动面零重叠：T7a 只动 `App.tsx` 的 `load()` 失败处理与顶部横幅渲染；T7b 只动 `SideQuestions.tsx` / `side-questions.ts` 与 `App.tsx` 里 `<SideQuestions>` 那一处挂载。唯一共享文件是 `App.tsx`，两处相距一千多行，合的时候不会真冲突。

---

## base 分支判定（T7a / T7b 共用，2026-09-16 实测）

### 结论

| 项目 | 分支 | 依据 |
| --- | --- | --- |
| **实现 PR 的 base** | **`main`（4.22.1，`6c62a656`）** | 本包要改的代码在两条线上逐字节相同；owner 定的流向是"4.x 的所有改动默认进入 5.x"，所以修在 4.22.x 会自动流到 5.x，反过来不会回到 4.x |
| 本工作包文档所在分支 | `dev`（5.0.1，`5bf1f31d`） | `docs/mms-web/bot-work/` 整个目录（含 README 索引和 T1–T6 十九份包）**只存在于 `dev`**，`origin/main` 上没有这个目录。文档放 `main` 会另起一棵孤立的文档树，并在 4.x→5.x 合流时和 `dev` 的 README 必然冲突 |

这和 T6a / T6b 是同一个形状：包文档在 5.x 的文档树里，实现落在 4.22.x 线上。

### 实测证据

发布线重组已经完成（README 里"分支现状"那张表是重组前的，已在本轮一并订正）：

```
origin/main  6c62a656  package.json version = 4.22.1
origin/dev   5bf1f31d  package.json version = 5.0.1
origin/dev-pre 2b9260d8  闲置
```

逐文件比对 blob hash（`git rev-parse origin/<b>:<path>`）：

| 文件 | main | dev | 判定 |
| --- | --- | --- | --- |
| `apps/mms-web/src/api.ts` | `5ba09216` | `5ba09216` | **逐字节相同** |
| `apps/mms-web/src/SideQuestions.tsx` | `7e30d56a` | `7e30d56a` | **逐字节相同** |
| `apps/mms-web/src/side-questions.ts` | `68399708` | `68399708` | **逐字节相同** |
| `apps/mms-web/tests/side-questions.test.mjs` | 同 | 同 | **逐字节相同** |
| `apps/mms-web/src/App.tsx` | `beed496a` | `e8b89e91` | 差 64 行 |
| `apps/mms-web/src/styles.css` | `fa48b069` | `0832c54f` | 差 49 行 |

两个差异文件的差异**都不落在本轮两个包要改的地方**：

- `App.tsx` 的 64 行差异**全部是 Bot 工作台接线**：`BotIcon` import、`BotStudio` import、`isGuideReady()` 抽函数、`page` 初值读 `#page=bots`、`navigate` / `beginGuideStep` / `startIntroduction` / `guideNavigate` 里的 `bots` 分支、侧栏 `.has-bots-entry` 入口按钮、topbar 的 `bots` 文案、`{page === "bots" && <BotStudio …>}`、以及 5.x 删掉的那行 `<WhatsNew ready={…} />`。
- 逐段 `diff` 验证过本包关心的四个区域在两条线上**逐字节相同**：`load()` 整体、8 秒轮询 `useEffect`、`{error && (…)}` 红条渲染、`runAction()` 整体。
- `styles.css` 的 49 行差异只有两块：`ModelExplorer` 的内联重试按钮（`.inline-alert-retryable` / `.inline-retry-button`，5.x 独有）和 `.model-picker-trigger` 的布局重写。`.error-banner`（595 / 604 行）和 `.connection-status`（496–511 行）两条线**行号与内容都相同**。

### 对实现者的要求

- **在 `main` 上开分支**。做完在交付里写明 base ref 的实际 commit。
- 5.x 侧唯一需要留意的差异：`apps/mms-web/src/bot.css:67` 有一条 `.app-shell[data-page="bots"] > .main-area > .error-banner` 的位置修正（5.x 独有）。你在 4.22 上改的是 `App.tsx` 的渲染结构和 `styles.css` 的 `.error-banner`，不碰 `bot.css`；但如果你给红条换了 class 名或改了它在 DOM 里的位置，**要在交付里点名提醒下一个做 4.x→5.x 合流的人去看这条规则**。默认做法是**不改 class 名、不改它在 `<main className="main-area">` 里的位置**，这样 5.x 那条规则继续生效。

### 下面所有行号都给两套

owner 给的行号是在 `origin/dev` 上读的。本文件两套都列，**以 `main` 那一列为准**（实现 base）。凡与 owner 原话不一致的都已标出。

---

## 症状

顶部反复出现红色阻断横幅：

> 无法连接 MMS 本地服务。恢复连接后，可再次发送同一请求。

而**底下的对话在正常工作**——会话在刷新、消息能发出去。横幅和真实连接状态脱节。

## 根因（已查明，实现者要在 base 分支上复核一遍）

### 1. 文案来自 `api.ts`，任何一次网络层失败都抛它

`apps/mms-web/src/api.ts:38`（**owner 原话说 37，实测是 38，差 1**；两条线同）：

```ts
  }).catch((error) => {
    if (signal?.aborted) throw error;
    throw new Error("无法连接 MMS 本地服务。恢复连接后，可再次发送同一请求。");
  });
```

这是 `request()` 里 `fetch(...)` 的 `.catch()`。它不区分"后台轮询超时"和"用户点了发送但发不出去"——**两者抛的是同一句话**。

### 2. `load()` 一次失败立刻置红，一次成功立刻清掉

| 位置 | main | dev |
| --- | --- | --- |
| `const load = useCallback(async (signal?: AbortSignal) => {` | `App.tsx:412` | `435` |
| 成功：`setConnected(true)` | `417` | `440` |
| 成功：`setError("")` | `418` | `441` |
| 失败：`setConnected(false)` | `433` | `456` |
| 失败：`setError((e as Error).message \|\| "无法连接 MMS 本地服务。")` | `434` | `457` |

owner 说的"约 435-462"是 dev 上 `load()` 的范围，对；main 上是 `412-439`。

### 3. 8 秒轮询

| 位置 | main | dev |
| --- | --- | --- |
| `const timer = setInterval(() => {` | `App.tsx:611` | `634` |
| `if (!mutation.current) void load();`，`}, 8000);` | `612` / `613` | `635` / `636` |

owner 说的"约 632-638"是 dev，实测 `634-638`（差 2）；main 上是 `611-615`。

### 4. 所以：没有重试、没有防抖、没有宽限期

一次失败立刻弹红条，一次成功清掉。任何瞬时抖动（Pilot 重启、睡眠唤醒、请求变慢、网卡切换）都会画出这条警报，8 秒后自愈，然后下次抖动再来一次。owner 看到的就是这个。

### 5. `mutation.current` 不是泄漏源 —— 不要去改那里

`mutation.current` 的复位在 `runAction()` 的 `finally` 里：

| 位置 | main | dev |
| --- | --- | --- |
| `mutation.current = true;` | `App.tsx:765` | `803` |
| `} finally { mutation.current = false;` | `792` | `830` |

owner 说的"约 830"是 dev，对；main 是 `792`。**它有 `finally` 兜底，不会泄漏成永久 true。** 写在这里是为了让你不要往这个方向找原因、更不要顺手去"修"它。轮询被 `mutation.current` 跳过是设计（写操作进行中不要用后台读覆盖 UI），不是 bug。

### 6. 仓库里**已经有**一个安静的连接指示，而且它做对了

这是本包最重要的一条：红条并不是唯一的连接信号，只是唯一吵的那个。

**侧栏底部的连接胶囊**（`connection-status`）：

| 位置 | main | dev |
| --- | --- | --- |
| `className={"connection-status " + (connected && !statusesStale ? "online" : "offline")}` | `App.tsx:1579` | `1625` |
| 整段 `<span>` | `1577-1586` | `1623-1632` |
| `styles.css` 的 `.connection-status` / `.online` / `.offline` | `496-511` | `496-511` |

它的文案是"服务在线" / "需要连接"，`online` 用 `--success`，`offline` 用 `--danger` 的**描边**（不是整条背景），不阻断任何内容。

**而且另一条轮询已经是这个做法了**：会话列表每 1 秒轮询一次（`document.hidden` 时 4 秒），失败时**只翻一个布尔量，从不碰 `error`**：

| 位置 | main | dev |
| --- | --- | --- |
| 成功 `setStatusesStale(false);` | `App.tsx:646` | `669` |
| 失败 `catch { … setStatusesStale(true); }` | `649` | `672` |

**结论：这个应用对"后台轮询失败"已经有一套安静、自愈、只改指示灯的处理方式，`load()` 是唯一一个走红条的例外。** 本包要做的就是把 `load()` 拉齐到这套已有做法上，不是发明新机制。

## 核心设计问题

**一个 `error` state 同时承载两件不该混的事：**

| | 后台轮询失败 | 用户操作失败 |
| --- | --- | --- |
| 来源 | `load()` 的 catch（8 秒一次，自动） | `runAction()` 的 catch（用户点了才有） |
| 性质 | 自愈的背景噪音 | 真的需要用户看见并重发 |
| 现在的表现 | **红色阻断横幅** | **红色阻断横幅** |

现在它们渲染成一模一样的东西，结果是真正要紧的"你的消息没发出去"被噪音淹没了。用户学会无视这条红条的那一刻，这个提示就彻底失效了。

代码里**已经有**独立的 `connected` 状态（`setConnected`，main `App.tsx:210` / dev `231`），只是没被用来做这个区分——红条的显示条件是 `{error && (…)}`，不是 `{!connected && …}`。

## 要读的代码（只读，先看完再动手）

| 位置（main / dev） | 看什么 |
| --- | --- |
| `api.ts:38` / `38` | 文案的唯一出处；`request()` 的 fetch catch |
| `App.tsx:210-212` / `231-233` | `connected`、`statusesStale`、`error` 三个 state 的声明，挨在一起 |
| `App.tsx:412-439` / `435-462` | `load()` 全文 |
| `App.tsx:611-615` / `634-638` | 8 秒轮询 |
| `App.tsx:643-676` / `666-699` | 1 秒会话轮询：**已有的安静失败处理范本** |
| `App.tsx:1577-1586` / `1623-1632` | **已有的安静连接指示** |
| `App.tsx:1655-1671` / `1705-1721` | 红条渲染（见下） |
| `App.tsx:663` / `686` | `setError("配置正在保存，请等待保存结束后离开。")` |
| `App.tsx:765-794` / `803-832` | `runAction()` 全文，含 `setError("")`（main 767 / dev 805）和 catch 里的 `setError((e as Error).message)`（main 789 / dev 827） |
| `styles.css:595-606` | `.error-banner` |
| `styles.css:1914` / `1939` | 窄屏下 `.error-banner` 的 padding 覆盖 |
| `styles.css:496-511` | `.connection-status` |

红条渲染（main `1655-1671`，dev `1705-1721`，两条线内容相同）：

```tsx
{error && (
  <div className="error-banner" role="alert">
    <CircleAlert size={17} />
    <span>{error}</span>
    {!connected && (
      <button className="text-button" onClick={() => void load()}>
        重新连接
      </button>
    )}
    <button
      className="icon-button"
      aria-label="关闭错误提示"
      onClick={() => setError("")}
    >
      <X size={16} />
    </button>
  </div>
)}
```

## `setError` 全部调用点的归类（已查清，实现者要复核并在交付里逐条复述）

`grep -n "setError" apps/mms-web/src/App.tsx` 在两条线上都只有 7 处，其中一处是声明。**没有第 7 处以外的调用点，也没有把 `setError` 传出去给子组件的地方**（已确认：`setError` 不出现在任何 JSX prop 里）。

| # | main | dev | 代码 | 类别 | 处置 |
| --- | --- | --- | --- | --- | --- |
| 0 | `212` | `233` | `const [error, setError] = useState("");` | 声明 | 保留；按方案可能拆成两个 state |
| 1 | `418` | `441` | `load()` 成功路径 `setError("")` | **连接** | 改：清连接失败计数，并清掉连接类提示 |
| 2 | `434` | `457` | `load()` 失败路径 `setError(msg)` | **连接** | 改：**不再直接置红条**，改为累加失败计数 |
| 3 | `663` | `686` | `requestNavigation()` 里 `setError("配置正在保存，请等待保存结束后离开。")` | **操作（业务提示）** | **保持红条**。它是用户点了导航才触发的，必须看见 |
| 4 | `767` | `805` | `runAction()` 开头 `setError("")` | **操作** | 保持：新操作开始前清掉上一条操作错误 |
| 5 | `789` | `827` | `runAction()` catch `setError((e as Error).message)` | **操作** | **保持红条，且必须醒目**。这就是"你的消息没发出去" |
| 6 | `1667` | `1717` | 关闭按钮 `onClick={() => setError("")}` | 渲染 | 保持：可关闭语义不许丢 |

**注意 #3 和 #5 共用同一个红条渲染。** 把 #2 从红条里摘出去之后，红条只剩 #3 和 #5 两个来源，两者都是用户动作的直接后果——这正是想要的结果。

**#5 的错误文本可能就是 `api.ts:38` 那句话**（用户点发送时服务真的断了，`mutate()` 走的也是 `request()`）。**这是对的，不要因为文案相同就把它一起降噪。** 判断依据是**谁触发的**，不是文案长什么样。

## 要做成什么

### A. 连接失败不要第一次就报警

- 连续失败 **2–3 次**（8 秒一轮，约 16–24 秒）才提示。**任意一次成功立刻清零计数并清掉提示。**
- 计数放 `useRef`（不需要触发重渲染），或一个 `consecutiveFailures` state，两种都行，在交付里说明选了哪种、为什么。
- **不要引入新的轮询、不要新增任何网络请求、不要改 8000 这个间隔。** 只改现有 `load()` 的失败处理。
- 首次加载（`loading === true`）时的失败怎么算，自己定一个说得通的规则并写进交付。默认建议：首次加载失败也走同一个计数器，因为首屏一次抖动同样不该直接砸一条红条上去。

### B. 把两类错误分开

- **连接健康度**用 `connected`（必要时加 `statusesStale`）驱动一个**安静的**指示。owner 给的例子是"顶部一条细的『重连中…』"。
  - 已有的侧栏 `connection-status` 胶囊是现成的样式语言，**优先复用它的视觉**（描边 + 小圆点 + 短文案），不要造新的视觉体系。
  - 允许的形态：顶部一条细条（不用 `--danger-bg` 整条铺底）、或直接强化已有的侧栏胶囊。选哪种、为什么，写进交付并附截图。
  - **不要用红色阻断式横幅。**
- **红色横幅只保留给用户操作失败**（上表的 #3 和 #5）。

实现上建议把 `error` 拆成两个 state（例如 `error` 只留操作失败、新增 `connectionNotice` 或直接用 `connected` + 计数推导），**不要**继续用一个字符串 state 加前缀 / 标记位去区分——那是把同一个坑挖深。如果你选了别的做法，在交付里说明理由。

### C. 硬验收项：不许一刀切把该看见的也降噪了

按 owner "功能要么做完要么不做"的原则，下面每一条都是硬要求：

- 操作失败（#5）**仍然必须醒目**：红色、`role="alert"`、位置不变。
- **必须保留现有的可关闭按钮**（`aria-label="关闭错误提示"`，main `1664-1669` / dev `1714-1719`）。
- **必须保留重发语义**：`api.ts:38` 那句"恢复连接后，可再次发送同一请求"要么继续成立，要么你改了文案并说明新的重发路径是什么。
- "重新连接"按钮（`{!connected && (…)}`，main `1659` / dev `1709`）现在挂在红条里。红条不再因连接失败出现之后，**这个按钮必须有去处**——搬到安静指示里，或明确说明为什么可以去掉。**不许静默丢失。**
- 交付里要给出**"发送失败"这一路径的实际截图或录屏证据**（见"真实验证"第 2 条）。

## 只许改

- `apps/mms-web/src/App.tsx`（`load()` 失败处理、红条渲染、必要的新 state）
- `apps/mms-web/src/styles.css`（安静指示的样式；如果复用 `.connection-status` 可能一行都不用改）
- `apps/mms-web/tests/` 下新增一个测试文件（见门禁）
- `docs/mms-web/design/t7a/`（截图）
- `apps/mms-web/DESIGN.md`：如果引入了新的 class / token 约定，补写进去（**路径是 `apps/mms-web/DESIGN.md`，不是 `docs/mms-web/DESIGN.md`，后者不存在**）

## 不许改

- **`apps/mms-web/src/api.ts`**。文案可以不动；如果你确实认为要动，**先停下来写进"需要 Fable 确认"**，不要自己改。`request()` 是所有前端请求的公共路径，动它影响面远超本包。
- 任何 `mms_web/**` Python。本包是纯前端。
- `apps/mms-web/src/SideQuestions.tsx`、`side-questions.ts`（**那是 T7b 的地盘**）
- 1 秒会话轮询那段（main `643-676` / dev `666-699`）和 `statusesStale` 的语义
- `mutation.current` 相关逻辑
- `apps/mms-web/src/bot.css`（4.22 上不存在；5.x 上那条 `.error-banner` 位置规则不归本包）
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`、`install.sh`
- 真实 `~/.config/mms*`
- 不加依赖（`CircleAlert`、`X` 已在 lucide-react 里）
- **不要重启 60824，不要动 8767**（owner 在用的实例）

## 门禁

```bash
# 1. 类型
npx tsc --noEmit -p apps/mms-web

# 2. 前端单测（必须带 glob）
node --test apps/mms-web/tests/*.test.mjs

# 3. 构建
npm run build --workspace @mms/web
```

`node --test apps/mms-web/tests/`（**不带 `*.test.mjs`**）会直接 `✖ 'test failed'`，2026-09-16 在 `5bf1f31d` 上复测过。**永远带 glob。**

### 实测基线（2026-09-16，跑之前先在你的 worktree 里 `npm install`）

**`origin/main` = `6c62a656` = 4.22.1（本包的实现 base）：**

| 门禁 | 实测值 |
| --- | --- |
| `npx tsc --noEmit -p apps/mms-web` | **0 错**（exit 0，输出 0 行） |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 56 / pass 56 / fail 0**（7 个测试文件：`composer-keys`、`markdown-reading`、`message-control`、`model-selection`、`side-questions`、`time`、`whats-new`） |
| `npm run build --workspace @mms/web` | **通过**，`index.css` 148.95 kB / `index.js` 660.01 kB（有 chunk >500kB 的既存告警，与本包无关） |

**`origin/dev` = `5bf1f31d` = 5.0.1（文档所在线，供合流时对照）：**

| 门禁 | 实测值 |
| --- | --- |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 121 / pass 121 / fail 0**（19 个测试文件） |
| `npm run build --workspace @mms/web` | **通过**，`index.css` 223.13 kB / `index.js` 793.19 kB |

**做完之后 `main` 上的 node test 数必须 ≥ 56 + 你新增的条数，fail 必须是 0。**

注意 `apps/mms-web/tsconfig.json` 的 `include` 只有 `["src"]`，**`tsc` 不检查 `apps/mms-web/tests/*.mjs`**，别指望它帮你抓测试文件的问题。

### 要补的单测

`load()` 的失败计数应该做成**可测的纯逻辑**（一个小函数或 reducer），新开 `apps/mms-web/tests/connection-banner.test.mjs`，至少覆盖：

- 第 1 次失败：不提示
- 第 2 次失败：仍不提示（如果阈值是 3）
- 到达阈值：提示出现
- 中间任意一次成功：计数清零、提示消失
- 达到阈值后再成功：提示消失且计数清零

如果你的实现没法抽成纯函数，在交付里说明，并改用别的方式证明这五条成立。

## 真实验证（不是可选项）

用 ego-browser 在**隔离实例**上验证。**自己另起端口，不要动 8767 和 60824。**

```bash
cd .worktrees/wt-T7a
npm install
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61761 \
  --state-root /tmp/bot-verify-t7a \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

两条必须做的验证：

1. **模拟服务短暂不可用**：停掉**你自己起的那个 61761 实例**几秒再拉起。
   - 确认**不再立刻弹红条**（截图：断开后第 1 个 8 秒周期）
   - 确认到达阈值前只有安静指示（截图）
   - 确认恢复后安静指示**自动消失**（截图）
   - 如果断开时间够长到触发提示，确认那个提示也是安静形态，不是红条
2. **制造一次真实的发送失败**：在实例停掉的状态下点发送（或用别的方式让 `runAction` 走进 catch）。
   - 确认**红条照常醒目出现**（截图）
   - 确认关闭按钮还在、点了能关（截图两张：关之前 / 关之后）
   - 确认"重新连接"入口有去处（截图）
   - **这一条 owner 点名要"实际截图或录屏证据"，不接受文字描述。**

截图全部存 `docs/mms-web/design/t7a/`。

## 验收清单（逐条可勾）

调查与复核：

- [ ] 在 `main` 上复核本文件所有行号，**列出所有与本文件不一致的**（本文件是 2026-09-16 在 `6c62a656` / `5bf1f31d` 上实测的，理论上应当全中；对不上说明 base 变了，停下来报告）。
- [ ] 复核并在交付里**逐条复述 `setError` 全部 7 个调用点的归类**（上表），确认没有第 8 处，确认 `setError` 没有被传给任何子组件。**不接受"我看了一眼没问题"。**
- [ ] 复述：`mutation.current` 有 `finally` 兜底，不是泄漏源，本包不碰它。
- [ ] 复述：仓库里已有安静连接指示（侧栏 `connection-status`）和已有的安静轮询失败处理（`statusesStale`），本包是往这套已有做法上拉齐。

实现 A（防抖）：

- [ ] 连续失败达到阈值（2 或 3，说明你选了几、为什么）才提示。
- [ ] 任意一次成功立刻清零计数并清掉提示。
- [ ] 首次加载失败的处理规则已明确并写进交付。
- [ ] **没有**新增轮询、**没有**新增网络请求、`8000` 这个间隔没动。
- [ ] `git diff` 里没有出现 `setInterval` / `setTimeout` 的新增（除非你能说明为什么必须加）。

实现 B（分流）：

- [ ] 连接健康度用安静指示呈现，不是红色阻断横幅。截图。
- [ ] 安静指示的视觉与已有 `.connection-status` 语言一致（或说明为什么另起一套）。截图。
- [ ] 红条只剩 #3（配置正在保存）和 #5（操作失败）两个来源。
- [ ] `error` 的拆分方式已说明（拆两个 state / 其它），理由写进交付。

实现 C（硬验收，不许降噪过头）：

- [ ] 操作失败仍然醒目：红色、`role="alert"`、位置不变。**截图。**
- [ ] 可关闭按钮保留且可用。**截图两张（关之前 / 关之后）。**
- [ ] 重发语义保留（或说明新的重发路径）。
- [ ] "重新连接"按钮有明确去处，没有静默丢失。**截图。**
- [ ] "发送失败"路径有**实际截图或录屏**证据。

门禁：

- [ ] `npx tsc --noEmit -p apps/mms-web` → 0。
- [ ] `node --test apps/mms-web/tests/*.test.mjs` → fail 0，pass ≥ 56 + 新增。**带 glob。**
- [ ] `npm run build --workspace @mms/web` 通过。
- [ ] 新增 `apps/mms-web/tests/connection-banner.test.mjs`，覆盖上面五条计数行为（或说明为什么抽不出纯函数、改用什么方式证明）。
- [ ] base ref 的实际 commit 写进交付。

真实验证：

- [ ] 断开 → 不立刻弹红条 → 恢复后安静指示自动消失。截图齐。
- [ ] 真实发送失败 → 红条醒目出现。截图齐。
- [ ] 截图全部在 `docs/mms-web/design/t7a/`。
- [ ] 没有重启 60824，没有动 8767，用的是自己起的端口。

合流提示：

- [ ] 交付里提醒下一个做 4.x→5.x 合流的人：5.x 的 `bot.css:67` 有一条 `.app-shell[data-page="bots"] > .main-area > .error-banner`；说明你有没有改红条的 class 名和 DOM 位置。

## 并行规则

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git fetch origin
git worktree add .worktrees/wt-T7a -b bot/T7a-connection-banner origin/main
cd .worktrees/wt-T7a && npm install
```

端口 61761。不碰 60824 和 8767。**不提交、不 push、不 merge。** 不在主 workspace 里改。

**和 T7b 并行不冲突**：T7b 只碰 `SideQuestions.tsx` / `side-questions.ts` / `App.tsx` 的 `<SideQuestions>` 挂载（main `2008` 一带），本包碰 `App.tsx` 的 `load()`（`412-439`）和红条（`1655-1671`）。

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T7a
分支 / worktree / base ref（含实际 commit）：
改动文件：git diff --stat 输出
行号复核：与工作包不一致的逐条列出（应当为空）
setError 归类：7 个调用点逐条复述 + 处置
基线数字：base ref 上实测的 tsc / node test / build
测试：tsc、node --test（对比 56）、build、新增单测
真实验证：端口、验收清单逐条结果、截图路径（断开/恢复/发送失败各自的）
合流提示：红条 class 名与 DOM 位置有没有变，5.x 的 bot.css:67 要不要跟改
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

## 需要 Fable 确认

1. **阈值取 2 还是 3。** 2 次 = 约 16 秒，3 次 = 约 24 秒。本包给 2–3 的区间，由实现者选并说明；如果 owner 有偏好请定。
2. **安静指示的形态。** owner 举的例子是"顶部一条细的『重连中…』"；仓库里已有侧栏 `connection-status` 胶囊。是加顶部细条（两处都有），还是只强化已有胶囊（一处），请定。本包默认允许实现者选并附截图说明。
3. **`api.ts:38` 的文案要不要改。** 本包默认不动（`request()` 是公共路径）。如果 owner 希望后台轮询和用户操作抛不同的错误（例如给 `request()` 加一个 `quiet` 标记），那是另一种形状，会扩大改动面，请确认。
4. **"重新连接"按钮的去处。** 本包要求"必须有去处，不许静默丢失"，但没有指定搬到哪。实现者会给方案，owner 可在验收时定。
