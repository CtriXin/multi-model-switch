# T7b · BTW 旁问卡片收起后要被记住

Date: 2026-09-16
Task: Stride 370e87ec37e741df
建议模型：gemini3.6（纯前端）
来源：owner 2026-09-16——"问过之后折叠了 每次新的会话反回时候 还是会弹窗 不好"

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件，然后按下面"要读的代码"逐处确认。

**本包与 T7a 互相独立，可以并行**，两个包都建议给 gemini。两者改动面零重叠：T7b 只动 `SideQuestions.tsx` / `side-questions.ts` 和 `App.tsx` 里 `<SideQuestions>` 那一处挂载（main `App.tsx:2008` 一带）；T7a 只动 `App.tsx` 的 `load()`（`412-439`）和顶部红条（`1655-1671`）。唯一共享文件是 `App.tsx`，两处相距一千多行，合的时候不会真冲突。

---

## base 分支判定（T7a / T7b 共用，2026-09-16 实测）

### 结论

| 项目 | 分支 | 依据 |
| --- | --- | --- |
| **实现 PR 的 base** | **`main`（4.22.1，`6c62a656`）** | 本包要改的三个文件在两条线上**逐字节相同**；owner 定的流向是"4.x 的所有改动默认进入 5.x"，修在 4.22.x 会自动流到 5.x，反过来不会回到 4.x |
| 本工作包文档所在分支 | `dev`（5.0.1，`5bf1f31d`） | `docs/mms-web/bot-work/` 整个目录（含 README 索引和 T1–T6 十九份包）**只存在于 `dev`**，`origin/main` 上没有这个目录 |

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
| `apps/mms-web/src/SideQuestions.tsx` | `7e30d56a` | `7e30d56a` | **逐字节相同** |
| `apps/mms-web/src/side-questions.ts` | `68399708` | `68399708` | **逐字节相同** |
| `apps/mms-web/tests/side-questions.test.mjs` | 同 | 同 | **逐字节相同** |
| `apps/mms-web/src/api.ts` | `5ba09216` | `5ba09216` | **逐字节相同** |
| `apps/mms-web/src/App.tsx` | `beed496a` | `e8b89e91` | 差 64 行 |
| `apps/mms-web/src/styles.css` | `fa48b069` | `0832c54f` | 差 49 行 |

**本包要改的三个文件里，两个逐字节相同，第三个（`App.tsx`）的差异不落在本包要改的地方：**

- `App.tsx` 的 64 行差异**全部是 Bot 工作台接线**（`BotIcon` / `BotStudio` import、`isGuideReady()`、`page` 初值读 `#page=bots`、几处 `bots` 分支、侧栏 `.has-bots-entry` 入口、topbar 文案、`{page === "bots" && <BotStudio …>}`、以及 5.x 删掉的那行 `<WhatsNew ready={…} />`）。
- 本包关心的两处——`useSideQuestions(...)` 调用和 `<SideQuestions state={sideQuestions} />` 挂载所在的 `{page === "session"}` / `{detail && (…)}` 结构——在两条线上**内容相同，只是行号平移**（`useSideQuestions` 差 38 行，JSX 差 50 行）。
- `styles.css` 的 49 行差异是 `ModelExplorer` 的内联重试按钮和 `.model-picker-trigger` 布局，**和旁问卡片无关**。`.btw-*` 样式两条线相同。

### 对实现者的要求

- **在 `main` 上开分支**。做完在交付里写明 base ref 的实际 commit。
- 5.x 侧唯一要留意的：`<SideQuestions>` 外面多了一层 `page` 可以等于 `"bots"` 的可能（5.x 的 `BotStudio`）。这不改变本包的语义——`page === "bots"` 时 `{page === "session" && …}` 同样为假，卡片同样卸载，而本包的修法（状态提升或持久化）对这条路径同样成立。交付里提一句即可。

### 下面所有行号都给两套

owner 给的行号是在 `origin/dev` 上读的。本文件两套都列，**以 `main` 那一列为准**（实现 base）。owner 给的三个行号（`SideQuestions.tsx:330`、`349-350`、`App.tsx:2058`）在 `dev` 上**全部命中**；`SideQuestions.tsx` 两条线行号相同，`App.tsx` 在 `main` 上是 `2008`。

