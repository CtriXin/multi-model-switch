# T1 · Bot 界面视觉系统重做（本轮重点）

Task: 370e87ec37e741df · 分支 `bot/T1-ui` · 建议模型 gemini3.6 主做，glm5.3 评审
先读：`docs/mms-web/bot-work/README.md`、`apps/mms-web/DESIGN.md`、`apps/mms-web/PRODUCT.md`、`docs/mms-web/CLAUDE-CONTINUATION.md` 的"用户明确在意的体验"一节。如果你的环境装了 `impeccable` 或 `design-taste-frontend` skill，先加载再动手。

## 目标一句话

Bot 页面要和 Pilot 是同一个产品：同一套主题色、同一套字号、同一种对话阅读感。用户看到的是"和同事聊天"，不是管理后台。

## 只许改 / 不许改

只许改：
- `apps/mms-web/src/bot.css`、`bot-memory.css`、`bot-communications.css`
- `apps/mms-web/src/Bot.tsx`、`BotStudio.tsx`、`BotMemoryPanel.tsx`、`BotCommunications.tsx`、`BotArtifactPreview.tsx`（只改 JSX 结构和 className，不改数据流、请求、状态机）
- `apps/mms-web/DESIGN.md`（追加"Bot 页面"一节）
- `apps/mms-web/tests/` 里新增纯函数测试

不许改：`studio.css` 的 token 定义（可以新增 Bot 专属 token，不能改已有值）、`App.tsx`、`types.ts`、任何 `mms_web/*.py`、任何 `tests/*.py`。T2 会往 `Bot.tsx` 插一个 `<BotPlan>` 组件，插入点在 `BotChat` 的任务详情区，你不要改那一带的逻辑。

## 现状诊断（对照截图）

### 1. 主题只有黑色，根因是 bot.css 无视 token

App 已经有完整主题系统：`App.tsx` 第 503 行把 `data-theme=light|dark` 写到 `<html>`，`studio.css` 第 2 到 40 行定义 `--bg --surface --ink --muted --line --soft --accent --accent-hover --danger --amber --success`，加五种 `data-accent`。

`bot.css` 有 225 处硬编码 hex，`bot-memory.css` 61 处，`bot-communications.css` 35 处。全部挂在 `.app-shell[data-page="bots"]` 下用高优先级覆盖，所以用户切浅色、换强调色，Bot 页面纹丝不动。

`bot.css` 是三层叠出来的：
- 第 1 到 130 行：最早的 dashboard 版（`bot-workspace-grid`、`bot-dispatch`、`bot-task-list`、`bot-event-feed`、`bot-inspector`、带图标和计数的 section heading）。
- 第 131 到 310 行：第二版把它整体刷黑做成聊天壳。
- 第 311 到 560 行：v2.2 按参考图再覆盖一次。
- 之后是预览弹窗和 onboarding。

"太像管理后台"的根子就在第一层还活着，后面两层是补丁。

### 2. 左边缘有四条

截图里一条对话内出现了四个不同的起始 x：
- 用户消息：贴列左边缘，长消息撑满整列（`width: fit-content !important` 与 `max-width` 互相打架，长文本时变成整行灰条，看起来像系统横幅，不像用户说的话）。
- 成果卡（`bot-proof.txt`、`collaboration.txt`）：贴列左边缘，但 Bot 文字在头像右侧 60px 处。`.bot-chat-artifacts` 在三处分别写了 `margin-left: 32px`、`auto`、`40px`，后者赢。
- Bot 回复：头像列 + 文字列。
- 等待提示、"已发消息给 调度 · 3条消息往来"、错误块：各自 32/40px 或整行边框条。

### 3. 成果卡尺寸随机

`.bot-chat-artifacts` 用 `repeat(auto-fit, minmax(150px, 1fr))`，一个文件卡和一个截图卡并排时一个 530px 一个 600px，截图被拉成 16:10 的大图卡塞在第二列。

### 4. 身份标记不统一

Bot 列表和头部用 pixel 头像；执行中的回复头像被换成蓝色 LoaderCircle 转圈；结束回复的 mark 是绿色方块。同一个 Bot 三种脸。

### 5. 卡片右侧图标簇（截图 1）

`BotCard`（`Bot.tsx` 第 268 到 345 行）在一行里放了 编辑（Settings2 滑杆图标）+ 删除（Trash2），再把自动唤醒（AlarmClockCheck，绿色）用 `position: absolute; right: 7px; bottom: 6px` 钉在右下角，和删除按钮叠成两行。滑杆图标没人知道是"编辑"。

### 6. 零散的后台味

- 头部右侧四个东西：记忆、协作·8、待命、刷新图标。刷新是开发者动作。
- 消息上方有 "你" / "大总管" 小标签，Pilot 不这么做。
- Onboarding 是一个独立的浮动面板（带边框圆角、居中、比消息窄），和消息流不是一个语言。
- 输入框底部 "立即执行" 是个 label 伪装的开关，读起来像状态文字。
- 各处 `border + box-shadow 0 24px 80px` 的幽灵卡。

## 设计规范（照这个做）

注册：product register，Restrained 色彩策略。工具要消失在任务里。

### 主题
- 全部颜色走 token。允许新增 Bot 专属 token，定义在 `bot.css` 顶部的 `:root` 与 `:root[data-theme="dark"]` 两处，语义命名（`--bot-bubble-user`、`--bot-avatar-1..6` 等），值用 `color-mix()` 从 `--accent`、`--surface`、`--ink` 派生。
- 六种头像色各给浅色 / 深色两组值，pixel 图案在两种主题下都要有 ≥ 3:1 对比。
- 做完后 `grep -c "#[0-9a-fA-F]\{3,8\}" bot*.css` 三个文件合计 ≤ 12，且只允许出现在 token 定义处。
- 五种 `data-accent` 都要看一遍：选中态、发送按钮、链接、状态点跟着变。

