import argparse
import json
import os
import sys
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BLOG_ID = os.getenv("NAVER_BLOG_ID", "ansony0227")
DEFAULT_CATEGORY_NO = os.getenv("NAVER_BLOG_CATEGORY_NO", "19")
DEFAULT_VISIBILITY = os.getenv("NAVER_BLOG_VISIBILITY", "public")  # "public" = 전체공개, "private" = 비공개
DEFAULT_USER_DATA_DIR = os.getenv("NAVER_USER_DATA_DIR", ".naver_profile")
DEFAULT_PAGES_URL = os.getenv("PAGES_URL", "https://meesokim.github.io/my-youtube-gallary")

VISIBILITY_LABELS = {
    "public": "전체공개",
    "private": "비공개",
}


def load_videos(json_path: str = "data/videos.json") -> list[dict]:
    """data/videos.json에서 비디오 목록을 로드합니다."""
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def select_video(
    videos: list[dict],
    youtube_id: Optional[str] = None,
    filename: Optional[str] = None,
    latest: bool = False,
) -> Optional[dict]:
    """조건에 맞는 비디오 항목을 선택합니다."""
    if not videos:
        return None
    if youtube_id:
        for video in videos:
            if video.get("youtube_id") == youtube_id:
                return video
        return None
    if filename:
        for video in videos:
            if video.get("filename") == filename:
                return video
        return None
    if latest:
        return videos[-1]
    return videos[-1]


def format_naver_blog_post(
    video: dict,
    pages_url: str = DEFAULT_PAGES_URL,
) -> tuple[str, list[str], list[str]]:
    """비디오 요약 데이터를 네이버 블로그 제목, 본문 문단 리스트, 태그 리스트로 변환합니다."""
    title = (video.get("title") or "유튜브 영상 정리").strip()
    paragraphs: list[str] = []

    blog_intro = (video.get("blog_intro") or "").strip()
    blog_sections = video.get("blog_sections") or []
    blog_conclusion = (video.get("blog_conclusion") or "").strip()
    recommendation = (video.get("recommendation") or "").strip()

    if blog_intro:
        paragraphs.extend([p.strip() for p in blog_intro.split("\n\n") if p.strip()])

    if blog_sections:
        for section in blog_sections:
            heading = (section.get("heading") or "").strip()
            content = (section.get("content") or "").strip()
            key_quote = (section.get("key_quote") or "").strip()
            if heading:
                paragraphs.append(f"■ {heading}")
            if content:
                paragraphs.extend([p.strip() for p in content.split("\n\n") if p.strip()])
            if key_quote:
                paragraphs.append(f"💬 \"{key_quote}\"")
    else:
        overview = (video.get("overview") or "").strip()
        points = video.get("points") or []
        if overview:
            paragraphs.append(overview)
        for idx, pt in enumerate(points, 1):
            paragraphs.append(f"{idx}. {pt}")

    if blog_conclusion:
        paragraphs.extend([p.strip() for p in blog_conclusion.split("\n\n") if p.strip()])

    if recommendation:
        paragraphs.append(f"👉 추천 한마디: {recommendation}")

    ytid = (video.get("youtube_id") or "").strip()
    fname = (video.get("filename") or "").strip()
    links: list[str] = []
    if ytid:
        links.append(f"▶ 원본 영상 보기: https://www.youtube.com/watch?v={ytid}")
    if fname and pages_url:
        links.append(f"📄 슬라이드 및 상세 정리: {pages_url.rstrip('/')}/{fname}.html")
    if links:
        paragraphs.extend(links)

    raw_keywords = video.get("keywords") or ""
    tags = [kw.strip().lstrip("#").replace(" ", "") for kw in raw_keywords.split(",") if kw.strip()]
    return title, paragraphs, tags


def _get_editor_root(page):
    """SmartEditor ONE이 iframe(#mainFrame) 내부에 있으면 해당 Frame을, 아니면 page를 반환합니다."""
    try:
        frame_el = page.locator("iframe#mainFrame")
        if frame_el.count() > 0:
            frame = page.frame(name="mainFrame") or frame_el.first.content_frame()
            if frame is not None:
                return frame
    except Exception:
        pass
    return page