---

## 症状

Pilot 主会话里的 BTW 旁问卡片：owner 问过之后把它收起来了，但**每次新的会话返回时它又自己展开**。

> "问过之后折叠了 每次新的会话反回时候 还是会弹窗 不好"

## 根因（已查明，实现者要在 base 分支上复核一遍）

### 1. 折叠状态是组件内 `useState`，没有任何持久化

`apps/mms-web/src/SideQuestions.tsx:330`（**两条线行号相同**）：

```tsx
export function SideQuestions({ state }: { state: SideQuestionState }) {   // :329
  const [choice, setChoice] = useState<Record<string, boolean>>({});       // :330
```

### 2. 展开与否 = 用户选择 ?? 默认值

`SideQuestions.tsx:348-363`（**两条线行号相同**），owner 给的 `349-350` 命中：

```tsx
{rows.map((row, index) => {
  const fallback = defaultExpanded(row, index === rows.length - 1);   // :349
  const expanded = choice[row.btwId] ?? fallback;                     // :350
  return (
    <Card
      key={row.btwId}
      row={row}
      expanded={expanded}
      toggle={() =>
        setChoice((old) => ({ ...old, [row.btwId]: !expanded }))      // :357
      }
      …
```

### 3. `defaultExpanded` 让最新那条永远默认展开

`apps/mms-web/src/side-questions.ts:144-153`（**两条线行号相同**）：

```ts
/** Open while the answer is arriving, and open for the newest question.
 *
 *  Folding the moment an answer lands means reading the thing you just asked
 *  takes another click. So the latest question stays open until the next one
 *  takes its place, and everything behind it folds to one line. A card the
 *  reader has toggled keeps their choice instead of this.
 */
export function defaultExpanded(row: SideQuestion, newest = false): boolean {   // :151
  return isInFlight(row) || newest;                                             // :152
}
```

注意最后一句注释——*"A card the reader has toggled keeps their choice instead of this."* **这个承诺现在是假的**，因为 `choice` 活不过一次卸载。

### 4. `<SideQuestions>` 挂在 `{detail && (…)}` 里面，`detail` 一空整棵子树卸载

| 位置 | main | dev |
| --- | --- | --- |
| `const sideQuestions = useSideQuestions(detail?.session.id, detail?.sideQuestions);` | `App.tsx:1016` | `1054` |
| `{page === "session" && (` | `1916` | `1966` |
| `{detail && (` （包住 `.conversation-content`） | `1967` | `2017` |
| `<SideQuestions state={sideQuestions} />` | **`2008`** | **`2058`**（owner 给的数，dev 上命中） |

**所以有两个卸载触发条件**，两个都会把 `choice` 清空：

- `page` 不再是 `"session"`（回首页、进设置，5.x 上还有进 Bot 工作台）
- `detail` 变成 `null`

### 5. `detail` 在哪些情况下会变空 —— 已查清三处 `setDetail(null)`

`grep -n "setDetail(null)" apps/mms-web/src/App.tsx`：

| # | main | dev | 在哪个函数里 | 什么时候触发 |
| --- | --- | --- | --- | --- |
| 1 | `683` | `706` | `navigate(next, after?)`，`if (next !== "session") { setSelectedId(""); setDetail(null); … }` | 任何离开会话页的导航（点"新建任务"、点设置、5.x 上点 Bot 工作台） |
| 2 | `700` | `723` | `beginGuideStep(step)`，`setPage("new"); setSelectedId(""); setDetail(null); …` | 首次引导跳到 workspace / compose 步（5.x 上还有 `page === "bots"` 时） |
| 3 | **`749`** | **`787`** | `openSession(id)` | **每次打开会话都会先 `setDetail(null)`** ← **这条是 owner 症状的直接成因** |

`openSession()`（main `740-754` / dev `778-794`）里是：

```tsx
currentSelection.current = id;
setSelectedId(id);
setDetail(null);        // main :749 / dev :787
setSessionError("");
setPage("session");
```

