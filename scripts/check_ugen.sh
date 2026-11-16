#!/usr/bin/env bash
# Day-one check for the ASUS UGen300 USB on Ubuntu (docs/hardware.md). Read-only: installs nothing.
# Usage: scripts/check_ugen.sh            -> device, HailoRT, Python binding
#        scripts/check_ugen.sh --compose  -> also one Whyscope compose request on the UGen300 (needs hailo.llm_hef)
cd "$(dirname "$0")/.."
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
ok()   { echo "  [ok]   $*"; }
fail() { echo "  [FAIL] $*"; FAILED=1; }

echo "1. USB device"
if command -v lsusb >/dev/null; then
  lsusb | grep -i -E "hailo|asus" && ok "a Hailo/ASUS USB device is listed (write down the ID line)" \
    || echo "  [?]    no line says Hailo or ASUS; compare 'lsusb' with the UGen300 unplugged and plugged in"
else
  echo "  [?]    lsusb not installed (sudo apt install usbutils)"
fi

echo "2. HailoRT command line"
if command -v hailortcli >/dev/null; then
  hailortcli --version 2>/dev/null | head -1
  hailortcli scan && ok "hailortcli scan" || fail "hailortcli scan (driver / udev rules / HailoRT 5.x?)"
  hailortcli fw-control identify && ok "fw-control identify" || fail "fw-control identify"
else
  fail "hailortcli not found: install HailoRT 5.x for the USB UGen300 first"
fi

echo "3. Python binding ($PY)"
$PY -c "from hailo_platform import VDevice; from hailo_platform.genai import LLM, Speech2Text; print('  hailo_platform OK')" \
  && ok "hailo_platform + genai import" \
  || fail "hailo_platform not importable in $PY (install the HailoRT wheel matching HailoRT and this Python)"

if [ "$1" = "--compose" ]; then
  echo "4. Whyscope compose on the UGen300"
  $PY - <<'EOF' || FAILED=1
import json, time
from hub.config import load_config
from hub.hailo import HailoLLM
from hub.compose import Composer
cfg = load_config()
cfg["mode"] = "hailo"
llm = HailoLLM(cfg)
print("  model:", llm.name)
entry = json.load(open("knowledge/entries/animals/animals-snail-shell.json", encoding="utf-8"))
c = Composer.__new__(Composer)            # reuse the prompt builder without starting the loader thread
c.cfg, c.full_cfg = cfg["compose"], cfg
for i in range(3):
    t = time.perf_counter()
    raw = llm.chat(c._messages(entry, 6), int(cfg["compose"].get("max_new_tokens", 120)))
    print(f"  run {i + 1}: {time.perf_counter() - t:.2f} s  {raw.strip()[:120]}")
EOF
fi

[ -z "$FAILED" ] && echo "All checks passed." || { echo "Some checks failed (see [FAIL] above)."; exit 1; }
