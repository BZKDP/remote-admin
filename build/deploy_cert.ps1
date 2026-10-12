# Разворот публичного сертификата компании на ПК сотрудника (запускать от администратора).
# После этого Windows/Defender/SmartScreen доверяют подписи нашего агента.
# Для парка машин лучше раздать этот .cer через GPO:
#   Computer Config > Policies > Windows Settings > Security Settings > Public Key Policies
#     -> Trusted Root Certification Authorities  (импорт codesign.cer)
#     -> Trusted Publishers                      (импорт codesign.cer)
param(
  [string]$Cer = "$PSScriptRoot\certs\codesign.cer"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Cer)) { Write-Error "Нет файла сертификата: $Cer" }

Import-Certificate -FilePath $Cer -CertStoreLocation "Cert:\LocalMachine\Root"            | Out-Null
Import-Certificate -FilePath $Cer -CertStoreLocation "Cert:\LocalMachine\TrustedPublisher" | Out-Null
Write-Host "Сертификат установлен в Trusted Root + Trusted Publisher. Подпись агента теперь доверенная."
