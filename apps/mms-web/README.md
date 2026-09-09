# MMS Web

MMS 的本地 Web 客户端。网页选择模型与服务通道后，通过原 MMS launcher 创建真实 Pi RPC 会话。原 mms/mmf 命令、路由与默认行为未改。

## 可用范围

- 直接选择 MMS 已有模型和通道；不需要预先保存 preset。
- 选择或添加本机工作文件夹，新建真实任务、连续对话、查看流式内容与工具过程。
- 停止当前执行，刷新恢复页面，服务重启后使用 Pi 原生 session 文件继续上下文。
- 处理 Pi extension 的 confirm、select、input、editor 请求。
- 成功 write/edit 产生的工作区内文本文件可在成果栏查看和下载。上限 1 MiB；隐藏文件、越界路径与 symlink 越界不可读取。
- 会话搜索、模型星标、浅色/深色、窄屏布局。

当前真实执行工具是 Pi，可使用 MMS 提供的不同模型。Claude Code/Codex 等原生 harness 的完整接入、Glint 既有会话同步、附件上传、可视化 diff/网页产物预览和发布安装包属于后续迭代。不能把模型品牌与 harness 接入混为一谈。

## 运行

开发依赖：Python 3.11+ 与 MMS 的现有 Python dependencies，Node.js，以及已安装的 Pi。Web 会优先使用 Pi 全局安装旁的兼容 Node，不改全局 PATH。

从 repo 根构建一次：

    npm --prefix apps/mms-web ci --workspaces=false
    npm --prefix apps/mms-web run build --workspaces=false

启动独立客户端：

    ./mms-web --open

macOS 也可双击 repo 中的 MMS Web.command。当前文件是开发入口，不是已经完成签名/打包的发行安装器。

默认 Web 状态位于 ~/.local/share/mms-web（尊重 XDG_DATA_HOME）。首次使用在网页内填写服务类型、地址、Key 与模型；保存的是该目录内的独立 MMS config。显式读取现有 mmf：

    ./mms-web --config-root ~/.config/mms-next --open

现有真实 MMS 配置只读。每次启动在 Web 的 runtimes 目录生成私有运行副本，MMS 在副本内创建 gateway/session/config 状态。不会把真实 HOME OAuth 作为恢复来源。Pi 保留 MMS 原有 soft HOME 行为，属于配置与会话隔离，不是 OS 文件系统沙箱。

手工新增配置的能力信息保持 unknown；私有 runtime bundle 使用 MMS 的导出校验器以及保守能力默认值，不虚构已验证的 vision/context/tool 能力。

## 数据与退出

只绑定 127.0.0.1:8765，同源 HTTP、Host/Origin 校验、POST CSRF token。不要直接发布到公网。配置中的 Key 不返回浏览器，运行凭据与会话记录使用私有文件。

退出本地服务会关闭其管理的 Pi 进程，重新启动后可继续有原生 history 的会话。停止执行按钮只中断本轮并清空队列，保留会话。

?preview=1 仅用于明确标记的 UI 样例；正常入口绝不会 fallback 到样例。

## 验证与开发

    python3 -m pytest -q tests/test_mms_web_*.py
    npm --prefix apps/mms-web run build --workspaces=false

集成测试包含本地 HTTP provider + 实际安装的 Pi + 原 MMS launcher + 原生 history 恢复；未安装兼容 Pi 时该项显式 skip。它不访问真实 provider，也不修改 host 配置。另有独立真实 provider 的网页验收记录，不能用 fixture 结果替代。

API 合同见 docs/mms-web/API.md；PRODUCT.md / DESIGN.md 是前台设计上下文。集成后整个 Web 目录由主导维护，保留外部 agent 的返还记录作为来源。源码保持在任务 worktree，尚未提交、合并或发布。
