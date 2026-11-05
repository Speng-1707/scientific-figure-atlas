"""把 GitHub Issue 投稿、主图及 PDF 内嵌图片转成静态图库记录。"""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import pymupdf as fitz
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "figures.json"
SITE_DATA = ROOT / "site" / "data" / "figures.json"
ASSETS = ROOT / "site" / "assets"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PDF_FIGURES = 30
MAX_PALETTE_COLORS = 18
ALLOWED_HOSTS = {"github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com"}
CATEGORIES = {
    "统计图表": ["统计", "柱状", "折线", "散点", "箱线", "小提琴", "bar", "scatter", "plot", "curve", "chart"],
    "热图与矩阵": ["热图", "矩阵", "heatmap", "matrix", "相关性", "correlation"],
    "机制与示意图": ["机制", "示意", "通路", "mechanism", "schematic", "pathway"],
    "流程与框架": ["流程", "框架", "工作流", "workflow", "framework", "pipeline"],
    "显微与影像": ["显微", "荧光", "影像", "microscopy", "imaging", "tissue"],
    "地图与空间": ["地图", "空间", "地理", "map", "spatial", "regional", "geographic"],
    "网络与关系": ["网络", "关系", "network", "graph", "桑基", "sankey"],
}


def clean(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value == "_No response_" else value


def parse_sections(body: str) -> dict[str, str]:
    parts = re.split(r"^###\s+", body, flags=re.MULTILINE)[1:]
    result = {}
    for part in parts:
        heading, _, value = part.partition("\n")
        result[heading.strip()] = value.strip()
    return result


def first_url(text: str) -> str | None:
    match = re.search(r"https://[^\s)>\"']+", text or "")
    return match.group(0).rstrip(".,") if match else None


def safe_profile_url(text: str) -> str:
    url = first_url(clean(text))
    return url if url and urlparse(url).scheme in {"http", "https"} else ""


def download(url: str, limit: int) -> tuple[bytes, str]:
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError("附件必须通过 GitHub 上传")
    request = Request(url, headers={"User-Agent": "scientific-figure-atlas-action"})
    with urlopen(request, timeout=45) as response:
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


def prepare_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as original:
            if original.format not in {"PNG", "JPEG", "WEBP", "TIFF", "BMP"}:
                raise ValueError("不支持的图片格式")
            original.load()
            rgba = ImageOps.exif_transpose(original).convert("RGBA")
    except (UnidentifiedImageError, OSError):
        raise ValueError("图片附件无法读取") from None
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    image = background.convert("RGB")
    image.thumbnail((3000, 3000))
    return image


def palette(image: Image.Image, maximum_colors: int = MAX_PALETTE_COLORS) -> list[dict]:
    """提取尽可能完整但仍可读的代表色板，包含彩色和有意义的中性色。"""
    small = image.copy()
    small.thumbnail((360, 360))
    quantized = small.quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    raw = quantized.getpalette()
    colors = [(count, tuple(raw[index * 3:index * 3 + 3])) for count, index in sorted(quantized.getcolors(), reverse=True)]
    useful = [(count, rgb) for count, rgb in colors if sum(rgb) / 3 < 248]
    chromatic = [(count, rgb) for count, rgb in useful if max(rgb) - min(rgb) >= 16]
    neutral = [(count, rgb) for count, rgb in useful if max(rgb) - min(rgb) < 16]
    selected: list[tuple[int, tuple[int, int, int]]] = []
    for count, rgb in chromatic + neutral:
        if all(sum((a - b) ** 2 for a, b in zip(rgb, previous)) > 18 ** 2 for _, previous in selected):
            selected.append((count, rgb))
        if len(selected) == maximum_colors:
            break
    if not selected:
        selected = colors[:1]
    total = sum(count for count, _ in selected)
    return [{"hex": "#%02X%02X%02X" % rgb, "rgb": list(rgb), "weight": round(count / total * 100, 1)} for count, rgb in selected]


def contributor(sections: dict[str, str]) -> dict[str, str]:
    github_user = os.environ["ISSUE_USER"]
    return {
        "author": github_user,
        "contributor_name": clean(sections.get("投稿人姓名或昵称")) or github_user,
        "contributor_affiliation": clean(sections.get("所属机构（可选）")),
        "contributor_profile": safe_profile_url(sections.get("个人主页（可选）", "")),
    }


def base_record(identifier: str, sections: dict[str, str], paper_path: str, image_path: Path) -> dict:
    return {
        "id": identifier,
        "title": clean(sections["图片标题"]).splitlines()[0],
        **contributor(sections),
        "paper_title": clean(sections.get("所属论文标题")),
        "why": clean(sections["为什么觉得这张图好？"]),
        "usage": clean(sections["以后可以用在哪里？"]),
        "image": f"assets/{image_path.name}",
        "paper": paper_path,
        "issue_number": int(os.environ["ISSUE_NUMBER"]),
        "issue_url": os.environ["ISSUE_URL"],
    }


def extract_pdf_records(paper_bytes: bytes, identifier: str, sections: dict[str, str], paper_path: str) -> list[dict]:
    """提取 PDF 内嵌的主要栅格图片；小图标和重复图片会被过滤。"""
    records = []
    seen_xrefs = set()
    document = fitz.open(stream=paper_bytes, filetype="pdf")
    try:
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text")
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                extracted = document.extract_image(xref)
                try:
                    image = prepare_image(extracted["image"])
                except ValueError:
                    continue
                width, height = image.size
                if width < 220 or height < 160 or width * height < 60_000:
                    continue
                number = len(records) + 1
                auto_id = f"{identifier}-pdf-{number:02d}"
                image_path = ASSETS / f"{auto_id}.jpg"
                image.save(image_path, quality=90, optimize=True)
                record = base_record(auto_id, sections, paper_path, image_path)
                record.update({
                    "title": f"{record['paper_title'] or record['title']} · 自动抓取图 {number}",
                    "why": f"从投稿论文 PDF 第 {page_number} 页自动抓取，尚未经过人工推荐。",
                    "category": classify(" ".join([record["paper_title"], page_text])),
                    "palette": palette(image),
                    "recommended": False,
                    "source_type": "pdf_auto",
                    "pdf_page": page_number,
                })
                records.append(record)
                if len(records) >= MAX_PDF_FIGURES:
                    return records
    finally:
        document.close()
    return records


def main() -> None:
    sections = parse_sections(os.environ["ISSUE_BODY"])
    required = ["图片标题", "为什么觉得这张图好？", "以后可以用在哪里？", "科研图片"]
    if any(not clean(sections.get(field)) for field in required):
        raise ValueError("投稿缺少必填字段")
    image_url = first_url(sections["科研图片"])
    if not image_url:
        raise ValueError("没有找到图片附件链接")
    image_bytes, _ = download(image_url, MAX_IMAGE_BYTES)
    image = prepare_image(image_bytes)
    identifier = f"issue-{os.environ['ISSUE_NUMBER']}-{uuid4().hex[:8]}"
    ASSETS.mkdir(parents=True, exist_ok=True)
    image_path = ASSETS / f"{identifier}.jpg"
    image.save(image_path, quality=92, optimize=True)

    paper_bytes = None
    paper_path = ""
    paper_url = first_url(sections.get("论文 PDF（可选）", ""))
    if paper_url:
        paper_bytes, _ = download(paper_url, MAX_PDF_BYTES)
        if not paper_bytes.startswith(b"%PDF-"):
            raise ValueError("论文附件不是有效 PDF")
        pdf_file = ASSETS / f"{identifier}.pdf"
        pdf_file.write_bytes(paper_bytes)
        paper_path = f"assets/{pdf_file.name}"

    chosen = clean(sections.get("分类")) or "自动分类"
    combined = " ".join(clean(sections.get(x)) for x in ["图片标题", "所属论文标题", "为什么觉得这张图好？", "以后可以用在哪里？"])
    main_record = base_record(identifier, sections, paper_path, image_path)
    main_record.update({
        "category": classify(combined) if chosen == "自动分类" else chosen,
        "palette": palette(image),
        "recommended": True,
        "source_type": "recommended",
    })
    new_records = [main_record]
    if paper_bytes:
        new_records.extend(extract_pdf_records(paper_bytes, identifier, sections, paper_path))

    issue_number = int(os.environ["ISSUE_NUMBER"])
    records = [item for item in json.loads(DATA_FILE.read_text(encoding="utf-8")) if item.get("issue_number") != issue_number]
    records[0:0] = new_records
    rendered = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    DATA_FILE.write_text(rendered, encoding="utf-8")
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA.write_text(rendered, encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"title={main_record['title']}\n")
            handle.write(f"pdf_figures={len(new_records) - 1}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"投稿处理失败：{error}", file=sys.stderr)
        raise
