# #307 返工 01 — Pilot 内的文件夹树

**基线**:`origin/codex/stride-7e934fe611bc41b4`,base `main`。**分支落后一个 release**(merge-base `f663db83`,`origin/main` 已到 4.22.4 之后),开工前先同步。

**先说结论**:核心症状真的修掉了。系统对话框整条删干净(`grep` 全仓只剩测试里的反向断言),换成一次 `os.scandir`,不持 mutation lock。验收方在真实实例上人为把请求拖到 8 秒,**界面全程可交互**,busy 期间有"正在列出文件夹…"的可见提示,ESC / × / 点 backdrop 三条出口全部实测能退,而且退出会 abort 在飞的请求。后端的安全边界逐条符合,四条后端 mutation 全部被抓。`components.tsx` 的 `Dialog` 一个字没动,改动收在 `LaunchOptions` 里 —— 这条做得对。

下面是必须修的。**其中两条是我包里写错了,不是你的问题**,我先说这两条。

---

## 先纠正我包里的两个错误

### 我错了一 · "这条路径改完之后没有平台分支"

我在包里写:"改完之后这条路径**没有任何平台判断**,所以 macOS 上验过就等于 Windows 上也对 —— 这一点很重要,因为我们没有稳定的 Windows 真机验证渠道。"

**这个前提对下半段成立,对上半段不成立。** `mms_web/workspace_browse.py` 里 `_windows_platform()` 被调用 **13 次**,分布在 8 个函数里,而且差异不只是"多列几个盘符":

- `_list_drives()`(`:60-83`)在 macOS 上直接 `return []`,整个函数体零执行
- `_ancestors_until_ceiling()`(`:133-145`):POSIX 走到 `/` 或 home 就封顶,Windows 两个 `if not _windows_platform()` 都跳过,于是**一路爬到盘符根**,可达集合两个平台不一样
- `_is_under()`(`:154-161`):POSIX 用 `parent in child.parents`,Windows 用 `child.relative_to(parent)`
- `classify_user_path(..., windows=True)` 的 `unc` 只有在 Windows 上才真正进入列目录逻辑,`scandir(\\server\share)` 完全未验证

所以正确的说法是:**逐层列目录、过滤、symlink、400 上限这些下半段,macOS 验过等于 Windows 对;树的顶层(盘符层)和可达边界这上半段,macOS 上一行都没跑过。** 这一点必须在交付里明写,不能含糊。

### 我错了二 · "不要重建 `mms_web_static/`"

包第十节我写了:"**不要重建 `mms_web_static/`。** dev 和 main 上改 `apps/mms-web/src` 的 commit 历来不带 bundle,只有 release commit 带。"

**这条后来被证明是错的,我已经纠正过,但你的包是在纠正之前写的,所以你按错的做了。** 遍历 `git log origin/dev -30 -- apps/mms-web/src`,`6d9001d6`、`88114765`、`f8c21cb2`、`5be8649a`、`a035c667` 五个非 release 的 fix/feat commit **全部同时重建了 bundle**,我逐个复核确认。仓库的实际约定是:**任何 `apps/mms-web/src` 改动都在同一 commit 重建 bundle。**

这条的后果你已经指出来了,而且很要紧:**合并 #307 本身不会让机主的 Windows 安装版好起来** —— 安装版跑的是 checked-in 的 `mms_web_static/`,里面仍是旧的 `/workspaces/choose` 代码。

**所以这一轮要重建 bundle。** 重建时先 `npm ci --workspaces=false --ignore-scripts`(严格按 lockfile),再跑 `python3 scripts/build_mms_web_release.py --skip-install` —— 上一轮 #304 就是因为用了本地漂移的 `node_modules`,在产物里夹带了一个未申报的依赖升级。

---

## 必改 1 · 三条 mutation 逃逸:测试从来没渲染过 `WorkspaceDialog`(P0)

| mutation | 结果 |
|---|---|
| 删掉 4.22.2 真正的焦点修复(`useEffect` + rAF + setTimeout 那段) | **88 pass / 0 fail**,tsc 也过 |
| 把弹窗里整块 `{browsing ? <FolderTree…> : …}` 删光 | **88 pass / 0 fail** |
| `BusyNotice` 永不渲染(只留 `<p className="muted">`) | **88 pass / 0 fail** |

根因是一致的:`renderToStaticMarkup` 只用在 `FolderTree` 和 `BusyNotice` 两个**孤立组件**上,而它们在弹窗里有没有被挂上,靠的是 `readFileSync(LaunchOptions.tsx)` + 正则去 grep(`workspace-folder-tree.test.mjs` 第 74/75、80、97-99 行共三处)。

