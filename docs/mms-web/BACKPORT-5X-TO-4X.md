# MMS 5.x 到 4.x (main 稳定线) 代码回流流程规范与模板

> 适用场景：将 5.x (如 `dev` / `dev-pre`) 中自包含的优质能力与修复，单独摘取并回流到 4.22.x / 4.x 稳定线（重组后为 `main` 分支），同时绝对不带进 5.x 专属模块（如 Bot 工作台等）。
> 首次实践案例：T6b（「运行环境」设置 Tab 回流）。

---

## 1. 确定改动边界与关注点分类

在做 5.x → 4.x 回流时，最常见的来源是一个混合了多个特性的巨大 commit 或合并（例如当年的 revert commit `e4b053ef` 一口气移除了 Bot、运行环境 Tab、发布列表、browser_provider 等）。

**边界判定三步法**：
1. **分类关注点**：列出源改动中包含的所有独立功能模块，明确本次只回流哪一个（如：只要「运行环境」Tab，坚决不要 Bot 工作台及无关辅助接口）。
2. **依赖正向与逆向排查**：
   - **正向调用链**：检查要回流的目标组件（如 `SettingsPage.tsx`）的全部 imports、API 请求及数据来源。
   - **逆向消费方**：检查疑似相关的类/函数（如 `browser_provider.py`、`/api/v1/update/history`）的全部消费者。如果某模块的所有消费者均为 5.x 专属模块（例如 `browser_provider.py` 仅被 `bot_computer.py`、`bots.py`、`test_mms_bot_coordinator.py` 消费），则坚决不带。
3. **环境就绪度确认**：检查 4.x 目标分支是否已有现成后端支持。若后端已有数据源（如 4.x `server.py` 已提供 `capability_snapshot()`，`types.ts` 已声明对应结构），则本次回流应严格收敛为**纯前端改动**，绝不随意动 Python 后端。

---

## 2. 怎么证明不带进不该带的东西（干净回流保证）

4.x 稳定线有极高的干净度约束（如：**4.22.x 保持无 Bot**）。验证方式必须客观、可量化且零遗漏：

1. **Import 白名单核对**：检查修改后的源文件 import 清单，确保每一个依赖模块在 4.x 线上合法存在，且不含任何受限前缀（如无 `Bot*.tsx`、`bot*.css` 等）。
2. **文本级与单词边界严格 Grep**：
   - 使用正则表达式单词边界 `grep -inE "\bbot\b|\.bot" <changed_files>` 检查，确保不是误命中 `bottom` 或 `both`，且零命中违规关键词。
   - 重点注意 CSS 文件合并：从 5.x 挑选样式块时，必须人工跳过主题选择器列表中的 `.bot-workspace` 或 `.sidebar-footer.has-bots-entry` 等混装规则。
3. **代码库全局树断言**：
   - 提交前与 CI 门禁中运行：
     ```bash
     git ls-tree -r --name-only HEAD | grep -i bot
     ```
     必须严格返回零条。
4. **添加不可逆守卫测试**：
   - 为该隔离约束新建专用自动化测试（例如 `tests/test_mms_4_22_no_workbench.py`），对关键目录 glob 及核心源码进行断言，防止未来任何合并意外引入违规文件。

---

## 3. 混装测试文件的拆解策略

5.x 上的单测文件经常是多个特性的混装测试（例如 `settings-runtime-updates.test.mjs` 中混杂了 semver、运行环境、发布历史、Bot 工作台、重试按钮等）。

**拆解原则**：
1. **精确摘取**：只截取与目标功能直接相关的测试用例块（例如只提取验证「运行环境」Tab 及芯片渲染的断言）。
2. **剔除未回流依赖**：若 5.x 测试依赖了未带回的工具（如 `semver-sort.ts`），坚决不要强行引入该工具，直接剔除相关测试块。
3. **独立命名**：严禁沿用原混装测试文件名，应采用能清晰反映回流特性的专属文件名（例如 `settings-runtime.test.mjs`）。
4. **双端适配与防回归**：为 4.x 特有的边界补充测试用例，例如验证旧版常驻卡片已从顶部剥离、主题对比度符合无硬编码语义规范。

---

## 4. 两条线结构差异的手工对齐

5.x 与 4.x 通常已存在多轮分叉，不可直接执行盲目的 `git cherry-pick`，必须做手工对齐。

