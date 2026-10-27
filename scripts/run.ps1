# Start the Whyscope hub on 0.0.0.0:8000
Set-Location (Split-Path -Parent $PSScriptRoot)
$venv = if (Test-Path .venvpath) { (Get-Content .venvpath -Raw).Trim() } else { ".venv" }
& (Join-Path $venv "Scripts\python.exe") -m uvicorn hub.server:app --host 0.0.0.0 --port 8000
