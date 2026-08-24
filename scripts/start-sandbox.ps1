param(
  [string]$SandboxDir = (Join-Path $PSScriptRoot "..\sandbox")
)

$ErrorActionPreference = "Stop"
Set-Location $SandboxDir

if (-not (Test-Path ".env")) {
  $token = -join ((1..32) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })
  $gh = (gh auth token)
  @"
SANDBOX_TOKEN=$token
GH_TOKEN=$gh
GITHUB_REPO=ashkandehnavi/n8n-code
"@ | Set-Content -Path ".env" -Encoding ascii
  Write-Host "Wrote sandbox/.env"
}

docker compose up -d --build
Write-Host "Waiting for sandbox health..."
for ($i = 0; $i -lt 20; $i++) {
  try {
    $h = Invoke-RestMethod "http://127.0.0.1:8099/health" -TimeoutSec 3
    if ($h.ok) { break }
  } catch { Start-Sleep -Seconds 2 }
}

Write-Host "Starting Cloudflare tunnel (HTTP/2)..."
$cf = Join-Path $env:TEMP "cloudflared.exe"
if (-not (Test-Path $cf)) {
  curl.exe -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -o $cf
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
$log = Join-Path $SandboxDir "cloudflared.log"
Start-Process -FilePath $cf -ArgumentList @("tunnel","--url","http://127.0.0.1:8099","--no-autoupdate","--protocol","http2") -RedirectStandardError $log -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $log) {
    $m = [regex]::Match((Get-Content $log -Raw -ErrorAction SilentlyContinue), "https://[a-z0-9-]+\.trycloudflare\.com")
    if ($m.Success) { $url = $m.Value; break }
  }
}
if (-not $url) { throw "Tunnel URL not found. See sandbox/cloudflared.log" }
$url | Set-Content (Join-Path $SandboxDir "tunnel-url.txt") -Encoding ascii
Write-Host "TUNNEL=$url"
Write-Host "If this URL changed, rebuild and re-upload the n8n workflow (Init State.sandbox_url)."
