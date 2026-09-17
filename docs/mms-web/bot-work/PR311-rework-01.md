# #311 返工 01 — 助手回复专注阅读

**基线**:`origin/codex/stride-a485945b68b64048`,base `dev`。**dev 已经前进到 v5.0.5**,开工前先同步。

**先说结论**:弹窗本身是对的,而且截图是真的。验收方自己把源码构建出来、在同一视口打开同一个 sample 会话截图,和你提交的 `reader-open.png` 做逐像素比对 —— **零个不同像素**。这批 PR 出过两次伪造截图,你这张经得起查。

真机实测通过的部分:悬停出入口(未悬停时 `pointer-events:none`,不拦截)、`dialog[open]` 且 `:modal` 为真、长正文单独滚动而页面不滚(`bodyScrollH 7599 / clientH 656`,`scrollY` 始终 0)、Esc / 点遮罩 / × 三条关闭路径都通、**弹窗内 Enter 不会误发 composer**(草稿一字未动)、关掉后 composer 的 Enter 仍是发送、窄屏 390×844 可用无横向溢出、`transcript.css` +75 行裸 hex 增加 **0**、`components.tsx` 的 `Dialog` 一行未动(你另起了一个 `<dialog>`,有重复但取舍合理)。

下面三条要修。

---

## 必改 1 · bundle 无法用仓库 lockfile 复现(P0)

和 #304 上一轮**同一个形态**,连夹带的包都一样。

`sourceSha256` 自查是**过的**(manifest `8b35190e…` == 实算,96 个文件逐项对上)。但按 lockfile 复现不过:

- `cd apps/mms-web && npm ci --workspaces=false --ignore-scripts`(`added 123 packages`,**零 lockfile mismatch 警告**)后重建 → 产出 `index-6C4gqord.js`(sha `5412bd37…`)
- 你提交的是 `index-BAxf71_M.js`(sha `b92c6b68…`)
- CSS、favicon、vendor 下 18 个文件全部 MATCH,只有 JS 和随之而来的 `index.html`、`build.json` DIFFER
- 两个 JS 差 **28 字节**,首个差异在 offset 367247,是 `micromark-extension-gfm-table` 的 `EditMap` 实现:你的产物里是 **2.1.2** 的 `this.index = new Map`,而 lockfile 钉的是 **2.1.1**
- **决定性验证**:验收方只把 `node_modules` 里那个包换成 2.1.2(不动 lockfile)重建 → 四个文件 digest **bit-for-bit 与你提交的一致**

`git diff -- package.json package-lock.json apps/mms-web/package.json` 是**空的**,所以这次依赖漂移**未申报**。

**期望**:二选一,不要两边都不做。
- 干净环境 `cd apps/mms-web && npm ci --ignore-scripts` 之后重跑 `python3 scripts/build_mms_web_release.py --skip-install`,用那份产物替换提交里的 `mms_web_static/`;或者
- 如果确实要用 `micromark-extension-gfm-table@2.1.2`,**把 `apps/mms-web/package-lock.json` 的更新一并提交**,并在 PR 里申报这次依赖升级(`AGENT.md`:加依赖前先告诉用户)

**验证**:`npm ci` 后重建,`git status --short mms_web_static` 必须为空。

### 顺带一条仓库级结论,你不用做,但要知道

`sourceSha256` **不是可复现性 gate**。它覆盖 `src/**` 加 5 个配置文件(含 lockfile 的**文本**),但不覆盖**实际安装的 `node_modules``。本次它完美 MATCH 而产物 DIFFER,正是这个盲区的实例。

#304 新加的那条门禁(`test_packaged_web_bundle_matches_source`)能抓的是另一件事 —— "src 改了但 bundle 没重建",那条很有用,合并冲突时当场抓红过。两条互补,都不能替代对方。真正能抓这一类的只有"`npm ci` 后重建、比对 `build.json.files` 全表",成本是每个 PR 的 CI 多几分钟,暂时靠人工验收和纪律守着。

---

## 必改 2 · 三条 mutation 全绿:整个功能可以从 `EventView` 删光(P0)

| 我删了什么 | 用户实际看到 | `node --test` |
|---|---|---|
| `components.tsx` 的 `EventView` 里整块 `<ReplyReader …>` | 按钮还在,点了什么都不会发生,**功能完全不存在** | **159 pass / 0 fail** |
| `onKeyDown` 里 `act === "close"` 分支(连同 `onCancel`) | Esc 关不掉 | **159 pass / 0 fail** |
| `act === "copy"` 分支 | Enter 不复制 | **159 pass / 0 fail** |
| 整个 `onKeyDown` handler | 键盘全废 | **159 pass / 0 fail** |

`reply-reader.test.mjs` **是真渲染**(esbuild 转真 TSX + `renderToStaticMarkup`,范式对),问题是**它只单独渲染 `ReplyReader` 和 `MessageActions` 两个叶子,从不渲染 `EventView`** —— 而 `EventView` 才是把按钮、状态和弹窗接起来的那一层。keydown 一次都没模拟过,只测了纯函数 `replyReaderKey` 的返回值,**没测那个返回值有没有被用上**。

这是这批 PR 第五次栽在同一个地方(#281、#286、#303、#307 各一次)。

**期望**:补上能锁住整条链路的测试。照 `composer-effort-picker.test.mjs` 的路子渲染 `EventView`,断言"assistant 事件带 `onRead`、`reading=true` 时输出 `.reply-reader`";keydown 要真模拟,断言 **handler 按 `replyReaderKey` 的返回值做了对应动作**,而不是只断言那个函数返回什么。

**验证**:上面那四条 mutation,**每一条都必须红**。

---

## 必改 3 · 弹窗刚打开时,第一下 Enter 是关窗而不是复制

footer 上写着「Esc 关闭 · Enter 复制原文」,但真机实测:

```
F. fresh open activeEl: BUTTON[aria-label="关闭阅读"]
   after immediate Enter -> dialog open? false
