# Create a Windows Startup folder shortcut that auto-launches SISI-TV on login.
#
# The shortcut points at start.bat in the project root, which:
#   - git pull --ff-only
#   - .venv\Scripts\sisi-tv.exe
#
# The shortcut runs minimized (WindowStyle 7) so the console doesn't grab focus
# on every login. Re-running this script overwrites the existing shortcut, so
# it's safe to invoke from install.bat on repeat installs.

$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $root 'start.bat'

if (-not (Test-Path $target)) {
    Write-Error "start.bat not found at $target"
    exit 1
}

$startupDir = [Environment]::GetFolderPath('Startup')
if (-not (Test-Path $startupDir)) {
    Write-Error "Startup folder not found: $startupDir"
    exit 1
}

$linkPath = Join-Path $startupDir 'SISI-TV.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # minimized
$shortcut.Description = 'SISI-TV: pull latest and launch on login.'
$shortcut.IconLocation = (Join-Path $root 'src\ngc_cams_web\static\boy-sisi.png')
$shortcut.Save()

Write-Host "[ OK ] Startup shortcut created:"
Write-Host "       $linkPath"
Write-Host "       -> $target"
