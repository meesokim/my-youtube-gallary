import unittest
from unittest.mock import patch

import publish_naver_blog


class NaverBlogPublisherTests(unittest.TestCase):
    def test_defaults_are_public_and_target_blog(self):
        self.assertEqual(publish_naver_blog.DEFAULT_BLOG_ID, "ansony0227")
        self.assertEqual(publish_naver_blog.DEFAULT_CATEGORY_NO, "19")
        self.assertEqual(publish_naver_blog.DEFAULT_VISIBILITY, "public")
        self.assertEqual(publish_naver_blog.VISIBILITY_LABELS["public"], "전체공개")

    def test_format_naver_blog_post_with_rich_sections(self):
        video = {
            "title": "내가 직접 보고 느낀 AI 이야기",
            "blog_intro": "처음엔 반신반의했어요.\n\n그런데 막상 보니 생각이 달라졌습니다.",
            "blog_sections": [
                {
                    "heading": "1. 왜 지금 이 흐름이 중요할까?",
                    "content": "첫 문단입니다.\n\n두 번째 문단입니다.",
                    "key_quote": "결국 쓰는 사람이 중심이 되어야 한다.",
                }
            ],
            "blog_conclusion": "저도 당장 내일부터 조금씩 써보려고요.",
            "recommendation": "고민 중인 분들께 꼭 추천하고 싶어요.",
            "youtube_id": "MTVZxNnPLKo",
            "filename": "test-blog",
            "keywords": "AI, 개인생각, 자동화",
        }
        title, paragraphs, tags = publish_naver_blog.format_naver_blog_post(
            video, pages_url="https://example.com"
        )
        self.assertEqual(title, "내가 직접 보고 느낀 AI 이야기")
        self.assertIn("처음엔 반신반의했어요.", paragraphs)
        self.assertIn("■ 1. 왜 지금 이 흐름이 중요할까?", paragraphs)
        self.assertIn('💬 "결국 쓰는 사람이 중심이 되어야 한다."', paragraphs)
        self.assertIn("저도 당장 내일부터 조금씩 써보려고요.", paragraphs)
        self.assertIn("▶ 원본 영상 보기: https://www.youtube.com/watch?v=MTVZxNnPLKo", paragraphs)
        self.assertIn("📄 슬라이드 및 상세 정리: https://example.com/test-blog.html", paragraphs)
        self.assertEqual(tags, ["AI", "개인생각", "자동화"])

    def test_format_naver_blog_post_legacy_fallback(self):
        video = {
            "title": "예전 형식 영상",
            "overview": "전체 요약입니다.",
            "points": ["핵심 1", "핵심 2"],
            "youtube_id": "abc12345678",
        }
        title, paragraphs, tags = publish_naver_blog.format_naver_blog_post(video)
        self.assertEqual(title, "예전 형식 영상")
        self.assertIn("전체 요약입니다.", paragraphs)
        self.assertIn("1. 핵심 1", paragraphs)
        self.assertIn("2. 핵심 2", paragraphs)
        self.assertEqual(tags, [])

    def test_select_video(self):
        videos = [
            {"youtube_id": "id1", "filename": "f1"},
            {"youtube_id": "id2", "filename": "f2"},
        ]
        self.assertEqual(publish_naver_blog.select_video(videos, youtube_id="id1")["filename"], "f1")
        self.assertEqual(publish_naver_blog.select_video(videos, filename="f2")["youtube_id"], "id2")
        self.assertEqual(publish_naver_blog.select_video(videos, latest=True)["youtube_id"], "id2")

    def test_dry_run_cli(self):
        sample = [{"title": "테스트", "overview": "개요", "youtube_id": "id1", "keywords": "테스트"}]
        with patch.object(publish_naver_blog, "load_videos", return_value=sample), \
             patch("sys.argv", ["publish_naver_blog.py", "--latest", "--dry-run"]):
            self.assertEqual(publish_naver_blog.main(), 0)


if __name__ == "__main__":
    unittest.main()
