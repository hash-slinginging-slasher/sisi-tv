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

REM --- 3b. Optional fullscreen viewer (pywebview) --------------------------
REM pywebview pulls in pythonnet, which only has wheels for Python 3.7-3.13.
REM On Python 3.14+ this build fails. The server doesn't need it, so we
REM treat the failure as non-fatal and skip the kiosk shortcut.
set VIEWER_INSTALLED=0
echo.
echo Installing optional fullscreen viewer (pywebview)...
".venv\Scripts\python.exe" -m pip install -e ".[viewer]"
if errorlevel 1 (
    echo [WARN] Could not install the pywebview viewer extra.
    echo        Most likely cause: pythonnet has no wheel for your Python
    echo        version (it currently supports 3.7-3.13). The SISI-TV server
    echo        will still install and run -- only the auto-fullscreen kiosk
    echo        viewer is skipped. To enable it, install Python 3.13 and re-run.
) else (
    echo [ OK ] Viewer installed.
    set VIEWER_INSTALLED=1
)

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
REM We drop two .cmd stubs directly into the per-user Startup folder. No
REM PowerShell, no .lnk indirection -- each step ends with an `if exist`
REM check so you can see in the install log whether the file is really there.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_SERVER=%STARTUP_DIR%\SISI-TV.cmd"
set "STARTUP_VIEWER=%STARTUP_DIR%\SISI-TV Viewer.cmd"

echo.
if not exist "%STARTUP_DIR%" (
    echo [WARN] Startup folder does not exist: %STARTUP_DIR%
    echo        Skipping autostart configuration.
    goto :done
)

REM Remove any legacy .lnk shortcuts from previous PowerShell-based installs.
del "%STARTUP_DIR%\SISI-TV.lnk" >nul 2>&1
del "%STARTUP_DIR%\SISI-TV Viewer.lnk" >nul 2>&1

echo Writing server autostart stub to:
echo        %STARTUP_SERVER%
(
    echo @echo off
    echo cd /d "%~dp0"
    echo call "%~dp0start.bat"
) > "%STARTUP_SERVER%"
if exist "%STARTUP_SERVER%" (
    echo [ OK ] Server autostart created. Each login will git pull + launch SISI-TV.
) else (
    echo [FAIL] Could not create %STARTUP_SERVER%.
)

REM --- 7. Auto-start the fullscreen viewer (only if pywebview installed) ---
echo.
if "%VIEWER_INSTALLED%"=="1" (
    echo Writing viewer autostart stub to:
    echo        %STARTUP_VIEWER%
    (
        echo @echo off
        echo cd /d "%~dp0"
        echo start "" /min "%~dp0.venv\Scripts\sisi-tv-viewer.exe"
    ) > "%STARTUP_VIEWER%"
    if exist "%STARTUP_VIEWER%" (
        echo [ OK ] Viewer autostart created. Each login opens /grid fullscreen.
    ) else (
        echo [FAIL] Could not create %STARTUP_VIEWER%.
    )
) else (
    del "%STARTUP_VIEWER%" >nul 2>&1
    echo [SKIP] Viewer extra not installed; not creating the kiosk shortcut.
)

echo.
echo Startup folder contents:
dir /b "%STARTUP_DIR%" 2>nul
goto :done

:done
echo.
echo ============================================
echo   Install complete.
echo ============================================
echo.
echo Auto-start: SISI-TV.cmd and (if pywebview installed) SISI-TV Viewer.cmd
echo are in shell:startup, so the next login will git pull + launch the
echo server and open the /grid page fullscreen. To disable either,
echo delete the .cmd from shell:startup (paste in Win+R).
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
