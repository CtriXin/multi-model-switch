# Windows MMS：让本地 AI 帮你修复，再把结果交回来

你不需要先学会 Git 才能报告问题。目标是让 AI 在发生问题的电脑上找到原因，你验证修复结果，再把可审阅的改动交给维护者。

## 先在终端启动 Pi

网页有问题时，在开始菜单搜索并打开 PowerShell，进入工作文件夹，再启动。Windows 暂时不依赖 MMS 全屏 TUI；如果 `mms pi` 被 PowerShell 的脚本解析或 TUI 影响，使用下面的明确入口：

```powershell
Set-Location "$env:USERPROFILE\Downloads"
$mms = "$env:LOCALAPPDATA\MMS\versions\v4.21.14\mms"
$python = "$env:LOCALAPPDATA\MMS\.venv\Scripts\python.exe"
& $python $mms pi
```

安装前先确认 `pi.cmd --version` 能输出版本；Pi 需要用 `npm.cmd install --global @earendil-works/pi-coding-agent` 单独安装。已配置的模型和通道仍由 MMS 提供；缺少模型服务时，需要先在 Pilot 中填写你自己的服务地址和 API Key。

## 把这段话发给本地 AI

```text
我在使用 MMS 时遇到了只在本机复现的问题：<描述现象、操作步骤和报错>。
请在这台电脑上诊断并修复，让我验证。

先确认实际安装版本、源码来源、运行中的进程、配置根与日志。
请建立独立的修复目录，保存基线和改动，别让我反复截图、重装来代替你排查。
不要删除我的配置和会话，不要改凭据或全局账号来绕过错误。

每轮请说明已确认的根因、改动、测试结果，以及我需要验证的具体操作。
我验证后，如果还有问题，请继续在同一份记录中处理。
修好后生成 MMS-REPAIR-REPORT.md，以及源代码 patch 或修改后的源码文件。
报告区分本地修复、自动测试和我的人工验证，不要假装已经发布。

准备向项目提交之前，请问我是否有 GitHub 账号、是否愿意公开提交。
有账号但不会 Git，请一步步帮我准备 fork、branch 和 PR。
没有账号或不想使用 Git，请准备脱敏的报告和补丁包，让我发给维护者。
登录、密码、验证码和 token 由我自己操作；不要要求我在聊天中发这些信息。
公开提交前先让我看到将要发送的文件和文字。
```

如果连 Pi 也启动不了，直接提供完整终端报错即可；有其他可用的本地 coding agent 时，也可以把同一段话交给它。你不必先把 MMS 修好才有资格报告问题。

## 给 AI 的执行约定

1. 先确认复现的版本，不要默认用最新 `dev` 替换用户正在用的 release。Windows 4.21 修复与后续 5.0 功能是不同范围。
2. 优先在独立源码目录里修复。普通安装目录 `%LOCALAPPDATA%\MMS\versions\<版本>` 通常不是 Git checkout；不要在里面直接运行 `git diff` 然后交一个空 patch。
3. 如果为了快速验证必须修改 installed runtime，先保存原文件和 SHA256，记录改动清单，停止受影响的运行进程再应用。不要修改正在执行修复工作的 Pi 自身依赖；必要时让用户在新窗口启动候选版本。
4. 每次修改必须留下完整 diff，包含新增文件、测试和恢复方法。用户安装后本地文件可能已改过，所以不要只凭相同版本号认定源码与 tag 相同。
5. 修复启动、工具执行和页面状态时，分别检查 Pi 原生记录、Web API 和页面；文件真的写好了，不代表页面状态也正确。
6. 正常用户日志要先脱敏。不要公开 `credentials.sh`、`auth.json`、API Key、token、整个配置目录或原始会话记录。
7. 本地修复通过后，生成下方报告并引导用户选择提交方式。环境修复也有价值；如果没有需要上游修改的代码，写清原因，不制造无意义 PR。

## 报告内容

让 AI 保存一份 `MMS-REPAIR-REPORT.md`：

```text
# MMS 本机修复报告
操作系统 / Python / Node / Pi：
MMS 版本 / 基线 commit / 当前源码是否已有本地修改：
复现步骤：
期望结果：
实际结果：
已确认根因（不确定的单独写）：
修改文件及每项修改的目的：
测试命令和结果：
用户在实际电脑上的验证结果：
尚未验证的场景：
恢复方法：
补丁或修改文件的位置、校验值：
提交方式 / PR 或 Issue 链接：
```

