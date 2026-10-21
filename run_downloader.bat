@echo off
setlocal enabledelayedexpansion

title Smart Browser-Based Batch Downloader Launcher
color 0A

:: 1. Navigate to script directory
cd /d "%~dp0"

echo =====================================================================
echo           SMART BROWSER-BASED BATCH DOWNLOADER LAUNCHER
echo =====================================================================
echo.
echo [IMPORTANT] Please ensure Microsoft Edge is running with remote debugging enabled.
echo [IMPORTANT] You can start Edge with: msedge.exe --remote-debugging-port=9222
echo.

:: 2. Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not found in system PATH.
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check the option: "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo [OK] Python detected:
python --version
echo.

:: 3. Install / Update dependencies using the same python interpreter
echo [SETUP] Verifying and installing required packages from requirements.txt...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install required packages.
    pause
    exit /b 1
)

:: 4. Install Playwright browser binaries
echo [SETUP] Verifying Playwright browser binaries...
python -m playwright install msedge >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Playwright msedge installation encountered a notice.
    echo Trying chromium fallback...
    python -m playwright install chromium >nul 2>nul
)

echo.
echo =====================================================================
echo                  STARTING BATCH DOWNLOADER
echo =====================================================================
echo.

:: 5. Launch main application
python downloader.py

echo.
echo =====================================================================
echo  Execution finished. Console log output preserved above.
echo =====================================================================
pause
endlocal