# v4.22.0 · `/btw` 旁问

## 升级须知

在 `v4.21.14` 之上新增一个功能：旁问 `/btw`。终端 `mms pi` 和 Pilot 都可用。其余行为不变，Windows 仍是 Native Preview，配置根仍是 `~/.config/mms-next`，无需迁移。不想要这个功能可以关掉，见下文「关掉它」。

## 旁问 `/btw`

主任务跑到一半想问点别的，以前只能打断它。现在在 Pi 会话里直接发 `/btw <问题>`：

- **主任务不中断**，编辑器也不锁，继续该干嘛干嘛。
- 旁问能看到主任务的上下文（所以可以问「刚才那个报错是什么意思」），**但旁问的问答不会进入主任务的上下文**，不污染后续推理。
- 答案流式出现在编辑器上方的卡片里，答完留在原地；按 `Esc` 收起。会话流里同时留下一条折叠记录，带答案预览和 `/btw:open <id> 查看全文`。
- 记录写进 session 文件，`pi -r` 续接后 `/btw:history` 仍可翻。

配套命令：`/btw`（无参数开全屏工作区）、`/btw:thread`、`/btw:cancel`、`/btw:history`、`/btw:open`、`/btw:bring`、`/btw:follow`。

Pilot 侧的旁问改走同一个原生扩展，答题者和它看到的上下文范围会显示在卡片上；扩展不可用时回落到原有路径，并在返回里注明原因。

## 与已装的 pi-btw 共存

如果你自己已经装了 `pi-btw`，MMS 不重复注入，避免命令被改名成 `/btw:1`：

- 本次会话真正会加载的配置里已有 `pi-btw`（项目 `.pi`，或 `PI_CODING_AGENT_DIR` 指向的那棵树）→ **不注入**，打印一行说明。
- 只有你的全局 `~/.pi/agent` 里装了 → **照常注入**，因为 MMS 给每个会话独立的 `PI_CODING_AGENT_DIR`，那份根本不会被加载；同样打印一行说明。

## 关掉它

`~/.config/mms/preferences.toml`：

```toml
pi_btw = false                # 全局关闭

[launch.cli.pi]
pi_btw = false                # 只关 Pi
```

## 内建扩展来源

`assets/pi-extensions/pi-btw/` 是 `@ctrixin-dev/pi-btw` `0.59.0-fork.4` 的构建产物，由 `scripts/sync_pi_btw.py` 从 tag `v0.59.0-fork.4` vendoring 而来，`SOURCE.json` 记录 commit 与 sha256。它是 `@narumitw/pi-btw`（MIT）的 fork，LICENSE、NOTICE 与第三方声明随包保留。

## 静态包

`mms_web_static/build.json` 随版本更新到 `4.22.0`。
