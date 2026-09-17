# T8a — 选项目文件夹不再依赖系统对话框

**base**:`main`(4.22.x 稳定线)。修完默认回流 `dev` —— 两条线的相关代码逐字相同,所以是同一处修复,不是两份。

**这不是止血包。** 机主明确要求彻底修复,不要"加个 owner window 然后把超时对齐"。裁决在第三节。

---

## 一、症状(Windows,机主实测)

用户在「找到你的项目」弹窗里点「浏览其他文件夹…」:

1. 什么都没弹出来,等了十几秒后弹窗里出现橙色提示:「文件夹选择器没有打开。请直接输入完整的 Windows 路径,例如 `C:\Users\Admin\Downloads`。」
2. **在那之前的十几秒里,整个界面什么都点不了,也关不掉。**

第二条是这个包要解决的核心问题。第一条是它的起因。

---

## 二、根因,逐条核实过

### A. 对话框其实弹出来了,只是在浏览器窗口后面

`mms_web/server.py:388` 的 PowerShell 脚本:

```powershell
Add-Type -AssemblyName System.Windows.Forms;
$d=New-Object System.Windows.Forms.FolderBrowserDialog;
$d.Description='选择 MMS 的工作文件夹';
if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){ ... }
```

`$d.ShowDialog()` 是**无参重载,没有 owner window**。WinForms 这个重载只能拿当前进程的活动窗口当 owner,而 `server.py:397` 用的是 `subprocess.run(command, capture_output=True, ...)` —— stdout/stderr 都被重定向,PowerShell 没有可见控制台可以充当 owner。结果是这个对话框的 Z 序不保证在浏览器前面,大概率被整个盖住。

用户看到的"没有打开",实际是"打开了,在别的窗口后面,而且不会闪任务栏"。

### B. 那十几秒里界面完全锁死,而且五条出路全堵

`apps/mms-web/src/LaunchOptions.tsx` 的 `choose()` 把 `busy` 置 true,然后:

| 用户能做的动作 | 为什么没反应 | 位置 |
|---|---|---|
| 点页面其他地方 | `Dialog` 用原生 `<dialog>` + `showModal()`,backdrop 挡住整页 | `components.tsx:135` |
| 点弹窗里任何一条文件夹 | `disabled={busy}` | `LaunchOptions.tsx:154` |
| 点「浏览其他文件夹…」 | `disabled={busy}` | `LaunchOptions.tsx:161` |
| 点右上角 × | `close={() => { if (!busy) close(); }}` —— busy 时**静默无效** | `LaunchOptions.tsx:130` |
| 按 ESC | `onCancel` 先 `e.preventDefault()` 掐掉原生关闭,再调那个被 busy 挡住的 `close` | `components.tsx:143-146` |
| 点弹窗外面(backdrop) | `onClick` 走同一个被 busy 挡住的 `close` | `components.tsx:147-149` |

而且**界面上没有一个字**说明在等什么、要等多久。用户唯一能做的是等,或者杀掉浏览器标签。

### C. 前端 15 秒放弃,后端等 120 秒,中间的落差全是坑

`LaunchOptions.tsx:117-120`:

```ts
const result = await Promise.race([
  mutate<{path: string}>("/workspaces/choose", {}),
  new Promise<never>((_, reject) => setTimeout(() => reject(new Error("文件夹选择器没有打开。…")), 15000)),
]);
```

`Promise.race` 超时只是让前端这条 promise reject,**那个 fetch 没有被取消**,后端 `subprocess.run(..., timeout=120)` 还在等那个隐藏的对话框。后果:

- 用户重试 N 次 → 累积 N 个隐藏对话框 + N 个 PowerShell 进程,各等最多 2 分钟
- **如果用户后来在某个隐藏对话框里真的选了文件夹,那次选择会被直接丢掉** —— 前端 15 秒前就 reject 了,没有任何人再读那个返回值

### D. 这个能力在 Windows 上从来没被正式声明支持

`docs/mms-web/API.md:95` 原文:

> POST /workspaces 接收 {path},返回 Workspace;POST /workspaces/choose **在 macOS** 打开本机文件夹选择器,返回 {path},取消返回空 path。只由用户点击触发。

`server.py` 里的 `win32` 分支是后来加的,API 文档一直没更新。

### E. 手机 / 局域网访问时这条路径没有意义

