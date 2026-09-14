param(
  [string]$Ref = "",
  [string]$Channel = "",
  [string]$InstallRoot = "",
  [string]$ConfigRoot = "",
  [string]$StateRoot = "",
  [switch]$NoPath,
  [switch]$NoVenv,
  [switch]$DryRun
)

# MMS Windows Native Preview bootstrap.
# Windows PowerShell 5.1 compatible: no ternary, no &&, no ?? , no $IsWindows.

$ErrorActionPreference = "Stop"
$repo = "CtriXin/multi-model-switch"
$portBase = 8765
$portSpan = 20

# Stock Windows 10 PowerShell 5.1 still negotiates TLS 1.0/1.1. GitHub answers
# TLS 1.2+ only, so without this every fetch below fails with an SSL error.
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

if ($Channel) { $Ref = $Channel }
if ($Ref -and ($Ref -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or $Ref.Contains(".."))) {
  throw "-Ref/-Channel 不是合法的分支或标签名：$Ref"
}

$localAppData = $env:LOCALAPPDATA
if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE "AppData\Local" }
$explicitConfigRoot = [bool]$ConfigRoot
if (-not $InstallRoot) { $InstallRoot = Join-Path $localAppData "MMS" }
if (-not $StateRoot) { $StateRoot = Join-Path $localAppData "MMS\mms-web" }

