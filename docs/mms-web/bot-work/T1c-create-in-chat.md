# T1c · 新建即对话：命名、头像、预设都在聊天里完成

Task: 370e87ec37e741df · 分支 `bot/T1c-create-in-chat` · 建议模型 gemini3.6 主做（要看截图），glm5.3 做代码侧评审
先读：`docs/mms-web/bot-work/README.md`、`T1-ui-visual-system.md` 的"一条左边缘""单一焦点边框"两节、`apps/mms-web/DESIGN.md` 的"Bot 页面"一节。

## 目标一句话

点"新建"之后用户不再看到任何弹窗：Bot 立刻出现在聊天里，名字、头像、工作方式都在对话区和头部原地改；聊天中说出的长期要求可以一键沉淀成预设。

## 现状（已经做到的一半）

`BotStudio.tsx` 的 `createDraftBot` 已经不弹窗：直接 `POST /bots` 建一个叫"新 Bot"的草稿并选中。`Bot.tsx` 的 `BotOnboarding` 在聊天区放了三道 chip 选择题（处理哪类事 / 怎么回报 / 怎么推进），答案由 `onboardingPrompt()` 拼进 `systemPrompt`，开头固定一行"这是创建时确认的工作预设，请持续遵守："；`readOnboardingAnswers()` 负责反向解析。

没做到的：名字一直是"新 Bot"，改名、改头像、改描述都要点"编辑 Bot"开弹窗；聊天里说"以后回复短一点"不会回写到预设；预设编辑器只认那三个答案，用户手写进 systemPrompt 的其它行会被覆盖。

## 只许改 / 不许改

只许改：
- `apps/mms-web/src/Bot.tsx`：`BotOnboarding`、`BotChat` 的 `<header className="bot-chat-header">`、用户消息气泡的 hover 动作区。
- `apps/mms-web/src/BotStudio.tsx`：`onUpdateBot` 的 patch 字段（见 B3）、`createDraftBot`。
- `apps/mms-web/src/bot.css`：新增原地编辑与 popover 样式，只用已有 token。
- `apps/mms-web/src/bot-presets.ts`（新增）：本包全部纯函数放这里，方便测试。
- `apps/mms-web/tests/bot-presets.test.mjs`（新增）。
- `apps/mms-web/DESIGN.md`："Bot 页面"一节追加"原地编辑"小节。

不许改：`types.ts`、任何 `mms_web/*.py`、任何 `tests/*.py`、`BotEditor` 弹窗本体（保留原样，这轮只是不再是新建路径）、`BotPlan.tsx`、`BotMemoryPanel.tsx`、`BotCommunications.tsx`、`studio.css`。后端 `update_bot` 已接受部分字段（`name` ≤ 80、`description` ≤ 1000、`systemPrompt` ≤ 12000、`avatarId`、`avatarColor`），本包不需要新接口。

派发前置：主 workspace 里另一个会话正在做几何头像系统（`Bot.tsx`、`bot.css`、`bots.py` 未提交）。**等那份改动提交到任务分支后再从 HEAD 开本包分支**，头像 popover 直接复用届时 `BotEditor` 里的图形行和颜色行组件，不要自己再画一套。

## A · 向导补第四步：起名

1. `BotOnboarding` 三道 chip 题后追加第四步"我叫什么"：一个单行文本框，预填建议名，光标自动落在框里并全选，用户可直接回车确认。
2. 建议名由 `suggestBotName(answers)` 生成，只看 `focus`：工作与项目 → "项目助手"，资料整理与写作 → "写作助手"，生活安排 → "生活管家"，其它 → "通用助手"。同名已存在时加序号："项目助手 2"。纯函数，输入 `answers` 和现有名字列表。
3. 点确认时**一次** `onUpdateBot(bot.id, { name, systemPrompt })`，不要分两次请求。名字为空退回建议名。
4. 侧栏卡片：`name === "新 Bot"` 且 `systemPrompt` 为空时，标题用 `--muted` 色并显示"未命名"，提示用户去聊天区完成。用户跳过向导直接发消息也允许，Bot 保持"新 Bot"，下面 B 节的原地改名兜底。

## B · 头部原地编辑

