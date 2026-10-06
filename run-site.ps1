$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$siteUrl = "http://localhost:3001"

function Test-Port {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" } |
        Select-Object -First 1
    return $null -ne $connection
}

if (-not (Test-Port 8000)) {
    Start-Process powershell -WindowStyle Hidden -WorkingDirectory $backend -ArgumentList @(
        "-NoExit",
        "-Command",
        '$env:DATABASE_URL="sqlite:///./dev.db"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
    )
}

if (-not (Test-Port 3001)) {
    Start-Process powershell -WindowStyle Hidden -WorkingDirectory $frontend -ArgumentList @(
        "-NoExit",
        "-Command",
        "npm run dev -- -p 3001"
    )
}

Write-Host ""
Write-Host "AI Memory website is starting."
Write-Host "Open this single link:"
Write-Host $siteUrl
Write-Host ""
Write-Host "The frontend will proxy API requests to the backend through /api."
