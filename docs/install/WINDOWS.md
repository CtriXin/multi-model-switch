# Windows Native Preview：从刚装好的系统开始

Windows 目前是 **Native Preview**。下面按一台刚装好 Windows 11、还没有任何开发环境的电脑来写，不需要你先懂 Python、Node 或 Git。

macOS / Linux 的安装见 [README](../../README.md)，一条 `curl` 命令就够了，不用看这篇。

## 1. 先看系统有什么

开始菜单搜索 **Windows PowerShell**，打开**普通窗口**（不要用管理员权限）。逐条粘贴：

```powershell
winget --version
python --version
node --version
npm --version
```

## 2. 补上缺的运行时

`python` 或 `node` 提示找不到就装对应的：

```powershell
winget install --id Python.Python.3.12 -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

装完**关掉所有 PowerShell 窗口，再开一个新的**，新的 `PATH` 才会生效。然后重新执行上面那三条 `--version` 确认。

没有 `winget` 的话，从 [python.org](https://www.python.org/downloads/windows/) 和 [nodejs.org](https://nodejs.org/en/download) 下载安装，安装向导里要勾选"加入 PATH"。

## 3. 装 Pi

Pi 是 MMS 调用的本机 coding agent，要单独装到 Node 的 global package。PowerShell 里用 `npm.cmd` 可以避开执行策略对 `npm.ps1` 的拦截：

```powershell
npm.cmd install --global @earendil-works/pi-coding-agent
pi.cmd --version
```

`pi.cmd` 找不到就关掉所有 PowerShell 再开一个新窗口；还是找不到，执行 `npm.cmd prefix --global`，把它显示的**那个目录本身**加进用户 `PATH`（Windows 通常不是 `bin` 子目录），再开新窗口。

> 安装器只检查 Pi 有没有在 `PATH` 里，**不会替你装 Pi**。

## 4. 装 MMS

下面的命令会下载官方安装脚本，它会准备 MMS 自己的 Python venv 和 Pilot，不会导入或覆盖你已有的 config / session。把 `v4.21.14` 换成你要装的版本：

```powershell
$script = Join-Path $env:TEMP 'mms-install-v4.21.14.ps1'

Invoke-WebRequest -UseBasicParsing `
  -Uri 'https://raw.githubusercontent.com/CtriXin/multi-model-switch/v4.21.14/packages/mms-install/bin/install.ps1' `
  -OutFile $script

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $script -Ref v4.21.14
```

装完再开一个新的 PowerShell，确认命令来自 MMS：

```powershell
Get-Command mms
mms config root
```

## 5. 启动 Pilot

```powershell
mms web start --open
Start-Sleep -Seconds 5
mms web status
```

浏览器地址通常是 `http://127.0.0.1:8765`，**只在这台电脑上可访问**。

停止、重启和看 JSON 状态分别是 `mms web stop`、`mms web restart`、`mms web status --json`。

## 6. 命令行启动 Pi

Windows 暂时没有可依赖的 MMS TUI（直接输入不带参数的 `mms` 可能碰到 Python `curses` / `_curses` 的问题）。启动 Pi 用这个明确的命令，它会显示模型选择，选好按 Enter：

```powershell
$mms = "$env:LOCALAPPDATA\MMS\versions\v4.21.14\mms"
$python = "$env:LOCALAPPDATA\MMS\.venv\Scripts\python.exe"
& $python $mms pi
```

第一次值得试的几句：`hi`、`你是什么模型`、`Get-Location`，然后让它创建一个带中文或 emoji 的文件。

**不要把 `PYTHONUTF8=1` 永久写进系统环境变量。** 如果以前设过，当前窗口可以清掉：

```powershell
Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
```

## 遇到自己机器特有的问题

先把它当成一个可以交给维护者的小 issue。可以在 Pilot 里直接让本地 AI 诊断当前电脑；诊断完再决定怎么提：有 GitHub 账号就 fork 加 PR，没有就生成一份脱敏的 Markdown 报告和 `.patch` 文件，由维护者代提。

**不要发出去的东西**：API Key、`credentials.sh`、整个 `mms-next` 配置目录、没脱敏的 session。

可复制的提示词、完整的 PowerShell 取证命令、GitHub fork / PR 的小白步骤和 PR 模板都在 [`../mms-web/WINDOWS-CONTRIBUTING.md`](../mms-web/WINDOWS-CONTRIBUTING.md)。

相关契约文档：[`../mms-web/WINDOWS-PLATFORM-CONTRACT.md`](../mms-web/WINDOWS-PLATFORM-CONTRACT.md)。
