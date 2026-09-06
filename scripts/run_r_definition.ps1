#requires -Version 7.0
param(
  [Parameter(Mandatory = $true)]
  [string]$WorkDir,

  [Parameter(Mandatory = $true)]
  [string]$Script,

  [Parameter(Mandatory = $true)]
  [string]$LogPrefix,

  [string]$Rscript = "",

  [string]$Python = "",

  [string]$Config = "",

  [string]$Database = "",

  [string]$ProcessDir = "",

  [string]$SourceChecker = "",

  [string]$ArchiveDir = "",

  [switch]$NoArchiveOldLogs,

  [switch]$PreflightOnly,

  [ValidateRange(1, 1440)]
  [int]$TimeoutMinutes = 30
)

$ErrorActionPreference = "Stop"

$skillRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Config)) {
  $Config = $env:DBCODEBOOK_DEFINITION_CONFIG
  if ([string]::IsNullOrWhiteSpace($Config)) {
    $candidate = Join-Path $skillRoot "config.local.json"
    if (Test-Path -LiteralPath $candidate) { $Config = $candidate }
  }
}
if (-not [string]::IsNullOrWhiteSpace($Config)) {
  $configPath = (Resolve-Path -LiteralPath $Config -ErrorAction Stop).Path
  $settings = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($settings.schema_version -ne 1) { throw "Configuration schema_version must be 1." }
  foreach ($name in @("rscript", "python")) {
    $configured = [string]$settings.executables.$name
    if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $name -ValueOnly)) -and $configured) {
      $configured = [Environment]::ExpandEnvironmentVariables($configured)
      if (-not [System.IO.Path]::IsPathRooted($configured)) {
        $configured = Join-Path (Split-Path -Parent $configPath) $configured
      }
      Set-Variable -Name $name -Value $configured
    }
  }
}

# Codex may expose the Linux locale name C.UTF-8. Windows R cannot use that
# locale and may rewrite Chinese punctuation as <U+....>. Let R select the
# machine's native UTF-8 locale instead.
Remove-Item Env:LC_ALL -ErrorAction SilentlyContinue
Remove-Item Env:LANG -ErrorAction SilentlyContinue
Remove-Item Env:LC_CTYPE -ErrorAction SilentlyContinue

$overallWatch = [System.Diagnostics.Stopwatch]::StartNew()
$phaseSeconds = [ordered]@{}

function Format-Duration {
  param([Parameter(Mandatory = $true)][double]$Seconds)
  return ("{0:N2} s" -f $Seconds)
}

function Resolve-RequiredPath {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Kind
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "$Kind does not exist: $Path"
  }
  return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-Executable {
  param(
    [string]$Configured,
    [Parameter(Mandatory = $true)][string[]]$Candidates,
    [Parameter(Mandatory = $true)][string]$Kind
  )

  if (-not [string]::IsNullOrWhiteSpace($Configured)) {
    return Resolve-RequiredPath -Path $Configured -Kind $Kind
  }
  foreach ($candidate in $Candidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) {
      return $command.Source
    }
  }
  throw "$Kind was not found on PATH and no explicit path was supplied."
}

function Invoke-RCode {
  param(
    [Parameter(Mandatory = $true)][string]$RscriptPath,
    [Parameter(Mandatory = $true)][string]$Code,
    [Parameter(Mandatory = $true)][string]$FailureMessage
  )

  $tempScript = Join-Path (
    [System.IO.Path]::GetTempPath()
  ) ("definition_preflight_" + [guid]::NewGuid().ToString("N") + ".R")
  try {
    [System.IO.File]::WriteAllText(
      $tempScript,
      $Code,
      [System.Text.UTF8Encoding]::new($false)
    )
    & $RscriptPath --vanilla --encoding=UTF-8 $tempScript
    if ($LASTEXITCODE -ne 0) {
      throw $FailureMessage
    }
  }
  finally {
    Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
  }
}

