# Create a Windows Startup folder shortcut that auto-launches the SISI-TV
# fullscreen viewer on login.
#
# The shortcut points at .venv\Scripts\sisi-tv-viewer.exe (built from the
# [project.gui-scripts] entry point so it has no console window). The viewer
# polls the local server until it responds, then opens /grid fullscreen.
#
# Re-running this script overwrites the existing shortcut, so it's safe to
# invoke from install.bat on repeat installs.

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $root '.venv\Scripts\sisi-tv-viewer.exe'

if (-not (Test-Path $target)) {
    Write-Error "sisi-tv-viewer.exe not found at $target. Run install.bat first."
    exit 1
}

$startupDir = [Environment]::GetFolderPath('Startup')
if (-not (Test-Path $startupDir)) {
    Write-Error "Startup folder not found: $startupDir"
    exit 1
}

$linkPath = Join-Path $startupDir 'SISI-TV Viewer.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # minimized -- no console window appears anyway, but
                           # this keeps focus from jumping during boot.
$shortcut.Description = 'SISI-TV: fullscreen camera grid viewer on login.'
$shortcut.IconLocation = (Join-Path $root 'src\ngc_cams_web\static\boy-sisi.png')
$shortcut.Save()

Write-Host "[ OK ] Viewer startup shortcut created:"
Write-Host "       $linkPath"
Write-Host "       -> $target"