### 版式
- 字体沿用 Pilot：系统 sans；正文 15px，辅助说明 13px，工具行和时间 12px，最小 11px。字号用固定 rem，不用 clamp。
- 对话列宽 `min(880px, 100% - 48px)`，居中。不再用 `.bot-chat-stream > *` 强制每个子元素同宽。
- 标题只有一个：头部 Bot 名 17px / 600。消息内不再有 "你" / "Bot 名" 标签；发送者靠左右位置和头像区分。

### 一条左边缘
定义一个内容基线：
```
--bot-gutter: 40px;   /* 头像 28px + 间距 12px */
```
- Bot 发出的所有块（正文、成果、等待提示、协作标记、错误、T2 的计划块）都从 `--bot-gutter` 开始，宽度到列右边缘为止。
- 用户消息：右对齐气泡，`max-width: 66%`，`width: fit-content`，不允许撑满整列；圆角 14px，右下角 4px；背景 `--bot-bubble-user`，文字 `--ink`。
- 连续同一发送者的消息只在第一条显示头像，后续留出 gutter 空位。
- 时间戳 hover 才出现，放在气泡外侧。

### 成果与附件
- 成果作为 Bot 消息的附件行，位于该消息正文之下、同一 gutter 内。
- 文件卡固定：高 44px，宽 `min(280px, 100%)`，图标 + 文件名 + 大小，`flex-wrap`。
- 图片卡固定：缩略图 200×125 `object-fit: cover`，下方文件名 12px。多张横排换行。
- 卡片只有 1px `--line` 边框，无阴影；hover 边框变 `--accent`。
- 点击行为不变（仍走现有预览弹窗）。

### 头像与状态
- 全站唯一身份标记：pixel 头像。列表 30px，头部 36px，消息 28px。
- 执行中：头像外圈 2px `--accent` 描边呼吸（`prefers-reduced-motion` 时静态），不替换头像。
- 结束：不再显示绿色方块；正文照常出现即可。失败：正文前一行 `--danger` 色短句。
- 状态文案保持"待命 / 执行中 / 等待你 / 已排队"，状态点 6px。

### Bot 列表卡（截图 1 的修法）
- 卡内一行：头像、名字、状态点 + 状态词；第二行描述或当前任务，单行省略。
- hover / focus-within 时右侧出现一个 `MoreHorizontal` 按钮，打开原生 popover 菜单：编辑 Bot、删除 Bot。触屏常显。
- 自动唤醒不再是绝对定位图标：开启时在状态词后追加 `· 自动唤醒`，用 `AlarmClockCheck` 12px 前缀。
- 不允许任何 `position: absolute` 叠图标。

### 头部
- 左：头像、名字、描述。右：记忆、协作（带数字），两个 quiet 按钮同样式。状态词进名字旁边。刷新按钮删掉（数据本来就轮询）。
- 头部高 64px，1px `--line` 下边框，无阴影。

### Onboarding
- 渲染成一条普通的 Bot 消息：正文 + 一排选项 chip（`--soft` 背景，选中变 `--accent` 描边）。不再是浮动面板。
- 已回答的 chip 保留选中态，可点击改。

### 输入框
- 沿用 Pilot 输入区：`--surface` 背景、1px `--line`、圆角 14px、轻阴影 ≤ 8px 模糊，二选一不能同时有大阴影和边框。
- 底部左侧：一个真正的按钮 `定时…`，点开显示日期时间控件；未设置时显示 `立即执行`，设置后显示时间并可清除。右侧发送按钮 32×32。
- Enter 发送、Shift+Enter 换行、composition 不误发（现有逻辑不改，只改样式）。

### 通用
- 每个交互元素有 default / hover / focus-visible / active / disabled 五态；focus 用 2px `--accent` outline。
- 过渡 150 到 200ms，ease-out。
- 不出现横向滚动条：1440 / 1024 / 768 / 400 四个宽度各查一次。
- 正文对比度 ≥ 4.5:1，两种主题各测一次。
- `bot-memory.css`、`bot-communications.css` 同样换 token，视觉与主对话一致。
- 第一层 dashboard 样式：先 `grep` 每个 class 在 TSX 里还有没有渲染路径。仍在用的（`TaskInspector`、`DispatchForm`、`EventFeed` 等）按新规范重做；确认无渲染路径的删掉 CSS 和对应 TSX 死代码，并在汇报里列出删了什么。

## 禁止
- 渐变文字、装饰性玻璃、卡中卡、大圆角（卡 ≤ 14px）、`border-left` 色条、`z-index: 999`。
- 新字体、新依赖。
- 改任何请求、状态机、轮询、事件解析逻辑。样式任务不碰行为。
- 重启 60824。

## 验收
1. 自建实例（README 第 5 条，建议端口 61101），用 ego-browser 截图放到 `docs/mms-web/design/t1/`：浅色、深色各一张对话页；靛蓝 + 另一种强调色各一张；1024 与 400 宽各一张；Bot 列表 hover 态一张。
2. 一条包含 用户消息、Bot 长回复（含列表和代码）、文件成果、截图成果、等待提示、协作标记、失败消息 的对话，所有 Bot 侧块左边缘 x 相同（截图里用 DevTools 量，写进汇报）。
3. `npm run build --workspace @mms/web` 通过；`node --test apps/mms-web/tests/*.test.mjs` 逐个通过。
4. hex 计数 ≤ 12。
5. `apps/mms-web/DESIGN.md` 追加"Bot 页面（2026-09-12）"一节，写清 token、gutter、附件规格。
6. 按 README 的汇报格式写 walls.md。
