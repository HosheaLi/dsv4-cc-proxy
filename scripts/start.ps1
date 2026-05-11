<#
.SYNOPSIS
    Start or manage DeepSeek Bridge proxy service.
.DESCRIPTION
    Starts the DeepSeek Bridge proxy, or installs/uninstalls it as a Windows
    scheduled task for automatic startup at logon.
.PARAMETER Install
    Register the proxy as a Windows Scheduled Task (auto-start at user logon).
.PARAMETER Uninstall
    Remove the Windows Scheduled Task.
.PARAMETER Status
    Check whether the scheduled task is registered and the service is running.
.PARAMETER PassThru
    When starting, return the process object instead of waiting. Useful for
    scripting and background execution.
.EXAMPLE
    .\start.ps1
    Start the proxy in the current terminal.
.EXAMPLE
    .\start.ps1 -Install
    Install as a scheduled task and start it.
.EXAMPLE
    .\start.ps1 -Uninstall
    Remove the scheduled task.
#>

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$PassThru
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$ProxyScript = Join-Path $ProjectRoot "dsv4_cc_proxy\__main__.py"
$VenvDir = Join-Path $ProjectRoot ".venv"
$TaskName = "DeepSeekBridge"

# ---- Find Python ----
function Find-Python {
    $candidates = @("python3", "python")
    foreach ($cmd in $candidates) {
        try {
            $v = & $cmd --version 2>&1
            if ($v -match "Python 3\.(1[1-9]|[2-9]\d+)") {
                return (Get-Command $cmd).Source
            }
        } catch { continue }
    }
    throw "Python 3.11+ not found.`nDownload from: https://www.python.org/downloads/"
}

function Write-Event {
    param([string]$Message)
    try {
        Write-EventLog -LogName Application -Source "DeepSeekBridge" -EntryType Information -EventId 1000 -Message $Message -ErrorAction SilentlyContinue
    } catch {
        # Event source may not exist; ignore
    }
}

# ---- Install / Uninstall ----
if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "[STATUS] Task '$TaskName' is NOT registered." -ForegroundColor Yellow
        return
    }
    $state = $task.State
    Write-Host "[STATUS] Task '$TaskName' is $state." -ForegroundColor Green
    return
}

if ($Uninstall) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] Scheduled task '$TaskName' removed." -ForegroundColor Green
    } catch {
        Write-Host "[WARN] Task '$TaskName' not found or could not be removed." -ForegroundColor Yellow
    }
    return
}

if ($Install) {
    $PythonExe = Find-Python
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        Write-Host "[INFO] Creating virtual environment..."
        & $PythonExe -m venv $VenvDir
    }
    Write-Host "[INFO] Installing dependencies..."
    & (Join-Path $VenvDir "Scripts\pip.exe") install -q -e $ProjectRoot

    # Register scheduled task
    $action = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$ProxyScript`"" -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -AtLogon
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive -RunLevel Limited

    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
        Write-Host "[OK] Scheduled task '$TaskName' registered (auto-start at logon, restart on crash)." -ForegroundColor Green
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "[OK] Task started." -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed to register scheduled task: $_" -ForegroundColor Red
        Write-Host "Try running PowerShell as Administrator, or use start.bat for manual startup."
        exit 1
    }
    return
}

# ---- Start in foreground ----
$PythonExe = Find-Python
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[INFO] Creating virtual environment..."
    & $PythonExe -m venv $VenvDir
    Write-Host "[INFO] Installing dependencies..."
    & (Join-Path $VenvDir "Scripts\pip.exe") install -q -e $ProjectRoot
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  DeepSeek Bridge  (dsv4-cc-proxy)" -ForegroundColor Cyan
Write-Host "  Listening on http://localhost:16889" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To configure Claude Code, set:" -ForegroundColor Yellow
Write-Host '  "ANTHROPIC_BASE_URL": "http://localhost:16889"' -ForegroundColor Yellow
Write-Host ""

if ($PassThru) {
    $proc = Start-Process -FilePath $VenvPython -ArgumentList "`"$ProxyScript`"" -NoNewWindow -PassThru
    return $proc
} else {
    & $VenvPython $ProxyScript
}
