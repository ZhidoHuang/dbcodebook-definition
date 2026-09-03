param([string]$Config = "")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
if ([string]::IsNullOrWhiteSpace($Config)) {
  $candidate = Join-Path $repoRoot "config.local.json"
  if (Test-Path -LiteralPath $candidate) {
    $Config = $candidate
  }
}

$configuredPython = ""
$configuredRscript = ""
if (-not [string]::IsNullOrWhiteSpace($Config)) {
  $settings = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
  $configuredPython = [string]$settings.executables.python
  $configuredRscript = [string]$settings.executables.rscript
}

$pythonArguments = @()
if (-not [string]::IsNullOrWhiteSpace($configuredPython)) {
  $python = $configuredPython
} else {
  $command = Get-Command "py" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $command) {
    $python = $command.Source
    $pythonArguments = @("-3")
  } else {
    $command = Get-Command "python3", "python" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "Python was not found." }
    $python = $command.Source
  }
}

if (-not [string]::IsNullOrWhiteSpace($configuredRscript)) {
  $rscript = $configuredRscript
} else {
  $command = Get-Command "Rscript" -ErrorAction SilentlyContinue | Select-Object -First 1
  $rscript = if ($null -eq $command) { "" } else { $command.Source }
}

$env:PYTHONUTF8 = "1"
if (-not [string]::IsNullOrWhiteSpace($rscript)) {
  $env:RSCRIPT = $rscript
}

$pythonTests = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "test_*.py" | Sort-Object Name
foreach ($test in $pythonTests) {
  Write-Output "RUN $($test.Name)"
  & $python @pythonArguments $test.FullName
  if ($LASTEXITCODE -ne 0) { throw "$($test.Name) failed." }
}

if (-not [string]::IsNullOrWhiteSpace($rscript)) {
  & (Join-Path $PSScriptRoot "test_run_r_definition_no_install.ps1") -Rscript $rscript
  if ($LASTEXITCODE -ne 0) { throw "test_run_r_definition_no_install.ps1 failed." }

  Remove-Item Env:LC_ALL -ErrorAction SilentlyContinue
  Remove-Item Env:LANG -ErrorAction SilentlyContinue
  Remove-Item Env:LC_CTYPE -ErrorAction SilentlyContinue
  & $rscript --vanilla --encoding=UTF-8 (Join-Path $PSScriptRoot "test_summary_fact_helpers.R")
  if ($LASTEXITCODE -ne 0) { throw "test_summary_fact_helpers.R failed." }
} else {
  Write-Output "R_TESTS_SKIP: Rscript is not configured or on PATH"
}

Write-Output "ALL_SKILL_TESTS_PASS"
