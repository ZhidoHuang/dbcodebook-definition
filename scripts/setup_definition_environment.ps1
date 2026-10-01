param(
  [string]$Rscript = "",
  [string]$Config = "",
  [string]$Python = "",
  [switch]$InstallMissing,
  [switch]$UpdateDbCodeBookr
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'r_environment.ps1')
if (-not $Config) { $Config = $env:DBCODEBOOK_DEFINITION_CONFIG }
if (-not $Config) {
  $candidate = Join-Path (Split-Path -Parent $PSScriptRoot) 'config.local.json'
  if (Test-Path -LiteralPath $candidate) { $Config = $candidate }
}
if ($Config) {
  $Config = (Resolve-Path -LiteralPath $Config).Path
  $settings = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach ($name in @('rscript', 'python')) {
    if (-not (Get-Variable -Name $name -ValueOnly) -and $settings.executables.$name) {
      $value = [Environment]::ExpandEnvironmentVariables([string]$settings.executables.$name)
      if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path (Split-Path -Parent $Config) $value }
      Set-Variable -Name $name -Value $value
    }
  }
}
$rEnvironment = Start-DefinitionREnvironment -Config $Config -Python $Python
try {

if ([string]::IsNullOrWhiteSpace($Rscript)) {
  $command = Get-Command "Rscript" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $command) {
    throw "Rscript was not found on PATH and no explicit path was supplied."
  }
  $Rscript = $command.Source
} elseif (-not (Test-Path -LiteralPath $Rscript)) {
  throw "Rscript does not exist: $Rscript"
}

$cranPackages = @("devtools", "openxlsx", "dplyr", "tidyr", "jsonlite")
$quotedCranPackages = ($cranPackages | ForEach-Object { "'" + $_ + "'" }) -join ","
$installMissingValue = if ($InstallMissing) { "TRUE" } else { "FALSE" }
$updateDbCodeBookrValue = if ($UpdateDbCodeBookr) { "TRUE" } else { "FALSE" }

$expression = @"
cran_packages <- c($quotedCranPackages)
install_missing <- $installMissingValue
update_dbcodebookr <- $updateDbCodeBookrValue

missing_cran <- cran_packages[
  !vapply(cran_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_cran) && install_missing) {
  install.packages(missing_cran, repos = "https://cloud.r-project.org")
}

missing_cran <- cran_packages[
  !vapply(cran_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_cran)) {
  stop(paste0(
    "Missing CRAN packages: ", paste(missing_cran, collapse = ", "),
    ". Re-run this setup command with -InstallMissing."
  ))
}

dbcodebookr_installed <- requireNamespace("dbCodeBookr", quietly = TRUE)
if ((!dbcodebookr_installed && install_missing) || update_dbcodebookr) {
  devtools::install_github("ZhidoHuang/dbCodeBookr", upgrade = "never")
  dbcodebookr_installed <- requireNamespace("dbCodeBookr", quietly = TRUE)
}
if (!dbcodebookr_installed) {
  stop(
    "dbCodeBookr is not installed. Re-run this setup command with -InstallMissing."
  )
}

cat("Definition R environment is ready.\n")
cat(paste0(
  c(cran_packages, "dbCodeBookr"), "=",
  vapply(c(cran_packages, "dbCodeBookr"),
         function(pkg) as.character(utils::packageVersion(pkg)),
         character(1)),
  collapse = "\n"
))
cat("\n")
"@

$tempScript = Join-Path (
  $rEnvironment.TempRoot
) ("definition_environment_" + [guid]::NewGuid().ToString("N") + ".R")
try {
  [System.IO.File]::WriteAllText(
    $tempScript,
    $expression,
    [System.Text.UTF8Encoding]::new($false)
  )
  & $Rscript --vanilla --encoding=UTF-8 $tempScript
  if ($LASTEXITCODE -ne 0) {
    throw "Definition R environment setup/check failed."
  }
}
finally {
  Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
}

} finally { Stop-DefinitionREnvironment -State $rEnvironment }