Pilot 支持手机和局域网访问(4.22.2 刚把这条做通)。这时候点「浏览其他文件夹」,系统对话框会弹在**跑 Pilot 那台机器**上 —— 手机用户看不到、也操作不了,只能干等 15 秒锁死。同一个根因的另一个表现。

---

## 三、裁决:删掉系统对话框,换成 Pilot 内的文件夹树

**不要**加 owner window、不要只把超时对齐。把 `/workspaces/choose` 这条路径整个拿掉,「浏览其他文件夹…」改成在弹窗里展开一棵文件夹树。

四个理由:

1. **零平台分支。** 现在 `server.py:380-396` 有 `darwin` / `win32` / 其他 三条分支,各有各的毛病(macOS 的 `osascript choose folder` 有同款 owner/Z 序隐患,只是没人报)。改完之后这条路径**没有任何平台判断**,所以 macOS 上验过就等于 Windows 上也对 —— 这一点很重要,因为我们没有稳定的 Windows 真机验证渠道。
2. **不会再锁死界面。** 列一层目录是一次普通的读请求,几十毫秒,不是"用户可能离开半小时的系统窗口"。
3. **手机 / 局域网访问天然可用。** 树在浏览器里,谁打开谁看见。
4. **不再需要 subprocess。** 少一条起子进程的路径,少一处编码/超时/Z 序问题。

### 你需要先回答的问题

**删掉系统对话框之后,macOS 上有没有丢失任何用户原本做得到的事?** 逐条列出来再动手。我的判断是没有 —— 这个弹窗的主路径是**搜索**(标题就写着"输入项目名,就能找到常用的工作文件夹"),「浏览其他文件夹…」一直是兜底。兜底从"系统窗口"换成"树",而且粘贴完整路径这条路一直在。但这是你要验证的,不是照抄我的判断。

如果你发现确实丢了什么(比如 Finder 收藏夹、网络卷、某个只有原生对话框能到的位置),**停下来说明**,不要自己决定保留系统对话框。

---

## 四、需要一个新端点(现有的不够用)

我查过了,**不能直接复用 `/files/tree`**:

`mms_web/files.py:283` 的 `tree()` 第一行就是 `self.resolve(str(payload.get("workspaceId", "")), ...)`,返回的 `path` 全是 `child.relative_to(root)`,还要过 `allowed(child.relative_to(root))`。它是**某个已存在 workspace 内部**的浏览器,不能用来找一个还不是 workspace 的目录。

`mms_web/workspace_search.py` 也不够:`:76-78` 只扫 `real_home()`(注释写明 "without scanning other drives or profile internals"),`:88` 在 macOS 上用 Spotlight。它是**搜索**,不是**逐层浏览**。

所以需要一个新的只读端点,比如 `POST /workspaces/browse`。

### 它的安全边界 —— 这里我给裁决,你按这个做

Pilot 可以局域网访问,所以"列出任意目录"不能随手开。裁决:

**可以做的:**
- 只返回**目录**,不返回文件,不返回大小、mtime 或任何文件内容
- 沿用 `files.py` 已有的 `EXCLUDED` 和隐藏目录过滤(点开头的目录不列)
- 不跟随 symlink(和 `tree()` 的 `child.is_symlink()` 一致)
- 每层上限 400 项(和 `tree()` 一致)
- 和 `/workspaces/choose` 一样,列进 `_UNLOCKED_POSTS`(`server.py:374`)—— 它是只读的,不该持 mutation lock。**注意**:`RELEASE-v4.18.0.md` 记着这条教训("这些搜索之前跑在全局写锁里,一次拖拽会让发消息、停会话、确认更新一起排队几秒"),别重新踩。
- 起点必须是用户已经能到达的位置:home、已有 workspace 的路径及其父级、以及用户在输入框里自己打出来的路径。**不要**做一个"从根目录随便逛"的入口。

**不可以做的:**
- 不要返回文件列表(用户在选文件夹,给他文件只会干扰,而且扩大信息面)
- 不要在响应里带任何凭据路径、`.ssh`、`.aws` 这类目录 —— 沿用 `EXCLUDED` 就能挡掉,但要写一条测试证明挡住了
- 不要让这个端点能被用来判断某个任意路径是否存在(错误信息统一,不要区分"不存在"和"没权限")

### Windows 没有单一根 —— 这是必须解决的第一个问题

POSIX 从 `/` 往下逛就行。Windows 没有单一根:用户要从 `C:` 还是 `D:` 开始?现有代码**从来没有枚举过盘符**(`workspace_search.py:76` 的注释明确说不扫其他盘)。

