# Restart the local development API (127.0.0.1:8000) and worker with the project virtual environment.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv\Scripts\python.exe'
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*uvicorn*apps.api.app.main*' -or $_.CommandLine -like '*apps.worker.main*') } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
$api = @('-m', 'uvicorn', 'apps.api.app.main:app', '--host', '127.0.0.1', '--port', '8000')
Start-Process -FilePath $python -WorkingDirectory $root -ArgumentList $api -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root '.local/api.stdout.log') -RedirectStandardError (Join-Path $root '.local/api.stderr.log')
# Scoped to the bootstrapped synthetic organization so it never races test tenants.
$worker = @('-m', 'apps.worker.main', '--interval', '1', '--organization', '10000000-0000-4000-8000-000000000001')
Start-Process -FilePath $python -WorkingDirectory $root -ArgumentList $worker -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root '.local/worker.stdout.log') -RedirectStandardError (Join-Path $root '.local/worker.stderr.log')
for ($i = 0; $i -lt 30; $i++) {
  try { if ((Invoke-WebRequest 'http://127.0.0.1:8000/api/v1/health' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { 'API and worker ready'; exit 0 } } catch { Start-Sleep -Milliseconds 500 }
}
throw 'API did not become healthy; see .local/api.stderr.log'