**它无条件先清空 `detail`**，然后由 `selectedId` 的轮询 effect（main `577` 一带 / dev `600` 一带）异步拉回详情。也就是说：**"切到别的会话再切回来"必然经过一次 `detail === null`，`choice` 必然被清空**，重新挂载后 `defaultExpanded(row, 最新一条) === true`，已回答的最新那条又自己展开了。

这就是 owner 说的"每次新的会话返回时候还是会弹窗"。**用户的收起动作从来没被记住过。**

补充：`useSideQuestions` 这个 hook 本身挂在 App 顶层（main `App.tsx:1016`），**`detail` 变空时它不会卸载**——它只在 `sessionId` 变化时清 `local` 和 `notice`（`SideQuestions.tsx:56-59`）。这一点对方案选择很关键，见下面 A。

## 正确语义

**看过一次就不再自动展开。**

- 到达时自动展开一次（有用的提示）；
- 用户收起之后**永久记住**，不再因为"它是最新一条"而重新展开。

**要求实现者把这条语义明确写成"已读 / 已处置"的概念，而不是继续用"是不是最新"来推断。** `newest` 是位置，不是状态；用位置去猜用户看没看过，就是现在这个 bug 的根。

## 要读的代码（只读，先看完再动手）

| 位置（main / dev） | 看什么 |
| --- | --- |
| `side-questions.ts:144-153` | `defaultExpanded` 与它的注释（那句承诺） |
| `side-questions.ts:86-92` | `isSettled` / `isInFlight` |
| `side-questions.ts:112-142` | `mergeSideQuestions` / `upsertSideQuestion`：行的来源与排序（`createdAt` 升序，最后一条是最新） |
| `SideQuestions.tsx:50-59` | `useSideQuestions` 的签名和 `sessionId` 变化时的清理 |
| `SideQuestions.tsx:329-367` | `SideQuestions` 组件全文 |
| `SideQuestions.tsx:270-312` | `Card` 的渲染与 `expanded` 的用法 |
| `App.tsx:1016` / `1054` | `useSideQuestions` 的调用点（**在 App 顶层，不随 detail 卸载**） |
| `App.tsx:1916` / `1966`、`1967` / `2017`、`2008` / `2058` | 两层挂载条件与 `<SideQuestions>` |
| `App.tsx:683 / 700 / 749`（dev `706 / 723 / 787`） | 三处 `setDetail(null)` |
| `App.tsx:92-108`（dev `94-110`） | `readSetting` / `saveSetting`：**已有的 try/catch localStorage 包装** |
| `apps/mms-web/src/SessionAttention.ts:5-17`、`40-65` | **已有的"已读回执"范本**：按 id 存 localStorage、读时清洗、写时 `slice(-1000)` 截断、全程 try/catch、还监听 `storage` 事件跨标签页同步 |
| `apps/mms-web/tests/side-questions.test.mjs:43-53` | **两条现有的 `defaultExpanded` 用例，本包会改到其中一条** |

`readSetting` / `saveSetting`（main `App.tsx:92-108`）：

```ts
function readSetting<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : fallback;
  } catch {
    return fallback;
  }
}
function saveSetting(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
}
```

它们是模块内私有的（没 `export`）。要在 `SideQuestions.tsx` 里复用就得导出或另写一份——**另写一份的话必须同样 try/catch**，见下面的硬要求。

## 要做成什么

### A. 折叠状态必须在组件卸载后仍然保留

两个方向，**实现者选一个并在交付里说明理由**：

**方向 1：把状态提到不会随 `detail` 卸载的层级。**

- 最自然的落点是 `useSideQuestions`（`SideQuestions.tsx:50`），它已经挂在 App 顶层（`App.tsx:1016`），`detail` 变空时不卸载。把"已读 / 收起"的记录放进这个 hook，通过 `SideQuestionState` 交给组件。
- **但要注意**：这个 hook 里有 `useEffect(() => { setLocal(empty); setNotice(""); }, [sessionId])`（`SideQuestions.tsx:56-59`）。`openSession()` 会让 `sessionId` 走 `id → undefined → id`，这个 effect 会跑两次。**你新加的记录不能被这个 effect 清掉**（用 `useRef` 或独立的 state，不要塞进 `local`）。这一条务必自测。
- 代价：**刷新页面就丢**。
- 另一个落点是把 `choice` 提到 `App` 组件里，通过 prop 传给 `<SideQuestions>`。可行但会给 `App.tsx` 再加一个 state，而 `App.tsx` 已经很重；优先考虑放进 hook。

