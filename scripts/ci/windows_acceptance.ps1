# MMS Pilot T3 Windows acceptance driver.
#
# Runs on a real Windows host (GitHub Actions windows-* runner or a manual
# machine) and checks the seams that cannot be proven on Linux/macOS:
# PowerShell 5.1/7 editions, the install.ps1 dry-run contract, Windows paths
# with spaces/Chinese, UNC, junction redirection into .pilot/attachments,
# Pi discoverability, and the mms web start/status/url/restart/stop lifecycle
# through the same cmd/ps1 shims install.ps1 generates.
#
# A pass here is Windows acceptance. A pass on Linux/macOS never was.
# Syntax stays Windows PowerShell 5.1 compatible (no &&, no ternary).

param(
  [string]$RepoRoot = "",
  [string]$PythonExe = "python",
  [string]$TempRoot = "",
  [string]$ShellEdition = "7",   # "5.1" or "7"
  [bool]$PiPresent = $false
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
if (-not $TempRoot) { $TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mms-win-accept-" + [guid]::NewGuid().ToString("N")) }
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:MMS_SKIP_VENV_REEXEC = "1"
if (-not $env:MMS_CONFIG_ROOT) { $env:MMS_CONFIG_ROOT = Join-Path $TempRoot "cfg" }
if (-not $env:MMS_STATE_ROOT) { $env:MMS_STATE_ROOT = Join-Path $TempRoot "state" }
$env:PYTHONPATH = $RepoRoot

function Write-Phase([string]$name) {
  Write-Host ""
  Write-Host "=== PHASE $name ===" -ForegroundColor Cyan
}

function Assert-True($condition, [string]$message) {
  if (-not $condition) { throw "ASSERT FAILED: $message" }
}

# Run a python probe written to a temp file (avoids cross-shell quoting).
function Invoke-PyProbe([string]$code, [string[]]$argv = @()) {
  $file = Join-Path $TempRoot ("probe-" + [guid]::NewGuid().ToString("N") + ".py")
  [System.IO.File]::WriteAllText($file, $code, (New-Object System.Text.UTF8Encoding($true)))
  # stdout only: with $ErrorActionPreference=Stop, merging a native command's
  # stderr via 2>&1 can turn the first warning into a terminating error (PS 5.1).
  $out = & $PythonExe $file @argv
  $status = $LASTEXITCODE
  if ($status -ne 0) { throw "python probe exited $status`: $($out -join "`n")" }
  return (($out | ForEach-Object { "$_" }) -join "`n")
}

# Invoke install.ps1 safely: a `throw` inside the script propagates as a
# terminating error through the call operator, so catch it instead of dying.
function Invoke-Installer([hashtable]$installerArgs) {
  $captured = @()
  $status = 1
  try {
    $captured = @(& $installer @installerArgs *>&1)
    $status = $LASTEXITCODE
    if ($null -eq $status) { $status = 0 }
  } catch {
    $captured = @($_.Exception.Message)
    $status = 1
  }
  return @{ exit = [int]$status; text = (($captured | ForEach-Object { "$_" }) -join "`n") }
}

# Parse the JSON object/array embedded in command output (tolerates noise).
function ConvertFrom-CommandJson([string]$text) {
  $first = $text.IndexOf("{")
  $last = $text.LastIndexOf("}")
  if ($first -lt 0 -or $last -le $first) { throw "no JSON object in output: $text" }
  return ($text.Substring($first, $last - $first + 1) | ConvertFrom-Json)
}

# --- Phase 0: guard + shell edition -----------------------------------------
Write-Phase "0 guard"
if ($env:RUNNER_OS) {
  Assert-True ($env:RUNNER_OS -eq "Windows") "RUNNER_OS is $($env:RUNNER_OS); Windows acceptance must run on Windows"
}
$version = $PSVersionTable.PSVersion
if ($ShellEdition -eq "5.1") {
  Assert-True ($version.Major -eq 5) "expected Windows PowerShell 5.1, found $($version)"
} else {
  Assert-True ($version.Major -ge 7) "expected PowerShell 7+, found $($version)"
}
Write-Host "shell edition OK: $($version), os=$([System.Environment]::OSVersion.VersionString)"

# --- Phase 1: platform descriptor + browser capability ----------------------
Write-Phase "1 platform-descriptor"
$snapshot = Invoke-PyProbe @'
import json, os
from pathlib import Path
from mms_platform import describe_platform, capability_snapshot

d = describe_platform()
assert d.os == "win32", d
assert d.path_style == "windows", d
assert d.process_control == "windows-process-group", d
assert str(Path(os.environ["MMS_CONFIG_ROOT"]).resolve()).lower() == d.config_root.lower(), d
assert str(Path(os.environ["MMS_STATE_ROOT"]).resolve()).lower() == d.state_root.lower(), d
snap = capability_snapshot()
browsers = {b["backend"]: b for b in snap["browser"]}
assert browsers["ego"]["supported"] is False, browsers["ego"]
assert browsers["web-access"]["supported"] is True, browsers["web-access"]
print("PLATFORM_OK", json.dumps(snap["platform"], ensure_ascii=False))
'@
Assert-True ($snapshot -match "PLATFORM_OK") "platform descriptor mismatch: $snapshot"
Write-Host $snapshot

# --- Phase 2: install.ps1 dry-run (no network, no writes) -------------------
Write-Phase "2 installer-dry-run"
$installer = Join-Path $RepoRoot "packages\mms-install\bin\install.ps1"
Assert-True (Test-Path -LiteralPath $installer) "install.ps1 not found at $installer"
$installRoot = Join-Path $TempRoot "install"
$dryConfig = Join-Path $TempRoot "dry-cfg"
$dryState = Join-Path $TempRoot "dry-state"
$dry = Invoke-Installer -installerArgs @{ Ref = "ci-probe"; InstallRoot = $installRoot; ConfigRoot = $dryConfig; StateRoot = $dryState; DryRun = $true }
Assert-True ($dry.exit -eq 0) "installer dry-run exited $($dry.exit): $($dry.text)"
$dryText = $dry.text
Assert-True ($dryText -match "Windows Native Preview bootstrap") "dry-run missing bootstrap banner: $dryText"
Assert-True ($dryText.Contains($installRoot)) "dry-run did not echo the install root: $dryText"
Assert-True (-not (Test-Path (Join-Path $installRoot "versions"))) "dry-run must not create anything under the install root"
if (-not $PiPresent) {
  Assert-True ($dryText -match "Pi was not found on PATH") "pi-absent cell must warn about missing Pi: $dryText"
}
Write-Host "installer dry-run OK (nothing downloaded, nothing written)"

# --- Phase 3: missing Python/Node produce readable errors -------------------
Write-Phase "3 installer-missing-deps"
$realPath = $env:PATH
try {
  $env:PATH = "$env:SystemRoot\System32"
  $neg = Invoke-Installer -installerArgs @{ Ref = "ci-probe"; InstallRoot = $installRoot; DryRun = $true }
} finally {
  $env:PATH = $realPath
}
Assert-True ($neg.exit -ne 0) "installer must fail when python/node are missing"
Assert-True ($neg.text -match "is required|未找到") "installer missing-deps error must explain the requirement: $($neg.text)"
Write-Host "missing-deps error OK: $($neg.text.Split("`n")[0])"

# --- Phase 4: Windows paths (spaces, Chinese, quoting) -----------------------
Write-Phase "4 windows-paths"
$spaceDir = Join-Path $TempRoot "项目 Directory With Spaces 中文"
New-Item -ItemType Directory -Force -Path $spaceDir | Out-Null
$spaceFile = Join-Path $spaceDir "文件 notes.txt"
[System.IO.File]::WriteAllText($spaceFile, "windows path probe 中文", (New-Object System.Text.UTF8Encoding($false)))
$pathProbe = Invoke-PyProbe @'
import sys
from pathlib import Path
p = Path(sys.argv[1])
data = p.read_text(encoding="utf-8")
assert data == "windows path probe 中文", data
assert p.is_absolute() and ":" in str(p), p
print("PATH_OK", str(p))
'@ @($spaceFile)
Assert-True ($pathProbe -match "PATH_OK") "path probe failed: $pathProbe"
Write-Host $pathProbe

# --- Phase 5: UNC read/write --------------------------------------------------
Write-Phase "5 unc"
$shareName = "mms-ci-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$uncMechanism = ""
$uncFile = ""
$createdShare = $false
try {
  try {
    New-SmbShare -Name $shareName -Path $TempRoot -FullAccess "$env:USERDOMAIN\$env:USERNAME" -ErrorAction Stop | Out-Null
    $createdShare = $true
    $uncMechanism = "smb-share"
    $uncFile = "\\localhost\$shareName\unc 测试 file.txt"
  } catch {
    Write-Host "New-SmbShare unavailable ($($_.Exception.Message)); falling back to the admin share"
    if (-not (Test-Path "\\localhost\c$")) { throw "no local SMB share and no \\localhost\c$ admin share; UNC cannot be verified on this host" }
    $uncMechanism = "admin-share"
    $drive = $TempRoot.Substring(0, 1)
    $rest = $TempRoot.Substring(3)
    $uncFile = "\\localhost\$drive`$\$rest\unc 测试 file.txt"
  }
  [System.IO.File]::WriteAllText($uncFile, "unc data 中文", (New-Object System.Text.UTF8Encoding($false)))
  $uncRead = [System.IO.File]::ReadAllText($uncFile, [System.Text.Encoding]::UTF8)
  Assert-True ($uncRead -eq "unc data 中文") "UNC roundtrip mismatch: $uncRead"
  $uncProbe = Invoke-PyProbe @'
import sys
from pathlib import Path
p = Path(sys.argv[1])
assert p.read_text(encoding="utf-8") == "unc data 中文", p
print("UNC_OK", str(p))
'@ @($uncFile)
  Assert-True ($uncProbe -match "UNC_OK") "python UNC probe failed: $uncProbe"
  Write-Host "UNC OK via $uncMechanism`: $uncFile"
} finally {
  if ($createdShare) { Remove-SmbShare -Name $shareName -Force -ErrorAction SilentlyContinue }
}

# --- Phase 6: junction redirection into .pilot/attachments -------------------
Write-Phase "6 junction-guard"
$junctionWorkspace = Join-Path $TempRoot "junction-workspace"
$junctionTarget = Join-Path $TempRoot "junction-real-attachments"
New-Item -ItemType Directory -Force -Path (Join-Path $junctionWorkspace ".pilot") | Out-Null
New-Item -ItemType Directory -Force -Path $junctionTarget | Out-Null
$junctionLink = Join-Path $junctionWorkspace ".pilot\attachments"
New-Item -ItemType Junction -Path $junctionLink -Target $junctionTarget | Out-Null
$junctionProbe = Invoke-PyProbe @'
import sys
from pathlib import Path
from types import SimpleNamespace
from mms_web.files import FileService
from mms_web.errors import WebError
import base64

workspace = Path(sys.argv[1]).resolve()
catalog = SimpleNamespace(_workspaces=lambda: [{"id": "w", "path": str(workspace)}])
files = FileService(catalog, Path(sys.argv[2]))
payload = {"workspaceId": "w", "name": "junction probe.txt",
           "data": base64.b64encode(b"probe").decode("utf-8")}
try:
    files.import_to_workspace(payload)
except (WebError, OSError) as exc:
    print("JUNCTION_REJECTED", exc)
    sys.exit(0)
print("JUNCTION_NOT_REJECTED import wrote through the junction")
sys.exit(3)
'@ @($junctionWorkspace, (Join-Path $TempRoot "junction-state"))
Assert-True ($junctionProbe -match "JUNCTION_REJECTED") "junction redirection was not rejected: $junctionProbe"
Write-Host $junctionProbe

# --- Phase 7: Pi discoverability ----------------------------------------------
Write-Phase "7 pi-discover"
$piCommand = Get-Command pi -ErrorAction SilentlyContinue
if ($PiPresent) {
  Assert-True ($null -ne $piCommand) "pi was expected on PATH in this cell"
  $piVersion = & pi --version
  Assert-True ($LASTEXITCODE -eq 0) "pi --version failed: $($piVersion -join ' ')"
  $piProbe = Invoke-PyProbe @'
import shutil
found = shutil.which("pi")
assert found, "shutil.which could not discover pi"
print("PI_DISCOVERED", found)
'@
  Assert-True ($piProbe -match "PI_DISCOVERED") "pilot-style PATH discovery failed: $piProbe"
  Write-Host "pi OK: $($piVersion -join ' ') -> $piProbe"
} else {
  Assert-True ($null -eq $piCommand) "pi must be absent in the floor cell so the missing-Pi path stays covered"
  Write-Host "pi intentionally absent; missing-Pi messaging was checked in phase 2"
}

# --- Phase 8: mms shim lifecycle (start/status/url/restart/stop) -------------
Write-Phase "8 mms-web-lifecycle"
$binDir = Join-Path $TempRoot "bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$lifeState = Join-Path $TempRoot "life-state"
$lifeConfig = Join-Path $TempRoot "life-cfg"
New-Item -ItemType Directory -Force -Path $lifeConfig | Out-Null
$mmsCmd = Join-Path $binDir "mms.cmd"
$mmsPs1 = Join-Path $binDir "mms.ps1"
$pythonFull = (Get-Command $PythonExe -ErrorAction Stop).Source
# Mirror install.ps1's shim shape; ASCII without BOM so cmd.exe parses it cleanly.
$cmdText = "@echo off`r`nset MMS_CONFIG_ROOT=$lifeConfig`r`nset MMS_STATE_ROOT=$lifeState`r`n`"$pythonFull`" `"$RepoRoot\mms`" %*`r`n"
[System.IO.File]::WriteAllText($mmsCmd, $cmdText, [System.Text.Encoding]::ASCII)
$ps1Text = "`$env:MMS_CONFIG_ROOT = '$lifeConfig'`n`$env:MMS_STATE_ROOT = '$lifeState'`n& '$pythonFull' '$RepoRoot\mms' `$args`n"
[System.IO.File]::WriteAllText($mmsPs1, $ps1Text, [System.Text.Encoding]::ASCII)

$portText = Invoke-PyProbe @'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
'@
$port = [int]($portText.Trim().Split("`n")[-1])
Write-Host "lifecycle port: $port"

function Invoke-MmsVerb([string[]]$verbArgs) {
  # stdout only; stderr stays visible on the console and never corrupts JSON.
  $output = & $mmsCmd @verbArgs
  return @{ exit = $LASTEXITCODE; text = (($output | ForEach-Object { "$_" }) -join "`n") }
}

try {
  $start = Invoke-MmsVerb @("web", "start", "--port", "$port", "--json")
  Assert-True ($start.exit -eq 0) "mms web start exited $($start.exit): $($start.text)"
  $started = ConvertFrom-CommandJson $start.text
  Assert-True ($started.mine -eq $true) "started instance not recognized as mine: $($start.text)"
  Assert-True ($started.url -eq "http://127.0.0.1:$port") "unexpected url: $($start.text)"
  $startPid = [int]$started.pid
  Assert-True ($startPid -gt 0) "no pid reported: $($start.text)"

  $status = Invoke-MmsVerb @("web", "status", "--port", "$port", "--json")
  Assert-True ($status.exit -eq 0) "mms web status exited $($status.exit): $($status.text)"
  $statusPayload = ConvertFrom-CommandJson $status.text
  $statusRows = @($statusPayload.instances)
  Assert-True ($statusRows.Count -eq 1) "expected exactly one instance: $($status.text)"
  Assert-True ($statusRows[0].pid -eq $startPid) "status pid drifted: $($status.text)"

  $url = Invoke-MmsVerb @("web", "url", "--port", "$port")
  Assert-True ($url.exit -eq 0) "mms web url exited $($url.exit)"
  Assert-True ($url.text -match "http://127\.0\.0\.1:$port") "unexpected url output: $($url.text)"

  # The installer also ships an mms.ps1 shim; exercise it at least once.
  $urlViaPs1 = & $mmsPs1 web url --port "$port"
  Assert-True ($LASTEXITCODE -eq 0 -and (($urlViaPs1 | ForEach-Object { "$_" }) -join "`n") -match "http://127\.0\.0\.1:$port") "mms.ps1 shim failed: $($urlViaPs1 -join ' ')"

  $again = Invoke-MmsVerb @("web", "start", "--port", "$port", "--json")
  Assert-True ($again.exit -eq 0) "second start exited $($again.exit): $($again.text)"
  Assert-True ([int](ConvertFrom-CommandJson $again.text).pid -eq $startPid) "second start spawned another instance: $($again.text)"

  $restart = Invoke-MmsVerb @("web", "restart", "--port", "$port", "--json")
  Assert-True ($restart.exit -eq 0) "mms web restart exited $($restart.exit): $($restart.text)"
  Assert-True ((ConvertFrom-CommandJson $restart.text).url -eq "http://127.0.0.1:$port") "restart url drifted: $($restart.text)"

  $stop = Invoke-MmsVerb @("web", "stop", "--port", "$port", "--json")
  Assert-True ($stop.exit -eq 0) "mms web stop exited $($stop.exit): $($stop.text)"
  $stopped = @(ConvertFrom-CommandJson $stop.text)
  Assert-True ($stopped.Count -eq 1 -and [int]$stopped[0].pid -eq $startPid) `
    "graceful stop did not stop the instance (known Windows seam: CloseMainWindow on a console process): $($stop.text)"

  $after = Invoke-MmsVerb @("web", "status", "--port", "$port", "--json")
  Assert-True ($after.exit -eq 1) "status after stop must report no own instance: $($after.text)"
  $afterPayload = ConvertFrom-CommandJson $after.text
  Assert-True (@($afterPayload.instances).Count -eq 0) "instance still visible after stop: $($after.text)"
  Write-Host "mms web lifecycle OK via shims (start/status/url/restart/stop)"
} finally {
  try { $null = & $mmsCmd web stop --all --port "$port" --json 2>&1 } catch { }
}

Write-Host ""
Write-Host "WINDOWS_ACCEPTANCE_DRIVER_PASS edition=$ShellEdition pi=$PiPresent temp=$TempRoot" -ForegroundColor Green
exit 0
