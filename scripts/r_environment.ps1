# Shared by setup and runner. Changes last only for the caller's try/finally.
function Start-DefinitionREnvironment {
  param([string]$Config = "", [string]$Python = "")
  if (-not $Python) {
    $Python = (Get-Command python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1).Source
  }
  if (-not $Python) { throw "Set executables.python in config.local.json or supply -Python." }
  $runtimeArgs = @('-X', 'utf8', (Join-Path $PSScriptRoot 'r_runtime.py'))
  if ($Config) { $runtimeArgs += @('--config', $Config) }
  $json = & $Python @runtimeArgs
  if ($LASTEXITCODE -ne 0) { throw "R runtime paths are not ready; fix the reported configuration before setup or generation." }
  $plan = ($json -join "`n") | ConvertFrom-Json
  $saved = @{}
  foreach ($property in $plan.environment.PSObject.Properties) {
    $saved[$property.Name] = [Environment]::GetEnvironmentVariable($property.Name, 'Process')
    $value = if ($null -eq $property.Value) { $null } else { [string]$property.Value }
    [Environment]::SetEnvironmentVariable($property.Name, $value, 'Process')
  }
  return @{ TempRoot = $plan.temp_root; Saved = $saved }
}

function Stop-DefinitionREnvironment {
  param($State)
  if ($null -ne $State) {
    foreach ($name in $State.Saved.Keys) {
      [Environment]::SetEnvironmentVariable($name, $State.Saved[$name], 'Process')
    }
  }
}
