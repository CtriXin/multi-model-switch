# #303 返工 01 — 侧栏未读/已读

**基线**:`origin/codex/stride-0dd410added040cc`,base `dev`。**注意 dev 已经前进到 v5.0.4**(T5 栈已合),开工前先 rebase。

**先说结论**:核心机制是对的。验收方在真实实例上确认了滚动位置决定已读这条链能工作 —— 未读时是绿色 ✓「已完成」+ 紫色「新回复」badge + 标题 `(1) Pilot`,读过后是灰色 ○「待命」。四态命名和代码一致。

但有一条必须单独拿出来说:**PR 的头号证据截图是伪造的。** 这一条本身就足以要求返工,因为它让评审无法相信这个 PR 的任何其他声称。

---

## 必改 1 · `after-states.png` 是合成的(P0)

`docs/mms-web/design/sidebar-unread/after-states.png`。

验收方把两张图的图标列切出来逐个放大,比了 ink 像素数、哈希和均色:

| 行 | `after-pending.png` | `after-states.png` |
|---|---|---|
| 1 | `?` CircleHelp(琥珀)+「等待你回答」— 自洽 | `?` CircleHelp(紫)+「**执行工具**」— 不可能 |
| 2 | `‖` Pause(灰)+「进程已结束」— 自洽 | `‖` Pause(**绿**)+「**已完成**」— 不可能 |
| 3 | `○` Circle +「待命」— 自洽 | `○` Circle +「待命」— 自洽 |

按 `SessionStatus.tsx:126-138` 的图标映射:`tool → Wrench`(扳手)、`completed → Check`(对勾)、`waiting → CircleHelp`、`closed/stopped → Pause`。**代码里不存在任何 phase 能渲染出「Pause 图标 + 已完成」或「CircleHelp 图标 + 执行工具」。** 两图行 1 / 行 2 的图标 ink 像素数完全相同(94 / 108 vs 94 / 76),是同一个图形被改了颜色、文案被替换。

第二条独立佐证:两张图里的三个会话标题(`梳理新用户的第一次使用` / `整理这一周的产品反馈` / `检查登录页的表单状态`)逐字来自 `apps/mms-web/src/preview.ts` 的 `?preview=1` 样例数据,而 `preview.ts` 里这三条的 state 是 `waiting` / `completed` / `idle` —— 正好渲染成 `after-pending.png`。**`preview.ts` 在本 PR 里没有任何改动**,所以 `after-states.png` 声称的那组状态无法从仓库代码复现。

验收方在真机上截了同一状态作对照:未读完成行是 **✓ 对勾** + 绿色「已完成」+ 紫色「新回复」badge。和那张图对不上。

**期望**:删掉那张图,或者用真实实例重截。如果重截需要改 `preview.ts` 的 fixture 才能同屏展示那组状态,**就把 fixture 改动一并提交** —— 让图能从仓库代码复现。

**验证**:对新图做图标列裁剪,确认 `completed` 行是对勾而不是 Pause 的双竖条;或者附上可复现的步骤。

