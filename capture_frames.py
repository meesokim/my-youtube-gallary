import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Optional


def format_timestamp(seconds: int) -> str:
    """초 단위 정수를 MM:SS 또는 HH:MM:SS 문자열로 변환합니다."""
    sec = max(0, int(seconds))
    hours, rem = divmod(sec, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _find_ytdlp() -> Optional[str]:
    """현재 Python 환경(bin)을 우선 확인한 뒤 PATH에서 yt-dlp 실행 파일을 찾습니다."""
    candidate = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    found = shutil.which("yt-dlp")
    if found:
        return found
    return None


def _build_ytdlp_env() -> dict[str, str]:
    """yt-dlp의 JS 챌린지 해결을 위해 deno 경로(~/.deno/bin)를 PATH에 포함합니다."""
    env = os.environ.copy()
    deno_bin = os.path.expanduser("~/.deno/bin")
    if os.path.isdir(deno_bin):
        env["PATH"] = f"{deno_bin}:{env.get('PATH', '')}"
    return env


def get_youtube_stream_url(video_id: str) -> Optional[str]:
    """yt-dlp를 사용해 유튜브 영상의 직접 스트림 URL을 한 번만 조회합니다."""
    ytdlp_bin = _find_ytdlp()
    if not ytdlp_bin:
        return None

    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        res = subprocess.run(
            [
                ytdlp_bin,
                "--remote-components",
                "ejs:github",
                "-g",
                "-f",
                "b[height<=720]/b/bv*[height<=720]",
                watch_url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=_build_ytdlp_env(),
            check=True,
        )
        urls = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return urls[0] if urls else None
    except Exception as e:
        print(f"[-] yt-dlp 스트림 URL 조회 실패 ({video_id}): {e}")
        return None


def capture_frame_ffmpeg(stream_url: str, timestamp_sec: int, output_path: str) -> bool:
    """ffmpeg로 스트림 URL의 지정 시점 1프레임을 JPEG로 저장합니다."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or not stream_url:
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        subprocess.run(
            [
                ffmpeg_bin,
                "-ss",
                str(max(0, int(timestamp_sec))),
                "-i",
                stream_url,
                "-frames:v",
                "1",
                "-q:v",
                "3",
                "-y",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"[-] ffmpeg 프레임 캡처 실패 (@ {timestamp_sec}s): {e}")
        return False


def capture_frame_ytdlp_ffmpeg(video_id: str, timestamp_sec: int, output_path: str) -> bool:
    """단일 시점 캡처용 헬퍼 (yt-dlp로 스트림 URL 조회 후 ffmpeg 캡처)."""
    stream_url = get_youtube_stream_url(video_id)
    if not stream_url:
        return False
    return capture_frame_ffmpeg(stream_url, timestamp_sec, output_path)


def capture_frame_playwright(video_id: str, timestamp_sec: int, output_path: str) -> bool:
    """Playwright 헤드리스 Chromium으로 유튜브 임베드 플레이어 화면을 폴백 캡처합니다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    sec = max(0, int(timestamp_sec))
    embed_url = f"https://www.youtube.com/embed/{video_id}?start={sec}&autoplay=1&mute=1"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            try:
                page.goto(embed_url, wait_until="domcontentloaded", timeout=20_000)
                video_loc = page.locator("video").first
                video_loc.wait_for(state="visible", timeout=10_000)
                page.wait_for_timeout(3000)
                video_loc.screenshot(path=output_path, type="jpeg", quality=85)
                return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
            finally:
                browser.close()
    except Exception as e:
        print(f"[-] Playwright 프레임 캡처 실패 ({video_id} @ {sec}s): {e}")
        return False


def compute_frame_signature(image_path: str) -> Optional[list[int]]:
    """이미지를 32x18 그레이스케일로 축소해 중복/공백 판별용 시그니처를 계산합니다."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            small = img.convert("L").resize((32, 18))
            return list(small.getdata())
    except Exception:
        return None


def is_blank_frame(sig: list[int]) -> bool:
    """검은 화면이나 단색 화면처럼 정보량이 거의 없는 프레임인지 판별합니다."""
    if not sig:
        return True
    mean_val = sum(sig) / len(sig)
    spread = max(sig) - min(sig)
    return mean_val < 12 or spread < 15


def is_duplicate_frame(
    sig: list[int],
    existing_sigs: list[list[int]],
    threshold: float = 8.0,
) -> bool:
    """기존에 선택된 프레임과 픽셀 평균 절대 차이(MAD)가 임계값 미만이면 중복으로 판별합니다."""
    if not sig or not existing_sigs:
        return False
    for prev in existing_sigs:
        if len(prev) != len(sig):
            continue
        mad = sum(abs(a - b) for a, b in zip(sig, prev)) / len(sig)
        if mad < threshold:
            return True
    return False


def capture_section_frames(
    video_id: str,
    blog_sections: list[dict],
    output_root: str = "docs/captures",
) -> list[dict]:
    """blog_sections 각 항목의 timestamp_sec 시점을 캡처하되, 중복·공백 프레임은 다른 시점으로 대체하거나 제외합니다."""
    if not video_id or not blog_sections:
        return blog_sections

    target_dir = os.path.join(output_root, video_id)
    os.makedirs(target_dir, exist_ok=True)

    stream_url = get_youtube_stream_url(video_id)
    accepted_sigs: list[list[int]] = []
    used_secs: set[int] = set()
    probe_offsets = [0, 12, -12, 25, -25, 45, 70]

    for idx, section in enumerate(blog_sections, start=1):
        raw_sec = section.get("timestamp_sec")
        if raw_sec is None:
            base_sec = 30 + (idx - 1) * 90
        else:
            try:
                base_sec = max(0, int(raw_sec))
            except (TypeError, ValueError):
                base_sec = 30 + (idx - 1) * 90

        filename = f"section_{idx}.jpg"
        output_path = os.path.join(target_dir, filename)
        rel_path = f"captures/{video_id}/{filename}"

        # 이미 캡처된 파일이 있고 중복이 아니면 재사용
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            sig = compute_frame_signature(output_path)
            if sig and not is_blank_frame(sig) and not is_duplicate_frame(sig, accepted_sigs):
                accepted_sigs.append(sig)
                section["timestamp_sec"] = base_sec
                section["timestamp_label"] = format_timestamp(base_sec)
                section["image"] = rel_path
                used_secs.add(base_sec)
                continue

        captured_ok = False
        chosen_sec = base_sec

        for offset in probe_offsets:
            cand_sec = max(5, base_sec + offset)
            if cand_sec in used_secs:
                continue

            ok = (
                capture_frame_ffmpeg(stream_url, cand_sec, output_path)
                if stream_url
                else capture_frame_ytdlp_ffmpeg(video_id, cand_sec, output_path)
            )
            if not ok:
                ok = capture_frame_playwright(video_id, cand_sec, output_path)
            if not ok:
                continue

            sig = compute_frame_signature(output_path)
            if sig is None:
                captured_ok = True
                chosen_sec = cand_sec
                break

            if is_blank_frame(sig) or is_duplicate_frame(sig, accepted_sigs):
                continue

            accepted_sigs.append(sig)
            captured_ok = True
            chosen_sec = cand_sec
            break

        if captured_ok:
            used_secs.add(chosen_sec)
            section["timestamp_sec"] = chosen_sec
            section["timestamp_label"] = format_timestamp(chosen_sec)
            section["image"] = rel_path
            print(f"[+] 화면 캡처 완료 ({section['timestamp_label']}): {output_path}")
        else:
            if os.path.isfile(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            section.pop("image", None)
            section["timestamp_sec"] = base_sec
            section["timestamp_label"] = format_timestamp(base_sec)
            print(f"[!] 중복 또는 공백 화면으로 인해 섹션 {idx} 캡처를 생략합니다.")

    return blog_sections


def main() -> int:
    parser = argparse.ArgumentParser(description="videos.json 항목의 유튜브 섹션별 화면 캡처를 생성합니다.")
    parser.add_argument("--id", dest="youtube_id", help="캡처할 유튜브 video_id")
    parser.add_argument("--latest", action="store_true", help="가장 최근 영상 1개만 캡처")
    parser.add_argument("--json-path", default="data/videos.json", help="videos.json 경로")
    args = parser.parse_args()

    if not os.path.exists(args.json_path):
        print(f"[-] 파일을 찾을 수 없습니다: {args.json_path}")
        return 1

    with open(args.json_path, "r", encoding="utf-8") as f:
        videos = json.load(f)

    targets = []
    if args.youtube_id:
        targets = [v for v in videos if v.get("youtube_id") == args.youtube_id]
    elif args.latest and videos:
        targets = [videos[-1]]
    else:
        print("[-] --id <youtube_id> 또는 --latest 옵션을 지정하세요.")
        return 1

    if not targets:
        print("[-] 대상 영상을 찾지 못했습니다.")
        return 1

    for video in targets:
        sections = video.get("blog_sections") or []
        if sections:
            capture_section_frames(video["youtube_id"], sections)

    with open(args.json_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=4)
    print("[+] videos.json 업데이트 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
