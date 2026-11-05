"""One-time migration: remove PDF-derived records and add ratings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "figures.json"
SITE_DATA = ROOT / "site" / "data" / "figures.json"
ASSETS = (ROOT / "site" / "assets").resolve()

records = json.loads(DATA.read_text(encoding="utf-8"))
removed = [record for record in records if record.get("source_type") == "pdf_auto"]
remaining = [record for record in records if record.get("source_type") != "pdf_auto"]
referenced = {value for record in remaining for value in (record.get("image", ""), record.get("paper", "")) if value}
for record in removed:
    value = record.get("image", "")
    if value and value not in referenced and value.startswith("assets/"):
        target = (ROOT / "site" / value).resolve()
        if target.parent != ASSETS:
            raise ValueError(f"Unsafe asset path: {value}")
        if target.exists():
            target.unlink()
for record in remaining:
    record["rating"] = max(1, min(5, int(record.get("rating", 5 if record.get("recommended", True) else 1))))
    record["source_type"] = "submitted"
    record.pop("recommended", None)
rendered = json.dumps(remaining, ensure_ascii=False, indent=2) + "\n"
DATA.write_text(rendered, encoding="utf-8")
SITE_DATA.write_text(rendered, encoding="utf-8")
print(f"Removed {len(removed)} PDF-derived records; kept {len(remaining)} submissions.")
