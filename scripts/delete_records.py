"""Delete selected gallery records and unreferenced local assets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "figures.json"
SITE_DATA = ROOT / "site" / "data" / "figures.json"
ASSETS = (ROOT / "site" / "assets").resolve()
ID_PATTERN = re.compile(r"^issue-\d+-[A-Za-z0-9-]+$", re.MULTILINE)


def parse_ids(body: str) -> set[str]:
    marker = body.partition("DELETE_IDS:")[2]
    return set(ID_PATTERN.findall(marker))


def local_asset(value: str) -> Path | None:
    if not value or not value.startswith("assets/"):
        return None
    target = (ROOT / "site" / value).resolve()
    if target.parent != ASSETS:
        raise ValueError(f"不安全的资源路径：{value}")
    return target


def main() -> None:
    requested = parse_ids(os.environ.get("ISSUE_BODY", ""))
    if not requested:
        raise ValueError("删除请求中没有有效的记录 ID")
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    removed = [record for record in records if record.get("id") in requested]
    remaining = [record for record in records if record.get("id") not in requested]
    if not removed:
        raise ValueError("没有找到待删除记录")
    referenced = {value for record in remaining for value in (record.get("image", ""), record.get("paper", "")) if value}
    for record in removed:
        for value in (record.get("image", ""), record.get("paper", "")):
            if value and value not in referenced:
                target = local_asset(value)
                if target and target.exists():
                    target.unlink()
    rendered = json.dumps(remaining, ensure_ascii=False, indent=2) + "\n"
    DATA_FILE.write_text(rendered, encoding="utf-8")
    SITE_DATA.write_text(rendered, encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"count={len(removed)}\n")


if __name__ == "__main__":
    main()
