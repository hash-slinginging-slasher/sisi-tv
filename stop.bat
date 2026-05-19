@echo off
setlocal EnableExtensions

echo ============================================
echo   SISI-TV stop
echo ============================================
echo.

REM Kill the uvicorn launcher (the venv shim that runs the FastAPI app).
REM /F = force, /T = also kill children. taskkill returns 128 when nothing
REM matched; we treat that as success ("already stopped").
echo Stopping SISI-TV server (sisi-tv.exe)...
taskkill /F /T /IM sisi-tv.exe >nul 2>&1
if errorlevel 1 (
    echo [ OK ] No sisi-tv.exe was running.
) else (
    echo [ OK ] sisi-tv.exe stopped.
)

REM Kill the optional pywebview kiosk window if it was launched.
echo Stopping SISI-TV viewer (sisi-tv-viewer.exe)...
taskkill /F /T /IM sisi-tv-viewer.exe >nul 2>&1
if errorlevel 1 (
    echo [ OK ] No sisi-tv-viewer.exe was running.
) else (
    echo [ OK ] sisi-tv-viewer.exe stopped.
)

REM Kill orphan ffmpeg children: the recording manager and HLS manager spawn
REM ffmpeg per camera. They normally exit when their parent uvicorn dies, but
REM the lifespan shutdown is bounded at 5s -- anything that didn't terminate
REM by then is orphaned. /T isn't useful here (ffmpeg has no children we
REM care about), so just target the image name.
echo Cleaning up orphan ffmpeg processes...
taskkill /F /IM ffmpeg.exe >nul 2>&1
if errorlevel 1 (
    echo [ OK ] No ffmpeg.exe was running.
) else (
    echo [ OK ] ffmpeg.exe stopped.
)

echo.
echo ============================================
echo   SISI-TV stopped.
echo ============================================
echo.
echo To start again:
echo   start.bat                      ^(also runs git pull first^)
echo   .venv\Scripts\sisi-tv.exe      ^(skips git pull^)
echo.
endlocal
exit /b 0
