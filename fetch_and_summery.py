import os
import sys
import json
import re
import requests
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# .env 파일에서 환경 변수 로드
load_dotenv()

def get_youtube_title(video_id: str) -> str:
    """oEmbed API를 통해 유튜브 비디오 제목을 수집"""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("title", "")
    except Exception as e:
        print(f"[-] 유튜브 제목 추출 중 오류 발생: {e}")
    return ""

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
        print(f"[-] 유튜브 통계 수집 중 오류 발생: {e}")
    return 0, "0"

# ==========================================
# 1. Gemini 구조화된 출력(Structured Output) 정의
# ==========================================
class BlogSection(BaseModel):
    heading: str = Field(description="블로그 본문 섹션의 소제목 (딱딱한 보고서 제목 대신, 글쓴이의 시선과 궁금증이 담긴 자연스러운 소제목. 예: '1. 왜 다들 힘들다는데 여기만 잘 나갈까?')")
    content: str = Field(description="해당 소제목에 대한 본문 (글쓴이가 직접 영상을 보고 정리하며 자신의 생각과 느낌을 녹여낸 1인칭 블로그 문체, 2~3개 문단, 문단 간에는 반드시 '\\n\\n' 줄바꿈 사용. 영상 속 구체적인 사례·수치·발언 맥락을 짚으면서도 '솔직히 이 부분이 인상 깊었다', '내 생각에는~' 같은 개인적 감상과 해석을 자연스럽게 섞어 서술)")
    key_quote: str = Field(description="이 섹션을 읽고 글쓴이 머릿속에 콕 박힌 한 줄 생각이나 핵심 문장 (블로그 인용구 박스에 들어갈 문장)")

class VideoAnalysis(BaseModel):
    title: str = Field(description="영상의 핵심 주제를 반영한 매력적인 한국어 제목")
    overview: str = Field(description="영상의 전체적인 내용을 2~3문장으로 명확하게 정리한 한국어 개요 (갤러리 카드 및 PPT 표지용)")
    points: list[str] = Field(description="영상의 핵심 인사이트 딱 3개 리스트 (한국어, PPT 슬라이드용). 각 항목은 반드시 '핵심 주제 및 요약 제목: 이에 대한 명확한 근거와 상세 디테일 설명' 포맷이어야 함 (예: '마케팅 혁신: 직원 브랜딩과 소통을 중심으로 강력한 팬덤을 형성하여 수익을 극대화함')")
    blog_intro: str = Field(description="블로그 포스트의 도입부(서론). 글쓴이가 이 영상을 왜 보게 되었는지, 보면서 처음 든 생각이나 공감이 무엇이었는지 친구에게 이야기하듯 자연스럽게 여는 1~2문단 (문단 간 '\\n\\n' 구분)")
    blog_sections: list[BlogSection] = Field(description="영상의 흐름과 핵심 주제를 글쓴이의 시선으로 풀어내는 3~5개의 블로그 본론 섹션 리스트. 단순 요약이 아니라 영상을 보고 느낀 점, 공감되거나 의문이 든 지점을 구체적 근거와 함께 진솔하게 작성")
    blog_conclusion: str = Field(description="블로그 포스트의 마무리(결론). 영상을 다 보고 나서 남은 개인적인 여운, 내 삶이나 일에 적용해보고 싶은 생각, 솔직한 다짐을 담은 1~2문단 (문단 간 '\\n\\n' 구분)")
    category: str = Field(description="영상의 장르나 대분류 (예: 개발, AI, 생산성, 경제, 비즈니스, 트렌드 등 1개 단어)")
    keywords: str = Field(description="쉼표(,)로 구분된 관련 핵심 키워드 3~6개 (예: 머신러닝, 자동화, 파이썬)")
    filename: str = Field(description="영어 소문자와 대시(-)로만 구성된 유니크한 파일명 (예: intro-to-gemini-api)")
    recommendation: str = Field(description="내가 직접 보고 추천하는 느낌으로, 이 영상을 왜 보면 좋은지 솔직한 감상과 얻을 수 있는 점을 2~3문장으로 담은 따뜻한 한국어 추천 문구")

