@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "VENV_DIR=%PROJECT_DIR%.venv"
set "PROXY_SCRIPT=%PROJECT_DIR%dsv4_cc_proxy\__main__.py"

:parse_args
if /i "%~1"=="--help" goto :help
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--install" (
    set "DO_INSTALL=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--uninstall" (
    set "DO_UNINSTALL=1"
    shift
    goto :parse_args
)

rem ---- Check Python ----
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    python3 --version >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Python is not found. Please install Python 3.11+ from:
        echo         https://www.python.org/downloads/
        echo.
        echo Make sure to check "Add Python to PATH" during installation.
        pause
        exit /b 1
    )
    set "PY=python3"
) else (
    set "PY=python"
)

rem ---- Install/Uninstall Windows service ----
if defined DO_INSTALL (
    powershell.exe -ExecutionPolicy RemoteSigned -File "%SCRIPT_DIR%install_windows_service.ps1" -Install
    if !ERRORLEVEL! equ 0 (
        echo [OK] DeepSeek Bridge service installed successfully.
    )
    pause
    exit /b !ERRORLEVEL!
)
if defined DO_UNINSTALL (
    powershell.exe -ExecutionPolicy RemoteSigned -File "%SCRIPT_DIR%install_windows_service.ps1" -Remove
    if !ERRORLEVEL! equ 0 (
        echo [OK] DeepSeek Bridge service removed.
    )
    pause
    exit /b !ERRORLEVEL!
)

rem ---- Setup virtual environment ----
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    "%PY%" -m venv "%VENV_DIR%"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [INFO] Installing dependencies...
call "%VENV_DIR%\Scripts\pip.exe" install -q -e "%PROJECT_DIR%"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   DeepSeek Bridge  (dsv4-cc-proxy)
echo   Listening on http://localhost:16889
echo ==============================================
echo.
echo To configure Claude Code, set:
echo   "ANTHROPIC_BASE_URL": "http://localhost:16889"
echo.
"%VENV_DIR%\Scripts\python.exe" "%PROXY_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Proxy exited with code %ERRORLEVEL%
    pause
)
exit /b %ERRORLEVEL%

:help
echo DeepSeek Bridge — Anthropic API Compatibility Proxy
echo.
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   --install     Register as Windows scheduled task (auto-start at logon)
echo   --uninstall   Remove the Windows scheduled task
echo   --help, -h    Show this help message
echo.
echo Without options, starts the proxy in the current terminal window.
echo Press Ctrl+C to stop.
pause
exit /b 0
