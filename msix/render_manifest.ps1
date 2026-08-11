param(
  [string]$Template,
  [string]$Out,
  [string]$Name,
  [string]$Publisher,
  [string]$PublisherDisplay,
  [string]$Version,
  [string]$MinVersion,
  [string]$MaxVersion
)
# KOTOBA-AI — 用配置值填充 AppxManifest.xml.tpl，输出 UTF-8 无 BOM 的正式清单
$ErrorActionPreference = 'Stop'
$t = Get-Content -Raw -Encoding UTF8 $Template
$map = @{
  '__NAME__'             = $Name
  '__PUBLISHER__'        = $Publisher
  '__PUBLISHER_DISPLAY__'= $PublisherDisplay
  '__VERSION__'          = $Version
  '__MIN_VERSION__'      = $MinVersion
  '__MAX_VERSION__'      = $MaxVersion
}
foreach ($k in $map.Keys) {
  $t = $t.Replace($k, $map[$k])
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($Out, $t, $utf8NoBom)
Write-Host "manifest -> $Out"
