# v4.19.2 · 安全升级提示

本版把旧安装和跨配置根升级的边界说清楚，避免用户在没有准备好时点一键更新。

<!-- mms-upgrade-policy: {"manualBelow":"4.13.0","reason":"4.13.0 起配置根统一为 ~/.config/mms-next；4.12 及更早版本请先运行安装器完成迁移。"} -->

## 更新

- 安装器检测到旧 `~/.config/mms` 里有真实 MMS 配置文件时会提醒用户。它不会自动卸载、删除、移动或迁移整个旧目录，因为目录里可能仍有 gateway/session 运行数据。
- Pilot 更新中心会显示结构化的手动升级说明，并提供可复制的安装命令。跨越已声明的迁移边界时不会显示一键更新按钮。
- 如果 Pilot 正在使用上一次更新留下的暂存副本，更新中心也会要求先重新运行安装器，让命令行和 Web 回到同一份安装。

## 升级须知

- **4.12.0 及更早版本**：本版要求先等待执行中、待确认和排队任务结束，再停止旧 Pilot，执行下面的命令并重新打开 Pilot：

  ```bash
  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
  ```

- 这不是清空操作。安装器不会删除旧 `~/.config/mms`；确认新 Pilot 和通道正常后，再由用户决定是否处理旧目录。不要在 gateway/session 仍运行时移动或删除它。
- 以前只在旧终端配置过的通道，升级后请在 Pilot 设置中重新连接并确认模型可用。

## 验证

- 更新服务、安装器 dry-run、手动迁移 policy、暂存副本和 coordinator guard 回归通过。
- Pilot bundle 已按 `4.19.2` 重建。
