@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo   SISI-TV installer
echo ============================================
echo Working dir: %CD%
echo.

REM --- 1. Python check ------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python is not on PATH.
    echo        Install Python 3.11 or newer from https://python.org/downloads/
    echo        (tick "Add Python to PATH" during install), then re-run this script.
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python 3.11 or newer is required. Currently installed:
    python --version
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [ OK ] %%v

REM --- 2. Virtual env -------------------------------------------------------
if not exist .venv (
    echo Creating .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [FAIL] venv creation failed.
        exit /b 1
    )
)
echo [ OK ] Virtual environment ready ^(.venv^).

REM --- 3. Python dependencies ----------------------------------------------
echo Installing SISI-TV and dependencies ^(this can take a minute^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo [FAIL] pip install failed. Scroll up for details.
    exit /b 1
)
echo [ OK ] Python packages installed.

REM --- 4. ffmpeg ------------------------------------------------------------
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ffmpeg not on PATH. Checking for winget ...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [WARN] ffmpeg is missing and winget is not available.
        echo        Recording and live MJPEG will not work until ffmpeg is installed.
        echo        Install manually from https://ffmpeg.org/download.html
        echo        or with Chocolatey:  choco install ffmpeg
    ) else (
        echo Installing ffmpeg via winget ^(Gyan.FFmpeg^) ...
        winget install --id=Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
        if errorlevel 1 (
            echo [WARN] winget install of ffmpeg failed. Install it manually if needed.
        ) else (
            echo [ OK ] ffmpeg installed via winget.
        )
    )
) else (
    echo [ OK ] ffmpeg already on PATH.
)

REM --- 5. Default storage dirs ---------------------------------------------
REM Created lazily by the app on first record, but pre-creating avoids the
REM very first "disk usage" check from failing on a brand-new D:\ drive.
if exist "D:\" (
    if not exist "D:\ngc-cams-recordings" mkdir "D:\ngc-cams-recordings" >nul 2>&1
    if not exist "D:\ngc-cams-snapshots"  mkdir "D:\ngc-cams-snapshots"  >nul 2>&1
    echo [ OK ] Default storage dirs ready under D:\.
) else (
    echo [WARN] No D:\ drive detected. The app defaults to D:\ngc-cams-recordings\.
    echo        Change paths via the Settings page after launch, or set them in
    echo        %USERPROFILE%\.ngc-cams\settings.json before first run.
)

echo.
echo ============================================
echo   Install complete.
echo ============================================
echo.
echo Launch SISI-TV with either:
echo.
echo   .venv\Scripts\sisi-tv.exe
echo.
echo or activate the venv first and then run "sisi-tv":
echo.
echo   .venv\Scripts\activate
echo   sisi-tv
echo.
echo The app will open http://127.0.0.1:8000/ in your default browser.
echo.

endlocal