$resolvedWorkDir = Resolve-RequiredPath -Path $WorkDir -Kind "WorkDir"
$scriptPath = if ([System.IO.Path]::IsPathRooted($Script)) {
  $Script
} else {
  Join-Path $resolvedWorkDir $Script
}
$resolvedScript = Resolve-RequiredPath -Path $scriptPath -Kind "R script"
$scriptRelative = [System.IO.Path]::GetRelativePath($resolvedWorkDir, $resolvedScript)
if ($scriptRelative -eq ".." -or $scriptRelative.StartsWith(".." + [System.IO.Path]::DirectorySeparatorChar) -or [System.IO.Path]::IsPathRooted($scriptRelative)) {
  throw "R script must be inside WorkDir; run the current formal source, not a scratch copy."
}
$resolvedRscript = Resolve-Executable -Configured $Rscript -Candidates @("Rscript") -Kind "Rscript"
$env:DBCODEBOOK_DEFINITION_SKILL_ROOT = Split-Path -Parent $PSScriptRoot

$staticWatch = [System.Diagnostics.Stopwatch]::StartNew()
$scriptText = [System.IO.File]::ReadAllText($resolvedScript, [System.Text.Encoding]::UTF8)
$publicBoundary = [regex]::Match($scriptText, '(?m)^# \u8F93\u51FA\s*$')
if (-not $publicBoundary.Success) {
  throw "Public R boundary is missing."
}
$publicSource = $scriptText.Substring(0, $publicBoundary.Index)
$publicIssues = [System.Collections.Generic.List[string]]::new()
$databaseRoot = if ([string]::IsNullOrWhiteSpace($Database)) {
  Split-Path -Leaf (Split-Path -Parent $resolvedWorkDir)
} else {
  $Database
}
$isCharls = $databaseRoot -eq "CHARLS"

if ($publicSource -match '(?m)^names\(dt\)\[1\]\s*<-\s*["'']ID["'']\s*$') {
  $publicIssues.Add('Remove redundant names(dt)[1] <- "ID".')
}
if ($publicSource -match '(?m)^names\(name_z\)\[1\]\s*<-\s*["'']Easy\.label["'']\s*$') {
  $publicIssues.Add('Remove redundant names(name_z)[1] <- "Easy.label".')
}
if ($publicSource -match '\[\[\s*["'']Easy label["'']\s*\]\]') {
  $publicIssues.Add('read.csv normalizes "Easy label" to "Easy.label". Use the normalized column name.')
}

$usesCheckNamesFalse = $publicSource -match '(?is)read\.csv\([^)]*check\.names\s*=\s*FALSE'
if ($usesCheckNamesFalse) {
  $publicIssues.Add('read.csv(check.names = FALSE) is forbidden. Assign unique aliases in dbCodeBook before download.')
}

