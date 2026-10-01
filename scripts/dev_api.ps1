# Restart the local development API on 127.0.0.1:8000 with the project virtual environment.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*apps.api.app.main*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -WorkingDirectory $root `
  -ArgumentList '-m', 'uvicorn', 'apps.api.app.main:app', '--host', '127.0.0.1', '--port', '8000' `
  -RedirectStandardOutput (Join-Path $root '.local/api.stdout.log') -RedirectStandardError (Join-Path $root '.local/api.stderr.log') -WindowStyle Hidden
for ($i = 0; $i -lt 30; $i++) {
  try { if ((Invoke-WebRequest 'http://127.0.0.1:8000/api/v1/health' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { 'API ready'; exit 0 } } catch { Start-Sleep -Milliseconds 500 }
}
throw 'API did not become healthy; see .local/api.stderr.log'
