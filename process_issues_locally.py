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
            is_collab = (res.status_code == 204)
            _collaborator_cache[username] = is_collab
            return is_collab
        except Exception:
            pass

    return False

def get_all_issues(repo, token=None):
    """열려있거나 닫혀있는 리포지토리의 모든 이슈 수집"""
    if check_gh_cli():
        try:
            print("[*] GitHub CLI(gh)를 사용하여 전체 이슈 목록을 불러옵니다...")
            res = subprocess.run(
                ["gh", "issue", "list", "--repo", repo, "--state", "all", "--limit", "100", "--json", "number,title,body,author,state"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            return json.loads(res.stdout)
        except Exception as e:
            print(f"[!] gh CLI로 전체 이슈를 가져오는 중 오류 발생: {e}")

    if token:
        try:
            print("[*] GitHub API (HTTP)를 사용하여 전체 이슈 목록을 불러옵니다...")
            url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                issues = res.json()
                return [i for i in issues if "pull_request" not in i]
            else:
                print(f"[!] 전체 이슈 API 요청 실패 (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[!] GitHub API 요청 중 오류 발생: {e}")
            
    return []

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

def create_issue(repo, title, body, token=None):
    """GitHub에 새로운 이슈를 생성하고 생성된 이슈 정보를 반환"""
    if check_gh_cli():
        try:
            res = subprocess.run(
                ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body, "--json", "number,url"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            data = json.loads(res.stdout)
            return data.get("number"), data.get("url")
        except Exception:
            pass

    if token:
        try:
            url = f"https://api.github.com/repos/{repo}/issues"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.post(url, headers=headers, json={"title": title, "body": body}, timeout=10)
            if res.status_code == 201:
                data = res.json()
                return data.get("number"), data.get("html_url")
        except Exception:
            pass
            
    return None, None

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
        
    # 1. 원격의 모든 이슈 목록 조회
    issues = get_all_issues(repo, token)
    
    # 2. 유튜브 ID 추출 정규식
    youtube_pattern = re.compile(
        r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    )
    
    # 원격 이슈를 파싱하여 youtube_id -> issue 객체 맵 작성
    issue_by_ytid = {}
    for issue in issues:
        title = issue.get("title", "")
        match = youtube_pattern.search(title)
        if match:
            ytid = match.group(1)
            # 동일 유튜브 영상 이슈가 중복되면 더 낮은 번호(최초 이슈)를 우선 맵핑
            if ytid not in issue_by_ytid or issue.get("number") < issue_by_ytid[ytid].get("number"):
                issue_by_ytid[ytid] = issue

    # 3. 로컬 videos.json 데이터 로드
    videos_path = "data/videos.json"
    videos = []
    if os.path.exists(videos_path):
        try:
            with open(videos_path, "r", encoding="utf-8") as f:
                videos = json.load(f)
        except Exception:
            videos = []

    videos_updated = False
    
    # ==========================================
    # 동기화 방향 1: Videos ➔ GitHub (이슈 매핑 교정 및 신규 이슈 생성)
    # ==========================================
    print("\n[*] 1단계 동기화 검증: 로컬 비디오 데이터 ➔ 원격 이슈 매핑 검증 중...")
    for video in videos:
        ytid = video.get("youtube_id")
        title = video.get("title")
        if not ytid:
            continue
            
        if ytid in issue_by_ytid:
            actual_num = issue_by_ytid[ytid].get("number")
            # 이슈 번호 매핑 교정
            if video.get("issue_number") != actual_num:
                print(f"[▲] 교정: 비디오 '{title}'의 이슈 번호를 #{video.get('issue_number')}에서 실제 원격 번호 #{actual_num}로 자동 변경합니다.")
                video["issue_number"] = actual_num
                videos_updated = True
        else:
            # 원격에 매핑된 이슈가 없는 경우 ➔ 새로 생성하여 양방향 링크 성립
            print(f"[!] 경고: 비디오 '{title}'({ytid})에 대응하는 이슈가 깃허브에 존재하지 않습니다. 새로 생성합니다...")
            title_url = f"https://www.youtube.com/watch?v={ytid}"
            body_txt = f"(로컬 비디오 데이터 '{title}'에서 유실 복구 목적으로 자동 생성한 이슈입니다.)"
            num, url = create_issue(repo, title_url, body_txt, token)
            if num:
                print(f"[+] 이슈 자동 생성 성공: #{num} -> {url}")
                comment = "로컬 비디오 데이터 복구를 위해 자동 생성되어 곧바로 클로즈 처리됩니다."
                close_github_issue(repo, num, comment, token)
                
                # 메타데이터에 매핑
                video["issue_number"] = num
                videos_updated = True
                
                # 메모리 캐시 정보 동기화
                issue_by_ytid[ytid] = {"number": num, "title": title_url, "state": "closed"}
            else:
                print(f"[-] 이슈 생성 실패: '{title}'")

    if videos_updated:
        # 갱신된 데이터를 videos.json에 저장
        with open(videos_path, "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=4)
        print("[+] 1단계 동기화 완료: videos.json 파일이 갱신되었습니다.")

    # ==========================================
    # 동기화 방향 2: GitHub ➔ Videos (원격 이슈 감지하여 로컬 요약 추가)
    # ==========================================
    print("\n[*] 2단계 동기화 검증: 원격 이슈 ➔ 로컬 비디오 누락 체크 중...")
    
    # 깃허브에 올라온 이슈 중 videos.json에 데이터가 누락된 리스트 검사
    existing_ytids = {v.get("youtube_id") for v in videos if v.get("youtube_id")}
    any_video_added = False

    for ytid, issue in issue_by_ytid.items():
        if ytid not in existing_ytids:
            num = issue.get("number")
            title = issue.get("title", "").strip()
            body = issue.get("body", "") or ""
            body = body.strip()
            
            # 작성자 롤(Role) 판단
            author_data = issue.get("author") or issue.get("user")
            author = author_data.get("login") if isinstance(author_data, dict) else author_data
            
            print(f"\n● 이슈 #{num} ({title})이 원격에 존재하나 로컬 데이터가 누락되었습니다.")
            is_collab = is_collaborator(repo, author, token)
            
            user_context = ""
            should_process = False
            
            if is_collab:
                print(f"  -> 승인된 사용자({author})가 등록한 이슈입니다. 즉시 로컬로 가져옵니다.")
                user_context = body
                should_process = True
            else:
                print(f"  -> 일반 사용자({author})의 이슈입니다. 관리자 답변 코멘트를 조회합니다...")
                comments = get_issue_comments(repo, num, token)
                
                admin_comments = []
                bot_waiting_comment_exists = False
                
                for comment in comments:
                    c_author_data = comment.get("author") or comment.get("user")
                    c_author = c_author_data.get("login") if isinstance(c_author_data, dict) else c_author_data
                    c_body = comment.get("body", "") or ""
                    
                    if "소유자나 Collaborator가 이슈에 답변 코멘트를 등록하면" in c_body:
                        bot_waiting_comment_exists = True
                        
                    if is_collaborator(repo, c_author, token):
                        admin_comments.append(c_body)
                        
                if admin_comments:
                    user_context = admin_comments[-1]
                    print(f"  -> 관리자의 답변 코멘트가 감지되었습니다. 처리를 승인합니다.")
                    should_process = True
                else:
                    print("  -> 아직 승인(관리자 답변)이 없어 데이터 수집을 스킵합니다.")
                    if not bot_waiting_comment_exists:
                        waiting_message = (
                            "👋 안녕하세요! 일반 사용자가 추천하신 영상의 자동 요약 및 퍼블리싱을 진행하려면, "
                            "이 리포지토리의 소유자나 Collaborator가 이슈에 답변 코멘트(취지 등)를 등록해야 합니다. "
                            "답변 코멘트가 달리면 요약 처리가 자동으로 시작됩니다."
                        )
                        add_github_comment(repo, num, waiting_message, token)
                        print("  -> 이슈에 대기 안내 코멘트를 작성했습니다.")
                    should_process = False
                    
            if should_process:
                print(f"[*] 요약 스크립트 실행 중 (fetch_and_summery.py)...")
                res_summary = subprocess.run(["python", "fetch_and_summery.py", title, user_context, str(num)])
                if res_summary.returncode == 0:
                    any_video_added = True
                    # videos.json 캐시를 루프 안에서 다시 불러옴
                    if os.path.exists(videos_path):
                        with open(videos_path, "r", encoding="utf-8") as f:
                            videos = json.load(f)
                        existing_ytids.add(ytid)
                        
                # 만약 원본 이슈가 열린(open) 상태였다면 자동으로 닫아줍니다.
                if issue.get("state") == "open":
                    comment = "요약 분석 및 정적 사이트 복구 빌드가 완료되어 이슈를 종료합니다."
                    close_github_issue(repo, num, comment, token)

    # ==========================================
    # 4단계: 최종 빌드 및 릴리즈 배포
    # ==========================================
    if videos_updated or any_video_added:
        print("\n[*] 3단계: 요약 데이터 변경이 감지되었습니다. 정적 사이트(generate.py) 빌드 중...")
        res_gen = subprocess.run(["python", "generate.py"])
        
        if res_gen.returncode == 0:
            print("[*] 4단계: Git 커밋 및 원격 저장소 푸시 중...")
            try:
                try:
                    subprocess.run(["git", "config", "user.name"], check=True, stdout=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])
                    subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
                
                subprocess.run(["git", "add", "."], check=True)
                diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
                if diff_res.returncode != 0:
                    subprocess.run(["git", "commit", "-m", "chore: Auto-sync videos metadata and remote issues"], check=True)
                    subprocess.run(["git", "push", "origin", "main"], check=True)
                    print("[+] 동기화 변경사항이 깃허브에 성공적으로 배포 완료되었습니다.")
                else:
                    print("[-] 변경된 파일 내역이 없어 푸시를 생략합니다.")
            except subprocess.CalledProcessError as e:
                print(f"[!] Git 동기화 푸시 중 에러 발생: {e}")
    else:
        print("\n[*] 동기화 완료: 로컬 데이터베이스와 원격 이슈 데이터가 완전히 일치하여 정적 사이트를 유지합니다.")

if __name__ == "__main__":
    main()
