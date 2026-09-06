param([string]$Rscript = $env:RSCRIPT)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Rscript)) {
  $command = Get-Command "Rscript" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $command) {
    Write-Output "run_r_definition no-install fixture SKIP: Rscript is not configured or on PATH"
    exit 0
  }
  $Rscript = $command.Source
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$runner = Join-Path $repoRoot "scripts\run_r_definition.ps1"
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) (
  "definition_runner_no_install_" + [guid]::NewGuid().ToString("N")
)

try {
  New-Item -ItemType Directory -Path $tempDir | Out-Null
  $scriptPath = Join-Path $tempDir "fixture.R"
  $publicPart = @'
library("devtools")
library("openxlsx")
library("dplyr")
install_github <- function(...) stop("INSTALL_RAN")
install_github("ZhidoHuang/dbCodeBookr") # setup only
library("dbCodeBookr")
'@
  $outputBoundary = "# " + [string][char]0x8F93 + [string][char]0x51FA
  $fixture = $publicPart + "`n`n" + $outputBoundary + @'

cat("RUN_OK\n")
'@
  [System.IO.File]::WriteAllText(
    $scriptPath,
    $fixture,
    [System.Text.UTF8Encoding]::new($false)
  )

  $missingCopyBlocked = $false
  try {
    & $runner `
      -WorkDir $tempDir `
      -Script "fixture.R" `
      -LogPrefix "fixture" `
      -Rscript $Rscript `
      -PreflightOnly *> $null
  }
  catch {
    $missingCopyBlocked = $_.Exception.Message -match "文案.md"
  }
  if (-not $missingCopyBlocked) {
    throw "Runner did not block a definition with no 文案.md."
  }

  [System.IO.File]::WriteAllText(
    (Join-Path $tempDir "文案.md"),
    "## 摘要导读`n<div class=`"styled`">正文</div>`n`n## Criteria`n规则`n`n## 小book提示`n边界`n`n## 参考资料说明`n来源`n",
    [System.Text.UTF8Encoding]::new($false)
  )
  $styledCopyBlocked = $false
  try {
    & $runner `
      -WorkDir $tempDir `
      -Script "fixture.R" `
      -LogPrefix "fixture" `
      -Rscript $Rscript `
      -PreflightOnly *> $null
  }
  catch {
    $styledCopyBlocked = $_.Exception.Message -match "plain reader text"
  }
  if (-not $styledCopyBlocked) {
    throw "Runner did not block styled HTML in 文案.md."
  }

  $readerCopy = @'
## 摘要导读
说明本主题定义什么、调查问了什么。

## Criteria
逐项说明分析变量怎样得到。

## 小book提示
说明会影响整个主题的使用边界。

## 参考资料说明
说明材料分别支持哪些事实。
'@
  [System.IO.File]::WriteAllText(
    (Join-Path $tempDir "文案.md"),
    $readerCopy,
    [System.Text.UTF8Encoding]::new($false)
  )

  $configPath = Join-Path $tempDir "config.json"
  @{ schema_version = 1; executables = @{ rscript = $Rscript } } |
    ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $configPath -Encoding UTF8
  $preflightOutput = & $runner `
    -WorkDir $tempDir `
    -Script "fixture.R" `
    -LogPrefix "fixture" `
    -Config $configPath `
    -PreflightOnly 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) {
    throw "Runner preflight fixture failed with exit code $LASTEXITCODE."
  }
  if ($preflightOutput -match "RUN_OK" -or $preflightOutput -match "INSTALL_RAN") {
    throw "Preflight-only mode executed the R definition."
  }
  if (Get-ChildItem -LiteralPath $tempDir -Filter "fixture_run_*.log" -File) {
    throw "Preflight-only mode created a formal-run log."
  }

  $badConfig = Join-Path $tempDir "bad-config.json"
  @{ schema_version = 1; executables = @{ rscript = "missing-Rscript.exe" } } |
    ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $badConfig -Encoding UTF8
  $invalidConfigBlocked = $false
  try {
    & $runner -WorkDir $tempDir -Script "fixture.R" -LogPrefix "fixture" -Config $badConfig -PreflightOnly *> $null
  } catch {
    $invalidConfigBlocked = $_.Exception.Message -match "Rscript does not exist"
  }
  if (-not $invalidConfigBlocked) { throw "Invalid configured executable was silently replaced." }

  & $runner -WorkDir $tempDir -Script "fixture.R" -LogPrefix "fixture" -Rscript $Rscript
  if ($LASTEXITCODE -ne 0) {
    throw "Runner fixture failed with exit code $LASTEXITCODE."
  }

  $log = Get-ChildItem -LiteralPath $tempDir -Filter "fixture_run_*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($null -eq $log) {
    throw "Runner fixture did not create a log."
  }
  $content = Get-Content -LiteralPath $log.FullName -Raw -Encoding UTF8
  if ($content -notmatch "RUN_OK" -or $content -match "INSTALL_RAN") {
    throw "Runner did not skip the package-install setup line."
  }
  Write-Output "run_r_definition no-install fixture PASS"
}
finally {
  Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
