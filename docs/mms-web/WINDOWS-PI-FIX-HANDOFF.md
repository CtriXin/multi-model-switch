# Windows MMS Pi 修复交接

## 交接身份

- 时间：2026-09-14 Asia/Singapore
- 当前 owner：Windows 上负责复现、修复和验收的 Pi/CLI agent
- 交接方：Codex，model `gpt-6`，session `01a08f66-2a8a-7841-b4b6-6e28a33c178a`
- task：`855b1bed42aa43bb`
- 当前 release：`v4.21.14`（包含 Windows Pilot 修复和新手安装/贡献说明）
- 已验证基线 commit：`cc502916`
- Windows 安装验证基线：`v4.21.12`

## 用户目标

让 Windows Native Preview 能稳定启动 MMS 的 Pi 会话，并完成普通对话和 shell tool 操作。用户会在 Windows 上实际验证；每次失败都由本 agent 根据证据修复，直到用户确认通过，再把本轮修改和验证结果回传给 Codex。

## 已确认的根因与修复

Windows 启动 Pi 前会清理旧 session。旧实现用 POSIX `os.kill(pid, 0)` 检查 PID，Windows 会在这里抛出 `OSError: [WinError 11] 试图加载格式不正确的程序。`，因此 Pi 尚未真正启动。

`v4.21.12` 已在 `mms_launchers.py` 增加 Windows Win32 `OpenProcess` / `GetExitCodeProcess` 存活检查；POSIX 仍使用原来的 `os.kill(pid, 0)`。Windows 用户已在该版本完成 acceptance。后续源代码收编还包括 artifact preview、共享 `fd/rg`、skills 路径和 traceback 日志修复，已随 `v4.21.14` 发布。

本修复不改变 model routing、Bot API、调度、session/config root、真实 credentials 或 OAuth。

## Windows 机器已知环境

- 用户：`C:\Users\Admin`
- 安装入口：`C:\Users\Admin\AppData\Local\MMS\mms.cmd`
- 安装 root：`C:\Users\Admin\AppData\Local\MMS`
- Python：`C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`
- MMS venv：`C:\Users\Admin\AppData\Local\MMS\.venv\Scripts\python.exe`
- Pi：`0.85.1`
- config root：`C:\Users\Admin\.config\mms-next`
- Web state root：`C:\Users\Admin\AppData\Local\MMS\mms-web`
- Web 默认地址：`http://127.0.0.1:8765`

不要删除或覆盖已有 config/session；不要把 credentials 内容贴回聊天。

## 用户先执行的安装命令

```powershell
$script = Join-Path $env:TEMP 'mms-install-v4.21.14.ps1'

Invoke-WebRequest -UseBasicParsing `
  -Uri 'https://raw.githubusercontent.com/CtriXin/multi-model-switch/v4.21.14/packages/mms-install/bin/install.ps1' `
  -OutFile $script

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $script -Ref v4.21.14
```

安装完成后新开 PowerShell，确认 web：

```powershell
mms web stop --all
mms web start --open
Start-Sleep -Seconds 5
mms web status --json
```

确认 Pi CLI 启动路径：

```powershell
$mms = "$env:LOCALAPPDATA\MMS\versions\v4.21.14\mms"
$python = "$env:LOCALAPPDATA\MMS\.venv\Scripts\python.exe"
& $python $mms pi
```

选择一个模型后按 Enter。先验证 `hi`、`你是什么模型`、`Get-Location`，再验证创建 UTF-8 中文/emoji 文件。

## 每次失败的取证命令

只贴输出，不要截图；路径、PID、模型名可以保留，credentials/API key 必须删掉。

```powershell
mms --version
mms web status --json

Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -ge 8765 -and $_.LocalPort -le 8784 } |
  ForEach-Object {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
    [PSCustomObject]@{
      Port = $_.LocalPort
      PID = $_.OwningProcess
      Executable = $p.ExecutablePath
      CommandLine = $p.CommandLine
    }
  } | Format-List

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'MMS|mms_web|pi' } |
  Select-Object ProcessId,ExecutablePath,CommandLine |
  Format-List

Get-Content -LiteralPath "$env:LOCALAPPDATA\MMS\mms-web\logs\mms-web.log" `
  -Encoding UTF8 -Tail 200

Get-ChildItem "$env:LOCALAPPDATA\MMS\mms-web\runtimes" -Recurse `
  -Filter "launch-stderr.json" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 3 |
  ForEach-Object {
    "FILE=$($_.FullName)"
    Get-Content $_.FullName -Raw -Encoding UTF8
  }
```

如果出现 `WinError 11`，回传完整 traceback；如果能回复一部分后断开，回传发送时间、会话模型、上面日志尾部和对应 runtime 文件。

## Agent 修改边界

1. 先复现并确定失败发生在启动、Pi RPC、Web session persistence、shell tool、编码还是前端状态同步。
2. 只修改与证据对应的源码；不要改真实 config、credentials、OAuth、模型列表或用户 session 数据来绕过问题。
3. POSIX 行为必须保持不变；Windows 分支要有 import/lifecycle 或等价回归覆盖。
4. 不要把已安装目录里的生成文件直接当成最终修复。若只能临时修改 installed runtime，必须标记为临时实验，并说明最终应落到哪个 source file。
5. 每轮结束必须说明是否需要升版本；不能把“进程存在”或“页面打开”当成对话验收。

## 回传给 Codex 的固定格式

```text
[回传给 Codex]
版本 / commit：
用户复现步骤：
实际现象：
根因（已确认 / 推断 / 未知）：
修改文件及每个修改目的：
新增或运行的测试：
Windows 命令输出摘要：
用户可见结果：
剩余问题或下一步：
```

用户确认“可以连续对话、shell tool 完成后正常返回、Web 状态不再卡死”之前，状态只能写为“Windows acceptance pending”，不能写成 complete。
