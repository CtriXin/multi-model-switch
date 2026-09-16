# v4.12.0 · 终端会话接入、配置自动收拢与 Pilot 体验收口

- **终端会话进 Pilot**（#149、#159）：用 `mms` / `mmf` 在终端里开始的 Pi 会话会以只读方式出现在 Pilot 列表里；选择「接入并继续」会把 transcript 复制到新的 runtime 后继续对话，终端里的原文件一个字节不动。可在设置「使用」里关闭列表显示。
- **老机器自动收拢配置**（#163）：已在 Pilot 里配过通道、但共享根 `~/.config/mms-next` 还是空的机器，打开 Pilot 时会校验后把配置接进共享根，终端不再需要手动 export；安装脚本遇到正在运行的 Pilot server 会请它优雅退出、继续安装并重新打开，`--keep-running-pilot` 保留暂停行为。
- **k3 上下文窗口尊重用户策略**（#168）：Web 模型页写入的 `k3` context 覆盖不再被 256K 保守默认吞掉；未设策略时仍保持 256K。
- **Pilot 体验收口**（#155）：本地文件引用预览与服务诊断；Weber 成为唯一网页 skill，web-access / agent-browser 作为其内置后端；可选合并本机 `~/.claude`、`~/.codex`、`~/.config/opencode` skills（默认关闭，只读）；设置拆成外观 / 使用两个标签；`.pilot/attachments` 30 天无引用的导入副本自动清理；通道支持新建、删除（带确认与审计）；新手引导按安装持久化；模型下拉不再被矮屏裁掉。token-saver 与内建 Caveman 包随本版下线，已有 preference 不生效但不会报错。
- **LAN 写操作**（#169）：`--listen all` 模式下浏览器 `Origin` 按与 `Host` 相同的规则校验，多网卡地址上的写请求不再被 403。

本版本不主动终止正在运行的会话或任务；配置收拢是复制不是移动，原目录保留作为回退。版本源、Web package metadata 和静态 Web bundle 同步为 `4.12.0`。
