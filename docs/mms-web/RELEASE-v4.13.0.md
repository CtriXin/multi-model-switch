# v4.13.0 · 只有一个配置根

- **所有入口只读 `~/.config/mms-next`**（#183）：`mms`、`mmf`、`mmg` 和 Pilot 共用同一个根。在 Pilot 里保存的通道，终端下一次启动就能看到；同样的通道在任何电脑上都能拉取模型。
- **旧根 `~/.config/mms` 退出配置来源**：不再自动读取、导入或回退；shell 里残留的 `MMS_CONFIG_ROOT=~/.config/mms` 或 `MMS_CONFIG_ROOT_MODE=stable` 会被忽略并指回 `mms-next`。空根时终端提示 `mms web` 去 Pilot 完成配置。旧目录本身保留不动，其中的 gateway 会话目录继续作为运行时状态使用。
- **`mmd` / `mmm` 退休**：本机命令矩阵只剩 `mms` / `mmf` / `mmg`；`scripts/link_local_channel_commands.sh` 会删除它写过的这两个包装器。
- **安装不再多起一个 Pilot**：安装脚本会请任何占用默认端口的 Pilot 退出（包括页面里自更新过的、或另一份安装起的），装完重新打开；识别已有实例的方式与服务端一致，不再在 8766 起第二个实例造成 403。

升级后请在每台电脑重跑一次安装命令，然后打开 Pilot；旧电脑上如果之前只在终端配过通道，需要在 Pilot 里重新添加一次。版本源、Web package metadata 和静态 Web bundle 同步为 `4.13.0`。
