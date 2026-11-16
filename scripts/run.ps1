# Start the Whyscope hub on 0.0.0.0:$env:WHYSCOPE_PORT (default 8000). Serves HTTPS when certs\cert.pem and
# certs\key.pem exist (create them with: python scripts\make_cert.py), so phones can use the microphone and camera.
Set-Location (Split-Path -Parent $PSScriptRoot)
$venv = if (Test-Path .venvpath) { (Get-Content .venvpath -Raw).Trim() } else { ".venv" }
$port = if ($env:WHYSCOPE_PORT) { $env:WHYSCOPE_PORT } else { "8000" }
$extra = @()
if ((Test-Path certs\cert.pem) -and (Test-Path certs\key.pem)) {
    $extra = @("--ssl-certfile", "certs\cert.pem", "--ssl-keyfile", "certs\key.pem")
    Write-Host "HTTPS on port $port"
} else {
    Write-Host "HTTP on port $port (phones cannot use the microphone; run scripts\make_cert.py for HTTPS)"
}
& (Join-Path $venv "Scripts\python.exe") -m uvicorn hub.server:app --host 0.0.0.0 --port $port @extra
