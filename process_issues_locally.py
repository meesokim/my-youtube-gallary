import os
import re
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
        # git@github.com:owner/repo.git 또는 https://github.com/owner/repo.git 매칭
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

def get_open_issues(repo, token=None):
    """열려있는 이슈 목록 조회 (제목에 유튜브 링크가 포함된 이슈 필터링용)"""
    # 1. gh CLI가 동작하는 경우 최우선 사용
    if check_gh_cli():
        try:
            print("[*] GitHub CLI(gh)를 사용하여 이슈 목록을 불러옵니다...")
            res = subprocess.run(
                ["gh", "issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,body"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            return json.loads(res.stdout)
        except Exception as e:
            print(f"[!] gh CLI로 이슈를 가져오는 중 오류 발생: {e}")

    # 2. 토큰을 이용한 직접 GitHub API 호출
    if token:
        try:
            print("[*] GitHub API (HTTP)를 사용하여 이슈 목록을 불러옵니다...")
            url = f"https://api.github.com/repos/{repo}/issues?state=open"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                issues = res.json()
                # Pull Request는 API 상에서 issue로도 조회되므로 pull_request 키가 없는 순수 이슈만 필터링
                return [i for i in issues if "pull_request" not in i]
            else:
                print(f"[!] 이슈 API 요청 실패 (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] GitHub API 요청 중 오류 발생: {e}")
            
    return None

def close_github_issue(repo, issue_number, comment, token=None):
    """이슈 완료 코멘트를 달고 닫기"""
    # 1. gh CLI 사용
    if check_gh_cli():
        try:
            # 코멘트 추가 및 닫기
            subprocess.run(
                ["gh", "issue", "close", str(issue_number), "--repo", repo, "--comment", comment],
                check=True
            )
            print(f"[+] gh CLI를 통해 이슈 #{issue_number}를 성공적으로 닫았습니다.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] gh CLI로 이슈 #{issue_number} 닫기 실패: {e}")

    # 2. 토큰 기반 GitHub API 사용
    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            # 코멘트 달기
            comment_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            requests.post(comment_url, headers=headers, json={"body": comment}, timeout=10)
            
            # 이슈 닫기
            issue_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
            res = requests.patch(issue_url, headers=headers, json={"state": "closed"}, timeout=10)
            if res.status_code == 200:
                print(f"[+] API를 통해 이슈 #{issue_number}를 성공적으로 닫았습니다.")
                return True
            else:
                print(f"[!] API로 이슈 #{issue_number} 닫기 실패 (HTTP {res.status_code})")
        except Exception as e:
            print(f"[!] API 이슈 닫기 중 오류 발생: {e}")
            
    return False

def main():
    repo = get_repo_name()
    token = get_github_token()
    
    print(f"[*] 타겟 리포지토리: {repo}")
    
    if not check_gh_cli() and not token:
        print("[!] 에러: GitHub CLI(gh)에 로그인되어 있지 않고, .env에 GH_TOKEN(또는 GITHUB_TOKEN)도 설정되어 있지 않습니다.")
        print("    로컬에서 이슈를 제어하기 위해 gh CLI 로그인 혹은 토큰 환경변수가 필수적입니다.")
        sys.exit(1)
        
    issues = get_open_issues(repo, token)
    if issues is None:
        print("[-] 이슈 목록을 성공적으로 가져오지 못했습니다.")
        sys.exit(1)
        
    if not issues:
        print("[*] 현재 열려있는 이슈가 없습니다.")
        sys.exit(0)
        
    # 유튜브 링크가 포함된 이슈 필터링
    youtube_pattern = re.compile(r"(?:youtube\.com|youtu\.be)")
    target_issues = []
    
    for issue in issues:
        title = issue.get("title", "")
        if youtube_pattern.search(title):
            target_issues.append(issue)
            
    if not target_issues:
        print("[*] 유튜브 링크가 제목에 포함된 열려있는 이슈가 없습니다.")
        sys.exit(0)
        
    print(f"[+] 처리할 타겟 이슈 {len(target_issues)}개를 감지했습니다.")
    
    for idx, issue in enumerate(target_issues, 1):
        num = issue.get("number")
        title = issue.get("title", "").strip()
        body = issue.get("body", "") or ""
        body = body.strip()
        
        print(f"\n--- [{idx}/{len(target_issues)}] 이슈 #{num} 처리 시작 ---")
        print(f"● 이슈 제목 (유튜브 링크): {title}")
        print(f"● 이슈 본문 (정리 취지): {body[:80]}..." if len(body) > 80 else f"● 이슈 본문: {body}")
        
        # 1. 스크립트 요약 실행
        print("[*] 1단계: fetch_and_summery.py 실행 중...")
        res_summary = subprocess.run(["python", "fetch_and_summery.py", title, body])
        if res_summary.returncode != 0:
            print(f"[!] 이슈 #{num} 요약 과정에서 실패했습니다. 다음 이슈로 넘어갑니다.")
            continue
            
        # 2. 정적 사이트 빌드
        print("[*] 2단계: generate.py 정적 사이트 빌드 중...")
        res_gen = subprocess.run(["python", "generate.py"])
        if res_gen.returncode != 0:
            print(f"[!] 이슈 #{num} 빌드 과정에서 실패했습니다. 다음 이슈로 넘어갑니다.")
            continue
            
        # 3. 변경 사항 Git Commit & Push
        print("[*] 3단계: Git 변경사항 Commit & Push 중...")
        try:
            subprocess.run(["git", "add", "."], check=True)
            # 변경사항 확인
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
            if diff_res.returncode != 0: # 변경 사항이 있는 경우
                commit_msg = f"feat: Auto-update from local issue worker #{num}"
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
                subprocess.run(["git", "push", "origin", "main"], check=True)
                print("[+] 원격 리포지토리에 변경사항을 커밋 및 푸시 완료했습니다.")
            else:
                print("[-] 변경된 데이터가 없어 커밋을 건너뜁니다.")
        except subprocess.CalledProcessError as e:
            print(f"[!] Git 작업 중 에러 발생: {e}. 다음 이슈로 넘어갑니다.")
            continue
            
        # 4. 이슈 종결
        comment = (
            f"로컬 이슈 워커를 통해 자동으로 요약 분석 및 PPTX 생성이 완료되었습니다!\n"
            f"GitHub Pages 배포가 완료되면 반영됩니다."
        )
        close_github_issue(repo, num, comment, token)
        print(f"--- 이슈 #{num} 처리 완료 ---")

if __name__ == "__main__":
    main()
