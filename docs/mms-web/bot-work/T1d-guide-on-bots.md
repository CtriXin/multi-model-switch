# T1d · Bot 页不弹 Pilot 首次引导

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD（0830465b 或之后）
建议模型：gemini3.6

## 问题

全新 state 下打开 `#page=bots`，Pilot 的首次引导（"第一次用 AI？1/7"）会盖在 Bot 工作台上，第 1 步就说"当前页面暂未显示这个入口"。引导讲的是 Pilot 会话页，Bot 页有自己的创建向导，两者叠在一起。

复现：
```bash
cd <你的 worktree>
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61700 \
  --state-root /tmp/bot-verify-T1d --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```
浏览器开 `http://127.0.0.1:61700/#page=bots`，用无痕或先清 `localStorage` 里的 `mms-web-tour-seen-v1`。

## 要做成什么

1. `page === "bots"` 时不自动开始引导。不把引导标成已看过：用户回到 Pilot 会话页时，引导照常第一次弹出。
2. 引导进行中用户点侧栏"Bot"入口进入 Bot 页，引导关闭（`navigate("bots")` 时 `setGuideStep(null)`），不报错、不残留高亮。
3. 在 Bot 页点"?"再点"开始介绍"，先回到 Pilot 新会话页，再从 welcome 开始；不在 Bot 页上讲 Pilot。
4. 其它页面的引导行为一律不变：7 步顺序、settings/connection 步骤、`tourSeen` 服务端记录、`?` 面板内容都不动。

## 代码位置

- `apps/mms-web/src/App.tsx`：`page` 状态在 217 行；`navigate()` 在 683 行附近；`beginGuideStep()` / `startIntroduction()` 在 700 到 720 行；tour 挂载在 1027 行 `const tour = guideStep && modelReady && !setupOpen ? <GuidedTour .../> : null`。
- `apps/mms-web/src/HelpGuide.tsx`：67 到 80 行的 `useEffect` 决定首次自动开始，`seenKey = "mms-web-tour-seen-v1"`，服务端 `/ui-preferences` 的 `tourSeen`。`ready` prop 由 App 传入，最省事的做法是让 `ready` 在 Bot 页为 false，并确认它不会因此被 `markSeen`。

## 只许改

- `apps/mms-web/src/App.tsx`：只改上面列的插入点，每处不超过几行。
- `apps/mms-web/src/HelpGuide.tsx`：只改自动开始的条件。
- 新增 `apps/mms-web/tests/guided-tour-bots.test.mjs`：至少覆盖"Bot 页不自动开始""进入 Bot 页关闭引导"两条纯函数或状态断言。参考现有 `tests/*.test.mjs` 的写法，不引入依赖。

## 不许改

- `Bot.tsx`、`BotStudio.tsx`、`bot*.css`、`GuidedTour.tsx` 的步骤内容。
- `mms_web/` 任何 Python。
- 受保护文件与真实 `~/.config/mms*`。

## 验收

- 新 state 打开 `#page=bots`：没有引导，截图。
- 同一 state 点回 Pilot 新会话页：引导 1/7 弹出，截图。
- 引导进行到 2/7 时点"Bot"入口：引导消失，Bot 页正常，截图。
- Bot 页点"?"→"开始介绍"：落到 Pilot 新会话页并显示 welcome，截图。
- `npx tsc --noEmit -p apps/mms-web` 0 错误；`node --test apps/mms-web/tests/*.test.mjs` 全过且数量不低于 83 加你新增的；`npm run build --workspace @mms/web` 通过。

## 并行规则

沿用 README：自己开 worktree `git worktree add ../wt-T1d -b bot/T1d-guide-on-bots codex/stride-370e87ec37e741df`，端口 61700，不碰 60824，不提交、不 push、不 merge。做完把 `git diff --stat`、测试命令与结果、截图路径、未完成项按 README 格式写进你 worktree 的 `walls.md`，然后汇报。
