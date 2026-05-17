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
if errorlevel 1 goto :no_python

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto :old_python

echo [ OK ] Python found:
python --version

REM --- 2. Virtual env -------------------------------------------------------
if not exist .venv (
    echo Creating .venv ...
    python -m venv .venv
    if errorlevel 1 goto :venv_failed
)
echo [ OK ] Virtual environment ready: .venv

REM --- 3. Python dependencies ----------------------------------------------
echo.
echo Installing SISI-TV and dependencies. This can take a minute...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
if errorlevel 1 goto :pip_failed
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 goto :pip_failed
echo [ OK ] Python packages installed.

REM --- 4. ffmpeg ------------------------------------------------------------
echo.
where ffmpeg >nul 2>&1
if not errorlevel 1 goto :ffmpeg_ok

echo ffmpeg is not on PATH. Checking for winget...
where winget >nul 2>&1
if errorlevel 1 goto :no_winget

echo Installing ffmpeg via winget Gyan.FFmpeg ...
winget install --id=Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :winget_failed
echo [ OK ] ffmpeg installed via winget.
goto :after_ffmpeg

:ffmpeg_ok
echo [ OK ] ffmpeg already on PATH.
goto :after_ffmpeg

:no_winget
echo [WARN] ffmpeg is missing and winget is not available.
echo        Recording and live MJPEG will not work without ffmpeg.
echo        Install manually from https://ffmpeg.org/download.html
echo        or with Chocolatey:  choco install ffmpeg
goto :after_ffmpeg

:winget_failed
echo [WARN] winget could not install ffmpeg. Install it manually if needed.
goto :after_ffmpeg

:after_ffmpeg

REM --- 5. Default storage dirs ---------------------------------------------
echo.
if not exist "C:\sisi-tv-storage"           mkdir "C:\sisi-tv-storage"           >nul 2>&1
if not exist "C:\sisi-tv-storage\snapshots" mkdir "C:\sisi-tv-storage\snapshots" >nul 2>&1
if errorlevel 1 goto :storage_failed
echo [ OK ] Default storage dirs ready: C:\sisi-tv-storage
goto :startup

:storage_failed
echo [WARN] Could not create C:\sisi-tv-storage automatically.
echo        Either run install.bat from an elevated prompt, or open the
echo        Settings page after launch to point recording_root somewhere writable.
goto :startup

:startup
REM --- 6. Auto-start on login ----------------------------------------------
echo.
echo Creating Startup-folder shortcut so SISI-TV launches at login ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-startup-shortcut.ps1"
if errorlevel 1 (
    echo [WARN] Could not create the autostart shortcut. You can re-run
    echo        scripts\create-startup-shortcut.ps1 manually later, or skip
    echo        autostart entirely.
) else (
    echo [ OK ] Autostart configured: each login will git pull and launch SISI-TV.
)
goto :done

:done
echo.
echo ============================================
echo   Install complete.
echo ============================================
echo.
echo Auto-start: SISI-TV.lnk is in your Startup folder, so the next
echo login will git pull + launch automatically. To disable, delete
echo it from shell:startup (paste in Win+R).
echo.
echo Launching SISI-TV in a new window ...
start "SISI-TV" "%~dp0.venv\Scripts\sisi-tv.exe"
echo.
echo The app should open http://127.0.0.1:8000/ in your default browser.
echo Change bind_host / bind_port via Settings for LAN access.
echo.
echo To relaunch later: start.bat   (also runs git pull first)
echo                    .venv\Scripts\sisi-tv.exe   (skips git pull)
echo.
exit /b 0

REM --- Error exits ----------------------------------------------------------

:no_python
echo [FAIL] Python is not on PATH.
echo        Install Python 3.11 or newer from https://www.python.org/downloads/
echo        Tick "Add Python to PATH" during install, then re-run this script.
exit /b 1

:old_python
echo [FAIL] Python 3.11 or newer is required. Currently installed:
python --version
exit /b 1

:venv_failed
echo [FAIL] Could not create the .venv virtual environment.
exit /b 1

:pip_failed
echo [FAIL] pip install failed. Scroll up for details.
exit /b 1