修复包只包含报告、diff、必要的源码和测试；不要把整个安装目录打包。让 AI 先检查 diff 中有没有密钥、聊天内容、私人路径和无关文件，再交给你审阅。

## 没有 GitHub 账号，或暂时不想学 Git

让 AI 生成上述报告和修复包，你可以发给项目维护者代为整理。没有 Git 也能保存完整的修改文件及其基线版本、校验值，不需要为了报告故障先注册账号。

GitHub 上公开发 Issue 或 PR 需要账号。如果愿意注册，可打开 [GitHub 注册页](https://github.com/signup)，登录完成后再继续；密码和验证码自己填写。

## 有 GitHub 账号，但不会 Git

Git 是电脑上记录源码改动的工具，GitHub 是托管和审阅这些改动的网站。安装 MMS 不需要 Git；下面只在你愿意贡献修复时使用。

先安装 Git 和可选的 GitHub CLI：

```powershell
winget install --id Git.Git -e --source winget
winget install --id GitHub.cli -e --source winget
```

关闭 PowerShell，再打开新窗口，确认：

```powershell
git --version
gh --version
```

若没有 `winget`，可从 [Git for Windows](https://git-scm.com/downloads/win) 和 [GitHub CLI](https://cli.github.com/) 官方页面安装。不会操作时，让 AI 一步步指导；不用一次看懂全部命令。

### 先准备独立源码

1. 在浏览器登录 GitHub，打开 [MMS 仓库](https://github.com/CtriXin/multi-model-switch)，点击 **Fork**，在自己账号下创建副本。
2. 让 AI 检查维护者要求的目标分支和原始版本。当前 Windows 4.21 系列请保持 4.21 基线，不要顺便合入 5.0 的 dev 功能；提交前向维护者确认该修复应进入哪个分支。
3. 下面的命令会询问你的用户名和已核实的基线 tag，复制时不需要自己替换尖括号：

```powershell
$githubUser = Read-Host '你的 GitHub 用户名'
$baseTag = Read-Host '本次问题的基线 tag，例如 v4.21.14'
$repairRoot = Join-Path $env:USERPROFILE 'mms-repair'
git clone "https://github.com/$githubUser/multi-model-switch.git" $repairRoot
Set-Location $repairRoot
git remote add upstream https://github.com/CtriXin/multi-model-switch.git
git fetch upstream --tags
git switch -c fix/windows-local-repair $baseTag
```

如果 `mms-repair` 已存在，请让 AI 检查并复用或选择新目录，不要删除旧目录。AI 应把已验证修复、测试和新增文件带入这个 checkout，并在这里复测。

### 检查并保存改动

让 AI 先展示要提交的文件，再执行这些检查：

```powershell
git status --short
git diff --check
git diff --stat
git diff
```

接下来由 AI 给出与你实际文件对应的 `git add` 和 `git commit` 命令，只提交本次修复。不要为省事把 credentials、日志、session 或整个目录加入 commit。

如果 Git 提示没有姓名或邮箱，请在当前仓库设置，避免修改全局配置。可从 GitHub 的 **Settings → Emails** 找到你的 GitHub 隐私邮箱；不必公开私人邮箱。若项目的 agent commit 规则另有要求，先遵循该规则。

### 登录并发 PR

你自己运行并完成浏览器登录，不要把凭据发给 AI：

```powershell
gh auth login --hostname github.com --git-protocol https --web
```

确认修复包和公开说明后，推送自己的分支：

```powershell
git push -u origin fix/windows-local-repair
```

打开自己的 fork，点击 **Compare & pull request**。目标仓库选择 `CtriXin/multi-model-switch`，目标分支使用前面与维护者确认的分支。标题说清触发条件和修复行为，正文包括根因、改动、自动测试和你在 Windows 上实际验证的结果。也可以让 AI 用 GitHub CLI 准备 PR 草稿；真正公开发送前由你确认。

## 只报告问题也可以

不愿改代码时，可在 [MMS Issues](https://github.com/CtriXin/multi-model-switch/issues) 新建 issue。提供复现步骤、版本、脱敏的报错和预期结果即可；没有代码修复不影响维护者接收报告。