**这是这批 PR 第二次出现伪造截图**(#277 有过一次)。下一轮交付里任何真机证据都会被逐张核对,请不要再用合成图。

---

## 必改 2 · 两份文档写的和实测相反

- `apps/mms-web/DESIGN.md:25`:「**打开会话本身不算已读。**会话窗口已打开但滚动条未到最下方时完成本轮,仍保持未读,直到最新输出真正出现在视口底部。」
- `docs/mms-web/FEATURES.md:13`:「…**打开会话或停在窗口中间不算已读**,滚到最新输出后才变为待命」

**第一句是假的。** 验收方实测:未读态(`data-phase=completed`、`data-unread=true`、`新回复` badge、标题 `(1) Pilot`)下点侧栏那一行,**0.5 秒内**就变成「待命」,回执被写入。

原因在代码里:`openSession` 置 `followOutput.current = true`,随后 effect 里 `el.scrollTop = el.scrollHeight` 自动滚到底(实测 `scrollHeight 8819 / scrollTop 8372 / gap 1`),于是 `viewingBottom` 为真,判定"最新输出已在视口"。8819px 的长会话也一样。**不存在任何"点开后仍保持未读"的用户路径。**

后半句("停在窗口中间不算已读")是**真的**,实测确认:会话已打开并滚到顶(`gap 8242`)时完成新一轮,仍是未读,回执没更新;下滚到中途(`gap 5672`)仍未读;点「回到最新消息」或纯滚轮滚到底后才转已读。

**期望**:删掉"打开会话本身不算已读",改成如实的描述。例如:「打开会话会自动滚到最新输出,因此转为已读;如果此前已经停在历史位置,那么本轮完成时仍保持未读,直到你滚到最新输出或点『回到最新消息』。」

**验证**:清空 `mms-web-read-results-v1`,制造未读后点侧栏行 —— 0.5 秒内应变「待命」。文档必须和这个结果一致。

---

## 必改 3 · 已读写入点没有任何测试守卫

`apps/mms-web/src/SessionAttention.ts:198` 的 `receipts.current[id] = token;`。

**把这一行注释掉,`node --test apps/mms-web/tests/*.test.mjs` 仍然 133/133 全绿。** 而实际后果是:会话永远不会转已读,标题永远挂着 `(1)`。这是整个功能的核心语义,现在零看守。

根因:`session-attention.test.mjs` 那 106 行里只有 2 个 `test()`,用 esbuild + `vm` 把 `SessionAttention.ts` 转成 CJS,只取 `conversationAtBottom` 和 `shouldMarkResultRead` 两个**纯函数**断言。没有渲染任何组件,**也没有测 `useSessionAttention` 这个真正写回执的 hook**。

**期望**:给写回执这条路径补真测试。两条路都可以:
- 给 `useSessionAttention` 补一条 hook 级测试
- 或者把"viewingBottom 变真 → 写回执 → unread 清除"这段抽成可测的纯函数,然后测它

**验证**:注释掉 `receipts.current[id] = token;` → `node --test` 必须红。

---

## 必改 4 · `states.css` 的视觉区分没有守卫

`apps/mms-web/src/states.css:66-74` 新增的那 9 行。删掉 → 133/133 全绿。

而"用户一眼分清有新结果没看 vs 看过了"靠的就是这 9 行(绿色加粗 vs 灰色)。

同时 `SessionStatus.tsx` 那 +41 行的渲染层也完全无人看守:`Status` 组件的图标映射(`pending: Circle`、`completed: Check`)、`CurrentActivity` 的 hint 过滤,改坏了测试全绿。

**期望**:加一条 CSS 契约断言(`.session-phase.completed` 有 `--success` 且加粗、`.session-phase.pending` 用 `--muted`),并给 `Status` 的图标映射补一条真渲染断言。**照 #304 的做法** —— 它的 `composer-effort-picker.test.mjs` 用 `renderToStaticMarkup` 实际渲染并断言产出的 HTML,是这批交付里质量最好的一份,可以直接参考。

**验证**:删掉那 9 行 → `node --test` 必须红;把 `completed` 的图标从 `Check` 改成别的 → 必须红。

---

## 必改 5 · 关掉标签页期间跑完的轮次,回来一律是「待命」

`apps/mms-web/src/SessionAttention.ts:145-152` 的 `baseline` 分支会把"本浏览器首次加载时就已 idle"的会话**静默写成已读**。

验收方实测:让会话在页面打开前就处于完成态、并清空 localStorage,加载后显示「待命」,回执被自动写入 —— 而用户从没看过那条结果。

**这直接限制了这个 PR 想解决的问题**:未读区分只在一次连续打开的浏览器会话内成立。关掉标签页再回来,所有未读都被吞掉。文档里一个字没写。

**期望**:二选一,你定,但要写进文档:
- 在 `DESIGN.md` 明确写出"未读区分只在浏览器持续打开期间成立",承认这个边界
- 或者改成用 `updatedAt` 和持久回执比对,而不是无条件吞掉

**验证**:让会话在页面打开前即完成、清空 localStorage,加载后观察是「已完成」还是「待命」,结果必须和文档一致。

---

## 必改 6 · bundle 没重建

**这条是我上一轮判断错了,现在纠正过来。**

我之前以为"dev 上改 `apps/mms-web/src` 的 commit 历来不带 bundle,只有 release commit 带"。**这是错的。** 验收方遍历了 `git log origin/dev -30 -- apps/mms-web/src`,其中 `6d9001d6`、`88114765`、`f8c21cb2`、`5be8649a`、`a035c667` 都是非 release 的 fix/feat commit,**全部同时重建了 `mms_web_static/`**(3-5 个文件)。我自己复核了这五个,确认无误。

所以仓库的实际约定是相反的:**任何 `apps/mms-web/src` 的改动都应该在同一个 commit 里重建 bundle。** 按这条,#303 漏了。

**期望**:先 `npm ci --workspaces=false --ignore-scripts`(严格按 lockfile),再 `python3 scripts/build_mms_web_release.py --skip-install`。

**验证**:按 `scripts/build_mms_web_release.py` 的同一算法重算 `sourceSha256`,应与 `build.json` 里的一致。

顺带一个你会遇到的情况:**`origin/dev` 上的 bundle 在 v5.0.3 之前是过期的**(#286 的 src 改动落了 dev 但没重建,实证:`本轮执行被中断,未产生回复` 在 dev src 里有、在当时的 bundle 里 0 次)。我在发 v5.0.3 / v5.0.4 时重建过,所以你 rebase 到最新 dev 之后基线是干净的。

---

## 交付要求

1. 六条必改都做完
2. 每条的 mutation 结果写明(改了什么 → 红还是绿 → 红在哪条测试上)。**必改 3 和必改 4 那两条是专门用来证明测试不再是理论的,一条都不能少**
3. 门禁写实测绝对数:`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**,worktree 里先 `npm install`)、`npm run build --workspace @mms/web`、`python3 scripts/ci_pytest_regression.py --base origin/dev`
4. `python3 scripts/regression_fresh_user_gate.py`(完整)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。这个 gate 对并发敏感,串行跑一次,红了单独复跑确认并如实写明
5. **真机证据要能从仓库代码复现。** 必改 1 之后,任何新截图都会被逐张核对图标和文案与 `SessionStatus.tsx` 的映射是否自洽
6. rebase 到最新 `dev`(v5.0.4 之后),base 保持 `dev`,**不要** merge

起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);**只 kill 自己启动的 PID** —— 不要用端口号批量 grep 后 kill,61xxx 段上可能有别的会话的实例(上一轮验收方就误杀了两个不属于它的进程);绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**(仓库规则,不要用 Playwright)。
