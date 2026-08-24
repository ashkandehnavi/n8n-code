param(
  [string]$SandboxDir = (Join-Path $PSScriptRoot "..\sandbox")
)

$ErrorActionPreference = "Stop"
Set-Location $SandboxDir

if (-not (Test-Path ".env")) {
  $gh = (gh auth token)
  @"
GH_TOKEN=$gh
GITHUB_REPO=ashkandehnavi/n8n-code
"@ | Set-Content -Path ".env" -Encoding ascii
  Write-Host "Wrote sandbox/.env"
}

docker compose up -d --build
Write-Host "Waiting for sandbox health..."
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
  try {
    $h = Invoke-RestMethod "http://127.0.0.1:8099/health" -TimeoutSec 3
    if ($h.ok) { $ok = $true; break }
  } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) { throw "Sandbox did not become healthy on http://127.0.0.1:8099/health" }

Write-Host "Sandbox UI:  http://127.0.0.1:8099"
Write-Host "Public URL:  https://sandbox.denox.ir"