```

原生 `<dialog>` 的 `showModal()` 会自动聚焦第一个可聚焦元素,也就是右上角的 × 按钮。此时 `replyReaderKey` 对 `BUTTON` 返回 `null`,于是走原生按钮 click → **窗被关掉**。用户必须先点一下正文,焦点变成 `DIALOG.reply-reader` 之后,Enter 才会复制(验证过:footer 变「Enter 已复制」、弹窗保持打开、composer 草稿一字未动)。

也就是说:**你写在界面上的承诺,用户照做的第一下就不成立。**

顺带一提,这和 4.22.2 修过的那个 bug 是同一个根因 —— `showModal()` 抢焦点。那次是抢到关闭按钮导致 `autoFocus` 失效,这次是抢到关闭按钮导致 Enter 语义反转。

**期望**:`showModal()` 之后把焦点主动移到正文(给 `.reply-reader-body` 加 `tabIndex={-1}` 然后 `focus()`),或者在 `replyReaderKey` 的 `BUTTON` 例外里排除这个关闭按钮。改完把这条也写进测试。

**验证**:真机 —— 打开弹窗后**直接**按 Enter,必须是复制(footer 变「已复制」、弹窗保持打开),不是关闭。

---

## 可选 · 窄屏多出来的 4dvh 用不上

`@media (max-width: 700px)` 把 `dialog.reply-reader` 的 `max-height` 放宽到 `96dvh`,但 `.reply-reader-body` 的 `max-height: calc(92dvh - 120px)` 没跟着放。纯浪费,不影响可用性。

---

## 合并顺序:你排在最后

`dev` 上还有 #303、#308 在等着合,它们和你**源码零冲突**,但**都重建了 bundle**,所以 `mms_web_static/*` 必然互相冲突(rename/delete + `build.json` + `index.html`)。

验收方建议你**最后合**,理由很实际:你的 bundle 本来就要重做(必改 1),排最后正好只重建一次。

另外 #308(Grok harness)和你都碰 `components.tsx`,但它只在 `harnessNames` 里加一行 `grok: "Grok"`,你改的是 `EventView`,`merge-tree` 实测 `components.tsx` 干净。语义上还互补 —— 你的弹窗标题正是 `harnessNames[detail.session.harness]`,#308 合了之后 Grok 会话的标题就能正确显示成「Grok · <模型>」。

**解 bundle 冲突时不要挑一侧** —— 那会让 bundle 和合并后的源码脱节。正确做法:把两侧带哈希的 assets 都删掉,`build.json` / `index.html` 随便取一侧占位,然后 `npm ci` + `build_mms_web_release.py --skip-install`,把重建产物一并提交。#304 刚按这个流程走过,`test_packaged_web_bundle_matches_source` 当场验收通过。

---

## 交付要求

1. 三条必改做完(可选那条随意)
2. 每条的 mutation 结果写明。**必改 2 那四条一条都不能少**
3. 门禁写实测绝对数:`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**)、`npm run build --workspace @mms/web`、`python3 -m pytest tests/test_mms_release_version.py`(dev 上现在有两条,第二条会校验 bundle 和 src 一致)
4. 必改 3 改了用户可见行为,真机验一次并存证据
5. 同步到最新 `dev`,base 保持 `dev`,**不要** merge

起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**;**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill;绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**。
