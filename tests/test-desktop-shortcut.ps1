# test-desktop-shortcut.ps1
# Verifies the two StreamPilot desktop shortcuts (one per monitor) are
# correctly configured. Run after scripts/setup/make-desktop-shortcut.ps1 to
# confirm everything is wired up.

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
$expectedNames = @("StreamPilot.lnk", "StreamPilot (2).lnk")

Write-Host "`nStreamPilot shortcut tests`n" -ForegroundColor Cyan

Assert "run.bat exists"  (Test-Path $runBat)  $runBat
Assert "Icon exists"     (Test-Path $icoPath) $icoPath

$found = Get-ChildItem "$env:USERPROFILE\Desktop" -Filter "StreamPilot*.lnk" -ErrorAction SilentlyContinue
Assert "Exactly 2 StreamPilot shortcuts (one per monitor)" ($found.Count -eq 2) "Found $($found.Count): $($found.Name -join ', ')"

$shell = New-Object -ComObject WScript.Shell
foreach ($name in $expectedNames) {
    $path = "$env:USERPROFILE\Desktop\$name"
    Assert "$name exists" (Test-Path $path) $path
    if (Test-Path $path) {
        $sc = $shell.CreateShortcut($path)
        Assert "$name target is run.bat" ($sc.TargetPath -eq $runBat) "Got: $($sc.TargetPath)"
        Assert "$name icon set correctly" ($sc.IconLocation -like "*$([System.IO.Path]::GetFileName($icoPath))*") "Got: $($sc.IconLocation)"
    }
}

$runBatContent = Get-Content $runBat -Raw
Assert "run.bat launches with --watch (hot-reload on by default)" ($runBatContent -match '--watch')
Assert "run.bat still opens the dashboard"                        ($runBatContent -match '--dashboard')

Write-Host "`n$pass passed, $fail failed`n" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })

Read-Host "Press Enter to close"

if ($fail -gt 0) { exit 1 }
