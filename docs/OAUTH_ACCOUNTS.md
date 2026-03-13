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
- 已支持统一接入向导：
  - `mms config connect`
  - 主界面按 `O`
  - 可继续进入“管理现有通道”

## 运行模型

- `provider` 继续表示网关/模型源，走 `base_url + api_key`
- `account` 表示官方账号档案，走本机官方 CLI 登录态
- 对用户来说，两者都会进入同一个“执行通道”选择层
- `claude` / `codex` 启动时：
  - 指定了 `--account` 就优先走账号档案
  - 没指定但配置了默认账号时，走默认账号
  - 否则回退到原有模型源路径
- `OAuth account` 路径当前不复用 provider 的 `/v1/models` 列表
- `codex --account <id>` / `claude --account <id>` 默认直接进入官方 CLI，模型选择交给官方 CLI 自己处理
- 来源选择会按“当前已选模型”动态过滤，不再只看当前 CLI
- 如果某个模型同时命中多个来源，MMS 的 TUI 会在选完模型后同屏展开执行通道列表

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

也可以直接：

```bash
./mms config connect
```

然后选：

- `添加官方通道`
- 或 `管理现有通道`

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

### 5. 交互式选择执行通道

当某个 CLI 同时存在：

- 一个或多个账号档案
- 以及一个可用模型源

直接执行：

```bash
./mms codex
```

或

```bash
./mms claude
```

会在当前 TUI 里展开“执行通道”列表，让你决定这次走：

- 某个账号档案
- 还是模型源

如果你先选中了具体模型，例如 `gpt-5.4`，这里不会再把所有来源一股脑列出来，而是只显示真正能承载 `gpt-5.4` 的来源。

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
- 已经有统一接入向导，但真正的登录动作仍然调用官方 CLI 自己的登录命令
- OAuth 账号当前只做两类检查：
  - 登录态是否可用
  - 官方 CLI 是否能正常启动
- 当前不做 provider 式 model list；后续如果某个官方 CLI 能稳定枚举模型，再单独加
- 当前不支持统一显示官方真实用量 / 剩余额度；管理页和 `mms config stats` 展示的是本地启动统计
- `qwen` / `kimi` 继续保持当前直达路径，不进入这个抽象层
