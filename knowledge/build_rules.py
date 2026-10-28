"""Generate knowledge/sensitive_rules.json from the cheat sheets in knowledge/cheats/.

The cheat sheets are the single source of truth for sensitive-topic triggers.
Run from anywhere:  python knowledge/build_rules.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHEATS_DIR = HERE / "cheats"
OUT_PATH = HERE / "sensitive_rules.json"


def main() -> None:
    categories = []
    for path in sorted(CHEATS_DIR.glob("*.json")):
        cheat = json.loads(path.read_text(encoding="utf-8"))
        categories.append({
            "id": cheat["id"],
            "category_zh": cheat["category_zh"],
            "triggers": cheat["triggers"],
            "triggers_en": cheat["en"]["triggers"],
            "urgent": bool(cheat.get("urgent", False)),
        })
    OUT_PATH.write_text(
        json.dumps({"categories": categories}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(categories)} categories to {OUT_PATH}")


if __name__ == "__main__":
    main()