if ($isCharls) {
  $rawDataPath = Join-Path $resolvedWorkDir 'raw_data.csv'
  if (Test-Path -LiteralPath $rawDataPath) {
    $rawHeader = [System.IO.File]::ReadLines($rawDataPath, [System.Text.Encoding]::UTF8) |
      Select-Object -First 1
    $rawHeaderCounts = [System.Collections.Generic.Dictionary[string, int]]::new(
      [System.StringComparer]::Ordinal
    )
    foreach ($columnName in $rawHeader.Split(',')) {
      if ($rawHeaderCounts.ContainsKey($columnName)) {
        $rawHeaderCounts[$columnName]++
      } else {
        $rawHeaderCounts[$columnName] = 1
      }
    }
    $duplicateRawHeader = @(
      $rawHeaderCounts.GetEnumerator() |
        Where-Object { $_.Value -gt 1 } |
        ForEach-Object { $_.Key }
    )
    if ($duplicateRawHeader) {
      $publicIssues.Add(
        "raw_data.csv contains duplicate columns. Assign unique aliases in dbCodeBook before download: $($duplicateRawHeader -join ', ')"
      )
    }
  }
  $hasSimpleCodebookRead = $publicSource.Contains('name_z <- read.csv("raw_codebook.csv")')
  if (-not $hasSimpleCodebookRead) {
    $publicIssues.Add(
      'CHARLS public R must read raw_codebook.csv without extra options.'
    )
  }
  $hasSimpleDataRead = $publicSource.Contains('dt <- read.csv("raw_data.csv")')
  $hasHouseholdDataRead = $publicSource.Contains(
    'colClasses = c(householdid = "character", id = "character")'
  )
  $hasPersonDataRead = $publicSource.Contains(
    'colClasses = c(id = "character")'
  )
  $hasCommunityDataRead = $publicSource.Contains(
    'colClasses = c(communityid = "character")'
  )
  if (-not ($hasSimpleDataRead -or $hasPersonDataRead -or $hasHouseholdDataRead -or $hasCommunityDataRead)) {
    $publicIssues.Add(
      'CHARLS public R must use the simple read, except that person/household/community identity columns may be preserved as character.'
    )
  }
  if ($publicSource -match '(?m)^names\((?:data|dt)\)\s*\[[^\]]+\]\s*<-') {
    $publicIssues.Add(
      'CHARLS public R must not rename raw columns by position. Assign unique aliases in dbCodeBook before download.'
    )
  }
  if ($publicSource -match 'read\.csv\(\s*["'']raw_(?:data|codebook)\.csv["''][^)]*(?:(?<!file)encoding|col\.names)\s*=') {
    $publicIssues.Add('CHARLS public raw reads must not add encoding or column-name options.')
  }
  if ($publicSource -match '(?is)read\.csv\(\s*["'']raw_(?:data|codebook)\.csv["''][^)]*?(?:fileEncoding|na\.strings)\s*=') {
    $publicIssues.Add(
      'CHARLS public raw reads must not add fileEncoding or na.strings; use the shared empty-string step after reading.'
    )
  }
}

if ($publicSource -match '(?m)^raw_row_count\s*<-\s*nrow\(data\)\s*$') {
  $publicIssues.Add('Background raw_row_count leaked into public R.')
}
if ($publicSource -match '(?m)^raw_vars\s*<-\s*name_z\$newname\s*$') {
  $publicIssues.Add('raw_vars detours through raw_codebook in public R.')
}
if ($publicSource -match '(?m)^if\s*\(\s*!"id"\s*%in%\s*names\((?:data|dt)\)\s*\)\s*\{') {
  $publicIssues.Add('Defensive id fallback leaked into public R.')
}
if ($publicSource -match '(?ms)^data\s*<-\s*data\s*%>%\s*\n?\s*filter\(year\s*%in%') {
  $publicIssues.Add('Global target-wave filter belongs at the formal output boundary, not the read block.')
}

$requiredPublicHeader = @(
  'library("openxlsx")',
  'library("dplyr")',
  'library("dbCodeBookr")'
)
foreach ($token in $requiredPublicHeader) {
  if (-not $publicSource.Contains($token)) {
    $publicIssues.Add("Missing fixed public R header token: $token")
  }
}

if ($publicSource -match '(?is)for\s*\(\s*pkg\s+in\s+c\([^)]*["'']dbCodeBookr["'']') {
  $publicIssues.Add('Do not place dbCodeBookr in the generic package loop.')
}

if ($publicSource -match '(?mi)^#\s*raw_data\.csv.*dbcodebook\.cn.*Go to.*$') {
  $publicIssues.Add('Remove the reader-facing raw_data.csv guide from formal definition R.')
}