所以树的最顶层需要一个"这台电脑"层级,列出可用盘符。Python 3.12+ 有 `os.listdrives()`;更低版本要用别的办法。**确认当前支持的最低 Python 版本再选实现**,别引新依赖。

顺带:`workspace_search.py:35` 的 `_looks_like_path()` 已经能识别 POSIX / 盘符 / UNC 三种形态且不碰磁盘,可以复用它做输入校验。UNC 路径(`\\server\share`)要不要支持,你定,但要在交付里说清结论和理由。

---

## 五、busy 语义必须一起修 —— 这条独立于上面

即使文件夹浏览不再阻塞,**"某个操作进行中 → 弹窗完全锁死且无出路"这个模式本身是 bug**,而且 `select()`(点一条已有文件夹)走的是同一套 `busy`,它要发 `POST /workspaces`,网络慢的时候同样会锁死。

所以三条都要:

1. **`busy` 期间必须有可见提示。** 现在是完全静默。至少要说明正在做什么。
2. **`busy` 期间 × 和 ESC 必须能关。** 关闭即放弃这次操作 —— 用 `AbortController` 取消在飞的请求,而不是让它悄悄跑完再改状态。现在 `LaunchOptions.tsx:130` 的 `if (!busy) close()` 和 `components.tsx:143` 的 `e.preventDefault()` 配合起来把 ESC 彻底吞掉,这个组合要拆掉。
3. **`components.tsx` 的 `Dialog` 是共享组件,改它要谨慎。** 全仓有多少处在用 `Dialog`?逐个确认改动不会让某个真的不该被关掉的弹窗(比如更新确认)变得可关。`dismissible={false}` 那条路径的语义不能动。如果为了安全需要把改动收在 `LaunchOptions` 里而不动 `Dialog`,那样更好 —— **优先不动共享组件**。

---

## 六、不能破坏的东西

- **搜索是主路径,不要动它。** 输入项目名 → 列出匹配 → 回车/点选。`workspace_search.py` 的行为保持原样。
- **粘贴完整路径必须仍然可用。** 这是现在错误提示里推荐的办法,也是树之外的快捷路径。
- **「最近和常用的文件夹」那一段保持。** 截图里 `v4.21.14` 那条就是它。
- **弹窗打开后光标必须仍然落在搜索框。** 这是 4.22.2 专门修过的(`RELEASE-v4.22.2.md`:原生 `<dialog>` 的 `showModal()` 会把焦点抢到右上角关闭按钮,`autoFocus` 被冲掉)。**不要回退这条。** `LaunchOptions.tsx` 那个 `autoFocus` 和相关处理要保住,并且加一条测试锁住它 —— 现在它没有测试看守,是靠 release note 记着的。
- **键盘全程可用。** 搜索 → 上下键选择 → 回车确认,这条链现在是通的(`LaunchOptions.tsx:141-150` 的 `onKeyDown`)。树也要能键盘走:上下移动、右键/回车展开、左键收起。
- **`reference` 模式。** 这个弹窗有两个用途(选工作文件夹 / 引用文件夹插入正文),`reference` prop 区分。两条路径都要验。

---

## 七、测试要求

**这批交付已经三次栽在"测试全绿而整块 UI 可以删光",所以下面的 mutation 一条都不能少。**

### 必须有真渲染测试

前端测试不许只 `readFileSync` + 正则。用 `react-dom/server` 的 `renderToStaticMarkup`(仓库已有 `react-dom`,**不要为此加新依赖**;如果发现必须加,停下来说明)。参考同目录现成的范式:`apps/mms-web/tests/bot-wait-controls.test.mjs:16-22`。

### mutation 清单(每条自己跑,记录红/绿)

1. 把文件夹树组件的渲染体改成 `return null` → 必须红
2. 把树的展开处理函数改成空函数 → 必须红
3. 把 `busy` 期间的提示文案删掉 → 必须红
4. 把 `busy` 期间允许 ESC/× 关闭的那处改回 `if (!busy) close()` → 必须红
5. 把搜索框的 `autoFocus` 处理删掉 → 必须红(这条现在没有测试,要新建)
6. 后端:把新端点的 `EXCLUDED` / 隐藏目录过滤删掉 → 必须红
7. 后端:把 `is_symlink()` 检查删掉 → 必须红
8. 后端:把新端点从 `_UNLOCKED_POSTS` 里拿掉(让它持 mutation lock)→ 要有测试红,或者说明为什么这条锁不住(如果锁不住,那 v4.18.0 那个教训就还是没人看守,要补)

