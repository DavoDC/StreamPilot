# make-desktop-shortcut.ps1
# Creates the StreamPilot desktop shortcut. Safe to re-run any time - always
# removes any existing StreamPilot*.lnk on the Desktop first (clears out
# accidental duplicates, e.g. "StreamPilot (2).lnk" from a prior manual copy)
# then creates exactly one clean shortcut.
#
# Run: powershell -ExecutionPolicy Bypass -File "...\scripts\setup\make-desktop-shortcut.ps1"
# Verify: powershell -ExecutionPolicy Bypass -File "...\tests\test-desktop-shortcut.ps1"

$repoDir      = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$scriptsDir   = "$repoDir\scripts"
$runBat       = "$scriptsDir\run.bat"
$icoPath      = "$repoDir\assets\StreamPilotIconICO.ico"
$desktopShortcut = "$env:USERPROFILE\Desktop\StreamPilot.lnk"

if (-not (Test-Path $runBat)) {
    Write-Error "run.bat not found at $runBat"
    exit 1
}
if (-not (Test-Path $icoPath)) {
    Write-Error "Icon not found at $icoPath"
    exit 1
}

# --- Remove any existing StreamPilot shortcuts on the Desktop (incl. duplicates) ---
Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "StreamPilot*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "Removed: $($_.FullName)"
}

# --- Create shortcut ---
# run.bat is the single source of truth for launch args (currently --dashboard
# --watch, i.e. hot-reload dev mode is on by default) - the shortcut just
# points at it, so updating run.bat is enough to change what this launches.
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($desktopShortcut)
$s.TargetPath       = $runBat
$s.WorkingDirectory = $scriptsDir
$s.IconLocation     = "$icoPath,0"
$s.Description      = "Launch StreamPilot (hot-reload dev mode on by default - see run.bat)"
$s.Save()

Write-Host "StreamPilot shortcut created: $desktopShortcut"
Write-Host "Target: $runBat"
Write-Host "Done."
