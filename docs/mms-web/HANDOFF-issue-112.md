# issue-112 交接：识图能力真值、Web 能力编辑与界面收口

分支 `issue-112-vision-truth`，PR [#114](https://github.com/CtriXin/multi-model-switch/pull/114)，20 个提交，68 个文件，+2895 / -300。
基点是 dev 的 `6c8c934c`（PR #111 合并后）。已 cherry-pick dev 的 `ee92bebb`（PR #118 版本号显示）。

**尚未做整体合并。** dev 之后又合入了 #115 成果侧栏、#116 项目资料与上下文来源。冲突面见文末。

---

## 一、识图能力真值（issue #112 的主线）

### 排查到的两个独立缺陷

**中转扩展的自检从不生效。** `mms_pi_support.py` 无条件注入 `scripts/pi-vision-extension.ts`。该扩展本来会检查主模型是否多模态，多模态就不注册 `describe_image`。但它读的是 `process.env.PI_MODEL`，而 MMS 写入的是 `MMS_PI_SELECTED_MODEL`，`settings.json` 里也没有 `defaultModel`，模型是经 `--model` 命令行参数传给 Pi 的。因此 `currentModel` 恒为 undefined，自检永不触发，k3 这类能自己读图的模型也被注册了中转工具并实际调用。

排查依据：读代码，加上核对本机真实 gateway 会话的 `settings.json`，确认其中只有 retry、extensions、theme，没有 `defaultModel`。

**vision 有四份互不联动的真值。** `_PI_MODEL_INPUT_HINTS`（mms_pi_support）、`_VISION_CAPABLE_MODEL_NAMES`（mms_core）、`_KNOWN_VISION_MODELS`（mms_config_web）、`resolve_model_capabilities`。`_pi_model_input_types()` 不调用能力解析器，所以 WebUI 与 model-policy 的设置到不了 Pi。

### 改法

`_pi_model_input_types(model_name, caps=None)` 现在接收解析后的能力，优先级从高到低：

1. 用户自己设的：`manual_override`、`model_policy`
2. `_PI_MODEL_INPUT_HINTS`：只放 Pi 实测结论
3. curated：`provider_profile`、`approved_facts`
4. 名称匹配兜底

保留第 2 层高于第 3 层是有原因的：`minimax-m2.7` 被 hint 钉成纯文本，而 2026-05-21 的 calibration 说它支持图片。全表 12 个模型判定零变化。

`conservative_fallback` 不能当作「不支持图片」，它的含义是没有任何来源声明过。

### 中转链路

启动前算好结论，经两个环境变量注入：

- `MMS_PI_MAIN_MODEL_VISION`：`1` 表示主模型自己能读图，扩展直接不注册工具
- `MMS_PI_VISION_POOL`：JSON 数组，本通道能读图的 models.json wire id

**候选池没有内置模型名单。** 池子就是当前通道里能力判定为能读图的模型，每次识图随机取用，失败依次降级。原来写死的 `["MiniMax-M3", "kimi-for-coding", "gpt-5.5"]` 已删除，`tests/test_pi_vision_relay.py` 里有一条断言禁止任何模型名重新出现在选择路径上。

唯一开关是 `config.toml` 的 `[vision_sidecar] enabled`。池子为空时 launcher 打印明确提示，不静默降级。

契约写在 `docs/AGENT_GUARDRAILS.md` 的 Vision Capability Single Truth 与 Pi Vision Relay Contract 两节。

### 验证

按用户给定规则实测：k3 可读图，deepseek-v4-flash 与 v4-pro 不可，glm 不可。provider profiles 里本来就是这么声明的，之前只是 Pi 不读。

`deepseek-v4.1-flash` 的 profile 位于本地未推送的提交 `628e6b2f`（作者 GLM-5.3），不在本分支。该数据一旦落地即自动生效，不需要再改代码。

---

## 二、Web 能力编辑

通道模型页新增能力列：可读取图片、上下文长度可编辑，走 effort 已有的预览确认写入通道。每行标注当前值来源（你设置的 / 通道预设 / MMF 目录 / 未声明按保守值）。

当某行与 MMF 目录已知能力不一致时出现「用 MMF 默认」按钮。目录值由 `resolve_model_capabilities(..., model_policy={})` 算出，即覆盖之前 MMF 本来知道的事实，不是猜的默认值。

两条端到端测试证明：在 Web 里改识图或上下文并保存后，新启动的 Pi 会话读到的 `input` 与 `contextWindow` 确实改变，来源为 `model_policy`。

---

## 三、工作区与会话管理

`catalog.py` 新增 `rename_workspace` / `remove_workspace`，`server.py` 加两条路由。移除只从侧栏移除，目录、文件和会话都保留，会话落到「其他工作空间」分组仍可打开和搜索；启动目录不可移除。

侧栏交互：工作区标题 hover 出全部收起与排序菜单（手动 / 按最后编辑时间），文件夹 hover 出复制路径、重命名、移除、上移下移、在该目录新建会话，会话行 hover 出复制 Session ID、重命名、分叉、导出、归档与时间戳，长列表分页加载。排序、顺序、折叠状态存在浏览器。

---

## 四、外观与设置

**设置改为 960×680 弹窗**，不再占整个路由。行内边距从 27px 收到 11px，说明文字行高从 1.9 收到 1.5。

**主题**新增跟随系统，实时跟随 `prefers-color-scheme`，不需要刷新。

**主题色**换成 Glint 的五个：靛蓝、青蓝、品红、琥珀、翠绿。深色用 Glint 原值，浅色做了加深版本，否则 `#8C8CFF` 这类在白底对比度不够。

**字体**分界面、等宽、中文兜底三项，家族名取自 Glint 的 FontCatalog。抄了它一条规则：只列这台电脑真的装了的字体，用 canvas 宽度探测判断。选了一个没装的字体却毫无变化，比少几个选项更糟。字号改为加减步进器，12 到 20，立即生效。

**安装器分发编程字体。** `install.sh` 新增 `install_coding_fonts`，把 Fira Code 与 JetBrains Mono 装到用户字体目录（macOS `~/Library/Fonts`，Linux `~/.local/share/fonts`）。两者均为 SIL OFL，可再分发。已装则跳过，`--no-coding-fonts` 关闭，`--dry-run` 如实报告。

**选择即复制**，默认关闭。开启后在对话区选中文字即写入剪贴板。它写的是系统剪贴板，会覆盖原有内容，这一点与终端的 primary selection 不同，是浏览器的能力边界。输入框内的选择和空选区不触发。依赖 `navigator.clipboard`，需要安全上下文；`127.0.0.1` 满足，局域网 http 地址不满足。

---

## 五、厂商标记

`apps/mms-web/public/vendor/` 下 16 个 SVG，来自 `@lobehub/icons-static-svg`（MIT），用彩色变体。覆盖 Claude、OpenAI、Gemini、Grok、DeepSeek、Qwen、Kimi、MiniMax、GLM、StepFun、豆包、混元、文心、Llama、Mistral、Nemotron。

GLM 用的是智谱的 Z 标，不是 ChatGLM 产品图标。

没有对应文件的厂商回退首字母，不画自造图形冒充 logo。**新增厂商 = 丢一个 SVG 进该目录 + 在 `VendorMark.tsx` 的 tint 表加一行。**

Kimi 和 Grok 的标记自带深色圆角底板，不再加徽标底色。

---

## 六、界面细节

从 Gemini 的 `feat/ui-pilot-redesign` 取了非品牌部分：字体基础层、更利落的状态文案、运行状态胶囊（完成后整体消失）、状态点静态光环替代脉冲、选中行处理。

**没取两条并说明原因**：它把 `font-variant-numeric: tabular-nums` 和 `letter-spacing: -0.012em` 加在 `:root` 上。等宽数字放进中文句子会让数字发散，负字距对中文是把字挤在一起，而这个界面中文占绝大多数。等宽数字改为只用在需要对齐的地方，负字距不用。另外该分支 `mms_web_static/brand/` 有 836 KB 未被引用的 PNG，建议删。

其余修复：

- 过程开关从会话末尾移到工作栏，跟随滚动常驻；状态与位置合并成一行
- 侧栏会话行改为槽位互换，菜单占用状态点位置，标题截断点不随 hover 移动
- 会话行右侧固定预留 30px，标题在菜单之前截断，任何状态下不重叠
- 补齐动效令牌 `--duration-fast` / `--duration-base` / `--ease-out`；禁用状态不再响应 hover；侧栏新控件补焦点环
- 工作区选择器的焦点描边移到 chip 层（原来 select 的 3px 外扩正好等于 chip 的 5px 内边距，环压在边框上成了两层框）
- 搜索结果行的中间列补 `min-width: 0`，标题与副标题单行截断，箭头 `flex: none`
- 两个设置面板统一字号（模型页原来是 17px/23px 的整页尺度，外观页是 13px）
- 模型浏览器改为纵向弹性布局，搜索条按需占位、两栏取剩余高度并各自滚动（此前两栏取满框高，比框高出一个搜索条的高度被裁掉）
- 嵌套弹窗的内边距（`dialog:has(.model-explorer)` 用后代选择器命中了嵌套弹窗，改为直接子元素）
- 新会话标题截断时补省略号（前端 `text.slice(0, 42)` 原来什么都不加）
- 浏览器标签页图标按主题色实时生成

---

## 七、验证

| 项目 | 结果 |
| --- | --- |
| 完整测试套件 | 1756 passed |
| 相对 dev 的新增失败 | 0 |
| fresh-user gate | 467 passed / 12 failed，与基线逐条一致 |
| 新增测试 | 27（vision relay 14、workspace 5、capability 8） |
| TypeScript 与 vite 构建 | 通过 |

套件里那批失败在未改动的检出上同样存在。其中 5 个 state-core 用例在 /tmp 路径下会被跳过，在真实仓库路径下失败，与本分支无关。

浏览器实测（ego-browser + 8801 实例）：工作区排序菜单、文件夹操作菜单、会话操作菜单、收起全部的状态切换、过程开关在单轮手动展开后的文案、字体设置、模型家族着色、设置弹窗对齐与滚动、焦点描边、搜索行截断、版本号显示。

---

## 八、给下一位的注意事项

**改 `server.py` 后必须重启服务。** 静态资源每次请求读盘，前端改动刷新即可见；Python 代码是进程启动时加载的。#118 的 `appVersion` 一开始不显示就是这个原因。

**本地测试实例**：`~/.local/share/mms-web-pr114` 是 live-state 的副本，跑在 8801。用户的服务在 8765，state root 是 `.../live-state`，不要动。

**未做整体合并。** dev 领先 8 个提交（#115 #116 #118）。冲突文件：`App.tsx`、`components.tsx`、`SettingsPage.tsx`、`studio.css`、`server.py`，加上生成的前端产物。

接的时候需要注意：#118 的版本号在本分支接在品牌徽章之后，设置里放在标签行右端（原来的 `settings-heading` 已随设置改弹窗而删除，对应 CSS 也改成了 `.settings-tabs > .app-version`）。#115 和 #116 也动了 `App.tsx` 与 `SettingsPage.tsx`，合并后请在浏览器里重新过一遍设置弹窗、模型页滚动与侧栏。

**前端产物冲突一律重建**，不要手工解：`rm -rf apps/mms-web/dist && python3 scripts/build_mms_web_release.py --skip-install`。

**Gemini 曾把品牌提交直接推到本分支**（`e1f34d29`，作者 Antigravity）。该提交的样式我没有覆盖，logo 几何后来按用户要求恢复成 8765 的比例：4×18、中间 12、间距 3、圆角取宽度一半、每根独立倾斜 13 度。原先是整组容器倾斜，会连间距一起斜，所以显得锐。

**未做但讨论过的两项**：Pi 没有 Kimi 那种三档审批模式（逐条确认 / 自动通过 / 完全自主），Pi 命令行只有 `--approve` / `--no-approve`，管的是项目本地文件信任。我们现在只有二值的只读规划开关。要做的话 `web-controls.ts` 已经在 `tool_call` 上逐个拦截，三种行为都能实现。另外 Pi 未发出过结构化 todo 事件（核对了 11 个真实会话的记录），Kimi 那个待办面板不会自己出现。
