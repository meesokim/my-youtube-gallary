# 🎬 YouTube 추천 영상 AI 요약 갤러리 & PPTX 생성기

[![Deploy to GitHub Pages](https://github.com/meesokim/my-youtube-gallary/actions/workflows/deploy.yml/badge.svg)](https://github.com/meesokim/my-youtube-gallary/actions/workflows/deploy.yml)

유튜브 추천 영상을 분석하여 핵심 내용을 잘 정리한 **PPTX 발표 자료**와 무설치로 슬라이드를 볼 수 있는 **HTML 프리뷰 및 재생 가능한 상세 요약 페이지**를 자동으로 빌드하고 배포하는 프로젝트입니다.

🔗 **GitHub Pages 실시간 사이트**: [https://meesokim.github.io/my-youtube-gallary](https://meesokim.github.io/my-youtube-gallary)

---

## ✨ 주요 기능
1. **유튜브 스크립트 기반 AI 요약**:
   - 영상의 한글/영문 자막 스크립트를 추출한 뒤, `Gemini 2.5 Flash` 모델을 사용해 한국어로 개요 및 주요 핵심 포인트를 요약합니다.
2. **원스톱 영상 정보 상세 페이지 생성**:
   - 상세 페이지 내에서 **유튜브 영상 직접 재생**이 가능합니다.
   - 분석 정보를 바탕으로 16:9 와이드스크린 레이아웃의 **발표용 PPTX 파일**을 생성 및 다운로드 링크를 제공합니다.
   - **HTML 슬라이드 프리뷰** 및 **Office Online 뷰어** 기능을 탑재하여 다운로드 없이 웹 브라우저 내에서 PPTX 내용을 즉시 열람할 수 있습니다.
3. **카테고리 필터 및 검색 인덱스 페이지**:
   - 수집된 모든 비디오 카드를 모아서 보는 `index.html`을 생성합니다.
   - 카테고리별 필터링 기능과 제목/키워드 실시간 검색 기능을 제공합니다.
4. **이슈(Issue) 연동 자동 배포 자동화**:
   - GitHub Issue에 유튜브 링크를 등록하면 GitHub Actions 봇이 자동으로 요약 정보를 수집하고 사이트를 갱신하여 GitHub Pages에 배포한 후 이슈를 자동으로 종결합니다.

---

## 🚀 로컬 테스트 방법 (Local Test)

로컬에서 테스트해볼 수 있도록 간편한 대화형 스크립트를 탑재하였습니다.

### 1. 사전 요구사항 및 설정
- Python 3.10 이상이 필요합니다.
- 의존성 패키지를 설치합니다:
  ```bash
  pip install -r requirements.txt
  ```
- 프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래와 같이 Gemini API Key를 등록합니다:
  ```env
  GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
  ```

### 2. 로컬 테스트 스크립트 실행
아래 스크립트를 구동하여 간편하게 유튜브 영상 정보를 요약하고 웹 페이지를 생성할 수 있습니다:
```bash
./run_local_test.sh
```
- 스크립트를 실행하면 **유튜브 영상 링크**와 **정리 취지**를 묻는 프롬프트가 실행됩니다.
- 분석과 빌드가 성공하면, 안내에 따라 `y`를 입력해 로컬 웹 서버(`http://localhost:8000`)를 실행하고 즉시 웹브라우저로 결과물을 확인해 보실 수 있습니다.

---

## 🛠️ GitHub Actions 자동화 사용법 (Issue Trigger)

이슈 등록만으로 새로운 비디오 요약 카드를 배포하려면 아래 가이드대로 **최초 1회 설정**을 마쳐야 합니다.

### 1. GitHub 리포지토리 필수 설정
1. **Gemini API Key 등록**:
   - 리포지토리 **`Settings`** ➔ **`Secrets and variables`** ➔ **`Actions`**로 이동합니다.
   - **`New repository secret`**을 눌러 이름에 **`GEMINI_API_KEY`**, 값에 본인의 API Key를 저장합니다.
2. **GitHub Actions 쓰기 권한 부여**:
   - 리포지토리 **`Settings`** ➔ **`Actions`** ➔ **`General`**로 이동합니다.
   - 최하단 **`Workflow permissions`**에서 **`Read and write permissions`** 라디오 버튼을 체크하고 저장합니다.

### 2. 신규 추천 비디오 이슈로 추가하기
- 리포지토리의 **`Issues`** 탭에서 **`New Issue`**를 만듭니다.
- **제목**: 요약할 유튜브 영상 주소를 입력합니다. (예: `https://www.youtube.com/watch?v=LKKTAJytBRo`)
- **본문**: 해당 영상을 추천하는 이유나 특별히 강조해서 요약하고 싶은 취지를 적어줍니다.
- **결과**: 이슈가 등록되면 Actions 봇이 실행되어 자동으로 영상을 요약해 `docs/` 폴더에 반영 및 GitHub Pages로 릴리즈 후 이슈를 자동으로 닫습니다.

---

## 📂 파일 구조 설명
- `fetch_and_summery.py`: 자막 수집 및 Gemini 구조화(Structured JSON) 데이터 추출 스크립트.
- `generate.py`: 수집된 데이터를 바탕으로 `docs` 폴더 내에 PPTX 파일, 상세 HTML, 메인 index.html을 빌드하는 스크립트.
- `templates/`: 빌드에 사용되는 Jinja2 기반 HTML 템플릿들.
- `data/videos.json`: 현재까지 분석이 완료된 누적 비디오 데이터 저장소.
- `docs/`: 실제 GitHub Pages를 통해 외부로 서비스되는 정적 파일 배포 경로.