function Write-TextFile([string]$path, [string]$text) {
  # PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM, and a BOM on the
  # first line of a .cmd file makes cmd.exe fail on `@echo off`.
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Quote-Single([string]$value) {
  return "'" + $value.Replace("'", "''") + "'"
}

function Get-Interpreter([string]$label, [string[]]$candidates, [int]$major, [int]$minor) {
  $tried = @()
  foreach ($candidate in $candidates) {
    $parts = $candidate.Split(" ")
    $found = Get-Command $parts[0] -ErrorAction SilentlyContinue
    if (-not $found) { continue }
    $source = $found.Source
    if (-not $source) { $source = $parts[0] }
    if ($source -like "*\WindowsApps\*") {
      # The Microsoft Store app-execution alias is a zero-length stub that
      # opens the Store instead of running an interpreter.
      $item = Get-Item -LiteralPath $source -ErrorAction SilentlyContinue
      if ($item -and $item.Length -eq 0) {
        $tried += "$candidate（Microsoft Store 占位符，不是真的解释器）"
        continue
      }
    }
    $rest = @()
    if ($parts.Length -gt 1) { $rest = $parts[1..($parts.Length - 1)] }
    $text = ""
    try { $text = (& $source @rest --version 2>$null) -join " " } catch { $text = "" }
    $match = [regex]::Match($text, '([0-9]+)\.([0-9]+)')
    if (-not $match.Success) { $tried += "$candidate（无法读取版本）"; continue }
    $foundMajor = [int]$match.Groups[1].Value
    $foundMinor = [int]$match.Groups[2].Value
    if ($foundMajor -lt $major) { $tried += "$candidate（$text）"; continue }
    if ($foundMajor -eq $major -and $foundMinor -lt $minor) { $tried += "$candidate（$text）"; continue }
    return @{ path = $source; args = $rest; version = $text }
  }
  $detail = ""
  if ($tried.Count -gt 0) { $detail = " 已检查：" + ($tried -join "；") + "。" }
  throw "$label $major.$minor+ 未找到。请先安装 $label $major.$minor 或更新版本，再重新运行本 Preview bootstrap。$detail"
}

function Resolve-Ref([string]$requested) {
  if ($requested -and $requested -ne "stable") { return $requested }
  # There is no `stable` branch; stable means the latest published release tag,
  # exactly like the bash installer. `main` is deliberately behind and must
  # never be the default source.
  $release = Invoke-RestMethod -UseBasicParsing -TimeoutSec 30 `
    -Uri "https://api.github.com/repos/$repo/releases/latest" `
    -Headers @{ "User-Agent" = "mms-install" }
  if (-not $release.tag_name) { throw "无法解析最新发布版本。请改用 -Ref v<版本> 或 -Channel dev。" }
  if ($release.draft -or $release.prerelease) { throw "最新发布是 draft/prerelease。请显式指定 -Ref v<版本>。" }
  return $release.tag_name
}

function Get-LivePilotPorts {
  $ports = @()
  for ($port = $portBase; $port -lt ($portBase + $portSpan); $port++) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Method Head -TimeoutSec 1 -ErrorAction Stop `
        -Uri "http://127.0.0.1:$port/"
      # ContainsKey, not indexing: a missing key throws on the header
      # dictionary types both editions use, and a throw here would make the
      # guard silently miss a live Pilot.
      if ($response.Headers -and $response.Headers.ContainsKey("X-MMS-Web-Identity")) { $ports += $port }
    } catch { }
  }
  return $ports
}

$python = Get-Interpreter "Python" @("python", "python3", "py -3") 3 11
$node = Get-Interpreter "Node" @("node") 18 17
$pi = Get-Command pi -ErrorAction SilentlyContinue

Write-Host "MMS Windows Native Preview bootstrap"
Write-Host "  install: $InstallRoot"
if ($explicitConfigRoot) {
  Write-Host "  config:  $ConfigRoot（本次显式覆盖，写入启动脚本）"
} else {
  Write-Host "  config:  由 MMS 解析（不覆盖；可用 -ConfigRoot 或 MMS_CONFIG_ROOT 指定，安装后用 mms config root 查看）"
}
Write-Host "  state:   $StateRoot"
Write-Host "  python:  $($python.path) $($python.version)"
Write-Host "  node:    $($node.path) $($node.version)"
if (-not $pi) { Write-Warning "Pi was not found on PATH; Pilot launch will remain unavailable until Pi is installed." }
if ($DryRun) { exit 0 }

$Ref = Resolve-Ref $Ref
if ($Ref -match '^v') { $versionName = $Ref } else { $versionName = "preview-" + ($Ref -replace '[\\/:*?"<>|]', '-') }
$versionRoot = Join-Path (Join-Path $InstallRoot "versions") $versionName

# Replacing a version directory that a live Pilot is serving from would delete
# files out from under running Pi sessions, so pause instead — nothing is
# stopped and no session is cleaned up.
if (Test-Path -LiteralPath $versionRoot) {
  $live = Get-LivePilotPorts
  if ($live.Count -gt 0) {
    throw "Pilot 正在运行（端口 $($live -join '、')），已暂停安装：没有停止任何进程，也没有清理会话。请在页面的更新入口完成安全更新，或先执行 mms web stop，然后重新运行本命令。"
  }
}

$stamp = [guid]::NewGuid().ToString("N").Substring(0, 8)
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("mms-install-" + $stamp)
$zip = Join-Path $temp "source.zip"
$extract = Join-Path $temp "source"
New-Item -ItemType Directory -Force -Path $temp | Out-Null
try {
  if ($Ref -match '^v') { $archiveRef = "tags/$Ref" } else { $archiveRef = "heads/$Ref" }
  try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 -Uri "https://github.com/$repo/archive/refs/$archiveRef.zip" -OutFile $zip
  } catch {
    throw "下载 $archiveRef 失败：$($_.Exception.Message)。请确认该标签/分支存在，或改用 -Ref v<版本>。"
  }
  Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
  $source = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
  if (-not $source -or -not (Test-Path (Join-Path $source.FullName "mms_web\__main__.py"))) {
    throw "下载的压缩包里没有 MMS Pilot（$archiveRef）。该版本可能早于 Windows Preview。"
  }

  New-Item -ItemType Directory -Force -Path (Split-Path $versionRoot) | Out-Null
  $staged = "$versionRoot.new-$stamp"
  if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Recurse -Force }
  try {
    Copy-Item -LiteralPath $source.FullName -Destination $staged -Recurse
  } catch [System.UnauthorizedAccessException] {
    throw "没有写入 $((Split-Path $versionRoot)) 的权限。请换一个 -InstallRoot（默认在 %LOCALAPPDATA% 下不需要管理员），或以有权限的账号重试。"
  }

  # Swap, keeping the previous copy until the new one is in place so a failure
  # rolls back to a working install instead of half-deleting one.
  $retired = ""
  if (Test-Path -LiteralPath $versionRoot) {
    $retired = "$versionRoot.old-$stamp"
    Move-Item -LiteralPath $versionRoot -Destination $retired
  }
  try {
    Move-Item -LiteralPath $staged -Destination $versionRoot
  } catch {
    if ($retired) { Move-Item -LiteralPath $retired -Destination $versionRoot -Force }
    throw
  }
  if ($retired) {
    Remove-Item -LiteralPath $retired -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $retired) { Write-Warning "旧版本仍被占用，已保留在 $retired，可稍后手动删除。" }
  }

  New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
  if ($explicitConfigRoot) { New-Item -ItemType Directory -Force -Path $ConfigRoot | Out-Null }

  # Pilot needs httpx to reach a channel and rich for CLI output; the bash
  # installer puts both in a venv, so Windows must not skip that step.
  $launchPython = $python.path
  $launchArgs = $python.args
  if (-not $NoVenv) {
    $venv = Join-Path $InstallRoot ".venv"
    $venvPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
      & $python.path @($python.args) -m venv $venv
      if ($LASTEXITCODE -ne 0) { throw "创建 venv 失败：$venv。可以加 -NoVenv 跳过，但那样必须自己安装 rich httpx tomli-w tzdata。" }
    }
    & $venvPython -m pip install --quiet --upgrade pip
    # tzdata: Windows CPython ships no IANA database; zoneinfo(Asia/Singapore)
    # in session timestamps fails without it.
    & $venvPython -m pip install --quiet rich httpx tomli-w tzdata
    if ($LASTEXITCODE -ne 0) { throw "安装 Python 依赖失败（rich httpx tomli-w tzdata）。没有 httpx，Pilot 无法连接模型通道。" }
    $launchPython = $venvPython
    $launchArgs = @()
  }

  $entry = Join-Path $versionRoot "mms"
  $cmd = Join-Path $InstallRoot "mms.cmd"
  $ps1 = Join-Path $InstallRoot "mms.ps1"
  $cmdArgs = ""
  if ($launchArgs.Count -gt 0) { $cmdArgs = " " + ($launchArgs -join " ") }
  $lines = @("@echo off", "setlocal")
  # Only default the roots. A user who exported MMS_STATE_ROOT/MMS_CONFIG_ROOT
  # meant it, and the shim must not silently win over their choice.
  $lines += "if not defined MMS_STATE_ROOT set `"MMS_STATE_ROOT=$StateRoot`""
  if ($explicitConfigRoot) { $lines += "if not defined MMS_CONFIG_ROOT set `"MMS_CONFIG_ROOT=$ConfigRoot`"" }
  $lines += "`"$launchPython`"$cmdArgs `"$entry`" %*"
  $lines += "exit /b %ERRORLEVEL%"
  Write-TextFile $cmd (($lines -join "`r`n") + "`r`n")

  $psArgs = ""
  if ($launchArgs.Count -gt 0) { $psArgs = " " + (($launchArgs | ForEach-Object { Quote-Single $_ }) -join " ") }
  $psLines = @()
  $psLines += "if (-not `$env:MMS_STATE_ROOT) { `$env:MMS_STATE_ROOT = $(Quote-Single $StateRoot) }"
  if ($explicitConfigRoot) { $psLines += "if (-not `$env:MMS_CONFIG_ROOT) { `$env:MMS_CONFIG_ROOT = $(Quote-Single $ConfigRoot) }" }
  $psLines += "& $(Quote-Single $launchPython)$psArgs $(Quote-Single $entry) @args"
  $psLines += "exit `$LASTEXITCODE"
  Write-TextFile $ps1 (($psLines -join "`n") + "`n")

  & $launchPython -c "import httpx, rich" 2>$null
  if ($LASTEXITCODE -ne 0) { Write-Warning "启动用的 Python 缺少 httpx/rich，Pilot 绑定通道会失败。请运行：`"$launchPython`" -m pip install rich httpx tomli-w tzdata" }
  & $launchPython -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Singapore')" 2>$null
  if ($LASTEXITCODE -ne 0) { Write-Warning "启动用的 Python 缺少 tzdata，会话时间戳会失败。请运行：`"$launchPython`" -m pip install tzdata" }

  $resolvedConfig = ""
  try {
    $resolvedConfig = (& $launchPython -c "import sys; sys.path.insert(0, sys.argv[1]); from mms_state_io import resolve_mms_config_dir; print(resolve_mms_config_dir())" $versionRoot) -join ""
  } catch { $resolvedConfig = "" }

  if (-not $NoPath) {
    $key = "HKCU:\Environment"
    $raw = ""
    try { $raw = [string](Get-ItemProperty -Path $key -Name Path -ErrorAction Stop).Path } catch { $raw = "" }
    $entries = @()
    if ($raw) { $entries = @($raw.Split(';') | Where-Object { $_ }) }
    $already = @($entries | Where-Object { $_.TrimEnd('\') -ieq $InstallRoot.TrimEnd('\') })
    if ($already.Count -eq 0) {
      $updated = (@($entries) + $InstallRoot) -join ';'
      # Keep the existing value kind: rewriting a REG_EXPAND_SZ user PATH as a
      # plain string would bake every %USERPROFILE%-style entry into a literal.
      $kind = "String"
      try { $kind = (Get-Item -Path $key).GetValueKind("Path").ToString() } catch { $kind = "String" }
      if ($kind -eq "ExpandString") { Set-ItemProperty -Path $key -Name Path -Value $updated -Type ExpandString }
      else { Set-ItemProperty -Path $key -Name Path -Value $updated -Type String }
      try {
        # Set-ItemProperty does not notify Explorer, so a new window would keep
        # the old PATH until sign-out.
        if (-not ("Mms.MmsEnvBroadcast" -as [type])) {
          Add-Type -Name MmsEnvBroadcast -Namespace Mms -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true, CharSet = System.Runtime.InteropServices.CharSet.Auto)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr hWnd, uint Msg, System.IntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out System.IntPtr lpdwResult);
"@ | Out-Null
        }
        $result = [System.IntPtr]::Zero
        [void][Mms.MmsEnvBroadcast]::SendMessageTimeout([System.IntPtr]0xffff, 0x1A, [System.IntPtr]::Zero, "Environment", 2, 1000, [ref]$result)
      } catch {
        Write-Warning "已写入用户 PATH，但没能通知资源管理器。新窗口如果还找不到 mms，请注销后重新登录。"
      }
      Write-Host "已把 $InstallRoot 加入用户 PATH。打开一个新的 PowerShell 窗口即可使用 mms。"
    }
    if (($env:Path -split ';') -notcontains $InstallRoot) { $env:Path = "$env:Path;$InstallRoot" }
  }

  Write-Host "已安装 Windows Native Preview（$Ref）。已有的 config / session 目录没有被导入，也没有被覆盖。"
  Write-Host "  entry:   $cmd"
  if ($resolvedConfig) { Write-Host "  config:  $resolvedConfig（mms config root 可复核）" }
  Write-Host "  验证：在新窗口执行 Get-Command mms，然后 mms web start"
} finally {
  Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
