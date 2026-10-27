# Whyscope installer (Windows). Usage: powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Cpu] [-NoOptional] [-NoModels]
param([switch]$Cpu, [switch]$NoOptional, [switch]$NoModels)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

# Pick the newest Python the launcher knows (3.12-3.14 work with PyTorch wheels).
$py = $null
$listed = (& cmd /c "py -0 2>&1") -join " "
foreach ($v in "3.13", "3.12", "3.14", "3.11") { if ($listed -match [regex]::Escape("-V:$v")) { $py = @("py", "-$v"); break } }
if (-not $py) { $py = @("python") }
Write-Host "Using Python:" ($py -join " ")
& $py[0] $py[1..($py.Length)] -m venv .venv
$vpy = ".\.venv\Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip

if (-not $Cpu -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyTorch (CUDA 12.8)..."
    & $vpy -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { Write-Host "CUDA torch failed; falling back to CPU torch"; & $vpy -m pip install --quiet torch }
} else {
    & $vpy -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
}
& $vpy -m pip install --quiet -r requirements.txt
if (-not $NoOptional) {
    foreach ($p in (Get-Content requirements-optional.txt | Where-Object { $_ -and -not $_.StartsWith("#") })) {
        & $vpy -m pip install --quiet --only-binary=:all: $p
        if ($LASTEXITCODE -ne 0) { Write-Host "[skip] optional package $p failed to install" }
    }
}
if (-not $NoModels) { & $vpy scripts\download_models.py }
Write-Host "Done. Start with: scripts\run.ps1"