**这正是包第七节明令禁止的写法**,而且是这批 PR 第四次栽在同一个地方(#281、#286、#303 各一次)。

**期望**:用 `renderToStaticMarkup` 渲染 **`WorkspaceDialog` 本身**(mock `api.request` / `mutate`),断言 browsing 态出现 `role="tree"` 和「使用这个文件夹」、busy 态出现 `.workspace-busy`。现有那三条正则断言可以保留(对"命名没漂"仍有价值),但不能是唯一看守。

**验证**:上面那三条 mutation 重跑,**每一条都必须红**。

## 必改 2 · autoFocus 的测试锁的是属性,不是修复

你加的测试断言 `autoFocus={WORKSPACE_SEARCH_AUTOFOCUS}` 这个属性字符串存在。但 4.22.2 真正的修复是 `LaunchOptions.tsx:112-121` 那段 `useEffect`(focus / rAF / setTimeout 三拍)—— 因为原生 `<dialog>` 的 `showModal()` 会把焦点抢到右上角关闭按钮,光有 `autoFocus` 属性是不够的,这正是当初要修的原因。

删掉那段 `useEffect`,测试 88/88 全绿。

**期望**:断言那段 `useEffect` 存在并且生效。最好在真 mount 之后查 `document.activeElement`。

**验证**:删掉那段 `useEffect` → 必须红。

## 必改 3 · 树里方向键是死的

两个最自然的状态下键盘完全无效:

- 点完「浏览其他文件夹…」之后 `FOCUS: {"tag":"BODY"}` —— 那个按钮 `disabled={!!busy}`,busy 期间被禁用导致失焦,busy 结束后没人把焦点还回去。此时按 `ArrowDown` 完全无效。
- 把焦点放到树行上(它们是 `<button>`)再按方向键,`selected` 不变 —— 因为 `onTreeKey` 只挂在**搜索 input** 的 `onKeyDown` 上(`LaunchOptions.tsx:245`),树行自己没有 `onKeyDown`。

手动 focus 回搜索框之后才正常(`ArrowDown` → selected 1,`ArrowRight` → 展开 5→16)。所以逻辑写对了,**缺的是焦点管理**。

包第六节要求"树也要能键盘走:上下移动、右键/回车展开、左键收起"。

**期望**:进入 browsing 之后把焦点还给搜索框,或者给树容器挂同一套 `onKeyDown` 并做 roving tabindex。

**验证**:真机 —— 点「浏览其他文件夹…」后**直接**按 ↓,`aria-selected` 必须移动;点一行之后按 ↓ 同样必须移动。

## 必改 4 · 窄屏树横向溢出 588px

390×844 实测:`treeScrollW 902` vs `treeClientW 314`。

`studio.css:1592` 新增的 `.workspace-matches .workspace-folder-row > span { flex: 0 0 auto; }`(特异度 0,2,1)把**两个** span 都命中了,压过下面的 `.workspace-folder-label { flex: 1; min-width: 0 }`(0,1,0)。于是 label 按 max-content 撑开,路径永不换行,整棵树要横向拖。搜索结果列表没这个问题(走的是旧的 `.workspace-matches button > span`)。

**期望**:那条规则只作用于 chevron(改成 `> .workspace-folder-chevron`),label 保留 `flex: 1; min-width: 0`。

**验证**:390×844 下 `treeScrollW === treeClientW`,且 `getComputedStyle(label).flex === "1 1 0%"`。

## 必改 5 · 手机上展不开

单击行只高亮,**展开只能双击或点那个 14×14 的 chevron**。手机没有 dblclick,14px 也远低于触摸目标下限。

包第三节把"手机 / 局域网访问天然可用"列为选这个方案的四个理由之一,第九节要求"窄屏 390×844 必须可用 —— 手机访问是这个功能的现实场景之一"。

**期望**:单击整行就展开/收起,或者把 chevron 的命中区扩到 ≥44px。

**验证**:390×844 真机单击一行,`aria-expanded` 必须翻转。

## 必改 6 · 400 项静默截断

`folder-tree.ts:17` 定义了 `truncated`,但 `loadEntries`(`LaunchOptions.tsx:158-161`)只取 `data.entries` 把它丢掉了。子目录超过 400 个时用户看到的是**静默截断** —— 他不知道还有更多。

同仓库 `ContextEvidence.tsx:28` 和 `FilesPanel.tsx:119` 都会提示,这里不一致。

**期望**:透出并在树尾显示一句,对齐 `FilesPanel.tsx:119` 的写法。

**验证**:造 410 个子目录,真机进去必须看到提示。

## 已经替你做掉的两条(必改 7、8)

机主一度找不到执行人,我先动手做了后端这两条,**已推到 `codex/stride-7e934fe611bc41b4`**(commit `0b11f941`)。你 pull 之后它们就在,不用重做 —— 下面两节留着是为了让你知道改了什么、以及怎么验。

顺带做的还有:合并了最新 `main`(分支原来落后一个 release),以及那条 `/` 可列的契约测试(见"我的裁决"一节)。

`tests/test_mms_web_workspace_browse.py` 现在 **18 passed**(原 13)。两条 mutation 我跑过:把 `_is_under` 退回裸 `relative_to` → 红;删掉 `ascii_uppercase` 回退分支 → 红。

**前端那六条(必改 1-6)我一行没碰**,都归你。

---

## 必改 7 · `_list_drives()` 零覆盖

盘符层是这个 PR 唯一的 Windows 专有逻辑,而它的两个测试(`test_mms_web_workspace_browse.py:149`、`test_mms_web_windows_workspace_picker.py:16`)**都把整个 `_list_drives` monkeypatch 掉了**,所以 `os.listdrives` 分支和 `string.ascii_uppercase` 回退分支的覆盖率是 **0**。

API 选型是对的:最低 Python 是 **3.11**(`.github/workflows/windows-acceptance.yml` 两个 cell 是 3.11,`install.sh:1466` 接受 python3.11),而 `os.listdrives()` 是 3.12+,所以用 `getattr(os, "listdrives", None)` 探测 + `ascii_uppercase` 回退是正确的,也没引新依赖。路径形态解析(`drive_root`/`drive_abs`/`drive_relative`/`unc`)在 macOS 上有单测,这条做到了。

**期望**:不要 monkeypatch 整个函数,改成 monkeypatch `os.listdrives` / `os.path.exists`,分别覆盖 3.12+ 路径和 3.11 回退路径。

**验证**:删掉 `string.ascii_uppercase` 回退分支 → 必须红。

## 必改 8 · `_is_under()` 的 Windows 分支缺 normcase

`workspace_browse.py:154-161`:Windows 分支用 `child.relative_to(parent)` 且**没有 normcase**,所以 `c:\users` 和 `C:\Users` 会判不相等。而同一个文件里的 `_same` 和 `_known_roots` **反而做了 normcase** —— 内部不自洽。

**期望**:Windows 分支两侧都 `os.path.normcase`。

**验证**:加一条 `_windows_platform=True` 的单测,`C:\Users\A` vs `c:\users` 必须判 under。

---

## 我的裁决 · `/` 可列这件事

你发现 `browse({"path": "/"})` 返回 13 项根目录,`/Users/xin` 返回 208 项(机主真实 home,尽管你跑在临时 HOME)。根因是 `_known_roots()`(`:176`)把**用户传进来的 path 本身**放进 `roots`,于是 `_may_list(target, roots)` 对任何显式绝对路径恒为 True。

你说得对,**这是我包里写的边界自相矛盾**:我既写了"用户在输入框里自己打出来的路径"算合法起点,又写了"不要做一个从根目录随便逛的入口"。这两条不能同时成立。

**裁决:接受当前行为,但要把它写成契约。**

理由:枚举文件系统这个能力**本来就存在** —— 用户可以粘贴任意路径创建 workspace,然后用 `/files/tree` 浏览它。#307 没有引入新的权限面,只是让同一件事更方便。而树 UI 要有用,就必须能从用户给的起点往下走。Pilot 的局域网访问有 token 保护,威胁模型里访问者是可信的。

**但现在这个行为没有任何测试锁住**,所以将来有人收紧或放宽都是无意识的。

**期望**:
- 补一条测试断言 `browse({"path": "/"})` 的行为(在 POSIX 上返回根目录列表),把它写成明确契约
- 在 `docs/mms-web/API.md` 里写明这个端点的边界:只返回目录、不返回文件内容、起点包括用户显式给出的绝对路径
- **不要**因此放宽任何过滤(`EXCLUDED`、隐藏目录、symlink 仍然照挡)

---

## 顺带发现的另一处同病灶(不在本包范围)

`mms_web/files.py:236-250` 的 `choose_local`(「添加内容」→ 选择文件)仍然是老样子:`sys.platform != "darwin"` + `osascript` + `subprocess.run(timeout=120)`,**而且它不在 `_UNLOCKED_POSTS` 里,持 mutation lock 最长两分钟**。Windows 上这条路径直接 409。

这比 #307 修掉的那个更糟 —— 持锁两分钟会把发消息、停会话、确认更新全部排队。我会单独立包,**不要在这一轮顺手改**。

---

## 交付要求

1. 八条必改 + 那条裁决要求的测试和文档
2. **重建 bundle**(见"我错了二"),方式:先 `npm ci --workspaces=false --ignore-scripts` 再 `python3 scripts/build_mms_web_release.py --skip-install`;重建后按同一算法重算 `sourceSha256` 和 `build.json` 比对
3. **同步到最新 `main`**(现在落后一个 release)
4. 每条的 mutation 结果写明(改了什么 → 红还是绿 → 红在哪条测试上)。**必改 1 那三条和必改 2、7 是专门用来证明测试不再是理论的,一条都不能少**
5. 门禁写实测绝对数:`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**)、`npm run build --workspace @mms/web`、相关 pytest、`studio.css` 裸 hex(base 48,不得增加)
6. **交付里必须明写**:盘符层(`_list_drives`)未经真 Windows 人工验证;以及这条路径的上半段仍有平台分支,macOS 的验证不覆盖它
7. 必改 3、4、5 改了用户可见行为,真机各验一次并存证据

起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**;**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill;绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**。
