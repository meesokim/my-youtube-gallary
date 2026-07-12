import os
import sys
import subprocess
import json
import requests
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

def get_repo_name():
    """git remote URL로부터 'owner/repo' 추출"""
    try:
        url = subprocess.check_output(["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        import re
        match = re.search(r"github\.com[:/]([^/]+/[^.]+)", url)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "meesokim/my-youtube-gallary"  # 기본값 fallback

def get_github_token():
    """.env 또는 시스템 환경변수에서 GitHub Token 획득"""
    return os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")

def check_gh_cli():
    """gh CLI가 설치되어 있고 로그인되어 있는지 체크"""
    try:
        res = subprocess.run(["gh", "auth", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode == 0
    except FileNotFoundError:
        return False

def create_issue(repo, title, body, token=None):
    """GitHub에 새로운 이슈를 생성하고 생성된 이슈 정보를 반환"""
    # 1. gh CLI 사용
    if check_gh_cli():
        try:
            print("[*] GitHub CLI(gh)를 사용하여 이슈를 생성합니다...")
            res = subprocess.run(
                ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            output_url = res.stdout.strip()
            # 생성된 URL에서 이슈 번호 추출 (예: https://github.com/owner/repo/issues/123)
            import re
            match = re.search(r"/issues/(\d+)", output_url)
            if match:
                num = int(match.group(1))
                return num, output_url
            return None, output_url
        except Exception as e:
            print(f"[!] gh CLI로 이슈 생성 중 오류 발생: {e}")

    # 2. GitHub REST API 사용
    if token:
        try:
            print("[*] GitHub API (HTTP)를 사용하여 이슈를 생성합니다...")
            url = f"https://api.github.com/repos/{repo}/issues"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.post(url, headers=headers, json={"title": title, "body": body}, timeout=10)
            if res.status_code == 201:
                data = res.json()
                return data.get("number"), data.get("html_url")
            else:
                print(f"[!] API로 이슈 생성 실패 (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] GitHub API 이슈 생성 중 오류 발생: {e}")
            
    return None, None

def main():
    repo = get_repo_name()
    token = get_github_token()
    
    if not check_gh_cli() and not token:
        print("[!] 에러: GitHub CLI(gh)에 로그인되어 있지 않고, .env에 GH_TOKEN(또는 GITHUB_TOKEN)도 설정되어 있지 않습니다.")
        print("    이슈 생성을 위해 gh CLI 로그인 혹은 토큰 환경변수가 필요합니다.")
        sys.exit(1)
        
    print("=============================================")
    print(" GitHub 로컬 이슈 생성 및 자동 처리 트리거")
    print("=============================================")
    print("")
    
    youtube_url = input("▶ 생성할 유튜브 영상 링크: ").strip()
    if not youtube_url:
        print("[-] 에러: 유튜브 링크는 필수 입력 사항입니다.")
        sys.exit(1)
        
    body = input("▶ 요약 및 정리 취지 (엔터 치면 기본 요약): ").strip()
    
    print(f"\n[*] 1단계: GitHub 저장소({repo})에 이슈 생성 중...")
    num, url = create_issue(repo, youtube_url, body, token)
    
    if not num:
        print("[-] 이슈 생성에 실패했습니다. 자격 증명을 확인하세요.")
        sys.exit(1)
        
    print(f"[+] 이슈 생성 성공! 이슈 번호: #{num}")
    print(f"    이슈 URL: {url}")
    
    print("\n[*] 2단계: 로컬 이슈 워커(process_issues_locally.py)를 구동하여 즉시 요약 및 배포 처리 중...")
    # process_issues_locally.py 실행하여 방금 생성한 이슈 처리
    subprocess.run(["python", "process_issues_locally.py"])
    
    print("\n=============================================")
    print("[+] 로컬 이슈 생성 및 전체 요약/배포 작업이 완료되었습니다!")
    print("=============================================")

if __name__ == "__main__":
    main()
