# #304 返工 01 — 思考强度独立选择器

**基线**:`origin/feat/composer-effort-picker`,base `dev`。**注意 dev 已经前进到 v5.0.4**(T5 栈已合),开工前先 rebase。

**先说结论**:交互目标达到了,而且**测试质量是这批交付里最好的一份**。改 effort 从 3 次点击(模型弹窗 → 高级选项 → 下拉)降到 1 次(底栏常驻按钮),验收方在真机上量过。四条 mutation(渲染体 `return null` / 删掉常驻挂载 / 去掉运行态禁用 / `sortLevels` 不排序)**全部被抓**。`composer-effort-picker.test.mjs` 是真渲染(esbuild + `vm` 加载真实 `TaskSettings.tsx` 和 `Popover.tsx`,`renderToStaticMarkup` 断言产出的 HTML),还有一条反向断言确认旧控件已移除。这个做法请保持。

**先纠正我上一轮的一个错判**:我说过"你重建了 `mms_web_static/`,这条要撤"。**那是错的,你重建 bundle 是对的。** 验收方遍历 `git log origin/dev -30 -- apps/mms-web/src`,`6d9001d6`、`88114765`、`f8c21cb2`、`5be8649a`、`a035c667` 五个非 release 的 fix/feat commit 全部同时重建了 bundle;我自己复核确认无误。仓库的实际约定是"任何 src 改动都在同一 commit 重建 bundle",所以这一项 #303 才是漏的,你是合规的。

但 bundle 有另一个真问题,见必改 1。

---

## 必改 1 · bundle 无法用仓库 lockfile 复现,而且夹带了一个未申报的依赖升级(P0)

验收方在干净 worktree 里 `npm ci --workspaces=false --ignore-scripts`(严格按 `apps/mms-web/package-lock.json`)再跑 `python3 scripts/build_mms_web_release.py --skip-install`:

- **CSS 逐字节一致**(`index-COfD3LmK.css`,sha256 `01df4e7e…` 完全相同)→ 说明工具链环境是可比的
- **JS 不一致**:你提交的 `index-CSkv64VK.js`(750169 B)vs 复现出的 `index-D4zMDnPF.js`(750141 B)
- 首个分歧在 byte 364319,是 vendor 代码:你的有 `this.map=[],this.index=new Map`,复现出的只有 `this.map=[]`

定位到这是 `micromark-extension-gfm-table/lib/edit-map.js` 的 `EditMap` 类。`this.index` 这个字段是 **2.1.2** 才引入的(上游注释写着 "so `add` does not scan `map` (quadratic on table-heavy documents)"),而 **lockfile 钉的是 2.1.1**,2.1.1 里没有这个字段。

也就是说:**你交付的用户产物里含有一个未申报、未写入 lockfile 的第三方依赖升级。** 功能上无害(是上游的性能修复),但它违反 `AGENT.md` 的「Before … adding dependencies, explicitly tell the user first」,而且 `validate_bundle` 只自校验 manifest,永远发现不了这件事。

**期望**:二选一。
- **不带** `--skip-install`(或者先 `npm ci`)重建,产出与 lockfile 一致的 bundle;或者
- 在本 PR 里**显式提交 lockfile 升到 2.1.2**,并说明为什么要升

**验证**:干净目录 `npm ci --workspaces=false --ignore-scripts` 后跑 `scripts/build_mms_web_release.py --skip-install`,产出的 `build.json.files` 必须与你提交的逐项 sha256 相同(这次是 CSS 相同、JS 不同)。

---

## 必改 2 · 补一条门禁,否则"bundle 和源码不一致"永远没人发现

这条是验收方在查必改 1 时挖出来的,严格说不是你引入的问题,但你正在动 bundle,顺手把它堵上。

`build.json` 带一个 `sourceSha256`(对 `src/**` + package.json + lockfile + index.html + vite.config.ts + tsconfig.json 的指纹)。验收方按 `scripts/build_mms_web_release.py` 的算法逐分支重算:

| 分支 | `build.json` 的 `sourceSha256` | 实际 src 指纹 | 一致? |
|---|---|---|---|
| 当时的 `origin/dev` | `36ec8136…` | `072b314c…` | **否** |
| #303 | `36ec8136…` | `8ae992ec…` | **否** |
| #304 | `87747bb0…` | `87747bb0…` | 是 |
| #303+#304 合并 | `87747bb0…` | `a56e5279…` | **否** |

而 `tests/test_mms_release_version.py` 在**以上全部情况下都 pass**。看 `mms_web/update_stage.py:64` 的 `validate_bundle`:它只校验 `version` 相符 + 每个文件的 sha256 自洽,**从不拿 `sourceSha256` 去比对真实 src**。

所以"bundle 在谎报自己的来源"这个状态零门禁。

**期望**:在 `tests/test_mms_release_version.py` 里补一条 —— 按 `scripts/build_mms_web_release.py` 的同一算法重算 `sourceSha256`,和 `build.json` 里的比对。

