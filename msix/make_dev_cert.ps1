param(
  [string]$Publisher,   # 例如 "CN=KOTOBA-AI Local Test"（与清单 Publisher 一致才可本机安装）
  [string]$Password,    # 导出 pfx 的口令
  [string]$CertDir      # 输出 dev_cert.pfx / dev_cert.cer 的目录
)
# KOTOBA-AI — 生成本地测试用自签名代码签名证书。
# 仅用于本机真机验证；上架版由微软用官方证书重签，本证书与之无关。
$ErrorActionPreference = 'Stop'

$cn = if ($Publisher -like 'CN=*') {
  $Publisher.Substring(3).Split(',')[0].Trim()
} else {
  $Publisher.Trim()
}

$pfx  = Join-Path $CertDir 'dev_cert.pfx'
$cer  = Join-Path $CertDir 'dev_cert.cer'
$store = 'Cert:\CurrentUser\My'

$cert = Get-ChildItem $store | Where-Object { $_.Subject -eq ('CN=' + $cn) } | Select-Object -First 1
if (-not $cert) {
  # Code Signing EKU (2.5.29.37=...3.3)，否则 signtool 拒绝使用该证书
  $cert = New-SelfSignedCertificate -Type Custom `
    -Subject ('CN=' + $cn) `
    -KeyUsage DigitalSignature `
    -FriendlyName ('KOTOBA-AI ' + $cn) `
    -CertStoreLocation $store `
    -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3') `
    -NotAfter ((Get-Date).AddYears(3))
  Write-Host ("created self-signed cert CN=" + $cn)
} else {
  Write-Host ("reusing existing cert CN=" + $cn)
}

$secure = ConvertTo-SecureString -String $Password -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $secure | Out-Null
Export-Certificate -Cert $cert -FilePath $cer -Type CERT | Out-Null
Write-Host "cert ok: $pfx"
