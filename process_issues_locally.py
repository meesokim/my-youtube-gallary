import os
import re
import sys
import subprocess
import json
import requests
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 캐시를 사용해 중복 API 조회를 방지
_collaborator_cache = {}

def get_repo_name():
    """git remote URL로부터 'owner/repo' 추출"""
    try:
        url = subprocess.check_output(["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
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

def is_collaborator(repo, username, token=None):
    """지정된 사용자가 리포지토리의 오너 혹은 Collaborator인지 여부 판별"""
    if not username:
        return False
        
    owner = repo.split('/')[0]
    if username.lower() == owner.lower():
        return True
        
    # 캐시 확인
    if username in _collaborator_cache:
        return _collaborator_cache[username]

    # 1. gh CLI 사용
    if check_gh_cli():
        try:
            res = subprocess.run(
                ["gh", "api", f"repos/{repo}/collaborators/{username}", "--silent"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            is_collab = (res.returncode == 0)
            _collaborator_cache[username] = is_collab
            return is_collab
        except Exception:
            pass

    # 2. GitHub API 사용
    if token:
        try:
            url = f"https://api.github.com/repos/{repo}/collaborators/{username}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.get(url, headers=headers, timeout=5)
            # 204 No Content면 Collaborator임, 404면 아님
            is_collab = (res.status_code == 204)
            _collaborator_cache[username] = is_collab
            return is_collab
        except Exception:
            pass

    # 권한 판단이 불가한 경우 기본값 False
    return False

def get_open_issues(repo, token=None):
    """열려있는 이슈 목록 조회"""
    if check_gh_cli():
        try:
            print("[*] GitHub CLI(gh)를 사용하여 이슈 목록을 불러옵니다...")
            res = subprocess.run(
                ["gh", "issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,body,author"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            return json.loads(res.stdout)
        except Exception as e:
            print(f"[!] gh CLI로 이슈를 가져오는 중 오류 발생: {e}")

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
                return [i for i in issues if "pull_request" not in i]
            else:
                print(f"[!] 이슈 API 요청 실패 (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] GitHub API 요청 중 오류 발생: {e}")
            
    return None

def get_issue_comments(repo, issue_number, token=None):
    """특정 이슈의 코멘트 목록 조회"""
    if check_gh_cli():
        try:
            res = subprocess.run(
                ["gh", "api", f"repos/{repo}/issues/{issue_number}/comments", "--json", "author,body"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            return json.loads(res.stdout)
        except Exception:
            pass

    if token:
        try:
            url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
            
    return []

def add_github_comment(repo, issue_number, comment_body, token=None):
    """이슈에 코멘트 추가"""
    if check_gh_cli():
        try:
            subprocess.run(
                ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", comment_body],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            res = requests.post(url, headers=headers, json={"body": comment_body}, timeout=10)
            return res.status_code == 201
        except Exception:
            pass
    return False

def close_github_issue(repo, issue_number, comment, token=None):
    """이슈 완료 코멘트를 달고 닫기"""
    if check_gh_cli():
        try:
            subprocess.run(
                ["gh", "issue", "close", str(issue_number), "--repo", repo, "--comment", comment],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"[+] gh CLI를 통해 이슈 #{issue_number}를 성공적으로 닫았습니다.")
            return True
        except Exception as e:
            print(f"[!] gh CLI로 이슈 #{issue_number} 닫기 실패: {e}")

    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            comment_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            requests.post(comment_url, headers=headers, json={"body": comment}, timeout=10)
            
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
        sys.exit(1)
        
    issues = get_open_issues(repo, token)
    if issues is None:
        print("[-] 이슈 목록을 성공적으로 가져오지 못했습니다.")
        sys.exit(1)
        
    if not issues:
        print("[*] 현재 열려있는 이슈가 없습니다.")
        sys.exit(0)
        
    youtube_pattern = re.compile(r"(?:youtube\.com|youtu\.be)")
    target_issues = []
    
    for issue in issues:
        title = issue.get("title", "")
        if youtube_pattern.search(title):
            target_issues.append(issue)
            
    if not target_issues:
        print("[*] 유튜브 링크가 제목에 포함된 열려있는 이슈가 없습니다.")
        sys.exit(0)
        
    print(f"[+] 처리할 후보 이슈 {len(target_issues)}개를 감지했습니다.")
    
    processed_count = 0
    
    for idx, issue in enumerate(target_issues, 1):
        num = issue.get("number")
        title = issue.get("title", "").strip()
        body = issue.get("body", "") or ""
        body = body.strip()
        
        # 작성자 추출 (하이브리드 대응)
        author_data = issue.get("author") or issue.get("user")
        author = author_data.get("login") if isinstance(author_data, dict) else author_data
        
        print(f"\n--- [{idx}/{len(target_issues)}] 이슈 #{num} 검사 시작 (작성자: {author}) ---")
        
        # 권한 확인
        is_collab = is_collaborator(repo, author, token)
        
        user_context = ""
        should_process = False
        
        if is_collab:
            print(f"[+] 승인된 사용자({author})가 등록한 이슈입니다. 즉시 처리를 시작합니다.")
            user_context = body
            should_process = True
        else:
            print(f"[*] 일반 사용자({author})가 등록한 이슈입니다. 관리자(Collaborator)의 답변 코멘트를 확인합니다...")
            comments = get_issue_comments(repo, num, token)
            
            # 협업자가 쓴 답변 코멘트 찾기 (가장 최신 것)
            admin_comments = []
            bot_waiting_comment_exists = False
            
            for comment in comments:
                c_author_data = comment.get("author") or comment.get("user")
                c_author = c_author_data.get("login") if isinstance(c_author_data, dict) else c_author_data
                c_body = comment.get("body", "") or ""
                
                # 봇이 이미 남겨둔 대기 안내문이 있는지 검사
                if "소유자나 Collaborator가 이슈에 답변 코멘트를 등록하면" in c_body:
                    bot_waiting_comment_exists = True
                    
                if is_collaborator(repo, c_author, token):
                    admin_comments.append((c_author, c_body))
                    
            if admin_comments:
                # 가장 최근에 달린 관리자 답변
                latest_admin, latest_comment = admin_comments[-1]
                print(f"[+] 관리자({latest_admin})의 답변 코멘트를 확인했습니다: \"{latest_comment[:40]}...\"")
                user_context = latest_comment
                should_process = True
            else:
                print("[-] 아직 관리자(Collaborator)의 답변 코멘트가 등록되지 않아 처리를 보류합니다.")
                # 대기 안내문이 없다면 안내 코멘트 등록 (최초 1회만)
                if not bot_waiting_comment_exists:
                    waiting_message = (
                        "👋 안녕하세요! 일반 사용자가 추천하신 영상의 자동 요약 및 퍼블리싱을 진행하려면, "
                        "이 리포지토리의 소유자나 Collaborator가 이슈에 답변 코멘트(취지 등)를 등록해야 합니다. "
                        "답변 코멘트가 달리면 요약 처리가 자동으로 시작됩니다."
                    )
                    add_github_comment(repo, num, waiting_message, token)
                    print("[+] 이슈에 관리자 대기 안내 코멘트를 달았습니다.")
                should_process = False
                
        if not should_process:
            continue
            
        # 1. 스크립트 요약 실행
        print("[*] 1단계: fetch_and_summery.py 실행 중...")
        res_summary = subprocess.run(["python", "fetch_and_summery.py", title, user_context, str(num)])
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
            # Actions 환경 등에서 git config가 안 잡혀있을 때를 위한 자동 보안
            try:
                subprocess.run(["git", "config", "user.name"], check=True, stdout=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])
                subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
                
            subprocess.run(["git", "add", "."], check=True)
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
            if diff_res.returncode != 0:
                commit_msg = f"feat: Auto-update from issue #{num}"
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
            f"요약 분석 및 PPTX 생성이 완료되었습니다!\n"
            f"배포 완료 후 사이트에 반영됩니다."
        )
        close_github_issue(repo, num, comment, token)
        print(f"--- 이슈 #{num} 처리 완료 ---")
        processed_count += 1
        
    print(f"\n[*] 총 {processed_count}개의 이슈가 성공적으로 처리되었습니다.")

if __name__ == "__main__":
    main()
