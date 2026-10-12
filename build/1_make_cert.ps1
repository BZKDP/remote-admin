# Создаёт СВОЙ code-signing сертификат компании (self-signed) и экспортирует:
#   certs\codesign.pfx  — приватный ключ для подписи (храни в секрете!)
#   certs\codesign.cer  — публичная часть для разворота на ПК сотрудников
# Запуск от обычного пользователя:  cd build ;  .\1_make_cert.ps1 -CompanyName "ООО Ромашка"
param(
  [string]$CompanyName = "Company IT",
  [string]$PfxPassword = "change-this-pfx-pass",
  [string]$OutDir = "$PSScriptRoot\certs"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$cert = New-SelfSignedCertificate `
  -Type CodeSigningCert `
  -Subject "CN=$CompanyName Code Signing, O=$CompanyName" `
  -KeyUsage DigitalSignature `
  -KeyAlgorithm RSA -KeyLength 3072 `
  -HashAlgorithm SHA256 `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears(5) `
  -FriendlyName "$CompanyName Code Signing"

$pfx = Join-Path $OutDir "codesign.pfx"
$cer = Join-Path $OutDir "codesign.cer"
$sec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $sec | Out-Null
Export-Certificate  -Cert $cert -FilePath $cer | Out-Null

Write-Host "Сертификат создан."
Write-Host "  Subject:    CN=$CompanyName Code Signing"
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  PFX: $pfx   (приватный ключ — не публиковать)"
Write-Host "  CER: $cer   (разворачивать на ПК сотрудников через deploy_cert.ps1 / GPO)"
