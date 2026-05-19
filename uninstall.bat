@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo   SISI-TV uninstall
echo ============================================
echo Working dir: %CD%
echo.
echo This will:
echo   1. Stop sisi-tv.exe, sisi-tv-viewer.exe, ffmpeg.exe
echo   2. Remove the Startup-folder shortcuts so the app no longer
echo      launches on login
echo   3. Delete the .venv directory
echo   4. Optionally delete user data: settings, recordings,
echo      snapshots, DB
echo.
echo The git checkout itself ^(this folder^) is NOT removed -- delete it
echo manually after this script if you want a clean wipe.
echo.

choice /C YN /M "Proceed with uninstall"
if errorlevel 2 goto :cancelled

REM --- 1. Stop everything --------------------------------------------------
echo.
echo Stopping running processes...
taskkill /F /T /IM sisi-tv.exe        >nul 2>&1
taskkill /F /T /IM sisi-tv-viewer.exe >nul 2>&1
taskkill /F /IM    ffmpeg.exe         >nul 2>&1
echo [ OK ] Processes stopped or were not running.

REM --- 2. Remove Startup-folder shortcuts ---------------------------------
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo.
echo Removing autostart shortcuts from:
echo   %STARTUP_DIR%
del "%STARTUP_DIR%\SISI-TV.cmd"        >nul 2>&1
del "%STARTUP_DIR%\SISI-TV Viewer.cmd" >nul 2>&1
del "%STARTUP_DIR%\SISI-TV.lnk"        >nul 2>&1
del "%STARTUP_DIR%\SISI-TV Viewer.lnk" >nul 2>&1
echo [ OK ] Autostart shortcuts removed.

REM --- 3. Delete .venv -----------------------------------------------------
REM Goto pattern avoids nested if-blocks that would trip on parens in echo
REM lines (this is the same parser issue install.bat originally hit).
echo.
if not exist .venv goto :no_venv
echo Removing .venv ...
rmdir /s /q .venv
if exist .venv goto :venv_locked
echo [ OK ] .venv deleted.
goto :user_data

:no_venv
echo [SKIP] No .venv to remove.
goto :user_data

:venv_locked
echo [WARN] .venv could not be removed. A handle is still open --
echo        close any terminals / IDEs that still have the venv
echo        activated, then re-run this script.

REM --- 4. User data (optional, gated) -------------------------------------
:user_data
echo.
echo User-data locations:
set "STORAGE_ROOT=Z:\SISI-TV-storage\%COMPUTERNAME%"
set "SETTINGS_DIR=%USERPROFILE%\.ngc-cams"
set "HLS_CACHE=%TEMP%\sisi-tv-hls"
echo   Recordings + SQLite DB:  %STORAGE_ROOT%
echo   Settings overrides:      %SETTINGS_DIR%
echo   HLS scratch cache:       %HLS_CACHE%
echo.
choice /C YN /M "Also delete recordings + snapshots + DB at %STORAGE_ROOT%"
if errorlevel 2 goto :skip_storage
if not exist "%STORAGE_ROOT%" goto :storage_absent
echo Removing %STORAGE_ROOT% ...
rmdir /s /q "%STORAGE_ROOT%"
if exist "%STORAGE_ROOT%" goto :storage_locked
echo [ OK ] %STORAGE_ROOT% deleted.
goto :ask_settings

:storage_absent
echo [SKIP] %STORAGE_ROOT% does not exist.
goto :ask_settings

:storage_locked
echo [WARN] Could not remove %STORAGE_ROOT% -- in use or permission denied.
goto :ask_settings

:skip_storage
echo [SKIP] Recordings + DB preserved at %STORAGE_ROOT%.

:ask_settings
echo.
choice /C YN /M "Also delete settings overrides at %SETTINGS_DIR%"
if errorlevel 2 goto :skip_settings
if not exist "%SETTINGS_DIR%" goto :settings_absent
echo Removing %SETTINGS_DIR% ...
rmdir /s /q "%SETTINGS_DIR%"
if exist "%SETTINGS_DIR%" goto :settings_locked
echo [ OK ] %SETTINGS_DIR% deleted.
goto :clear_cache

:settings_absent
echo [SKIP] %SETTINGS_DIR% does not exist.
goto :clear_cache

:settings_locked
echo [WARN] Could not remove %SETTINGS_DIR%.
goto :clear_cache

:skip_settings
echo [SKIP] Settings preserved at %SETTINGS_DIR%.

:clear_cache
REM HLS scratch dir is always safe to remove -- transient .ts/.m3u8 files
REM regenerated on the next run. Done silently if missing.
if not exist "%HLS_CACHE%" goto :done
rmdir /s /q "%HLS_CACHE%" >nul 2>&1
if not exist "%HLS_CACHE%" echo [ OK ] HLS scratch cache cleared.

:done
echo.
echo ============================================
echo   SISI-TV uninstalled.
echo ============================================
echo.
echo To remove the git checkout itself, delete %CD% manually.
echo To reinstall, re-run install.bat from this directory.
echo.
endlocal
exit /b 0

:cancelled
echo.
echo Uninstall cancelled. Nothing was changed.
endlocal
exit /b 0