$publicLines = $publicSource -split "`r?`n"
for ($lineIndex = 0; $lineIndex -lt $publicLines.Count; $lineIndex++) {
  $recodeMatch = [regex]::Match(
    $publicLines[$lineIndex],
    '^\s*#\s*recode\.(chr|num)\(([^)]+)\)\s*$'
  )
  if (-not $recodeMatch.Success) {
    continue
  }
  $recodeKind = $recodeMatch.Groups[1].Value
  $recodeTarget = $recodeMatch.Groups[2].Value.Trim()
  $nextIndex = $lineIndex + 1
  while ($nextIndex -lt $publicLines.Count -and [string]::IsNullOrWhiteSpace($publicLines[$nextIndex])) {
    $nextIndex++
  }
  if ($nextIndex -ge $publicLines.Count) {
    $publicIssues.Add("Orphan recode.$recodeKind marker for $recodeTarget.")
    continue
  }
  $assignmentPattern = '^\s*' + [regex]::Escape($recodeTarget) + '\s*<-'
  if ($publicLines[$nextIndex] -notmatch $assignmentPattern) {
    $publicIssues.Add("recode.$recodeKind marker target differs from assignment: $recodeTarget")
    continue
  }
  $blockLines = [System.Collections.Generic.List[string]]::new()
  for ($blockIndex = $nextIndex; $blockIndex -lt $publicLines.Count; $blockIndex++) {
    $blockLines.Add($publicLines[$blockIndex])
    if ($blockIndex -gt $nextIndex -and $publicLines[$blockIndex] -match '^\s*\)\)?\s*$') {
      break
    }
  }
  $blockText = $blockLines -join "`n"
  $targetCount = [regex]::Matches($blockText, [regex]::Escape($recodeTarget)).Count
  if ($targetCount -lt 2) {
    $publicIssues.Add("recode.$recodeKind marker does not recode its own target: $recodeTarget")
  }
}

if ($publicIssues.Count -gt 0) {
  throw "Public R preflight failed:`n- $($publicIssues -join "`n- ")"
}
$staticWatch.Stop()
$phaseSeconds["Static checks"] = $staticWatch.Elapsed.TotalSeconds

$readerCopyWatch = [System.Diagnostics.Stopwatch]::StartNew()
$readerCopyPath = Join-Path $resolvedWorkDir "文案.md"
$resolvedReaderCopy = Resolve-RequiredPath -Path $readerCopyPath -Kind "Plain reader copy 文案.md"
$readerCopyText = [System.IO.File]::ReadAllText(
  $resolvedReaderCopy,
  [System.Text.Encoding]::UTF8
)
$requiredReaderCopyHeadings = @(
  "## 摘要导读",
  "## Criteria",
  "## 小book提示",
  "## 参考资料说明"
)
foreach ($heading in $requiredReaderCopyHeadings) {
  if (-not $readerCopyText.Contains($heading)) {
    throw "文案.md is missing required heading: $heading"
  }
}
if ($readerCopyText -match '(?is)<(?:div|span|section|style)\b|(?:class|style)\s*=') {
  throw "文案.md must contain plain reader text only. Remove HTML, class, color, and style markup before formal R execution."
}
$readerCopyWatch.Stop()
$phaseSeconds["Reader copy check"] = $readerCopyWatch.Elapsed.TotalSeconds

$packageWatch = [System.Diagnostics.Stopwatch]::StartNew()
$libraryMatches = [regex]::Matches(
  $publicSource,
  '(?m)^\s*library\(\s*["'']([^"'']+)["'']\s*\)'
)
$requiredRPackages = @(
  $libraryMatches |
    ForEach-Object { $_.Groups[1].Value } |
    Sort-Object -Unique
)
if ($requiredRPackages.Count -gt 0) {
  $quotedPackages = @(
    $requiredRPackages |
      ForEach-Object { "'" + $_.Replace("'", "\\'") + "'" }
  ) -join ','
  $packageCheckExpression = @"
packages <- c($quotedPackages)
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop(paste0(
    "Missing installed R packages: ", paste(missing, collapse = ", "),
    ". Run setup_definition_environment.ps1 before the formal definition."
  ))
}
"@
  Invoke-RCode `
    -RscriptPath $resolvedRscript `
    -Code $packageCheckExpression `
    -FailureMessage "R package preflight failed. Formal definitions never install packages while running."
}
$packageWatch.Stop()
$phaseSeconds["Package check"] = $packageWatch.Elapsed.TotalSeconds

