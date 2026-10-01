$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeInfo = Get-Content -LiteralPath (Join-Path $projectRoot '.local/runtime/versions.json') -Raw | ConvertFrom-Json
$env:JAVA_HOME = $runtimeInfo.java_home
$keycloakRoot = Join-Path $projectRoot ".local/runtime/keycloak-$($runtimeInfo.keycloak)"
$importPath = Join-Path $keycloakRoot 'data/import'
New-Item -ItemType Directory -Path $importPath -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot '.local/realm.json') -Destination (Join-Path $importPath 'realm.json')
$adminLine = Get-Content -LiteralPath (Join-Path $projectRoot '.env') | Where-Object { $_.StartsWith('KEYCLOAK_ADMIN_PASSWORD=') }
$env:KC_BOOTSTRAP_ADMIN_USERNAME = 'local-admin'
$env:KC_BOOTSTRAP_ADMIN_PASSWORD = $adminLine.Substring('KEYCLOAK_ADMIN_PASSWORD='.Length)
& (Join-Path $keycloakRoot 'bin/kc.bat') start-dev --import-realm --http-host=127.0.0.1 --http-port=58080 --hostname=http://localhost:58080
