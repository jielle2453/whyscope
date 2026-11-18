"""Temporary eval configs (work/config_base.yaml, work/config_ft.yaml): copies of config.yaml whose answer bank caches live
in work/ (the live hub's data/answer_bank_en.npz is never written). config_ft adds answer_bank.model and the calibrated
thresholds from work/calib.json. Use with WHYSCOPE_CONFIG=... for eval/check_safety_en.py and eval/run_bank_order.py."""
import json

import yaml

from common import ROOT, WORK

cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
b = dict(cfg)
b["answer_bank"] = {**cfg["answer_bank"], "cache": str(WORK / "cache_base.npz")}
yaml.safe_dump(b, open(WORK / "config_base.yaml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
try:
    cal = json.load(open(WORK / "calib.json", encoding="utf-8"))
except OSError:
    cal = None
if cal:
    f = dict(cfg)
    f["answer_bank"] = {**cfg["answer_bank"], "model": "models/recall/whyscope-minilm-en-v1",
                        "threshold": cal["answer"]["ft"], "sensitive_threshold": cal["sensitive"]["ft"],
                        "cache": str(WORK / "cache_ft.npz")}
    yaml.safe_dump(f, open(WORK / "config_ft.yaml", "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print("ft:", f["answer_bank"])
print("base:", b["answer_bank"])
