# Подписывает exe своим сертификатом + метка времени (подпись остаётся валидной после истечения серта).
# signtool НЕ нужен — используется встроенный в Windows Set-AuthenticodeSignature.
# Запуск:  cd build ;  .\3_sign.ps1 -Exe ..\dist\RemoteAdminAgent.exe
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [string]$Pfx = "$PSScriptRoot\certs\codesign.pfx",
  [string]$PfxPassword = "change-this-pfx-pass",
  [string]$TimestampUrl = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Exe)) { Write-Error "Нет файла: $Exe" }
if (-not (Test-Path $Pfx)) { Write-Error "Нет сертификата: $Pfx (сначала 1_make_cert.ps1)" }

# грузим pfx (совместимо с Windows PowerShell 5.1)
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
          $Pfx, $PfxPassword,
          [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)

$res = Set-AuthenticodeSignature -FilePath $Exe -Certificate $cert `
        -HashAlgorithm SHA256 -TimestampServer $TimestampUrl
Write-Host "Статус подписи: $($res.Status)"
Get-AuthenticodeSignature $Exe | Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
