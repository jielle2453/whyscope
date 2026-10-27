#!/usr/bin/env bash
# Whyscope installer (Linux/macOS). Usage: scripts/install.sh [--cpu] [--no-optional] [--no-models]
set -e
cd "$(dirname "$0")/.."
CPU=0; OPT=1; MODELS=1
for a in "$@"; do case $a in --cpu) CPU=1;; --no-optional) OPT=0;; --no-models) MODELS=0;; esac; done
PY=python3
for v in 3.13 3.12 3.14 3.11; do command -v python$v >/dev/null 2>&1 && { PY=python$v; break; }; done
echo "Using $PY"
$PY -m venv .venv
VPY=.venv/bin/python
$VPY -m pip install --quiet --upgrade pip
if [ $CPU = 0 ] && command -v nvidia-smi >/dev/null 2>&1; then
  $VPY -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cu126 || $VPY -m pip install --quiet torch
else
  $VPY -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
fi
$VPY -m pip install --quiet -r requirements.txt
if [ $OPT = 1 ]; then
  grep -v '^#' requirements-optional.txt | grep . | while read -r p; do
    $VPY -m pip install --quiet --only-binary=:all: "$p" || echo "[skip] optional package $p failed to install"
  done
fi
if [ $CPU = 0 ] && command -v nvidia-smi >/dev/null 2>&1; then
  [ "$($VPY -c 'import torch;print(torch.cuda.is_available())')" = "True" ] ||     $VPY -m pip install --quiet --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cu126
  # ultralytics pulls a CPU torchvision from PyPI; it must match the CUDA torch or YOLO fails on the GPU
  if $VPY -c "import torchvision" 2>/dev/null; then
    $VPY -m pip install --quiet --force-reinstall --no-deps torchvision --index-url https://download.pytorch.org/whl/cu126
  fi
  echo "torch.cuda.is_available() = $($VPY -c 'import torch;print(torch.cuda.is_available())')"
fi
[ $MODELS = 1 ] && $VPY scripts/download_models.py
echo "Done. Start with: scripts/run.sh"
