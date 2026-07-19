# make-desktop-shortcut.ps1
# Creates two StreamPilot desktop shortcuts - one to drag to each monitor, so
# David can launch from whichever screen he's looking at (same multi-copy
# pattern as the Claude Code shortcut maker in the workspace repo). Safe to
# re-run any time - always removes any existing StreamPilot*.lnk on the
# Desktop first (clears out stray duplicates), then creates exactly the two
# named below. Explicitly named (not left to Windows' auto "(2)" suffix) so
# there's never ambiguity about which files are real - an auto-suffixed
# duplicate left a 0-byte ghost icon in Explorer's cache after deletion once.
#
# Run: powershell -ExecutionPolicy Bypass -File "...\scripts\setup\make-desktop-shortcut.ps1"
# Verify: powershell -ExecutionPolicy Bypass -File "...\tests\test-desktop-shortcut.ps1"

$repoDir      = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$scriptsDir   = "$repoDir\scripts"
$runBat       = "$scriptsDir\run.bat"
$icoPath      = "$repoDir\assets\StreamPilotIconICO.ico"
$shortcutNames = @("StreamPilot.lnk", "StreamPilot 2.lnk")

if (-not (Test-Path $runBat)) {
    Write-Error "run.bat not found at $runBat"
    exit 1
}
if (-not (Test-Path $icoPath)) {
    Write-Error "Icon not found at $icoPath"
    exit 1
}

# --- Remove any existing StreamPilot shortcuts on the Desktop (incl. stray duplicates) ---
Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "StreamPilot*.lnk" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "Removed: $($_.FullName)"
}

# --- Create both shortcuts ---
# run.bat is the single source of truth for launch args (currently --dashboard
# --watch, i.e. hot-reload dev mode is on by default) - both shortcuts just
# point at it, so updating run.bat is enough to change what they launch.
$shell = New-Object -ComObject WScript.Shell
foreach ($name in $shortcutNames) {
    $path = "$env:USERPROFILE\Desktop\$name"
    $s = $shell.CreateShortcut($path)
    $s.TargetPath       = $runBat
    $s.WorkingDirectory = $scriptsDir
    $s.IconLocation     = "$icoPath,0"
    $s.Description      = "Launch StreamPilot (hot-reload dev mode on by default - see run.bat)"
    $s.Save()
    Write-Host "Created: $path"
}

Write-Host "Target: $runBat"
Write-Host "Done."
