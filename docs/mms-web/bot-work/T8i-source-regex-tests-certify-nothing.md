# T8i — 13 处 UI 逻辑可以被掏空,而测试全绿

**base**:`main`(文件夹树部分)+ `dev`(Bot / 会话部分)。两部分可以分两个 PR,也可以一个人接连做完。

**这不是"覆盖率不够"。** 这是一类**特定写法的测试在系统性地认证错误的东西**,已经在这个仓库反复出现。两次合并后复查,一共抓到 **12 条**(另有 1 条查实是误报)mutation,合并这批 PR 时又当场抓到 **2 条**:把生产代码掏空,整套测试仍然绿。**没有一条是机器抓到的。**

---

## 一、根因,先讲清楚,不然你会修错

有两种前端测试写法,它们的保护力差一个量级:

| 写法 | 能抓到 | 抓不到 |
|---|---|---|
| **读源码字符串**<br>`fs.readFileSync(...)` + `assert.match(/.../)` | 整块**删除** | **掏空**(留着壳,改掉行为) |
| **真编译真执行**<br>`esbuild` 提取 JSX → `renderToStaticMarkup` / 直接调 handler | 删除 **和** 掏空 | — |

12 条 green 全部落在第一类上。举个最干净的例子:

```jsx
// apps/mms-web/src/App.tsx:1478
onDoubleClick={(event) => {
  event.preventDefault();
  beginSessionRename(s);
  ...
}}
```

- **整个 `onDoubleClick` 删掉** → `session-rename-dblclick.test.mjs` 红 ✅
- **留着壳,把 body 换成 `if (false) beginSessionRename(s)`** → **240 条测试全绿** ❌

因为那条测试是 `assert.match(source, /onDoubleClick/)`。`onDoubleClick` 这个字符串还在,所以它满意了。**双击改名这个功能可以完全失效而没有人知道。**

仓库里已经有写对的例子,照着它们抄:

- `apps/mms-web/tests/bot-model-chip.test.mjs` —— 用 esbuild 提取真实 JSX 并**执行** handler
- `apps/mms-web/tests/reply-reader.test.mjs` —— 4/4 细粒度 mutation 全红,包括 IME 组字保护和 `showModal`
- `apps/mms-web/tests/bot-wait-controls.test.mjs:16-22` —— `react-dom/server` 真渲染的样板
- `apps/mms-web/tests/session-attention.test.mjs` —— 直接调被测函数

**要做的事就是:把下面 13 条对应的测试从第一类改写成第二类。** 不是加测试数量,是换写法。加一堆同样读源码的新测试等于什么都没做。

---

## 二、验收清单:这 14 条 mutation 必须全部变红

每条**单独跑**,记录红/绿。做完之前任何一条还是绿的,这个包就没完成。

### A 部分 —— 文件夹树(base `main`)

| # | mutation | 文件 |
|---|---|---|
| A1 | 去掉「重复按右方向键保持展开」的 `!rows[activeIndex].expanded` 守卫(第二次按变成收起) | `apps/mms-web/src/LaunchOptions.tsx:205` |
| A2 | 让 ArrowLeft 既不收起也不跳到父节点 | `LaunchOptions.tsx:207-209` |
| A3 | 删掉整个 `<span class="workspace-folder-chevron">` 渲染块(可见的展开标记 **和** 44px 触摸目标) | `apps/mms-web/src/folder-tree.ts:165-178` |
| A4 | 把每一行的 `aria-expanded` 写死成 `false` | `folder-tree.ts` |
| A5 | 删掉 `@media (max-width:390px)` 整条规则 | `apps/mms-web/src/studio.css:1593-1618` |
| A6 | 删掉 44px chevron 触摸目标 | `studio.css` 同段 |
| A7 | 删掉 `min-width:0` / `overflow-x` 溢出守卫 | `studio.css` 同段 |

**A1–A2 特别注意**:`LaunchOptions.tsx` **一条行为测试都没有**。现有的 `workspace-folder-tree.test.mjs:25` 是把它当**字符串**读(`launchSource`),只正则断言 `/workspaces/browse` 这个路径存在(:165-166);键盘测试(:151-162)只断言 `applyTreeKey` 返回 `"expand"` / `"collapse"` 这两个字面量 —— **解释这两个字面量的那段代码完全没人守**。

**已经查过、不用做的一条**(免得你重新推导一遍):`workspace_browse.py:268` 的 `child.is_symlink()` 去掉之后测试也是绿的,但那**不是覆盖洞** —— `child.is_dir(follow_symlinks=False)` 对 symlink 本来就返回 False,`is_symlink()` 是冗余的第二道。它读起来就是它做的事,留着没坏处。**不要动它,也不要为它写测试。**

### B 部分 —— Bot 与会话(base `dev`)

| # | mutation | 文件 |
|---|---|---|
| B1 | `onDoubleClick` 的 body 改成 `if (false) beginSessionRename(s)` | `apps/mms-web/src/App.tsx:1478` |
| B2 | 让终端会话(`owner === "cli"`)的改名守卫失效 | `App.tsx:1007` |
| B3 | 把旧版等待提示的显示条件换成 `false` | `apps/mms-web/src/Bot.tsx:2748` |
| B4 | `handleDismissWait` 改成直接 `return;` | `Bot.tsx:1787` |
| B5 | `handleAnswerWait` 改成直接 `return;` | `Bot.tsx:1767` |

