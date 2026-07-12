import os
import sys
import json
import re
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# .env 파일에서 환경 변수 로드
load_dotenv()

# ==========================================
# 1. Gemini 구조화된 출력(Structured Output) 정의
# ==========================================
class VideoAnalysis(BaseModel):
    title: str = Field(description="영상의 핵심 주제를 반영한 한국어 제목")
    overview: str = Field(description="영상의 전체적인 내용을 2~3문장으로 명확하게 정리한 한국어 개요")
    points: list[str] = Field(description="영상의 핵심 요약 및 디테일한 설명 3~5개 리스트 (한국어)")
    category: str = Field(description="영상의 장르나 대분류 (예: 개발, AI, 생산성, 경제, 트렌드 등 1개 단어)")
    keywords: str = Field(description="쉼표(,)로 구분된 관련 핵심 키워드 3~5개 (예: 머신러닝, 자동화, 파이썬)")
    filename: str = Field(description="영어 소문자와 대시(-)로만 구성된 유니크한 파일명 (예: intro-to-gemini-api)")

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

def analyze_script_with_gemini(script_text: str, video_id: str) -> dict:
    """Gemini API를 사용하여 구조화된 JSON 데이터로 분석결과 수신"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[-] 에러: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    아래 제공된 유튜브 영상의 자막 스크립트를 분석하여 필요한 메타데이터 정보를 추출해주세요.
    반드시 지정된 스키마 구조에 맞추어 한국어로 자연스럽고 깔끔하게 요약해주어야 합니다.
    
    [유튜브 자막 스크립트]
    {script_text[:15000]} # 토큰 절약을 위한 슬라이싱 (필요시 조절)
    """
    
    try:
        # 최신 안정화 모델인 gemini-2.5-flash 활용
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoAnalysis,
                temperature=0.2
            ),
        )
        
        # JSON 문자열을 딕셔너리로 파싱
        result = json.loads(response.text)
        # 유튜브 연동을 위해 스크립트 레이어에서 추출한 id 강제 매핑
        result['youtube_id'] = video_id
        return result
    except Exception as e:
        print(f"[-] Gemini API 요청 중 오류 발생: {e}")
        return None

def update_videos_json(new_video_data: dict, json_path: str = "data/videos.json"):
    """결과 데이터를 기존 data/videos.json에 추가 또는 업데이트"""
    # 디렉토리 자동 생성
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    
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
        videos_list[existing_index] = new_video_data
        print(f"[+] 기존 영상 데이터를 업데이트했습니다: {new_video_data['title']}")
    else:
        videos_list.append(new_video_data)
        print(f"[+] 새 영상 데이터를 성공적으로 추가했습니다: {new_video_data['title']}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(videos_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python fetch_and_summarize.py <유튜브_링크>")
        sys.exit(1)
        
    youtube_url = sys.argv[1]
    v_id = get_youtube_id(youtube_url)
    
    if not v_id:
        print("[-] 올바른 유튜브 링크 형태가 아닙니다.")
        sys.exit(1)
        
    print(f"[*] 유튜브 ID 추출 완료: {v_id}")
    print("[*] 자막(스크립트) 수집을 시작합니다...")
    script = fetch_youtube_script(v_id)
    
    if not script:
        print("[-] 요약할 스크립트 텍스트가 부족하여 작업을 중단합니다.")
        sys.exit(1)
        
    print("[*] Gemini AI가 컨텐츠를 분석하고 요약하는 중입니다...")
    analysis_result = analyze_script_with_gemini(script, v_id)
    
    if analysis_result:
        update_videos_json(analysis_result)
        print("[*] 모든 파이프라인 처리가 완료되었습니다. 'data/videos.json'을 확인하세요.")
    else:
        print("[-] 분석 실패.")
