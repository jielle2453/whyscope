# Start Whyscope in UGen300 mode on this laptop: the UGen worker (127.0.0.1:8711, holds LLM + Whisper + YOLO + CLIP)
# and the hub (port 8000). Already-running pieces are left alone; use -Restart to restart the hub, -RestartWorker to
# restart the worker (graceful, POST /shutdown first: needed after a model / HEF change in the config).
#   powershell -ExecutionPolicy Bypass -File scripts\start_ugen.ps1 [-Restart] [-RestartWorker] [-Lan]
#   -Lan: listen on all interfaces so phones on the same Wi-Fi can reach the hub (pairing still needs a token).
param([switch]$Restart, [switch]$RestartWorker, [switch]$Lan, [string]$Config = "")
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Config) { $Config = Join-Path $Repo "config.hailo.yaml" }
$Logs = Join-Path $Repo "data\logs"
New-Item -ItemType Directory -Force $Logs | Out-Null
$env:WHYSCOPE_CONFIG = $Config; $env:HF_HUB_OFFLINE = "1"; $env:PYTHONUNBUFFERED = "1"; $env:PYTHONIOENCODING = "utf-8"
Set-Location $Repo

function Find-Proc($pattern) {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match $pattern }
}

# 1. UGen worker (only one process may own the USB device)
if ($RestartWorker -and (Find-Proc 'hub\.hailo_worker')) {
    # graceful: POST /shutdown releases the models first. A killed worker leaves its LLM on the device and the next
    # worker's LLM / VLM then fails with HAILO_INTERNAL_FAILURE(8) (docs/ugen.md); kill only if it does not stop.
    try { $wc = New-Object System.Net.WebClient; $wc.Proxy = $null; $wc.Headers.Add("Content-Type", "application/json")
          $wc.UploadString("http://127.0.0.1:8711/shutdown", "{}") | Out-Null } catch {}
    for ($i = 0; $i -lt 30 -and (Find-Proc 'hub\.hailo_worker'); $i++) { Start-Sleep 1 }
    Find-Proc 'hub\.hailo_worker' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep 2
}
if (Find-Proc 'hub\.hailo_worker') {
    Write-Host "UGen worker already running"
} else {
    Start-Process -FilePath C:\whyscope-hailo-venv\Scripts\python.exe -ArgumentList "-m", "hub.hailo_worker" `
        -RedirectStandardOutput "$Logs\worker.log" -RedirectStandardError "$Logs\worker.err.log" -WindowStyle Hidden
    Write-Host "UGen worker starting (models take about 20 s to load)"
}

# 2. Hub on port 8000
$hub = Find-Proc 'uvicorn hub\.server.*--port 8000'
if ($hub -and $Restart) { $hub | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 2; $hub = $null }
if ($hub) {
    Write-Host "Hub already running on port 8000 (use -Restart to restart it)"
} else {
    $bind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
    Start-Process -FilePath C:\whyscope-venv\Scripts\python.exe -ArgumentList "-m", "uvicorn", "hub.server:app", "--host", $bind, "--port", "8000" `
        -RedirectStandardOutput "$Logs\hub.log" -RedirectStandardError "$Logs\hub.err.log" -WindowStyle Hidden
    Write-Host "Hub starting on ${bind}:8000 -> http://127.0.0.1:8000/kid and /parent"
}