def _dismiss_editor_popups(root) -> None:
    """임시저장 복구 팝업이나 도움말 오버레이가 뜨면 닫습니다."""
    cancel_selectors = [
        "button.se-popup-button-cancel",
        "button:has-text('취소')",
        "button.se-help-panel-close-button",
    ]
    for sel in cancel_selectors:
        try:
            btn = root.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click()
                time.sleep(0.3)
        except Exception:
            pass


def _select_visibility_in_publish_layer(root, visibility: str) -> None:
    """발행 레이어에서 공개 설정(전체공개 / 비공개)을 명시적으로 선택합니다."""
    target_label = VISIBILITY_LABELS.get(visibility, "전체공개")
    selectors = [
        f"label:has-text('{target_label}')",
        f"span:has-text('{target_label}')",
        f"button:has-text('{target_label}')",
    ]
    for sel in selectors:
        try:
            loc = root.locator(sel).first
            if loc.is_visible(timeout=1500):
                loc.click()
                time.sleep(0.3)
                print(f"[+] 공개 설정 선택 완료: {target_label}")
                return
        except Exception:
            continue
    print(f"[!] 경고: 발행 창에서 '{target_label}' 선택 요소를 찾지 못했습니다. 기본 설정을 확인하세요.")


def publish_to_naver_blog(
    video: dict,
    blog_id: str = DEFAULT_BLOG_ID,
    category_no: str = DEFAULT_CATEGORY_NO,
    visibility: str = DEFAULT_VISIBILITY,
    user_data_dir: str = DEFAULT_USER_DATA_DIR,
    headless: bool = False,
    login_only: bool = False,
    draft_only: bool = False,
) -> bool:
    """Playwright persistent context를 사용해 네이버 블로그에 글을 발행합니다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[-] playwright가 설치되어 있지 않습니다. `.venv/bin/pip install playwright` 후 다시 실행하세요.")
        return False

    if visibility not in VISIBILITY_LABELS:
        raise ValueError(f"지원하지 않는 visibility 값입니다: {visibility} (public 또는 private 사용)")

    title, paragraphs, tags = format_naver_blog_post(video) if video else ("", [], [])

    os.makedirs(user_data_dir, exist_ok=True)
    write_url = f"https://blog.naver.com/{blog_id}/postwrite?categoryNo={category_no}"

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if login_only:
                print("[*] 브라우저에서 네이버 로그인을 완료해주세요. 로그인 후 글쓰기 페이지로 이동하면 세션이 저장됩니다.")
                page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
                page.wait_for_url(
                    lambda url: "nid.naver.com" not in url,
                    timeout=300_000,
                )
                page.goto(write_url, wait_until="domcontentloaded")
                time.sleep(2)
                print(f"[+] 로그인 세션이 '{user_data_dir}'에 저장되었습니다.")
                return True

            print(f"[*] 네이버 블로그 글쓰기 페이지 열기: {write_url}")
            page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)

            if "nid.naver.com" in page.url:
                if headless:
                    print("[-] 네이버 로그인이 필요합니다. 먼저 `--login` 옵션으로 1회 로그인해 주세요.")
                    return False
                print("[*] 네이버 로그인이 필요합니다. 열린 브라우저에서 직접 로그인을 완료해 주세요...")
                page.wait_for_url(lambda url: "nid.naver.com" not in url, timeout=300_000)
                page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(2)

            root = _get_editor_root(page)
            _dismiss_editor_popups(root)

            # 제목 입력
            title_loc = root.locator(".se-documentTitle .se-text-paragraph").first
            title_loc.wait_for(state="visible", timeout=15_000)
            title_loc.click()
            page.keyboard.type(title, delay=10)
            time.sleep(0.3)

            # 본문 입력
            body_loc = root.locator(".se-component.se-text .se-text-paragraph").last
            body_loc.click()
            for idx, para in enumerate(paragraphs):
                page.keyboard.type(para, delay=2)
                if idx < len(paragraphs) - 1:
                    page.keyboard.press("Enter")
                    page.keyboard.press("Enter")
            time.sleep(0.5)

            if draft_only:
                print("[*] --draft 옵션이 지정되어 발행을 누르지 않고 입력만 완료했습니다.")
                return True

            # 상단 발행 버튼 클릭
            publish_open_btn = root.locator("button[class*='publish_btn'], button:has-text('발행')").first
            publish_open_btn.click()
            time.sleep(1)

            # 공개 설정 선택 (기본: 전체공개)
            _select_visibility_in_publish_layer(root, visibility)

            # 태그 입력
            if tags:
                tag_input = root.locator("input[placeholder*='태그']").first
                try:
                    if tag_input.is_visible(timeout=1500):
                        for tag in tags[:10]:
                            tag_input.fill(tag)
                            page.keyboard.press("Enter")
                            time.sleep(0.1)
                except Exception:
                    pass

            # 최종 발행 확인 버튼 클릭
            confirm_btn = root.locator("button[class*='confirm_btn']").first
            if confirm_btn.count() == 0:
                confirm_btn = root.locator("div[class*='publish'] button:has-text('발행')").last
            confirm_btn.click()
            time.sleep(3)

            print(f"[+] 네이버 블로그 발행 완료 ({VISIBILITY_LABELS[visibility]}): {page.url}")
            return True
        finally:
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="ytubereco 요약 글을 네이버 블로그에 발행합니다.")
    parser.add_argument("--login", action="store_true", help="브라우저를 열어 네이버 로그인 세션을 저장합니다.")
    parser.add_argument("--id", dest="youtube_id", help="발행할 유튜브 video_id")
    parser.add_argument("--filename", help="발행할 비디오의 filename")
    parser.add_argument("--latest", action="store_true", help="data/videos.json의 가장 최근 항목을 발행합니다.")
    parser.add_argument("--blog-id", default=DEFAULT_BLOG_ID, help=f"네이버 블로그 ID (기본값: {DEFAULT_BLOG_ID})")
    parser.add_argument("--category-no", default=DEFAULT_CATEGORY_NO, help=f"카테고리 번호 (기본값: {DEFAULT_CATEGORY_NO})")
    parser.add_argument(
        "--visibility",
        choices=["public", "private"],
        default=DEFAULT_VISIBILITY,
        help="공개 범위 (public: 전체공개, private: 비공개, 기본값: public)",
    )
    parser.add_argument("--user-data-dir", default=DEFAULT_USER_DATA_DIR, help="Playwright 세션 저장 경로")
    parser.add_argument("--headless", action="store_true", help="헤드리스 모드로 실행")
    parser.add_argument("--draft", action="store_true", help="발행 버튼을 누르지 않고 에디터 입력까지만 수행")
    parser.add_argument("--dry-run", action="store_true", help="실제 브라우저 실행 없이 변환된 글과 설정만 출력")
    args = parser.parse_args()

    if args.login:
        ok = publish_to_naver_blog(
            video={},
            blog_id=args.blog_id,
            category_no=args.category_no,
            visibility=args.visibility,
            user_data_dir=args.user_data_dir,
            headless=False,
            login_only=True,
        )
        return 0 if ok else 1

    videos = load_videos()
    video = select_video(videos, youtube_id=args.youtube_id, filename=args.filename, latest=args.latest)
    if not video:
        print("[-] 발행할 비디오 데이터를 찾지 못했습니다.")
        return 1

    if args.dry_run:
        title, paragraphs, tags = format_naver_blog_post(video)
        print(f"블로그 ID: {args.blog_id}")
        print(f"카테고리 번호: {args.category_no}")
        print(f"공개 설정: {VISIBILITY_LABELS[args.visibility]} ({args.visibility})")
        print(f"제목: {title}")
        print(f"태그: {', '.join(tags)}")
        print("-" * 40)
        print("\n\n".join(paragraphs[:4]))
        if len(paragraphs) > 4:
            print(f"\n... (총 {len(paragraphs)}개 문단)")
        return 0

    ok = publish_to_naver_blog(
        video=video,
        blog_id=args.blog_id,
        category_no=args.category_no,
        visibility=args.visibility,
        user_data_dir=args.user_data_dir,
        headless=args.headless,
        draft_only=args.draft,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