def get_youtube_id(url: str) -> str:
    """유튜브 URL에서 video_id를 추출하는 헬퍼 함수"""
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_youtube_script(video_id: str) -> str:
    """YouTube 자막을 추출하여 하나의 문자열로 결합"""
    try:
        ytt_api = YouTubeTranscriptApi()
        # 한국어 자막 우선 시도 후, 없을 경우 영어 자막 시도
        try:
            transcript = ytt_api.fetch(video_id, languages=['ko'])
        except NoTranscriptFound:
            transcript = ytt_api.fetch(video_id, languages=['en'])
            
        full_script = " ".join([item.text for item in transcript])
        return full_script
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"[-] 경고: 해당 영상({video_id})은 자막을 지원하지 않거나 스크립트를 가져올 수 없습니다.")
        return ""
    except Exception as e:
        print(f"[-] 자막 추출 중 오류 발생: {e}")
        return ""

def analyze_script_with_gemini(script_text: str, video_id: str, user_context: str = "", video_title: str = "") -> dict:
    """Gemini API를 사용하여 구조화된 JSON 데이터로 분석결과 수신"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[-] 에러: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    title_context = f"\n    [원본 유튜브 영상 제목]\n    {video_title}\n" if video_title else ""
    
    prompt = f"""
    당신은 유튜브 영상을 깊이 있게 시청한 뒤, 개인 블로그에 자신의 솔직한 생각과 느낌을 담아 글을 쓰는 1인칭 블로거입니다.
    남이 써준 칼럼이나 AI 요약본처럼 딱딱하게 쓰지 말고, 내가 직접 영상을 보며 고개를 끄덕였거나 놀랐던 지점, 내 생각과 감정이 생생하게 묻어나는 글로 한국어 스키마를 채워주세요.

    [작성 가이드라인]
    1. 구체적 디테일 + 개인적 시선: 영상 속 구체적인 사례, 비유, 수치, 핵심 논거를 빠짐없이 담되, 사실을 나열하는 데 그치지 말고 그 대목에서 느낀 점이나 개인적인 해석('이 대목에서 솔직히 좀 놀랐다', '곰곰이 생각해보니~', '개인적으로는 이 부분이 제일 크게 와닿았다')을 자연스럽게 녹여내세요.
    2. 내가 직접 쓴 듯한 블로그 문체 (`blog_intro`, `blog_sections`, `blog_conclusion`):
       - 딱딱한 보도자료·AI 칼럼 문체('~입니다/합니다' 일변도, '시사하는 바가 큽니다', '여러분은 어떻게 생각하십니까?' 같은 뻔한 상투어)를 피하세요.
       - 실제로 내가 쓴 글처럼 편하고 진솔한 구어체/해요체('~해요', '~더라고요', '~거든요', '~인 것 같아요' 등)를 자연스럽게 섞어 문장 호흡을 살리세요.
       - `blog_intro`: 이 영상을 보게 된 계기나 첫인상, 보면서 들었던 문제의식이나 호기심을 내 이야기로 자연스럽게 열어주세요.
       - `blog_sections`: 영상의 핵심 흐름을 3~5개의 소주제로 나누어 소제목(`heading`), 2~3문단의 본문(`content`, 문단 간 `\\n\\n` 줄바꿈 필수), 내 머릿속에 남은 한 줄 생각(`key_quote`)을 작성하세요.
       - `blog_conclusion`: 영상을 다 보고 난 뒤의 솔직한 소감, 내 일상이나 일에 비추어 본 생각과 여운으로 담백하게 마무리하세요.
    3. 발표자료(PPTX)용 3대 핵심 요약 (`overview`, `points`):
       - `overview`와 `points`(3개)는 슬라이드와 요약 카드에 들어갈 항목이므로, 핵심만 명확하고 밀도 있게 정리하세요.
{title_context}
    [유튜브 자막 스크립트]
    {script_text[:50000]}
    """
    
    if user_context and user_context.strip():
        prompt += f"""
        
        [글쓴이의 핵심 생각 및 정리 취지]
        {user_context}
        
        위 [글쓴이의 핵심 생각 및 정리 취지]는 글쓴이 본인이 직접 남긴 생각과 감정입니다. 이를 글의 중심축으로 삼아, `blog_intro`, `blog_sections`, `blog_conclusion`, `recommendation` 전반에 글쓴이의 느낌과 주관, 관점이 강하고 진솔하게 드러나도록 작성하세요.
        """
    
    import time
    models_to_try = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash']
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=VideoAnalysis,
                        temperature=0.6
                    ),
                )
                result = json.loads(response.text)
                result['youtube_id'] = video_id
                return result
            except Exception as e:
                err_str = str(e)
                print(f"[-] Gemini API 요청 중 오류 발생 ({model_name}, 시도 {attempt+1}/3): {e}")
                if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(5 * (attempt + 1))
                else:
                    break
    return None

def update_videos_json(new_video_data: dict, issue_number: int = None, json_path: str = "data/videos.json"):
    """결과 데이터를 기존 data/videos.json에 추가 또는 업데이트"""
    # 디렉토리 자동 생성
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    
    if issue_number:
        new_video_data['issue_number'] = issue_number
        
    videos_list = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                videos_list = json.load(f)
                if not isinstance(videos_list, list):
                    videos_list = []
        except json.JSONDecodeError:
            print("[!] 기존 json 파일이 손상되었거나 비어있어 새로 초기화합니다.")
            videos_list = []

    # 동일한 youtube_id가 있다면 업데이트, 없다면 신규 추가
    existing_index = next((i for i, v in enumerate(videos_list) if v.get('youtube_id') == new_video_data['youtube_id']), None)
    
    if existing_index is not None:
        # 기존 필드 유지 (예: issue_number, views, likes 등)
        for key in list(videos_list[existing_index].keys()):
            if key not in new_video_data:
                new_video_data[key] = videos_list[existing_index][key]
        videos_list[existing_index] = new_video_data
        print(f"[+] 기존 영상 데이터를 업데이트했습니다: {new_video_data['title']}")
    else:
        videos_list.append(new_video_data)
        print(f"[+] 새 영상 데이터를 성공적으로 추가했습니다: {new_video_data['title']}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(videos_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python fetch_and_summarize.py <유튜브_링크> [요약_취지] [이슈_번호]")
        sys.exit(1)
        
    youtube_url = sys.argv[1]
    user_context = sys.argv[2] if len(sys.argv) > 2 else ""
    issue_num_str = sys.argv[3] if len(sys.argv) > 3 else ""
    issue_num = int(issue_num_str) if issue_num_str and issue_num_str.isdigit() else None
    
    v_id = get_youtube_id(youtube_url)
    
    if not v_id:
        print("[-] 올바른 유튜브 링크 형태가 아닙니다.")
        sys.exit(1)
        
    print(f"[*] 유튜브 ID 추출 완료: {v_id}")
    if user_context:
        print(f"[*] 정리 취지: {user_context}")
    if issue_num:
        print(f"[*] 연동 이슈 번호: {issue_num}")
        
    print("[*] 자막(스크립트) 및 영상 제목 수집을 시작합니다...")
    video_title = get_youtube_title(v_id)
    script = fetch_youtube_script(v_id)
    
    if not script:
        print("[!] 자막(스크립트) 수집에 실패했습니다. (자막이 없는 영상일 수 있습니다.)")
        print("[*] 제목 및 취지 기반으로 AI 분석을 진행합니다...")
        if not video_title:
            video_title = "제목을 가져올 수 없는 비디오"
        script = f"(자막 정보 없음. 비디오 제목: {video_title})"
        
    print("[*] Gemini AI가 컨텐츠를 심층 분석하고 블로그 글 형태로 다듬는 중입니다...")
    analysis_result = analyze_script_with_gemini(script, v_id, user_context, video_title=video_title)
    
    if analysis_result:
        views, likes = fetch_youtube_stats(v_id)
        analysis_result['views'] = views
        analysis_result['likes'] = likes
        update_videos_json(analysis_result, issue_num)
        print("[*] 모든 파이프라인 처리가 완료되었습니다. 'data/videos.json'을 확인하세요.")
    else:
        print("[-] 분석 실패.")
        sys.exit(1)
