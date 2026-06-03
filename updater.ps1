# Silent auto-updater helper for NEXRAD Radar.
# Launched (detached) by the running app right before it exits. It waits for the
# app to fully close so its files unlock, runs the downloaded installer silently,
# then relaunches the (now-updated) app.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File updater.ps1 -Installer <path> -AppExe <path>
param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][string]$AppExe
)
$ErrorActionPreference = 'SilentlyContinue'

$procName = [IO.Path]::GetFileNameWithoutExtension($AppExe)

# Wait (up to ~30 s) for every instance of the app to exit so its exe/_internal
# files are no longer locked by the running process.
for ($i = 0; $i -lt 60; $i++) {
    if (-not (Get-Process -Name $procName -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}
Start-Sleep -Milliseconds 700   # small grace for child processes to release handles

# Run the installer silently and WAIT for it to finish overwriting the files.
if (Test-Path $Installer) {
    try {
        Start-Process -FilePath $Installer `
            -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOCANCEL' `
            -Wait
    } catch { }
}

# Relaunch the app (the new version if the install succeeded; the old one if not,
# so the user is never left with nothing).
if (Test-Path $AppExe) {
    Start-Process -FilePath $AppExe
}

# Best-effort cleanup of the downloaded installer.
try { Remove-Item -Path $Installer -Force -ErrorAction SilentlyContinue } catch { }