$topicLeaf = Split-Path -Leaf $resolvedWorkDir
$defaultSourceChecker = Join-Path $PSScriptRoot "check_definition_source_record.py"
$sourceCheckerPath = if ([string]::IsNullOrWhiteSpace($SourceChecker)) {
  $defaultSourceChecker
} else {
  $SourceChecker
}

$sourceWatch = [System.Diagnostics.Stopwatch]::StartNew()
if ($topicLeaf -match '^(\d{3})_') {
  $topicId = $Matches[1]
  $resolvedPython = Resolve-Executable -Configured $Python -Candidates @("py", "python", "python3") -Kind "Python"
  $pythonArguments = @()
  if ((Split-Path -Leaf $resolvedPython) -ieq "py.exe") {
    $pythonArguments = @("-3")
  }
  if ([string]::IsNullOrWhiteSpace($ProcessDir)) {
    throw "ProcessDir is required for a numbered definition topic."
  }
  $sourceRecord = Join-Path $ProcessDir "definition_search_record.json"
  $rawCodebook = Join-Path $resolvedWorkDir "raw_codebook.csv"

  $resolvedSourceRecord = Resolve-RequiredPath -Path $sourceRecord -Kind "Definition source-search record"
  $resolvedSourceChecker = Resolve-RequiredPath -Path $sourceCheckerPath -Kind "Definition source-record checker"
  $resolvedRawCodebook = Resolve-RequiredPath -Path $rawCodebook -Kind "raw_codebook.csv"

  & $resolvedPython @pythonArguments $resolvedSourceChecker `
    --record $resolvedSourceRecord `
    --r-script $resolvedScript `
    --raw-codebook $resolvedRawCodebook `
    --formal-dir $resolvedWorkDir `
    --topic-id $topicId
  if ($LASTEXITCODE -ne 0) {
    throw "Definition source/download gate failed. The final source list, raw codebook, extracted CSV files, and original download zip must agree before formal R execution."
  }

}
$sourceWatch.Stop()
$phaseSeconds["Source check"] = $sourceWatch.Elapsed.TotalSeconds

$scriptBytes = [System.IO.File]::ReadAllBytes($resolvedScript)
if ($scriptBytes.Length -ge 3 -and $scriptBytes[0] -eq 0xEF -and $scriptBytes[1] -eq 0xBB -and $scriptBytes[2] -eq 0xBF) {
  throw "R script has a UTF-8 BOM. Rewrite it as UTF-8 without BOM before running: $resolvedScript"
}

if ($PreflightOnly) {
  $overallWatch.Stop()
  Write-Output "Definition preflight completed successfully."
  foreach ($phase in $phaseSeconds.GetEnumerator()) {
    Write-Output ("{0}: {1}" -f $phase.Key, (Format-Duration $phase.Value))
  }
  Write-Output ("Total: {0}" -f (Format-Duration $overallWatch.Elapsed.TotalSeconds))
  exit 0
}

if ([string]::IsNullOrWhiteSpace($ArchiveDir)) {
  $ArchiveDir = Join-Path $resolvedWorkDir "archived_logs"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logName = "${LogPrefix}_run_${timestamp}.log"
$logPath = Join-Path $resolvedWorkDir $logName

if (-not $NoArchiveOldLogs) {
  $resolvedArchiveDir = $ArchiveDir
  if (-not [System.IO.Path]::IsPathRooted($resolvedArchiveDir)) {
    $resolvedArchiveDir = Join-Path $resolvedWorkDir $resolvedArchiveDir
  }
  New-Item -ItemType Directory -Force -Path $resolvedArchiveDir | Out-Null

  Get-ChildItem -LiteralPath $resolvedWorkDir -Filter "${LogPrefix}_run_*.log" -File |
    Where-Object { $_.FullName -ne $logPath } |
    ForEach-Object {
      $target = Join-Path $resolvedArchiveDir $_.Name
      if (Test-Path -LiteralPath $target) {
        $target = Join-Path $resolvedArchiveDir ("{0}.archived_{1}.log" -f $_.BaseName, (Get-Date -Format "yyyyMMdd_HHmmssfff"))
      }
      Move-Item -LiteralPath $_.FullName -Destination $target
    }
}

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $resolvedRscript
$psi.WorkingDirectory = $resolvedWorkDir
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
$psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)
$scriptForR = $resolvedScript.Replace('\', '/').Replace("'", "\\'")
$runtimeScriptPath = Join-Path (
  [System.IO.Path]::GetTempPath()
) ("definition_runtime_" + [guid]::NewGuid().ToString("N") + ".R")
$runtimeSource = @"
script_lines <- readLines('$scriptForR', encoding = "UTF-8", warn = FALSE)
setup_line <- startsWith(
  trimws(script_lines),
  'install_github("ZhidoHuang/dbCodeBookr")'
)
script_lines <- script_lines[!setup_line]
eval(parse(text = paste(script_lines, collapse = "\n")), envir = .GlobalEnv)
"@
[System.IO.File]::WriteAllText(
  $runtimeScriptPath,
  $runtimeSource,
  [System.Text.UTF8Encoding]::new($false)
)
if ($null -ne $psi.ArgumentList) {
  $psi.ArgumentList.Add("--encoding=UTF-8")
  $psi.ArgumentList.Add($runtimeScriptPath)
} else {
  $psi.Arguments = "--encoding=UTF-8 `"$runtimeScriptPath`""
}

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi

