import unittest
from PIL import Image
from scripts.process_submission import classify, first_url, palette, parse_sections

class ProcessingTests(unittest.TestCase):
    def test_issue_sections(self):
        body = "### 图片标题\n机制图\n\n### 分类\n自动分类\n\n### 科研图片\n![a](https://github.com/user-attachments/assets/1)"
        parsed = parse_sections(body)
        self.assertEqual(parsed["图片标题"], "机制图")
        self.assertIn("user-attachments", parsed["科研图片"])

    def test_classification_and_palette(self):
        self.assertEqual(classify("调控通路机制 schematic"), "机制与示意图")
        image = Image.new("RGB", (100, 100), "#207050")
        colors = palette(image)
        self.assertEqual(colors[0]["hex"], "#207050")

    def test_html_attachment_url_stops_before_quote(self):
        html = '<img alt="Image" src="https://github.com/user-attachments/assets/example-id" />'
        self.assertEqual(first_url(html), "https://github.com/user-attachments/assets/example-id")

if __name__ == "__main__": unittest.main()
