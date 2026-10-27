# Whyscope installer (Windows). Usage: powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Cpu] [-NoOptional] [-NoModels]
param([switch]$Cpu, [switch]$NoOptional, [switch]$NoModels, [string]$VenvDir = "")
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

# Pick the newest Python the launcher knows (3.12-3.14 work with PyTorch wheels).
$py = $null
$listed = (& cmd /c "py -0 2>&1") -join " "
foreach ($v in "3.13", "3.12", "3.14", "3.11") { if ($listed -match [regex]::Escape("-V:$v")) { $py = @("py", "-$v"); break } }
if (-not $py) { $py = @("python") }
Write-Host "Using Python:" ($py -join " ")
# Windows cannot load CUDA DLLs from paths over ~260 chars (WinError 206). In a deep checkout, put the venv at a short path
# and record it in .venvpath (run.ps1 reads that file).
if (-not $VenvDir) { $VenvDir = if ((Get-Location).Path.Length -gt 140) { Join-Path $env:SystemDrive "whyscope-venv" } else { ".venv" } }
if ($VenvDir -ne ".venv") { Set-Content -Path .venvpath -Value (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Force $VenvDir)).Path -Encoding ascii; Write-Host "venv at $VenvDir (long repo path)" }
& $py[0] $py[1..($py.Length)] -m venv $VenvDir
$vpy = Join-Path $VenvDir "Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip

if (-not $Cpu -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing PyTorch (CUDA 12.6)..."
    & $vpy -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu126
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
if (-not $Cpu -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    $ok = (& $vpy -c "import torch;print(torch.cuda.is_available())")
    if ($ok -ne "True") { & $vpy -m pip install --quiet --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cu126 }
    # ultralytics pulls a CPU torchvision from PyPI; it must match the CUDA torch or YOLO fails on the GPU
    & $vpy -c "import torchvision" 2>$null
    if ($LASTEXITCODE -eq 0) { & $vpy -m pip install --quiet --force-reinstall --no-deps torchvision --index-url https://download.pytorch.org/whl/cu126 }
    Write-Host "torch.cuda.is_available() =" (& $vpy -c "import torch;print(torch.cuda.is_available())")
}
if (-not $NoModels) { & $vpy scripts\download_models.py }
Write-Host "Done. Start with: scripts\run.ps1"
