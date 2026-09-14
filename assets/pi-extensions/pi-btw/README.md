# `assets/pi-extensions/pi-btw` — 内建 Pi /btw 扩展（构建产物，不要手改）

`index.ts` 是 `@ctrixin/pi-btw`（`@narumitw/pi-btw` 的 fork）用 esbuild 打成的**单文件**，
MMS 在启动每一个自己拉起的 Pi 时通过 `--extension` 注入它，让「旁问」不打断主任务。
Pilot 与终端 `mms`/`mmf` 走同一个解析函数
（`mms_pi_support.pi_btw_extension_path()`），规则见 `docs/MMS_USER_PREFERENCES.md` 的 `pi_btw`。

## 这个目录里有什么

| 文件 | 说明 |
| --- | --- |
| `index.ts` | esbuild 产物（内容是 JS，扩展名 `.ts` 是 Pi 的 Jiti 加载器要求）。**不要编辑**。 |
| `VERSION` | 被打包的 `@ctrixin/pi-btw` 版本。 |
| `SOURCE.json` | 来源 ref/commit、esbuild 与 pi 版本、`sha256`、external peers、被内联进来的依赖、以及只有源码里才有的可选依赖清单。 |
| `LICENSE` / `NOTICE` | 上游 MIT 许可与 fork 出处，随产物一起分发。 |
| `THIRD-PARTY-NOTICES.md` | 被打进 `index.ts` 的第三方包及其许可证行。 |

产物只 import Pi 自己带的包（`@earendil-works/*`、`typebox`）和 `node:*`：Pi 会为扩展解析这些
裸标识符。其他依赖必须内联，因为这个目录没有 `node_modules`。

## 刷新

```bash
git -C <pi-btw repo> worktree add --detach /private/tmp/pi-btw-vendor <tag>
ln -s <pi-btw repo>/node_modules /private/tmp/pi-btw-vendor/node_modules
python3 scripts/sync_pi_btw.py --source /private/tmp/pi-btw-vendor --ref <tag> --verify
git -C <pi-btw repo> worktree remove /private/tmp/pi-btw-vendor
```

`--verify` 会让本机安装的 `pi` 真的加载产物并检查 `btw`、`btw:cancel` 是否都注册上了。
日常校验（不写文件）：

```bash
python3 scripts/sync_pi_btw.py --check
```

launcher 侧是 fail-closed 的：缺 `SOURCE.json`、`sha256` 不匹配或体积异常时**不注入**并在启动日志
写一行原因；`/btw` 缺席不会让启动失败。
