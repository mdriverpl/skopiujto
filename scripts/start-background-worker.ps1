$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime/python/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = (Get-Command python).Source }
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and
    $_.CommandLine -like '*-m backend.background_worker*' -and
    $_.ExecutablePath -eq $pythonPath
}
if ($existing) { Write-Output "Worker already running: $($existing.ProcessId)"; exit }
$runtimePath = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$workerProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m', 'backend.background_worker' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'background-worker.out.log') -RedirectStandardError (Join-Path $runtimePath 'background-worker.err.log')
Write-Output "Background worker started: PID $($workerProcess.Id)"
