# test-desktop-shortcut.ps1
# Verifies the StreamPilot desktop shortcut is correctly configured.
# Run after scripts/setup/make-desktop-shortcut.ps1 to confirm everything is wired up.

$pass = 0
$fail = 0

function Assert($label, $condition, $detail = "") {
    if ($condition) {
        Write-Host "  PASS  $label" -ForegroundColor Green
        $script:pass++
    } else {
        $msg = if ($detail) { "  FAIL  $label -- $detail" } else { "  FAIL  $label" }
        Write-Host $msg -ForegroundColor Red
        $script:fail++
    }
}

$repoDir      = Split-Path -Parent $PSScriptRoot
$runBat       = "$repoDir\scripts\run.bat"
$icoPath      = "$repoDir\assets\StreamPilotIconICO.ico"
$desktopShortcut = "$env:USERPROFILE\Desktop\StreamPilot.lnk"

Write-Host "`nStreamPilot shortcut tests`n" -ForegroundColor Cyan

Assert "run.bat exists"              (Test-Path $runBat)          $runBat
Assert "Icon exists"                 (Test-Path $icoPath)         $icoPath
Assert "Desktop shortcut exists"     (Test-Path $desktopShortcut) $desktopShortcut

$dupes = Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "StreamPilot*.lnk" -ErrorAction SilentlyContinue
Assert "No duplicate StreamPilot shortcuts" ($dupes.Count -eq 1) "Found $($dupes.Count): $($dupes.Name -join ', ')"

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($desktopShortcut)
Assert "Shortcut target is run.bat"  ($sc.TargetPath -eq $runBat)           "Got: $($sc.TargetPath)"
Assert "Icon set correctly"          ($sc.IconLocation -like "*$([System.IO.Path]::GetFileName($icoPath))*") "Got: $($sc.IconLocation)"

$runBatContent = Get-Content $runBat -Raw
Assert "run.bat launches with --watch (hot-reload on by default)" ($runBatContent -match '--watch')
Assert "run.bat still opens the dashboard"                        ($runBatContent -match '--dashboard')

Write-Host "`n$pass passed, $fail failed`n" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })

Read-Host "Press Enter to close"

if ($fail -gt 0) { exit 1 }
