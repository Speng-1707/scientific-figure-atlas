from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from PIL import Image
import scripts.process_submission as processing
from scripts.process_submission import classify, first_url, palette, parse_sections

class ProcessingTests(unittest.TestCase):
    def test_issue_sections(self):
        body = "### 图片标题\n机制图\n\n### 分类\n自动分类\n\n### 科研图片\n![a](https://github.com/user-attachments/assets/1)"
        parsed = parse_sections(body)
        self.assertEqual(parsed["图片标题"], "机制图")
        self.assertIn("user-attachments", parsed["科研图片"])

    def test_classification_and_palette(self):
        self.assertEqual(classify("调控通路机制 schematic"), "机制与示意图")
        image = Image.new("RGB", (180, 100))
        for x in range(180):
            for y in range(100):
                image.putpixel((x, y), ((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256))
        colors = palette(image)
        self.assertGreaterEqual(len(colors), 12)
        self.assertLessEqual(len(colors), 18)

    def test_html_attachment_url_stops_before_quote(self):
        html = '<img alt="Image" src="https://github.com/user-attachments/assets/example-id" />'
        self.assertEqual(first_url(html), "https://github.com/user-attachments/assets/example-id")

    def test_pdf_embedded_image_becomes_auto_record(self):
        stream = BytesIO()
        Image.new("RGB", (400, 240), "#207050").save(stream, "PNG")
        document = fitz.open()
        page = document.new_page(width=500, height=400)
        page.insert_text((40, 40), "regional spatial map")
        page.insert_image(fitz.Rect(40, 80, 440, 320), stream=stream.getvalue())
        pdf = document.tobytes(); document.close()
        sections = {"图片标题": "主图", "投稿人姓名或昵称": "测试者", "所属论文标题": "Spatial study",
                    "为什么觉得这张图好？": "清晰", "以后可以用在哪里？": "汇报"}
        with tempfile.TemporaryDirectory() as directory:
            original_assets = processing.ASSETS
            processing.ASSETS = Path(directory)
            os.environ.update(ISSUE_USER="tester", ISSUE_NUMBER="99", ISSUE_URL="https://example.test/99")
            try:
                records = processing.extract_pdf_records(pdf, "test", sections, "assets/test.pdf")
            finally:
                processing.ASSETS = original_assets
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["recommended"])
        self.assertEqual(records[0]["source_type"], "pdf_auto")
        self.assertEqual(records[0]["category"], "地图与空间")

if __name__ == "__main__": unittest.main()
