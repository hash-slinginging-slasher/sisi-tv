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
if not exist "D:\" goto :no_d_drive
if not exist "D:\ngc-cams-recordings" mkdir "D:\ngc-cams-recordings" >nul 2>&1
if not exist "D:\ngc-cams-snapshots"  mkdir "D:\ngc-cams-snapshots"  >nul 2>&1
echo [ OK ] Default storage dirs ready under D:\.
goto :done

:no_d_drive
echo [WARN] No D:\ drive detected.
echo        The app defaults to D:\ngc-cams-recordings\ and D:\ngc-cams-snapshots\.
echo        Open the Settings page after launch to change them, or pre-create
echo        %USERPROFILE%\.ngc-cams\settings.json with the right paths.
goto :done

:done
echo.
echo ============================================
echo   Install complete.
echo ============================================
echo.
echo Launch SISI-TV with:
echo.
echo   .venv\Scripts\sisi-tv.exe
echo.
echo Or activate the venv first:
echo.
echo   .venv\Scripts\activate
echo   sisi-tv
echo.
echo The app will open http://127.0.0.1:8000/ in your default browser.
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
