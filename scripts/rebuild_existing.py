"""一次性升级已有记录的色板和来源/投稿人字段。"""
import json
from pathlib import Path
from PIL import Image
from process_submission import DATA_FILE, SITE_DATA, ROOT, palette

records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
for record in records:
    image_path = ROOT / "site" / record["image"]
    if image_path.exists():
        with Image.open(image_path) as image:
            record["palette"] = palette(image.convert("RGB"))
    record.setdefault("recommended", True)
    record.setdefault("source_type", "recommended")
    record.setdefault("contributor_name", record.get("author", "匿名投稿者"))
    record.setdefault("contributor_affiliation", "")
    record.setdefault("contributor_profile", "")

rendered = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
DATA_FILE.write_text(rendered, encoding="utf-8")
SITE_DATA.write_text(rendered, encoding="utf-8")
print(f"Updated {len(records)} existing record(s).")