**验证**:这条测试在一个 bundle 过期的分支上必须**红**,重建之后转绿。(我在发 v5.0.3 / v5.0.4 时重建过 bundle,所以你 rebase 到最新 dev 之后基线是干净的 —— 要构造红的情况,改一行 src 不重建即可。)

---

## 必改 3 · 用户丢了一件原来能做的事:把 effort 退回「MMS 默认」

dev 上的 `EffortSelect` 第一项是:

```tsx
<option value="">MMS 默认 · {facts.defaultThinkingLevel}</option>
```

`App.tsx:851` 的 `effort = readRoutePreferences()[presetId]?.effort || ""` —— 空串就是"跟随 MMS 默认"。验收方在 dev 实例上确认该选项确实存在。

你的 `EffortPicker` 只列具体档位,`change` 一律 `saveRoutePreference(value, {effort: level})` 写死一个具体值,**菜单里没有任何清除项**。所以用户选过一次之后再也回不到"跟随默认",而且换模型时不再继承新模型的默认 effort。

**期望**:菜单首项补一个「MMS 默认 · {defaultLevel}」,点选时写 `effort: ""`,对齐 dev `EffortSelect` 的 `<option value="">`。

**验证**:选一个具体档位后再选「MMS 默认」,`localStorage["mms-web-route-preferences"][presetId].effort` 应为 `""`,触发按钮回到跟随默认的显示。

---

## 必改 4 · 存了一个通道不支持的档位时,界面说谎而且照样下发(P0)

验收方在两个实例上写入同一条 `mms-web-route-preferences: {"…MiniMax-M2.7": {"effort": "max"}}`(该模型只支持 off/minimal/low/medium/high),然后刷新:

| | dev / #303 | #304 |
|---|---|---|
| 控件显示 | select 选中 `此通道不支持 max,请重选`(该 option `disabled`) | 触发按钮显示 `思考 · 最高` |
| 档位列表 | `MMS 默认 · high` / `此通道不支持 max,请重选` / off / minimal / low / medium / high | off / minimal / low / medium / high(**没有 max**) |
| 高亮项 | 选中不支持项并明确报错 | **`anyActive: []`,一项都没高亮** |
| 警告文案 | 有 | **无**(全页 grep `不支持|请重选` = null) |

而 `App.tsx:1812` 仍然把它下发:`thinkingLevel: effort || undefined`。

**按钮说「最高」,菜单里没有「最高」,一项都不高亮,零提示,而这个值照样发给了 launcher。** 这正是 `docs/AGENT_GUARDRAILS.md` 反例第一条点名要避免的形态 —— "界面里选中了某个模型,但 launcher 最终启动时使用了另一个"。

根因在 `TaskSettings.tsx` 的 `currentEffort = value || defaultLevel || levels[0] || "medium"` —— 它不检查 `value` 是否在 `levels` 里。

**期望**:`value` 不在 `levels` 里时,按钮或菜单必须给出等价于「此通道不支持 X,请重选」的提示,并且**不得让这个值被当作有效选中态下发**。

**验证**:写入 `{"<presetId>":{"effort":"max"}}`(模型不支持 max)后刷新,页面必须出现不支持提示,菜单里必须有明确的"当前值无效"标识。

---

## 必改 5 · 编造的能力兜底名单

`TaskSettings.tsx` 的 `SessionSettings` 里:

```ts
const hasEffort = Boolean(r && (rawLevels.length > 0 || r.model?.reasoning));
const sortedLevels = sortLevels(rawLevels.length > 0 ? rawLevels : ["low", "medium", "high"]);
```

改之前这里**没有**兜底 —— 旧代码是 `<option value="" disabled>尚未读取</option>` 加真实档位。现在只要 runtime 没报 `supportedThinkingLevels` 而 `model.reasoning` 为真,就**凭空给出 low/medium/high 并允许点选下发**。

而且 `SessionTools.tsx:225` 早就有一份**不同的**兜底 `["off","minimal","low","medium","high"]`,所以现在同一语义有两份互相矛盾的硬编码。

仓库有硬规则("Vision Capability Single Truth"、"Context Window Single Truth"),核心是同一个能力不许有第二份代码内名单。这条兜底是同一类违规。

**期望**:删掉这个兜底,回到"没有真实档位就显示未读取 / 不可调"。如果你认为确实需要兜底,**必须和 `SessionTools.tsx:225` 那份合并成单一来源**,并说明理由。

**验证**:构造 `runtime.supportedThinkingLevels = []` 且 `model.reasoning = true`,UI 不得列出任何未被声明支持的档位。

**顺带**:`LEVEL_ORDER = ["off","minimal","low","medium","high","xhigh","max"]` 这 7 个 key 和顺序与 `ModelExplorer.tsx:34` 的 `effortLabels` 完全重复。它不含模型名,不算上面那类违规,但改成 `Object.keys(effortLabels)` 更好。低优先。

---

## 必改 6 · 不支持 thinking 的模型下,新手引导第 4 步必然误导