1. **名字**：`<h1>` 变成可点击（`role="button"`，键盘 Enter 也可进入）。点击后原位换成 `<input>`，字号、字重、行高和 `<h1>` 完全一致，**不允许布局跳动**（宽度用同一个容器撑住，不要让 input 默认宽度把状态徽章挤走）。Enter 或失焦保存，Esc 取消，空值不保存。保存中显示 `LoaderCircle`，失败时在头部下方一行 `bot-inline-error`，不弹窗。
2. **描述**：同样处理 `<p>`，单行，上限 1000 字，空描述显示"随时可以接活"占位（`--muted`），点击后 input 为空。
3. **头像**：点击头部头像弹出 popover（用原生 `popover` 属性或 `position: fixed`，不能被 `bot-chat-header` 的 overflow 裁掉），内容是 `BotEditor` 里现成的图形行 + 颜色行。点选即保存：`onUpdateBot(bot.id, { avatarId })` 或 `{ avatarColor }`，无需保存按钮。`BotStudio.tsx` 的 `onUpdateBot` 现在对 `avatarId` / `avatarColor` / `wakeEnabled` 只回填当前值，改成 `patch.x ?? current.x` 的同一模式。
4. 焦点边框沿用 T1 的单一 `outline`，不能同时出现 border 和 outline。
5. "编辑 Bot"弹窗保留，卡片 hover 菜单入口不动。这轮不做模型 / 唤醒 / 记忆预算的原地编辑。

## C · 对话中沉淀长期约定

1. `systemPrompt` 新增一段固定格式，紧跟在向导三行之后、结尾那句"结果优先"之前：
   ```
   补充约定：
   - <一条>
   - <一条>
   ```
   最多 12 条，每条 ≤ 200 字，去重（trim 后完全相同视为重复）。
2. `bot-presets.ts` 提供 `parsePreset(systemPrompt) → { answers, rules: string[], other: string }` 和 `buildPreset({ answers, rules, other })`。`other` 是用户手写的、不属于向导也不属于补充约定的行，**必须原样保留**。把现有 `readOnboardingAnswers` / `onboardingPrompt` 改成调用这两个函数，行为对旧格式的 systemPrompt 完全兼容（写测试：旧 prompt 解析再拼回，逐字相等）。
3. 用户消息气泡 hover 时出现一个安静动作"记为约定"（沿用卡片"配置 / 删除"那种 hover 才出现的方式，键盘 focus 也能到）。点击后把这条消息文本作为一条 rule 追加并 `onUpdateBot`，成功后气泡下方一行 `--muted` 小字"已记为长期约定"，3 秒后消失。超过 12 条时提示"约定已满，先去预设里删几条"。
4. 自动提议：`looksLikeStandingInstruction(text)` 匹配"以后 / 今后 / 从现在起 / 每次 / 默认 / 都要 / 总是 / 别再 / 不要再"且长度 ≤ 200 字，返回 true。任务结束（`task.status` 进入终态）后，在该用户消息下方出现一行内联提示："要把这句记为长期约定吗？ [记住] [不用]"。同一条消息只提示一次，"不用"后本次页面生命周期内不再提示这条。不弹窗、不自动写入。
5. "调整工作预设"编辑器（`onboardingEditing`）下方列出补充约定，每条右侧一个删除 ×；保存时通过 `buildPreset` 拼回。
6. 模型侧识别（让 Bot 自己判断哪句是长期要求）**不在本包范围**，不要改 `bot_executor.py` 的提示词。

## 验收

- 新建 → 不出现任何 `role="dialog"`；聊天区依次出现三道 chip 题和起名框；回车后侧栏名字更新，`systemPrompt` 以"这是创建时确认的工作预设"开头。
- 头部点名字改名，Esc 取消后名字不变；改名前后头部高度不变（用 ego-browser 量 `header.getBoundingClientRect().height`）。
- 头像 popover 在窄窗口（400px）不被裁切。
- 老 Bot（systemPrompt 里有用户手写的行）打开预设编辑器再保存，手写行仍在。
- 记为约定 → `GET /bots/:id` 的 systemPrompt 含"补充约定："段；第 13 条被拒且有提示。
- 浅色、深色主题各截一张：新建向导、头部编辑态、约定提示行。
- `node --test apps/mms-web/tests/bot-presets.test.mjs` 通过，至少覆盖：suggestBotName 四个分支和重名序号；parse/build 往返；旧格式兼容；12 条上限与去重；looksLikeStandingInstruction 正反例各 3 条。
- `npm run build --workspace @mms/web` 通过；README 里的 focused Python tests 数字不下降（本包不该碰 Python，跑一遍只是证明没碰）。
- 不重启 60824，独立实例用 61600。

## 汇报格式

按 README"通用验收"写进你 worktree 的 `walls.md`。截图路径要给绝对路径。
