# Установка ПОДПИСАННОГО RemoteAdminAgent.exe на ПК сотрудника (от администратора).
# Python на целевом ПК НЕ нужен. Кладёт exe + config.json, ставит доверие к сертификату,
# регистрирует задачу автозапуска В СЕССИИ ПОЛЬЗОВАТЕЛЯ (иначе экран/ввод не работают — Session 0).
#
# Пример:
#   .\install_agent.ps1 -Server "ws://<server-host>:8765" -AgentKey "секрет" -User "ivanov"
param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$AgentKey,
  [string]$User = $env:USERNAME,
  [string]$ExeSource = "$PSScriptRoot\..\dist\RemoteAdminAgent.exe",
  [string]$CerSource = "$PSScriptRoot\..\build\certs\codesign.cer"
)
$ErrorActionPreference = "Stop"
$dst = "C:\ProgramData\RemoteAdmin"
New-Item -ItemType Directory -Force -Path $dst | Out-Null

# 1) доверие к нашему сертификату (чтобы Defender/SmartScreen не ругались)
if (Test-Path $CerSource) {
  Import-Certificate -FilePath $CerSource -CertStoreLocation "Cert:\LocalMachine\Root"             | Out-Null
  Import-Certificate -FilePath $CerSource -CertStoreLocation "Cert:\LocalMachine\TrustedPublisher"  | Out-Null
  Write-Host "Сертификат компании добавлен в доверенные."
} else {
  Write-Warning "Нет $CerSource — подпись будет недоверенной на этом ПК."
}

# 2) файлы агента + конфиг
Copy-Item $ExeSource (Join-Path $dst "RemoteAdminAgent.exe") -Force
@{ server = $Server; agent_key = $AgentKey } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $dst "config.json")

# 3) проверим, что подпись валидна на этой машине
$sig = Get-AuthenticodeSignature (Join-Path $dst "RemoteAdminAgent.exe")
Write-Host "Подпись exe: $($sig.Status)"

# 4) автозапуск в сессии пользователя (экран + мышь/клавиатура работают)
$exe = Join-Path $dst "RemoteAdminAgent.exe"
$action  = New-ScheduledTaskAction -Execute $exe
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName "RemoteAdminAgent" -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName "RemoteAdminAgent"

Write-Host "Готово. Агент установлен и запущен в сессии '$User', сервер $Server."
Write-Host "Удаление: Unregister-ScheduledTask RemoteAdminAgent -Confirm:`$false ; Remove-Item '$dst' -Recurse -Force"