$runWatch = [System.Diagnostics.Stopwatch]::StartNew()
$started = $process.Start()
if (-not $started) {
  throw "Failed to start Rscript."
}

$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$finishedInTime = $process.WaitForExit($TimeoutMinutes * 60 * 1000)
if (-not $finishedInTime) {
  try {
    $process.Kill()
    $process.WaitForExit()
  }
  catch {
    Write-Warning "Rscript exceeded the time limit and the stop request returned: $($_.Exception.Message)"
  }
}
$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result
$exitCode = if ($finishedInTime) { $process.ExitCode } else { 124 }
if (-not $finishedInTime) {
  $timeoutMessage = "Rscript exceeded the $TimeoutMinutes minute limit and was stopped. It was not retried automatically."
  $stderr = @($stderr.TrimEnd(), $timeoutMessage) -join [Environment]::NewLine
}
$runWatch.Stop()
$phaseSeconds["R execution"] = $runWatch.Elapsed.TotalSeconds
Remove-Item -LiteralPath $runtimeScriptPath -Force -ErrorAction SilentlyContinue
$overallWatch.Stop()

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("===== Rscript invocation =====")
$lines.Add("Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$lines.Add("WorkDir: $resolvedWorkDir")
$lines.Add("Script: $resolvedScript")
$lines.Add("Rscript: $resolvedRscript")
$lines.Add("Timeout: $TimeoutMinutes minute(s)")
$lines.Add("Automatic retry: no")
$lines.Add("")
$lines.Add("===== timing =====")
foreach ($phase in $phaseSeconds.GetEnumerator()) {
  $lines.Add(("{0}: {1}" -f $phase.Key, (Format-Duration $phase.Value)))
}
$lines.Add(("Total: {0}" -f (Format-Duration $overallWatch.Elapsed.TotalSeconds)))
$lines.Add("")
$lines.Add("===== stdout =====")
$lines.Add($stdout.TrimEnd())
$lines.Add("")
$lines.Add("===== stderr =====")
$lines.Add($stderr.TrimEnd())
$lines.Add("")
$lines.Add("===== Rscript status =====")
$lines.Add("Rscript exit code: $exitCode")
[System.IO.File]::WriteAllText($logPath, ($lines -join [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))

if ($exitCode -ne 0) {
  Write-Error "Rscript failed with exit code $exitCode. Log: $logPath"
  exit $exitCode
}

Write-Output "Rscript completed successfully."
Write-Output "Log: $logPath"
Write-Output ("Duration: {0}" -f (Format-Duration $overallWatch.Elapsed.TotalSeconds))
exit 0
