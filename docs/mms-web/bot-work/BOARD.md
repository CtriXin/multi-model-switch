# 任务看板

**更新于 2026-09-17,`main` = v4.22.4,`dev` = v5.0.4。** 这份是派发依据:每条给包路径、当前状态、依赖、以及能不能现在派。

规则:**一个包一个执行方,一个迭代点一个版本。** 包里写明 base 分支,不要改。agent 不自行 merge —— 合并和发版由 Fable 做。

---

## 一、可以现在派(无依赖)

| 包 | 路径 | 规模 | 状态 |
|---|---|---|---|
| **T8a · 选项目文件夹不再依赖系统对话框** | `docs/mms-web/bot-work/T8a-folder-picker-without-a-system-dialog.md` | 大 | **已派** |
| **T8c · 把 pytest 基线洗干净** | `docs/mms-web/bot-work/T8c-clean-the-pytest-baseline.md` | 中,第一阶段纯只读 | **可派** |
| **#303 返工** | `docs/mms-web/bot-work/PR303-rework-01.md` | 中 | **可派** |
| **#304 返工** | `docs/mms-web/bot-work/PR304-rework-01.md` | 中 | **可派** |

**T8a** base 是 `main`。机主在 Windows 上实测:点「浏览其他文件夹…」什么都不弹,然后十几秒里整个界面点不了也关不掉。四层根因(对话框弹在浏览器后面、五条退出路径全堵、前端 15 秒放弃而后端等 120 秒、手机访问时对话框弹在主机上)。裁决是**删掉系统对话框换成 Pilot 内的文件夹树**,不是加 owner window 止血 —— 这样这条路径不再有任何 `sys.platform` 分支,macOS 上验过就等于 Windows 上也对。

**T8c** base 是 `main`。`main` 上有 63 个测试在任何分支上都红(实测:63 failed / 2427 passed / 36 skipped),它们**永远不参与 CI 回归门**,因为 `ci_pytest_regression.py` 只对"base 通过而 head 失败"的报错。其中 37 个集中在 `test_opencode_launcher.py`、7 个在 `test_pi_committee.py`,所以大概是 5-8 个根因不是 63 个问题。**第一阶段只产出一份分类表,不许改代码。**

---

## 二、两个交互 PR:都需返工,包已写

两个 PR 文件零重叠,两种合并顺序都无冲突,合后 `node --test` 140/140、`tsc` 0 错。但各自都有必须先修的东西。

### #303 · 侧栏区分未读已完成和已读待命 → `PR303-rework-01.md`

核心机制是对的 —— 验收方在真实实例上确认了滚动位置决定已读这条链能工作。但:

