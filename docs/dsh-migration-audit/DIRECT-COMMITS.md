# 51 个未归入所收集 PR 引入范围的提交

包括直接提交与内部 merge，均属于 702 个唯一 commit，不能再与总数相加。不是全部都未经过审查，也不代表只有这 51 个 commit 含独立功能。

| Commit | 标题 | 分类 / 能力 | 判断 |
|---|---|---|---|
| [16092a43](https://github.com/CtriXin/multi-model-switch/commit/16092a43611af338b1fbf9eae403c2d478e08d51) | release: v5.1.5 Preview | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [af14eae5](https://github.com/CtriXin/multi-model-switch/commit/af14eae5ee85e454faaa77161fbc4d052483969c) | release: v5.1.4 Preview | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [97b562ca](https://github.com/CtriXin/multi-model-switch/commit/97b562cad2ea9b4fae140799a517e658df79a8d7) | release: v5.1.3 Preview | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [7dc64bb1](https://github.com/CtriXin/multi-model-switch/commit/7dc64bb1c4b588b291573c5cd3d97163b7497028) | release: prepare Fleet repair for v5.1.2 Preview | C,T,H / C19,C23,C24 | 5.1.2 版本准备同时有 Fleet render 测试和说明修复；不是纯 stamp。 |
| [789d45ba](https://github.com/CtriXin/multi-model-switch/commit/789d45ba367e09b2871e0e3b7bb89ac27e9d3b16) | fix(bot): close Fleet lifecycle and approval gaps | P,T / C16,C17,C18,C19 | Fleet 生命周期/计划批准/定时意图与只读边界修复，属于 #295 能力；不能只读最终 PR diff。 |
| [5707bb07](https://github.com/CtriXin/multi-model-switch/commit/5707bb073826f8eff8f7d77f7ba60c0e449b17be) | fix(bot): enforce exact Fleet choices and read-only worker tools | P,T / C02,C16,C19 | 精确模型失败停止、只读工具与 session 限制；作为 Fleet 插件的硬验收合同保留。 |
| [58fdbaab](https://github.com/CtriXin/multi-model-switch/commit/58fdbaabb305becd45a54a824ceefd1068781058) | merge: bring Fleet candidate onto current dev for repair | P,T,H / C16,C19,C21 | Fleet 候选先与当前 dev 合流再修复；后续 5707bb07/789d45ba 才构成最终边界。 |
| [ce7054b3](https://github.com/CtriXin/multi-model-switch/commit/ce7054b35941642056f8de6fb8ff0f403b82da05) | merge(main): carry atomic persistence and replay fixes into Preview | P,C,T,H / C11,C16,C18,C22 | main 原子持久化/回放修复向 Preview 合流，保留 Bot 合同；按来源能力去重。 |
| [faeb3676](https://github.com/CtriXin/multi-model-switch/commit/faeb367677cda97f9da02cbf54911b77d04e721c) | fix(bot): keep mobile model chip readable beside header controls | P,D / C12,C16 | Bot 模型 chip 手机布局；按目标 DSH 页面实测决定是否需 UI 插件。 |
| [6017983b](https://github.com/CtriXin/multi-model-switch/commit/6017983bc61a03308761b5a50589a0a31ea417ff) | merge(main): preserve randomized test isolation on Preview | T,H / C23 | 随机顺序测试隔离同步至 Preview；无独立新功能。 |
| [8b647aef](https://github.com/CtriXin/multi-model-switch/commit/8b647aef6c322e18001d213fb301e0835fcaf23d) | merge(main): align CI with the installer runtime dependencies | C,T,H / C10,C23 | CI 运行依赖同步；无独立新功能。 |
| [45b66ed9](https://github.com/CtriXin/multi-model-switch/commit/45b66ed962598f406026e8b7efeaf8bc49353bb2) | merge(main): carry nonblocking listener bind and CI evidence to Preview | C,T,H / C07,C10,C23 | 无阻塞 listener 与 CI 证据同步；同源修复不重复计价值。 |
| [f8241530](https://github.com/CtriXin/multi-model-switch/commit/f824153020da1d43ebedf373087aa654d51c6b13) | merge(main): integrate verified stable fixes into 5.1 Preview | P,R,C,T,H / C01,C11,C21,C23 | 稳定修复进入 5.1；包含更新元数据与类型/数据边界，非单纯版本标签。 |
| [63ebca48](https://github.com/CtriXin/multi-model-switch/commit/63ebca487c29e76e003a854969a42b3266be4d76) | fix(bot): return complete worker responses after security header integration | P,T / C07,C16 | 合流安全响应头后 worker 成功响应中断的修复；保留真实 HTTP 完整性验收，旧 handler 不搬。 |
| [f25cfa34](https://github.com/CtriXin/multi-model-switch/commit/f25cfa340989466340d1965cb73679d30349836f) | release: prepare v5.1.0 preview integration milestone | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [fc45824a](https://github.com/CtriXin/multi-model-switch/commit/fc45824a3166a7040043d1580a409c8f8d1b7bdb) | fix: forward verified stable repairs into dev integration | P,C,T,H / C12,C14,C23 | 目录树、阅读与 stable 修复前向合流；按实际文件列出范围，未重演 merge。 |
| [14bce1f0](https://github.com/CtriXin/multi-model-switch/commit/14bce1f08a04798a14207e3aa31ed358bccaf759) | fix(bot): preserve schedule state and retire temporary sessions safely | P,T / C16,C18 | 日程/任务 dispatch 持久化、DST、临时 session 回收与模型/effort修复；保留语义，复用新 runtime。 |
| [b03995c8](https://github.com/CtriXin/multi-model-switch/commit/b03995c8c68ffb2e875987e73d74638128eeafb5) | fix(web): bring stable Pilot fixes into dev while preserving Bot contracts | P,C,T,H / C07,C12,C13,C16,C21 | stable Pilot 修复前向合流，同时保留 Bot owner/接口；不是 main 全覆盖 dev。 |
| [9c3678d2](https://github.com/CtriXin/multi-model-switch/commit/9c3678d2a8e529bad704aff838067c7667812e68) | release: v5.0.6 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [d22e0e5f](https://github.com/CtriXin/multi-model-switch/commit/d22e0e5f8250bef6085805c9bd39c0e8d692f2df) | docs: #311 rework packet — the reader works, its wiring is untested | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [b7bf90ca](https://github.com/CtriXin/multi-model-switch/commit/b7bf90ca91a14f63178031af50416f3fa9188513) | release: v5.0.5 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [9110141d](https://github.com/CtriXin/multi-model-switch/commit/9110141d8ee317add104437501f03cbd3a6b8556) | docs: changelog index, task board, two rework packets, and the missing 4.22.x notes | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [4db68f21](https://github.com/CtriXin/multi-model-switch/commit/4db68f21d9a0c9425953107f7004c8cce383f301) | release: v5.0.4 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [759090b9](https://github.com/CtriXin/multi-model-switch/commit/759090b9e58c312d0d1b3a9716192a99cc78c6a1) | release: v5.0.3 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [1b710ef0](https://github.com/CtriXin/multi-model-switch/commit/1b710ef089ca9876b8fdfbd08ad6d9f077ffebd0) | docs: T8c packet — classify the 63 tests that are red on every branch | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [5895f367](https://github.com/CtriXin/multi-model-switch/commit/5895f36738e347470ae721b500ba79939b7b0a36) | docs(web): T8b packet — reopen work identities without the persona | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [0eb5ca63](https://github.com/CtriXin/multi-model-switch/commit/0eb5ca635d6c2db75df5a4604e192f716d99497a) | docs(web): T8a packet — replace the native folder dialog with an in-app tree | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [4d432553](https://github.com/CtriXin/multi-model-switch/commit/4d4325539ce9d0412cc20ae22071c5363325354f) | docs(bot): T5d packet — a planned step's model never actually applies | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [9602daa7](https://github.com/CtriXin/multi-model-switch/commit/9602daa7ffb0dff3bbbcd157edcc99d70dda1cff) | fix(bots): 悬停卡片留底边距，拆开挤在一行的结论 | P,D / C12,C19 | Fleet 悬停卡片布局；可选 UI 差异，非 core fork 理由。 |
| [0fd3c418](https://github.com/CtriXin/multi-model-switch/commit/0fd3c4189e40fe497865e73f3ea4ef4cab14ba6a) | fix(bots): 文案改成人口语，拿掉芯片钉住这类词 | P,D / C19 | Fleet 通俗文案与输出组织；保留用户语言，替换旧 UI 实现。 |
| [bf056b5e](https://github.com/CtriXin/multi-model-switch/commit/bf056b5e20048712015bbf2de4c945a72a31db97) | feat(bots): 入口改成寻求场外帮助，悬停只给短摘 | P,D / C19 | 寻求场外帮助入口及短摘；作为 Fleet plugin 产品交互保留。 |
| [5d8a5a40](https://github.com/CtriXin/multi-model-switch/commit/5d8a5a40186d1382b0bb46616552df7821189b7a) | feat(bots): 听意见改成判断+分歧，各家做成悬停芯片 | P,D / C19 | 判断/分歧与各家意见芯片；与 Fleet 功能合计一次。 |
| [b8765a7b](https://github.com/CtriXin/multi-model-switch/commit/b8765a7bc268acf60e18f74323e4a1a73e1d9844) | feat(bots): 多方听意见默认只摊开分歧和风险 | P,D / C19 | 默认强调分歧与风险；保留汇总语义，不重复搬整套计划渲染。 |
| [67d3e0ae](https://github.com/CtriXin/multi-model-switch/commit/67d3e0aed722f8e16979c3511a7d46cb3fb0e5c3) | fix(bots): 家族名单收成 mms_core，第一次扇出给可见提示 | P,R,T / C02,C19 | 模型家族真值集中和首次扇出反馈；插件消费 registry，不另维护名单。 |
| [f7de6ae3](https://github.com/CtriXin/multi-model-switch/commit/f7de6ae367527bf4af4dd1a183617a3e085acc04) | feat(bots): 同一 Bot 上多方听意见，发送即听 | P,T / C19 | 同一 Bot 多模型意见初始实现；以 #295 修复后的精确模型/只读边界为准。 |
| [79667bd5](https://github.com/CtriXin/multi-model-switch/commit/79667bd58cd7343f2ec6d79b36e3a06c9252b564) | release: v4.23.2 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [9607f7b5](https://github.com/CtriXin/multi-model-switch/commit/9607f7b511f53791fe41e904eb5d55729a8c6ce5) | test: remove hidden Rich and saved-preference ordering assumptions | T / C23 | 隔离 Rich/保存偏好排序假设；迁移测试方法，避免依赖开发机环境。 |
| [4df90d69](https://github.com/CtriXin/multi-model-switch/commit/4df90d69a8691f798fec40ca746314293fe4efea) | ci: provision installer dependencies for the full regression suite | C,T / C10,C23 | CI 安装运行依赖；新发行沿用可复现依赖要求，不复制过期版本。 |
| [44b1e946](https://github.com/CtriXin/multi-model-switch/commit/44b1e946982013519043bb6a11f1143dcab99d05) | fix(web): avoid reverse DNS while binding Pilot listeners | C,T / C07,C10 | 监听器禁止反向 DNS 阻塞；DSH 集成保留慢网络负向验收。 |
| [d46e2c9b](https://github.com/CtriXin/multi-model-switch/commit/d46e2c9b244f69b5a18ca42f3e6f9958653b5f80) | merge(main): include current update repair specification | H,T / C11,C23 | 更新修复规格合流；文档不作为已验证产品行为。 |
| [69bc57ba](https://github.com/CtriXin/multi-model-switch/commit/69bc57ba18e4e2a023e73edefac01c33a2815ab6) | docs: T8e packet — reverse DNS freezes the whole Pilot for 30s on the LAN switch | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [e34f14d1](https://github.com/CtriXin/multi-model-switch/commit/e34f14d1a6e6ea9a6471dff0d9424cab4fe9db2a) | docs: T8d packet — an in-app update never records what it installed | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [64f96e63](https://github.com/CtriXin/multi-model-switch/commit/64f96e635de2565b3459d14f6f2d499394002d17) | fix(updates): record verified installs and preserve rollback and state identity | R,C,T / C09,C11 | 真实安装版本/channel、回滚和实例状态身份加固；#319 较弱候选无需重合。 |
| [33f3d475](https://github.com/CtriXin/multi-model-switch/commit/33f3d47547e842ba675b08e610480e24e39e95f9) | release: prepare v4.23.0 stable integration milestone | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [7e3d5461](https://github.com/CtriXin/multi-model-switch/commit/7e3d54613cbeb314db514d48b30b3dcdda8858f2) | fix(registry): restore catalog drift and preserve committee protocols | P,R,T / C01,C02,C23 | 多模型 reference provenance 与 committee protocol 保留；#312 已被更完整实现取代。 |
| [13d05ab8](https://github.com/CtriXin/multi-model-switch/commit/13d05ab815003905d0a7f2c675adc6ef81408b4a) | test(web): verify schedule entities across release channel switches | C,T / C18,C21 | 跨线 gate 适配独立 schedule 实体；保留兼容案例，不把执行失败当无关。 |
| [96349100](https://github.com/CtriXin/multi-model-switch/commit/9634910007f1ffa25618d2babc465ec72dfe99a7) | docs: mark #307 rework items 7 and 8 as already done | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [d72bfa6c](https://github.com/CtriXin/multi-model-switch/commit/d72bfa6cf9821c3272240cee838a05a92e716b32) | docs: #307 rework packet — and two corrections to the packet it answers | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [933b6ade](https://github.com/CtriXin/multi-model-switch/commit/933b6ade1101b884fc8ee345ec64081a1060fd53) | docs: T8c phase 2 — three rulings and a rule against lazy fixes | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [a0f77398](https://github.com/CtriXin/multi-model-switch/commit/a0f773981e711b149c9a0db25cc6e5d4b8c9ae55) | docs: add the changelog index to the stable line | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
| [e6f3a575](https://github.com/CtriXin/multi-model-switch/commit/e6f3a575857acdef1295945d9f659d62a604a117) | release: v4.22.4 | H / C24 | 历史发布/工作包记录；不作为独立运行能力迁移，保留与后续实现的追溯。 |