### 后端测试

- 新端点:正常列目录、目录不存在、路径是文件不是目录、symlink、超过 400 项、隐藏目录被挡、`EXCLUDED` 被挡
- **Windows 路径形态**:盘符根(`C:\`)、盘符相对(`C:foo`)、UNC。用 `pathlib.PureWindowsPath` 之类的方式在 macOS 上也能测形态解析,不要求真 Windows 机器。
- 确认 `/workspaces/choose` 删掉之后没有别的调用点(grep 全仓,包括 `mms_web_static/` 之外的地方)

---

## 八、真机验证

- **macOS 上必须真机走完**:搜索 → 选一条、浏览树 → 逐层进入 → 选中、粘贴完整路径、`reference` 模式、键盘全程、`busy` 期间按 ESC 能退出。存证据。
- **Windows 上的验证**:我们没有稳定渠道。这正是选"零平台分支"方案的理由之一 —— 改完之后这条路径没有 `sys.platform` 判断,macOS 验过的逻辑在 Windows 上是同一份。但**盘符层是 Windows 独有的**,它必须:
  - 有单元测试覆盖路径形态解析(不需要真机)
  - 在交付里明确写出"这一层在真 Windows 上未经人工验证",不要含糊过去
  - 如果机主能提供一次 Windows 真机验证,优先补上
- 起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);绝不用 `pkill`,只 kill 自己启动的 PID;绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**(仓库规则,不要用 Playwright)。

---

## 九、设计

这是用户直接操作的界面,改动前读 `apps/mms-web/DESIGN.md` 和 `PRODUCT.md`,并用装好的 **impeccable** skill。

具体要求:
- 树不要做成一个嵌套卡片堆。弹窗已经有搜索框 + 结果列表,树应该和它们是同一套视觉语言。
- 不要引入渐变文字、装饰性玻璃态、层层圆角卡片(仓库明令禁止的那几样)。
- `bot.css` / `studio.css` 那套裸 hex 的约束同样适用于你新增的样式:**用既有 token,不要写新的裸 hex**。改完统计一下你碰的那个 css 文件的裸 hex 数,和改动前对比,交付里写明。
- 窄屏(390×844)必须可用 —— 手机访问是这个功能的现实场景之一。

---

## 十、门禁

- `npx tsc --noEmit -p apps/mms-web`
- `node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**,否则 `markdown-reading.test.mjs` 会因为缺 `unified` 失败;worktree 里先 `npm install`)
- `npm run build --workspace @mms/web`
- 定向 pytest:`tests/test_mms_web_files.py`、`tests/test_mms_web_workspaces.py`(如果存在)、以及所有碰到 `server.py` 的测试文件。写 base/head 绝对数。
- `python3 scripts/ci_pytest_regression.py --base origin/main`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。**这个 gate 对并发敏感**:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败;串行跑一次,红了单独复跑确认并如实写明。
- **不要重建 `mms_web_static/`。** dev 和 main 上改 `apps/mms-web/src` 的 commit 历来不带 bundle,只有 release commit 带。带上会和别的 PR 撞,而且会把静态包变成半发布状态。

---

## 十一、文档

- `docs/mms-web/API.md:95` 那句"在 macOS 打开本机文件夹选择器"要改成新行为的准确描述。
- 如果 `docs/mms-web/FEATURES.md` 或 `DESIGN.md` 提到过文件夹选择器,一起改。
- 交付里写清:改动边界、哪些主功能没动、实际做了什么验证、哪些没做、残余风险。

---

## 十二、边界

- **不要**动 `mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs` —— 这些是保护文件。
- **不要**动 `workspace_search.py` 的搜索行为。它是这个弹窗的主路径,现在是好的。
- **不要**顺手重构 `files.py` 的 `resolve()` / `allowed()` / `tree()`。新端点可以复用它们的过滤常量,但不要改它们的语义 —— `/files/tree` 是另一条在用的路径。
- **优先不动 `components.tsx` 的 `Dialog`**。如果必须动,先说明影响面(全仓有多少处在用)再改,且 `dismissible={false}` 的语义不能变。
- base 是 `main`。推到一个新分支,提 PR,base 填 `main`。**不要** merge。