**典型案例：三元运算符与布局重构**
- 5.x 设置页是平铺的 4 路分支：`models / appearance / usage / runtime`。
- 4.x 原本是 3 路分支且带有嵌套括号，同时在 `</nav>` 下方常驻了一个旧的 `<section className="platform-capability">`。
- **对齐步骤**：
  1. 将旧的嵌套三元展开为清晰对齐的 4 路条件渲染分支。
  2. 做出关键交互决策：将原本在 `</nav>` 下方常驻的旧平台能力卡彻底移入新的「运行环境」Tab 内，消除“同一份信息显示两遍”的体验回归。
  3. 清理废弃 CSS：在引入新规则的同时，同步删除 4.x 中被取代的旧简化样式（如旧 `.platform-capability strong` 简写），防止两套 CSS 规则竞争冲突。
  4. 每次结构调整后立即运行 `npx tsc --noEmit -p apps/mms-web` 确保类型与 JSX 闭合完全无误。

---

## 5. 门禁验证体系与基线比对

必须在回流前后使用**定量比对法**，不能凭印象或绝对通过数判定。

### 5.1 基线获取（开工第一件事）
在 base ref（未修改状态）下运行并记录：
- 前端测试：`node --test apps/mms-web/tests/*.test.mjs`（记录 passed 数量，如 56 passed）
- 专项 pytest：`python3 -m pytest tests/test_mms_web_updates.py tests/test_mms_release_version.py -q`（如 14 passed）
- 类型检查：`npx tsc --noEmit -p apps/mms-web`（应为 0 错误）

### 5.2 回流后的全量门禁检查单
1. **类型安全**：`npx tsc --noEmit -p apps/mms-web`（必须 0 错误）。
2. **前端单测**：`node --test apps/mms-web/tests/*.test.mjs`（通过数 ≥ 基线 + 新增数，且 0 fail）。
3. **前端打包**：`npm run build --workspace @mms/web`（确保 dist 正确生成且无 rollup 报错）。
4. **专属防御测试**：`PYTHONPATH=. python3 -m pytest -q tests/test_mms_4_22_no_bot.py`（全量通过）。
5. **新用户全量回归 Gate**：`python3 scripts/regression_fresh_user_gate.py`（完整版运行，对比既存失败集合，diff 必须为空）。
6. **无受限符号检查**：
   ```bash
   git ls-tree -r --name-only HEAD | grep -i bot  # 必须为 0
   grep -inE "\bbot\b|\.bot" apps/mms-web/src/studio.css # 必须为 0
   ```

### 5.3 真实视觉与交互验证（隔离端口）
- 严禁重启或污染正在运行的实例（如 60824 和 8767）。
- 使用高位隔离端口（如 `61755`）和独立临时 state-root（如 `/tmp/bot-verify-t6b`）启动实例。
- 借助 `ego-browser` 进行全流程界面操作和真实渲染验证。
- 截图归档至 `docs/mms-web/design/<task-id>/`，必须覆盖：
  - 导航 Tab 并列与选中状态；
  - 核心内容卡片、芯片（chip）、状态 pill、动态目录展示；
  - 极端边界与空状态兜底展示；
  - 旧位置残留检查（无重复显示）。

---

## 6. 常见陷阱与避坑指南 (Lessons Learned)

1. **同名误导陷阱**：
   - 看到名字相似（如 `browser_provider.py` 与运行环境页上的“浏览器能力”），不可想当然地认为存在依赖，必须追查 AST/调用树确认真相。
2. **CSS 混装污染**：
   - 5.x 的全局样式文件往往在公共选择器列表中夹杂了专属类（如 `.bot-workspace`），大段复制粘贴极易破坏无污染硬约束。复制必须精确定位行号范围，并在复制后强制全文 grep。
3. **混装测试的盲目迁移**：
   - 直接把 5.x 测试文件整体复制过来往往会因缺失 `semver-sort.ts` 或 Bot API 而报错。必须按功能段落裁剪，并赋予清晰命名的独立测试文件。
4. **常驻卡片重复展示回归**：
   - 在 4.x 中很多能力原本是直接挂在通用设置或 nav 下方的，回流到独立 Tab 后，必须记得移除外层旧组件，否则会导致同一信息在页面出现两遍。
5. **后续合流提示（4.x → 5.x 反向同步）**：
   - owner 策略是“4.x 的所有改动默认进入 5.x”。当本回流 PR 合入 `main` 后，未来合回 `dev` (5.x) 时，由于 5.x 已经有该 Tab，合并者**切勿直接用 4.x 文件强行覆盖 5.x**，避免将 5.x 上的其它专属增强冲掉。