**方向 2：用 `localStorage` 按 `sessionId + btwId` 存。**

- 键的形状建议 `mms-web-btw-seen-v1`，值是 `Record<string, string>` 或 `Record<string, true>`，id 用 `sessionId + "|" + btwId`（`btwId` 本身可能不含会话信息，别只用它）。
- 好处：刷新、关标签页、换设备之外的所有情况都记住。
- **硬要求（owner 点名）**：`localStorage` 在隐私窗口 / 禁用站点数据时**读写都会抛**，`localStorage` 这个标识符本身的访问就可能抛。**读和写都必须 try/catch，取不到时要能正常降级**（降级到"当前会话内记住"，或降级到现在的行为，但不能白屏、不能抛到 React 边界）。照抄 `SessionAttention.ts:5-17 / 57-65` 的形状最稳妥：读时清洗数据（别信 localStorage 里的东西是你写的形状）、写时截断（`slice(-1000)`）避免无限增长。

**两个方向都可以，也可以组合**（hook 里的 ref 作为热路径 + localStorage 作为持久层，这正是 `SessionAttention.ts` 的做法）。**选哪个、为什么、降级行为是什么，写进交付。**

### B. `defaultExpanded` 的语义要改

新语义：

| 行的状态 | 自动展开？ |
| --- | --- |
| **仍在进行中**（`isInFlight(row)`，即 `prepared` / `accepted` / `running`） | **是，继续自动展开**（用户需要看到它在跑） |
| **已回答 / 已结束**（`completed` / `failed` / `cancelled` / `uncertain`），**用户还没看过** | **是，自动展开一次** |
| **已回答 / 已结束**，**用户看过了**（收起过，或按你定义的"已处置"） | **否，按用户最后一次选择** |

- 签名要改：现在是 `defaultExpanded(row, newest = false)`。新签名应当吃"已读 / 已处置"这个事实，而不是 `newest` 这个位置。建议 `defaultExpanded(row, seen = false)` 或 `defaultExpanded(row, { seen })`。**具体签名你定，但"是不是最新"不能再作为判断依据。**
- `SideQuestions.tsx:349` 那行 `index === rows.length - 1` 要跟着改掉。
- **保持纯函数**——它现在在 `side-questions.ts` 里，是可测的纯逻辑，这个性质不许破坏（不许在里面读 localStorage）。持久化留在调用方。

### C. 边界：新来一条旁问要自动展开，但不能连累旧卡片

明确写成验收项：

- **新来一条旁问时，它应该自动展开**（这是有用的提示）。
- **不能因此把用户已经收起的旧卡片一起重新展开。**

也就是说"已读"必须是**按 `btwId` 逐条记的**，不是一个全局的"用户收起过旁问区"的开关。

### D. 查清 `detail` 变空的全部情况并在交付里说明

上面第 5 条已经查清三处 `setDetail(null)`（main `683` / `700` / `749`），外加 `{page === "session" && …}` 这层。**实现者要自己复核一遍**并在交付里复述，因为这决定了状态该提到哪一层：

- 如果只有 `detail` 会空、`page` 一直是 `"session"` → 提到 App 或 hook 就够
- 如果 `page` 也会变（实测会：`navigate("new")` / `navigate("models")` / 5.x 的 `navigate("bots")`）→ 同样要提到 App 或 hook 之上
- 如果还要活过刷新 → 必须 localStorage

## 只许改

- `apps/mms-web/src/SideQuestions.tsx`
- `apps/mms-web/src/side-questions.ts`
- `apps/mms-web/src/App.tsx`：**只允许** `useSideQuestions` 调用处（main `1016`）和 `<SideQuestions>` 挂载处（main `2008`）的最小接线；如果方案需要，允许 `export` 现有的 `readSetting` / `saveSetting`（main `92` / `100`）
- `apps/mms-web/tests/side-questions.test.mjs`（**owner 点名要在这里补单测**）
- `docs/mms-web/design/t7b/`（截图）
- `apps/mms-web/DESIGN.md`：如果引入了新的 class / token 约定（**路径是 `apps/mms-web/DESIGN.md`，不是 `docs/mms-web/DESIGN.md`，后者不存在**）

