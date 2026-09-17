# T8b — 工作身份:模型 + 通道 + 思考强度的命名组合

**base**:`dev`,**在 #303 和 #304 都落地之后**。理由见第四节(冲突面)。

**这个包重开 #290**(`feat/pilot-work-identities`,2026-09-16 关闭未合),但**缩了范围**。裁决在第三节 —— 先读它,再看要不要复用旧分支的代码。

---

## 一、#290 当时做了什么

分支还在:`origin/feat/pilot-work-identities`,+402/-14,10 个文件。它 base 挂的是 `codex/stride-2718d9d92afa45ef`(#288 的分支,已合进 dev),所以现在已经落后很多。

它做的是把模型切换收成可命名的**工作身份** = 模型 + 通道 + 思考强度 + **一句人设**:

- 输入框模型菜单顶部列出身份;高级选项可「保存当前为工作身份」
- 点身份真正切 `presetId` 和 `thinkingLevel`
- **新会话若有人设,第一句带可见头 `（工作身份：写代码）`**
- 当前会话只切模型和强度,人设不加进历史
- 设置 → 本机 可删除身份
- 存 `localStorage`,不写 `~/.config/mms*`,不改 Bot runtime

文件:`App.tsx` +76、`QuickModelMenu.tsx` +112、`SettingsPage.tsx` +36、`TaskSettings.tsx` +40、`SessionStatus.tsx` +4、`quick-model.css` +5、`studio.css` +4、新 `work-identities.ts` +87、两个测试 +52。

---

## 二、地形变了

#290 关掉之后,`dev` 上落了两个改同一片区域的 PR:

- **#304**(`feat/composer-effort-picker`):把思考强度从模型弹窗里拆出来,在底栏模型选择器右边做成**独立常驻的 `EffortPicker`**,并**移除了 `QuickModelMenu` 里旧的嵌套二级下拉**。
- **#303**(`codex/stride-0dd410added040cc`):侧栏区分未读已完成 / 已读待命,动了 `App.tsx` +78、`SessionStatus.tsx` +41。

所以 #290 当初的一个前提没了:effort 不再藏在模型弹窗深处。它现在是底栏一个 2 次点击可达的控件。

**这不构成放弃身份的理由 —— 反而让它的价值更清楚。** 现在底栏有两个独立控件(模型选择器、effort 选择器),要凑一个特定组合得分别设两次。把组合命名存下来一键调用,收益是可见的,就像宏对单键。

但它引入一个新的正确性要求:**身份切换和 `EffortPicker` 写的是同一个状态,两个入口必须一致。** 切完身份,底栏那个 effort 控件必须立刻显示新值,不能一个说"深入"一个说"均衡"。

---

## 三、裁决:重开,但把人设砍掉

**做**:模型 + 通道 + 思考强度 的命名组合。保存、列出、一键切换、删除。

**不做**:人设。

砍人设的理由:

`（工作身份：写代码）`这个实现是把设定塞进**用户消息的第一句**。那不是设定,那是在用户的话里凭空加一段他没说的文字 —— 之后这句会一直留在对话历史里,被模型当成用户说的,也会被导出、被 fork 带走。真正的做法是会话级的 system 设定,那是另一个量级的改动(要碰后端的会话创建、要决定它算不算历史、要考虑 Bot 那边已有的 `systemPrompt` 怎么共存)。

而且 #290 自己的设计里已经有一处别扭:"新会话带人设,切到当前会话不带"。这个区分本身讲得通(不该改写已有会话的设定),但它暴露了人设和"模型+通道+effort"不是一类东西 —— 后三个是**路由参数**,随时可切;人设是**会话设定**,只在开头有意义。混在一个"身份"里,必然要为它开特例。

按"功能要么做完要么不做":用 hack 实现的人设不算做完。**模型+通道+effort 的命名组合本身已经是完整有用的功能,不依赖人设就成立。** 人设等到有真正的会话级设定机制时再单独立包。

如果你在实现中发现砍掉人设之后这个功能"不值得做了",**停下来说明理由**,不要自己把人设加回去。

---

## 四、冲突面(我已核实)

`#290` 和 `#303` / `#304` 的文件重叠:

| 文件 | #290 | 谁还在动 |
|---|---|---|
| `TaskSettings.tsx` | +40 | **#304** +241/-134 |
| `studio.css` | +4 | **#304** +112/-2 |
| `QuickModelMenu.tsx` | +112 | **#304** 在删这里的嵌套下拉 |
| `App.tsx` | +76 | **#303** +78/-19 |
| `SessionStatus.tsx` | +4 | **#303** +41/-12 |

五个文件全部撞。所以:

1. **必须等 #303 和 #304 都进 dev 之后再开工。** 现在 rebase 是在流沙上盖房子。
2. **旧分支的代码大概率不能直接 rebase。** `QuickModelMenu.tsx` 那 +112 是往那个菜单顶部加身份列表,而 #304 正在重构同一个菜单。先读 #304 落地后的 `QuickModelMenu.tsx` 和 `TaskSettings.tsx`,再决定是 rebase 还是照着旧分支重写。**重写不丢人**,旧分支的价值主要在 `work-identities.ts`(+87,纯逻辑,大概率还能用)和它的测试。

**砍掉人设之后有个好消息要你验证**:`App.tsx +76` 里很可能大部分是人设注入的逻辑。如果去掉人设后 `App.tsx` 根本不需要改,那和 #303 的冲突就消失了。**先确认这一点**,它决定这个包的实际规模。

---

## 五、要做的事

### 存储

- 沿用 `localStorage`,**不写** `~/.config/mms*`。这条是对的,保持。
- 键名沿用 #290 的(读一下 `work-identities.ts`),这样老用户存过的身份不会丢。如果必须改结构,要能读旧格式。
- 身份数量要有上限(参考仓库里别处的做法,比如 skills 的 20 个上限),并且超限时给可见提示,不要静默丢。
- 名字要有长度上限和去重规则。同名怎么办 —— 覆盖还是拒绝,你定,但要一致且可见。

### 保存

- 「保存当前为工作身份」:抓当前的 `presetId` + `channel` + `effort`,让用户命名。
- **保存时不可用的组合要挡住。** 比如当前模型不支持某个 effort 挡位。参照 `facts?.supportedThinkingLevels`(#304 用的就是这个)。
- 存的是什么要想清楚:存 `presetId` 就同时锁定了模型和通道。如果用户后来删了那个通道,这个身份就失效了 —— **失效的身份必须可见地标出来并且可删,不能静默不工作,也不能静默回退到别的通道**。这条是硬要求,仓库的 guardrails 反例第一条就是"界面里选中了某个模型,实际启动用了另一个"。

### 切换

- 点身份 → 切 `presetId` + `effort`。
- **底栏的 `EffortPicker`(#304 做的那个)必须立刻反映新值。** 两个入口写同一个状态,这是本包最容易出的 bug。
- **运行中的任务(running / waiting)不能被身份切换干扰。** #304 已经在运行态禁用了 EffortPicker,身份切换要遵守同一个约束 —— 要么一起禁用,要么明确只影响下一轮。你定,但要和 #304 的行为一致,不要两个控件两套规则。
- 当前模型不支持某个身份里的 effort 挡位时,要可见地说明,不要静默降级。

### 列出与删除

- 模型菜单顶部列身份(#290 的位置)。如果 #304 落地后那个菜单形状变了,位置可以调整,但要在交付里说明为什么。
- 设置 → 本机 可删除(#290 的位置,保持)。

### 不要做

- 不要人设(见第三节)。
- 不要写 `~/.config/mms*` 或任何真实全局配置。
- 不要动 Bot runtime。
- 不要动 `mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms_bridge.py` / `mms_account_state.py` / `mms_session.py` / `mms_adapter_registry.py` / `mms` / `ccs`(保护文件)。
- 不要重建 `mms_web_static/`。dev 上改 `apps/mms-web/src` 的 commit 历来不带 bundle,只有 release commit 带。
- 不要新增第二份"哪些模型支持哪些 effort 挡位"的数据。仓库有硬规则(Vision / Context Window 的单一真值链),同理适用:能力判定只走 `facts`,不许在代码里再建一张表。

---

## 六、测试

**这批交付已经三次栽在"测试全绿而整块 UI 可以删光",所以下面的 mutation 一条都不能少。**

前端测试不许只 `readFileSync` + 正则。用 `react-dom/server` 的 `renderToStaticMarkup`(仓库已有 `react-dom`,**不要为此加新依赖**)。现成范式:`apps/mms-web/tests/bot-wait-controls.test.mjs:16-22`,以及 #302 返工新加的 `apps/mms-web/tests/bot-schedule-panel-render.test.mjs`(190 行,真渲染)。

### mutation 清单(每条自己跑,记录红/绿)

1. 把身份列表的渲染改成 `return null` → 必须红
2. 把切换身份的处理函数改成空函数 → 必须红
3. 把"切身份后同步 `EffortPicker` 显示值"那一步删掉 → **必须红**(这是本包最容易回归的地方)
4. 把"失效身份的可见标记"删掉 → 必须红
5. 把身份数量上限去掉 → 必须红
6. 把保存时的 effort 可用性校验删掉 → 必须红

### 其他

- `work-identities.ts` 的纯逻辑(存、读、去重、上限、失效判定)要有单测。
- 旧格式兼容要有一条测试:塞一份 #290 时代的 `localStorage` 数据,能正常读出来。
- `localStorage` 不可用时(隐私模式、被禁)不能白屏或报错 —— 要有一条测试。

---

## 七、真机验证

必须走完,存证据:

1. 设一个特定的模型+通道+effort 组合 → 保存为身份 → 刷新页面 → 身份还在 → 点它 → **底栏的模型选择器和 effort 选择器同时显示正确值**
2. 存两个不同身份,来回切
3. 删除身份
4. 造一个失效身份(存完之后把那个通道从配置里去掉,或者用一个不存在的 presetId 手写进 `localStorage`)→ 界面可见地标出它失效 → 能删掉 → **点它不会静默切到别的模型**
5. 任务运行中点身份 → 行为和 #304 的 EffortPicker 在运行态的行为一致
6. 窄屏 390×844 下身份列表可用

起验证实例:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);绝不用 `pkill`,只 kill 自己启动的 PID;绝不写真实 `~/.config/mms*`。真实页面交互用 **ego-browser**(仓库规则,不要用 Playwright)。

---

## 八、设计

用户直接操作的界面,改动前读 `apps/mms-web/DESIGN.md` 和 `PRODUCT.md`,并用装好的 **impeccable** skill。

- 身份在菜单里是一行一行的选项,不要做成卡片网格。
- 不要渐变文字、装饰性玻璃态、层层圆角卡片(仓库明令禁止)。
- **不要写新的裸 hex**,用既有 token。改完统计你碰的那些 css 文件的裸 hex 数并和改动前对比,交付里写明。
- 失效身份的视觉要克制:它是"这条现在用不了",不是报错。

---

## 九、门禁

- `npx tsc --noEmit -p apps/mms-web`
- `node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**,否则 `markdown-reading.test.mjs` 会因为缺 `unified` 失败;worktree 里先 `npm install`)
- `npm run build --workspace @mms/web`
- 定向 pytest:这个包理论上不碰后端,如果确实一行 Python 都没改,在交付里说明,并跑一次相关的 web 测试确认没牵连
- `python3 scripts/ci_pytest_regression.py --base origin/dev`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。**这个 gate 对并发敏感**:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败;串行跑一次,红了单独复跑确认并如实写明。

---

## 十、交付

- 新分支,提 PR,base 填 `dev`。**不要** merge。
- 旧分支 `feat/pilot-work-identities` 先留着不要删,等新 PR 合了我来清。
- 交付里写清:改动边界、哪些主功能没动、实际做了什么验证、哪些没做、残余风险。
- 行号复核:如果你在交付里引用了行号,自己复核一遍再写(这一批有过行号整体偏移 11 行的交付)。
- **第四节那个问题要在交付里明确回答**:砍掉人设之后 `App.tsx` 还需要改吗?
