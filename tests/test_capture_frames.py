import os
import tempfile
import unittest
from unittest.mock import patch

from jinja2 import Environment, FileSystemLoader
from PIL import Image

import capture_frames
import fetch_and_summery


class CaptureFramesTests(unittest.TestCase):
    def test_format_timestamp(self):
        self.assertEqual(capture_frames.format_timestamp(0), "00:00")
        self.assertEqual(capture_frames.format_timestamp(125), "02:05")
        self.assertEqual(capture_frames.format_timestamp(3665), "01:01:05")

    def test_blog_section_schema_has_timestamp_sec(self):
        self.assertIn("timestamp_sec", fetch_and_summery.BlogSection.model_fields)

    def test_capture_section_frames_deduplicates_identical_frames(self):
        sections = [
            {"heading": "1. 도입", "timestamp_sec": 30, "content": "내용 1", "key_quote": "인용 1"},
            {"heading": "2. 전개", "timestamp_sec": 30, "content": "내용 2", "key_quote": "인용 2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            def fake_ffmpeg(stream_url, sec, out_path):
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                # 30초는 첫 섹션과 동일 이미지, 42초(+12초)는 다른 패턴 이미지 생성
                img = Image.new("RGB", (64, 36), (30, 60, 120))
                if sec == 30:
                    for x in range(32):
                        img.putpixel((x, 10), (240, 240, 240))
                else:
                    for x in range(32, 64):
                        for y in range(18, 36):
                            img.putpixel((x, y), (250, 220, 40))
                img.save(out_path, "JPEG")
                return True

            with patch.object(capture_frames, "get_youtube_stream_url", return_value="https://example.com/stream"), \
                 patch.object(capture_frames, "capture_frame_ffmpeg", side_effect=fake_ffmpeg):
                updated = capture_frames.capture_section_frames("MTVZxNnPLKo", sections, output_root=tmpdir)

            self.assertEqual(updated[0]["timestamp_sec"], 30)
            self.assertEqual(updated[0]["image"], "captures/MTVZxNnPLKo/section_1.jpg")
            # 두 번째 섹션은 30초와 달라진 42초(+12초) 프레임을 선택해야 함
            self.assertEqual(updated[1]["timestamp_sec"], 42)
            self.assertEqual(updated[1]["image"], "captures/MTVZxNnPLKo/section_2.jpg")

    def test_capture_section_frames_skips_when_only_duplicate_available(self):
        sections = [
            {"heading": "1. 도입", "timestamp_sec": 30, "content": "내용 1", "key_quote": "인용 1"},
            {"heading": "2. 같은화면", "timestamp_sec": 90, "content": "내용 2", "key_quote": "인용 2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            def fake_always_same(stream_url, sec, out_path):
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                img = Image.new("RGB", (64, 36), (40, 80, 140))
                for x in range(20):
                    img.putpixel((x, 5), (250, 250, 250))
                img.save(out_path, "JPEG")
                return True

            with patch.object(capture_frames, "get_youtube_stream_url", return_value="https://example.com/stream"), \
                 patch.object(capture_frames, "capture_frame_ffmpeg", side_effect=fake_always_same):
                updated = capture_frames.capture_section_frames("MTVZxNnPLKo", sections, output_root=tmpdir)

            self.assertIn("image", updated[0])
            self.assertNotIn("image", updated[1])

    def test_video_template_renders_capture_figure_without_youtube_link(self):
        env = Environment(loader=FileSystemLoader("templates"))
        env.globals["encode_url"] = lambda s: s
        env.globals["pages_url"] = "https://example.com"
        template = env.get_template("video.html")

        video = {
            "title": "캡처 테스트",
            "overview": "개요",
            "points": ["p1", "p2", "p3"],
            "blog_intro": "서론",
            "blog_sections": [
                {
                    "heading": "1. 첫 장면",
                    "timestamp_sec": 90,
                    "timestamp_label": "01:30",
                    "image": "captures/MTVZxNnPLKo/section_1.jpg",
                    "content": "본문",
                    "key_quote": "인용구",
                },
            ],
            "blog_conclusion": "결론",
            "category": "AI",
            "keywords": "AI",
            "filename": "test-capture",
            "youtube_id": "MTVZxNnPLKo",
            "recommendation": "추천",
        }
        rendered = template.render(video=video)
        self.assertIn('class="blog-capture"', rendered)
        self.assertIn('./captures/MTVZxNnPLKo/section_1.jpg', rendered)
        self.assertIn("1. 첫 장면 (01:30)", rendered)
        self.assertNotIn("youtube.com/watch?v=MTVZxNnPLKo&t=90s", rendered)

    def test_create_pptx_embeds_unique_section_images(self):
        from pptx import Presentation
        import generate

        with tempfile.TemporaryDirectory() as tmpdir:
            img1 = os.path.join(tmpdir, "s1.jpg")
            img2 = os.path.join(tmpdir, "s2.jpg")
            Image.new("RGB", (320, 180), (20, 40, 80)).save(img1, "JPEG")
            Image.new("RGB", (320, 180), (80, 40, 20)).save(img2, "JPEG")

            video_data = {
                "title": "PPTX 이미지 테스트",
                "overview": "개요 문장",
                "points": ["인사이트 1: 설명 1", "인사이트 2: 설명 2", "인사이트 3: 설명 3"],
                "blog_sections": [
                    {"heading": "섹션 1", "image": img1, "timestamp_label": "00:35"},
                    {"heading": "섹션 2", "image": img2, "timestamp_label": "03:00"},
                    {"heading": "섹션 2 중복", "image": img2, "timestamp_label": "03:00"},
                ],
                "category": "AI",
                "keywords": "AI, PPTX",
                "youtube_id": "FOulPu0TvHs",
                "recommendation": "추천합니다.",
            }
            out_pptx = os.path.join(tmpdir, "out.pptx")
            generate.create_pptx(video_data, out_pptx)

            prs = Presentation(out_pptx)
            # 슬라이드 2, 3에는 그림(shape_type == 13)이 1개씩 들어가고, 중복된 3번째는 제외되어야 함
            pic_counts = [sum(1 for s in slide.shapes if s.shape_type == 13) for slide in prs.slides]
            self.assertEqual(pic_counts, [0, 1, 1, 0, 0])


if __name__ == "__main__":
    unittest.main()
