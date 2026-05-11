<#
.SYNOPSIS
    Install/uninstall DeepSeek Bridge as a Windows scheduled task.
.DESCRIPTION
    Registers a scheduled task that starts the proxy at user logon and
    automatically restarts it if it crashes (up to 3 retries, 1-min intervals).
.PARAMETER Install
    Register the scheduled task.
.PARAMETER Remove
    Unregister the scheduled task.
.PARAMETER Status
    Check if the task is registered and running.
.PARAMETER System
    Run as LOCAL SYSTEM (requires Administrator). Default runs as current user.
.EXAMPLE
    .\install_windows_service.ps1 -Install
    Install for current user.
.EXAMPLE
    .\install_windows_service.ps1 -Install -System
    Install as system-wide service (admin required).
.EXAMPLE
    .\install_windows_service.ps1 -Remove
    Unregister the task.
#>

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Status,
    [switch]$System
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$ProxyScript = Join-Path $ProjectRoot "dsv4_cc_proxy\__main__.py"
$VenvDir = Join-Path $ProjectRoot ".venv"
$TaskName = "DeepSeekBridge"

function Write-Step {
    param([string]$Message, [string]$Color = "White")
    Write-Host "  [$([DateTime]::Now.ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}

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

if ($Status) {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Write-Host "[STATUS] Task '$TaskName': $($task.State)" -ForegroundColor Green
        $running = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -match [Regex]::Escape("dsv4_cc_proxy")
        }
        if ($running) {
            Write-Host "[STATUS] Proxy process is running (PID: $($running.Id))." -ForegroundColor Green
        } else {
            Write-Host "[STATUS] Proxy process is not running." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[STATUS] Task '$TaskName' is not registered." -ForegroundColor Yellow
    }
    return
}

if ($Remove) {
    Write-Step "Removing scheduled task '$TaskName'..." -Color Yellow
    try {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Step "Task removed." -Color Green
    } catch {
        Write-Step "Task not found or already removed." -Color Yellow
    }
    return
}

if (-not $Install) {
    Write-Host "Usage: .\install_windows_service.ps1 -Install | -Remove | -Status" -ForegroundColor Yellow
    return
}

# ---- Install ----
Write-Host "`n=== DeepSeek Bridge — Windows Service Installer ===`n" -ForegroundColor Cyan

# 1. Find Python
Write-Step "Checking Python..." -Color Cyan
try {
    $PythonExe = Find-Python
    $pyVer = & $PythonExe --version 2>&1
    Write-Step "Found $pyVer at $PythonExe" -Color Green
} catch {
    Write-Step "ERROR: $_" -Color Red
    exit 1
}

# 2. Setup venv
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating virtual environment..." -Color Cyan
    & $PythonExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Step "ERROR: Failed to create virtual environment." -Color Red
        exit 1
    }
    Write-Step "Virtual environment created." -Color Green
} else {
    Write-Step "Virtual environment exists." -Color Green
}

# 3. Install dependencies
Write-Step "Installing dependencies..." -Color Cyan
$pip = Join-Path $VenvDir "Scripts\pip.exe"
& $pip install -q -e $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    Write-Step "ERROR: Failed to install dependencies." -Color Red
    exit 1
}
Write-Step "Dependencies installed." -Color Green

# 4. Register scheduled task
Write-Step "Registering scheduled task '$TaskName'..." -Color Cyan
$action = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$ProxyScript`"" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

if ($System) {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principal = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive -RunLevel Limited
}

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
    Write-Step "Task registered successfully." -Color Green
} catch {
    Write-Step "ERROR: Failed to register task. Try running as Administrator." -Color Red
    Write-Step "Details: $_" -Color Red
    exit 1
}

# 5. Start the task
Write-Step "Starting task..." -Color Cyan
try {
    Start-ScheduledTask -TaskName $TaskName
    Write-Step "Task started." -Color Green
} catch {
    Write-Step "WARN: Task registered but could not start: $_" -Color Yellow
    Write-Step "It will start automatically at next logon." -Color Yellow
}

Write-Host "`n=== Installation complete ===" -ForegroundColor Cyan
Write-Host "The proxy will start automatically at your next logon."
Write-Host "To start now, run:  .\start.ps1" -ForegroundColor Yellow
Write-Host "To check status:     .\install_windows_service.ps1 -Status" -ForegroundColor Yellow
Write-Host "To uninstall:        .\install_windows_service.ps1 -Remove" -ForegroundColor Yellow
