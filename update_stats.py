import json
import os
import re
import requests
import subprocess
import sys

def fetch_youtube_stats(video_id: str) -> tuple[int, str]:
    """유튜브 비디오의 조회수와 좋아요 수를 수집"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            view_match = re.search(r"\"viewCount\":\"(\d+)\"", response.text)
            like_match = re.search(r"\"iconName\":\"LIKE\",\"title\":\"([^\"]+)\"", response.text)
            
            views = int(view_match.group(1)) if view_match else 0
            likes = like_match.group(1) if like_match else "0"
            return views, likes
    except Exception as e:
        print(f"[-] 유튜브 통계 수집 중 오류 발생 ({video_id}): {e}")
    return 0, "0"

def main():
    json_path = "data/videos.json"
    if not os.path.exists(json_path):
        print(f"[-] {json_path} 파일이 존재하지 않습니다.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        videos = json.load(f)

    print(f"[*] 총 {len(videos)}개 영상의 조회수 및 좋아요 정보를 업데이트합니다...")
    updated_count = 0
    for video in videos:
        ytid = video.get("youtube_id")
        if not ytid:
            continue
        print(f"  -> 비디오 '{video.get('title')}' ({ytid}) 가져오는 중...")
        views, likes = fetch_youtube_stats(ytid)
        video["views"] = views
        video["likes"] = likes
        print(f"     조회수: {views:,}회 | 좋아요: {likes}")
        updated_count += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=4)

    print(f"[+] {updated_count}개 영상의 정보가 업데이트되어 videos.json에 저장되었습니다.")

    # 사이트 재생성
    print("[*] 사이트를 다시 빌드합니다...")
    subprocess.run([sys.executable, "generate.py"])
    print("[+] 빌드가 완료되었습니다.")

if __name__ == "__main__":
    main()