验收方装了个 shim 把 `/launch-options` 的 `supportedThinkingLevels` 置空、`model.reasoning` 置 false,清掉 `mms-web-tour-seen-v1`,走了一遍新手引导到第 4 步:

- `[data-guide="effort"]` 锚点数 **0** —— 自动隐藏生效,符合预期
- 第 4/7 步正常显示、可继续,**不卡不报错**(`visibleTarget()` 全找不到就返回 `null`,卡片居中)
- 但文案是「**模型右侧的「思考强度」就是 effort**」,而页面上根本没有这个控件
- **更糟**:你加的兜底逻辑触发了 `document.querySelector('.task-settings-trigger')?.click()`,**弹出了模型搜索列表** —— 而 #304 刚把 effort 行从那个弹窗里删掉了。于是引导打开一个与 effort 完全无关的模型选择器,高亮圈也没有(`ringBox: null`),同时告诉用户去看一个不存在的东西

改之前这一步至少是自洽的(弹窗里确实有「思考强度」行)。

**期望**:`hasEffort` 为假时把 `effort` 从 `steps` 里过滤掉。`GuidedTour.tsx:44` 已经有现成范式(`modelReady ? tourSteps.filter(s => s !== "connection")`),照它做。至少要去掉那个"打开模型弹窗"的兜底 click。

**验证**:用不支持 thinking 的模型走引导,第 4 步应被跳过。不得出现"模型搜索列表弹开 + 文案说『模型右侧的思考强度』"这个组合。

---

## 必改 7 · PR 描述里「0 警告」不实

`npm run build --workspace @mms/web` 稳定输出 `(!) Some chunks are larger than 500 kB after minification`(`index-*.js` 799 kB)。dev、#304、合并态都有这条 —— 是既有状况,不是你引入的,但描述里写「0 警告 0 错误」不准确。

**期望**:改成「0 错误,1 个既有的 chunk-size 警告」。

---

## 已经验过、不用动的

这几项验收方实测通过,保持现状:

- **`Popover.tsx` +13/-3 完全向后兼容。** 三个新增可选 prop:`panelWidth?` → 不传仍是 340;`disabled = false` → false 时与原状一致;`dataGuide?` 不传时 React 省略该属性。8 个使用方里只有 `EffortPicker` 传了新 prop,其余 7 处行为不变,真机也验了会话筛选弹窗和模型弹窗正常。唯一小瑕疵:`aria-expanded={open}` 仍留在 `disabled` 的按钮上,无害。
- **`studio.css` +112 没有增加裸 hex。** dev 48 个 → #304 48 个,diff 的 `+` 行里 `#xxxxxx` 计数为 **0**,全部走 `var(--accent/--ink/--muted/--soft/--line)`。
- **窄屏 390×844 收起形态对。** `.task-effort-prefix` 的 `display` 计算值为 `none`(媒体查询生效),按钮只剩 `深入` + 图标(62px),无横向溢出(`documentElement.scrollWidth <= innerWidth`)。
- **能力判定的真值链没问题。** `facts` 走既有的 `POST /launch-options`,`SessionSettings` 用既有的 `detail.runtime.supportedThinkingLevels`,没有新开数据源,也没有新增硬编码模型名单(必改 5 那个是档位兜底,不是模型名单)。
- **其他 effort 入口都没丢。** `SessionTools.tsx` 的 RuntimePanel thinking select、`/thinking <level>` 斜杠命令、ConnectionDialog 建通道时的每通道 effort —— 三条原样未动,验收方确认这三个文件在本 PR 的 diff 里是空的。

**一处未申报的行为变更**,方向像修复但描述里没提:`SessionSettings` 的 `locked` 多了 `|| !detail.session.capabilities.send`,这同时改变了同弹窗内「工作方式」select 的禁用状态。在交付里说明一句。

---

## 交付要求

1. 七条必改都做完(必改 7 只是改 PR 描述)
2. 每条的 mutation 结果写明。**你原有的四条 mutation 要重跑确认仍是红**,新增的必改 3/4/5/6 各自也要有一条能证明它被锁住的 mutation
3. 门禁写实测绝对数:`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**,worktree 里先 `npm install`)、`npm run build --workspace @mms/web`、`python3 scripts/ci_pytest_regression.py --base origin/dev`。参考基线:dev 是 **130 pass**,你这个分支是 **137 pass**(+7,和你说的"7 项新测试"吻合)
4. `python3 scripts/regression_fresh_user_gate.py`(完整)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。这个 gate 对并发敏感,串行跑一次,红了单独复跑确认并如实写明
5. 必改 3、4、6 改了用户可见行为,真机各验一次并存证据
6. rebase 到最新 `dev`(v5.0.4 之后),base 保持 `dev`,**不要** merge
7. **rebase 之后必须重建 bundle**(按必改 1 的正确方式),因为 dev 已经前进

起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);**只 kill 自己启动的 PID** —— 不要用端口号批量 grep 后 kill,61xxx 段上可能有别的会话的实例(上一轮验收方就误杀了两个不属于它的进程);绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**(仓库规则,不要用 Playwright)。
