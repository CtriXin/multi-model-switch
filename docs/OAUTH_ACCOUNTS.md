# MMS 多 OAuth 账号落地说明

## 当前已落地

- 新增 `accounts` / `account.defaults` 配置层，用来管理官方 CLI 的账号档案
- 首轮只覆盖 `claude` 和 `codex`
- 支持的命令：
  - `mms config account.list`
  - `mms config account.add`
  - `mms config account.edit <id>`
  - `mms config account.remove <id>`
  - `mms config account.status [id]`
  - `mms config account.login <id>`
  - `mms config account.default <cli> <id>`
- 启动时支持 `--account <id>` 临时切换账号档案
- 不托管 OAuth token 明文；账号隔离依赖每个账号独立的 `home_dir`

## 运行模型

- `provider` 继续表示网关/模型源，走 `base_url + api_key`
- `account` 表示官方账号档案，走本机官方 CLI 登录态
- `claude` / `codex` 启动时：
  - 指定了 `--account` 就优先走账号档案
  - 没指定但配置了默认账号时，走默认账号
  - 否则回退到原有模型源路径

## 账号隔离方式

- 每个账号档案都绑定一个独立 `home_dir`
- 启动官方 CLI 时会为当前进程注入：
  - `HOME=<home_dir>`
  - `XDG_CONFIG_HOME=<home_dir>/.config`
- 这样可以把不同 Plan / 不同官方登录态分开，不互相覆盖

## 最小试验

### 1. 新建账号档案

```bash
./mms config account.add claude
./mms config account.list
```

### 2. 进入官方登录

```bash
./mms config account.login <id>
./mms config account.status <id>
```

### 3. 设为默认账号

```bash
./mms config account.default claude <id>
./mms config account.default
```

### 4. 临时切换启动

```bash
./mms claude --account <id>
./mms codex --account <id>
./mms claude --provider default
```

## 四象限 Todo

| 象限 | 项目 | 状态 |
| --- | --- | --- |
| 高价值 / 低成本 | `account` 配置层、默认账号、`--account` 临时切换 | 已完成 |
| 高价值 / 高成本 | 启动前交互式账号选择、按额度/权重自动切换 | 待做 |
| 低价值 / 低成本 | 账号列表里显示更丰富的登录摘要、示例配置片段 | 待做 |
| 低价值 / 高成本 | 把 `qwen` / `kimi` 也抽进统一 OAuth 账号体系 | 暂不做 |

## 当前边界

- 还没做“启动前交互选账号”，首轮先用 `account.default` + `--account`
- 还没做自动配额切换
- 还没把 OAuth 登录流程做成图形/向导化，仍然依赖官方 CLI 自己的登录命令
- `qwen` / `kimi` 继续保持当前直达路径，不进入这个抽象层
