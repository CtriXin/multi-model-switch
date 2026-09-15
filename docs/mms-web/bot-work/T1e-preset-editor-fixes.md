# T1e · 预设编辑器四处修正

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD
建议模型：gemini3.6
来源：2026-09-15 真实模型验收，截图在 `docs/mms-web/design/acceptance-20260915/`

T1c 的链路验收通过（无弹窗创建、起名预填、记为约定、任务后提议都实测看到）。下面四条是验收里发现的缺陷，按严重度排。

## 1. 重新打开"调整工作预设"时名字被换成建议名（必须修）

现象：Bot 已叫"验收临时助手"，点头部"预设"打开编辑器，"我叫什么？"输入框 value 是 `项目助手`。用户改完约定顺手点"确认并开始对话"，Bot 会被静默改名。截图 `10-preset-editor.png`。

位置：`Bot.tsx` 向导组件里 `const suggestedName = suggestBotName(answers, existingNames); const [nameInput, setNameInput] = useState(suggestedName);` 以及随后的 `useEffect` 在答案变化时 `setNameInput(suggestedName)`。

要求：编辑模式（Bot 已有非空名字）下，输入框初值是当前名字，答案变化不覆盖用户已有名字；只有创建模式或名字为空/"未命名"时才用建议名。保存时名字没变就不发 name 字段。

## 2. 预设编辑器没有关闭入口（必须修）

现象：打开后再点一次头部"预设"按钮关不掉，发消息后它仍留在聊天顶部占位。

要求：头部"预设"按钮变为 toggle（`aria-pressed` 跟随）；编辑器右上加一个"取消"文字按钮，Esc 也关闭；关闭时丢弃未保存的修改，不弹确认。发送消息不自动关闭它，保持现状即可。

## 3. 固定尾句排在"补充约定："之后（小修）

现象：`buildPreset` 生成的 systemPrompt 里，`补充约定：` 标题后面先是用户的约定，然后紧跟固定尾句 `- 结果优先，过程保持安静…`，纯文本读起来像用户约定的最后一条。编辑器 UI 里 `parsePreset` 已经跳过它，所以只是文本顺序问题。

要求：`bot-presets.ts` 的 `buildPreset` 把 `DEFAULT_FOOTER` 放在向导答案之后、`补充约定：` 之前；`parsePreset` 对两种顺序都要能解析（老 Bot 的 systemPrompt 还是旧顺序）。补一条测试到 `apps/mms-web/tests/bot-presets.test.mjs`：旧顺序与新顺序 parse 结果相同，build 结果尾句在约定之前。

## 4. 名字输入框双层焦点框（小修）

现象：编辑器里名字输入框同时有蓝色 border 和外层 outline。T1 的要求是单一 outline。

要求：只留一种焦点表现，与 `bot-chat-title-input` 一致。hex 计数保持 12。

## 顺带看一眼，不强制

- 头部状态"待命"与侧栏卡片"等待你补充信息"同屏并存（卡片反映的是一条旧 waiting 任务）。是否让头部在有 waiting 任务时也显示等待，你给个建议写进汇报，不用改。
- 侧栏卡片第二行会塞整段模型回复，靠截断。建议写进汇报。

## 只许改

`apps/mms-web/src/Bot.tsx`（向导 / 编辑器 / 头部按钮相关代码）、`apps/mms-web/src/bot-presets.ts`、`apps/mms-web/src/bot.css`（第 4 条）、`apps/mms-web/tests/bot-presets.test.mjs`、`docs/mms-web/DESIGN.md`（如有 token 变化）。

## 不许改

`BotStudio.tsx`、`BotPlan.tsx`、任何 `mms_web/` Python、受保护文件、真实 `~/.config/mms*`。

## 验收

- 用一个已有名字的 Bot 打开编辑器：输入框是当前名字；改一条约定保存后 `GET /api/v1/bots` 里 name 不变，截图。
- 编辑器能用按钮、头部 toggle、Esc 三种方式关闭，截图。
- `node --test apps/mms-web/tests/*.test.mjs` 全过且数量 ≥ 84；`npx tsc --noEmit -p apps/mms-web` 0 错误；`npm run build --workspace @mms/web` 通过；`grep -o '#[0-9a-fA-F]\{3,8\}' apps/mms-web/src/bot*.css | sort -u | wc -l` 是 12。

## 并行规则

沿用 README：`git worktree add ../wt-T1e -b bot/T1e-preset-editor codex/stride-370e87ec37e741df`，端口 61701，不碰 60824，不提交、不 push、不 merge。可以和 T1d 串行在同一个会话里做，但要分开两个 worktree、分别汇报。
