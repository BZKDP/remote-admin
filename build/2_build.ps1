# Сборка RemoteAdminAgent.exe из agent.py через PyInstaller (без Python на целевых ПК).
# Запуск:  cd build ;  .\2_build.ps1
$ErrorActionPreference = "Stop"
$root  = Split-Path $PSScriptRoot -Parent
$agent = Join-Path $root "agent\agent.py"
$ver   = Join-Path $PSScriptRoot "version_info.txt"
$dist  = Join-Path $root "dist"
$work  = Join-Path $PSScriptRoot "work"

Write-Host "PyInstaller build..."
python -m PyInstaller `
  --onefile --noconsole --clean --noconfirm `
  --name RemoteAdminAgent `
  --version-file "$ver" `
  --distpath "$dist" --workpath "$work" --specpath "$PSScriptRoot" `
  --collect-submodules pynput `
  --collect-submodules mss `
  --hidden-import PIL `
  "$agent"

$exe = Join-Path $dist "RemoteAdminAgent.exe"
if (Test-Path $exe) {
  Write-Host "OK: $exe  ($([math]::Round((Get-Item $exe).Length/1MB,1)) MB)"
} else {
  Write-Error "Сборка не удалась"
}
