@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo   SISI-TV autostart
echo ============================================
echo %DATE% %TIME%
echo Working dir: %CD%
echo.

REM --- Pull latest code -----------------------------------------------------
REM `git pull --ff-only` won't merge or rebase; if there are local commits or
REM merge conflicts it just no-ops and we still launch the existing checkout.
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] git is not on PATH. Skipping update.
    goto :launch
)

echo Pulling latest from origin/main ...
git pull --ff-only
if errorlevel 1 (
    echo [WARN] git pull failed. Continuing with current checkout.
) else (
    echo [ OK ] Repo up to date.
)

:launch
REM --- Launch the app -------------------------------------------------------
if not exist ".venv\Scripts\sisi-tv.exe" (
    echo [FAIL] .venv\Scripts\sisi-tv.exe not found.
    echo        Run install.bat first to set up the virtual environment.
    pause
    exit /b 1
)

echo Launching SISI-TV ...
".venv\Scripts\sisi-tv.exe"
endlocal
