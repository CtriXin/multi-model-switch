# 逐 PR 台账（198 条）

分类解释和具体迁移入口见 [能力对照](CAPABILITIES.md)。完整文件列表、commit、主分支祖先关系见 [CSV](PR-INVENTORY.csv) 或 [交互筛选](index.html)。

**MERGED 是 GitHub 状态；main/dev 历史包含不证明当前能力仍在。** 例如 Bot 曾合入再撤销。CLOSED 可能已被其他提交吸收，OPEN 不计已交付能力。D 不是现在删除产品的授权。

| PR | 原标题 | 状态 | 分类 / 能力 | 逐项判断 |
|---|---|---|---|---|
| [#111](https://github.com/CtriXin/multi-model-switch/pull/111) | feat: MMS v4 本地 Web 对话与 Pi 会话控制 | MERGED | P,D / C03,C08,C12,C13,C14,C15 | v4 首个 Web/Pi 控制面；保留模板和使用要求，通用聊天、流式与 RPC 包装可在替代验收后退役。 |
| [#113](https://github.com/CtriXin/multi-model-switch/pull/113) | fix(web): persist standalone model defaults in v4.0.1 | MERGED | P,R / C01,C02 | 独立模型默认值属于配置合同；接 DSH 时导出明确默认值，不依赖其环境猜测。 |
| [#114](https://github.com/CtriXin/multi-model-switch/pull/114) | fix(vision): 统一识图能力真值；feat(web): 模型能力编辑、侧栏操作与外观设置 | MERGED | P,D / C02,C12,C15 | 保留能力真值、来源与人工复核；模型页和主题实现可重做。部分内容先经 #124 整合，不能重复算功能。 |
| [#115](https://github.com/CtriXin/multi-model-switch/pull/115) | feat(web): artifact previews, selections and version comparison (v4.1.0) | MERGED | P,D / C05 | 预览大部可复用 DSH；有界内容快照、版本差异、选段绑定仍是独立插件候选。 |
| [#116](https://github.com/CtriXin/multi-model-switch/pull/116) | feat(web): project materials and per-message source records (4.2.0) | MERGED | P / C04 | 项目资料及来源记录值得保留；通过上下文/持久化插件实现，不能只拷一段 system prompt。 |
| [#118](https://github.com/CtriXin/multi-model-switch/pull/118) | fix(web): show the running version in the logo and settings (4.2.1) | MERGED | C,T / C11 | 运行版本显示属于发行层真值；不需要 fork DSH core，保留源码/安装/bundle 一致性验收。 |
| [#119](https://github.com/CtriXin/multi-model-switch/pull/119) | feat(web): v4.3.0 新手悬浮引导与功能帮助 | MERGED | P,C,D / C15 | 教程和帮助按目标用户保留；旧 DOM 锚点和页面布局不移植。 |
| [#120](https://github.com/CtriXin/multi-model-switch/pull/120) | 简化一键安装：移除 9 个可选包、零选择、pi 必装、装完打开 MMS Web | MERGED | C,R,D / C06,C09,C10 | 安装简化与 Pi 就绪判定留在 MMS；退役的全局包不恢复，清理保护以 #124/#130 后续实现为准。 |
| [#122](https://github.com/CtriXin/multi-model-switch/pull/122) | 增加 npx 安装入口：npx @ctrixin/mms | CLOSED | C,H / C10 | 已被其他安装 PR 吸收而关闭；不重新合并。npx 分发入口是自有发行层，不是 DSH core 功能。 |
| [#124](https://github.com/CtriXin/multi-model-switch/pull/124) | feat(web): integrate PR 114 and 120 as MMS Pilot v4.4.0 | MERGED | P,C,R,T / C02,C05,C09,C10,C12,C15 | 整合 #114/#120 且另有热切模型、隔离实例和清理保护修复；不是单纯版本 PR，保留这些合同。 |
| [#125](https://github.com/CtriXin/multi-model-switch/pull/125) | MMS Web 版本提示与页面一键升级 | CLOSED | H,D / C11 | 旧更新原型已由 #137 之后的事务更新替代；无需移植原型，但不能删除安全更新需求。 |
| [#127](https://github.com/CtriXin/multi-model-switch/pull/127) | 能力真值按官方文档核对，批量填入改为逐行复核 | MERGED | P,R / C01,C02 | 官方能力资料、来源索引、人工复核和 OpenRouter discovery 可做 registry 适配插件；历史具体数值需按新真值更新。 |
| [#128](https://github.com/CtriXin/multi-model-switch/pull/128) | feat(pilot): inline files, project search and capability review v4.5.0 | MERGED | P,D / C02,C05,C14 | 附件落盘/正文路径、项目搜索、能力复核有价值；通用附件 UI 可用 DSH，项目定位与证据另补。 |
| [#130](https://github.com/CtriXin/multi-model-switch/pull/130) | 停止安装 offduty/onduty 与 /nsr，并清理已装条目 | MERGED | R,D / C06,C09 | 停止全局强装 skills 并限制清理目标是既有边界；不把退休全局注入机制搬到 DSH。 |
| [#131](https://github.com/CtriXin/multi-model-switch/pull/131) | feat(web): 先连接服务再开始新手教程，发布 v4.6.0 | MERGED | P,C,D / C01,C15 | 面向同事的连接优先引导保留，DSH 通用 provider 设置可复用；向导页面只迁移缺口。 |
| [#132](https://github.com/CtriXin/multi-model-switch/pull/132) | feat(pilot): 开箱即用的任务 skills 与文件夹引用 v4.7.0 | MERGED | P,R / C06,C14 | 任务 skills、显式草稿和目录引用可做 bundle/preset；原 skill 内容优先复用，避免再造工具链。 |
| [#133](https://github.com/CtriXin/multi-model-switch/pull/133) | fix(pilot): keep session status readable and label file entry (v4.7.1) | MERGED | P,D / C12,C13 | 状态和文件入口文案是 UX 验收项；先比较 DSH 原生表现，再决定少量 UI 插件。 |
| [#134](https://github.com/CtriXin/multi-model-switch/pull/134) | fix(pilot): hide empty context receipts and simplify material details (v4.7.2) | MERGED | D,T / C04,C13 | 空上下文回执不展示的规则保留；旧 React 分支无需单独移植。 |
| [#135](https://github.com/CtriXin/multi-model-switch/pull/135) | feat(pilot): quick model selection with optional channel controls (v4.8.0) | MERGED | P,D / C01,C12 | 模型快捷入口和可选通道控制；DSH 已有模型座位，差异只做通道友好名/策略插件。 |
| [#136](https://github.com/CtriXin/multi-model-switch/pull/136) | release: promote Pilot v4.8.0 to main | MERGED | H / C24 | main 发布整合记录；能力归原功能 PR，不计第二份迁移工作。 |
| [#137](https://github.com/CtriXin/multi-model-switch/pull/137) | feat(pilot): ship v4.9 safe updates and simpler installation | MERGED | C,T,D / C10,C11 | 安全更新及 npx 安装整合；保留预检/回滚/真实版本规则，旧 Python 更新事务不是 DSH 插件必搬对象。 |
| [#138](https://github.com/CtriXin/multi-model-switch/pull/138) | feat(pilot): capability bulk selection and v4.8.1 | MERGED | P,D / C02,C12 | 能力批量勾选保留为 registry 管理 UX；不意味着要复制整个模型设置页。 |
| [#139](https://github.com/CtriXin/multi-model-switch/pull/139) | release: sync Pilot v4.8.1 to main | MERGED | H / C24 | 4.8.1 发布整合；按 #138 能力归类。 |
| [#140](https://github.com/CtriXin/multi-model-switch/pull/140) | release: publish Pilot v4.9.0 safe updates on main | MERGED | H / C24 | 4.9 发布整合；按 #137 能力归类。 |
| [#142](https://github.com/CtriXin/multi-model-switch/pull/142) | 更新说明按 Markdown 渲染；工作区名不再压在悬停按钮下 | MERGED | C,D / C11,C15 | Markdown 发布说明和侧栏布局可由定制 UI/发行元数据覆盖；旧样式不搬。 |
| [#143](https://github.com/CtriXin/multi-model-switch/pull/143) | feat(pilot): v4.10.0 连接悬浮引导、来源记录与任务模板 v2 | MERGED | P / C03,C04,C06,C15 | Recipe v2、实际消费证据、连接引导；重点迁移能力要求复核、脱敏预览和来源证据，不是单纯 preset 目录。 |
| [#144](https://github.com/CtriXin/multi-model-switch/pull/144) | release(pilot): v4.10.0 连接悬浮引导与可分享任务 | MERGED | H / C24 | 4.10 发布整合；功能计入 #143。 |
| [#147](https://github.com/CtriXin/multi-model-switch/pull/147) | 两条安装命令输出对齐：按结果而不是按参数决定版本提示 | MERGED | C,T / C10,C11 | 安装提示必须对应实际解析版本；留作发行验收，不 fork core。 |
| [#149](https://github.com/CtriXin/multi-model-switch/pull/149) | Pilot 读取命令行启动的会话（只读） | MERGED | P,R / C07,C08 | 实际 merge 同时涉及只读 CLI 会话与远程访问；Pi 历史需要专用桥接，DSH 持久化不自动兼容 Pi JSONL。 |
| [#152](https://github.com/CtriXin/multi-model-switch/pull/152) | fix(claude): use well-formed deny rule "Bash(rm -rf /*)" | MERGED | R,T / C09 | Claude 路径 deny 规则留在 MMS launcher；与替换 Pilot 执行引擎无关。 |
| [#153](https://github.com/CtriXin/multi-model-switch/pull/153) | 统一配置根：CLI 与 Pilot 共用 mms-next | MERGED | R,C,T / C01,C09,C10 | 单配置根和首次 bootstrap 属于 MMS 配置控制面；保留保护与迁移边界。 |
| [#154](https://github.com/CtriXin/multi-model-switch/pull/154) | release(pilot): v4.10.1 | MERGED | H / C24 | 4.10.1 发布包装；不独立迁移。 |
| [#155](https://github.com/CtriXin/multi-model-switch/pull/155) | Pilot: 文件预览同步、Weber 收口、Skills 合并、设置拆分、附件清理、通道增删 | MERGED | P,R,D / C01,C05,C06,C12 | 文件预览、Weber/Skills 合并、附件生命周期与通道增删的混合 PR；复用 skills 和合同，按模块迁移。 |
| [#156](https://github.com/CtriXin/multi-model-switch/pull/156) | release: v4.11.0 shared config root | MERGED | H / C24 | 4.11 发布包装；功能归 #155。 |
| [#157](https://github.com/CtriXin/multi-model-switch/pull/157) | feat(pilot): 会话消息显示时间戳与回复用时 | MERGED | D,T / C13 | 时间戳/耗时属于通用会话展示；DSH 可优先替代，保留时间语义验收。 |
| [#158](https://github.com/CtriXin/multi-model-switch/pull/158) | chore: release v4.11.1 | MERGED | H / C24 | 4.11.1 发布包装；不单独迁移。 |
| [#159](https://github.com/CtriXin/multi-model-switch/pull/159) | 接入终端会话：在 Pilot 里继续 mmf 开始的对话 | MERGED | P,R / C08 | 终端 Pi 会话复制到 Pilot 私有 session 后续接；不是接管同一 PTY，也不能直接当 DSH 原生恢复。 |
| [#163](https://github.com/CtriXin/multi-model-switch/pull/163) | 老机器自动收拢配置，安装不再被运行中的 Pilot 卡死 | MERGED | R,C,T,D / C09,C10 | 配置根收敛保留；自动停止 Pilot 的安装分支已被 #199/#226 撤销，不恢复旧行为。 |
| [#164](https://github.com/CtriXin/multi-model-switch/pull/164) | fix(claude): seed new 2.1.x upsell/dismissal state keys into sessions | MERGED | R,T / C09 | Claude UI-state allowlist 是多 CLI launcher 隔离能力，留 MMS。 |
| [#167](https://github.com/CtriXin/multi-model-switch/pull/167) | 手机端可用：局域网下写操作失败、触摸摸不到行内菜单 | CLOSED | P,T,H / C07,C12 | plain HTTP UUID/clipboard 与触摸菜单已由 #181 吸收；关闭不等于功能丢失，保留移动端验收。 |
| [#168](https://github.com/CtriXin/multi-model-switch/pull/168) | fix(launch): let model_policy override the plain-k3 safe-base window guard | MERGED | P,R,T / C02 | 用户 context policy 优先于旧 K3 guard；当前统一真值以 #233 为准，旧 guard 不重复搬。 |
| [#169](https://github.com/CtriXin/multi-model-switch/pull/169) | fix(web): --listen all 模式下 Origin 校验与 Host 规则一致 | MERGED | P,T / C07 | Host/Origin 一致性是远程访问合同，必须进入 DSH remote 扩展验收。 |
| [#173](https://github.com/CtriXin/multi-model-switch/pull/173) | chore: release v4.12.0 | MERGED | C,H / C08,C24 | 4.12 发布含 CLI 会话设置文案；以 #149/#159 实际采用语义为准。 |
| [#174](https://github.com/CtriXin/multi-model-switch/pull/174) | 首页：输入框可拖高并随输入长高，拉高后「最近」列表移到右侧成两栏 | MERGED | P,D / C12 | 可拖高/自增长 composer 和两栏布局是可选 UX；先用 DSH 原生交互，不预先重写整页。 |
| [#175](https://github.com/CtriXin/multi-model-switch/pull/175) | fix(web): 模型页不再把未设置的 models_endpoint 当成 manual（拉取模型变灰） | MERGED | P,R,T / C01 | models_endpoint 缺省与显式 manual 的区分需要保留；避免插件错误启用敏感通道探测。 |
| [#176](https://github.com/CtriXin/multi-model-switch/pull/176) | chore: release v4.12.1 | MERGED | H / C24 | 4.12.1 发布包装；不单独迁移。 |
| [#179](https://github.com/CtriXin/multi-model-switch/pull/179) | feat(mms-web): 会话页 composer 滚动感知折叠 | MERGED | P,D / C12 | composer 滚动折叠可选 UI 定制；无 core fork 证据。 |
| [#180](https://github.com/CtriXin/multi-model-switch/pull/180) | Pilot 设置页：Enter 发送可关、删掉纯说明区块、开关换成胶囊形态 | MERGED | P,D / C12,C15 | Enter 偏好和设置简化是用户偏好；优先采用 DSH 设置能力，仅补差异。 |
| [#181](https://github.com/CtriXin/multi-model-switch/pull/181) | 手机与另一台电脑访问：设置里一个开关，默认关闭 | MERGED | P,C,T / C07 | LAN 开关、QR、token、接口地址及 #167 手机修复值得保留；DSH 默认 Web 不是直接 LAN 等价物。 |
| [#182](https://github.com/CtriXin/multi-model-switch/pull/182) | feat(pilot): 拖入的文件夹按名字和内容自动找回路径 | MERGED | P / C14 | 目录名称/条目指纹找路径是特定浏览器受限场景能力；可做 workspace 工具/UI 插件。 |
| [#183](https://github.com/CtriXin/multi-model-switch/pull/183) | 配置根只保留 ~/.config/mms-next：旧根退出、mmd/mmm 退休、安装脚本停掉任何占用默认端口的 Pilot | MERGED | R,C,D / C09,C10 | 单根/入口清理保留；旧安装停服路径已被 #199/#226 撤销，不能按本 PR 原样复制。 |
| [#184](https://github.com/CtriXin/multi-model-switch/pull/184) | chore: release v4.13.0 | MERGED | H / C24 | 4.13 发布包装；不单独迁移。 |
| [#185](https://github.com/CtriXin/multi-model-switch/pull/185) | feat(capability): v4.1-tier effort unblocked for deepseek/GLM/Qwen families | MERGED | P,R,T / C02 | effort/vision/token 上限校准方法和证据值得保留；2026-09-10 数字不是永久配置。 |
| [#186](https://github.com/CtriXin/multi-model-switch/pull/186) | fix(web): --listen all 下关闭开关不再清空 token 门禁 | MERGED | P,T / C07 | 对外监听不可关闭 token 门禁，作为 remote 插件硬验收项保留。 |
| [#187](https://github.com/CtriXin/multi-model-switch/pull/187) | chore: release v4.13.1 | MERGED | H / C24 | 4.13.1 发布包装；能力归 #186。 |
| [#189](https://github.com/CtriXin/multi-model-switch/pull/189) | mms web status / url / start / stop / restart：管理本机的 Pilot 服务 | MERGED | C,R,T / C10,C08 | 服务 status/url/start/stop/restart 属于发行管理；当前无 supervisor，不能声称开机自动恢复执行。 |
| [#190](https://github.com/CtriXin/multi-model-switch/pull/190) | chore: release v4.14.0 | MERGED | H / C24 | 4.14 发布包装；功能归 #189。 |
| [#192](https://github.com/CtriXin/multi-model-switch/pull/192) | mms web 不带子命令时打印帮助页 | MERGED | C,D / C10 | 裸 web 命令只打印帮助是 MMS CLI UX；自有 launcher 保留，DSH 侧按新入口设计。 |
| [#194](https://github.com/CtriXin/multi-model-switch/pull/194) | fix(capability): kimi-code k3 context 262144 -> 1048576 (match official calibration) | MERGED | P,R,T / C02 | Kimi context 校准后续收敛至 #233；迁移统一 resolver，不复制多处历史常量。 |
| [#195](https://github.com/CtriXin/multi-model-switch/pull/195) | 更新同时换掉 mms 和 Pilot；确认前说明端口与失效功能，完成后自动刷新 | MERGED | C,T,D / C11 | 整安装更新/候选预检/回滚/确认值得保留；实现留发行层，不能仅更新网页 bundle。 |
| [#196](https://github.com/CtriXin/multi-model-switch/pull/196) | fix(test): 补上 #185 漏改的两条 pi launcher 断言（dev 当前是红的） | MERGED | T,H / C02,C23 | 修复 #185 遗漏断言；保留能力变化必须覆盖真实消费者的验收要求。 |
| [#197](https://github.com/CtriXin/multi-model-switch/pull/197) | chore: release v4.15.0 | MERGED | H / C24 | 4.15 发布包装；包含升级须知格式，不是新执行能力。 |
| [#198](https://github.com/CtriXin/multi-model-switch/pull/198) | fix(update): 不要把新版装进上一次更新留下的暂存副本 | MERGED | C,T / C11 | 禁止把 staging source 当正式安装位置；定制发行层必须保留该边界。 |
| [#199](https://github.com/CtriXin/multi-model-switch/pull/199) | fix: close capability and session safety gaps | MERGED | P,R,C,T,D / C02,C03,C08,C09,C10 | 能力/session/安装安全修复混合；保留附件和隔离，废弃 token-saver 与被撤回的自动停服路径。 |
| [#200](https://github.com/CtriXin/multi-model-switch/pull/200) | fix(web): 终端能跑 Pi 但 Pilot 全灰；顺带说清到底缺什么 | MERGED | R,C,T,D / C09,C10 | Pi 可用性必须与实际启动路径一致；保留 launcher，若完全退出 Pi 才退役缓存探测代码。 |
| [#201](https://github.com/CtriXin/multi-model-switch/pull/201) | chore: release v4.15.1 | MERGED | H / C24 | 4.15.1 发布包装；功能归 #198/#200。 |
| [#202](https://github.com/CtriXin/multi-model-switch/pull/202) | fix(web): npx 装进 npm 默认缓存的 Pi 也要认 | MERGED | R,C,T,D / C09,C10 | npm 默认缓存的 Pi 发现修复；Pi 仍保留时不可删除，DSH 不需要照搬它。 |
| [#203](https://github.com/CtriXin/multi-model-switch/pull/203) | install: 公开默认钉在已验证的 v4.4.0，不再跟最新 release | CLOSED | H,D / C11 | 用户撤回的 v4.4 固定版本方案；不恢复这个历史 pin，仍需明确发行渠道。 |
| [#204](https://github.com/CtriXin/multi-model-switch/pull/204) | fix: finish core runtime and model configuration flow | MERGED | P,R,C,T / C01,C02,C09,C10 | 模型拉取替换、运行根、Pi 安装 fail-closed 等真实混合改动；遗漏回归已由后续 PR 修正。 |
| [#205](https://github.com/CtriXin/multi-model-switch/pull/205) | fix(pi): 全局装了 pi 但 bin 不在 PATH 时，安装被卡死 | MERGED | R,C,T,D / C09,C10 | 全局 Pi bin 不在 PATH 的发现/预热修复；只在 Pi 被正式退役后可删除相关实现。 |
| [#206](https://github.com/CtriXin/multi-model-switch/pull/206) | chore: release v4.15.2 | MERGED | H / C24 | 4.15.2 发布包装；功能归 #205。 |
| [#208](https://github.com/CtriXin/multi-model-switch/pull/208) | fix(config-web): survive a second Ctrl-C during shutdown cleanup | MERGED | R,T,D / C09 | 旧配置 Web Ctrl-C 清理修复；现存维护入口保留，DSH 不需要同份实现。 |
| [#209](https://github.com/CtriXin/multi-model-switch/pull/209) | fix(capability): settle K3 on one context truth and repair the red tests | MERGED | P,R,T,H / C02,C23 | K3 多处真值与测试收敛；以 #233 单 resolver 取代旧常量补丁。 |
| [#210](https://github.com/CtriXin/multi-model-switch/pull/210) | ci: fail a PR for the tests it breaks | MERGED | T / C23 | base/head pytest 门禁值得保留，但其结果分类后来由 #326/#335 加固，不能迁移早期假绿逻辑。 |
| [#211](https://github.com/CtriXin/multi-model-switch/pull/211) | test(pilot): lock model fetch to replace the route, not merge into it | MERGED | P,R,T / C01,C23 | 拉取成功覆盖 channel 模型、删除项不得被新会话使用；重要行为测试应迁入 registry 插件。 |
| [#212](https://github.com/CtriXin/multi-model-switch/pull/212) | feat(config-web): step the configuration WebUI down to a maintenance entry | MERGED | R,D / C09 | 配置 Web 已降为维护入口，仍有账号/偏好/迁移用途；不能因 Pilot/DSH 有设置页就全部删除。 |
| [#213](https://github.com/CtriXin/multi-model-switch/pull/213) | fix(codex): tell Codex the context window of a 1M model it cannot know | MERGED | R,P,T / C02,C09 | Codex context 配置注入留 MMS；代码写入已验证不等于 Codex 实际 compact 行为已验证。 |
| [#214](https://github.com/CtriXin/multi-model-switch/pull/214) | release(pilot): prepare v4.16.0 | MERGED | H / C24 | 4.16 发布包装；按原功能归类。 |
| [#215](https://github.com/CtriXin/multi-model-switch/pull/215) | fix(config): finish retiring ~/.config/mms as a config location | MERGED | R,C,T / C09,C10 | 旧配置根清理和 resolver precedence 保留；不重新启用 legacy root 默认写入。 |
| [#216](https://github.com/CtriXin/multi-model-switch/pull/216) | feat: 识图借用扩展到 Claude Code 和 OpenCode，Pilot 加 What's New | MERGED | P,R,C / C02,C06,C09,C15 | vision MCP relay 可继续复用；What's New 属于发行 UX，后续展示策略已变。 |
| [#217](https://github.com/CtriXin/multi-model-switch/pull/217) | release(pilot): prepare v4.17.0 | MERGED | H / C24 | 4.17 发布包装；功能归 #215/#216。 |
| [#218](https://github.com/CtriXin/multi-model-switch/pull/218) | fix(pilot): show the release notes to installs that already existed | MERGED | C,T,D / C15 | 新安装与升级用户区分是发行验收；自动弹出策略后由 #243 调整，不照搬旧页面逻辑。 |
| [#219](https://github.com/CtriXin/multi-model-switch/pull/219) | release(pilot): prepare v4.17.1 | MERGED | H / C24 | 4.17.1 发布包装；不单独迁移。 |
| [#220](https://github.com/CtriXin/multi-model-switch/pull/220) | release(pilot): prepare v4.18.0 | MERGED | H / C24 | 4.18 发布包装；功能归 #182。 |
| [#221](https://github.com/CtriXin/multi-model-switch/pull/221) | feat(pilot): integrate T1 BTW and T2 message control | MERGED | P,D,T / C13 | BTW、steer/interrupt/queue 的用户语义保留；DSH 原生控制可替代通用部分，旁问隔离和撤回需补测。 |
| [#225](https://github.com/CtriXin/multi-model-switch/pull/225) | release(pilot): prepare v4.19.0 | MERGED | H / C24 | 4.19 发布包装；功能归 #221。 |
| [#226](https://github.com/CtriXin/multi-model-switch/pull/226) | fix(install): tell the user how to update while Pilot is running; drop the dead stop-and-reopen path (#223) | MERGED | R,C,D,T / C10 | 删除无效 stop-and-reopen 安装分支；更新不得无声杀会话的规则保留。 |
| [#227](https://github.com/CtriXin/multi-model-switch/pull/227) | fix: restore k3[1m] vision fallback, fix bridge lb_debug path, stale ChannelModels label, guardrails drift (#224) | MERGED | P,R,T / C01,C02,C09 | vision 名称兜底、bridge lb_debug、通道陈旧标签及 guardrails 修复；不属于可被 DSH Web 直接覆盖的 launcher 代码。 |
| [#228](https://github.com/CtriXin/multi-model-switch/pull/228) | test: reconcile the tests broken by #199/#204/#205 with the mms-next contract (#222) | MERGED | R,T / C09,C23 | 测试合同收敛同时含 real-home 产品修复；保留隔离和路径合同，不只是测试数量变化。 |
| [#229](https://github.com/CtriXin/multi-model-switch/pull/229) | release: v4.19.1 fixes | MERGED | R,C,H / C09,C24 | 发布同时补 gateway HOME 的 real-home marker，不能仅按 release 标题当作无代码。 |
| [#231](https://github.com/CtriXin/multi-model-switch/pull/231) | feat: add Windows Native Preview support | MERGED | C,R,T,D / C09,C10,C22 | Windows Native Preview 跨平台/安装/锁/路径边界保留；Python/Pi 专用 shim 仅在不再使用时退役。 |
| [#232](https://github.com/CtriXin/multi-model-switch/pull/232) | feat: guide safe upgrades across config roots | MERGED | C,R,T / C09,C11 | 跨配置根升级只读引导、阻止不安全一键迁移；发行层能力，不需要 core fork。 |
| [#233](https://github.com/CtriXin/multi-model-switch/pull/233) | feat(capability): one context-window truth for every harness; [1m] becomes input normalization (#230) | MERGED | P,R,T / C02 | 跨 harness context-window 单真值及输入别名归一化是重要资产；DSH adapter 消费解析结果。 |
| [#234](https://github.com/CtriXin/multi-model-switch/pull/234) | fix: keep public installer on mms entrypoint | MERGED | R,C,T / C09,C10 | 公开 mms 与维护者本机别名分离；留自有安装器，避免覆盖人的工作入口。 |
| [#235](https://github.com/CtriXin/multi-model-switch/pull/235) | chore: release v4.19.4 | MERGED | H / C24 | 4.19.4 发布包装；功能归 #233。 |
| [#236](https://github.com/CtriXin/multi-model-switch/pull/236) | fix: repair Pilot first-run model settings flow | MERGED | P,R,T,D / C01,C12 | approved bundle 直接启动、空选择提示、保存栏/确认 UX；保留 runtime 合同，页面按需复用。 |
| [#237](https://github.com/CtriXin/multi-model-switch/pull/237) | chore: release v4.20.0 Windows Native Preview | MERGED | C,H,T / C22,C24 | Windows Preview 发布合同保留；Windows Server 通过不代表所有桌面环境已验收。 |
| [#239](https://github.com/CtriXin/multi-model-switch/pull/239) | feat(web): Bot page visual system on Pilot theme tokens | MERGED | P,D,H / C16,C12 | Bot 视觉子 PR 随 #242 集成；可选 UI 插件，不需要复制所有 CSS。 |
| [#240](https://github.com/CtriXin/multi-model-switch/pull/240) | feat(bots): bounded retry for infrastructure errors and result delivery | MERGED | P,T / C20 | 仅执行开始前做基础设施重试、通知日志/HMAC webhook；可做 host 插件，保留防重复副作用边界。 |
| [#241](https://github.com/CtriXin/multi-model-switch/pull/241) | feat(bots): coordinator plan produced by the Bot's model and executed by the runtime | MERGED | P,D,T / C17 | Bot 模型生成计划、依赖执行、批准/撤回；复用 DSH 子代理底层，只补用户需要的计划状态层。 |
| [#242](https://github.com/CtriXin/multi-model-switch/pull/242) | feat(pilot): Bot 工作台 v2.x（身份、任务、协作、记忆、Coordinator、通知、视觉系统） | MERGED | P,D,T / C16,C17,C19,C20 | 持久 Bot/Task/Memory/Mailbox/Coordinator 复合能力；曾被 #262 从稳定线撤销，现 dev 恢复，不能因 Git 祖先关系说 main 有 Bot。 |
| [#243](https://github.com/CtriXin/multi-model-switch/pull/243) | feat(pilot): 设置页运行环境标签、帮助内版本更新、设置边距 | MERGED | P,C,D / C12,C15 | 运行环境 tab、帮助内版本历史、成果复制；事实数据保留，旧 UI 结构按 DSH 插槽重组。 |
| [#244](https://github.com/CtriXin/multi-model-switch/pull/244) | fix(windows): resolve Pi launcher and package tzdata | MERGED | R,C,T,D / C09,C22 | Windows Pi cmd/exe、tzdata、跨平台锁修复；保留当前 MMS，DSH 迁移只带验收场景。 |
| [#245](https://github.com/CtriXin/multi-model-switch/pull/245) | release: v4.21.0 Windows Preview fixes | CLOSED | H,D / C22,C24 | 因错误 release 基线会夹带 Bot 而关闭；Windows-only 发布另行完成，不重新合入旧集成分支。 |
| [#246](https://github.com/CtriXin/multi-model-switch/pull/246) | fix(windows): make CIM command discovery encoding-proof | MERGED | C,R,T,D / C10,C22 | CIM UTF-8/Base64 编码修复针对 Python 服务发现；保留 Windows 中文路径验收。 |
| [#247](https://github.com/CtriXin/multi-model-switch/pull/247) | fix(windows): tolerate slow Pi startup handshake | CLOSED | D,H / C22 | 无证据的延长握手超时候选被撤回；实际 pipe 问题由 #248 修复，不把 90 秒等待作为资产。 |
| [#248](https://github.com/CtriXin/multi-model-switch/pull/248) | fix(windows): preserve Pi RPC pipes through launcher | MERGED | R,C,T,D / C09,C22 | Windows launcher 保持 RPC pipes；Pi 继续使用时保留，DSH 原生进程不搬此补丁。 |
| [#249](https://github.com/CtriXin/multi-model-switch/pull/249) | fix(windows): use PowerShell when Pi bash is unavailable | CLOSED | R,C,H / C09,C22 | Windows shell 修复走独立 4.21 维护线发布，PR 因基线混 Bot 关闭；不是功能被放弃。 |
| [#250](https://github.com/CtriXin/multi-model-switch/pull/250) | fix(windows): support workspace folder picker | MERGED | D,T / C14,C22 | 原生 Windows 文件夹对话框后来被 #307 应用内树替代；旧 WinForms picker 可退役。 |
| [#251](https://github.com/CtriXin/multi-model-switch/pull/251) | fix(windows): keep folder picker responsive | MERGED | D,T / C14,C22 | 原生 picker 显示/超时补丁被 #307 替代；保留不可阻塞远程用户的要求。 |
| [#252](https://github.com/CtriXin/multi-model-switch/pull/252) | release: package v4.21.7 workspace picker fix | MERGED | H / C24 | 4.21.7 bundle 发布包装；不能当新文件夹能力。 |
| [#253](https://github.com/CtriXin/multi-model-switch/pull/253) | merge: 4.21.x Windows 维护线合回 dev，开启 5.0 线 | CLOSED | H,D / C21 | 当时违背稳定线/Bot 边界的集成候选已作废；不恢复历史分支方案。 |
| [#254](https://github.com/CtriXin/multi-model-switch/pull/254) | bot: 任务分支合入 dev-pre（会话隔离、几何头像、direct-first、T1c 工单） | MERGED | P,R,T / C16,C17,C21 | Bot owner 隔离、direct-first 与视觉调整；业务合同保留，Windows 修复按共享能力去重。 |
| [#255](https://github.com/CtriXin/multi-model-switch/pull/255) | dev: 撤销 Bot 合并，合入 4.21.x Windows 维护线（5.0 转 dev-pre） | CLOSED | H,D / C21 | 旧 Bot 回退候选因基线冲突被 #262 重做；无需再次合并。 |
| [#256](https://github.com/CtriXin/multi-model-switch/pull/256) | merge: sync dev with v4.21.14 and fix preview web launch | MERGED | C,R,H / C10,C22 | 同步 Windows 4.21.14 并修复 preview 启动；是整合和 installer 真实变更，按两部分处理。 |
| [#257](https://github.com/CtriXin/multi-model-switch/pull/257) | fix(installer): launch Pilot for preview channels | MERGED | C,T / C10 | Preview 安装后正确询问/启动 Pilot；移到自有发行脚本。 |
| [#258](https://github.com/CtriXin/multi-model-switch/pull/258) | feat(pi): bundle and inject the MMS /btw extension | MERGED | P,R,D / C06,C13 | Pi BTW 扩展继续供 Pi launcher 使用；DSH 若有等价旁问不搬 Pi 注入层，只迁隔离语义。 |
| [#259](https://github.com/CtriXin/multi-model-switch/pull/259) | feat(web): route /btw side questions through native Pi extension | MERGED | P,D,T / C13 | Pi BTW_EVENT 映射可随 Pi Web driver 退役；脱敏/取消/主队列隔离必须保留。 |
| [#260](https://github.com/CtriXin/multi-model-switch/pull/260) | fix(installer): skip obsolete preview setup hint when launching Web | MERGED | C,D / C10 | 安装提示清理；新发行包不用复制历史文案分支。 |
| [#261](https://github.com/CtriXin/multi-model-switch/pull/261) | [准备] release: 5.0.0 预览（Bot 工作台 + 4.21.x Windows 修复） | CLOSED | H,D / C24 | 旧 Preview 发布准备因冲突被 #263 替代，无独立能力。 |
| [#262](https://github.com/CtriXin/multi-model-switch/pull/262) | dev: 撤销 Bot 合并，dev 保持 4.21.x 稳定线（重做 #255） | MERGED | H,T / C16,C21 | 明确撤销 Bot 到稳定线的落入；是历史产品边界，不能用 ancestor 判定功能仍在。 |
| [#263](https://github.com/CtriXin/multi-model-switch/pull/263) | [准备] release: 5.0.0 预览（Bot 工作台） | MERGED | H / C24 | 5.0 Preview 版本与 bundle 准备；按 Bot 功能 PR 去重。 |
| [#264](https://github.com/CtriXin/multi-model-switch/pull/264) | release: 4.22.0 · /btw 旁问 | MERGED | H / C24 | 4.22 BTW 发布包装；其版本不一致问题由 #266 修复。 |
| [#265](https://github.com/CtriXin/multi-model-switch/pull/265) | feat(web): Bot 工作台收尾（T3d-ui / T2c / T1f）并整合 dev 4.22.0 与 /btw | MERGED | P,D,T / C16,C17 | 真实等待提问卡、计划状态和最多三问 Bot 引导保留；可用 DSH UI 插件补业务层。 |
| [#266](https://github.com/CtriXin/multi-model-switch/pull/266) | fix(release): align v4.22 runtime version metadata | MERGED | C,T / C11,C23 | runtime/package/static 版本一致性门禁重要；不迁移旧 tag，只迁发行验证。 |
| [#267](https://github.com/CtriXin/multi-model-switch/pull/267) | release: 5.0.0 Preview · Bot 工作台 | MERGED | H / C21,C24 | 稳定修复进 5.0 Preview 的整合记录；按底层能力去重。 |
| [#269](https://github.com/CtriXin/multi-model-switch/pull/269) | release: 5.0.1 · 修复设置滚动条遮挡与 Bot 交互/弹窗样式 | MERGED | P,D / C12,C16 | 实际含滚动条、停止/重试、Bot 弹窗改进；虽标题 release，不能忽略其 UI 改动。 |
| [#270](https://github.com/CtriXin/multi-model-switch/pull/270) | fix(bot): prevent premature compact and preserve Pilot port | MERGED | P,C,T,D / C10,C16 | compact 单位修复是 Pi 适配细节；端口保持是服务合同，Bot 短会话 no-op 行为继续验证。 |
| [#271](https://github.com/CtriXin/multi-model-switch/pull/271) | fix(installer): tell the user Pilot is opening on a preview install | MERGED | C,H / C10,C21 | installer 修复进入稳定线；与 #260 同源能力，不重复迁移。 |
| [#272](https://github.com/CtriXin/multi-model-switch/pull/272) | release: main becomes the 4.22.x stable line | MERGED | H / C21,C24 | main 变 4.22 stable 的整合节点；不等于所有祖先功能都留在 main。 |
| [#273](https://github.com/CtriXin/multi-model-switch/pull/273) | merge: carry the 4.22.x installer fix into the 5.x line | MERGED | C,H / C10,C21 | 稳定线 installer 修复转入 5.x；重复整合，非第二份功能。 |
| [#274](https://github.com/CtriXin/multi-model-switch/pull/274) | release: dev becomes the 5.x line | MERGED | H / C16,C21,C24 | dev 变 5.x，Bot 恢复到 dev；是分支边界变化，不是废弃整个 4.x。 |
| [#275](https://github.com/CtriXin/multi-model-switch/pull/275) | docs(bot-work): refresh T5 packets against 5.0.1 and add T6 channel-switch and backport packets | MERGED | H,T / C17,C18,C21 | 工作包与边界文档，保留需求/验收知识，不作为已实现新功能。 |
| [#276](https://github.com/CtriXin/multi-model-switch/pull/276) | docs(bot-work): T7a connection banner and T7b btw card fold memory packets | MERGED | H,T / C12,C13 | 连接横幅/BTW 折叠工作包；实现分别见 #282/#281。 |
| [#277](https://github.com/CtriXin/multi-model-switch/pull/277) | feat(web): backport runtime settings tab to 4.22 stable line (T6b) | MERGED | P,C,H / C15 | 运行环境设置回流 stable；与 #243 去重，保留真实能力和版本数据。 |
| [#278](https://github.com/CtriXin/multi-model-switch/pull/278) | T5a · 定时改成独立的 schedule 实体 + 真正的周期调度（后端，不要合） | MERGED | P,T / C18,C16 | 实际已整合 #302/#306，不是只剩后端；独立日程实体/时区/暂停恢复超出 DSH 会话提醒默认语义。 |
| [#279](https://github.com/CtriXin/multi-model-switch/pull/279) | feat(web): 4.x↔5.x 双向切换门禁 + 忽略未知 owner 的会话 (T6a) | MERGED | R,C,T / C08,C21 | 跨线 owner 过滤与门禁；DSH 不懂 MMS 的 Bot owner，迁移/兼容必须显式处理。 |
| [#280](https://github.com/CtriXin/multi-model-switch/pull/280) | docs(bot-work): T7c surface MMF blocked reasons and T7d keep the current window signed in | MERGED | H,T / C01,C07 | blocked reasons 和当前窗口认证工作包；实现见 #285/#283。 |
| [#281](https://github.com/CtriXin/multi-model-switch/pull/281) | feat(web): BTW 旁问卡片收起后持久化记忆与已处置语义 (T7b 返工完成) | MERGED | P,D,T / C13 | 旁问折叠/已处置状态是可选 UI 偏好；保留运行中不能伪装已处置的语义。 |
| [#282](https://github.com/CtriXin/multi-model-switch/pull/282) | feat(web): 连接横幅 3 次防抖与错误状态分流 (T7a) | MERGED | D,T / C12 | 连接与操作错误分流值得保留；DSH 若已满足无需迁移这份三次轮询计数器。 |
| [#283](https://github.com/CtriXin/multi-model-switch/pull/283) | fix(web): 打开手机访问不再把当前窗口踢掉（开关/换 token 给当前会话种 cookie） | MERGED | P,T / C07 | 开 LAN/换 token 必须让当前授权窗口持续可用；remote 插件需覆盖 cookie 交接。 |
| [#284](https://github.com/CtriXin/multi-model-switch/pull/284) | docs(bot-work): T7e blank turn after a mid-run steer | MERGED | H,T / C13 | steer 空白回合问题的工作包；不作为额外功能统计。 |
| [#285](https://github.com/CtriXin/multi-model-switch/pull/285) | fix(mms-web): 把 MMF 挡下来的真实原因说给用户听（T7c） | MERGED | P,R,T / C01 | 真实 blocked reasons 映射是模型配置控制面的一部分；插件不得把权限问题伪装成选模错误。 |
| [#286](https://github.com/CtriXin/multi-model-switch/pull/286) | fix(web): 修复中途引导及服务重启后回合空白、状态误判与作废消息不可重发问题 (T7e) | MERGED | D,T / C08,C13 | 回合中断/空结果/重发语义保留；DSH 原生 transcript 可替代，需在真实中断场景验证。 |
| [#288](https://github.com/CtriXin/multi-model-switch/pull/288) | feat(pilot): 收口聊天通道显示、设置三栏和 Bot 设定入口 | MERGED | P,D / C12,C16 | 用户明确要的通道表达、设置保存与 Bot 入口；可迁 UI 差异，不能因 #290 关闭连带丢掉。 |
| [#289](https://github.com/CtriXin/multi-model-switch/pull/289) | feat(web): 项目文件夹选择弹窗打开时输入框默认自动聚焦 | MERGED | D,T / C12,C14 | 文件夹弹窗焦点修复是通用 UX 验收，旧定时 focus 补丁不必复制。 |
| [#290](https://github.com/CtriXin/multi-model-switch/pull/290) | feat(pilot): 工作身份 — 一次切换模型、通道、effort 和人设 | CLOSED | P,H,D / C03,C12 | 旧工作身份形态按用户反馈关闭；模型/通道/effort 组合可在确认仍需时做 preset，不擅自恢复 persona。 |
| [#291](https://github.com/CtriXin/multi-model-switch/pull/291) | docs(bot-work): T7f · 删掉一条已排队的引导，它还是会送出去 | MERGED | H,T / C13 | 排队撤回问题工作包；实际修复见 #294。 |
| [#292](https://github.com/CtriXin/multi-model-switch/pull/292) | feat(tui): add Grok Build as a Pi-like launcher | MERGED | R,T / C09 | Grok TUI 隔离启动/协议兼容留 MMS；DSH 的 Web 不替代多 CLI launcher。 |
| [#293](https://github.com/CtriXin/multi-model-switch/pull/293) | docs(bot-work): T5b 追加 · T5a 验收之后的五条 | MERGED | H,T / C18 | 日程验收追加与 mutation 要求；不是独立实现。 |
| [#294](https://github.com/CtriXin/multi-model-switch/pull/294) | fix(web): 删掉已排队引导时如实反映撤回结果 | MERGED | D,T / C13 | 必须以 runtime 确认判断撤回是否成功；可由 DSH 原生队列替代，但要求不能丢。 |
| [#295](https://github.com/CtriXin/multi-model-switch/pull/295) | feat(bots): ship reviewed Fleet opinions with exact models and read-only workers | MERGED | P,T / C19,C16,C17 | 已恢复并 MERGED；保留用户要的 Fleet。关键修复在直接提交 5707bb07/789d45ba，最终 merge diff 不是全功能清单。 |
| [#296](https://github.com/CtriXin/multi-model-switch/pull/296) | release: v4.22.2 | MERGED | H / C24 | 4.22.2 共享修复发布；按原 PR 去重。 |
| [#297](https://github.com/CtriXin/multi-model-switch/pull/297) | docs: README 改成实际的两条发布线 | MERGED | H,C / C21,C24 | 两条发布线文档；新方案需重写发行约定，不能把历史分支文字当功能。 |
| [#298](https://github.com/CtriXin/multi-model-switch/pull/298) | release: v5.0.2 | MERGED | H / C24 | 5.0.2 发布；功能归 #288/#292。 |
| [#299](https://github.com/CtriXin/multi-model-switch/pull/299) | feat(pilot): 更新对话框里选通道，4.x 可以直接切到 5.x 预览 | MERGED | C,T / C11,C21 | 更新通道选择保留；从 5.x 降到 4.x 并未实现一键降级，后续 #327 澄清。 |
| [#300](https://github.com/CtriXin/multi-model-switch/pull/300) | docs: 更新通道开关已落地，订正 README 里「已知缺口」的说法 | MERGED | H,C / C21 | 渠道文档曾过度承诺可逆；以 #313/#327 后续真实边界为准。 |
| [#301](https://github.com/CtriXin/multi-model-switch/pull/301) | release: v4.22.3 | MERGED | H / C24 | 4.22.3 发布组合；不是四项功能的第二次实现。 |
| [#302](https://github.com/CtriXin/multi-model-switch/pull/302) | T5b · 定时选择器与管理列表（前端） | MERGED | P,T,H / C18 | 日程 UI 随 #278 整合；一套能力，保留时区/错过/暂停/完成等不同状态。 |
| [#303](https://github.com/CtriXin/multi-model-switch/pull/303) | fix(web): 侧栏区分未读已完成和已读待命 | MERGED | P,D,T / C12 | 未读完成与已读待命；保留语义和首次无历史回执边界，DSH 实际体验通过后可退役旧状态层。 |
| [#304](https://github.com/CtriXin/multi-model-switch/pull/304) | feat(web): 将思考强度从模型弹窗中拆分为独立常驻快捷选择器 | MERGED | P,D,T / C12 | 独立 effort 快捷入口是用户交互偏好；DSH 已有 effort，可替换 model slot 补差异，无 core fork 证据。 |
| [#306](https://github.com/CtriXin/multi-model-switch/pull/306) | T5c · 在对话里换 Bot 的模型，下一轮生效 | MERGED | P,T / C16,C12 | Bot 模型下一轮生效，歧义不得猜选；用 DSH session 选择能力实现业务状态，不能只改 UI 标签。 |
| [#307](https://github.com/CtriXin/multi-model-switch/pull/307) | fix(web): T8a in-app folder tree instead of the native picker | MERGED | P,D,T / C14 | 应用内目录树解决远程/native picker 错位；DSH 有 workspace 基础，需核对浏览主机目录的具体 UX。 |
| [#308](https://github.com/CtriXin/multi-model-switch/pull/308) | feat(web): add Grok as an optional Pilot harness | CLOSED | H,R / C09,C08 | Grok ACP 实验 CLOSED，遵守用户不合入的决定；只保留 adapter/能力协商经验，不把实验当现有能力。 |
| [#309](https://github.com/CtriXin/multi-model-switch/pull/309) | docs: T8c phase-1 — pytest 基线分类报告(65 红 → 10 根因,只诊断不改码) | MERGED | T,H / C23 | 测试基线诊断资产保留；旧失败数量不是当前健康结论。 |
| [#310](https://github.com/CtriXin/multi-model-switch/pull/310) | bot: T5d —— 计划步骤指定的模型真正生效 | MERGED | P,T / C16,C17 | 计划步骤指定模型必须真正执行于一次性会话且不污染主 Bot；DSH agentOptions 可承载，但生命周期要补验收。 |
| [#311](https://github.com/CtriXin/multi-model-switch/pull/311) | feat(web): 助手回复可专注阅读 | MERGED | P,D / C12,C13 | 专注阅读是轻量 UI 插件候选；先检查 DSH 现成阅读方式，不迁整份 transcript。 |
| [#312](https://github.com/CtriXin/multi-model-switch/pull/312) | T8c phase 2: pytest 基线修到 0 failed(2490 passed)+ openrouter diff 修复 + pi committee 协议声明(待批) | CLOSED | T,P,R,H / C01,C02,C23 | 较弱 registry 修复被 #313/#315 取代；环境清理有效断言已吸收，不能因 CLOSED 算丢失。 |
| [#313](https://github.com/CtriXin/multi-model-switch/pull/313) | release: v4.23.0 stable 目录浏览与可靠性修复 | MERGED | P,R,C,T / C01,C11,C14,C22,C23 | release 内含目录树、registry provenance、protocol、原子写/回滚等真修复；逐能力保留，不按发布包装丢弃。 |
| [#314](https://github.com/CtriXin/multi-model-switch/pull/314) | fix(bot): 优化聊天头部模型展示为横向胶囊并支持点击直达设定 | MERGED | P,D / C12,C16 | Bot 当前/下一轮模型展示和快捷设置入口；保留清晰状态，可按 DSH 插槽重做。 |
| [#315](https://github.com/CtriXin/multi-model-switch/pull/315) | release: v5.1.0 Preview Bot 整合与可靠性修复 | MERGED | P,C,R,T / C08,C11,C16,C18,C21,C23 | 大整合且修复 worker response、日程原子性、临时会话回收等；不能视为简单同步 main。 |
| [#316](https://github.com/CtriXin/multi-model-switch/pull/316) | fix(pilot): 5.x 也能切回 4.x 稳定版 | CLOSED | C,H,D / C11,C21 | 有效通道 UI 已由 #315 吸收；标题声称切回 4.x 不等于真正自动降级，不再合旧候选。 |
| [#317](https://github.com/CtriXin/multi-model-switch/pull/317) | fix(web): nest 出门也要用 under the remote-access switch | MERGED | P,C / C07 | 远程访问开关与公网域名关系保留；任务引导不等于自动部署隧道。 |
| [#318](https://github.com/CtriXin/multi-model-switch/pull/318) | fix(web): T8f retry Windows atomic replace instead of dropping the write | CLOSED | C,T,H / C22,C11 | Windows atomic replace 修复已进入 #313/#315；关闭是吸收，不是放弃数据可靠性。 |
| [#319](https://github.com/CtriXin/multi-model-switch/pull/319) | fix: an in-app update records what it installed in version.json (T8d) | CLOSED | C,T,H / C11 | 安装版本记录由 #313/#315 更完整方案替代；保留真实 tag/channel、旧 guardian 首跳与回滚边界。 |
| [#320](https://github.com/CtriXin/multi-model-switch/pull/320) | feat(web): double-click a sidebar session to rename it | MERGED | P,D / C12 | 双击重命名已 MERGED；是可选 UI 入口，CLI 会话不可改名的所有权边界保留。 |
| [#321](https://github.com/CtriXin/multi-model-switch/pull/321) | fix: binding a remote-access listener no longer does reverse DNS (T8e) | CLOSED | C,T,H / C07,C10 | reverse DNS 阻塞修复已被整合，后由 #325 扫全；不重复移植第二套 listener 类。 |
| [#322](https://github.com/CtriXin/multi-model-switch/pull/322) | feat(web): open version and updates from the sidebar v label | MERGED | P,C,D / C11,C15 | 侧栏版本直达更新是可选发行 UX，可用品牌/设置插件实现。 |
| [#323](https://github.com/CtriXin/multi-model-switch/pull/323) | fix(web): focus the rename field when the dialog opens | MERGED | D,T / C12 | Dialog 展示后聚焦并返回入口；后续 #295/#331 加固，迁移交互验收而非复制 timer 补丁。 |
| [#324](https://github.com/CtriXin/multi-model-switch/pull/324) | fix(web): 只读慢路由移出 mutation_lock（T8g） | MERGED | P,R,T,D / C01,C12 | 只读慢探测不得持全局写锁；MMS registry 留用时保留修复，DSH 重写时带并发验收。 |
| [#325](https://github.com/CtriXin/multi-model-switch/pull/325) | fix(web): 补完 T8e 反向 DNS 清扫,删掉一处假的权限检查 (v4.23.1) | MERGED | R,C,T,D / C09,C14 | 配置 Web DNS 与虚假权限检查修复；保留实际可访问性检查，旧 server 实现不搬 DSH。 |
| [#326](https://github.com/CtriXin/multi-model-switch/pull/326) | ci: 门禁在说谎 —— 删掉的红测试被算成修好了,前端从来没进过 CI | MERGED | T / C23 | 真实执行前端测试、区分删除/修复的门禁是重要资产；按 DSH plugin 测试入口改写。 |
| [#327](https://github.com/CtriXin/multi-model-switch/pull/327) | fix(update): 5.x 选 4.x 稳定版时不再被告知「已是最新」(T8h) | MERGED | C,T / C11,C21 | 如实解释跨线降级需 installer；留发行策略，不能把选择 channel 当完成迁移。 |
| [#328](https://github.com/CtriXin/multi-model-switch/pull/328) | fix(web): make update confirmation a full step | MERGED | P,C,D,T / C11,C12 | 更新确认独立步骤和按钮可见性保留；发行 UI 插件足够，无 core fork 证据。 |
| [#329](https://github.com/CtriXin/multi-model-switch/pull/329) | fix(web): keep mobile popovers and the composer on screen | MERGED | P,D,T / C07,C12 | 手机 popover/软键盘可见性是必要验收；目标 DSH 页面需实测，不能因有 Web 就视为已满足。 |
| [#330](https://github.com/CtriXin/multi-model-switch/pull/330) | feat: 中度使用后的低打扰飞书体验反馈 | OPEN | P,C / C25 | OPEN：低打扰自愿反馈可做 UI/偏好插件；不是迁移前置，不计已交付功能，不自动提交表单。 |
| [#331](https://github.com/CtriXin/multi-model-switch/pull/331) | fix(web): 交互修复与 v5.1.6 Preview | MERGED | P,D,T / C12,C16,C18,C19 | 模型/effort 异步成功才关闭、草稿/focus、Fleet/日程交互保留为验收；DSH UI 按差异补齐。 |
| [#332](https://github.com/CtriXin/multi-model-switch/pull/332) | fix(web): Stable 焦点与选择反馈修复 v4.23.3 | MERGED | D,T / C12,C14 | #331 共享焦点和保存反馈回流 stable；一套要求，不算另一套迁移功能。 |
| [#333](https://github.com/CtriXin/multi-model-switch/pull/333) | test(web): 文件夹树测试改为真执行,截断提示按层,390px 路径单行 (T8i A) | MERGED | P,T / C14,C23 | 真执行目录树测试且修复分层截断/390px 路径；行为测试保留，旧实现测试重写。 |
| [#334](https://github.com/CtriXin/multi-model-switch/pull/334) | test(web): 改名/等待控制/确认步骤/Popover 接线改真执行测试 (T8i B+C) | MERGED | T / C12,C13,C23 | 重命名/等待/确认/Popover 的实际接线测试保留为场景，不只迁纯函数断言。 |
| [#335](https://github.com/CtriXin/multi-model-switch/pull/335) | fix: 收尾共享门禁与文件夹真路径回归，发布 v4.23.4 | MERGED | R,C,P,T / C09,C14,C23 | 共享门禁和文件夹真实调用链收尾；不是仅版本发布，保留删除/skip/xfail 不算修复的规则。 |
| [#336](https://github.com/CtriXin/multi-model-switch/pull/336) | fix: 完成 T8i 实际接线回归与双线门禁，发布 v5.1.7 | MERGED | P,T / C12,C14,C16,C23 | 整组件实际事件接线与双线门禁收尾；保留验收知识，目标 plugin 新写调用链测试。 |
| [#337](https://github.com/CtriXin/multi-model-switch/pull/337) | docs: 给 AI 的项目交接文档,README 从 403 行降到 164 行 | OPEN | H,C / C24 | OPEN 文档整理；可继续作为项目知识，不是 DSH 已实现或待迁移功能。 |
| [#338](https://github.com/CtriXin/multi-model-switch/pull/338) | fix: 修复开启远程访问时的升级检查（v4.23.5） | MERGED | P,C,T / C07,C11 | LAN 开启时 guardian 认证与 proxy/redirect 边界；保留真实更新事务安全规则，属于发行集成。 |
| [#339](https://github.com/CtriXin/multi-model-switch/pull/339) | fix: 同步远程访问开启时的升级认证修复（v5.1.8） | MERGED | P,C,T,H / C07,C11 | #338 同类修复进入 dev；同一合同两线落地，不重复计算价值。 |
| [#340](https://github.com/CtriXin/multi-model-switch/pull/340) | fix(settings): 移除设置滚动容器顶部 padding 并为首项增加 margin-top | OPEN | D,T / C12 | OPEN 小样式候选；对现有 Pilot 可评估合入，DSH 新布局无需照搬该 CSS。 |
| [#341](https://github.com/CtriXin/multi-model-switch/pull/341) | feat(pilot): recover failed sessions with reviewed drafts (v5.1.9) | OPEN | P,T / C08 | OPEN 失败会话恢复候选；脱敏可审阅草稿/显式发送值得迁移，不计快照已合并能力。 |
| [#342](https://github.com/CtriXin/multi-model-switch/pull/342) | feat(pilot): backport failed-session recovery to Stable (v4.23.6) | OPEN | P,T,H / C08 | OPEN #341 Stable 回补候选；同一恢复能力，不能因两个 PR 算两项。 |