## 不许改

- **`App.tsx` 的其它任何地方**。尤其是三处 `setDetail(null)`（main `683` / `700` / `749`）和 `openSession()` 的结构——**不要为了保住 `detail` 去改 `openSession`**。`setDetail(null)` 是有意的（切会话时不要让旧会话的内容留在屏幕上），改它会影响会话切换的观感和 `ConversationOutline` 等一串 `key={detail.session.id}` 的组件。正确的修法是让折叠记忆活过卸载，不是阻止卸载。
- `App.tsx` 的 `load()` / 顶部红条 / `error` 相关（**那是 T7a 的地盘**）
- `apps/mms-web/src/api.ts` 与任何 `/api/v1/sessions/*/btw*` 接口
- 任何 `mms_web/**` Python。本包是纯前端，**不新增后端字段**。"已读"是客户端事实，不要为它开服务端存储。如果你认为必须服务端存，**停下来写进"需要 Fable 确认"**。
- `mergeSideQuestions` / `upsertSideQuestion` / `isSettled` / `isInFlight` 的语义
- `SideQuestions.tsx` 里 `useSideQuestions` 的轮询逻辑（`:70-98`）
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`、`install.sh`
- 真实 `~/.config/mms*`
- 不加依赖
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
| `node --test apps/mms-web/tests/side-questions.test.mjs`（单文件） | **tests 17 / pass 17 / fail 0** |
| `npm run build --workspace @mms/web` | **通过**，`index.css` 148.95 kB / `index.js` 660.01 kB（有 chunk >500kB 的既存告警，与本包无关） |

**`origin/dev` = `5bf1f31d` = 5.0.1（文档所在线，供合流时对照）：**

| 门禁 | 实测值 |
| --- | --- |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 121 / pass 121 / fail 0**（19 个测试文件） |
| `node --test apps/mms-web/tests/side-questions.test.mjs`（单文件） | **tests 17 / pass 17 / fail 0**（该文件两条线逐字节相同） |
| `npm run build --workspace @mms/web` | **通过**，`index.css` 223.13 kB / `index.js` 793.19 kB |

**做完之后 `main` 上的 node test 数必须 ≥ 56 + 你新增的条数，fail 必须是 0。**

注意 `apps/mms-web/tsconfig.json` 的 `include` 只有 `["src"]`，**`tsc` 不检查 `apps/mms-web/tests/*.mjs`**。

### 要补的单测（`apps/mms-web/tests/side-questions.test.mjs`）

**现有两条 `defaultExpanded` 用例在 `:43-53`，本包会改到第二条：**

```js
test('a card is open while answering, whatever its place in the list', () => {   // :43
 assert.equal(defaultExpanded(row({ status: 'running' })), true);
 assert.equal(defaultExpanded(row({ status: 'accepted' })), true);
});

test('the newest question stays open and the ones behind it fold', () => {       // :48  ← 语义要改
 for (const status of ['completed', 'failed', 'cancelled', 'uncertain']) {
  assert.equal(defaultExpanded(row({ status }), true), true, `newest ${status}`);
  assert.equal(defaultExpanded(row({ status }), false), false, `older ${status}`);
 }
});
```

第一条（`:43`，进行中必展开）**语义不变，必须继续通过**。第二条（`:48`）的语义被本包替换，**改写它、不要简单删掉**，新名字要说清新语义。

至少覆盖：

- 进行中的行（`prepared` / `accepted` / `running`）无论看没看过，`defaultExpanded` 都是 `true`
- 已结束的四种状态（`completed` / `failed` / `cancelled` / `uncertain`）**未看过** → `true`
- 同样四种状态**已看过** → `false`
- **不再依赖位置**：同一条已结束、未看过的行，无论它是列表里的最后一条还是中间一条，结果相同（这条直接钉死"不能再用 `newest` 推断"）
- 如果持久化层抽了纯函数（例如"从存储对象算某条是否已看过"），一并补：存储为空、存储里有别的会话的记录、存储内容是垃圾数据（不是对象 / 字段类型不对）三种情况

**localStorage 抛异常的降级路径**如果能抽成纯函数就补单测；抽不出来就在真实验证里用浏览器的"阻止站点数据"验一次并截图，在交付里说明选了哪条路。

## 真实验证（不是可选项）

用 ego-browser 在**隔离实例**上验证。**自己另起端口，不要动 8767 和 60824。**

```bash
cd .worktrees/wt-T7b
npm install
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61762 \
  --state-root /tmp/bot-verify-t7b \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

owner 点名的那条主路径，**每一步都要截图**：

1. 提一个旁问（`/btw <问题>`）
2. 等它回答完（卡片显示"已回答"）
3. **收起它**
4. **切到别的会话，再切回来**
5. **确认仍是收起的** ← 核心验收点
6. 再提一条新旁问
7. **确认新的自动展开、旧的仍收起** ← 边界验收点

补充路径（也要截图）：

- 回首页（`navigate("new")`）再回会话 → 仍收起
- 进设置再回会话 → 仍收起
- 旁问**还在生成中**时 → 自动展开（`isInFlight` 的行为没被破坏）
- 刷新页面 → 按你选的方案，写明预期并截图证明实际行为与预期一致（方向 1 会丢，方向 2 不会；**两种都可接受，但交付里必须写清楚，不许含糊**）

截图全部存 `docs/mms-web/design/t7b/`。

## 验收清单（逐条可勾）

调查与复核：

- [ ] 在 `main` 上复核本文件所有行号，**列出所有与本文件不一致的**（本文件是 2026-09-16 在 `6c62a656` / `5bf1f31d` 上实测的，理论上应当全中；对不上说明 base 变了，停下来报告）。
- [ ] **查清并在交付里说明 `detail` 在哪些情况下会变空导致卸载**，逐条列出（应当是三处 `setDetail(null)` + `{page === "session"}` 那层）。**这决定了状态该提到哪一层**，不接受"我看了一眼没问题"。
- [ ] 复述：`useSideQuestions` 挂在 App 顶层，`detail` 变空时不卸载；但它有 `[sessionId]` 的清理 effect，`openSession` 会让 `sessionId` 走 `id → undefined → id`。

实现 A（活过卸载）：

- [ ] 选了方向 1 / 方向 2 / 组合，理由写进交付。
- [ ] 折叠状态在组件卸载后仍然保留。
- [ ] 如果落在 `useSideQuestions` 里：新记录**没有**被 `[sessionId]` 的清理 effect 清掉，已自测。
- [ ] 如果用 `localStorage`：**读和写都 try/catch**；取不到时正常降级，不白屏、不抛到 React 边界；读时清洗数据；写时有大小上限（照 `SessionAttention.ts` 的 `slice(-1000)`）。
- [ ] 键里带 `sessionId`，不同会话的同名记录不串。

实现 B（语义）：

- [ ] `defaultExpanded` 改成吃"已读 / 已处置"，**不再吃"是不是最新"**。
- [ ] 进行中（`isInFlight`）继续自动展开。
- [ ] 已结束 + 未看过 → 自动展开一次。
- [ ] 已结束 + 看过了 → 按用户最后一次选择。
- [ ] `defaultExpanded` **仍是纯函数**，没有在里面读存储。
- [ ] `SideQuestions.tsx:349` 的 `index === rows.length - 1` 已改掉。
- [ ] 交付里写明"已读 / 已处置"的准确定义（收起算已读？展开看过也算？两种都行，但要写死）。

实现 C（边界）：

- [ ] 新来一条旁问自动展开。**截图。**
- [ ] 新来一条旁问**没有**把用户已收起的旧卡片一起重新展开。**截图。**
- [ ] "已读"是按 `btwId` 逐条记的，不是全局开关。

测试：

- [ ] `apps/mms-web/tests/side-questions.test.mjs` 里 `:43` 那条（进行中必展开）**改写后仍通过或原样通过**。
- [ ] `:48` 那条（"最新的展开、后面的折叠"）**已改写**成新语义，不是删掉了事。
- [ ] 新增用例覆盖：进行中 / 已结束未看过 / 已结束已看过 / 不依赖位置。
- [ ] 存储层的纯函数（如有）也有单测，含垃圾数据。
- [ ] localStorage 抛异常的降级：单测或浏览器实测，二选一并说明。

门禁：

- [ ] `npx tsc --noEmit -p apps/mms-web` → 0。
- [ ] `node --test apps/mms-web/tests/*.test.mjs` → fail 0，pass ≥ 56 + 新增。**带 glob。**
- [ ] `npm run build --workspace @mms/web` 通过。
- [ ] base ref 的实际 commit 写进交付。

真实验证：

- [ ] 提问 → 回答 → 收起 → 切走再切回 → **仍收起**。截图齐（七步每步一张）。
- [ ] 再提一条新旁问 → 新的展开、旧的仍收起。截图。
- [ ] 回首页 / 进设置再回会话 → 仍收起。截图。
- [ ] 生成中的卡片自动展开。截图。
- [ ] 刷新页面的行为已写明预期并截图证明。
- [ ] 截图全部在 `docs/mms-web/design/t7b/`。
- [ ] 没有重启 60824，没有动 8767，用的是自己起的端口。

合流提示：

- [ ] 交付里提一句：5.x 上 `page` 还可能是 `"bots"`，`<SideQuestions>` 同样卸载，本包的修法对那条路径同样成立。

## 并行规则

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git fetch origin
git worktree add .worktrees/wt-T7b -b bot/T7b-btw-card-fold-memory origin/main
cd .worktrees/wt-T7b && npm install
```

端口 61762。不碰 60824 和 8767。**不提交、不 push、不 merge。** 不在主 workspace 里改。

**和 T7a 并行不冲突**：T7a 碰 `App.tsx` 的 `load()`（main `412-439`）和红条（`1655-1671`），本包碰 `App.tsx` 的 `1016` 和 `2008` 两处最小接线。

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T7b
分支 / worktree / base ref（含实际 commit）：
改动文件：git diff --stat 输出
行号复核：与工作包不一致的逐条列出（应当为空）
detail 变空的全部情况：逐条列出 + 这如何决定了状态放在哪一层
方案选择：方向 1 / 2 / 组合，理由；localStorage 的降级行为
"已读 / 已处置"的准确定义：
基线数字：base ref 上实测的 tsc / node test / build
测试：tsc、node --test（对比 56）、build、side-questions.test.mjs 的新增与改写
真实验证：端口、七步主路径逐步结果、补充路径结果、截图路径
刷新页面的预期与实际：
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

## 需要 Fable 确认

1. **刷新页面要不要记住。** 方向 1（提升状态）刷新就丢，方向 2（localStorage）不丢。owner 的原话只说"每次新的会话返回时候"，没说刷新。本包默认允许实现者选并写清行为；如果 owner 要求刷新也记住，那就只能走 localStorage。
2. **"已读"的准确定义。** 本包默认"用户收起过 = 已处置"。另一种可能是"卡片展开着停留过 N 秒 = 看过了，下次不自动展开"。后者更贴近"看过一次就不再自动展开"的字面意思，但会引入计时，复杂度高一档。本包默认取前者，请确认。
3. **要不要清理旧记录。** localStorage 方案会随会话增长。本包要求照 `SessionAttention.ts` 做 `slice(-1000)` 截断，没要求按会话删除（会话被删时记录成为孤儿，但只占几十字节）。如果 owner 要求精确清理，那需要知道会话删除事件，改动面会外扩到 `App.tsx` 之外。
4. **`readSetting` / `saveSetting` 要不要 export。** 本包允许把 `App.tsx:92 / 100` 这两个私有函数导出给 `SideQuestions.tsx` 复用，避免第三份 localStorage 包装（仓库里现在已有 `drafts.ts`、`SessionAttention.ts`、`ModelExplorer.tsx`、`HelpGuide.tsx` 各写各的）。如果 owner 更希望不动 `App.tsx` 的导出面、宁可在 `SideQuestions.tsx` 里另写一份，请确认。