- **头号证据截图 `after-states.png` 是伪造的(P0)。** 图标像素级比对显示行 1 是「CircleHelp + 执行工具」、行 2 是「Pause + 已完成」,而代码映射是 `tool → Wrench`、`completed → Check` —— **代码里不存在任何 phase 能渲染出那两个组合**。两图对应图标的 ink 像素数完全相同,是同一图形改色换文案。另一条佐证:图里三个会话标题逐字来自 `preview.ts` 的样例数据,而那三条的 state 正好渲染成另一张真图。**这是这批 PR 第二次伪造截图**(#277 有过)。
- **两份文档写的和实测相反。** DESIGN.md 和 FEATURES.md 都写「打开会话本身不算已读」,实测是**点开 0.5 秒内就转已读**(`openSession` 置 `followOutput.current = true` 后自动滚到底)。后半句「停在窗口中间不算已读」是真的。
- **已读写入点和 `states.css` 的视觉区分都没有测试守卫** —— 注释掉 `receipts.current[id] = token` 或删掉那 9 行 CSS,133/133 全绿。
- **关掉标签页期间跑完的轮次,回来一律是「待命」**(`baseline` 分支静默吞掉),文档没写。这直接限制了这个功能想解决的问题。
- **bundle 没重建** —— 见下面那条纠正。

### #304 · 思考强度拆成独立常驻选择器 → `PR304-rework-01.md`

**测试质量是这批交付里最好的一份**(真渲染 + 4 条 mutation 全被抓),交互收益是真的(3 次点击 → 1 次,真机量过)。但:

- **bundle 无法用仓库 lockfile 复现,而且夹带了一个未申报的依赖升级(P0)。** 严格按 lockfile 重建:CSS 逐字节一致,JS 不一致 —— 提交的产物里含 `micromark-extension-gfm-table@2.1.2` 的 `this.index = new Map`,而 lockfile 钉的是 2.1.1。违反 AGENT.md「加依赖前先告诉用户」。
- **用户丢了两件原来能做的事**:把 effort 退回「MMS 默认」(旧 select 有 `<option value="">`,新菜单没有清除项);以及存了一个通道不支持的档位时得到「此通道不支持 X,请重选」的警告 —— 现在退化成**按钮显示「最高」、菜单里没有最高、一项都不高亮、零提示,而这个值照样下发给 launcher**。后者正是 `AGENT_GUARDRAILS.md` 反例第一条的形态。
- **编造的能力兜底名单**:`rawLevels.length > 0 ? rawLevels : ["low","medium","high"]` 凭空给出档位,而 `SessionTools.tsx:225` 已有一份不同的兜底,同一语义现在有两份矛盾的硬编码。
- **不支持 thinking 的模型下新手引导第 4 步必然误导**:锚点不存在时兜底 click 打开了模型弹窗(而 #304 刚把 effort 从那里删掉),文案说「模型右侧的思考强度」,页面上没有那个控件。
- PR 描述里「0 警告」不实(vite 稳定输出 chunk-size 警告)。

---

## 三、一条我判错了的规则,已纠正

我之前说"dev 上改 `apps/mms-web/src` 的 commit 历来不带 bundle,只有 release commit 带",因此判定 #304 重建 bundle 是违规、要撤。

**那是错的。** 遍历 `git log origin/dev -30 -- apps/mms-web/src`,`6d9001d6`、`88114765`、`f8c21cb2`、`5be8649a`、`a035c667` 五个非 release 的 fix/feat commit 全部同时重建了 bundle(3-5 个文件),我逐个复核确认。

**仓库的实际约定是:任何 `apps/mms-web/src` 的改动都应该在同一个 commit 里重建 bundle。** 所以 **#304 是合规的,#303 才是漏的**。两个包都已按纠正后的规则写。

顺带查出一个真缺口:`tests/test_mms_release_version.py` 只校验 `build.json` 的 version 相符 + 每个文件 sha256 自洽,**从不拿 `sourceSha256` 去比对真实 src**,所以"bundle 在谎报自己的来源"这个状态零门禁。已并入 #304 的返工(必改 2)。

---

## 四、准备进行(有依赖,现在派会白做)

| 包 | 路径 | 卡在什么上 |
|---|---|---|
| **T5d · 让「计划步骤指定模型」真的生效** | `docs/mms-web/bot-work/T5d-planned-step-model-actually-applies.md` | **已解锁**(T5 栈已进 dev),可派 |
| **T8b · 工作身份:模型 + 通道 + 思考强度** | `docs/mms-web/bot-work/T8b-work-identities-model-channel-effort.md` | #303 和 #304 都落地 |
| **#295 · 同一 Bot 上多方听意见** | PR 已开,需 rebase 到 v5.0.4 | **已解锁**,可派 |

**T5d 是 P1,而且是一个已经上线的能力在静默失效。** `task["presetIdOverride"]`(计划里给某一步指定模型)对任何跑过一次任务的 Bot 都被忽略,没有任何报错 —— `_launch` 只换 `bot["presetId"]` 不重置 `sessionId`,而 `PiBotExecutor.start()` 只在新建 session 时才用算好的 preset。实测 `requested: pi:alpha / EFFECTIVE: pi:beta / reusedSession: true`。这正是 `AGENT_GUARDRAILS.md` 反例第一条点名要避免的形态。

它现在被 T5c 留下的一条 characterization test 明确标注(`test_preset_override_is_chosen_but_a_reused_session_still_runs_the_old_model`),修好时那条会变红 —— **执行方必须把它转正,而不是当成回归**。裁决写在包里:override 的子任务跑在自己的一次性会话里,不占 `bot["sessionId"]`,**不要照抄 pending 的解法**。

**T8b 砍掉了人设。** #290 原本的实现是把 `（工作身份：写代码）`塞进用户消息第一句 —— 那些字会一直留在对话历史里、被导出、被 fork 带走。"模型+通道+effort 的命名组合"本身已经完整有用。它和 #303 / #304 五个文件全撞(`App.tsx`、`SessionStatus.tsx`、`TaskSettings.tsx`、`studio.css`、`QuickModelMenu.tsx`),所以必须等那两个落地。

**#295 要 rebase,而且要把两份 family 列表合成一份**(`bot-fleet.ts` 的 `FAMILY_PREFIXES` 和 `mms_config_web.py` 的 `_FALLBACK_MODEL_FAMILIES`)。

---

## 五、记着但还没立包的小项

都不阻塞发布。按值排序:

1. **`pending-messages` 同一条消息的状态渲染两次。** 用户可见的重复。
2. **`BotStudio.loadSchedules` 是 N+1 轮询** —— 3 秒一次对每个 Bot 各发一个请求,而且 `await` 完才排下一次;`useCallback(..., [])` 的依赖漏了 `isPreview`(当前不炸,因为它挂载后不变)。
3. **「本轮执行被中断,未产生回复」对用户主动点停止偏重了。** 要分开说需要后端给事件加一个标记。这是机主的决策项,不是 bug。
4. **#281 的 anti-mutation 该提到 hook 集成层** —— 注释掉 `saveBtwSeen(choices)` 仍然 81/81 全绿。
5. **#286 的 `btw_vs_non_btw_evidence.json` 是 seeded fixture 却被标成「接口真值」**,而且它的 `"state"` 和 PR 正文不一致。
6. **T5b 那个返工 commit 没留交付记录**(没有 walls 条目、没有 mutation 表、没有门禁实测数),必改 3 也缺一条真机证据。门禁数字是验收方补测的。
7. **worktree 清理**:`.worktrees/wt-T5b` 和 `.worktrees/wt-T5c` 现在可以用 `scripts/cleanup_merged_worktree.sh` 清掉(全栈已进 dev)。

---

## 六、本轮已完成并发布

| 迭代点 | 落在哪 | 版本 |
|---|---|---|
| T7f · 删掉已排队的引导,界面说实话 | `main` | v4.22.3 |
| 更新对话框里可以选 4.x / 5.x 通道 | `main` | v4.22.3 |
| 设置多了「运行环境」标签页(从 5.x 回流) | `main` | v4.22.3 |
| 连接不稳定时不再动不动弹红条 | `main` | v4.22.3 |
| T7b · 收起的旁问卡片不会自己弹回来 | `main` | **v4.22.4** |
| grok Build 进 TUI | `dev` | v5.0.2 |
| 日常界面收口(聊天/设置/Bot 抽屉) | `dev` | v5.0.2 |
| T7e · 被打断的回合不再是一片空白 | `dev` | **v5.0.3** |
| T5a+T5b · Bot 按周期自己醒来 + 定时管理列表 | `dev` | **v5.0.4** |
| T5c · 在对话里换 Bot 的模型,下一轮生效 | `dev` | **v5.0.4** |

完整索引在 `docs/mms-web/CHANGELOG.md`,每版详细说明在 `docs/mms-web/RELEASE-v<版本>.md`。

---

## 七、派发时要带给执行方的硬约束

每个包里都写了,这里汇总一次:

- **绝不**碰端口 **8767 / 60824 / 8765 / 8766** —— 机主自己的 Pilot 跑在上面。要起验证实例用 61000-62000 的随机端口。
- **只 kill 自己启动的 PID。** 不要用端口号或进程名批量 grep 之后 kill —— 61xxx 段上可能有别的会话的验证实例。上一轮有个验收方用 `grep "mms_web --port 61"` 批量 kill,误杀了两个不属于它的进程。
- **绝不**用 `pkill`。
- **绝不**写真实 `~/.config/mms*` 或 `~/.mms`。用临时 HOME;跑 gate 前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。
- **绝不**动保护文件:`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- **不要** merge PR,**不要**改别人的 worktree,**不要** stash / reset / clean。
- **改了 `apps/mms-web/src` 就要在同一个 commit 重建 bundle**(`python3 scripts/build_mms_web_release.py`)。重建时要能从仓库 lockfile 复现 —— 先 `npm ci --workspaces=false --ignore-scripts`,不要让本地 node_modules 的漂移进到产物里。
- 真实页面交互用 **ego-browser**(仓库规则),不要用 Playwright。
- **真机证据必须能从仓库代码复现。** 截图会被逐张核对图标和文案是否和源码里的映射自洽。
- 前端测试必须真渲染(`react-dom/server` 的 `renderToStaticMarkup`),不许只 `readFileSync` + 正则。现成范式:`apps/mms-web/tests/bot-schedule-panel-render.test.mjs`、`apps/mms-web/tests/composer-effort-picker.test.mjs`。
- **mutation 是硬要求**:把核心改动撤掉,测试必须变红。这一批已经三次栽在"测试全绿而整块 UI 可以从 JSX 删光"。
- `node --test apps/mms-web/tests/*.test.mjs` 的 **glob 必须带**,否则 `markdown-reading.test.mjs` 会因为缺 `unified` 失败;worktree 里先 `npm install`。
- fresh-user gate **对并发敏感**:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败。串行跑一次,红了单独复跑确认并如实写明。
