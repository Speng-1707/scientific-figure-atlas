"""Import anonymous Cloudflare uploads into the static GitHub gallery."""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.process_submission import ASSETS, DATA_FILE, SITE_DATA, classify, palette, prepare_image


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "scientific-figure-atlas-action"})
    with urlopen(request, timeout=60) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("anonymous image exceeds size limit")
    return data


def main() -> None:
    input_file = Path(os.environ.get("ANONYMOUS_INPUT", "anonymous-pending.json"))
    incoming = json.loads(input_file.read_text(encoding="utf-8"))
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    imported = []
    for item in incoming:
        identifier = item["id"]
        ASSETS.mkdir(parents=True, exist_ok=True)
        image_path = ASSETS / f"{identifier}.jpg"
        if image_path.exists():
            image = prepare_image(image_path.read_bytes())
        else:
            image = prepare_image(download(item["image_url"]))
            image.save(image_path, quality=92, optimize=True)
        combined = " ".join(str(item.get(key, "")) for key in ("title", "why", "usage"))
        record = {
            "id": identifier,
            "title": item.get("title") or "待补充标题",
            "author": "anonymous",
            "contributor_name": item.get("contributor_name") or "匿名投稿者",
            "contributor_affiliation": "",
            "contributor_profile": "",
            "paper_title": "",
            "why": item.get("why") or "快速上传，推荐理由待补充。",
            "usage": item.get("usage") or "未来用途待补充。",
            "image": f"assets/{image_path.name}",
            "paper": "",
            "issue_number": "",
            "issue_url": "",
            "category": classify(combined),
            "palette": palette(image),
            "rating": max(1, min(5, int(item.get("rating", 5)))),
            "source_type": "anonymous",
        }
        records = [existing for existing in records if existing.get("id") != identifier]
        records.insert(0, record)
        imported.append(identifier)
    rendered = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    DATA_FILE.write_text(rendered, encoding="utf-8")
    SITE_DATA.write_text(rendered, encoding="utf-8")
    Path("anonymous-synced.json").write_text(json.dumps({"ids": imported}), encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"count={len(imported)}\n")


if __name__ == "__main__":
    main()