**B4 / B5 是这一批里最要紧的**:这是 Bot 问你问题、你回答或忽略的那条路径。掏空之后 Bot 的提问**永远不会被应答**,而 240 条测试全绿。

**B2 是个权限守卫**:终端会话不该能在 Pilot 里改名(和行尾菜单的行为一致)。守卫失效没有任何测试会响。

### C 部分 —— 合并这批 PR 时新抓到的(base `dev`)

这两条是在 2026-09-17 合并 #328 / #329 时**当场**测出来的,不是历史欠账。它们证明这个洞还在持续产生,所以一并放进验收清单。

| # | mutation | 文件 |
|---|---|---|
| C1 | 保留 `scrollTo({ top: 0 })` 和 `.update-confirm h3` 这两段文字,但让两次调用都不执行 | `apps/mms-web/src/UpdateCenter.tsx:75-80` |
| C2 | 让 `Popover` 不再调用 `popoverPlacement`,改回 `{ top: box.bottom + 10, right: 12, width: panelWidth }` | `apps/mms-web/src/Popover.tsx:31` |

**C2 是这批里最说明问题的一条。** `popover-placement.test.mjs` 写得很好 —— 它 import 真函数、断言算出来的数字,正是这个包想要的写法。但它测的是**模块**,没测**接线**。把 `Popover.tsx` 那一行换回旧的右对齐,**265 条测试全绿** —— 而那正是 #329 要修的那个 bug:手机上弹出面板甩出屏幕。

**一个写对的纯函数测试,配上没人测的调用点,保护力是零。** 这是同一个洞的另一半,别只做上半截。

(我自己在 #325 里踩过一模一样的:测试直接实例化 `SetupHTTPServer`,把调用点改回裸 `ThreadingHTTPServer` 照样绿。当时的解法是把绑定拆成一个工厂函数,让测试走真正的调用路径 —— C2 可以照这个思路。)

---

## 三、顺带修的两个小问题(在同一个 PR 里)

1. **390px 下一屏只能看到 2.33 行。** 实测行高 `120 / 120 / 68` px,滚动框 280px,因为完整绝对路径会折成 4 行。没有横向溢出(`scrollWidth == innerWidth == 390`,合格),但太挤。**做法你定** —— 路径中段省略、只显示目录名、或者压低行高。别为了这个把 A5–A7 那三条 CSS 改没了。
2. **截断提示的文案和范围对不上。** `LaunchOptions.tsx:219` 是 `truncated = Object.values(truncatedAt).some(Boolean)` —— 只要**任何一层**截断过,后面**每一层**都会显示「这一层文件夹太多…」。要么让提示跟着当前层,要么改文案别说「这一层」。

---

## 四、这次有机器帮你了

在这个包开工前,`.github/workflows/digger.yml` 里**没有任何 job 跑前端测试或 `tsc`** —— 这正是这类问题反复出现的原因。PR #326 加了一个 `frontend` job,跑 `tsc --noEmit` + `node --test` + bundle 新鲜度检查。

**先确认 #326 已经合并再开工**,这样你的每一次 push 都有机器在守。

---

## 五、门禁

- `apps/mms-web/node_modules/.bin/tsc --noEmit -p apps/mms-web` —— **不要用 `npx tsc`**,仓库根目录会解析到一个同名的无关包,给你假的失败
- `node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带上**)。写 base/head 绝对数
- 这个包**只改前端和测试**,不碰后端。如果你发现必须动后端才做得到,先停下来说明
- `python3 scripts/ci_pytest_regression.py --base origin/main`(B 部分用 `origin/dev`)
- **改了 `apps/mms-web/src` 就必须在同一个 PR 里重建 `mms_web_static/`**:`cd apps/mms-web && npm ci --workspaces=false --ignore-scripts`,然后 `python3 scripts/build_mms_web_release.py --skip-install`。**按 workspace 装,不要在仓库根目录装** —— 根装会解析出 lockfile 之外的传递依赖,产出不同的 bundle
- 不要用 `sourceSha256` 证明 bundle 对得上,它只覆盖 src 和 5 个配置文件,不覆盖装好的 `node_modules`

---

## 六、边界

- **不要**为了让 mutation 变红而放宽现有测试。现有测试必须继续全绿
- **不要**把第一类测试**删掉**换成第二类 —— 在原地改写,或者保留旧的再加新的。删掉红测试是另一个已经发生过的事故(见 `T8g` 同批的 #326)
- **不要**顺手重构 `LaunchOptions.tsx` 或 `Bot.tsx` 的结构。只改到能被测试为止
- **不要**碰保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`
- **绝不**碰端口 8767 / 60824 / 8765 / 8766;起验证实例用 61000-62000 的随机端口,**只 kill 自己启动的 PID**,绝不按端口或进程名批量 grep 后 kill,绝不用 `pkill`
- **绝不**写真实 `~/.config/mms*` 或 `~/.local/share/mms-web`。跑测试前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`,并在交付里说明你怎么确认隔离生效的

## 七、交付

- 提 PR(A 部分 base `main`,B / C 部分 base `dev`),**不要** merge
- 交付里逐条列出第二节那 14 行的红/绿 —— **这是这个包唯一的验收标准**
- 门禁实测数、bundle 是否重建、第三节两个小问题各自怎么处理的
- 不碰版本文件。版本由合并方 bump
