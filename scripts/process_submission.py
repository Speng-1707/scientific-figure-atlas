"""把 GitHub Issue 投稿转成静态图库记录。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "figures.json"
SITE_DATA = ROOT / "site" / "data" / "figures.json"
ASSETS = ROOT / "site" / "assets"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 40 * 1024 * 1024
ALLOWED_HOSTS = {"github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com"}
CATEGORIES = {
    "统计图表": ["统计", "柱状", "折线", "散点", "箱线", "小提琴", "bar", "scatter", "plot", "曲线"],
    "热图与矩阵": ["热图", "矩阵", "heatmap", "matrix", "相关性"],
    "机制与示意图": ["机制", "示意", "通路", "mechanism", "schematic", "pathway"],
    "流程与框架": ["流程", "框架", "工作流", "workflow", "framework", "pipeline"],
    "显微与影像": ["显微", "荧光", "影像", "microscopy", "imaging", "组织"],
    "地图与空间": ["地图", "空间", "地理", "map", "spatial", "地形"],
    "网络与关系": ["网络", "关系", "network", "graph", "桑基"],
}


def parse_sections(body: str) -> dict[str, str]:
    parts = re.split(r"^###\s+", body, flags=re.MULTILINE)[1:]
    result = {}
    for part in parts:
        heading, _, value = part.partition("\n")
        result[heading.strip()] = value.strip()
    return result


def first_url(text: str) -> str | None:
    match = re.search(r"https://[^\s)>]+", text or "")
    return match.group(0).rstrip(".,") if match else None


def download(url: str, limit: int) -> tuple[bytes, str]:
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError("附件必须通过 GitHub 上传")
    request = Request(url, headers={"User-Agent": "scientific-figure-atlas-action"})
    with urlopen(request, timeout=30) as response:
        if int(response.headers.get("Content-Length", 0)) > limit:
            raise ValueError("附件超过大小限制")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("附件超过大小限制")
        return data, response.headers.get_content_type()


def classify(text: str) -> str:
    normalized = text.lower()
    scores = {name: sum(word in normalized for word in words) for name, words in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "其他 / 待分类"


def palette(image: Image.Image) -> list[dict]:
    small = image.copy(); small.thumbnail((240, 240))
    quantized = small.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    raw = quantized.getpalette()
    colors = [(count, tuple(raw[index*3:index*3+3])) for count, index in sorted(quantized.getcolors(), reverse=True)]
    chromatic = [(count, rgb) for count, rgb in colors if max(rgb)-min(rgb) >= 24 and 28 < sum(rgb)/3 < 242]
    selected = []
    for count, rgb in chromatic or colors:
        if all(sum((a-b)**2 for a,b in zip(rgb, previous)) > 36**2 for _, previous in selected):
            selected.append((count, rgb))
        if len(selected) == 6: break
    total = sum(count for count, _ in selected)
    return [{"hex": "#%02X%02X%02X" % rgb, "rgb": list(rgb), "weight": round(count/total*100, 1)} for count, rgb in selected]


def main() -> None:
    body = os.environ["ISSUE_BODY"]
    sections = parse_sections(body)
    required = ["图片标题", "为什么觉得这张图好？", "以后可以用在哪里？", "科研图片"]
    if any(not sections.get(field) for field in required):
        raise ValueError("投稿缺少必填字段")
    image_url = first_url(sections["科研图片"])
    if not image_url: raise ValueError("没有找到图片附件链接")
    image_bytes, _ = download(image_url, MAX_IMAGE_BYTES)
    try:
        from io import BytesIO
        with Image.open(BytesIO(image_bytes)) as original:
            if original.format not in {"PNG", "JPEG", "WEBP", "TIFF"}: raise ValueError("不支持的图片格式")
            original.load(); rgba = ImageOps.exif_transpose(original).convert("RGBA")
    except (UnidentifiedImageError, OSError):
        raise ValueError("图片附件无法读取") from None
    background = Image.new("RGBA", rgba.size, "white"); background.alpha_composite(rgba)
    image = background.convert("RGB"); image.thumbnail((3000, 3000))
    identifier = f"issue-{os.environ['ISSUE_NUMBER']}-{uuid4().hex[:8]}"
    ASSETS.mkdir(parents=True, exist_ok=True)
    image_path = ASSETS / f"{identifier}.jpg"; image.save(image_path, quality=92, optimize=True)
    paper_path = ""
    paper_url = first_url(sections.get("论文 PDF（可选）", ""))
    if paper_url:
        paper_bytes, _ = download(paper_url, MAX_PDF_BYTES)
        if not paper_bytes.startswith(b"%PDF-"): raise ValueError("论文附件不是有效 PDF")
        pdf_file = ASSETS / f"{identifier}.pdf"; pdf_file.write_bytes(paper_bytes); paper_path = f"assets/{pdf_file.name}"
    chosen = sections.get("分类", "自动分类").splitlines()[0].strip()
    combined = " ".join(sections.get(x, "") for x in ["图片标题", "所属论文标题", "为什么觉得这张图好？", "以后可以用在哪里？"])
    category = classify(combined) if chosen == "自动分类" else chosen
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    records.insert(0, {"id": identifier, "title": sections["图片标题"].splitlines()[0],
        "author": os.environ["ISSUE_USER"], "paper_title": sections.get("所属论文标题", "").replace("_No response_", ""),
        "why": sections["为什么觉得这张图好？"], "usage": sections["以后可以用在哪里？"],
        "category": category, "image": f"assets/{image_path.name}", "paper": paper_path,
        "palette": palette(image), "issue_number": int(os.environ["ISSUE_NUMBER"]), "issue_url": os.environ["ISSUE_URL"]})
    rendered = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    DATA_FILE.write_text(rendered, encoding="utf-8")
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True); SITE_DATA.write_text(rendered, encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output: Path(output).open("a", encoding="utf-8").write(f"title={sections['图片标题'].splitlines()[0]}\n")


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(f"投稿处理失败：{error}", file=sys.stderr); raise
