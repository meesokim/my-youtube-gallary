#!/bin/bash

# 에러 발생 시 즉시 중단
set -e

# .env 파일 존재 여부 확인
if [ ! -f .env ]; then
  echo "[!] .env 파일이 없습니다. GEMINI_API_KEY가 포함된 .env 파일을 생성해주세요."
  exit 1
fi

echo "============================================="
echo " YouTube 추천 영상 AI 요약 갤러리 로컬 테스트"
echo "============================================="
echo ""

# 사용자 입력 받기
read -p "▶ 유튜브 영상 링크를 입력하세요: " YOUTUBE_URL
if [ -z "$YOUTUBE_URL" ]; then
  echo "[-] 에러: 유튜브 링크는 필수 입력 사항입니다."
  exit 1
fi

read -p "▶ 요약 및 정리 취지를 입력하세요 (엔터 치면 기본 요약): " USER_CONTEXT

echo ""
echo "[*] 1단계: 유튜브 자막 수집 및 Gemini AI 컨텐츠 분석 시작..."
python fetch_and_summery.py "$YOUTUBE_URL" "$USER_CONTEXT"

echo ""
echo "[*] 2단계: 갤러리 페이지 및 PPTX 파일 빌드 중..."
python generate.py

echo ""
echo "============================================="
echo "[+] 로컬 테스트 빌드가 완료되었습니다!"
echo "    - 갱신된 비디오 목록: data/videos.json"
echo "    - 빌드된 결과물 폴더: docs/"
echo "============================================="
echo ""

read -p "▶ 로컬 웹 서버(http://localhost:8000)를 실행해 브라우저로 확인하시겠습니까? (y/n): " RUN_SERVER

if [ "$RUN_SERVER" = "y" ] || [ "$RUN_SERVER" = "Y" ]; then
  echo ""
  echo "[*] http://localhost:8000 에서 로컬 웹 서버를 구동합니다."
  echo "    브라우저를 열어 http://localhost:8000 을 입력해 확인해 보세요!"
  echo "    (서버를 종료하려면 단말기에서 Ctrl + C 를 누르세요.)"
  echo ""
  python -m http.server 8000 --directory docs
fi
